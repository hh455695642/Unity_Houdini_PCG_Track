"""Cumulative, patch-independent contract validation for CityRoad.

Modes:

* ``--source live`` validates the current Houdini GUI before persistence.
* ``--source fresh`` loads the production HIP in this disposable hython
  process, creates a new locked instance from the production HDA, and validates
  the persisted definition.  The production HIP/HDA are never saved here.

Historical ``patch_cityroad_*`` modules are intentionally not imported.
"""

from __future__ import annotations

import argparse
import hashlib
import importlib
import json
import os
import math
from pathlib import Path
import sys
from typing import Any

import hou


SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = SCRIPT_DIR.parents[3]
DEFAULT_HDA = PROJECT_ROOT / "Assets/PCG/HDA/City/CityRoad.hda"
DEFAULT_HIP = PROJECT_ROOT / "HoudiniProject/PCG_Track_21.0.440/PCG_Bike_CityRoad.hip"
CONTRACT_PATH = SCRIPT_DIR.parent / "contracts/cityroad_contract.json"
ASSET_TYPE = "pcgbike::CityRoad::1.0"
LIVE_ASSET_PATH = "/obj/CityRoad_DEV"
CORE_NAME = "CityRoadCore"


class ContractFailure(RuntimeError):
    pass


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ContractFailure(message)


def detail_value(geometry: hou.Geometry, name: str, default: Any = None) -> Any:
    attribute = geometry.findGlobalAttrib(name)
    return geometry.attribValue(attribute) if attribute is not None else default


def require_node(core: hou.Node, name: str) -> hou.Node:
    node = core.node(name)
    require(node is not None, f"Missing required CityRoad node: {core.path()}/{name}")
    return node


def public_interface_hash(asset: hou.Node) -> str:
    definition = asset.type().definition()
    require(definition is not None, "CityRoad asset has no HDA definition")
    # Before persistence the approved public API exists only on the editable
    # Live instance.  Fresh/locked verification uses the definition verbatim.
    templates = definition.parmTemplateGroup() if asset.isLockedHDA() else asset.parmTemplateGroup()
    dialog = templates.asDialogScript()
    return hashlib.sha256(dialog.encode("utf-8")).hexdigest()


def load_contract() -> dict[str, Any]:
    contract = json.loads(CONTRACT_PATH.read_text(encoding="utf-8"))
    require(contract.get("schema_version") == 1, "Unsupported CityRoad contract schema")
    require(contract.get("asset_type") == ASSET_TYPE, "CityRoad contract type mismatch")
    return contract


def position_key(position, precision: int = 4) -> tuple[float, float, float]:
    return tuple(round(float(value), precision) for value in position)


def geometry_edges(geometry: hou.Geometry):
    positions = {
        point.number(): position_key(point.position()) for point in geometry.points()
    }
    edges = set()
    neighbors: dict[tuple[float, float, float], set[tuple[float, float, float]]] = {}
    for primitive in geometry.prims():
        vertices = primitive.vertices()
        count = len(vertices)
        for index in range(count):
            a = positions[vertices[index].point().number()]
            b = positions[vertices[(index + 1) % count].point().number()]
            if a == b:
                continue
            edge = tuple(sorted((a, b)))
            edges.add(edge)
            neighbors.setdefault(a, set()).add(b)
            neighbors.setdefault(b, set()).add(a)
    return edges, neighbors


def constraint_edges(geometry: hou.Geometry):
    result = []
    for primitive in geometry.prims():
        points = primitive.points()
        require(
            len(points) == 2,
            f"V10 constraint primitive {primitive.number()} is not a line")
        result.append(tuple(sorted((
            position_key(points[0].position()),
            position_key(points[1].position()),
        ))))
    return result


def bounds_by_piece(geometry: hou.Geometry, kind: str):
    result = {}
    for primitive in geometry.prims():
        kind_attrib = geometry.findPrimAttrib("topology_piece_kind")
        level_attrib = geometry.findPrimAttrib("road_level")
        piece_attrib = geometry.findPrimAttrib("topology_piece_id")
        if not (kind_attrib and level_attrib and piece_attrib):
            return {}
        if primitive.stringAttribValue(kind_attrib) != kind:
            continue
        key = (
            primitive.intAttribValue(level_attrib),
            primitive.intAttribValue(piece_attrib),
        )
        bounds = result.setdefault(key, hou.BoundingBox())
        for point in primitive.points():
            bounds.enlargeToContain(point.position())
    return result


def validate_network(asset: hou.Node, core: hou.Node, contract: dict[str, Any]) -> dict[str, Any]:
    actual_hash = public_interface_hash(asset)
    expected_hash = (
        contract["public_interface_sha256"]
        if asset.isLockedHDA()
        else contract.get("live_public_interface_sha256", contract["public_interface_sha256"])
    )
    require(expected_hash != "PENDING_CAPTURE", "CityRoad public interface baseline is not captured")
    require(
        actual_hash == expected_hash,
        "CityRoad public parameter interface changed: "
        f"actual={actual_hash} expected={expected_hash}")

    for name, expected_type in contract["required_nodes"].items():
        node = require_node(core, name)
        require(
            node.type().name() == expected_type,
            f"CityRoad node type changed: {name}={node.type().name()} expected={expected_type}")

    for name, expected_inputs in contract["required_connections"].items():
        node = require_node(core, name)
        actual_inputs = {
            str(connection.inputIndex()): connection.inputNode().name()
            for connection in node.inputConnections()
        }
        for index, source in expected_inputs.items():
            require(
                actual_inputs.get(index) == source,
                f"CityRoad connection changed: {name}[{index}]={actual_inputs.get(index)} expected={source}")

    for name, markers in contract["snippet_markers"].items():
        node = require_node(core, name)
        snippet = node.parm("snippet")
        require(snippet is not None, f"Required snippet parameter missing: {name}")
        source = snippet.evalAsString()
        for marker in markers:
            require(marker in source, f"Required CityRoad marker missing: {name}:{marker}")

    max_inputs = asset.type().maxNumInputs()
    require(
        max_inputs == contract["max_inputs"],
        "CityRoad input connector contract changed: "
        f"maxNumInputs={max_inputs} expected={contract['max_inputs']}")
    return {
        "public_interface_sha256": actual_hash,
        "required_node_count": len(contract["required_nodes"]),
        "max_inputs": max_inputs,
    }


