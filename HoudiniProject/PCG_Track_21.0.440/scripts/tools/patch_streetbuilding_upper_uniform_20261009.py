"""Incremental continuation of the A-rule implementation preserved from Live.

The pre-existing A solver is retained byte-for-byte. Avoid running the legacy
quadratic category sorter before the linear single-cell A path. No persistence;
the project's VerifyFull owns definition/HIP saving after cumulative validation.
"""
import hashlib

BEFORE_SHA256 = 'af7c810815f9793115aa230ca2cc82b3c43a320f0225e1b80fb97b66831e4e5a'
MARKER = '// STREETBUILDING_UPPER_UNIFORM_A_20261008'
AFTER_MARKER = '// STREETBUILDING_UPPER_UNIFORM_A_20261009_LINEAR_DISPATCH'
OLD = '''        int sorted[]=sb_order(pool,mode,seed,degraded);
        int uniform_active=floor>0 && mode==1;
        if(uniform_active) {
            int limited=0;string summary="";
            int arranged[]=sb_upper_uniform(pool,limited,summary);
            if(len(arranged)>0) {sorted=arranged;uniform_summary=summary;}
        }'''
NEW = '''        int uniform_active=floor>0 && mode==1;
        int sorted[];
        // 性能关键点：标准层 A 路径不预跑旧类别排序，单格留白求解保持线性。
        // 扩展点：数量、素材和占格来自 pool；这里仅分配完整模块的位置。
        if(uniform_active) {
            int limited=0;string summary="";
            sorted=sb_upper_uniform(pool,limited,summary);
            if(len(sorted)>0)uniform_summary=summary;
        }
        // 零窗和所有非目标模式保持原行为，不引入随机调用或楼层因子。
        if(len(sorted)==0)sorted=sb_order(pool,mode,seed,degraded);'''


def apply(asset=None, save=False):
    if save:
        raise ValueError('Persistence is owned by Invoke-PcgRegression VerifyFull')
    if asset is None:
        import hou
        asset=hou.node('/obj/StreetBuilding_DEV')
    if asset is None or asset.type().name()!='pcgbike::StreetBuilding::1.0':
        raise RuntimeError('Expected current StreetBuilding Live instance')
    node=asset.node('StreetBuildingCore/SELECT_FACADE_MODULES')
    parm=node.parm('snippet');before=parm.eval()
    if AFTER_MARKER in before:
        reconstructed=before.replace(AFTER_MARKER,MARKER).replace(NEW,OLD)
        if hashlib.sha256(reconstructed.encode()).hexdigest()!=BEFORE_SHA256:
            raise RuntimeError('Already-patched source has unexpected independent edits')
        return {'changed':False,'sha256':hashlib.sha256(before.encode()).hexdigest()}
    if MARKER not in before or before.count(OLD)!=1 or hashlib.sha256(before.encode()).hexdigest()!=BEFORE_SHA256:
        raise RuntimeError('Live source marker/full hash differs from captured source')
    after=before.replace(MARKER,AFTER_MARKER).replace(OLD,NEW)
    try:
        parm.set(after)
        node.cook(force=True)
        if node.errors() or node.warnings():
            raise RuntimeError(str((node.errors(),node.warnings())))
    except Exception:
        parm.set(before)
        node.cook(force=True)
        raise
    return {'changed':True,'sha256':hashlib.sha256(after.encode()).hexdigest(),'saved':False}
