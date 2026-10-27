"""Incremental pipe routing patch. Current Live snippets are the precondition.

Does not load a HIP, touch Unity, or save a definition. The caller owns Capture,
Cook/contract verification, saving and rollback. All geometry units are metres.
"""
from __future__ import annotations
import hashlib
import json
from pathlib import Path

MARKER = "STREETBUILDING_PIPE_ROUTE_20261026_V2"
EVIDENCE = Path(__file__).resolve().parents[2] / ".codex_tmp/regression/streetbuilding-placement-20261026/evidence/current-streetbuilding-live.json"

HELPERS = r'''
// STREETBUILDING_PIPE_ROUTE_20261026_V2
// P元数据只描述素材端点／半径／合法直段长度，不包含生成配额。
int rp_spec(string path; export vector a; export vector b; export float radius;
    export float minimum; export float maximum) {
    foreach(string row;split(rr_raw(),"\n")) {
        string f[]=split(row,"|");
        if(len(f)==12 && f[0]=="P" && f[1]=="1" && f[2]==path) {
            a=set(atof(f[3]),atof(f[4]),atof(f[5]));b=set(atof(f[6]),atof(f[7]),atof(f[8]));
            radius=atof(f[9]);minimum=atof(f[10]);maximum=atof(f[11]);return 1;
        }
    }
    return 0;
}
void rp_bounds(string path;vector position;vector right;vector outward;vector scale;
    export vector lo;export vector hi) {
    string f[]=split(rr_row(path),"|");lo=set(1e10,1e10,1e10);hi=-lo;
    if(len(f)!=18)return;
    vector minimum=set(atof(f[15]),atof(f[16]),atof(f[17])),size=set(atof(f[12]),atof(f[13]),atof(f[14]));
    for(int x=0;x<2;x++)for(int y=0;y<2;y++)for(int z=0;z<2;z++) {
        vector v=(minimum+size*set(x,y,z))*scale;
        vector p=position+right*v.x+set(0,v.y,0)+outward*v.z;lo=min(lo,p);hi=max(hi,p);
    }
}
// The frame is a module pivot, not necessarily the supporting outer wall face.
// Query actual selected wall envelopes in this corridor before applying the 10cm centre distance.
int rp_surface(vector frame;vector right;vector outward;float radius;export float surface) {
    string geometry="op:../MERGE_DIRECT_BUILDING_INSTANCES";int found=0;surface=-1e10;
    for(int p=0;p<npoints(geometry);p++) {
        string role=point(geometry,"module_role",p);
        if(role!="GroundWall" && role!="GroundShop" && role!="GroundShopDoor" && role!="Entrance"
            && role!="MiddleWindow" && role!="MiddleBlank" && role!="SideWall" && role!="RearWall")continue;
        string path=point(geometry,"unity_instance",p);if(len(rr_row(path))==0)continue;
        vector pos=point(geometry,"P",p);pos.x=-pos.x;
        vector4 hq=point(geometry,"orient",p),uq=set(hq.x,-hq.y,-hq.z,hq.w);
        vector pr=qrotate(uq,set(1,0,0)),po=qrotate(uq,set(0,0,1));
        if(dot(po,outward)<.999)continue;
        vector sc=point(geometry,"scale",p);if(length2(sc)<.001)sc=1;
        vector lo,hi;rp_bounds(path,pos,pr,po,sc,lo,hi);
        float umin=1e10,umax=-1e10,zmin=1e10,zmax=-1e10;
        for(int x=0;x<2;x++)for(int z=0;z<2;z++) {
            vector delta=set(x?hi.x:lo.x,0,z?hi.z:lo.z)-frame;
            float u=dot(delta,right),d=dot(delta,outward);
            umin=min(umin,u);umax=max(umax,u);zmin=min(zmin,d);zmax=max(zmax,d);
        }
        if(umin>radius || umax<-radius || zmin>.75 || zmax<-.25)continue;
        surface=max(surface,zmax);found=1;
    }
    return found;
}
// 从真实已选主体模块读局部障碍。只在选中走廊上绕腰线／檐口；不做全局寻路。
int rp_obstacles(vector wall;vector right;vector outward;float radius;float roof;
    export float lows[];export float highs[];export int levels[]) {
    string geometry="op:../MERGE_DIRECT_BUILDING_INSTANCES";
    for(int p=0;p<npoints(geometry);p++) {
        string role=point(geometry,"module_role",p);
        if(role!="Cornice" && role!="FloorBand" && role!="FloorBandCorner" && role!="Parapet"
            && role!="ParapetCorner" && role!="ParapetConcaveCorner" && role!="FacadeColumn")continue;
        string path=point(geometry,"unity_instance",p);if(len(rr_row(path))==0)continue;
        vector position=point(geometry,"P",p);position.x=-position.x;
        vector4 hq=point(geometry,"orient",p),uq=set(hq.x,-hq.y,-hq.z,hq.w);
        vector pr=qrotate(uq,set(1,0,0)),po=qrotate(uq,set(0,0,1));
        vector sc=point(geometry,"scale",p);if(length2(sc)<.001)sc=1;
        vector lo,hi;rp_bounds(path,position,pr,po,sc,lo,hi);
        float umin=1e10,umax=-1e10,zmin=1e10,zmax=-1e10;
        for(int x=0;x<2;x++)for(int z=0;z<2;z++) {
            vector delta=set(x?hi.x:lo.x,0,z?hi.z:lo.z)-wall;
            float u=dot(delta,right),d=dot(delta,outward);
            umin=min(umin,u);umax=max(umax,u);zmin=min(zmin,d);zmax=max(zmax,d);
        }
        if(umin>radius+.015 || umax<-radius-.015 || zmin>.75 || zmax<-.02 || lo.y>roof+.01 || hi.y<.4)continue;
        if(zmax+radius+.025<=.10)continue;
        // Full-height columns are corridor blockers, not a reason to move the whole pipe away.
        if(role=="FacadeColumn" && hi.y-lo.y>1.5)return 0;
        // Roof terminal hopper reaches 14cm inward from the trunk socket.
        // Keep the terminal clear as well as the 5cm-radius tube itself.
        float inward=hi.y>=roof-.01?max(radius,.14):radius;
        int level=max(1,int(ceil((zmax+inward+.025-.10)/.40)));
        if(level>2)return 0;
        append(lows,max(.4,lo.y-.10));append(highs,min(roof,hi.y+.10));append(levels,level);
    }
    int order[]=argsort(lows);float sl[],sh[];int sn[];
    foreach(int index;order) {
        float l=lows[index],h=highs[index];int n=levels[index];
        if(h<l)continue;
        if(len(sl)>0 && l-n*.5 <= sh[-1]+sn[-1]*.5+.05) {
            sh[-1]=max(sh[-1],h);sn[-1]=max(sn[-1],n);
        } else {append(sl,l);append(sh,h);append(sn,n);}
    }
    lows=sl;highs=sh;levels=sn;return 1;
}
int rp_straight(string path;vector wall;vector right;vector outward;float y0;float y1;float centre;
    int face;string surface;int floor;int group;export int part;float minimum;float maximum;
    export vector route_lo;export vector route_hi) {
    float distance=y1-y0;if(distance<.0001)return 1;
    int count=max(1,int(ceil(distance/maximum)));float segment=distance/count;
    if(segment<minimum-.0001)return 0;
    for(int i=0;i<count;i++) {
        vector start=wall+set(0,y0+i*segment,0)+outward*centre,end=start+set(0,segment,0);
        vector pos=start-outward*.10;
        int p=rr_emit(path,"DrainPipe",8,pos,right,outward,face,surface,floor,group,part++,start,end);
        vector scale=set(1,segment,1),lo,hi;setpointattrib(0,"scale",p,scale,"set");
        rp_bounds(path,pos,right,outward,scale,lo,hi);
        setpointattrib(0,"attachment_bounds_min",p,lo,"set");setpointattrib(0,"attachment_bounds_max",p,hi,"set");
        setpointattrib(0,"pipe_wall_origin",p,wall,"set");setpointattrib(0,"pipe_wall_outward",p,outward,"set");
        setpointattrib(0,"pipe_route_schema",p,1,"set");
        route_lo=min(route_lo,lo);route_hi=max(route_hi,hi);
    }
    return 1;
}
int rp_offset(string path;vector wall;vector right;vector outward;float y;float centre;int direction;
    int face;string surface;int floor;int group;export int part;export vector route_lo;export vector route_hi) {
    vector rout=outward*direction,rright=right*direction;
    vector start=wall+set(0,y,0)+outward*centre,end=start+set(0,.5,0)+outward*(direction*.40);
    vector pos=start-rout*.10;
    int p=rr_emit(path,"DrainPipe",12,pos,rright,rout,face,surface,floor,group,part++,start,end);
    vector lo,hi;rr_bounds(path,pos,rright,rout,lo,hi);
    setpointattrib(0,"pipe_wall_origin",p,wall,"set");setpointattrib(0,"pipe_wall_outward",p,outward,"set");
    setpointattrib(0,"pipe_route_schema",p,1,"set");
    route_lo=min(route_lo,lo);route_hi=max(route_hi,hi);return p;
}
'''

