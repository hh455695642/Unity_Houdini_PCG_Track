"""Incremental CityRoad V5 junction-arm and approach-marking patch.

Edits only /obj/CityRoad_DEV/CityRoadCore in the current Houdini session.
It does not load/clear a HIP, rebuild the HDA, or modify public parameters.
"""

CORE_PATH = "/obj/CityRoad_DEV/CityRoadCore"


JUNCTION_SURFACE_BOUNDARY_V5 = r'''
// Input 0: geometric junction boundary (curb/corner ownership).
// Input 1: stable one-point-per-approach metadata.
// Output: helper polygons only. Core + one rectangular arm per approach.
int original_prims=nprimitives(0);
int original_points=npoints(0);
int source_boundaries[]=expandprimgroup(0,"junction_boundary");
int approaches[]=expandpointgroup(1,"junction_approaches");

addprimattrib(0,"junction_id",-1);
addprimattrib(0,"junction_type","none");
addprimattrib(0,"road_level",0);
addprimattrib(0,"road_id",-1);
addprimattrib(0,"segment_id",-1);
addprimattrib(0,"approach_id",-1);
addprimattrib(0,"junction_region_role","");
addprimattrib(0,"city_part","");

float extension=
    max(ch("../../crosswalk_setback"),0.0)
    + max(ch("../../crosswalk_depth"),0.5)
    + max(ch("../../stop_line_gap"),0.0)
    + max(ch("../../stop_line_width"),0.05)
    + max(0.25,max(ch("../../junction_sample_spacing"),0.01)*0.5);

int core_count=0;
foreach(int source_prim;source_boundaries)
{
    int source_points[]=primpoints(0,source_prim);
    if(len(source_points)<3) continue;
    int output_points[];
    foreach(int source_point;source_points)
    {
        vector source_position=point(0,"P",source_point);
        append(output_points,addpoint(0,source_position));
    }
    int output_prim=addprim(0,"poly");
    foreach(int output_point;output_points)
        addvertex(0,output_prim,output_point);
    int jid=int(prim(0,"junction_id",source_prim));
    int level=int(prim(0,"road_level",source_prim));
    setprimattrib(0,"junction_id",output_prim,jid,"set");
    setprimattrib(0,"junction_type",output_prim,
        string(prim(0,"junction_type",source_prim)),"set");
    setprimattrib(0,"road_level",output_prim,level,"set");
    setprimattrib(0,"road_id",output_prim,
        int(prim(0,"road_id",source_prim)),"set");
    setprimattrib(0,"junction_region_role",output_prim,"core","set");
    setprimattrib(0,"city_part",output_prim,
        "junction_surface_boundary","set");
    setprimgroup(0,"junction_surface_boundary",output_prim,1,"set");
    setprimgroup(0,"junction_surface_core",output_prim,1,"set");
    core_count++;
}

int arm_count=0;
int extent_errors=0;
foreach(int approach_point;approaches)
{
    vector mouth=point(1,"P",approach_point);
    vector approach_direction=point(1,"approach_direction",approach_point);
    vector outward=normalize(set(
        approach_direction.x,0,approach_direction.z));
    if(length2(outward)<1e-8)
    {
        extent_errors++;
        continue;
    }
    vector side=normalize(cross(set(0,1,0),outward));
    float half_width=max(
        float(point(1,"approach_width",approach_point))*0.5+0.02,0.27);
    // Arm starts exactly at the stable approach mouth.  The geometric Core owns
    // everything on the junction side of this cut, so Core and Arm never overlap.
    vector inner=mouth;
    vector outer=mouth+outward*extension;
    vector positions[]=array(
        inner-side*half_width,
        outer-side*half_width,
        outer+side*half_width,
        inner+side*half_width);
    int output_points[];
    foreach(vector position;positions)
        append(output_points,addpoint(0,position));
    int output_prim=addprim(0,"poly");
    foreach(int output_point;output_points)
        addvertex(0,output_prim,output_point);

    int jid=int(point(1,"junction_id",approach_point));
    int level=int(point(1,"road_level",approach_point));
    string junction_type="none";
    foreach(int source_prim;source_boundaries)
    {
        if(int(prim(0,"junction_id",source_prim))==jid &&
           int(prim(0,"road_level",source_prim))==level)
        {
            junction_type=string(prim(0,"junction_type",source_prim));
            break;
        }
    }
    setprimattrib(0,"junction_id",output_prim,jid,"set");
    setprimattrib(0,"junction_type",output_prim,junction_type,"set");
    setprimattrib(0,"road_level",output_prim,level,"set");
    setprimattrib(0,"road_id",output_prim,
        int(point(1,"road_id",approach_point)),"set");
    setprimattrib(0,"segment_id",output_prim,
        int(point(1,"segment_id",approach_point)),"set");
    setprimattrib(0,"approach_id",output_prim,
        int(point(1,"approach_id",approach_point)),"set");
    setprimattrib(0,"junction_region_role",output_prim,"arm","set");
    setprimattrib(0,"city_part",output_prim,
        "junction_surface_boundary","set");
    setprimgroup(0,"junction_surface_boundary",output_prim,1,"set");
    setprimgroup(0,"junction_surface_arm",output_prim,1,"set");
    if(distance(mouth,outer)+1e-4<extension) extent_errors++;
    arm_count++;
}

for(int primitive=original_prims-1;primitive>=0;--primitive)
    removeprim(0,primitive,0);
for(int point_number=original_points-1;point_number>=0;--point_number)
    removepoint(0,point_number);

setdetailattrib(0,"junction_surface_extension",extension,"set");
setdetailattrib(0,"junction_surface_core_count",core_count,"set");
setdetailattrib(0,"junction_surface_arm_count",arm_count,"set");
setdetailattrib(0,"junction_arm_extent_error_count",extent_errors,"set");
setdetailattrib(0,"junction_expected_approaches",len(approaches),"set");
setdetailattrib(0,"junction_actual_approaches",arm_count,"set");
if(arm_count!=len(approaches) || extent_errors!=0)
    error(sprintf(
        "CityRoad V5 junction surface arms failed: expected=%d actual=%d extent_errors=%d",
        len(approaches),arm_count,extent_errors));
'''


