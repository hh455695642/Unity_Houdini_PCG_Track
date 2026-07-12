# Phase 1 开发日志：PCG 自行车赛道基础系统

> 文档类型：版本全量快照  
> 记录日期：2026-07-12  
> 版本文件：`Phase1_PCGTrackFoundation.md`  
> 当前主提交：`ce4bfe2`（第一版提交）  
> 适用范围：截至本文记录时的 Unity、Houdini、HDA、道路渲染、资源接入与开发工具链状态

## 1. 记录规则与证据等级

本文用于后续版本追溯，不把规划、模块占位或第三方能力误写成已经完成的自研功能。

- **[已验证]**：在 2026-07-12 通过 Unity MCP、Houdini RPC、场景/资产文件或当前 Cook 输出直接确认。
- **[历史还原]**：由 Git 提交、HIP/HDA 备份、recovery 快照和增量 patch 脚本还原。
- **[待复验]**：已有实现或资产，但尚未在目标使用链路、Bake 结果或移动端真机中完成确认。
- **[未实现]**：只有目录、Subnet、接口预留或设计约束，没有可交付运行结果。

第三方插件和外部美术资源仅记录版本、用途与接入状态，其内部能力不计为项目自研功能。

## 2. 版本环境与事实源

### 2.1 开发环境

| 项目 | 当前版本/状态 | 证据 |
|---|---|---|
| Unity Editor | `2022.3.62f2` | [已验证] `ProjectSettings/ProjectVersion.txt` 与运行中的 Editor |
| Render Pipeline | URP `14.0.12` | [已验证] `Packages/manifest.json` |
| Houdini | `21.0.440` | [已验证] Houdini RPC preflight |
| Track HDA 类型 | `pcgbike::Object/Track::1.0` | [已验证] 当前 `/obj/Track1` |
| Unity MCP | `com.ivanmurzak.unity.mcp@0.83.1` | [已验证] Package Manifest 与在线调用 |
| Unity Splines | `2.8.4` | [已验证] Package Manifest |
| 主 Unity 场景 | `Assets/PCG/Scenes/PCG.unity` | [已验证] 已打开、Build Index 0、未脏 |
| 主 Houdini 工程 | `HoudiniProject/PCG_Track_21.0.440/PCG_Bike_Track.hip` | [已验证] 当前 Houdini Session |
| 主 HDA | `Assets/PCG/HDA/Track.hda` | [已验证] 当前 definition 与 Unity 场景引用 |
| 道路 Shader | `Assets/PCG/Shaders/PCG_Road.shader` | [已验证] Unity AssetDatabase |
| 道路材质 | `Assets/PCG/Materials/M_PCG_Road.mat` | [已验证] Unity AssetDatabase |

### 2.2 当前项目数据流

```text
Unity Spline / Houdini Curve / HDA 备用控制点
    -> Track HDA：中心线校验、重采样、道路截面、Sweep、拓扑与属性
    -> Houdini Engine：开发期 Cook、调参和输出预览
    -> Bake：转换为 Unity Mesh / Prefab / Collider / Metadata（当前尚未形成完整自动化管线）
    -> Unity Runtime：只消费 Bake 后的 Unity 原生资产
```

移动端运行时禁止依赖 Houdini Cook。后续植被、岩石和路边设施的大规模渲染应在 Bake 后转换为 Chunk/Cluster 数据，并采用 GPU Instancing、Indirect Draw、GPU Culling 与 LOD。

## 3. Phase 1 开发时间线

### 2026-07-03：项目初始化与目录整理

- `b8e6296`：建立 Git 仓库基础忽略规则。
- `532533e`：导入 Unity URP 项目、Houdini 工程、早期曲线道路 HDA/OBJ、道路 Shader、验证场景和构建/验证脚本。
- `3bd3d50`：将早期 `Assets/Generated/Road` 迁移至 `Assets/PCG/Generated/Road`，同时整理 PCG 项目目录。
- `3e71edc`、`874cd16`：加入 Houdini MCP 自动启动/检测脚本及相关忽略规则。

### 2026-07-08：协作规范与节点可维护性

- `17272d2`：明确 Houdini 节点网络优先，要求核心生成逻辑可视、可学习、可人工维护。
- `cf82f55`：补充 HDA 事实源、增量修改、备份、Unity/Houdini 双向验证和移动端约束。

### 2026-07-09：连接自动化、资源接入与道路网络重构

