"""One-time, hash-guarded Live cleanup. Does not save a production HDA or HIP.

Pass the connected hou API to apply(hou, save=False). The complete source can
also be submitted to the standard MCP execute_code tool under normal policy.
This migration is an audit record, not a builder or a dependency of validators.
"""
import hashlib
import json
from pathlib import Path
import re
import textwrap

MARKER = 'STREETBUILDING_CORE_CLEANUP_20260928'
CORE = '/obj/StreetBuilding_DEV/StreetBuildingCore'
RETIRED = ('BUILD_LOD1', 'NORMAL_LOD1', 'BUILD_LOD2', 'NORMAL_LOD2',
           'BUILD_COLLISION', 'GRAYBOX_MODULE_LIBRARY')
HASHES = {
    'BUILD_LOD0': '8952e7022a940446e50e3b313d14ea91f4841ab6d36882c272f9a79e238d87e9',
    'DETAIL_INSTANCE_POINTS': '8ed2329ad731b35c932ea4ec61107fc0f1c02b44b9156ac0eab7be89bdb44f82',
    'BUILD_DIRECT_ROOF_INSTANCES': '0edc287385bdde9fe3d3d3a41597b484c41ac8cb2a97a026ce89853bfd1ae620',
    'BUILD_DIRECT_ROOF_EDGE_INSTANCES': 'fe9c0fd0e268cb218679dc85213543ce8e0a48f8a384c9ab06606cbd0f4820d6',
    'SELECT_FACADE_VARIANTS': '6e60fb8809f2f70a4593687944283a55e386079ac6ebc54364f0e2bba49aab45',
}
UNUSED = {
    'DETAIL_INSTANCE_POINTS': ('sbv6_has_role',),
    'BUILD_DIRECT_ROOF_INSTANCES': ('sb_has_variant', 'sb_has_role'),
    'BUILD_DIRECT_ROOF_EDGE_INSTANCES': ('sb_has_variant', 'sb_has_role'),
    'SELECT_FACADE_VARIANTS': ('sb_has_variant', 'sb_emit'),
}
# Fixed stage boundaries and positions keep repeated application deterministic.
# Node paths and operational connections are deliberately retained.
STAGES = [
    ('00_INPUT_VALIDATE', '00 输入整理', (-24, 32, 68, 14),
     [('EMPTY_GEOMETRY', -22, 40), ('IN_MODULE_LIBRARY', -22, 35), ('INTERNAL_TEST_PARCEL', -10, 40),
      ('IN_SITE_PARCELS', 0, 40), ('SELECT_SITE_SOURCE', -5, 36), ('CANONICALIZE_PARCELS', -5, 33.8),
      ('IN_FRONTAGE_GUIDES', 12, 36)],
     '职责：统一地块与外部输入。\n输入：HDA 1 地块 / 2 临街引导 / 3 外部模块；空几何供各生成器使用。\n输出：规范地块与辅助输入。修改：实例面板的地块来源和测试尺寸。扩展：接入前先保留输入校验。'),
    ('10_RULES_AND_CATALOG', '10 规则与素材解析', (0, 17, 20, 13),
     [('RESOLVE_FRONTAGES', 2, 24), ('PARSE_GENERATION_RULES', 2, 20), ('PARSE_UNITY_INSTANCE_CATALOG', 12, 20)],
     '职责：临街识别、实例规则、素材目录解析。\n输入：规范地块、引导、实例参数、素材目录。输出：有效规则与候选规格。\n修改：生成数量在实例；素材仅约束选择。扩展：沿用显式地块/局部覆盖优先级。'),
    ('20_FACADE_CAPACITY', '20 立面容量', (0, 5, 20, 10),
     [('BUILD_FACADE_CELLS', 2, 9), ('ALLOCATE_FACADE_CAPACITY', 2, 6.8)],
     '职责：建立立面格子，先门、再窗、最后填墙。\n输入：有效规则和素材规格。输出：容量分配与请求/实际数量。\n修改：按模块和物理立面核对额度。扩展：新角色不得增加已有配额。'),
    ('30_FACADE_SELECTION', '30 模块选择', (0, -7, 20, 10),
     [('SELECT_FACADE_VARIANTS', 2, -3), ('SELECT_FACADE_MODULES', 2, -5.2)],
     '职责：选择素材变体并完成模块排列。\n输入：容量分配与素材候选。输出：完整立面放置记录。\n修改：保持固定种子确定性；排列不增加数量。扩展：在候选适用范围内增加变体。'),
    ('40_BUILDING_INSTANCES', '40 主体实例', (0, -20, 24, 11),
     [('DIRECT_UNITY_INSTANCE_FACADE', 2, -15.3), ('BUILD_DIRECT_SIDE_REAR_INSTANCES', 13, -15.3),
      ('BUILD_DIRECT_ROOF_INSTANCES', 2, -18), ('BUILD_DIRECT_ROOF_EDGE_INSTANCES', 13, -18)],
     '职责：正面、侧后立面、屋顶、女儿墙及屋顶边缘。\n输入：立面放置记录与素材目录。输出：主体实例点。\n修改：各表面职责独立。扩展：保持包围、朝向、接缝合约。\n隐式依赖：屋顶节点按相对路径读取 PARSE_GENERATION_RULES。'),
    ('50_ATTACHMENT_INSTANCES', '50 附件实例', (27, -20, 17, 13),
     [('SELECT_ATTACHMENT_MODULES', 29, -14), ('DETAIL_INSTANCE_POINTS', 29, -17)],
     '职责：附件规则、素材选择和表面放置。\n输入：规则、目录、实际立面墙体。输出：独立附件实例点。\n修改：密度、范围、实例预算。扩展：新增附件保留支撑面检查。'),
    ('60_PROXY_MODEL', '60 灰模主模型', (-24, -20, 21, 33),
     [('RESOLVE_MASSING', -22, 6), ('RESOLVE_FACADE_GRAMMAR', -22, 2),
      ('VALIDATE_MODULE_LIBRARY', -12, -2), ('BUILD_LOD0', -22, -8), ('NORMAL_LOD0', -22, -13)],
     '职责：灰模模式的主模型与法线。\n输入：实例规则、体块、外部模块。输出：灰模主模型。\n修改：BUILD_LOD0 保留兼容名，当前仅生成主模型。扩展：外部素材仍从 HDA 输入 3 接入。\n隐式依赖：BUILD_LOD0 读取素材目录的楼层高度；本区不生成 LOD1/2 或碰撞。'),
    ('70_UNITY_CONTRACT', '70 汇合与校验', (-24, -39, 68, 16),
     [('MERGE_DIRECT_BUILDING_INSTANCES', 2, -29), ('FILTER_REAL_INSTANCES', 2, -32),
      ('VALIDATE_DIRECT_BUILDING_INSTANCES', 2, -35), ('LOD0_MODULE_SOURCE_SWITCH', -15, -37),
      ('VALIDATE_DIRECT_DETAIL_INSTANCES', 29, -29), ('DETAIL_MODULE_SOURCE_SWITCH', 29, -35),
      ('PREVIEW_MISSING_MODULES', 14, -32), ('BUILD_METADATA', 39, -35)],
     '职责：合并、过滤、诊断，分离真实实例与缺件预览。\n输入：主体、附件、灰模、规则与容量。输出：主模型、附件、诊断、预览四条路径。\n修改：保持预览不进入 Bake 实例。扩展：新诊断追加在 metadata；校验器通过相对路径读取规则与目录。'),
    ('80_OUTPUT_VALIDATE', '80 稳定输出', (-24, -51, 68, 10),
     [('OUT_BUILDING_LOD0', -22, -48), ('OUT_BUILDING_LOD1', -13, -48), ('OUT_BUILDING_LOD2', -4, -48),
      ('OUT_DETAIL_INSTANCES', 5, -48), ('OUT_BUILDING_COLLISION', 14, -48),
      ('OUT_BUILDING_METADATA', 23, -48), ('OUT_BUILDING_PREVIEW', 32, -48)],
     '职责：保持 Unity 输出槽编号稳定。\n输入：校验后的各条输出。输出：0 主模型 / 1 空 / 2 空 / 3 附件 / 4 空 / 5 metadata / 6 预览。\n修改：1、2、4 为兼容空槽；预览不可 Bake。扩展：新增正式输出必须更新累计合约和 Unity 桥接。'),
]


