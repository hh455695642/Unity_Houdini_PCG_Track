"""StreetBuilding V7 incremental patch: rectangle/L massing and Catalog V3.

The patch is deliberately based on the persisted V6.1 definition.  It checks
the exact snippets that were captured before editing, supports a byte-clean
``save=False`` pass, is idempotent, and restores the live node on failure.
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
PREVIOUS_MARKER = "STREETBUILDING_V6_1_ROOF_ALIGNMENT"
MARKER = "STREETBUILDING_V7_LSHAPE_STYLE_FAMILIES"
CONTRACT_VERSION = "StreetBuilding.DirectInstances.7.0"

EXPECTED_SNIPPETS = {
    "INTERNAL_TEST_PARCEL": "05cc38f65272030880f3edee8f427c707794f9942370a8ac3ec9027fa0a4c90f",
    "CANONICALIZE_PARCELS": "c3df1921f55bef01d6f9cdb604ac2d161c13e5b573503b53b4bea35d47a260e8",
    "RESOLVE_FRONTAGES": "d7b9ab1aa8c3cd2798ce4e1993ffc7aada16081085cf0cf272342f32cdde6d12",
    "RESOLVE_MASSING": "046425c3bbff7763862d048aa61827c19e07546fd7152572e61ce34f57b16e45",
    "DIRECT_UNITY_INSTANCE_FACADE": "f0bb5435bae9defc6d48d7b8aa980c22869d4ee4b3517770c3627645e8b2ce7b",
    "PARSE_UNITY_INSTANCE_CATALOG": "ea367c76c02bf179836a9206ed81b4719f2cd2d3e25f234e01eecaabf1c42401",
    "BUILD_DIRECT_SIDE_REAR_INSTANCES": "b089630b0fbf6a81065ade4bdd3062423cac5c0f15ceed0e66b352cb3540b59a",
    "BUILD_DIRECT_ROOF_INSTANCES": "f4a790a550e95cb6eac2998faeaf0f8bc375c9dd9528edf7271941097361ab1e",
    "BUILD_DIRECT_ROOF_EDGE_INSTANCES": "39827429b584224bf92adc74ec615cb6844801d2e6db6971f20bb490c4dcf215",
    "DETAIL_INSTANCE_POINTS": "9ddfb618eb5947a0713087403f82349b3150602af709c4276b3daad1421c0411",
    "VALIDATE_DIRECT_BUILDING_INSTANCES": "2cf323a89209687dad7bbc1bb5f71a1314848f0e92497afc4a14636dffcaae15",
    "VALIDATE_DIRECT_DETAIL_INSTANCES": "6cbb211b466a76234293a4dc551d6a25bb729ea7bc77d6114f465d6599139194",
    "BUILD_METADATA": "d8e9b2f6b40a04601ff8633264143c95287fe539d1e3a9184a10f845399187fc",
}


INTERNAL_PARCEL = r'''// STREETBUILDING_V7_INTERNAL_RECTANGLE_OR_L
float width = max(4.0, ch("../../internal_width"));
float depth = max(4.0, ch("../../internal_depth"));
int shape = chi("../../massing_shape");
float notch_w = ch("../../notch_width");
float notch_d = ch("../../notch_depth");
int notch_side = chi("../../notch_side");
if (shape < 0 || shape > 1) error("StreetBuilding supports Rectangle or L Shape only");
if (shape == 1)
{
    if (abs(notch_w / 2.0 - rint(notch_w / 2.0)) > .001
        || abs(notch_d / 2.0 - rint(notch_d / 2.0)) > .001)
        error("StreetBuilding L notch dimensions must use the 2m module grid");
    if (notch_w < 2.0 || notch_d < 2.0 || width - notch_w < 4.0 || depth - notch_d < 4.0)
        error("StreetBuilding L notch must preserve two-cell wings");
}
vector positions[];
if (shape == 0)
    positions = array(set(-width*.5,0,-depth*.5), set(width*.5,0,-depth*.5),
        set(width*.5,0,depth*.5), set(-width*.5,0,depth*.5));
else if (notch_side == 0)
    positions = array(set(-width*.5,0,depth*.5), set(width*.5,0,depth*.5),
        set(width*.5,0,-depth*.5), set(-width*.5+notch_w,0,-depth*.5),
        set(-width*.5+notch_w,0,-depth*.5+notch_d),
        set(-width*.5,0,-depth*.5+notch_d));
else
    positions = array(set(-width*.5,0,depth*.5), set(width*.5,0,depth*.5),
        set(width*.5,0,-depth*.5+notch_d),
        set(width*.5-notch_w,0,-depth*.5+notch_d),
        set(width*.5-notch_w,0,-depth*.5), set(-width*.5,0,-depth*.5));
int prim = addprim(0, "poly");
foreach (vector position; positions) addvertex(0, prim, addpoint(0, position));
setprimattrib(0, "building_id", prim, 0, "set");
setprimattrib(0, "style_id", prim, chs("../../style_id"), "set");
setprimattrib(0, "massing_shape", prim, shape == 0 ? "rectangle" : "l_shape", "set");
setprimattrib(0, "notch_side", prim, notch_side == 0 ? "rear_left" : "rear_right", "set");
setdetailattrib(0, "streetbuilding_internal_source", 1, "set");
'''


PARSER = r'''// STREETBUILDING_V7_PARSE_CATALOG
string catalog = chs("../../unity_instance_catalog");
if (len(strip(catalog)) == 0)
    error("StreetBuilding Unity Asset Instances requires a compiled module catalog");
string rows[] = split(catalog, "\n");
int schema = 1;
string module_family = "legacy";
if (len(rows) > 0)
{
    string header[] = split(strip(rows[0]), "|");
    if ((len(header) == 5 && header[0] == "SBV2")
        || (len(header) == 6 && header[0] == "SBV3"))
    {
        schema = header[0] == "SBV3" ? 3 : 2;
        if (header[1] != chs("../../style_id"))
            error("StreetBuilding catalog style header does not match style_id");
        if (abs(atof(header[2])-2.0) > .001 || abs(atof(header[3])-4.0) > .001
            || abs(atof(header[4])-3.0) > .001)
            error("StreetBuilding catalog requires a 2m / 4m / 3m authoring grid");
        if (schema == 3)
        {
            module_family = strip(header[5]);
            if (len(module_family) == 0 || module_family == "*")
                error("StreetBuilding V3 requires one selected module family");
        }
    }
}
int module_rows = 0;
foreach (string row; rows)
{
    string f[] = split(strip(row), "|");
    if (schema >= 2 && len(f) > 0 && f[0] == "M")
    {
        if (len(f) != 14 || atof(f[13]) <= 0.0)
            error("StreetBuilding catalog contains an invalid module row");
        float width = atof(f[11]);
        if ((abs(width-2.0) > .001 && abs(width-4.0) > .001) || atof(f[12]) <= 0.0)
            error("StreetBuilding catalog module dimensions are invalid");
        module_rows++;
    }
    if (schema == 1 && len(f) == 10) module_rows++;
}
if (module_rows == 0) error("StreetBuilding catalog has no module rows");
setdetailattrib(0, "catalog_schema", schema, "set");
setdetailattrib(0, "catalog_module_rows", module_rows, "set");
setdetailattrib(0, "module_family", module_family, "set");
setdetailattrib(0, "catalog_payload", catalog, "set");
'''


SIDE_BODY = r'''// STREETBUILDING_V7_SIDE_REAR_L_ENVELOPE
string catalog = chs("../../unity_instance_catalog");
if (sb_schema(catalog) < 2) return;
float width = ch("../../internal_width");
float depth = ch("../../internal_depth");
int depth_cells = int(rint(depth / 2.0));
int width_cells = int(rint(width / 2.0));
int shape = chi("../../massing_shape");
float notch_w = ch("../../notch_width");
float notch_d = ch("../../notch_depth");
int notch_side = chi("../../notch_side");
int notch_wc = int(rint(notch_w / 2.0));
int notch_dc = int(rint(notch_d / 2.0));
if (abs(depth-depth_cells*2.0) > .01 || abs(width-width_cells*2.0) > .01)
    error("StreetBuilding dimensions must be multiples of 2m");
if (shape == 1 && (notch_wc < 1 || notch_dc < 1 || width_cells-notch_wc < 2
    || depth_cells-notch_dc < 2)) error("StreetBuilding invalid L notch");
int floors = max(2, chi("../../floor_count"));
float ground_h = ch("../../ground_floor_height");
float typical_h = ch("../../typical_floor_height");
int global_seed = chi("../../seed");
float shell_variation = .6;
int side_mode = chi("../../side_mode");
int rear_mode = chi("../../rear_mode");

// Rectangle keeps the exact V6.1 loops and therefore the persisted point counts.
if (shape == 0)
{
    if (side_mode != 1)
    {
        for (int face = 1; face <= 2; face++)
        {
            vector origin = face == 1 ? set(-width*.5,0,-depth) : set(width*.5,0,0);
            vector right = face == 1 ? set(0,0,1) : set(0,0,-1);
            vector outward = face == 1 ? set(-1,0,0) : set(1,0,0);
            float yaw = face == 1 ? 90.0 : -90.0;
            string surface = face == 1 ? "left" : "right";
            for (int cell=0; cell<depth_cells; cell++)
                sbv7_emit_wall_cell(catalog, "SideWall", origin, right, outward,
                    yaw, face, surface, cell, cell, floors, ground_h, typical_h,
                    global_seed, shell_variation, 2);
        }
    }
    if (rear_mode != 0)
    {
        vector origin = set(width*.5,0,-depth);
        for (int cell=0; cell<width_cells; cell++)
            sbv7_emit_wall_cell(catalog, "RearWall", origin, set(-1,0,0),
                set(0,0,-1), -180, 3, "rear", cell, cell, floors, ground_h,
                typical_h, global_seed, shell_variation, rear_mode);
    }
}
else
{
    int serial = 0;
    // Five non-front boundary runs. Rear-left and rear-right are mirrors.
    if (notch_side == 0)
    {
        if (side_mode != 1)
        {
            for (int c=0;c<depth_cells;c++)
                sbv7_emit_wall_cell(catalog,"SideWall",set(width*.5,0,0),set(0,0,-1),set(1,0,0),-90,2,"right",c,serial++,floors,ground_h,typical_h,global_seed,shell_variation,2);
            for (int c=0;c<notch_dc;c++)
                sbv7_emit_wall_cell(catalog,"SideWall",set(-width*.5+notch_w,0,-depth),set(0,0,1),set(-1,0,0),90,1,"notch_inner",c,serial++,floors,ground_h,typical_h,global_seed,shell_variation,2);
            for (int c=0;c<depth_cells-notch_dc;c++)
                sbv7_emit_wall_cell(catalog,"SideWall",set(-width*.5,0,-depth+notch_d),set(0,0,1),set(-1,0,0),90,1,"left",c,serial++,floors,ground_h,typical_h,global_seed,shell_variation,2);
        }
        if (rear_mode != 0)
        {
            for (int c=0;c<width_cells-notch_wc;c++)
                sbv7_emit_wall_cell(catalog,"RearWall",set(width*.5,0,-depth),set(-1,0,0),set(0,0,-1),-180,3,"rear",c,serial++,floors,ground_h,typical_h,global_seed,shell_variation,rear_mode);
            for (int c=0;c<notch_wc;c++)
                sbv7_emit_wall_cell(catalog,"RearWall",set(-width*.5+notch_w,0,-depth+notch_d),set(-1,0,0),set(0,0,-1),-180,3,"notch_rear",c,serial++,floors,ground_h,typical_h,global_seed,shell_variation,rear_mode);
        }
    }
    else
    {
        if (side_mode != 1)
        {
            for (int c=0;c<depth_cells;c++)
                sbv7_emit_wall_cell(catalog,"SideWall",set(-width*.5,0,-depth),set(0,0,1),set(-1,0,0),90,1,"left",c,serial++,floors,ground_h,typical_h,global_seed,shell_variation,2);
            for (int c=0;c<notch_dc;c++)
                sbv7_emit_wall_cell(catalog,"SideWall",set(width*.5-notch_w,0,-depth),set(0,0,1),set(1,0,0),-90,2,"notch_inner",c,serial++,floors,ground_h,typical_h,global_seed,shell_variation,2);
            for (int c=0;c<depth_cells-notch_dc;c++)
                sbv7_emit_wall_cell(catalog,"SideWall",set(width*.5,0,0),set(0,0,-1),set(1,0,0),-90,2,"right",c,serial++,floors,ground_h,typical_h,global_seed,shell_variation,2);
        }
        if (rear_mode != 0)
        {
            for (int c=0;c<width_cells-notch_wc;c++)
                sbv7_emit_wall_cell(catalog,"RearWall",set(width*.5-notch_w,0,-depth),set(-1,0,0),set(0,0,-1),-180,3,"rear",c,serial++,floors,ground_h,typical_h,global_seed,shell_variation,rear_mode);
            for (int c=0;c<notch_wc;c++)
                sbv7_emit_wall_cell(catalog,"RearWall",set(width*.5,0,-depth+notch_d),set(-1,0,0),set(0,0,-1),-180,3,"notch_rear",c,serial++,floors,ground_h,typical_h,global_seed,shell_variation,rear_mode);
        }
    }
}
removeattrib(0, "point", "N");
'''


SIDE_HELPER = r'''
void sbv7_emit_wall_cell(string catalog; string wall_role; vector origin;
    vector right; vector outward; float yaw; int face; string surface; int local_cell;
    int serial; int floors; float ground_h; float typical_h; int global_seed;
    float shell_variation; int wall_mode)
{
    int key = global_seed*1009 + face*503 + serial*37;
    int span; string ground = sbv61_choose_height(catalog, wall_role, key, ground_h, span);
    sb_emit(catalog, wall_role, ground, origin, right, outward, (local_cell+.5)*2,
        0, yaw, face, surface, 0, serial, key, 0);
    int cs; string cornice = sb_choose_variant(catalog, "Cornice", key+7, 1, cs);
    sb_emit(catalog, "Cornice", cornice, origin, right, outward, (local_cell+.5)*2,
        ground_h-1.0, yaw, face, surface, 0, serial, key+7, 0);
    for (int floor=1; floor<floors; floor++)
    {
        int fkey = key + floor*101;
        float chance = wall_role == "RearWall" ? .65 : .6;
        string role = wall_mode == 2 && rand(float(fkey)*.173) < shell_variation*chance
            ? "MiddleWindow" : wall_role;
        int fs; string variant = role == "SideWall" || role == "RearWall"
            ? sbv61_choose_height(catalog, role, fkey, typical_h, fs)
            : sb_choose_variant(catalog, role, fkey, 1, fs);
        sb_emit(catalog, role, variant, origin, right, outward, (local_cell+.5)*2,
            ground_h+(floor-1)*typical_h, yaw, face, surface, floor, serial, fkey, 0);
    }
}
'''


ROOF_BODY = r'''// STREETBUILDING_V7_ROOF_L_FOOTPRINT
string catalog = chs("../../unity_instance_catalog");
if (sb_schema(catalog) < 2 || !chi("../../generate_roof")) return;
float width = ch("../../internal_width");
float depth = ch("../../internal_depth");
int width_cells = int(rint(width/2.0));
int depth_cells = int(rint(depth/2.0));
int shape = chi("../../massing_shape");
int notch_wc = int(rint(ch("../../notch_width")/2.0));
int notch_dc = int(rint(ch("../../notch_depth")/2.0));
int notch_side = chi("../../notch_side");
if (abs(width-width_cells*2.0) > .01 || abs(depth-depth_cells*2.0) > .01)
    error("StreetBuilding roof dimensions must be multiples of 2m");
int floors = max(2,chi("../../floor_count"));
float roof_y = ch("../../ground_floor_height")+(floors-1)*ch("../../typical_floor_height");
int global_seed = chi("../../seed");
vector origin=set(-width*.5,0,0); vector right=set(1,0,0); vector outward=set(0,0,-1);
for (int zcell=0;zcell<depth_cells;zcell++) for (int xcell=0;xcell<width_cells;xcell++)
{
    int removed = shape == 1 && zcell >= depth_cells-notch_dc
        && (notch_side == 0 ? xcell < notch_wc : xcell >= width_cells-notch_wc);
    if (removed) continue;
    int cell=zcell*width_cells+xcell;
    int key=global_seed*1009+4*503+cell*37;
    int span; string roof=sb_choose_variant(catalog,"RoofSurface",key,1,span);
    vector tile_origin=origin+set(0,0,-(zcell+.5)*2.0);
    sb_emit(catalog,"RoofSurface",roof,tile_origin,right,outward,(xcell+.5)*2.0,
        roof_y,0,4,"roof",floors,cell,key,0);
}
removeattrib(0,"point","N");
'''


EDGE_BODY = r'''// STREETBUILDING_V7_ROOF_EDGE_L_FOOTPRINT
string catalog=chs("../../unity_instance_catalog");
if (sb_schema(catalog)<2 || !chi("../../generate_roof")) return;
float parapet_h=ch("../../parapet_height"); if (parapet_h<=.001) return;
int shape=chi("../../massing_shape");
if (!sb_has_role(catalog,"Parapet") || !sb_has_role(catalog,"ParapetCorner")
    || (shape==1 && !sb_has_role(catalog,"ParapetConcaveCorner")))
    error("StreetBuilding parapet roles are incomplete");
float width=ch("../../internal_width"); float depth=ch("../../internal_depth");
float nw=ch("../../notch_width"); float nd=ch("../../notch_depth");
int ns=chi("../../notch_side");
int wc=int(rint(width/2.0)); int dc=int(rint(depth/2.0));
int nwc=int(rint(nw/2.0)); int ndc=int(rint(nd/2.0));
int floors=max(2,chi("../../floor_count"));
float roof_y=ch("../../ground_floor_height")+(floors-1)*ch("../../typical_floor_height");
int seed=chi("../../seed");
if (shape==0)
{
    for (int face=0;face<4;face++)
    {
        int cells=face<2?wc:dc;
        vector origin=face==0?set(-width*.5,0,0):face==1?set(width*.5,0,-depth):face==2?set(-width*.5,0,-depth):set(width*.5,0,0);
        vector right=face==0?set(1,0,0):face==1?set(-1,0,0):face==2?set(0,0,1):set(0,0,-1);
        vector outward=face==0?set(0,0,1):face==1?set(0,0,-1):face==2?set(-1,0,0):set(1,0,0);
        float yaw=face==0?0:face==1?-180:face==2?90:-90;
        string surface=face==0?"front":face==1?"rear":face==2?"left":"right";
        sbv7_emit_parapet_run(catalog,origin,right,outward,cells,yaw,face,surface,floors,seed,face*100);
    }
    vector cp[]=array(set(-width*.5,roof_y,0),set(width*.5,roof_y,0),set(width*.5,roof_y,-depth),set(-width*.5,roof_y,-depth));
    float cy[]=array(0.0,-90.0,-180.0,90.0);
    for(int c=0;c<4;c++) sbv7_emit_corner(catalog,"ParapetCorner",cp[c],cy[c],floors,seed,c);
}
else
{
    vector origins[]; vector rights[]; vector outs[]; int cells[]; float yaws[];
    vector corners[]; float corner_yaws[]; int concave=3;
    if(ns==0)
    {
        origins=array(set(-width*.5,0,0),set(width*.5,0,0),set(width*.5,0,-depth),set(-width*.5+nw,0,-depth),set(-width*.5+nw,0,-depth+nd),set(-width*.5,0,-depth+nd));
        rights=array(set(1,0,0),set(0,0,-1),set(-1,0,0),set(0,0,1),set(-1,0,0),set(0,0,1));
        outs=array(set(0,0,1),set(1,0,0),set(0,0,-1),set(-1,0,0),set(0,0,-1),set(-1,0,0));
        cells=array(wc,dc,wc-nwc,ndc,nwc,dc-ndc);
        yaws=array(0.0,-90.0,-180.0,90.0,-180.0,90.0);
        corners=array(set(-width*.5,roof_y,0),set(width*.5,roof_y,0),set(width*.5,roof_y,-depth),set(-width*.5+nw,roof_y,-depth),set(-width*.5+nw,roof_y,-depth+nd),set(-width*.5,roof_y,-depth+nd));
        corner_yaws=array(0.0,-90.0,-180.0,90.0,0.0,90.0);
    }
    else
    {
        origins=array(set(-width*.5,0,0),set(width*.5,0,0),set(width*.5,0,-depth+nd),set(width*.5-nw,0,-depth+nd),set(width*.5-nw,0,-depth),set(-width*.5,0,-depth));
        rights=array(set(1,0,0),set(0,0,-1),set(-1,0,0),set(0,0,-1),set(-1,0,0),set(0,0,1));
        outs=array(set(0,0,1),set(1,0,0),set(0,0,-1),set(1,0,0),set(0,0,-1),set(-1,0,0));
        cells=array(wc,dc-ndc,nwc,ndc,wc-nwc,dc);
        yaws=array(0.0,-90.0,-180.0,-90.0,-180.0,90.0);
        corners=array(set(-width*.5,roof_y,0),set(width*.5,roof_y,0),set(width*.5,roof_y,-depth+nd),set(width*.5-nw,roof_y,-depth+nd),set(width*.5-nw,roof_y,-depth),set(-width*.5,roof_y,-depth));
        corner_yaws=array(0.0,-90.0,-180.0,-90.0,0.0,90.0);
    }
    for(int e=0;e<6;e++) sbv7_emit_parapet_run(catalog,origins[e],rights[e],outs[e],cells[e],yaws[e],4,"roof_edge",floors,seed,e*100);
    for(int c=0;c<6;c++) sbv7_emit_corner(catalog,c==concave?"ParapetConcaveCorner":"ParapetCorner",corners[c],corner_yaws[c],floors,seed,c);
}
removeattrib(0,"point","N");
'''


EDGE_HELPER = r'''
void sbv7_emit_parapet_run(string catalog; vector origin; vector right; vector outward;
    int cells; float yaw; int face; string surface; int floors; int seed; int serial_base)
{
    float roof_y=ch("../../ground_floor_height")+(floors-1)*ch("../../typical_floor_height");
    for(int cell=1;cell<cells-1;cell++)
    {
        int key=seed*1009+(face+5)*503+(serial_base+cell)*37;
        int span; string variant=sb_choose_variant(catalog,"Parapet",key,1,span);
        sb_emit(catalog,"Parapet",variant,origin,right,outward,(cell+.5)*2.0,
            roof_y,yaw,face,surface,floors,serial_base+cell,key,0);
    }
}
void sbv7_emit_corner(string catalog; string role; vector position; float yaw;
    int floors; int seed; int corner)
{
    int key=seed*1009+9001+corner*37; int span;
    string variant=sb_choose_variant(catalog,role,key,1,span);
    sb_emit(catalog,role,variant,position,set(1,0,0),set(0,0,1),0,0,yaw,4,
        "roof_edge",floors,corner,key,0);
}
'''


def _sha(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _catalog_row(role: str, variant: str, width: float = 2, height: float = 3) -> str:
    return f"M|{role}|{variant}|0|Assets/Test/{variant}.prefab|0|0|0|0|0|0|{width}|{height}|1"


TEST_V3 = "\n".join([
    "SBV3|na_brick_mixeduse_01|2|4|3|family_a",
    _catalog_row("Entrance", "entrance"),
    "M|Entrance|entrance|1|Assets/Test/EntranceDoor.prefab|0|0|0|0|0|0|2|3|1",
    _catalog_row("GroundShop", "shop", height=4),
    _catalog_row("GroundWall", "ground", height=4), _catalog_row("Cornice", "cornice", height=1),
    _catalog_row("MiddleWindow", "window"), _catalog_row("MiddleWindow", "curved_double", 4, 3),
    _catalog_row("MiddleBlank", "blank"),
    _catalog_row("SideWall", "side_ground", height=4), _catalog_row("SideWall", "side_upper"),
    _catalog_row("RearWall", "rear_ground", height=4), _catalog_row("RearWall", "rear_upper"),
    _catalog_row("FacadeColumn", "trim_ground"), _catalog_row("FacadeColumn", "brick_upper"),
    _catalog_row("RoofSurface", "roof", height=2),
    _catalog_row("Parapet", "straight", height=.6), _catalog_row("ParapetCorner", "convex", height=.6),
    _catalog_row("ParapetConcaveCorner", "concave", height=.6),
    _catalog_row("Awning", "awning", height=1), _catalog_row("Sign", "sign", height=1),
    _catalog_row("FireEscape", "escape", 4, 6), _catalog_row("ACUnit", "ac", height=1),
    _catalog_row("RoofProp", "tank", height=2),
])


def _upgrade_common(text: str) -> str:
    old = '''int sb_schema(string catalog)\n{\n    string rows[] = split(catalog, "\\n");\n    if (len(rows) > 0)\n    {\n        string header[] = split(strip(rows[0]), "|");\n        if (len(header) == 5 && header[0] == "SBV2") return 2;\n    }\n    return 1;\n}\n'''
    new = '''int sb_schema(string catalog)\n{\n    string rows[] = split(catalog, "\\n");\n    if (len(rows) > 0)\n    {\n        string header[] = split(strip(rows[0]), "|");\n        if (len(header) == 6 && header[0] == "SBV3") return 3;\n        if (len(header) == 5 && header[0] == "SBV2") return 2;\n    }\n    return 1;\n}\n\nstring sb_family(string catalog)\n{\n    string rows[] = split(catalog, "\\n");\n    if (len(rows) > 0)\n    {\n        string header[] = split(strip(rows[0]), "|");\n        if (len(header) == 6 && header[0] == "SBV3") return header[5];\n    }\n    return "legacy";\n}\n'''
    if old not in text:
        raise RuntimeError("common helper precondition failed")
    text = text.replace(old, new, 1).replace("schema == 2", "schema >= 2")
    needle = 'setpointattrib(0, "catalog_schema", pt, sb_schema(catalog), "set");'
    if needle in text:
        text = text.replace(needle, needle + '\n    setpointattrib(0, "module_family", pt, sb_family(catalog), "set");', 1)
    return text


def _replace_body(text: str, marker: str, helper: str, body: str) -> str:
    if marker not in text:
        raise RuntimeError(f"body marker missing: {marker}")
    return text.split(marker, 1)[0] + helper + "\n" + body


def _parameter_specs() -> list[hou.ParmTemplate]:
    return [
        hou.MenuParmTemplate("massing_shape", "Massing Shape / 体块形状",
            ("rectangle", "l_shape"), ("Rectangle / 矩形", "L Shape / L形"), default_value=0),
        hou.FloatParmTemplate("notch_width", "L Notch Width (m) / L缺口宽", 1,
            default_value=(4.0,), min=2.0, max=100.0, min_is_strict=True),
        hou.FloatParmTemplate("notch_depth", "L Notch Depth (m) / L缺口深", 1,
            default_value=(4.0,), min=2.0, max=100.0, min_is_strict=True),
        hou.MenuParmTemplate("notch_side", "L Notch Side / L缺口方向",
            ("rear_left", "rear_right"), ("Rear Left / 后左", "Rear Right / 后右"), default_value=0),
    ]


def _massing_folder_indices(group: hou.ParmTemplateGroup) -> tuple[int, ...]:
    for name in ("input_folder8_1", "input_folder_1"):
        indices = group.findIndices(name)
        if indices:
            return indices
    def visit(entries) -> str | None:
        for entry in entries:
            if isinstance(entry, hou.FolderParmTemplate):
                if entry.label().startswith("Massing"):
                    return entry.name()
                found = visit(entry.parmTemplates())
                if found:
                    return found
        return None
    name = visit(group.entries())
    return group.findIndices(name) if name else ()


def _add_parameters(asset: hou.Node) -> list[str]:
    group = asset.parmTemplateGroup()
    changed = []
    folder = _massing_folder_indices(group)
    if not folder:
        raise RuntimeError("Massing folder is missing")
    for template in _parameter_specs():
        existing = group.find(template.name())
        if existing is None:
            group.appendToFolder(folder, template)
            changed.append(template.name())
    if changed:
        asset.setParmTemplateGroup(group)
    return changed


def _patch_detail(text: str) -> str:
    text = text.replace("STREETBUILDING_V6_1_DETAIL_INSTANCE_POINTS", "STREETBUILDING_V7_DETAIL_INSTANCES", 1)
    text = text.replace('detail(0, "catalog_schema", 0) != 2', 'detail(0, "catalog_schema", 0) < 2', 1)
    text = text.replace('setpointattrib(0, "catalog_schema", pt, 2, "set");',
        'int catalog_schema = 2; string module_family = "legacy";\n'
        '        string header_rows[] = split(catalog, "\\n");\n'
        '        if (len(header_rows) > 0) { string hf[] = split(strip(header_rows[0]), "|");\n'
        '            if (len(hf) == 6 && hf[0] == "SBV3") { catalog_schema = 3; module_family = hf[5]; } }\n'
        '        setpointattrib(0, "catalog_schema", pt, catalog_schema, "set");\n'
        '        setpointattrib(0, "module_family", pt, module_family, "set");', 1)
    text = text.replace('4.65 + (floor - 1) * 3', 'ch("../../ground_floor_height") + .65 + (floor - 1) * ch("../../typical_floor_height")')
    # Select roof props from valid interior cells, never from the removed notch.
    start = text.index('if (emitted < 64 && chi("../../generate_roof")')
    end = text.index('\nsetdetailattrib(0, "output_role"', start)
    roof = r'''if (emitted < 64 && chi("../../generate_roof") && wcells >= 3 && dcells >= 3
    && sbv6_has_role(catalog, "RoofProp")
    && rand(float(seed) * .887 + 31.0) < density * .55)
{
    int valid_cells[];
    int shape = chi("../../massing_shape");
    int nwc = int(rint(ch("../../notch_width") / 2.0));
    int ndc = int(rint(ch("../../notch_depth") / 2.0));
    int ns = chi("../../notch_side");
    for (int z=1; z<dcells-1; z++) for (int x=1; x<wcells-1; x++)
    {
        int removed = shape == 1 && z >= dcells-ndc
            && (ns == 0 ? x < nwc : x >= wcells-nwc);
        if (!removed) append(valid_cells, z*wcells+x);
    }
    if (len(valid_cells) > 0)
    {
        int pick = clamp(int(floor(rand(float(seed)*.417+3.0)*len(valid_cells))), 0, len(valid_cells)-1);
        int cell = valid_cells[pick]; int xcell = cell % wcells; int zcell = cell / wcells;
        float roof_y = ch("../../ground_floor_height") + (floors-1)*ch("../../typical_floor_height");
        emitted += sbv6_emit(catalog,"RoofProp",seed*1009+4*503+cell*37,
            set(-width*.5,0,-(zcell+.5)*2.0),set(1,0,0),set(0,0,-1),
            (xcell+.5)*2,roof_y,0,4,"roof",floors,cell);
    }
}
'''
    text = text[:start] + roof + text[end:]
    return text.replace("StreetBuilding.DirectInstances.6.1", CONTRACT_VERSION).replace(PREVIOUS_MARKER, MARKER)


def _patch_simple_metadata(text: str) -> str:
    text = text.replace("StreetBuilding.DirectInstances.6.1", CONTRACT_VERSION)
    text = text.replace(PREVIOUS_MARKER, MARKER)
    if "streetbuilding_massing_shape" not in text:
        text += '\nsetdetailattrib(0, "streetbuilding_massing_shape", chi("../../massing_shape") == 0 ? "rectangle" : "l_shape", "set");\n'
    return text


def _validate(asset: hou.Node) -> dict:
    core = asset.node("StreetBuildingCore")
    lod0 = core.node("OUT_BUILDING_LOD0")
    def cook(node: hou.Node, label: str) -> None:
        try:
            node.cook(force=True)
        except hou.OperationFailed as exc:
            diagnostics = []
            for child in core.allSubChildren():
                diagnostics.extend(f"{child.path()}: {message}" for message in child.errors())
                diagnostics.extend(f"{child.path()}: {message}" for message in child.warnings())
            raise RuntimeError(label + " cook failed:\n" + "\n".join(diagnostics)) from exc
    names = ("module_source", "unity_instance_catalog", "style_id", "internal_width",
        "internal_depth", "floor_count", "ground_floor_height", "typical_floor_height",
        "parapet_height", "rear_mode", "side_mode", "generate_roof", "generate_lods",
        "seed", "facade_rhythm", "detail_density", "generate_attachments",
        "massing_shape", "notch_width", "notch_depth", "notch_side")
    saved = {name: asset.parm(name).eval() for name in names}
    try:
        values = {"module_source":1,"unity_instance_catalog":TEST_V3,"style_id":"na_brick_mixeduse_01",
            "internal_width":12,"internal_depth":10,"floor_count":4,"ground_floor_height":4,
            "typical_floor_height":3,"parapet_height":.6,"rear_mode":2,"side_mode":2,
            "generate_roof":1,"generate_lods":0,"seed":29,"facade_rhythm":3,
            "detail_density":1,"generate_attachments":1,"massing_shape":0,
            "notch_width":4,"notch_depth":4,"notch_side":0}
        for name, value in values.items(): asset.parm(name).set(value)
        cook(lod0, "V7 rectangle")
        geo = lod0.geometry()
        roles = [p.stringAttribValue("module_role") for p in geo.points()]
        if geo.intrinsicValue("pointcount") != 161 or roles.count("RoofSurface") != 30 \
                or roles.count("Parapet") != 14 or roles.count("ParapetCorner") != 4:
            counts = {role: roles.count(role) for role in set(roles)}
            raise RuntimeError(f"V7 changed the persisted V6.1 rectangle baseline: "
                f"points={geo.intrinsicValue('pointcount')} roles={counts}")
        results = {"rectangle_points":161, "rectangle_roof_tiles":30}
        for side in (0, 1):
            asset.parm("massing_shape").set(1); asset.parm("notch_side").set(side)
            cook(lod0, f"V7 L side {side}"); geo = lod0.geometry()
            roles = [p.stringAttribValue("module_role") for p in geo.points()]
            if roles.count("RoofSurface") != 26 or roles.count("ParapetConcaveCorner") != 1 \
                    or roles.count("ParapetCorner") != 5:
                raise RuntimeError(f"V7 L roof/parapet coverage failed for side {side}")
            for point in geo.points():
                if point.stringAttribValue("module_family") != "family_a":
                    raise RuntimeError("V7 module_family metadata is missing")
                if point.stringAttribValue("module_role") == "RoofSurface":
                    ux = -point.position()[0]; z = point.position()[2]
                    removed = z < -6.0 and (ux < -2.0 if side == 0 else ux > 2.0)
                    if removed: raise RuntimeError("V7 roof tile entered the L notch")
            results[f"l_{'left' if side == 0 else 'right'}_points"] = geo.intrinsicValue("pointcount")
        diagnostics = []
        for node in (lod0, core.node("OUT_DETAIL_INSTANCES"), core.node("VALIDATE_DIRECT_BUILDING_INSTANCES"), core.node("VALIDATE_DIRECT_DETAIL_INSTANCES")):
            cook(node, "V7 diagnostics"); diagnostics += list(node.errors()) + list(node.warnings())
        if diagnostics: raise RuntimeError("V7 cook diagnostics: " + "\n".join(diagnostics))
        results.update({"l_roof_tiles":26,"convex_corners":5,"concave_corners":1,"module_family":"family_a"})
        return results
    finally:
        for name, value in saved.items(): asset.parm(name).set(value)


def apply_loaded(asset: hou.Node, save: bool) -> dict:
    if asset is None or asset.type().name() != ASSET_TYPE:
        raise RuntimeError(f"Expected {ASSET_PATH} {ASSET_TYPE}")
    definition = asset.type().definition()
    if definition is None: raise RuntimeError("StreetBuilding has no definition")
    comment = definition.comment() or ""
    if MARKER in comment:
        group = definition.parmTemplateGroup()
        folder = _massing_folder_indices(group)
        if not folder:
            raise RuntimeError("V7 definition Massing folder is missing")
        repaired = []
        for template in _parameter_specs():
            if group.find(template.name()) is None:
                group.appendToFolder(folder, template)
                repaired.append(template.name())
        if repaired and save:
            definition.setParmTemplateGroup(group)
            asset.matchCurrentDefinition()
            hou.hipFile.save()
        return {"status":"REPAIRED" if repaired else "UNCHANGED","save":save,
            "revision":MARKER,"contract":CONTRACT_VERSION,"parameters":repaired}
    if PREVIOUS_MARKER not in comment:
        raise RuntimeError("V7 requires the exact persisted V6.1 marker")
    asset.allowEditingOfContents()
    core = asset.node("StreetBuildingCore")
    for name, expected in EXPECTED_SNIPPETS.items():
        node = core.node(name)
        if node is None or _sha(node.parm("snippet").eval()) != expected:
            raise RuntimeError(f"V7 precondition hash failed: {name}")
    changed = ["parm:" + name for name in _add_parameters(asset)]
    core.node("INTERNAL_TEST_PARCEL").parm("snippet").set(INTERNAL_PARCEL); changed.append("INTERNAL_TEST_PARCEL")
    core.node("PARSE_UNITY_INSTANCE_CATALOG").parm("snippet").set(PARSER); changed.append("PARSE_UNITY_INSTANCE_CATALOG")

    front = core.node("DIRECT_UNITY_INSTANCE_FACADE")
    front_text = _upgrade_common(front.parm("snippet").eval()).replace("sb_schema(catalog) != 2", "sb_schema(catalog) < 2")
    front.parm("snippet").set(front_text.replace("STREETBUILDING_V6_1_FRONT_HEIGHTS", "STREETBUILDING_V7_FRONT")); changed.append(front.name())

    side = core.node("BUILD_DIRECT_SIDE_REAR_INSTANCES")
    side_text = _upgrade_common(side.parm("snippet").eval())
    side_text = _replace_body(side_text, "// STREETBUILDING_V6_1_SIDE_REAR_HEIGHTS", SIDE_HELPER, SIDE_BODY)
    side.parm("snippet").set(side_text); changed.append(side.name())

    roof = core.node("BUILD_DIRECT_ROOF_INSTANCES")
    roof_text = _replace_body(_upgrade_common(roof.parm("snippet").eval()), "// STREETBUILDING_V6_1_ROOF_SHELL", "", ROOF_BODY)
    roof.parm("snippet").set(roof_text); changed.append(roof.name())

    edge = core.node("BUILD_DIRECT_ROOF_EDGE_INSTANCES")
    edge_text = _replace_body(_upgrade_common(edge.parm("snippet").eval()), "// STREETBUILDING_V6_1_ROOF_EDGE_INSTANCES", EDGE_HELPER, EDGE_BODY)
    edge.parm("snippet").set(edge_text); changed.append(edge.name())

    detail = core.node("DETAIL_INSTANCE_POINTS")
    detail.parm("snippet").set(_patch_detail(detail.parm("snippet").eval())); changed.append(detail.name())
    for name in ("VALIDATE_DIRECT_BUILDING_INSTANCES", "VALIDATE_DIRECT_DETAIL_INSTANCES", "BUILD_METADATA", "RESOLVE_MASSING"):
        node = core.node(name); node.parm("snippet").set(_patch_simple_metadata(node.parm("snippet").eval())); changed.append(name)

    validation = _validate(asset)
    if save:
        definition.updateFromNode(asset)
        definition.setParmTemplateGroup(asset.parmTemplateGroup())
        definition.setComment((definition.comment() or "").replace(PREVIOUS_MARKER, MARKER))
        asset.matchCurrentDefinition()
        hou.hipFile.save()
    return {"status":"UPDATED","save":save,"revision":MARKER,"contract":CONTRACT_VERSION,
        "nodes":changed,"validation":validation}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--project-root", required=True, type=Path)
    parser.add_argument("--save", choices=("true", "false"), default="false")
    args = parser.parse_args()
    root = args.project_root.resolve(); hda = (root/REL_HDA).resolve(); hip = (root/REL_HIP).resolve()
    before = (hashlib.sha256(hda.read_bytes()).hexdigest(), hashlib.sha256(hip.read_bytes()).hexdigest())
    hou.hipFile.load(str(hip), suppress_save_prompt=True, ignore_load_warnings=False)
    hou.hda.installFile(str(hda), change_oplibraries_file=False, force_use_assets=True)
    result = apply_loaded(hou.node(ASSET_PATH), args.save == "true")
    after = (hashlib.sha256(hda.read_bytes()).hexdigest(), hashlib.sha256(hip.read_bytes()).hexdigest())
    if args.save == "false" and before != after:
        raise RuntimeError("V7 save=False modified persisted HDA/HIP bytes")
    result["files"] = {"hda":after[0],"hip":after[1]}
    print(json.dumps(result, indent=2))


if __name__ == "__main__": main()
