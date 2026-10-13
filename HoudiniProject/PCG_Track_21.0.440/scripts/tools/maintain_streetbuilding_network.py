"""Incremental human navigation and native SOP maintenance; never saves assets.

The current captured network is the input. This module is not a builder.
Public templates, instance values, node names, and output slots are protected.
"""
import hashlib
import json
from pathlib import Path

ROOT = Path('E:/HoudiniProject/Unity_Houdini_PCG_Track')
TASK = ROOT / '.codex_tmp/streetbuilding-maintenance-20261013'
KEEP = 'P orient scale unity_instance instance_prefix name building_id face_index floor_index cell_index module_span selection_seed module_role module_variant surface_role facade_band is_building_entrance is_shop_entrance lod chunk_id pcg_kind pcg_variant preview_missing preview_size'.split()
NATIVE = {
 'front': ('DIRECT_UNITY_INSTANCE_FACADE', 'FRONT', '@facade_target>1', 'front_and_secondary_instances'),
 'side': ('BUILD_DIRECT_SIDE_REAR_INSTANCES', 'SIDE_REAR', '@facade_target<2', 'side_and_rear_instances'),
}
DESCRIPTIONS = {
 'EMPTY_GEOMETRY': ('空几何源：生成器从这里开始，不是待删除的空节点。', '多个生成器及兼容空输出依赖本节点；保持零点零面。'),
 'IN_SITE_PARCELS': ('输入 1：闭合地块面；保留 building_id 和显式地块覆盖。', '日常入口：HDA 地块来源 site_source；外部输入有错误时必须报告，不能自动换成测试地块。'),
 'IN_FRONTAGE_GUIDES': ('输入 2：临街曲线；自然确定主正面与次正面。', '修改曲线后在 RESOLVE_FRONTAGES 的 Primitive 表查看 front_edge / secondary_front_edge。'),
 'IN_MODULE_LIBRARY': ('输入 3：外部代理模块库；属于素材输入。', '仅灰模分支使用；正式素材实例使用 unity_style_catalog，不能把此输入当作生成配额。'),
 'INTERNAL_TEST_PARCEL': ('生成测试地块：矩形或四角 L 形。', 'Detail；输入0为空。输出 polygon，prim int building_id、string massing_shape/notch_side。入口：building_width/depth（m）、massing_shape、l_notch_*（格/米）。保持至少一格翼墙；到 SELECT_SITE_SOURCE 查看平面轮廓。'),
 'SELECT_SITE_SOURCE': ('选择测试地块或外部地块，明确保留两条分支。', 'input 表达式连接 HDA site_source；不要用 Bypass 删除未选中的分支。'),
 'CANONICALIZE_PARCELS': ('地块校验：压平 XZ、处理闭合重复点、统一绕序并保留显式属性。', 'Detail；输入0空几何，输入1原始地块。输出 polygon 和 prim source_prim/building_id/floor_count/seed。保留 VEX：每个地块的拓扑与绕序、源属性映射需要一起验证；普通 Clean 会改变此语义。阈值 1e-5m 是数值容差，面积 0.01m² 是退化判定，不是日常美术入口。'),
 'RESOLVE_FRONTAGES': ('识别临街方向，生成稳定建筑编号与楼层/种子。', 'Detail；输入0规范地块，输入1引导曲线。写 prim int front_edge/secondary_front_edge/rear_edge/building_id/floor_count/seed。保留 VEX：道路距离、边法线与拓扑邻接共同决定朝向。入口：输入2曲线、floor_count、variation_seed；查看 Primitive 表；扩展新道路规则须测编号和四角 L 形。'),
 'PARSE_UNITY_INSTANCE_CATALOG': ('只解析素材规格与候选目录；不继承生成数量。', 'Detail；输入0空几何；读取 HDA unity_style_catalog。写 detail float style_cell_width/style_ground_height/style_typical_height，string catalog_payload/catalog_raw。保留 VEX：版本无关的素材行校验和规格解析；楼层高度由素材规格决定。隐式读取 PARSE_GENERATION_RULES/effective_ground_use 以处理住宅首层高度；不得增加生成配额。'),
 'PARSE_GENERATION_RULES': ('实例面板是基础生成规则来源，再应用显式局部/地块覆盖。', 'Detail；输入0带临街属性的地块，输入1空几何。写 detail effective_*（float/int）、rule_payload_*（string）。入口：体块、首层用途、楼层数、各生成开关；查看 Detail 中 rule_source 和 effective_*。保留 VEX：覆盖优先级与迁移边界不能拆成不透明路径引用；隐藏旧风格字段无生成语义。'),
 'BUILD_FACADE_CELLS': ('将矩形/L 形分成可追踪的立面格点。', 'Detail；输入0有效规则，输入1素材规格。输出 points：int facade_target/face_index/floor_index/cell_index/run_*，vector placement_origin/right/outward，float placement_yaw。保留 VEX：四角凹口与同方向分段的共享编号。入口：建筑宽深（按 style_cell_width 对齐）、楼层数、缺口格数；查看 Point 表。'),
 'ALLOCATE_FACADE_CAPACITY': ('先确定门位，再按连续剩余空间分配窗，最后填墙。', 'Detail；输入0立面格点。写 point 请求/实际数量与规划角色；detail upper_window_report/ground_shopfront_report/rule_report。入口：facade_layout_mode、window_count_min/max、shopfront_quantity_mode/count、商业门数量。单双宽均为一个模块；标准层额度按每层每物理立面，L 形同方向分段共享。保留 VEX：容量压缩与连续占格求解；不得偷偷改写实例请求值。'),
 'SELECT_FACADE_VARIANTS': ('按素材适用范围、权重和确定性种子选择实例变体。', 'Detail；输入0容量记录，输入1目录。输出 point string unity_instance/module_role/module_variant、quaternion orient、vector scale 和预览标记。保留 VEX：候选匹配、跨格模块和墙体回退；入口是素材候选及 layout_seed，不能在此增加数量。检查资产路径、占格与朝向。'),
 'SELECT_FACADE_MODULES': ('完成对齐、居中、连续、对称等排列，不增加数量。', 'Detail；输入0已选择实例，输入1容量记录。调整 point P/arrangement_*，写 detail arrangement_report。入口：facade_rhythm（标准层）、ground_rhythm（首层）。保留 VEX：连续片段和对称变体约束；查看 Point P 和 Detail 降级原因。附件输入2依赖最终墙面，修改后须验证墙挂支撑。'),
 'DIRECT_UNITY_INSTANCE_FACADE': ('正面/次正面输出边界：原生 SOP 过滤后只写角色 metadata。', 'Detail；输入0来自 FRONT_INSTANCE_ATTRIBUTES，保留点顺序与 Unity 实例 schema；写 detail string output_role。筛选和属性白名单在上游 Blast / Attribute Delete 参数中可见。兼容路径保留；不要把属性清理重新塞回生成算法。'),
 'BUILD_DIRECT_SIDE_REAR_INSTANCES': ('侧面/背面输出边界：原生 SOP 过滤后只写角色 metadata。', 'Detail；输入0来自 SIDE_REAR_INSTANCE_ATTRIBUTES；写 detail string output_role。facade_target>=2 的筛选与属性白名单在上游节点；背面生成入口是 rear_facade_mode。检查四角 L 形边界与物理立面共享配额。'),
 'BUILD_DIRECT_ROOF_INSTANCES': ('按建筑有效轮廓生成屋顶实例，避开 L 形缺口。', 'Detail；输入0素材目录；相对路径读取 PARSE_GENERATION_RULES 的 effective_*。输出 point P/orient/scale/unity_instance/module_role。入口：roof_enabled 与素材 RoofSurface。保留 VEX：网格铺设、候选匹配与凹口覆盖；看屋顶俯视及 Point 表，不能把缺口填满。'),
 'BUILD_DIRECT_ROOF_EDGE_INSTANCES': ('生成女儿墙、转角与屋顶边缘，保持外边界连续。', 'Detail；输入0目录；相对路径读取 PARSE_GENERATION_RULES。输出实例点；入口 parapet_enabled、parapet_height（m）、architectural_trim_enabled。保留 VEX：凹凸角类型与朝向、闭合边界分段；看顶视图和 module_role，扩展独立角模块后验证四角缺口。'),
 'SELECT_ATTACHMENT_MODULES': ('整理显式附件覆盖、楼层范围、立面 mask 和预算。', 'Detail；输入0有效规则。写 detail layer_attachment_*（density float，max/mask/from/to int，source string）。入口：各 *_density（0..1）、*_max_count（每栋）、attachments_enabled；总密度与单类密度共同作用。保留 VEX：覆盖优先级与楼层索引；素材适配约束不能反向覆盖实例配额。'),
 'DETAIL_INSTANCE_POINTS': ('在实际墙体或屋顶支撑面上放置附件。', 'Detail；输入0目录，输入1附件规则，输入2最终墙体实例。输出 points 的 P/orient/scale/unity_instance、attachment_host_*，detail 各类数量。保留 VEX：墙挂 AC 连续实墙支撑、凹口包含与屋顶落地约束。入口各附件密度/数量；独立 OUT_DETAIL_INSTANCES，扩展新附件必须保留支撑检查和 64 个/栋预算。'),
 'RESOLVE_MASSING': ('计算代理建筑高度，复用素材楼层高度。', 'Detail；输入0规则；相对路径读取目录 style_*_height。写 prim float building_height/parapet_height、int chunk_id；写 detail 楼层高度。入口 floor_count（含首层）；本节点是代理/metadata 支路，正式实例由立面格点驱动。短 VEX 保留：跨元素级别的尺寸映射集中一处，避免重复计算。'),
 'RESOLVE_FACADE_GRAMMAR': ('灰模兼容立面语法：代理门窗、邻接墙与首层用途。', 'Detail；输入0体块面。写 prim bay_count/entrance_bay/shopfront_bays/ground_use/facade_rhythm/wall_surface_id 等。保留 VEX：旧代理语法和共享墙关系；生成实例的精确配额入口在 ALLOCATE_FACADE_CAPACITY。修改代理语法时同时看内部代理与外部模块输入3。'),
 'VALIDATE_MODULE_LIBRARY': ('验证输入3模块用途、尺寸和原生网格标记。', 'Detail；输入0外部代理模块库；写 detail 有效标记和尺寸。保留 VEX：输入库兼容校验；素材变化后看这里的 errors 与 Detail。不要删除：当前 Switch 未选中不代表输入3兼容分支无用。'),
 'BUILD_LOD0': ('生成可编辑灰模主模型；技术名保留以兼容 Unity。', 'Detail；输入0空，输入1代理语法，输入2外部模块库；隐式读取素材楼层高度。输出 polygon/packed 模块及 prim unity_material、surface_role、building_id 等。保留 VEX：开口、共享墙、外部模块变换和语义面生成相互约束，强行展开会改变拓扑/顺序与兼容性。日常尺寸、用途和素材从实例/输入调整；算法扩展须比 UV、法线、绕序、材质和无底面合约。'),
 'NORMAL_LOD0': ('原生 Normal SOP：代理主模型的法线入口。', '输入灰模主模型；参数 cuspangle 控制折角（度）。只影响代理法线，不改变素材实例的 mesh。调整后检查 outward normals 与 Unity 预览；保留原有参数。'),
 'MERGE_DIRECT_BUILDING_INSTANCES': ('汇合正面、侧后、屋顶和屋顶边缘四条实例分支。', '输入0..3 顺序保持稳定；向正式实例、缺件预览和 metadata 分流。不要把预览方块混入正式 Bake。'),
 'FILTER_REAL_INSTANCES': ('正式实例边界：剔除缺件后记录剔除数量。', 'Detail；输入0原生过滤/清理后的点，输入1过滤前的汇合点。只写 detail int preview_missing_count=npoints(1)-npoints(0)，无逐点遍历。删除条件在 REAL_INSTANCE_FILTER；去掉预览属性在 REAL_INSTANCE_ATTRIBUTES。输入1是可见计数依据，不是隐藏路径。'),
 'PREVIEW_MISSING_MODULES': ('缺件可视化：将缺失槽显示为灰色预览盒。', 'Detail；输入0过滤前实例点。输出 polygon、prim unity_material/preview_slot，detail streetbuilding_preview_only；删除 unity_instance。保留 VEX：按缺件实际尺寸生成六面盒，并隔离真实实例 metadata；改为 Copy to Points 会改变既有拓扑/属性顺序，当前无日常编辑收益。入口 preview_missing_modules；仅 OUT_BUILDING_PREVIEW，不可 Bake。'),
 'VALIDATE_DIRECT_BUILDING_INSTANCES': ('校验主体实例、实际数量、有效变换和预算。', 'Detail；输入0正式点；相对路径读取规则/目录/容量。写 detail 输出契约；错误必须保留。保留 VEX：逐实例和每物理立面数量的独立校验。它不是生成器；调整数量后同时检查报告与最终 module_role。'),
 'VALIDATE_DIRECT_DETAIL_INSTANCES': ('单次校验附件路径、朝向、支撑和每栋预算。', 'Detail；输入0附件点。整表仅扫描一次，空点输入直接返回以保留旧空输出 schema。检查 unity_instance/orient/scale、目录与实际墙面，写 detail 输出信息。保留 VEX：实例级兼容与支撑校验；更改后验证空输出、四角缺口与 64 个/栋上限。'),
 'LOD0_MODULE_SOURCE_SWITCH': ('选择代理 mesh 或真实素材实例点，二者都保留。', 'input 表达式读取 HDA module_source；输出0正式主模型。缺件预览是单独的输出6。'),
 'DETAIL_MODULE_SOURCE_SWITCH': ('素材实例模式才输出附件；灰模附件槽为空。', 'input 表达式读取 module_source；输出3。不要通过当前 Switch 位置推断上游无用。'),
 'METADATA_ATTACHMENT_INPUTS': ('收集附件诊断与主体缺件记录，保证空附件仍有诊断。', '输入0主体点，输入1附件点，输入2附件规则；BUILD_METADATA 的输入3依赖 detail 信息。保留所有输入顺序和可选分支。'),
 'BUILD_METADATA': ('输出可审计的规则来源、请求/实际数量与缺件诊断。', 'Detail；输入0空，输入1代理语法，输入2容量，输入3汇合诊断。输出 metadata points 与 detail report。保留 VEX：跨分支汇总不是几何生成，不能只看点数验证。查看 OUT_BUILDING_METADATA 的 Point/Detail 表；新诊断从这里追加，不改变已有字段。'),
}
for name, slot, role in [('OUT_BUILDING_LOD0',0,'正式主模型/素材实例'),('OUT_BUILDING_LOD1',1,'兼容空槽'),('OUT_BUILDING_LOD2',2,'兼容空槽'),('OUT_DETAIL_INSTANCES',3,'独立附件实例'),('OUT_BUILDING_COLLISION',4,'兼容空槽'),('OUT_BUILDING_METADATA',5,'数量/来源/缺件诊断'),('OUT_BUILDING_PREVIEW',6,'缺件预览，禁止 Bake')]:
 DESCRIPTIONS[name] = (f'稳定输出 {slot}：{role}。', '输出编号、技术名和上游引用受累计合约保护；中键/Geometry Spreadsheet 查看，不新增运行时 Houdini 依赖。')