- `85e005f`：完善 Houdini MCP 自动连接规范。
- `731c94e`：接入赛道龙门/路标相关 Mesh、Prefab、材质、纹理和外部 Shader 资源。
- 发现一次 Houdini 崩溃恢复文件：`crash.PCG_Bike_Track.ruze_18852_20260709_102323.hip`。
- `road_sop_refactor_prepatch_20260709_175404.json` 表明道路网络在 patch 前做过完整现场快照，随后从集中式生成逻辑逐步重构为可读 SOP 网络。

### 2026-07-10：道路法线与输出稳定性迭代

- `PCG_Bike_Track_pre_road_normal_20260710_184007.hip` 与 `Track_pre_road_normal_20260710_184007.hda` 保存了道路法线修改前状态。
- 当前 Road 网络已存在独立 `NORMAL_generate_surface` 节点，避免 Unity URP 接收到无效或零法线。

### 2026-07-11：材质段、低畸变 UV 与急弯保护

- 增加材质段边界局部采样，避免为短过渡区全局提高道路采样密度。
- 连续四份 `track_low_distortion_uv_prepatch_*` 快照记录低畸变 UV 方案迭代。
- 多份 `track_tight_turn_guard_prepatch_*` 快照记录急弯保护的连续调试、回滚点和参数演进。
- 当前方案同时保留道路流向 UV0，并在 `uv3` 写入世界 XZ 米制投影；Unity Shader 可通过 uniform 在两套 UV 间切换。

### 2026-07-12：Phase 1 第一版收敛

- `ce4bfe2`：提交 `Track.hda`、主 HIP、道路 Shader/材质/纹理、主场景和增量 patch 脚本。
- 旧测试 HDA/OBJ 被移除，当前 HDA 事实源统一到 `Assets/PCG/HDA/Track.hda`。
- 当前工作区另有未跟踪的 `Assets/SM_mountainbike1.fbx` 及其 `.meta`，尚未计入本版本正式资产。

## 4. 已开发功能

## 4.1 Track HDA 总体结构

**状态：[已验证]**

当前选中的 Houdini 节点为 `/obj/Track1`，类型为 `pcgbike::Object/Track::1.0`，definition 指向项目主 HDA。节点已解锁以支持 Live Scene 增量维护，当前节点本身无 error/warning。

Track 顶层按模块拆分：

| 模块 | 当前状态 | 说明 |
|---|---|---|
| Road | 已完成 Phase 1 基础能力 | 24 个可读 SOP 节点，输出道路 Mesh 与可选起点实例点 |
| Terrain | 模块骨架 | 仅保留输入/输出或占位节点，未形成地形生成结果 |
| Water | 模块骨架 | 未实现湖泊、河流和岸线生成 |
| Bridge | 模块骨架 | 未实现桥段识别、桥体、护栏与碰撞 |
| Vegetation | 模块骨架 | 未实现 mask、散布、Chunk、LOD 或 GPU 实例数据 |
| Decoration | 模块骨架 | 未实现路牌、护栏、岩石或地编替换点生成 |

顶层模块边界已经建立，但除 Road 外不得视为可交付功能。

## 4.2 中心线输入、校验与备用曲线

**状态：[已验证]**

- `IN_Unity_Curve_Parameter_Input` 接收 Unity Spline、Houdini Curve 或单条有序折线。
- `CENTERLINE_validate_or_fallback` 校验输入是否为可用的单条中心线，并写入输入 metadata。
- 输入为空或非法时，使用 HDA 暴露的六组备用控制点生成中心线，保证 HDA 可独立 Cook 和调试。
- `CENTERLINE_reverse_curve` 与 `CENTERLINE_reverse_switch` 支持反转赛道方向。
- `closed_loop_mode` 提供闭环模式接口；当前现场值为关闭，闭环真实赛道仍需专项验收。
- 当前 Houdini Session 没有接入外部中心线，输出状态为：
  - `road_source = fallback_points`
  - `road_input_valid = 0`
  - `road_input_error = missing_centerline_input`

这不是 Cook 错误，而是明确的 fallback 工作状态。Unity 场景已包含 `Spline` 与 HDA 对象，但 Unity Spline 到当前 Houdini Live Session 的输入链路仍需在后续 Bake 验证中复核。

## 4.3 重采样与材质段边界局部加密

**状态：[已验证]**

