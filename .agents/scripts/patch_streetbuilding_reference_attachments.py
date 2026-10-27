"""Incremental reference attachment migration. Current Live only; never saves.

Run apply(hou.node('/obj/StreetBuilding_DEV'), save=False) through MCP. Exact
Capture hashes protect source edits. Exception restores every original field,
connection and interface and destroys only this patch's new SOPs.
"""
import hashlib
import json
from pathlib import Path

MARKER = 'STREETBUILDING_REFERENCE_ATTACHMENTS_20261024'
ROOT = Path('E:/HoudiniProject/Unity_Houdini_PCG_Track')
BASELINE = ROOT / '.codex_tmp/regression/20261024-214327-StreetBuilding-streetbuilding-reference-attachments-20261024/baseline.json'
NAMES = ('ATTACHMENT_SUPPORT_CANDIDATES','PLAN_CONTINUOUS_ATTACHMENTS','PLAN_TYPED_ROOF_PROPS',
         'ASSEMBLE_CONTINUOUS_ATTACHMENTS','VALIDATE_REFERENCE_ATTACHMENTS','ATTACHMENT_DIAGNOSTICS')

COMMON = r'''
// 输入/输出长度单位m；M旧目录18列保持；X仅承载显式素材语义。
string rr_raw() {return chs("../../unity_style_catalog");}
int rr_sub(string path) {
    foreach(string row;split(rr_raw(),"\n")){string f[]=split(row,"|");if(len(f)==5 && f[0]=="X" && f[1]=="1" && f[2]==path)return atoi(f[3]);}return 0;
}
float rr_joint(string path) {
    foreach(string row;split(rr_raw(),"\n")){string f[]=split(row,"|");if(len(f)==5 && f[0]=="X" && f[1]=="1" && f[2]==path)return atof(f[4]);}return 0;
}
string rr_row(string path) {
    foreach(string row;split(rr_raw(),"\n")){string f[]=split(row,"|");if(len(f)==18 && f[0]=="M" && f[4]==path)return row;}return "";
}
int rr_scope(string path; int band; int facade) {
    foreach(string row;split(rr_raw(),"\n")) {
        string f[]=split(row,"|");
        if(len(f)==18 && f[0]=="M" && f[4]==path && (atoi(f[11])&band)==band && (atoi(f[10])&facade) && atof(f[9])>0)return 1;
    }
    return 0;
}
string rr_pick(int subtype; int band; int facade; int key) {
    string candidates[];float weights[];float total=0;
    foreach(string row;split(rr_raw(),"\n")) {
        string f[]=split(row,"|");if(len(f)!=18 || f[0]!="M" || !(atoi(f[10])&facade) || !(atoi(f[11])&band) || atof(f[9])<=0)continue;
        if(rr_sub(f[4])!=subtype)continue;
        int role=atoi(f[2]);if((subtype<=2 && role!=18) || (subtype>=3 && subtype<=7 && role!=16) || (subtype>=8 && subtype<=12 && role!=23))continue;
        append(candidates,f[4]);append(weights,atof(f[9]));total+=atof(f[9]);
    }
    if(len(candidates)==0)return "";
    float target=rand(float(key)*.173+29.1)*total,at=0;
    for(int i=0;i<len(candidates);i++){at+=weights[i];if(target<=at)return candidates[i];}
    return candidates[-1];
}
void rr_bounds(string path; vector origin; vector right; vector outward; export vector lo; export vector hi) {
    string f[]=split(rr_row(path),"|");lo=set(1e10,1e10,1e10);hi=-lo;
    if(len(f)!=18)return;
    vector minimum=set(atof(f[15]),atof(f[16]),atof(f[17]));vector size=set(atof(f[12]),atof(f[13]),atof(f[14]));
    for(int x=0;x<2;x++)for(int y=0;y<2;y++)for(int z=0;z<2;z++) {
        vector p=minimum+size*set(x,y,z);p=origin+right*p.x+set(0,p.y,0)+outward*p.z;lo=min(lo,p);hi=max(hi,p);
    }
}
int rr_overlap(vector lo;vector hi;vector a;vector b;float margin) {
    return hi.x+margin>a.x && lo.x-margin<b.x && hi.y+margin>a.y && lo.y-margin<b.y && hi.z+margin>a.z && lo.z-margin<b.z;
}
int rr_emit(string path; string role; int subtype; vector pos; vector right; vector outward;
    int face;string surface;int floor;int group;int part;vector joint_a;vector joint_b) {
    int p=addpoint(0,set(-pos.x,pos.y,pos.z));float yaw=degrees(atan2(-outward.x,outward.z));
    string gid=sprintf("B0_%s_%d_%s",role,group,surface);
    string prefix=sprintf("SB_REF_%s_F%02d_P%02d",gid,floor,part);
    setpointattrib(0,"orient",p,quaternion(radians(yaw),set(0,1,0)),"set");setpointattrib(0,"scale",p,set(1,1,1),"set");
    setpointattrib(0,"unity_instance",p,path,"set");setpointattrib(0,"module_role",p,role,"set");
    string f[]=split(rr_row(path),"|");string variant=len(f)==18?f[3]:"";
    setpointattrib(0,"module_variant",p,variant,"set");setpointattrib(0,"pcg_variant",p,variant,"set");
    setpointattrib(0,"name",p,prefix,"set");setpointattrib(0,"instance_prefix",p,prefix,"set");
    setpointattrib(0,"pcg_kind",p,"streetbuilding_detail_instance","set");
    setpointattrib(0,"building_id",p,0,"set");setpointattrib(0,"face_index",p,face,"set");
    setpointattrib(0,"floor_index",p,floor,"set");setpointattrib(0,"cell_index",p,group,"set");
    setpointattrib(0,"module_span",p,len(f)==18?atoi(f[5]):1,"set");setpointattrib(0,"selection_seed",p,group,"set");
    setpointattrib(0,"surface_role",p,surface,"set");setpointattrib(0,"facade_band",p,(face==4 || subtype==7 || subtype==9)?"roof":floor==0?"ground":"middle","set");
    setpointattrib(0,"is_building_entrance",p,0,"set");setpointattrib(0,"is_shop_entrance",p,0,"set");
    setpointattrib(0,"lod",p,0,"set");setpointattrib(0,"chunk_id",p,0,"set");
    setpointattrib(0,"attachment_group_id",p,gid,"set");setpointattrib(0,"attachment_part_index",p,part,"set");
    setpointattrib(0,"attachment_subtype",p,subtype,"set");
    setpointattrib(0,"connection_start",p,set(-joint_a.x,joint_a.y,joint_a.z),"set");
    setpointattrib(0,"connection_end",p,set(-joint_b.x,joint_b.y,joint_b.z),"set");
    vector lo,hi;rr_bounds(path,pos,right,outward,lo,hi);setpointattrib(0,"attachment_bounds_min",p,lo,"set");setpointattrib(0,"attachment_bounds_max",p,hi,"set");
    return p;
}
int rr_enabled(){return chi("../../module_source")==1 && chi("../../attachments_enabled") && int(detail("op:../SELECT_ATTACHMENT_MODULES","effective_attachments",0));}
int rr_active(){return chi("../../roof_props_layout_mode")==1 || chi("../../fire_escape_layout_mode")==1 || chi("../../drainpipe_enabled");}
'''