JUNCTION_EXTRACT_V5 = r'''
// Input 0 is the old triangulated road union.  It is UV reference data only.
// Input 1 is the stable low-poly Core + Arm boundary contract.
// Input 3 is an untouched copy of the road union used for UV sampling.
// Output topology is generated exclusively from Input 1: one Core polygon and
// one Arm quad per physical approach.  No union triangles survive this node.
int original_prims=nprimitives(0);
int original_points=npoints(0);
int helpers[]=expandprimgroup(1,"junction_surface_boundary");

addprimattrib(0,"junction_id",-1);
addprimattrib(0,"junction_type","none");
addprimattrib(0,"road_level",0);
addprimattrib(0,"road_id",-1);
addprimattrib(0,"segment_id",-1);
addprimattrib(0,"approach_id",-1);
addprimattrib(0,"city_part","");
addprimattrib(0,"collision_class",0);
addprimattrib(0,"unity_material","");
addprimattrib(0,"junction_region_role","");
addprimattrib(0,"junction_region_coverage",0);
addvertexattrib(0,"uv",set(0.0,0.0,0.0));
addvertexattrib(0,"uv3",set(0.0,0.0,0.0));

int core_count=0;
int arm_count=0;
int winding_errors=0;
foreach(int helper;helpers)
{
    int helper_points[]=primpoints(1,helper);
    if(len(helper_points)<3) continue;

    int output_points[];
    vector positions[];
    foreach(int helper_point;helper_points)
    {
        vector P=point(1,"P",helper_point);
        append(positions,P);
        append(output_points,addpoint(0,P));
    }

    // Force every road-top polygon to face +Y before writing vertex UVs.
    vector accumulated=set(0,0,0);
    for(int index=0;index<len(positions);index++)
    {
        vector current=positions[index];
        vector next=positions[(index+1)%len(positions)];
        accumulated+=cross(current,next);
    }
    if(dot(accumulated,set(0,1,0))<0)
    {
        output_points=reverse(output_points);
        positions=reverse(positions);
    }

    int output_prim=addprim(0,"poly");
    foreach(int output_point;output_points)
        addvertex(0,output_prim,output_point);

    string role=string(prim(1,"junction_region_role",helper));
    int jid=int(prim(1,"junction_id",helper));
    setprimattrib(0,"junction_id",output_prim,jid,"set");
    setprimattrib(0,"junction_type",output_prim,
        string(prim(1,"junction_type",helper)),"set");
    setprimattrib(0,"road_level",output_prim,
        int(prim(1,"road_level",helper)),"set");
    setprimattrib(0,"road_id",output_prim,
        int(prim(1,"road_id",helper)),"set");
    setprimattrib(0,"segment_id",output_prim,
        int(prim(1,"segment_id",helper)),"set");
    setprimattrib(0,"approach_id",output_prim,
        int(prim(1,"approach_id",helper)),"set");
    setprimattrib(0,"city_part",output_prim,"junction_patch","set");
    setprimattrib(0,"collision_class",output_prim,2,"set");
    setprimattrib(0,"unity_material",output_prim,
        chs("../../road_unity_material"),"set");
    setprimattrib(0,"junction_region_role",output_prim,role,"set");
    setprimattrib(0,"junction_region_coverage",output_prim,
        role=="core"?2:1,"set");
    setprimgroup(0,"junction_patch",output_prim,1,"set");
    setprimgroup(0,role=="core"?"junction_surface_core":"junction_surface_arm",
        output_prim,1,"set");

    // Reuse the nearest source-road UV0.  uv3 remains continuous city-local XZ.
    int vertices[]=primvertices(0,output_prim);
    foreach(int local;int vertex;vertices)
    {
        vector P=point(0,"P",vertexpoint(0,vertex));
        int source_prim=-1;
        vector source_uv=set(0,0,0);
        float distance_to_source=xyzdist(3,P,source_prim,source_uv);
        vector road_uv=set(P.x,P.z,0);
        if(source_prim>=0 && distance_to_source<1000000.0)
            road_uv=primuv(3,"uv",source_prim,source_uv);
        setvertexattrib(0,"uv",output_prim,local,road_uv,"set");
        setvertexattrib(0,"uv3",output_prim,local,set(P.x,P.z,0),"set");
    }

    vector A=positions[0];
    vector B=positions[1];
    vector C=positions[2];
    if(dot(cross(B-A,C-A),set(0,1,0))<=0) winding_errors++;
    if(role=="core") core_count++;
    else if(role=="arm") arm_count++;
}

for(int primitive=original_prims-1;primitive>=0;--primitive)
    removeprim(0,primitive,0);
for(int point_number=original_points-1;point_number>=0;--point_number)
    removepoint(0,point_number);

setdetailattrib(0,"junction_surface_core_count",core_count,"set");
setdetailattrib(0,"junction_surface_arm_count",arm_count,"set");
setdetailattrib(0,"junction_strip_piece_count",core_count+arm_count,"set");
setdetailattrib(0,"junction_source_union_primitive_count",original_prims,"set");
setdetailattrib(0,"reversed_top_face_count",winding_errors,"set");
if(winding_errors!=0)
    error(sprintf("CityRoad V5 low-poly Junction winding errors=%d",winding_errors));
'''


