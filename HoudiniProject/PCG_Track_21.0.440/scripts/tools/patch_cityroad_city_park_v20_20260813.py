"""Incremental CityRoad V20 city-park patch.

The patch edits only the current live ``/obj/CityRoad_DEV`` instance.  Core
park generation remains a readable SOP/VEX network; Python is only the
transactional construction and verification glue.  ``save=False`` is the
default so the regression gate remains the sole persistence authority.
"""

from __future__ import annotations

import argparse
import importlib
import json
import sys
from pathlib import Path

try:
    import hou  # type: ignore
except ImportError:  # Imported by unit tooling outside Houdini.
    hou = None


ASSET_PATH = "/obj/CityRoad_DEV"
EXPECTED_TYPE = "pcgbike::CityRoad::1.0"
EXPECTED_HDA_SUFFIX = "/Assets/PCG/HDA/City/CityRoad.hda"
EXPECTED_HIP_SUFFIX = "/HoudiniProject/PCG_Track_21.0.440/PCG_Bike_CityRoad.hip"
EXPECTED_PUBLIC_HASH = "326b3b34356b6b17b6fd3b98d7ef9d77adecebeb236c7a8f25daee04c1b8f660"
MARKER = "CITYROAD_V20_CITY_PARK"
SUBNET_NAME = "CR_CITY_PARK"
OUTPUT_NAMES = (
    "OUT_PARK_GROUND",
    "OUT_PARK_PATHS",
    "OUT_PARK_WATER",
    "OUT_PARK_COLLISION",
    "OUT_PARK_TREES",
    "OUT_PARK_EXCLUSION",
)
OUTPUT_INDEX_BASE = 10


