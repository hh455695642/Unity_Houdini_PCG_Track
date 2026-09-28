"""Canonical arrangement menu shared by Live, candidate and production saves."""
MARKER = 'STREETBUILDING_ARRANGEMENT_20260915'


def promote(templates, asset):
    import hou
    from streetbuilding_instance_interface import MARKER as INSTANCE_MARKER, promote as promote_instance
    if INSTANCE_MARKER in asset.node('StreetBuildingCore/PARSE_GENERATION_RULES').evalParm('snippet'):
        return promote_instance(templates, asset)
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
    if 'STREETBUILDING_GROUND_USE_V2_20260923' in asset.node(
            'StreetBuildingCore/ALLOCATE_FACADE_CAPACITY').evalParm('snippet'):
        ground = templates.find('ground_floor_use')
        ground.setMenuItems(('random', 'residential', 'commercial'))
        ground.setMenuLabels(('随机 / Random', '住宅 / Residential', '商业 / Commercial'))
        templates.replace('ground_floor_use', ground)
        mode = templates.find('facade_layout_mode')
        mode.setMenuItems(('precise', 'random'))
        mode.setMenuLabels(('精确 / Precise', '随机 / Random'))
        templates.replace('facade_layout_mode', mode)
        for name, label in (
                ('entrance_count_min', '商业门数最小值 / Commercial Door Minimum'),
                ('entrance_count_max', '商业门数 / Commercial Door Count (随机：最大值)')):
            parm = templates.find(name)
            parm.setLabel(label)
            parm.setMinValue(1)
            parm.setMaxValue(4)
            # Precise uses Max as its single visible count; random uses both.
            parm.setConditional(hou.parmCondType.HideWhen,
                                '{ facade_layout_mode == precise }' if name.endswith('_min') else '')
            templates.replace(name, parm)
        for name in ('shopfront_count_min', 'shopfront_count_max'):
            templates.hide(name, True)
        # Retired fields remain in the bridge for lossless HAPI migration.
        # They are absent from the ground-rule Inspector controls.
        for name in ('shop_door_count_min', 'shop_door_count_max'):
            legacy = templates.find(name)
            legacy.hide(False)
            legacy.setConditional(hou.parmCondType.HideWhen, '')
            legacy.setLabel('旧 Shop Door 数值（仅迁移） / Legacy Shop Door')
            templates.remove(name)
            templates.appendToFolder(templates.findIndices('sb_bridge'), legacy)
        for name in ('residential_door_enabled',):
            parm = asset.parmTemplateGroup().find(name)
            if parm is None:
                raise RuntimeError('Ground V2 interface is missing: ' + name)
            if templates.find(name) is None:
                templates.insertAfter('shopfront_ratio', parm)
            else:
                templates.replace(name, parm)
        # Houdini Engine omits hidden parms from its Unity cache. Keep the
        # migration version in the existing collapsible bridge folder so an
        # imported scene instance can set it after a definition refresh.
        schema = asset.parmTemplateGroup().find('ground_rule_schema_version')
        if schema is None or templates.find('sb_bridge') is None:
            raise RuntimeError('Ground V2 schema/Unity bridge is missing')
        schema.hide(False)
        if templates.find('ground_rule_schema_version') is not None:
            templates.remove('ground_rule_schema_version')
        templates.appendToFolder(templates.findIndices('sb_bridge'), schema)
    from streetbuilding_window_interface import promote as promote_windows
    return promote_windows(templates, asset)