SUPPORTS = r'''
// 真实墙段候选：从最终墙窗模块提取；共享层间位置，不使用包围盒假墙。
if(!rr_active())return;
float cw=detail("op:../PARSE_UNITY_INSTANCE_CATALOG","style_cell_width",0);
string keys[];vector origins[],rights[];string surfaces[];int faces[],masks[];float lows[],highs[];
for(int h=0;h<npoints(1);h++) {
    if(int(point(1,"floor_index",h))!=1 || int(point(1,"preview_missing",h)))continue;
    string role=point(1,"module_role",h);
    if(role!="MiddleWindow" && role!="MiddleBlank" && role!="SideWall" && role!="RearWall")continue;
    int face=point(1,"face_index",h),target=point(1,"facade_target",h);string surface=point(1,"surface_role",h);
    vector origin=point(1,"arrangement_origin",h),right=point(1,"arrangement_right",h);origin.y=0;
    if(abs(length2(right)-1)>.001)continue;
    string key=sprintf("%d/%s/%g/%g/%g/%g",face,surface,origin.x,origin.z,right.x,right.z);
    int run=find(keys,key);if(run<0){run=len(keys);append(keys,key);append(origins,origin);append(rights,right);append(surfaces,surface);append(faces,face);append(masks,target==0?1:target==1?2:target==3?8:4);append(lows,1e10);append(highs,-1e10);}
    vector p=point(1,"P",h);p.x=-p.x;p.y=0;float u=dot(p-origin,right),halfspan=max(1,int(point(1,"module_span",h)))*cw*.5;
    lows[run]=min(lows[run],u-halfspan);highs[run]=max(highs[run],u+halfspan);
}
for(int r=0;r<len(keys);r++) {
    int p=addpoint(0,origins[r]);setpointattrib(0,"support_origin",p,origins[r],"set");setpointattrib(0,"support_right",p,rights[r],"set");
    setpointattrib(0,"support_outward",p,normalize(cross(rights[r],set(0,1,0))),"set");
    setpointattrib(0,"support_surface",p,surfaces[r],"set");setpointattrib(0,"support_face",p,faces[r],"set");
    setpointattrib(0,"support_mask",p,masks[r],"set");setpointattrib(0,"support_low",p,lows[r],"set");setpointattrib(0,"support_high",p,highs[r],"set");
}
'''

