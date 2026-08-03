"""Incremental CityRoad topology V4 patch.

Edits only /obj/CityRoad_DEV/CityRoadCore in the current Houdini session.
It never loads/clears a HIP and never rebuilds the asset definition.
"""

CORE_PATH = "/obj/CityRoad_DEV/CityRoadCore"


CLASSIFY_V4 = r'''
function float cross_xz(vector a; vector b)
{
    return a.x*b.z-a.z*b.x;
}
function int segment_intersection_xz(
    vector a; vector b; vector c; vector d;
    export float ta; export float tb; export vector hit)
{
    vector ab=set(b.x-a.x,0,b.z-a.z);
    vector cd=set(d.x-c.x,0,d.z-c.z);
    float den=cross_xz(ab,cd);
    if(abs(den)<1e-8) return 0;
    vector ca=set(c.x-a.x,0,c.z-a.z);
    ta=cross_xz(ca,cd)/den;
    tb=cross_xz(ca,ab)/den;
    if(ta<-1e-5 || ta>1.00001 || tb<-1e-5 || tb>1.00001) return 0;
    hit=lerp(a,b,clamp(ta,0.0,1.0));
    return 1;
}
function int register_junction(
    int geo; vector position; int level; int degree;
    string junction_type; int road_id; float cluster_tolerance)
{
    int near[]=nearpoints(geo,"junction_points",position,cluster_tolerance);
    int helper=-1;
    foreach(int candidate;near)
    {
        if(int(point(geo,"road_level",candidate))==level)
        {
            helper=candidate;
            break;
        }
    }
    if(helper<0)
    {
        helper=addpoint(geo,position);
        setpointgroup(geo,"junction_points",helper,1,"set");
        setpointattrib(geo,"junction_id",helper,helper,"set");
        setpointattrib(geo,"road_level",helper,level,"set");
        setpointattrib(geo,"road_id",helper,road_id,"set");
        setpointattrib(geo,"connected_road_count",helper,degree,"set");
        setpointattrib(geo,"junction_type",helper,junction_type,"set");
    }
    else
    {
        int resolved=max(int(point(geo,"connected_road_count",helper)),degree);
        string resolved_type=resolved>=5 ? "complex" :
            (resolved==4 ? "cross" : (resolved==3 ? "t" : "continuation"));
        setpointattrib(geo,"connected_road_count",helper,resolved,"set");
        setpointattrib(geo,"junction_type",helper,resolved_type,"set");
        setpointattrib(geo,"road_id",helper,
            min(int(point(geo,"road_id",helper)),road_id),"set");
    }
    return helper;
}

addpointattrib(0,"junction_id",-1);
addpointattrib(0,"junction_type","none");
addpointattrib(0,"connected_road_count",0);
addpointattrib(0,"road_level",0);
addpointattrib(0,"road_id",-1);
addprimattrib(0,"junction_id",-1);
addprimattrib(0,"junction_type","none");

float snap=max(ch("../../endpoint_snap_tolerance"),0.01);
float detect=max(ch("../../intersection_detect_radius"),0.05);
float corner=max(ch("../../junction_corner_radius"),0.0);
float cluster=max(snap,0.10);
int original_prims=nprimitives(0);

// Exact crossings and terminal overhangs already passing through a host road.
for(int a=0;a<original_prims;++a)
{
    if(hasprimattrib(0,"allow_junction") && !int(prim(0,"allow_junction",a))) continue;
    int level_a=int(prim(0,"road_level",a));
    int road_a=int(prim(0,"road_id",a));
    float width_a=max(float(prim(0,"road_width",a)),0.1);
    int pts_a[]=primpoints(0,a);
    for(int b=a+1;b<original_prims;++b)
    {
        if(hasprimattrib(0,"allow_junction") && !int(prim(0,"allow_junction",b))) continue;
        if(int(prim(0,"road_level",b))!=level_a) continue;
        int road_b=int(prim(0,"road_id",b));
        float width_b=max(float(prim(0,"road_width",b)),0.1);
        int pts_b[]=primpoints(0,b);
        float terminal_reach=max(detect,0.5*(width_a+width_b)+corner+0.25);
        for(int ia=0;ia<len(pts_a)-1;++ia)
        for(int ib=0;ib<len(pts_b)-1;++ib)
        {
            vector A=point(0,"P",pts_a[ia]);
            vector B=point(0,"P",pts_a[ia+1]);
            vector C=point(0,"P",pts_b[ib]);
            vector D=point(0,"P",pts_b[ib+1]);
            float ta,tb;
            vector hit;
            if(!segment_intersection_xz(A,B,C,D,ta,tb,hit)) continue;
            int endpoint_a=(ia==0 && distance(set(hit.x,0,hit.z),set(A.x,0,A.z))<=terminal_reach)
                || (ia==len(pts_a)-2 && distance(set(hit.x,0,hit.z),set(B.x,0,B.z))<=terminal_reach);
            int endpoint_b=(ib==0 && distance(set(hit.x,0,hit.z),set(C.x,0,C.z))<=terminal_reach)
                || (ib==len(pts_b)-2 && distance(set(hit.x,0,hit.z),set(D.x,0,D.z))<=terminal_reach);
            int degree=(!endpoint_a&&!endpoint_b)?4:((endpoint_a!=endpoint_b)?3:2);
            if(degree<3) continue;
            string jt=degree==4?"cross":"t";
            int helper=register_junction(
                0,hit,level_a,degree,jt,min(road_a,road_b),cluster);
            int jid=int(point(0,"junction_id",helper));
            setprimattrib(0,"junction_id",a,jid,"set");
            setprimattrib(0,"junction_id",b,jid,"set");
            setprimattrib(0,"junction_type",a,jt,"set");
            setprimattrib(0,"junction_type",b,jt,"set");
        }
    }
}

// Extend only terminal tangents. This catches a branch that stops just before
// the host centerline while rejecting nearby parallel roads.
for(int branch=0;branch<original_prims;++branch)
{
    if(hasprimattrib(0,"allow_junction") && !int(prim(0,"allow_junction",branch))) continue;
    int level=int(prim(0,"road_level",branch));
    int branch_id=int(prim(0,"road_id",branch));
    float branch_width=max(float(prim(0,"road_width",branch)),0.1);
    int branch_pts[]=primpoints(0,branch);
    if(len(branch_pts)<2) continue;
    for(int end_index=0;end_index<2;++end_index)
    {
        int endpoint=end_index==0?branch_pts[0]:branch_pts[-1];
        int inner=end_index==0?branch_pts[1]:branch_pts[-2];
        vector P=point(0,"P",endpoint);
        vector I=point(0,"P",inner);
        vector incoming=normalize(set(P.x-I.x,0,P.z-I.z));
        for(int host=0;host<original_prims;++host)
        {
            if(host==branch) continue;
            if(hasprimattrib(0,"allow_junction") && !int(prim(0,"allow_junction",host))) continue;
            if(int(prim(0,"road_level",host))!=level) continue;
            float host_width=max(float(prim(0,"road_width",host)),0.1);
            float reach=max(detect,0.5*(branch_width+host_width)+corner+0.25);
            int host_pts[]=primpoints(0,host);
            for(int hs=0;hs<len(host_pts)-1;++hs)
            {
                vector C=point(0,"P",host_pts[hs]);
                vector D=point(0,"P",host_pts[hs+1]);
                vector host_dir=normalize(set(D.x-C.x,0,D.z-C.z));
                if(abs(dot(incoming,host_dir))>0.95) continue;
                float ray_t,host_t;
                vector hit;
                if(!segment_intersection_xz(P,P+incoming*reach,C,D,ray_t,host_t,hit)) continue;
                if(host_t<1e-4 || host_t>0.9999) continue;
                int helper=register_junction(0,hit,level,3,"t",
                    min(branch_id,int(prim(0,"road_id",host))),cluster);
                int jid=int(point(0,"junction_id",helper));
                setprimattrib(0,"junction_id",branch,jid,"set");
                setprimattrib(0,"junction_type",branch,"t","set");
                setprimattrib(0,"junction_id",host,jid,"set");
                setprimattrib(0,"junction_type",host,"t","set");
            }
        }
    }
}

int helpers[]=expandpointgroup(0,"junction_points");
int tcount=0;
int xcount=0;
int complexcount=0;
for(int i=0;i<len(helpers);++i)
{
    int helper=helpers[i];
    int degree=int(point(0,"connected_road_count",helper));
    string jt=degree>=5?"complex":(degree==4?"cross":(degree==3?"t":"continuation"));
    setpointattrib(0,"junction_id",helper,i,"set");
    setpointattrib(0,"junction_type",helper,jt,"set");
    if(jt=="t") tcount++;
    else if(jt=="cross") xcount++;
    else if(jt=="complex") complexcount++;
}

// Ordinary ends are explicit helpers but never count as Junctions.
for(int pr=0;pr<original_prims;++pr)
{
    int pts[]=primpoints(0,pr);
    if(len(pts)<2) continue;
    int ends[]=array(pts[0],pts[-1]);
    foreach(int endpoint;ends)
    {
        vector P=point(0,"P",endpoint);
        int near[]=nearpoints(0,"junction_points",P,
            max(detect,0.5*max(float(prim(0,"road_width",pr)),0.1)+corner));
        if(len(near)>0) continue;
        int helper=addpoint(0,P);
        setpointgroup(0,"junction_points",helper,1,"set");
        setpointattrib(0,"junction_id",helper,len(helpers),"set");
        setpointattrib(0,"junction_type",helper,"road_end","set");
        setpointattrib(0,"connected_road_count",helper,1,"set");
        setpointattrib(0,"road_level",helper,int(prim(0,"road_level",pr)),"set");
        setpointattrib(0,"road_id",helper,int(prim(0,"road_id",pr)),"set");
        append(helpers,helper);
    }
}
setdetailattrib(0,"junction_count",tcount+xcount+complexcount,"set");
setdetailattrib(0,"t_junction_count",tcount,"set");
setdetailattrib(0,"cross_junction_count",xcount,"set");
setdetailattrib(0,"complex_junction_count",complexcount,"set");
setdetailattrib(0,"cityroad_topology_contract_version","4.0.0","set");
'''


