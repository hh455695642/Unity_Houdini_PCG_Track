"""Incremental Live-only patch; persistence belongs to VerifyFull."""
import hashlib
EXPECTED_SHA256 = '793bf0bc74790a0add9a0b3a35804f7103049de979de86711485cb7b8b3b70cf'
OLD = '''    if (floor==0 && detail(0,sprintf("layer_trim_%d",floor==0?0:1),0))
    {
        int cs; string cornice=sb_choose_variant(catalog,"Cornice",key+7,1,cs);
        sbv9_emit_selected(catalog,"Cornice",cornice,origin,right,outward,u,(floor==0?ground_h:ground_h+floor*typical_h)-1,yaw,
            face,surface,floor,cell,key+7,0,0,target,"cornice",0,0);
    }
'''
NEW = '''    // STREETBUILDING_SINGLE_GROUND_TRIM_20260929
    // 当前无商业基座/裙房层：首层仅保留下方独立循环生成的层间 FloorBand。
    // 性能关键点：不发射额外 Cornice 实例或缺失预览，避免重复线脚与 overdraw。
    // 扩展点：未来裙房由显式实例层规则控制；屋顶檐口仍由屋顶边缘节点负责。
'''

def apply(asset, save=False):
    if save: raise ValueError('Use VerifyFull for definition/HIP persistence')
    parm = asset.node('StreetBuildingCore/SELECT_FACADE_VARIANTS').parm('snippet')
    before = parm.eval()
    if NEW in before and OLD not in before: return {'changed':False,'idempotent':True}
    if hashlib.sha256(before.encode('utf-8')).hexdigest()!=EXPECTED_SHA256 or before.count(OLD)!=1:
        raise RuntimeError('Live snippet differs from the captured baseline')
    names=('MERGE_DIRECT_BUILDING_INSTANCES','OUT_BUILDING_LOD0','OUT_BUILDING_PREVIEW')
    baseline_warnings={}
    for name in names:
        node=asset.node('StreetBuildingCore/'+name)
        node.cook(force=True)
        if node.errors(): raise RuntimeError('Baseline cook error: '+name)
        baseline_warnings[name]=node.warnings()
    try:
        if asset.matchesCurrentDefinition(): asset.allowEditingOfContents()
        parm.set(before.replace(OLD,NEW,1))
        for name in names:
            node=asset.node('StreetBuildingCore/'+name)
            node.cook(force=True)
            if node.errors() or node.warnings()!=baseline_warnings[name]:
                raise RuntimeError(name+': '+str(node.errors()+node.warnings()))
    except Exception:
        parm.set(before)
        raise
    return {'changed':True,'saved':False,'removed':'ground Cornice only','unchanged_baseline_warnings':baseline_warnings}
