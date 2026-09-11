"""Validate persisted StreetBuilding V12 from a fresh locked HDA instance."""

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
REVISION = "STREETBUILDING_V12_HDA_PANEL_GENERATION"
CONTRACT_VERSION = "StreetBuilding.HdaPanelGeneration.12.0"
SOURCE_PREFIX = "Assets/PCG/Art/Downtown City MegaKit[Standard]/Exports/FBX (Unity)/"
DETAIL_PREFIX = "Assets/PCG/Art/StreetBuilding/NA_Brick_MixedUse_01/Prefabs/ValidationDetails/"
OUTPUTS = ("OUT_BUILDING_LOD0", "OUT_BUILDING_LOD1", "OUT_BUILDING_LOD2",
           "OUT_DETAIL_INSTANCES", "OUT_BUILDING_COLLISION", "OUT_BUILDING_METADATA")

ROLE_NAMES = ("GroundShop", "GroundShopDoor", "GroundWall", "Entrance",
              "MiddleWindow", "MiddleBlank", "CornerConvex", "CornerConcave",
              "Cornice", "Parapet", "SideWall", "RearWall", "FacadeColumn",
              "FloorBand", "Awning", "Sign", "FireEscape", "ACUnit", "RoofProp",
              "RoofSurface", "ParapetCorner", "ParapetConcaveCorner")
ATTACHMENT_TOKENS = ("awning", "sign", "fire_escape", "wall_ac", "roof_props")


def prefab_filename(path: str) -> str:
    """Match Unity's Prefab.name: the asset filename without its final extension."""
    return Path(path.replace("\\", "/")).stem


def style_row(role: int, path: str, width: int = 1, height: float = 3,
              weight: float = 1, facades: int = 15, floors: int = 7) -> str:
    variant = prefab_filename(path)
    return (f"M|0|{role}|{variant}|{path}|{width}|1|2|{height}|{weight}|"
            f"{facades}|{floors}|2|{height}|.2|-1|0|-.1")


STYLE_CATALOG = "\n".join((
    "STYLE|2|4|3",
    style_row(3, SOURCE_PREFIX + "DoorFrame_Metal_Single.fbx", height=4),
    style_row(3, SOURCE_PREFIX + "DoorFrame_Trim.fbx", height=4, weight=.6),
    style_row(0, SOURCE_PREFIX + "Metal_FirstFloor_Window.fbx", height=4),
    style_row(0, SOURCE_PREFIX + "Trim_FirstFloor_Window_001.fbx", height=4),
    style_row(1, SOURCE_PREFIX + "Door_2.fbx", height=4),
    style_row(2, SOURCE_PREFIX + "Brick_Plain_4.fbx", height=4),
    style_row(4, SOURCE_PREFIX + "Brick_Window_Trim.fbx"),
    style_row(4, SOURCE_PREFIX + "Brick_Window_Trim_Single.fbx"),
    style_row(4, SOURCE_PREFIX + "Brick_Window_CurvedDouble.fbx",
              width=2, weight=.35),
    style_row(5, SOURCE_PREFIX + "Brick_Plain_3.fbx"),
    style_row(5, SOURCE_PREFIX + "Brick_Plain_3_noWear.fbx", weight=.5),
    style_row(6, SOURCE_PREFIX + "Brick_Plain_4.fbx", height=4),
    style_row(6, SOURCE_PREFIX + "Brick_Plain_3.fbx"),
    style_row(7, SOURCE_PREFIX + "Brick_Plain_4.fbx", height=4),
    style_row(7, SOURCE_PREFIX + "Brick_Plain_3.fbx"),
    style_row(8, SOURCE_PREFIX + "Cornice_Brick_Center.fbx", height=1),
    style_row(8, SOURCE_PREFIX + "Cornice_Metal_Center.fbx", height=1, weight=.3),
    style_row(10, SOURCE_PREFIX + "Brick_Plain_4.fbx", height=4),
    style_row(10, SOURCE_PREFIX + "Brick_Plain_3.fbx"),
    style_row(10, SOURCE_PREFIX + "Brick_Plain_3_noWear.fbx", weight=.5),
    style_row(11, SOURCE_PREFIX + "Brick_Plain_4.fbx", height=4),
    style_row(11, SOURCE_PREFIX + "Brick_Plain_3.fbx"),
    style_row(11, SOURCE_PREFIX + "Brick_Plain_3_noWear.fbx", weight=.5),
    style_row(12, SOURCE_PREFIX + "Trim_Column_Center.fbx", height=4),
    style_row(12, SOURCE_PREFIX + "Brick_Column_Small.fbx"),
    style_row(19, SOURCE_PREFIX + "Roof_2x2.fbx", height=2, floors=4),
    style_row(9, DETAIL_PREFIX + "PF_SB_NAB01_Parapet_Straight.prefab",
              height=.6, floors=4),
    style_row(20, DETAIL_PREFIX + "PF_SB_NAB01_Parapet_Corner.prefab",
              height=.6, floors=4),
    style_row(21,
              "Assets/PCG/Art/StreetBuilding/urban_brick_mixeduse_01/Prefabs/"
              "PF_SB_urban_brick_mixeduse_01_Parapet_ConcaveCorner.prefab",
              height=.6, floors=4),
    style_row(14, DETAIL_PREFIX + "PF_SB_NAB01_Awning_Validation.prefab",
              height=1),
    style_row(15, DETAIL_PREFIX + "PF_SB_NAB01_Sign_Validation.prefab",
              height=1),
    style_row(16,
              DETAIL_PREFIX + "PF_SB_NAB01_FireEscape_Validation.prefab", width=2, height=6),
    style_row(17, SOURCE_PREFIX + "Prop_ACUnit.fbx", height=1),
    style_row(18, DETAIL_PREFIX + "PF_SB_NAB01_Roof_WaterTank.prefab",
              height=2),
    style_row(18, DETAIL_PREFIX + "PF_SB_NAB01_Roof_Vent.prefab",
              height=2, weight=.7),
    style_row(18, DETAIL_PREFIX + "PF_SB_NAB01_Roof_MechanicalBox.prefab",
              height=2, weight=.5),
))


class ContractFailure(RuntimeError):
    pass


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ContractFailure(message)


def catalog_module_rows(catalog: str) -> list[list[str]]:
    """Return validated module rows from the versionless Unity style payload."""
    rows = []
    for row in catalog.splitlines():
        fields = row.split("|")
        if fields[0] != "M":
            continue
        require(len(fields) == 18, f"Malformed module catalog row: {row}")
        rows.append(fields)
    require(rows, "Style catalog does not contain module rows")
    return rows


def variants_for_role(catalog: str, role: str) -> set[str]:
    role_index = ROLE_NAMES.index(role)
    return {fields[3] for fields in catalog_module_rows(catalog)
            if int(fields[2]) == role_index}


def assert_prefab_filename_variant(asset: hou.Node) -> dict[str, Any]:
    """Require the payload and generated points to derive Variant from asset filenames."""
    catalog_rows = catalog_module_rows(STYLE_CATALOG)
    for fields in catalog_rows:
        expected = prefab_filename(fields[4])
        require(fields[3] == expected,
                f"Catalog variant {fields[3]!r} must equal asset filename {expected!r}")

    configure(asset, STYLE_CATALOG, density=1)
    for token in ATTACHMENT_TOKENS:
        asset.parm(f"{token}_density").set(1)

    checked = 0
    for output in ("OUT_BUILDING_LOD0", "OUT_DETAIL_INSTANCES"):
        for point in geometry(asset, output).points():
            path = point.stringAttribValue("unity_instance")
            variant = point.stringAttribValue("module_variant")
            expected = prefab_filename(path)
            require(path and variant == expected,
                    f"{output} variant {variant!r} must equal asset filename {expected!r}: {path}")
            checked += 1
    require(checked > 0, "Prefab filename variant contract emitted no instance points")
    return {"catalog_rows": len(catalog_rows), "instance_points": checked}


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
    values = {
        "module_source": module_source, "unity_style_catalog": catalog,
        "building_width": width,
        "building_depth": depth, "floor_height_ground": 4.0,
        "floor_height_typical": 3.0, "floor_count": floors, "parapet_height": .6,
        "facade_rhythm": rhythm, "attachment_global_density": density,
        "attachments_enabled": attachments, "rear_facade_mode": rear,
        "side_facade_mode": side, "roof_enabled": roof, "lod_outputs_enabled": 0,
        "variation_seed": seed, "massing_shape": shape, "l_notch_width": notch_width,
        "l_notch_depth": notch_depth, "l_notch_side": notch_side,
        "site_source": 0, "site_source_auto": 0, "corner_building": 0,
    }
    for name, value in values.items():
        asset.parm(name).set(value)