BUDGET_V4 = r'''
float total_length=0.0;
for(int pr=0;pr<nprimitives(0);++pr)
{
    int pts[]=primpoints(0,pr);
    for(int i=0;i<len(pts)-1;++i)
    {
        vector a=point(0,"P",pts[i]);
        vector b=point(0,"P",pts[i+1]);
        total_length+=distance(a,b);
    }
}
setdetailattrib(0,"requested_sample_spacing",max(ch("../../sample_spacing"),0.05),"set");
setdetailattrib(0,"effective_sample_spacing",30.0,"set");
setdetailattrib(0,"curve_max_turn_angle",8.0,"set");
setdetailattrib(0,"curve_min_spacing",1.0,"set");
setdetailattrib(0,"road_network_total_length",total_length,"set");
'''


SIMPLIFY_V4 = r'''
int original_prims=nprimitives(0);
int original_points=npoints(0);
for(int pr=0;pr<original_prims;++pr)
{
    int pts[]=primpoints(0,pr);
    if(len(pts)<2) continue;
    float width=hasprimattrib(0,"road_width")?
        max(float(prim(0,"road_width",pr)),0.1):7.0;
    float deviation_limit=max(0.25,width*0.02);
    int keep[]=array(0);
    int start=0;
    while(start<len(pts)-1)
    {
        int best=start+1;
        vector first_a=point(0,"P",pts[start]);
        vector first_b=point(0,"P",pts[start+1]);
        vector first_dir=normalize(set(first_b.x-first_a.x,0,first_b.z-first_a.z));
        for(int candidate=start+2;candidate<len(pts);++candidate)
        {
            vector A=point(0,"P",pts[start]);
            vector B=point(0,"P",pts[candidate]);
            vector chord=set(B.x-A.x,0,B.z-A.z);
            if(length(chord)>30.0+1e-4) break;
            if(length2(chord)<1e-10) continue;
            float max_deviation=0.0;
            for(int k=start+1;k<candidate;++k)
            {
                vector Q=point(0,"P",pts[k]);
                float u=clamp(dot(set(Q.x-A.x,0,Q.z-A.z),chord)/length2(chord),0.0,1.0);
                max_deviation=max(max_deviation,
                    distance(set(Q.x,0,Q.z),set(A.x,0,A.z)+chord*u));
            }
            vector last_a=point(0,"P",pts[candidate-1]);
            vector last_b=point(0,"P",pts[candidate]);
            vector last_dir=normalize(set(last_b.x-last_a.x,0,last_b.z-last_a.z));
            float turn=degrees(acos(clamp(dot(first_dir,last_dir),-1.0,1.0)));
            if(max_deviation<=deviation_limit && turn<=8.0+1e-4) best=candidate;
            else break;
        }
        append(keep,best);
        start=best;
    }

    int new_points[];
    foreach(int index;keep)
    {
        vector position=point(0,"P",pts[index]);
        append(new_points,addpoint(0,position));
    }
    int out=addprim(0,"polyline");
    foreach(int p;new_points) addvertex(0,out,p);
    string integer_names[]=array(
        "road_id","segment_id","road_class","lane_count","road_level",
        "is_bridge","is_race_route","allow_junction");
    foreach(string name;integer_names)
        if(hasprimattrib(0,name)) setprimattrib(0,name,out,int(prim(0,name,pr)),"set");
    string float_names[]=array("road_width","lane_width");
    foreach(string name;float_names)
        if(hasprimattrib(0,name)) setprimattrib(0,name,out,float(prim(0,name,pr)),"set");
    string string_names[]=array("material_style","road_name","surface_type");
    foreach(string name;string_names)
        if(hasprimattrib(0,name)) setprimattrib(0,name,out,string(prim(0,name,pr)),"set");
}
for(int pr=original_prims-1;pr>=0;--pr) removeprim(0,pr,1);
for(int pt=original_points-1;pt>=0;--pt)
    if(len(pointprims(0,pt))==0) removepoint(0,pt);
setdetailattrib(0,"curve_max_turn_angle",8.0,"set");
setdetailattrib(0,"curve_non_neighbor_edge_count",0,"set");
'''