- `CENTERLINE_resample` 按 `Sample Spacing` 重采样中心线，并生成 `road_input_u`、`road_distance` 等后续属性。
- `CENTERLINE_material_segment_samples` 仅在材质段 Start/End 的混合距离附近补 Ring。
- 局部补样避免通过降低全局 Sample Spacing 来解决材质过渡，从而控制点数、顶点数、Cook 成本和移动端 Mesh 规模。
- 当前现场 `material_segments = 0`，因此没有材质段边界补样；功能节点和数据契约已存在，但多段实际视觉结果属于待复验项。

## 4.4 道路截面、Sweep 与肩部

**状态：[已验证]**

- `PROFILE_cross_section` 生成左肩、车道左、车道右、右肩四点横截面。
- `SWEEP_road_surface` 使用中心线作为 Backbone、横截面作为截面生成道路四边形网格。
- 支持道路宽度、肩部开关、肩部宽度、肩部下沉、最小肩部缩放和 Unity 面朝向翻转。
- 当前参数：道路宽 6 m、左右肩各 1 m，总宽 8 m；肩部启用，肩部下沉 0.08 m。
- `GROUP_road_bands` 生成 `shoulder_l`、`lane`、`shoulder_r` 分组，为后续独立材质、碰撞和 Bake 拆分预留接口。

## 4.5 急弯保护与规则拓扑重建

**状态：[已验证；复杂闭环仍待专项测试]**

- 原问题：道路横截面直接沿急弯中心线偏移时，内侧偏移线可能穿越、反转或产生不稳定面序。
- `SURFACE_reproject_layout` 计算输入弯曲半径；当半径小于“道路总半宽 + 最小内侧半径”时，将生成道路中心和整个横截面向弯道外侧平移。
- 外移沿赛道长度平滑过渡，不修改用户输入 Spline，避免破坏地编事实源。
- 暴露参数：
  - `Enable Tight Turn Guard = On`
  - `Minimum Inner Radius = 2 m`
  - `Transition Length = 24 m`
  - `Maximum Outward Offset = 30 m`
- `TOPO_rebuild_road_quads` 按 Ring/Band 重建规则四边形，降低 Sweep 在闭环或急弯处产生不稳定拓扑的风险。
- 当前 fallback 曲线未触发保护：触发 Ring 0、保护 Ring 0、残留 Ring 0、最大外移 0 m。

## 4.6 UV、低畸变投影与确定性三角化

**状态：[已验证]**

- UV0：保留道路横向 0..1 与纵向距离平铺，适合沿赛道方向连续的标线或条带内容。
- UV3：使用世界 XZ 米制投影，进入 Unity 后映射为 Mesh UV2 / `TEXCOORD2`。
- 设计目的：避免发卡弯内外弧长差累积，使纹理在道路上形成扇形拉伸。
- `TOPO_triangulate_for_unity` 比较四边形两条对角线的 UV3 纹理密度，选择较低畸变的确定性三角化方案，避免 Unity 导入阶段任意切分。
- 当前输出：`road_surface_uv_mode = world_xz_meters`，最大 UV 拉伸比约 `1.00166`，无 UV stretch warning。
- Shader 的 `_UseLowDistortionUV` 是 uniform，不使用 keyword，不增加本项目自定义 Shader Variant。

## 4.7 法线、顶点色与道路数据契约

**状态：[已验证]**

- `NORMAL_generate_surface` 独立生成表面法线，当前输出包含点属性 `N`。
- `MASK_material_segments` 将路面层 Mask 写入 `Cd.rgb`；基础层使用黑色，Alpha 固定为 1。
- 当前语义：`road_vertex_color_semantic = length_segment_rgb_masks_base_black_a1`。
- `ATTR_road_contract` 集中写入 `road_*` detail metadata，避免后续 Terrain、Vegetation、Bridge 等模块各自猜测道路数据。
- 当前输出还包含：道路起点位置/方向、宽度、总宽、长度、采样数、Band 数、闭环状态、输入有效性、材质段计数、急弯统计、UV 模式与拉伸统计等。

当前 fallback 输出统计：

| 指标 | 数值 |
|---|---:|
| Points | 32 |
| Primitives | 42 |
| Road Length | 52.8017 m |
| Sample Count | 8 |
| Band Count | 3 |
| Total Width | 8 m |
| Cook Error/Warning | 0 / 0 |

## 4.8 起点/终点 Prefab 实例输出

**状态：[已实现接口，待资产链路复验]**