CONTINUOUS = r'''
// 整组布局：消防梯优先，管线复用一个竖向走廊；失败整组拒绝。
if(!rr_active())return;
int enabled=rr_enabled(),floors=detail("op:../SELECT_ATTACHMENT_MODULES","effective_floor_count",0);
float gh=detail("op:../PARSE_UNITY_INSTANCE_CATALOG","style_ground_height",0),th=detail("op:../PARSE_UNITY_INSTANCE_CATALOG","style_typical_height",0);
float roof=gh+(floors-1)*th;
int frequest=chi("../../fire_escape_layout_mode")==1?max(0,chi("../../fire_escape_group_count")):0;
int drequest=chi("../../drainpipe_enabled")?max(0,chi("../../drainpipe_count")):0;
int fact=0,dact=0;string freason=enabled?"capacity":"disabled",dreason=freason;
int first=max(2,chi("../../fire_escape_floor_start")),last=min(floors,chi("../../fire_escape_floor_end"));
vector occupied_lo[],occupied_hi[];
for(int r=0;r<npoints(1) && fact<frequest && enabled;r++) {
    int mask=point(1,"support_mask",r),face=point(1,"support_face",r);if(!(mask&chi("../../fire_escape_face_mask")))continue;
    vector origin=point(1,"support_origin",r),right=point(1,"support_right",r),out=point(1,"support_outward",r);string surf=point(1,"support_surface",r);
    float low=point(1,"support_low",r),high=point(1,"support_high",r);if(first>last){freason="floor_range";continue;}
    if(chi("../../fire_escape_roof_access") && last!=floors){freason="roof_access_floor_range";continue;}
    string left=rr_pick(3,2,mask,101+r),rightpart=rr_pick(4,2,mask,102+r),top=rr_pick(5,2,mask,103+r),bottom=rr_pick(6,2,mask,104+r),access=rr_pick(7,4,mask,105+r);
    if(len(left)==0 || len(rightpart)==0 || len(top)==0 || len(bottom)==0 || (chi("../../fire_escape_roof_access") && len(access)==0)){freason="no_material";continue;}
    if(abs(rr_joint(left)-th)>.005 || abs(rr_joint(rightpart)-th)>.005){freason="height_mismatch";continue;}
    int need=last-first+2+(chi("../../fire_escape_roof_access")?1:0);if(npoints(0)+need>64){freason="budget";continue;}
    for(float u=low+2;u<=high-2+.001 && fact<frequest;u+=4) {
        // 验证真实窗口宿主覆盖每层，同方向分段从不跨越凹口。
        int hosts_ok=1;
        for(int f=first-1;f<=last-1;f++) {
            int found=0;
            for(int h=0;h<npoints(2);h++) {
                if(int(point(2,"floor_index",h))!=f || int(point(2,"face_index",h))!=face || string(point(2,"surface_role",h))!=surf || string(point(2,"module_role",h))!="MiddleWindow" || int(point(2,"preview_missing",h)))continue;
                vector hp=point(2,"P",h);hp.x=-hp.x;hp.y=0;
                vector delta=hp-origin;float hu=dot(delta,right);
                if(length(delta-right*hu)<.001 && abs(hu-u)<=1.01){found=1;break;}
            }
            if(!found){hosts_ok=0;break;}
        }
        if(!hosts_ok)continue;
        vector pos=origin+right*u+set(0,gh+(first-2)*th,0);vector lo,hi;rr_bounds(left,pos,right,out,lo,hi);hi.y=gh+(last-2)*th+1;
        int hit=0;for(int i=0;i<len(occupied_lo);i++)if(rr_overlap(lo,hi,occupied_lo[i],occupied_hi[i],.15))hit=1;if(hit)continue;
        append(occupied_lo,lo);append(occupied_hi,hi);
        int part=0;
        rr_emit(bottom,"FireEscape",6,pos,right,out,face,surf,first-1,fact,part++,pos,pos);
        for(int f=first;f<last;f++) {
            int st=(f-first)%2==0?3:4;string path=st==3?left:rightpart;
            vector p=origin+right*u+set(0,gh+(f-2)*th,0);
            float sx=st==3?-1.3:1.3,ex=-sx;
            rr_emit(path,"FireEscape",st,p,right,out,face,surf,f-1,fact,part++,p+right*sx+out,p+right*ex+out+set(0,th,0));
        }
        vector final=origin+right*u+set(0,gh+(last-2)*th,0);
        rr_emit(top,"FireEscape",5,final,right,out,face,surf,last-1,fact,part++,final,final);
        if(chi("../../fire_escape_roof_access"))
            rr_emit(access,"FireEscape",7,origin+right*u+set(0,roof,0),right,out,face,surf,floors,fact,part++,final,final);
        fact++;
    }
}
if(fact==frequest)freason="none";
for(int r=0;r<npoints(1) && dact<drequest && enabled;r++) {
    int mask=point(1,"support_mask",r),face=point(1,"support_face",r);if(!(mask&chi("../../drainpipe_face_mask")))continue;
    vector origin=point(1,"support_origin",r),right=point(1,"support_right",r),out=point(1,"support_outward",r);string surf=point(1,"support_surface",r);
    float low=point(1,"support_low",r),high=point(1,"support_high",r);
    string straight=rr_pick(8,2,mask,211+r),top=rr_pick(9,4,mask,212+r),bottom=rr_pick(10,1,mask,213+r);
    if(len(straight)==0 || len(top)==0 || len(bottom)==0 || !rr_scope(straight,1,mask)){dreason="no_material";continue;}
    float length=rr_joint(straight);if(length<=0 || abs(roof/length-rint(roof/length))>.005){dreason="height_mismatch";continue;}
    int segments=int(rint(roof/length));if(npoints(0)+segments+2>64){dreason="budget";continue;}
    // 固定墙段两端走廊，避开窗中心；整条共用u，不逐层重抽。
    for(int side=0;side<2 && dact<drequest;side++) {
        float u=side==0?low+.16:high-.16;if(high-low<.5)continue;
        vector pos=origin+right*u,lo,hi;rr_bounds(straight,pos,right,out,lo,hi);hi.y=roof+.1;
        int hit=0;for(int i=0;i<len(occupied_lo);i++)if(rr_overlap(lo,hi,occupied_lo[i],occupied_hi[i],.15))hit=1;if(hit)continue;
        append(occupied_lo,lo);append(occupied_hi,hi);
        int part=0;rr_emit(bottom,"DrainPipe",10,pos,right,out,face,surf,0,dact,part++,pos+out*.55,pos+out*.55);
        for(int s=0;s<segments;s++) {
            vector p=pos+set(0,s*length,0);
            int host_floor=p.y<gh-.001?0:min(floors-1,1+int(floor((p.y-gh)/th)));
            rr_emit(straight,"DrainPipe",8,p,right,out,face,surf,host_floor,dact,part++,p+out*.55,p+out*.55+set(0,length,0));
        }
        vector final=pos+set(0,roof,0);rr_emit(top,"DrainPipe",9,final,right,out,face,surf,floors,dact,part++,final+out*.55,final+out*.55);dact++;
    }
}
if(dact==drequest)dreason="none";
setdetailattrib(0,"reference_fire_requested",frequest,"set");setdetailattrib(0,"reference_fire_actual",fact,"set");setdetailattrib(0,"reference_fire_reason",freason,"set");
setdetailattrib(0,"reference_drain_requested",drequest,"set");setdetailattrib(0,"reference_drain_actual",dact,"set");setdetailattrib(0,"reference_drain_reason",dreason,"set");
'''

ROOF = r'''
// 全支承包围多边形检查：矩形物件的AABB是保守占地，不只检查中心或四角。
if(!rr_active())return;
int enabled=rr_enabled() && int(detail("op:../SELECT_ATTACHMENT_MODULES","effective_generate_roof",0));
float w=detail("op:../SELECT_ATTACHMENT_MODULES","effective_width",0),d=detail("op:../SELECT_ATTACHMENT_MODULES","effective_depth",0);
int floors=detail("op:../SELECT_ATTACHMENT_MODULES","effective_floor_count",0);
float roof=detail("op:../PARSE_UNITY_INSTANCE_CATALOG","style_ground_height",0)+(floors-1)*float(detail("op:../PARSE_UNITY_INSTANCE_CATALOG","style_typical_height",0));
int shape=detail("op:../SELECT_ATTACHMENT_MODULES","effective_shape",0),side=detail("op:../SELECT_ATTACHMENT_MODULES","effective_notch_side",0);
float nw=detail("op:../SELECT_ATTACHMENT_MODULES","effective_notch_width",0),nd=detail("op:../SELECT_ATTACHMENT_MODULES","effective_notch_depth",0);
for(int subtype=1;subtype<=2;subtype++) {
    int requested=chi("../../roof_props_layout_mode")==1?max(0,chi(subtype==1?"../../water_tower_count":"../../chimney_count")):0,actual=0;
    string reason=enabled?"capacity":"disabled";
    for(float z=-1;z>=-d+1 && actual<requested && enabled;z-=.5)for(float x=-w*.5+1;x<=w*.5-1 && actual<requested;x+=.5) {
        string path=rr_pick(subtype,4,15,subtype*101+actual);if(len(path)==0){reason="no_material";continue;}
        vector pos=set(x,roof,z),lo,hi;rr_bounds(path,pos,set(1,0,0),set(0,0,1),lo,hi);
        float margin=.25;if(lo.x<-w*.5+margin || hi.x>w*.5-margin || lo.z<-d+margin || hi.z>-margin)continue;
        if(shape==1) {
            vector nl=set(side%2==0?-w*.5:w*.5-nw,roof-1,side<2?-d:-nd);
            vector nh=set(side%2==0?-w*.5+nw:w*.5,roof+100,side<2?-d+nd:0);
            if(rr_overlap(lo,hi,nl,nh,margin))continue;
        }
        int hit=0;for(int p=0;p<npoints(0);p++) {
            vector a=point(0,"attachment_bounds_min",p),b=point(0,"attachment_bounds_max",p);
            if(rr_overlap(lo,hi,a,b,.3)){hit=1;break;}
        }
        if(hit)continue;if(npoints(0)>=64){reason="budget";continue;}
        rr_emit(path,"RoofProp",subtype,pos,set(1,0,0),set(0,0,1),4,"roof",floors,actual+(subtype-1)*32,0,pos,pos);actual++;
    }
    if(actual==requested)reason="none";
    string token=subtype==1?"water":"chimney";
    setdetailattrib(0,"reference_"+token+"_requested",requested,"set");setdetailattrib(0,"reference_"+token+"_actual",actual,"set");setdetailattrib(0,"reference_"+token+"_reason",reason,"set");
}
'''

