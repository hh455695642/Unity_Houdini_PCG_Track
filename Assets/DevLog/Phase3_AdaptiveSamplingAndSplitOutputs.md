# Phase 3 开发日志：质量约束自适应采样与道路分层输出

> 文档类型：Phase 3 增量开发日志
>
> 记录日期：2026-07-15
>
> 关联提交：`290457b`（提交说明：`3`）
>
> 基线版本：Phase 2 功能提交 `9404214`，Phase 2 日志提交 `73ac45d`
>
> 记录范围：只记录提交 `290457b` 相对 Phase 2 新增、调整、替换或移除的内容

## 1. 日志范围与证据

本文不是项目全量快照。Unity/URP/Houdini 版本、Unity Knot Contract V1、Spline 自动 Recook、道路 Banking、Profile/Sweep、Shader 与移动端通用约束以 Phase 1、Phase 2 日志为准。

证据标记：

- **[已验证]**：通过 Git 提交差异、当前 Houdini MCP 强制 Cook、Unity MCP、场景 YAML 或输出 Geometry 直接确认。
- **[提交已实现]**：实现已进入 `290457b`，但本次没有运行会创建临时节点的完整回归脚本。
- **[待复验]**：已有接口或实现，仍缺干净 Houdini Engine Session、Bake、极端样例或移动端真机验证。
- **[输出预留]**：输出节点和数据契约已经建立，但当前没有实际几何，不按已完成功能计算。

`290457b` 只修改 4 个文件：

| 文件 | 主要内容 |
|---|---|
| `Assets/PCG/HDA/Track.hda` | Road Subnet、自适应采样、UV/材质契约、分层输出和 HDA 参数界面 |
| `HoudiniProject/PCG_Track_21.0.440/PCG_Bike_Track.hip` | 当前 Track 实例、Road 网络和输出现场 |
| `Assets/PCG/Scenes/PCG.unity` | 启用 Knot 上传/自动 Recook，序列化新的道路、路肩和碰撞输出 |
| `HoudiniProject/PCG_Track_21.0.440/scripts/tools/verify_curve_road_test.py` | 自适应采样、闭环、材质和分层输出回归契约 |

本提交没有新增或修改 C#、Shader、RendererFeature、RenderPass、RenderTexture、Compute Shader 或运行时 Houdini 依赖。

## 2. Phase 3 提交概览

| 模块 | 本阶段增量 | 当前状态 |
|---|---|---|
| 曲线采样 | 由单一均匀采样扩展为“基础间距 + 质量阈值 + 强制锚点”的自适应采样 | [已验证] |
| 质量指标 | 增加弦误差、Heading、Grade、Bank、最小间距和细节密度约束 | [已验证] |
| UV3 | 从世界 XZ 投影改为沿道路弧长/横向米制坐标 | [已验证] |
| 材质段 | 改为弧长米制过渡、固定锚点、后段覆盖前段和闭环跨缝语义 | [提交已实现] |
| Road 架构 | 将道路节点封装进独立 `Road` Subnet，并按 7 个 Network Box 组织 | [已验证] |
| Unity 输出 | 增加路面、路肩、裙边、碰撞和数据中心线的独立 Output Contract | [已验证] |
| 裙边 | 已有独立输出和分组契约，当前输出 0 Primitive | [输出预留] |
| Unity 场景 | 正式启用 Knot Contract 上传和事件驱动自动 Recook，提交分层输出结果 | [已验证] |
| 验证脚本 | 新增自适应密度、闭环接缝、材质段和分层输出测试 | [提交已实现；本次未全量执行] |

## 3. 质量约束自适应采样

### 3.1 节点链与职责

**状态：[已验证]**

Road 中新增独立采样模块：

```text
CENTERLINE_source_switch
  -> CENTERLINE_quality_reference_resample
  -> CENTERLINE_quality_metrics
  -> CENTERLINE_collect_forced_samples
  -> CENTERLINE_adaptive_select
  -> CENTERLINE_sampling_switch
  -> FRAME_normalize_authored_up
```