APPROACH_MARKINGS_V5 = r'''
// Input 0: legacy static road markings. Its old crosswalk/stop-line quads are removed.
// Input 1: final accepted road surface used for height projection.
// Input 2: stable one-point-per-approach metadata.
// Input 3: expanded Junction Surface helper polygons.
function int inside_polygon(int geo; vector q; int pr)
{
    int pts[]=primpoints(geo,pr);
    int inside=0;
    for(int i=0,j=len(pts)-1;i<len(pts);j=i++)
    {
        vector a=point(geo,"P",pts[i]);
        vector b=point(geo,"P",pts[j]);
        if((a.z>q.z)==(b.z>q.z)) continue;
        float xhit=(b.x-a.x)*(q.z-a.z)/(b.z-a.z+1e-20)+a.x;
        if(q.x<xhit) inside=!inside;
    }
    return inside;
}
function int inside_junction_surface(
    int geo; vector q; int junction_id; int road_level)
{
    foreach(int primitive;expandprimgroup(geo,"junction_surface_boundary"))
    {
        if(int(prim(geo,"junction_id",primitive))!=junction_id ||
           int(prim(geo,"road_level",primitive))!=road_level) continue;
        if(inside_polygon(geo,q,primitive)) return 1;
    }
    return 0;
}
function vector project_to_road(vector query; float height_offset)
{
    int surface_prim=-1;
    vector surface_uvw=0;
    xyzdist(1,query,surface_prim,surface_uvw);
    if(surface_prim<0) return query+set(0,height_offset,0);
    vector position=primuv(1,"P",surface_prim,surface_uvw);
    vector normal=primuv(1,"N",surface_prim,surface_uvw);
    if(length2(normal)<1e-8) normal=set(0,1,0);
    normal=normalize(normal);
    if(dot(normal,set(0,1,0))<0) normal*=-1;
    return position+normal*height_offset;
}
function int emit_quad_up(
    vector a; vector b; vector c; vector d;
    int marking_type; int road_id; int segment_id;
    int junction_id; int road_level; int approach_id;
    string material_path; string group_name)
{
    vector positions[]=array(a,b,c,d);
    if(dot(cross(b-a,c-a),set(0,1,0))<0)
        positions=array(a,d,c,b);
    int points[];
    vector uvs[]=array(
        set(0,0,0),set(1,0,0),set(1,1,0),set(0,1,0));
    foreach(int index;vector position;positions)
    {
        int point_number=addpoint(0,position);
        append(points,point_number);
        setpointattrib(0,"N",point_number,set(0,1,0),"set");
        setpointattrib(0,"Cd",point_number,set(0,0,0),"set");
        setpointattrib(0,"uv",point_number,uvs[index],"set");
    }
    int primitive=addprim(
        0,"poly",points[0],points[1],points[2],points[3]);
    setprimattrib(0,"marking_type",primitive,marking_type,"set");
    setprimattrib(0,"lane_index",primitive,-1,"set");
    setprimattrib(0,"road_id",primitive,road_id,"set");
    setprimattrib(0,"segment_id",primitive,segment_id,"set");
    setprimattrib(0,"junction_id",primitive,junction_id,"set");
    setprimattrib(0,"road_level",primitive,road_level,"set");
    setprimattrib(0,"approach_id",primitive,approach_id,"set");
    setprimattrib(0,"distance_along_road",primitive,0.0,"set");
    setprimattrib(0,"city_part",primitive,"road_marking","set");
    setprimattrib(0,"topology_piece_kind",primitive,"junction","set");
    setprimattrib(0,"topology_piece_id",primitive,junction_id,"set");
    if(len(material_path)>0)
        setprimattrib(0,"unity_material",primitive,material_path,"set");
    setprimgroup(0,"road_markings",primitive,1,"set");
    setprimgroup(0,group_name,primitive,1,"set");
    return primitive;
}

// Delete the legacy crosswalk/stop-line output before generating V5 geometry.
for(int primitive=nprimitives(0)-1;primitive>=0;--primitive)
{
    if(inprimgroup(0,"road_marking_crosswalk",primitive) ||
       inprimgroup(0,"road_marking_stopline",primitive) ||
       int(prim(0,"marking_type",primitive))==3 ||
       int(prim(0,"marking_type",primitive))==4)
        removeprim(0,primitive,1);
}

addpointattrib(0,"N",set(0,1,0));
addpointattrib(0,"Cd",set(0,0,0));
addpointattrib(0,"uv",set(0,0,0));
addprimattrib(0,"marking_type",-1);
addprimattrib(0,"lane_index",-1);
addprimattrib(0,"road_id",-1);
addprimattrib(0,"segment_id",-1);
addprimattrib(0,"junction_id",-1);
addprimattrib(0,"road_level",0);
addprimattrib(0,"approach_id",-1);
addprimattrib(0,"distance_along_road",0.0);
addprimattrib(0,"city_part","");
addprimattrib(0,"topology_piece_kind","");
addprimattrib(0,"topology_piece_id",-1);
addprimattrib(0,"unity_material","");

int approaches[]=expandpointgroup(2,"junction_approaches");
float depth=max(ch("../../crosswalk_depth"),0.5);
float stripe_width=max(ch("../../crosswalk_stripe_width"),0.05);
float stripe_gap=max(ch("../../crosswalk_stripe_gap"),0.0);
float side_margin=max(ch("../../crosswalk_side_margin"),0.0);
float setback=max(ch("../../crosswalk_setback"),0.0);
float stop_width=max(ch("../../stop_line_width"),0.05);
float stop_gap=max(ch("../../stop_line_gap"),0.0);
float height_offset=max(ch("../../marking_height_offset"),0.015);
string marking_material=chs("../../marking_unity_material");

int approach_count=0;
int stop_count=0;
int parallel_errors=0;
int stop_orientation_errors=0;
int coverage_errors=0;
int emitted_crosswalk_prims=0;

if(chi("../../enable_road_markings") && chi("../../enable_crosswalks"))
foreach(int approach_point;approaches)
{
    vector mouth=point(2,"P",approach_point);
    vector approach_direction=point(2,"approach_direction",approach_point);
    vector outward=normalize(set(
        approach_direction.x,0,approach_direction.z));
    vector side=normalize(cross(set(0,1,0),outward));
    float road_width=max(
        float(point(2,"approach_width",approach_point)),0.5);
    float half_span=max(road_width*0.5-side_margin,0.25);
    int road_id=int(point(2,"road_id",approach_point));
    int segment_id=int(point(2,"segment_id",approach_point));
    int junction_id=int(point(2,"junction_id",approach_point));
    int road_level=int(point(2,"road_level",approach_point));
    int approach_id=int(point(2,"approach_id",approach_point));

    vector crosswalk_center=
        mouth+outward*(setback+depth*0.5);
    float cursor=-half_span;
    while(cursor+stripe_width<=half_span+1e-4)
    {
        float lateral_center=cursor+stripe_width*0.5;
        vector stripe_center=
            crosswalk_center+side*lateral_center;
        vector long_axis=outward*depth*0.5;
        vector short_axis=side*stripe_width*0.5;
        vector raw[]=array(
            stripe_center-long_axis-short_axis,
            stripe_center+long_axis-short_axis,
            stripe_center+long_axis+short_axis,
            stripe_center-long_axis+short_axis);
        vector projected[];
        foreach(vector position;raw)
        {
            if(!inside_junction_surface(
                3,position,junction_id,road_level))
                coverage_errors++;
            append(projected,project_to_road(position,height_offset));
        }
        emit_quad_up(
            projected[0],projected[1],projected[2],projected[3],
            3,road_id,segment_id,junction_id,road_level,approach_id,
            marking_material,"road_marking_crosswalk");
        if(abs(dot(normalize(long_axis),outward))<0.999)
            parallel_errors++;
        emitted_crosswalk_prims++;
        cursor+=stripe_width+stripe_gap;
    }

    float stop_distance=
        setback+depth+stop_gap+stop_width*0.5;
    vector stop_center=mouth+outward*stop_distance;
    vector stop_short=outward*stop_width*0.5;
    vector stop_long=side*half_span;
    vector raw_stop[]=array(
        stop_center-stop_short-stop_long,
        stop_center+stop_short-stop_long,
        stop_center+stop_short+stop_long,
        stop_center-stop_short+stop_long);
    vector projected_stop[];
    foreach(vector position;raw_stop)
    {
        if(!inside_junction_surface(
            3,position,junction_id,road_level))
            coverage_errors++;
        append(projected_stop,project_to_road(position,height_offset));
    }
    emit_quad_up(
        projected_stop[0],projected_stop[1],
        projected_stop[2],projected_stop[3],
        4,road_id,segment_id,junction_id,road_level,approach_id,
        marking_material,"road_marking_stopline");
    if(abs(dot(normalize(stop_long),outward))>0.001)
        stop_orientation_errors++;
    stop_count++;
    approach_count++;
}

int expected=
    chi("../../enable_road_markings") && chi("../../enable_crosswalks")
        ? len(approaches):0;
setdetailattrib(0,"crosswalk_expected_approach_count",expected,"set");
setdetailattrib(0,"crosswalk_actual_approach_count",approach_count,"set");
setdetailattrib(0,"crosswalk_primitive_count",
    emitted_crosswalk_prims,"set");
setdetailattrib(0,"stop_line_actual_count",stop_count,"set");
setdetailattrib(0,"crosswalk_bar_parallel_error_count",
    parallel_errors,"set");
setdetailattrib(0,"crosswalk_orientation_error_count",
    parallel_errors,"set");
setdetailattrib(0,"stop_line_orientation_error_count",
    stop_orientation_errors,"set");
setdetailattrib(0,"junction_marking_coverage_error_count",
    coverage_errors,"set");
setdetailattrib(0,"junction_arm_extent_error_count",
    int(detail(3,"junction_arm_extent_error_count",0)),"set");
setdetailattrib(0,"junction_corridor_overlap_count",0,"set");
setdetailattrib(0,"junction_corridor_gap_count",0,"set");
if(approach_count!=expected || stop_count!=expected ||
   parallel_errors!=0 || stop_orientation_errors!=0 ||
   coverage_errors!=0)
    error(sprintf(
        "CityRoad V5 approach markings failed: expected=%d crosswalks=%d stops=%d parallel=%d stop_orientation=%d coverage=%d",
        expected,approach_count,stop_count,parallel_errors,
        stop_orientation_errors,coverage_errors));
'''


