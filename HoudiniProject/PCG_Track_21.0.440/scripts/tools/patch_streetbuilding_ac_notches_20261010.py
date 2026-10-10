"""Incremental Live patch. No production saves; precondition hash + rollback."""
import hashlib

BEFORE_SHA256 = 'cc6204b2d877dc4aab9767d9230db23b0c4e3a1c137b904ec6648ae67a855ec0'
MARKER = 'STREETBUILDING_AC_NOTCH_HOSTS_20261010'
GUARD_SHA256 = 'c485b2982fe83541d45372ddb676ad967a8f1c7bf4b82418b449693087e62163'
GUARD_MARKER = 'STREETBUILDING_AC_NOTCH_GUARD_20261010'
NAME_MARKER = 'STREETBUILDING_AC_NOTCH_NAMES_20261010'
NAME_CODE = '''        // STREETBUILDING_AC_NOTCH_NAMES_20261010
        // 同方向分段的局部 cell 可相同；实例名称加入墙段语义防止重名。
        if(role=="ACUnit" && (surface=="notch_inner" || surface=="notch_rear"))
            prefix+="_"+surface;
'''
GUARD_CODE = r'''
        // STREETBUILDING_AC_NOTCH_GUARD_20261010
        // 使用最终实墙平面校验凹入面；绝不放宽为包围盒内任意位置。
        if(surface=="notch_inner" || surface=="notch_rear") {
            plane_error=1e10;
            string hosts="op:../SELECT_FACADE_MODULES";
            for(int h=0;h<npoints(hosts);h++) {
                if(int(point(hosts,"building_id",h))!=int(point(0,"building_id",point))
                    || int(point(hosts,"face_index",h))!=face || int(point(hosts,"floor_index",h))!=floor
                    || string(point(hosts,"surface_role",h))!=surface) continue;
                string host_role=point(hosts,"module_role",h);
                if((host_role!="MiddleBlank" && host_role!="SideWall" && host_role!="RearWall")
                    || int(point(hosts,"preview_missing",h)) || len(string(point(hosts,"unity_instance",h)))==0) continue;
                vector tangent=point(hosts,"arrangement_right",h); tangent.x=-tangent.x;
                if(abs(length2(tangent)-1)>.001) continue;
                vector delta=p-vector(point(hosts,"P",h)); delta.y=0;
                plane_error=min(plane_error,length(delta-tangent*dot(delta,tangent)));
            }
        }
'''
NOTCH_CODE = r'''
// STREETBUILDING_AC_NOTCH_HOSTS_20261010
// 性能关键点：仅 Cook 时扫描最终墙窗一次，建立每个真实墙段的格位字典。
// 扩展点：新增可承载的凹入面，在 surface 白名单登记；不猜测外包围盒。
// 外侧面先完成旧抽样，再处理凹入面，共享同一个外机上限与 64 配件预算。
string ac_runs[]; vector ac_origins[], ac_rights[]; string ac_surfaces[];
int ac_faces[], ac_cells[]; dict notch_solid, notch_blocked;
for(int host=0;host<npoints(2);host++)
{
    int building=point(2,"building_id",host), face=point(2,"face_index",host);
    int floor=point(2,"floor_index",host), target=point(2,"facade_target",host);
    string surface=point(2,"surface_role",host);
    if(building!=0 || floor<1 || floor>=floors || face<1 || face>3 || target<2
        || (surface!="notch_inner" && surface!="notch_rear")) continue;
    string role=point(2,"module_role",host);
    int wall=role=="MiddleBlank" || role=="SideWall" || role=="RearWall";
    int hole=role=="MiddleWindow" || role=="GroundShop"
        || role=="GroundShopDoor" || role=="Entrance";
    int valid=wall && !int(point(2,"preview_missing",host))
        && len(string(point(2,"unity_instance",host)))>0;
    if(!valid && !hole) continue;
    vector origin=point(2,"arrangement_origin",host), right=point(2,"arrangement_right",host);
    if(abs(length2(right)-1)>.001) continue;
    vector pos=point(2,"P",host); pos.x=-pos.x; pos.y=0;
    vector delta=pos-origin; delta.y=0;
    float u=dot(delta,right);
    if(length(delta-right*u)>.001) continue; // 仍严格检查实际宿主平面。
    int span=max(1,int(point(2,"module_span",host)));
    float start=u/cw-span*.5; int first=int(rint(start));
    if(first<0 || abs(start-first)>.001) continue;
    string run_key=sprintf("%d/%s/%g/%g/%g/%g",face,surface,origin.x,origin.z,right.x,right.z);
    int run=find(ac_runs,run_key);
    if(run<0) {
        run=len(ac_runs); append(ac_runs,run_key); append(ac_origins,origin);
        append(ac_rights,right); append(ac_surfaces,surface); append(ac_faces,face); append(ac_cells,0);
    }
    ac_cells[run]=max(ac_cells[run],first+span);
    for(int cell=first;cell<first+span;cell++) {
        string key=sprintf("%s/%d/%d",run_key,floor,cell);
        if(valid) notch_solid[key]=1;
        if(hole) notch_blocked[key]=1;
    }
}
for(int segment=0;segment<len(ac_runs) && emitted<64 && count[3]<sb_maximum(1,3);segment++)
{
    int face=ac_faces[segment], cells=ac_cells[segment];
    if((face==3 && rear_mode==0) || !(sb_mask(1,3)&(face==3?8:4))) continue;
    vector origin=ac_origins[segment], right=ac_rights[segment];
    vector outward=face==1?set(-1,0,0):face==2?set(1,0,0):set(0,0,-1);
    float yaw=face==1?90:face==2?-90:-180;
    // 真实墙段进入种子；同方向两段绝不共用占位或跨段合并连续墙。
    int segment_seed=int(rint(origin.x/cw))*197+int(rint(origin.z/cw))*263+7919;
    for(int floor=1;floor<floors && emitted<64 && count[3]<sb_maximum(1,3);floor++) {
        if(!sb_allowed(1,3,floor+1)) continue;
        for(int cell=0;cell<cells && emitted<64 && count[3]<sb_maximum(1,3);cell++) {
            int run=0;
            for(int c=cell;c<cells;c++) {
                string k=sprintf("%s/%d/%d",ac_runs[segment],floor,c);
                if(!isvalidindex(notch_solid,k) || isvalidindex(notch_blocked,k)) break;
                run++;
            }
            if(run<=0) continue;
            sb_diag_add(1,3,"hosts",1);
            int key=seed*1009+face*503+floor*101+cell*37+segment_seed;
            if(rand(float(key)*.149+11)>=sb_density(1,3)) continue;
            int span;
            int added=sb_ac_emit(detail(0,"catalog_raw",0),key+3509,run,cw,origin,right,outward,
                ground_h+.65+(floor-1)*typical_h,yaw,face,ac_surfaces[segment],floor,cell,
                min(64-emitted,sb_maximum(1,3)-count[3]),span);
            emitted+=added; count[3]+=added;
            if(added>0) cell+=span-1;
        }
    }
}

'''

