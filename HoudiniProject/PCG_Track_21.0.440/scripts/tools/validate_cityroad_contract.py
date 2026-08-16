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
LAYOUT_CONTRACT_PATH = SCRIPT_DIR.parent / "contracts/cityroad_subnet_layout_contract.json"
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
    if node is not None:
        return node
    matches = []
    for child in core.children():
        if child.type().name() != "subnet" or not child.name().startswith("CR_"):
            continue
        candidate = child.node(name)
        if candidate is not None:
            matches.append(candidate)
    require(
        len(matches) == 1,
        f"Required CityRoad leaf must be unique: {name}, found "
        f"{[candidate.path() for candidate in matches]}")
    return matches[0]


def _subnet_output_source(subnet: hou.Node, output_index: int) -> hou.Node | None:
    outputs = []
    for child in subnet.children():
        if child.type().name() != "output":
            continue
        parm = child.parm("outputidx")
        index = int(parm.eval()) if parm is not None else len(outputs)
        outputs.append((index, child))
    for index, output in sorted(outputs, key=lambda item: item[0]):
        if index != output_index:
            continue
        connections = output.inputConnections()
        return connections[0].inputNode() if connections else None
    return None


def logical_source_name(connection: hou.NodeConnection) -> str | None:
    """Resolve a connection through an authored subnet output to its leaf."""

    source = connection.inputNode()
    output_index = connection.outputIndex()
    visited = set()
    while source is not None and source.type().name() == "subnet" and source.name().startswith("CR_"):
        if source.path() in visited:
            raise ContractFailure(f"Subnet output cycle at {source.path()}")
        visited.add(source.path())
        source = _subnet_output_source(source, output_index)
        output_index = 0
    return source.name() if source is not None else None


def _safe(callable_value, default=None):
    try:
        return callable_value()
    except Exception:
        return default


def _json_value(value):
    if value is None or isinstance(value, (bool, int, float, str)):
        return value
    if isinstance(value, (tuple, list)):
        return [_json_value(item) for item in value]
    return str(value)


def public_interface_schema(asset: hou.Node) -> dict[str, Any]:
    definition = asset.type().definition()
    require(definition is not None, "CityRoad asset has no HDA definition")
    result = {}

    def visit(templates, folder):
        for template in templates:
            name = _safe(lambda: template.name(), "")
            label = _safe(lambda: template.label(), "")
            template_type = _safe(lambda: template.type(), None)
            kind = (_safe(lambda: template_type.name(), str(template_type))
                    if template_type is not None else "unknown")
            key = "/".join(folder + [name or ("@" + label)])
            result[key] = {
                "name": name,
                "label": label,
                "type": kind,
                "folder": folder,
                "components": _safe(lambda: template.numComponents(), None),
                "default": _json_value(_safe(lambda: template.defaultValue(), None)),
                "min": _safe(lambda: template.minValue(), None),
                "max": _safe(lambda: template.maxValue(), None),
                "min_strict": _safe(lambda: template.minIsStrict(), None),
                "max_strict": _safe(lambda: template.maxIsStrict(), None),
                "menu_items": _json_value(_safe(lambda: template.menuItems(), None)),
                "menu_labels": _json_value(_safe(lambda: template.menuLabels(), None)),
                "hidden": _safe(lambda: template.isHidden(), None),
                "conditionals": str(_safe(lambda: template.conditionals(), {})),
            }
            children = _safe(lambda: template.parmTemplates(), None)
            if children:
                visit(children, folder + [name or ("@" + label)])

    # Hash the persisted definition schema.  Houdini is free to rewrite
    # DialogScript-only folder/baseparm ids; those are not public API.
    visit(definition.parmTemplateGroup().parmTemplates(), [])
    return result


