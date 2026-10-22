"""Canonical V2 instance controls. No generation defaults enter StyleConfig."""
MARKER = 'STREETBUILDING_RANDOM_V2_20261022'


def promote(templates, asset, hou):
    if MARKER not in asset.node('StreetBuildingCore/PARSE_GENERATION_RULES').evalParm('snippet'):
        return templates
    additions = []
    for name, label, default in (('random_algorithm', '采样算法版本（1 原算法／2 稳定随机）', 1),
                                 ('random_seed', '主随机种子', 0),
                                 ('random_feasible', '采样策略（0 按请求／1 可行组合优先）', 0)):
        t = templates.find(name) or hou.IntParmTemplate(name, label, 1, default_value=(default,))
        if name == 'random_algorithm':
            t.setMinValue(1); t.setMaxValue(2); t.setMinIsStrict(True); t.setMaxIsStrict(True)
        if name == 'random_feasible':
            t.setMinValue(0); t.setMaxValue(1); t.setMinIsStrict(True); t.setMaxIsStrict(True)
        additions.append(t)
    identity = templates.find('random_instance_id') or hou.StringParmTemplate('random_instance_id', '实例随机身份（显式初始化）', 1)
    identity.setHelp('V2 必填稳定 ASCII 标识；保存/重载不变。复制建筑后在下次显式生成时使用新身份。Houdini 独立使用时请设置唯一值。')
    additions.append(identity)
    for t in additions:
        if templates.find(t.name()) is not None:
            templates.remove(t.name())
        t.hide(False)
    folder = templates.find('sb_random')
    for t in additions:
        folder.addParmTemplate(t)
    templates.replace('sb_random', folder)
    for group in ('massing', 'ground', 'upper', 'attachments'):
        name = 'random_seq_' + group
        if templates.find(name) is None:
            t = hou.IntParmTemplate(name, '随机组序号 ' + group, 1, default_value=(0,), min=0, min_is_strict=True)
            t.hide(True)
            folder = templates.find('sb_internal'); folder.addParmTemplate(t); templates.replace('sb_internal', folder)
    return templates