def assert_interface(asset: hou.Node, contract: dict[str, Any]) -> None:
    require(asset.type().name() == ASSET_TYPE, f"Wrong type {asset.type().name()}")
    require(asset.type().maxNumInputs() == 3, "StreetBuilding must retain three inputs")
    definition = asset.type().definition()
    require(definition and REVISION in (definition.comment() or ""), "V12 marker is missing")
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
    require(isinstance(group.find("unity_style_catalog"), hou.StringParmTemplate),
            "Catalog transport parameter is missing")
    require(isinstance(group.find("unity_bridge_end_marker"), hou.StringParmTemplate),
            "Unity bridge HAPI end marker is missing")
    require(group.find("unity_generation_rules") is None
            and group.find("style_id") is None
            and group.find("unity_bridge_revision") is None,
            "Removed generation/style bridge parameters are still public")
    require(group.find("sb_bridge") is not None and not group.find("sb_bridge").isHidden(),
            "Unity bridge folder must remain HAPI-visible")
    floor_template = group.find("floor_count")
    require(floor_template.maxValue() == 12 and floor_template.maxIsStrict(),
            "Floor Count must be strictly limited to 12")
    require("massing_shape == rectangle" in str(group.find("l_notch_width").conditionals()),
            "L-notch controls must be conditional")


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
            == core.node("FILTER_REAL_INSTANCES") and core.node("FILTER_REAL_INSTANCES").input(0)
            == core.node("MERGE_DIRECT_BUILDING_INSTANCES"), "Preview filter/validator wiring failed")
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


def assert_full_envelope(asset: hou.Node) -> dict[str, Any]:
    configure(asset, STYLE_CATALOG)
    value = geometry(asset)
    require(len(geometry(asset, "OUT_BUILDING_PREVIEW").prims()) == 0,
            "Complete style must not emit missing cells")
    count = len(value.points())
    require(len(value.prims()) == 0 and count > 0, "Versionless shell output is empty")
    faces = {point.intAttribValue("face_index") for point in value.points()}
    require(faces == {0, 1, 2, 3, 4}, f"Full envelope missing faces: {faces}")
    require(sum(point.intAttribValue("is_building_entrance") for point in value.points()) == 1,
            "Full envelope must contain exactly one logical entrance")
    require(all(point.intAttribValue("face_index") == 0 for point in value.points()
                if point.intAttribValue("is_building_entrance")), "Entrance escaped front face")
    span_seed = 29 if any(point.intAttribValue("module_span") == 2 for point in value.points()) else None
    if span_seed is None:
        for candidate_seed in range(1, 65):
            configure(asset, STYLE_CATALOG, seed=candidate_seed)
            if any(point.intAttribValue("module_span") == 2
                   for point in geometry(asset).points()):
                span_seed = candidate_seed
                break
    require(span_seed is not None, "Two-cell solver was not reachable across deterministic seeds")
    configure(asset, STYLE_CATALOG)
    value = geometry(asset)
    require(all(tuple(round(float(c), 5) for c in point.attribValue("scale")) == (1.0, 1.0, 1.0)
                for point in value.points()), "Versionless payload emitted non-unit scale")
    require(all(abs(math.sqrt(sum(float(c) ** 2 for c in point.attribValue("orient"))) - 1) < .001
                for point in value.points()), "Versionless payload emitted non-unit orientation")
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
    for row in STYLE_CATALOG.splitlines():
        fields = row.split("|")
        if len(fields) == 18 and fields[0] == "M":
            height_by_variant[(ROLE_NAMES[int(fields[2])], fields[3])] = float(fields[8])
    for point in value.points():
        role = point.stringAttribValue("module_role")
        if role in ("RoofSurface", "Parapet", "ParapetCorner"):
            continue
        height = height_by_variant[(role, point.stringAttribValue("module_variant"))]
        require(point.position()[1] + height <= roof_y + .01,
                f"{role} exceeds roof plane at {point.position()}")
    first = signature(value)
    # Preserve the exact legacy signature when side/rear windows are disabled.
    # The new mask-enabled behavior is covered independently by assert_upper_windows.
    legacy_rows = catalog_module_rows(STYLE_CATALOG)
    for row in legacy_rows:
        if int(row[2]) == 4:
            row[10] = '3'
    configure(asset, 'STYLE|2|4|3\n' + '\n'.join('|'.join(row) for row in legacy_rows))
    require(signature(geometry(asset)) == 'b84502d2b2ba0d13fea24f798ab0e82275790459afc788350adfe90b491b4fc2',
            'Legacy instance output differs from the captured production signature')
    configure(asset, STYLE_CATALOG)
    require(signature(geometry(asset)) == first, "Weighted selection is not deterministic")
    configure(asset, STYLE_CATALOG, seed=47)
    second = signature(geometry(asset))
    require(second != first, "Different seeds did not change variant distribution")
    configure(asset, STYLE_CATALOG, rear=0, side=1, roof=0)
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
    configure(asset, STYLE_CATALOG)
    with_parapet = len(geometry(asset).points())
    asset.parm("parapet_height").set(0)
    require(len(geometry(asset).points()) == with_parapet - 18,
            "parapet_height=0 must remove only the 18 roof-edge modules")
    return {"points": count, "faces": 5, "roof_tiles": 30,
            "parapet_straights": 14, "parapet_corners": 4,
            "unique_assets": len({point.stringAttribValue('unity_instance') for point in value.points()}),
            "sha256": first, "different_seed_sha256": second}