NOTES = {
 '00_INPUT_VALIDATE': '阅读导航：沿主线向下，旁支为灰模/附件；技术名保持稳定。\n职责：选择并校验地块。输入：HDA 1地块/2临街/3代理素材。输出：规范地块。\n修改：先回到 HDA 面板调宽深、楼层、用途；中键看节点说明，Spreadsheet 看属性。\n扩展：保留输入校验与稳定编号；空槽/未选分支有兼容用途。',
 '10_RULES_AND_CATALOG': '职责：临街识别、实例规则和素材目录。输入：地块/道路/实例/素材。\n输出：effective_* 和 style_*；生成数量来自实例，素材仅是候选与尺寸。\n修改：实例面板与输入2曲线；到 PARSE_GENERATION_RULES 的 Detail 看有效值/来源。\n扩展：显式局部/地块覆盖；目录因住宅高度读取规则，勿改成风格配额继承。',
 '20_FACADE_CAPACITY': '职责：格点与容量，先门→窗→填墙。输入：规则/素材规格。输出：请求/实际额度。\n修改：窗数按每层每物理立面，双宽也只算一个；L形同方向分段共享额度。\n查看：ALLOCATE_FACADE_CAPACITY 的 upper_window_report / ground_shopfront_report。\n扩展：新角色保持门优先、连续占格与容量压缩诊断。',
 '30_FACADE_SELECTION': '职责：素材变体选择与排列。输入：容量/目录。输出：最终放置实例点。\n修改：facade_rhythm/ground_rhythm 与 layout_seed；数量仍在实例面板。\n查看：Point 表的 module_role/module_variant/module_span/P；Detail arrangement_report。\n扩展：候选权重与适用范围；排列不得增加配额，墙挂附件依赖最终墙面。',
 '40_BUILDING_INSTANCES': '职责：正面、侧后、屋顶、边缘四支主体实例。输入：放置记录/目录。输出：实例点。\n修改：普通筛选看 Blast 的 Group，属性清理看 Attribute Delete 的 Point Attributes。\n屋顶入口 roof_enabled；女儿墙 parapet_enabled/height（m）；查看最终实例角色。\n扩展：保持四角L形覆盖/朝向；屋顶分支按相对路径读取有效规则，算法说明见中键。',
 '50_ATTACHMENT_INSTANCES': '职责：附件规则、选择与支撑放置。输入：规则/目录/实际墙面。输出：附件实例点。\n修改：*_density（0..1）与 *_max_count（每栋）；attachments_enabled 为总开关。\n查看：DETAIL_INSTANCE_POINTS 的 attachment_host_*、OUT_DETAIL_INSTANCES 和 metadata。\n扩展：新附件保持实墙/凹口/屋顶支撑检查及每栋64个总预算。',
 '60_PROXY_MODEL': '职责：灰模兼容语法、mesh 与原生法线。输入：规则/输入3素材。输出：代理主模型。\n修改：HDA 宽深/楼层/用途；NORMAL_LOD0 的 cuspangle（度）只影响代理法线。\n查看：BUILD_LOD0 的 primitive 材质/语义、NORMAL_LOD0 的 N；正式素材走右侧实例线。\n扩展：保留开口/共享墙/外部模块合约；BUILD_LOD0 技术名保留，不生成LOD1/2或碰撞。',
 '70_UNITY_CONTRACT': '职责：汇合、真实点过滤、预览隔离和诊断。输入：主体/附件/规则。输出：四条有效数据线。\n修改：正式过滤在 REAL_INSTANCE_FILTER；预览开关 preview_missing_modules。\n查看：OUT_BUILDING_METADATA 报告请求/实际/来源，预览盒只到 OUT_BUILDING_PREVIEW。\n扩展：新增诊断保持字段稳定；FILTER_REAL_INSTANCES 输入1用于精确计数。',
 '80_OUTPUT_VALIDATE': '职责：稳定 Unity 输出槽。输入：校验后的数据。输出：0主模型/3附件/5诊断/6预览。\n修改：1、2、4为空兼容槽；不要删其连线或把预览 Bake。\n查看：按输出名点亮 Display 或用 Spreadsheet；核对材质、朝向、实例与报告。\n扩展：正式新增输出必须更新累计合约和 Unity 桥接；移动端只消费 Bake 数据。',
}