ASSEMBLY = r'''
// 旧模式原样透传；新模式逐组有限装配，Unity消费单位scale的Prefab实例。
if(!rr_active())return;
// 新走廊优先；仅新模式启用时移除相交的旧概率小附件，实例请求不回写。
for(int p=npoints(0)-1;p>=0;p--) {
    string role=point(0,"module_role",p);if(role!="ACUnit" && role!="Awning" && role!="Sign")continue;
    vector pos=point(0,"P",p);pos.x=-pos.x;int face=point(0,"face_index",p);
    vector right=face==0?set(1,0,0):face==1?set(0,0,1):face==2?set(0,0,-1):set(-1,0,0);
    vector out=normalize(cross(right,set(0,1,0))),lo,hi;rr_bounds(string(point(0,"unity_instance",p)),pos,right,out,lo,hi);
    for(int q=0;q<npoints(1);q++)if(rr_overlap(lo,hi,vector(point(1,"attachment_bounds_min",q)),vector(point(1,"attachment_bounds_max",q)),.05)){removepoint(0,p);break;}
}
int available=64-npoints(0);string accepted[];
for(int q=0;q<npoints(1);q++) {
    string group=point(1,"attachment_group_id",q);if(find(accepted,group)>=0)continue;
    int need=0;for(int s=0;s<npoints(1);s++)if(string(point(1,"attachment_group_id",s))==group)need++;
    if(need>available)continue;append(accepted,group);available-=need;
}
string ints[]=array("building_id","face_index","floor_index","cell_index","module_span","selection_seed","is_building_entrance","is_shop_entrance","lod","chunk_id","attachment_part_index","attachment_subtype");
string texts[]=array("unity_instance","module_role","module_variant","pcg_variant","name","instance_prefix","pcg_kind","surface_role","facade_band","attachment_group_id");
string vectors[]=array("scale","connection_start","connection_end","attachment_bounds_min","attachment_bounds_max");
for(int q=0;q<npoints(1);q++) {
    if(find(accepted,string(point(1,"attachment_group_id",q)))<0)continue;
    int p=addpoint(0,vector(point(1,"P",q)));foreach(string a;ints)setpointattrib(0,a,p,int(point(1,a,q)),"set");
    foreach(string a;texts)setpointattrib(0,a,p,string(point(1,a,q)),"set");foreach(string a;vectors)setpointattrib(0,a,p,vector(point(1,a,q)),"set");
    setpointattrib(0,"orient",p,vector4(point(1,"orient",q)),"set");
}
string diagnostic_tokens[]=array("fire","drain","water","chimney");
foreach(string token;diagnostic_tokens) {
    setdetailattrib(0,"reference_"+token+"_requested",int(detail(1,"reference_"+token+"_requested",0)),"set");
    setdetailattrib(0,"reference_"+token+"_actual",int(detail(1,"reference_"+token+"_actual",0)),"set");
    setdetailattrib(0,"reference_"+token+"_reason",string(detail(1,"reference_"+token+"_reason",0)),"set");
}
setdetailattrib(0,"streetbuilding_detail_count",npoints(0),"set");
setdetailattrib(0,"streetbuilding_effective_width",float(detail("op:../SELECT_ATTACHMENT_MODULES","effective_width",0)),"set");
setdetailattrib(0,"streetbuilding_effective_depth",float(detail("op:../SELECT_ATTACHMENT_MODULES","effective_depth",0)),"set");
setdetailattrib(0,"streetbuilding_effective_floor_count",int(detail("op:../SELECT_ATTACHMENT_MODULES","effective_floor_count",0)),"set");
setdetailattrib(0,"streetbuilding_effective_shape",int(detail("op:../SELECT_ATTACHMENT_MODULES","effective_shape",0)),"set");
'''

VALIDATE = r'''
// 独立输出几何门禁：只读真实零件和连接属性；禁止断组/负缩放。
if(!rr_active())return;
for(int p=0;p<npoints(0);p++) {
    string gid=point(0,"attachment_group_id",p);if(len(gid)==0)continue;
    if(distance(vector(point(0,"scale",p)),set(1,1,1))>.0001)error("Reference attachment scale must remain one");
    int st=point(0,"attachment_subtype",p);if(st!=3 && st!=4 && st!=8)continue;
    int index=point(0,"attachment_part_index",p);
    for(int q=0;q<npoints(0);q++) {
        int next=point(0,"attachment_subtype",q);
        if(string(point(0,"attachment_group_id",q))!=gid || int(point(0,"attachment_part_index",q))!=index+1 || (next!=3 && next!=4 && next!=8))continue;
        if(distance(vector(point(0,"connection_end",p)),vector(point(0,"connection_start",q)))>.005)error("Reference attachment connection gap: %s",gid);
    }
}
'''

DIAGNOSTICS = r'''
// 请求值始终来自实例；统计完整组和零件分别计数，不用元数据冒充实际。
if(!rr_active())return;
string report="v1\n",tokens[]=array("water","chimney","fire","drain"),names[]=array("WaterTower","Chimney","FireEscape","DrainPipe");
for(int kind=0;kind<4;kind++) {
    string groups[];int pieces=0;
    for(int p=0;p<npoints(0);p++) {
        int st=point(0,"attachment_subtype",p);int match=kind==0?st==1:kind==1?st==2:kind==2?st>=3 && st<=7:st>=8 && st<=12;
        if(!match)continue;string group=point(0,"attachment_group_id",p);if(find(groups,group)<0)append(groups,group);pieces++;
    }
    int request=detail(0,"reference_"+tokens[kind]+"_requested",0),actual=len(groups);string reason=detail(0,"reference_"+tokens[kind]+"_reason",0);
    if(actual<request && reason=="none")reason="budget";
    report+=sprintf("R|%s|%d|%d|%s|instance\n",names[kind],request,actual,reason);
    setdetailattrib(0,"reference_"+tokens[kind]+"_actual",actual,"set");setdetailattrib(0,"reference_"+tokens[kind]+"_parts",pieces,"set");
}
setdetailattrib(0,"reference_attachment_diagnostics",report,"set");setdetailattrib(0,"streetbuilding_detail_count",npoints(0),"set");
'''


