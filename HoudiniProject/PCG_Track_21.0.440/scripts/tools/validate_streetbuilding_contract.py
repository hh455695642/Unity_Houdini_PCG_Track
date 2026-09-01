"""Validate persisted StreetBuilding V9 from a fresh locked HDA instance."""

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
REVISION = "STREETBUILDING_V9_STYLECONFIG_SBV4_RULES"
CONTRACT_VERSION = "StreetBuilding.StyleConfig.9.0"
SOURCE_PREFIX = "Assets/PCG/Art/Downtown City MegaKit[Standard]/Exports/FBX (Unity)/"
DETAIL_PREFIX = "Assets/PCG/Art/StreetBuilding/NA_Brick_MixedUse_01/Prefabs/ValidationDetails/"
OUTPUTS = ("OUT_BUILDING_LOD0", "OUT_BUILDING_LOD1", "OUT_BUILDING_LOD2",
           "OUT_DETAIL_INSTANCES", "OUT_BUILDING_COLLISION", "OUT_BUILDING_METADATA")

V1 = "\n".join((
    f"Entrance|entrance_metal|0|{SOURCE_PREFIX}DoorFrame_Metal_Single.fbx|0|0|0|0|0|0",
    f"Entrance|entrance_metal|1|{SOURCE_PREFIX}Door_2.fbx|-0.5|0|-0.12|0|0|0",
    f"GroundShop|shop_metal|0|{SOURCE_PREFIX}Metal_FirstFloor_Window.fbx|0|0|0|0|0|0",
    f"GroundShop|shop_trim|0|{SOURCE_PREFIX}Trim_FirstFloor_Window_001.fbx|0|0|0|0|0|0",
    f"Cornice|brick_center|0|{SOURCE_PREFIX}Cornice_Brick_Center.fbx|0|0|0|0|0|0",
    f"MiddleWindow|trim|0|{SOURCE_PREFIX}Brick_Window_Trim.fbx|0|0|0|0|0|0",
    f"MiddleWindow|trim_single|0|{SOURCE_PREFIX}Brick_Window_Trim_Single.fbx|0|0|0|0|0|0",
    f"FacadeColumn|trim_ground|0|{SOURCE_PREFIX}Trim_Column_Center.fbx|0|0|0|0|0|0",
    f"FacadeColumn|brick_upper|0|{SOURCE_PREFIX}Brick_Column_Small.fbx|0|0|0|0|0|0",
))


def v2(role: str, variant: str, asset: str, width: float = 2, height: float = 3,
       weight: float = 1, part: int = 0, x: float = 0, y: float = 0, z: float = 0) -> str:
    return (f"M|{role}|{variant}|{part}|{SOURCE_PREFIX}{asset}.fbx|{x}|{y}|{z}|0|0|0|"
            f"{width}|{height}|{weight}")


def detail(role: str, variant: str, path: str, width: float = 2,
           height: float = 1, weight: float = 1) -> str:
    return f"M|{role}|{variant}|0|{path}|0|0|0|0|0|0|{width}|{height}|{weight}"


V2 = "\n".join((
    "SBV2|na_brick_mixeduse_01|2|4|3",
    v2("Entrance", "entrance_metal", "DoorFrame_Metal_Single", part=0),
    v2("Entrance", "entrance_metal", "Door_2", part=1, x=-.5, z=-.12),
    v2("Entrance", "entrance_trim", "DoorFrame_Trim", weight=.6, part=0),
    v2("Entrance", "entrance_trim", "Door_1", weight=.6, part=1, x=-.5),
    v2("GroundShop", "shop_metal", "Metal_FirstFloor_Window", height=4),
    v2("GroundShop", "shop_trim", "Trim_FirstFloor_Window_001", height=4),
    v2("GroundWall", "brick_ground", "Brick_Plain_4", height=4),
    v2("Cornice", "brick_center", "Cornice_Brick_Center", height=1),
    v2("Cornice", "metal_center", "Cornice_Metal_Center", height=1, weight=.3),
    v2("MiddleWindow", "trim", "Brick_Window_Trim"),
    v2("MiddleWindow", "trim_single", "Brick_Window_Trim_Single"),
    v2("MiddleWindow", "curved_double", "Brick_Window_CurvedDouble", width=4, weight=.35),
    v2("MiddleBlank", "brick_plain", "Brick_Plain_3"),
    v2("MiddleBlank", "brick_clean", "Brick_Plain_3_noWear", weight=.5),
    v2("SideWall", "brick_ground", "Brick_Plain_4", height=4),
    v2("SideWall", "brick_upper", "Brick_Plain_3"),
    v2("SideWall", "brick_upper_clean", "Brick_Plain_3_noWear", weight=.5),
    v2("RearWall", "brick_ground", "Brick_Plain_4", height=4),
    v2("RearWall", "brick_upper", "Brick_Plain_3"),
    v2("RearWall", "brick_upper_clean", "Brick_Plain_3_noWear", weight=.5),
    v2("FacadeColumn", "trim_ground", "Trim_Column_Center"),
    v2("FacadeColumn", "brick_upper", "Brick_Column_Small"),
    v2("RoofSurface", "roof_2x2", "Roof_2x2", height=2, y=.2),
    detail("Parapet", "straight_2m", DETAIL_PREFIX + "PF_SB_NAB01_Parapet_Straight.prefab",
           height=.6),
    detail("ParapetCorner", "corner_90", DETAIL_PREFIX + "PF_SB_NAB01_Parapet_Corner.prefab",
           height=.6),
    detail("Awning", "validation_canopy", DETAIL_PREFIX + "PF_SB_NAB01_Awning_Validation.prefab"),
    detail("Sign", "validation_board", DETAIL_PREFIX + "PF_SB_NAB01_Sign_Validation.prefab"),
    detail("FireEscape", "validation_two_floor",
           DETAIL_PREFIX + "PF_SB_NAB01_FireEscape_Validation.prefab", width=4, height=6),
    detail("ACUnit", "wall_unit", SOURCE_PREFIX + "Prop_ACUnit.fbx"),
    detail("RoofProp", "water_tank", DETAIL_PREFIX + "PF_SB_NAB01_Roof_WaterTank.prefab",
           height=2, weight=1),
    detail("RoofProp", "roof_vent", DETAIL_PREFIX + "PF_SB_NAB01_Roof_Vent.prefab",
           height=2, weight=.7),
    detail("RoofProp", "mechanical_box", DETAIL_PREFIX + "PF_SB_NAB01_Roof_MechanicalBox.prefab",
           height=2, weight=.5),
))