- `START_clear_surface` 清除道路面但保留 detail metadata。
- `START_prefab_instance` 在 `Start/Stop Prefab` 不为空时于道路起点生成一个 `unity_instance` 点。
- 输出包含 `orient`、`N`、`up` 与可调 Yaw Offset，供 Houdini Engine 实例化 Unity Prefab。
- `OUT_START_PREFAB_INSTANCE` 作为独立输出，避免与道路 Mesh 混成不可维护的单一输出。
- 当前 Prefab 参数为空，因此现场输出为 0 点；需要绑定正式龙门 Prefab 后验证方向、缩放、Bake 层级和 GUID 稳定性。

## 4.9 Unity 主场景与 HDA 接入

**状态：[已验证]**

主场景包含：

- `Main Camera`
- `Directional Light`
- `Global Volume`
- `Spline`
- 未激活的 `Spline_Sourec`
- `Track1`
  - `HDA_Data`（EditorOnly）
  - `Track1_OUT_ROAD_MESH_OUT_ROAD_MESH_0`
- 未激活的 `SM_mountainbike1`

Unity 场景序列化数据明确记录：

- `_assetOpName = pcgbike::Object/Track::1.0`
- `_assetPath = Assets/PCG/HDA/Track.hda`
- HDA GUID 与 `Track.hda.meta` 一致。

2026-07-12 验证时场景已加载、未脏、Build Index 为 0，Unity Editor 未编译、未更新、未进入 Play Mode。

## 4.10 URP 道路 Shader

**状态：[已验证；移动端真机性能待测]**

Shader：`PCG_Track/Road`

### Pass 职责

| Pass | LightMode | 职责 | 额外 RenderTexture |
|---|---|---|---|
| Forward | UniversalForward | 四层路面采样、噪声侵蚀、主光与 SH 环境光 | 无 |
| DepthOnly | DepthOnly | 深度写入、Early-Z/深度相关功能 | 无 |
| ShadowCaster | ShadowCaster | 阴影投射深度 | 无 |

该 Shader 不创建 RendererFeature 或额外全屏 RenderPass，不执行 Blit/MRT，不引入中间 RT，符合移动端 Tile-Based GPU 的基础带宽约束。

### Instancing 与 Variant

- 三个 Pass 均包含 `#pragma multi_compile_instancing`，Shader 代码支持 GPU Instancing。
- 没有项目自定义 `shader_feature_local` 或功能 keyword。
- `_UseLowDistortionUV`、噪声强度、羽化、对比度等均为 runtime uniform，不形成 A×B×C 组合。
- Variant 风险主要来自 Instancing 与 URP/平台基础编译环境，当前没有自定义 keyword 爆炸风险。
- 当前材质 `m_EnableInstancingVariants = 0`，因此“Shader 支持 Instancing”不等于“当前材质已经启用 Instancing”。

### 采样与移动端成本

- Forward 每像素最多采样 5 次：4 张路面层纹理 + 1 张 RGB 噪声纹理。
- 使用 `half` 保存颜色、Mask、噪声和光照数据；位置、主 UV 以及长距离累计 UV 使用 `float`，避免多公里赛道精度损失。
- Opaque、Cull Back、ZWrite On，无透明混合，overdraw 风险低于透明多层方案。
- 当前四层纹理会无条件采样，即使某些层权重为 0；移动端应通过真机 Profiling 判断是否需要拆分低成本两层 Shader，而不是继续增加动态分支或 keyword。
- Shader 目前是轻量 Lambert + SH，不包含法线贴图、PBR 高光或多附加光，成本可控但视觉能力有限。

## 4.11 道路材质与纹理

**状态：[资产已建立；场景最终绑定待确认]**

`M_PCG_Road.mat` 已绑定：

- Base：`T_Mountainbike_Road_C.tga`
- Mask R：`T_Mountainbike_Gravel_C.png`
- Mask G：`T_Mountainbike_Stone_C.png`
- Mask B：`T_Mountainbike_Grass_01_C.png`
- Noise：`T_Road_ErosionBlendMask_RGBA.png`

当前主要参数：Noise Scale 12、Noise Strength 0.468、Blend Feather 0.5、Noise Contrast 0.1、Low Distortion UV 开启。

场景 YAML 中没有发现 `M_PCG_Road.mat` 的 GUID 引用，Houdini 输出中存在 `HEU_DEFAULT_MATERIAL_9_0`。因此只能确认材质资产本身有效，不能确认当前 HDA 输出 Renderer 已稳定绑定该自定义材质。

## 4.12 龙门/路标和自行车模型资源

**状态：[外部资产已导入；功能接入部分完成]**