def assert_details(asset: hou.Node, contract: dict[str, Any]) -> dict[str, Any]:
    configure(asset, STYLE_CATALOG, density=1)
    for token in ATTACHMENT_TOKENS:
        asset.parm(f"{token}_density").set(1)
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
    wall_ac_variants = variants_for_role(STYLE_CATALOG, "ACUnit")

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
            require(point.stringAttribValue("module_variant") not in wall_ac_variants,
                    "RoofProp must not reuse a wall AC asset filename")
            require(abs(point.position()[1] - 13.0) <= .01,
                    "RoofProp pivot must sit directly on roofY")

    detail_sha = signature(value)
    require(signature(geometry(asset, "OUT_DETAIL_INSTANCES")) == detail_sha,
            "Same-seed detail output is not deterministic")
    seen_roof_variants = set()
    for seed in range(1, 65):
        configure(asset, STYLE_CATALOG, seed=seed, density=1)
        for token in ATTACHMENT_TOKENS:
            asset.parm(f"{token}_density").set(1)
        for point in geometry(asset, "OUT_DETAIL_INSTANCES").points():
            if point.stringAttribValue("module_role") == "RoofProp":
                variant = point.stringAttribValue("module_variant")
                require(variant not in wall_ac_variants and abs(point.position()[1] - 13.0) <= .01,
                        f"Invalid roof detail {variant}")
                seen_roof_variants.add(variant)
    require(len(seen_roof_variants) >= 2,
            f"Roof detail seed coverage failed: {sorted(seen_roof_variants)}")

    configure(asset, STYLE_CATALOG, seed=47, density=1)
    for token in ATTACHMENT_TOKENS:
        asset.parm(f"{token}_density").set(1)
    different_seed_sha = signature(geometry(asset, "OUT_DETAIL_INSTANCES"))
    require(different_seed_sha != detail_sha, "Different seed did not change any detail")

    configure(asset, STYLE_CATALOG, density=1, attachments=0)
    require(not geometry(asset, "OUT_DETAIL_INSTANCES").points(),
            "attachments_enabled=false did not empty Detail output")
    require(signature(geometry(asset)) == shell_sha,
            "attachments_enabled=false changed the LOD0 shell")
    configure(asset, STYLE_CATALOG, density=0)
    require(not geometry(asset, "OUT_DETAIL_INSTANCES").points(),
            "attachment_global_density=0 did not empty Detail output")
    require(signature(geometry(asset)) == shell_sha,
            "attachment_global_density=0 changed the LOD0 shell")
    configure(asset, STYLE_CATALOG, density=1, module_source=0)
    require(not geometry(asset, "OUT_DETAIL_INSTANCES").points(),
            "Internal module source emitted direct detail instances")

    return {"points": count, "roles": sorted(set(roles)), "budget": budget,
            "roof_prop_variants": sorted(seen_roof_variants),
            "sha256": detail_sha, "different_seed_sha256": different_seed_sha,
            "toggle_isolated_from_lod0": True}


def assert_l_shape(asset: hou.Node) -> dict[str, Any]:
    results: dict[str, Any] = {}
    for side, label in ((0, "rear_left"), (1, "rear_right")):
        configure(asset, STYLE_CATALOG, density=1, shape=1, notch_width=4, notch_depth=4,
                  notch_side=side)
        for token in ATTACHMENT_TOKENS:
            asset.parm(f"{token}_density").set(1)
        value = geometry(asset)
        roles = [point.stringAttribValue("module_role") for point in value.points()]
        require(len(value.points()) > 0, f"{label} L output is empty")
        require(roles.count("RoofSurface") == 26,
                f"{label} L must remove exactly four roof tiles")
        require(roles.count("Parapet") == 10
                and roles.count("ParapetCorner") == 5
                and roles.count("ParapetConcaveCorner") == 1,
                f"{label} L parapet topology is incomplete")
        corner_points = [point for point in value.points()
                         if point.stringAttribValue("module_role") in
                         ("ParapetCorner", "ParapetConcaveCorner")]
        by_cell = {point.intAttribValue("cell_index"): point for point in corner_points}
        require(set(by_cell) == set(range(6)),
                f"{label} corner serials changed: {sorted(by_cell)}")
        expected_roles = ["ParapetCorner"] * 6
        expected_roles[4 if side == 0 else 3] = "ParapetConcaveCorner"
        expected_yaws = ([0, -90, -180, 90, -180, 90]
                         if side == 0 else [0, -90, -180, -90, -180, 90])
        for cell in range(6):
            point = by_cell[cell]
            require(point.stringAttribValue("module_role") == expected_roles[cell],
                    f"{label} corner {cell} has the wrong convex/concave role")
            require(quaternion_matches(point.attribValue("orient"), expected_yaws[cell]),
                    f"{label} corner {cell} has the wrong orientation")
        convex_paths = {point.stringAttribValue("unity_instance") for point in corner_points
                        if point.stringAttribValue("module_role") == "ParapetCorner"}
        concave_paths = {point.stringAttribValue("unity_instance") for point in corner_points
                         if point.stringAttribValue("module_role") == "ParapetConcaveCorner"}
        require(not convex_paths.intersection(concave_paths),
                f"{label} convex and concave corners share an asset")
        for point in value.points():
            if point.stringAttribValue("module_role") != "RoofSurface":
                continue
            unity_x = -float(point.position()[0])
            z = float(point.position()[2])
            in_notch = z < -6.0 and (unity_x < -2.0 if side == 0 else unity_x > 2.0)
            require(not in_notch, f"{label} roof tile entered the notch")
        first = signature(value)
        require(signature(geometry(asset)) == first,
                f"{label} same-seed selection is not deterministic")
        details_value = geometry(asset, "OUT_DETAIL_INSTANCES")
        ac_points = [point for point in details_value.points()
                     if point.stringAttribValue("module_role") == "ACUnit"]
        require(ac_points, f"{label} did not exercise AC placement")
        for point in ac_points:
            assert_ac_support_plane(point, 12, 10)
            face = point.intAttribValue("face_index")
            cell = point.intAttribValue("cell_index")
            unity_x = -float(point.position()[0])
            if side == 0 and face == 1:
                require(cell >= 2, "Rear-left AC entered removed left-side cells")
            if side == 1 and face == 2:
                require(cell < 3, "Rear-right AC entered removed right-side cells")
            if face == 3:
                in_notch = unity_x < -2.0 if side == 0 else unity_x > 2.0
                require(not in_notch, f"{label} rear AC entered the notch")
        results[label] = {"points": len(value.points()), "roof_tiles": 26,
                          "parapet_straights": 10, "convex_corners": 5,
                          "concave_corners": 1, "ac_units": len(ac_points),
                          "corner_assets_distinct": True, "sha256": first}

    configure(asset, STYLE_CATALOG, shape=1, notch_width=10, notch_depth=4)
    rejected = False
    try:
        target = node(asset, "OUT_BUILDING_LOD0")
        target.cook(force=True)
        rejected = bool(target.errors())
    except hou.OperationFailed:
        rejected = True
    require(rejected, "L shape accepted a notch that leaves only one module cell")
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


def set_facade_override(asset: hou.Node, *, floor_from: int, floor_to: int,
                        mode: int, rhythm: int, entrance: tuple[int, int] = (0, 0),
                        shop_door: tuple[int, int] = (0, 0),
                        shopfront: tuple[int, int] = (0, 0),
                        window: tuple[int, int] = (0, 0),
                        blank: tuple[int, int] = (0, 0)) -> None:
    asset.parm("facade_overrides").set(1)
    values = {
        "facade_override_target1": 0,
        "facade_override_floor_start1": floor_from,
        "facade_override_floor_end1": floor_to,
        "facade_override_layout_mode1": mode,
        "facade_override_rhythm1": rhythm,
        "facade_override_entrance_min1": entrance[0],
        "facade_override_entrance_max1": entrance[1],
        "facade_override_shop_door_min1": shop_door[0],
        "facade_override_shop_door_max1": shop_door[1],
        "facade_override_shopfront_min1": shopfront[0],
        "facade_override_shopfront_max1": shopfront[1],
        "facade_override_window_min1": window[0],
        "facade_override_window_max1": window[1],
        "facade_override_blank_min1": blank[0],
        "facade_override_blank_max1": blank[1],
    }
    for name, value in values.items():
        asset.parm(name).set(value)


def set_attachment_overrides(asset: hou.Node, rows: list[tuple[int, float, int, int, int, int]]) -> None:
    asset.parm("attachment_overrides").set(len(rows))
    for index, (kind, density, maximum, mask, floor_from, floor_to) in enumerate(rows, 1):
        values = {
            f"attachment_override_kind{index}": kind,
            f"attachment_override_density{index}": density,
            f"attachment_override_max_count{index}": maximum,
            f"attachment_override_front{index}": 1 if mask & 1 else 0,
            f"attachment_override_secondary_front{index}": 1 if mask & 2 else 0,
            f"attachment_override_side{index}": 1 if mask & 4 else 0,
            f"attachment_override_rear{index}": 1 if mask & 8 else 0,
            f"attachment_override_floor_start{index}": floor_from,
            f"attachment_override_floor_end{index}": floor_to,
        }
        for name, value in values.items():
            asset.parm(name).set(value)


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