- `CENTERLINE_quality_reference_resample`：生成高密度参考曲线，只用于质量评估，不直接作为最终输出。
- `CENTERLINE_quality_metrics`：计算弦误差、方向变化、坡度变化、Bank 变化和闭环 Frame 质量。
- `CENTERLINE_collect_forced_samples`：收集 Knot、材质段边界及混合边界等不可被简化的锚点。
- `CENTERLINE_adaptive_select`：在 `sample_spacing` 基础样本上按质量阈值递归补点，同时尊重最小间距。
- `CENTERLINE_sampling_switch`：Feature Toggle；关闭自适应采样时回退到 Phase 2 的均匀 `CENTERLINE_resample`。

`sample_spacing` 仍是普通路段的主密度控制。自适应分支只在弯曲、坡度、Bank 或强制锚点要求更高时增加采样，避免为了局部复杂区域全局加密整条赛道。

### 3.2 HDA 参数

**状态：[已验证]**

| 参数 | 默认值 | 职责 |
|---|---:|---|
| `enable_adaptive_sampling` | On | 自适应采样总开关 |
| `adaptive_detail_density` | 1.0 | 统一缩放质量阈值；0.25–2.0 |
| `adaptive_min_spacing_m` | 1.0 m | 自适应补点的最小间距下限 |
| `adaptive_max_chord_error_m` | 0.10 m | 最大弦误差 |
| `adaptive_max_heading_delta_deg` | 8° | 相邻样本最大方向变化 |
| `adaptive_max_grade_delta_deg` | 4° | 相邻样本最大坡度变化 |
| `adaptive_max_bank_delta_deg` | 2° | 相邻样本最大倾角变化 |

细节密度只作用于自适应质量阈值：弦误差按 `density²` 缩放，Heading/Grade/Bank 阈值按 `density` 缩放。完全直线仍由 `sample_spacing` 控制，不会仅因提高细节密度而无意义增点。

本阶段没有保留 `adaptive_max_point_count`。当最小间距阻止质量阈值继续满足时，通过 `road_adaptive_constraint_floor_hit_count` 报告，而不是静默丢弃约束。该设计避免结果依赖任意点数上限，但极端曲线仍可能产生较高的编辑器 Cook 和 Mesh 顶点成本。

### 3.3 新增自适应数据契约

**状态：[已验证]**

主要 Detail Metadata：

- 参考与输出：`road_adaptive_reference_count`、`road_adaptive_base_count_estimate`、`road_adaptive_output_count`、`road_adaptive_refine_count`。
- 强制锚点：`road_knot_anchor_count`、`road_material_anchor_count`、`road_adaptive_forced_selected_count`。
- 有效阈值：`road_adaptive_effective_chord_error_m`、`road_adaptive_effective_heading_delta_deg`、`road_adaptive_effective_grade_delta_deg`、`road_adaptive_effective_bank_delta_deg`。
- 诊断：`road_adaptive_refinement_ratio`、`road_adaptive_constraint_floor_hit_count`、`road_adaptive_quality_profile`。

Point 侧增加 `road_force_sample`、`road_force_priority`、`unity_segment_index` 和 `unity_segment_u`，用于稳定保留 Knot/材质锚点并追踪原始 Bezier Segment。

## 4. UV3 与材质段契约调整

### 4.1 UV3 改为道路局部米制坐标

**状态：[已验证；移动端视觉待测]**

Phase 2 的 UV3 世界 XZ 米制投影被替换为：

```text
road_surface_uv_mode = arc_length_lateral_metric
UV3.x = 道路横向米制距离
UV3.y = 沿各道路列累计的表面弧长
```

该坐标继续进入 Unity Mesh UV2 / Shader `TEXCOORD2`，不改变 Shader 属性接口：

- UV0 继续负责车道线等方向性纹理。
- UV3 继续供非方向性路面层的 `_UseLowDistortionUV` uniform 使用。
- 不新增 Shader keyword、Variant、纹理采样、Pass 或中间 RT。