def _interface(hou, asset, group=None):
    if group is None:group = asset.parmTemplateGroup()
    if group.find('roof_props_layout_mode') is not None:
        return group
    def integer(name,label,default,minimum=0,maximum=64,condition=''):
        p=hou.IntParmTemplate(name,label,1,default_value=(default,),min=minimum,max=maximum,min_is_strict=True,max_is_strict=True)
        if condition:p.setConditional(hou.parmCondType.HideWhen,condition)
        return p
    def mode(name,label,tokens,labels):
        return hou.MenuParmTemplate(name,label,menu_items=tokens,menu_labels=labels,default_value=0)
    fields=[mode('roof_props_layout_mode','屋顶附件布局',('legacy','typed_counts'),('旧概率散布','按类型固定数量')),
        integer('water_tower_count','完整水塔（每栋）',0,0,2,'{ roof_props_layout_mode == 0 }'),
        integer('chimney_count','完整烟囱（每栋）',0,0,4,'{ roof_props_layout_mode == 0 }'),
        mode('fire_escape_layout_mode','消防梯布局',('legacy','continuous'),('旧单段','连续梯组')),
        integer('fire_escape_group_count','连续消防梯组（整栋共享）',0,0,8,'{ fire_escape_layout_mode == 0 }'),
        integer('fire_escape_face_mask','消防梯立面位掩码（1正/2次正/4侧/8背）',8,0,15,'{ fire_escape_layout_mode == 0 }'),
        integer('fire_escape_floor_start','服务起始层（首层=1）',2,2,99,'{ fire_escape_layout_mode == 0 }'),
        integer('fire_escape_floor_end','服务终止层（自动截到实际层数）',99,2,99,'{ fire_escape_layout_mode == 0 }'),
        hou.ToggleParmTemplate('fire_escape_roof_access','顶部检修梯',default_value=False),
        hou.ToggleParmTemplate('drainpipe_enabled','连续落水管',default_value=False),
        integer('drainpipe_count','完整管线（整栋共享）',0,0,8,'{ drainpipe_enabled == 0 }'),
        integer('drainpipe_face_mask','落水管立面位掩码（1正/2次正/4侧/8背）',12,0,15,'{ drainpipe_enabled == 0 }')]
    fields[8].setConditional(hou.parmCondType.HideWhen,'{ fire_escape_layout_mode == 0 }')
    folder=hou.FolderParmTemplate('sb_reference_attachments','参考附件 / Reference Attachments',parm_templates=fields,folder_type=hou.folderType.Simple)
    host=next(t for t in group.entries() if isinstance(t,hou.FolderParmTemplate) and any(x.name()=='attachments_enabled' for x in t.parmTemplates()))
    group.appendToFolder(host,folder)
    for name in ('roof_props_density','roof_props_max_count','fire_escape_density','fire_escape_max_count'):
        t=group.find(name);t.setConditional(hou.parmCondType.HideWhen,'{ '+('roof_props_layout_mode' if name.startswith('roof_') else 'fire_escape_layout_mode')+' != 0 }');group.replace(name,t)
    t=group.find('attachment_global_density');t.setLabel('概率散布密度 / Legacy Scatter Density');group.replace(t.name(),t)
    return group


def apply(asset, save=False, hou_module=None):
    if hou_module is None:
        import hou
    else:
        hou = hou_module
    if save:
        raise RuntimeError('This incremental patch never saves production files')
    if asset.path()!='/obj/StreetBuilding_DEV' or asset.type().name()!='pcgbike::StreetBuilding::1.0':
        raise RuntimeError('Unexpected Live asset identity')
    core=asset.node('StreetBuildingCore')
    if core.node(NAMES[-1]) is not None:
        if MARKER not in core.node(NAMES[-1]).evalParm('snippet'):
            raise RuntimeError('Unrecognized existing reference attachment nodes')
        return {'status':'unchanged','save':False}
    baseline=json.loads(BASELINE.read_text(encoding='utf-8'))
    # Source text from exact current Capture, no historical patch dependency.
    targets=('PARSE_UNITY_INSTANCE_CATALOG','DETAIL_INSTANCE_POINTS','VALIDATE_DIRECT_DETAIL_INSTANCES','BUILD_METADATA')
    for name in targets:
        original=baseline['nodes']['StreetBuildingCore/'+name]['parameters']['snippet']['raw']
        if core.node(name).parm('snippet').rawValue()!=original:
            raise RuntimeError('Capture source hash mismatch: '+name)
    previous_group=asset.parmTemplateGroup()
    previous={n.name():{'snippet':n.parm('snippet').rawValue() if n.parm('snippet') else None,'inputs':tuple(n.inputs())} for n in core.children()}
    added=[]
    try:
        asset.setParmTemplateGroup(_interface(hou,asset))
        parser=core.node('PARSE_UNITY_INSTANCE_CATALOG');source=parser.evalParm('snippet')
        needle='"ParapetConcaveCorner","FloorBandCorner");'
        if source.count(needle)!=1:raise RuntimeError('Parser role precondition changed')
        parser.parm('snippet').set(source.replace(needle,'"ParapetConcaveCorner","FloorBandCorner","DrainPipe");'))
        # Legacy selection rejects semantic termination pieces; Generic and
        # compatible storey assets retain original catalog order and RNG calls.
        detail=core.node('DETAIL_INSTANCE_POINTS');source=detail.evalParm('snippet')
        source=source.replace('if (master<=0) {return;}','if (master<=0) {return;}')
        fire='if ((sb_mask(1,2)&8) && count[2]<sb_maximum(1,2)'
        roof='if (count[4]<sb_maximum(2,4)'
        if source.count(fire)!=1 or source.count(roof)!=1:raise RuntimeError('Legacy emitter marker mismatch')
        source=source.replace(fire,'if (chi("../../fire_escape_layout_mode")==0 && (sb_mask(1,2)&8) && count[2]<sb_maximum(1,2)')
        source=source.replace(roof,'if (chi("../../roof_props_layout_mode")==0 && count[4]<sb_maximum(2,4)')
        marker='if(len(f)!=18 || f[0]!="M") continue;'
        filtering='''
        if(atoi(f[2])==16) {
            int subtype=0;foreach(string xr;split(raw,"\\n")){string x[]=split(xr,"|");if(len(x)==5 && x[0]=="X" && x[2]==f[4])subtype=atoi(x[3]);}
            if(subtype>=5)continue;
        }
'''
        if source.count(marker)!=1:raise RuntimeError('Legacy catalog filter marker mismatch')
        source=source.replace(marker,marker+filtering)
        detail.parm('snippet').set(source)
        guard=core.node('VALIDATE_DIRECT_DETAIL_INSTANCES');source=guard.evalParm('snippet')
        source=source.replace('"ParapetConcaveCorner");','"ParapetConcaveCorner","FloorBandCorner","DrainPipe");')
        source=source.replace('if (role == "FireEscape" && face != 3)','if (role == "FireEscape" && face != 3 && chi("../../fire_escape_layout_mode")==0)')
        guard.parm('snippet').set(source)
        recipes=[SUPPORTS,CONTINUOUS,ROOF,ASSEMBLY,VALIDATE,DIAGNOSTICS]
        comments=['候选支承面：输入最终墙窗，输出真实物理墙段及范围；单位m。',
            '整组布局：消防梯优先，管线整条共享位置；失败保留请求并报告原因。',
            '屋顶类型配额：完整占地与凹口相交检测，水塔优先，再布烟囱。',
            '零件装配：单位缩放；有限64零件预算，完整组原子装配。',
            '连接验证：梯组与管线真实端点误差≤5mm；扩展点为显式素材子类型。',
            '诊断：按完整组统计请求、实际、原因；零件数单独统计。']
        nodes={}
        for index,(name,recipe,comment) in enumerate(zip(NAMES,recipes,comments)):
            n=core.createNode('attribwrangle',name);added.append(n);nodes[name]=n
            n.setParms({'class':'detail','snippet':'// '+MARKER+'\n'+COMMON+recipe});n.setComment(comment);n.setGenericFlag(hou.nodeFlag.DisplayComment,True)
            n.setPosition(hou.Vector2(32+index*3,-14))
        support,plan,roofnode,assembly,valid,diag=[nodes[name] for name in NAMES]
        support.setInput(0,core.node('EMPTY_GEOMETRY'));support.setInput(1,core.node('SELECT_FACADE_MODULES'))
        plan.setInput(0,core.node('EMPTY_GEOMETRY'));plan.setInput(1,support);plan.setInput(2,core.node('SELECT_FACADE_MODULES'))
        roofnode.setInput(0,plan);assembly.setInput(0,detail);assembly.setInput(1,roofnode);valid.setInput(0,assembly);diag.setInput(0,valid)
        guard.setInput(0,diag);core.node('METADATA_ATTACHMENT_INPUTS').setInput(1,diag)
        metadata=core.node('BUILD_METADATA');metadata.parm('snippet').set(metadata.evalParm('snippet')+'\n// '+MARKER+'\nif(hasdetailattrib(3,"reference_attachment_diagnostics"))setdetailattrib(0,"reference_attachment_diagnostics",string(detail(3,"reference_attachment_diagnostics",0)),"set");\n')
        # Existing 9 navigation boxes/notes are cumulative interface; append
        # new nodes to the current attachment box without changing their count.
        box=core.findNetworkBox('50_ATTACHMENT_INSTANCES')
        if box is None:raise RuntimeError('Attachment stage box missing')
        for n in added:box.addItem(n)
        for n in (support,plan,roofnode,assembly,valid,diag):
            try:n.cook(force=True)
            except Exception as error:raise RuntimeError(n.name()+': '+repr((n.errors(),n.warnings()))) from error
            if n.errors() or n.warnings():raise RuntimeError(n.name()+': '+repr((n.errors(),n.warnings())))
        return {'status':'patched','save':False,'nodes':list(NAMES)}
    except Exception:
        for n in reversed(added):n.destroy()
        asset.setParmTemplateGroup(previous_group)
        for name,state in previous.items():
            n=core.node(name)
            if state['snippet'] is not None:n.parm('snippet').set(state['snippet'])
            for i in range(len(n.inputs())):n.setInput(i,None)
            for i,source in enumerate(state['inputs']):n.setInput(i,source)
        raise