def assert_generation_rules(asset: hou.Node, contract: dict[str, Any]) -> dict[str, Any]:
    configure(asset, STYLE_CATALOG, density=1)
    asset.parm("corner_building").set(1)
    for token in ("awning", "sign", "fire_escape", "wall_ac", "roof_props"):
        asset.parm(f"{token}_density").set(1)

    parser = geometry(asset, "PARSE_UNITY_INSTANCE_CATALOG")
    require(int(parser.attribValue("catalog_module_rows")) > 0,
            "Versionless payload did not emit module rows")
    require(parser.findGlobalAttrib("catalog_schema") is None
            and parser.findGlobalAttrib("module_family") is None,
            "Removed schema/family metadata was emitted")

    asset.parm("variation_seed").set(29)
    asset.parm("facade_layout_mode").set(2)
    for name, value in {
        "entrance_count_min": 1, "shop_door_count_min": 1,
        "shopfront_count_min": 2, "window_count_min": 0, "blank_count_min": 2,
    }.items(): asset.parm(name).set(value)
    allocated = geometry(asset, "ALLOCATE_FACADE_CAPACITY")
    counts = semantic_counts(allocated, 0, 1)
    require(counts == {"entrance": 1, "shop_door": 1, "shopfront": 2, "blank": 2},
            f"Manual exact allocation failed: {counts}")
    selected = geometry(asset, "SELECT_FACADE_MODULES")
    require(selected.findPointAttrib("catalog_schema") is None
            and selected.findPointAttrib("module_family") is None,
            "Removed schema/family metadata reached module selection")
    require({point.intAttribValue("facade_target") for point in selected.points()} >= {0, 1, 2, 3},
            "Corner building did not expose all semantic facade targets")

    for name, value in {
        "entrance_count_min": 2, "shop_door_count_min": 2,
        "shopfront_count_min": 4, "window_count_min": 0, "blank_count_min": 3,
    }.items(): asset.parm(name).set(value)
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

    asset.parm("facade_layout_mode").set(0)
    set_facade_override(asset, floor_from=3, floor_to=3, mode=2, rhythm=1,
                        window=(2, 2))
    floor_value = geometry(asset, "ALLOCATE_FACADE_CAPACITY")
    require(semantic_counts(floor_value, 0, 3).get("window", 0) == 2,
            "Front third-floor sparse override did not resolve exactly two windows")

    asset.parm("facade_overrides").set(0)
    asset.parm("facade_layout_mode").set(1)
    asset.parm("variation_seed").set(41)
    for name, value in {
        "entrance_count_min": 0, "entrance_count_max": 1,
        "shop_door_count_min": 0, "shop_door_count_max": 1,
        "shopfront_count_min": 1, "shopfront_count_max": 4,
        "window_count_min": 1, "window_count_max": 5,
        "blank_count_min": 0, "blank_count_max": 3,
    }.items(): asset.parm(name).set(value)
    random_a = signature(geometry(asset, "SELECT_FACADE_MODULES"))
    random_b = signature(geometry(asset, "SELECT_FACADE_MODULES"))
    require(random_a == random_b, "Random Range is not deterministic for the same seed")
    asset.parm("variation_seed").set(47)
    random_c = signature(geometry(asset, "SELECT_FACADE_MODULES"))
    require(random_c != random_a, "Random Range did not react to a different seed")

    set_attachment_overrides(asset, [
        (0, 1, 8, 3, 1, 1), (1, 1, 8, 3, 1, 1), (2, 1, 4, 8, 2, 4),
        (3, 1, 16, 12, 2, 4), (4, 1, 8, 15, 1, 13),
    ])
    details = geometry(asset, "OUT_DETAIL_INSTANCES")
    roles = {point.stringAttribValue("module_role") for point in details.points()}
    require({"Awning", "Sign", "FireEscape", "ACUnit", "RoofProp"}.issubset(roles),
            f"Independent attachment groups are incomplete: {sorted(roles)}")
    require(len(details.points()) <= contract["budgets"]["detail_instances_per_building"],
            "Attachment groups exceeded the 64-instance budget")

    set_attachment_overrides(asset, [(3, 1, 16, 8, 3, 3)])
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
        parcel = make_external_input("VERIFY_VERSIONLESS_PARCEL",
            [(-8, 0, 0), (8, 0, 0), (8, 0, -10), (-8, 0, -10)],
            closed=True, payload=parcel_payload)
        frontage = make_external_input("VERIFY_VERSIONLESS_FRONTAGE",
            [(-8, 0, 0), (8, 0, 0)], closed=False)
        asset.setInput(0, parcel); asset.setInput(1, frontage)
        asset.parm("variation_seed").set(29)
        asset.parm("site_source").set(0)
        internal = geometry(asset, "PARSE_GENERATION_RULES")
        require(int(internal.attribValue("effective_seed")) == 29
                and str(internal.attribValue("rule_source")) == "hda",
                "Internal mode incorrectly consumed streetbuilding_rule_payload")
        asset.parm("site_source").set(1)
        resolved = geometry(asset, "PARSE_GENERATION_RULES")
        parcel_actual = {"width": float(resolved.attribValue("effective_width")),
                         "seed": int(resolved.attribValue("effective_seed")),
                         "source": str(resolved.attribValue("rule_source")),
                         "primitives": len(resolved.prims())}
        require(abs(parcel_actual["width"] - 16) <= 1e-6
                and parcel_actual["seed"] == 73
                and parcel_actual["source"] == "parcel",
                f"External parcel payload did not override HDA defaults: {parcel_actual}")
    finally:
        asset.setInput(0, None); asset.setInput(1, None)
        if parcel is not None: parcel.destroy()
        if frontage is not None: frontage.destroy()
        asset.parm("site_source").set(0)

    return {"payload_header": "STYLE", "manual_counts": counts,
            "compression_reported": True, "third_floor_windows": 2,
            "random_same_seed": random_a, "random_different_seed": random_c,
            "attachment_roles": sorted(roles), "internal_ignores_parcel": True,
            "external_parcel_priority": True}


def assert_dimension_contract() -> dict[str, Any]:
    result: dict[str, Any] = {}
    for width, depth in ((10.0, 8.0), (12.0, 10.0), (16.0, 12.0)):
        instance = hou.node("/obj").createNode(ASSET_TYPE, f"VERIFY_{int(width)}_{int(depth)}")
        configure(instance, STYLE_CATALOG, width=width, depth=depth)
        result[f"{width}x{depth}"] = len(geometry(instance).points())
        instance.destroy()
    for width in (7.0, 11.0, 15.0):
        instance = hou.node("/obj").createNode(ASSET_TYPE, f"REJECT_{int(width)}")
        configure(instance, STYLE_CATALOG, width=width)
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