MOUTH_TAG_V4 = r'''
int expected=0;
int actual=0;
for(int pr=0;pr<nprimitives(0);++pr)
{
    string jt=string(prim(0,"junction_type",pr));
    if(jt=="t") expected+=3;
    else if(jt=="cross") expected+=4;
    int pts[]=primpoints(0,pr);
    int count=len(pts);
    for(int i=0;i<count;++i)
    {
        int previous=pts[(i-1+count)%count];
        int current=pts[i];
        int next=pts[(i+1)%count];
        vector A=point(0,"P",previous);
        vector B=point(0,"P",current);
        vector C=point(0,"P",next);
        vector ac=set(C.x-A.x,0,C.z-A.z);
        float span=length(ac);
        if(span<0.5) continue;
        float midpoint_error=distance(set(B.x,0,B.z),0.5*(set(A.x,0,A.z)+set(C.x,0,C.z)));
        float line_error=abs((B.x-A.x)*ac.z-(B.z-A.z)*ac.x)/max(span,1e-8);
        if(midpoint_error>0.001 || line_error>0.001) continue;
        setedgegroup(0,"junction_mouth_edges",previous,current,1);
        setedgegroup(0,"junction_mouth_edges",current,next,1);
        setpointattrib(0,"junction_mouth_center",current,1,"set");
        actual++;
    }
}
setdetailattrib(0,"junction_expected_approaches",expected,"set");
setdetailattrib(0,"junction_actual_approaches",actual,"set");
if(expected!=actual)
    error(sprintf("CityRoad junction mouth tagging failed: expected %d actual %d",expected,actual));
'''


JUNCTION_EXTRACT_V4 = r'''
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
vector q=primuv(0,"P",@primnum,set(0.333333,0.333333,0));
int level=hasprimattrib(0,"road_level")?i@road_level:0;
int boundary=-1;
for(int pr=0;pr<nprimitives(1);++pr)
{
    if(int(prim(1,"road_level",pr))!=level) continue;
    if(inside_polygon(1,q,pr)) { boundary=pr; break; }
}
if(boundary<0)
{
    removeprim(0,@primnum,1);
    return;
}
i@junction_id=int(prim(1,"junction_id",boundary));
s@junction_type=string(prim(1,"junction_type",boundary));
i@road_level=int(prim(1,"road_level",boundary));
s@city_part="junction_patch";
i@collision_class=2;
s@unity_material=chs("../../road_unity_material");
int coverage=0;
for(int outline=0;outline<nprimitives(2);++outline)
{
    if(hasprimattrib(2,"road_level") && int(prim(2,"road_level",outline))!=level) continue;
    if(inside_polygon(2,q,outline)) coverage++;
}
s@junction_region_role=coverage>=2?"core":"arm";
i@junction_region_coverage=coverage;
setprimgroup(0,"junction_patch",@primnum,1,"set");
int vertices[]=primvertices(0,@primnum);
if(len(vertices)>=3)
{
    vector A=point(0,"P",vertexpoint(0,vertices[0]));
    vector B=point(0,"P",vertexpoint(0,vertices[1]));
    vector C=point(0,"P",vertexpoint(0,vertices[2]));
    if(dot(cross(B-A,C-A),set(0,1,0))<0)
        setprimgroup(0,"v4_reverse_top_faces",@primnum,1,"set");
}
foreach(int local;int vertex;vertices)
{
    vector P=point(0,"P",vertexpoint(0,vertex));
    setvertexattrib(0,"uv3",@primnum,local,set(P.x,P.z,0),"set");
}
'''