def adjust_layout(asset, save=False, hou_module=None):
    """Repair the current unsaved patch's stage membership, with exact rollback."""
    if hou_module is None:
        import hou
    else:
        hou=hou_module
    if save or asset.path()!='/obj/StreetBuilding_DEV':
        raise RuntimeError('Unexpected layout target or persistence request')
    core=asset.node('StreetBuildingCore')
    target=core.findNetworkBox('50_ATTACHMENT_INSTANCES')
    source=core.findNetworkBox('80_OUTPUT_VALIDATE')
    if target is None or source is None:
        raise RuntimeError('Capture stage boxes not found')
    nodes=[core.node(name) for name in NAMES]
    if any(node is None or MARKER not in node.evalParm('snippet') for node in nodes):
        raise RuntimeError('Current Live patch marker mismatch')
    desired=[hou.Vector2(32+index*3,-14) for index in range(len(nodes))]
    if all(node.parentNetworkBox()==target and node.position()==position
           for node,position in zip(nodes,desired)):
        return {'status':'unchanged','save':False}
    if any(node.parentNetworkBox() not in (source,target) for node in nodes):
        raise RuntimeError('Unrecognized reference attachment box ownership')
    old=[(node,node.parentNetworkBox(),node.position()) for node in nodes]
    bounds=[(box,box.position(),box.size()) for box in (source,target)]
    try:
        for node,position in zip(nodes,desired):
            prior=node.parentNetworkBox()
            if prior is not None:prior.removeItem(node)
            node.setPosition(position)
            target.addItem(node)
        for box,position,size in bounds:
            box.setPosition(position);box.setSize(size)
        return {'status':'patched','save':False,'stage':target.name(),'nodes':list(NAMES)}
    except Exception:
        for node,prior,position in old:
            current=node.parentNetworkBox()
            if current is not None:current.removeItem(node)
            node.setPosition(position)
            if prior is not None:prior.addItem(node)
        for box,position,size in bounds:
            box.setPosition(position);box.setSize(size)
        raise


def revise_roof_access(asset, save=False, hou_module=None):
    """Reject a requested roof connection as one group when it cannot reach roof."""
    if hou_module is None:
        import hou
    else:
        hou=hou_module
    if save or asset.path()!='/obj/StreetBuilding_DEV':
        raise RuntimeError('Unexpected roof-access target or persistence request')
    node=asset.node('StreetBuildingCore/PLAN_CONTINUOUS_ATTACHMENTS')
    original=node.parm('snippet').rawValue()
    desired='// '+MARKER+'\n'+COMMON+CONTINUOUS
    if original==desired:
        return {'status':'unchanged','save':False}
    expected='e47818ed9cd5498e0d9a96604c636f4c79bcae3f0186e111d9d632e739775b84'
    if hashlib.sha256(original.encode('utf-8')).hexdigest()!=expected:
        raise RuntimeError('Live roof-access VEX no longer matches the reviewed pre-edit hash')
    try:
        node.parm('snippet').set(desired)
        node.cook(force=True)
        if node.errors() or node.warnings():
            raise RuntimeError('Roof-access VEX diagnostics: '+repr((node.errors(),node.warnings())))
        return {'status':'patched','save':False,'node':node.path()}
    except Exception:
        node.parm('snippet').set(original)
        raise