PARK_GENERATOR_VEX = r'''
// CITYROAD_V20_CITY_PARK
// 输入: Unity 闭合 SplineContainer；输出: 非重叠草地/园路/湖面、碰撞、树点和建筑排除边界。

float cross2(vector a; vector b; vector c)
{
    return (b.x-a.x)*(c.z-a.z) - (b.z-a.z)*(c.x-a.x);
}

int point_in_polygon_xz(vector q; vector poly[])
{
    int inside = 0;
    int count = len(poly);
    for (int i = 0, j = count-1; i < count; j = i++)
    {
        vector a = poly[i];
        vector b = poly[j];
        int crosses = ((a.z > q.z) != (b.z > q.z));
        if (crosses)
        {
            float x = (b.x-a.x) * (q.z-a.z) / max(abs(b.z-a.z), 1e-8) + a.x;
            if (q.x < x) inside = !inside;
        }
    }
    return inside;
}

int segments_intersect_xz(vector a; vector b; vector c; vector d)
{
    float ab_c = cross2(a,b,c);
    float ab_d = cross2(a,b,d);
    float cd_a = cross2(c,d,a);
    float cd_b = cross2(c,d,b);
    return ((ab_c > 1e-5 && ab_d < -1e-5) || (ab_c < -1e-5 && ab_d > 1e-5))
        && ((cd_a > 1e-5 && cd_b < -1e-5) || (cd_a < -1e-5 && cd_b > 1e-5));
}

float point_segment_distance_xz(vector p; vector a; vector b)
{
    vector ab = set(b.x-a.x, 0, b.z-a.z);
    vector ap = set(p.x-a.x, 0, p.z-a.z);
    float t = clamp(dot(ap,ab) / max(dot(ab,ab), 1e-8), 0.0, 1.0);
    vector closest = a + ab*t;
    return distance(set(p.x,0,p.z), set(closest.x,0,closest.z));
}

float lake_metric(vector p; vector center; float rx; float rz; float seed; float jitter)
{
    float nx = (p.x-center.x) / max(rx, 0.1);
    float nz = (p.z-center.z) / max(rz, 0.1);
    float angle = atan2(nz, nx);
    float ripple = 1.0 + jitter * (0.55*sin(angle*3.0+seed) + 0.45*sin(angle*5.0-seed*0.37));
    return sqrt(nx*nx+nz*nz) / max(ripple, 0.5);
}

void tag_surface(int prim; string role; string material; int park_id)
{
    string clean_role = role;
    setprimattrib(0, "park_output", prim, role, "set");
    string output_role = role=="exclusion" ? "park_exclusion" : role;
    setprimattrib(0, "output_role", prim, output_role, "set");
    setprimattrib(0, "park_id", prim, park_id, "set");
    setprimattrib(0, "pcg_site_type", prim, "park", "set");
    setprimattrib(0, "exclude_building", prim, 1, "set");
    if (material != "") setprimattrib(0, "unity_material", prim, material, "set");
    setprimattrib(0, "name", prim, sprintf("CityPark_%d_%s", park_id, clean_role), "set");
    setprimattrib(0, "instance_prefix", prim, sprintf("CityPark/%d/%s", park_id, clean_role), "set");
}

int add_surface_quad(vector p0; vector p1; vector p2; vector p3; float y;
                     string role; string material; int park_id)
{
    p0.y = y; p1.y = y; p2.y = y; p3.y = y;
    int a = addpoint(0,p0); int b = addpoint(0,p1);
    int c = addpoint(0,p2); int d = addpoint(0,p3);
    int pr = addprim(0,"poly",a,b,c,d);
    int vertices[] = primvertices(0,pr);
    vector2 uvs[] = array(set(p0.x,p0.z), set(p1.x,p1.z), set(p2.x,p2.z), set(p3.x,p3.z));
    foreach (int i; int vtx; vertices) setvertexattrib(0,"uv",pr,i,uvs[i],"set");
    tag_surface(pr,role,material,park_id);
    return pr;
}

int original_prims = nprimitives(0);
int enabled = chi("../../../enable_city_park");
int water_enabled = chi("../../../enable_park_water");
int paths_enabled = chi("../../../enable_park_paths");
int trees_enabled = chi("../../../enable_park_trees");
int global_seed = chi("../../../park_seed");
float inset = max(chf("../../../park_boundary_inset"),0.0);
int lake_count = clamp(chi("../../../park_lake_count"),1,2);
float lake_ratio = clamp(chf("../../../park_lake_area_ratio"),0.05,0.45);
float path_width = max(chf("../../../park_path_width"),0.5);
int branch_count = clamp(chi("../../../park_path_branch_count"),0,3);
float path_jitter = clamp(chf("../../../park_path_jitter"),0.0,0.35);
float tree_density = max(chf("../../../park_tree_density_per_hectare"),0.0);
float tree_spacing = max(chf("../../../park_tree_min_spacing"),1.0);
float tree_clearance = max(chf("../../../park_tree_clearance"),0.0);
string ground_mat = chs("../../../park_ground_unity_material");
string path_mat = chs("../../../park_path_unity_material");
string water_mat = chs("../../../park_water_unity_material");
string tree_prefabs[] = array(chs("../../../tree_prefab1"), chs("../../../tree_prefab2"), chs("../../../tree_prefab3"));
float tree_weights[] = array(max(chf("../../../tree_weight1"),0.0), max(chf("../../../tree_weight2"),0.0), max(chf("../../../tree_weight3"),0.0));
float tree_scale_min = max(chf("../../../tree_scale_min"),0.01);
float tree_scale_max = max(chf("../../../tree_scale_max"),tree_scale_min);

int valid_count = 0;
int invalid_count = 0;
int ground_quads = 0;
int path_quads = 0;
int water_quads = 0;
int tree_count = 0;

if (enabled)
{
    for (int source_prim=0; source_prim<original_prims; source_prim++)
    {
        int vertices[] = primvertices(0,source_prim);
        vector poly[];
        float heights[];
        float min_y = 1e18, max_y = -1e18;
        foreach (int vtx; vertices)
        {
            vector p = point(0,"P",vertexpoint(0,vtx));
            append(poly,p);
            append(heights,p.y);
            min_y = min(min_y,p.y); max_y = max(max_y,p.y);
        }
        if (len(poly)>3 && distance(poly[0],poly[-1])<0.01)
        {
            pop(poly);
            pop(heights);
        }
        int closed = int(primintrinsic(0,"closed",source_prim));
        if (!closed && len(poly)>2 && distance(poly[0],poly[-1])<0.1) closed=1;

        float signed_area = 0.0;
        vector centroid = 0;
        vector bbmin = set(1e18,0,1e18), bbmax = set(-1e18,0,-1e18);
        foreach (int i; vector p; poly)
        {
            vector q = poly[(i+1)%len(poly)];
            signed_area += p.x*q.z-q.x*p.z;
            centroid += p;
            bbmin.x=min(bbmin.x,p.x); bbmin.z=min(bbmin.z,p.z);
            bbmax.x=max(bbmax.x,p.x); bbmax.z=max(bbmax.z,p.z);
        }
        float area = abs(signed_area)*0.5;
        centroid /= max(len(poly),1);
        heights = sort(heights);
        int height_count = len(heights);
        centroid.y = height_count%2
            ? heights[height_count/2]
            : (heights[max(height_count/2-1,0)]+heights[height_count/2])*0.5;
        int self_intersection=0;
        for (int i=0;i<len(poly) && !self_intersection;i++)
        for (int j=i+1;j<len(poly);j++)
        {
            if (j==i || j==(i+1)%len(poly) || i==(j+1)%len(poly)) continue;
            if (segments_intersect_xz(poly[i],poly[(i+1)%len(poly)],poly[j],poly[(j+1)%len(poly)]))
                self_intersection=1;
        }
        float min_required_area = max(64.0, (path_width+inset+tree_clearance)*16.0);
        int valid = closed && len(poly)>=3 && len(poly)<=512 && !self_intersection
            && max_y-min_y<=0.25 && area>=min_required_area;
        if (!valid) { invalid_count++; continue; }
        valid_count++;

        // Canonical 1 cm boundary hash. Sorting the per-vertex hashes makes
        // park_id invariant to spline input order, start vertex and winding.
        float boundary_sum=0.0;
        float boundary_square_sum=0.0;
        foreach (vector p; poly)
        {
            int qx = int(rint(p.x*100.0));
            int qz = int(rint(p.z*100.0));
            float vertex_hash=frac(
                sin(float(qx)*12.9898+float(qz)*78.233)*43758.5453);
            boundary_sum+=vertex_hash;
            boundary_square_sum+=vertex_hash*vertex_hash;
        }
        int qa=int(rint(area*10.0));
        float boundary_hash=rand(set(
            boundary_sum,
            boundary_square_sum,
            float(qa)+float(len(poly))*0.6180339));
        int park_id=max(1,int(floor(boundary_hash*2147483000.0)));
        float base_y = centroid.y;
        float sx = max(bbmax.x-bbmin.x,1.0), sz=max(bbmax.z-bbmin.z,1.0);
        float target_cells = clamp(area/2.0,64.0,3500.0);
        float cell = clamp(sqrt((sx*sz)/target_cells),0.75,5.0);
        int nx = max(1,int(ceil(sx/cell))), nz=max(1,int(ceil(sz/cell)));
        cell = max(sx/nx,sz/nz);
        nx = min(int(ceil(sx/cell)),128); nz=min(int(ceil(sz/cell)),128);

        float lake_area = area*lake_ratio/max(lake_count,1);
        float base_radius = sqrt(lake_area/M_PI);
        float lake_rx = min(base_radius*1.35,sx*0.34);
        float lake_rz = min(base_radius/1.35,sz*0.34);
        vector lake_centers[];
        for (int li=0; li<lake_count; li++)
        {
            float side = li==0 ? -1.0 : 1.0;
            float ox = side*sx*(lake_count==1 ? 0.0 : 0.16);
            float oz = (rand(set(global_seed,park_id,li))-0.5)*sz*0.12;
            append(lake_centers,set(centroid.x+ox,base_y,centroid.z+oz));
        }
        int branch_offset=int(floor(
            rand(set(float(global_seed+park_id),37.0,91.0))*len(poly)))%len(poly);

        // Exclusion boundary remains an exact projected copy of the authored spline.
        int exclusion_points[];
        foreach (vector p; poly)
        {
            p.y=base_y;
            append(exclusion_points,addpoint(0,p));
        }
        // Use a closed polygon rather than a curve so Houdini Engine always
        // emits a Unity MeshFilter. The renderer is hidden after import; only
        // its ordered perimeter is compiled into PCGSiteExclusionData.
        int exclusion = addprim(0,"poly",exclusion_points);
        tag_surface(exclusion,"exclusion","",park_id);
        setprimattrib(0,"pcg_site_type",exclusion,"park","set");
        setprimattrib(0,"exclude_building",exclusion,1,"set");

        for (int ix=0; ix<nx; ix++)
        for (int iz=0; iz<nz; iz++)
        {
            float x0=bbmin.x+ix*cell, x1=min(x0+cell,bbmax.x);
            float z0=bbmin.z+iz*cell, z1=min(z0+cell,bbmax.z);
            vector p0=set(x0,base_y,z0), p1=set(x1,base_y,z0), p2=set(x1,base_y,z1), p3=set(x0,base_y,z1);
            vector center=(p0+p1+p2+p3)*0.25;
            if (!point_in_polygon_xz(p0,poly) || !point_in_polygon_xz(p1,poly)
                || !point_in_polygon_xz(p2,poly) || !point_in_polygon_xz(p3,poly)) continue;
            float edge_distance=1e18;
            for (int e=0;e<len(poly);e++) edge_distance=min(edge_distance,point_segment_distance_xz(center,poly[e],poly[(e+1)%len(poly)]));
            int force_ground = edge_distance<inset;

            int is_water=0, is_path=0;
            if (water_enabled && !force_ground)
            {
                foreach (int li; vector lc; lake_centers)
                {
                    float metric=lake_metric(center,lc,lake_rx,lake_rz,float(global_seed+park_id+li*17),path_jitter);
                    if (metric<1.0) is_water=1;
                }
            }
            if (!is_water && paths_enabled && !force_ground)
            {
                foreach (int li; vector lc; lake_centers)
                {
                    float metric=lake_metric(
                        center,lc,lake_rx,lake_rz,
                        float(global_seed+park_id+li*17),path_jitter);
                    float radial=(metric-1.0)*min(lake_rx,lake_rz);
                    if (radial>=tree_clearance && radial<=tree_clearance+path_width)
                    {
                        is_path=1;
                        break;
                    }
                }
                for (int bi=0;bi<branch_count && !is_path;bi++)
                {
                    int anchor_index=(branch_offset
                        +int(floor(float(bi)*len(poly)/max(branch_count,1))))%len(poly);
                    vector anchor=poly[anchor_index]; anchor.y=base_y;
                    vector target=lake_centers[0];
                    float dx=anchor.x-target.x, dz=anchor.z-target.z;
                    float inv=1.0/max(sqrt(dx*dx+dz*dz),1e-4);
                    target.x += dx*inv*(max(lake_rx,lake_rz)+tree_clearance+path_width*0.5);
                    target.z += dz*inv*(max(lake_rx,lake_rz)+tree_clearance+path_width*0.5);
                    if (point_segment_distance_xz(center,anchor,target)<=path_width*0.5) is_path=1;
                }
            }
            if (is_water)
            {
                add_surface_quad(p0,p1,p2,p3,base_y-0.04,"water",water_mat,park_id);
                water_quads++;
            }
            else if (is_path)
            {
                add_surface_quad(p0,p1,p2,p3,base_y+0.02,"paths",path_mat,park_id);
                add_surface_quad(p0,p1,p2,p3,base_y,"collision","",park_id);
                path_quads++;
            }
            else
            {
                add_surface_quad(p0,p1,p2,p3,base_y,"ground",ground_mat,park_id);
                ground_quads++;
            }
        }

        if (trees_enabled && tree_density>0 && tree_count<4096)
        {
            int park_tree_count=0;
            // A 1.05x grid with only +/-2% jitter guarantees neighbouring
            // candidates remain at least tree_spacing apart without an O(N^2) loop.
            float sample_cell=max(tree_spacing*1.05,2.0);
            int tx=min(int(ceil(sx/sample_cell)),128), tz=min(int(ceil(sz/sample_cell)),128);
            float probability=clamp(tree_density*sample_cell*sample_cell/10000.0,0.0,1.0);
            float total_weight=max(tree_weights[0]+tree_weights[1]+tree_weights[2],1e-5);
            for (int ix=0;ix<tx && tree_count<4096 && park_tree_count<2048;ix++)
            for (int iz=0;iz<tz && tree_count<4096 && park_tree_count<2048;iz++)
            {
                vector key=set(float(global_seed+park_id),float(ix),float(iz));
                if (rand(key+17.0)>probability) continue;
                float jx=(rand(key+31.0)-0.5)*sample_cell*0.04;
                float jz=(rand(key+47.0)-0.5)*sample_cell*0.04;
                vector p=set(bbmin.x+(ix+0.5)*sample_cell+jx,base_y,bbmin.z+(iz+0.5)*sample_cell+jz);
                if (!point_in_polygon_xz(p,poly)) continue;
                float edge_distance=1e18;
                for (int e=0;e<len(poly);e++) edge_distance=min(edge_distance,point_segment_distance_xz(p,poly[e],poly[(e+1)%len(poly)]));
                if (edge_distance<inset+tree_clearance) continue;
                int blocked=0;
                foreach (int li; vector lc; lake_centers)
                {
                    float metric=lake_metric(
                        p,lc,lake_rx+tree_clearance+cell,lake_rz+tree_clearance+cell,
                        float(global_seed+park_id+li*17),path_jitter);
                    if (water_enabled && metric<1.0) blocked=1;
                }
                if (paths_enabled)
                {
                    foreach (int li; vector lc; lake_centers)
                    {
                        float metric=lake_metric(
                            p,lc,lake_rx,lake_rz,
                            float(global_seed+park_id+li*17),path_jitter);
                        float radial=(metric-1.0)*min(lake_rx,lake_rz);
                        if (radial>=-cell
                            && radial<=tree_clearance*2.0+path_width+cell)
                        {
                            blocked=1;
                            break;
                        }
                    }
                }
                for (int bi=0;bi<branch_count && !blocked;bi++)
                {
                    int anchor_index=(branch_offset
                        +int(floor(float(bi)*len(poly)/max(branch_count,1))))%len(poly);
                    vector anchor=poly[anchor_index]; anchor.y=base_y;
                    vector target=lake_centers[0];
                    if (point_segment_distance_xz(p,anchor,target)
                        <=path_width*0.5+tree_clearance+cell) blocked=1;
                }
                if (blocked) continue;

                float choice=rand(key+71.0)*total_weight;
                int variant=choice<tree_weights[0]?0:(choice<tree_weights[0]+tree_weights[1]?1:2);
                int pt=addpoint(0,p);
                float yaw=rand(key+89.0)*M_PI*2.0;
                float scale=lerp(tree_scale_min,tree_scale_max,rand(key+101.0));
                string group=sprintf("CityPark/Trees/Park_%d/Variant_%d",park_id,variant);
                setpointattrib(0,"park_output",pt,"trees","set");
                setpointattrib(0,"output_role",pt,"park_trees","set");
                setpointattrib(0,"park_id",pt,park_id,"set");
                setpointattrib(0,"pcg_site_type",pt,"park","set");
                setpointattrib(0,"exclude_building",pt,1,"set");
                setpointattrib(0,"unity_instance",pt,tree_prefabs[variant],"set");
                setpointattrib(0,"instance_prefix",pt,group,"set");
                setpointattrib(0,"pcg_group_key",pt,group,"set");
                setpointattrib(0,"pcg_kind",pt,"park_tree","set");
                setpointattrib(0,"pcg_variant",pt,variant,"set");
                setpointattrib(0,"orient",pt,quaternion(yaw,set(0,1,0)),"set");
                setpointattrib(0,"pscale",pt,scale,"set");
                tree_count++;
                park_tree_count++;
            }
        }
    }
}

// Remove only the uploaded authoring curves; all generated geometry was added afterwards.
for (int pr=original_prims-1;pr>=0;pr--) removeprim(0,pr,1);
setdetailattrib(0,"cityroad_city_park_contract", "CITYROAD_V20_CITY_PARK", "set");
setdetailattrib(0,"park_valid_count",valid_count,"set");
setdetailattrib(0,"park_invalid_count",invalid_count,"set");
setdetailattrib(0,"park_ground_quad_count",ground_quads,"set");
setdetailattrib(0,"park_path_quad_count",path_quads,"set");
setdetailattrib(0,"park_water_quad_count",water_quads,"set");
setdetailattrib(0,"park_tree_count",tree_count,"set");
'''