V3 = V2.replace("SBV2|na_brick_mixeduse_01|2|4|3",
                "SBV3|na_brick_mixeduse_01|2|4|3|validation_family", 1) + "\n" + detail(
    "ParapetConcaveCorner", "concave_90",
    "Assets/PCG/Art/StreetBuilding/urban_brick_mixeduse_01/Prefabs/"
    "PF_SB_urban_brick_mixeduse_01_Parapet_ConcaveCorner.prefab", height=.6)


def v4(role: int, variant: str, path: str, width: int = 1, height: float = 3,
       weight: float = 1, facades: int = 15, floors: int = 7) -> str:
    return (f"M|0|{role}|{variant}|{path}|{width}|1|2|{height}|{weight}|"
            f"{facades}|{floors}|2|{height}|.2|-1|0|-.1")


V4 = "\n".join((
    "SBV4|test_style|2|4|3",
    v4(3, "entrance", "Assets/Test/entrance.prefab", height=4),
    v4(0, "shop", "Assets/Test/shop.prefab", height=4),
    v4(1, "shop_door", "Assets/Test/shop_door.prefab", height=4),
    v4(2, "ground", "Assets/Test/ground.prefab", height=4),
    v4(4, "window_a", "Assets/Test/window_a.prefab"),
    v4(4, "window_b", "Assets/Test/window_b.prefab"),
    v4(5, "blank", "Assets/Test/blank.prefab"),
    v4(10, "side_ground", "Assets/Test/side_ground.prefab", height=4),
    v4(10, "side_upper", "Assets/Test/side_upper.prefab"),
    v4(11, "rear_ground", "Assets/Test/rear_ground.prefab", height=4),
    v4(11, "rear_upper", "Assets/Test/rear_upper.prefab"),
    v4(8, "cornice", "Assets/Test/cornice.prefab", height=1),
    v4(12, "column_ground", "Assets/Test/column_ground.prefab", height=4),
    v4(12, "column_upper", "Assets/Test/column_upper.prefab"),
    v4(19, "roof", "Assets/Test/roof.prefab", height=2, floors=4),
    v4(9, "parapet", "Assets/Test/parapet.prefab", height=.6, floors=4),
    v4(20, "corner", "Assets/Test/corner.prefab", height=.6, floors=4),
    v4(21, "concave", "Assets/Test/concave.prefab", height=.6, floors=4),
    v4(14, "awning", "Assets/Test/awning.prefab", height=1),
    v4(15, "sign", "Assets/Test/sign.prefab", height=1),
    v4(16, "escape", "Assets/Test/escape.prefab", width=2, height=6),
    v4(17, "ac", "Assets/Test/ac.prefab", height=1),
    v4(18, "tank", "Assets/Test/tank.prefab", height=2),
))


class ContractFailure(RuntimeError):
    pass


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ContractFailure(message)


def node(asset: hou.Node, name: str) -> hou.Node:
    result = asset.node(f"StreetBuildingCore/{name}")
    require(result is not None, f"Missing node {name}")
    return result


def geometry(asset: hou.Node, name: str = "OUT_BUILDING_LOD0") -> hou.Geometry:
    output = node(asset, name)
    try:
        output.cook(force=True)
    except hou.OperationFailed as exception:
        raise ContractFailure(f"{name} cook failed: {output.errors()}") from exception
    require(not output.errors(), f"{name} errors: {output.errors()}")
    require(not output.warnings(), f"{name} warnings: {output.warnings()}")
    return output.geometry()


def signature(value: hou.Geometry) -> str:
    names = sorted(attribute.name() for attribute in value.pointAttribs())
    payload = {
        "P": [[round(float(component), 6) for component in point.position()] for point in value.points()],
        "a": {name: [point.attribValue(name) for point in value.points()] for name in names},
        "prims": value.intrinsicValue("primitivecount"),
    }
    return hashlib.sha256(json.dumps(payload, sort_keys=True, default=list).encode()).hexdigest()


def quaternion_matches(actual, yaw_degrees: float) -> bool:
    half = math.radians(yaw_degrees) * .5
    expected = (0.0, math.sin(half), 0.0, math.cos(half))
    dot = sum(float(a) * b for a, b in zip(actual, expected))
    return abs(abs(dot) - 1.0) <= 1e-4


def assert_ac_support_plane(point: hou.Point, width: float, depth: float) -> None:
    face = point.intAttribValue("face_index")
    x, _, z = (float(value) for value in point.position())
    plane_error = abs(x - width * .5) if face == 1 else (
        abs(x + width * .5) if face == 2 else abs(z + depth))
    require(plane_error <= .001,
            f"ACUnit pivot is {plane_error:.4f}m away from face {face} support plane")


def configure(asset: hou.Node, catalog: str, *, width: float = 12, depth: float = 10,
              floors: int = 4, seed: int = 29, rhythm: int = 3, rear: int = 2,
              side: int = 2, roof: int = 1, density: float = .6,
              attachments: int = 1, module_source: int = 1, shape: int = 0,
              notch_width: float = 4, notch_depth: float = 4, notch_side: int = 0) -> None:
    style = catalog.split("|", 2)[1] if catalog.startswith(("SBV2|", "SBV3|", "SBV4|")) else "na_brick_mixeduse_01"
    values = {
        "module_source": module_source, "unity_instance_catalog": catalog,
        "style_id": style, "internal_width": width,
        "internal_depth": depth, "ground_floor_height": 4.0,
        "typical_floor_height": 3.0, "floor_count": floors, "parapet_height": .6,
        "facade_rhythm": rhythm, "detail_density": density,
        "generate_attachments": attachments, "rear_mode": rear, "side_mode": side,
        "generate_roof": roof, "generate_lods": 0, "seed": seed,
        "massing_shape": shape, "notch_width": notch_width,
        "notch_depth": notch_depth, "notch_side": notch_side,
        "unity_generation_rules": "", "site_source": 0, "corner_building": 0,
    }
    for name, value in values.items():
        asset.parm(name).set(value)