def _expect_current(core,baseline=None):
 if baseline is None:baseline=json.loads((TASK/'disk-inspection.json').read_text(encoding='utf-8'))['targets'][0]
 for entry in baseline['nodes']:
  n=core.parent().node(entry['path'].split('/obj/StreetBuilding_DEV/')[-1])
  if n is None or n.type().name()!=entry['type']:raise RuntimeError('Captured node/type differs: '+entry['path'])
  s=entry['parms'].get('snippet')
  if s is not None and n.name() not in ('DIRECT_UNITY_INSTANCE_FACADE','BUILD_DIRECT_SIDE_REAR_INSTANCES','FILTER_REAL_INSTANCES','VALIDATE_DIRECT_DETAIL_INSTANCES'):
   if hashlib.sha256(n.evalParm('snippet').encode()).digest()!=hashlib.sha256(s.encode()).digest():
    raise RuntimeError('Non-target VEX changed: '+n.path())
 return baseline

def _layout(core, native=False):
 for name, texts in DESCRIPTIONS.items(): core.node(name).setComment('\n'.join(texts))
 for box in core.networkBoxes():
  if box.name() not in NOTES:raise RuntimeError('Unknown authored box; preserve it: '+box.name())
  note=core.findStickyNote('NOTE_'+box.name())
  if note is None:raise RuntimeError('Do not duplicate a missing authored note: '+box.name())
  note.setText(NOTES[box.name()]);note.setSize((24,3.4))
 core.findStickyNote('NOTE_60_PROXY_MODEL').setSize((20,3.4))
 # Reuse original anchors; only crowded consumer/merge rows move for native SOPs.
 positions={
  'DIRECT_UNITY_INSTANCE_FACADE':(2,-21),'BUILD_DIRECT_SIDE_REAR_INSTANCES':(13,-21),
  'BUILD_DIRECT_ROOF_INSTANCES':(2,-24),'BUILD_DIRECT_ROOF_EDGE_INSTANCES':(13,-24),
  'MERGE_DIRECT_BUILDING_INSTANCES':(2,-31),'FILTER_REAL_INSTANCES':(2,-38),
  'VALIDATE_DIRECT_BUILDING_INSTANCES':(2,-41),'PREVIEW_MISSING_MODULES':(14,-34),
  'VALIDATE_DIRECT_DETAIL_INSTANCES':(29,-33),'DETAIL_MODULE_SOURCE_SWITCH':(29,-40),
  'METADATA_ATTACHMENT_INPUTS':(37,-36),'BUILD_METADATA':(39,-40),
  'LOD0_MODULE_SOURCE_SWITCH':(-15,-41),
 }
 for name,position in positions.items():core.node(name).setPosition(position)
 for name in [n for n in DESCRIPTIONS if n.startswith('OUT_')]:
  n=core.node(name); n.setPosition((n.position()[0],-54))
 for name,position in {'NOTE_40_BUILDING_INSTANCES':(1,-10),'NOTE_70_UNITY_CONTRACT':(-23,-29),'NOTE_80_OUTPUT_VALIDATE':(-23,-47)}.items():core.findStickyNote(name).setPosition(position)
 for box in core.networkBoxes():box.fitAroundContents()

