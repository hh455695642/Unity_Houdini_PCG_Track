"""Incremental Live patch; never persist before the cumulative VerifyFull gate."""
import hashlib

EXPECTED_SHA256='b0b83fa398b2a715c463a84be5e1f5b0641280b8cc2bac4f5d105a0aaac4000b'
OLD='''    // 屋顶大组中的檐口只沿顶部边缘生成；不复制到各建筑楼层。
    if(detail("op:../PARSE_GENERATION_RULES","layer_trim_2",0))
    {
        for(int cell=0;cell<cells;cell++) {
            int key=seed*1009+7001+serial_base+cell*37; int span;
            string variant=sb_choose_variant(catalog,"Cornice",key,1,span);
            sb_emit(catalog,"Cornice",variant,origin,right,outward,(cell+.5)*sb_notch_cw(),
                roof_y-1,yaw,4,"roof_edge",floors,serial_base+cell,key,0);
        }
    }
'''
NEW='''    // STREETBUILDING_NO_LOWER_ROOF_CORNICE_20260930
    // 屋顶仅保留顶部女儿墙/压边，不再在顶层窗户上方额外生成下移一米的檐口。
    // 性能关键点：直接省去 Cornice 实例与缺失素材预览，不通过隐藏网格增加负担。
    // 扩展点：未来独立屋檐由显式实例规则生成；女儿墙开关及转角逻辑保持独立。
'''

def apply(asset,save=False):
    if save: raise ValueError('Use VerifyFull for persistence')
    p=asset.node('StreetBuildingCore/BUILD_DIRECT_ROOF_EDGE_INSTANCES').parm('snippet')
    before=p.eval()
    if NEW in before and OLD not in before: return {'changed':False,'idempotent':True}
    if hashlib.sha256(before.encode('utf-8')).hexdigest()!=EXPECTED_SHA256 or before.count(OLD)!=1:
        raise RuntimeError('Live roof snippet differs from this Capture baseline')
    names=('OUT_BUILDING_LOD0','OUT_BUILDING_PREVIEW','OUT_BUILDING_METADATA')
    for name in names:
        n=asset.node('StreetBuildingCore/'+name); n.cook(force=True)
        if n.errors() or n.warnings(): raise RuntimeError('Baseline output diagnostics: '+name)
    try:
        if asset.matchesCurrentDefinition(): asset.allowEditingOfContents()
        p.set(before.replace(OLD,NEW,1))
        for name in names:
            n=asset.node('StreetBuildingCore/'+name); n.cook(force=True)
            if n.errors() or n.warnings(): raise RuntimeError(name+': '+str(n.errors()+n.warnings()))
    except Exception:
        p.set(before)
        raise
    return {'changed':True,'saved':False,'removed':'roof_y-1 Cornice only'}