def assert_interface(asset: hou.Node, contract: dict[str, Any]) -> None:
    require(asset.type().name() == ASSET_TYPE, f"Wrong type {asset.type().name()}")
    require(asset.type().maxNumInputs() == 3, "StreetBuilding must retain three inputs")
    definition = asset.type().definition()
    require(definition and REVISION in (definition.comment() or ""), "V9 marker is missing")
    group = asset.parmTemplateGroup()
    for name, expected in contract["public_defaults"].items():
        parameter = asset.parm(name)
        require(parameter is not None, f"Missing public parameter {name}")
        actual = parameter.eval()
        require(abs(float(actual) - expected) <= 1e-6 if isinstance(expected, float)
                else actual == expected, f"Default mismatch {name}: {actual!r} != {expected!r}")
    for name, expected in contract["menus"].items():
        template = group.find(name)
        require(template is not None and list(template.menuItems()) == expected,
                f"Menu mismatch for {name}")
    require(isinstance(group.find("unity_instance_catalog"), hou.StringParmTemplate),
            "Catalog transport parameter is missing")
    require(isinstance(group.find("unity_generation_rules"), hou.StringParmTemplate),
            "Generation-rule transport parameter is missing")
    require(isinstance(group.find("unity_bridge_revision"), hou.StringParmTemplate),
            "Unity bridge HAPI end marker is missing")
    require(not group.find("style_id").isHidden()
            and not group.find("unity_instance_catalog").isHidden()
            and not group.find("unity_generation_rules").isHidden()
            and not group.find("unity_bridge_revision").isHidden(),
            "Unity bridge must remain HAPI-visible; the project Authoring inspector owns artist visibility")


def assert_network(asset: hou.Node, contract: dict[str, Any]) -> None:
    core = asset.node(contract["core_node"])
    require(core is not None, "StreetBuildingCore is missing")
    for name, expected in contract["required_nodes"].items():
        target = core.node(name)
        require(target is not None and target.type().name() == expected,
                f"Required node/type mismatch: {name}/{expected}")
    require(core.node("PARSE_GENERATION_RULES").inputs()[:2] == (
        core.node("RESOLVE_FRONTAGES"), core.node("PARSE_UNITY_INSTANCE_CATALOG")),
        "Generation-rule parser wiring failed")
    require(core.node("RESOLVE_MASSING").input(0) == core.node("PARSE_GENERATION_RULES"),
            "Massing rule wiring failed")
    require(core.node("BUILD_FACADE_CELLS").inputs()[:2] == (
        core.node("PARSE_GENERATION_RULES"), core.node("PARSE_UNITY_INSTANCE_CATALOG")),
        "Facade-cell wiring failed")
    require(core.node("ALLOCATE_FACADE_CAPACITY").input(0) == core.node("BUILD_FACADE_CELLS"),
            "Facade allocator wiring failed")
    require(core.node("SELECT_FACADE_MODULES").inputs()[:2] == (
        core.node("ALLOCATE_FACADE_CAPACITY"), core.node("PARSE_UNITY_INSTANCE_CATALOG")),
        "Facade selector wiring failed")
    require(core.node("DIRECT_UNITY_INSTANCE_FACADE").input(0)
            == core.node("SELECT_FACADE_MODULES"), "Front semantic-consumer wiring failed")
    require(core.node("BUILD_DIRECT_SIDE_REAR_INSTANCES").input(0)
            == core.node("SELECT_FACADE_MODULES"), "Side/rear semantic-consumer wiring failed")
    require(core.node("MERGE_DIRECT_BUILDING_INSTANCES").inputs()[:4] == (
        core.node("DIRECT_UNITY_INSTANCE_FACADE"),
        core.node("BUILD_DIRECT_SIDE_REAR_INSTANCES"),
        core.node("BUILD_DIRECT_ROOF_INSTANCES"),
        core.node("BUILD_DIRECT_ROOF_EDGE_INSTANCES")), "Full-envelope merge wiring failed")
    require(core.node("VALIDATE_DIRECT_BUILDING_INSTANCES").input(0)
            == core.node("MERGE_DIRECT_BUILDING_INSTANCES"), "Validator wiring failed")
    require(core.node("LOD0_MODULE_SOURCE_SWITCH").input(1)
            == core.node("VALIDATE_DIRECT_BUILDING_INSTANCES"), "V6 shell switch wiring failed")
    require(core.node("DETAIL_INSTANCE_POINTS").input(0)
            == core.node("PARSE_UNITY_INSTANCE_CATALOG"), "Detail parser wiring failed")
    require(core.node("DETAIL_INSTANCE_POINTS").input(1)
            == core.node("SELECT_ATTACHMENT_MODULES"), "Attachment-rule wiring failed")
    require(core.node("VALIDATE_DIRECT_DETAIL_INSTANCES").input(0)
            == core.node("DETAIL_INSTANCE_POINTS"), "Detail validator wiring failed")
    require(core.node("DETAIL_MODULE_SOURCE_SWITCH").input(1)
            == core.node("VALIDATE_DIRECT_DETAIL_INSTANCES"), "Detail switch wiring failed")
    require(core.node("OUT_DETAIL_INSTANCES").input(0)
            == core.node("DETAIL_MODULE_SOURCE_SWITCH"), "Detail output wiring failed")
    empty = core.node("EMPTY_GEOMETRY")
    for name in ("OUT_BUILDING_LOD1", "OUT_BUILDING_LOD2", "OUT_BUILDING_COLLISION"):
        require(node(asset, name).input(0) == empty, f"{name} must remain empty")
    require(node(asset, "OUT_BUILDING_METADATA").input(0) == core.node("BUILD_METADATA"),
            "Metadata output must expose rule diagnostics")