def validate_outputs(core: hou.Node, contract: dict[str, Any]) -> dict[str, Any]:
    stats = {}
    for name in contract["output_nodes"]:
        node = require_node(core, name)
        try:
            node.cook(force=True)
        except Exception as exception:
            messages = list(node.errors())
            raise ContractFailure(
                f"CityRoad output cook failed at {node.path()}: "
                + " | ".join(messages or [str(exception)])) from exception
        require(not node.errors(), f"CityRoad output errors at {name}: {node.errors()}")
        require(not node.warnings(), f"CityRoad output warnings at {name}: {node.warnings()}")
        geometry = node.geometry()
        if name.startswith("OUT_STREET_"):
            require(len(geometry.points()) > 0, f"CityRoad street output is empty: {name}")
            require(len(geometry.prims()) == 0,
                    f"CityRoad street output must contain points only: {name}")
        else:
            require(len(geometry.prims()) > 0, f"CityRoad output is empty: {name}")
        stats[name] = {
            "points": len(geometry.points()),
            "primitives": len(geometry.prims()),
            "vertices": sum(len(primitive.vertices()) for primitive in geometry.prims()),
        }
    return stats


def _point_record(point: hou.Point) -> dict[str, Any]:
    geometry = point.geometry()
    def value(name: str, default=None):
        attribute = geometry.findPointAttrib(name)
        return point.attribValue(attribute) if attribute is not None else default
    return {
        "position": tuple(float(v) for v in point.position()),
        "instance": str(value("unity_instance", "")),
        "prefix": str(value("instance_prefix", "")),
        "kind": str(value("pcg_kind", "")),
        "group": str(value("pcg_group_key", "")),
        "corridor": int(value("pcg_corridor_id", -1)),
        "side": int(value("pcg_side", 0)),
        "variant": int(value("pcg_variant", -1)),
        "owner": int(value("pcg_owner_id", -1)),
        "tangent": tuple(float(v) for v in value("pcg_tangent", (0, 0, 1))),
        "distance": float(value("pcg_distance", -1.0)),
        "length": float(value("pcg_corridor_length", -1.0)),
        "orient": tuple(float(v) for v in value("orient", (0, 0, 0, 1))),
        "scale": float(value("pscale", -1.0)),
    }


def _street_records(node: hou.Node) -> list[dict[str, Any]]:
    node.cook(force=True)
    require(not node.errors(), f"Street output errors at {node.path()}: {node.errors()}")
    require(not node.warnings(), f"Street output warnings at {node.path()}: {node.warnings()}")
    geometry = node.geometry()
    require(detail_value(geometry, "unity_split_attr", "") == "pcg_group_key",
            f"Street output split attribute changed at {node.name()}")
    required = {
        "unity_instance", "instance_prefix", "orient", "pscale", "pcg_kind",
        "pcg_group_key", "pcg_corridor_id", "pcg_side", "pcg_variant",
        "pcg_owner_id", "pcg_tangent", "pcg_distance", "pcg_corridor_length",
    }
    actual = {attribute.name() for attribute in geometry.pointAttribs()}
    require(required <= actual,
            f"Street output metadata missing at {node.name()}: {sorted(required - actual)}")
    return [_point_record(point) for point in geometry.points()]