def revise_roof_reservations(asset, save=False, hou_module=None):
    """Reserve newly accepted roof props locally; preserve the reviewed Live COMMON.

    The hash is from the current Live rawValue recorded in live-roof-snippet.json,
    not a regenerated recipe. Only four exact ASCII body blocks are replaced.
    """
    if save or asset.path() != '/obj/StreetBuilding_DEV' or asset.type().name() != 'pcgbike::StreetBuilding::1.0':
        raise RuntimeError('Unexpected roof-reservation target or persistence request')
    node = asset.node('StreetBuildingCore/PLAN_TYPED_ROOF_PROPS')
    if node is None:
        raise RuntimeError('Reviewed Live roof planner is missing')
    parm = node.parm('snippet')
    original = parm.rawValue()
    expected = '0a2ab17cdfb34cddf8cece59fea4940aa9314e660725eb65641c2ad5128c0232'
    revision = '// STREETBUILDING_REFERENCE_ROOF_RESERVATIONS_20261025\n'
    prefix = '// ' + MARKER + '\n'
    replacements = (
        ('for(int subtype=1;subtype<=2;subtype++) {',
         'int input_point_count=npoints(0),new_emit_count=0;\n'
         'vector reserved_lo[],reserved_hi[];\n'
         '// Same-pass addpoint writes are not readable; reserve accepted bounds locally.\n'
         'for(int p=0;p<input_point_count;p++) {\n'
         '    append(reserved_lo,vector(point(0,"attachment_bounds_min",p)));\n'
         '    append(reserved_hi,vector(point(0,"attachment_bounds_max",p)));\n'
         '}\n'
         'for(int subtype=1;subtype<=2;subtype++) {'),
        ('        int hit=0;for(int p=0;p<npoints(0);p++) {\n'
         '            vector a=point(0,"attachment_bounds_min",p),b=point(0,"attachment_bounds_max",p);\n'
         '            if(rr_overlap(lo,hi,a,b,.3)){hit=1;break;}\n'
         '        }',
         '        int hit=0;for(int p=0;p<len(reserved_lo);p++) {\n'
         '            if(rr_overlap(lo,hi,reserved_lo[p],reserved_hi[p],.3)){hit=1;break;}\n'
         '        }'),
        ('        if(hit)continue;if(npoints(0)>=64){reason="budget";continue;}',
         '        if(hit)continue;if(input_point_count+new_emit_count>=64){reason="budget";continue;}'),
        ('        rr_emit(path,"RoofProp",subtype,pos,set(1,0,0),set(0,0,1),4,"roof",floors,actual+(subtype-1)*32,0,pos,pos);actual++;',
         '        rr_emit(path,"RoofProp",subtype,pos,set(1,0,0),set(0,0,1),4,"roof",floors,actual+(subtype-1)*32,0,pos,pos);\n'
         '        append(reserved_lo,lo);append(reserved_hi,hi);new_emit_count++;actual++;'),
    )
    digest = lambda text: hashlib.sha256(text.encode('utf-8')).hexdigest()
    if revision in original:
        # Reverse the exact approved transformation to validate idempotence
        # without copying/re-encoding any pre-existing COMMON or Chinese text.
        reviewed = original
        if reviewed.count(revision) != 1 or not reviewed.startswith(prefix + revision):
            raise RuntimeError('Roof-reservation revision marker changed')
        for old, new in reversed(replacements):
            if reviewed.count(new) != 1:
                raise RuntimeError('Existing roof-reservation revision differs from this repair')
            reviewed = reviewed.replace(new, old)
        reviewed = reviewed.replace(prefix + revision, prefix, 1)
        if digest(reviewed) != expected:
            raise RuntimeError('Existing roof-reservation VEX does not derive from reviewed Live')
        return {'status': 'unchanged', 'save': False, 'node': node.path(), 'sha256': digest(original)}
    if digest(original) != expected or not original.startswith(prefix):
        raise RuntimeError('Live roof-reservation VEX no longer matches the reviewed pre-edit hash')
    desired = original
    for old, new in replacements:
        if desired.count(old) != 1:
            raise RuntimeError('Exact Live roof-reservation body precondition changed')
        desired = desired.replace(old, new)
    desired = desired.replace(prefix, prefix + revision, 1)
    try:
        parm.set(desired)
        node.cook(force=True)
        if node.errors() or node.warnings():
            raise RuntimeError('Roof-reservation VEX diagnostics: ' + repr((node.errors(), node.warnings())))
        return {'status': 'patched', 'save': False, 'node': node.path(),
                'before_sha256': expected, 'sha256': digest(desired)}
    except Exception:
        parm.set(original)
        node.cook(force=True)
        raise


def revise_floor_scope(asset, save=False, hou_module=None):
    """Repair real material layer ownership after the fresh HAPI/Bake counterexample."""
    if hou_module is None:
        import hou
    else:
        hou=hou_module
    if save or asset.path()!='/obj/StreetBuilding_DEV':
        raise RuntimeError('Unexpected floor-scope target or persistence request')
    core=asset.node('StreetBuildingCore')
    planner=core.node('PLAN_CONTINUOUS_ATTACHMENTS');guard=core.node('VALIDATE_DIRECT_DETAIL_INSTANCES')
    old_plan=planner.evalParm('snippet');old_guard=guard.evalParm('snippet')
    desired_plan='// '+MARKER+'\n'+COMMON+CONTINUOUS
    needle='string allowed=sb_layer_catalog(chs("../../unity_style_catalog"),face==4?4:floor==0?1:2,facade);'
    replacement='int attachment_subtype=point(0,"attachment_subtype",point);\n    int material_band=(face==4 || (role=="FireEscape" && attachment_subtype==7) || (role=="DrainPipe" && attachment_subtype==9))?4:floor==0?1:2;\n    string allowed=sb_layer_catalog(chs("../../unity_style_catalog"),material_band,facade);'
    if old_plan==desired_plan and replacement in old_guard:
        return {'status':'unchanged','save':False}
    expected={planner:'41e088656dc16d403dbb716aaa603a2890c780193748b052080c936cf5ef877a',guard:'8a00db3c680e546d73d40abfa84015440af387a1bce0e183de704cb3620ff63b'}
    for node,source in ((planner,old_plan),(guard,old_guard)):
        if hashlib.sha256(source.encode()).hexdigest()!=expected[node]:
            raise RuntimeError('Live floor-scope precondition changed: '+node.path())
    if old_guard.count(needle)!=1:
        raise RuntimeError('Exact material-band guard marker is missing')
    try:
        planner.parm('snippet').set(desired_plan);guard.parm('snippet').set(old_guard.replace(needle,replacement))
        for node in (planner,guard):
            node.cook(force=True)
            if node.errors() or node.warnings():raise RuntimeError('Floor-scope VEX diagnostics: '+repr((node.path(),node.errors(),node.warnings())))
        return {'status':'patched','save':False,'nodes':[planner.path(),guard.path()]}
    except Exception:
        planner.parm('snippet').set(old_plan);guard.parm('snippet').set(old_guard)
        raise