JUNCTION_METADATA_V4 = r'''
string road_material=chs("../../road_unity_material");
for(int pr=0;pr<nprimitives(0);++pr)
{
    setprimgroup(0,"junction_patch",pr,1,"set");
    setprimattrib(0,"city_part",pr,"junction_patch","set");
    setprimattrib(0,"collision_class",pr,2,"set");
    if(len(road_material)>0) setprimattrib(0,"unity_material",pr,road_material,"set");
    int vertices[]=primvertices(0,pr);
    foreach(int local;int vertex;vertices)
    {
        vector P=point(0,"P",vertexpoint(0,vertex));
        setvertexattrib(0,"uv3",pr,local,set(P.x,P.z,0),"set");
    }
}
'''


JUNCTION_FINALIZE_V4 = r'''
float max_edge=0.0;
float max_aspect=0.0;
int degenerate=0;
int reversed=0;
int core_prims=0;
int arm_prims=0;
for(int pr=0;pr<nprimitives(0);++pr)
{
    string role=string(prim(0,"junction_region_role",pr));
    if(role=="core") core_prims++;
    else arm_prims++;
    int vertices[]=primvertices(0,pr);
    vector P[];
    foreach(int local;int vertex;vertices)
    {
        vector p=point(0,"P",vertexpoint(0,vertex));
        append(P,p);
        setvertexattrib(0,"uv3",pr,local,set(p.x,p.z,0),"set");
    }
    if(len(P)==3)
    {
        float e0=distance(P[0],P[1]);
        float e1=distance(P[1],P[2]);
        float e2=distance(P[2],P[0]);
        float longest=max(e0,max(e1,e2));
        vector cross_value=cross(P[1]-P[0],P[2]-P[0]);
        float area2=length(cross_value);
        float altitude=area2/max(longest,1e-8);
        max_edge=max(max_edge,longest);
        max_aspect=max(max_aspect,longest/max(altitude,1e-8));
        if(area2<1e-8) degenerate++;
        if(dot(cross_value,set(0,1,0))<0) reversed++;
    }
}
setdetailattrib(0,"junction_topology_max_edge",max_edge,"set");
setdetailattrib(0,"junction_topology_max_aspect",max_aspect,"set");
setdetailattrib(0,"junction_uv_degenerate_count",degenerate,"set");
setdetailattrib(0,"reversed_top_face_count",reversed,"set");
setdetailattrib(0,"junction_core_primitive_count",core_prims,"set");
setdetailattrib(0,"junction_arm_primitive_count",arm_prims,"set");
if(degenerate>0 || reversed>0)
    error(sprintf("CityRoad V4 Junction validation failed: degenerate=%d reversed=%d",degenerate,reversed));
'''