SURFACE_CONTRACT_VEX = r'''
// CITYROAD_V20_CITY_PARK_OUTPUT_CONTRACT
setdetailattrib(0,"unity_split_attr","name","set");
setdetailattrib(0,"cityroad_city_park_contract","CITYROAD_V20_CITY_PARK","set");
'''

TREE_CONTRACT_VEX = r'''
// CITYROAD_V20_CITY_PARK_TREE_CONTRACT
setdetailattrib(0,"unity_split_attr","pcg_group_key","set");
setdetailattrib(0,"cityroad_city_park_contract","CITYROAD_V20_CITY_PARK","set");
'''


def _normalized(path: str) -> str:
    return path.replace("\\", "/")


def _require_node(parent, name: str):
    node = parent.node(name)
    if node is None:
        raise RuntimeError(f"Missing CityRoad prerequisite: {parent.path()}/{name}")
    return node


def _public_hash(asset) -> str:
    script_dir = str(Path(__file__).resolve().parent)
    if script_dir not in sys.path:
        sys.path.insert(0, script_dir)
    import validate_cityroad_contract
    importlib.reload(validate_cityroad_contract)
    return validate_cityroad_contract.public_interface_hash(asset)


def _float_parm(name, label, default, minimum, maximum, help_text):
    return hou.FloatParmTemplate(
        name, label, 1, default_value=(default,), min=minimum, max=maximum,
        min_is_strict=True, max_is_strict=True, help=help_text)