def assert_internal(asset: hou.Node) -> dict[str, int]:
    asset.parm("module_source").set(0)
    value = geometry(asset)
    require(value.intrinsicValue("primitivecount") > 0, "Internal Proxy no longer emits geometry")
    require(all(math.isfinite(float(c)) for point in value.points() for c in point.position()),
            "Internal Proxy contains NaN/Inf")
    details = geometry(asset, "OUT_DETAIL_INSTANCES")
    require(not details.points() and not details.prims(),
            "Internal Proxy must not emit direct detail instances")
    return {"points": len(value.points()), "primitives": len(value.prims())}


def assert_v1(asset: hou.Node, contract: dict[str, Any]) -> dict[str, Any]:
    configure(asset, V1, rear=0, side=1, roof=0, rhythm=0)
    value = geometry(asset)
    require(len(value.prims()) == 0 and len(value.points()) > 0,
            "V1 compatibility output is empty")
    roles = [point.stringAttribValue("module_role") for point in value.points()]
    require({"Entrance", "GroundShop", "Cornice", "MiddleWindow", "FacadeColumn"}.issubset(roles),
            "V1 compatibility roles are incomplete")
    require(sum(point.intAttribValue("is_building_entrance") for point in value.points()) == 1,
            "V1 must retain one logical entrance")
    require({point.intAttribValue("face_index") for point in value.points()} == {0},
            "V1 compatibility must remain front-only")
    required = set(contract["required_attributes"])
    actual = {attribute.name() for attribute in value.pointAttribs()}
    require(not required - actual, f"V1 missing attributes: {sorted(required - actual)}")
    paths = [point.stringAttribValue("unity_instance") for point in value.points()]
    require(all(path.startswith(SOURCE_PREFIX) for path in paths), "V1 source paths changed")
    first = signature(value)
    require(signature(geometry(asset)) == first, "V1 same-input output is not deterministic")
    details = geometry(asset, "OUT_DETAIL_INSTANCES")
    require(not details.points(), "V1 compatibility payload must not emit V6 details")
    return {"points": len(value.points()), "unique_assets": len(set(paths)), "sha256": first}


def assert_v2(asset: hou.Node) -> dict[str, Any]:
    configure(asset, V2)
    value = geometry(asset)
    count = len(value.points())
    require(len(value.prims()) == 0 and count > 0, "V2 shell output is empty")
    faces = {point.intAttribValue("face_index") for point in value.points()}
    require(faces == {0, 1, 2, 3, 4}, f"V2 full envelope missing faces: {faces}")
    require(sum(point.intAttribValue("is_building_entrance") for point in value.points()) == 1,
            "V2 must contain exactly one logical entrance")
    require(all(point.intAttribValue("face_index") == 0 for point in value.points()
                if point.intAttribValue("is_building_entrance")), "Entrance escaped front face")
    span_seed = 29 if any(point.intAttribValue("module_span") == 2 for point in value.points()) else None
    if span_seed is None:
        for candidate_seed in range(1, 65):
            configure(asset, V2, seed=candidate_seed)
            if any(point.intAttribValue("module_span") == 2
                   for point in geometry(asset).points()):
                span_seed = candidate_seed
                break
    require(span_seed is not None, "V2 two-cell solver was not reachable across deterministic seeds")
    configure(asset, V2)
    value = geometry(asset)
    require(all(tuple(round(float(c), 5) for c in point.attribValue("scale")) == (1.0, 1.0, 1.0)
                for point in value.points()), "V2 emitted non-unit scale")
    require(all(abs(math.sqrt(sum(float(c) ** 2 for c in point.attribValue("orient"))) - 1) < .001
                for point in value.points()), "V2 emitted non-unit orientation")
    roles = [point.stringAttribValue("module_role") for point in value.points()]
    require(roles.count("RoofSurface") == 30, "12x10 roof must contain 30 2x2 tiles")
    require(roles.count("Parapet") == 14 and roles.count("ParapetCorner") == 4,
            "12x10 parapet must contain 14 straight modules and four corners")
    roof_points = [point for point in value.points()
                   if point.stringAttribValue("module_role") == "RoofSurface"]
    require({round(point.position()[0], 3) for point in roof_points}
            == {-5.0, -3.0, -1.0, 1.0, 3.0, 5.0},
            "Roof X centers do not cover the full 12m footprint")
    require({round(point.position()[2], 3) for point in roof_points}
            == {-1.0, -3.0, -5.0, -7.0, -9.0},
            "Roof Z centers do not cover the full 10m footprint")
    roof_y = 13.0
    height_by_variant = {}
    for row in V2.splitlines():
        fields = row.split("|")
        if len(fields) == 14 and fields[0] == "M":
            height_by_variant[(fields[1], fields[2])] = float(fields[12])
    for point in value.points():
        role = point.stringAttribValue("module_role")
        if role in ("RoofSurface", "Parapet", "ParapetCorner"):
            continue
        height = height_by_variant[(role, point.stringAttribValue("module_variant"))]
        require(point.position()[1] + height <= roof_y + .01,
                f"{role} exceeds roof plane at {point.position()}")
    first = signature(value)
    require(signature(geometry(asset)) == first, "V2 weighted selection is not deterministic")
    configure(asset, V2, seed=47)
    second = signature(geometry(asset))
    require(second != first, "Different seeds did not change V2 variant distribution")
    configure(asset, V2, rear=0, side=1, roof=0)
    disabled = geometry(asset)
    require({point.intAttribValue("face_index") for point in disabled.points()} == {0},
            "Side/rear/roof mode switches did not disable their faces")
    for output in ("OUT_BUILDING_LOD1", "OUT_BUILDING_LOD2", "OUT_BUILDING_COLLISION"):
        other = geometry(asset, output)
        require(not other.points() and not other.prims(), f"{output} is not empty")
    metadata = geometry(asset, "OUT_BUILDING_METADATA")
    require(metadata.findGlobalAttrib("streetbuilding_rule_report") is not None
            and metadata.findGlobalAttrib("streetbuilding_rule_source") is not None,
            "Metadata output is missing rule diagnostics")
    configure(asset, V2)
    with_parapet = len(geometry(asset).points())
    asset.parm("parapet_height").set(0)
    require(len(geometry(asset).points()) == with_parapet - 18,
            "parapet_height=0 must remove only the 18 roof-edge modules")
    return {"points": count, "faces": 5, "roof_tiles": 30,
            "parapet_straights": 14, "parapet_corners": 4,
            "unique_assets": len({point.stringAttribValue('unity_instance') for point in value.points()}),
            "sha256": first, "different_seed_sha256": second}