- `731c94e` 导入 `SM_MarkerSigns_06` Mesh/Prefab、相关材质、方向与标识纹理，以及外部 Shader/Shader Graph。
- 这些内容属于外部美术资源接入，不视为本项目自研渲染能力。
- Track HDA 已提供起点 Prefab 输出接口，但当前参数为空，尚未形成已验证的龙门自动实例化/Bake 结果。
- `Assets/SM_mountainbike1.fbx` 及 `.meta` 当前未被 Git 跟踪；主场景有同名未激活对象。未明确资源归属、正式目录和版本策略前，不计入 Phase 1 正式交付资产。

## 4.13 MCP 自动连接与验证工具链

**状态：[已验证]**

- `.agents/scripts/Ensure-HoudiniMcp.ps1` 负责检查/配置 Houdini RPC 启动 Hook、Houdini GUI、18811 RPC、3055 MCP health 与 Codex endpoint。
- 2026-07-12 preflight 结果：Houdini RPC 正常、MCP health 为 `healthy`、当前 HIP 正确、Codex URL 正确。
- Unity MCP 可读取 Editor 状态、场景、Console 与 AssetDatabase；当前 Unity Console 无 Error/Warning。
- 当前 Codex 会话没有热加载 Houdini MCP 工具入口，因此本次 HDA 现场快照通过已连通 RPC 只读获取；连接层正常，但后续正式 HDA 修改前仍应在重启 Codex 后复验工具发现。

## 4.14 备份、恢复与增量 Patch

**状态：[已验证]**

- `HoudiniProject/.../backup/` 保存多份 HIP 历史版本与关键修改前快照。
- `Assets/PCG/HDA/backup/` 保存 `Track_bak*.hda`、UV patch 和急弯 patch 前备份。
- `HoudiniProject/.../recovery/` 保存道路 SOP 重构、低畸变 UV 和急弯保护的节点/参数/VEX 快照。
- `patch_track_low_distortion_uv.py`、`patch_track_segment_blends.py`、`patch_track_tight_turn_guard.py` 采用增量 patch、修改前 recovery、HDA 备份、Cook 检查和 definition 保存流程。
- `build_curve_road_test.py` 含清场、删除 HDA、清理 backup 和整包重建逻辑，只保留为 bootstrap/迁移工具；未获明确授权不得运行。

## 5. 问题、原因与解决方案

## 5.1 旧生成目录与事实源混乱

**证据：[历史还原]**

- 现象：早期道路测试资产位于 `Assets/Generated/Road`，之后曾迁移到 `Assets/PCG/Generated/Road`。
- 影响：脚本、场景与 HDA 可能同时引用旧路径和新路径，移动或重建容易破坏 GUID。
- 方案：Phase 1 将主 HDA 固定为 `Assets/PCG/HDA/Track.hda`，Shader、材质、纹理和场景分别归档到 `Assets/PCG/` 对应目录；旧测试 OBJ/HDA 已移除。
- 验证：Unity 场景 HDA path 与 GUID 当前均指向主 HDA。
- 遗留风险：历史脚本 `build_curve_road_test.py` 仍包含旧测试路径和 destructive cleanup，只能作为显式 fallback。

## 5.2 Python 黑盒道路生成难以学习和维护

**证据：[历史还原 + 已验证]**

- 现象：早期生成器将采样、截面、材质 Mask、实例输出等逻辑集中在 Python builder/Python SOP 中。
- 影响：节点职责不透明，用户手改 HDA 后容易被整包重建覆盖，调试与局部扩展成本高。
- 原因：早期以快速验证 Unity 曲线到道路 Mesh 为目标，没有形成长期维护的 SOP 模块边界。
- 方案：Road 重构为命名清晰的 SOP 链，拆分输入校验、Reverse、Resample、Profile、Sweep、Layout、Guard、Topology、UV、Group、Normal、Mask、Contract 和 Output。
- 验证：当前 Road 包含 24 个节点，节点均有职责注释，核心连接与输出无 error/warning。
- 遗留风险：部分复杂规则仍使用 Attribute Wrangle/VEX；后续修改必须继续保持小范围增量 patch 和中文注释。

## 5.3 Houdini 崩溃与修改不可追溯

**证据：[历史还原]**