def _int_parm(name, label, default, minimum, maximum, help_text):
    return hou.IntParmTemplate(
        name, label, 1, default_value=(default,), min=minimum, max=maximum,
        min_is_strict=True, max_is_strict=True, help=help_text)


def _toggle(name, label, default, help_text):
    return hou.ToggleParmTemplate(name, label, default_value=default, help=help_text)


def _material_parm(name, label, default):
    return hou.StringParmTemplate(
        name, label, 1, default_value=(default,), string_type=hou.stringParmType.FileReference,
        file_type=hou.fileType.Any, help="Unity Assets/ 路径；Bake 前由项目侧验证。")


def _install_public_parameters(asset):
    ptg = asset.parmTemplateGroup()
    existing = ptg.find("enable_city_park")
    if existing is not None:
        return False

    park_input = hou.StringParmTemplate(
        "unity_park_areas", "Park Areas / 公园边界", 1, default_value=("",),
        string_type=hou.stringParmType.NodeReference,
        help="Unity 闭合 SplineContainer 输入；一个容器可包含多个公园边界。")
    park_input.setTags({"oprelative": "."})

    parms = [
        _toggle("enable_city_park", "Enable City Park / 启用城市公园", False,
                "总开关。关闭或没有边界时公园分支直接输出空结果。"),
        park_input,
        _int_parm("park_seed", "Park Seed / 公园随机种子", 1729, 0, 2147483647,
                  "控制湖泊、园路和树木的确定性随机布局。"),
        _float_parm("park_boundary_inset", "Boundary Inset (m) / 边界内缩", 2.0, 0.0, 20.0,
                    "从地块边界向内保留的安全距离。"),
        _toggle("enable_park_water", "Enable Lake / 启用湖泊", True, "生成 1-2 个低成本不透明湖面。"),
        _int_parm("park_lake_count", "Lake Count / 湖泊数量", 1, 1, 2, "V1 支持 1-2 个湖泊。"),
        _float_parm("park_lake_area_ratio", "Lake Area Ratio / 湖泊面积占比", 0.25, 0.05, 0.45,
                    "湖泊目标面积相对公园面积的比例。"),
        _toggle("enable_park_paths", "Enable Paths / 启用园路", True, "生成湖边环路与随机支路。"),
        _float_parm("park_path_width", "Path Width (m) / 园路宽度", 3.0, 0.5, 10.0,
                    "园路渲染和碰撞宽度。"),
        _int_parm("park_path_branch_count", "Path Branch Count / 园路支路数", 2, 0, 3,
                  "从边界连接到环路的支路数量。"),
        _float_parm("park_path_jitter", "Path Jitter / 园路扰动", 0.15, 0.0, 0.35,
                    "控制环路轮廓的低频扰动强度。"),
        _toggle("enable_park_trees", "Enable Park Trees / 启用公园树木", True,
                "树点复用 CityRoad Tree Variants 调色板。"),
        _float_parm("park_tree_density_per_hectare", "Tree Density (/ha) / 每公顷树密度", 120.0, 0.0, 1000.0,
                    "最终仍受每公园/每 CityRoad 实例预算限制。"),
        _float_parm("park_tree_min_spacing", "Tree Minimum Spacing (m) / 树最小间距", 6.0, 1.0, 30.0,
                    "规则网格散布单元尺寸，避免密集重叠。"),
        _float_parm("park_tree_clearance", "Tree Clearance (m) / 树木净距", 2.5, 0.0, 20.0,
                    "树木到边界、湖岸和园路的额外净距。"),
        _material_parm("park_ground_unity_material", "Ground Unity Material / 草地 Unity 材质",
                       "Assets/PCG/Materials/CityPark/M_PCG_CityPark_Grass.mat"),
        _material_parm("park_path_unity_material", "Path Unity Material / 园路 Unity 材质",
                       "Assets/PCG/Materials/CityPark/M_PCG_CityPark_Path.mat"),
        _material_parm("park_water_unity_material", "Water Unity Material / 湖水 Unity 材质",
                       "Assets/PCG/Materials/CityPark/M_PCG_CityPark_Water.mat"),
    ]
    folder = hou.FolderParmTemplate(
        "city_park_folder", "City Park / 城市公园", parm_templates=parms,
        folder_type=hou.folderType.Simple)
    folder.setHelp("指定闭合地块并生成移动端友好的灰盒城市公园。")
    ptg.append(folder)
    asset.setParmTemplateGroup(ptg)
    return True