def assert_details(asset: hou.Node, contract: dict[str, Any]) -> dict[str, Any]:
    configure(asset, V2, density=1)
    for kind in range(5):
        asset.parm(f"attachment_{kind}_density").set(1)
    shell = geometry(asset)
    shell_sha = signature(shell)
    value = geometry(asset, "OUT_DETAIL_INSTANCES")
    count = len(value.points())
    budget = int(contract["budgets"]["detail_instances_per_building"])
    require(0 < count <= budget, f"Detail point budget failed: {count}/{budget}")
    require(not value.prims(), "Detail output must contain instance points only")

    required = set(contract["required_attributes"])
    actual = {attribute.name() for attribute in value.pointAttribs()}
    require(not required - actual, f"Details missing attributes: {sorted(required - actual)}")
    roles = [point.stringAttribValue("module_role") for point in value.points()]
    expected_wall_roles = {"Awning", "Sign", "FireEscape", "ACUnit"}
    require(expected_wall_roles.issubset(set(roles)),
            f"Wall detail role coverage failed: {sorted(set(roles))}")
    require(roles.count("FireEscape") <= 1, "A building emitted multiple fire escapes")
    require(all(point.stringAttribValue("unity_instance").startswith((SOURCE_PREFIX, DETAIL_PREFIX))
                for point in value.points()), "Detail output contains an unapproved asset path")
    require(all(tuple(round(float(c), 5) for c in point.attribValue("scale")) == (1.0, 1.0, 1.0)
                for point in value.points()), "Detail output emitted non-unit scale")
    require(all(abs(math.sqrt(sum(float(c) ** 2 for c in point.attribValue("orient"))) - 1) < .001
                for point in value.points()), "Detail output emitted non-unit orientation")
    require(all(point.stringAttribValue("pcg_kind") == "streetbuilding_detail_instance"
                for point in value.points()), "Detail pcg_kind contract changed")

    width_cells, depth_cells = 6, 5
    entrance_cell = width_cells // 2
    for point in value.points():
        role = point.stringAttribValue("module_role")
        face = point.intAttribValue("face_index")
        floor = point.intAttribValue("floor_index")
        cell = point.intAttribValue("cell_index")
        if role in ("Awning", "Sign"):
            require(face in (0, 2) and floor == 0
                    and (face != 0 or cell != entrance_cell),
                    f"{role} overlaps the entrance or escaped a ground frontage")
        elif role == "FireEscape":
            require(face == 3 and floor == 1,
                    "FireEscape must attach to the rear and start above ground")
        elif role == "ACUnit":
            require(face in (1, 2, 3) and floor >= 1,
                    "ACUnit must attach to an upper side/rear surface")
            assert_ac_support_plane(point, 12, 10)
        elif role == "RoofProp":
            x_cell = cell % width_cells
            z_cell = cell // width_cells
            require(face == 4 and 1 <= x_cell <= width_cells - 2
                    and 1 <= z_cell <= depth_cells - 2,
                    "RoofProp escaped the one-cell roof safety margin")
            require(point.stringAttribValue("module_variant") != "ac_unit",
                    "RoofProp must not reuse the wall AC unit")
            require(abs(point.position()[1] - 13.0) <= .01,
                    "RoofProp pivot must sit directly on roofY")

    detail_sha = signature(value)
    require(signature(geometry(asset, "OUT_DETAIL_INSTANCES")) == detail_sha,
            "Same-seed detail output is not deterministic")
    seen_roof_variants = set()
    for seed in range(1, 65):
        configure(asset, V2, seed=seed, density=1)
        for kind in range(5):
            asset.parm(f"attachment_{kind}_density").set(1)
        for point in geometry(asset, "OUT_DETAIL_INSTANCES").points():
            if point.stringAttribValue("module_role") == "RoofProp":
                variant = point.stringAttribValue("module_variant")
                require(variant != "ac_unit" and abs(point.position()[1] - 13.0) <= .01,
                        f"Invalid roof detail {variant}")
                seen_roof_variants.add(variant)
    require(len(seen_roof_variants) >= 2,
            f"Roof detail seed coverage failed: {sorted(seen_roof_variants)}")

    configure(asset, V2, seed=47, density=1)
    for kind in range(5):
        asset.parm(f"attachment_{kind}_density").set(1)
    different_seed_sha = signature(geometry(asset, "OUT_DETAIL_INSTANCES"))
    require(different_seed_sha != detail_sha, "Different seed did not change any detail")

    configure(asset, V2, density=1, attachments=0)
    require(not geometry(asset, "OUT_DETAIL_INSTANCES").points(),
            "generate_attachments=false did not empty Detail output")
    require(signature(geometry(asset)) == shell_sha,
            "generate_attachments=false changed the LOD0 shell")
    configure(asset, V2, density=0)
    require(not geometry(asset, "OUT_DETAIL_INSTANCES").points(),
            "detail_density=0 did not empty Detail output")
    require(signature(geometry(asset)) == shell_sha, "detail_density=0 changed the LOD0 shell")
    configure(asset, V2, density=1, module_source=0)
    require(not geometry(asset, "OUT_DETAIL_INSTANCES").points(),
            "Internal module source emitted direct detail instances")

    return {"points": count, "roles": sorted(set(roles)), "budget": budget,
            "roof_prop_variants": sorted(seen_roof_variants),
            "sha256": detail_sha, "different_seed_sha256": different_seed_sha,
            "toggle_isolated_from_lod0": True}