def assert_layer_rules(asset: hou.Node) -> dict[str, Any]:
    """Independent behavior contracts for style defaults and floor ownership."""
    import copy
    def defaults():
        result = dict(groundUse=0, layoutMode=0, rhythm=0, shopfrontRatio=.65,
                      entranceMin=1, entranceMax=1, shopDoorMin=0, shopDoorMax=1,
                      shopfrontMin=1, shopfrontMax=4, windowMin=2, windowMax=8,
                      blankMin=0, blankMax=4, trimEnabled=True, roofEnabled=True,
                      attachmentsEnabled=True, parapetHeight=.6, density=1)
        for key in ('awning', 'sign', 'fireEscape', 'wallAC', 'roofProps'):
            result[key] = dict(enabled=True, density=1, maxCount=4, facades=15)
        return result
    rules = dict(version=1, ground=defaults(), upper=defaults(), roof=defaults())
    lines = [STYLE_CATALOG.splitlines()[0]]
    for fields in catalog_module_rows(STYLE_CATALOG):
        role = int(fields[2])
        mask = 1 if role in (0, 1, 2, 3, 14, 15) else 2 if role in (4, 5, 16, 17) else 4 if role in (9, 18, 19, 20, 21) else 3
        for band in (1, 2, 4):
            if mask & band:
                row = fields.copy(); row[11] = str(band); lines.append('|'.join(row))
    catalog = '\n'.join(lines)
    def setup(payload=catalog, floors=4, seed=31):
        configure(asset, payload, density=1)
        asset.parm('floor_count').set(floors)
        asset.parm('variation_seed').set(seed)
        asset.parm('style_rule_source').set(1)
        for layer in ('ground', 'upper', 'roof'):
            asset.parm('style_override_' + layer).set(0)
        asset.parm('unity_style_rules').set(json.dumps(rules, sort_keys=True))
    def records():
        return [(p.stringAttribValue('module_role'), p.intAttribValue('floor_index'),
                 p.stringAttribValue('unity_instance'), tuple(p.position()),
                 tuple(p.attribValue('orient'))) for p in geometry(asset, 'OUT_DETAIL_INSTANCES').points()]
    def apply_rules():
        asset.parm('unity_style_rules').set(json.dumps(rules, sort_keys=True))
    cases=0
    for floors in (1, 2, 4, 12):
        for seed in (1, 31, 97):
            setup(floors=floors, seed=seed)
            points=records()
            require(len(points)<=64, 'Layer rules exceeded final instance budget')
            require(all(floor==0 for role,floor,*_ in points if role in ('Awning','Sign')), 'Ground attachments leaked')
            require(all(0<floor<floors for role,floor,*_ in points if role in ('FireEscape','ACUnit')), 'Upper attachments leaked')
            require(all(floor==floors for role,floor,*_ in points if role=='RoofProp'), 'Roof attachment band leaked')
            require(points==records(), 'Layer style determinism failed')
            geometry(asset, 'OUT_BUILDING_LOD0')
            cases+=1
    # Same Prefab can be referenced again in Upper, independent of Ground.
    upper_rows=[]
    for row in catalog_module_rows(catalog):
        if int(row[2]) in (14,15):
            row[11]='2'; upper_rows.append('|'.join(row))
    setup(catalog+'\n'+'\n'.join(upper_rows))
    points=records()
    require(any(role=='Awning' and floor>0 for role,floor,*_ in points), 'Explicit upper awning did not generate')
    require(any(role=='Sign' and floor>0 for role,floor,*_ in points), 'Explicit upper sign did not generate')
    unaffected=[p for p in points if p[1]>0]
    rules['ground']['density']=0; apply_rules()
    reduced=records()
    require(not any(p[1]==0 for p in reduced), 'Ground density zero ignored')
    require([p for p in reduced if p[1]>0]==unaffected, 'Changing Ground changed another layer')
    rules['upper']['attachmentsEnabled']=False; apply_rules()
    require(all(p[0]=='RoofProp' for p in records()), 'Upper off toggle ignored')
    rules['roof']['roofProps']['maxCount']=0; apply_rules()
    require(not records(), 'Roof maximum zero ignored')
    rules['ground']=defaults(); rules['upper']=defaults(); rules['roof']=defaults(); apply_rules()
    asset.parm('attachments_enabled').set(0)
    require(not records(), 'Global off must constrain style defaults')
    setup()
    rules['ground']['groundUse']=3; apply_rules()
    parsed=node(asset,'PARSE_GENERATION_RULES').geometry()
    require(parsed.intAttribValue('effective_ground_use')==3, 'Style ground use not consumed')
    asset.parm('ground_floor_use').set(1); asset.parm('style_override_ground').set(1)
    require(node(asset,'PARSE_GENERATION_RULES').geometry().intAttribValue('effective_ground_use')==1,
            'Explicit instance layer override did not win')
    setup()
    asset.parm('massing_shape').set(1)
    rules['roof']['roofEnabled']=False; apply_rules()
    require(not any(p.stringAttribValue('module_role') in ('RoofSurface','Parapet','ParapetCorner','ParapetConcaveCorner')
                    for p in geometry(asset,'OUT_BUILDING_LOD0').points()), 'Disabled L roof still emitted roof modules')
    require(not any(p[0]=='RoofProp' for p in records()), 'Disabled L roof still emitted props')
    rules['roof']['roofEnabled']=True; rules['roof']['parapetHeight']=0; apply_rules()
    require(not any(p.stringAttribValue('module_role').startswith('Parapet')
                    for p in geometry(asset,'OUT_BUILDING_LOD0').points()), 'L parapet zero still emitted edges')
    return {'status':'PASS','seed_floor_cases':cases,'upper_awning_sign':True,
            'independent_layers':True,'density_toggle_budget':True,'instance_override':True}


def assert_preview_normals_and_corners(asset: hou.Node) -> None:
    """Measure actual polygon normals and corner envelopes, independent of VEX text."""
    core = asset.node('StreetBuildingCore')
    preview = core.node('PREVIEW_MISSING_MODULES')
    preview.cook(force=True)
    require(not preview.errors() and not preview.warnings(), 'Preview cook diagnostics')
    slots = preview.inputs()[0].geometry().points()
    groups = {}
    for prim in preview.geometry().prims():
        groups.setdefault(prim.intAttribValue('preview_slot'), []).append(prim)
    for slot, faces in groups.items():
        point = slots[slot]
        role = point.stringAttribValue('module_role')
        corner = role in ('ParapetCorner', 'ParapetConcaveCorner')
        require(len(faces) == (60 if corner else 30), 'Missing corner must contain both wall arms')
        for start in range(0, len(faces), 30):
            arm = faces[start:start+30]
            positions = [v.point().position() for f in arm for v in f.vertices()]
            lo = hou.Vector3(tuple(min(p[i] for p in positions) for i in range(3)))
            hi = hou.Vector3(tuple(max(p[i] for p in positions) for i in range(3)))
            center = (lo + hi) * .5
            for face in arm:
                vertices = [v.point().position() for v in face.vertices()]
                face_center = sum(vertices, hou.Vector3()) / len(vertices)
                require(face.normal().dot(face_center-center) > 1e-5,
                        'Inward or degenerate preview normal: ' + role)
        if corner:
            inverse = hou.Quaternion(point.attribValue('orient')).inverse()
            positions = [inverse.rotate(v.point().position()-point.position())
                         for f in faces for v in f.vertices()]
            actual = [min(p[i] for p in positions) for i in (0,2)] + [max(p[i] for p in positions) for i in (0,2)]
            expected = [-2, -.08, .08, 2] if role == 'ParapetConcaveCorner' else [-2, -2, .08, .08]
            require(all(abs(a-b)<1e-4 for a,b in zip(actual,expected)),
                    'Parapet corner extends outside its two reserved cells: ' + str(actual))