def _configure_blast(node, entity, group):
    node.parm("grouptype").set(entity)
    node.parm("group").set(group)
    node.parm("negate").set(1)
    node.parm("fillhole").set(0)


def _create_output_branch(subnet, generator, role: str, index: int):
    is_tree = role == "trees"
    blast = subnet.createNode("blast", f"PARK_KEEP_{role.upper()}")
    blast.setInput(0, generator)
    _configure_blast(blast, 3 if is_tree else 4, f"@park_output={role}")
    contract = subnet.createNode("attribwrangle", f"PARK_{role.upper()}_OUTPUT_CONTRACT")
    contract.setInput(0, blast)
    contract.parm("class").set(0)
    contract.parm("snippet").set(TREE_CONTRACT_VEX if is_tree else SURFACE_CONTRACT_VEX)
    contract.setComment(f"City Park {role} 的稳定 Unity/Bake metadata 合约。")
    contract.setGenericFlag(hou.nodeFlag.DisplayComment, True)
    previous = contract
    if role in ("ground", "paths", "water"):
        normal = subnet.createNode("normal", f"PARK_{role.upper()}_NORMALS")
        normal.setInput(0, contract)
        previous = normal
    output = subnet.createNode("output", f"SUBNET_OUT_PARK_{role.upper()}_{index}")
    output.setInput(0, previous)
    output.parm("outputidx").set(index)
    output.setComment(f"CR_CITY_PARK {role} 稳定子网输出。")
    output.setGenericFlag(hou.nodeFlag.DisplayComment, True)
    return output