def assert_v3_l_shape(asset: hou.Node) -> dict[str, Any]:
    results: dict[str, Any] = {}
    for side, label in ((0, "rear_left"), (1, "rear_right")):
        configure(asset, V3, density=1, shape=1, notch_width=4, notch_depth=4,
                  notch_side=side)
        for kind in range(5):
            asset.parm(f"attachment_{kind}_density").set(1)
        value = geometry(asset)
        roles = [point.stringAttribValue("module_role") for point in value.points()]
        require(len(value.points()) > 0, f"V3 {label} L output is empty")
        require(roles.count("RoofSurface") == 26,
                f"V3 {label} L must remove exactly four roof tiles")
        require(roles.count("Parapet") == 10
                and roles.count("ParapetCorner") == 5
                and roles.count("ParapetConcaveCorner") == 1,
                f"V3 {label} L parapet topology is incomplete")
        corner_points = [point for point in value.points()
                         if point.stringAttribValue("module_role") in
                         ("ParapetCorner", "ParapetConcaveCorner")]
        by_cell = {point.intAttribValue("cell_index"): point for point in corner_points}
        require(set(by_cell) == set(range(6)),
                f"V3 {label} corner serials changed: {sorted(by_cell)}")
        expected_roles = ["ParapetCorner"] * 6
        expected_roles[4 if side == 0 else 3] = "ParapetConcaveCorner"
        expected_yaws = ([0, -90, -180, 90, -180, 90]
                         if side == 0 else [0, -90, -180, -90, -180, 90])
        for cell in range(6):
            point = by_cell[cell]
            require(point.stringAttribValue("module_role") == expected_roles[cell],
                    f"V3 {label} corner {cell} has the wrong convex/concave role")
            require(quaternion_matches(point.attribValue("orient"), expected_yaws[cell]),
                    f"V3 {label} corner {cell} has the wrong orientation")
        convex_paths = {point.stringAttribValue("unity_instance") for point in corner_points
                        if point.stringAttribValue("module_role") == "ParapetCorner"}
        concave_paths = {point.stringAttribValue("unity_instance") for point in corner_points
                         if point.stringAttribValue("module_role") == "ParapetConcaveCorner"}
        require(not convex_paths.intersection(concave_paths),
                f"V3 {label} convex and concave corners share an asset")
        require(all(point.stringAttribValue("module_family") == "validation_family"
                    for point in value.points()),
                f"V3 {label} module_family metadata is missing")
        for point in value.points():
            if point.stringAttribValue("module_role") != "RoofSurface":
                continue
            unity_x = -float(point.position()[0])
            z = float(point.position()[2])
            in_notch = z < -6.0 and (unity_x < -2.0 if side == 0 else unity_x > 2.0)
            require(not in_notch, f"V3 {label} roof tile entered the notch")
        first = signature(value)
        require(signature(geometry(asset)) == first,
                f"V3 {label} same-seed selection is not deterministic")
        details_value = geometry(asset, "OUT_DETAIL_INSTANCES")
        require(all(point.stringAttribValue("module_family") == "validation_family"
                    for point in details_value.points()),
                f"V3 {label} detail family metadata is missing")
        ac_points = [point for point in details_value.points()
                     if point.stringAttribValue("module_role") == "ACUnit"]
        require(ac_points, f"V3 {label} did not exercise AC placement")
        for point in ac_points:
            assert_ac_support_plane(point, 12, 10)
            face = point.intAttribValue("face_index")
            cell = point.intAttribValue("cell_index")
            unity_x = -float(point.position()[0])
            if side == 0 and face == 1:
                require(cell >= 2, "V3 rear-left AC entered removed left-side cells")
            if side == 1 and face == 2:
                require(cell < 3, "V3 rear-right AC entered removed right-side cells")
            if face == 3:
                in_notch = unity_x < -2.0 if side == 0 else unity_x > 2.0
                require(not in_notch, f"V3 {label} rear AC entered the notch")
        results[label] = {"points": len(value.points()), "roof_tiles": 26,
                          "parapet_straights": 10, "convex_corners": 5,
                          "concave_corners": 1, "ac_units": len(ac_points),
                          "corner_assets_distinct": True, "sha256": first}

    configure(asset, V3, shape=1, notch_width=10, notch_depth=4)
    rejected = False
    try:
        target = node(asset, "OUT_BUILDING_LOD0")
        target.cook(force=True)
        rejected = bool(target.errors())
    except hou.OperationFailed:
        rejected = True
    require(rejected, "V3 accepted an L notch that leaves only one module cell")
    results["invalid_notch"] = "rejected"
    return results


def semantic_counts(value: hou.Geometry, target: int, floor_one_based: int) -> dict[str, int]:
    result: dict[str, int] = {}
    for point in value.points():
        if (point.intAttribValue("facade_target") != target
                or point.intAttribValue("floor_1based") != floor_one_based):
            continue
        role = point.stringAttribValue("semantic_role")
        result[role] = result.get(role, 0) + 1
    return result


def generation_global(seed: int, mode: int = 2, corner: int = 1) -> str:
    return (f"SBR1\nG|12|10|0|4|4|0|4|{corner}|3|{mode}|2|.65|2|2|1|.6|1|1|1|{seed}")


def make_external_input(name: str, points: list[tuple[float, float, float]], *,
                        closed: bool, payload: str = "") -> hou.Node:
    container = hou.node("/obj").createNode("geo", name)
    for child in container.children():
        child.destroy()
    source = container.createNode("python", "BUILD_CONTRACT_GEOMETRY")
    source.parm("python").set(
        "geo=hou.pwd().geometry()\n"
        f"coords={points!r}\n"
        "pts=[geo.createPoint() for _ in coords]\n"
        "for p,c in zip(pts,coords): p.setPosition(c)\n"
        "poly=geo.createPolygon()\n"
        "for p in pts: poly.addVertex(p)\n"
        f"poly.setIsClosed({closed!r})\n"
        "bid=geo.addAttrib(hou.attribType.Prim,'building_id',0)\n"
        "poly.setAttribValue(bid,77)\n"
        + ("rule=geo.addAttrib(hou.attribType.Prim,'streetbuilding_rule_payload','')\n"
           f"poly.setAttribValue(rule,{payload!r})\n" if payload else ""))
    source.setDisplayFlag(True); source.setRenderFlag(True)
    return container