相对世界 XZ 投影，新契约可覆盖坡道和非水平赛道，并保持道路横向/纵向都以米为单位；代价是 HDA 需要为每个横向列累计表面距离，Cook 计算略增。

### 4.2 材质段改为弧长米制混合

**状态：[提交已实现；复杂组合待全量回归]**

新增/明确的契约：

- `road_material_blend_space = arc_length_meters`。
- Start/End 仍以 0–1 赛道参数编辑，但混合宽度使用 `Start/End Blend Distance (m)`。
- 材质 Start、End 和混合边界成为自适应采样强制锚点，不受 `adaptive_detail_density` 改变。
- 多段重叠时采用 `road_material_segment_order = later_overrides_earlier`。
- `Cd.rgb` 始终归一化，避免多层权重相加超过 1。
- 开放曲线中 `Start > End` 记为无效段并计入 `road_segment_invalid_count`；闭环曲线中相同配置表示跨接缝区间。
- `road_material_undersampled_transition_count` 用于报告受最小间距限制而采样不足的过渡。

这不是恢复 Phase 1 的独立 `CENTERLINE_material_segment_samples` 节点；材质锚点已并入统一自适应采样模块，旧 `road_material_boundary_sample_count` 契约仍被禁止。

## 5. Road Subnet 与 HDA 接口整理

### 5.1 模块封装

**状态：[已验证]**

Track 顶层当前只保留一个直接子模块：

```text
/obj/Track1
  -> Road
```

`Road` 内有 53 个直接子节点，按职责划分为 7 个 Network Box：

1. `BOX_01_CURVE_SOURCE`：Unity Contract、方向和 Bezier 重建。
2. `BOX_02_SAMPLING`：均匀/自适应采样、质量指标和 Frame 归一化。
3. `BOX_03_PROFILE_SWEEP`：Profile 与 Sweep。
4. `BOX_04_LAYOUT_BANKING`：布局、Grade/Banking 和 Debug Frame。
5. `BOX_05_TOPO_MATERIAL`：拓扑、UV、分组、法线、材质 Mask 和 metadata。
6. `BOX_06_OUTPUTS`：分层 Geometry 输出。
7. `BOX_07_START_PREFAB`：起终点 Prefab 实例输出。

网络保留一个 `ROAD_PIPELINE_GUIDE` Sticky Note；验证脚本要求每个节点和 Network Box 都有有效注释，且全部节点恰好归入一个模块。核心生成逻辑仍是可读 SOP/VEX 节点网络，没有改回 Python builder 黑盒。

### 5.2 参数界面收敛

**状态：[已验证]**

HDA 顶层参数整理为 `Curve`、`Track Shape`、`Road Banking`、`Material` 和 `Fallback Curve` 等职责文件夹，并增加中英文采样/质量标签。

本阶段移除以下实验性或重复接口：

- `adaptive_max_point_count`
- `adaptive_refine_material_blends`
- `closed_loop_mode`
- `enable_closed_loop_twist_correction`
- `frame_transport_mode`
- `min_shoulder_scale`
- `skirt_unity_material`

闭环状态继续来自 Unity Knot Contract/输入曲线事实，不再由独立 HDA Toggle 覆盖。裙边若后续生成，材质继承 `road_unity_material`，避免增加无必要的接口组合。

当前 HDA 的 `road_width` 默认值和现场值均为 20 m；这属于 Phase 3 当前资产接口事实，后续若要恢复更窄的默认竞速路宽，应作为显式参数变更单独提交。

## 6. Unity 分层输出契约

### 6.1 输出模式与索引

**状态：[已验证]**

新增 `road_output_mode`：

- `Combined Legacy`：Output 0 保持旧的合并渲染几何，供兼容和验证使用。
- `Split Quality`：Output 0 只输出主路面；当前默认值为 `Split Quality`。

固定输出索引：