def assert_partial_preview(asset: hou.Node) -> dict[str, Any]:
    """Empty/sparse catalogs are valid; generated placeholders never enter real instances."""
    configure(asset, "STYLE|2|4|3", attachments=0)
    asset.parm("style_rule_source").set(0)
    asset.parm("site_source_auto").set(1)
    core=asset.node("StreetBuildingCore")
    real=core.node("OUT_BUILDING_LOD0")
    preview=core.node("OUT_BUILDING_PREVIEW")
    real.cook(force=True); preview.cook(force=True)
    require(not real.errors() and not preview.errors(), "Empty catalog cook failed")
    require(len(real.geometry().points())==0, "Empty catalog emitted real instances")
    require(len(preview.geometry().prims())>0, "Empty catalog graybox is missing")
    metadata=geometry(asset,"OUT_BUILDING_METADATA")
    missing=metadata.intAttribValue("preview_missing_count")
    assert_preview_normals_and_corners(asset)
    corner_count = sum(p.intAttribValue('preview_missing') and p.stringAttribValue('module_role') in
                       ('ParapetCorner', 'ParapetConcaveCorner')
                       for p in core.node('PREVIEW_MISSING_MODULES').inputs()[0].geometry().points())
    require(missing>0 and len(preview.geometry().prims())==(missing+corner_count)*30,
            "Zero-instance diagnostics and merged cell faces disagree")
    summary=metadata.stringAttribValue("preview_missing_summary")
    require(sum(int(row.split('|')[2]) for row in summary.splitlines())==missing,
            "Grouped missing counts disagree")
    for attr in ("building_id","floor_index","face_index","cell_index","module_role","preview_slot"):
        require(preview.geometry().findPrimAttrib(attr) is not None, "Missing cell locator: "+attr)
    materials={p.stringAttribValue('unity_material') for p in preview.geometry().prims()}
    require(materials=={'Assets/PCG/Materials/SB_MissingCell.mat','Assets/PCG/Materials/SB_MissingCellEdge.mat'},
            "Cells must use their own face and border materials")
    require(asset.parmTemplateGroup().find("preview_missing_modules").isHidden(), "Legacy preview selector remains visible")
    for notch_side in (0, 1):
        asset.parm('massing_shape').set(1)
        asset.parm('l_notch_side').set(notch_side)
        assert_preview_normals_and_corners(asset)
    asset.parm('massing_shape').set(0)
    asset.parm('roof_enabled').set(0)
    preview.cook(force=True)
    require(not any(p.stringAttribValue('module_role') in ('RoofSurface','Parapet','ParapetCorner','ParapetConcaveCorner')
                    for p in preview.geometry().prims()), "Disabled roof emitted missing cells")
    asset.parm('roof_enabled').set(1)
    asset.parm("preview_missing_modules").set(1)
    preview.cook(force=True)
    require(len(preview.geometry().prims())>0, "Legacy leave-empty must now show automatic cells")
    row=style_row(2, SOURCE_PREFIX+"Brick_Plain_4.fbx",height=4,floors=1,facades=1)
    asset.parm("unity_style_catalog").set("STYLE|2|4|3\n"+row)
    asset.parm("ground_floor_use").set(2)
    real.cook(force=True)
    points=real.geometry().points()
    require(len(points)>0, "Sparse ground module did not generate")
    require(all(p.stringAttribValue("module_role")=="GroundWall" and p.intAttribValue("floor_index")==0 for p in points), "Sparse catalog borrowed another floor/role")
    before=[tuple(p.position()) for p in points]
    asset.parm("preview_missing_modules").set(0)
    real.cook(force=True); preview.cook(force=True)
    require(before==[tuple(p.position()) for p in real.geometry().points()], "Preview display changed real instances")
    require(len(preview.geometry().prims())>0, "Sparse missing modules have no grayboxes")
    require(preview.geometry().intAttribValue("streetbuilding_preview_only")==1, "Preview output lacks Bake exclusion marker")
    # A connected empty input is invalid, not an implicit standalone fallback.
    site=asset.parent().createNode("geo", "VERIFY_PARTIAL_SITE")
    try:
        empty=site.createNode("null")
        asset.setInput(0,site)
        canonical=core.node("CANONICALIZE_PARCELS")
        try: canonical.cook(force=True)
        except hou.OperationFailed: pass
        require(bool(canonical.errors()), "Connected empty site silently fell back")
        grid=site.createNode("grid")
        grid.parm("rows").set(2); grid.parm("cols").set(2)
        grid.setDisplayFlag(True); grid.setRenderFlag(True)
        canonical.cook(force=True)
        require(not canonical.errors() and len(canonical.geometry().prims())==1,
                "Connected valid parcel was not consumed")
        line=site.createNode("line")
        line.setDisplayFlag(True); line.setRenderFlag(True)
        try: canonical.cook(force=True)
        except hou.OperationFailed: pass
        require(bool(canonical.errors()), "Invalid line site silently fell back")
        asset.setInput(0,None)
        canonical.cook(force=True)
        require(not canonical.errors(), "Disconnected standalone did not recover")
    finally:
        asset.setInput(0,None); site.destroy()
    return {"empty":True,"sparse_real_instances":len(before),"preview_isolated":True,"auto_site":True}


def assert_unified_ground(parent_asset: hou.Node) -> dict[str, Any]:
    asset = parent_asset.parent().createNode(ASSET_TYPE, 'VERIFY_UNIFIED_GROUND')
    try:
        rows = []
        for row in catalog_module_rows(STYLE_CATALOG):
            if int(row[2]) in (0, 1, 2, 3):
                row[11] = '1'
            rows.append('|'.join(row))
        payload = STYLE_CATALOG.splitlines()[0] + '\n' + '\n'.join(rows)
        configure(asset, payload, rhythm=0)
        asset.parm('unified_ground_walls').set(1)
        previous = -1
        variants = set()
        positions = []
        for seed in range(20):
            asset.parm('layout_seed').set(seed * 311 + 7)
            asset.parm('previous_entrance_cell').set(previous)
            geo = geometry(asset, 'SELECT_FACADE_MODULES')
            points = list(geo.points())
            entrances = [p for p in points if p.intAttribValue('is_building_entrance')]
            require(len(entrances) == 1, 'Unified entrance must be exactly one')
            entry = entrances[0]
            require(entry.intAttribValue('preview_missing') == 0, 'Unified entrance is a placeholder')
            current = entry.intAttribValue('cell_index')
            require(current != previous, 'Unified entrance repeats previous legal cell')
            previous = current
            positions.append(current)
            variants.add(entry.stringAttribValue('module_variant'))
            ground = [p for p in points if p.intAttribValue('floor_index') == 0]
            front = [p for p in ground if p.intAttribValue('facade_target') == 0]
            roles = {p.stringAttribValue('module_role') for p in front}
            require({'Entrance', 'GroundShop', 'GroundWall'} <= roles, 'Unified front omitted door/window/wall')
            for target in (2, 3):
                walls = [p for p in ground if p.intAttribValue('facade_target') == target and p.stringAttribValue('module_role') == 'GroundWall']
                require(walls and all(p.intAttribValue('preview_missing') == 0 for p in walls), 'Unified side/rear walls missing')
            signature = [(p.stringAttribValue('name'), tuple(p.position())) for p in points]
            same = geometry(asset, 'SELECT_FACADE_MODULES')
            require(signature == [(p.stringAttribValue('name'), tuple(p.position())) for p in same.points()], 'Locked layout is not deterministic')
            geometry(asset, 'OUT_BUILDING_LOD0')
        require(len(variants) > 1 and len(set(positions)) > 1, 'Entrance variants/positions do not vary')
        # Unity legacy instances can retain random-range/manual rules instead of style defaults.
        for mode in (1, 2):
            asset.parm('facade_layout_mode').set(mode)
            asset.parm('entrance_count_min').set(1)
            asset.parm('entrance_count_max').set(1)
            previous = -1
            for seed in range(20):
                asset.parm('layout_seed').set(30000 + seed * 137)
                asset.parm('previous_entrance_cell').set(previous)
                geo = geometry(asset, 'OUT_BUILDING_LOD0')
                entries = [p for p in geo.points() if p.intAttribValue('is_building_entrance')]
                require(len(entries) == 1, 'Legacy rule mode lost unique entrance')
                cell = entries[0].intAttribValue('cell_index')
                require(cell != previous, 'Legacy rule mode repeats previous entrance')
                previous = cell
        asset.parm('facade_layout_mode').set(0)
        # A two-cell entrance must occupy real adjacent cells without swallowing walls/windows.
        wide = []
        for row in catalog_module_rows(payload):
            if int(row[2]) == 3: row[5] = '2'
            wide.append('|'.join(row))
        asset.parm('unity_style_catalog').set('STYLE|2|4|3\n' + '\n'.join(wide))
        geo = geometry(asset, 'SELECT_FACADE_MODULES')
        entrances = [p for p in geo.points() if p.intAttribValue('is_building_entrance')]
        require(len(entrances) == 1 and entrances[0].intAttribValue('module_span') == 2, 'Wide entrance span lost')
        front = [p for p in geo.points() if p.intAttribValue('floor_index') == 0 and p.intAttribValue('facade_target') == 0 and p.stringAttribValue('module_role') in ('GroundWall', 'GroundShop', 'GroundShopDoor', 'Entrance')]
        occupied = []
        for p in front: occupied.extend(range(p.intAttribValue('cell_index'), p.intAttribValue('cell_index') + p.intAttribValue('module_span')))
        require(sorted(occupied) == list(range(6)), 'Unified spans overlap or leave holes')
        asset.parm('unity_style_catalog').set('STYLE|2|4|3\n' + '\n'.join(row for row in wide if row.split('|')[2] != '3'))
        failed = False
        try:
            target = node(asset, 'SELECT_FACADE_MODULES')
            target.cook(force=True)
            failed = bool(target.errors())
        except hou.OperationFailed:
            failed = True
        require(failed, 'Missing entrance was accepted')
        return dict(cases=20, positions=positions, entrance_variants=len(variants), wide_entrance=True, missing_entrance='rejected')
    finally:
        asset.destroy()