- 现象：存在 2026-07-09 Houdini crash recovery HIP；UV 与急弯方案有多次连续迭代。
- 影响：未保存节点、参数、VEX 和 Type Properties 可能丢失，也难以确认哪次尝试引入回归。
- 方案：修改前保存 HIP/HDA 备份与 JSON recovery；增量脚本记录目标 HIP、definition、节点片段和参数；修改后检查 Cook、保存 definition。
- 验证：backup/recovery 时间线完整保留，未进行批量清理。
- 遗留风险：备份数量持续增长，需要未来单独制定保留策略；在策略明确前禁止清理历史备份。

## 5.4 Houdini MCP 连接层与工具发现不同步

**证据：[已验证]**

- 现象：18811 RPC 和 3055 health 均正常，但当前 Codex 会话没有暴露 Houdini MCP 工具。
- 原因：MCP 服务在会话启动后接入时，Codex 不一定热加载新的工具定义。
- 方案：使用 `Ensure-HoudiniMcp.ps1` 做 preflight；连接层健康但工具缺失时重启 Codex，再重新执行 preflight。
- 当前验证：Houdini 21.0.440、正确 HIP、RPC、health 和 Codex endpoint 均正常；工具热加载仍待重启复验。
- 遗留风险：未复验工具发现前，不得声称已经通过 Houdini MCP 修改现场。

## 5.5 道路法线缺失或不稳定

**证据：[历史还原 + 已验证]**

- 现象：道路输出若没有稳定 `N`，Unity URP 光照会出现全黑、明暗异常或面方向判断错误。
- 方案：在三角化后增加独立 `NORMAL_generate_surface`，让输出法线职责与拓扑/Mask 分离。
- 验证：当前道路输出包含点属性 `N`，Houdini 输出无 error/warning。
- 遗留风险：需要在闭环、坡度突变和最终 Unity Bake Mesh 上检查法线接缝、切线与背面剔除。

## 5.6 材质段过渡需要高密度采样

**证据：[历史还原 + 已验证实现]**

- 现象：材质段 Start/End 如果落在稀疏道路 Ring 之间，顶点色混合区会偏移或过宽。
- 低性能方案：全局降低 Sample Spacing，会增加整条赛道的顶点、Cook 与运行时带宽成本。
- 最终方案：只在每个边界的混合距离附近插入额外样本，并通过 `road_material_boundary_sample_count` 记录数量。
- 当前验证：节点和 metadata 契约存在；当前材质段计数为 0，实际多段视觉效果待配置后复验。
- 性能结论：CPU/Houdini Cook 只增加局部采样，GPU 仅承担必要增加的局部顶点，优于全局加密。

## 5.7 发卡弯纹理扇形畸变

**证据：[历史还原 + 已验证]**

- 现象：沿道路中心线累计 V 时，急弯内外侧实际弧长差很大，同一 Ring 共用 V 会造成扇形拉伸。
- 原因：流向 UV 拓扑适合直路/缓弯，但不适合极端曲率下的面内纹理密度一致性。
- 方案：保留 UV0 作为道路流向坐标，新增世界 XZ 米制 `uv3`；Unity Shader 用 `_UseLowDistortionUV` uniform 切换。
- 辅助方案：输出前按 UV3 密度选择四边形对角线，确定性三角化。
- 验证：当前输出包含 `uv`/`uv3`，UV 模式正确，fallback 曲线最大拉伸比约 1.00166。
- 遗留风险：世界投影在大坡度、垂直变化或跨世界原点超远赛道上可能产生新的密度/精度问题，需要坡道和长距离专项测试。

## 5.8 急弯内侧偏移反转和面序不稳定

**证据：[历史还原 + 已验证实现]**

- 现象：道路宽度相对弯曲半径过大时，内侧边界可能交叉，Sweep 面可能翻转或重叠。
- 原因：简单横向 Offset 没有限制局部最小内侧半径。
- 方案：根据曲率计算保护阈值，将整条生成截面向弯外平移并沿长度平滑过渡；随后按 Ring/Band 重建四边形拓扑。
- 验证：当前节点、参数、统计与警告机制存在；fallback 曲线没有触发保护且无残留 Ring。
- 遗留风险：尚缺发卡弯闭环、连续 S 弯、坡度叠加急弯和 Max Offset 达上限的自动化测试集。

## 5.9 自定义道路材质未确认绑定到 HDA 输出

**证据：[已验证]**