def _node(core,name,kind,parms,previous,box,pos,comment):
 n=core.node(name)
 if n is None:n=core.createNode(kind,name,run_init_scripts=False)
 if n.type().name()!=kind:raise RuntimeError('Existing native node has different type: '+name)
 n.setParms(parms);n.setInput(0,previous);n.setPosition(pos);n.setComment(comment)
 if n.parentNetworkBox()!=box:box.addItem(n)
 return n

def _parameter_state(parm):
 """Keep channel objects as well as text; rawValue alone loses animation."""
 frames=tuple(parm.keyframes())
 try:expression=parm.expression();language=parm.expressionLanguage()
 except Exception:expression=None;language=None
 return dict(raw=parm.rawValue(),keyframes=frames,
  keyframe_codes=tuple(frame.asCode() for frame in frames),
  expression=expression,language=language)

def _restore_changed_parameters(node,states):
 # Only changed channels are written. Unrelated authored expressions/animation
 # must not be rewritten merely because another node failed its precondition.
 for name,state in states.items():
  parm=node.parm(name)
  actual=_parameter_state(parm)
  if all(actual[key]==state[key] for key in ('raw','keyframe_codes','expression','language')):continue
  parm.deleteAllKeyframes()
  if state['keyframes']:parm.setKeyframes(state['keyframes'])
  elif state['expression'] is not None:
   parm.setExpression(state['expression'],language=state['language'])
  else:parm.set(state['raw'],follow_parm_reference=False)