def _install_network(asset):
    core = _require_node(asset, "CityRoadCore")
    existing = core.node(SUBNET_NAME)
    if existing is not None:
        generator = existing.node("PARK_LAYOUT_AND_SCATTER_V20")
        if generator is None or MARKER not in generator.parm("snippet").evalAsString():
            raise RuntimeError("Existing CR_CITY_PARK does not match the V20 marker")
        created = []
        empty_input = existing.node("EMPTY_PARK_AREAS")
        park_input = existing.node("IN_UNITY_PARK_AREAS")
        if empty_input is None or park_input is None:
            raise RuntimeError("Existing CR_CITY_PARK input contract is incomplete")
        input_switch = existing.node("PARK_ENABLE_INPUT_SWITCH")
        if input_switch is None:
            input_switch = existing.createNode("switch", "PARK_ENABLE_INPUT_SWITCH")
            created.append(input_switch)
        input_switch.setInput(0, empty_input)
        input_switch.setInput(1, park_input)
        input_switch.parm("input").setExpression(
            'if(ch("../../../enable_city_park")!=0'
            ' && strlen(chs("../../../unity_park_areas"))>0,1,0)',
            language=hou.exprLanguage.Hscript)
        input_switch.setComment("总开关关闭或边界未绑定时，不 Cook Unity Object Merge 分支。")
        input_switch.setGenericFlag(hou.nodeFlag.DisplayComment, True)
        generator.setInput(0, input_switch)
        generator.parm("snippet").set(PARK_GENERATOR_VEX)
        for role in ("ground", "paths", "water", "collision", "trees", "exclusion"):
            contract = _require_node(existing, f"PARK_{role.upper()}_OUTPUT_CONTRACT")
            contract.setComment(f"City Park {role} 的稳定 Unity/Bake metadata 合约。")
            contract.setGenericFlag(hou.nodeFlag.DisplayComment, True)
        for child in existing.children():
            if child.type().name() == "output":
                child.setComment("CR_CITY_PARK 稳定子网输出。")
                child.setGenericFlag(hou.nodeFlag.DisplayComment, True)
        for index, output_name in enumerate(OUTPUT_NAMES):
            output = _require_node(core, output_name)
            output.parm("outputidx").set(OUTPUT_INDEX_BASE + index)
        existing.layoutChildren(horizontal_spacing=1.5, vertical_spacing=1.5)
        empty_input.setPosition(hou.Vector2((-33.0, 7.0)))
        input_switch.setPosition(hou.Vector2((-31.0, 5.2)))
        return True, created

    created = []
    subnet = core.createNode("subnet", SUBNET_NAME)
    created.append(subnet)
    subnet.setComment(
        "城市公园 V20：闭合边界校验 → 网格化湖/路/草地 → 树点散布 → 六类稳定输出。\n"
        "运行时只消费 Bake 后 Unity Mesh/Collider/GPU instance 数据。")
    subnet.setGenericFlag(hou.nodeFlag.DisplayComment, True)
    subnet.setColor(hou.Color((0.22, 0.48, 0.24)))
    subnet.setPosition(hou.Vector2((44.0, -54.0)))

    empty_input = subnet.createNode("null", "EMPTY_PARK_AREAS")
    empty_input.setComment("空输入/无效绑定的零成本回退，避免 Object Merge 诊断污染。")
    park_input = subnet.createNode("object_merge", "IN_UNITY_PARK_AREAS")
    park_input.parm("numobj").set(1)
    park_input.parm("objpath1").setExpression(
        'ifs(strlen(chs("../../../unity_park_areas"))>0'
        ' && opexist(chsop("../../../unity_park_areas")),'
        ' chsop("../../../unity_park_areas"),"../EMPTY_PARK_AREAS")',
        language=hou.exprLanguage.Hscript)
    park_input.parm("xformtype").set(2)
    park_input.parm("pack").set(0)
    park_input.setComment("Unity 闭合 SplineContainer 参数输入；保持世界坐标。")
    park_input.setGenericFlag(hou.nodeFlag.DisplayComment, True)

    input_switch = subnet.createNode("switch", "PARK_ENABLE_INPUT_SWITCH")
    input_switch.setInput(0, empty_input)
    input_switch.setInput(1, park_input)
    input_switch.parm("input").setExpression(
        'if(ch("../../../enable_city_park")!=0'
        ' && strlen(chs("../../../unity_park_areas"))>0,1,0)',
        language=hou.exprLanguage.Hscript)
    input_switch.setComment("总开关关闭或边界未绑定时，不 Cook Unity Object Merge 分支。")
    input_switch.setGenericFlag(hou.nodeFlag.DisplayComment, True)

    generator = subnet.createNode("attribwrangle", "PARK_LAYOUT_AND_SCATTER_V20")
    generator.setInput(0, input_switch)
    generator.parm("class").set(0)
    generator.parm("snippet").set(PARK_GENERATOR_VEX)
    generator.setComment(
        "单次编辑期生成：规则网格保证草地/园路/湖面互斥；树木只输出点和实例 metadata。")
    generator.setGenericFlag(hou.nodeFlag.DisplayComment, True)

    role_order = ("ground", "paths", "water", "collision", "trees", "exclusion")
    for index, role in enumerate(role_order):
        _create_output_branch(subnet, generator, role, index)

    subnet.layoutChildren(horizontal_spacing=1.5, vertical_spacing=1.5)
    empty_input.setPosition(hou.Vector2((-33.0, 7.0)))
    input_switch.setPosition(hou.Vector2((-31.0, 5.2)))
    box = subnet.createNetworkBox("PARK_V20_GENERATION")
    box.setComment("城市公园 V20｜输入、布局、表面、植被与排除合约")
    box.setColor(hou.Color((0.18, 0.38, 0.20)))
    for child in subnet.children():
        box.addItem(child)
    box.fitAroundContents()

    for index, output_name in enumerate(OUTPUT_NAMES):
        output = core.createNode("output", output_name)
        output.setInput(0, subnet, index)
        output.parm("outputidx").set(OUTPUT_INDEX_BASE + index)
        output.setPosition(hou.Vector2((52.0 + index*2.2, -58.0)))
        output.setComment("City Park V20 stable output contract")
        output.setGenericFlag(hou.nodeFlag.DisplayComment, True)
        created.append(output)
    return True, created