def public_interface_hash(asset: hou.Node) -> str:
    payload = json.dumps(public_interface_schema(asset), ensure_ascii=False,
                         sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def load_contract() -> dict[str, Any]:
    contract = json.loads(CONTRACT_PATH.read_text(encoding="utf-8"))
    require(contract.get("schema_version") == 1, "Unsupported CityRoad contract schema")
    require(contract.get("asset_type") == ASSET_TYPE, "CityRoad contract type mismatch")
    return contract


def load_layout_contract() -> dict[str, Any]:
    contract = json.loads(LAYOUT_CONTRACT_PATH.read_text(encoding="utf-8"))
    require(contract.get("schema_version") == 1,
            "Unsupported CityRoad subnet layout contract schema")
    return contract


def _positions_overlap(nodes: list[hou.Node]) -> list[tuple[str, str]]:
    buckets: dict[tuple[float, float], str] = {}
    overlaps = []
    for node in nodes:
        position = node.position()
        key = (round(float(position.x()), 3), round(float(position.y()), 3))
        if key in buckets:
            overlaps.append((buckets[key], node.path()))
        else:
            buckets[key] = node.path()
    return overlaps


def validate_subnet_layout(core: hou.Node) -> dict[str, Any]:
    contract = load_layout_contract()
    expected_subnets = contract["subnets"]
    direct = list(core.children())
    direct_names = {node.name() for node in direct}
    expected_direct = set(expected_subnets) | set(contract["preserved_top_level"])
    require(
        len(direct) == contract["top_level_node_count"],
        f"CityRoadCore direct node count changed: {len(direct)} "
        f"expected={contract['top_level_node_count']}")
    require(direct_names == expected_direct,
            "CityRoadCore direct node membership differs from V19 layout contract")

    leaf_paths: dict[str, str] = {}
    member_count = 0
    max_inputs = 0
    max_outputs = 0
    dependencies: dict[str, set[str]] = {name: set() for name in expected_subnets}
    for subnet_name, expected_members in expected_subnets.items():
        subnet = core.node(subnet_name)
        require(subnet is not None and subnet.type().name() == "subnet",
                f"Missing authored CityRoad subnet: {subnet_name}")
        outputs = [node for node in subnet.children() if node.type().name() == "output"]
        members = [node for node in subnet.children() if node.type().name() != "output"]
        require({node.name() for node in members} == set(expected_members),
                f"CityRoad subnet membership changed: {subnet_name}")
        member_count += len(members)
        max_inputs = max(max_inputs, len(subnet.inputConnections()))
        max_outputs = max(max_outputs, len(outputs))
        require(len(subnet.inputConnections()) <= contract["max_subnet_inputs"],
                f"CityRoad subnet input limit exceeded: {subnet_name}")
        require(len(outputs) <= contract["max_subnet_outputs"],
                f"CityRoad subnet output limit exceeded: {subnet_name}")
        require(subnet.comment().strip(), f"CityRoad subnet comment is empty: {subnet_name}")
        for connection in subnet.inputConnections():
            label_parm = subnet.parm(f"label{connection.inputIndex() + 1}")
            require(label_parm is not None and label_parm.evalAsString().strip() and
                    not label_parm.evalAsString().startswith("Sub-Network Input"),
                    f"CityRoad subnet connector label is not authored: "
                    f"{subnet_name}[{connection.inputIndex()}]")
        for output in outputs:
            require(output.name().startswith("SUBNET_OUT_") and output.comment().strip(),
                    f"CityRoad subnet output is not explicitly named: {output.path()}")
        require(not _positions_overlap(list(subnet.children())),
                f"Overlapping nodes inside CityRoad subnet: {subnet_name}")
        for node in subnet.children():
            position = node.position()
            require(not (abs(float(position.x())) < 1e-6 and
                         abs(float(position.y())) < 1e-6),
                    f"CityRoad node remains at origin: {node.path()}")
            if node.type().name() in ("attribwrangle", "switch", "output"):
                require(node.comment().strip(),
                        f"CityRoad Wrangle/Switch/Output comment is empty: {node.path()}")
        for member in members:
            previous = leaf_paths.get(member.name())
            require(previous is None,
                    f"Duplicate CityRoad leaf name: {member.name()} at "
                    f"{previous} and {member.path()}")
            leaf_paths[member.name()] = member.path()
        for connection in subnet.inputConnections():
            source = connection.inputNode()
            if source is not None and source.name() in dependencies:
                dependencies[subnet_name].add(source.name())

    require(member_count == contract["original_member_count"],
            f"CityRoad moved leaf count changed: {member_count}")
    require(not _positions_overlap(direct), "Overlapping nodes at CityRoadCore top level")
    for node in direct:
        position = node.position()
        require(not (abs(float(position.x())) < 1e-6 and
                     abs(float(position.y())) < 1e-6),
                f"CityRoad top-level node remains at origin: {node.path()}")
        if node.type().name() == "output":
            require(node.comment().strip(),
                    f"CityRoad formal output comment is empty: {node.path()}")

    visiting: set[str] = set()
    visited: set[str] = set()
    def visit(name: str) -> None:
        if name in visiting:
            raise ContractFailure(f"CityRoad subnet dependency cycle detected at {name}")
        if name in visited:
            return
        visiting.add(name)
        for dependency in dependencies[name]:
            visit(dependency)
        visiting.remove(name)
        visited.add(name)
    for name in dependencies:
        visit(name)

    boxes = list(core.networkBoxes())
    expected_areas = contract["areas"]
    require(len(boxes) == len(expected_areas),
            f"CityRoad top-level Network Box count changed: {len(boxes)}")
    for name, expected_members in expected_areas.items():
        box = next((item for item in boxes if item.name() == name), None)
        require(box is not None, f"Missing CityRoad top-level Network Box: {name}")
        actual_members = {item.name() for item in box.items()}
        require(actual_members == set(expected_members),
                f"CityRoad Network Box membership changed: {name}")

    return {
        "contract_id": contract["contract_id"],
        "top_level_nodes": len(direct),
        "author_subnets": len(expected_subnets),
        "moved_leaf_nodes": member_count,
        "max_subnet_inputs": max_inputs,
        "max_subnet_outputs": max_outputs,
        "network_boxes": len(boxes),
        "dependency_dag": True,
    }


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
            str(connection.inputIndex()): logical_source_name(connection)
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

    markings = require_node(
        core, "CITYROAD_VALIDATE_STATIC_MARKING_JUNCTION_CLIP_V24").geometry()
    intrusion = int(detail_value(markings, "longitudinal_marking_junction_intrusion_count", -1))
    validation_stage = str(detail_value(markings, "marking_validation_stage", ""))
    boundary_gap = float(detail_value(markings, "marking_boundary_gap_max", 1e9))
    join_error = float(detail_value(markings, "edge_line_join_error_max", 1e9))
    lane_primitives = int(detail_value(markings, "lane_line_primitive_count", -1))
    lane_count = int(asset.parm("default_lane_count").eval())
    require(validation_stage == "post_commit_v24",
            f"V24 marking validation stage changed: {validation_stage}")
    require(intrusion == 0 and boundary_gap <= 0.001,
            f"V7/V24 marking clip failed: intrusion={intrusion} gap={boundary_gap}")
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
        "marking_validation_stage": validation_stage,
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


def _geometry_equivalence_snapshot(node: hou.Node) -> dict[str, Any]:
    node.cook(force=False)
    require(not node.errors(), f"Geometry equivalence errors at {node.name()}: {node.errors()}")
    require(not node.warnings(),
            f"Geometry equivalence warnings at {node.name()}: {node.warnings()}")
    geometry = node.geometry()
    positions = sorted(tuple(float(component) for component in point.position())
                       for point in geometry.points())
    area = 0.0
    for primitive in geometry.prims():
        points = primitive.points()
        if len(points) < 3:
            continue
        origin = points[0].position()
        for index in range(1, len(points) - 1):
            a = points[index].position() - origin
            b = points[index + 1].position() - origin
            area += 0.5 * a.cross(b).length()
    box = geometry.boundingBox()
    material_attribs = {}
    for name in ("shop_materialpath", "unity_material", "material_id"):
        attrib = geometry.findPrimAttrib(name)
        if attrib is not None:
            material_attribs[name] = sorted(str(primitive.attribValue(attrib))
                                            for primitive in geometry.prims())
    return {
        "points": len(geometry.points()),
        "primitives": len(geometry.prims()),
        "positions": positions,
        "bounds": tuple(float(value) for vector in (box.minvec(), box.maxvec())
                        for value in vector),
        "area": area,
        "primitive_groups": sorted((group.name(), len(group.prims()))
                                   for group in geometry.primGroups()),
        "point_groups": sorted((group.name(), len(group.points()))
                               for group in geometry.pointGroups()),
        "materials": material_attribs,
    }


def _require_geometry_equivalent(name: str, v1: dict[str, Any],
                                 v2: dict[str, Any]) -> dict[str, Any]:
    for key in ("points", "primitives", "primitive_groups", "point_groups", "materials"):
        require(v1[key] == v2[key],
                f"V18 {name} V1/V2 {key} changed: V1={v1[key]!r} V2={v2[key]!r}")
    require(len(v1["positions"]) == len(v2["positions"]),
            f"V18 {name} V1/V2 point count changed")
    point_error = max((max(abs(a - b) for a, b in zip(left, right))
                       for left, right in zip(v1["positions"], v2["positions"])),
                      default=0.0)
    bounds_error = max((abs(a - b) for a, b in zip(v1["bounds"], v2["bounds"])),
                       default=0.0)
    area_scale = max(abs(float(v1["area"])), 1e-12)
    area_relative_error = abs(float(v2["area"]) - float(v1["area"])) / area_scale
    require(point_error <= 1e-4,
            f"V18 {name} V1/V2 point error {point_error} exceeds 1e-4")
    require(bounds_error <= 1e-4,
            f"V18 {name} V1/V2 bounds error {bounds_error} exceeds 1e-4")
    require(area_relative_error <= 1e-5,
            f"V18 {name} V1/V2 area error {area_relative_error} exceeds 1e-5")
    return {
        "points": v2["points"], "primitives": v2["primitives"],
        "point_error": point_error, "bounds_error": bounds_error,
        "area_relative_error": area_relative_error,
    }


def _v18_output_snapshot(core: hou.Node) -> dict[str, Any]:
    geometry_nodes = {
        "road": "CITYROAD_UNITY_ROAD_NORMALS",
        "sidewalk": "CURB_SIDEWALK_STATS",
        "collision": "OUT_ROAD_COLLISION",
        "marking": "CITYROAD_MARKING_OUTPUT_CONTRACT",
    }
    geometry = {key: _geometry_equivalence_snapshot(require_node(core, node_name))
                for key, node_name in geometry_nodes.items()}
    street = {}
    for key, node_name in (
        ("lamps", "OUT_STREET_LAMPS"),
        ("trees", "OUT_STREET_TREES"),
        ("tree_pits", "OUT_STREET_TREE_PITS"),
    ):
        street[key] = _street_signature(_street_records(require_node(core, node_name)))
    return {"geometry": geometry, "street": street}


def validate_v18_cook_optimization(core: hou.Node,
                                   compare_switches: bool = True) -> dict[str, Any]:
    """V18 structural/index contracts; performance is gated separately."""

    segment_index = require_node(core, "GRAPH_SEGMENT_INDEX_V2").geometry()
    approach_index = require_node(core, "JUNCTION_APPROACH_INDEX_V2").geometry()
    junction_center_index = require_node(core, "JUNCTION_CENTER_INDEX_V2").geometry()
    corridor_index = require_node(core, "CORRIDOR_INTERVAL_INDEX_V2").geometry()
    graph_switch = require_node(core, "CITYROAD_GRAPH_V1_V2")
    road_switch = require_node(core, "CITYROAD_ROAD_SURFACE_V1_V2")
    adaptive_switch = require_node(core, "CITYROAD_ADAPTIVE_SURFACE_V1_V2")
    audit_switch = require_node(core, "CITYROAD_SIDEWALK_AUDIT_V1_V2")
    require(graph_switch.evalParm("input") == 1,
            "V18 graph V1/V2 switch is not on V2")
    require(road_switch.evalParm("input") == 1,
            "V18 road-surface V1/V2 switch is not on V2")
    require(adaptive_switch.evalParm("input") == 1,
            "V18 adaptive-surface V1/V2 switch is not on V2")
    require(audit_switch.evalParm("input") == 1,
            "V18 sidewalk audit switch is not on the Cook path")
    values = {
        "segment_count": int(detail_value(segment_index, "segment_index_count", -1)),
        "approach_count": int(detail_value(approach_index, "approach_index_count", -1)),
        "junction_count": int(detail_value(
            junction_center_index, "junction_center_index_count", -1)),
        "corridor_count": int(detail_value(corridor_index, "corridor_interval_count", -1)),
        "corridor_source_segment_count": int(detail_value(
            corridor_index, "corridor_source_segment_count", -1)),
        "segment_points": len(segment_index.points()),
        "approach_points": len(approach_index.points()),
        "junction_points": len(junction_center_index.points()),
        "corridor_points": len(corridor_index.points()),
    }
    require(values["segment_count"] > 0 and
            values["segment_count"] == values["segment_points"],
            f"V18 segment index count mismatch: {values}")
    require(values["approach_count"] > 0 and
            values["approach_count"] == values["approach_points"],
            f"V18 approach index count mismatch: {values}")
    require(values["junction_count"] > 0 and
            values["junction_count"] == values["junction_points"],
            f"V18 junction index count mismatch: {values}")
    require(values["corridor_count"] > 0 and
            values["corridor_count"] == values["corridor_points"],
            f"V18 corridor index count mismatch: {values}")
    require(values["corridor_source_segment_count"] > 0,
            f"V18 corridor source-segment count mismatch: {values}")

    corridor_attributes = (
        "source_primitive", "source_segment", "interval_start", "interval_end",
        "interval_start_boundary", "interval_end_boundary",
        "interval_start_approach", "interval_end_approach",
        "interval_start_tangent", "interval_end_tangent",
    )
    missing_corridor_attributes = [
        name for name in corridor_attributes
        if corridor_index.findPointAttrib(name) is None
    ]
    require(not missing_corridor_attributes,
            f"V18 corridor attributes missing: {missing_corridor_attributes}")
    unbound_boundaries = 0
    for point in corridor_index.points():
        if (int(point.attribValue("interval_start_boundary")) and
                int(point.attribValue("interval_start_approach")) < 0):
            unbound_boundaries += 1
        if (int(point.attribValue("interval_end_boundary")) and
                int(point.attribValue("interval_end_approach")) < 0):
            unbound_boundaries += 1
    require(unbound_boundaries == 0,
            f"V18 corridor has {unbound_boundaries} unbound junction boundaries")
    values["unbound_corridor_boundaries"] = unbound_boundaries

    stable_approach_ids = sorted(
        int(point.attribValue("stable_approach_id"))
        for point in approach_index.points())
    stable_junction_ids = sorted(
        int(point.attribValue("stable_junction_id"))
        for point in junction_center_index.points())
    require(stable_approach_ids == list(range(values["approach_count"])),
            "V18 stable Approach ids are not dense and deterministic")
    require(stable_junction_ids == list(range(values["junction_count"])),
            "V18 stable Junction ids are not dense and deterministic")

    for switch_name in (
        "CITYROAD_CROSSWALK_ENABLE_V2", "CITYROAD_MARKING_ENABLE_V2",
        "CITYROAD_STREET_LAMP_ENABLE_V2", "CITYROAD_STREET_TREE_ENABLE_V2",
    ):
        require(require_node(core, switch_name).evalParm("input") == 1,
                f"V18 early feature gate is not enabled by its default: {switch_name}")

    for node_name in ("ROAD_BUILD_SURFACE_V2",
                      "ROAD_BUILD_ADAPTIVE_CORNER_SURFACE_V2"):
        source = require_node(core, node_name).parm("snippet").evalAsString()
        require("CITYROAD_COOK_OPTIMIZATION_V18_CORRIDOR_CONSUMER" in source,
                f"V18 road node does not consume Corridor intervals: {node_name}")
        require("Shared interval table already validated this trim." in source,
                f"V18 road node retained the per-segment junction diagnostic: {node_name}")
    require("CITYROAD_COOK_OPTIMIZATION_V18_MARKING_TABLE" in
            require_node(core, "CITYROAD_BUILD_STATIC_MARKING_MESH")
            .parm("snippet").evalAsString(),
            "V18 static marking branch did not remove duplicate junction work")
    require("CITYROAD_COOK_OPTIMIZATION_V18_APPROACH_MARKING_OWNER" in
            require_node(core, "CITYROAD_BUILD_APPROACH_MARKINGS_V5")
            .parm("snippet").evalAsString(),
            "V18 Approach marking branch is not the junction-marking owner")
    require("CITYROAD_COOK_OPTIMIZATION_V18_LAMP_TREE_TWO_POINTER" in
            require_node(core, "CITYROAD_STREET_BUILD_TREES_V1")
            .parm("snippet").evalAsString(),
            "V18 street tree branch does not use the ordered lamp merge")
    for node_name in (
        "GRAPH_SEGMENT_INDEX_V2", "JUNCTION_APPROACH_INDEX_V2",
        "JUNCTION_CENTER_INDEX_V2",
        "CORRIDOR_INTERVAL_INDEX_V2", "GRAPH_CLASSIFY_JUNCTIONS",
        "ROAD_BUILD_SURFACE_V2", "ROAD_BUILD_ADAPTIVE_CORNER_SURFACE_V2",
        "CITYROAD_TOPOLOGY_CLASSIFY_ROAD",
        "CITYROAD_STREET_BUILD_LAMPS_V1", "CITYROAD_STREET_BUILD_TREES_V1",
    ):
        node = require_node(core, node_name)
        require(not node.errors(), f"V18 errors at {node_name}: {node.errors()}")
        require(not node.warnings(), f"V18 warnings at {node_name}: {node.warnings()}")
    if not compare_switches:
        values["equivalence"] = "deferred_to_disposable_unlocked_copy"
        return values
    try:
        graph_switch.parm("input").set(0)
        road_switch.parm("input").set(0)
        adaptive_switch.parm("input").set(0)
        v1 = _v18_output_snapshot(core)
        graph_switch.parm("input").set(1)
        road_switch.parm("input").set(1)
        adaptive_switch.parm("input").set(1)
        v2 = _v18_output_snapshot(core)
        equivalence = {
            key: _require_geometry_equivalent(key, v1["geometry"][key],
                                              v2["geometry"][key])
            for key in v1["geometry"]
        }
        require(v1["street"] == v2["street"],
                "V18 street-furniture V1/V2 deterministic signature changed")

        # The exact sidewalk audit remains available on input 0 and is cooked
        # explicitly by cumulative contracts; input 1 is the production path.
        audit_switch.parm("input").set(0)
        audit_v1 = _geometry_equivalence_snapshot(
            require_node(core, "SIDEWALK_REGION_CONNECTIVITY"))
        audit_switch.parm("input").set(1)
        audit_v2 = _geometry_equivalence_snapshot(
            require_node(core, "SIDEWALK_REGION_CONNECTIVITY"))
        equivalence["sidewalk_audit_path"] = _require_geometry_equivalent(
            "sidewalk_audit_path", audit_v1, audit_v2)
        values["equivalence"] = equivalence
        values["street_signatures_equal"] = True
    finally:
        graph_switch.parm("input").set(1)
        road_switch.parm("input").set(1)
        adaptive_switch.parm("input").set(1)
        audit_switch.parm("input").set(1)
    return values


def debug_v18_graph(asset: hou.Node) -> dict[str, Any]:
    core = require_node(asset, CORE_NAME)
    switch = require_node(core, "CITYROAD_GRAPH_V1_V2")
    graph = require_node(core, "GRAPH_CLASSIFY_JUNCTIONS")
    snapshots = {}
    try:
        for mode in (0, 1):
            switch.parm("input").set(mode)
            graph.cook(force=False)
            geometry = graph.geometry()
            primitive_rows = []
            for primitive in geometry.prims():
                def prim_value(name, fallback):
                    attrib = geometry.findPrimAttrib(name)
                    return primitive.attribValue(attrib) if attrib is not None else fallback
                primitive_rows.append((
                    int(prim_value("road_id", -1)),
                    int(prim_value("road_level", -1)),
                    int(prim_value("junction_id", -1)),
                    str(prim_value("junction_type", "")),
                ))
            helper_rows = []
            for point in geometry.points():
                attrib = geometry.findPointAttrib("junction_id")
                if attrib is None:
                    continue
                junction_id = int(point.attribValue(attrib))
                if junction_id < 0:
                    continue
                helper_rows.append((
                    junction_id,
                    tuple(round(float(value), 6) for value in point.position()),
                ))
            snapshots[str(mode)] = {
                "primitives": primitive_rows,
                "helpers": sorted(set(helper_rows)),
                "detail": {
                    name: detail_value(geometry, name, -1)
                    for name in (
                        "cityroad_graph_segment_count",
                        "cityroad_graph_broadphase_candidates",
                        "cityroad_graph_exact_tests",
                    )
                },
            }
    finally:
        switch.parm("input").set(1)
    left, right = snapshots["0"], snapshots["1"]
    return {
        "v1": left,
        "v2": right,
        "primitive_differences": [
            {"index": index, "v1": v1, "v2": v2}
            for index, (v1, v2) in enumerate(zip(left["primitives"], right["primitives"]))
            if v1 != v2
        ],
        "helpers_only_v1": sorted(set(left["helpers"]) - set(right["helpers"])),
        "helpers_only_v2": sorted(set(right["helpers"]) - set(left["helpers"])),
    }


def debug_remote_v18_graph(asset_path: str, host: str, port: int) -> dict[str, Any]:
    import hrpyc
    connection, _remote_hou = hrpyc.import_remote_module(host, port, "hou")
    try:
        tools_path = str(SCRIPT_DIR).replace("\\", "/")
        connection.execute(
            "import sys, importlib, hou; "
            f"sys.path.insert(0, {tools_path!r}) if {tools_path!r} not in sys.path else None; "
            "import validate_cityroad_contract as _pcg_cityroad_contract; "
            "importlib.reload(_pcg_cityroad_contract)")
        payload = connection.eval(
            "_pcg_cityroad_contract.json.dumps("
            f"_pcg_cityroad_contract.debug_v18_graph(hou.node({asset_path!r})), "
            "ensure_ascii=False)")
        return json.loads(str(payload))
    finally:
        connection.close()


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
        "subnet_layout": validate_subnet_layout(core),
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
        "v18_cook_optimization": validate_v18_cook_optimization(
            core, compare_switches=not require_locked),
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
            "import sys, importlib, hou; "
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
    # A locked instance proves the persisted definition is consumable.  The
    # internal rollback switch is intentionally not public/editable, so run
    # its equivalence comparison only after unlocking this disposable copy.
    fresh.allowEditingOfContents(propagate=True)
    result["v18_cook_optimization"] = validate_v18_cook_optimization(
        require_node(fresh, CORE_NAME), compare_switches=True)
    result["locked_validation_completed_before_equivalence"] = True
    result["source"] = "fresh_locked_instance"
    result["hip"] = str(hip_path)
    result["hda"] = str(hda_path)
    result["saved"] = False
    result["configuration_copy_skipped"] = skipped
    try:
        from validate_cityroad_short_curve_markings_v24 import run as validate_short_curves
        result["v24_short_curve_markings"] = validate_short_curves(hda_path, "fixed")
    except Exception as exception:
        raise ContractFailure(
            f"V24 short-curve marking regression failed: {exception}") from exception
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
        tools_path = str(SCRIPT_DIR).replace("\\", "/")
        connection.execute(
            "import sys, importlib, hou; "
            f"sys.path.insert(0, {tools_path!r}) if {tools_path!r} not in sys.path else None; "
            "import validate_cityroad_contract as _pcg_cityroad_contract; "
            "importlib.reload(_pcg_cityroad_contract)")
        return str(connection.eval(
            f"_pcg_cityroad_contract.public_interface_hash(hou.node({asset_path!r}))"))
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
    parser.add_argument("--debug-v18-graph", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if args.debug_v18_graph:
        print(json.dumps(debug_remote_v18_graph(args.asset, args.host, args.port),
                         ensure_ascii=False, indent=2))
        return 0
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