| Output | 节点 | `unity_output_name` | 职责 |
|---:|---|---|---|
| 0 | `OUT_ROAD_MESH` | `Road_Surface` | 主路面渲染 Mesh；Legacy 模式下为合并几何 |
| 1 | `OUT_START_PREFAB_INSTANCE` | — | 起终点 Prefab 实例点 |
| 2 | `OUT_ROAD_SHOULDERS` | `Road_Shoulders` | 左右路肩渲染 Mesh |
| 3 | `OUT_ROAD_SKIRTS` | `Road_Skirts` | 裙边输出契约 |
| 4 | `OUT_ROAD_COLLISION` | `Road_Collision` | 主路面 + 路肩碰撞 Mesh，不包含裙边 |
| 5 | `OUT_ROAD_CENTERLINE` | `Road_Centerline_Data` | 无 Primitive 的最终采样/Frame 数据 |

`road_source_quad` 为拆分前每个四边形提供稳定来源 ID。验证契约要求：

- Road、Shoulder、Skirt 三个渲染集合互不重叠。
- 三者并集必须等于 Legacy 合并输出。
- Collision 必须等于 Road + Shoulder，且全部 Primitive 进入 `collision_geo`。
- Centerline 只输出点数据，`road_centerline_data_only = 1`，并使用 `unity_tag = EditorOnly`。

### 6.2 材质和碰撞分离

**状态：[已验证]**

- `road_unity_material` 默认指向 `Assets/PCG/Materials/M_PCG_Road.mat`。
- `shoulder_unity_material` 当前也指向同一材质，但已经是可独立替换的 HDA 参数。
- Skirt 继承 Road 材质，不增加独立参数。
- Unity 场景中主路面和路肩分别生成 `MeshRenderer + MeshFilter`。
- `MeshCollider` 已从主路面渲染对象移到独立 `Road_Collision` 对象，碰撞和渲染拓扑职责解耦。

当前 `OUT_ROAD_SKIRTS` 为 0 Point / 0 Primitive，Unity 不生成 Skirt 子对象。因此本阶段完成的是裙边输出契约，不代表裙边几何生成功能已经完成。

### 6.3 当前 Houdini 输出快照

**状态：[已验证]**

当前 fallback 曲线、20 m 路宽、Split Quality 模式下：

| 输出 | Points | Primitives | Vertices | 当前结果 |
|---|---:|---:|---:|---|
| `OUT_ROAD_MESH` | 30 | 28 | 84 | 主路面 |
| `OUT_ROAD_SHOULDERS` | 60 | 56 | 168 | 左右路肩 |
| `OUT_ROAD_SKIRTS` | 0 | 0 | 0 | 输出预留 |
| `OUT_ROAD_COLLISION` | 60 | 84 | 252 | 主路面 + 路肩碰撞 |
| `OUT_ROAD_CENTERLINE` | 15 | 0 | 0 | EditorOnly 数据中心线 |

## 7. Unity 场景接入变化

**状态：[已验证]**

`Assets/PCG/Scenes/PCG.unity` 在本提交中完成以下变化：

- `Spline` 上的 `TrackSplineHoudiniInputSettings.EnableKnotDataUpload` 从 Off 改为 On。
- `Track1` 上的 `TrackSplineHoudiniSync` 组件从 Disabled 改为 Enabled。
- `_autoCookOnSplineChanged = true`，Debounce 仍为 0.35 秒。
- Houdini Asset 内部名称从残留的 `Track10` 统一为 `Track1`。
- HDA 引用继续指向 `Assets/PCG/HDA/Track.hda`，GUID 未改变。
- 提交新的 Road Surface、Road Shoulders 和 Road Collision 场景对象。
- Road Surface/Shoulders 使用 `M_PCG_Road.mat`；Road Collision 只包含 `MeshCollider`。
- HDA 已识别 `OUT_ROAD_SKIRTS` 和 `OUT_ROAD_CENTERLINE`，但两者当前没有可实例化的渲染 Primitive。

场景序列化的上传诊断仍为 `0 Spline / 0 Knot / Not uploaded in this editor domain`。这些字段是 Editor Domain 运行诊断，不应据此否定 `EnableKnotDataUpload = 1`；提交只保证 Feature 已正式启用，实际上传仍需在干净 Houdini Engine Session 中复验。

