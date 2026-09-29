"""One-time, hash-guarded Live migration. Never saves HDA/HIP definitions."""
import hashlib

EXPECTED_SHA256 = 'e9caa1573d450586ba33af29d709d3afc41c99006a95fade5c6de6cf9d974b0c'
MARKER = '// STREETBUILDING_TRIM_ENDPOINTS_20260928'
OLD = '''    if (detail(0,sprintf("layer_trim_%d",floor==0?0:1),0) && target==0 && point(0,"run_local_cell",source)==0)
    {
        string column=sbv9_choose_height(catalog,"FacadeColumn",key+17,
            floor==0?ground_h:typical_h);
        if (len(column)==0) { int cs; column=sb_choose_variant(catalog,"FacadeColumn",key+17,1,cs); }
        sbv9_emit_selected(catalog,"FacadeColumn",column,origin,right,outward,0,
            floor==0?0:ground_h+(floor-1)*typical_h,yaw,face,surface,floor,-1,key+17,
            0,0,target,"column",0,0);
    }
'''
ANCHOR = '// 腰线单独按原始格分配，不随跨格窗户吞格；缺资源仍可预览。'
NEW = '''// STREETBUILDING_TRIM_ENDPOINTS_20260928
// 性能关键点：独立遍历原始格，每条正立面墙段每层只发射两端；不依赖门窗吞格。
// 扩展点：次正立面遵守自身素材立面掩码；缺素材保留两端预览槽，不改写实例数量参数。
for(int source=0;source<original;source++) {
    int target=point(0,"facade_target",source), floor=point(0,"floor_index",source);
    if(target>1 || point(0,"run_local_cell",source)!=0 ||
        !int(detail(0,sprintf("layer_trim_%d",floor==0?0:1),0))) continue;
    int residential=chi("../../ground_rule_schema_version")>=2 && floor==0 &&
        int(detail(0,"effective_ground_use",0))==1;
    string catalog=sb_layer_catalog(raw,floor==0 && !residential?1:2,int(pow(2,target)));
    int cell=point(0,"cell_index",source), face=point(0,"face_index",source);
    int key=seed*1009+building_id*8191+target*503+min(floor,1)*101+cell*37+17;
    string column=sbv9_choose_height(catalog,"FacadeColumn",key,floor==0?ground_h:typical_h);
    if(len(column)==0) {int cs; column=sb_choose_variant(catalog,"FacadeColumn",key,1,cs);}
    float run_width=int(point(0,"run_cell_count",source))*cell_width;
    for(int end=0;end<2;end++) {
        // 保留原主立面起点 C-1；其他端点使用互不冲突的负编号，避免与墙模块重名。
        int endpoint_cell=-(target*2+end+1);
        sbv9_emit_selected(catalog,"FacadeColumn",column,
            vector(point(0,"placement_origin",source)),vector(point(0,"placement_right",source)),
            vector(point(0,"placement_outward",source)),end*run_width,
            floor==0?0:ground_h+(floor-1)*typical_h,float(point(0,"placement_yaw",source)),
            face,string(point(0,"surface_role",source)),floor,endpoint_cell,key,
            0,0,target,"column",0,0);
    }
}
'''


def apply(asset, save=False):
    if save:
        raise RuntimeError('Use VerifyFull persistence gate; migration only supports save=False')
    node = asset.node('StreetBuildingCore/SELECT_FACADE_VARIANTS')
    parm = node.parm('snippet')
    original = parm.eval()
    if MARKER in original:
        return {'changed': False, 'idempotent': True}
    if hashlib.sha256(original.encode('utf-8')).hexdigest() != EXPECTED_SHA256:
        raise RuntimeError('Current Live snippet differs from the inspected baseline')
    if original.count(OLD) != 1 or original.count(ANCHOR) != 1:
        raise RuntimeError('Expected trim anchors are not unique')
    replacement = original.replace(OLD, '').replace(ANCHOR, NEW + ANCHOR)
    try:
        parm.set(replacement)
        node.cook(force=True)
        if node.errors() or node.warnings():
            raise RuntimeError(str((node.errors(), node.warnings())))
    except Exception:
        parm.set(original)
        node.cook(force=True)
        raise
    return {'changed': True, 'node': node.path(),
            'sha256': hashlib.sha256(replacement.encode('utf-8')).hexdigest()}