def assert_v9_rules(asset: hou.Node, contract: dict[str, Any]) -> dict[str, Any]:
    configure(asset, V4, density=1)
    asset.parm("corner_building").set(1)
    for kind in range(5):
        asset.parm(f"attachment_{kind}_density").set(1)

    parser = geometry(asset, "PARSE_UNITY_INSTANCE_CATALOG")
    require(int(parser.attribValue("catalog_schema")) == 4,
            "SBV4 payload did not resolve as schema 4")
    require(str(parser.attribValue("module_family")) == "test_style",
            "SBV4 StyleId was not preserved")

    manual = generation_global(29) + "\nO|0|1|1|2|3|1|1|1|1|2|2|0|0|2|2"
    asset.parm("unity_generation_rules").set(manual)
    allocated = geometry(asset, "ALLOCATE_FACADE_CAPACITY")
    counts = semantic_counts(allocated, 0, 1)
    require(counts == {"entrance": 1, "shop_door": 1, "shopfront": 2, "blank": 2},
            f"Manual exact allocation failed: {counts}")
    selected = geometry(asset, "SELECT_FACADE_MODULES")
    require(all(point.intAttribValue("catalog_schema") == 4 for point in selected.points()),
            "SBV4 schema metadata was lost during module selection")
    require({point.intAttribValue("facade_target") for point in selected.points()} >= {0, 1, 2, 3},
            "Corner building did not expose all semantic facade targets")

    overflow = generation_global(29) + "\nO|0|1|1|2|3|2|2|2|2|4|4|0|0|3|3"
    asset.parm("unity_generation_rules").set(overflow)
    compressed = geometry(asset, "ALLOCATE_FACADE_CAPACITY")
    report = str(compressed.attribValue("streetbuilding_rule_report"))
    require(int(compressed.attribValue("streetbuilding_rule_compressed")) == 1
            and "functional_priority" in report,
            "Functional-priority compression report is missing")
    compressed_counts = semantic_counts(compressed, 0, 1)
    require(compressed_counts.get("entrance", 0) >= 1
            and compressed_counts.get("shop_door", 0) >= 1,
            "Overflow compression discarded required functional doors")
    metadata = geometry(asset, "OUT_BUILDING_METADATA")
    require(int(metadata.attribValue("streetbuilding_rule_compressed")) == 1
            and "functional_priority" in str(metadata.attribValue("streetbuilding_rule_report")),
            "Compression diagnostics did not reach Metadata output")

    floor_override = generation_global(29, mode=0) + "\nO|0|3|3|2|1|0|0|0|0|0|0|2|2|0|0"
    asset.parm("unity_generation_rules").set(floor_override)
    floor_value = geometry(asset, "ALLOCATE_FACADE_CAPACITY")
    require(semantic_counts(floor_value, 0, 3).get("window", 0) == 2,
            "Front third-floor sparse override did not resolve exactly two windows")

    random_payload = (generation_global(41, mode=1)
        + "\nO|0|1|4|1|0|0|1|0|1|1|4|1|5|0|3")
    asset.parm("unity_generation_rules").set(random_payload)
    random_a = signature(geometry(asset, "SELECT_FACADE_MODULES"))
    random_b = signature(geometry(asset, "SELECT_FACADE_MODULES"))
    require(random_a == random_b, "Random Range is not deterministic for the same seed")
    asset.parm("unity_generation_rules").set(random_payload.replace("|41", "|47", 1))
    random_c = signature(geometry(asset, "SELECT_FACADE_MODULES"))
    require(random_c != random_a, "Random Range did not react to a different seed")

    attachment_payload = manual + "\n" + "\n".join((
        "A|0|1|8|3|1|1", "A|1|1|8|3|1|1", "A|2|1|4|8|2|4",
        "A|3|1|16|12|2|4", "A|4|1|8|15|1|99"))
    asset.parm("unity_generation_rules").set(attachment_payload)
    details = geometry(asset, "OUT_DETAIL_INSTANCES")
    roles = {point.stringAttribValue("module_role") for point in details.points()}
    require({"Awning", "Sign", "FireEscape", "ACUnit", "RoofProp"}.issubset(roles),
            f"Independent attachment groups are incomplete: {sorted(roles)}")
    require(len(details.points()) <= contract["budgets"]["detail_instances_per_building"],
            "Attachment groups exceeded the 64-instance budget")

    ac_rear_third = manual + "\nA|3|1|16|8|3|3"
    asset.parm("unity_generation_rules").set(ac_rear_third)
    restricted = geometry(asset, "OUT_DETAIL_INSTANCES")
    ac_points = [point for point in restricted.points()
                 if point.stringAttribValue("module_role") == "ACUnit"]
    require(ac_points and all(point.intAttribValue("face_index") == 3
                              and point.intAttribValue("floor_index") == 2
                              for point in ac_points),
            "Attachment facade/floor override escaped Rear floor 3")

    parcel = frontage = None
    try:
        parcel_payload = "SBR1\nG|16|10|0|4|4|0|4|0|3|0|0|.65|2|2|1|.6|1|1|1|73"
        parcel = make_external_input("VERIFY_SBV9_PARCEL",
            [(-8, 0, 0), (8, 0, 0), (8, 0, -10), (-8, 0, -10)],
            closed=True, payload=parcel_payload)
        frontage = make_external_input("VERIFY_SBV9_FRONTAGE",
            [(-8, 0, 0), (8, 0, 0)], closed=False)
        asset.setInput(0, parcel); asset.setInput(1, frontage)
        asset.parm("site_source").set(1)
        asset.parm("unity_generation_rules").set(generation_global(29))
        resolved = geometry(asset, "PARSE_GENERATION_RULES")
        parcel_actual = {"width": float(resolved.attribValue("effective_width")),
                         "seed": int(resolved.attribValue("effective_seed")),
                         "source": str(resolved.attribValue("rule_source")),
                         "primitives": len(resolved.prims())}
        require(abs(parcel_actual["width"] - 16) <= 1e-6
                and parcel_actual["seed"] == 73
                and parcel_actual["source"] == "parcel",
                f"Parcel payload did not override Unity GenerationPreset rules: {parcel_actual}")
    finally:
        asset.setInput(0, None); asset.setInput(1, None)
        if parcel is not None: parcel.destroy()
        if frontage is not None: frontage.destroy()
        asset.parm("site_source").set(0)

    return {"sbv4_schema": 4, "manual_counts": counts,
            "compression_reported": True, "third_floor_windows": 2,
            "random_same_seed": random_a, "random_different_seed": random_c,
            "attachment_roles": sorted(roles), "parcel_priority": True}