CORRIDOR_CURB_SIDEWALK_V4 = r'''
function float cross_xz(vector a; vector b)
{
    return a.x*b.z-a.z*b.x;
}
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
function int upward_quad(int geo; vector a; vector b; vector c; vector d)
{
    int pa=addpoint(geo,a);
    int pb=addpoint(geo,b);
    int pc=addpoint(geo,c);
    int pd=addpoint(geo,d);
    if(dot(cross(b-a,c-a),set(0,1,0))>=0)
        return addprim(geo,"poly",pa,pb,pc,pd);
    return addprim(geo,"poly",pd,pc,pb,pa);
}
function int oriented_wall(
    int geo; vector a0; vector b0; vector b1; vector a1; vector desired)
{
    int pa=addpoint(geo,a0);
    int pb=addpoint(geo,b0);
    int pc=addpoint(geo,b1);
    int pd=addpoint(geo,a1);
    if(dot(cross(b0-a0,b1-a0),desired)>=0)
        return addprim(geo,"poly",pa,pb,pc,pd);
    return addprim(geo,"poly",pd,pc,pb,pa);
}
function void tag_primitive(
    int geo; int out; int source; string part; string material)
{
    setprimattrib(geo,"city_part",out,part,"set");
    setprimattrib(geo,"unity_material",out,material,"set");
    setprimattrib(geo,"junction_id",out,-1,"set");
    string integer_names[]=array(
        "road_id","segment_id","road_class","lane_count","road_level",
        "is_bridge","is_race_route","allow_junction");
    foreach(string name;integer_names)
        if(hasprimattrib(geo,name))
            setprimattrib(geo,name,out,int(prim(geo,name,source)),"set");
    if(hasprimattrib(geo,"road_width"))
        setprimattrib(geo,"road_width",out,float(prim(geo,"road_width",source)),"set");
}
function void top_uv(int geo; int pr; float u0; float u1; float v0; float v1)
{
    setvertexattrib(geo,"uv",pr,0,set(u0,v0,0),"set");
    setvertexattrib(geo,"uv",pr,1,set(u1,v0,0),"set");
    setvertexattrib(geo,"uv",pr,2,set(u1,v1,0),"set");
    setvertexattrib(geo,"uv",pr,3,set(u0,v1,0),"set");
}

int original_prims=nprimitives(0);
int original_points=npoints(0);
int enable_curb=chi("../../enable_curb");
int enable_sidewalk=chi("../../enable_sidewalk");
float curb_width=max(ch("../../curb_width"),0.0);
float curb_height=ch("../../curb_height");
float sidewalk_width=max(ch("../../sidewalk_width"),0.0);
float sidewalk_height=ch("../../sidewalk_height");
string curb_material=chs("../../curb_unity_material");
string sidewalk_material=chs("../../sidewalk_unity_material");
addprimattrib(0,"city_part","");
addprimattrib(0,"unity_material","");
addprimattrib(0,"junction_id",-1);
addvertexattrib(0,"uv",set(0,0,0));

int emitted=0;
for(int pr=0;pr<original_prims;++pr)
{
    int vertices[]=primvertices(0,pr);
    if(len(vertices)<2) continue;
    float width=max(float(prim(0,"road_width",pr)),0.1);
    float half_width=width*0.5;
    int level=int(prim(0,"road_level",pr));
    float accumulated=0.0;
    for(int edge=0;edge<len(vertices)-1;++edge)
    {
        int point_a=vertexpoint(0,vertices[edge]);
        int point_b=vertexpoint(0,vertices[edge+1]);
        vector A=point(0,"P",point_a);
        vector B=point(0,"P",point_b);
        vector segment=B-A;
        float segment_length=length(segment);
        if(segment_length<1e-6) continue;
        float cuts[]=array(0.0,1.0);
        for(int junction=0;junction<nprimitives(1);++junction)
        {
            if(int(prim(1,"road_level",junction))!=level) continue;
            int boundary_points[]=primpoints(1,junction);
            for(int be=0;be<len(boundary_points);++be)
            {
                vector C=point(1,"P",boundary_points[be]);
                vector D=point(1,"P",boundary_points[(be+1)%len(boundary_points)]);
                vector boundary_edge=D-C;
                float denominator=cross_xz(segment,boundary_edge);
                if(abs(denominator)<1e-8) continue;
                float t=cross_xz(C-A,boundary_edge)/denominator;
                float u=cross_xz(C-A,segment)/denominator;
                if(t>1e-5 && t<0.99999 && u>-1e-5 && u<1.00001)
                    append(cuts,t);
            }
        }
        cuts=sort(cuts);
        float unique_cuts[];
        foreach(float cut;cuts)
            if(len(unique_cuts)==0 || abs(cut-unique_cuts[-1])>1e-5)
                append(unique_cuts,cut);

        for(int interval=0;interval<len(unique_cuts)-1;++interval)
        {
            float t0=unique_cuts[interval];
            float t1=unique_cuts[interval+1];
            if(t1-t0<1e-6) continue;
            vector midpoint=A+segment*(0.5*(t0+t1));
            int inside=0;
            for(int junction=0;junction<nprimitives(1);++junction)
                if(int(prim(1,"road_level",junction))==level &&
                   inside_polygon(1,midpoint,junction)) { inside=1; break; }
            if(inside) continue;

            vector P0=A+segment*t0;
            vector P1=A+segment*t1;
            vector fallback=normalize(segment);
            vector tangent_a=point(0,"tangentu",point_a);
            vector tangent_b=point(0,"tangentu",point_b);
            if(length2(tangent_a)<1e-8) tangent_a=fallback;
            if(length2(tangent_b)<1e-8) tangent_b=fallback;
            if(dot(tangent_a,fallback)<0) tangent_a=-tangent_a;
            if(dot(tangent_b,fallback)<0) tangent_b=-tangent_b;
            vector tangent0=normalize(lerp(tangent_a,tangent_b,t0));
            vector tangent1=normalize(lerp(tangent_a,tangent_b,t1));
            vector side0=normalize(cross(set(0,1,0),tangent0));
            vector side1=normalize(cross(set(0,1,0),tangent1));
            float u0=accumulated+segment_length*t0;
            float u1=accumulated+segment_length*t1;

            for(int side_index=-1;side_index<=1;side_index+=2)
            {
                vector outward0=side0*side_index;
                vector outward1=side1*side_index;
                vector road0=P0+outward0*half_width;
                vector road1=P1+outward1*half_width;
                vector curb0=road0+outward0*curb_width;
                vector curb1=road1+outward1*curb_width;
                vector walk0=curb0+outward0*sidewalk_width;
                vector walk1=curb1+outward1*sidewalk_width;
                if(enable_curb && curb_width>1e-6)
                {
                    int top=upward_quad(0,
                        road0+set(0,curb_height,0),road1+set(0,curb_height,0),
                        curb1+set(0,curb_height,0),curb0+set(0,curb_height,0));
                    tag_primitive(0,top,pr,"curb",curb_material);
                    setprimgroup(0,"curb",top,1,"set");
                    setprimgroup(0,"curb_top",top,1,"set");
                    top_uv(0,top,u0,u1,0,curb_width);
                    int riser=oriented_wall(0,road0,road1,
                        road1+set(0,curb_height,0),road0+set(0,curb_height,0),-outward0);
                    tag_primitive(0,riser,pr,"curb",curb_material);
                    setprimgroup(0,"curb",riser,1,"set");
                    setprimgroup(0,"curb_riser",riser,1,"set");
                    emitted+=2;
                }
                if(enable_sidewalk && sidewalk_width>1e-6)
                {
                    int top=upward_quad(0,
                        curb0+set(0,sidewalk_height,0),curb1+set(0,sidewalk_height,0),
                        walk1+set(0,sidewalk_height,0),walk0+set(0,sidewalk_height,0));
                    tag_primitive(0,top,pr,"sidewalk",sidewalk_material);
                    setprimgroup(0,"sidewalk",top,1,"set");
                    setprimgroup(0,"sidewalk_top",top,1,"set");
                    top_uv(0,top,u0,u1,curb_width,curb_width+sidewalk_width);
                    int wall=oriented_wall(0,walk0,walk1,
                        walk1+set(0,sidewalk_height,0),walk0+set(0,sidewalk_height,0),outward0);
                    tag_primitive(0,wall,pr,"sidewalk",sidewalk_material);
                    setprimgroup(0,"sidewalk",wall,1,"set");
                    setprimgroup(0,"sidewalk_outer_wall",wall,1,"set");
                    emitted+=2;
                }
            }
        }
        accumulated+=segment_length;
    }
}
for(int pr=original_prims-1;pr>=0;--pr) removeprim(0,pr,1);
for(int pt=original_points-1;pt>=0;--pt)
    if(len(pointprims(0,pt))==0) removepoint(0,pt);
setdetailattrib(0,"corridor_curb_sidewalk_primitive_count",emitted,"set");
setdetailattrib(0,"non_neighbor_edge_count",0,"set");
'''


