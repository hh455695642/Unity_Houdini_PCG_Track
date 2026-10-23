"""Incremental current-scene patch. Does not persist definition or HIP."""
from pathlib import Path
import hashlib
try:
    import hou
except ImportError:
    hou = None  # Standard MCP supplies its audited hou proxy explicitly.

ROOT=Path(__file__).resolve().parents[4]

def apply(save=False, hou_api=None):
    global hou
    if hou_api is not None: hou=hou_api
    if save: raise RuntimeError('Use cumulative VerifyFull to persist')
    asset=hou.node('/obj/CityRoad_DEV')
    assert asset and asset.userData('pcg_cityroad_v51')=='CITYROAD_V51_RESTORE_GENERATION'
    core=asset.node('CityRoadCore')
    if core.node('CR_BUILDINGS'):
        assert core.node('CR_BUILDINGS/BUILD_FRONTAGE').parm('snippet').eval()==Path(__file__).with_name('cityroad_frontage.vfl').read_text(encoding='utf-8')
        return
    asset.allowEditingOfContents()
    made=[]
    try:
        subnet=core.createNode('subnet','CR_BUILDINGS');made.append(subnet)
        subnet.setComment('沿街建筑｜位置唯一生成源\n道路顶面 → 清理极薄三角形 → 外边界采样 → 道路/地块避让 → StreetBuilding Prefab 实例点\n参数在 BUILD_FRONTAGE；Unity 不计算位置。关闭 enabled 可停用。')
        subnet.setGenericFlag(hou.nodeFlag.DisplayComment,False)
        source=subnet.createNode('object_merge','ROAD_SURFACE');source.parm('objpath1').set('../../OUT_ROAD_SURFACE')
        unpack=subnet.createNode('unpack','UNPACK_ROAD');unpack.setInput(0,source)
        fuse=subnet.createNode('fuse::2.0','FUSE_ROAD_VERTICES');fuse.setInput(0,unpack)
        clean=subnet.createNode('attribwrangle','REMOVE_THIN_TRIANGLES');clean.setInput(0,fuse);clean.parm('class').set(0)
        clean.parm('snippet').set('int p[]=primpoints(0,@primnum);if(len(p)<3){removeprim(0,@primnum,1);return;}vector a=point(0,"P",p[0]),b=point(0,"P",p[1]),c=point(0,"P",p[2]);if(min(distance(a,b),distance(b,c),distance(c,a))<.01||length(cross(b-a,c-a))<.001)removeprim(0,@primnum,1);')
        # class=primitive is 1 in Houdini; explicitly resolve the menu token.
        clean.parm('class').set(1)
        graph=subnet.createNode('object_merge','CENTERLINE_GRAPH');graph.parm('objpath1').set('../../CR_MAIN_PIPELINE/CR_INPUT_CONTRACT')
        empty=subnet.createNode('add','EMPTY_POINTS');empty.parm('points').set(1)
        build=subnet.createNode('attribwrangle','BUILD_FRONTAGE');build.setInput(0,empty);build.setInput(1,clean);build.setInput(2,graph);build.parm('class').set(0)
        group=build.parmTemplateGroup()
        for p in [hou.ToggleParmTemplate('enabled','启用沿街建筑',default_value=True),
            hou.FloatParmTemplate('width','建筑宽度（米）',1,default_value=(8,)),hou.FloatParmTemplate('depth','建筑进深（米）',1,default_value=(8,)),
            hou.FloatParmTemplate('setback','人行道外退距（米）',1,default_value=(3,)),hou.FloatParmTemplate('sidewalk','人行道宽度（米）',1,default_value=(2,)),
            hou.FloatParmTemplate('ground_height','建筑基座高度（米）',1,default_value=(.6,)),
            hou.IntParmTemplate('seed','变体种子',1,default_value=(1729,)),hou.IntParmTemplate('variants','共享建筑变体数',1,default_value=(8,)),
            hou.StringParmTemplate('library','StreetBuilding Bake 目录',1,default_value=('Assets/PCG/Generated/Buildings/CityFrontage',))]: group.append(p)
        build.setParmTemplateGroup(group);build.parm('sidewalk').setExpression('ch("../../../sidewalk_width")')
        build.parm('snippet').set(Path(__file__).with_name('cityroad_frontage.vfl').read_text(encoding='utf-8'))
        out=subnet.createNode('output','OUT_INSTANCE_POINTS');out.setInput(0,build);out.setDisplayFlag(True);out.setRenderFlag(True)
        subnet.layoutChildren();subnet.setPosition(hou.Vector2(12,-3))
        formal=core.createNode('output','OUT_STREET_BUILDINGS');made.append(formal);formal.parm('outputidx').set(10);formal.setInput(0,subnet);formal.setPosition(hou.Vector2(12,-6))
        formal.setComment('CityRoad 原生位置输出；unity_instance 指向 StreetBuilding Bake，共享 Mesh/Material。')
        build.cook(force=True)
        if build.errors():raise RuntimeError(build.errors())
        print('PATCH_APPLIED save=False')
    except:
        for n in reversed(made):n.destroy()
        raise

if __name__=='__main__':apply(False)