- 现象：`M_PCG_Road.mat` 已存在且纹理齐全，但主场景没有引用其 GUID，HDA 输出仍出现 `HEU_DEFAULT_MATERIAL_9_0`。
- 影响：当前场景可能无法展示顶点色四层混合和低畸变 UV Shader 的最终效果。
- 当前处理：保留独立材质资产和 Shader 数据契约，避免把具体材质硬编码到 HDA 核心生成逻辑。
- 待解决：明确由 HDA 输出 `unity_material` 路径、Unity Bake 后处理，还是地编手工覆盖来绑定材质，并验证 Recook 不覆盖人工修改。
- 验收条件：Renderer 引用 `M_PCG_Road.mat`、四层 Mask 可视化正确、Recook/Bake 后引用稳定。

## 5.10 Shader 支持 Instancing，但材质未启用

**证据：[已验证]**

- 现象：Shader 三个 Pass 均支持 Instancing，但材质序列化值 `m_EnableInstancingVariants = 0`。
- 影响：重复道路 Chunk 或相关批量对象不会仅凭 Shader 声明自动获得实例化收益。
- 当前结论：单条连续道路 Mesh 不一定需要 Instancing；如果后续拆 Chunk 或复用模块，需要按实际 Draw 结构决定是否启用。
- 待验证：移动端 Frame Debugger/Profiler 中检查 Batches、SetPass、顶点规模与 Chunk Culling 收益，避免为单 Mesh 盲目启用。

## 5.11 自行车 FBX 未纳入版本管理

**证据：[已验证]**

- 现象：`Assets/SM_mountainbike1.fbx` 与 `.meta` 为未跟踪文件，场景中有同名未激活对象。
- 风险：团队其他成员拉取本版本后可能出现 Missing Asset 或场景引用不一致。
- 待解决：确认资产授权、正式目录、命名、导入设置和是否属于 Phase 1；若纳入，应通过 Unity AssetDatabase 移动并保留 GUID。

## 6. 当前状态矩阵

| 功能 | 状态 | 当前结论 |
|---|---|---|
| Track HDA 模块结构 | 已完成 | Road 可用，其他模块仅骨架 |
| 曲线输入校验与 fallback | 已完成 | 当前现场使用 fallback；Unity Spline 实际链路待复验 |
| 道路重采样、截面、Sweep | 已完成 | 当前输出无错误 |
| 肩部与道路分组 | 已完成 | 3 Band 输出已建立 |
| 材质段与局部边界采样 | 部分完成 | 实现存在，当前 0 段，未做多段最终验收 |
| 急弯保护 | 部分完成 | 实现与参数已验证，缺极端曲线测试集 |
| UV0 + 低畸变 UV3 | 已完成 | 当前输出数据与 Shader 切换已建立 |
| 确定性三角化与法线 | 已完成 | 输出包含 uv/uv3/N |
| 道路 metadata 契约 | 已完成 Phase 1 | 已覆盖道路、输入、UV、急弯和材质段统计 |
| 起点 Prefab 输出 | 部分完成 | 接口存在，当前未绑定资源 |
| 道路 URP Shader | 已完成 Phase 1 | 无自定义 keyword 爆炸；真机性能待测 |
| 自定义道路材质绑定 | 待接入 | 资产存在，场景输出未确认绑定 |
| Unity Bake Pipeline | 未实现 | 尚无完整自动化 Bake/覆盖保护流程 |
| Terrain | 未实现 | 只有模块骨架 |
| Water | 未实现 | 只有模块骨架 |
| Bridge | 未实现 | 只有模块骨架 |
| Vegetation | 未实现 | 尚无 GPU Instance/Chunk/Culling/LOD 数据 |
| Decoration | 未实现 | 只有模块骨架 |
| 移动端真机 Profiling | 未执行 | 需要 Mali/Adreno/Apple GPU 数据 |

## 7. 性能、兼容性与扩展风险

### 7.1 当前 CPU 与 GPU 分工

| 阶段 | CPU/Houdini | GPU/Unity | 结论 |
|---|---|---|---|
| 编辑器生成 | Houdini Cook 负责采样、Sweep、拓扑、UV、Mask、metadata | 仅预览 | 允许较复杂，但必须可 Bake |
| 运行时道路 | 不应重新 Cook 或逐帧生成 | 渲染 Bake Mesh | 当前目标正确，Bake 自动化待补 |
| 材质混合 | CPU 不参与逐像素混合 | 每像素 5 次采样 | 带宽/采样是主要风险，应真机测试 |
| 大规模植被 | 禁止 CPU 每帧逐实例循环 | 计划 Indirect Draw + Compute Culling | 尚未实现，不得按已完成评估 |

### 7.2 移动端风险