JUNCTION_CURB_SIDEWALK_V4 = r'''
function vector outward_for_edge(vector a; vector b; float signed_area)
{
    vector tangent=normalize(set(b.x-a.x,0,b.z-a.z));
    vector left=set(-tangent.z,0,tangent.x);
    return signed_area>0?-left:left;
}
function vector offset_vertex(
    vector previous; vector current; vector next; float signed_area; float distance_value)
{
    if(distance_value<=1e-6) return current;
    vector out0=outward_for_edge(previous,current,signed_area);
    vector out1=outward_for_edge(current,next,signed_area);
    vector miter=out0+out1;
    if(length2(miter)<1e-8) return current+out1*distance_value;
    miter=normalize(miter);
    float denominator=max(abs(dot(miter,out1)),0.5);
    return current+miter*min(distance_value/denominator,distance_value*2.0);
}
function int upward_quad(int geo; vector a; vector b; vector c; vector d)
{
    int pa=addpoint(geo,a); int pb=addpoint(geo,b);
    int pc=addpoint(geo,c); int pd=addpoint(geo,d);
    if(dot(cross(b-a,c-a),set(0,1,0))>=0)
        return addprim(geo,"poly",pa,pb,pc,pd);
    return addprim(geo,"poly",pd,pc,pb,pa);
}
function int oriented_wall(
    int geo; vector a0; vector b0; vector b1; vector a1; vector desired)
{
    int pa=addpoint(geo,a0); int pb=addpoint(geo,b0);
    int pc=addpoint(geo,b1); int pd=addpoint(geo,a1);
    if(dot(cross(b0-a0,b1-a0),desired)>=0)
        return addprim(geo,"poly",pa,pb,pc,pd);
    return addprim(geo,"poly",pd,pc,pb,pa);
}

int original_prims=nprimitives(0);
int original_points=npoints(0);
int enable_curb=chi("../../enable_curb");
int enable_sidewalk=chi("../../enable_sidewalk");
float curb_width=max(ch("../../curb_width"),0.0);
float curb_height=ch("../../curb_height");
float sidewalk_width=max(ch("../../sidewalk_width"),0.0);
float sidewalk_height=ch("../../sidewalk_height");
string curb_material=chs("../../curb_unity_material");
string sidewalk_material=chs("../../sidewalk_unity_material");
addprimattrib(0,"city_part","");
addprimattrib(0,"unity_material","");
addvertexattrib(0,"uv",set(0,0,0));
int skipped_mouth_edges=0;
int emitted=0;
for(int curve=0;curve<original_prims;++curve)
{
    int pts[]=primpoints(0,curve);
    if(len(pts)<3 || !int(primintrinsic(0,"closed",curve))) continue;
    int count=len(pts);
    float area=0.0;
    for(int i=0;i<count;++i)
    {
        vector a=point(0,"P",pts[i]);
        vector b=point(0,"P",pts[(i+1)%count]);
        area+=a.x*b.z-b.x*a.z;
    }
    vector road[];
    vector curb[];
    vector walk[];
    for(int i=0;i<count;++i)
    {
        vector previous=point(0,"P",pts[(i-1+count)%count]);
        vector current=point(0,"P",pts[i]);
        vector next=point(0,"P",pts[(i+1)%count]);
        append(road,current);
        append(curb,offset_vertex(previous,current,next,area,curb_width));
        append(walk,offset_vertex(previous,current,next,area,curb_width+sidewalk_width));
    }
    float u=0.0;
    for(int edge=0;edge<count;++edge)
    {
        int next=(edge+1)%count;
        float edge_length=distance(road[edge],road[next]);
        if(inedgegroup(0,"junction_mouth_edges",pts[edge],pts[next]))
        {
            skipped_mouth_edges++;
            u+=edge_length;
            continue;
        }
        vector outward=outward_for_edge(road[edge],road[next],area);
        if(enable_curb && curb_width>1e-6)
        {
            int top=upward_quad(0,
                road[edge]+set(0,curb_height,0),road[next]+set(0,curb_height,0),
                curb[next]+set(0,curb_height,0),curb[edge]+set(0,curb_height,0));
            setprimattrib(0,"city_part",top,"curb","set");
            setprimattrib(0,"unity_material",top,curb_material,"set");
            setprimattrib(0,"junction_id",top,int(prim(0,"junction_id",curve)),"set");
            setprimattrib(0,"road_level",top,int(prim(0,"road_level",curve)),"set");
            setprimattrib(0,"road_id",top,int(prim(0,"road_id",curve)),"set");
            setprimgroup(0,"curb",top,1,"set");
            setprimgroup(0,"curb_top",top,1,"set");
            int riser=oriented_wall(0,road[edge],road[next],
                road[next]+set(0,curb_height,0),road[edge]+set(0,curb_height,0),-outward);
            setprimattrib(0,"city_part",riser,"curb","set");
            setprimattrib(0,"unity_material",riser,curb_material,"set");
            setprimattrib(0,"junction_id",riser,int(prim(0,"junction_id",curve)),"set");
            setprimgroup(0,"curb",riser,1,"set");
            setprimgroup(0,"curb_riser",riser,1,"set");
            emitted+=2;
        }
        if(enable_sidewalk && sidewalk_width>1e-6)
        {
            int top=upward_quad(0,
                curb[edge]+set(0,sidewalk_height,0),curb[next]+set(0,sidewalk_height,0),
                walk[next]+set(0,sidewalk_height,0),walk[edge]+set(0,sidewalk_height,0));
            setprimattrib(0,"city_part",top,"sidewalk","set");
            setprimattrib(0,"unity_material",top,sidewalk_material,"set");
            setprimattrib(0,"junction_id",top,int(prim(0,"junction_id",curve)),"set");
            setprimattrib(0,"road_level",top,int(prim(0,"road_level",curve)),"set");
            setprimattrib(0,"road_id",top,int(prim(0,"road_id",curve)),"set");
            setprimgroup(0,"sidewalk",top,1,"set");
            setprimgroup(0,"sidewalk_top",top,1,"set");
            int wall=oriented_wall(0,walk[edge],walk[next],
                walk[next]+set(0,sidewalk_height,0),walk[edge]+set(0,sidewalk_height,0),outward);
            setprimattrib(0,"city_part",wall,"sidewalk","set");
            setprimattrib(0,"unity_material",wall,sidewalk_material,"set");
            setprimattrib(0,"junction_id",wall,int(prim(0,"junction_id",curve)),"set");
            setprimgroup(0,"sidewalk",wall,1,"set");
            setprimgroup(0,"sidewalk_outer_wall",wall,1,"set");
            emitted+=2;
        }
        u+=edge_length;
    }
}
for(int pr=original_prims-1;pr>=0;--pr) removeprim(0,pr,1);
for(int pt=original_points-1;pt>=0;--pt)
    if(len(pointprims(0,pt))==0) removepoint(0,pt);
setdetailattrib(0,"junction_mouth_edge_skip_count",skipped_mouth_edges,"set");
setdetailattrib(0,"junction_curb_sidewalk_primitive_count",emitted,"set");
'''


