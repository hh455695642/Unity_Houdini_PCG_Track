"""Material-only styles: canonical public panel shared by candidate and saved HDA."""
MARKER = 'STREETBUILDING_INSTANCE_RULES_20260927'


def promote(templates, asset, hou_module=None):
    if hou_module is None:
        import hou
    else:
        hou = hou_module
    if MARKER not in asset.node('StreetBuildingCore/PARSE_GENERATION_RULES').evalParm('snippet'):
        return templates
    entries = {}
    def collect(items):
        for t in items:
            if isinstance(t, hou.FolderParmTemplate) and t.folderType() != hou.folderType.MultiparmBlock:
                collect(t.parmTemplates())
            else: entries[t.name()] = t
    collect(templates.entries())
    # Extension point: new authoring controls belong to an explicit instance group.
    def menu(name,label,items,labels,default=0):
        if name not in entries:
            entries[name]=hou.MenuParmTemplate(name,label,items,labels,default_value=default)
    menu('ground_quantity_mode','商业门数量模式',('precise','random'),('固定数量','随机范围'))
    menu('ground_attachment_placement','首层雨棚／招牌挂点',('0','1'),('网格随机','跟随实际门窗'))
    entries['ground_attachment_placement'].setMenuUseToken(True)
    entries['ground_attachment_placement'].setHelp('仅影响首层雨棚和招牌；跟随最终实际门窗。密度、上限及立面/楼层覆盖继续由实例附件规则控制。')
    if 'STREETBUILDING_GROUND_CORNER_20261003' in asset.node('StreetBuildingCore/SELECT_FACADE_VARIANTS').evalParm('snippet'):
        if 'corner_building' not in entries:
            entries['corner_building']=hou.ToggleParmTemplate('corner_building','街角建筑（首层侧面装饰）',default_value=False)
        menu('corner_street_side','首层临街侧面',('0','1','2'),('左侧','右侧','两侧'),1)
        entries['corner_street_side'].setMenuUseToken(True)
    menu('shopfront_control','橱窗控制方式',('count','ratio'),('按模块数量','按占格比例'))
    menu('shopfront_quantity_mode','橱窗数量模式',('precise','random'),('固定数量','随机范围'))
    if 'shopfront_facades' not in entries:
        entries['shopfront_facades']=hou.IntParmTemplate('shopfront_facades','橱窗分布立面（位掩码）',1,default_value=(15,),min=0,max=15)
    if 'shopfront_count' not in entries:
        entries['shopfront_count']=hou.IntParmTemplate('shopfront_count','橱窗数量（每个选中立面）',1,default_value=(2,),min=0,max=64,min_is_strict=True,max_is_strict=True)
    for i,label in enumerate(('正面','左侧','右侧','后面')):
        name='shopfront_face_'+str(i)
        if name not in entries:entries[name]=hou.ToggleParmTemplate(name,'橱窗：'+label,default_value=True)
    if 'ground_rhythm' not in entries:
        entries['ground_rhythm']=hou.IntParmTemplate('ground_rhythm','首层排列方式',1,default_value=(0,),menu_items=('0','1','3','4'),menu_labels=('随机','均匀分布','左右对称','成组'))
    entries['ground_rhythm'].setMenuUseToken(True)
    used=set()
    def take(name,label=None,hide='',help=None):
        t=entries[name]; used.add(name)
        t.hide(False)
        t.setConditional(hou.parmCondType.HideWhen,hide)
        t.setConditional(hou.parmCondType.DisableWhen,'')
        if label:t.setLabel(label)
        if help:t.setHelp(help)
        return t
    def group(name,label,children):
        return hou.FolderParmTemplate(name,label,tuple(children),folder_type=hou.folderType.Collapsible)
    mass=[]
    for n in ('building_width','building_depth','massing_shape','l_notch_width_cells','l_notch_depth_cells','l_notch_side','floor_count','rear_facade_mode'):
        t=take(n)
        if n.startswith('l_notch_'):t.setConditional(hou.parmCondType.HideWhen,'{ massing_shape == rectangle }')
        if n in ('building_width','building_depth'):t.setConditional(hou.parmCondType.HideWhen,'{ site_source == external }')
        mass.append(t)
    commercial='{ ground_floor_use == residential }'
    ground=[take('ground_floor_use'),take('residential_door_enabled',hide='{ ground_floor_use == commercial }'),
        take('ground_quantity_mode',hide=commercial),
        take('entrance_count_min','商业门最小数量（整栋首层）',commercial+' { ground_quantity_mode == precise }'),
        take('entrance_count_max','商业门数量／随机最大值（整栋首层）',commercial),
        take('shopfront_control',hide=commercial)]
    for i in range(4):ground.append(take('shopfront_face_'+str(i),hide=commercial))
    ground += [take('shopfront_quantity_mode',hide=commercial+' { shopfront_control == ratio }'),
        take('shopfront_count','橱窗数量（每个选中立面）',commercial+' { shopfront_control == ratio } { shopfront_quantity_mode == random }'),
        take('shopfront_count_min','橱窗随机最小数量（每个选中立面）',commercial+' { shopfront_control == ratio } { shopfront_quantity_mode == precise }'),
        take('shopfront_count_max','橱窗随机最大数量（每个选中立面）',commercial+' { shopfront_control == ratio } { shopfront_quantity_mode == precise }'),
        take('shopfront_ratio','橱窗占格比例（扣除门后的可用格数）',commercial+' { shopfront_control == count }'),
        take('ground_rhythm')]
    for n in ('shopfront_count_min','shopfront_count_max','window_count_min','window_count_max'):
        entries[n].setMinValue(0);entries[n].setMaxValue(64);entries[n].setMinIsStrict(True);entries[n].setMaxIsStrict(True)
    # Existing values survive interface replacement; these are defaults for new instances.
    entries['shopfront_count_min'].setDefaultValue((1,));entries['shopfront_count_max'].setDefaultValue((4,))
    upper=[take('facade_layout_mode','标准层数量模式'),take('window_count_min','窗模块数量／随机最小值（每层每立面）'),
        take('window_count_max','窗模块随机最大数量（每层每立面）','{ facade_layout_mode != random }'),take('facade_rhythm','标准层排列方式')]
    roof=[take(n) for n in ('roof_enabled','parapet_enabled','parapet_height','architectural_trim_enabled')]
    if 'corner_building' in entries:
        roof += [take('corner_building',help='只控制首层侧面装饰，不改变墙体、门窗、上层、屋顶或道路识别。'),
            take('corner_street_side',hide='{ corner_building == 0 }',help='主正面的局部左／右；仅外侧墙段，L 形凹口内墙不自动临街。')]
    attach=[take('attachments_enabled'),take('attachment_global_density',hide='{ attachments_enabled == 0 }'),
        take('ground_attachment_placement',hide='{ attachments_enabled == 0 }')]
    for key,label in (('awning','雨棚'),('sign','招牌'),('fire_escape','消防梯'),('wall_ac','墙面空调'),('roof_props','屋顶附件')):
        attach.append(group('sb_attachments_'+key,label,[take(key+'_density',hide='{ attachments_enabled == 0 }'),take(key+'_max_count',hide='{ attachments_enabled == 0 }')]))
    local=[take('facade_overrides'),take('attachment_overrides')]
    # No-op legacy rows stay readable; retired controls must not invite edits.
    mp=local[0]; children=[]
    for p in mp.parmTemplates():
        if any(x in p.name() for x in ('blank_','shop_door_','entrance_')):p.hide(True)
        if 'shopfront_min' in p.name():p.setLabel('首层橱窗数量／随机最小值')
        if 'shopfront_max' in p.name():p.setLabel('首层橱窗随机最大数量')
        children.append(p)
    mp.setParmTemplates(children)
    random=[take('variation_seed','变化种子（用途与素材）'),take('layout_seed','布局种子（门位与门窗布局）')]
    output=[take('lod_outputs_enabled'),take('debug_metadata_enabled')]
    inputs=[take('site_source_auto','自动选择地块来源'),take('site_source'),take('module_source')]
    for n in ('proxy_bay_width_target','proxy_bay_width_min','proxy_bay_width_max','proxy_wall_material','proxy_trim_material','proxy_window_material'):
        inputs.append(take(n,hide='{ module_source == unity_asset_instances }'))
    internal=[]
    for name,t in entries.items():
        if name not in used:
            t.hide(True);internal.append(t)
    result=hou.ParmTemplateGroup()
    for name,label,items in [('sb_massing','建筑体块',mass),('sb_ground','首层门窗',ground),('sb_upper','标准层门窗',upper),
        ('sb_roof_trim','屋顶与线脚',roof),('sb_attachments','附件',attach),('sb_local','局部覆盖',local),
        ('sb_random','随机与预览',random),('sb_output','输出与诊断',output),('sb_inputs','高级输入',inputs)]:
        result.append(group(name,label,items))
    hidden=group('sb_internal','内部兼容数据（不参与生成规则）',internal);hidden.hide(True);result.append(hidden)
    return result
