"""Incremental commercial host placement patch. No disk/definition save."""
import hashlib
MARKER='STREETBUILDING_COMMERCIAL_MOUNTS_20261026'
HELPERS=r'''
// STREETBUILDING_COMMERCIAL_MOUNTS_20261026
// 素材挂点是局部几何规格；缺少 A|1 时按真实 bounds 推导，不改变实例配额。
int sb_mount_geometry(string path; export vector lo; export vector hi; export vector mount; export int explicit_mount)
{
    int found=0; explicit_mount=0;lo=0;hi=0;mount=0;
    foreach(string row;split(detail(0,"catalog_raw",0),"\n")) {
        string f[]=split(row,"|");
        if(len(f)==18 && f[0]=="M" && f[4]==path) {
            lo=set(atof(f[15]),atof(f[16]),atof(f[17]));
            hi=lo+set(atof(f[12]),atof(f[13]),atof(f[14])); found=1;
        }
        if(len(f)==6 && f[0]=="A" && f[1]=="1" && f[2]==path) {
            mount=set(atof(f[3]),atof(f[4]),atof(f[5])); explicit_mount=1;
        }
    }
    if(!explicit_mount)mount=set(0,hi.y,hi.z);
    return found;
}
'''
OLD_CALL='''            ground_h-(kind==0?.56:.32),yaw,face,surface,0,cell,'''
NEW_CALL='''            host_mount.y,yaw,face,surface,0,cell,'''
OLD_HOST='''        int added=sbv9_emit_limited_host(host_catalog,kind==0?"Awning":"Sign",
            key+(kind==0?3101:3203),pos+outward*.22,right,outward,0,'''
NEW_HOST='''        vector host_lo,host_hi,host_mount; int host_explicit;
        if(!sb_mount_geometry(point(2,"unity_instance",host),host_lo,host_hi,host_mount,host_explicit)) continue;
        vector host_origin=pos+right*host_mount.x+outward*host_mount.z;
        int added=sbv9_emit_limited_host(host_catalog,kind==0?"Awning":"Sign",
            key+(kind==0?3101:3203),host_origin,right,outward,0,'''
OLD_EMIT='''        vector unity_p = origin + right * (local_u + offset.x)
            + set(0, base_y + offset.y, 0) + outward * offset.z;
        int pt = addpoint(0, set(-unity_p.x, unity_p.y, unity_p.z));'''
NEW_EMIT='''        vector placement_origin=origin; float placement_y=base_y;
        int mount_explicit=0; vector source_lo=0,source_hi=0,source_mount=0;
        if(len(host_id)>0 && (role=="Awning" || role=="Sign")) {
            if(!sb_mount_geometry(path,source_lo,source_hi,source_mount,mount_explicit))return 0;
            int horizontal=role=="Sign" && source_hi.x-source_lo.x>=source_hi.z-source_lo.z;
            if(!mount_explicit)source_mount=set(0,horizontal?source_lo.y:source_hi.y,source_lo.z);
            float target_y=base_y+(horizontal?.02:role=="Awning"?-.04:-.02);
            placement_y=target_y-source_mount.y;
            placement_origin-=right*source_mount.x+outward*source_mount.z;
            float available=host_width;
            if(source_hi.x-source_lo.x>available+.02 || placement_y+source_lo.y<2.35-.0001) {
                sb_diag_add(0,sb_diag_kind(role),source_hi.x-source_lo.x>available+.02?"width_rejected":"clearance_rejected",1);return 0;
            }
        }
        vector unity_p = placement_origin + right * (local_u + offset.x)
            + set(0, placement_y + offset.y, 0) + outward * offset.z;
        int pt = addpoint(0, set(-unity_p.x, unity_p.y, unity_p.z));'''
OLD_METADATA='''            setpointattrib(0,"attachment_host_span",pt,host_span,"set");'''
NEW_METADATA=OLD_METADATA+'''
            setpointattrib(0,"attachment_mount_source",pt,mount_explicit?"explicit":"bounds","set");
            setpointattrib(0,"attachment_min_y",pt,unity_p.y+source_lo.y,"set");
            setpointattrib(0,"attachment_max_y",pt,unity_p.y+source_hi.y,"set");'''
def build_snippet(current,expected_sha):
    if MARKER in current:return current
    assert hashlib.sha256(current.encode()).hexdigest()==expected_sha,'Commercial source changed before patch'
    marker='int sbv6_emit_host('
    assert current.count(marker)==1
    result=current.replace(marker,HELPERS+'\n'+marker,1)
    for old,new in [(OLD_EMIT,NEW_EMIT),(OLD_METADATA,NEW_METADATA),(OLD_HOST,NEW_HOST),(OLD_CALL,NEW_CALL)]:
        assert result.count(old)==1,('Expected one exact commercial block',old[:90],result.count(old))
        result=result.replace(old,new,1)
    substitutions=[
      ('string host_id; string host_role; int host_span)', 'string host_id; string host_role; int host_span; float host_width)'),
      ('base_y,yaw,face,surface,floor,cell,"","",0);','base_y,yaw,face,surface,floor,cell,"","",0,0);'),
      ('base_y,yaw,face,surface,floor,cell,host_id,host_role,host_span);','base_y,yaw,face,surface,floor,cell,host_id,host_role,host_span,host_width);'),
      ('host_id,host_role,int(point(2,"module_span",host)));','host_id,host_role,int(point(2,"module_span",host)),host_hi.x-host_lo.x);'),
    ]
    for old,new in substitutions:
        assert old in result,old
        result=result.replace(old,new)
    return result