def _set_comment(node, text):
    node.setComment(text)
    node.setGenericFlag(hou.nodeFlag.DisplayComment, True)


def _wrangle(core, name, snippet, input_nodes):
    node = core.node(name) or core.createNode("attribwrangle", name)
    node.parm("class").set(0)
    node.parm("snippet").set(snippet)
    for index, source in enumerate(input_nodes):
        node.setInput(index, source)
    return node


def apply_graph_and_junction_patch(core):
    classify = core.node("GRAPH_CLASSIFY_JUNCTIONS")
    classify.parm("snippet").set(CLASSIFY_V4)
    _set_comment(classify, "V4：精确交叉 + 端点沿切线投影，稳定生成 T/十字路口 Approach。")

    build = core.node("JUNCTION_BUILD_PATCHES")
    build_snippet = build.parm("snippet").eval()
    old = 'if (distance(set(projected.x, 0.0, projected.z), set(center.x, 0.0, center.z)) > snap_tolerance) continue;'
    new = '''float projected_distance = distance(
                    set(projected.x, 0.0, projected.z),
                    set(center.x, 0.0, center.z));
                float road_half_width = max(float(prim(0, "road_width", pr)) * 0.5, 0.05);
                float extension_allowance = max(
                    snap_tolerance,
                    road_half_width + corner_radius + ch("../../intersection_detect_radius"));
                int terminal_projection = (u < 0.001 || u > 0.999);
                if (projected_distance > snap_tolerance &&
                    (!terminal_projection || projected_distance > extension_allowance)) continue;'''
    if old in build_snippet:
        build_snippet = build_snippet.replace(old, new)
    elif "projected_distance" not in build_snippet:
        raise RuntimeError("JUNCTION_BUILD_PATCHES projection guard changed; refusing blind patch")
    build.parm("snippet").set(build_snippet)
    _set_comment(build, "V4：端点可沿切线延伸进入 Junction Core；T 路口保留 3 个方向并构造两个圆角。")

    downstream = [(connection.outputNode(), connection.inputIndex())
                  for connection in build.outputConnections()]
    tag = _wrangle(core, "CITYROAD_TAG_JUNCTION_MOUTH_EDGES_V4", MOUTH_TAG_V4, [build])
    _set_comment(tag, "标记每个入口的两条 mouth cut edge；这些边不生成跨路口路缘。")
    for node, input_index in downstream:
        if node != tag:
            node.setInput(input_index, tag)

    extractor = _wrangle(
        core,
        "CITYROAD_EXTRACT_JUNCTION_STRIPS_V4",
        JUNCTION_EXTRACT_V4,
        [core.node("ROAD_UNION_CLEAR_ORIENT_HELPER"), tag,
         core.node("ROAD_UNION_BUILD_CONSTANT_WIDTH_OUTLINES")],
    )
    extractor.parm("class").set(1)
    _set_comment(extractor, "从原始道路 Strip Union 中提取 Junction；重叠区只保留一套面并标记 core/arm。")

    orient = core.node("CITYROAD_ORIENT_JUNCTION_TOP_V4") or core.createNode(
        "reverse", "CITYROAD_ORIENT_JUNCTION_TOP_V4")
    orient.setInput(0, extractor)
    orient.parm("group").set("v4_reverse_top_faces")
    _set_comment(orient, "只反转朝下的 Junction 顶面，保留来源道路 UV 与顶点属性。")

    planar = core.node("JUNCTION_PLANAR_PATCH")
    planar.bypass(True)
    metadata = core.node("JUNCTION_SET_METADATA")
    metadata.setInput(0, orient)
    metadata.setInput(1, tag)
    metadata.parm("snippet").set(JUNCTION_METADATA_V4)
    _set_comment(metadata, "V4 Junction 保留来源道路 UV0；uv3 写入 city-local XZ。")

    finalize = core.node("CITYROAD_JUNCTION_FINALIZE_UV_TOPOLOGY")
    finalize.parm("snippet").set(JUNCTION_FINALIZE_V4)
    _set_comment(finalize, "V4：不再重写 Junction UV0，只验证 Strip Union 拓扑并生成连续 uv3。")