NEW_BRANCH = r'''
    // Explicit P pipe geometry takes the near-wall route; old catalogs retain their historical .55 path.
    vector pipe_a,pipe_b;float radius,min_length,max_length;
    if(rp_spec(straight,pipe_a,pipe_b,radius,min_length,max_length)) {
        if(distance(pipe_a,set(0,0,.10))>.001 || distance(pipe_b,set(0,1,.10))>.001
            || abs(radius-.05)>.001 || min_length<.05 || max_length>1.001 || min_length>max_length) {
            dreason="connection_spec";continue;
        }
        string offset=rr_pick(12,2,mask,214+r);
        vector oa,ob,ta,tb,ba,bb;float rad0,mn0,mx0,rad1,mn1,mx1,rad2,mn2,mx2;
        if(!rp_spec(top,ta,tb,rad0,mn0,mx0) || !rp_spec(bottom,ba,bb,rad1,mn1,mx1)) {dreason="connection_spec";continue;}
        for(int side=0;side<8 && dact<drequest;side++) {
            float edge=.16+.16*int(side/2),u=side%2==0?low+edge:high-edge;
            if(high-low<2*edge+.10)continue;
            vector frame=origin+right*u;float wall_surface;
            if(!rp_surface(frame,right,out,radius,wall_surface)){dreason="no_wall_host";continue;}
            vector wall=frame+out*wall_surface;float obstacle_lo[],obstacle_hi[];int obstacle_n[];
            if(!rp_obstacles(wall,right,out,radius,roof,obstacle_lo,obstacle_hi,obstacle_n))continue;
            if(len(obstacle_lo)>0 && (len(offset)==0 || !rp_spec(offset,oa,ob,rad2,mn2,mx2)
                || distance(oa,set(0,0,.10))>.001 || distance(ob,set(0,.5,.5))>.001)) {dreason="connection_spec";continue;}
            // Dry-run the finite route first. Group creation is atomic; no partial pipes on rejection.
            float y=.4,centre=.10;int need=2,valid=1;
            for(int i=0;i<len(obstacle_lo);i++) {
                float begin=obstacle_lo[i]-.5*obstacle_n[i];
                if(begin<y-.001){valid=0;break;}
                float gap=begin-y;if(gap>.0001 && gap<min_length){valid=0;break;}
                need+=int(ceil(max(0.0,gap)/max_length))+obstacle_n[i];
                float hold=max(0.0,min(roof,obstacle_hi[i])-(begin+.5*obstacle_n[i]));
                if(hold>.0001 && hold<min_length){valid=0;break;}
                need+=int(ceil(hold/max_length));
                y=min(roof,obstacle_hi[i]);centre=.10+.4*obstacle_n[i];
                if(y+.5*obstacle_n[i]<roof-.001){need+=obstacle_n[i];y+=.5*obstacle_n[i];centre=.10;}
            }
            float last=roof-y;if(last>.0001 && last<min_length)valid=0;
            need+=int(ceil(max(0.0,last)/max_length));
            if(!valid){dreason="routing_clearance";continue;}
            if(npoints(0)+need>64){dreason="budget";continue;}
            vector line_lo=set(1e10,1e10,1e10),line_hi=-line_lo;
            for(int x=0;x<2;x++)for(int z=0;z<2;z++)for(int yy=0;yy<2;yy++) {
                vector corner=wall+right*(x?radius:-radius)+out*(z?.95:.04)+set(0,yy?roof+.45:0,0);
                line_lo=min(line_lo,corner);line_hi=max(line_hi,corner);
            }
            int hit=0;for(int i=0;i<len(occupied_lo);i++)if(rr_overlap(line_lo,line_hi,occupied_lo[i],occupied_hi[i],.05))hit=1;
            if(hit)continue;
            int part=0;vector route_lo=set(1e10,1e10,1e10),route_hi=-route_lo;
            vector bottom_pos=wall+set(0,.4,0),start=bottom_pos+out*.10;
            int bottom_point=rr_emit(bottom,"DrainPipe",10,bottom_pos,right,out,face,surf,0,dact,part++,start,start);
            setpointattrib(0,"pipe_route_schema",bottom_point,1,"set");
            vector blo,bhi;rr_bounds(bottom,bottom_pos,right,out,blo,bhi);route_lo=min(route_lo,blo);route_hi=max(route_hi,bhi);
            y=.4;centre=.10;
            for(int i=0;i<len(obstacle_lo);i++) {
                int n=obstacle_n[i];float begin=obstacle_lo[i]-.5*n;
                rp_straight(straight,wall,right,out,y,begin,centre,face,surf,0,dact,part,min_length,max_length,route_lo,route_hi);
                y=begin;
                for(int j=0;j<n;j++){rp_offset(offset,wall,right,out,y,centre,1,face,surf,0,dact,part,route_lo,route_hi);y+=.5;centre+=.4;}
                float end=min(roof,obstacle_hi[i]);
                rp_straight(straight,wall,right,out,y,end,centre,face,surf,0,dact,part,min_length,max_length,route_lo,route_hi);y=end;
                if(y+.5*n<roof-.001)
                    for(int j=0;j<n;j++){rp_offset(offset,wall,right,out,y,centre,-1,face,surf,0,dact,part,route_lo,route_hi);y+=.5;centre-=.4;}
            }
            rp_straight(straight,wall,right,out,y,roof,centre,face,surf,0,dact,part,min_length,max_length,route_lo,route_hi);
            vector final=wall+set(0,roof,0)+out*(centre-.10),joint=final+out*.10;
            int top_point=rr_emit(top,"DrainPipe",9,final,right,out,face,surf,floors,dact,part++,joint,joint);
            setpointattrib(0,"pipe_route_schema",top_point,1,"set");
            vector tlo,thi;rr_bounds(top,final,right,out,tlo,thi);route_lo=min(route_lo,tlo);route_hi=max(route_hi,thi);
            append(occupied_lo,route_lo);append(occupied_hi,route_hi);dact++;
        }
        continue;
    }
'''