def assert_dimension_contract() -> dict[str, Any]:
    result: dict[str, Any] = {}
    for width, depth in ((10.0, 8.0), (12.0, 10.0), (16.0, 12.0)):
        instance = hou.node("/obj").createNode(ASSET_TYPE, f"VERIFY_{int(width)}_{int(depth)}")
        configure(instance, V2, width=width, depth=depth)
        result[f"{width}x{depth}"] = len(geometry(instance).points())
        instance.destroy()
    for width in (7.0, 11.0, 15.0):
        instance = hou.node("/obj").createNode(ASSET_TYPE, f"REJECT_{int(width)}")
        configure(instance, V2, width=width)
        failed = False
        try:
            target = node(instance, "OUT_BUILDING_LOD0")
            target.cook(force=True)
            failed = bool(target.errors())
        except hou.OperationFailed:
            failed = True
        require(failed, f"Invalid width {width}m was accepted")
        result[str(width)] = "rejected"
        instance.destroy()
    return result


def validate(hda: Path, hip: Path, contract_path: Path) -> dict[str, Any]:
    require(hda.is_file() and hip.is_file(), "StreetBuilding HDA/HIP is missing")
    contract = json.loads(contract_path.read_text(encoding="utf-8"))
    require(contract["revision"] == REVISION and contract["contract_version"] == CONTRACT_VERSION,
            "Contract revision/version mismatch")
    expected = {"StreetBuilding.V5.CatalogV2Compatibility", "StreetBuilding.V5.WeightedDeterminism",
                "StreetBuilding.V5.FullEnvelopeFaces", "StreetBuilding.V5.SpanSolver",
                "StreetBuilding.V5.SurfaceOrientation", "StreetBuilding.V5.SideRearRoofModes",
                "StreetBuilding.V5.UnityThreeBuildingShowcase",
                "StreetBuilding.V6.DetailOutputIsolation",
                "StreetBuilding.V6.DetailToggleAndDensity",
                "StreetBuilding.V6.DetailDeterminism",
                "StreetBuilding.V6.DetailSurfacePlacement",
                "StreetBuilding.V6.DetailInstanceBudget",
                "StreetBuilding.V6.ProjectOwnedValidationPrefabs",
                "StreetBuilding.V6.UnityThreeBuildingDetails",
                "StreetBuilding.V6_1.RoofFootprintCoverage",
                "StreetBuilding.V6_1.ShellTopAlignment",
                "StreetBuilding.V6_1.ParapetContinuity",
                "StreetBuilding.V6_1.RoofDetailGrounding",
                "StreetBuilding.V6_1.RoofDetailSemantics",
                "StreetBuilding.V6_1.CatalogBounds",
                "StreetBuilding.V7.RectangleAndLShapeOnly",
                "StreetBuilding.V7.LShapeConcaveCorner",
                "StreetBuilding.V7.LShapeRoofAndParapetCoverage",
                "StreetBuilding.V7.CatalogV3FamilyCompatibility",
                "StreetBuilding.V7.DeterministicFamilySelection",
                "StreetBuilding.V8.CornerTopologyOrientation",
                "StreetBuilding.V8.DedicatedConcaveCornerAsset",
                "StreetBuilding.V8.ACWallSupportPlane",
                "StreetBuilding.V8.ACLShapeCellContainment",
                "StreetBuilding.V9.SBV4StylePayload",
                "StreetBuilding.V9.GenerationModes",
                "StreetBuilding.V9.FacadeFloorOverrides",
                "StreetBuilding.V9.FunctionPriorityCompression",
                "StreetBuilding.V9.ParcelFrontageRulePayload",
                "StreetBuilding.V9.AttachmentGroups",
                "StreetBuilding.V9.RuleDeterminism",
                "StreetBuilding.V9.UnityBridgeHapiVisible"}
    require(expected.issubset(contract["contract_ids"]), "V5-V9 cumulative IDs are missing")
    hou.hipFile.clear(suppress_save_prompt=True)
    hou.hipFile.load(str(hip), suppress_save_prompt=True, ignore_load_warnings=False)
    hou.hda.installFile(str(hda), change_oplibraries_file=False, force_use_assets=True)
    fresh = hou.node("/obj").createNode(ASSET_TYPE, "VERIFY_STREETBUILDING_V9_LOCKED")
    require(not fresh.isEditable(), "Fresh validation instance must remain locked")
    assert_interface(fresh, contract)
    assert_network(fresh, contract)
    return {"status": "PASS", "asset_type": fresh.type().name(), "instance": fresh.path(),
            "locked": not fresh.isEditable(), "internal_proxy": assert_internal(fresh),
            "v1_compatibility": assert_v1(fresh, contract), "v2_full_envelope": assert_v2(fresh),
            "v6_1_modular_details": assert_details(fresh, contract),
            "v7_l_shape_catalog_v3": assert_v3_l_shape(fresh),
            "v9_styleconfig_rules": assert_v9_rules(fresh, contract),
            "dimension_contract": assert_dimension_contract()}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    default_root = Path(__file__).resolve().parents[4]
    parser.add_argument("--project-root", type=Path, default=default_root)
    parser.add_argument("--hda", type=Path)
    parser.add_argument("--hip", type=Path)
    parser.add_argument("--contract", type=Path)
    args = parser.parse_args()
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
