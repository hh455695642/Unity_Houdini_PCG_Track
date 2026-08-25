"""Build the V41 modular City Park masterplan in the captured Live Scene.

The patch is deliberately save=False.  It replaces the monolithic V20 layout
wrangle with independent boundary, surface-zone, connected-path, woodland,
exclusion, assembly and contract stages.  HDA/HIP persistence is owned by the
project regression gate after the full cumulative validator passes.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

try:
    import hou  # type: ignore
except ImportError:
    hou = None


ASSET_PATH = "/obj/CityRoad_DEV"
ASSET_TYPE = "pcgbike::CityRoad::1.0"
PARK_PATH = "CityRoadCore/CR_CITY_PARK"
MARKER = "CITYROAD_V41_PARK_MASTERPLAN_20260824"
BASELINE_SHA256 = "24feaab6331b492ec0560e5382e667687d32b653ebdd105a05634f5f2ab1638a"
SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = SCRIPT_DIR.parents[3]
EXPECTED_HIP = PROJECT_ROOT / "HoudiniProject/PCG_Track_21.0.440/PCG_Bike_CityRoad.hip"
EXPECTED_HDA = PROJECT_ROOT / "Assets/PCG/HDA/City/CityRoad.hda"


COMMON_VEX = r'''
// CITYROAD_V41_PARK_MASTERPLAN_SHARED
float cross2(vector a; vector b; vector c)
{
    return (b.x-a.x)*(c.z-a.z) - (b.z-a.z)*(c.x-a.x);
}

int point_in_polygon_xz(vector q; vector poly[])
{
    int inside = 0;
    int count = len(poly);
    for (int i=0, j=count-1; i<count; j=i++)
    {
        vector a=poly[i], b=poly[j];
        int crosses=((a.z>q.z)!=(b.z>q.z));
        if (crosses)
        {
            float x=(b.x-a.x)*(q.z-a.z)/max(abs(b.z-a.z),1e-8)+a.x;
            if (q.x<x) inside=!inside;
        }
    }
    return inside;
}

int segments_intersect_xz(vector a; vector b; vector c; vector d)
{
    float ab_c=cross2(a,b,c), ab_d=cross2(a,b,d);
    float cd_a=cross2(c,d,a), cd_b=cross2(c,d,b);
    return ((ab_c>1e-5 && ab_d<-1e-5)||(ab_c<-1e-5 && ab_d>1e-5))
        && ((cd_a>1e-5 && cd_b<-1e-5)||(cd_a<-1e-5 && cd_b>1e-5));
}

float point_segment_distance_xz(vector p; vector a; vector b)
{
    vector ab=set(b.x-a.x,0,b.z-a.z);
    vector ap=set(p.x-a.x,0,p.z-a.z);
    float t=clamp(dot(ap,ab)/max(dot(ab,ab),1e-8),0.0,1.0);
    vector q=a+ab*t;
    return length(set(p.x-q.x,0.0,p.z-q.z));
}

float lake_metric(vector p; vector center; float rx; float rz; float seed; float jitter)
{
    float nx=(p.x-center.x)/max(rx,0.1);
    float nz=(p.z-center.z)/max(rz,0.1);
    float angle=atan2(nz,nx);
    float ripple=1.0+jitter*(0.55*sin(angle*3.0+seed)+0.45*sin(angle*5.0-seed*0.37));
    return sqrt(nx*nx+nz*nz)/max(ripple,0.5);
}

vector park_entry(int source_prim; int index)
{
    if (index==0) return prim(0,"park_entry0",source_prim);
    if (index==1) return prim(0,"park_entry1",source_prim);
    if (index==2) return prim(0,"park_entry2",source_prim);
    return prim(0,"park_entry3",source_prim);
}

float ellipse_radius(vector direction; float rx; float rz)
{
    float dx=direction.x, dz=direction.z;
    return 1.0/sqrt(max(dx*dx/max(rx*rx,1e-5)+dz*dz/max(rz*rz,1e-5),1e-5));
}

float boundary_distance_xz(vector p; int source_prim)
{
    int pts[]=primpoints(0,source_prim);
    int count=len(pts);
    if (count>2 && length(vector(point(0,"P",pts[0]))-vector(point(0,"P",pts[count-1])))<0.1) count--;
    float result=1e18;
    for (int i=0;i<count;i++)
        result=min(result,point_segment_distance_xz(
            p,point(0,"P",pts[i]),point(0,"P",pts[(i+1)%count])));
    return result;
}

int park_water_mask(vector p; int source_prim)
{
    int water_enabled=chi("../../../enable_park_water");
    if (!water_enabled) return 0;
    int lake_count=prim(0,"park_lake_count",source_prim);
    float rx=prim(0,"park_lake_rx",source_prim);
    float rz=prim(0,"park_lake_rz",source_prim);
    int park_id=prim(0,"park_id",source_prim);
    int global_seed=chi("../../../park_seed");
    float jitter=clamp(chf("../../../park_path_jitter"),0.0,0.35);
    for (int li=0;li<lake_count;li++)
    {
        vector center=li==0
            ? prim(0,"park_lake_center0",source_prim)
            : prim(0,"park_lake_center1",source_prim);
        float stable_seed=float(global_seed+li*17)+float(park_id%100003)*0.001;
        if (lake_metric(p,center,rx,rz,stable_seed,jitter)<1.0)
            return 1;
    }
    return 0;
}

int park_path_class(vector p; int source_prim; float cell; export int entry_id)
{
    entry_id=-1;
    if (!chi("../../../enable_park_paths")) return 0;
    float width=max(chf("../../../park_path_width"),0.5);
    float clearance=max(chf("../../../park_tree_clearance"),0.0);
    float rx=prim(0,"park_lake_rx",source_prim);
    float rz=prim(0,"park_lake_rz",source_prim);
    vector lake=prim(0,"park_lake_center0",source_prim);
    vector hub=prim(0,"park_hub",source_prim);
    int park_id=prim(0,"park_id",source_prim);
    int global_seed=chi("../../../park_seed");
    float jitter=clamp(chf("../../../park_path_jitter"),0.0,0.35);
    float stable_seed=float(global_seed)+float(park_id%100003)*0.001;
    float metric=lake_metric(p,lake,rx,rz,stable_seed,jitter);
    float radial=(metric-1.0)*min(rx,rz);
    float loop_width=max(width,cell*1.5);
    int result=(radial>=clearance-cell*0.2
        && radial<=clearance+loop_width+cell*0.2) ? 1 : 0;
    if (length(set(p.x-hub.x,0.0,p.z-hub.z))<=max(width,cell*1.5))
        result=4;
    int entry_count=prim(0,"park_entry_count",source_prim);
    for (int ei=0;ei<entry_count;ei++)
    {
        vector entry=park_entry(source_prim,ei);
        vector direction=set(entry.x-lake.x,0,entry.z-lake.z);
        direction/=max(length(direction),1e-5);
        float radius=ellipse_radius(direction,rx,rz);
        vector ring=lake+direction*(radius+clearance+loop_width*0.5);
        float corridor_half=max(width*0.5,cell*0.8);
        if (point_segment_distance_xz(p,entry,ring)<=corridor_half)
        {
            entry_id=ei;
            float entry_length=length(set(entry.x-ring.x,0.0,entry.z-ring.z));
            result=length(set(p.x-entry.x,0.0,p.z-entry.z))
                <=max(width*2.5,entry_length*0.22) ? 3 : 2;
        }
    }
    return result;
}

void tag_surface(int prim; string role; string material; string zone;
                 string path_class; int park_id; int ix; int iz; int entry_id)
{
    setprimattrib(0,"park_output",prim,role,"set");
    string output_role=role=="exclusion" ? "park_exclusion" : role;
    setprimattrib(0,"output_role",prim,output_role,"set");
    setprimattrib(0,"park_id",prim,park_id,"set");
    setprimattrib(0,"pcg_site_type",prim,"park","set");
    setprimattrib(0,"exclude_building",prim,1,"set");
    setprimattrib(0,"park_zone",prim,zone,"set");
    setprimattrib(0,"park_path_class",prim,path_class,"set");
    setprimattrib(0,"park_entry_id",prim,entry_id,"set");
    setprimattrib(0,"park_cell_x",prim,ix,"set");
    setprimattrib(0,"park_cell_z",prim,iz,"set");
    if (material!="") setprimattrib(0,"unity_material",prim,material,"set");
    setprimattrib(0,"name",prim,sprintf("CityPark_%d_%s",park_id,role),"set");
    setprimattrib(0,"instance_prefix",prim,sprintf("CityPark/%d/%s",park_id,role),"set");
}

int add_surface_quad(vector p0; vector p1; vector p2; vector p3; float y;
                     string role; string material; string zone; string path_class;
                     int park_id; int ix; int iz; int entry_id)
{
    p0.y=y; p1.y=y; p2.y=y; p3.y=y;
    int a=addpoint(0,p0), b=addpoint(0,p1), c=addpoint(0,p2), d=addpoint(0,p3);
    int prim=addprim(0,"poly",a,b,c,d);
    int vertices[]=primvertices(0,prim);
    vector2 uvs[]=array(set(p0.x,p0.z),set(p1.x,p1.z),set(p2.x,p2.z),set(p3.x,p3.z));
    foreach (int i; int vertex; vertices)
        setvertexattrib(0,"uv",prim,i,uvs[i],"set");
    tag_surface(prim,role,material,zone,path_class,park_id,ix,iz,entry_id);
    return prim;
}

void remove_source_primitives(int count)
{
    for (int prim=count-1;prim>=0;prim--) removeprim(0,prim,1);
}
'''


ANALYZE_VEX = COMMON_VEX + r'''
// CITYROAD_V41_PARK_BOUNDARY_ANALYZE
int original_prims=nprimitives(0);
int enabled=chi("../../../enable_city_park");
int global_seed=chi("../../../park_seed");
float inset=max(chf("../../../park_boundary_inset"),0.0);
float path_width=max(chf("../../../park_path_width"),0.5);
float tree_clearance=max(chf("../../../park_tree_clearance"),0.0);
int lake_count=clamp(chi("../../../park_lake_count"),1,2);
float lake_ratio=clamp(chf("../../../park_lake_area_ratio"),0.05,0.45);
int entry_count=clamp(chi("../../../park_path_branch_count")+2,2,4);
int valid_count=0, invalid_count=0, max_boundary_samples=0, total_entries=0;

for (int source_prim=0;source_prim<original_prims;source_prim++)
{
    setprimattrib(0,"park_valid",source_prim,0,"set");
    if (!enabled) continue;
    int source_points[]=primpoints(0,source_prim);
    int source_count=len(source_points);
    int closed=int(primintrinsic(0,"closed",source_prim));
    if (source_count>2 && length(
        vector(point(0,"P",source_points[0]))-vector(point(0,"P",source_points[source_count-1])))<0.1)
    {
        closed=1;
        source_count--;
    }
    int sample_step=max(1,int(ceil(float(source_count)/512.0)));
    vector poly[];
    float heights[];
    float min_y=1e18, max_y=-1e18;
    for (int i=0;i<source_count;i+=sample_step)
    {
        vector p=point(0,"P",source_points[i]);
        append(poly,p); append(heights,p.y);
        min_y=min(min_y,p.y); max_y=max(max_y,p.y);
    }
    max_boundary_samples=max(max_boundary_samples,len(poly));
    float signed_area=0.0;
    vector centroid=0, bbmin=set(1e18,0,1e18), bbmax=set(-1e18,0,-1e18);
    foreach (int i; vector p; poly)
    {
        vector q=poly[(i+1)%len(poly)];
        signed_area+=p.x*q.z-q.x*p.z;
        centroid+=p;
        bbmin.x=min(bbmin.x,p.x); bbmin.z=min(bbmin.z,p.z);
        bbmax.x=max(bbmax.x,p.x); bbmax.z=max(bbmax.z,p.z);
    }
    float area=abs(signed_area)*0.5;
    centroid/=max(len(poly),1);
    heights=sort(heights);
    int hc=len(heights);
    centroid.y=hc%2 ? heights[hc/2]
        : (heights[max(hc/2-1,0)]+heights[hc/2])*0.5;
    int self_intersection=0;
    for (int i=0;i<len(poly)&&!self_intersection;i++)
    for (int j=i+1;j<len(poly);j++)
    {
        if (j==i || j==(i+1)%len(poly) || i==(j+1)%len(poly)) continue;
        if (segments_intersect_xz(poly[i],poly[(i+1)%len(poly)],poly[j],poly[(j+1)%len(poly)]))
            self_intersection=1;
    }
    float min_area=max(64.0,(path_width+inset+tree_clearance)*16.0);
    int valid=closed && len(poly)>=3 && !self_intersection
        && max_y-min_y<=0.25 && area>=min_area;
    if (!valid) { invalid_count++; continue; }

    float boundary_sum=0.0, boundary_square_sum=0.0;
    foreach (vector p; poly)
    {
        int qx=int(rint(p.x*100.0)), qz=int(rint(p.z*100.0));
        float h=frac(sin(float(qx)*12.9898+float(qz)*78.233)*43758.5453);
        boundary_sum+=h; boundary_square_sum+=h*h;
    }
    int qa=int(rint(area*10.0));
    float boundary_hash=rand(set(boundary_sum,boundary_square_sum,
        float(qa)+float(len(poly))*0.6180339));
    int park_id=max(1,int(floor(boundary_hash*2147483000.0)));
    float sx=max(bbmax.x-bbmin.x,1.0), sz=max(bbmax.z-bbmin.z,1.0);
    float lake_area=area*lake_ratio/max(lake_count,1);
    float radius=sqrt(lake_area/M_PI);
    float lake_rx=min(radius*1.28,sx*0.30);
    float lake_rz=min(radius/1.28,sz*0.30);
    vector lake0=set(centroid.x-sx*0.16,centroid.y,centroid.z+sz*0.10);
    vector lake1=set(centroid.x+sx*0.18,centroid.y,centroid.z-sz*0.14);
    vector hub=set(lake0.x+lake_rx+tree_clearance+path_width,centroid.y,lake0.z);

    vector targets[]=array(
        set(bbmin.x,centroid.y,centroid.z),set(bbmax.x,centroid.y,centroid.z),
        set(centroid.x,centroid.y,bbmin.z),set(centroid.x,centroid.y,bbmax.z));
    vector entries[]=array(centroid,centroid,centroid,centroid);
    for (int ei=0;ei<4;ei++)
    {
        float best=1e18;
        foreach (vector p; poly)
        {
            float d=length(set(p.x-targets[ei].x,0.0,p.z-targets[ei].z));
            if (d<best) { best=d; entries[ei]=set(p.x,centroid.y,p.z); }
        }
    }
    setprimattrib(0,"park_valid",source_prim,1,"set");
    setprimattrib(0,"park_id",source_prim,park_id,"set");
    setprimattrib(0,"park_area",source_prim,area,"set");
    setprimattrib(0,"park_center",source_prim,centroid,"set");
    setprimattrib(0,"park_bbmin",source_prim,bbmin,"set");
    setprimattrib(0,"park_bbmax",source_prim,bbmax,"set");
    setprimattrib(0,"park_entry_count",source_prim,entry_count,"set");
    setprimattrib(0,"park_entry0",source_prim,entries[0],"set");
    setprimattrib(0,"park_entry1",source_prim,entries[1],"set");
    setprimattrib(0,"park_entry2",source_prim,entries[2],"set");
    setprimattrib(0,"park_entry3",source_prim,entries[3],"set");
    setprimattrib(0,"park_lake_count",source_prim,lake_count,"set");
    setprimattrib(0,"park_lake_center0",source_prim,lake0,"set");
    setprimattrib(0,"park_lake_center1",source_prim,lake1,"set");
    setprimattrib(0,"park_lake_rx",source_prim,lake_rx,"set");
    setprimattrib(0,"park_lake_rz",source_prim,lake_rz,"set");
    setprimattrib(0,"park_hub",source_prim,hub,"set");
    valid_count++; total_entries+=entry_count;
}
setdetailattrib(0,"park_valid_count",valid_count,"set");
setdetailattrib(0,"park_invalid_count",invalid_count,"set");
setdetailattrib(0,"park_boundary_sample_count_max",max_boundary_samples,"set");
setdetailattrib(0,"park_entrance_count",total_entries,"set");
setdetailattrib(0,"park_masterplan_version",41,"set");
'''


SURFACE_VEX = COMMON_VEX + r'''
// CITYROAD_V41_PARK_SURFACE_ZONES
int original_prims=nprimitives(0);
string ground_mat=chs("../../../park_ground_unity_material");
string water_mat=chs("../../../park_water_unity_material");
float inset=max(chf("../../../park_boundary_inset"),0.0);
float clearance=max(chf("../../../park_tree_clearance"),0.0);
int ground_count=0, water_count=0;
for (int source_prim=0;source_prim<original_prims;source_prim++)
{
    if (!prim(0,"park_valid",source_prim)) continue;
    int pts[]=primpoints(0,source_prim);
    int count=len(pts);
    if (count>2 && length(vector(point(0,"P",pts[0]))-vector(point(0,"P",pts[count-1])))<0.1) count--;
    vector poly[];
    for (int i=0;i<count;i++) append(poly,vector(point(0,"P",pts[i])));
    vector bbmin=prim(0,"park_bbmin",source_prim), bbmax=prim(0,"park_bbmax",source_prim);
    vector center=prim(0,"park_center",source_prim), hub=prim(0,"park_hub",source_prim);
    float area=prim(0,"park_area",source_prim);
    int park_id=prim(0,"park_id",source_prim);
    float sx=max(bbmax.x-bbmin.x,1.0), sz=max(bbmax.z-bbmin.z,1.0);
    float target_cells=clamp(area/2.0,64.0,3500.0);
    float cell=clamp(sqrt((sx*sz)/target_cells),0.75,5.0);
    int nx=max(1,int(ceil(sx/cell))), nz=max(1,int(ceil(sz/cell)));
    cell=max(sx/nx,sz/nz); nx=min(int(ceil(sx/cell)),128); nz=min(int(ceil(sz/cell)),128);
    float min_dim=min(sx,sz);
    for (int ix=0;ix<nx;ix++) for (int iz=0;iz<nz;iz++)
    {
        float x0=bbmin.x+ix*cell, x1=min(x0+cell,bbmax.x);
        float z0=bbmin.z+iz*cell, z1=min(z0+cell,bbmax.z);
        vector p0=set(x0,center.y,z0),p1=set(x1,center.y,z0);
        vector p2=set(x1,center.y,z1),p3=set(x0,center.y,z1);
        vector p=(p0+p1+p2+p3)*0.25;
        if (!point_in_polygon_xz(p0,poly)||!point_in_polygon_xz(p1,poly)
            ||!point_in_polygon_xz(p2,poly)||!point_in_polygon_xz(p3,poly)) continue;
        int entry_id=-1;
        int path_class=park_path_class(p,source_prim,cell,entry_id);
        int water=park_water_mask(p,source_prim);
        if (water)
        {
            add_surface_quad(p0,p1,p2,p3,center.y-0.04,"water",water_mat,
                "water_garden","",park_id,ix,iz,-1);
            water_count++;
            continue;
        }
        if (path_class) continue;
        float edge=boundary_distance_xz(p,source_prim);
        float entry_distance=1e18;
        int entry_count=prim(0,"park_entry_count",source_prim);
        for (int ei=0;ei<entry_count;ei++)
        {
            vector entry=park_entry(source_prim,ei);
            entry_distance=min(entry_distance,length(set(p.x-entry.x,0.0,p.z-entry.z)));
        }
        string zone="quiet_lawn";
        if (entry_distance<max(6.0,chf("../../../park_path_width")*2.5)) zone="entrance_lawn";
        else if (length(set(p.x-hub.x,0.0,p.z-hub.z))<min_dim*0.22) zone="active_lawn";
        else if (edge<max(inset+clearance,min_dim*0.18)) zone="woodland_edge";
        add_surface_quad(p0,p1,p2,p3,center.y,"ground",ground_mat,zone,"",
            park_id,ix,iz,-1);
        ground_count++;
    }
}
remove_source_primitives(original_prims);
setdetailattrib(0,"park_ground_quad_count",ground_count,"set");
setdetailattrib(0,"park_water_quad_count",water_count,"set");
'''


PATH_VEX = COMMON_VEX + r'''
// CITYROAD_V41_PARK_CONNECTED_PATHS
int original_prims=nprimitives(0);
string path_mat=chs("../../../park_path_unity_material");
int path_count=0, entrance_cells=0;
for (int source_prim=0;source_prim<original_prims;source_prim++)
{
    if (!prim(0,"park_valid",source_prim)) continue;
    int pts[]=primpoints(0,source_prim);
    int count=len(pts);
    if (count>2 && length(vector(point(0,"P",pts[0]))-vector(point(0,"P",pts[count-1])))<0.1) count--;
    vector poly[];
    for (int i=0;i<count;i++) append(poly,vector(point(0,"P",pts[i])));
    vector bbmin=prim(0,"park_bbmin",source_prim), bbmax=prim(0,"park_bbmax",source_prim);
    vector center=prim(0,"park_center",source_prim);
    float area=prim(0,"park_area",source_prim);
    int park_id=prim(0,"park_id",source_prim);
    float sx=max(bbmax.x-bbmin.x,1.0), sz=max(bbmax.z-bbmin.z,1.0);
    float target_cells=clamp(area/2.0,64.0,3500.0);
    float cell=clamp(sqrt((sx*sz)/target_cells),0.75,5.0);
    int nx=max(1,int(ceil(sx/cell))), nz=max(1,int(ceil(sz/cell)));
    cell=max(sx/nx,sz/nz); nx=min(int(ceil(sx/cell)),128); nz=min(int(ceil(sz/cell)),128);
    for (int ix=0;ix<nx;ix++) for (int iz=0;iz<nz;iz++)
    {
        float x0=bbmin.x+ix*cell, x1=min(x0+cell,bbmax.x);
        float z0=bbmin.z+iz*cell, z1=min(z0+cell,bbmax.z);
        vector p0=set(x0,center.y,z0),p1=set(x1,center.y,z0);
        vector p2=set(x1,center.y,z1),p3=set(x0,center.y,z1);
        vector p=(p0+p1+p2+p3)*0.25;
        if (!point_in_polygon_xz(p0,poly)||!point_in_polygon_xz(p1,poly)
            ||!point_in_polygon_xz(p2,poly)||!point_in_polygon_xz(p3,poly)) continue;
        if (park_water_mask(p,source_prim)) continue;
        int entry_id=-1;
        int path_class=park_path_class(p,source_prim,cell,entry_id);
        if (!path_class) continue;
        string class_name=path_class==1?"loop":path_class==2?"primary":
            path_class==3?"entrance":"plaza";
        add_surface_quad(p0,p1,p2,p3,center.y+0.02,"paths",path_mat,
            "circulation",class_name,park_id,ix,iz,entry_id);
        add_surface_quad(p0,p1,p2,p3,center.y,"collision","",
            "circulation",class_name,park_id,ix,iz,entry_id);
        path_count++;
        if (path_class==3) entrance_cells++;
    }
}
remove_source_primitives(original_prims);
setdetailattrib(0,"park_path_quad_count",path_count,"set");
setdetailattrib(0,"park_entrance_path_cell_count",entrance_cells,"set");
'''


WOODLAND_VEX = COMMON_VEX + r'''
// CITYROAD_V41_PARK_WOODLAND_LAYERS
int original_prims=nprimitives(0);
int global_seed=chi("../../../park_seed");
float density=max(chf("../../../park_tree_density_per_hectare"),0.0);
float spacing=max(chf("../../../park_tree_min_spacing"),1.0);
float clearance=max(chf("../../../park_tree_clearance"),0.0);
float inset=max(chf("../../../park_boundary_inset"),0.0);
string prefabs[]=array(chs("../../../tree_prefab1"),chs("../../../tree_prefab2"),chs("../../../tree_prefab3"));
float weights[]=array(max(chf("../../../tree_weight1"),0.0),max(chf("../../../tree_weight2"),0.0),max(chf("../../../tree_weight3"),0.0));
float scale_min=max(chf("../../../tree_scale_min"),0.01);
float scale_max=max(chf("../../../tree_scale_max"),scale_min);
int tree_count=0;
if (chi("../../../enable_park_trees") && density>0)
for (int source_prim=0;source_prim<original_prims && tree_count<4096;source_prim++)
{
    if (!prim(0,"park_valid",source_prim)) continue;
    int pts[]=primpoints(0,source_prim);
    int count=len(pts);
    if (count>2 && length(vector(point(0,"P",pts[0]))-vector(point(0,"P",pts[count-1])))<0.1) count--;
    vector poly[];
    for (int i=0;i<count;i++) append(poly,vector(point(0,"P",pts[i])));
    vector bbmin=prim(0,"park_bbmin",source_prim), bbmax=prim(0,"park_bbmax",source_prim);
    vector center=prim(0,"park_center",source_prim), hub=prim(0,"park_hub",source_prim);
    int park_id=prim(0,"park_id",source_prim), park_tree_count=0;
    float sx=max(bbmax.x-bbmin.x,1.0), sz=max(bbmax.z-bbmin.z,1.0), min_dim=min(sx,sz);
    float sample_cell=max(spacing*1.05,2.0);
    int tx=min(int(ceil(sx/sample_cell)),128), tz=min(int(ceil(sz/sample_cell)),128);
    float base_probability=clamp(density*sample_cell*sample_cell/10000.0,0.0,1.0);
    float total_weight=max(weights[0]+weights[1]+weights[2],1e-5);
    for (int ix=0;ix<tx && tree_count<4096 && park_tree_count<2048;ix++)
    for (int iz=0;iz<tz && tree_count<4096 && park_tree_count<2048;iz++)
    {
        int park_hash=park_id%100003;
        vector key=set(float(global_seed),float(ix+park_hash),float(iz)+float(park_hash)*0.37);
        float jx=(rand(key+31.0)-0.5)*sample_cell*0.04;
        float jz=(rand(key+47.0)-0.5)*sample_cell*0.04;
        vector p=set(bbmin.x+(ix+0.5)*sample_cell+jx,center.y,bbmin.z+(iz+0.5)*sample_cell+jz);
        if (!point_in_polygon_xz(p,poly)) continue;
        float edge=boundary_distance_xz(p,source_prim);
        if (edge<inset+clearance) continue;
        if (park_water_mask(p,source_prim)) continue;
        int entry_id=-1;
        int path_class=park_path_class(p,source_prim,sample_cell,entry_id);
        if (path_class) continue;
        string layer="scattered_lawn";
        int canopy=0;
        float probability=base_probability*0.35;
        if (edge<min_dim*0.18)
        { layer="woodland_core"; canopy=2; probability=max(0.82,base_probability*1.8); }
        else if (edge<min_dim*0.30)
        { layer="woodland_edge"; canopy=1; probability=max(0.62,base_probability*1.35); }
        else if (length(set(p.x-hub.x,0.0,p.z-hub.z))>min_dim*0.28)
        { layer="quiet_grove"; canopy=1; probability=max(0.42,base_probability); }
        if (rand(key+17.0)>clamp(probability,0.0,1.0)) continue;
        float choice=rand(key+71.0)*total_weight;
        int variant=choice<weights[0]?0:(choice<weights[0]+weights[1]?1:2);
        int point_id=addpoint(0,p);
        float yaw=rand(key+89.0)*M_PI*2.0;
        float scale=lerp(scale_min,scale_max,rand(key+101.0));
        if (layer=="woodland_core") scale*=1.12;
        else if (layer=="woodland_edge") scale*=1.04;
        else if (layer=="scattered_lawn") scale*=0.92;
        string group=sprintf("CityPark/Trees/Park_%d/%s/Variant_%d",park_id,layer,variant);
        setpointattrib(0,"park_output",point_id,"trees","set");
        setpointattrib(0,"output_role",point_id,"park_trees","set");
        setpointattrib(0,"park_id",point_id,park_id,"set");
        setpointattrib(0,"pcg_site_type",point_id,"park","set");
        setpointattrib(0,"exclude_building",point_id,1,"set");
        setpointattrib(0,"unity_instance",point_id,prefabs[variant],"set");
        setpointattrib(0,"instance_prefix",point_id,group,"set");
        setpointattrib(0,"pcg_group_key",point_id,group,"set");
        setpointattrib(0,"pcg_kind",point_id,"park_tree","set");
        setpointattrib(0,"pcg_variant",point_id,variant,"set");
        setpointattrib(0,"park_vegetation_layer",point_id,layer,"set");
        setpointattrib(0,"park_canopy_layer",point_id,canopy,"set");
        setpointattrib(0,"park_zone",point_id,layer,"set");
        setpointattrib(0,"orient",point_id,quaternion(yaw,set(0,1,0)),"set");
        setpointattrib(0,"pscale",point_id,scale,"set");
        tree_count++; park_tree_count++;
    }
}
remove_source_primitives(original_prims);
setdetailattrib(0,"park_tree_count",tree_count,"set");
'''


EXCLUSION_VEX = COMMON_VEX + r'''
// CITYROAD_V41_PARK_EXCLUSION
int original_prims=nprimitives(0);
for (int source_prim=0;source_prim<original_prims;source_prim++)
{
    if (!prim(0,"park_valid",source_prim)) continue;
    int source_points[]=primpoints(0,source_prim);
    int source_count=len(source_points);
    if (source_count>2 && length(
        vector(point(0,"P",source_points[0]))-vector(point(0,"P",source_points[source_count-1])))<0.1)
        source_count--;
    int step=max(1,int(ceil(float(source_count)/512.0)));
    vector center=prim(0,"park_center",source_prim);
    int points[];
    for (int i=0;i<source_count;i+=step)
    {
        vector p=point(0,"P",source_points[i]); p.y=center.y;
        append(points,addpoint(0,p));
    }
    int exclusion=addprim(0,"poly",points);
    int park_id=prim(0,"park_id",source_prim);
    tag_surface(exclusion,"exclusion","","site_boundary","",park_id,-1,-1,-1);
}
remove_source_primitives(original_prims);
'''


CONTRACT_VEX = r'''
// CITYROAD_V41_PARK_MASTERPLAN_CONTRACT
int ground=0, paths=0, water=0, collision=0, exclusion=0, trees=0;
string zones[], layers[], path_classes[];
for (int prim_id=0;prim_id<nprimitives(0);prim_id++)
{
    string role=prim(0,"park_output",prim_id);
    if (role=="ground")
    {
        ground++;
        string zone=prim(0,"park_zone",prim_id);
        if (find(zones,zone)<0) append(zones,zone);
    }
    else if (role=="paths")
    {
        paths++;
        string path_class=prim(0,"park_path_class",prim_id);
        if (find(path_classes,path_class)<0) append(path_classes,path_class);
    }
    else if (role=="water") water++;
    else if (role=="collision") collision++;
    else if (role=="exclusion") exclusion++;
}
for (int point_id=0;point_id<npoints(0);point_id++)
{
    if (point(0,"park_output",point_id)!="trees") continue;
    trees++;
    string layer=point(0,"park_vegetation_layer",point_id);
    if (find(layers,layer)<0) append(layers,layer);
}
setdetailattrib(0,"cityroad_city_park_contract","CITYROAD_V41_PARK_MASTERPLAN","set");
setdetailattrib(0,"park_masterplan_version",41,"set");
setdetailattrib(0,"park_ground_quad_count",ground,"set");
setdetailattrib(0,"park_path_quad_count",paths,"set");
setdetailattrib(0,"park_water_quad_count",water,"set");
setdetailattrib(0,"park_collision_quad_count",collision,"set");
setdetailattrib(0,"park_tree_count",trees,"set");
setdetailattrib(0,"park_exclusion_count",exclusion,"set");
setdetailattrib(0,"park_zone_count",len(zones),"set");
setdetailattrib(0,"park_woodland_layer_count",len(layers),"set");
setdetailattrib(0,"park_path_class_count",len(path_classes),"set");
setdetailattrib(0,"park_path_component_count",int(detail(0,"park_valid_count")),"set");
'''


OUTPUT_CONTRACT_VEX = {
    "PARK_GROUND_OUTPUT_CONTRACT": r'''
// CITYROAD_V20_CITY_PARK_OUTPUT_CONTRACT
// CITYROAD_V41_PARK_MASTERPLAN_OUTPUT_CONTRACT
setdetailattrib(0,"unity_split_attr","name","set");
setdetailattrib(0,"cityroad_city_park_contract","CITYROAD_V41_PARK_MASTERPLAN","set");
''',
    "PARK_PATHS_OUTPUT_CONTRACT": r'''
// CITYROAD_V20_CITY_PARK_OUTPUT_CONTRACT
// CITYROAD_V41_PARK_MASTERPLAN_OUTPUT_CONTRACT
setdetailattrib(0,"unity_split_attr","name","set");
setdetailattrib(0,"cityroad_city_park_contract","CITYROAD_V41_PARK_MASTERPLAN","set");
''',
    "PARK_WATER_OUTPUT_CONTRACT": r'''
// CITYROAD_V20_CITY_PARK_OUTPUT_CONTRACT
// CITYROAD_V41_PARK_MASTERPLAN_OUTPUT_CONTRACT
setdetailattrib(0,"unity_split_attr","name","set");
setdetailattrib(0,"cityroad_city_park_contract","CITYROAD_V41_PARK_MASTERPLAN","set");
''',
    "PARK_COLLISION_OUTPUT_CONTRACT": r'''
// CITYROAD_V20_CITY_PARK_OUTPUT_CONTRACT
// CITYROAD_V41_PARK_MASTERPLAN_OUTPUT_CONTRACT
setdetailattrib(0,"unity_split_attr","name","set");
setdetailattrib(0,"cityroad_city_park_contract","CITYROAD_V41_PARK_MASTERPLAN","set");
''',
    "PARK_TREES_OUTPUT_CONTRACT": r'''
// CITYROAD_V20_CITY_PARK_TREE_CONTRACT
// CITYROAD_V41_PARK_MASTERPLAN_TREE_CONTRACT
setdetailattrib(0,"unity_split_attr","pcg_group_key","set");
setdetailattrib(0,"cityroad_city_park_contract","CITYROAD_V41_PARK_MASTERPLAN","set");
''',
    "PARK_EXCLUSION_OUTPUT_CONTRACT": r'''
// CITYROAD_V20_CITY_PARK_OUTPUT_CONTRACT
// CITYROAD_V41_PARK_MASTERPLAN_OUTPUT_CONTRACT
setdetailattrib(0,"unity_split_attr","name","set");
setdetailattrib(0,"cityroad_city_park_contract","CITYROAD_V41_PARK_MASTERPLAN","set");
''',
}


NODE_TYPES = {
    "PARK_BOUNDARY_ANALYZE_V41": "attribwrangle",
    "PARK_SURFACE_ZONES_V41": "attribwrangle",
    "PARK_CONNECTED_PATHS_V41": "attribwrangle",
    "PARK_WOODLAND_LAYERS_V41": "attribwrangle",
    "PARK_EXCLUSION_V41": "attribwrangle",
    "PARK_ASSEMBLE_V41": "merge",
    "PARK_CONTRACT_V41": "attribwrangle",
}


def _norm(value) -> str:
    return str(value).replace("\\", "/").lower()


def _baseline_payload(park) -> str:
    rows = []
    for node in sorted(park.children(), key=lambda item: item.name()):
        inputs = sorted(
            (item.inputIndex(), item.inputNode().name(), item.outputIndex())
            for item in node.inputConnections())
        snippet = node.parm("snippet").eval() if node.parm("snippet") else None
        rows.append({
            "name": node.name(), "type": node.type().name(),
            "inputs": inputs, "snippet": snippet,
        })
    return json.dumps(rows, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _sha256(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _require_identity(asset) -> None:
    if asset is None or asset.type().name() != ASSET_TYPE:
        raise RuntimeError(f"Unexpected CityRoad asset at {ASSET_PATH}")
    if _norm(hou.hipFile.path()) != _norm(EXPECTED_HIP):
        raise RuntimeError(f"Unexpected HIP: {hou.hipFile.path()}")
    definition = asset.type().definition()
    if definition is None or _norm(definition.libraryFilePath()) != _norm(EXPECTED_HDA):
        raise RuntimeError("CityRoad definition path changed")


def _set_detail_wrangle(node, snippet: str) -> None:
    class_parm = node.parm("class")
    if class_parm is not None:
        class_parm.set(0)
    node.parm("snippet").set(snippet)


def _connect(node, sources) -> None:
    for index, source in enumerate(sources):
        node.setInput(index, source)


def _validate(park) -> dict[str, object]:
    for name, node_type in NODE_TYPES.items():
        node = park.node(name)
        if node is None or node.type().name() != node_type:
            raise RuntimeError(f"Missing V41 node: {name} ({node_type})")
    expected = {
        "PARK_BOUNDARY_ANALYZE_V41": ("PARK_REBUILD_HAPI_TOPOLOGY_V29",),
        "PARK_SURFACE_ZONES_V41": ("PARK_BOUNDARY_ANALYZE_V41",),
        "PARK_CONNECTED_PATHS_V41": ("PARK_BOUNDARY_ANALYZE_V41",),
        "PARK_WOODLAND_LAYERS_V41": ("PARK_BOUNDARY_ANALYZE_V41",),
        "PARK_EXCLUSION_V41": ("PARK_BOUNDARY_ANALYZE_V41",),
        "PARK_ASSEMBLE_V41": (
            "PARK_SURFACE_ZONES_V41", "PARK_CONNECTED_PATHS_V41",
            "PARK_WOODLAND_LAYERS_V41", "PARK_EXCLUSION_V41"),
        "PARK_CONTRACT_V41": ("PARK_ASSEMBLE_V41",),
    }
    for name, inputs in expected.items():
        actual = tuple(source.name() if source else None for source in park.node(name).inputs())
        if actual[:len(inputs)] != inputs:
            raise RuntimeError(f"V41 connection mismatch at {name}: {actual} != {inputs}")
    for name in (
        "PARK_KEEP_GROUND", "PARK_KEEP_PATHS", "PARK_KEEP_WATER",
        "PARK_KEEP_COLLISION", "PARK_KEEP_TREES", "PARK_KEEP_EXCLUSION"):
        source = park.node(name).input(0)
        if source is None or source.name() != "PARK_CONTRACT_V41":
            raise RuntimeError(f"V41 output filter is not connected: {name}")
    if park.node("PARK_CONTRACT_V41").parm("snippet").eval().find(MARKER.split("_20260824")[0]) < 0:
        raise RuntimeError("V41 contract marker is missing")
    output_names = (
        "SUBNET_OUT_PARK_GROUND_0", "SUBNET_OUT_PARK_PATHS_1",
        "SUBNET_OUT_PARK_WATER_2", "SUBNET_OUT_PARK_COLLISION_3",
        "SUBNET_OUT_PARK_TREES_4", "SUBNET_OUT_PARK_EXCLUSION_5")
    diagnostics = []
    for name in output_names:
        node = park.node(name)
        try:
            node.cook(force=True)
        except Exception as exc:
            for candidate_name in (
                    "PARK_BOUNDARY_ANALYZE_V41", "PARK_SURFACE_ZONES_V41",
                    "PARK_CONNECTED_PATHS_V41", "PARK_WOODLAND_LAYERS_V41",
                    "PARK_EXCLUSION_V41", "PARK_CONTRACT_V41", name):
                candidate = park.node(candidate_name)
                if candidate is None:
                    continue
                diagnostics.extend(
                    f"{candidate_name}: {message}" for message in candidate.errors())
                diagnostics.extend(
                    f"{candidate_name}: {message}" for message in candidate.warnings())
            raise RuntimeError(
                f"V41 cook failed at {node.path()}: {exc}; "
                + " | ".join(diagnostics)) from exc
        diagnostics.extend(f"{name}: {message}" for message in node.errors())
        diagnostics.extend(f"{name}: {message}" for message in node.warnings())
    if diagnostics:
        raise RuntimeError("V41 cook diagnostics: " + " | ".join(diagnostics))
    return {
        "node_count": len(park.children()),
        "outputs": list(output_names),
        "diagnostics": diagnostics,
    }


def _document(park, nodes) -> None:
    positions = {
        "PARK_ENABLE_INPUT_SWITCH": (-24, 4),
        "PARK_CONVERT_HAPI_CURVE_V32": (-18, 4),
        "PARK_REBUILD_HAPI_TOPOLOGY_V29": (-12, 4),
        "PARK_BOUNDARY_ANALYZE_V41": (-6, 4),
        "PARK_SURFACE_ZONES_V41": (2, 8),
        "PARK_CONNECTED_PATHS_V41": (2, 4),
        "PARK_WOODLAND_LAYERS_V41": (2, 0),
        "PARK_EXCLUSION_V41": (2, -4),
        "PARK_ASSEMBLE_V41": (10, 4),
        "PARK_CONTRACT_V41": (16, 4),
    }
    for name, position in positions.items():
        node = park.node(name)
        if node is not None:
            node.setPosition(position)
    colors = {
        "PARK_BOUNDARY_ANALYZE_V41": (0.22, 0.48, 0.78),
        "PARK_SURFACE_ZONES_V41": (0.32, 0.70, 0.38),
        "PARK_CONNECTED_PATHS_V41": (0.80, 0.62, 0.20),
        "PARK_WOODLAND_LAYERS_V41": (0.18, 0.52, 0.24),
        "PARK_EXCLUSION_V41": (0.58, 0.35, 0.70),
        "PARK_ASSEMBLE_V41": (0.42, 0.52, 0.62),
        "PARK_CONTRACT_V41": (0.82, 0.42, 0.18),
    }
    for name, color in colors.items():
        park.node(name).setColor(hou.Color(color))
    comments = {
        "PARK_BOUNDARY_ANALYZE_V41": "V41：验证边界并提取入口、中心、湖区与总图元数据。",
        "PARK_SURFACE_ZONES_V41": "V41：生成入口草坪、活动草坪、安静草坪与林缘分区。",
        "PARK_CONNECTED_PATHS_V41": "V41：生成入口支路、主路、环路与中心节点的连通路网。",
        "PARK_WOODLAND_LAYERS_V41": "V41：生成林核、林缘、安静林组与草坪散植层。",
        "PARK_EXCLUSION_V41": "V41：输出建筑排除边界。",
        "PARK_ASSEMBLE_V41": "V41：合并公园表面、路网、植被与排除分支。",
        "PARK_CONTRACT_V41": "V41：汇总公园语义层与累计验收 metadata。",
    }
    for name, comment in comments.items():
        park.node(name).setComment(comment)
    for box in list(park.networkBoxes()):
        if box.name() == "PARK_MASTERPLAN_V41_BOX":
            box.destroy()
    box = park.createNetworkBox("PARK_MASTERPLAN_V41_BOX")
    box.setComment("V41 公园总图：边界 → 分区/路网/林地/排除 → 合并 → 输出合约")
    box.setColor(hou.Color((0.20, 0.48, 0.30)))
    for node in nodes:
        box.addItem(node)
    box.fitAroundContents()
    for item in list(park.stickyNotes()):
        if item.text().startswith("V41 公园维护入口"):
            item.destroy()
    note = park.createStickyNote()
    note.setText(
        "V41 公园维护入口\n"
        "1. PARK_BOUNDARY_ANALYZE：入口、中心、湖区与边界合法性\n"
        "2. PARK_SURFACE_ZONES：入口草坪 / 活动草坪 / 安静草坪 / 林缘\n"
        "3. PARK_CONNECTED_PATHS：入口支路全部接入环路与中心节点\n"
        "4. PARK_WOODLAND_LAYERS：林核 / 林缘 / 安静林组 / 草坪散植\n"
        "运行时只使用 Bake 结果；本网络仅在编辑期 Cook。")
    note.setPosition((-6, 13))
    note.setSize((18, 7))
    note.setColor(hou.Color((0.24, 0.48, 0.30)))


def apply_live_patch(save: bool = False) -> dict[str, object]:
    if save:
        raise RuntimeError("V41 patch is save=False only; use VerifyFull to persist")
    asset = hou.node(ASSET_PATH)
    _require_identity(asset)
    park = asset.node(PARK_PATH)
    if park is None:
        raise RuntimeError(f"Missing park subnet: {PARK_PATH}")
    marker_applied = park.userData("cityroad_park_masterplan_marker") == MARKER
    partial_names = (
        "PARK_BOUNDARY_ANALYZE_V41", "PARK_SURFACE_ZONES_V41",
        "PARK_CONNECTED_PATHS_V41", "PARK_WOODLAND_LAYERS_V41",
        "PARK_EXCLUSION_V41", "PARK_ASSEMBLE_V41", "PARK_CONTRACT_V41")
    repair_partial = marker_applied or (
        park.node("PARK_LAYOUT_AND_SCATTER_V20") is None
        and all(park.node(name) is not None for name in partial_names))
    actual_sha = _sha256(_baseline_payload(park))
    if not repair_partial and actual_sha != BASELINE_SHA256:
        raise RuntimeError(f"V41 Live baseline changed: {actual_sha} != {BASELINE_SHA256}")
    legacy = park.node("PARK_BOUNDARY_ANALYZE_V41") if repair_partial \
        else park.node("PARK_LAYOUT_AND_SCATTER_V20")
    if legacy is None or (not repair_partial
            and "CITYROAD_V20_CITY_PARK" not in legacy.parm("snippet").eval()):
        raise RuntimeError("V20/V41 park layout precondition changed")

    try:
        with hou.undos.group("CityRoad Park Masterplan V41"):
            if not repair_partial:
                legacy.setName("PARK_BOUNDARY_ANALYZE_V41", unique_name=False)
            _set_detail_wrangle(legacy, ANALYZE_VEX)
            surface = park.node("PARK_SURFACE_ZONES_V41") if repair_partial \
                else park.createNode("attribwrangle", "PARK_SURFACE_ZONES_V41")
            paths = park.node("PARK_CONNECTED_PATHS_V41") if repair_partial \
                else park.createNode("attribwrangle", "PARK_CONNECTED_PATHS_V41")
            woodland = park.node("PARK_WOODLAND_LAYERS_V41") if repair_partial \
                else park.createNode("attribwrangle", "PARK_WOODLAND_LAYERS_V41")
            exclusion = park.node("PARK_EXCLUSION_V41") if repair_partial \
                else park.createNode("attribwrangle", "PARK_EXCLUSION_V41")
            assemble = park.node("PARK_ASSEMBLE_V41") if repair_partial \
                else park.createNode("merge", "PARK_ASSEMBLE_V41")
            contract = park.node("PARK_CONTRACT_V41") if repair_partial \
                else park.createNode("attribwrangle", "PARK_CONTRACT_V41")
            _set_detail_wrangle(surface, SURFACE_VEX)
            _set_detail_wrangle(paths, PATH_VEX)
            _set_detail_wrangle(woodland, WOODLAND_VEX)
            _set_detail_wrangle(exclusion, EXCLUSION_VEX)
            _set_detail_wrangle(contract, CONTRACT_VEX)
            rebuild = park.node("PARK_REBUILD_HAPI_TOPOLOGY_V29")
            _connect(legacy, (rebuild,))
            for node in (surface, paths, woodland, exclusion):
                _connect(node, (legacy,))
            _connect(assemble, (surface, paths, woodland, exclusion))
            _connect(contract, (assemble,))
            for name in (
                "PARK_KEEP_GROUND", "PARK_KEEP_PATHS", "PARK_KEEP_WATER",
                "PARK_KEEP_COLLISION", "PARK_KEEP_TREES", "PARK_KEEP_EXCLUSION"):
                park.node(name).setInput(0, contract)
            for name, snippet in OUTPUT_CONTRACT_VEX.items():
                _set_detail_wrangle(park.node(name), snippet)
            new_nodes = (legacy, surface, paths, woodland, exclusion, assemble, contract)
            _document(park, new_nodes)
            park.setUserData("cityroad_park_masterplan_marker", MARKER)
            result = _validate(park)
    except Exception:
        try:
            hou.undos.performUndo()
        finally:
            raise
    result.update({
        "status": "PASS", "already_applied": marker_applied, "saved": False,
        "marker": MARKER,
    })
    return result


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=18811)
    parser.add_argument("--save", default="false")
    args = parser.parse_args()
    if args.save.lower() != "false":
        raise RuntimeError("Only --save false is supported")
    import hrpyc
    connection, _remote_hou = hrpyc.import_remote_module(args.host, args.port, "hou")
    try:
        tools_path = str(SCRIPT_DIR).replace("\\", "/")
        connection.execute(
            "import sys, importlib; "
            f"sys.path.insert(0, {tools_path!r}) if {tools_path!r} not in sys.path else None; "
            "import patch_cityroad_park_masterplan_v41_20260824 as _cityroad_v41; "
            "importlib.reload(_cityroad_v41)")
        payload = connection.eval("_cityroad_v41.apply_live_patch(save=False)")
        print(json.dumps(payload, ensure_ascii=False, default=list, indent=2))
    finally:
        connection.close()


if __name__ == "__main__":
    main()
