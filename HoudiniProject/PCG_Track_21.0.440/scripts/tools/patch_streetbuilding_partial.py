"""Incremental patch of the captured Live asset. Never saves HIP/definition.

Inputs are hashed Live snippets, not a historical builder. Called through MCP.
"""
import hashlib
import json
from pathlib import Path

def apply(hou, asset, updates_path, save=False):
    if save:
        raise ValueError('VerifyFull must precede explicit saving')
    updates = json.loads(Path(updates_path).read_text(encoding='utf-8'))
    core = asset.node('StreetBuildingCore')
    originals = {}
    for name, item in updates.items():
        parm = core.node(name).parm('snippet')
        text = parm.evalAsString()
        if text == item['snippet']:
            continue
        if hashlib.sha256(text.encode()).hexdigest() != item['before']:
            raise ValueError('Live snippet changed: ' + name)
        originals[name] = text
    if asset.parm('preview_missing_modules') and not originals:
        return 'already applied'
    original_group = asset.parmTemplateGroup()
    group = asset.parmTemplateGroup()
    old_source = core.node('SELECT_SITE_SOURCE').parm('input').expression()
    validate = core.node('VALIDATE_DIRECT_BUILDING_INSTANCES')
    previous_input = validate.input(0)
    created = []
    try:
        for name in originals:
            core.node(name).parm('snippet').set(updates[name]['snippet'])
        # Keep existing parameter identifiers, migrate old instances explicitly.
        folder = hou.FolderParmTemplate('sb_preview', '预览 / Preview')
        folder.addParmTemplate(hou.IntParmTemplate('preview_missing_modules', '缺失模块显示', 1,
            default_value=(0,), menu_items=('0','1'), menu_labels=('灰盒','留空')))
        folder.addParmTemplate(hou.ToggleParmTemplate('site_source_auto', '自动地块来源', default_value=True))
        group.append(folder)
        source = group.find('site_source')
        source.setConditional(hou.parmCondType.HideWhen, '{ site_source_auto == 1 }')
        group.replace('site_source', source)
        asset.setParmTemplateGroup(group)
        asset.parm('site_source_auto').set(0)
        core.node('SELECT_SITE_SOURCE').parm('input').setExpression(
            'int(hou.pwd().parent().parent().input(0) is not None) if hou.pwd().parent().parent().evalParm("site_source_auto") else hou.pwd().parent().parent().evalParm("site_source")',
            hou.exprLanguage.Python)
        real = core.createNode('attribwrangle', 'FILTER_REAL_INSTANCES'); created.append(real)
        real.parm('class').set(0)
        real.parm('snippet').set('''// Keep preview markers out of the production instance output.
int missing=0;
for(int p=npoints(0)-1;p>=0;p--) if(point(0,"preview_missing",p)) { missing++; removepoint(0,p); }
setdetailattrib(0,"preview_missing_count",missing,"set");
removeattrib(0,"point","preview_missing"); removeattrib(0,"point","preview_size");''')
        real.setInput(0, previous_input); validate.setInput(0, real)
        preview = core.createNode('attribwrangle', 'PREVIEW_MISSING_MODULES'); created.append(preview)
        preview.parm('class').set(0)
        preview.parm('snippet').set('''// Editor-only geometry: no Prefab substitution, no full-screen rendering cost.
int count=npoints(0);
int show=chi("../../preview_missing_modules")==0 && chi("../../module_source")==1;
for(int p=0;p<count;p++) {
    if(!show || !point(0,"preview_missing",p)) continue;
    vector origin=point(0,"P",p); vector size=point(0,"preview_size",p);
    vector4 q=point(0,"orient",p);
    vector corners[]=array(set(-.5,0,-.5),set(.5,0,-.5),set(.5,1,-.5),set(-.5,1,-.5),
        set(-.5,0,.5),set(.5,0,.5),set(.5,1,.5),set(-.5,1,.5));
    int indices[]=array(0,3,2,1,4,5,6,7,0,4,7,3,1,2,6,5,3,7,6,2);
    for(int f=0;f<5;f++) {
        int face=addprim(0,"poly");
        for(int c=0;c<4;c++) {
            vector pos=origin+qrotate(q,corners[indices[f*4+c]]*size);
            addvertex(0,face,addpoint(0,pos));
        }
        setprimattrib(0,"unity_material",face,chs("../../proxy_wall_material"),"set");
        setprimattrib(0,"streetbuilding_preview_only",face,1,"set");
    }
}
for(int p=count-1;p>=0;p--) removepoint(0,p);
removeattrib(0,"point","unity_instance"); removeattrib(0,"point","instance_prefix");
removeattrib(0,"point","name");
setdetailattrib(0,"streetbuilding_preview_only",1,"set");''')
        preview.setInput(0, previous_input)
        output = core.createNode('output', 'OUT_BUILDING_PREVIEW'); created.append(output)
        output.parm('outputidx').set(6); output.setInput(0, preview)
        real.setPosition(hou.Vector2(16,-14)); preview.setPosition(hou.Vector2(20,-14)); output.setPosition(hou.Vector2(20,-17))
        preview.setComment('缺失模块灰盒预览；独立输出，正式 Bake 必须排除。')
        return 'applied without saving'
    except Exception:
        validate.setInput(0, previous_input)
        for node in reversed(created): node.destroy()
        asset.setParmTemplateGroup(original_group)
        core.node('SELECT_SITE_SOURCE').parm('input').setExpression(old_source)
        for name, text in originals.items(): core.node(name).parm('snippet').set(text)
        raise
