"""V6 patch: deterministic modular detail instances for StreetBuilding.

This patch requires the persisted V5 marker, works in a disposable hython
process, supports save=False, and only writes the production HDA/HIP when the
complete in-memory validation succeeds.
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
PREVIOUS_MARKER = "STREETBUILDING_V5_FULL_ENVELOPE_INSTANCES"
MARKER = "STREETBUILDING_V6_MODULAR_DETAILS"
REVISION = MARKER
CONTRACT_VERSION = "StreetBuilding.DirectInstances.6.0"

SIDE_REAR_V5_MARKER = "// STREETBUILDING_V5_SIDE_REAR"
SIDE_REAR_V6_MARKER = "// STREETBUILDING_V6_SIDE_REAR_SHELL"
SIDE_REAR_DENSITY_V5 = 'float density = clamp(ch("../../detail_density"), 0.0, 1.0);'
SIDE_REAR_DENSITY_V6 = "float shell_variation = 0.6;"


OLD_ROOF_ATTACHMENT = r'''        if (chi("../../generate_attachments") && sb_has_role(catalog, "RoofProp")
            && rand(float(key) * .291 + 5.0) < density * .12)
        {
            int ps; string prop = sb_choose_variant(catalog, "RoofProp", key + 23, 1, ps);
            sb_emit(catalog, "RoofProp", prop, tile_origin, right, outward, (xcell + .5) * 2,
                roof_y + .25, 0, 4, "roof", floors, cell, key + 23, 0);
        }
'''


DETAIL_SNIPPET = r'''// STREETBUILDING_V6_DETAIL_INSTANCE_POINTS
int sbv6_has_role(string catalog; string role)
{
    foreach (string row; split(catalog, "\n"))
    {
        string f[] = split(strip(row), "|");
        if (len(f) == 14 && f[0] == "M" && f[1] == role) return 1;
    }
    return 0;
}

string sbv6_choose(string catalog; string role; int selection_seed)
{
    float total = 0.0;
    foreach (string row; split(catalog, "\n"))
    {
        string f[] = split(strip(row), "|");
        if (len(f) == 14 && f[0] == "M" && f[1] == role && atoi(f[3]) == 0)
            total += max(0.0, atof(f[13]));
    }
    if (total <= 0.0) return "";
    float target = rand(float(selection_seed) * .731 + 19.17) * total;
    float cursor = 0.0;
    foreach (string row; split(catalog, "\n"))
    {
        string f[] = split(strip(row), "|");
        if (len(f) != 14 || f[0] != "M" || f[1] != role || atoi(f[3]) != 0) continue;
        cursor += max(0.0, atof(f[13]));
        if (target <= cursor) return f[2];
    }
    return "";
}

int sbv6_parts(string catalog; string role; string variant)
{
    int count = 0;
    foreach (string row; split(catalog, "\n"))
    {
        string f[] = split(strip(row), "|");
        if (len(f) == 14 && f[0] == "M" && f[1] == role && f[2] == variant)
            count = max(count, atoi(f[3]) + 1);
    }
    return count;
}

string sbv6_part(string catalog; string role; string variant; int part;
    export vector offset; export int span)
{
    offset = 0; span = 1;
    foreach (string row; split(catalog, "\n"))
    {
        string f[] = split(strip(row), "|");
        if (len(f) == 14 && f[0] == "M" && f[1] == role && f[2] == variant
            && atoi(f[3]) == part)
        {
            offset = set(atof(f[5]), atof(f[6]), atof(f[7]));
            if (length2(set(atof(f[8]), atof(f[9]), atof(f[10]))) > 1e-10)
                error("StreetBuilding V6 detail rotations belong inside Prefabs");
            span = int(rint(atof(f[11]) / 2.0));
            return f[4];
        }
    }
    return "";
}

int sbv6_emit(string catalog; string role; int selection_seed; vector origin;
    vector right; vector outward; float local_u; float base_y; float yaw;
    int face; string surface; int floor; int cell)
{
    string variant = sbv6_choose(catalog, role, selection_seed);
    if (len(variant) == 0) return 0;
    int parts = sbv6_parts(catalog, role, variant);
    for (int part = 0; part < parts; part++)
    {
        vector offset; int span;
        string path = sbv6_part(catalog, role, variant, part, offset, span);
        if (len(path) == 0) error("StreetBuilding V6 missing %s/%s part %d", role, variant, part);
        vector unity_p = origin + right * (local_u + offset.x)
            + set(0, base_y + offset.y, 0) + outward * offset.z;
        int pt = addpoint(0, set(-unity_p.x, unity_p.y, unity_p.z));
        vector4 orient = quaternion(radians(yaw), set(0, 1, 0));
        string token = face == 0 ? "FR" : face == 1 ? "LT" :
            face == 2 ? "RT" : face == 3 ? "BK" : "RF";
        string prefix = sprintf("SB_D0000_%s_F%02d_C%02d_%s_%s_P%d",
            token, floor, cell, role, variant, part);
        setpointattrib(0, "orient", pt, orient, "set");
        setpointattrib(0, "scale", pt, set(1, 1, 1), "set");
        setpointattrib(0, "unity_instance", pt, path, "set");
        setpointattrib(0, "instance_prefix", pt, prefix, "set");
        setpointattrib(0, "name", pt, prefix, "set");
        setpointattrib(0, "building_id", pt, 0, "set");
        setpointattrib(0, "face_index", pt, face, "set");
        setpointattrib(0, "floor_index", pt, floor, "set");
        setpointattrib(0, "cell_index", pt, cell, "set");
        setpointattrib(0, "module_span", pt, span, "set");
        setpointattrib(0, "selection_seed", pt, selection_seed, "set");
        setpointattrib(0, "catalog_schema", pt, 2, "set");
        setpointattrib(0, "module_role", pt, role, "set");
        setpointattrib(0, "module_variant", pt, variant, "set");
        setpointattrib(0, "surface_role", pt, surface, "set");
        setpointattrib(0, "facade_band", pt, face == 4 ? "roof" : floor == 0 ? "ground" : "middle", "set");
        setpointattrib(0, "is_building_entrance", pt, 0, "set");
        setpointattrib(0, "is_shop_entrance", pt, 0, "set");
        setpointattrib(0, "lod", pt, 0, "set");
        setpointattrib(0, "chunk_id", pt, 0, "set");
        setpointattrib(0, "pcg_kind", pt, "streetbuilding_detail_instance", "set");
        setpointattrib(0, "pcg_variant", pt, variant, "set");
    }
    return parts;
}

string catalog = chs("../../unity_instance_catalog");
if (chi("../../module_source") != 1 || detail(0, "catalog_schema", 0) != 2
    || !chi("../../generate_attachments")) return;
float density = clamp(ch("../../detail_density"), 0.0, 1.0);
if (density <= 0.0) return;
float width = ch("../../internal_width");
float depth = ch("../../internal_depth");
int wcells = int(rint(width / 2.0));
int dcells = int(rint(depth / 2.0));
int floors = max(2, chi("../../floor_count"));
int seed = chi("../../seed");
int entrance = wcells / 2;
int emitted = 0;

vector front_origin = set(-width * .5, 0, .22);
for (int cell = 0; cell < wcells && emitted < 64; cell++)
{
    if (cell == entrance) continue;
    int key = seed * 1009 + cell * 37;
    if (sbv6_has_role(catalog, "Awning") && rand(float(key) * .197 + 1.0) < density)
        emitted += sbv6_emit(catalog, "Awning", key + 3101, front_origin,
            set(1, 0, 0), set(0, 0, 1), (cell + .5) * 2, 3.05, 0, 0, "front", 0, cell);
    if (emitted < 64 && sbv6_has_role(catalog, "Sign")
        && rand(float(key) * .263 + 7.0) < density * .72)
        emitted += sbv6_emit(catalog, "Sign", key + 3203, front_origin,
            set(1, 0, 0), set(0, 0, 1), (cell + .5) * 2, 2.45, 0, 0, "front", 0, cell);
}

int rear_mode = chi("../../rear_mode");
if (emitted < 64 && rear_mode == 2 && floors >= 3 && sbv6_has_role(catalog, "FireEscape"))
    emitted += sbv6_emit(catalog, "FireEscape", seed * 1009 + 3307,
        set(width * .5, 0, -depth - .24), set(-1, 0, 0), set(0, 0, -1),
        width * .5, 4.0, -180, 3, "rear", 1, max(0, wcells / 2 - 1));

if (emitted < 64 && rear_mode != 0 && floors >= 2 && sbv6_has_role(catalog, "ACUnit"))
    emitted += sbv6_emit(catalog, "ACUnit", seed * 1009 + 3407,
        set(width * .5, 0, -depth - .20), set(-1, 0, 0), set(0, 0, -1),
        (max(0, wcells - 2) + .5) * 2, 4.7, -180, 3, "rear", 1, max(0, wcells - 2));

if (chi("../../side_mode") != 1 && sbv6_has_role(catalog, "ACUnit"))
{
    for (int face = 1; face <= 2 && emitted < 64; face++)
    {
        vector origin = face == 1 ? set(-width * .5 - .20, 0, -depth) : set(width * .5 + .20, 0, 0);
        vector right = face == 1 ? set(0, 0, 1) : set(0, 0, -1);
        vector outward = face == 1 ? set(-1, 0, 0) : set(1, 0, 0);
        float yaw = face == 1 ? 90.0 : -90.0;
        for (int floor = 1; floor < floors && emitted < 64; floor++)
        {
            for (int cell = 0; cell < dcells && emitted < 64; cell++)
            {
                int key = seed * 1009 + face * 503 + floor * 101 + cell * 37;
                if (rand(float(key) * .149 + 11.0) < density * .28)
                    emitted += sbv6_emit(catalog, "ACUnit", key + 3509, origin, right, outward,
                        (cell + .5) * 2, 4.65 + (floor - 1) * 3, yaw, face,
                        face == 1 ? "left" : "right", floor, cell);
            }
        }
    }
}

if (emitted < 64 && chi("../../generate_roof") && wcells >= 3 && dcells >= 3
    && sbv6_has_role(catalog, "RoofProp"))
{
    int xcell = clamp(int(floor(rand(float(seed) * .417 + 3.0) * max(1, wcells - 2))) + 1, 1, wcells - 2);
    int zcell = clamp(int(floor(rand(float(seed) * .613 + 5.0) * max(1, dcells - 2))) + 1, 1, dcells - 2);
    int cell = zcell * wcells + xcell;
    float roof_y = 4 + (floors - 1) * 3;
    emitted += sbv6_emit(catalog, "RoofProp", seed * 1009 + 4 * 503 + cell * 37,
        set(-width * .5, 0, -zcell * 2.0), set(1, 0, 0), set(0, 0, -1),
        (xcell + .5) * 2, roof_y + .25, 0, 4, "roof", floors, cell);
}

setdetailattrib(0, "output_role", "detail_instances", "set");
setdetailattrib(0, "streetbuilding_contract", "StreetBuilding.DirectInstances.6.0", "set");
setdetailattrib(0, "streetbuilding_revision", "STREETBUILDING_V6_MODULAR_DETAILS", "set");
setdetailattrib(0, "streetbuilding_detail_count", npoints(0), "set");
removeattrib(0, "point", "N");
'''


VALIDATE_SNIPPET = r'''// STREETBUILDING_V6_VALIDATE_DETAILS
int points = npoints(0);
if (points > 64) error("StreetBuilding V6 detail budget exceeded: %d", points);
for (int point = 0; point < points; point++)
{
    string path = point(0, "unity_instance", point);
    string role = point(0, "module_role", point);
    int face = point(0, "face_index", point);
    int floor = point(0, "floor_index", point);
    vector scale = point(0, "scale", point);
    vector4 orient = point(0, "orient", point);
    if (len(path) == 0) error("StreetBuilding V6 emitted an empty detail asset path");
    if (distance(scale, set(1, 1, 1)) > .0001) error("StreetBuilding V6 requires unit detail scale");
    if (abs(length(orient) - 1.0) > .001) error("StreetBuilding V6 emitted a non-unit detail orient");
    if ((role == "Awning" || role == "Sign") && (face != 0 || floor != 0))
        error("StreetBuilding V6 front detail placement failed for %s", role);
    if (role == "FireEscape" && face != 3)
        error("StreetBuilding V6 FireEscape must be on the rear face");
    if (role == "ACUnit" && (face < 1 || face > 3 || floor < 1))
        error("StreetBuilding V6 ACUnit must be on an upper side/rear face");
    if (role == "RoofProp" && face != 4)
        error("StreetBuilding V6 RoofProp must be on the roof");
}
setdetailattrib(0, "output_role", "detail_instances", "set");
setdetailattrib(0, "streetbuilding_contract", "StreetBuilding.DirectInstances.6.0", "set");
setdetailattrib(0, "streetbuilding_revision", "STREETBUILDING_V6_MODULAR_DETAILS", "set");
setdetailattrib(0, "streetbuilding_detail_count", points, "set");
'''


def _row(role: str, variant: str, path: str, width: int = 2, height: int = 3,
         weight: float = 1.0) -> str:
    return f"M|{role}|{variant}|0|Assets/Test/{path}.prefab|0|0|0|0|0|0|{width}|{height}|{weight}"


TEST_V2 = "\n".join([
    "SBV2|na_brick_mixeduse_01|2|4|3",
    _row("Entrance", "entrance_metal", "Entrance"),
    _row("GroundShop", "shop_metal", "Shop"),
    _row("GroundWall", "brick_ground", "Ground", height=4),
    _row("Cornice", "brick_center", "Cornice", height=1),
    _row("MiddleWindow", "trim", "Window"),
    _row("MiddleWindow", "curved_double", "WindowDouble", width=4),
    _row("MiddleBlank", "brick_plain", "Blank"),
    _row("SideWall", "brick_ground", "SideGround", height=4),
    _row("SideWall", "brick_upper", "SideUpper"),
    _row("RearWall", "brick_ground", "RearGround", height=4),
    _row("RearWall", "brick_upper", "RearUpper"),
    _row("FacadeColumn", "trim_ground", "ColumnGround"),
    _row("FacadeColumn", "brick_upper", "ColumnUpper"),
    _row("RoofSurface", "roof_2x2", "Roof", height=2),
    _row("Awning", "validation_canopy", "Awning", height=1),
    _row("Sign", "validation_board", "Sign", height=1),
    _row("FireEscape", "validation_two_floor", "FireEscape", width=4, height=6),
    _row("ACUnit", "wall_unit", "AC", height=1),
    _row("RoofProp", "ac_unit", "RoofProp", height=2),
])


def _ensure_node(core: hou.Node, type_name: str, name: str) -> tuple[hou.Node, bool]:
    node = core.node(name)
    if node is not None:
        if node.type().name() != type_name:
            raise RuntimeError(f"{node.path()} must be {type_name}, got {node.type().name()}")
        return node, False
    return core.createNode(type_name, name), True


def _set_input(node: hou.Node, index: int, source: hou.Node | None) -> bool:
    current = node.inputs()[index] if index < len(node.inputs()) else None
    if current == source:
        return False
    node.setInput(index, source)
    return True


def _set_snippet(node: hou.Node, snippet: str, marker: str, changed: list[str]) -> None:
    parm = node.parm("snippet")
    if parm is None:
        raise RuntimeError(f"{node.path()} has no snippet parameter")
    current = parm.eval()
    if current == snippet:
        return
    if marker in current and MARKER in current:
        raise RuntimeError(f"Unexpected divergent V6 snippet at {node.path()}")
    parm.set(snippet)
    changed.append(node.name() + ":snippet")


def _signature(geometry: hou.Geometry) -> list[tuple]:
    return sorted((
        point.stringAttribValue("name"),
        point.stringAttribValue("unity_instance"),
        tuple(round(value, 6) for value in point.position()),
        tuple(round(value, 6) for value in point.attribValue("orient")),
    ) for point in geometry.points())


def _validate(asset: hou.Node) -> dict:
    core = asset.node("StreetBuildingCore")
    lod0 = core.node("OUT_BUILDING_LOD0")
    details = core.node("OUT_DETAIL_INSTANCES")
    names = (
        "module_source", "unity_instance_catalog", "style_id", "internal_width",
        "internal_depth", "ground_floor_height", "typical_floor_height", "floor_count",
        "facade_rhythm", "detail_density", "generate_attachments", "rear_mode",
        "side_mode", "generate_roof", "generate_lods", "seed",
    )
    saved = {name: asset.parm(name).eval() for name in names}
    try:
        asset.parm("module_source").set(1)
        asset.parm("unity_instance_catalog").set(TEST_V2)
        asset.parm("style_id").set("na_brick_mixeduse_01")
        asset.parm("internal_width").set(12)
        asset.parm("internal_depth").set(10)
        asset.parm("ground_floor_height").set(4)
        asset.parm("typical_floor_height").set(3)
        asset.parm("floor_count").set(4)
        asset.parm("facade_rhythm").set(3)
        asset.parm("detail_density").set(1)
        asset.parm("generate_attachments").set(1)
        asset.parm("rear_mode").set(2)
        asset.parm("side_mode").set(2)
        asset.parm("generate_roof").set(1)
        asset.parm("generate_lods").set(0)
        asset.parm("seed").set(29)
        lod0.cook(force=True)
        details.cook(force=True)
        shell_signature = _signature(lod0.geometry())
        detail_signature = _signature(details.geometry())
        if not shell_signature or not detail_signature or len(detail_signature) > 64:
            raise RuntimeError("V6 shell/detail output budget failed")
        roles = {point.stringAttribValue("module_role") for point in details.geometry().points()}
        expected = {"Awning", "Sign", "FireEscape", "ACUnit", "RoofProp"}
        if roles != expected:
            raise RuntimeError(f"V6 detail role coverage failed: {sorted(roles)}")
        details.cook(force=True)
        if _signature(details.geometry()) != detail_signature:
            raise RuntimeError("V6 same-seed detail output is not deterministic")
        asset.parm("seed").set(47)
        details.cook(force=True)
        if _signature(details.geometry()) == detail_signature:
            raise RuntimeError("V6 different seed did not change details")
        asset.parm("seed").set(29)
        asset.parm("generate_attachments").set(0)
        details.cook(force=True)
        if details.geometry().intrinsicValue("pointcount") != 0:
            raise RuntimeError("V6 attachment toggle did not empty detail output")
        lod0.cook(force=True)
        if _signature(lod0.geometry()) != shell_signature:
            raise RuntimeError("V6 attachment toggle changed LOD0")
        asset.parm("generate_attachments").set(1)
        asset.parm("detail_density").set(0)
        details.cook(force=True)
        if details.geometry().intrinsicValue("pointcount") != 0:
            raise RuntimeError("V6 zero density did not empty detail output")
        lod0.cook(force=True)
        if _signature(lod0.geometry()) != shell_signature:
            raise RuntimeError("V6 zero density changed LOD0")
        diagnostics = []
        for node in (lod0, details, core.node("DETAIL_INSTANCE_POINTS"),
                     core.node("VALIDATE_DIRECT_DETAIL_INSTANCES")):
            diagnostics.extend(node.errors())
            diagnostics.extend(node.warnings())
        if diagnostics:
            raise RuntimeError("V6 cook diagnostics: " + "\n".join(diagnostics))
        return {
            "lod0_points": len(shell_signature),
            "detail_points": len(detail_signature),
            "detail_roles": sorted(roles),
            "deterministic": True,
            "max_details": 64,
        }
    finally:
        for name, value in saved.items():
            asset.parm(name).set(value)


def apply_loaded(asset: hou.Node, save: bool) -> dict:
    if asset is None or asset.type().name() != "pcgbike::StreetBuilding::1.0":
        raise RuntimeError("Expected /obj/StreetBuilding_DEV pcgbike::StreetBuilding::1.0")
    definition = asset.type().definition()
    if definition is None:
        raise RuntimeError("StreetBuilding has no definition")
    comment = definition.comment() or ""
    if PREVIOUS_MARKER not in comment and MARKER not in comment:
        raise RuntimeError("StreetBuilding V6 requires the exact persisted V5 marker")
    asset.allowEditingOfContents()
    core = asset.node("StreetBuildingCore")
    if core is None:
        raise RuntimeError("StreetBuildingCore is missing")
    changed: list[str] = []
    parser = core.node("PARSE_UNITY_INSTANCE_CATALOG")
    side_rear = core.node("BUILD_DIRECT_SIDE_REAR_INSTANCES")
    roof = core.node("BUILD_DIRECT_ROOF_INSTANCES")
    detail = core.node("DETAIL_INSTANCE_POINTS")
    output = core.node("OUT_DETAIL_INSTANCES")
    empty = core.node("EMPTY_GEOMETRY")
    if None in (parser, side_rear, roof, detail, output, empty):
        raise RuntimeError("StreetBuilding V5 detail prerequisites are missing")

    side_parm = side_rear.parm("snippet")
    side_snippet = side_parm.eval()
    if SIDE_REAR_V5_MARKER in side_snippet:
        required = (
            SIDE_REAR_DENSITY_V5,
            '< density * .6 ? "MiddleWindow" : "SideWall"',
            "< density * .65",
        )
        if not all(token in side_snippet for token in required):
            raise RuntimeError("Unexpected V5 side/rear density implementation")
        side_snippet = side_snippet.replace(SIDE_REAR_V5_MARKER, SIDE_REAR_V6_MARKER)
        side_snippet = side_snippet.replace(SIDE_REAR_DENSITY_V5, SIDE_REAR_DENSITY_V6)
        side_snippet = side_snippet.replace("< density * .6", "< shell_variation * .6")
        side_snippet = side_snippet.replace("< density * .65", "< shell_variation * .65")
        side_parm.set(side_snippet)
        changed.append(side_rear.name() + ":snippet")
    elif SIDE_REAR_V6_MARKER not in side_snippet or SIDE_REAR_DENSITY_V6 not in side_snippet:
        raise RuntimeError("Unexpected side/rear shell implementation for V6")

    roof_parm = roof.parm("snippet")
    roof_snippet = roof_parm.eval()
    if OLD_ROOF_ATTACHMENT in roof_snippet:
        roof_parm.set(roof_snippet.replace(OLD_ROOF_ATTACHMENT, "")
                      .replace("STREETBUILDING_V5_ROOF", "STREETBUILDING_V6_ROOF_SHELL"))
        changed.append(roof.name() + ":snippet")
    elif "STREETBUILDING_V6_ROOF_SHELL" not in roof_snippet:
        raise RuntimeError("V6 roof precondition did not match the V5 attachment block")

    _set_snippet(detail, DETAIL_SNIPPET, "STREETBUILDING_V6_DETAIL_INSTANCE_POINTS", changed)
    if _set_input(detail, 0, parser): changed.append(detail.name() + ":input0")
    if len(detail.inputs()) > 1 and _set_input(detail, 1, None): changed.append(detail.name() + ":input1")

    validator, created = _ensure_node(core, "attribwrangle", "VALIDATE_DIRECT_DETAIL_INSTANCES")
    if created: changed.append(validator.name())
    _set_snippet(validator, VALIDATE_SNIPPET, "STREETBUILDING_V6_VALIDATE_DETAILS", changed)
    if _set_input(validator, 0, detail): changed.append(validator.name() + ":input0")

    switch, created = _ensure_node(core, "switch", "DETAIL_MODULE_SOURCE_SWITCH")
    if created: changed.append(switch.name())
    if _set_input(switch, 0, empty): changed.append(switch.name() + ":input0")
    if _set_input(switch, 1, validator): changed.append(switch.name() + ":input1")
    switch.parm("input").setExpression('ch("../../module_source")', hou.exprLanguage.Hscript)
    if _set_input(output, 0, switch): changed.append(output.name() + ":input0")

    for legacy_name in ("COPY_GRAYBOX_DETAILS_TO_POINTS", "GRAYBOX_AWNING_MODULE", "DETAIL_INSTANCE_CONTRACT"):
        legacy = core.node(legacy_name)
        if legacy is not None:
            legacy.destroy()
            changed.append(legacy_name + ":removed")

    box = core.findNetworkBox("70_UNITY_CONTRACT")
    if box is not None:
        for node in (detail, validator, switch):
            box.addNode(node)
    detail.setPosition(parser.position() + hou.Vector2(7, -2))
    validator.setPosition(detail.position() + hou.Vector2(0, -2))
    switch.setPosition((validator.position() + output.position()) * .5)
    detail.setComment("V6 / 按建筑面、楼层、Cell 与 Seed 生成独立模块化细节点。")
    validator.setComment("V6 / 校验资产路径、朝向、挂接面与每栋 64 点预算。")
    switch.setComment("V6 / 仅 Unity Catalog 模式输出细节；Internal Proxy 保持空输出。")
    for node in (detail, validator, switch):
        node.setGenericFlag(hou.nodeFlag.DisplayComment, True)

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
        "revision": REVISION,
        "contract": CONTRACT_VERSION,
        "nodes": changed,
        "validation": validation,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--project-root", required=True, type=Path)
    parser.add_argument("--save", choices=("true", "false"), default="false")
    parser.add_argument("--update-existing", choices=("true", "false"), default="true",
                        help="Regression-gate compatibility; V6 always updates the existing definition.")
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
        raise RuntimeError("V6 save=False modified persisted HDA/HIP bytes")
    result["files"] = {"hda": after[0], "hip": after[1]}
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