def add_metadata_projection(asset, save=False, hou_module=None):
    """Keep final point counts, but strip attachment-only point schema from the metadata merge branch."""
    if hou_module is None:
        import hou
    else:
        hou=hou_module
    if save or asset.path()!='/obj/StreetBuilding_DEV':
        raise RuntimeError('Unexpected metadata projection target or persistence request')
    core=asset.node('StreetBuildingCore');name='PROJECT_REFERENCE_METADATA_INPUT'
    merge=core.node('METADATA_ATTACHMENT_INPUTS');diag=core.node('ATTACHMENT_DIAGNOSTICS')
    existing=core.node(name)
    snippet='''// STREETBUILDING_REFERENCE_METADATA_SCHEMA_20261025
// 元数据仍使用最终真实附件点计数；连接/占地属性只保留在正式附件输出。
// 此支路删除新增 point 属性，避免向原有 merge 引入新的属性不匹配警告。
if(!(chi("../../roof_props_layout_mode")==1 || chi("../../fire_escape_layout_mode")==1 || chi("../../drainpipe_enabled")))return;
string metadata_only_drop[]=array("attachment_group_id","attachment_part_index","attachment_subtype","connection_start","connection_end","attachment_bounds_min","attachment_bounds_max");
foreach(string attribute;metadata_only_drop)removeattrib(0,"point",attribute);
'''
    if existing is not None:
        if existing.evalParm('snippet')!=snippet or existing.input(0)!=diag or merge.input(1)!=existing:
            raise RuntimeError('Existing metadata projection differs from this repair')
        return {'status':'unchanged','save':False}
    if merge.input(1)!=diag:raise RuntimeError('Metadata projection input precondition changed')
    box=core.findNetworkBox('70_UNITY_CONTRACT');position=box.position();size=box.size()
    node=None
    try:
        node=core.createNode('attribwrangle',name);node.setParms({'class':'detail','snippet':snippet})
        node.setInput(0,diag);node.setPosition(merge.position()+hou.Vector2(-3,-1.5))
        node.setComment('元数据投影：保留最终附件点与 detail 诊断，仅移除附件专用连接属性；不改正式实例输出。')
        node.setGenericFlag(hou.nodeFlag.DisplayComment,True);box.addItem(node);box.setPosition(position);box.setSize(size)
        merge.setInput(1,node);node.cook(force=True)
        if node.errors() or node.warnings():raise RuntimeError('Metadata projection diagnostics: '+repr((node.errors(),node.warnings())))
        return {'status':'patched','save':False,'node':node.path()}
    except Exception:
        merge.setInput(1,diag)
        if node is not None:node.destroy()
        box.setPosition(position);box.setSize(size)
        raise


def normalize_reference_folder(asset, save=False, hou_module=None):
    """Normalize only the approved new folder after definition rollback; retain every parameter value."""
    if hou_module is None:
        import hou
    else:
        hou=hou_module
    if save or asset.path()!='/obj/StreetBuilding_DEV':raise RuntimeError('Unexpected interface normalization target')
    group=asset.parmTemplateGroup();template=group.find('sb_reference_attachments2')
    if template is None and group.find('sb_reference_attachments') is not None:return {'status':'unchanged','save':False}
    if template is None or group.find('sb_reference_attachments') is not None:raise RuntimeError('Unexpected reference folder structure')
    from streetbuilding_attachment_interface import FIELDS
    if tuple(p.name() for p in template.parmTemplates())!=FIELDS:raise RuntimeError('Reference folder contents changed')
    values={p.name():p.rawValue() for p in asset.parms()}
    original=asset.parmTemplateGroup()
    try:
        template.setName('sb_reference_attachments');group.replace('sb_reference_attachments2',template);asset.setParmTemplateGroup(group)
        for name,value in values.items():
            p=asset.parm(name)
            if p is not None and p.rawValue()!=value:raise RuntimeError('Interface normalization changed instance parameter: '+name)
        return {'status':'normalized','save':False,'folder':'sb_reference_attachments','parameter_values_preserved':True}
    except Exception:
        asset.setParmTemplateGroup(original)
        raise


def repair_reference_parameter_types(asset, save=False, hou_module=None):
    """Restore approved integer/menu/toggle templates after old-definition rollback synthesized float spares."""
    if hou_module is None:
        import hou
    else:
        hou=hou_module
    if save or asset.path()!='/obj/StreetBuilding_DEV':raise RuntimeError('Unexpected reference type repair target')
    from streetbuilding_attachment_interface import FIELDS
    original=asset.parmTemplateGroup();folder=original.find('sb_reference_attachments')
    if folder is None or tuple(p.name() for p in folder.parmTemplates())!=FIELDS:
        raise RuntimeError('Reference type repair folder precondition changed')
    before={p.name():p.rawValue() for p in asset.parms()}
    values={name:asset.evalParm(name) for name in FIELDS}
    if any(float(value)!=int(value) for value in values.values()):raise RuntimeError('Non-integer reference request cannot be migrated silently')
    expected_float=all(original.find(name).type()==hou.parmTemplateType.Float for name in FIELDS)
    if not expected_float:raise RuntimeError('Reference type repair only accepts the diagnosed float-placeholder state')
    try:
        group=asset.parmTemplateGroup();group.remove('sb_reference_attachments')
        group=_interface(hou,asset,group);asset.setParmTemplateGroup(group)
        for name,value in values.items():asset.parm(name).set(int(value))
        after=asset.parmTemplateGroup()
        for name in FIELDS:
            template=after.find(name)
            expected=hou.parmTemplateType.Menu if name in ('roof_props_layout_mode','fire_escape_layout_mode') else hou.parmTemplateType.Toggle if name in ('fire_escape_roof_access','drainpipe_enabled') else hou.parmTemplateType.Int
            if template.type()!=expected or template.isHidden():raise RuntimeError('Reference type repair failed: '+name)
        for name,value in before.items():
            p=asset.parm(name)
            if name not in FIELDS and p is not None and p.rawValue()!=value:raise RuntimeError('Unrelated instance value changed: '+name)
        return {'status':'repaired','save':False,'field_count':len(FIELDS),'instance_values_preserved':True}
    except Exception:
        asset.setParmTemplateGroup(original)
        for name,value in before.items():
            p=asset.parm(name)
            if p is not None:p.set(value)
        raise