def masked(source):
    # Preserve offsets while excluding comments and string literals from braces.
    return re.sub(r'//[^\n]*|/\*.*?\*/|"(?:\\.|[^"\\])*"',
                  lambda m: ''.join('\n' if c == '\n' else ' ' for c in m.group()), source, flags=re.S)


def block_end(source, opening):
    code = masked(source)
    assert code[opening] == '{'
    depth = 1
    for i in range(opening+1, len(code)):
        depth += (code[i] == '{') - (code[i] == '}')
        if depth == 0:
            return i+1
    raise ValueError('Unbalanced VEX block')


def remove_function(source, name):
    code = masked(source)
    occurrences = list(re.finditer(r'\b' + re.escape(name) + r'\s*\(', code))
    if len(occurrences) != 1:
        raise ValueError('Function is used or absent: ' + name)
    found = re.search(r'^\s*(?:function\s+)?(?:void|int|float|string|vector[24]?)\s+'
                      + re.escape(name) + r'\s*\([^{}]*\)\s*\{', code, flags=re.M)
    if found is None:
        raise ValueError('Function signature mismatch: ' + name)
    return source[:found.start()] + '\n' + source[block_end(source, found.end()-1):]


def rewrite(name, source):
    if hashlib.sha256(source.encode()).hexdigest() != HASHES[name]:
        raise ValueError('Precondition VEX hash mismatch: ' + name)
    if name == 'BUILD_LOD0':
        token = 'if(lod_value==0 || chi("../../lod_outputs_enabled"))'
        assert source.count(token) == 1
        start = source.index(token); opening = source.index('{', start)
        end = block_end(source, opening)
        source = source[:start] + textwrap.dedent(source[opening+1:end-1]).lstrip('\n') + source[end:]
        token = 'if(lod_value==2)'
        assert source.count(token) == 1
        start = source.rfind('\n', 0, source.index(token)) + 1
        opening = source.index('{', source.index(token))
        source = source[:start] + source[block_end(source, opening):].lstrip('\r\n')
        for old, new in (('int detailed=lod_value==0;', 'int detailed=1;'),
                         (' && lod_value<2', ''), ('lod_value<2 && ', ''), (' && lod_value==0', '')):
            assert old in source
            source = source.replace(old, new)
        source, count = re.subn(r'^\s*if\(lod_value<2\)\n', '\n', source, flags=re.M)
        assert count == 1
        assert not re.search(r'lod_value\s*(?:==|<)', source)
        note = '// 主模型灰模路径；lod=0 仅保留输出命名与属性兼容，不生成其他 LOD。\n'
    else:
        for function in UNUSED[name]:
            source = remove_function(source, function)
        note = '// 删除无调用的历史辅助函数；实际放置、种子和输出属性保持不变。\n'
    return '// ' + MARKER + '\n' + note + source.lstrip('\n')