## 8. 验证脚本增量

**状态：[提交已实现；本次未全量执行]**

`verify_curve_road_test.py` 新增或扩展：

- HDA 参数默认值、文件夹顺序、中英文 Header 和已移除接口检查。
- Road 53 节点、7 个 Network Box、Sticky Note、连接、Output Index 和注释完整性检查。
- 500 m 直线下 `sample_spacing` 主导密度、自适应不产生无意义加密。
- 发卡弯在弦误差/Heading 约束下自动补点，且不产生车道重叠。
- `adaptive_detail_density` 在弯道、坡度和 Bank 变化上产生单调密度变化。
- 最小间距触发时写入约束下限诊断，不使用已移除的点数上限诊断。
- 材质强制锚点不随细节密度变化。
- 开放曲线无效材质段、重叠段后者覆盖、RGB 权重归一化。
- 闭环材质段跨接缝、闭环 UV 跨度、接缝位置、Frame 连续性和残余 Twist。
- Unity Knot Roll 跨 ±180° 解包与最大 Bank Clamp。
- Legacy 合并输出与 Split Road/Shoulder/Skirt/Collision 的集合一致性。
- Centerline 必须为无 Primitive、EditorOnly 的数据输出。

本次编写日志没有执行完整脚本，因为脚本会在当前 Houdini Live Scene 中创建多组临时测试资产。当前结论使用提交内容检查、主 HDA 强制 Cook 和现有输出快照；完整回归结果仍标记为待复验。

## 9. 本阶段验证记录

### 9.1 Houdini

**状态：[已验证]**

- Preflight：18811 RPC 正常，3055 MCP Health 为 `healthy`，当前 Codex 会话已发现 Houdini MCP 工具。
- Houdini：21.0.440。
- 当前 HIP：`HoudiniProject/PCG_Track_21.0.440/PCG_Bike_Track.hip`。
- 当前目标：`/obj/Track1`，类型 `pcgbike::Track::1.0`。
- Definition：`Assets/PCG/HDA/Track.hda`。
- Track 已处于可编辑状态；本次没有执行 `allowEditingOfContents()`，没有修改或保存 HDA/HIP。
- 强制 Cook 成功；`/obj/Track1` 共扫描 81 个节点，Error 0，Warning 0。
- Road Subnet 直接包含 53 个节点。
- 当前 HIP 存在未保存状态；为避免覆盖用户现场，本次保持未保存，不执行 Save。

### 9.2 Unity

**状态：[已验证；当前场景 Dirty]**

- Unity Editor 未播放、未暂停、未编译；写入本日志后执行 `ForceSynchronousImport`，AssetDatabase 刷新成功。
- `Assets/PCG/Scenes/PCG.unity` 已加载、有效、Build Index 0，当前 Editor 场景为 Dirty。
- `Spline`：`SplineContainer + TrackSplineHoudiniInputSettings`，组件均启用。
- `Track1`：`HEU_HoudiniAssetRoot + TrackSplineHoudiniSync`，组件均启用。
- 当前层级存在 Road Surface、Road Shoulders 和 Road Collision 三个生成对象。
- Road Surface/Shoulders 为 `MeshRenderer + MeshFilter`；Road Collision 只有 `MeshCollider`。
- Unity MCP LogCollector 当前返回 0 条日志。
- 本次没有保存 Dirty 场景，Git 中 `PCG.unity` 仍保持 `290457b` 的提交内容。

### 9.3 Git 工作区

- 当前 HEAD：`290457b`，分支 `main` 与 `origin/main` 一致。
- 本次开始前已有未跟踪文件：`Assets/SM_mountainbike1.fbx` 及其 `.meta`。
- 上述自行车资产不属于提交 `290457b`，本日志不修改、不移动、不纳入 Phase 3 功能。

## 10. 性能与移动端影响

