"""Validate the persisted REV4.1 StreetBuilding HDA in isolated hython."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
from pathlib import Path
import sys
from typing import Any

import hou


ASSET_TYPE = "pcgbike::StreetBuilding::1.0"
REVISION = "STREETBUILDING_REV4_1_SINGLE_ENTRANCE_EDGE_COLUMNS"
CONTRACT_VERSION = "StreetBuilding.DirectInstances.4.1"
SOURCE_PREFIX = "Assets/PCG/Art/Downtown City MegaKit[Standard]/Exports/FBX (Unity)/"
OUTPUTS = (
    "OUT_BUILDING_LOD0",
    "OUT_BUILDING_LOD1",
    "OUT_BUILDING_LOD2",
    "OUT_DETAIL_INSTANCES",
    "OUT_BUILDING_COLLISION",
    "OUT_BUILDING_METADATA",
)
CATALOG = "\n".join((
    f"Entrance|entrance_metal|0|{SOURCE_PREFIX}DoorFrame_Metal_Single.fbx|0|0|0|0|0|0",
    f"Entrance|entrance_metal|1|{SOURCE_PREFIX}Door_2.fbx|-0.5|0|0|0|0|0",
    f"GroundShop|shop_metal|0|{SOURCE_PREFIX}Metal_FirstFloor_Window.fbx|0|0|0|0|0|0",
    f"GroundShop|shop_trim|0|{SOURCE_PREFIX}Trim_FirstFloor_Window_001.fbx|0|0|0|0|0|0",
    f"Cornice|brick_center|0|{SOURCE_PREFIX}Cornice_Brick_Center.fbx|0|0|0|0|0|0",
    f"MiddleWindow|trim|0|{SOURCE_PREFIX}Brick_Window_Trim.fbx|0|0|0|0|0|0",
    f"MiddleWindow|trim_single|0|{SOURCE_PREFIX}Brick_Window_Trim_Single.fbx|0|0|0|0|0|0",
    f"FacadeColumn|trim_ground|0|{SOURCE_PREFIX}Trim_Column_Center.fbx|0|0|0|0|0|0",
    f"FacadeColumn|brick_upper|0|{SOURCE_PREFIX}Brick_Column_Small.fbx|0|0|0|0|0|0",
))


class ContractFailure(RuntimeError):
    pass


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ContractFailure(message)


def point_values(geometry: hou.Geometry, name: str) -> list[Any]:
    attribute = geometry.findPointAttrib(name)
    require(attribute is not None, f"Missing point attribute {name}")
    return [point.attribValue(attribute) for point in geometry.points()]


def geometry_signature(geometry: hou.Geometry) -> str:
    attributes = sorted(attribute.name() for attribute in geometry.pointAttribs())
    payload = {
        "points": [[round(float(c), 6) for c in point.position()] for point in geometry.points()],
        "attributes": {
            name: [point.attribValue(name) for point in geometry.points()]
            for name in attributes
        },
        "primitives": geometry.intrinsicValue("primitivecount"),
    }
    return hashlib.sha256(
        json.dumps(payload, ensure_ascii=False, sort_keys=True, default=list).encode("utf-8")
    ).hexdigest()


def output_node(asset: hou.Node, name: str) -> hou.Node:
    node = asset.node(f"StreetBuildingCore/{name}")
    require(node is not None, f"Missing output node {name}")
    return node


def output_geometry(asset: hou.Node, name: str) -> hou.Geometry:
    node = output_node(asset, name)
    try:
        node.cook(force=True)
    except hou.OperationFailed as exception:
        raise ContractFailure(f"{name} cook failed: {node.errors()}") from exception
    require(not node.errors(), f"{name} cook errors: {node.errors()}")
    require(not node.warnings(), f"{name} cook warnings: {node.warnings()}")
    return node.geometry()


def assert_interface(asset: hou.Node, contract: dict[str, Any]) -> None:
    require(asset.type().name() == ASSET_TYPE, f"Wrong asset type: {asset.type().name()}")
    require(asset.type().maxNumInputs() == 3, "StreetBuilding must retain exactly three inputs")
    definition = asset.type().definition()
    require(definition is not None, "StreetBuilding definition is missing")
    require(REVISION in (definition.comment() or ""), "REV4 definition marker is missing")

    group = asset.parmTemplateGroup()
    for name, expected in contract["public_defaults"].items():
        parm = asset.parm(name)
        require(parm is not None, f"Missing public parameter {name}")
        actual = parm.eval()
        if isinstance(expected, float):
            require(abs(float(actual) - expected) <= 1e-6,
                    f"Default mismatch for {name}: {actual} != {expected}")
        else:
            require(actual == expected, f"Default mismatch for {name}: {actual!r} != {expected!r}")
    catalog_template = group.find("unity_instance_catalog")
    require(catalog_template is not None and isinstance(catalog_template, hou.StringParmTemplate),
            "unity_instance_catalog must exist as a string transport parameter")
    for name, expected_items in contract["menus"].items():
        template = group.find(name)
        require(template is not None, f"Missing menu {name}")
        require(list(template.menuItems()) == expected_items,
                f"Menu mismatch for {name}: {template.menuItems()}")


def assert_network(asset: hou.Node, contract: dict[str, Any]) -> None:
    core = asset.node(contract["core_node"])
    require(core is not None, "StreetBuildingCore is missing")
    for name, expected_type in contract["required_nodes"].items():
        node = core.node(name)
        require(node is not None, f"Missing required node {name}")
        require(node.type().name() == expected_type,
                f"Node {name} type {node.type().name()} != {expected_type}")
    for name in ("FIX_EXTERNAL_NORMALS_LOD0", "FIX_EXTERNAL_NORMALS_LOD1", "FIX_EXTERNAL_NORMALS_LOD2"):
        require(core.node(name) is None, f"Legacy node {name} remains in REV4")
    switch = core.node("LOD0_MODULE_SOURCE_SWITCH")
    require(switch.input(1) == core.node("DIRECT_UNITY_INSTANCE_FACADE"),
            "REV4 direct instance node is not connected to the LOD0 source switch")
    require(output_node(asset, "OUT_BUILDING_LOD0").input(0) == switch,
            "LOD0 output does not use the source switch")
    empty = core.node("EMPTY_GEOMETRY")
    for name in OUTPUTS[1:]:
        require(output_node(asset, name).input(0) == empty,
                f"{name} must be empty in the REV4 facade-only phase")


def configure_direct(asset: hou.Node, width: float = 12.0) -> None:
    asset.parm("module_source").set(1)
    asset.parm("unity_instance_catalog").set(CATALOG)
    asset.parm("internal_width").set(width)
    asset.parm("ground_floor_height").set(4.0)
    asset.parm("typical_floor_height").set(3.0)
    asset.parm("floor_count").set(4)
    asset.parm("rear_mode").set(0)
    asset.parm("side_mode").set(1)
    asset.parm("generate_roof").set(0)
    asset.parm("generate_lods").set(0)
    asset.parm("generate_attachments").set(0)


def assert_internal_proxy(asset: hou.Node) -> dict[str, int]:
    asset.parm("module_source").set(0)
    geometry = output_geometry(asset, "OUT_BUILDING_LOD0")
    require(geometry.intrinsicValue("primitivecount") > 0,
            "Internal Proxy no longer emits its existing LOD0 geometry")
    for point in geometry.points():
        require(all(math.isfinite(float(value)) for value in point.position()),
                "Internal Proxy contains NaN/Inf points")
    return {
        "points": int(geometry.intrinsicValue("pointcount")),
        "primitives": int(geometry.intrinsicValue("primitivecount")),
    }


def assert_direct_instances(asset: hou.Node, contract: dict[str, Any]) -> dict[str, Any]:
    configure_direct(asset)
    geometry = output_geometry(asset, "OUT_BUILDING_LOD0")
    require(geometry.intrinsicValue("primitivecount") == 0,
            "Direct instance output contains rebuilt polygon/packed geometry")
    require(geometry.intrinsicValue("pointcount") == 39,
            f"12m/4-floor facade must emit 39 part points, got {len(geometry.points())}")
    require(geometry.findPointAttrib("N") is None,
            "Direct instance output must remove N when orient is authored")
    actual_attributes = {attribute.name() for attribute in geometry.pointAttribs()}
    missing = sorted(set(contract["required_attributes"]) - actual_attributes)
    require(not missing, f"Direct output missing attributes: {missing}")

    paths = [str(value) for value in point_values(geometry, "unity_instance")]
    require(all(path.startswith(SOURCE_PREFIX) and path.endswith(".fbx") for path in paths),
            "unity_instance paths were rewritten away from original MegaKit FBX assets")
    require(set(paths).issubset({row.split("|")[3] for row in CATALOG.splitlines()}),
            "Direct output contains a path not present in the compiled catalog")
    roles = [str(value) for value in point_values(geometry, "module_role")]
    require(roles.count("Entrance") == 2, "Entrance must emit frame + door source parts")
    require(roles.count("GroundShopDoor") == 0, "GroundShopDoor must be absent in REV4.1")
    require(roles.count("GroundShop") == 5, "Ground floor must emit five shop windows")
    require(roles.count("Cornice") == 6, "Header must emit six original cornice instances")
    require(roles.count("MiddleWindow") == 18, "Three upper floors must emit 18 windows")
    require(roles.count("FacadeColumn") == 8,
            "Two ground and six upper edge-column instances are required")

    cells = [int(value) for value in point_values(geometry, "cell_index")]
    entrance_cells = {cell for cell, value in zip(cells, point_values(geometry, "is_building_entrance"))
                      if int(value) == 1}
    shop_door_cells = {cell for cell, value in zip(cells, point_values(geometry, "is_shop_entrance"))
                       if int(value) == 1}
    require(entrance_cells == {3}, f"Expected one centered entrance cell, got {entrance_cells}")
    require(not shop_door_cells, f"Unexpected shop-door cells: {shop_door_cells}")

    for point, role, cell, path in zip(geometry.points(), roles, cells, paths):
        if role == "FacadeColumn" or path.endswith("Door_2.fbx"):
            continue
        expected_houdini_x = -(-6.0 + (cell + 0.5) * 2.0)
        require(abs(float(point.position()[0]) - expected_houdini_x) <= 1e-6,
                f"Cell {cell} is not emitted at its 2m cell center")

    upper = [(int(floor), float(point.position()[1])) for point, role, floor in zip(
        geometry.points(), roles, point_values(geometry, "floor_index")) if role == "MiddleWindow"]
    expected_y = {1: 4.0, 2: 7.0, 3: 10.0}
    require(all(abs(y - expected_y[floor]) <= 1e-6 for floor, y in upper),
            f"Upper floor rows do not follow 4m + 3m native grid: {upper}")
    variants_by_cell = {}
    for cell, role, variant in zip(cells, roles, point_values(geometry, "module_variant")):
        if role == "MiddleWindow":
            variants_by_cell.setdefault(cell, str(variant))
    require([variants_by_cell[index] for index in range(6)] ==
            ["trim", "trim", "trim_single", "trim_single", "trim", "trim"],
            f"Paired A A B B A A rhythm failed: {variants_by_cell}")
    column_points = [point for point, role in zip(geometry.points(), roles)
                     if role == "FacadeColumn"]
    column_x = sorted({round(float(point.position()[0]), 6) for point in column_points})
    require(column_x == [-6.0, 6.0],
            f"Edge columns must sit on the +/-6m facade boundaries: {column_x}")
    column_rows = sorted(round(float(point.position()[1]), 6) for point in column_points)
    require(column_rows == [0.0, 0.0, 4.0, 4.0, 7.0, 7.0, 10.0, 10.0],
            f"Edge-column vertical rows are incorrect: {column_rows}")
    for name in OUTPUTS[1:]:
        empty = output_geometry(asset, name)
        require(len(empty.points()) == 0 and len(empty.prims()) == 0,
                f"{name} is not empty in facade-only mode")

    before = geometry_signature(geometry)
    after = geometry_signature(output_geometry(asset, "OUT_BUILDING_LOD0"))
    require(before == after, "Same direct catalog and parameters produced a different hash")
    return {"points": len(geometry.points()), "unique_assets": len(set(paths)), "sha256": before}


def assert_width_contract() -> dict[str, Any]:
    results: dict[str, Any] = {}
    for width in (10.0, 12.0):
        instance = hou.node("/obj").createNode(ASSET_TYPE, f"VERIFY_WIDTH_{int(width)}")
        configure_direct(instance, width)
        geometry = output_geometry(instance, "OUT_BUILDING_LOD0")
        require(len(geometry.prims()) == 0 and len(geometry.points()) > 0,
                f"Valid {width}m frontage did not emit points")
        results[str(width)] = len(geometry.points())
        instance.destroy()
    for width in (7.0, 11.0, 15.0):
        instance = hou.node("/obj").createNode(ASSET_TYPE, f"VERIFY_INVALID_WIDTH_{int(width)}")
        configure_direct(instance, width)
        node = output_node(instance, "OUT_BUILDING_LOD0")
        failed = False
        try:
            node.cook(force=True)
            failed = bool(node.errors())
        except hou.OperationFailed:
            failed = True
        require(failed, f"Non-2m frontage {width}m did not fail closed")
        results[str(width)] = "rejected"
        instance.destroy()
    return results


def validate(hda_path: Path, hip_path: Path, contract_path: Path) -> dict[str, Any]:
    require(hda_path.is_file(), f"HDA not found: {hda_path}")
    require(hip_path.is_file(), f"HIP not found: {hip_path}")
    contract = json.loads(contract_path.read_text(encoding="utf-8"))
    require(contract["revision"] == REVISION, "Contract revision does not match validator")
    require(contract["contract_version"] == CONTRACT_VERSION,
            "Contract version does not match validator")
    hou.hipFile.clear(suppress_save_prompt=True)
    hou.hipFile.load(str(hip_path), suppress_save_prompt=True, ignore_load_warnings=False)
    hou.hda.installFile(str(hda_path), change_oplibraries_file=False, force_use_assets=True)
    fresh = hou.node("/obj").createNode(ASSET_TYPE, "VERIFY_STREETBUILDING_REV4_LOCKED")
    require(not fresh.isEditable(), "Fresh REV4 validation instance must remain locked")
    assert_interface(fresh, contract)
    assert_network(fresh, contract)
    internal = assert_internal_proxy(fresh)
    direct = assert_direct_instances(fresh, contract)
    widths = assert_width_contract()
    return {
        "status": "PASS",
        "asset_type": fresh.type().name(),
        "instance": fresh.path(),
        "locked": not fresh.isEditable(),
        "internal_proxy": internal,
        "direct_instances": direct,
        "width_contract": widths,
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    default_root = Path(__file__).resolve().parents[4]
    parser.add_argument("--project-root", type=Path, default=default_root)
    parser.add_argument("--hda", type=Path)
    parser.add_argument("--hip", type=Path)
    parser.add_argument("--contract", type=Path)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    root = args.project_root.resolve()
    hda = (args.hda or root / "Assets/PCG/HDA/City/StreetBuilding.hda").resolve()
    hip = (args.hip or root / "HoudiniProject/PCG_Track_21.0.440/PCG_Bike_StreetBuilding.hip").resolve()
    contract = (args.contract or root / "HoudiniProject/PCG_Track_21.0.440/scripts/contracts/streetbuilding_contract.json").resolve()
    print(json.dumps(validate(hda, hip, contract), ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (ContractFailure, OSError, ValueError, json.JSONDecodeError) as exception:
        print(f"STREETBUILDING_CONTRACT_FAIL: {exception}", file=sys.stderr)
        raise SystemExit(1)