def assert_upper_wall_fallback(parent_asset: hou.Node) -> dict[str, Any]:
    asset = parent_asset.parent().createNode(ASSET_TYPE, 'VERIFY_UPPER_WALLS')
    try:
        rows = [r for r in catalog_module_rows(STYLE_CATALOG) if int(r[2]) not in (10, 11)]
        for r in rows:
            if int(r[2]) == 5:
                r[10], r[11] = '15', '2'
        def check(mask):
            for r in rows:
                if int(r[2]) == 5: r[10] = str(mask)
            configure(asset, 'STYLE|2|4|3\n' + '\n'.join('|'.join(r) for r in rows))
            points = list(geometry(asset, 'SELECT_FACADE_MODULES').points())
            for target in (2, 3):
                walls = [p for p in points if p.intAttribValue('floor_index') > 0
                         and p.intAttribValue('facade_target') == target
                         and p.stringAttribValue('module_role') in ('SideWall', 'RearWall', 'MiddleBlank')]
                require(walls, 'Upper side/rear output absent')
                allowed = bool(mask & (1 << target))
                require(all((p.intAttribValue('preview_missing') == 0) == allowed for p in walls),
                        'Upper wall direction filtering/fallback failed')
                if allowed:
                    require(all(p.stringAttribValue('module_role') == 'MiddleBlank' for p in walls),
                            'Upper fallback used wrong floor role')
        check(15)
        check(4)
        check(3)
        return dict(all_faces=True, side_only=True, front_only_excluded=True)
    finally:
        asset.destroy()


def assert_upper_windows(parent_asset: hou.Node) -> dict[str, Any]:
    """Reproduce ignored facade masks and reject cross-run window footprints."""
    asset = parent_asset.parent().createNode(ASSET_TYPE, 'VERIFY_UPPER_WINDOWS')
    cases = 0
    try:
        for shape in (0, 1):
            for target in (2, 3):
                for mask, width, walls in ((3, 1, True), (4, 1, True), (8, 1, True),
                                            (12, 1, True), (15, 2, True), (15, 2, False)):
                    rows = [r for r in catalog_module_rows(STYLE_CATALOG) if int(r[2]) != 4
                            and (walls or int(r[2]) not in (5, 10, 11))]
                    path = SOURCE_PREFIX + ('Brick_Window_CurvedDouble.fbx' if width == 2
                                            else 'Brick_Window_Trim_Single.fbx')
                    catalog = 'STYLE|2|4|3\n' + '\n'.join('|'.join(r) for r in rows)
                    catalog += '\n' + style_row(4, path, width=width, facades=mask, floors=2)
                    configure(asset, catalog, shape=shape, attachments=0)
                    set_facade_override(asset, floor_from=2, floor_to=4, mode=2,
                                        rhythm=1, window=(64, 64))
                    asset.parm('facade_override_target1').set(target)
                    source = geometry(asset, 'ALLOCATE_FACADE_CAPACITY').freeze()
                    output = geometry(asset, 'SELECT_FACADE_MODULES').freeze()
                    eligible = [p for p in source.points() if p.intAttribValue('floor_index') > 0
                                and p.intAttribValue('facade_target') == target]
                    emitted = [p for p in output.points() if p.intAttribValue('floor_index') > 0
                               and p.intAttribValue('facade_target') == target
                               and p.stringAttribValue('semantic_role') in ('window', 'blank')]
                    require(eligible and emitted, 'Upper-window fixture has no facade cells')
                    occupied = set()
                    windows = 0
                    for p in emitted:
                        cell, floor = p.intAttribValue('cell_index'), p.intAttribValue('floor_index')
                        first = next(q for q in eligible if q.intAttribValue('cell_index') == cell
                                     and q.intAttribValue('floor_index') == floor)
                        span = p.intAttribValue('module_span')
                        role = p.stringAttribValue('module_role')
                        if role == 'MiddleWindow':
                            windows += 1
                            require(mask & (1 << target), 'Disabled side/rear window was emitted')
                            require(span == width and not p.intAttribValue('preview_missing'),
                                    'Window span or instance path was lost')
                        origin = hou.Vector3(first.attribValue('placement_origin'))
                        right = hou.Vector3(first.attribValue('placement_right'))
                        run_cell = first.intAttribValue('run_local_cell')
                        require(run_cell + span <= first.intAttribValue('run_cell_count'),
                                'Window crosses the end of its wall run')
                        for offset in range(span):
                            candidates = [q for q in eligible
                                          if q.intAttribValue('floor_index') == floor
                                          and q.intAttribValue('face_index') == first.intAttribValue('face_index')
                                          and q.intAttribValue('run_local_cell') == run_cell + offset
                                          and q.attribValue('placement_origin') == first.attribValue('placement_origin')
                                          and q.attribValue('placement_right') == first.attribValue('placement_right')]
                            require(len(candidates) == 1, 'Window crossed a corner or disconnected wall run')
                            q = candidates[0]
                            require(q.stringAttribValue('semantic_role') == first.stringAttribValue('semantic_role'),
                                    'Window consumed a blank cell')
                            key = (floor, q.intAttribValue('cell_index'))
                            require(key not in occupied, 'Two modules occupy the same facade cell')
                            occupied.add(key)
                        expected = origin + right * (first.floatAttribValue('local_u') + (span - 1))
                        expected[1] = 4 + (floor - 1) * 3
                        expected[0] = -expected[0]
                        require((p.position() - expected).length() < .001, 'Window pivot is not centered on its span')
                        if role != 'MiddleWindow':
                            require(bool(p.intAttribValue('preview_missing')) == (not walls),
                                    'Missing window broke wall fallback/preview isolation')
                    require(len(occupied) == len(eligible), 'Facade cells were lost during span consumption')
                    require((windows > 0) == bool(mask & (1 << target)),
                            'Allowed side/rear windows were ignored in favor of walls')
                    if width == 1 and mask & (1 << target):
                        require(windows == len(eligible), 'Single-cell windows did not honor all window semantics')
                    require(signature(output) == signature(geometry(asset, 'SELECT_FACADE_MODULES')),
                            'Upper side/rear windows are nondeterministic')
                    geometry(asset)  # final instance validation, including no Cook diagnostics
                    cases += 1
        return {'cases': cases, 'facade_masks': True, 'continuous_spans': True,
                'wall_and_preview_fallback': True, 'deterministic': True}
    finally:
        asset.destroy()