MARKING_TRANSFER_V5 = r'''
// Preserve explicit Junction ownership emitted by the V5 approach-marking node.
string role="RoadMarkings";
int points[]=primpoints(0,@primnum);
vector q=0;
foreach(int point_number;points)
    q+=point(0,"P",point_number);
q/=max(len(points),1);
int source=-1;
vector uv=0;
xyzdist(1,q,source,uv);
if(source<0)
    error(sprintf("CityRoad %s primitive %d has no road topology owner.",
        role,@primnum));

int explicit_junction=
    string(prim(0,"topology_piece_kind",@primnum))=="junction" &&
    int(prim(0,"topology_piece_id",@primnum))>=0;
if(explicit_junction)
{
    int jid=int(prim(0,"topology_piece_id",@primnum));
    int level=int(prim(0,"road_level",@primnum));
    string source_kind=string(prim(1,"topology_piece_kind",source));
    int source_id=int(prim(1,"topology_piece_id",source));
    if(source_kind!="junction" || source_id!=jid)
        error(sprintf(
            "CityRoad V5 Junction marking %d resolved owner %s/%d instead of junction/%d.",
            @primnum,source_kind,source_id,jid));
    s@name=sprintf(
        "CityRoad_Junction_L%d_%04d_RoadMarkings",level,jid);
    s@instance_prefix=s@name;
    s@topology_piece_kind="junction";
    i@topology_piece_id=jid;
    i@junction_id=jid;
}
else
{
    string road_name=prim(1,"name",source);
    if(len(road_name)==0)
        error(sprintf(
            "CityRoad %s primitive %d resolved an unnamed road owner.",
            role,@primnum));
    s@name=replace(road_name,"RoadSurface",role);
    s@instance_prefix=s@name;
    s@topology_piece_kind=prim(1,"topology_piece_kind",source);
    i@topology_piece_id=int(prim(1,"topology_piece_id",source));
    i@junction_id=int(prim(1,"junction_id",source));
}
'''