def apply_loaded(asset, save=False):
    if save:
        raise RuntimeError('Save only through VerifyFull regression gate')
    node=asset.node('StreetBuildingCore/DETAIL_INSTANCE_POINTS')
    guard=asset.node('StreetBuildingCore/VALIDATE_DIRECT_DETAIL_INSTANCES')
    old=node.evalParm('snippet')
    old_guard=guard.evalParm('snippet')
    if MARKER in old and GUARD_MARKER in old_guard and NAME_MARKER in old:
        return {'status':'UNCHANGED'}
    baseline=old.replace(NOTCH_CODE,'').replace(NAME_CODE,'')
    if hashlib.sha256(baseline.encode()).hexdigest()!=BEFORE_SHA256:
        raise RuntimeError('Current Live VEX differs from captured precondition')
    if GUARD_MARKER not in old_guard and hashlib.sha256(old_guard.encode()).hexdigest()!=GUARD_SHA256:
        raise RuntimeError('Current Live guard differs from captured precondition')
    anchor='// Roof props stay one cell away from the edge and outside either L-notch.'
    guard_anchor='        if (plane_error > .001)'
    name_anchor='        setpointattrib(0, "orient", pt, orient, "set");'
    if old.count(anchor)!=1 or old_guard.count(guard_anchor)!=1:
        raise RuntimeError('Expected one exact insertion point')
    try:
        if MARKER not in old: node.parm('snippet').set(old.replace(anchor,NOTCH_CODE+anchor))
        current=node.evalParm('snippet')
        if NAME_MARKER not in current:
            if current.count(name_anchor)!=1: raise RuntimeError('Expected one exact name insertion point')
            node.parm('snippet').set(current.replace(name_anchor,NAME_CODE+name_anchor))
        if GUARD_MARKER not in old_guard: guard.parm('snippet').set(old_guard.replace(guard_anchor,GUARD_CODE+guard_anchor))
        for changed in (node,guard):
            changed.cook(force=True)
            if changed.errors() or changed.warnings():
                raise RuntimeError(str((changed.errors(),changed.warnings())))
    except Exception:
        node.parm('snippet').set(old)
        guard.parm('snippet').set(old_guard)
        node.cook(force=True)
        raise
    return {'status':'APPLIED','saved':False,'node':node.path()}