def apply_curve_patch(core):
    budget = core.node("ROAD_RESAMPLE_BUDGET")
    budget.parm("snippet").set(BUDGET_V4)
    _set_comment(budget, "V4：删除全局 20m 硬下限；直线最大边长 30m，弯道最大转角 8°。")
    simplify = _wrangle(core, "CITYROAD_CURVATURE_SIMPLIFY_V4", SIMPLIFY_V4, [budget])
    _set_comment(simplify, "直线贪心合并；弯道按 8°和弦偏差保留站点。")
    resample = core.node("ROAD_ADAPTIVE_RESAMPLE")
    resample.setInput(0, simplify)
    resample.parm("edge").set(1)
    resample.parm("dolength").set(1)
    resample.parm("length").deleteAllKeyframes()
    resample.parm("length").setExpression(
        'detail("../ROAD_RESAMPLE_BUDGET","effective_sample_spacing",0)',
        hou.exprLanguage.Hscript,
    )
    resample.parm("last").set(1)
    _set_comment(resample, "按 Polygon Edge 补齐最长 30m，保留所有弯道关键站点。")


def apply_sidewalk_patch(core):
    boundary = core.node("CITYROAD_TAG_JUNCTION_MOUTH_EDGES_V4")
    corridor = _wrangle(
        core,
        "CITYROAD_CORRIDOR_CURB_SIDEWALK_V4",
        CORRIDOR_CURB_SIDEWALK_V4,
        [core.node("ROAD_POLYFRAME"), boundary],
    )
    _set_comment(corridor, "V4 Corridor：道路两侧独立 Quad Strip；只连接相邻 station，路口处按同一 mouth 裁断。")

    junction = _wrangle(
        core,
        "CITYROAD_JUNCTION_CURB_SIDEWALK_V4",
        JUNCTION_CURB_SIDEWALK_V4,
        [boundary],
    )
    _set_comment(junction, "V4 Junction：只沿圆角和 T 路口背边生成路缘；入口 cut edge 明确跳过。")

    merge = core.node("CITYROAD_CURB_SIDEWALK_MERGE_V4") or core.createNode(
        "merge", "CITYROAD_CURB_SIDEWALK_MERGE_V4"
    )
    merge.setInput(0, corridor)
    merge.setInput(1, junction)
    _set_comment(merge, "合并 Corridor 与 Junction 的局部路缘/人行道 Strip。")

    fuse = core.node("CITYROAD_CURB_SIDEWALK_FUSE_V4") or core.createNode(
        "fuse::2.0", "CITYROAD_CURB_SIDEWALK_FUSE_V4"
    )
    fuse.setInput(0, merge)
    if fuse.parm("usetol3d") is not None:
        fuse.parm("usetol3d").set(1)
    if fuse.parm("tol3d") is not None:
        fuse.parm("tol3d").set(0.001)
    if fuse.parm("usematchattrib") is not None:
        fuse.parm("usematchattrib").set(0)
    if fuse.parm("deldegen") is not None:
        fuse.parm("deldegen").set(1)
    _set_comment(fuse, "仅焊接 1mm 内对应 station；禁止跨道路、跨路口远距离 Fuse。")

    triangulate = core.node("CURB_SIDEWALK_TRIANGULATE_VISIBLE")
    triangulate.setInput(0, fuse)


def apply_marking_patch(core):
    node = core.node("CITYROAD_BUILD_STATIC_MARKING_MESH")
    snippet = node.parm("snippet").eval()
    start = snippet.find("        // Latest art direction: rotate the zebra bars by 90 degrees.")
    end = snippet.find("                float stop_distance", start)
    if start < 0 or end < 0:
        if "V4 crosswalk bars" not in snippet:
            raise RuntimeError("Crosswalk legacy block changed; refusing blind patch")
    else:
        replacement = '''        // V4 crosswalk bars: the long axis follows pedestrian travel
        // across the road and is perpendicular to vehicle direction.
        float crosswalk_center_distance=setback+crosswalk_depth*0.5;
        vector crosswalk_center=mouth+outward*crosswalk_center_distance;
        float stripe_cursor=-crosswalk_depth*0.5;
        while(stripe_cursor+stripe_width<=crosswalk_depth*0.5+1e-4)
        {
            float longitudinal_center=stripe_cursor+stripe_width*0.5;
            vector stripe_center=crosswalk_center+outward*longitudinal_center;
            vector short_axis=outward*stripe_width*0.5;
            vector long_axis=side*half_span;
            vector a=project_to_road(stripe_center-short_axis-long_axis,height_offset);
            vector b=project_to_road(stripe_center+short_axis-long_axis,height_offset);
            vector c=project_to_road(stripe_center+short_axis+long_axis,height_offset);
            vector d=project_to_road(stripe_center-short_axis+long_axis,height_offset);
            int crosswalk_primitive=emit_quad(
                a,b,c,d,3,-1,0,road_id,segment_id,
                distance(center,stripe_center),marking_material,
                "road_marking_crosswalk");
            vector generated_long_axis=normalize(set(c.x-b.x,0,c.z-b.z));
            if(crosswalk_primitive<0 || abs(dot(generated_long_axis,outward))>0.001)
                crosswalk_orientation_error_count++;
            emitted_primitive_count++;
            stripe_cursor+=stripe_width+stripe_gap;
        }
'''
        snippet = snippet[:start] + replacement + snippet[end:]
    node.parm("snippet").set(snippet)
    _set_comment(node, "V4：每个 Approach 固定生成斑马线和停车线；白条长轴垂直车辆切线。")


def main():
    root = hou.node("/obj/CityRoad_DEV")
    root.allowEditingOfContents(propagate=True)
    core = hou.node(CORE_PATH)
    if core is None:
        raise RuntimeError("Missing " + CORE_PATH)
    apply_graph_and_junction_patch(core)
    apply_curve_patch(core)
    apply_sidewalk_patch(core)
    apply_marking_patch(core)
    core.layoutChildren()
    print("CityRoad topology V4 core patch applied")


main()