def _street_signature(records: list[dict[str, Any]]) -> str:
    payload = json.dumps(records, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _set_and_cook(asset: hou.Node, core: hou.Node, values: dict[str, Any]) -> tuple[int, int, int]:
    for name, value in values.items():
        parm = asset.parm(name)
        require(parm is not None, f"Missing street parameter during boundary test: {name}")
        parm.set(value)
    result = []
    for name in ("OUT_STREET_LAMPS", "OUT_STREET_TREES", "OUT_STREET_TREE_PITS"):
        node = require_node(core, name)
        node.cook(force=True)
        require(not node.errors(), f"Street boundary cook failed at {name}: {node.errors()}")
        result.append(len(node.geometry().points()))
    return tuple(result)


def validate_street_furniture(asset: hou.Node, core: hou.Node) -> dict[str, Any]:
    lamp_node = require_node(core, "OUT_STREET_LAMPS")
    tree_node = require_node(core, "OUT_STREET_TREES")
    pit_node = require_node(core, "OUT_STREET_TREE_PITS")
    lamps = _street_records(lamp_node)
    trees = _street_records(tree_node)
    pits = _street_records(pit_node)
    require(lamps and trees and pits, "Default street-furniture outputs must not be empty")
    require(len(lamps) % 2 == 0, "Street lamps are not strictly paired")
    require(len(trees) == len(pits), "Default tree-pit probability must produce one pit per tree")

    allowed_prefix = "Assets/PCG/Art/StreetFurniture/Placeholders/"
    for record in lamps + trees + pits:
        require(record["instance"].startswith("Assets/") and record["instance"].endswith(".prefab"),
                f"Invalid Unity prefab path: {record['instance']}")
        require(record["instance"].startswith(allowed_prefix),
                f"Unexpected default placeholder path: {record['instance']}")
        require(record["prefix"] == record["group"], "instance_prefix/group key mismatch")
        require(record["side"] in (-1, 1), "Street side metadata is invalid")

    # Validate against the same final, unpacked road-top triangles consumed by
    # the V3 wrangles.  The earlier centre/radius approximation missed the
    # irregular corner and crosswalk cases visible in Unity.
    road_surface = require_node(core, "CITYROAD_TOPOLOGY_CLASSIFY_ROAD").geometry()
    road_triangles = []
    for primitive in road_surface.prims():
        positions = [point.position() for point in primitive.points()]
        if len(positions) == 3:
            road_triangles.append(tuple((float(p[0]), float(p[2])) for p in positions))
    require(road_triangles, "Final road-top surface contains no triangles")

    def point_in_triangle_xz(position, triangle, tolerance=0.05):
        px, pz = float(position[0]), float(position[2])
        (ax, az), (bx, bz), (cx, cz) = triangle

        def signed_distance(x0, z0, x1, z1, x2, z2):
            edge_x, edge_z = x2 - x1, z2 - z1
            length = math.hypot(edge_x, edge_z)
            if length <= 1e-9:
                return 1e9
            return ((x0 - x1) * edge_z - (z0 - z1) * edge_x) / length

        distances = (
            signed_distance(px, pz, ax, az, bx, bz),
            signed_distance(px, pz, bx, bz, cx, cz),
            signed_distance(px, pz, cx, cz, ax, az),
        )
        return (max(distances) <= tolerance or min(distances) >= -tolerance)

    road_intrusions = []
    for record in lamps + trees:
        if any(point_in_triangle_xz(record["position"], triangle)
               for triangle in road_triangles):
            road_intrusions.append((record["kind"], record["corridor"], record["owner"]))
    require(not road_intrusions,
            f"Street furniture overlaps final road surface: {road_intrusions[:8]}")
    lamp_skip_pairs = int(detail_value(
        require_node(core, "CITYROAD_STREET_BUILD_LAMPS_V1").geometry(),
        "street_lamp_skipped_road_surface_pair_count", -1))
    tree_surface_skips = int(detail_value(
        require_node(core, "CITYROAD_STREET_BUILD_TREES_V1").geometry(),
        "street_tree_skipped_road_surface_count", -1))
    require(lamp_skip_pairs > 0 and tree_surface_skips > 0,
            "Surface-containment fixture did not exercise lamp/tree rejection")

    lamp_groups: dict[tuple[int, int], list[dict[str, Any]]] = {}
    for lamp in lamps:
        require(lamp["kind"] == "Lamps" and abs(lamp["scale"] - 1.0) <= 1e-6,
                "Lamp kind/scale contract changed")
        lamp_groups.setdefault((lamp["corridor"], lamp["owner"]), []).append(lamp)
    for key, pair in lamp_groups.items():
        require(len(pair) == 2 and {item["side"] for item in pair} == {-1, 1},
                f"Lamp owner is not a left/right pair: {key}")
        require(abs(pair[0]["distance"] - pair[1]["distance"]) <= 1e-5,
                f"Lamp pair distance mismatch: {key}")
        for lamp in pair:
            require(lamp["distance"] >= asset.evalParm("junction_endpoint_clearance") - 1e-4,
                    f"Lamp violates endpoint clearance: {key}")
            require(lamp["distance"] <= lamp["length"] - asset.evalParm("junction_endpoint_clearance") + 1e-4,
                    f"Lamp violates endpoint clearance: {key}")
            tangent = hou.Vector3(lamp["tangent"])
            lateral = hou.Vector3(0, 1, 0).cross(tangent).normalized()
            expected = -float(lamp["side"]) * lateral
            forward = hou.Quaternion(lamp["orient"]).rotate(hou.Vector3(0, 0, 1)).normalized()
            require(forward.dot(expected) > 0.999,
                    f"Lamp +Z does not face the road centre: {key}")
    by_corridor_side: dict[tuple[int, int], list[float]] = {}
    for lamp in lamps:
        by_corridor_side.setdefault((lamp["corridor"], lamp["side"]), []).append(lamp["distance"])
    spacing = float(asset.evalParm("lamp_spacing"))
    for key, distances in by_corridor_side.items():
        distances.sort()
        for left, right in zip(distances, distances[1:]):
            gap = right - left
            multiple = max(1, round(gap / spacing))
            require(abs(gap - multiple * spacing) <= 1e-3,
                    f"Lamp spacing grid changed for {key}: {gap}")

    pit_by_owner = {(pit["corridor"], pit["owner"]): pit for pit in pits}
    tree_paths = set()
    non_quarter_turn = False
    for tree in trees:
        require(tree["kind"] == "Trees", "Tree kind metadata changed")
        require(asset.evalParm("tree_scale_min") - 1e-6 <= tree["scale"] <= asset.evalParm("tree_scale_max") + 1e-6,
                "Tree scale is outside the configured uniform range")
        tree_paths.add(tree["instance"])
        angle = 2.0 * math.atan2(tree["orient"][1], tree["orient"][3])
        quarter = math.pi * 0.5
        if abs(angle / quarter - round(angle / quarter)) > 1e-3:
            non_quarter_turn = True
        key = (tree["corridor"], tree["owner"])
        require(key in pit_by_owner, f"Tree has no matching pit: {key}")
        pit = pit_by_owner[key]
        require(pit["kind"] == "TreePits" and abs(pit["scale"] - 1.0) <= 1e-6,
                f"Tree pit kind/scale changed: {key}")
        require(sum((a - b) ** 2 for a, b in zip(tree["position"], pit["position"])) <= 1e-8,
                f"Tree pit position differs from tree: {key}")
        require(tree["distance"] >= asset.evalParm("junction_endpoint_clearance") - 1e-4 and
                tree["distance"] <= tree["length"] - asset.evalParm("junction_endpoint_clearance") + 1e-4,
                f"Tree violates endpoint clearance: {key}")
        nearest_lamp_sq = min(sum((a - b) ** 2 for a, b in zip(tree["position"], lamp["position"])) for lamp in lamps)
        require(nearest_lamp_sq + 1e-5 >= float(asset.evalParm("lamp_tree_clearance")) ** 2,
                f"Tree violates lamp clearance: {key}")
    require(non_quarter_turn, "Tree yaw is limited to 90-degree increments")
    require(len(tree_paths) == 3, f"Default tree variants were not preserved: {sorted(tree_paths)}")

    tracked = [
        "enable_sidewalk", "sidewalk_width", "minimum_sidewalk_width", "tree_seed",
        "tree_prefab1", "tree_prefab2", "tree_prefab3",
    ]
    original = {name: asset.parm(name).eval() for name in tracked}
    default_signature = _street_signature(trees)
    boundary = {}
    try:
        boundary["no_sidewalk"] = _set_and_cook(asset, core, {"enable_sidewalk": 0})
        require(boundary["no_sidewalk"] == (0, 0, 0),
                f"Street furniture generated without sidewalks: {boundary['no_sidewalk']}")
        boundary["narrow_sidewalk"] = _set_and_cook(asset, core, {
            "enable_sidewalk": original["enable_sidewalk"],
            "sidewalk_width": max(0.0, float(original["minimum_sidewalk_width"]) - 0.1),
        })
        require(boundary["narrow_sidewalk"] == (0, 0, 0),
                f"Street furniture generated on a narrow sidewalk: {boundary['narrow_sidewalk']}")
        _set_and_cook(asset, core, {
            "sidewalk_width": original["sidewalk_width"],
            "tree_seed": int(original["tree_seed"]) + 1,
        })
        changed_seed = _street_signature(_street_records(tree_node))
        require(changed_seed != default_signature, "Changing tree_seed did not change distribution")
        _set_and_cook(asset, core, {
            "tree_seed": original["tree_seed"],
            "tree_prefab2": original["tree_prefab1"],
        })
        merged = _street_records(tree_node)
        require(len({item["instance"] for item in merged}) == 2,
                "Duplicate tree prefab paths were not merged")
    finally:
        _set_and_cook(asset, core, original)
    restored = _street_records(tree_node)
    require(_street_signature(restored) == default_signature,
            "Tree distribution is not deterministic after parameter restore")
    return {
        "lamps": len(lamps),
        "lamp_pairs": len(lamp_groups),
        "trees": len(trees),
        "tree_pits": len(pits),
        "tree_variants": len(tree_paths),
        "road_surface_intrusions": len(road_intrusions),
        "lamp_surface_skipped_pairs": lamp_skip_pairs,
        "tree_surface_skips": tree_surface_skips,
        "deterministic_signature": default_signature,
        "boundary": boundary,
    }


def validate_v7_v8_v9(asset: hou.Node, core: hou.Node) -> dict[str, Any]:
    cuts = require_node(core, "CITYROAD_BUILD_JUNCTION_PARTITION_CUTS_V7").geometry()
    require(detail_value(cuts, "junction_partition_invalid_count", -1) == 0,
            "V7 invalid Junction partition cuts")

    helper = require_node(core, "CITYROAD_BUILD_JUNCTION_SURFACE_BOUNDARY_V5").geometry()
    expected = int(detail_value(helper, "junction_expected_approaches", -1))
    actual = int(detail_value(helper, "junction_actual_approaches", -2))
    extent_errors = int(detail_value(helper, "junction_arm_extent_error_count", -1))
    require(expected == actual and extent_errors == 0,
            f"V7 Junction extent failed: expected={expected} actual={actual} errors={extent_errors}")

    markings = require_node(core, "CITYROAD_BUILD_STATIC_MARKING_MESH").geometry()
    intrusion = int(detail_value(markings, "longitudinal_marking_junction_intrusion_count", -1))
    boundary_gap = float(detail_value(markings, "marking_boundary_gap_max", 1e9))
    join_error = float(detail_value(markings, "edge_line_join_error_max", 1e9))
    lane_primitives = int(detail_value(markings, "lane_line_primitive_count", -1))
    lane_count = int(asset.parm("default_lane_count").eval())
    require(intrusion == 0 and boundary_gap <= 0.001,
            f"V7 marking clip failed: intrusion={intrusion} gap={boundary_gap}")
    require(join_error <= 0.001, f"V8 edge-line continuity failed: {join_error}")
    if lane_count == 2:
        require(lane_primitives == 0,
                f"Two-lane road emitted divider primitives: {lane_primitives}")

    approach = require_node(core, "CITYROAD_BUILD_APPROACH_MARKINGS_V5").geometry()
    for name in (
        "junction_marking_coverage_error_count",
        "junction_arm_extent_error_count",
        "crosswalk_mouth_alignment_error_count",
        "stop_line_orientation_error_count",
    ):
        require(int(detail_value(approach, name, -1)) == 0,
                f"V7 approach marking contract failed: {name}")

    surface = require_node(core, "CITYROAD_TOPOLOGY_CLASSIFY_ROAD").geometry()
    transferred_markings = require_node(
        core, "CITYROAD_TOPOLOGY_TRANSFER_ROADMARKINGS").geometry()
    surface_bounds = bounds_by_piece(surface, "junction")
    marking_bounds = bounds_by_piece(transferred_markings, "junction")
    for key, marking_box in marking_bounds.items():
        require(key in surface_bounds, f"V7 Junction marking has no surface piece: {key}")
        surface_box = surface_bounds[key]
        smin, smax = surface_box.minvec(), surface_box.maxvec()
        mmin, mmax = marking_box.minvec(), marking_box.maxvec()
        tolerance = 0.001
        require(
            mmin[0] >= smin[0] - tolerance
            and mmin[2] >= smin[2] - tolerance
            and mmax[0] <= smax[0] + tolerance
            and mmax[2] <= smax[2] + tolerance,
            f"V7 Junction marking exceeds surface piece: {key}")

    rounded = require_node(core, "ROAD_ROUND_CENTERLINE_CORNERS").geometry()
    max_segments = int(detail_value(rounded, "rounded_corner_max_segment_count", -1))
    require(0 <= max_segments <= 4, f"V8 corner sample cap failed: {max_segments}")
    classified = require_node(core, "ROAD_CLASSIFY_CORNER_TOPOLOGY").geometry()
    half_strips = int(detail_value(classified, "adaptive_corner_max_half_strips", -1))
    require(half_strips == 1, f"V8 corner rail classification failed: {half_strips}")
    corner = require_node(core, "ROAD_BUILD_ADAPTIVE_CORNER_SURFACE").geometry()
    rails = int(detail_value(corner, "mobile_corner_rail_count", -1))
    points_per_side = int(detail_value(corner, "mobile_corner_points_per_side", -1))
    extra_strips = int(detail_value(corner, "mobile_corner_extra_strip_count", -1))
    require((rails, points_per_side, extra_strips) == (2, 5, 0),
            f"V8 mobile corner topology changed: {(rails, points_per_side, extra_strips)}")

    boundary = require_node(core, "ROAD_UNION_ROUND_FINAL_BOUNDARY").geometry()
    final_max = int(detail_value(boundary, "final_boundary_mobile_max_segment_count", -1))
    final_points = int(detail_value(boundary, "final_boundary_mobile_points_per_side", -1))
    final_patch = str(detail_value(boundary, "cityroad_final_boundary_patch", ""))
    require(0 <= final_max <= 4, f"V9 final boundary segment cap failed: {final_max}")
    require(final_points == 5 and final_patch == "V9",
            f"V9 final boundary contract changed: points={final_points} patch={final_patch}")
    return {
        "junction_approaches": actual,
        "marking_boundary_gap_max": boundary_gap,
        "edge_line_join_error_max": join_error,
        "corner_max_segments": max_segments,
        "corner_rails": rails,
        "final_boundary_max_segments": final_max,
    }


def validate_v10(core: hou.Node) -> dict[str, Any]:
    section_geometry = require_node(
        core, "CITYROAD_BUILD_CORNER_SECTION_CONSTRAINTS_V10").geometry()
    section_count = int(detail_value(section_geometry, "corner_section_constraint_count", -1))
    invalid = int(detail_value(section_geometry, "corner_section_invalid_quad_count", -1))
    lines_per_sample = int(detail_value(section_geometry, "corner_section_lines_per_sample", -1))
    patch = str(detail_value(section_geometry, "cityroad_corner_section_patch", ""))
    constraints = constraint_edges(section_geometry)
    require(section_count > 0 and len(constraints) == section_count,
            f"V10 invalid corner section count: detail={section_count} actual={len(constraints)}")
    require(len(set(constraints)) == len(constraints), "V10 duplicate corner section lines")
    require(invalid == 0 and lines_per_sample == 1 and patch == "V10",
            f"V10 corner section contract changed: invalid={invalid} lines={lines_per_sample} patch={patch}")

    final_geometry = require_node(core, "ROAD_PLANAR_TRIANGULATE_FINAL_BOUNDARY").geometry()
    final_edges, final_neighbors = geometry_edges(final_geometry)
    final_positions = list(final_neighbors)

    def nearest(position, candidates, use_y=True, tolerance=0.002):
        best = None
        best_distance = tolerance * tolerance
        for candidate in candidates:
            axes = (0, 1, 2) if use_y else (0, 2)
            distance = sum((position[index] - candidate[index]) ** 2 for index in axes)
            if distance <= best_distance:
                best = candidate
                best_distance = distance
        return best

    missing = []
    for edge in constraints:
        a = nearest(edge[0], final_positions)
        b = nearest(edge[1], final_positions)
        if a is None or b is None or tuple(sorted((a, b))) not in final_edges:
            missing.append(edge)
    require(not missing, f"V10 final road triangulation lost {len(missing)} section constraints")

    sidewalk_geometry = require_node(
        core, "CITYROAD_BUILD_SIDEWALK_SECTION_CONSTRAINTS_V10").geometry()
    sidewalk_count = int(detail_value(
        sidewalk_geometry, "sidewalk_corner_section_connector_count", -1))
    sidewalk_misses = int(detail_value(
        sidewalk_geometry, "sidewalk_corner_section_missed_boundary_count", -1))
    sidewalk_lines = int(detail_value(
        sidewalk_geometry, "sidewalk_corner_section_lines_per_endpoint", -1))
    sidewalk_patch = str(detail_value(
        sidewalk_geometry, "cityroad_sidewalk_section_patch", ""))
    require(
        sidewalk_count == section_count * 2
        and sidewalk_misses == 0
        and sidewalk_lines == 1
        and sidewalk_patch == "V10",
        "V10 sidewalk section contract changed: "
        f"count={sidewalk_count} misses={sidewalk_misses} lines={sidewalk_lines} patch={sidewalk_patch}")

    sidewalk_final = require_node(
        core, "CITYROAD_FUSE_SIDEWALK_TRIANGULATION_V10").geometry()
    _sidewalk_edges, sidewalk_neighbors = geometry_edges(sidewalk_final)
    sidewalk_positions = list(sidewalk_neighbors)
    outgoing_counts = []
    for primitive in sidewalk_geometry.prims():
        points = primitive.points()
        start = position_key(points[0].position())
        end = position_key(points[1].position())
        mapped_start = nearest(start, sidewalk_positions, use_y=False)
        if mapped_start is None:
            outgoing_counts.append(0)
            continue
        direction = (end[0] - start[0], end[2] - start[2])
        direction_length = max((direction[0] ** 2 + direction[1] ** 2) ** 0.5, 1e-12)
        outgoing = 0
        for neighbor in sidewalk_neighbors.get(mapped_start, set()):
            candidate = (neighbor[0] - mapped_start[0], neighbor[2] - mapped_start[2])
            candidate_length = max((candidate[0] ** 2 + candidate[1] ** 2) ** 0.5, 1e-12)
            alignment = (
                direction[0] * candidate[0] + direction[1] * candidate[1]
            ) / (direction_length * candidate_length)
            if alignment >= 0.999:
                outgoing += 1
        outgoing_counts.append(outgoing)
    require(all(count == 1 for count in outgoing_counts),
            f"V10 sidewalk endpoints lost single outward constraint: {outgoing_counts}")
    return {
        "corner_sections": section_count,
        "road_constraints_preserved": len(constraints) - len(missing),
        "sidewalk_sections": sidewalk_count,
        "sidewalk_outgoing_counts": outgoing_counts,
    }


def validate_v11_v12_v13(core: hou.Node) -> dict[str, Any]:
    """Cumulative contracts for the current sidewalk/final-boundary chain."""
    v11 = require_node(
        core, "CITYROAD_REPLACE_SIDEWALK_CORNER_WITH_QUAD_STRIPS_V11").geometry()
    v12 = require_node(
        core, "CITYROAD_FUSE_FINAL_BOUNDARY_CORNER_SECTIONS_V12").geometry()
    boundary = require_node(core, "ROAD_UNION_ROUND_FINAL_BOUNDARY").geometry()
    connectors = require_node(core, "SIDEWALK_OPEN_END_SIDE_CONNECTORS").geometry()
    seams = require_node(core, "SIDEWALK_PLANAR_MARK_SEAMS").geometry()
    topology = require_node(core, "SIDEWALK_TOPOLOGY_VALIDATE").geometry()
    regions = require_node(core, "SIDEWALK_REGION_METADATA").geometry()

    require(str(detail_value(v11, "cityroad_sidewalk_corner_strip_patch", "")) == "V11",
            "V11 sidewalk corner strip marker missing")
    require(int(detail_value(v11, "sidewalk_corner_strip_invalid_quad_count", -1)) == 0,
            "V11 contains invalid sidewalk corner strips")
    require(int(detail_value(v11, "sidewalk_corner_strip_missing_connector_count", -1)) == 0,
            "V11 is missing sidewalk corner connectors")
    require(str(detail_value(v12, "cityroad_shared_corner_boundary_patch", "")) == "V12",
            "V12 final boundary marker missing")

    terminal_count = int(detail_value(boundary, "square_open_end_terminal_count", -1))
    cap_count = int(detail_value(boundary, "square_open_end_cap_edge_count", -1))
    occluded_count = int(detail_value(
        boundary, "square_open_end_occluded_terminal_count", -1))
    target_count = int(detail_value(
        boundary, "square_open_end_corner_target_count", -1))
    skip_count = int(detail_value(
        boundary, "square_open_end_corner_skip_count", -1))
    connector_count = int(detail_value(
        connectors, "sidewalk_open_end_connector_count", -1))
    unmatched_count = int(detail_value(
        connectors, "sidewalk_open_end_unmatched_connector_count", -1))
    complete_count = int(detail_value(
        seams, "sidewalk_partition_complete_connector_count", -1))
    uncovered_count = int(detail_value(
        seams, "sidewalk_partition_uncovered_connector_count", -1))
    coverage = float(detail_value(
        seams, "sidewalk_partition_min_connector_coverage", -1.0))
    partition_errors = int(detail_value(
        regions, "square_open_end_partition_error_count", -1))
    topology_ok = int(detail_value(
        topology, "sidewalk_validation_topology_ok", 0))
    inside = int(detail_value(
        topology, "sidewalk_validation_road_inside_vertex_count", -1))
    crossings = int(detail_value(
        topology, "sidewalk_validation_road_boundary_crossing_edge_count", -1))
    overlaps = int(detail_value(
        topology, "sidewalk_validation_positive_overlap_triangle_count", -1))

    require(terminal_count == 8, f"V13 terminal count changed: {terminal_count}")
    require(cap_count + occluded_count == terminal_count,
            f"V13 cap accounting changed: caps={cap_count} occluded={occluded_count}")
    require(target_count == skip_count == cap_count * 2,
            f"V13 square corner accounting changed: target={target_count} skip={skip_count}")
    require(connector_count == terminal_count * 2 and unmatched_count == 0,
            f"V13 connector contract failed: count={connector_count} unmatched={unmatched_count}")
    require(complete_count == connector_count and uncovered_count == 0,
            f"V13 connector coverage failed: complete={complete_count} uncovered={uncovered_count}")
    require(coverage >= 0.985,
            f"V13 minimum active connector coverage changed: {coverage}")
    require(partition_errors == 0,
            f"V13 sidewalk region partition errors: {partition_errors}")
    require(topology_ok == 1 and inside == 0 and crossings == 0 and overlaps == 0,
            "V13 sidewalk topology validation failed: "
            f"ok={topology_ok} inside={inside} crossings={crossings} overlaps={overlaps}")
    return {
        "v11_patch": "V11",
        "v12_patch": "V12",
        "terminal_count": terminal_count,
        "square_cap_count": cap_count,
        "occluded_terminal_count": occluded_count,
        "connector_count": connector_count,
        "complete_connector_count": complete_count,
        "uncovered_connector_count": uncovered_count,
        "minimum_active_connector_coverage": coverage,
        "partition_error_count": partition_errors,
        "topology_ok": topology_ok,
    }


def validate_v14_nonterminal_rounding(core: hou.Node) -> dict[str, Any]:
    """V14: square only real open ends; preserve all other V9 rounding."""
    boundary = require_node(core, "ROAD_UNION_ROUND_FINAL_BOUNDARY").geometry()
    rounded = int(detail_value(
        boundary, "final_boundary_mobile_rounded_corner_count", -1))
    right_angles = int(detail_value(
        boundary, "final_boundary_mobile_right_angle_corner_count", -1))
    skipped = int(detail_value(
        boundary, "square_open_end_corner_skip_count", -1))
    candidates = int(detail_value(
        boundary, "nonterminal_rounding_candidate_count", -1))
    max_segments = int(detail_value(
        boundary, "final_boundary_mobile_max_segment_count", -1))
    patch = str(detail_value(
        boundary, "cityroad_nonterminal_rounding_patch", ""))

    require(patch == "V14", f"V14 marker missing: {patch}")
    require(rounded == 32 and rounded > 0,
            f"V14 non-terminal rounding changed: {rounded}")
    require(right_angles == 10,
            f"V14 right-angle rounding changed: {right_angles}")
    require(skipped == 14,
            f"V14 square open-end skip count changed: {skipped}")
    require(candidates == rounded + skipped == 46,
            "V14 candidate accounting failed: "
            f"candidates={candidates} rounded={rounded} skipped={skipped}")
    require(max_segments == 4,
            f"V14 mobile segment budget changed: {max_segments}")
    return {
        "rounded_nonterminal_corner_count": rounded,
        "rounded_right_angle_corner_count": right_angles,
        "square_open_end_corner_skip_count": skipped,
        "rounding_candidate_count": candidates,
        "max_segments": max_segments,
    }


def validate_v15_sidewalk_terminal_front_containment(
        core: hou.Node) -> dict[str, Any]:
    """V15: remove only constrained sidewalk in front of square open ends."""
    containment_node = require_node(
        core, "CITYROAD_VALIDATE_SIDEWALK_TERMINAL_FRONT_CONTAINMENT_V15")
    containment = containment_node.geometry()
    regions = require_node(core, "SIDEWALK_REGION_METADATA").geometry()
    seams = require_node(core, "SIDEWALK_PLANAR_MARK_SEAMS").geometry()
    values = {
        "active_terminal_front_count": int(detail_value(
            containment, "sidewalk_terminal_front_active_count", -1)),
        "sealed_terminal_front_count": int(detail_value(
            containment, "sidewalk_terminal_front_sealed_count", -1)),
        "occluded_terminal_front_count": int(detail_value(
            containment, "sidewalk_terminal_front_occluded_count", -1)),
        "invalid_terminal_front_count": int(detail_value(
            containment, "sidewalk_terminal_front_invalid_count", -1)),
        "marked_triangle_count": int(detail_value(
            containment, "sidewalk_terminal_front_marked_triangle_count", -1)),
        "deleted_triangle_count": int(detail_value(
            containment, "sidewalk_terminal_front_deleted_triangle_count", -1)),
        "residual_triangle_count": int(detail_value(
            containment, "sidewalk_terminal_front_residual_triangle_count", -1)),
        "nonconforming_triangle_count": int(detail_value(
            containment,
            "sidewalk_terminal_front_nonconforming_triangle_count", -1)),
        "outside_vertex_count": int(detail_value(
            containment, "sidewalk_site_outside_vertex_count", -1)),
        "site_boundary_crossing_edge_count": int(detail_value(
            containment, "sidewalk_site_boundary_crossing_edge_count", -1)),
        "outside_positive_area_triangle_count": int(detail_value(
            containment,
            "sidewalk_site_outside_positive_area_triangle_count", -1)),
        "containment_ok": int(detail_value(
            containment, "sidewalk_terminal_front_containment_ok", 0)),
        "patch": str(detail_value(
            containment, "cityroad_sidewalk_terminal_front_patch", "")),
        "sidewalk_primitive_count": len(regions.prims()),
        "region_count": int(detail_value(
            regions, "sidewalk_region_partition_count", -1)),
        "complete_connector_count": int(detail_value(
            seams, "sidewalk_partition_complete_connector_count", -1)),
        "uncovered_connector_count": int(detail_value(
            seams, "sidewalk_partition_uncovered_connector_count", -1)),
    }
    expected = {
        "active_terminal_front_count": 3,
        "sealed_terminal_front_count": 4,
        "occluded_terminal_front_count": 1,
        "invalid_terminal_front_count": 0,
        "marked_triangle_count": 4,
        "deleted_triangle_count": 4,
        "residual_triangle_count": 0,
        "nonconforming_triangle_count": 0,
        "outside_vertex_count": 0,
        "site_boundary_crossing_edge_count": 0,
        "outside_positive_area_triangle_count": 0,
        "containment_ok": 1,
        "patch": "V15",
        "sidewalk_primitive_count": 167,
        "region_count": 9,
        "complete_connector_count": 16,
        "uncovered_connector_count": 0,
    }
    failures = [key for key, expected_value in expected.items()
                if values[key] != expected_value]
    require(not failures, f"V15 sidewalk containment changed {failures}: {values}")
    return values


def validate_phase17_geometry(core: hou.Node) -> dict[str, Any]:
    stats_geometry = require_node(core, "CURB_SIDEWALK_STATS").geometry()
    checks = {
        "remaining_reversed_top_face_count": 0,
        "remaining_reversed_vertical_face_count": 0,
        "degenerate_primitive_count": 0,
    }
    actual = {}
    for name, expected in checks.items():
        value = int(detail_value(stats_geometry, name, -1))
        actual[name] = value
        require(value == expected, f"Phase17 geometry contract failed: {name}={value}")

    # Validate the final unpacked road mesh consumed by the output chain.  The
    # earlier planar constraint mesh intentionally contains temporary zero-area
    # constraint triangles that are removed before this node.
    road_geometry = require_node(core, "CITYROAD_UNITY_ROAD_NORMALS").geometry()
    degenerate = 0
    positive_y = 0
    checked = 0
    for primitive in road_geometry.prims():
        points = primitive.points()
        if len(points) != 3:
            continue
        a, b, c = (point.position() for point in points)
        cross = (b - a).cross(c - a)
        area2 = cross.length()
        if area2 <= 1e-8:
            degenerate += 1
            continue
        checked += 1
        if cross[1] > 1e-7:
            positive_y += 1
    require(degenerate == 0, f"Road final triangulation has {degenerate} degenerate triangles")
    require(checked > 0, "Road final triangulation has no triangles")
    require(positive_y == 0,
            f"Road Houdini winding contract failed: {positive_y}/{checked} triangles face +Y")
    return {**actual, "road_triangles": checked, "road_positive_y_triangles": positive_y}


def validate_asset(asset: hou.Node, require_locked: bool = False) -> dict[str, Any]:
    require(asset is not None, "CityRoad asset is missing")
    require(asset.type().name() == ASSET_TYPE,
            f"Unexpected CityRoad asset type: {asset.type().name()}")
    definition = asset.type().definition()
    require(definition is not None, "CityRoad asset has no HDA definition")
    if require_locked:
        require(asset.isLockedHDA(), "Fresh CityRoad validation instance is not locked")
    core = asset.node(CORE_NAME)
    require(core is not None, f"CityRoad core network is missing: {CORE_NAME}")
    contract = load_contract()
    result = {
        "status": "PASS",
        "asset": asset.path(),
        "definition": definition.libraryFilePath(),
        "locked": asset.isLockedHDA(),
        "contracts": contract["contract_ids"],
        "network": validate_network(asset, core, contract),
        "outputs": validate_outputs(core, contract),
        "street_furniture": validate_street_furniture(asset, core),
        "v7_v8_v9": validate_v7_v8_v9(asset, core),
        "v10": validate_v10(core),
        "v11_v12_v13": validate_v11_v12_v13(core),
        "v14_nonterminal_rounding": validate_v14_nonterminal_rounding(core),
        "v15_sidewalk_terminal_front_containment": (
            validate_v15_sidewalk_terminal_front_containment(core)),
        "phase17": validate_phase17_geometry(core),
    }
    return result


def validate_live_json(asset_path: str = LIVE_ASSET_PATH) -> str:
    return json.dumps(validate_asset(hou.node(asset_path), require_locked=False),
                      ensure_ascii=False, default=list)


def validate_remote_live(asset_path: str, host: str, port: int) -> dict[str, Any]:
    import hrpyc
    connection, _remote_hou = hrpyc.import_remote_module(host, port, "hou")
    try:
        tools_path = str(SCRIPT_DIR).replace("\\", "/")
        connection.execute(
            "import sys, importlib; "
            f"sys.path.insert(0, {tools_path!r}) if {tools_path!r} not in sys.path else None; "
            "import validate_cityroad_contract as _pcg_cityroad_contract; "
            "importlib.reload(_pcg_cityroad_contract)")
        payload = connection.eval(
            f"_pcg_cityroad_contract.validate_live_json({asset_path!r})")
        return json.loads(str(payload))
    finally:
        connection.close()


def copy_production_configuration(source: hou.Node, target: hou.Node) -> list[str]:
    """Copy only public instance values; the target contents remain locked."""

    skipped = []
    # Multiparm counts appear before their generated children in parm order, so
    # copying in this order also materializes the target child parameters.
    for source_parm in source.parms():
        target_parm = target.parm(source_parm.name())
        if target_parm is None:
            skipped.append(source_parm.name())
            continue
        if source_parm.parmTemplate().type() == hou.parmTemplateType.Button:
            continue
        try:
            target_parm.set(source_parm.eval())
        except Exception:
            try:
                target_parm.set(source_parm.evalAsString())
            except Exception:
                skipped.append(source_parm.name())
    for connection in source.inputConnections():
        target.setInput(
            connection.inputIndex(), connection.inputNode(), connection.outputIndex())
    return skipped


def validate_fresh(hda_path: Path, hip_path: Path) -> dict[str, Any]:
    require(hda_path.is_file(), f"CityRoad HDA not found: {hda_path}")
    require(hip_path.is_file(), f"CityRoad HIP not found: {hip_path}")
    hou.hipFile.load(str(hip_path), suppress_save_prompt=True, ignore_load_warnings=False)
    hou.hda.installFile(str(hda_path))
    obj = hou.node("/obj")
    existing = obj.node("VERIFY_CITYROAD_LOCKED")
    if existing is not None:
        existing.destroy()
    fresh = obj.createNode(ASSET_TYPE, "VERIFY_CITYROAD_LOCKED")
    production = hou.node(LIVE_ASSET_PATH)
    require(production is not None, f"Production CityRoad instance is missing: {LIVE_ASSET_PATH}")
    skipped = copy_production_configuration(production, fresh)
    result = validate_asset(fresh, require_locked=True)
    result["source"] = "fresh_locked_instance"
    result["hip"] = str(hip_path)
    result["hda"] = str(hda_path)
    result["saved"] = False
    result["configuration_copy_skipped"] = skipped
    return result


def fresh_interface_hash(hda_path: Path, hip_path: Path) -> str:
    require(hda_path.is_file(), f"CityRoad HDA not found: {hda_path}")
    require(hip_path.is_file(), f"CityRoad HIP not found: {hip_path}")
    hou.hipFile.load(str(hip_path), suppress_save_prompt=True, ignore_load_warnings=False)
    hou.hda.installFile(str(hda_path))
    fresh = hou.node("/obj").createNode(ASSET_TYPE, "VERIFY_CITYROAD_INTERFACE")
    return public_interface_hash(fresh)


def remote_interface_hash(asset_path: str, host: str, port: int) -> str:
    import hrpyc
    connection, remote_hou = hrpyc.import_remote_module(host, port, "hou")
    try:
        asset = remote_hou.node(asset_path)
        require(asset is not None, f"Live CityRoad asset is missing: {asset_path}")
        definition = asset.type().definition()
        require(definition is not None, "Live CityRoad asset has no HDA definition")
        dialog = definition.parmTemplateGroup().asDialogScript()
        return hashlib.sha256(str(dialog).encode("utf-8")).hexdigest()
    finally:
        connection.close()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", choices=("live", "fresh"), default="fresh")
    parser.add_argument("--asset", default=LIVE_ASSET_PATH)
    parser.add_argument("--hda", type=Path, default=DEFAULT_HDA)
    parser.add_argument("--hip", type=Path, default=DEFAULT_HIP)
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=18811)
    parser.add_argument("--emit-interface-hash", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if args.emit_interface_hash:
        if args.source == "live":
            value = remote_interface_hash(args.asset, args.host, args.port)
        else:
            value = fresh_interface_hash(args.hda.resolve(), args.hip.resolve())
        print(value)
        return 0
    if args.source == "live":
        result = validate_remote_live(args.asset, args.host, args.port)
    else:
        result = validate_fresh(args.hda.resolve(), args.hip.resolve())
    print(json.dumps(result, ensure_ascii=False, indent=2, default=list))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except ContractFailure as exception:
        print(f"CONTRACT_FAIL: {exception}", file=sys.stderr)
        raise SystemExit(1)
