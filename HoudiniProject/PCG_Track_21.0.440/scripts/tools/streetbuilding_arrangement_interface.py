"""Canonical arrangement menu shared by Live, candidate and production saves."""
MARKER = 'STREETBUILDING_ARRANGEMENT_20260915'


def promote(templates, asset):
    if MARKER not in asset.node('StreetBuildingCore/SELECT_FACADE_MODULES').evalParm('snippet'):
        return templates
    for name in ('facade_rhythm', 'facade_override_rhythm#'):
        parm = templates.find(name)
        if parm is None:
            raise RuntimeError('Missing arrangement interface: ' + name)
        parm.setLabel('排列方式')
        parm.setMenuItems(('0', '1', '3', '4'))
        parm.setMenuLabels(('随机', '均匀分布', '左右对称', '成组'))
        parm.setMenuUseToken(True)
        parm.setHelp('保持功能数量与入口位置；每段连续墙面独立排列。标准层同配置上下对齐。'
                     '成组默认两个；对称采用同款同宽模块，不镜像模型。旧值2按均匀分布读取。'
                     '规则来源：实例/风格默认，再由局部覆盖决定；限制见生成报告。')
        templates.replace(name, parm)
    return templates