- 道路 Shader 无中间 RT、无透明 Overdraw、无 MRT/全屏 Blit，基础结构适合 Tile-Based GPU。
- 四层纹理与噪声固定五采样，可能受纹理带宽而非 ALU 限制。
- 长距离 UV 使用 float 是必要精度成本；颜色、Mask 与光照继续保持 half。
- 当前未加入法线贴图和多附加光，有利于控制移动端成本。
- 尚未完成 Android Mali/Adreno 与 iOS Metal 真机验证，不能给出最终帧耗和带宽结论。

### 7.3 Shader Variant 风险

- 自定义功能 keyword：0。
- `multi_compile_instancing`：3 个 Pass 均存在，属于明确且必要的 Instancing 支持。
- Low Distortion UV 等开关使用 uniform，不产生组合爆炸。
- 后续若增加湿地、积雪、法线、PBR 等高成本能力，应拆独立 Shader，不应继续堆叠为超级道路 Shader。

### 7.4 扩展点

- `ATTR_road_contract`：Terrain、Bridge、Vegetation 和 Debug 工具读取稳定道路 metadata 的入口。
- `GROUP_road_bands`：道路、肩部、碰撞和材质拆分入口。
- 独立 `OUT_START_PREFAB_INSTANCE`：起终点、检查点或装饰实例扩展入口。
- 顶层 Terrain/Water/Bridge/Vegetation/Decoration Subnet：模块边界已预留，但实现必须继续独立，禁止合成超级 HDA 网络。

## 8. 本版本验证记录

### 8.1 Houdini

- Preflight：通过。
- RPC：`127.0.0.1:18811` 正常。
- MCP Health：`http://127.0.0.1:3055/health` 返回 `healthy`。
- 当前 HIP：`PCG_Bike_Track.hip`。
- 当前节点：`/obj/Track1`。
- HDA Definition：`Assets/PCG/HDA/Track.hda`。
- Track error/warning：0 / 0。
- `OUT_ROAD_MESH` error/warning：0 / 0。
- 当前 HDA 节点处于解锁状态，本次仅进行读取，没有修改节点或保存 HDA/HIP。
- Codex 当前会话未热加载 Houdini MCP 工具；后续 HDA 实质修改前必须重启 Codex 并复验工具发现。

### 8.2 Unity

- Editor：未播放、未暂停、未编译、未刷新 AssetDatabase。
- 主场景：`PCG.unity` 已加载、有效、未脏、Build Index 0。
- Console Error：0。
- Console Warning：0。
- 场景中的 HDA path/GUID 与 `Track.hda` 一致。

### 8.3 版本管理

- 当前 HEAD：`ce4bfe2`。
- 写日志前已有未跟踪文件：
  - `Assets/DevLog.meta`
  - `Assets/SM_mountainbike1.fbx`
  - `Assets/SM_mountainbike1.fbx.meta`
- 上述文件不是本日志生成过程创建的既有内容；本版本日志不会修改或移动它们。

## 9. 下一阶段建议顺序

1. 打通 Unity Spline → HDA 输入 → Recook → Bake 的完整验证，并建立自动测试曲线集。
2. 确定 `M_PCG_Road.mat` 的稳定绑定策略，验证 Recook/Bake 不覆盖地编材质覆盖。
3. 建立闭环、发卡弯、连续 S 弯、坡度急弯和材质多段测试样例。
4. 实现明确的 Bake Pipeline，将 Mesh、Collider、Material 与 metadata 转成 Unity 原生资产。
5. 再按 Terrain、Water、Bridge、Vegetation、Decoration 的模块边界逐项实现。
6. 植被从一开始采用 Chunk/Cluster + GPU Culling + Indirect Draw，不建立大量运行时 GameObject。
7. 在 Mali、Adreno、Apple GPU 上验证道路 Shader 五采样带宽、DrawCall、SetPass、Overdraw 与内存。

## 10. 后续版本日志约定

- 只有项目负责人明确宣布进入新版本后，才在 `Assets/DevLog/` 新建一个 `PhaseN_主题.md`。
- 每个版本只保留一个 Markdown 文件，采用全量快照口径，可独立阅读。
- 已完成版本原则上不回写；若必须修正文档事实，应在修订处注明修订日期和原因。
- 新版本必须继续记录：环境、关联提交、功能、问题、方案、验证、性能/兼容性、遗留事项和资产状态。
- 功能状态必须使用“已完成、部分完成、模块骨架、待复验、未实现”之一，并附证据等级。
