"""V6.1 patch: aligned roof shell, modular parapets and grounded roof details.

The patch is intentionally incremental over the persisted V6 definition.  It
has an exact V6 marker/snippet precondition, is idempotent, supports a byte-clean
``save=False`` validation pass and only persists after all in-memory contracts
pass in the disposable hython process.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

import hou


REL_HDA = Path("Assets/PCG/HDA/City/StreetBuilding.hda")
REL_HIP = Path("HoudiniProject/PCG_Track_21.0.440/PCG_Bike_StreetBuilding.hip")
ASSET_PATH = "/obj/StreetBuilding_DEV"
ASSET_TYPE = "pcgbike::StreetBuilding::1.0"
PREVIOUS_MARKER = "STREETBUILDING_V6_MODULAR_DETAILS"
MARKER = "STREETBUILDING_V6_1_ROOF_ALIGNMENT"
CONTRACT_VERSION = "StreetBuilding.DirectInstances.6.1"


ROOF_BODY = r'''// STREETBUILDING_V6_1_ROOF_SHELL
string catalog = chs("../../unity_instance_catalog");
if (sb_schema(catalog) != 2 || !chi("../../generate_roof")) return;
float width = ch("../../internal_width");
float depth = ch("../../internal_depth");
int width_cells = int(rint(width / 2.0));
int depth_cells = int(rint(depth / 2.0));
if (abs(width - width_cells * 2.0) > .01 || abs(depth - depth_cells * 2.0) > .01)
    error("StreetBuilding roof dimensions must be multiples of 2m");
int floors = max(2, chi("../../floor_count"));
float roof_y = ch("../../ground_floor_height")
    + (floors - 1) * ch("../../typical_floor_height");
int global_seed = chi("../../seed");
vector origin = set(-width * .5, 0, 0);
vector right = set(1, 0, 0);
vector outward = set(0, 0, -1);
for (int zcell = 0; zcell < depth_cells; zcell++)
{
    for (int xcell = 0; xcell < width_cells; xcell++)
    {
        int cell = zcell * width_cells + xcell;
        int key = global_seed * 1009 + 4 * 503 + cell * 37;
        int span; string roof = sb_choose_variant(catalog, "RoofSurface", key, 1, span);
        vector tile_origin = origin + set(0, 0, -(zcell + .5) * 2.0);
        sb_emit(catalog, "RoofSurface", roof, tile_origin, right, outward,
            (xcell + .5) * 2.0, roof_y, 0, 4, "roof", floors, cell, key, 0);
    }
}
removeattrib(0, "point", "N");
'''


ROOF_EDGE_BODY = r'''// STREETBUILDING_V6_1_ROOF_EDGE_INSTANCES
string catalog = chs("../../unity_instance_catalog");
if (sb_schema(catalog) != 2 || !chi("../../generate_roof")) return;
float parapet_h = ch("../../parapet_height");
if (parapet_h <= .001) return;
if (!sb_has_role(catalog, "Parapet") || !sb_has_role(catalog, "ParapetCorner"))
    error("StreetBuilding V6.1 requires Parapet and ParapetCorner when parapet_height is enabled");
float width = ch("../../internal_width");
float depth = ch("../../internal_depth");
int width_cells = int(rint(width / 2.0));
int depth_cells = int(rint(depth / 2.0));
if (width_cells < 2 || depth_cells < 2)
    error("StreetBuilding V6.1 parapet needs at least a 4m x 4m roof");
int floors = max(2, chi("../../floor_count"));
float roof_y = ch("../../ground_floor_height")
    + (floors - 1) * ch("../../typical_floor_height");
int seed = chi("../../seed");

// Straight pieces exclude the four corners; corner Prefabs own one metre of
// coping in both directions, so the perimeter is continuous without overlap.
for (int face = 0; face < 4; face++)
{
    int cells = face < 2 ? width_cells : depth_cells;
    vector origin = face == 0 ? set(-width * .5, 0, 0) :
        face == 1 ? set(width * .5, 0, -depth) :
        face == 2 ? set(-width * .5, 0, -depth) : set(width * .5, 0, 0);
    vector right = face == 0 ? set(1, 0, 0) : face == 1 ? set(-1, 0, 0) :
        face == 2 ? set(0, 0, 1) : set(0, 0, -1);
    vector outward = face == 0 ? set(0, 0, 1) : face == 1 ? set(0, 0, -1) :
        face == 2 ? set(-1, 0, 0) : set(1, 0, 0);
    float yaw = face == 0 ? 0 : face == 1 ? -180 : face == 2 ? 90 : -90;
    string surface = face == 0 ? "front" : face == 1 ? "rear" :
        face == 2 ? "left" : "right";
    for (int cell = 1; cell < cells - 1; cell++)
    {
        int key = seed * 1009 + (face + 5) * 503 + cell * 37;
        int span; string variant = sb_choose_variant(catalog, "Parapet", key, 1, span);
        sb_emit(catalog, "Parapet", variant, origin, right, outward,
            (cell + .5) * 2.0, roof_y, yaw, face, surface, floors, cell, key, 0);
    }
}

vector corner_positions[] = array(
    set(-width * .5, roof_y, 0), set(width * .5, roof_y, 0),
    set(width * .5, roof_y, -depth), set(-width * .5, roof_y, -depth));
float corner_yaws[] = array(0.0, -90.0, -180.0, 90.0);
for (int corner = 0; corner < 4; corner++)
{
    int key = seed * 1009 + 9001 + corner * 37;
    int span; string variant = sb_choose_variant(catalog, "ParapetCorner", key, 1, span);
    // The corner prefab pivot is the exact outside corner; its authored L shape
    // extends inward along local +X and -Z after applying this yaw.
    sb_emit(catalog, "ParapetCorner", variant, corner_positions[corner],
        set(1, 0, 0), set(0, 0, 1), 0, 0, corner_yaws[corner], 4,
        "roof_edge", floors, corner, key, 0);
}
removeattrib(0, "point", "N");
'''


def _replace_exact(text: str, old: str, new: str, label: str,
                   expected_count: int | None = None) -> str:
    count = text.count(old)
    if expected_count is not None and count != expected_count:
        raise RuntimeError(f"{label}: expected {expected_count} matches, got {count}")
    if count == 0:
        raise RuntimeError(f"{label}: precondition did not match")
    return text.replace(old, new)


def _set_input(node: hou.Node, index: int, source: hou.Node | None) -> bool:
    if node.input(index) == source:
        return False
    node.setInput(index, source)
    return True


def _ensure_node(core: hou.Node, type_name: str, name: str) -> tuple[hou.Node, bool]:
    node = core.node(name)
    if node is None:
        return core.createNode(type_name, name), True
    if node.type().name() != type_name:
        raise RuntimeError(f"{node.path()} must be {type_name}, got {node.type().name()}")
    return node, False


def _catalog_row(role: str, variant: str, path: str, width: float = 2,
                 height: float = 3, weight: float = 1) -> str:
    return (f"M|{role}|{variant}|0|Assets/Test/{path}.prefab|0|0|0|0|0|0|"
            f"{width}|{height}|{weight}")


TEST_V2 = "\n".join([
    "SBV2|na_brick_mixeduse_01|2|4|3",
    _catalog_row("Entrance", "entrance", "Entrance"),
    "M|Entrance|entrance|1|Assets/Test/EntranceDoor.prefab|0|0|0|0|0|0|2|3|1",
    _catalog_row("GroundShop", "shop", "Shop", height=4),
    _catalog_row("GroundWall", "ground", "Ground", height=4),
    _catalog_row("Cornice", "cornice", "Cornice", height=1),
    _catalog_row("MiddleWindow", "window", "Window"),
    _catalog_row("MiddleWindow", "curved_double", "WindowDouble", width=4),
    _catalog_row("MiddleBlank", "blank", "Blank"),
    _catalog_row("SideWall", "side_ground", "SideGround", height=4),
    _catalog_row("SideWall", "side_upper", "SideUpper"),
    _catalog_row("RearWall", "rear_ground", "RearGround", height=4),
    _catalog_row("RearWall", "rear_upper", "RearUpper"),
    _catalog_row("FacadeColumn", "trim_ground", "ColumnGround"),
    _catalog_row("FacadeColumn", "brick_upper", "ColumnUpper"),
    _catalog_row("RoofSurface", "roof_2x2", "Roof", height=2),
    _catalog_row("Parapet", "straight_2m", "Parapet", height=.6),
    _catalog_row("ParapetCorner", "corner_90", "ParapetCorner", height=.6),
    _catalog_row("Awning", "canopy", "Awning", height=1),
    _catalog_row("Sign", "board", "Sign", height=1),
    _catalog_row("FireEscape", "two_floor", "FireEscape", width=4, height=6),
    _catalog_row("ACUnit", "wall_unit", "AC", height=1),
    _catalog_row("RoofProp", "water_tank", "WaterTank", height=2, weight=1),
    _catalog_row("RoofProp", "roof_vent", "RoofVent", height=2, weight=.7),
    _catalog_row("RoofProp", "mechanical_box", "MechanicalBox", height=2, weight=.5),
])


def _signature(geometry: hou.Geometry) -> list[tuple]:
    return sorted((
        point.stringAttribValue("name"),
        point.stringAttribValue("unity_instance"),
        tuple(round(value, 6) for value in point.position()),
        tuple(round(value, 6) for value in point.attribValue("orient")),
    ) for point in geometry.points())


def _cook_or_raise(node: hou.Node, label: str) -> None:
    try:
        node.cook(force=True)
    except hou.OperationFailed as exc:
        core = node.parent()
        diagnostics = []
        for child in core.allSubChildren():
            diagnostics.extend(f"{child.path()}: {message}" for message in child.errors())
            diagnostics.extend(f"{child.path()}: {message}" for message in child.warnings())
        raise RuntimeError(label + " cook failed:\n" + "\n".join(diagnostics)) from exc


def _validate(asset: hou.Node) -> dict:
    core = asset.node("StreetBuildingCore")
    lod0 = core.node("OUT_BUILDING_LOD0")
    details = core.node("OUT_DETAIL_INSTANCES")
    names = (
        "module_source", "unity_instance_catalog", "style_id", "internal_width",
        "internal_depth", "ground_floor_height", "typical_floor_height", "floor_count",
        "parapet_height", "facade_rhythm", "detail_density", "generate_attachments",
        "rear_mode", "side_mode", "generate_roof", "generate_lods", "seed",
    )
    saved = {name: asset.parm(name).eval() for name in names}
    try:
        settings = {
            "module_source": 1, "unity_instance_catalog": TEST_V2,
            "style_id": "na_brick_mixeduse_01", "internal_width": 12,
            "internal_depth": 10, "ground_floor_height": 4,
            "typical_floor_height": 3, "floor_count": 4, "parapet_height": .6,
            "facade_rhythm": 3, "detail_density": 1, "generate_attachments": 1,
            "rear_mode": 2, "side_mode": 2, "generate_roof": 1,
            "generate_lods": 0, "seed": 29,
        }
        for name, value in settings.items():
            asset.parm(name).set(value)
        edge = core.node("BUILD_DIRECT_ROOF_EDGE_INSTANCES")
        _cook_or_raise(edge, "V6.1 roof edge")
        edge_points = edge.geometry().intrinsicValue("pointcount")
        _cook_or_raise(lod0, "V6.1 LOD0")
        geo = lod0.geometry()
        roles = [p.stringAttribValue("module_role") for p in geo.points()]
        counts = {role: roles.count(role) for role in set(roles)}
        if geo.intrinsicValue("pointcount") != 161:
            merge_inputs = [item.path() if item else None for item in core.node("MERGE_DIRECT_BUILDING_INSTANCES").inputs()]
            raise RuntimeError(f"V6.1 expected 161 LOD0 points, got {geo.intrinsicValue('pointcount')}: "
                               f"edge={edge_points}, merge={merge_inputs}, roles={counts}")
        if counts.get("RoofSurface") != 30 or counts.get("Parapet") != 14 \
                or counts.get("ParapetCorner") != 4:
            raise RuntimeError(f"V6.1 roof coverage counts failed: {counts}")
        roof_points = [p for p in geo.points() if p.stringAttribValue("module_role") == "RoofSurface"]
        expected_x = {-5.0, -3.0, -1.0, 1.0, 3.0, 5.0}
        expected_z = {-1.0, -3.0, -5.0, -7.0, -9.0}
        actual_x = {round(p.position()[0], 3) for p in roof_points}
        actual_z = {round(p.position()[2], 3) for p in roof_points}
        # Houdini mirrors Unity X for instance points.
        if actual_x != expected_x or actual_z != expected_z:
            raise RuntimeError(f"V6.1 roof footprint mismatch: X={actual_x}, Z={actual_z}")
        base_signature = _signature(geo)
        _cook_or_raise(lod0, "V6.1 deterministic LOD0")
        if _signature(lod0.geometry()) != base_signature:
            raise RuntimeError("V6.1 same-seed shell is not deterministic")

        roof_y = 13.0
        seen_roof_variants: set[str] = set()
        saw_roof_prop = False
        for seed in range(1, 65):
            asset.parm("seed").set(seed)
            _cook_or_raise(details, f"V6.1 details seed {seed}")
            for point in details.geometry().points():
                role = point.stringAttribValue("module_role")
                if role == "RoofProp":
                    saw_roof_prop = True
                    variant = point.stringAttribValue("module_variant")
                    seen_roof_variants.add(variant)
                    if variant == "ac_unit" or abs(point.position()[1] - roof_y) > .01:
                        raise RuntimeError(f"V6.1 invalid roof prop {variant} at {point.position()}")
                    if abs(point.position()[0]) > 4.01 or point.position()[2] > -1.99 \
                            or point.position()[2] < -8.01:
                        raise RuntimeError("V6.1 roof prop escaped the one-cell setback")
                if role == "ACUnit" and (point.intAttribValue("face_index") not in (1, 2, 3)
                                         or point.intAttribValue("floor_index") < 1):
                    raise RuntimeError("V6.1 AC unit escaped upper side/rear faces")
        if not saw_roof_prop or len(seen_roof_variants) < 2:
            raise RuntimeError(f"V6.1 roof prop seed coverage failed: {seen_roof_variants}")

        asset.parm("seed").set(29)
        diagnostics = []
        for node in (lod0, details, core.node("BUILD_DIRECT_ROOF_INSTANCES"),
                     core.node("BUILD_DIRECT_ROOF_EDGE_INSTANCES"),
                     core.node("VALIDATE_DIRECT_BUILDING_INSTANCES"),
                     core.node("VALIDATE_DIRECT_DETAIL_INSTANCES")):
            diagnostics.extend(node.errors())
            diagnostics.extend(node.warnings())
        if diagnostics:
            raise RuntimeError("V6.1 cook diagnostics: " + "\n".join(diagnostics))
        return {
            "lod0_points": 161,
            "roof_tiles": 30,
            "parapet_straights": 14,
            "parapet_corners": 4,
            "roof_prop_variants": sorted(seen_roof_variants),
            "deterministic": True,
        }
    finally:
        for name, value in saved.items():
            asset.parm(name).set(value)


def _patch_height_snippet(node: hou.Node, marker_old: str, marker_new: str,
                          side_rear: bool) -> bool:
    text = node.parm("snippet").eval()
    if marker_new in text:
        return False
    if marker_old not in text or MARKER in text:
        raise RuntimeError(f"Unexpected V6 height snippet at {node.path()}")
    text = _replace_exact(text, marker_old, marker_new, node.name() + ":marker", 1)
    floor_line = 'int floors = max(2, chi("../../floor_count"));'
    height_lines = (floor_line + '\nfloat ground_h = ch("../../ground_floor_height");'
                    '\nfloat typical_h = ch("../../typical_floor_height");')
    text = _replace_exact(text, floor_line, height_lines, node.name() + ":heights", 1)
    text = _replace_exact(text, "4 + (floor - 1) * 3",
                          "ground_h + (floor - 1) * typical_h",
                          node.name() + ":floor bases")
    if side_rear:
        text = _replace_exact(text, "\n                3, yaw,", "\n                ground_h - 1.0, yaw,",
                              node.name() + ":side cornice", 1)
        text = _replace_exact(text, "\n            3, -180,", "\n            ground_h - 1.0, -180,",
                              node.name() + ":rear cornice", 1)
    else:
        text = _replace_exact(text, ", u, 3, 0,", ", u, ground_h - 1.0, 0,",
                              node.name() + ":front cornice")
    node.parm("snippet").set(text)
    return True


SIDE_HEIGHT_SELECTOR = r'''
string sbv61_choose_height(string catalog; string role; int selection_seed;
    float target_height; export int selected_span)
{
    float total = 0.0;
    foreach (string row; split(catalog, "\n"))
    {
        string f[] = split(strip(row), "|");
        if (len(f) != 14 || f[0] != "M" || f[1] != role || atoi(f[3]) != 0
            || abs(atof(f[12]) - target_height) > .01) continue;
        int span = int(rint(atof(f[11]) / 2.0));
        if (span != 1) continue;
        total += max(0.0, atof(f[13]));
    }
    if (total <= 0.0) error("StreetBuilding V6.1 %s has no %.3fm module", role, target_height);
    float target = rand(float(selection_seed) * .731 + 19.17) * total;
    float cursor = 0.0;
    foreach (string row; split(catalog, "\n"))
    {
        string f[] = split(strip(row), "|");
        if (len(f) != 14 || f[0] != "M" || f[1] != role || atoi(f[3]) != 0
            || abs(atof(f[12]) - target_height) > .01) continue;
        int span = int(rint(atof(f[11]) / 2.0));
        if (span != 1) continue;
        cursor += max(0.0, atof(f[13]));
        if (target <= cursor) { selected_span = span; return f[2]; }
    }
    return "";
}
'''


def _patch_side_variant_heights(node: hou.Node) -> bool:
    text = node.parm("snippet").eval()
    marker = "// STREETBUILDING_V6_1_HEIGHT_FILTERED_VARIANTS"
    if marker in text:
        return False
    body_marker = "// STREETBUILDING_V6_1_SIDE_REAR_HEIGHTS"
    if body_marker not in text:
        raise RuntimeError("Unexpected V6.1 side/rear snippet for height filtering")
    text = text.replace(body_marker, marker + SIDE_HEIGHT_SELECTOR + "\n" + body_marker, 1)
    text = _replace_exact(
        text,
        'int span; string ground = sb_choose_variant(catalog, "SideWall", key, 1, span);',
        'int span; string ground = sbv61_choose_height(catalog, "SideWall", key, ground_h, span);',
        "side ground height selector", 1)
    text = _replace_exact(
        text,
        'int span; string ground = sb_choose_variant(catalog, "RearWall", key, 1, span);',
        'int span; string ground = sbv61_choose_height(catalog, "RearWall", key, ground_h, span);',
        "rear ground height selector", 1)
    old_upper = 'int fs; string variant = sb_choose_variant(catalog, role, fkey, 1, fs);'
    new_upper = ('int fs; string variant = role == "SideWall" || role == "RearWall"\n'
                 '                ? sbv61_choose_height(catalog, role, fkey, typical_h, fs)\n'
                 '                : sb_choose_variant(catalog, role, fkey, 1, fs);')
    text = _replace_exact(text, old_upper, new_upper, "side/rear upper height selectors", 2)
    node.parm("snippet").set(text)
    return True


def _patch_detail(node: hou.Node) -> bool:
    text = node.parm("snippet").eval()
    if "STREETBUILDING_V6_1_DETAIL_INSTANCE_POINTS" in text:
        return False
    if "STREETBUILDING_V6_DETAIL_INSTANCE_POINTS" not in text:
        raise RuntimeError("Unexpected V6 detail snippet")
    text = text.replace("STREETBUILDING_V6_DETAIL_INSTANCE_POINTS",
                        "STREETBUILDING_V6_1_DETAIL_INSTANCE_POINTS")
    text = _replace_exact(text, "float roof_y = 4 + (floors - 1) * 3;",
                          'float roof_y = ch("../../ground_floor_height") + (floors - 1) * ch("../../typical_floor_height");',
                          "detail roof height", 1)
    text = _replace_exact(text, "&& sbv6_has_role(catalog, \"RoofProp\"))",
                          '&& sbv6_has_role(catalog, "RoofProp")\n    && rand(float(seed) * .887 + 31.0) < density * .55)',
                          "detail roof probability", 1)
    text = _replace_exact(text, "set(-width * .5, 0, -zcell * 2.0)",
                          "set(-width * .5, 0, -(zcell + .5) * 2.0)",
                          "detail roof cell center", 1)
    text = _replace_exact(text, "roof_y + .25, 0, 4", "roof_y, 0, 4",
                          "detail roof grounding", 1)
    text = text.replace("StreetBuilding.DirectInstances.6.0", CONTRACT_VERSION)
    text = text.replace(PREVIOUS_MARKER, MARKER)
    node.parm("snippet").set(text)
    return True


def _patch_validators(building: hou.Node, detail: hou.Node) -> list[str]:
    changed = []
    btext = building.parm("snippet").eval()
    if "STREETBUILDING_V6_1_VALIDATE_OUTPUT" not in btext:
        if "STREETBUILDING_V5_VALIDATE_OUTPUT" not in btext:
            raise RuntimeError("Unexpected building validator")
        btext = btext.replace("STREETBUILDING_V5_VALIDATE_OUTPUT",
                              "STREETBUILDING_V6_1_VALIDATE_OUTPUT")
        btext = btext.replace("points >= 300", "points >= 400")
        btext = btext.replace("StreetBuilding V5", "StreetBuilding V6.1")
        btext = btext.replace("StreetBuilding.DirectInstances.5.0", CONTRACT_VERSION)
        btext = btext.replace("STREETBUILDING_V5_FULL_ENVELOPE_INSTANCES", MARKER)
        building.parm("snippet").set(btext)
        changed.append(building.name() + ":snippet")
    dtext = detail.parm("snippet").eval()
    if "STREETBUILDING_V6_1_VALIDATE_DETAILS" not in dtext:
        if "STREETBUILDING_V6_VALIDATE_DETAILS" not in dtext:
            raise RuntimeError("Unexpected detail validator")
        dtext = dtext.replace("STREETBUILDING_V6_VALIDATE_DETAILS",
                              "STREETBUILDING_V6_1_VALIDATE_DETAILS")
        needle = '    if (role == "RoofProp" && face != 4)\n        error("StreetBuilding V6 RoofProp must be on the roof");'
        replacement = needle + '''
    if (role == "RoofProp")
    {
        string variant = point(0, "module_variant", point);
        vector p = point(0, "P", point);
        float roof_y = ch("../../ground_floor_height")
            + (max(2, chi("../../floor_count")) - 1) * ch("../../typical_floor_height");
        if (variant == "ac_unit") error("StreetBuilding V6.1 forbids roof AC units");
        if (abs(p.y - roof_y) > .01) error("StreetBuilding V6.1 roof prop is floating");
    }'''
        dtext = _replace_exact(dtext, needle, replacement, "detail semantic validator", 1)
        dtext = dtext.replace("StreetBuilding V6 ", "StreetBuilding V6.1 ")
        dtext = dtext.replace("StreetBuilding.DirectInstances.6.0", CONTRACT_VERSION)
        dtext = dtext.replace(PREVIOUS_MARKER, MARKER)
        detail.parm("snippet").set(dtext)
        changed.append(detail.name() + ":snippet")
    return changed


def apply_loaded(asset: hou.Node, save: bool) -> dict:
    if asset is None or asset.type().name() != ASSET_TYPE:
        raise RuntimeError(f"Expected {ASSET_PATH} {ASSET_TYPE}")
    definition = asset.type().definition()
    if definition is None:
        raise RuntimeError("StreetBuilding has no definition")
    comment = definition.comment() or ""
    if PREVIOUS_MARKER not in comment and MARKER not in comment:
        raise RuntimeError("V6.1 requires the exact persisted V6 marker")
    asset.allowEditingOfContents()
    core = asset.node("StreetBuildingCore")
    changed: list[str] = []
    front = core.node("DIRECT_UNITY_INSTANCE_FACADE")
    side = core.node("BUILD_DIRECT_SIDE_REAR_INSTANCES")
    roof = core.node("BUILD_DIRECT_ROOF_INSTANCES")
    parser = core.node("PARSE_UNITY_INSTANCE_CATALOG")
    merge = core.node("MERGE_DIRECT_BUILDING_INSTANCES")
    building_validator = core.node("VALIDATE_DIRECT_BUILDING_INSTANCES")
    detail_points = core.node("DETAIL_INSTANCE_POINTS")
    detail_validator = core.node("VALIDATE_DIRECT_DETAIL_INSTANCES")
    if None in (front, side, roof, parser, merge, building_validator,
                detail_points, detail_validator):
        raise RuntimeError("StreetBuilding V6.1 prerequisites are missing")

    if _patch_height_snippet(front, "// STREETBUILDING_V5_FRONT",
                             "// STREETBUILDING_V6_1_FRONT_HEIGHTS", False):
        changed.append(front.name() + ":snippet")
    if _patch_height_snippet(side, "// STREETBUILDING_V6_SIDE_REAR_SHELL",
                             "// STREETBUILDING_V6_1_SIDE_REAR_HEIGHTS", True):
        changed.append(side.name() + ":snippet")
    if _patch_side_variant_heights(side):
        changed.append(side.name() + ":height-filter")

    current_roof = roof.parm("snippet").eval()
    if "// STREETBUILDING_V6_1_ROOF_SHELL" not in current_roof:
        old_marker = "// STREETBUILDING_V6_ROOF_SHELL"
        if old_marker not in current_roof:
            raise RuntimeError("Unexpected V6 roof snippet")
        common = current_roof.split(old_marker, 1)[0]
        roof.parm("snippet").set(common + ROOF_BODY)
        changed.append(roof.name() + ":snippet")
    else:
        common = current_roof.split("// STREETBUILDING_V6_1_ROOF_SHELL", 1)[0]

    edge, created = _ensure_node(core, "attribwrangle", "BUILD_DIRECT_ROOF_EDGE_INSTANCES")
    if edge.parm("class").eval() != 0:
        edge.parm("class").set(0)
        changed.append(edge.name() + ":class")
    expected_edge = common + ROOF_EDGE_BODY
    if edge.parm("snippet").eval() != expected_edge:
        if not created and MARKER in edge.parm("snippet").eval():
            raise RuntimeError("Divergent V6.1 roof edge snippet")
        edge.parm("snippet").set(expected_edge)
        changed.append(edge.name() + ":snippet")
    if created:
        changed.append(edge.name())
    if _set_input(edge, 0, parser):
        changed.append(edge.name() + ":input0")
    if _set_input(merge, 3, edge):
        changed.append(merge.name() + ":input3")

    if _patch_detail(detail_points):
        changed.append(detail_points.name() + ":snippet")
    changed.extend(_patch_validators(building_validator, detail_validator))

    edge.setPosition(roof.position() + hou.Vector2(3, 0))
    edge.setComment("V6.1 / 独立生成 2m 直线女儿墙与四个转角，不与屋面格重复。")
    edge.setGenericFlag(hou.nodeFlag.DisplayComment, True)
    roof.setComment("V6.1 / 2x2m 屋面中心铺设，完整覆盖建筑 footprint。")
    detail_points.setComment("V6.1 / 墙面空调与屋顶专用设施分流；屋顶设施落在 roofY。")

    validation = _validate(asset)
    if save and changed:
        definition.updateFromNode(asset)
        updated = (definition.comment() or "").replace(PREVIOUS_MARKER, MARKER)
        if MARKER not in updated:
            updated = updated.rstrip() + "\n" + MARKER
        definition.setComment(updated)
        asset.matchCurrentDefinition()
        hou.hipFile.save()
    return {
        "status": "UPDATED" if changed else "UNCHANGED",
        "save": save,
        "revision": MARKER,
        "contract": CONTRACT_VERSION,
        "nodes": changed,
        "validation": validation,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--project-root", required=True, type=Path)
    parser.add_argument("--save", choices=("true", "false"), default="false")
    parser.add_argument("--update-existing", choices=("true", "false"), default="true")
    args = parser.parse_args()
    root = args.project_root.resolve()
    hda = (root / REL_HDA).resolve()
    hip = (root / REL_HIP).resolve()
    before = (hashlib.sha256(hda.read_bytes()).hexdigest(),
              hashlib.sha256(hip.read_bytes()).hexdigest())
    hou.hipFile.load(str(hip), suppress_save_prompt=True, ignore_load_warnings=False)
    hou.hda.installFile(str(hda), change_oplibraries_file=False, force_use_assets=True)
    result = apply_loaded(hou.node(ASSET_PATH), args.save == "true")
    after = (hashlib.sha256(hda.read_bytes()).hexdigest(),
             hashlib.sha256(hip.read_bytes()).hexdigest())
    if args.save == "false" and before != after:
        raise RuntimeError("V6.1 save=False modified persisted HDA/HIP bytes")
    result["files"] = {"hda": after[0], "hip": after[1]}
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