def apply(hou, save=False):
    if save:
        raise ValueError('Use VerifyFull persistence; this patch always requires save=False')
    c = hou.node(CORE)
    assert c is not None and c.parent().type().name() == 'pcgbike::StreetBuilding::1.0'
    a = c.parent()
    expected_names = {n for _, _, _, entries, _ in STAGES for n, _, _ in entries}
    current = {n.name() for n in c.children()}
    if current == expected_names and all(MARKER in c.node(n).evalParm('snippet') for n in HASHES):
        assert a.parmTemplateGroup().find('lod_outputs_enabled').isHidden()
        return {'status': 'UNCHANGED', 'nodes': 40, 'saved': False}
    assert current == expected_names | set(RETIRED), 'Node inventory changed since planning'
    rewritten = {n: rewrite(n, c.node(n).evalParm('snippet')) for n in HASHES}
    for node in c.children():
        if node.name() in RETIRED:
            assert all(n.name() in RETIRED for n in node.outputs()), 'Retired node gained a consumer'
        for p in node.parms():
            assert not any(name in p.rawValue() for name in RETIRED), 'Retired node has an expression reference'
    backup = Path('E:/HoudiniProject/Unity_Houdini_PCG_Track/.codex_tmp/sb_core_cleanup/rollback-core.cpio')
    c.saveItemsToFile(c.allItems(), str(backup))
    templates = a.parmTemplateGroup()
    lod_value = a.parm('lod_outputs_enabled').eval()
    try:
        for name, code in rewritten.items():
            c.node(name).parm('snippet').set(code)
        for name in RETIRED:
            c.node(name).destroy()
        for note in c.stickyNotes():
            note.destroy()
        for box in c.networkBoxes():
            box.destroy()
        colors = [(0.23, .36, .46), (.24, .42, .34), (.39, .35, .23), (.39, .35, .23),
                  (.25, .39, .46), (.36, .28, .43), (.33, .34, .35), (.22, .39, .39), (.26, .32, .45)]
        for (name, title, rect, entries, text), color in zip(STAGES, colors):
            x, y, w, h = rect
            b = c.createNetworkBox(name)
            b.setComment(title)
            b.setColor(hou.Color(color))
            b.setAutoFit(False)
            b.setPosition(hou.Vector2(x, y))
            b.setSize(hou.Vector2(w, h))
            for node_name, nx, ny in entries:
                n = c.node(node_name)
                n.setPosition(hou.Vector2(nx, ny))
                b.addItem(n)
            note = c.createStickyNote('NOTE_' + name)
            note.setText(text)
            note.setTextSize(.30)
            note.setSize(hou.Vector2(w-2, 3))
            note.setPosition(hou.Vector2(x+1, y+h-4))
            b.addItem(note)
        updated = a.parmTemplateGroup()
        lod = updated.find('lod_outputs_enabled')
        lod.hide(True)
        updated.replace('lod_outputs_enabled', lod)
        a.setParmTemplateGroup(updated)
        assert a.parm('lod_outputs_enabled').eval() == lod_value
        assert {n.name() for n in c.children()} == expected_names
    except Exception:
        # Restore the exact pre-edit network, including notes and node flags.
        c.deleteItems(c.allItems())
        c.loadItemsFromFile(str(backup))
        a.setParmTemplateGroup(templates)
        a.parm('lod_outputs_enabled').set(lod_value)
        raise
    return {'status': 'APPLIED', 'nodes': len(c.children()), 'stages': len(c.networkBoxes()),
            'saved': False, 'source_hashes': HASHES}
