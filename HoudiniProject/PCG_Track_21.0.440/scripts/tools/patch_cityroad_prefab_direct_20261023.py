"""V53 -> direct Prefab slots; audited live-only migration, no persistence."""
from pathlib import Path
import hashlib
hou=None
OLD_SHA='491ef68b8147bcd3d7302357eb5ea513936451a01dfd6bf5b2dbf3869502d916'

def apply(save=False,hou_api=None):
    global hou
    if hou_api is not None:hou=hou_api
    if save:raise RuntimeError('Use cumulative VerifyFull to persist')
    a=hou.node('/obj/CityRoad_DEV');b=a.node('CityRoadCore/CR_BUILDINGS/BUILD_FRONTAGE')
    new=Path(__file__).with_name('cityroad_frontage.vfl').read_text(encoding='utf-8')
    if a.parm('building_prefabs') is not None:
        assert b.parm('snippet').eval()==new
        return 'UNCHANGED'
    old=b.parm('snippet').eval();assert hashlib.sha256(old.encode()).hexdigest()==OLD_SHA,'Current frontage changed; refusing replacement'
    old_group=a.parmTemplateGroup();old_bg=b.parmTemplateGroup()
    scalar={p.name():p.eval() for p in a.parms() if p.name().startswith('building_')}
    expr=b.parm('variants').expression()
    old_comment=b.parent().comment()
    try:
        folder=next(t for t in old_group.entries() if t.label()=='Street Buildings / 沿街建筑')
        children=[t for t in folder.parmTemplates() if t.name() not in ('building_library','building_variants')]
        for t in children:
            if t.name() in ('building_width','building_depth'):
                t.hide(False)
                t.setLabel('Footprint Width / 最大占地宽度（米）' if t.name().endswith('width') else 'Footprint Depth / 最大占地进深（米）')
                t.setMinValue(.1);t.setMinIsStrict(True)
                t.setHelp('手动填写所有建筑 Prefab 的最大占地范围，用于 CityRoad 的位置和避让。Prefab 原点在占地中心、基座 y=0，正面朝本地 +Z。')
            if t.name()=='building_spacing':t.setLabel('Minimum Gap / 最小建筑净间距（米）')
        prefab=hou.StringParmTemplate('building_prefab#','Building Prefab # / 建筑预设 #',1,default_value=('',))
        tags=prefab.tags();tags['heuassetpath']='1';prefab.setTags(tags)
        prefab.setHelp('直接拖入 Unity Prefab。手动修改 StreetBuilding 并 Bake / 更新 Prefab 后，点击 CityRoad Recook。空槽不参与随机。')
        slots=hou.FolderParmTemplate('building_prefabs','Building Prefabs / 建筑 Prefab 列表',parm_templates=[prefab],folder_type=hou.folderType.MultiparmBlock,default_value=0)
        children.insert(1,slots);folder.setParmTemplates(children)
        group=a.parmTemplateGroup();group.replace(folder.name(),folder);a.setParmTemplateGroup(group)
        # Preserve the current scene's explicit assignments; no project assets are HDA defaults.
        paths=[str(Path(scalar['building_library'])/('Building_%02d.prefab'%i)).replace('\\','/') for i in range(int(scalar['building_variants']))]
        a.parm('building_prefabs').set(len(paths))
        for i,path in enumerate(paths,1):a.parm('building_prefab%d'%i).set(path)
        for name,value in scalar.items():
            if a.parm(name) is not None:a.parm(name).set(value)
        bg=b.parmTemplateGroup();bg.remove('library');b.setParmTemplateGroup(bg)
        b.parm('variants').setExpression('ch("../../../building_prefabs")');b.parm('snippet').set(new)
        b.parent().setComment('沿街建筑｜CityRoad 原生生成位置与朝向\n直接在 HDA 沿街建筑面板拖入 Prefab；占地尺寸和间距手动调整。\nStreetBuilding 手动编辑、Bake / 更新 Prefab，然后 CityRoad Recook。')
        b.cook(force=True);assert not b.errors(),b.errors()
        return 'APPLIED save=False'
    except:
        a.setParmTemplateGroup(old_group)
        for name,value in scalar.items():
            if a.parm(name) is not None:a.parm(name).set(value)
        b.setParmTemplateGroup(old_bg);b.parm('variants').setExpression(expr);b.parm('snippet').set(old);b.parent().setComment(old_comment)
        raise