def validate(hda: Path, hip: Path, contract_path: Path) -> dict[str, Any]:
    require(hda.is_file() and hip.is_file(), "StreetBuilding HDA/HIP is missing")
    contract = json.loads(contract_path.read_text(encoding="utf-8"))
    require(contract["revision"] == REVISION and contract["contract_version"] == CONTRACT_VERSION,
            "Contract revision/version mismatch")
    expected = {"StreetBuilding.V5.WeightedDeterminism",
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
                "StreetBuilding.V8.CornerTopologyOrientation",
                "StreetBuilding.V8.DedicatedConcaveCornerAsset",
                "StreetBuilding.V8.ACWallSupportPlane",
                "StreetBuilding.V8.ACLShapeCellContainment",
                "StreetBuilding.V10.VersionlessStylePayload",
                "StreetBuilding.V9.GenerationModes",
                "StreetBuilding.V9.FacadeFloorOverrides",
                "StreetBuilding.V9.FunctionPriorityCompression",
                "StreetBuilding.V9.ParcelFrontageRulePayload",
                "StreetBuilding.V9.AttachmentGroups",
                "StreetBuilding.V9.RuleDeterminism",
                "StreetBuilding.V9.UnityBridgeHapiVisible",
                "StreetBuilding.V12.HdaPanelSingleSource",
                "StreetBuilding.V12.ExternalParcelOnlyOverride",
                "StreetBuilding.V12.StyleBridgeHapiVisible",
                "StreetBuilding.V13.PrefabFilenameVariant",
                "StreetBuilding.Layers.StyleDefaultsAndOverrides", "StreetBuilding.Layers.FloorOwnership",
                "StreetBuilding.Layers.IndependentSelection", "StreetBuilding.Layers.MigrationAndTransactions"}
    require(expected.issubset(contract["contract_ids"]), "Cumulative behavior IDs are missing")
    hou.hipFile.clear(suppress_save_prompt=True)
    hou.hipFile.load(str(hip), suppress_save_prompt=True, ignore_load_warnings=False)
    hou.hda.installFile(str(hda), change_oplibraries_file=False, force_use_assets=True)
    fresh = hou.node("/obj").createNode(ASSET_TYPE, "VERIFY_STREETBUILDING_V12_LOCKED")
    require(not fresh.isEditable(), "Fresh validation instance must remain locked")
    assert_interface(fresh, contract)
    assert_network(fresh, contract)
    return {"status": "PASS", "asset_type": fresh.type().name(), "instance": fresh.path(),
            "locked": not fresh.isEditable(), "internal_proxy": assert_internal(fresh),
            "prefab_filename_variant": assert_prefab_filename_variant(fresh),
            "versionless_full_envelope": assert_full_envelope(fresh),
            "v6_1_modular_details": assert_details(fresh, contract),
            "l_shape_topology": assert_l_shape(fresh),
            "generation_rules": assert_generation_rules(fresh, contract),
            "dimension_contract": assert_dimension_contract(),
            "three_layer_rules": assert_layer_rules(fresh),
            "partial_preview": assert_partial_preview(fresh),
            "unified_ground": assert_unified_ground(fresh),
            "upper_wall_fallback": assert_upper_wall_fallback(fresh),
            "upper_windows": assert_upper_windows(fresh)}


def validate_live_candidate(root: Path, hda: Path, contract: Path, host: str, port: int) -> dict[str, Any]:
    """Export Live to scratch files, verify fresh locked candidate before persistence.

    Uses the regression harness RPC connection, never an old patch/builder.
    This hython process owns only its disposable HIP and definition.
    """
    import uuid
    from pcg_regression_gate import connect_live
    candidate = root / '.codex_tmp' / 'regression' / ('streetbuilding-candidate-' + uuid.uuid4().hex)
    candidate.mkdir(parents=True)
    items = candidate / 'live.cpio'
    connection = connect_live(host, port)
    try:
        connection.execute('''
import hou
def _sb_export_candidate(path):
    a=hou.node('/obj/StreetBuilding_DEV')
    if a is None or a.type().name()!='pcgbike::StreetBuilding::1.0':
        raise RuntimeError('Live StreetBuilding instance changed')
    a.parent().saveItemsToFile((a,),path)
    return a.type().definition().libraryFilePath()
''')
        definition_path = str(connection.eval('_sb_export_candidate({!r})'.format(str(items))))
        require(Path(definition_path).resolve() == hda, 'Candidate definition differs from expected production HDA')
    finally:
        connection.close()
    hou.hda.installFile(str(hda), change_oplibraries_file=False, force_use_assets=True)
    hou.node('/obj').loadItemsFromFile(str(items))
    asset = hou.node('/obj/StreetBuilding_DEV')
    definition = asset.type().definition()
    templates = definition.parmTemplateGroup()
    layer = next(t for t in asset.parmTemplateGroup().entries()
                 if isinstance(t, hou.FolderParmTemplate)
                 and any(p.name()=='style_rule_source' for p in t.parmTemplates()))
    layer.setName('sb_layers')
    if templates.find('style_rule_source') is None:
        templates.append(layer)
    # Candidate interface must include the new Live preview controls; do not
    # silently validate new node code against an old definition interface.
    preview = next(t for t in asset.parmTemplateGroup().entries()
                   if isinstance(t, hou.FolderParmTemplate)
                   and any(p.name() == 'preview_missing_modules' for p in t.parmTemplates()))
    preview.setName('sb_preview')
    if templates.find('preview_missing_modules') is None:
        templates.append(preview)
    else:
        templates.replace('preview_missing_modules', asset.parmTemplateGroup().find('preview_missing_modules'))
    templates.replace('site_source', asset.parmTemplateGroup().find('site_source'))
    for name in ('unified_ground_walls', 'layout_seed', 'previous_entrance_cell'):
        template = asset.parmTemplateGroup().find(name)
        require(template is not None, 'Unified ground interface is missing: ' + name)
        if templates.find(name) is None:
            templates.append(template)
        else:
            templates.replace(name, template)
    candidate_hda = candidate / 'StreetBuilding.hda'
    candidate_hip = candidate / 'StreetBuilding.hip'
    definition.copyToHDAFile(str(candidate_hda))
    hou.hda.installFile(str(candidate_hda), change_oplibraries_file=False, force_use_assets=True)
    candidate_definition = hou.hda.definitionsInFile(str(candidate_hda))[0]
    candidate_definition.updateFromNode(asset)
    candidate_definition.setParmTemplateGroup(templates)
    candidate_definition.setIsPreferred(True)
    hou.hipFile.save(str(candidate_hip))
    result = validate(candidate_hda, candidate_hip, contract)
    result['candidate_directory'] = str(candidate)
    result['production_saved'] = False
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    default_root = Path(__file__).resolve().parents[4]
    parser.add_argument("--project-root", type=Path, default=default_root)
    parser.add_argument("--hda", type=Path)
    parser.add_argument("--hip", type=Path)
    parser.add_argument("--contract", type=Path)
    parser.add_argument("--source", choices=('fresh', 'live-candidate'), default='fresh')
    parser.add_argument("--host", default='127.0.0.1')
    parser.add_argument("--port", type=int, default=18811)
    args = parser.parse_args()
    root = args.project_root.resolve()
    hda = (args.hda or root / "Assets/PCG/HDA/City/StreetBuilding.hda").resolve()
    hip = (args.hip or root / "HoudiniProject/PCG_Track_21.0.440/PCG_Bike_StreetBuilding.hip").resolve()
    contract = (args.contract or root / "HoudiniProject/PCG_Track_21.0.440/scripts/contracts/streetbuilding_contract.json").resolve()
    result = (validate_live_candidate(root, hda, contract, args.host, args.port)
              if args.source == 'live-candidate' else validate(hda, hip, contract))
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (ContractFailure, OSError, ValueError, json.JSONDecodeError) as exception:
        print(f"STREETBUILDING_CONTRACT_FAIL: {exception}", file=sys.stderr)
        raise SystemExit(1)