def _validate_hot(asset):
    core = _require_node(asset, "CityRoadCore")
    subnet = _require_node(core, SUBNET_NAME)
    generator = _require_node(subnet, "PARK_LAYOUT_AND_SCATTER_V20")
    if MARKER not in generator.parm("snippet").evalAsString():
        raise RuntimeError("V20 generator marker is missing")
    stats = {}
    for name in OUTPUT_NAMES:
        node = _require_node(core, name)
        try:
            node.cook(force=True)
        except hou.OperationFailed as exc:
            diagnostics = []
            for candidate in (node,) + tuple(subnet.allSubChildren()):
                errors = tuple(candidate.errors())
                warnings = tuple(candidate.warnings())
                if errors or warnings:
                    diagnostics.append((candidate.path(), errors, warnings))
            raise RuntimeError(
                f"{name} failed to cook: {exc}; "
                f"diagnostics={diagnostics}") from exc
        if node.errors() or node.warnings():
            raise RuntimeError(f"{name} diagnostics: errors={node.errors()} warnings={node.warnings()}")
        geo = node.geometry()
        stats[name] = {"points": len(geo.points()), "primitives": len(geo.prims())}
    return stats


def apply_live_patch(save: bool = False, hou_module=None):
    global hou
    if hou_module is not None:
        hou = hou_module
    if hou is None:
        raise RuntimeError("The hou module is unavailable")

    asset = hou.node(ASSET_PATH)
    if asset is None or asset.type().name() != EXPECTED_TYPE:
        raise RuntimeError(f"Expected {EXPECTED_TYPE} at {ASSET_PATH}")
    definition = asset.type().definition()
    if definition is None:
        raise RuntimeError("CityRoad asset has no definition")
    library = _normalized(definition.libraryFilePath())
    hip = _normalized(hou.hipFile.path())
    if not library.endswith(EXPECTED_HDA_SUFFIX):
        raise RuntimeError(f"Unexpected CityRoad definition: {library}")
    if not hip.endswith(EXPECTED_HIP_SUFFIX):
        raise RuntimeError(f"Unexpected CityRoad HIP: {hip}")

    already_applied = asset.parm("enable_city_park") is not None and asset.node(
        "CityRoadCore/CR_CITY_PARK/PARK_LAYOUT_AND_SCATTER_V20") is not None
    if not already_applied:
        actual_hash = _public_hash(asset)
        if actual_hash != EXPECTED_PUBLIC_HASH:
            raise RuntimeError(
                "CityRoad V20 public-interface precondition changed: "
                f"actual={actual_hash} expected={EXPECTED_PUBLIC_HASH}")

    interface_before = asset.parmTemplateGroup()
    created_top = []
    try:
        with hou.undos.group("CityRoad V20 City Park"):
            interface_changed = _install_public_parameters(asset)
            network_changed, created_top = _install_network(asset)
            stats = _validate_hot(asset)
    except Exception:
        for node in reversed(created_top):
            if node is not None:
                try:
                    node.destroy()
                except Exception:
                    pass
        if asset.node("CityRoadCore/CR_CITY_PARK") is not None and not already_applied:
            try:
                asset.node("CityRoadCore/CR_CITY_PARK").destroy()
            except Exception:
                pass
        asset.setParmTemplateGroup(interface_before)
        raise

    if save:
        definition.updateFromNode(asset)
        hou.hipFile.save()
    return {
        "status": "PASS",
        "asset": asset.path(),
        "definition": library,
        "hip": hip,
        "saved": bool(save),
        "already_applied": bool(already_applied),
        "public_interface_sha256": _public_hash(asset),
        "outputs": stats,
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=18811)
    parser.add_argument("--save", default="false")
    args = parser.parse_args()
    import hrpyc
    connection, remote_hou = hrpyc.import_remote_module(args.host, args.port, "hou")
    try:
        tools_path = str(Path(__file__).resolve().parent).replace("\\", "/")
        connection.execute(
            "import sys, importlib; "
            f"sys.path.insert(0, {tools_path!r}) if {tools_path!r} not in sys.path else None; "
            "import patch_cityroad_city_park_v20_20260813 as _park_patch; "
            "importlib.reload(_park_patch)")
        payload = connection.eval(
            "_park_patch.apply_live_patch(save="
            + ("True" if args.save.lower() == "true" else "False")
            + ")")
        print(json.dumps(payload, ensure_ascii=False, default=list, indent=2))
    finally:
        connection.close()


if __name__ == "__main__":
    main()
