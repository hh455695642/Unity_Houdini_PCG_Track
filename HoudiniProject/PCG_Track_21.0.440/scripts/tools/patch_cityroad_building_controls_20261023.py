"""Current V52 -> public frontage controls. Incremental, idempotent, never saves."""
from pathlib import Path
import hashlib
hou = None
OLD_SHA = 'e8bfe04e3b565ed87cdb819cdce4d70d7c7ea5cdc879b358da497e7b4baed46d'

def templates(h):
    p = [h.ToggleParmTemplate('building_enabled','Enable Buildings / 生成沿街建筑',default_value=True)]
    for name,label,value,limit in [
        ('setback','Setback / 人行道外退距（米）',3,30),
        ('spacing','Spacing / 建筑净间距（米）',2,20),
        ('junction_margin','Corner Margin / 弯角及路口退让（米）',0,30),
        ('ground_height','Base Height / 基座高度（米）',.6,10)]:
        p.append(h.FloatParmTemplate('building_'+name,label,1,default_value=(value,),min=0,max=limit,min_is_strict=True))
    p.append(h.IntParmTemplate('building_seed','Random Seed / 建筑变体种子',1,default_value=(1729,)))
    # Internal catalog bridge: sizes describe baked models, never editable generation quotas.
    for name,value in [('width',8),('depth',8)]:
        t=h.FloatParmTemplate('building_'+name,name,1,default_value=(value,));t.hide(True);p.append(t)
    t=h.IntParmTemplate('building_variants','Catalog Variant Count',1,default_value=(8,));t.hide(True);p.append(t)
    t=h.StringParmTemplate('building_library','Catalog Folder',1,default_value=('Assets/PCG/Generated/Buildings/CityFrontage',));t.hide(True);p.append(t)
    return p

def apply(save=False,hou_api=None):
    global hou
    if hou_api is not None: hou=hou_api
    if save: raise RuntimeError('VerifyFull must persist')
    a=hou.node('/obj/CityRoad_DEV');b=a.node('CityRoadCore/CR_BUILDINGS/BUILD_FRONTAGE')
    new=Path(__file__).with_name('cityroad_frontage.vfl').read_text(encoding='utf-8')
    if a.parm('building_enabled'):
        assert b.parm('snippet').eval()==new,'Unexpected frontage code after patch'
        return 'UNCHANGED'
    old=b.parm('snippet').eval()
    assert hashlib.sha256(old.encode()).hexdigest()==OLD_SHA,'V52 source drift; preserve live edits'
    group=a.parmTemplateGroup();bg=b.parmTemplateGroup()
    saved={p.name():(p.keyframes(),p.eval()) for p in b.parms() if p.name() in ('enabled','width','depth','setback','ground_height','seed','variants','library')}
    try:
        g=a.parmTemplateGroup()
        g.append(hou.FolderParmTemplate('street_buildings_folder','Street Buildings / 沿街建筑',parm_templates=templates(hou),folder_type=hou.folderType.Simple))
        a.setParmTemplateGroup(g)
        g=b.parmTemplateGroup()
        for name,value in [('spacing',2),('junction_margin',0)]:g.append(hou.FloatParmTemplate(name,name,1,default_value=(value,)))
        b.setParmTemplateGroup(g)
        for name in ('enabled','width','depth','setback','ground_height','seed','variants','library','spacing','junction_margin'):
            channel='chs' if name=='library' else 'ch'
            b.parm(name).setExpression('%s("../../../building_%s")'%(channel,name))
        b.parm('snippet').set(new);b.cook(force=True)
        assert not b.errors(),b.errors()
        return 'APPLIED save=False'
    except:
        a.setParmTemplateGroup(group);b.setParmTemplateGroup(bg);b.parm('snippet').set(old)
        for name,(keys,value) in saved.items():
            b.parm(name).deleteAllKeyframes()
            if keys:b.parm(name).setKeyframes(keys)
            else:b.parm(name).set(value)
        raise
