"""Canonical window interface for Live, candidate export and definition saves."""
MARKER='STREETBUILDING_WINDOW_MODULE_COUNTS_20260927'

def promote(templates, asset, hou_module=None):
    if hou_module is None:
        import hou
    else:
        hou=hou_module
    if MARKER not in asset.node('StreetBuildingCore/ALLOCATE_FACADE_CAPACITY').evalParm('snippet'):
        return templates
    for name in ('window_count_min','window_count_max'):
        p=templates.find(name)
        p.setLabel('标准层窗模块数量 / 每层每立面' if name.endswith('_min') else '标准层窗模块最大数量 / Maximum')
        p.setConditional(hou.parmCondType.HideWhen,'{ facade_layout_mode != random }' if name.endswith('_max') else '')
        p.setConditional(hou.parmCondType.DisableWhen,'{ style_rule_source == 1 style_override_upper == 0 }')
        p.setHelp('一个窗模块计 1 个，双宽窗也计 1 个。每个标准层按正/左/右/后分别计算；L 形同方向墙段共享配额。余量自动填墙，容量不足见 Cook 诊断。风格默认生效时在三层配置开启标准层覆盖才能使用此值。')
        templates.replace(name,p)
    for name in ('blank_count_min','blank_count_max','facade_override_blank_min#','facade_override_blank_max#'):
        if templates.find(name) is not None:templates.hide(name,True)
    for name in ('facade_override_window_min#','facade_override_window_max#'):
        p=templates.find(name)
        if p:
            p.setLabel('窗模块数量' if '_min' in name else '窗模块最大数量')
            p.setHelp('标准层按物理立面共享模块配额；主/次正面命中同一正面，后行覆盖前行。空白余量自动填墙。')
            templates.replace(name,p)
    p=templates.find('facade_layout_mode')
    p.setHelp('精确：标准层使用窗模块数量。随机：在最少/最多模块数间按种子抽取。标准层继承风格时使用风格中的模式；首层使用既有用途和门/橱窗规则。')
    templates.replace(p.name(),p)
    p=templates.find('style_override_upper')
    p.setLabel('覆盖标准层（使用实例窗模块数量与排列）')
    p.setHelp('关闭时采用 StyleConfig 标准层规则；开启后采用实例面板。局部楼层/立面规则优先。')
    templates.replace(p.name(),p)
    return templates
