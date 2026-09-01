"""Add SBV4 StyleConfig and deterministic facade-rule stages to StreetBuilding.

The patch is incremental over the exact persisted V8 definition.  It operates on
the current live asset, defaults to save=False, and only persists after the
cumulative regression gate has passed.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

try:
    import hou
except ModuleNotFoundError:
    import builtins
    hou = builtins.hou


ASSET_PATH = "/obj/StreetBuilding_DEV"
ASSET_TYPE = "pcgbike::StreetBuilding::1.0"
PREVIOUS_MARKER = "STREETBUILDING_V8_CORNER_AC_ATTACHMENT"
MARKER = "STREETBUILDING_V9_STYLECONFIG_SBV4_RULES"
CONTRACT_VERSION = "StreetBuilding.StyleConfig.9.0"
REL_HDA = Path("Assets/PCG/HDA/City/StreetBuilding.hda")
REL_HIP = Path("HoudiniProject/PCG_Track_21.0.440/PCG_Bike_StreetBuilding.hip")

EXPECTED_SNIPPETS = {
    "CANONICALIZE_PARCELS": "c3df1921f55bef01d6f9cdb604ac2d161c13e5b573503b53b4bea35d47a260e8",
    "RESOLVE_FRONTAGES": "d7b9ab1aa8c3cd2798ce4e1993ffc7aada16081085cf0cf272342f32cdde6d12",
    "RESOLVE_MASSING": "11020dac9f4eb7ee154c6f7d2a0111fbeabe2d3df2409a7fdb377ac979968742",
    "RESOLVE_FACADE_GRAMMAR": "80c0721bb03b4fd044a1f6266243bf2964fda930462e12217a6117f9291c2acc",
    "PARSE_UNITY_INSTANCE_CATALOG": "b906fc37c1c2027cf4ba696aae2c208c1700d58e57208203f499dedf58fe3948",
    "DIRECT_UNITY_INSTANCE_FACADE": "9ee282a028de03b31e004cb5ef641de00f628f1f2d3025a4e26f7255608dcc1a",
    "BUILD_DIRECT_SIDE_REAR_INSTANCES": "f95d988e015cf3d0544da83c446d8b008c0927e23201ddbfdc51593f66428ed8",
    "BUILD_DIRECT_ROOF_INSTANCES": "8c5e0213f0555dfe31e22b79c07463ebfbbf203bec6cee64bbe1d5a29f23cda7",
    "BUILD_DIRECT_ROOF_EDGE_INSTANCES": "a25cc4fd5b6b2baba672bbfd1e1a085e1a739645ed4751febbb0f39d1279829f",
    "DETAIL_INSTANCE_POINTS": "c14780e1b7004627ca4faa886054174c06ecda049a25108248363f0f61712628",
    "VALIDATE_DIRECT_BUILDING_INSTANCES": "493762594d1d659cf9e40e8ee5ad05354c6b8d1d11548c461b40d5621d44d5ca",
    "VALIDATE_DIRECT_DETAIL_INSTANCES": "718490c2d5ca7f5687a2e8fa341e945fd40b5a4f3f0dd27269c9d5b127fd4ef7",
    "BUILD_METADATA": "cfb1927d1cb7a2e6a102f87101f56c63bde857aafaab4f904c55d296d6132c1f",
}

ROLE_NAMES = (
    "GroundShop", "GroundShopDoor", "GroundWall", "Entrance", "MiddleWindow",
    "MiddleBlank", "CornerConvex", "CornerConcave", "Cornice", "Parapet",
    "SideWall", "RearWall", "FacadeColumn", "FloorBand", "Awning", "Sign",
    "FireEscape", "ACUnit", "RoofProp", "RoofSurface", "ParapetCorner",
    "ParapetConcaveCorner",
)


def _sha(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _replace_once(text: str, old: str, new: str, label: str) -> str:
    if text.count(old) != 1:
        raise RuntimeError(f"V9 precondition failed for {label}: expected one exact match")
    return text.replace(old, new, 1)


PARSER = r'''// STREETBUILDING_V9_SBV4_STYLE_PARSER
string sbv9_role_name(int role)
{
    string names[] = array("GroundShop","GroundShopDoor","GroundWall","Entrance",
        "MiddleWindow","MiddleBlank","CornerConvex","CornerConcave","Cornice",
        "Parapet","SideWall","RearWall","FacadeColumn","FloorBand","Awning",
        "Sign","FireEscape","ACUnit","RoofProp","RoofSurface","ParapetCorner",
        "ParapetConcaveCorner");
    return role >= 0 && role < len(names) ? names[role] : "";
}

string catalog = chs("../../unity_instance_catalog");
if (chi("../../module_source") != 1)
{
    setdetailattrib(0, "catalog_schema", 0, "set");
    setdetailattrib(0, "catalog_module_rows", 0, "set");
    setdetailattrib(0, "module_family", "internal_proxy", "set");
    setdetailattrib(0, "catalog_payload", "", "set");
    return;
}
if (len(strip(catalog)) == 0)
    error("StreetBuilding Unity Asset Instances requires a compiled StyleConfig payload");

string rows[] = split(catalog, "\n");
string header[] = len(rows) > 0 ? split(strip(rows[0]), "|") : array();
int schema = 1;
string family = "legacy";
float cell_width = 2.0;
float ground_height = 4.0;
float typical_height = 3.0;
string normalized = catalog;
if (len(header) == 5 && header[0] == "SBV4")
{
    schema = 4;
    family = header[1];
    cell_width = atof(header[2]);
    ground_height = atof(header[3]);
    typical_height = atof(header[4]);
    if (family != chs("../../style_id"))
        error("StreetBuilding SBV4 style header does not match style_id");
    if (cell_width <= 0 || ground_height <= 0 || typical_height <= 0)
        error("StreetBuilding SBV4 dimensions must be positive");
    normalized = sprintf("SBV4|%s|%g|%g|%g", family, cell_width,
        ground_height, typical_height);
    int count = 0;
    foreach (string row; rows)
    {
        string f[] = split(strip(row), "|");
        if (len(f) == 0 || f[0] != "M") continue;
        if (len(f) != 18)
            error("StreetBuilding SBV4 contains an invalid module row");
        string role = sbv9_role_name(atoi(f[2]));
        float width = max(1, atoi(f[5])) * cell_width;
        float height = atof(f[8]) > 0 ? atof(f[8]) : max(.001, atof(f[13]));
        float weight = atof(f[9]);
        if (len(role) == 0 || len(f[3]) == 0 || len(f[4]) == 0 || weight <= 0)
            error("StreetBuilding SBV4 module identity/weight is invalid");
        normalized += sprintf("\nM|%s|%s|0|%s|0|0|0|0|0|0|%g|%g|%g",
            role, f[3], f[4], width, height, weight);
        count++;
    }
    if (count == 0) error("StreetBuilding SBV4 has no enabled module rows");
}
else if ((len(header) == 5 && header[0] == "SBV2")
    || (len(header) == 6 && header[0] == "SBV3"))
{
    schema = header[0] == "SBV3" ? 3 : 2;
    family = schema == 3 ? strip(header[5]) : "legacy";
    cell_width = atof(header[2]); ground_height = atof(header[3]);
    typical_height = atof(header[4]);
    if (header[1] != chs("../../style_id"))
        error("StreetBuilding catalog style header does not match style_id");
}

int module_rows = 0;
foreach (string row; split(normalized, "\n"))
{
    string f[] = split(strip(row), "|");
    if (schema >= 2 && len(f) > 0 && f[0] == "M")
    {
        if (len(f) != 14 || atof(f[13]) <= 0 || atof(f[11]) <= 0 || atof(f[12]) <= 0)
            error("StreetBuilding normalized module row is invalid");
        module_rows++;
    }
    if (schema == 1 && len(f) == 10) module_rows++;
}
if (module_rows == 0) error("StreetBuilding catalog has no module rows");
setdetailattrib(0, "catalog_schema", schema, "set");
setdetailattrib(0, "catalog_module_rows", module_rows, "set");
setdetailattrib(0, "module_family", family, "set");
setdetailattrib(0, "style_cell_width", cell_width, "set");
setdetailattrib(0, "style_ground_height", ground_height, "set");
setdetailattrib(0, "style_typical_height", typical_height, "set");
setdetailattrib(0, "catalog_payload", normalized, "set");
'''


PARSE_RULES = r'''// STREETBUILDING_V9_PARSE_GENERATION_RULES
void sbv9_apply_global(string payload; export float width; export float depth;
    export int shape; export float notch_w; export float notch_d; export int notch_side;
    export int floors; export int corner; export int ground_use; export int mode;
    export int rhythm; export float shop_ratio; export int side_mode; export int rear_mode;
    export int roof; export float parapet; export int trim; export int attachments;
    export float detail_density; export int seed)
{
    foreach (string row; split(payload, "\n"))
    {
        string f[] = split(strip(row), "|");
        if (len(f) != 21 || f[0] != "G") continue;
        if (atof(f[1]) > 0) width = atof(f[1]);
        if (atof(f[2]) > 0) depth = atof(f[2]);
        shape=atoi(f[3]); notch_w=atof(f[4]); notch_d=atof(f[5]); notch_side=atoi(f[6]);
        if (atoi(f[7]) > 0) floors=atoi(f[7]);
        corner=atoi(f[8]); ground_use=atoi(f[9]); mode=atoi(f[10]); rhythm=atoi(f[11]);
        shop_ratio=atof(f[12]); side_mode=atoi(f[13]); rear_mode=atoi(f[14]);
        roof=atoi(f[15]); parapet=atof(f[16]); trim=atoi(f[17]); attachments=atoi(f[18]);
        detail_density=atof(f[19]); seed=atoi(f[20]);
    }
}

string unity_payload = chs("../../unity_generation_rules");
string parcel_payload = "";
if (nprimitives(0) > 0 && hasprimattrib(0, "streetbuilding_rule_payload"))
    parcel_payload = string(prim(0, "streetbuilding_rule_payload", 0));

float width=ch("../../internal_width"); float depth=ch("../../internal_depth");
int shape=chi("../../massing_shape"); float notch_w=ch("../../notch_width");
float notch_d=ch("../../notch_depth"); int notch_side=chi("../../notch_side");
int floors=max(1,chi("../../floor_count")); int corner=chi("../../corner_building");
int ground_use=chi("../../ground_use"); int mode=chi("../../facade_control_mode");
int rhythm=chi("../../facade_rhythm"); float shop_ratio=ch("../../shopfront_ratio");
int side_mode=chi("../../side_mode"); int rear_mode=chi("../../rear_mode");
int roof=chi("../../generate_roof"); float parapet=ch("../../parapet_height");
int trim=chi("../../generate_architectural_trim"); int attachments=chi("../../generate_attachments");
float detail_density=ch("../../detail_density"); int seed=chi("../../seed");
sbv9_apply_global(unity_payload,width,depth,shape,notch_w,notch_d,notch_side,floors,
    corner,ground_use,mode,rhythm,shop_ratio,side_mode,rear_mode,roof,parapet,trim,
    attachments,detail_density,seed);
sbv9_apply_global(parcel_payload,width,depth,shape,notch_w,notch_d,notch_side,floors,
    corner,ground_use,mode,rhythm,shop_ratio,side_mode,rear_mode,roof,parapet,trim,
    attachments,detail_density,seed);

if (len(strip(unity_payload)) == 0)
{
    unity_payload = "SBR1";
    int count = chi("../../facade_overrides");
    for (int i=1; i<=count; i++)
        unity_payload += sprintf("\nO|%d|%d|%d|%d|%d|%d|%d|%d|%d|%d|%d|%d|%d|%d|%d",
            chi(sprintf("../../override_facade%d",i)),chi(sprintf("../../override_floor_from%d",i)),
            chi(sprintf("../../override_floor_to%d",i)),chi(sprintf("../../override_mode%d",i)),
            chi(sprintf("../../override_rhythm%d",i)),chi(sprintf("../../override_entrance_min%d",i)),
            chi(sprintf("../../override_entrance_max%d",i)),chi(sprintf("../../override_shopdoor_min%d",i)),
            chi(sprintf("../../override_shopdoor_max%d",i)),chi(sprintf("../../override_shopfront_min%d",i)),
            chi(sprintf("../../override_shopfront_max%d",i)),chi(sprintf("../../override_window_min%d",i)),
            chi(sprintf("../../override_window_max%d",i)),chi(sprintf("../../override_blank_min%d",i)),
            chi(sprintf("../../override_blank_max%d",i)));
    int acount = chi("../../attachment_rules");
    for (int i=1; i<=acount; i++)
        unity_payload += sprintf("\nA|%d|%g|%d|%d|%d|%d",
            chi(sprintf("../../attachment_kind%d",i)),chf(sprintf("../../attachment_density%d",i)),
            chi(sprintf("../../attachment_max%d",i)),chi(sprintf("../../attachment_facade_mask%d",i)),
            chi(sprintf("../../attachment_floor_from%d",i)),chi(sprintf("../../attachment_floor_to%d",i)));
}

for (int p=0; p<nprimitives(0); p++)
{
    setprimattrib(0,"floor_count",p,floors,"set"); setprimattrib(0,"seed",p,seed,"set");
    setprimattrib(0,"rear_mode",p,rear_mode,"set"); setprimattrib(0,"side_mode",p,side_mode,"set");
}
setdetailattrib(0,"rule_payload_unity",unity_payload,"set");
setdetailattrib(0,"rule_payload_parcel",parcel_payload,"set");
setdetailattrib(0,"rule_source",len(strip(parcel_payload))?"parcel":len(strip(chs("../../unity_generation_rules")))?"unity_preset":"hda","set");
setdetailattrib(0,"effective_width",width,"set"); setdetailattrib(0,"effective_depth",depth,"set");
setdetailattrib(0,"effective_shape",shape,"set"); setdetailattrib(0,"effective_notch_width",notch_w,"set");
setdetailattrib(0,"effective_notch_depth",notch_d,"set"); setdetailattrib(0,"effective_notch_side",notch_side,"set");
setdetailattrib(0,"effective_floor_count",floors,"set"); setdetailattrib(0,"effective_corner",corner,"set");
setdetailattrib(0,"effective_ground_use",ground_use,"set"); setdetailattrib(0,"effective_facade_mode",mode,"set");
setdetailattrib(0,"effective_rhythm",rhythm,"set"); setdetailattrib(0,"effective_shopfront_ratio",clamp(shop_ratio,0,1),"set");
setdetailattrib(0,"effective_side_mode",side_mode,"set"); setdetailattrib(0,"effective_rear_mode",rear_mode,"set");
setdetailattrib(0,"effective_generate_roof",roof,"set"); setdetailattrib(0,"effective_parapet",max(0,parapet),"set");
setdetailattrib(0,"effective_trim",trim,"set"); setdetailattrib(0,"effective_attachments",attachments,"set");
setdetailattrib(0,"effective_detail_density",clamp(detail_density,0,1),"set"); setdetailattrib(0,"effective_seed",seed,"set");
'''


BUILD_CELLS = r'''// STREETBUILDING_V9_BUILD_FACADE_CELLS
void sbv9_cell(int target; int face; string surface; vector origin; vector right;
    vector outward; float yaw; int local_cell; int run_count; int serial; int floor;
    float cell_width)
{
    int pt=addpoint(0,origin+right*((local_cell+.5)*cell_width));
    setpointattrib(0,"facade_target",pt,target,"set"); setpointattrib(0,"face_index",pt,face,"set");
    setpointattrib(0,"surface_role",pt,surface,"set"); setpointattrib(0,"cell_index",pt,serial,"set");
    setpointattrib(0,"run_local_cell",pt,local_cell,"set"); setpointattrib(0,"run_cell_count",pt,run_count,"set");
    setpointattrib(0,"floor_index",pt,floor,"set"); setpointattrib(0,"floor_1based",pt,floor+1,"set");
    setpointattrib(0,"placement_origin",pt,origin,"set"); setpointattrib(0,"placement_right",pt,right,"set");
    setpointattrib(0,"placement_outward",pt,outward,"set"); setpointattrib(0,"placement_yaw",pt,yaw,"set");
    setpointattrib(0,"local_u",pt,(local_cell+.5)*cell_width,"set");
}
void sbv9_run(int target; int face; string surface; vector origin; vector right;
    vector outward; float yaw; int count; export int serial; int floors; float cw)
{
    for (int floor=0;floor<floors;floor++) for (int c=0;c<count;c++)
        sbv9_cell(target,face,surface,origin,right,outward,yaw,c,count,serial+c,floor,cw);
    serial+=count;
}

float cw=detail(1,"style_cell_width",0); if (cw<=0) cw=2;
float width=detail(0,"effective_width",0); float depth=detail(0,"effective_depth",0);
int wc=int(rint(width/cw)); int dc=int(rint(depth/cw)); int floors=max(1,detail(0,"effective_floor_count",0));
int shape=detail(0,"effective_shape",0); int side_mode=detail(0,"effective_side_mode",0);
int rear_mode=detail(0,"effective_rear_mode",0); int corner=detail(0,"effective_corner",0);
float nw=detail(0,"effective_notch_width",0); float nd=detail(0,"effective_notch_depth",0);
int nwc=int(rint(nw/cw)); int ndc=int(rint(nd/cw)); int ns=detail(0,"effective_notch_side",0);
if (wc<2 || dc<2 || abs(width-wc*cw)>.01 || abs(depth-dc*cw)>.01)
    error("StreetBuilding parcel dimensions must follow the Style Cell grid");
if (shape==1 && (nwc<1 || ndc<1 || wc-nwc<2 || dc-ndc<2))
    error("StreetBuilding L notch must preserve two-cell wings");
for (int p=nprimitives(0)-1;p>=0;p--) removeprim(0,p,1);
int serial=0;
sbv9_run(0,0,"front",set(-width*.5,0,0),set(1,0,0),set(0,0,1),0,wc,serial,floors,cw);
if (shape==0)
{
    if (side_mode!=1)
    {
        sbv9_run(2,1,"left",set(-width*.5,0,-depth),set(0,0,1),set(-1,0,0),90,dc,serial,floors,cw);
        sbv9_run(corner?1:2,2,corner?"secondary_front":"right",set(width*.5,0,0),set(0,0,-1),set(1,0,0),-90,dc,serial,floors,cw);
    }
    if (rear_mode!=0) sbv9_run(3,3,"rear",set(width*.5,0,-depth),set(-1,0,0),set(0,0,-1),-180,wc,serial,floors,cw);
}
else if (ns==0)
{
    if (side_mode!=1)
    {
        sbv9_run(corner?1:2,2,corner?"secondary_front":"right",set(width*.5,0,0),set(0,0,-1),set(1,0,0),-90,dc,serial,floors,cw);
        sbv9_run(2,1,"notch_inner",set(-width*.5+nw,0,-depth),set(0,0,1),set(-1,0,0),90,ndc,serial,floors,cw);
        sbv9_run(2,1,"left",set(-width*.5,0,-depth+nd),set(0,0,1),set(-1,0,0),90,dc-ndc,serial,floors,cw);
    }
    if (rear_mode!=0)
    {
        sbv9_run(3,3,"rear",set(width*.5,0,-depth),set(-1,0,0),set(0,0,-1),-180,wc-nwc,serial,floors,cw);
        sbv9_run(3,3,"notch_rear",set(-width*.5+nw,0,-depth+nd),set(-1,0,0),set(0,0,-1),-180,nwc,serial,floors,cw);
    }
}
else
{
    if (side_mode!=1)
    {
        sbv9_run(2,1,"left",set(-width*.5,0,-depth),set(0,0,1),set(-1,0,0),90,dc,serial,floors,cw);
        sbv9_run(2,2,"notch_inner",set(width*.5-nw,0,-depth),set(0,0,1),set(1,0,0),-90,ndc,serial,floors,cw);
        sbv9_run(corner?1:2,2,corner?"secondary_front":"right",set(width*.5,0,0),set(0,0,-1),set(1,0,0),-90,dc-ndc,serial,floors,cw);
    }
    if (rear_mode!=0)
    {
        sbv9_run(3,3,"rear",set(width*.5-nw,0,-depth),set(-1,0,0),set(0,0,-1),-180,wc-nwc,serial,floors,cw);
        sbv9_run(3,3,"notch_rear",set(width*.5,0,-depth+nd),set(-1,0,0),set(0,0,-1),-180,nwc,serial,floors,cw);
    }
}
setdetailattrib(0,"streetbuilding_cell_count",npoints(0),"set");
'''


ALLOCATE = r'''// STREETBUILDING_V9_ALLOCATE_FACADE_CAPACITY
int sbv9_override(string payload; int target; int floor; export int mode; export int rhythm;
    export int emin; export int emax; export int dmin; export int dmax;
    export int smin; export int smax; export int wmin; export int wmax;
    export int bmin; export int bmax)
{
    int found=0;
    foreach (string row;split(payload,"\n"))
    {
        string f[]=split(strip(row),"|");
        if (len(f)!=16 || f[0]!="O" || atoi(f[1])!=target || floor<atoi(f[2]) || floor>atoi(f[3])) continue;
        mode=atoi(f[4]); rhythm=atoi(f[5]); emin=atoi(f[6]); emax=atoi(f[7]);
        dmin=atoi(f[8]); dmax=atoi(f[9]); smin=atoi(f[10]); smax=atoi(f[11]);
        wmin=atoi(f[12]); wmax=atoi(f[13]); bmin=atoi(f[14]); bmax=atoi(f[15]); found=1;
    }
    return found;
}
int sbv9_range(int lo; int hi; int key)
{
    lo=max(0,min(lo,hi)); hi=max(lo,max(lo,hi));
    return lo+int(floor(rand(float(key)*.173+13.7)*(hi-lo+1)));
}

string unity=detail(0,"rule_payload_unity",0); string parcel=detail(0,"rule_payload_parcel",0);
int global_mode=detail(0,"effective_facade_mode",0); int global_rhythm=detail(0,"effective_rhythm",0);
int ground_use=detail(0,"effective_ground_use",0); float ratio=detail(0,"effective_shopfront_ratio",0);
int seed=detail(0,"effective_seed",0); string report=""; int compressed_any=0;
for (int target=0;target<4;target++) for (int floor=1;floor<=detail(0,"effective_floor_count",0);floor++)
{
    int pts[];
    for (int p=0;p<npoints(0);p++) if (point(0,"facade_target",p)==target && point(0,"floor_1based",p)==floor) append(pts,p);
    int cap=len(pts); if (cap==0) continue;
    int mode=global_mode; int rhythm=global_rhythm;
    int emin=chi("../../entrance_count_min"),emax=chi("../../entrance_count_max");
    int dmin=chi("../../shopdoor_count_min"),dmax=chi("../../shopdoor_count_max");
    int smin=chi("../../shopfront_count_min"),smax=chi("../../shopfront_count_max");
    int wmin=chi("../../window_count_min"),wmax=chi("../../window_count_max");
    int bmin=chi("../../blank_count_min"),bmax=chi("../../blank_count_max");
    int overridden=sbv9_override(unity,target,floor,mode,rhythm,emin,emax,dmin,dmax,smin,smax,wmin,wmax,bmin,bmax);
    overridden=max(overridden,sbv9_override(parcel,target,floor,mode,rhythm,emin,emax,dmin,dmax,smin,smax,wmin,wmax,bmin,bmax));
    int e=0,d=0,s=0,w=0,b=0; int key=seed*1009+target*503+floor*101;
    if (!overridden && mode==0)
    {
        if (floor==1 && target<=1)
        {
            e=target==0?1:0; d=(ground_use>=2 && cap-e>0)?1:0;
            s=ground_use>=2?clamp(int(rint((cap-e-d)*ratio)),0,cap-e-d):0; b=cap-e-d-s;
        }
        else if (floor>1) { w=target<=1?max(1,int(rint(cap*.75))):int(rint(cap*.55)); b=cap-w; }
        else b=cap;
    }
    else if (mode==0)
    {
        e=emin; d=dmin; s=smin; w=wmin; b=bmin;
        if (e+d+s+w+b==0) b=cap;
    }
    else
    {
        e=mode==2?emin:sbv9_range(emin,emax,key+11); d=mode==2?dmin:sbv9_range(dmin,dmax,key+23);
        s=mode==2?smin:sbv9_range(smin,smax,key+37); w=mode==2?wmin:sbv9_range(wmin,wmax,key+47);
        b=mode==2?bmin:sbv9_range(bmin,bmax,key+59);
    }
    int re=e,rd=d,rs=s,rw=w,rb=b; int overflow=max(0,re+rd+rs+rw+rb-cap); string reason="none";
    int cut=min(rb,overflow); rb-=cut; overflow-=cut;
    cut=min(rw,overflow); rw-=cut; overflow-=cut;
    cut=min(rs,overflow); rs-=cut; overflow-=cut;
    int keep_e=(target==0 && floor==1 && re>0)?1:0; int keep_d=(floor==1 && rd>0)?1:0;
    cut=min(max(0,re-keep_e),overflow); re-=cut; overflow-=cut;
    cut=min(max(0,rd-keep_d),overflow); rd-=cut; overflow-=cut;
    cut=min(rd,overflow); rd-=cut; overflow-=cut; cut=min(re,overflow); re-=cut; overflow-=cut;
    if (re+rd+rs+rw+rb<cap) rb+=cap-(re+rd+rs+rw+rb);
    int was_compressed=(e+d+s+w+b)>cap; if (was_compressed) {compressed_any=1;reason="functional_priority";}
    float scores[]; foreach (int p;pts)
    {
        int c=point(0,"cell_index",p); float score=rand(float(key+c*37)*.719+5.1);
        if (rhythm==1) score=float(c); else if (rhythm==2) score=float(c%2)*100+c;
        else if (rhythm==3) score=abs(float(point(0,"run_local_cell",p))-(point(0,"run_cell_count",p)-1)*.5)+score*.01;
        else if (rhythm==4) score=float(c/2)+score*.01; append(scores,score);
    }
    int order[]=argsort(scores);
    for (int rank=0;rank<cap;rank++)
    {
        int p=pts[order[rank]]; string semantic=rank<re?"entrance":rank<re+rd?"shop_door":
            rank<re+rd+rs?"shopfront":rank<re+rd+rs+rw?"window":"blank";
        setpointattrib(0,"semantic_role",p,semantic,"set"); setpointattrib(0,"rule_mode",p,mode,"set");
        setpointattrib(0,"rule_rhythm",p,rhythm,"set"); setpointattrib(0,"rule_compressed",p,was_compressed,"set");
        setpointattrib(0,"requested_total",p,e+d+s+w+b,"set"); setpointattrib(0,"resolved_total",p,cap,"set");
    }
    report+=sprintf("T%dF%d:req[%d,%d,%d,%d,%d]>res[%d,%d,%d,%d,%d]:%s;",
        target,floor,e,d,s,w,b,re,rd,rs,rw,rb,reason);
}
setdetailattrib(0,"streetbuilding_rule_report",report,"set");
setdetailattrib(0,"streetbuilding_rule_compressed",compressed_any,"set");
setdetailattrib(0,"streetbuilding_rule_source",string(detail(0,"rule_source",0)),"set");
'''


SELECT_MAIN = r'''// STREETBUILDING_V9_SELECT_FACADE_MODULES
string sbv9_choose_height(string catalog; string role; int selection_seed; float target_height)
{
    float total=0;
    foreach (string row;split(catalog,"\n")) { string f[]=split(strip(row),"|");
        if (len(f)==14 && f[0]=="M" && f[1]==role && atoi(f[3])==0 && abs(atof(f[12])-target_height)<.01)
            total+=max(0,atof(f[13])); }
    if (total<=0) return "";
    float pick=rand(float(selection_seed)*.731+19.17)*total; float cursor=0;
    foreach (string row;split(catalog,"\n")) { string f[]=split(strip(row),"|");
        if (len(f)!=14 || f[0]!="M" || f[1]!=role || atoi(f[3])!=0 || abs(atof(f[12])-target_height)>=.01) continue;
        cursor+=max(0,atof(f[13])); if (pick<=cursor) return f[2]; }
    return "";
}

void sbv9_emit_selected(string catalog; string role; string variant; vector origin; vector right;
    vector outward; float u; float y; float yaw; int face; string surface; int floor; int cell;
    int key; int entrance; int shop_door; int target; string semantic; int rule_mode; int compressed)
{
    int parts=sb_part_count(catalog,role,variant);
    if (parts<=0) error("StreetBuilding has no parts for %s/%s",role,variant);
    for (int part=0;part<parts;part++)
    {
        int pt=sb_add_instance(catalog,role,variant,part,origin,right,outward,u,y,yaw,face,
            surface,floor,cell,key,entrance && part==0,shop_door && part==0);
        setpointattrib(0,"facade_target",pt,target,"set");
        setpointattrib(0,"semantic_role",pt,semantic,"set");
        setpointattrib(0,"rule_mode",pt,rule_mode,"set");
        setpointattrib(0,"rule_compressed",pt,compressed,"set");
    }
}

string catalog=detail(1,"catalog_payload",0); if (sb_schema(catalog)<1) return;
int catalog_schema=sb_schema(catalog);
int original=npoints(0); int seed=detail(0,"effective_seed",0); int building_id=0;
float ground_h=detail(1,"style_ground_height",0); float typical_h=detail(1,"style_typical_height",0);
float cell_width=detail(1,"style_cell_width",0); int consumed_sources[];
for (int source=0;source<original;source++)
{
    if (find(consumed_sources,source)>=0) continue;
    int target=point(0,"facade_target",source); int face=point(0,"face_index",source);
    int floor=point(0,"floor_index",source); int cell=point(0,"cell_index",source);
    string semantic=point(0,"semantic_role",source); string surface=point(0,"surface_role",source);
    vector origin=point(0,"placement_origin",source); vector right=point(0,"placement_right",source);
    vector outward=point(0,"placement_outward",source); float yaw=point(0,"placement_yaw",source);
    float u=point(0,"local_u",source); int key=seed*1009+building_id*8191+target*503+floor*101+cell*37;
    string role=""; string variant=""; int span=1; int available_span=1; int neighbors[];
    if (target<=1)
    {
        int run_cell=point(0,"run_local_cell",source);
        for (int offset=1;offset<=8;offset++)
        {
            int neighbor=-1;
            for (int candidate=0;candidate<original;candidate++)
                if (find(consumed_sources,candidate)<0
                    && point(0,"facade_target",candidate)==target
                    && point(0,"floor_index",candidate)==floor
                    && point(0,"run_local_cell",candidate)==run_cell+offset
                    && point(0,"semantic_role",candidate)==semantic)
                { neighbor=candidate; break; }
            if (neighbor<0) break;
            append(neighbors,neighbor); available_span++;
        }
    }
    if (catalog_schema==1)
    {
        if (target!=0) continue;
        role=floor==0?(semantic=="entrance"?"Entrance":"GroundShop"):"MiddleWindow";
        variant=role=="Entrance"?"entrance_metal":role=="GroundShop"?
            ((cell%2)==0?"shop_trim":"shop_metal"):((cell/2)%2==0?"trim":"trim_single");
    }
    else if (target<=1)
    {
        if (floor==0) role=semantic=="entrance"?"Entrance":semantic=="shop_door" && sb_has_role(catalog,"GroundShopDoor")?"GroundShopDoor":
            semantic=="shop_door" || semantic=="shopfront"?"GroundShop":"GroundWall";
        else role=semantic=="window"?"MiddleWindow":"MiddleBlank";
    }
    else role=target==3?"RearWall":"SideWall";
    if (catalog_schema>=2)
        variant=(target>=2)?sbv9_choose_height(catalog,role,key,floor==0?ground_h:typical_h):sb_choose_variant(catalog,role,key,available_span,span);
    if (len(variant)==0 && target>=2 && floor>0 && semantic=="window")
    { role="MiddleWindow"; variant=sb_choose_variant(catalog,role,key,1,span); }
    if (len(variant)==0) error("StreetBuilding V9 has no compatible %s module",role);
    if (target<=1 && span>1)
    {
        for (int index=0;index<span-1 && index<len(neighbors);index++)
            append(consumed_sources,neighbors[index]);
        u+=(span-1)*cell_width*.5;
    }
    sbv9_emit_selected(catalog,role,variant,origin,right,outward,u,
        floor==0?0:ground_h+(floor-1)*typical_h,yaw,face,surface,floor,cell,key,
        semantic=="entrance",semantic=="shop_door",target,semantic,
        int(point(0,"rule_mode",source)),int(point(0,"rule_compressed",source)));
    if (floor==0 && detail(0,"effective_trim",0) && sb_has_role(catalog,"Cornice"))
    {
        int cs; string cornice=catalog_schema==1?"brick_center":sb_choose_variant(catalog,"Cornice",key+7,1,cs);
        sbv9_emit_selected(catalog,"Cornice",cornice,origin,right,outward,u,ground_h-1,yaw,
            face,surface,0,cell,key+7,0,0,target,"cornice",0,0);
    }
    if (target==0 && point(0,"run_local_cell",source)==0 && sb_has_role(catalog,"FacadeColumn"))
    {
        string column=catalog_schema==1?(floor==0?"trim_ground":"brick_upper"):
            sbv9_choose_height(catalog,"FacadeColumn",key+17,floor==0?ground_h:typical_h);
        if (len(column)==0) { int cs; column=sb_choose_variant(catalog,"FacadeColumn",key+17,1,cs); }
        sbv9_emit_selected(catalog,"FacadeColumn",column,origin,right,outward,0,
            floor==0?0:ground_h+(floor-1)*typical_h,yaw,face,surface,floor,-1,key+17,
            0,0,target,"column",0,0);
    }
}
for (int p=original-1;p>=0;p--) removepoint(0,p);
for (int prim=nprimitives(0)-1;prim>=0;prim--) removeprim(0,prim,1);
setdetailattrib(0,"streetbuilding_contract","StreetBuilding.StyleConfig.9.0","set");
setdetailattrib(0,"streetbuilding_revision","STREETBUILDING_V9_STYLECONFIG_SBV4_RULES","set");
removeattrib(0,"point","N");
'''


ATTACHMENT_RULES = r'''// STREETBUILDING_V9_SELECT_ATTACHMENT_MODULES
void sbv9_attachment(string payload; int kind; export float density; export int maximum;
    export int mask; export int floor_from; export int floor_to)
{
    foreach (string row;split(payload,"\n"))
    {
        string f[]=split(strip(row),"|"); if (len(f)!=7 || f[0]!="A" || atoi(f[1])!=kind) continue;
        density=clamp(atof(f[2]),0,1); maximum=clamp(atoi(f[3]),0,64);
        mask=atoi(f[4]); floor_from=max(1,atoi(f[5])); floor_to=max(floor_from,atoi(f[6]));
    }
}
string unity=detail(0,"rule_payload_unity",0); string parcel=detail(0,"rule_payload_parcel",0);
for (int kind=0;kind<5;kind++)
{
    float density=chf(sprintf("../../attachment_%d_density",kind));
    int maximum=chi(sprintf("../../attachment_%d_max",kind)); int mask=15; int floor_from=1; int floor_to=99;
    sbv9_attachment(unity,kind,density,maximum,mask,floor_from,floor_to);
    sbv9_attachment(parcel,kind,density,maximum,mask,floor_from,floor_to);
    setdetailattrib(0,sprintf("attachment_density_%d",kind),density,"set");
    setdetailattrib(0,sprintf("attachment_max_%d",kind),maximum,"set");
    setdetailattrib(0,sprintf("attachment_mask_%d",kind),mask,"set");
    setdetailattrib(0,sprintf("attachment_floor_from_%d",kind),floor_from,"set");
    setdetailattrib(0,sprintf("attachment_floor_to_%d",kind),floor_to,"set");
}
'''


DETAIL_MAIN = r'''// STREETBUILDING_V9_ATTACHMENT_INSTANCE_POINTS
int sbv9_emit_limited(string catalog; string role; int selection_seed; vector origin;
    vector right; vector outward; float local_u; float base_y; float yaw;
    int face; string surface; int floor; int cell; int remaining)
{
    string variant=sbv6_choose(catalog,role,selection_seed);
    int parts=len(variant)>0?sbv6_parts(catalog,role,variant):0;
    if (parts<=0 || parts>remaining) return 0;
    return sbv6_emit(catalog,role,selection_seed,origin,right,outward,local_u,
        base_y,yaw,face,surface,floor,cell);
}

int sbv9_floor_allowed(int kind; int floor_one_based)
{
    int first=int(detail(1,sprintf("attachment_floor_from_%d",kind),0));
    int last=int(detail(1,sprintf("attachment_floor_to_%d",kind),0));
    return floor_one_based>=first && floor_one_based<=last;
}

string catalog=detail(0,"catalog_payload",0);
if (chi("../../module_source")!=1 || detail(0,"catalog_schema",0)<2
    || !detail(1,"effective_attachments",0)) return;

// Input 0 can carry the external Parcel.  Detail output must contain only
// instance points, while detail attributes remain available after removal.
for (int prim=nprimitives(0)-1;prim>=0;prim--) removeprim(0,prim,1);
for (int point=npoints(0)-1;point>=0;point--) removepoint(0,point);

float master=clamp(float(detail(1,"effective_detail_density",0)),0,1);
float density[]=array(
    float(detail(1,"attachment_density_0",0)),float(detail(1,"attachment_density_1",0)),
    float(detail(1,"attachment_density_2",0)),float(detail(1,"attachment_density_3",0)),
    float(detail(1,"attachment_density_4",0)));
int maximum[]=array(
    int(detail(1,"attachment_max_0",0)),int(detail(1,"attachment_max_1",0)),
    int(detail(1,"attachment_max_2",0)),int(detail(1,"attachment_max_3",0)),
    int(detail(1,"attachment_max_4",0)));
int mask[]=array(
    int(detail(1,"attachment_mask_0",0)),int(detail(1,"attachment_mask_1",0)),
    int(detail(1,"attachment_mask_2",0)),int(detail(1,"attachment_mask_3",0)),
    int(detail(1,"attachment_mask_4",0)));
int count[]=array(0,0,0,0,0);
if (master<=0) return;

float cw=max(.001,float(detail(0,"style_cell_width",0)));
float width=float(detail(1,"effective_width",0));
float depth=float(detail(1,"effective_depth",0));
int wcells=int(rint(width/cw)); int dcells=int(rint(depth/cw));
int shape=int(detail(1,"effective_shape",0));
int nwc=int(rint(float(detail(1,"effective_notch_width",0))/cw));
int ndc=int(rint(float(detail(1,"effective_notch_depth",0))/cw));
int ns=int(detail(1,"effective_notch_side",0));
int floors=max(1,int(detail(1,"effective_floor_count",0)));
int seed=int(detail(1,"effective_seed",0));
int corner=int(detail(1,"effective_corner",0));
float ground_h=chf("../../ground_floor_height");
float typical_h=chf("../../typical_floor_height");
int emitted=0; int entrance=wcells/2;

// Awning and sign slots: primary frontage and, for corner buildings, the
// secondary frontage.  Mask bits are Front=1, Secondary=2, Side=4, Rear=8.
for (int target=0;target<2 && emitted<64;target++)
{
    if ((target==0 && !(mask[0]&1) && !(mask[1]&1))
        || (target==1 && (!corner || (!(mask[0]&2) && !(mask[1]&2))))) continue;
    int cells=target==0?wcells:dcells;
    vector origin=target==0?set(-width*.5,0,.22):set(width*.5+.22,0,0);
    vector right=target==0?set(1,0,0):set(0,0,-1);
    vector outward=target==0?set(0,0,1):set(1,0,0);
    float yaw=target==0?0:-90; int face=target==0?0:2;
    string surface=target==0?"front":"secondary_front";
    for (int cell=0;cell<cells && emitted<64;cell++)
    {
        if (target==0 && cell==entrance) continue;
        int key=seed*1009+target*503+cell*37;
        if ((mask[0]&(target==0?1:2)) && count[0]<maximum[0]
            && sbv9_floor_allowed(0,1) && rand(float(key)*.197+1)<master*density[0])
        {
            int added=sbv9_emit_limited(catalog,"Awning",key+3101,origin,right,outward,
                (cell+.5)*cw,ground_h-.95,yaw,face,surface,0,cell,
                min(64-emitted,maximum[0]-count[0]));
            emitted+=added; count[0]+=added;
        }
        if ((mask[1]&(target==0?1:2)) && count[1]<maximum[1] && emitted<64
            && sbv9_floor_allowed(1,1) && rand(float(key)*.263+7)<master*density[1])
        {
            int added=sbv9_emit_limited(catalog,"Sign",key+3203,origin,right,outward,
                (cell+.5)*cw,ground_h-1.55,yaw,face,surface,0,cell,
                min(64-emitted,maximum[1]-count[1]));
            emitted+=added; count[1]+=added;
        }
    }
}

int rear_mode=int(detail(1,"effective_rear_mode",0));
if ((mask[2]&8) && count[2]<maximum[2] && emitted<64 && rear_mode==2
    && floors>=3 && sbv9_floor_allowed(2,2)
    && rand(float(seed)*.311+9)<master*density[2])
{
    int added=sbv9_emit_limited(catalog,"FireEscape",seed*1009+3307,
        set(width*.5,0,-depth-.24),set(-1,0,0),set(0,0,-1),width*.5,
        ground_h,-180,3,"rear",1,max(0,wcells/2-1),
        min(64-emitted,maximum[2]-count[2]));
    emitted+=added; count[2]+=added;
}

// Wall AC uses independent per-kind density/max, facade mask and floor range.
for (int face=1;face<=3 && emitted<64 && count[3]<maximum[3];face++)
{
    if (face==3 && rear_mode==0) continue;
    if (face<3 && int(detail(1,"effective_side_mode",0))==1) continue;
    if (!(mask[3]&(face==3?8:4))) continue;
    int cells=face==3?wcells:dcells;
    vector origin=face==1?set(-width*.5,0,-depth):face==2?set(width*.5,0,0):set(width*.5,0,-depth);
    vector right=face==1?set(0,0,1):face==2?set(0,0,-1):set(-1,0,0);
    vector outward=face==1?set(-1,0,0):face==2?set(1,0,0):set(0,0,-1);
    float yaw=face==1?90:face==2?-90:-180;
    string surface=face==1?"left":face==2?"right":"rear";
    for (int floor_one=2;floor_one<=floors && emitted<64 && count[3]<maximum[3];floor_one++)
    {
        if (!sbv9_floor_allowed(3,floor_one)) continue;
        int floor_index=floor_one-1;
        for (int cell=0;cell<cells && emitted<64 && count[3]<maximum[3];cell++)
        {
            int removed=shape==1 && face<3
                && ((ns==0 && face==1 && cell<ndc) || (ns==1 && face==2 && cell>=dcells-ndc));
            removed=max(removed,shape==1 && face==3
                && (ns==0?cell>=wcells-nwc:cell<nwc));
            if (removed || (corner && face==2)) continue;
            int key=seed*1009+face*503+floor_index*101+cell*37;
            if (rand(float(key)*.149+11)>=master*density[3]) continue;
            int added=sbv9_emit_limited(catalog,"ACUnit",key+3509,origin,right,outward,
                (cell+.5)*cw,ground_h+.65+(floor_one-2)*typical_h,yaw,face,surface,
                floor_index,cell,min(64-emitted,maximum[3]-count[3]));
            emitted+=added; count[3]+=added;
        }
    }
}

// Roof props stay one cell away from the edge and outside either L-notch.
if (count[4]<maximum[4] && emitted<64 && detail(1,"effective_generate_roof",0)
    && wcells>=3 && dcells>=3 && sbv9_floor_allowed(4,floors)
    && rand(float(seed)*.887+31)<master*density[4])
{
    int valid[];
    for (int z=1;z<dcells-1;z++) for (int x=1;x<wcells-1;x++)
    {
        int removed=shape==1 && z>=dcells-ndc && (ns==0?x<nwc:x>=wcells-nwc);
        if (!removed) append(valid,z*wcells+x);
    }
    if (len(valid)>0)
    {
        int pick=clamp(int(floor(rand(float(seed)*.417+3)*len(valid))),0,len(valid)-1);
        int cell=valid[pick]; int xcell=cell%wcells; int zcell=cell/wcells;
        float roof_y=ground_h+(floors-1)*typical_h;
        int added=sbv9_emit_limited(catalog,"RoofProp",seed*1009+4*503+cell*37,
            set(-width*.5,0,-(zcell+.5)*cw),set(1,0,0),set(0,0,-1),
            (xcell+.5)*cw,roof_y,0,4,"roof",floors,cell,
            min(64-emitted,maximum[4]-count[4]));
        emitted+=added; count[4]+=added;
    }
}

setdetailattrib(0,"attachment_awning_count",count[0],"set");
setdetailattrib(0,"attachment_sign_count",count[1],"set");
setdetailattrib(0,"attachment_fire_escape_count",count[2],"set");
setdetailattrib(0,"attachment_wall_ac_count",count[3],"set");
setdetailattrib(0,"attachment_roof_prop_count",count[4],"set");
setdetailattrib(0,"streetbuilding_effective_width",width,"set");
setdetailattrib(0,"streetbuilding_effective_depth",depth,"set");
setdetailattrib(0,"streetbuilding_effective_floor_count",floors,"set");
setdetailattrib(0,"streetbuilding_effective_shape",shape,"set");
setdetailattrib(0,"output_role","detail_instances","set");
setdetailattrib(0,"streetbuilding_contract","StreetBuilding.StyleConfig.9.0","set");
setdetailattrib(0,"streetbuilding_revision","STREETBUILDING_V9_STYLECONFIG_SBV4_RULES","set");
setdetailattrib(0,"streetbuilding_detail_count",npoints(0),"set");
removeattrib(0,"point","N");
'''


FILTER_FRONT = r'''// STREETBUILDING_V9_CONSUME_FRONT_SEMANTICS
for (int p=npoints(0)-1;p>=0;p--) if (point(0,"facade_target",p)>1) removepoint(0,p);
for (int prim=nprimitives(0)-1;prim>=0;prim--) removeprim(0,prim,1);
string keep[]=array("P","orient","scale","unity_instance","instance_prefix","name","building_id",
    "face_index","floor_index","cell_index","module_span","selection_seed","catalog_schema",
    "module_family","module_role","module_variant","surface_role","facade_band",
    "is_building_entrance","is_shop_entrance","lod","chunk_id","pcg_kind","pcg_variant");
string attributes[]=detailintrinsic(0,"pointattributes");
foreach (string name;attributes) if (find(keep,name)<0) removeattrib(0,"point",name);
string primitive_attributes[]=detailintrinsic(0,"primitiveattributes");
string vertex_attributes[]=detailintrinsic(0,"vertexattributes");
foreach (string name;primitive_attributes) removeattrib(0,"prim",name);
foreach (string name;vertex_attributes) removeattrib(0,"vertex",name);
setdetailattrib(0,"output_role","front_and_secondary_instances","set");
'''

FILTER_SIDE = r'''// STREETBUILDING_V9_CONSUME_SIDE_REAR_SEMANTICS
for (int p=npoints(0)-1;p>=0;p--) if (point(0,"facade_target",p)<2) removepoint(0,p);
for (int prim=nprimitives(0)-1;prim>=0;prim--) removeprim(0,prim,1);
string keep[]=array("P","orient","scale","unity_instance","instance_prefix","name","building_id",
    "face_index","floor_index","cell_index","module_span","selection_seed","catalog_schema",
    "module_family","module_role","module_variant","surface_role","facade_band",
    "is_building_entrance","is_shop_entrance","lod","chunk_id","pcg_kind","pcg_variant");
string attributes[]=detailintrinsic(0,"pointattributes");
foreach (string name;attributes) if (find(keep,name)<0) removeattrib(0,"point",name);
string primitive_attributes[]=detailintrinsic(0,"primitiveattributes");
string vertex_attributes[]=detailintrinsic(0,"vertexattributes");
foreach (string name;primitive_attributes) removeattrib(0,"prim",name);
foreach (string name;vertex_attributes) removeattrib(0,"vertex",name);
setdetailattrib(0,"output_role","side_and_rear_instances","set");
'''

CLEAN_DIRECT_INSTANCE_ATTRS = r'''// STREETBUILDING_V9_CLEAN_DIRECT_INSTANCE_ATTRS
for (int prim=nprimitives(0)-1;prim>=0;prim--) removeprim(0,prim,1);
string keep[]=array("P","orient","scale","unity_instance","instance_prefix","name","building_id",
    "face_index","floor_index","cell_index","module_span","selection_seed","catalog_schema",
    "module_family","module_role","module_variant","surface_role","facade_band",
    "is_building_entrance","is_shop_entrance","lod","chunk_id","pcg_kind","pcg_variant");
string attributes[]=detailintrinsic(0,"pointattributes");
foreach (string name;attributes) if (find(keep,name)<0) removeattrib(0,"point",name);
string primitive_attributes[]=detailintrinsic(0,"primitiveattributes");
string vertex_attributes[]=detailintrinsic(0,"vertexattributes");
foreach (string name;primitive_attributes) removeattrib(0,"prim",name);
foreach (string name;vertex_attributes) removeattrib(0,"vertex",name);
'''


def _upgrade_catalog_consumer(text: str) -> str:
    text = text.replace(
        'if (len(header) == 6 && header[0] == "SBV3") return 3;',
        'if (len(header) == 5 && header[0] == "SBV4") return 4;\n'
        '        if (len(header) == 6 && header[0] == "SBV3") return 3;')
    text = text.replace(
        'if (len(header) == 6 && header[0] == "SBV3") return header[5];',
        'if (len(header) == 5 && header[0] == "SBV4") return header[1];\n'
        '        if (len(header) == 6 && header[0] == "SBV3") return header[5];')
    text = text.replace('string catalog = chs("../../unity_instance_catalog");',
                        'string catalog = detail(0, "catalog_payload", 0);')
    text = text.replace('string catalog=chs("../../unity_instance_catalog");',
                        'string catalog=detail(0,"catalog_payload",0);')
    text = text.replace('max(2, chi("../../floor_count"))', 'max(1, chi("../../floor_count"))')
    return text.replace("StreetBuilding.DirectInstances.8.0", CONTRACT_VERSION).replace(
        "STREETBUILDING_V8_CORNER_AC_ATTACHMENT", MARKER)


def _clean_roof_consumer(text: str, edge: bool) -> str:
    text = _upgrade_catalog_consumer(text)
    guard = ('if (sb_schema(catalog)<2 || !chi("../../generate_roof")) return;'
             if edge else
             'if (sb_schema(catalog) < 2 || !chi("../../generate_roof")) return;')
    text = _replace_once(text, guard,
        guard[:-7] + "\n{\n" + CLEAN_DIRECT_INSTANCE_ATTRS + "return;\n}",
        "roof early attribute cleanup")
    if edge:
        text = _replace_once(text,
            'float parapet_h=ch("../../parapet_height"); if (parapet_h<=.001) return;',
            'float parapet_h=ch("../../parapet_height"); if (parapet_h<=.001)\n{\n'
            + CLEAN_DIRECT_INSTANCE_ATTRS + 'return;\n}',
            "roof-edge disabled attribute cleanup")
    return text + "\n" + CLEAN_DIRECT_INSTANCE_ATTRS


def _build_selector(front_text: str) -> str:
    marker = "// STREETBUILDING_V7_FRONT"
    if front_text.count(marker) != 1:
        raise RuntimeError("V9 could not isolate the persisted facade helper library")
    helpers = front_text.split(marker, 1)[0]
    helpers = _upgrade_catalog_consumer(helpers)
    return helpers + SELECT_MAIN


def _build_details(text: str) -> str:
    marker = 'string catalog = chs("../../unity_instance_catalog");'
    if text.count(marker) != 1:
        raise RuntimeError("V9 could not isolate the persisted detail helper library")
    helpers = _upgrade_catalog_consumer(text.split(marker, 1)[0])
    helpers = _replace_once(helpers,
        'int catalog_schema = 2; string module_family = "legacy";',
        'int catalog_schema = detail(0,"catalog_schema",0); string module_family = detail(0,"module_family",0);',
        "detail catalog metadata")
    old = '''        string header_rows[] = split(catalog, "\\n");
        if (len(header_rows) > 0) { string hf[] = split(strip(header_rows[0]), "|");
            if (len(hf) == 6 && hf[0] == "SBV3") { catalog_schema = 3; module_family = hf[5]; } }'''
    helpers = _replace_once(helpers, old, "", "detail legacy header parser")
    return helpers + DETAIL_MAIN


def _patch_detail_validator(text: str) -> str:
    text = _replace_once(text,
        '(role == "Awning" || role == "Sign") && (face != 0 || floor != 0)',
        '(role == "Awning" || role == "Sign") && ((face != 0 && face != 2) || floor != 0)',
        "secondary-front detail validation")
    text = _replace_once(text,
        'float width = ch("../../internal_width"); float depth = ch("../../internal_depth");',
        'float width = detail(0,"streetbuilding_effective_width",0); float depth = detail(0,"streetbuilding_effective_depth",0);',
        "effective detail dimensions")
    text = _replace_once(text,
        '(max(2, chi("../../floor_count")) - 1)',
        '(max(1, int(detail(0,"streetbuilding_effective_floor_count",0))) - 1)',
        "effective detail floor count")
    text = text.replace("StreetBuilding.DirectInstances.8.0", CONTRACT_VERSION).replace(
        PREVIOUS_MARKER, MARKER)
    text = _replace_once(text,
        'chi("../../massing_shape") == 0 ? "rectangle" : "l_shape"',
        'detail(0,"streetbuilding_effective_shape",0) == 0 ? "rectangle" : "l_shape"',
        "effective detail shape")
    return text


def _make_parameters(asset: hou.Node) -> hou.ParmTemplateGroup:
    old = asset.parmTemplateGroup()
    def existing(name: str) -> hou.ParmTemplate:
        item = old.find(name)
        if item is None:
            raise RuntimeError(f"V9 missing public parameter template {name}")
        return item

    standard = old.find("standardfolder5")
    entries = [standard] if standard is not None else []

    style = hou.FolderParmTemplate("sbv9_style", "Style / 风格", folder_type=hou.folderType.Simple)
    style.addParmTemplate(existing("module_source"))

    massing = hou.FolderParmTemplate("sbv9_massing", "Site & Massing / 地块与体块", folder_type=hou.folderType.Simple)
    for name in ("site_source","internal_width","internal_depth","massing_shape","notch_width",
                 "notch_depth","notch_side","corner_building","floor_count","ground_floor_height",
                 "typical_floor_height","parapet_height","rear_mode","side_mode","generate_roof"):
        massing.addParmTemplate(existing(name))

    facade = hou.FolderParmTemplate("sbv9_facade", "Facade Rules / 立面规则", folder_type=hou.folderType.Simple)
    facade.addParmTemplate(hou.MenuParmTemplate("facade_control_mode","Control Mode / 控制模式",
        ("auto","random_range","manual"),("Auto / 自动","Random Range / 范围随机","Manual / 精确"),default_value=0))
    for name in ("target_bay_width","minimum_bay_width","maximum_bay_width","ground_use",
                 "facade_rhythm","shopfront_ratio"):
        facade.addParmTemplate(existing(name))
    for token,label,default_min,default_max in (
        ("entrance","Entrance / 主入口",1,1),("shopdoor","Shop Door / 店门",0,1),
        ("shopfront","Shopfront / 铺面",1,4),("window","Window / 窗",2,8),
        ("blank","Blank / 空白",0,4)):
        facade.addParmTemplate(hou.IntParmTemplate(f"{token}_count_min",f"{label} Min",1,(default_min,),min=0,max=64))
        facade.addParmTemplate(hou.IntParmTemplate(f"{token}_count_max",f"{label} Max",1,(default_max,),min=0,max=64))

    overrides = hou.FolderParmTemplate("facade_overrides","Floor Overrides / 楼层覆盖",
        folder_type=hou.folderType.MultiparmBlock, default_value=0)
    overrides.addParmTemplate(hou.MenuParmTemplate("override_facade#","Facade / 立面",
        ("front","secondary_front","side","rear"),("Front","Secondary Front","Side","Rear"),default_value=0))
    overrides.addParmTemplate(hou.IntParmTemplate("override_floor_from#","Floor From",1,(1,),min=1,max=99))
    overrides.addParmTemplate(hou.IntParmTemplate("override_floor_to#","Floor To",1,(1,),min=1,max=99))
    overrides.addParmTemplate(hou.MenuParmTemplate("override_mode#","Mode",
        ("auto","random_range","manual"),("Auto","Random Range","Manual"),default_value=0))
    overrides.addParmTemplate(hou.MenuParmTemplate("override_rhythm#","Rhythm",
        ("auto","uniform","alternating","center_accent","paired"),
        ("Auto","Uniform","Alternating","Center Accent","Paired"),default_value=0))
    for token in ("entrance","shopdoor","shopfront","window","blank"):
        overrides.addParmTemplate(hou.IntParmTemplate(f"override_{token}_min#",f"{token} Min",1,(0,),min=0,max=64))
        overrides.addParmTemplate(hou.IntParmTemplate(f"override_{token}_max#",f"{token} Max",1,(0,),min=0,max=64))

    details = hou.FolderParmTemplate("sbv9_details","Details / 附件",folder_type=hou.folderType.Simple)
    for name in ("detail_density","generate_architectural_trim","generate_attachments"):
        details.addParmTemplate(existing(name))
    for kind,label,scale,maximum in ((0,"Awning / 雨棚",1.0,8),(1,"Sign / 招牌",.72,8),
            (2,"Fire Escape / 消防梯",.5,4),(3,"Wall AC / 空调",.28,16),(4,"Roof Props / 屋顶附件",.55,8)):
        details.addParmTemplate(hou.FloatParmTemplate(f"attachment_{kind}_density",f"{label} Density",1,(scale,),min=0,max=1))
        details.addParmTemplate(hou.IntParmTemplate(f"attachment_{kind}_max",f"{label} Max",1,(maximum,),min=0,max=64))
    attachment_rules = hou.FolderParmTemplate("attachment_rules","Attachment Overrides / 附件覆盖",
        folder_type=hou.folderType.MultiparmBlock,default_value=0)
    attachment_rules.addParmTemplate(hou.MenuParmTemplate("attachment_kind#","Kind",
        ("awning","sign","fire_escape","wall_ac","roof_props"),
        ("Awning","Sign","Fire Escape","Wall AC","Roof Props"),default_value=0))
    attachment_rules.addParmTemplate(hou.FloatParmTemplate("attachment_density#","Density",1,(.5,),min=0,max=1))
    attachment_rules.addParmTemplate(hou.IntParmTemplate("attachment_max#","Maximum",1,(8,),min=0,max=64))
    attachment_rules.addParmTemplate(hou.IntParmTemplate("attachment_facade_mask#","Facade Mask",1,(15,),min=0,max=15))
    attachment_rules.addParmTemplate(hou.IntParmTemplate("attachment_floor_from#","Floor From",1,(1,),min=1,max=99))
    attachment_rules.addParmTemplate(hou.IntParmTemplate("attachment_floor_to#","Floor To",1,(99,),min=1,max=99))

    random = hou.FolderParmTemplate("sbv9_random","Random / 随机",folder_type=hou.folderType.Simple)
    random.addParmTemplate(existing("seed"))
    output = hou.FolderParmTemplate("sbv9_output","Debug & Output / 调试与输出",folder_type=hou.folderType.Simple)
    for name in ("generate_lods","debug_metadata","wall_unity_material","trim_unity_material","window_unity_material"):
        output.addParmTemplate(existing(name))
    # Houdini Engine for Unity omits invisible parms from HEU_Parameters entirely.
    # Keep the bridge in a dedicated advanced folder, but HAPI-visible so the
    # project-owned Authoring inspector can write it while hiding it from artists.
    bridge = hou.FolderParmTemplate("sbv9_bridge","Advanced Bridge / Unity 自动桥接",folder_type=hou.folderType.Simple)
    style_id = existing("style_id"); style_id.hide(False); bridge.addParmTemplate(style_id)
    catalog = existing("unity_instance_catalog"); catalog.hide(False); bridge.addParmTemplate(catalog)
    rules = hou.StringParmTemplate("unity_generation_rules","Unity Generation Rules",1,("",),string_type=hou.stringParmType.Regular)
    rules.hide(False); bridge.addParmTemplate(rules)
    # Houdini Engine 8.0/HAPI drops the final child of the final Simple folder
    # when rebuilding HEU_Parameters. Keep a transport-only end marker after the
    # real payload fields so unity_generation_rules is always enumerated.
    revision = hou.StringParmTemplate("unity_bridge_revision", "Unity Bridge Revision", 1,
                                      ("SBV4",), string_type=hou.stringParmType.Regular)
    revision.hide(False); bridge.addParmTemplate(revision); bridge.hide(False)
    entries.extend((style,massing,facade,overrides,details,attachment_rules,random,output,bridge))
    return hou.ParmTemplateGroup(entries)


def _make_bridge_hapi_visible(definition: hou.HDADefinition) -> hou.ParmTemplateGroup:
    """Rebuild the hidden V9 folder so Houdini does not preserve its inherited hide flag."""
    group = definition.parmTemplateGroup()
    children = []
    for name in ("style_id", "unity_instance_catalog", "unity_generation_rules"):
        template = group.find(name)
        if template is None:
            raise RuntimeError(f"V9 persisted bridge template is missing: {name}")
        template.hide(False)
        children.append(template)
    revision = group.find("unity_bridge_revision")
    if revision is None:
        revision = hou.StringParmTemplate("unity_bridge_revision", "Unity Bridge Revision", 1,
                                          ("SBV4",), string_type=hou.stringParmType.Regular)
    revision.hide(False)
    children.append(revision)
    bridge_indices = group.findIndices("sbv9_bridge")
    if not bridge_indices:
        raise RuntimeError("V9 persisted bridge folder is missing")
    group.remove(bridge_indices)
    bridge = hou.FolderParmTemplate("sbv9_bridge", "Advanced Bridge / Unity 自动桥接",
                                    folder_type=hou.folderType.Simple)
    for template in children:
        bridge.addParmTemplate(template)
    bridge.hide(False)
    group.append(bridge)
    return group


def _ensure_node(core: hou.Node, name: str, position: tuple[float, float]) -> hou.Node:
    node = core.node(name)
    if node is None:
        node = core.createNode("attribwrangle", name)
    node.setPosition(hou.Vector2(position))
    node.parm("class").set(0)
    return node


def _cook(node: hou.Node, label: str) -> None:
    try:
        node.cook(force=True)
    except Exception as exc:
        raise RuntimeError(f"{label} cook failed: {node.errors()} {node.warnings()}") from exc
    if node.errors() or node.warnings():
        raise RuntimeError(f"{label} diagnostics: {node.errors()} {node.warnings()}")


def _test_sbv4() -> str:
    rows = ["SBV4|test_style|2|4|3"]
    def add(role: int, variant: str, path: str, width: int = 1, height: float = 3,
            weight: float = 1, facades: int = 15, floors: int = 7) -> None:
        rows.append(f"M|0|{role}|{variant}|{path}|{width}|1|2|{height}|{weight}|{facades}|{floors}|2|{height}|.2|-1|0|-.1")
    add(3,"entrance","Assets/Test/entrance.prefab",height=4); add(0,"shop","Assets/Test/shop.prefab",height=4)
    add(1,"shop_door","Assets/Test/shop_door.prefab",height=4); add(2,"ground","Assets/Test/ground.prefab",height=4)
    add(4,"window","Assets/Test/window.prefab"); add(5,"blank","Assets/Test/blank.prefab")
    add(10,"side_ground","Assets/Test/side_ground.prefab",height=4); add(10,"side_upper","Assets/Test/side_upper.prefab")
    add(11,"rear_ground","Assets/Test/rear_ground.prefab",height=4); add(11,"rear_upper","Assets/Test/rear_upper.prefab")
    add(8,"cornice","Assets/Test/cornice.prefab",height=1); add(12,"column_ground","Assets/Test/column_ground.prefab",height=4)
    add(12,"column_upper","Assets/Test/column_upper.prefab"); add(19,"roof","Assets/Test/roof.prefab",height=2,floors=4)
    add(9,"parapet","Assets/Test/parapet.prefab",height=.6,floors=4); add(20,"corner","Assets/Test/corner.prefab",height=.6,floors=4)
    add(21,"concave","Assets/Test/concave.prefab",height=.6,floors=4)
    add(14,"awning","Assets/Test/awning.prefab",height=1); add(15,"sign","Assets/Test/sign.prefab",height=1)
    add(16,"escape","Assets/Test/escape.prefab",width=2,height=6); add(17,"ac","Assets/Test/ac.prefab",height=1)
    add(18,"tank","Assets/Test/tank.prefab",height=2)
    return "\n".join(rows)


def _validate(asset: hou.Node, require_bridge_visible: bool = True) -> dict:
    core = asset.node("StreetBuildingCore")
    names = ("module_source","style_id","unity_instance_catalog","unity_generation_rules",
             "internal_width","internal_depth","floor_count","ground_floor_height",
             "typical_floor_height","parapet_height","rear_mode","side_mode","generate_roof",
             "generate_lods","seed","massing_shape","notch_width","notch_depth","notch_side",
             "corner_building","generate_attachments","detail_density","facade_control_mode",
             "attachment_0_density","attachment_0_max","attachment_1_density","attachment_1_max",
             "attachment_2_density","attachment_2_max","attachment_3_density","attachment_3_max",
             "attachment_4_density","attachment_4_max")
    group = asset.parmTemplateGroup()
    if require_bridge_visible:
        for bridge_name in ("style_id", "unity_instance_catalog", "unity_generation_rules",
                            "unity_bridge_revision"):
            template = group.find(bridge_name)
            if template is None or template.isHidden():
                raise RuntimeError(f"V9 Unity bridge must remain HAPI-visible: {bridge_name}")
    saved = {name: asset.parm(name).eval() for name in names}
    try:
        values = {"module_source":1,"style_id":"test_style","unity_instance_catalog":_test_sbv4(),
            "internal_width":12,"internal_depth":10,"floor_count":4,"ground_floor_height":4,
            "typical_floor_height":3,"parapet_height":.6,"rear_mode":2,"side_mode":2,
            "generate_roof":1,"generate_lods":0,"seed":29,"massing_shape":0,"notch_width":4,
            "notch_depth":4,"notch_side":0,"corner_building":1,"generate_attachments":1,
            "detail_density":1,"facade_control_mode":2,
            "attachment_0_density":1,"attachment_0_max":8,
            "attachment_1_density":1,"attachment_1_max":8,
            "attachment_2_density":1,"attachment_2_max":4,
            "attachment_3_density":1,"attachment_3_max":16,
            "attachment_4_density":1,"attachment_4_max":8}
        for name,value in values.items(): asset.parm(name).set(value)
        manual = "SBR1\nG|12|10|0|4|4|0|4|1|3|2|3|.65|2|2|1|.6|1|1|.6|29\nO|0|1|1|2|3|1|1|1|1|2|2|0|0|2|2"
        asset.parm("unity_generation_rules").set(manual)
        _cook(core.node("OUT_BUILDING_LOD0"),"V9 manual")
        geo=core.node("SELECT_FACADE_MODULES").geometry()
        front=[p for p in geo.points() if p.intAttribValue("facade_target")==0 and p.intAttribValue("floor_index")==0 and p.stringAttribValue("module_role") not in ("Cornice","FacadeColumn")]
        role_map={"entrance":"Entrance","shop_door":"GroundShopDoor","shopfront":"GroundShop","blank":"GroundWall"}
        counts={role:sum(p.stringAttribValue("module_role")==module for p in front)
                for role,module in role_map.items()}
        if counts!={"entrance":1,"shop_door":1,"shopfront":2,"blank":2}:
            sample=[(p.intAttribValue("facade_target"),p.intAttribValue("floor_index"),
                     p.stringAttribValue("module_role"),p.stringAttribValue("semantic_role"))
                    for p in list(geo.points())[:12]]
            raise RuntimeError(f"V9 manual exact allocation failed: {counts}, points={len(geo.points())}, sample={sample}")
        overflow=manual.rsplit("\n",1)[0]+"\nO|0|1|1|2|3|2|2|2|2|4|4|0|0|3|3"
        asset.parm("unity_generation_rules").set(overflow); _cook(core.node("ALLOCATE_FACADE_CAPACITY"),"V9 overflow")
        ag=core.node("ALLOCATE_FACADE_CAPACITY").geometry()
        if ag.intAttribValue("streetbuilding_rule_compressed")!=1 or "functional_priority" not in ag.stringAttribValue("streetbuilding_rule_report"):
            raise RuntimeError("V9 overflow compression metadata is missing")
        overflow_report=ag.stringAttribValue("streetbuilding_rule_report")
        asset.parm("massing_shape").set(1)
        for side in (0,1):
            asset.parm("notch_side").set(side); _cook(core.node("OUT_BUILDING_LOD0"),f"V9 L side {side}")
        asset.parm("massing_shape").set(0); asset.parm("notch_side").set(0); asset.parm("unity_generation_rules").set(manual)
        _cook(core.node("OUT_DETAIL_INSTANCES"),"V9 details")
        details=core.node("OUT_DETAIL_INSTANCES").geometry()
        if len(details.points())>64: raise RuntimeError("V9 detail budget exceeded 64")
        detail_roles={p.stringAttribValue("module_role") for p in details.points()}
        required={"Awning","Sign","FireEscape","ACUnit","RoofProp"}
        if not required.issubset(detail_roles):
            raise RuntimeError(f"V9 attachment groups are incomplete: {sorted(detail_roles)}")
        return {"manual_counts":counts,"overflow_report":overflow_report,
                "sbv4_schema":4,"secondary_front":sum(p.intAttribValue("facade_target")==1 for p in geo.points()),
                "detail_count":len(details.points()),"detail_roles":sorted(detail_roles),
                "unity_bridge_hapi_visible":require_bridge_visible}
    finally:
        for name,value in saved.items(): asset.parm(name).set(value)


def _validate_fresh_definition() -> dict:
    """Validate the published interface on a new locked instance, never the stale dev-node cache."""
    probe = hou.node("/obj").createNode(ASSET_TYPE)
    try:
        if probe.isEditable():
            raise RuntimeError("V9 bridge probe must use a fresh locked HDA instance")
        return _validate(probe)
    finally:
        probe.destroy()


def _validate_fresh_bridge_interface() -> dict:
    """Parameter-only migration check; cumulative geometry cooks run in VerifyFull."""
    probe = hou.node("/obj").createNode(ASSET_TYPE)
    try:
        if probe.isEditable():
            raise RuntimeError("V9 bridge probe must use a fresh locked HDA instance")
        group = probe.parmTemplateGroup()
        names = ("style_id", "unity_instance_catalog", "unity_generation_rules",
                 "unity_bridge_revision")
        for name in names:
            template = group.find(name)
            if probe.parm(name) is None or template is None or template.isHidden():
                raise RuntimeError(f"V9 Unity bridge is unavailable to HAPI: {name}")
        return {"unity_bridge_hapi_visible": True,
                "bridge_parameters": list(names), "locked": True}
    finally:
        probe.destroy()


def apply_loaded(asset: hou.Node, save: bool = False) -> dict:
    if asset is None or asset.type().name()!=ASSET_TYPE:
        raise RuntimeError(f"Expected {ASSET_PATH} {ASSET_TYPE}")
    definition=asset.type().definition()
    comment = definition.comment() if definition is not None else ""
    if definition is None or (PREVIOUS_MARKER not in comment and MARKER not in comment):
        raise RuntimeError("V9 requires the exact persisted V8 or V9 definition marker")
    core=asset.node("StreetBuildingCore")
    if core.node("SELECT_FACADE_MODULES") is not None and MARKER in core.node("SELECT_FACADE_MODULES").parm("snippet").eval():
        # Houdini may suffix folder tokens on Object HDAs; the transport fields
        # themselves retain stable public names and are what HAPI/Unity consume.
        bridge_names=("style_id","unity_instance_catalog","unity_generation_rules",
                      "unity_bridge_revision")
        definition_group=definition.parmTemplateGroup()
        bridge_visible=all(definition_group.find(name) is not None
                           and not definition_group.find(name).isHidden() for name in bridge_names)
        if not bridge_visible:
            candidate=_make_bridge_hapi_visible(definition)
            if not all(candidate.find(name) is not None and not candidate.find(name).isHidden()
                       for name in bridge_names):
                raise RuntimeError("V9 failed to build an HAPI-visible Unity bridge interface")
            if not save:
                validation=_validate(asset,require_bridge_visible=False)
                validation["unity_bridge_hapi_visible"]=True
                return {"status":"UPDATE_REQUIRED","save":False,"revision":MARKER,
                        "change":"Unity bridge visibility","validation":validation}
            definition.setParmTemplateGroup(candidate)
            asset.matchCurrentDefinition()
            validation=_validate_fresh_bridge_interface()
            hou.hipFile.save()
            return {"status":"UPDATED","save":True,"revision":MARKER,
                    "change":"Unity bridge visibility","validation":validation}
        validation=_validate_fresh_definition()
        if save:
            hou.hipFile.save()
        return {"status":"UNCHANGED","save":save,"revision":MARKER,"validation":validation}
    if not asset.matchesCurrentDefinition():
        raise RuntimeError("V9 requires the live asset to match its current definition before unlock")
    originals={}
    for name,expected in EXPECTED_SNIPPETS.items():
        node=core.node(name)
        if node is None or _sha(node.parm("snippet").eval())!=expected:
            raise RuntimeError(f"V9 precondition hash failed: {name}")
        originals[name]=node.parm("snippet").eval()
    asset.allowEditingOfContents()
    try:
        asset.setParmTemplateGroup(_make_parameters(asset))
        canonical=_replace_once(originals["CANONICALIZE_PARCELS"],
            '    setprimattrib(0, "source_prim", target_prim, source_prim, "set");',
            '''    setprimattrib(0, "source_prim", target_prim, source_prim, "set");
    if (hasprimattrib(1, "streetbuilding_rule_payload"))
        setprimattrib(0, "streetbuilding_rule_payload", target_prim,
            string(prim(1, "streetbuilding_rule_payload", source_prim)), "set");''',
            "Parcel rule payload transport")
        canonical=canonical.replace("StreetBuilding.Facade.2",CONTRACT_VERSION)
        core.node("CANONICALIZE_PARCELS").parm("snippet").set(canonical)
        parser=core.node("PARSE_UNITY_INSTANCE_CATALOG"); parser.parm("snippet").set(PARSER)
        rules=_ensure_node(core,"PARSE_GENERATION_RULES",(-5,-2)); rules.parm("snippet").set(PARSE_RULES)
        cells=_ensure_node(core,"BUILD_FACADE_CELLS",(0,-4)); cells.parm("snippet").set(BUILD_CELLS)
        allocate=_ensure_node(core,"ALLOCATE_FACADE_CAPACITY",(0,-6)); allocate.parm("snippet").set(ALLOCATE)
        select=_ensure_node(core,"SELECT_FACADE_MODULES",(0,-8)); select.parm("snippet").set(_build_selector(originals["DIRECT_UNITY_INSTANCE_FACADE"]))
        attachments=_ensure_node(core,"SELECT_ATTACHMENT_MODULES",(6,-6)); attachments.parm("snippet").set(ATTACHMENT_RULES)
        rules.setInput(0,core.node("RESOLVE_FRONTAGES")); rules.setInput(1,parser)
        core.node("RESOLVE_MASSING").setInput(0,rules)
        cells.setInput(0,rules); cells.setInput(1,parser); allocate.setInput(0,cells); select.setInput(0,allocate); select.setInput(1,parser)
        attachments.setInput(0,rules)
        front=core.node("DIRECT_UNITY_INSTANCE_FACADE"); front.setInput(0,select); front.parm("snippet").set(FILTER_FRONT)
        side=core.node("BUILD_DIRECT_SIDE_REAR_INSTANCES"); side.setInput(0,select); side.parm("snippet").set(FILTER_SIDE)
        core.node("BUILD_DIRECT_ROOF_INSTANCES").parm("snippet").set(
            _clean_roof_consumer(originals["BUILD_DIRECT_ROOF_INSTANCES"],False))
        core.node("BUILD_DIRECT_ROOF_EDGE_INSTANCES").parm("snippet").set(
            _clean_roof_consumer(originals["BUILD_DIRECT_ROOF_EDGE_INSTANCES"],True))
        detail=core.node("DETAIL_INSTANCE_POINTS"); detail.setInput(0,parser); detail.setInput(1,attachments)
        detail.parm("snippet").set(_build_details(originals["DETAIL_INSTANCE_POINTS"]))
        core.node("VALIDATE_DIRECT_DETAIL_INSTANCES").parm("snippet").set(
            _patch_detail_validator(originals["VALIDATE_DIRECT_DETAIL_INSTANCES"]))
        core.node("BUILD_METADATA").setInput(2,allocate)
        metadata=originals["BUILD_METADATA"]+'''\n// STREETBUILDING_V9_RULE_DIAGNOSTICS
setdetailattrib(0,"streetbuilding_rule_source",string(detail(2,"streetbuilding_rule_source",0)),"set");
setdetailattrib(0,"streetbuilding_rule_report",string(detail(2,"streetbuilding_rule_report",0)),"set");
setdetailattrib(0,"streetbuilding_rule_compressed",int(detail(2,"streetbuilding_rule_compressed",0)),"set");
setdetailattrib(0,"streetbuilding_contract","StreetBuilding.StyleConfig.9.0","set");
setdetailattrib(0,"streetbuilding_revision","STREETBUILDING_V9_STYLECONFIG_SBV4_RULES","set");\n'''
        core.node("BUILD_METADATA").parm("snippet").set(metadata)
        core.node("OUT_BUILDING_METADATA").setInput(0,core.node("BUILD_METADATA"))
        validation=_validate(asset)
        if save:
            definition.updateFromNode(asset)
            definition.setParmTemplateGroup(asset.parmTemplateGroup())
            definition.setComment((definition.comment() or "").replace(PREVIOUS_MARKER,MARKER))
            asset.matchCurrentDefinition(); hou.hipFile.save()
        return {"status":"UPDATED","save":save,"revision":MARKER,"contract":CONTRACT_VERSION,
                "nodes":["PARSE_GENERATION_RULES","BUILD_FACADE_CELLS","ALLOCATE_FACADE_CAPACITY",
                         "SELECT_FACADE_MODULES","SELECT_ATTACHMENT_MODULES"],"validation":validation}
    except Exception:
        if not save:
            asset.matchCurrentDefinition()
        raise


def main() -> None:
    parser=argparse.ArgumentParser(); parser.add_argument("--project-root",required=True,type=Path)
    parser.add_argument("--save",choices=("true","false"),default="false"); args=parser.parse_args()
    root=args.project_root.resolve(); hda=(root/REL_HDA).resolve(); hip=(root/REL_HIP).resolve()
    before_hda=hda.read_bytes(); before_hip=hip.read_bytes()
    try:
        hou.hipFile.load(str(hip),suppress_save_prompt=True,ignore_load_warnings=False)
        hou.hda.installFile(str(hda),change_oplibraries_file=False,force_use_assets=True)
        result=apply_loaded(hou.node(ASSET_PATH),args.save=="true")
    except Exception:
        if args.save=="true": hda.write_bytes(before_hda); hip.write_bytes(before_hip)
        raise
    if args.save=="false" and (hda.read_bytes()!=before_hda or hip.read_bytes()!=before_hip):
        raise RuntimeError("V9 save=False modified persisted HDA/HIP bytes")
    print(json.dumps(result,indent=2))


if __name__=="__main__": main()