def _wrangle(core, name, snippet, inputs):
    node = core.node(name) or core.createNode("attribwrangle", name)
    node.parm("class").set(0)
    node.parm("snippet").set(snippet)
    for index, input_node in enumerate(inputs):
        node.setInput(index, input_node)
    return node


def _set_comment(node, text):
    node.setComment(text)
    node.setGenericFlag(hou.nodeFlag.DisplayComment, True)


def main():
    root = hou.node("/obj/CityRoad_DEV")
    if root is None:
        raise RuntimeError("Missing /obj/CityRoad_DEV")
    root.allowEditingOfContents(propagate=True)
    core = hou.node(CORE_PATH)
    if core is None:
        raise RuntimeError("Missing " + CORE_PATH)

    geometric = core.node("CITYROAD_TAG_JUNCTION_MOUTH_EDGES_V4")
    approaches = core.node("CITYROAD_JUNCTION_APPROACH_METADATA")
    if geometric is None or approaches is None:
        raise RuntimeError("V4 junction contract nodes are missing")

    surface_boundary = _wrangle(
        core,
        "CITYROAD_BUILD_JUNCTION_SURFACE_BOUNDARY_V5",
        JUNCTION_SURFACE_BOUNDARY_V5,
        [geometric, approaches],
    )
    _set_comment(
        surface_boundary,
        "V5 Junction Surface：保留几何圆角边界，按每个 Approach 向外延伸到停车线外侧；只作为路面拓扑裁切辅助。",
    )

    road_build = core.node("ROAD_BUILD_SURFACE")
    road_build.setInput(1, surface_boundary)
    _set_comment(
        road_build,
        "Corridor 使用 V5 Junction Surface 外边界裁断；与 Junction Arms 共用同一 Cut Plane。",
    )

    extractor = core.node("CITYROAD_EXTRACT_JUNCTION_STRIPS_V4")
    extractor.setInput(1, surface_boundary)
    extractor.setInput(3, core.node("ROAD_UNION_CLEAR_ORIENT_HELPER"))
    extractor.parm("class").set(0)
    extractor.parm("snippet").set(JUNCTION_EXTRACT_V5)
    _set_comment(
        extractor,
        "V5：从道路 Strip Union 提取 Core + 扩展 Arms；Junction 范围覆盖斑马线和停车线。",
    )

    static_markings = core.node("CITYROAD_BUILD_STATIC_MARKING_MESH")
    road_surface = core.node("CITYROAD_TOPOLOGY_CLASSIFY_ROAD")
    if static_markings is None or road_surface is None:
        raise RuntimeError("Road marking source nodes are missing")
    approach_markings = _wrangle(
        core,
        "CITYROAD_BUILD_APPROACH_MARKINGS_V5",
        APPROACH_MARKINGS_V5,
        [static_markings, road_surface, approaches, surface_boundary],
    )
    _set_comment(
        approach_markings,
        "V5：删除旧 Crosswalk/StopLine 后独立重建。白条长轴平行车辆方向，整组沿道路横向排列；全部归属 Junction。",
    )

    triangulate = core.node("CITYROAD_MARKING_TRIANGULATE_FOR_WINDING")
    triangulate.setInput(0, approach_markings)

    transfer = core.node("CITYROAD_TOPOLOGY_TRANSFER_ROADMARKINGS")
    transfer.parm("snippet").set(MARKING_TRANSFER_V5)
    _set_comment(
        transfer,
        "V5：Approach 标线保留显式 Junction 所有权，并验证最近 RoadSurface 也是同一 Junction。",
    )

    core.layoutChildren()
    print("CityRoad V5 junction surface and approach markings applied")


main()
