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
    # Editable production instances can carry transient spare parameter UI.
    # The public API contract belongs to the persisted HDA definition.
    dialog = definition.parmTemplateGroup().asDialogScript()
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
    expected_hash = contract["public_interface_sha256"]
    require(expected_hash != "PENDING_CAPTURE", "CityRoad public interface baseline is not captured")
    require(actual_hash == expected_hash, "CityRoad public parameter interface changed")

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
        require(len(geometry.prims()) > 0, f"CityRoad output is empty: {name}")
        stats[name] = {
            "points": len(geometry.points()),
            "primitives": len(geometry.prims()),
            "vertices": sum(len(primitive.vertices()) for primitive in geometry.prims()),
        }
    return stats


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
        "v7_v8_v9": validate_v7_v8_v9(asset, core),
        "v10": validate_v10(core),
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