| 变化 | CPU / Houdini 编辑期 | GPU / Unity Runtime | 结论 |
|---|---|---|---|
| 自适应采样 | 增加高密度参考评估与选择成本 | Bake 后只体现为必要顶点 | 用局部 Cook 成本换取全局顶点可控性 |
| 材质强制锚点 | 增加少量固定采样 | 只增加必要的局部 Ring | 优于整条道路统一减小间距 |
| UV3 弧长米制 | 增加各横向列距离累计 | Shader 采样数和 Variant 不变 | 主要成本在编辑期 |
| Split 输出 | Houdini/Unity 导入对象数增加 | 路面与路肩至少形成两个 Renderer/Draw | 提高材质/剔除/碰撞可控性，但需关注 DrawCall |
| 独立 Collision | 额外生成碰撞 Mesh | 不参与 GPU 渲染 | 物理职责更清晰，可独立简化 |
| 数据中心线 | 多一份点数据 | EditorOnly，不进入发布渲染 | 可供后续 Bake/Vegetation/Bridge 消费 |

移动端关键结论：

- 本阶段没有新增全屏 Pass、Blit、RT、MRT、透明层或 Shader Variant，Tile-Based GPU 带宽路径不变。
- Split Road/Shoulder 会比单一合并 Mesh 增加 Renderer 和潜在 DrawCall；只有需要独立材质、剔除或编辑覆盖时才应保留拆分，发布 Bake Pipeline 应支持按目标平台合并策略。
- 当前 Collision 与渲染几何同等细分，后续应允许 Bake 阶段单独简化碰撞 Mesh，降低 PhysX 内存和移动端碰撞查询成本。
- 自适应采样没有最大点数硬上限；极端曲线必须通过 `road_adaptive_constraint_floor_hit_count`、输出点数和 Cook 时间设置内容生产红线。
- HDA/Cook 仍只属于开发期，移动端运行时不得依赖 Houdini Engine。

## 11. 当前遗留事项

1. 在备份/临时 HIP 中执行完整 `verify_curve_road_test.py`，记录所有自适应、闭环、材质和 Split Output 用例结果。
2. 在干净 Houdini Engine Session 中验证已启用的 Knot Contract、自动 Recook、Closed Spline 和多 Spline 上传。
3. 验证 Unity Recook 后 Road/Shoulder 材质引用、Collider、对象命名和地编覆盖不会漂移。
4. 为 `OUT_ROAD_SKIRTS` 实现明确的裙边几何生成或移除空输出；当前只能视为输出预留。
5. 建立 Bake Pipeline，消费 Road、Shoulder、Collision 和 EditorOnly Centerline metadata，并支持局部锁定/覆盖。
6. 为碰撞输出增加独立简化策略，避免直接复制全部渲染三角形进入移动端 PhysX。
7. 在长赛道、连续 S 弯、强坡度、极端 Knot Roll 和高细节密度下测量 Cook 时间、点数和内存峰值。
8. 在 Mali、Adreno、Apple GPU 上比较 Combined 与 Split 输出的 DrawCall、SetPass、剔除收益和材质带宽。
9. 验证新的 `arc_length_lateral_metric` UV3 在坡道、闭环接缝、宽路肩和实际四层路面纹理上的视觉一致性。
10. 明确 20 m 默认路宽是否符合正式赛道规格；若不是，应单独调整 HDA 默认值并重新验证场景输出。

## 12. Phase 3 结论

Phase 3 的核心交付是把道路采样从“全局统一间距”升级为“基础间距 + 几何/姿态质量阈值 + Knot/材质强制锚点”，并把单一道路输出拆成可独立消费的 Road、Shoulder、Collision 和 EditorOnly Centerline 数据契约。

当前主 HDA 强制 Cook 无 Error/Warning，Unity 场景已提交启用 Knot 上传和自动 Recook，并验证了主路面、路肩和独立碰撞对象。UV3 已改为道路弧长/横向米制坐标，材质段采用米制混合与确定性覆盖顺序。尚未完成的部分是完整回归脚本执行、干净 Houdini Engine 联调、裙边实际几何、Bake Pipeline、碰撞简化和移动端真机性能验证。
