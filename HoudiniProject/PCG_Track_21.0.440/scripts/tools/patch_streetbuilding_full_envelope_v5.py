"""V5 patch: deterministic full-envelope Unity module instances.

The patch only edits the current persisted StreetBuilding definition.  It has
an explicit REV4.1 marker precondition, supports a byte-clean save=False pass,
is idempotent, and never touches a Houdini GUI session.
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
PREVIOUS_MARKER = "STREETBUILDING_REV4_1_SINGLE_ENTRANCE_EDGE_COLUMNS"
MARKER = "STREETBUILDING_V5_FULL_ENVELOPE_INSTANCES"
REVISION = "STREETBUILDING_V5_FULL_ENVELOPE_INSTANCES"
CONTRACT_VERSION = "StreetBuilding.DirectInstances.5.0"


COMMON_VEX = r'''
int sb_schema(string catalog)
{
    string rows[] = split(catalog, "\n");
    if (len(rows) > 0)
    {
        string header[] = split(strip(rows[0]), "|");
        if (len(header) == 5 && header[0] == "SBV2") return 2;
    }
    return 1;
}

int sb_has_variant(string catalog; string role; string variant)
{
    int schema = sb_schema(catalog);
    foreach (string row; split(catalog, "\n"))
    {
        string f[] = split(strip(row), "|");
        if (schema == 2 && len(f) == 14 && f[0] == "M" && f[1] == role && f[2] == variant)
            return 1;
        if (schema == 1 && len(f) == 10 && f[0] == role && f[1] == variant)
            return 1;
    }
    return 0;
}

int sb_has_role(string catalog; string role)
{
    int schema = sb_schema(catalog);
    foreach (string row; split(catalog, "\n"))
    {
        string f[] = split(strip(row), "|");
        if (schema == 2 && len(f) == 14 && f[0] == "M" && f[1] == role) return 1;
        if (schema == 1 && len(f) == 10 && f[0] == role) return 1;
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
    int schema = sb_schema(catalog);
    int result = 0;
    foreach (string row; split(catalog, "\n"))
    {
        string f[] = split(strip(row), "|");
        if (schema == 2 && len(f) == 14 && f[0] == "M" && f[1] == role && f[2] == variant)
            result = max(result, atoi(f[3]) + 1);
        if (schema == 1 && len(f) == 10 && f[0] == role && f[1] == variant)
            result = max(result, atoi(f[2]) + 1);
    }
    return result;
}

string sb_catalog_part(string catalog; string role; string variant; int part;
    export vector offset; export vector rotation; export int span)
{
    int schema = sb_schema(catalog);
    offset = 0; rotation = 0; span = 1;
    foreach (string row; split(catalog, "\n"))
    {
        string f[] = split(strip(row), "|");
        if (schema == 2 && len(f) == 14 && f[0] == "M" && f[1] == role
            && f[2] == variant && atoi(f[3]) == part)
        {
            offset = set(atof(f[5]), atof(f[6]), atof(f[7]));
            rotation = set(atof(f[8]), atof(f[9]), atof(f[10]));
            span = int(rint(atof(f[11]) / 2.0));
            return f[4];
        }
        if (schema == 1 && len(f) == 10 && f[0] == role
            && f[1] == variant && atoi(f[2]) == part)
        {
            offset = set(atof(f[4]), atof(f[5]), atof(f[6]));
            rotation = set(atof(f[7]), atof(f[8]), atof(f[9]));
            return f[3];
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
        error("StreetBuilding V5 catalog rotations must be authored inside a Prefab");
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
    string prefix = sb_schema(catalog) == 1
        ? sprintf("SB_B0000_F%02d_C%02d_%s_%s_P%d", floor_index, cell_index, role, variant, part)
        : sprintf("SB_B0000_%s_F%02d_C%02d_%s_%s_P%d", face_token, floor_index, cell_index, role, variant, part);
    setpointattrib(0, "instance_prefix", pt, prefix, "set");
    setpointattrib(0, "name", pt, prefix, "set");
    setpointattrib(0, "building_id", pt, 0, "set");
    setpointattrib(0, "face_index", pt, face_index, "set");
    setpointattrib(0, "floor_index", pt, floor_index, "set");
    setpointattrib(0, "cell_index", pt, cell_index, "set");
    setpointattrib(0, "module_span", pt, span, "set");
    setpointattrib(0, "selection_seed", pt, selection_seed, "set");
    setpointattrib(0, "catalog_schema", pt, sb_schema(catalog), "set");
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


PARSE_SNIPPET = r'''// STREETBUILDING_V5_PARSE_CATALOG
string catalog = chs("../../unity_instance_catalog");
if (len(strip(catalog)) == 0)
    error("StreetBuilding Unity Asset Instances requires a compiled module catalog");
string rows[] = split(catalog, "\n");
int schema = 1;
if (len(rows) > 0)
{
    string header[] = split(strip(rows[0]), "|");
    if (len(header) == 5 && header[0] == "SBV2")
    {
        schema = 2;
        if (header[1] != chs("../../style_id"))
            error("StreetBuilding V2 style header does not match style_id");
        if (abs(atof(header[2]) - 2.0) > 0.001 || abs(atof(header[3]) - 4.0) > 0.001
            || abs(atof(header[4]) - 3.0) > 0.001)
            error("StreetBuilding V2 requires a 2m / 4m / 3m authoring grid");
    }
}
int module_rows = 0;
foreach (string row; rows)
{
    string f[] = split(strip(row), "|");
    if (schema == 2 && len(f) > 0 && f[0] == "M")
    {
        if (len(f) != 14 || atof(f[13]) <= 0.0)
            error("StreetBuilding V2 contains an invalid module row");
        float width = atof(f[11]);
        if ((abs(width - 2.0) > 0.001 && abs(width - 4.0) > 0.001) || atof(f[12]) <= 0.0)
            error("StreetBuilding V2 module dimensions are invalid");
        module_rows++;
    }
    if (schema == 1 && len(f) == 10) module_rows++;
}
if (module_rows == 0) error("StreetBuilding catalog has no module rows");
setdetailattrib(0, "catalog_schema", schema, "set");
setdetailattrib(0, "catalog_module_rows", module_rows, "set");
setdetailattrib(0, "catalog_payload", catalog, "set");
'''


FRONT_BODY = r'''// STREETBUILDING_V5_FRONT
string catalog = chs("../../unity_instance_catalog");
int schema = sb_schema(catalog);
float width = ch("../../internal_width");
int cells = int(rint(width / 2.0));
if (cells < 2 || abs(width - cells * 2.0) > 0.01)
    error("StreetBuilding frontage must be an exact multiple of 2m");
if (abs(ch("../../ground_floor_height") - 4.0) > 0.01
    || abs(ch("../../typical_floor_height") - 3.0) > 0.01)
    error("StreetBuilding direct style requires 4m ground and 3m typical floors");
int floors = max(2, chi("../../floor_count"));
int global_seed = chi("../../seed");
vector origin = set(-width * .5, 0, 0);
vector right = set(1, 0, 0);
vector outward = set(0, 0, 1);
int entrance_cell = cells / 2;

if (schema == 1)
{
    for (int cell = 0; cell < cells; cell++)
    {
        float u = (cell + .5) * 2.0;
        if (cell == entrance_cell)
        {
            for (int part = 0; part < 2; part++)
                sb_add_instance(catalog, "Entrance", "entrance_metal", part, origin, right, outward,
                    u, 0, 0, 0, "front", 0, cell, global_seed, 1, 0);
        }
        else
        {
            string shop = cell % 2 == 0 ? "shop_trim" : "shop_metal";
            sb_add_instance(catalog, "GroundShop", shop, 0, origin, right, outward,
                u, 0, 0, 0, "front", 0, cell, global_seed, 0, 0);
        }
        sb_add_instance(catalog, "Cornice", "brick_center", 0, origin, right, outward,
            u, 3, 0, 0, "front", 0, cell, global_seed, 0, 0);
        for (int floor = 1; floor < floors; floor++)
        {
            string window = ((cell / 2) % 2 == 0) ? "trim" : "trim_single";
            sb_add_instance(catalog, "MiddleWindow", window, 0, origin, right, outward,
                u, 4 + (floor - 1) * 3, 0, 0, "front", floor, cell, global_seed, 0, 0);
        }
    }
    for (int edge = 0; edge < 2; edge++)
    {
        float u = edge == 0 ? 0 : width;
        int cell = edge == 0 ? -1 : cells;
        sb_emit(catalog, "FacadeColumn", "trim_ground", origin, right, outward,
            u, 0, 0, 0, "front", 0, cell, global_seed + edge, 0);
        for (int floor = 1; floor < floors; floor++)
            sb_emit(catalog, "FacadeColumn", "brick_upper", origin, right, outward,
                u, 4 + (floor - 1) * 3, 0, 0, "front", floor, cell,
                global_seed + edge + floor * 17, 0);
    }
}
else
{
    int entrance_span; string entrance = sb_choose_variant(catalog, "Entrance", global_seed + 3, 1, entrance_span);
    for (int cell = 0; cell < cells; cell++)
    {
        float u = (cell + .5) * 2.0;
        int key = global_seed * 1009 + cell * 37;
        if (cell == entrance_cell)
            sb_emit(catalog, "Entrance", entrance, origin, right, outward, u, 0, 0,
                0, "front", 0, cell, key, 1);
        else
        {
            int span; string shop = sb_choose_variant(catalog,
                sb_has_role(catalog, "GroundShop") ? "GroundShop" : "GroundWall", key, 1, span);
            string role = sb_has_role(catalog, "GroundShop") ? "GroundShop" : "GroundWall";
            sb_emit(catalog, role, shop, origin, right, outward, u, 0, 0,
                0, "front", 0, cell, key, 0);
        }
        int cornice_span; string cornice = sb_choose_variant(catalog, "Cornice", key + 7, 1, cornice_span);
        sb_emit(catalog, "Cornice", cornice, origin, right, outward, u, 3, 0,
            0, "front", 0, cell, key + 7, 0);
    }
    int rhythm = chi("../../facade_rhythm");
    for (int floor = 1; floor < floors; floor++)
    {
        int cell = 0;
        while (cell < cells)
        {
            int key = global_seed * 1009 + floor * 101 + cell * 37;
            string role = "MiddleWindow";
            if (rhythm == 2 && ((cell + floor) % 2) != 0) role = "MiddleBlank";
            if (rhythm == 4 && (cell % 4 == 0 || cell % 4 == 3)) role = "MiddleBlank";
            int max_span = cell + 1 < cells ? 2 : 1;
            int span = 1; string variant = "";
            if (rhythm == 3 && max_span == 2 && abs((cell + 1) - cells * .5) <= 1.0
                && sb_has_variant(catalog, "MiddleWindow", "curved_double"))
            {
                role = "MiddleWindow"; variant = "curved_double"; span = 2;
            }
            else
                variant = sb_choose_variant(catalog, role, key, max_span, span);
            if (len(variant) == 0)
            {
                role = "MiddleBlank";
                variant = sb_choose_variant(catalog, role, key + 13, 1, span);
            }
            float u = (cell + span * .5) * 2.0;
            sb_emit(catalog, role, variant, origin, right, outward, u,
                4 + (floor - 1) * 3, 0, 0, "front", floor, cell, key, 0);
            cell += span;
        }
    }
    for (int edge = 0; edge < 2; edge++)
    {
        float u = edge == 0 ? 0 : width;
        int cell = edge == 0 ? -1 : cells;
        sb_emit(catalog, "FacadeColumn", "trim_ground", origin, right, outward,
            u, 0, 0, 0, "front", 0, cell, global_seed + edge, 0);
        for (int floor = 1; floor < floors; floor++)
            sb_emit(catalog, "FacadeColumn", "brick_upper", origin, right, outward,
                u, 4 + (floor - 1) * 3, 0, 0, "front", floor, cell,
                global_seed + edge + floor * 17, 0);
    }
}
removeattrib(0, "point", "N");
'''


SIDE_REAR_BODY = r'''// STREETBUILDING_V5_SIDE_REAR
string catalog = chs("../../unity_instance_catalog");
if (sb_schema(catalog) != 2) return;
float width = ch("../../internal_width");
float depth = ch("../../internal_depth");
int depth_cells = int(rint(depth / 2.0));
int width_cells = int(rint(width / 2.0));
if (abs(depth - depth_cells * 2.0) > .01) error("StreetBuilding depth must be a multiple of 2m");
int floors = max(2, chi("../../floor_count"));
int global_seed = chi("../../seed");
float density = clamp(ch("../../detail_density"), 0.0, 1.0);
int side_mode = chi("../../side_mode");
if (side_mode != 1)
{
    for (int face = 1; face <= 2; face++)
    {
        vector origin = face == 1 ? set(-width * .5, 0, -depth) : set(width * .5, 0, 0);
        vector right = face == 1 ? set(0, 0, 1) : set(0, 0, -1);
        vector outward = face == 1 ? set(-1, 0, 0) : set(1, 0, 0);
        float yaw = face == 1 ? 90.0 : -90.0;
        string surface = face == 1 ? "left" : "right";
        for (int cell = 0; cell < depth_cells; cell++)
        {
            int key = global_seed * 1009 + face * 503 + cell * 37;
            int span; string ground = sb_choose_variant(catalog, "SideWall", key, 1, span);
            sb_emit(catalog, "SideWall", ground, origin, right, outward, (cell + .5) * 2,
                0, yaw, face, surface, 0, cell, key, 0);
            int cs; string cornice = sb_choose_variant(catalog, "Cornice", key + 7, 1, cs);
            sb_emit(catalog, "Cornice", cornice, origin, right, outward, (cell + .5) * 2,
                3, yaw, face, surface, 0, cell, key + 7, 0);
            for (int floor = 1; floor < floors; floor++)
            {
                int fkey = key + floor * 101;
                string role = rand(float(fkey) * .173) < density * .6 ? "MiddleWindow" : "SideWall";
                int fs; string variant = sb_choose_variant(catalog, role, fkey, 1, fs);
                sb_emit(catalog, role, variant, origin, right, outward, (cell + .5) * 2,
                    4 + (floor - 1) * 3, yaw, face, surface, floor, cell, fkey, 0);
            }
        }
    }
}
int rear_mode = chi("../../rear_mode");
if (rear_mode != 0)
{
    vector origin = set(width * .5, 0, -depth);
    vector right = set(-1, 0, 0);
    vector outward = set(0, 0, -1);
    for (int cell = 0; cell < width_cells; cell++)
    {
        int key = global_seed * 1009 + 3 * 503 + cell * 37;
        int span; string ground = sb_choose_variant(catalog, "RearWall", key, 1, span);
        sb_emit(catalog, "RearWall", ground, origin, right, outward, (cell + .5) * 2,
            0, -180, 3, "rear", 0, cell, key, 0);
        int cs; string cornice = sb_choose_variant(catalog, "Cornice", key + 7, 1, cs);
        sb_emit(catalog, "Cornice", cornice, origin, right, outward, (cell + .5) * 2,
            3, -180, 3, "rear", 0, cell, key + 7, 0);
        for (int floor = 1; floor < floors; floor++)
        {
            int fkey = key + floor * 101;
            string role = rear_mode == 2 && rand(float(fkey) * .173) < density * .65
                ? "MiddleWindow" : "RearWall";
            int fs; string variant = sb_choose_variant(catalog, role, fkey, 1, fs);
            sb_emit(catalog, role, variant, origin, right, outward, (cell + .5) * 2,
                4 + (floor - 1) * 3, -180, 3, "rear", floor, cell, fkey, 0);
        }
    }
}
removeattrib(0, "point", "N");
'''


ROOF_BODY = r'''// STREETBUILDING_V5_ROOF
string catalog = chs("../../unity_instance_catalog");
if (sb_schema(catalog) != 2 || !chi("../../generate_roof")) return;
float width = ch("../../internal_width");
float depth = ch("../../internal_depth");
int width_cells = int(rint(width / 2.0));
int depth_cells = int(rint(depth / 2.0));
if (abs(width - width_cells * 2.0) > .01 || abs(depth - depth_cells * 2.0) > .01)
    error("StreetBuilding roof dimensions must be multiples of 2m");
int floors = max(2, chi("../../floor_count"));
float roof_y = 4 + (floors - 1) * 3;
int global_seed = chi("../../seed");
float density = clamp(ch("../../detail_density"), 0.0, 1.0);
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
        vector tile_origin = origin + set(0, 0, -zcell * 2.0);
        sb_emit(catalog, "RoofSurface", roof, tile_origin, right, outward, (xcell + .5) * 2,
            roof_y, 0, 4, "roof", floors, cell, key, 0);
        if (chi("../../generate_attachments") && sb_has_role(catalog, "RoofProp")
            && rand(float(key) * .291 + 5.0) < density * .12)
        {
            int ps; string prop = sb_choose_variant(catalog, "RoofProp", key + 23, 1, ps);
            sb_emit(catalog, "RoofProp", prop, tile_origin, right, outward, (xcell + .5) * 2,
                roof_y + .25, 0, 4, "roof", floors, cell, key + 23, 0);
        }
    }
}
removeattrib(0, "point", "N");
'''


VALIDATE_SNIPPET = r'''// STREETBUILDING_V5_VALIDATE_OUTPUT
int schema = detail(0, "catalog_schema", 0);
int points = npoints(0);
if (points <= 0 || points >= 300) error("StreetBuilding V5 point budget failed: %d", points);
int entrance_count = 0;
int faces[];
for (int point = 0; point < points; point++)
{
    string path = point(0, "unity_instance", point);
    if (len(path) == 0) error("StreetBuilding V5 emitted an empty unity_instance path");
    vector scale = point(0, "scale", point);
    if (distance(scale, set(1, 1, 1)) > .0001) error("StreetBuilding V5 requires unit scale");
    vector4 q = point(0, "orient", point);
    if (abs(length(q) - 1.0) > .001) error("StreetBuilding V5 emitted a non-unit orient");
    int face = point(0, "face_index", point);
    if (find(faces, face) < 0) append(faces, face);
    entrance_count += point(0, "is_building_entrance", point);
}
if (schema == 2 && entrance_count != 1)
    error("StreetBuilding V5 requires exactly one logical entrance, got %d", entrance_count);
setdetailattrib(0, "output_role", "building_lod0_instances", "set");
setdetailattrib(0, "streetbuilding_lod", 0, "set");
setdetailattrib(0, "streetbuilding_contract", "StreetBuilding.DirectInstances.5.0", "set");
setdetailattrib(0, "streetbuilding_revision", "STREETBUILDING_V5_FULL_ENVELOPE_INSTANCES", "set");
setdetailattrib(0, "streetbuilding_bottom_face_count", 0, "set");
setdetailattrib(0, "streetbuilding_front_only", schema == 1, "set");
setdetailattrib(0, "streetbuilding_face_count", len(faces), "set");
'''


TEST_V1 = "\n".join([
    "Entrance|entrance_metal|0|Assets/Test/DoorFrame_Metal_Single.fbx|0|0|0|0|0|0",
    "Entrance|entrance_metal|1|Assets/Test/Door_2.fbx|-0.5|0|-0.12|0|0|0",
    "GroundShop|shop_metal|0|Assets/Test/Metal_FirstFloor_Window.fbx|0|0|0|0|0|0",
    "GroundShop|shop_trim|0|Assets/Test/Trim_FirstFloor_Window_001.fbx|0|0|0|0|0|0",
    "Cornice|brick_center|0|Assets/Test/Cornice_Brick_Center.fbx|0|0|0|0|0|0",
    "MiddleWindow|trim|0|Assets/Test/Brick_Window_Trim.fbx|0|0|0|0|0|0",
    "MiddleWindow|trim_single|0|Assets/Test/Brick_Window_Trim_Single.fbx|0|0|0|0|0|0",
    "FacadeColumn|trim_ground|0|Assets/Test/Trim_Column_Center.fbx|0|0|0|0|0|0",
    "FacadeColumn|brick_upper|0|Assets/Test/Brick_Column_Small.fbx|0|0|0|0|0|0",
])


def _v2_row(role: str, variant: str, path: str, width: float = 2, height: float = 3,
            weight: float = 1, part: int = 0, x: float = 0, y: float = 0, z: float = 0) -> str:
    return f"M|{role}|{variant}|{part}|Assets/Test/{path}.fbx|{x}|{y}|{z}|0|0|0|{width}|{height}|{weight}"


TEST_V2 = "\n".join([
    "SBV2|na_brick_mixeduse_01|2|4|3",
    _v2_row("Entrance", "entrance_metal", "DoorFrame", part=0),
    _v2_row("Entrance", "entrance_metal", "Door", part=1, x=-.5),
    _v2_row("Entrance", "entrance_trim", "DoorFrameTrim", weight=.6, part=0),
    _v2_row("Entrance", "entrance_trim", "Door1", weight=.6, part=1, x=-.5),
    _v2_row("GroundShop", "shop_metal", "ShopMetal", height=4),
    _v2_row("GroundShop", "shop_trim", "ShopTrim", height=4),
    _v2_row("GroundWall", "brick_ground", "Brick4", height=4),
    _v2_row("Cornice", "brick_center", "Cornice", height=1),
    _v2_row("Cornice", "metal_center", "CorniceMetal", height=1, weight=.3),
    _v2_row("MiddleWindow", "trim", "Window"),
    _v2_row("MiddleWindow", "trim_single", "WindowSingle"),
    _v2_row("MiddleWindow", "curved_double", "WindowDouble", width=4, weight=.35),
    _v2_row("MiddleBlank", "brick_plain", "Brick3"),
    _v2_row("MiddleBlank", "brick_clean", "BrickClean", weight=.5),
    _v2_row("SideWall", "brick_ground", "Brick4", height=4),
    _v2_row("SideWall", "brick_upper", "Brick3"),
    _v2_row("SideWall", "brick_upper_clean", "BrickClean", weight=.5),
    _v2_row("RearWall", "brick_ground", "Brick4", height=4),
    _v2_row("RearWall", "brick_upper", "Brick3"),
    _v2_row("RearWall", "brick_upper_clean", "BrickClean", weight=.5),
    _v2_row("FacadeColumn", "trim_ground", "ColumnGround"),
    _v2_row("FacadeColumn", "brick_upper", "ColumnUpper"),
    _v2_row("RoofSurface", "roof_2x2", "Roof", height=2, y=.2),
    _v2_row("RoofProp", "ac_unit", "AC", height=2),
])


def _ensure_node(core: hou.Node, node_type: str, name: str) -> tuple[hou.Node, bool]:
    node = core.node(name)
    if node is None:
        return core.createNode(node_type, name), True
    if node.type().name() != node_type:
        raise RuntimeError(f"{name} has unexpected type {node.type().name()}")
    return node, False


def _set_input(node: hou.Node, index: int, source: hou.Node | None) -> bool:
    if node.input(index) == source:
        return False
    node.setInput(index, source)
    return True


def _set_snippet(node: hou.Node, snippet: str, marker: str, changed: list[str]) -> None:
    if node.parm("class").eval() != 0:
        node.parm("class").set(0)
        changed.append(node.name() + ":class")
    current = node.parm("snippet").eval()
    if current != snippet:
        if marker in current:
            raise RuntimeError(f"{node.name()} marker exists with unexpected VEX")
        node.parm("snippet").set(snippet)
        changed.append(node.name() + ":snippet")


def _signature(geometry: hou.Geometry) -> list[tuple]:
    return sorted((
        point.stringAttribValue("name"),
        point.stringAttribValue("unity_instance"),
        tuple(round(value, 5) for value in point.position()),
        tuple(round(value, 5) for value in point.attribValue("orient")),
    ) for point in geometry.points())


def _validate(asset: hou.Node) -> dict:
    core = asset.node("StreetBuildingCore")
    front = core.node("DIRECT_UNITY_INSTANCE_FACADE")
    side = core.node("BUILD_DIRECT_SIDE_REAR_INSTANCES")
    roof = core.node("BUILD_DIRECT_ROOF_INSTANCES")
    output = core.node("VALIDATE_DIRECT_BUILDING_INSTANCES")
    names = (
        "module_source", "unity_instance_catalog", "style_id", "internal_width",
        "internal_depth", "ground_floor_height", "typical_floor_height", "floor_count",
        "facade_rhythm", "detail_density", "generate_attachments", "rear_mode",
        "side_mode", "generate_roof", "generate_lods", "seed",
    )
    saved = {name: asset.parm(name).eval() for name in names}
    try:
        asset.parm("module_source").set(1)
        asset.parm("style_id").set("na_brick_mixeduse_01")
        asset.parm("internal_width").set(12.0)
        asset.parm("internal_depth").set(10.0)
        asset.parm("ground_floor_height").set(4.0)
        asset.parm("typical_floor_height").set(3.0)
        asset.parm("floor_count").set(4)
        asset.parm("generate_lods").set(0)
        asset.parm("seed").set(29)

        asset.parm("unity_instance_catalog").set(TEST_V1)
        front.cook(force=True)
        if front.geometry().intrinsicValue("pointcount") != 39:
            raise RuntimeError("V1 exact compatibility must remain 39 points")
        side.cook(force=True); roof.cook(force=True)
        if side.geometry().intrinsicValue("pointcount") or roof.geometry().intrinsicValue("pointcount"):
            raise RuntimeError("V1 compatibility must remain front-only")

        asset.parm("unity_instance_catalog").set(TEST_V2)
        asset.parm("facade_rhythm").set(3)
        asset.parm("detail_density").set(.6)
        asset.parm("generate_attachments").set(1)
        asset.parm("rear_mode").set(2)
        asset.parm("side_mode").set(2)
        asset.parm("generate_roof").set(1)
        output.cook(force=True)
        geometry = output.geometry()
        count = geometry.intrinsicValue("pointcount")
        if geometry.intrinsicValue("primitivecount") != 0 or count <= 39 or count >= 300:
            raise RuntimeError(f"V5 full envelope point budget failed: {count}")
        required = {
            "unity_instance", "orient", "scale", "instance_prefix", "name", "building_id",
            "face_index", "floor_index", "cell_index", "module_span", "selection_seed",
            "catalog_schema", "module_role", "module_variant", "surface_role",
            "is_building_entrance",
        }
        actual = {attribute.name() for attribute in geometry.pointAttribs()}
        if required - actual:
            raise RuntimeError(f"V5 missing attributes: {sorted(required - actual)}")
        faces = {point.intAttribValue("face_index") for point in geometry.points()}
        if faces != {0, 1, 2, 3, 4}:
            raise RuntimeError(f"V5 full envelope faces failed: {faces}")
        entrances = sum(point.intAttribValue("is_building_entrance") for point in geometry.points())
        if entrances != 1:
            raise RuntimeError(f"V5 expected one logical entrance, got {entrances}")
        paths = [point.stringAttribValue("unity_instance") for point in geometry.points()]
        if any(not path.startswith("Assets/Test/") for path in paths):
            raise RuntimeError("V5 rewrote or lost source asset paths")
        if not any(point.intAttribValue("module_span") == 2 for point in geometry.points()):
            raise RuntimeError("V5 two-cell span solver was not exercised")
        first_signature = _signature(geometry)
        output.cook(force=True)
        if _signature(output.geometry()) != first_signature:
            raise RuntimeError("V5 same-seed output is not deterministic")

        asset.parm("rear_mode").set(0)
        asset.parm("side_mode").set(1)
        asset.parm("generate_roof").set(0)
        output.cook(force=True)
        disabled_faces = {point.intAttribValue("face_index") for point in output.geometry().points()}
        if disabled_faces != {0}:
            raise RuntimeError(f"V5 side/rear/roof mode switches failed: {disabled_faces}")

        for output_name in (
            "OUT_BUILDING_LOD1", "OUT_BUILDING_LOD2", "OUT_DETAIL_INSTANCES",
            "OUT_BUILDING_COLLISION", "OUT_BUILDING_METADATA",
        ):
            other = core.node(output_name)
            other.cook(force=True)
            if other.geometry().intrinsicValue("pointcount") or other.geometry().intrinsicValue("primitivecount"):
                raise RuntimeError(f"{output_name} must remain empty in V5")
        diagnostics = []
        for node in (front, side, roof, output):
            diagnostics.extend(node.errors())
            diagnostics.extend(node.warnings())
        if diagnostics:
            raise RuntimeError("V5 cook diagnostics: " + "\n".join(diagnostics))
        return {"v1_points": 39, "v2_points": count, "faces": 5,
                "unique_paths": len(set(paths)), "deterministic": True}
    finally:
        for name, value in saved.items():
            asset.parm(name).set(value)


def apply_loaded(asset: hou.Node, save: bool) -> dict:
    if asset is None or asset.type().name() != "pcgbike::StreetBuilding::1.0":
        raise RuntimeError("Expected /obj/StreetBuilding_DEV pcgbike::StreetBuilding::1.0")
    definition = asset.type().definition()
    comment = definition.comment() or ""
    if PREVIOUS_MARKER not in comment and MARKER not in comment:
        raise RuntimeError("V5 precondition marker mismatch")
    asset.allowEditingOfContents(propagate=True)
    core = asset.node("StreetBuildingCore")
    if core is None:
        raise RuntimeError("StreetBuildingCore is missing")
    empty = core.node("EMPTY_GEOMETRY")
    normal0 = core.node("NORMAL_LOD0")
    output0 = core.node("OUT_BUILDING_LOD0")
    if None in (empty, normal0, output0):
        raise RuntimeError("StreetBuilding V5 source/output nodes are missing")
    changed: list[str] = []

    parser, created = _ensure_node(core, "attribwrangle", "PARSE_UNITY_INSTANCE_CATALOG")
    if created: changed.append(parser.name())
    _set_snippet(parser, PARSE_SNIPPET, "STREETBUILDING_V5_PARSE_CATALOG", changed)
    _set_input(parser, 0, empty)

    front, _ = _ensure_node(core, "attribwrangle", "DIRECT_UNITY_INSTANCE_FACADE")
    _set_snippet(front, COMMON_VEX + FRONT_BODY, "STREETBUILDING_V5_FRONT", changed)
    if _set_input(front, 0, parser): changed.append(front.name() + ":input0")

    side, created = _ensure_node(core, "attribwrangle", "BUILD_DIRECT_SIDE_REAR_INSTANCES")
    if created: changed.append(side.name())
    _set_snippet(side, COMMON_VEX + SIDE_REAR_BODY, "STREETBUILDING_V5_SIDE_REAR", changed)
    if _set_input(side, 0, parser): changed.append(side.name() + ":input0")

    roof, created = _ensure_node(core, "attribwrangle", "BUILD_DIRECT_ROOF_INSTANCES")
    if created: changed.append(roof.name())
    _set_snippet(roof, COMMON_VEX + ROOF_BODY, "STREETBUILDING_V5_ROOF", changed)
    if _set_input(roof, 0, parser): changed.append(roof.name() + ":input0")

    merge, created = _ensure_node(core, "merge", "MERGE_DIRECT_BUILDING_INSTANCES")
    if created: changed.append(merge.name())
    for index, source in enumerate((front, side, roof)):
        if _set_input(merge, index, source): changed.append(merge.name() + f":input{index}")

    validator, created = _ensure_node(core, "attribwrangle", "VALIDATE_DIRECT_BUILDING_INSTANCES")
    if created: changed.append(validator.name())
    _set_snippet(validator, VALIDATE_SNIPPET, "STREETBUILDING_V5_VALIDATE_OUTPUT", changed)
    if _set_input(validator, 0, merge): changed.append(validator.name() + ":input0")

    switch, _ = _ensure_node(core, "switch", "LOD0_MODULE_SOURCE_SWITCH")
    if _set_input(switch, 0, normal0): changed.append(switch.name() + ":input0")
    if _set_input(switch, 1, validator): changed.append(switch.name() + ":input1")
    if _set_input(output0, 0, switch): changed.append(output0.name() + ":input0")

    box = core.findNetworkBox("70_UNITY_CONTRACT")
    if box is not None:
        for node in (parser, front, side, roof, merge, validator, switch):
            box.addNode(node)
    base = normal0.position()
    parser.setPosition(base + hou.Vector2(0, -2))
    front.setPosition(base + hou.Vector2(-4, -4))
    side.setPosition(base + hou.Vector2(0, -4))
    roof.setPosition(base + hou.Vector2(4, -4))
    merge.setPosition(base + hou.Vector2(0, -6))
    validator.setPosition(base + hou.Vector2(0, -8))
    switch.setPosition((validator.position() + output0.position()) * .5)
    parser.setComment("V5 / 解析 V1 或 V2 Catalog，仅传输资产路径与 Authoring 数据。")
    front.setComment("V5 / 正面网格：单入口、节奏、权重与双格占用。")
    side.setComment("V5 / 左右侧与背面网格；由 side_mode / rear_mode 控制。")
    roof.setComment("V5 / 2x2m 屋面铺设与低密度屋顶附件。")
    validator.setComment("V5 / 纯点输出、单位缩放、单入口与移动端点数预算。")
    for node in (parser, front, side, roof, validator):
        node.setGenericFlag(hou.nodeFlag.DisplayComment, True)

    validation = _validate(asset)
    if save and changed:
        definition.updateFromNode(asset)
        updated = (definition.comment() or "").replace(PREVIOUS_MARKER, REVISION)
        if MARKER not in updated:
            updated = updated.rstrip() + "\n" + MARKER
        definition.setComment(updated)
        asset.matchCurrentDefinition()
        hou.hipFile.save()
    return {"status": "UPDATED" if changed else "UNCHANGED", "save": save,
            "revision": REVISION, "contract": CONTRACT_VERSION,
            "nodes": changed, "validation": validation}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--project-root", required=True, type=Path)
    parser.add_argument("--save", choices=("true", "false"), default="false")
    parser.add_argument("--update-existing", choices=("true", "false"), default="true")
    args = parser.parse_args()
    root = args.project_root.resolve()
    hda = (root / REL_HDA).resolve()
    hip = (root / REL_HIP).resolve()
    before = (hashlib.sha256(hda.read_bytes()).hexdigest(), hashlib.sha256(hip.read_bytes()).hexdigest())
    hou.hipFile.load(str(hip), suppress_save_prompt=True, ignore_load_warnings=False)
    hou.hda.installFile(str(hda), change_oplibraries_file=False, force_use_assets=True)
    result = apply_loaded(hou.node(ASSET_PATH), args.save == "true")
    after = (hashlib.sha256(hda.read_bytes()).hexdigest(), hashlib.sha256(hip.read_bytes()).hexdigest())
    if args.save == "false" and before != after:
        raise RuntimeError("save=False changed production files")
    result["files"] = {"hda": after[0], "hip": after[1]}
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
