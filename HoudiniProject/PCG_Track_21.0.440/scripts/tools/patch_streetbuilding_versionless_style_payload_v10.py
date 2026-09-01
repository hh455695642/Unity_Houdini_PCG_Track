"""Hard-cut StreetBuilding to one versionless StyleConfig payload.

The patch is incremental against the exact persisted V9 HDA.  It never replays
an older builder, verifies every edited VEX snippet by SHA-256, supports
save=False, and restores the locked definition on dry-run failure.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

import hou


ASSET_PATH = "/obj/StreetBuilding_DEV"
ASSET_TYPE = "pcgbike::StreetBuilding::1.0"
PREVIOUS_MARKER = "STREETBUILDING_V9_STYLECONFIG_SBV4_RULES"
MARKER = "STREETBUILDING_V10_VERSIONLESS_STYLE_PAYLOAD"
CONTRACT = "StreetBuilding.VersionlessStyle.10.0"
REL_HDA = "Assets/PCG/HDA/City/StreetBuilding.hda"
REL_HIP = "HoudiniProject/PCG_Track_21.0.440/PCG_Bike_StreetBuilding.hip"

EXPECTED_SNIPPETS = {
    "INTERNAL_TEST_PARCEL": "1dff9aeca901f2ab8c64e6097d65deba640de497d63099d2b15c6d6cca14589f",
    "CANONICALIZE_PARCELS": "8e84a24028a3db8e5e446945fdb9ebe53fa02eb7f262d83b25464216890e903d",
    "RESOLVE_FRONTAGES": "d7b9ab1aa8c3cd2798ce4e1993ffc7aada16081085cf0cf272342f32cdde6d12",
    "VALIDATE_MODULE_LIBRARY": "4a146e5eef9a2c27c3424ac8c5586106de31df62eef70d84ee6c6dd2bb568ba5",
    "PARSE_UNITY_INSTANCE_CATALOG": "d7f8107f5150db79d7b1985feec615d201db56bd3e2bd919c8965af15bb69e1c",
    "DIRECT_UNITY_INSTANCE_FACADE": "d64087c36ceea1544446d02343e3d5fb048f61c9a9c0ecec699c76e9ac4c1eee",
    "BUILD_DIRECT_SIDE_REAR_INSTANCES": "65a72c1dadeba1557914156594fa54a7c93cc6d45a7038832fd80069bfe66692",
    "BUILD_DIRECT_ROOF_INSTANCES": "089a6815b94e2cfef256d2380a60d4a3485ba1dd9c0c6f98cd076d6152ae6486",
    "BUILD_DIRECT_ROOF_EDGE_INSTANCES": "9ef976a30bd7a8406a7f0c5abc62ced1212f0a010f3d994443d9906b6dcabcb1",
    "SELECT_FACADE_MODULES": "f7b9075396d1617d49399e9ed08a17ed78c9c8d3f8f0617a86b4094c343cb31f",
    "SELECT_ATTACHMENT_MODULES": "52dde21accd7b1a6f65c47f1cd8b9a3ca4d940d6b48a1feb7b7fa96eef2b66e3",
    "DETAIL_INSTANCE_POINTS": "483473eb754ed931498697a6e69389624a5425509df8af4aa480ee37a6ef7b6a",
    "VALIDATE_DIRECT_BUILDING_INSTANCES": "493762594d1d659cf9e40e8ee5ad05354c6b8d1d11548c461b40d5621d44d5ca",
    "VALIDATE_DIRECT_DETAIL_INSTANCES": "a000499e9b145019abe665c28c1ca269426c954753bf153006cecb322367f767",
    "BUILD_LOD0": "82aa01a543388385cef654e1fc12fd0dc80b20a0670a44db6a3dd48bea2aebd3",
    "BUILD_LOD1": "dacab41d29ef52decc60aa7b2282a50ce6fa88211ad5be48dd02930da763d630",
    "BUILD_LOD2": "abfa85327cd52676579623d31f98b3128ee17c8dd0c3216e9e2f0293839aba0a",
    "BUILD_METADATA": "fdc5626db52e66043b78252786b8c319cb1da250c9f85a04a4ced24102b4882f",
}

FORBIDDEN_ACTIVE_TOKENS = (
    "SBV2", "SBV3", "SBV4", "catalog_schema", "module_family", "style_id",
)

PARSER = r'''// STREETBUILDING_V10_VERSIONLESS_STYLE_PARSER
string sb_role_name(int role)
{
    string names[] = array("GroundShop","GroundShopDoor","GroundWall","Entrance",
        "MiddleWindow","MiddleBlank","CornerConvex","CornerConcave","Cornice",
        "Parapet","SideWall","RearWall","FacadeColumn","FloorBand","Awning",
        "Sign","FireEscape","ACUnit","RoofProp","RoofSurface","ParapetCorner",
        "ParapetConcaveCorner");
    return role >= 0 && role < len(names) ? names[role] : "";
}

string payload = chs("../../unity_instance_catalog");
if (chi("../../module_source") != 1)
{
    setdetailattrib(0, "catalog_module_rows", 0, "set");
    setdetailattrib(0, "catalog_payload", "", "set");
    return;
}
if (len(strip(payload)) == 0)
    error("StreetBuilding Unity Asset Instances requires a compiled StyleConfig payload");

string rows[] = split(payload, "\n");
string header[] = len(rows) > 0 ? split(strip(rows[0]), "|") : array();
if (len(header) != 4 || header[0] != "STYLE")
    error("StreetBuilding StyleConfig payload header must be STYLE|CellWidth|GroundHeight|TypicalHeight");

float cell_width = atof(header[1]);
float ground_height = atof(header[2]);
float typical_height = atof(header[3]);
if (cell_width <= 0 || ground_height <= 0 || typical_height <= 0)
    error("StreetBuilding StyleConfig dimensions must be positive");

string normalized = sprintf("STYLE|%g|%g|%g", cell_width, ground_height, typical_height);
int module_rows = 0;
foreach (string row; rows)
{
    string f[] = split(strip(row), "|");
    if (len(f) == 0 || f[0] != "M") continue;
    if (len(f) != 18)
        error("StreetBuilding StyleConfig contains an invalid module row");
    string role = sb_role_name(atoi(f[2]));
    float width = max(1, atoi(f[5])) * cell_width;
    float height = atof(f[8]) > 0 ? atof(f[8]) : max(.001, atof(f[13]));
    float weight = atof(f[9]);
    if (len(role) == 0 || len(f[3]) == 0 || len(f[4]) == 0 || weight <= 0)
        error("StreetBuilding StyleConfig module identity/weight is invalid");
    normalized += sprintf("\nM|%s|%s|0|%s|0|0|0|0|0|0|%g|%g|%g",
        role, f[3], f[4], width, height, weight);
    module_rows++;
}
if (module_rows == 0) error("StreetBuilding StyleConfig has no enabled module rows");
setdetailattrib(0, "catalog_module_rows", module_rows, "set");
setdetailattrib(0, "style_cell_width", cell_width, "set");
setdetailattrib(0, "style_ground_height", ground_height, "set");
setdetailattrib(0, "style_typical_height", typical_height, "set");
setdetailattrib(0, "catalog_payload", normalized, "set");
'''

HELPERS = r'''// STREETBUILDING_V10_VERSIONLESS_CATALOG_HELPERS
int sb_has_variant(string catalog; string role; string variant)
{
    foreach (string row; split(catalog, "\n"))
    {
        string f[] = split(strip(row), "|");
        if (len(f) == 14 && f[0] == "M" && f[1] == role && f[2] == variant)
            return 1;
    }
    return 0;
}

int sb_has_role(string catalog; string role)
{
    foreach (string row; split(catalog, "\n"))
    {
        string f[] = split(strip(row), "|");
        if (len(f) == 14 && f[0] == "M" && f[1] == role) return 1;
    }
    return 0;
}

string sb_choose_variant(string catalog; string role; int selection_seed; int max_span;
    export int selected_span)
{
    float total = 0.0;
    foreach (string row; split(catalog, "\n"))
    {
        string f[] = split(strip(row), "|");
        if (len(f) != 14 || f[0] != "M" || f[1] != role || atoi(f[3]) != 0) continue;
        int span = int(rint(atof(f[11]) / 2.0));
        if (span < 1 || span > max_span) continue;
        total += max(0.0, atof(f[13]));
    }
    if (total <= 0.0) return "";
    float target = rand(float(selection_seed) * 0.731 + 19.17) * total;
    float cursor = 0.0;
    foreach (string row; split(catalog, "\n"))
    {
        string f[] = split(strip(row), "|");
        if (len(f) != 14 || f[0] != "M" || f[1] != role || atoi(f[3]) != 0) continue;
        int span = int(rint(atof(f[11]) / 2.0));
        if (span < 1 || span > max_span) continue;
        cursor += max(0.0, atof(f[13]));
        if (target <= cursor)
        {
            selected_span = span;
            return f[2];
        }
    }
    return "";
}

int sb_part_count(string catalog; string role; string variant)
{
    int result = 0;
    foreach (string row; split(catalog, "\n"))
    {
        string f[] = split(strip(row), "|");
        if (len(f) == 14 && f[0] == "M" && f[1] == role && f[2] == variant)
            result = max(result, atoi(f[3]) + 1);
    }
    return result;
}

string sb_catalog_part(string catalog; string role; string variant; int part;
    export vector offset; export vector rotation; export int span)
{
    offset = 0; rotation = 0; span = 1;
    foreach (string row; split(catalog, "\n"))
    {
        string f[] = split(strip(row), "|");
        if (len(f) == 14 && f[0] == "M" && f[1] == role
            && f[2] == variant && atoi(f[3]) == part)
        {
            offset = set(atof(f[5]), atof(f[6]), atof(f[7]));
            rotation = set(atof(f[8]), atof(f[9]), atof(f[10]));
            span = int(rint(atof(f[11]) / 2.0));
            return f[4];
        }
    }
    return "";
}

int sb_add_instance(string catalog; string role; string variant; int part;
    vector origin; vector face_right; vector outward; float local_u; float base_y;
    float houdini_yaw; int face_index; string surface; int floor_index; int cell_index;
    int selection_seed; int building_entrance; int shop_entrance)
{
    vector offset, rotation; int span;
    string path = sb_catalog_part(catalog, role, variant, part, offset, rotation, span);
    if (len(path) == 0) error("StreetBuilding catalog missing %s/%s part %d", role, variant, part);
    if (length2(rotation) > 1e-10)
        error("StreetBuilding catalog rotations must be authored inside a Prefab");
    vector unity_position = origin + face_right * (local_u + offset.x)
        + set(0, base_y + offset.y, 0) + outward * offset.z;
    vector houdini_position = set(-unity_position.x, unity_position.y, unity_position.z);
    int pt = addpoint(0, houdini_position);
    vector4 orient = quaternion(radians(houdini_yaw), set(0, 1, 0));
    setpointattrib(0, "orient", pt, orient, "set");
    setpointattrib(0, "scale", pt, set(1, 1, 1), "set");
    setpointattrib(0, "unity_instance", pt, path, "set");
    string face_token = face_index == 0 ? "FR" : face_index == 1 ? "LT" :
        face_index == 2 ? "RT" : face_index == 3 ? "BK" : "RF";
    string prefix = sprintf("SB_B0000_%s_F%02d_C%02d_%s_%s_P%d",
        face_token, floor_index, cell_index, role, variant, part);
    setpointattrib(0, "instance_prefix", pt, prefix, "set");
    setpointattrib(0, "name", pt, prefix, "set");
    setpointattrib(0, "building_id", pt, 0, "set");
    setpointattrib(0, "face_index", pt, face_index, "set");
    setpointattrib(0, "floor_index", pt, floor_index, "set");
    setpointattrib(0, "cell_index", pt, cell_index, "set");
    setpointattrib(0, "module_span", pt, span, "set");
    setpointattrib(0, "selection_seed", pt, selection_seed, "set");
    setpointattrib(0, "module_role", pt, role, "set");
    setpointattrib(0, "module_variant", pt, variant, "set");
    setpointattrib(0, "surface_role", pt, surface, "set");
    setpointattrib(0, "facade_band", pt, floor_index == 0 ? "ground" : surface == "roof" ? "roof" : "middle", "set");
    setpointattrib(0, "is_building_entrance", pt, building_entrance, "set");
    setpointattrib(0, "is_shop_entrance", pt, shop_entrance, "set");
    setpointattrib(0, "lod", pt, 0, "set");
    setpointattrib(0, "chunk_id", pt, 0, "set");
    setpointattrib(0, "pcg_kind", pt, "streetbuilding_module_instance", "set");
    setpointattrib(0, "pcg_variant", pt, variant, "set");
    return pt;
}

void sb_emit(string catalog; string role; string variant; vector origin; vector right;
    vector outward; float local_u; float y; float h_yaw; int face; string surface;
    int floor; int cell; int selection_seed; int entrance)
{
    int parts = sb_part_count(catalog, role, variant);
    if (parts <= 0) error("StreetBuilding has no parts for %s/%s", role, variant);
    for (int part = 0; part < parts; part++)
        sb_add_instance(catalog, role, variant, part, origin, right, outward, local_u, y,
            h_yaw, face, surface, floor, cell, selection_seed, entrance && part == 0, 0);
}
'''


def _sha(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _replace_once(text: str, old: str, new: str, label: str) -> str:
    count = text.count(old)
    if count != 1:
        raise RuntimeError(f"V10 precondition failed for {label}: expected once, found {count}")
    return text.replace(old, new, 1)


def _replace_all_checked(text: str, old: str, new: str, minimum: int, label: str) -> str:
    count = text.count(old)
    if count < minimum:
        raise RuntimeError(f"V10 precondition failed for {label}: expected >= {minimum}, found {count}")
    return text.replace(old, new)


def _filter_attributes(text: str) -> str:
    return text.replace(
        '"face_index","floor_index","cell_index","module_span","selection_seed","catalog_schema",\n'
        '    "module_family","module_role","module_variant","surface_role","facade_band",',
        '"face_index","floor_index","cell_index","module_span","selection_seed",\n'
        '    "module_role","module_variant","surface_role","facade_band",',
    )


def _consumer(text: str, marker: str) -> str:
    if text.count(marker) != 1:
        raise RuntimeError(f"V10 consumer marker mismatch: {marker}")
    node_helpers = ""
    if marker == "// STREETBUILDING_V8_ROOF_EDGE_TOPOLOGY":
        helper_start = "void sbv7_emit_parapet_run"
        if text.count(helper_start) != 1:
            raise RuntimeError("V10 roof-edge helper precondition failed")
        node_helpers = text.split(helper_start, 1)[1].split(marker, 1)[0]
        node_helpers = helper_start + node_helpers
    suffix = marker + text.split(marker, 1)[1]
    result = HELPERS + "\n" + node_helpers + "\n" + suffix
    result = result.replace("if (sb_schema(catalog) < 2 || !chi(\"../../generate_roof\"))",
                            "if (len(strip(catalog)) == 0 || !chi(\"../../generate_roof\"))")
    result = result.replace("if (sb_schema(catalog)<2 || !chi(\"../../generate_roof\"))",
                            "if (len(strip(catalog))==0 || !chi(\"../../generate_roof\"))")
    return _filter_attributes(result)


def _selector(text: str) -> str:
    marker = "// STREETBUILDING_V9_SELECT_FACADE_MODULES"
    result = _consumer(text, marker)
    result = _replace_once(
        result,
        'string catalog=detail(1,"catalog_payload",0); if (sb_schema(catalog)<1) return;\n'
        'int catalog_schema=sb_schema(catalog);',
        'string catalog=detail(1,"catalog_payload",0); if (len(strip(catalog))==0) return;',
        "selector payload guard",
    )
    result = _replace_once(
        result,
        '''    if (catalog_schema==1)
    {
        if (target!=0) continue;
        role=floor==0?(semantic=="entrance"?"Entrance":"GroundShop"):"MiddleWindow";
        variant=role=="Entrance"?"entrance_metal":role=="GroundShop"?
            ((cell%2)==0?"shop_trim":"shop_metal"):((cell/2)%2==0?"trim":"trim_single");
    }
    else if (target<=1)''',
        '''    if (target<=1)''',
        "selector legacy branch",
    )
    result = _replace_once(
        result,
        '''    if (catalog_schema>=2)
        variant=(target>=2)?sbv9_choose_height(catalog,role,key,floor==0?ground_h:typical_h):sb_choose_variant(catalog,role,key,available_span,span);''',
        '''    variant=(target>=2)?sbv9_choose_height(catalog,role,key,floor==0?ground_h:typical_h):sb_choose_variant(catalog,role,key,available_span,span);''',
        "selector version branch",
    )
    result = _replace_once(
        result,
        'int cs; string cornice=catalog_schema==1?"brick_center":sb_choose_variant(catalog,"Cornice",key+7,1,cs);',
        'int cs; string cornice=sb_choose_variant(catalog,"Cornice",key+7,1,cs);',
        "selector cornice",
    )
    result = _replace_once(
        result,
        '''string column=catalog_schema==1?(floor==0?"trim_ground":"brick_upper"):
            sbv9_choose_height(catalog,"FacadeColumn",key+17,floor==0?ground_h:typical_h);''',
        '''string column=sbv9_choose_height(catalog,"FacadeColumn",key+17,
            floor==0?ground_h:typical_h);''',
        "selector column",
    )
    return _update_contract(result)


def _detail(text: str) -> str:
    result = _replace_once(
        text,
        '''        int catalog_schema = detail(0,"catalog_schema",0); string module_family = detail(0,"module_family",0);

        setpointattrib(0, "catalog_schema", pt, catalog_schema, "set");
        setpointattrib(0, "module_family", pt, module_family, "set");
''',
        "",
        "detail metadata",
    )
    result = _replace_once(
        result,
        '''if (chi("../../module_source")!=1 || detail(0,"catalog_schema",0)<2
    || !detail(1,"effective_attachments",0)) return;''',
        '''if (chi("../../module_source")!=1 || len(strip(catalog))==0
    || !detail(1,"effective_attachments",0)) return;''',
        "detail payload guard",
    )
    return _update_contract(result)


def _building_validator(text: str) -> str:
    result = _replace_once(text, 'int schema = detail(0, "catalog_schema", 0);\n', "",
                           "building schema declaration")
    result = _replace_once(result, "if (schema == 2 && entrance_count != 1)",
                           "if (entrance_count != 1)", "entrance validation")
    result = _replace_once(result, 'if (schema >= 2 && chi("../../massing_shape") == 1)',
                           'if (chi("../../massing_shape") == 1)', "L-shape validation")
    result = _replace_once(result,
                           'setdetailattrib(0, "streetbuilding_front_only", schema == 1, "set");',
                           'setdetailattrib(0, "streetbuilding_front_only", 0, "set");',
                           "front-only metadata")
    return _update_contract(result)


def _update_contract(text: str) -> str:
    result = text.replace("StreetBuilding.StyleConfig.9.0", CONTRACT)
    result = result.replace("StreetBuilding.DirectInstances.8.0", CONTRACT)
    result = result.replace(PREVIOUS_MARKER, MARKER)
    result = result.replace("STREETBUILDING_V8_CORNER_AC_ATTACHMENT", MARKER)
    return result


def _module_library(text: str) -> str:
    derive = r'''    string style = "";
    for (int primitive = 0; primitive < nprimitives(0) && len(style) == 0; primitive++)
    {
        string raw = hasprimattrib(0, "unity_input_mesh_name")
            ? string(prim(0, "unity_input_mesh_name", primitive)) :
            (hasprimattrib(0, "_unity_input_mesh_name_")
                ? string(prim(0, "_unity_input_mesh_name_", primitive)) :
                (hasprimattrib(0, "name") ? string(prim(0, "name", primitive)) : ""));
        string tokens[] = re_split("__", raw);
        if ((len(tokens) == 6 && tokens[0] == "SBMSTYLE")
            || (len(tokens) == 9 && tokens[0] == "SBM"))
            style = tokens[1];
    }
    if (len(style) == 0)
        error("StreetBuilding external module library has no self-contained library key");
    setdetailattrib(0, "external_library_key", style, "set");'''
    return _replace_once(text, '    string style = chs("../../style_id");', derive,
                         "external library key")


def _styleless_lod(text: str) -> str:
    return _replace_once(
        text,
        '        string style=string(prim(1,"style_id",source));',
        '        string style=string(detail(2,"external_library_key",0));',
        "LOD external library key",
    )


def _parameter_group(asset: hou.Node) -> hou.ParmTemplateGroup:
    group = asset.parmTemplateGroup()
    catalog = group.find("unity_instance_catalog")
    rules = group.find("unity_generation_rules")
    if catalog is None or rules is None:
        raise RuntimeError("V10 requires the current Unity payload bridge")
    # Remove the complete legacy bridge folder when the payload fields are
    # nested.  Its internal name is unstable (for example sbv9_bridge2), so the
    # actual index path is the only reliable locator.
    catalog_indices = group.findIndices("unity_instance_catalog")
    if len(catalog_indices) > 1:
        group.remove((catalog_indices[0],))
    else:
        group.remove(catalog_indices)
        rules_indices = group.findIndices("unity_generation_rules")
        if rules_indices:
            group.remove(rules_indices)
    for name in ("style_id", "unity_bridge_revision", "unity_bridge_end_marker"):
        indices = group.findIndices(name)
        if indices:
            group.remove(indices)
    catalog.hide(False)
    rules.hide(False)
    group.append(catalog)
    group.append(rules)
    end_marker = hou.StringParmTemplate(
        "unity_bridge_end_marker", "Unity Bridge End Marker", 1, ("END",),
        string_type=hou.stringParmType.Regular)
    end_marker.hide(False)
    group.append(end_marker)
    return group


def _test_payload() -> str:
    rows = ["STYLE|2|4|3"]

    def add(role: int, variant: str, path: str, width: int = 1,
            height: float = 3, weight: float = 1, facades: int = 15,
            floors: int = 7) -> None:
        rows.append(
            f"M|0|{role}|{variant}|{path}|{width}|1|2|{height}|{weight}|"
            f"{facades}|{floors}|2|{height}|.2|-1|0|-.1")

    for role, variant, height in (
        (3, "entrance", 4), (0, "shop", 4), (1, "shop_door", 4),
        (2, "ground", 4), (4, "window", 3), (5, "blank", 3),
        (6, "convex", 3), (7, "concave", 3), (8, "cornice", 1),
        (9, "parapet", .6), (10, "side", 3), (11, "rear", 3),
        (12, "column", 3), (13, "band", 1), (14, "awning", 1),
        (15, "sign", 1), (16, "escape", 6), (17, "ac", 1),
        (18, "roof_prop", 2), (19, "roof", 2), (20, "corner", .6),
        (21, "concave_corner", .6),
    ):
        add(role, variant, f"Assets/Test/{variant}.prefab", height=height)
    for role, variant in ((6, "convex_ground"), (7, "concave_ground"),
                          (10, "side_ground"), (11, "rear_ground"),
                          (12, "column_ground")):
        add(role, variant, f"Assets/Test/{variant}.prefab", height=4)
    return "\n".join(rows)


def _validate(asset: hou.Node, interface_group: hou.ParmTemplateGroup | None = None,
              require_live_interface: bool = True) -> dict:
    group = interface_group or asset.parmTemplateGroup()
    for name in ("style_id", "unity_bridge_revision"):
        if group.find(name) is not None or (require_live_interface and asset.parm(name) is not None):
            raise RuntimeError(f"V10 removed bridge parameter is still present: {name}")
    for name in ("unity_instance_catalog", "unity_generation_rules", "unity_bridge_end_marker"):
        template = group.find(name)
        if (template is None or template.isHidden()
                or (require_live_interface and asset.parm(name) is None)):
            raise RuntimeError(f"V10 Unity bridge parameter is unavailable: {name}")
    if group.find("unity_bridge_end_marker").isHidden():
        raise RuntimeError("V10 Unity bridge end marker must remain HAPI-visible")

    core = asset.node("StreetBuildingCore")
    for name in EXPECTED_SNIPPETS:
        snippet = core.node(name).parm("snippet").eval()
        for token in FORBIDDEN_ACTIVE_TOKENS:
            if token in snippet:
                raise RuntimeError(f"V10 forbidden token {token} remains in {name}")

    values = {}
    for name in ("module_source", "unity_instance_catalog", "massing_shape",
                 "floor_count", "generate_roof", "generate_attachments"):
        parm = asset.parm(name)
        if parm is not None:
            values[name] = parm.eval()
    try:
        asset.parm("module_source").set(1)
        asset.parm("unity_instance_catalog").set(_test_payload())
        asset.parm("massing_shape").set(0)
        asset.parm("floor_count").set(4)
        asset.parm("generate_roof").set(1)
        asset.parm("generate_attachments").set(1)
        counts = {}
        for name in ("PARSE_UNITY_INSTANCE_CATALOG", "OUT_BUILDING_LOD0",
                     "OUT_DETAIL_INSTANCES", "OUT_BUILDING_METADATA"):
            node = core.node(name)
            try:
                node.cook(force=True)
            except hou.OperationFailed as exc:
                raise RuntimeError(
                    f"V10 {name} cook failed: {node.errors()} {node.warnings()}") from exc
            if node.errors() or node.warnings():
                raise RuntimeError(f"V10 {name} diagnostics: {node.errors()} {node.warnings()}")
            geometry = node.geometry()
            counts[name] = geometry.intrinsicValue("pointcount") if geometry is not None else 0
        parser = core.node("PARSE_UNITY_INSTANCE_CATALOG").geometry()
        if parser.findGlobalAttrib("catalog_module_rows") is None:
            raise RuntimeError("V10 parser did not publish module row count")
        if parser.findGlobalAttrib("catalog_schema") is not None or parser.findGlobalAttrib("module_family") is not None:
            raise RuntimeError("V10 parser emitted removed metadata")
        if counts["OUT_BUILDING_LOD0"] <= 0:
            raise RuntimeError("V10 emitted no building instances")
        return {"counts": counts, "versionless_payload": True, "bridge_visible": True}
    finally:
        for name, value in values.items():
            parm = asset.parm(name)
            if parm is not None:
                parm.set(value)


def _validate_fresh_definition() -> dict:
    fresh = hou.node("/obj").createNode(ASSET_TYPE, "VERIFY_V10_PAYLOAD_BRIDGE")
    try:
        return _validate(fresh)
    finally:
        fresh.destroy()


def _transformed(originals: dict[str, str]) -> dict[str, str]:
    result = dict(originals)
    result["INTERNAL_TEST_PARCEL"] = _replace_once(
        originals["INTERNAL_TEST_PARCEL"],
        'setprimattrib(0, "style_id", prim, chs("../../style_id"), "set");\n',
        "", "internal parcel identity")
    result["CANONICALIZE_PARCELS"] = _replace_once(
        originals["CANONICALIZE_PARCELS"],
        '''    if (hasprimattrib(1, "style_id"))
        setprimattrib(0, "style_id", target_prim,
            string(prim(1, "style_id", source_prim)), "set");
''', "", "parcel identity transport")
    result["RESOLVE_FRONTAGES"] = _replace_once(
        originals["RESOLVE_FRONTAGES"],
        '''    string style_id = hasprimattrib(0, "style_id")
        ? string(prim(0, "style_id", primitive)) : chs("../../style_id");
    if (len(style_id) == 0)
        style_id = chs("../../style_id");

''', "", "frontage identity resolve")
    result["RESOLVE_FRONTAGES"] = _replace_once(
        result["RESOLVE_FRONTAGES"],
        '    setprimattrib(0, "style_id", primitive, style_id, "set");\n',
        "", "frontage identity output")
    result["VALIDATE_MODULE_LIBRARY"] = _module_library(originals["VALIDATE_MODULE_LIBRARY"])
    result["PARSE_UNITY_INSTANCE_CATALOG"] = PARSER
    result["DIRECT_UNITY_INSTANCE_FACADE"] = _filter_attributes(originals["DIRECT_UNITY_INSTANCE_FACADE"])
    result["BUILD_DIRECT_SIDE_REAR_INSTANCES"] = _filter_attributes(originals["BUILD_DIRECT_SIDE_REAR_INSTANCES"])
    result["BUILD_DIRECT_ROOF_INSTANCES"] = _consumer(
        originals["BUILD_DIRECT_ROOF_INSTANCES"], "// STREETBUILDING_V7_ROOF_L_FOOTPRINT")
    result["BUILD_DIRECT_ROOF_EDGE_INSTANCES"] = _consumer(
        originals["BUILD_DIRECT_ROOF_EDGE_INSTANCES"], "// STREETBUILDING_V8_ROOF_EDGE_TOPOLOGY")
    result["SELECT_FACADE_MODULES"] = _selector(originals["SELECT_FACADE_MODULES"])
    result["DETAIL_INSTANCE_POINTS"] = _detail(originals["DETAIL_INSTANCE_POINTS"])
    result["VALIDATE_DIRECT_BUILDING_INSTANCES"] = _building_validator(
        originals["VALIDATE_DIRECT_BUILDING_INSTANCES"])
    result["VALIDATE_DIRECT_DETAIL_INSTANCES"] = _update_contract(
        originals["VALIDATE_DIRECT_DETAIL_INSTANCES"])
    for name in ("BUILD_LOD0", "BUILD_LOD1", "BUILD_LOD2"):
        result[name] = _styleless_lod(originals[name])
    result["BUILD_METADATA"] = _replace_once(
        originals["BUILD_METADATA"],
        '''    setpointattrib(0, "style_id", point_number,
        string(prim(1, "style_id", primitive)), "set");
''', "", "metadata identity")
    result["BUILD_METADATA"] = _update_contract(result["BUILD_METADATA"])
    return result


def apply_loaded(asset: hou.Node, save: bool = False) -> dict:
    if asset is None or asset.type().name() != ASSET_TYPE:
        raise RuntimeError(f"Expected {ASSET_PATH} {ASSET_TYPE}")
    definition = asset.type().definition()
    if definition is None:
        raise RuntimeError("V10 target has no HDA definition")
    comment = definition.comment() or ""
    if MARKER in comment:
        if not asset.matchesCurrentDefinition():
            asset.matchCurrentDefinition()
        current_group = definition.parmTemplateGroup()
        interface_current = (all(current_group.find(name) is not None
                                 and not current_group.find(name).isHidden()
                                 for name in ("unity_instance_catalog", "unity_generation_rules",
                                              "unity_bridge_end_marker"))
                             and current_group.find("style_id") is None
                             and current_group.find("unity_bridge_revision") is None)
        if not interface_current:
            candidate_group = _parameter_group(asset)
            asset.allowEditingOfContents()
            try:
                validation = _validate(asset, candidate_group, require_live_interface=False)
            finally:
                asset.matchCurrentDefinition()
            if save:
                definition.setParmTemplateGroup(candidate_group)
                asset.allowEditingOfContents()
                asset.matchCurrentDefinition()
                validation = _validate_fresh_definition()
                hou.hipFile.save()
            return {"status": "UPDATED", "save": save, "revision": MARKER,
                    "contract": CONTRACT, "change": "HAPI-visible payload bridge",
                    "validation": validation}
        validation = _validate_fresh_definition()
        if save:
            hou.hipFile.save()
        return {"status": "UNCHANGED", "save": save, "revision": MARKER,
                "contract": CONTRACT, "validation": validation}
    if PREVIOUS_MARKER not in comment:
        raise RuntimeError("V10 requires the exact persisted V9 definition marker")
    if not asset.matchesCurrentDefinition():
        raise RuntimeError("V10 requires the asset to match its current definition before unlock")

    asset.allowEditingOfContents()
    core = asset.node("StreetBuildingCore")
    originals = {}
    for name, expected in EXPECTED_SNIPPETS.items():
        node = core.node(name)
        if node is None:
            asset.matchCurrentDefinition()
            raise RuntimeError(f"V10 target node is missing: {name}")
        snippet = node.parm("snippet").eval()
        if _sha(snippet) != expected:
            asset.matchCurrentDefinition()
            raise RuntimeError(f"V10 precondition hash failed: {name}")
        originals[name] = snippet

    try:
        candidate_group = _parameter_group(asset)
        for name, snippet in _transformed(originals).items():
            core.node(name).parm("snippet").set(snippet)
        validation = _validate(asset, candidate_group, require_live_interface=False)
        if save:
            definition.updateFromNode(asset)
            definition.setParmTemplateGroup(candidate_group)
            definition.setComment(comment.replace(PREVIOUS_MARKER, MARKER))
            asset.allowEditingOfContents()
            asset.matchCurrentDefinition()
            validation = _validate_fresh_definition()
            hou.hipFile.save()
        else:
            asset.matchCurrentDefinition()
        return {"status": "UPDATED", "save": save, "revision": MARKER,
                "contract": CONTRACT, "nodes": sorted(EXPECTED_SNIPPETS),
                "validation": validation}
    except Exception:
        if not save:
            asset.matchCurrentDefinition()
        raise


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--project-root", required=True, type=Path)
    parser.add_argument("--save", choices=("true", "false"), default="false")
    args = parser.parse_args()
    root = args.project_root.resolve()
    hda = (root / REL_HDA).resolve()
    hip = (root / REL_HIP).resolve()
    before_hda = hda.read_bytes()
    before_hip = hip.read_bytes()
    try:
        hou.hipFile.load(str(hip), suppress_save_prompt=True, ignore_load_warnings=False)
        hou.hda.installFile(str(hda), change_oplibraries_file=False, force_use_assets=True)
        result = apply_loaded(hou.node(ASSET_PATH), args.save == "true")
    except Exception:
        if args.save == "true":
            hda.write_bytes(before_hda)
            hip.write_bytes(before_hip)
        raise
    if args.save == "false" and (hda.read_bytes() != before_hda or hip.read_bytes() != before_hip):
        raise RuntimeError("V10 save=False modified persisted HDA/HIP bytes")
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
