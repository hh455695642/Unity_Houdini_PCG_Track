"""Incremental panel presentation/metadata patch; never rebuilds the network.

Default save=False. The regression gate owns definition/HIP persistence.
"""
import hashlib

MARKER = 'STREETBUILDING_PANEL_METADATA_20261014'
METADATA_BEFORE = '8aee9489662b51909c60e6d9a2fcb207cd0211395fedc8b155fa65f9f22d8c07'
ALLOCATION_BEFORE = 'dba72c0bb9cf4fe2144595d0952fd483132cdc0fe0e9b24fc27f1ee9ee1afe1a'

APPEND = r'''
// STREETBUILDING_PANEL_METADATA_20261014
// 编辑器只读墙段图：直接发布真实 cell 拓扑，不复制分配规则。
// 扩展点：版本化文本允许追加诊断，旧实例属性保持兼容。
string panel_cells="op:../BUILD_FACADE_CELLS";
float panel_cw=detail("op:../PARSE_UNITY_INSTANCE_CATALOG","style_cell_width",0);
if(panel_cw<=0) panel_cw=2;
string panel_facades="v1\n";
if(chi("../../module_source")==1) for(int p=0;p<npoints(panel_cells);p++) {
    if(point(panel_cells,"floor_index",p)!=0 || point(panel_cells,"run_local_cell",p)!=0) continue;
    vector a=point(panel_cells,"placement_origin",p);
    vector right=point(panel_cells,"placement_right",p);
    int cells=point(panel_cells,"run_cell_count",p);
    vector b=a+right*(cells*panel_cw);
    panel_facades+=sprintf("%d|%d|%s|%g|%g|%g|%g|%d\n",
        int(point(panel_cells,"face_index",p)),int(point(panel_cells,"facade_target",p)),
        string(point(panel_cells,"surface_role",p)),a.x,a.z,b.x,b.z,cells);
}
setdetailattrib(0,"panel_facade_segments",panel_facades,"set");
setdetailattrib(0,"panel_metadata_version",1,"set");
'''


def apply(hou, node=None, save=False):
    node = node or hou.node('/obj/StreetBuilding_DEV')
    if node is None or node.type().name() != 'pcgbike::StreetBuilding::1.0':
        raise RuntimeError('StreetBuilding Live target mismatch')
    if save:
        raise RuntimeError('Use VerifyFull persistence gate; this patch is save=False only')
    snippet = node.node('StreetBuildingCore/BUILD_METADATA').parm('snippet')
    before = snippet.eval()
    metadata_after = before
    if MARKER in before:
        previous = APPEND.replace('if(chi("../../module_source")==1) for(int p=0;', 'for(int p=0;')
        if before.endswith(previous) and hashlib.sha256(before[:-len(previous)].encode()).hexdigest() == METADATA_BEFORE:
            metadata_after = before[:-len(previous)] + APPEND
        elif not before.endswith(APPEND):
            raise RuntimeError('Panel marker exists with unexpected implementation')
    elif hashlib.sha256(before.encode()).hexdigest() != METADATA_BEFORE:
        raise RuntimeError('BUILD_METADATA precondition hash mismatch')
    else:
        metadata_after = before + APPEND
    old_group = node.parmTemplateGroup()
    allocation = node.node('StreetBuildingCore/ALLOCATE_FACADE_CAPACITY').parm('snippet')
    allocation_before = allocation.eval()
    allocation_after = allocation_before
    if 'STREETBUILDING_PANEL_SOURCE_ROWS_20261014' not in allocation_before:
        if hashlib.sha256(allocation_before.encode()).hexdigest() != ALLOCATION_BEFORE:
            raise RuntimeError('ALLOCATE_FACADE_CAPACITY precondition hash mismatch')
        # 前置完整哈希 + 唯一锚点；只添加行号，不更改任何分配、排序或随机计算。
        loops = ['for(int layer=0;layer<2;layer++)foreach(string row;split(payloads[layer],"\\n"))',
                 'for(int layer=0;layer<2;layer++) foreach(string row;split(payloads[layer],"\\n"))']
        for loop in loops:
            anchor = loop + '\n' + ('    {' if loops.index(loop) == 0 else '        {')
            if allocation_after.count(anchor) != 1: raise RuntimeError('Override loop anchor mismatch')
            opening = 'for(int layer=0;layer<2;layer++) foreach(int panel_row; string row; split(payloads[layer],"\\n"))'
            allocation_after = allocation_after.replace(anchor, opening + '\n' + ('    {' if loops.index(loop) == 0 else '        {'))
        source = 'source=layer==0?"instance_override":"parcel_override";'
        if allocation_after.count(source) != 2: raise RuntimeError('Override source anchor mismatch')
        allocation_after = allocation_after.replace(source, 'source=sprintf("%s:%d",layer==0?"instance_override":"parcel_override",panel_row);')
        allocation_after += '\n// STREETBUILDING_PANEL_SOURCE_ROWS_20261014\n'
    group = node.parmTemplateGroup()
    changes = {
        'entrance_count_max': ('商业门数量上限（固定模式使用此数量；整栋首层）', None),
        'window_count_min': ('窗模块数量下限（固定模式使用此数量；每层每物理立面）', None),
        'parapet_height': (None, '{ parapet_enabled == 0 }'),
        'facade_override_layout_mode#': ('数量模式', None),
        'facade_override_shopfront_min#': ('橱窗模块数量下限（固定模式使用此数量）', '{ facade_override_floor_start# > 1 } { facade_override_floor_end# < 1 } { ground_floor_use == residential }'),
        'facade_override_shopfront_max#': ('橱窗随机最大模块数', '{ facade_override_layout_mode# != random_range } { facade_override_floor_start# > 1 } { facade_override_floor_end# < 1 } { ground_floor_use == residential }'),
        'facade_override_window_min#': ('窗模块数量下限（固定模式使用此数量）', '{ facade_override_floor_end# < 2 }'),
        'facade_override_window_max#': ('窗随机最大模块数', '{ facade_override_layout_mode# != random_range } { facade_override_floor_end# < 2 }'),
    }
    for kind in ('awning', 'sign', 'fire_escape', 'wall_ac', 'roof_props'):
        changes['sb_attachments_' + kind + '2'] = (None, '{ attachments_enabled == 0 }')
    try:
        for name, (label, condition) in changes.items():
            template = group.find(name)
            if template is None:
                raise RuntimeError('Missing current panel template: ' + name)
            if label is not None: template.setLabel(label)
            if condition is not None: template.setConditional(hou.parmCondType.HideWhen, condition)
            group.replace(name, template)
        if old_group.asDialogScript() != group.asDialogScript():
            node.setParmTemplateGroup(group)
        if metadata_after != before: snippet.set(metadata_after)
        if allocation_after != allocation_before: allocation.set(allocation_after)
        return {'status': 'PASS', 'saved': False, 'parameter_templates': list(changes)}
    except Exception:
        snippet.set(before)
        allocation.set(allocation_before)
        node.setParmTemplateGroup(old_group)
        raise