LEGACY_GUARD = '    // New near-wall geometry requires explicit P ports; do not place it using old .55 metadata.\n    string legacy_row[]=split(rr_row(straight),"|");\n    if(len(legacy_row)==18 && abs(atof(legacy_row[17])+atof(legacy_row[14])*.5-.55)>.025) {\n        dreason="connection_spec";continue;\n    }\n'

SCALE_VALIDATION = r'''
    vector reference_scale=point(0,"scale",p);
    int reference_subtype=point(0,"attachment_subtype",p);
    // Only explicitly authored clamp-free straight pipe may adapt its axial length.
    int axial_pipe=reference_subtype==8 && int(point(0,"pipe_route_schema",p))==1;
    if(axial_pipe) {
        if(abs(reference_scale.x-1)>.0001 || abs(reference_scale.z-1)>.0001
            || reference_scale.y<.05-.0001 || reference_scale.y>1.0001)
            error("Pipe straight length/diameter outside declared source range");
    } else if(distance(reference_scale,set(1,1,1))>.0001)error("Reference attachment scale must remain one");
'''


def sha(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()


def transform(snippets: dict[str, str]) -> dict[str, str]:
    """Return only the exact changed snippets, without mutating Houdini."""
    plan=snippets['PLAN_CONTINUOUS_ATTACHMENTS']
    if MARKER in plan:
        if 'New near-wall geometry requires explicit P ports' in plan:return {}
        if sha(plan)!='3d339cc6347cdab5f4c6387c11bbe9d8edd86944888810c1c1de095d294c3e8c':
            raise RuntimeError('Pipe V2 precondition differs before legacy geometry guard')
        anchor='    float length=rr_joint(straight);if(length<=0 || abs(roof/length-rint(roof/length))>.005){dreason="height_mismatch";continue;}'
        if plan.count(anchor)!=1:raise RuntimeError('Legacy guard anchor differs')
        return {'PLAN_CONTINUOUS_ATTACHMENTS':plan.replace(anchor,LEGACY_GUARD+'\n'+anchor,1)}
    if 'STREETBUILDING_PIPE_ROUTE_20261026_V1' in plan:
        expected=json.loads((EVIDENCE.parent/'pipe-v1-snippets.json').read_text(encoding='utf-8'))
        for name,value in snippets.items():
            if value!=expected[name]:raise RuntimeError('Pipe V1 postcondition differs: '+name)
        # Exact V1 -> V2 upgrade; preserve every independently authored earlier part.
        old_helper_start=plan.index('// STREETBUILDING_PIPE_ROUTE_20261026_V1')
        old_helper_end=plan.index('// 整组布局：消防梯优先，管线复用一个竖向走廊；失败整组拒绝。')
        plan=plan[:old_helper_start]+HELPERS+'\n'+plan[old_helper_end:]
        old='            vector wall=origin+right*u;float obstacle_lo[],obstacle_hi[];int obstacle_n[];'
        new='            vector frame=origin+right*u;float wall_surface;\n            if(!rp_surface(frame,right,out,radius,wall_surface)){dreason="no_wall_host";continue;}\n            vector wall=frame+out*wall_surface;float obstacle_lo[],obstacle_hi[];int obstacle_n[];'
        if plan.count(old)!=1:raise RuntimeError('V1 pipe surface anchor differs')
        plan=plan.replace(old,new,1)
        plan=plan.replace('    float length=rr_joint(straight);if(length<=0 || abs(roof/length-rint(roof/length))>.005){dreason="height_mismatch";continue;}',LEGACY_GUARD+"\n"+'    float length=rr_joint(straight);if(length<=0 || abs(roof/length-rint(roof/length))>.005){dreason="height_mismatch";continue;}',1)
        return {'PLAN_CONTINUOUS_ATTACHMENTS':plan}
    baseline=json.loads(EVIDENCE.read_text(encoding='utf-8-sig'))['nodes']
    for name in ('PLAN_CONTINUOUS_ATTACHMENTS','ASSEMBLE_CONTINUOUS_ATTACHMENTS','VALIDATE_REFERENCE_ATTACHMENTS'):
        if sha(snippets[name])!=sha(baseline[name]['snippet']):
            raise RuntimeError('Pipe patch precondition differs from captured Live: '+name)
    anchor='// 整组布局：消防梯优先，管线复用一个竖向走廊；失败整组拒绝。'
    if plan.count(anchor)!=1:raise RuntimeError('Pipe helper anchor is not unique')
    plan=plan.replace(anchor,HELPERS+'\n'+anchor,1)
    anchor='    float length=rr_joint(straight);if(length<=0 || abs(roof/length-rint(roof/length))>.005){dreason="height_mismatch";continue;}'
    if plan.count(anchor)!=1:raise RuntimeError('Pipe branch anchor is not unique')
    plan=plan.replace(anchor,NEW_BRANCH+'\n'+LEGACY_GUARD+'\n'+anchor,1)
    assembly=snippets['ASSEMBLE_CONTINUOUS_ATTACHMENTS']
    assembly=assembly.replace('"attachment_part_index","attachment_subtype");','"attachment_part_index","attachment_subtype","pipe_route_schema");',1)
    assembly=assembly.replace('"attachment_bounds_min","attachment_bounds_max");','"attachment_bounds_min","attachment_bounds_max","pipe_wall_origin","pipe_wall_outward");',1)
    validation=snippets['VALIDATE_REFERENCE_ATTACHMENTS']
    anchor='    if(distance(vector(point(0,"scale",p)),set(1,1,1))>.0001)error("Reference attachment scale must remain one");'
    if validation.count(anchor)!=1:raise RuntimeError('Pipe validation anchor is not unique')
    validation=validation.replace(anchor,SCALE_VALIDATION,1)
    # Both offset orientations join the same sequence; validate every pipe segment.
    validation=validation.replace('if(st!=3 && st!=4 && st!=8)continue;','if(st!=3 && st!=4 && (st<8 || st>12))continue;',1)
    validation=validation.replace('(next!=3 && next!=4 && next!=8))continue;', '(next!=3 && next!=4 && (next<8 || next>12)))continue;',1)
    return {'PLAN_CONTINUOUS_ATTACHMENTS':plan,'ASSEMBLE_CONTINUOUS_ATTACHMENTS':assembly,'VALIDATE_REFERENCE_ATTACHMENTS':validation}


def patch(asset, save=False):
    if save:raise ValueError('Caller must verify and save the definition explicitly')
    core=asset.node('StreetBuildingCore')
    names=('PLAN_CONTINUOUS_ATTACHMENTS','ASSEMBLE_CONTINUOUS_ATTACHMENTS','VALIDATE_REFERENCE_ATTACHMENTS')
    old={name:core.node(name).parm('snippet').rawValue() for name in names}
    updates=transform(old)
    try:
        for name,value in updates.items():core.node(name).parm('snippet').set(value)
    except Exception:
        for name,value in old.items():core.node(name).parm('snippet').set(value)
        raise
    return {'marker':MARKER,'changed_nodes':list(updates),'saved':False,'sha256':{name:sha(value) for name,value in updates.items()}}


if __name__=='__main__':
    captured=json.loads(EVIDENCE.read_text(encoding='utf-8-sig'))['nodes']
    changes=transform({name:captured[name]['snippet'] for name in ('PLAN_CONTINUOUS_ATTACHMENTS','ASSEMBLE_CONTINUOUS_ATTACHMENTS','VALIDATE_REFERENCE_ATTACHMENTS')})
    print(json.dumps({'changed_nodes':list(changes),'sha256':{name:sha(value) for name,value in changes.items()}},indent=2))