def _restore_box_membership(item,box):
 current=item.parentNetworkBox()
 if current==box:return
 if current is not None:current.removeItem(item)
 if box is not None:box.addItem(item)

def apply(hou, phase='navigation', save=False, core_path='/obj/StreetBuilding_DEV/StreetBuildingCore', baseline=None):
 if save:raise RuntimeError('Saving is owned by VerifyFull, not this maintenance script')
 core=hou.node(core_path)
 if core is None:raise RuntimeError('Captured live target is missing')
 # The optional target/baseline are for an isolated cumulative-validator
 # instance; normal Live migration still uses this task's Capture inspection.
 baseline=_expect_current(core,baseline)
 before={n.name():dict(position=n.position(),comment=n.comment(),inputs=[(c.inputIndex(),c.inputNode(),c.outputIndex()) for c in n.inputConnections()],parms={p.name():_parameter_state(p) for p in n.parms()},box=n.parentNetworkBox(),display=n.isDisplayFlagSet(),render=n.isRenderFlagSet()) for n in core.children()}
 before_notes={n.name():(n.text(),n.position(),n.size(),n.parentNetworkBox()) for n in core.stickyNotes()}
 before_boxes={b.name():(b.position(),b.size()) for b in core.networkBoxes()}
 try:
  with hou.undos.group('StreetBuilding human maintenance: '+phase):
   if phase=='navigation':_layout(core)
   elif phase in NATIVE:
    target_name,tag,group,role=NATIVE[phase]
    target=core.node(target_name)
    old=next(n['parms']['snippet'] for n in baseline['nodes'] if n['path'].endswith('/'+target_name))
    replacement='// '+old.splitlines()[0].removeprefix('// ')+'\n// Detail：原生筛选/清理后的点；只写 string detail output_role。\ns@output_role="'+role+'";'
    if target.evalParm('snippet') not in (old,replacement):raise RuntimeError('Consumer precondition hash mismatch: '+target_name)
    box=core.findNetworkBox('40_BUILDING_INSTANCES'); x=2 if phase=='front' else 13
    previous=core.node('SELECT_FACADE_MODULES')
    for name,kind,parms,y,comment in [
     (tag+'_TARGET_FILTER','blast',dict(group=group,grouptype='points'),-15,'原生立面筛选：Group 使用 point int facade_target；保留点顺序。正面0/次正面1；侧面2/背面3。'),
     (tag+'_POINTS_ONLY','blast',dict(group='*',grouptype='prims'),-17,'原生移除 primitive：正式实例边界只允许点。防御性清理与原 removeprim(...,1) 一致；正常上游已经没有面。'),
     (tag+'_INSTANCE_ATTRIBUTES','attribdelete',dict(ptdel='* '+' '.join('^'+k for k in KEEP),primdel='*',vtxdel='*',updatevar=0),-19,'原生实例属性白名单：Point Attributes 中 ^ 表示保留；Primitive/Vertex 删除全部，Detail 保留。扩展 Bake 字段时更新累计 schema 合约。')]:
     previous=_node(core,name,kind,parms,previous,box,(x,y),comment)
    target.setInput(0,previous);target.parm('snippet').set(replacement)
   elif phase=='detail_validation':
    target=core.node('VALIDATE_DIRECT_DETAIL_INSTANCES')
    old=next(n['parms']['snippet'] for n in baseline['nodes'] if n['path'].endswith('/VALIDATE_DIRECT_DETAIL_INSTANCES'))
    marker='// STREETBUILDING_V6_1_VALIDATE_DETAILS'
    if old.count(marker)!=1:raise RuntimeError('Detail validator marker differs from Capture')
    replacement=old.replace(marker,marker+'\n// 整表仅校验一次；空输入保留原 Point 运行级别的无执行语义。\nif (npoints(0)==0) return;',1)
    if target.evalParm('snippet') not in (old,replacement):raise RuntimeError('Detail-validation precondition hash mismatch')
    target.setParms({'class':'detail','snippet':replacement})
   elif phase=='real':
    target=core.node('FILTER_REAL_INSTANCES')
    old=next(n['parms']['snippet'] for n in baseline['nodes'] if n['path'].endswith('/FILTER_REAL_INSTANCES'))
    replacement='// Detail：输入0过滤后，输入1过滤前；无逐点遍历。\ni@preview_missing_count=npoints(1)-npoints(0);'
    if target.evalParm('snippet') not in (old,replacement):raise RuntimeError('Real-filter precondition hash mismatch')
    box=core.findNetworkBox('70_UNITY_CONTRACT');merge=core.node('MERGE_DIRECT_BUILDING_INSTANCES')
    f=_node(core,'REAL_INSTANCE_FILTER','blast',dict(group='@preview_missing!=0',grouptype='points'),merge,box,(2,-34),'正式 Bake 点过滤：删除 point int preview_missing 非零的缺件标记；条件可在 Group 中查看。预览分支仍从过滤前 Merge 读取。')
    a=_node(core,'REAL_INSTANCE_ATTRIBUTES','attribdelete',dict(ptdel='preview_missing preview_size',updatevar=0),f,box,(2,-36),'正式实例去掉预览专用 point 属性；其他属性和所有 detail 诊断保持不变。不要改成清空全部属性。')
    target.setInput(0,a);target.setInput(1,merge);target.parm('snippet').set(replacement)
   else:raise RuntimeError('Unknown phase: '+phase)
   # Node creation must not steal the authored display/render output flags.
   for name,s in before.items():
    if s['display']:core.node(name).setDisplayFlag(True)
    if s['render']:core.node(name).setRenderFlag(True)
   for box in core.networkBoxes():box.fitAroundContents()
 except Exception:
  for name,s in before.items():
   n=core.node(name);_restore_changed_parameters(n,s['parms'])
   n.setComment(s['comment'])
   current=[(c.inputIndex(),c.inputNode(),c.outputIndex()) for c in n.inputConnections()]
   if current!=s['inputs']:
    for i in range(len(n.inputs())):n.setInput(i,None)
    for i,source,out in s['inputs']:n.setInput(i,source,out)
   _restore_box_membership(n,s['box'])
  for n in list(core.children()):
   if n.name() not in before:n.destroy()
  for name,(text,position,size,box) in before_notes.items():
   _restore_box_membership(core.findStickyNote(name),box)
  # Moving a Network Box moves its members in HOM. Restore containers first,
  # then each authored member's exact position to avoid a second translation.
  for name,(position,size) in before_boxes.items():
   box=core.findNetworkBox(name);box.setPosition(position);box.setSize(size)
  for name,(text,position,size,box) in before_notes.items():
   note=core.findStickyNote(name);note.setText(text);note.setPosition(position);note.setSize(size)
  for name,s in before.items():
   core.node(name).setPosition(s['position'])
   if s['display']:core.node(name).setDisplayFlag(True)
   if s['render']:core.node(name).setRenderFlag(True)
  raise
 return dict(phase=phase,nodes=len(core.children()),boxes=len(core.networkBoxes()),notes=len(core.stickyNotes()),saved=False)
