# Phase 8 开发日志：Unity Spline 脚本重构与赛道横倾/宽度链路整理

> 文档类型：Phase 8 增量开发日志
>
> 记录日期：2026-07-22
>
> 关联提交一：`4d1b550615b715986f855764202f68d76eb0359e`（提交说明：`脚本重构`）
>
> 关联提交二：`c768e6daf1e2a6838310e9873e822507f71b02b9`（提交说明：`8`）
>
> 基线版本：Phase 7 日志提交 `3cee8043563d71e90ba57b03ba0135c029ac5cf0`
>
> 记录范围：记录 `3cee804..c768e6d` 中由上述两个提交新增、调整、替换或移除的内容

## 1. 日志范围与证据

本文不是 Track/Terrain 全量快照。Phase 1～Phase 7 已有的曲线输入、Knot Contract V1、赛道横倾、自适应采样、拆分输出、Terrain 生成、道路 Shader 与起点 Prefab 输出接口继续以对应阶段日志为准。

证据标记：

- **[已验证]**：通过 Git 父子差异、HDA 二进制的隔离 `hython` 检查、跟踪验证脚本、Unity MCP 或 Houdini MCP 当前只读状态直接确认。
- **[提交已实现]**：功能已经进入目标提交，但提交场景与当前 Live Scene 状态不同，或尚缺最终 Bake/移动端数据。
- **[待复验]**：代码或资产存在，但仍需专项输入、Player Build、视觉结果或目标设备数据确认。
- **[未改变]**：沿用前一阶段实现，本阶段没有修改对应 Shader、材质、Renderer 或运行时渲染路径。

两个提交形成连续版本链：

```text
3cee804  phase7 日志基线
    -> 4d1b550  脚本重构
    -> c768e6d  8
```

其中 `脚本重构` 负责 Unity C# 职责拆分、程序集边界和序列化类型迁移；`8` 负责 Track 参数术语、道路宽度 Ramp、冗余节点移除、Terrain 节点网络可读性、验证脚本和场景 Recook。

## 2. 提交概览

### 2.1 `4d1b550`：脚本重构

提交日期：2026-07-20 17:23:21 +08:00。

共修改 33 个文件，Git 统计为 `+21,212/-19,862`；大部分行数来自 `PCG.unity` Recook/序列化重写，不代表同等规模的独立业务代码。

| 模块 | 本提交变化 | 当前结论 |
|---|---|---|
| Unity Spline 输入 | 删除 714 行单体接口，拆为 Snapshot、Payload、Uploader、Interface | [已验证] |
| 程序集 | 新增 `PCGBike.Authoring` 与 Editor-only `PCGBike.Editor` | [已验证] |
| 场景组件 | Track/Terrain Authoring 组件重命名、分模块归档 | [已验证] |
| 序列化迁移 | 保留脚本 `.meta` GUID，并使用 `MovedFrom` 迁移旧类型名 | [已验证] |
| Player 边界 | Cook、轮询和 HAPI 上传均限制在 Editor 路径 | [已验证代码结构] |
| Track HDA | 移除旧 Debug Bank Frames 参数/分支；中心线源 Switch 等价重建 | [已验证二进制差异] |
| Unity 场景 | HDA 重新序列化，Terrain/Track Cook Count 重置为 8/4 | [提交已实现] |
| 测试 | 仅提交 `Assets/PCG/Scripts/Tests.meta` 目录占位 | [已验证；没有提交测试源码] |

### 2.2 `c768e6d`：8

提交日期：2026-07-22 13:42:41 +08:00。

共修改 14 个文件，Git 统计为 `+17,410/-11,051`；其中 `PCG.unity` 为 `+16,113/-10,840`，同样以 HDA Recook 与序列化噪声为主。

| 模块 | 本提交变化 | 当前结论 |
|---|---|---|
| Track 参数 | 对外 `Bank/Roll` 术语改为 `Lateral Tilt/Knot Tilt` | [已验证] |
| 道路宽度 | 新增按 `road_t` 采样的 `road_width_ramp` | [已验证] |
| Road SOP | 删除旁路状态的 `FRAME_normalize_authored_up`，消费者直接接采样中心线 | [已验证] |
| 固定采样默认值 | `sample_spacing` 默认从 8 m 调为 12 m | [已验证] |
| Terrain HDA | 重排 170 个节点并建立 10 个命名 Network Box、补充说明 | [已验证；算法/连线未变] |
| Patch 工具 | 新增参数迁移与冗余节点移除脚本 | [已验证代码] |
| 验证工具 | 扩充宽度 Ramp、默认输出、碰撞和自适应采样测试 | [已验证运行] |
| Unity 场景 | 新增第二个 `Track4`，两个 Track 分别输出 Road/Shoulder/Collision | [已验证] |
| 起点龙门 | Phase 7 的 Prefab 参数被清空，`RaceStart_Instance1` 不再存在 | [已验证；属于场景能力回退] |
| 历史日志 | 修正 Phase 2/3/7 中面向用户的横倾术语 | [已验证；不代表新增算法] |

## 3. Unity Spline 输入脚本重构

### 3.1 从单体接口拆成四层职责

**状态：[已验证]**

旧文件 `Assets/PCG/Scripts/Editor/PCGTrackSplineInputInterface.cs` 共 714 行，同时承担场景读取、Spline 校验、坐标转换、HAPI attribute 组装、节点创建、上传与接口注册。

重构后数据流为：

```text
SplineContainer + TrackSplineHoudiniInputAuthoring
    -> TrackSplineInputSnapshotBuilder
       校验 Spline/Knot，并建立不依赖现场对象变化的快照
    -> TrackSplineHapiPayloadBuilder
       生成 Houdini 坐标、Quaternion、Handle、Spline/Knot 索引数组
    -> TrackSplineHapiUploader
       创建 HAPI Curve、写 Attribute、合并多 Spline、CommitGeo
    -> TrackSplineHoudiniInputInterface
       只负责注册、支持判断、调用上传与报告结果
```

对应文件与职责：

| 文件 | 行数 | 职责 |
|---|---:|---|
| `TrackSplineInputSnapshot.cs` | 122 | 校验 `SplineContainer`、闭环/开放曲线最小 Knot 数、构建不可变快照 |
| `TrackSplineHapiPayload.cs` | 260 | Unity→Houdini 坐标转换、有限值检查、单位 Quaternion 检查、数组构建 |
| `TrackSplineHapiUploader.cs` | 335 | HAPI 节点创建、Curve Part、Attribute、Merge、Cook 与 `CommitGeo` |
| `TrackSplineHoudiniInputInterface.cs` | 139 | Houdini Engine 输入接口注册与调度 |

拆分后的总代码行数增加，主要来自更明确的输入校验、错误信息和职责边界；目标是降低单文件耦合，而不是单纯压缩行数。

### 3.2 Knot Contract V1 保持不变

**状态：[已验证]**

Uploader 继续以 Linear Carrier Curve 传输 Knot；闭环为 `isClosed=true`、`isPeriodic=false`。Houdini 侧仍通过以下数据重建 Cubic Bezier，然后进入唯一的生产采样链：

| Owner | Attribute |
|---|---|
| Point | `P`、`rot`、`unity_tangent_in`、`unity_tangent_out`、`unity_knot_index`、`unity_spline_index` |
| Primitive | `unity_spline_index`、`unity_spline_closed`、`unity_spline_knot_count` |
| Detail | `unity_spline_contract_version=1`、`unity_spline_contract_valid=1`、`unity_spline_contract_source=UnitySplineContainer` |

单 Spline 上传后直接返回；多 Spline 为每条分支创建输入节点并通过 Merge 合并。接口优先级保持为 `DEFAULT_PRIORITY + 100`，并保留在官方 `HEU_InputInterfaceSpline` 之后重试注册的保护，最大重试 8 次。

### 3.3 Snapshot 与 Payload 校验

**状态：[已验证代码结构]**

Snapshot Builder 负责：

- 只接受挂有 `TrackSplineHoudiniInputAuthoring` 标记且启用 Knot Contract 的 `SplineContainer`。
- 拒绝空 Spline；闭环至少 3 个 Knot，开放曲线至少 2 个 Knot。
- 记录总 Knot 数以及开放/闭环混合状态，避免上传过程中再次读取可变场景对象。

Payload Builder 负责：

- 转换位置、旋转和 In/Out Tangent 到 Houdini 坐标。
- 拒绝 NaN/Infinity、近零 Quaternion 和超出单位 Quaternion 容差的数据。
- 为多 Spline 明确写入 Knot/Spline 索引，避免合并后靠点顺序猜测来源。

### 3.4 程序集与目录边界

**状态：[已验证]**

```text
Assets/PCG/Scripts/
  Track/Authoring/
  Terrain/Authoring/
  Editor/Houdini/TrackSplineInput/
  Tests.meta
```

新增程序集：

| 程序集 | 平台 | 引用 | 职责 |
|---|---|---|---|
| `PCGBike.Authoring` | 全平台 | `HoudiniEngineUnity`、`Unity.Splines` | 保存场景可序列化组件；Player 中无 Cook/轮询执行 |
| `PCGBike.Editor` | Editor-only | Authoring、HoudiniEngineUnity、Splines、Mathematics | HAPI 上传、自定义 Inspector 与 Editor 输入接口 |

`PCGBike.Authoring` 仍有对 `HoudiniEngineUnity` 的编译期依赖，因为序列化组件字段引用 `HEU_HoudiniAssetRoot`。因此本阶段实现的是“Player 不执行 Houdini Cook/HAPI 逻辑”，不能表述为“Player 构建已完全移除 Houdini Engine 包依赖”。正式移动端包裁剪仍需独立 Player Build 验证。

### 3.5 组件重命名与序列化兼容

**状态：[已验证]**

| 旧类型 | 新类型 | 新 Namespace |
|---|---|---|
| `TrackSplineHoudiniInputSettings` | `TrackSplineHoudiniInputAuthoring` | `PCGBike.Track.Authoring` |
| `TrackSplineHoudiniSync` | `TrackSplineHoudiniCookSync` | `PCGBike.Track.Authoring` |
| `TerrainTrackDisplayBinding` | `TerrainTrackDisplaySopBinding` | `PCGBike.Terrain.Authoring` |

三类组件均使用 `MovedFrom` 指向旧 Namespace/Assembly/类名；移动和重命名同时保留对应 `.meta` GUID，避免主场景脚本引用丢失。

字段迁移：

- `_enableRotationUpload` 迁移为 `EnableKnotDataUpload`。
- `_samplingResolution` 迁移为仅保留兼容数据的 `_legacySamplingResolution`，不再成为生产采样控制。
- Track HDA 的 `sample_spacing` 仍是唯一正式采样密度入口。
- Cook Sync 保留 0.35 秒 debounce、Reload 超时与异步 Recook 行为。

当前 Unity MCP 已确认：

```text
Track1   -> PCGBike.Track.Authoring.TrackSplineHoudiniCookSync
Terrain1 -> PCGBike.Terrain.Authoring.TerrainTrackDisplaySopBinding
```

`Track4` 当前没有挂载 `TrackSplineHoudiniCookSync`，因此两个 Track 实例的自动同步职责不对称，后续若保留双 Track 场景必须明确其用途与同步策略。

### 3.6 多 Spline Transform 待复验点

**状态：[待复验]**

当前 Uploader 对第 0 条 Spline 传入 `Matrix4x4.identity`，对第 1 条及之后的分支传入 `snapshot.Transform.localToWorldMatrix`。这可能是在配合 Houdini Engine 对根输入节点的外部 Transform 处理，也可能在非 Identity Root Transform 下造成多分支坐标口径不一致。

本阶段没有提交可证明该行为正确的自动测试源码，不能直接判定为缺陷；需要用“同一 `SplineContainer` 内至少两条 Spline + 非零位移/旋转/缩放”做 HAPI 合并后的坐标专项验证。

## 4. Track HDA 横倾术语与参数迁移

### 4.1 对外参数重命名

**状态：[已验证]**

提交 `8` 将面向用户的道路 Banking/Roll 表述收敛为赛道 Lateral Tilt/Knot Tilt：

| 旧参数 | 新参数 |
|---|---|
| `enable_road_banking` | `enable_track_lateral_tilt` |
| `bank_use_spline_knot_roll` | `lateral_tilt_use_spline_knot_tilt` |
| `bank_design_speed_kph` | `lateral_tilt_design_speed_kph` |
| `bank_auto_strength` | `lateral_tilt_auto_strength` |
| `bank_max_angle_deg` | `lateral_tilt_max_angle_deg` |
| `bank_transition_length_m` | `lateral_tilt_transition_length_m` |
| `adaptive_max_bank_delta_deg` | `adaptive_max_lateral_tilt_delta_deg` |

可选 Debug 参数若存在则由 `debug_bank_frames` 改为 `debug_lateral_tilt_frames`；当前提交 HDA 已在前一提交移除实际 Debug 参数与节点，因此最终 `Track.hda` 不含该 Debug 开关。

`patch_rename_lateral_tilt_parameters.py` 的迁移策略：

- 保存当前参数值、表达式和关键帧。
- 只重写 HDA 内部 `../../旧名` Channel Reference。
- 检查旧参数已消失、新参数已存在。
- 对修改前后及保存后的完整 Geometry Signature 做一致性比较。
- 备份 HDA/HIP 后再保存 definition。

### 4.2 内部兼容契约保持旧名

**状态：[已验证]**

本阶段只重命名公共参数/UI 与说明，不批量改写既有内部数据契约。以下名称继续保留：

- 内部节点：`FRAME_compute_grade_bank`、`FRAME_apply_grade_bank`。
- 内部 Network Box 技术名：`BOX_04_LAYOUT_BANKING`。
- Point/Detail metadata：`road_bank_deg`、`road_bank_target_deg`、`road_banking_enabled`、`road_bank_design_speed_kph` 等。

这样可以避免 Terrain、验证脚本、Unity Bake 后处理或历史工具因为 metadata 改名而失效。外部术语和内部兼容字段不一致是有意的迁移边界，不应在后续未做全链路版本化时继续随意改名。

### 4.3 旧日志术语修订

Phase 2、Phase 3 与 Phase 7 日志在提交 `8` 中同步修正面向用户的术语及已删除节点说明。该变更是 2026-07-22 的事实修订，不代表这些历史阶段重新实现了横倾算法。

## 5. 道路宽度 Ramp

### 5.1 参数与计算

**状态：[已验证]**

Track HDA 在 `road_width` 后新增 Float Ramp：

```text
road_width_ramp
Label: Road Width Multiplier / 道路宽度曲线
Default: (0, 1) -> (1, 1), Linear
```

`SURFACE_reproject_layout` 按道路归一化弧长 `road_t` 采样：

```text
width_multiplier = max(chramp(road_width_ramp, road_t), 0)
local_road_width = max(road_width * width_multiplier, 0.1 m)
local_total_width = local_road_width + 2 * shoulder_width
```

行为约束：

- `road_width` 继续是基准主路宽度，Ramp 是无量纲倍率。
- 主路宽度下限钳制为 0.1 m，负 Ramp 不会生成负宽度。
- 左右路肩保持固定米制宽度，不跟随 Ramp 成比例缩放。
- 横截面中心不移动，左右车道边界围绕原中心对称变化。
- 闭环不自动修正 Ramp 接缝；用户必须保持首尾值一致。

### 5.2 新增输出数据

**状态：[已验证]**

Point Attribute：

- `road_width_multiplier`
- `road_width_m`
- `road_lateral_t`
- 原有 `road_lateral_offset_m`

Detail Attribute：

- `road_width_min`
- `road_width_max`
- `road_total_width_min`
- `road_total_width_max`

当前 Houdini Live 输出已经包含上述 Attribute。该数据可供 Terrain 贴合、碰撞验证、路边散布宽度和 Bake 后工具读取；后续模块应读取 metadata，不要重新猜测道路宽度。

### 5.3 固定采样默认值

**状态：[已验证]**

HDA `sample_spacing` 默认值从 8 m 调为 12 m。固定采样模式下，更大的间距会降低 Ring/顶点数量和编辑器 Cook 成本，但也会降低弯道、坡度和宽度 Ramp 的基础分辨率；Adaptive Sampling 仍可按弦误差、方向、坡度和横倾变化补样。

当前提交场景的两个 Track 分别序列化了 12 m 与 8 m，因此不能把 HDA 新默认值误写成所有场景实例都已统一使用 12 m。

## 6. 移除冗余 Authored-Up 节点

**状态：[已验证]**

提交前链路：

```text
CENTERLINE_sampling_switch
    -> FRAME_normalize_authored_up（已 Bypass）
       -> CENTERLINE_polyframe
       -> FRAME_compute_grade_bank input 1
```

提交后链路：

```text
CENTERLINE_sampling_switch
    -> CENTERLINE_polyframe
    -> FRAME_compute_grade_bank input 1
```

`FRAME_compute_grade_bank` 内部继续将 `road_authored_up` 对最终切线做正交化与归一化，再计算 Knot Tilt，因此移除中间节点不会删除必要的姿态处理。

`patch_remove_redundant_authored_up.py` 会检查目标节点、上游和两个消费者，重连后比较修改前后及保存后的完整 Geometry Signature，并保存备份。

需要注意：被删除节点在提交前已经处于 Bypass 状态，因此本次主要收益是减少网络歧义、避免未来误开启和缩短维护链路，不能夸大为已经节省了一次实际执行中的 VEX Pass。移动端 Runtime 本来就只消费 Bake Mesh，运行时 GPU/CPU 成本没有变化。

## 7. Terrain 节点网络整理

**状态：[已验证；生成算法未改变]**

`Terrain.hda` 的 DialogScript、参数接口、节点类型、节点参数、输入连线、注释、Bypass/Display/Render 状态均未变化。隔离比较只发现：

- 170 个节点位置调整。
- 10 个旧/匿名 Network Box 被替换为 10 个按阅读顺序命名的 Network Box。
- 9 个既有 Sticky Note 调整位置/尺寸。
- 新增 4 个学习/维护说明 Sticky Note。

新的阅读分组：

```text
00 TRACK INPUT
10 TERRAIN SOURCE
20 GUIDE MESH
30 LAKE CONSTRAINT
40 TRACK CONFORM + MASKS
50 ADAPTIVE EARTHWORK
55 DETAIL RESTORE
70 OUTPUT + METADATA
80 VALIDATION
90 DEBUG
```

新增 README Sticky Note 明确：Houdini 只参与 Editor Cook/Bake，Unity Runtime 只消费 Bake 资源；禁止随意改名 `OUT_*`、稳定 Mask Layer 和 metadata 字段。

因此 `Terrain.hda` 与 `PCG_Bike_Terrain.hip` 的二进制变化应归类为可读性/维护性整理，不应写成 Terrain 算法升级。

提交同时删除了孤立的 `Assets/PCG/HDA/Terrain.hda.bak.meta`。此前 Git 只跟踪该 `.meta`，没有跟踪对应 `.bak` 文件；这不是清理 `Assets/PCG/HDA/backup/` 中的正式历史备份。

## 8. Patch 与验证工具增强

### 8.1 新增增量 Patch

| 脚本 | 行数 | 职责 |
|---|---:|---|
| `patch_rename_lateral_tilt_parameters.py` | 333 | 安全迁移公共参数名、值、表达式、关键帧与 Channel Reference |
| `patch_remove_redundant_authored_up.py` | 466 | 删除冗余节点、重连消费者、保持 Geometry Signature |

两个脚本都按 Live Scene 增量修改、备份、验证、保存 definition 的路径设计，没有使用 `build_curve_road_test.py` 整包重建当前 HDA。

### 8.2 既有工具同步

- `patch_track_road_banking.py` 改用新的横倾参数名，并更新 UI Label/Help、节点注释和 Network Box 说明。
- `organize_track_road_network.py` 将面向用户的 Banking 表述修正为 Lateral Tilt。
- 内部 `bank_*`/`road_bank_*` 兼容字段继续保留。

### 8.3 `verify_curve_road_test.py` 扩充

**状态：[已验证运行]**

新增或强化的验证包括：

- HDA 参数文件夹、横倾参数名与 `road_width_ramp` 默认值。
- Ramp 0.5 倍变宽/变窄、2 倍扩宽、负值钳制到 0.1 m。
- 路肩保持固定米制宽度、车道中心不移动、`road_lateral_t` 正确。
- `road_width_min/max`、`road_total_width_min/max` 与逐 Ring 结果一致。
- 闭环 Ramp 首尾连续性样例。
- 固定采样默认 Road/Collision 点、面、Vertex 与 Group 合约。
- 自适应采样密度、参考点数、弯道/坡度/横倾约束及拆分输出。

2026-07-22 使用 Houdini 21.0.440 `hython` 对提交中的 `Track.hda` 执行当前验证脚本，结果为：

```text
VERIFY_OK=1
```

其中验证覆盖了 fallback、Width Ramp、开放/闭合曲线、坡度、Knot Tilt、自动横倾、S 弯与 Collision 输出。这是隔离的 HDA 自动验证，不等同于 Unity Houdini Engine 的完整 Recook/Bake 验收。

## 9. Unity 场景变化与 Recook

### 9.1 `脚本重构` 场景

提交 `4d1b550` 仍包含 1 个 Terrain HDA 与 1 个 Track HDA，保留 Phase 7 的起点龙门实例。Terrain/Track `_totalCookCount` 从 Phase 7 的 18/22 变为 8/4，表明场景经历了新的 Houdini Session/Reload/Recook 序列。

脚本类型迁移依赖 `.meta` GUID 与 `MovedFrom`，大量场景行变化主要是 Houdini Engine 生成数据重写，不应逐行解释为 C# 业务功能。

### 9.2 `8` 场景新增第二个 Track

**状态：[已验证]**

提交 `c768e6d` 将场景从 1 个 Track HDA 增加到 2 个：

```text
Track1
  HDA_Data
  Track1_OUT_ROAD_MESH...
  Track1_OUT_ROAD_SHOULDERS...
  Track1_OUT_ROAD_COLLISION...

Track4
  HDA_Data
  Track4_OUT_ROAD_MESH...
  Track4_OUT_ROAD_SHOULDERS...
  Track4_OUT_ROAD_COLLISION...
```

两个对象均引用：

```text
_assetOpName = pcgbike::Object/Track::1.0
_assetPath   = Assets/PCG/HDA/Track.hda
```

场景内六份道路 Mesh 形成两个一致的 Road/Shoulder/Collision 顶点比例组：

- 882 / 1,764 / 2,646
- 2,574 / 5,148 / 7,722

Terrain Cook Count 保持 8；两个 Track Cook Count 均为 5。当前提交证明的是“场景存在两个独立 Track HDA 实例和各自拆分输出”，但没有文档或代码证明它们已经构成正式多赛道玩法、分支赛道或 LOD 系统，因此不得扩大解释。

### 9.3 起点龙门回退

**状态：[已验证]**

`4d1b550` 中：

```text
start_prefab = Assets/.../SM_MarkerSigns_06.prefab
start_prefab_yaw_offset = 0
RaceStart_Instance1 存在
```

`c768e6d` 中两个 Track 的 `start_prefab` 都为空，Yaw Offset 回到 -90°，场景不再包含 `RaceStart_Instance1` 或实际 Start Prefab Output 子对象。

这不是起点 Prefab 接口被删除：`Track.hda` 的 `OUT_START_PREFAB_INSTANCE` 仍存在；它是 Phase 8 提交场景配置相对 Phase 7 的回退。若主验证场景仍要求起点龙门，需要重新明确由哪一个 Track 负责起点实例并完成方向/地面贴合复验。

## 10. 性能、兼容性与运行时边界

### 10.1 CPU vs GPU

| 阶段 | CPU/Houdini/Editor | GPU/Unity Runtime | Phase 8 影响 |
|---|---|---|---|
| Spline 上传 | Snapshot/Payload/HAPI Upload | 无 | 职责拆分、校验增强；仍是开发期流程 |
| HDA Cook | Width Ramp、横倾、采样、Mesh/Collision 输出 | 无 | 12 m 默认可减少固定采样；Ramp 增加少量每 Ring 运算 |
| Bake 后运行 | 不应 Cook 或轮询 | 渲染 Bake Mesh | 无新增运行时生成逻辑 |
| 场景双 Track | 两套 HDA 编辑器预览/Recook | 若直接保留则渲染两套 Mesh | 必须按实际可见性和玩法决定是否同时进入 Runtime |

### 10.2 URP、Pass 与带宽

本阶段没有修改 Shader、Material、RendererFeature、ScriptableRenderPass 或 URP Renderer：

- 新增 RenderPass：0。
- `RenderPassEvent`：不适用。
- 新增 RenderTexture：0。
- 新增 Blit/MRT：0。
- 新增 Shader Keyword/Variant：0。
- Forward 纹理采样数：沿用 Phase 7，未由本阶段增加。

Road Width Ramp 发生在 Houdini Cook/Bake，不增加移动端每帧 ALU 或纹理带宽。运行时成本只来自最终 Bake Mesh 的实际顶点数、DrawCall、Collider 和两套 Track 是否同时保留。

### 10.3 C# 运行时风险

- Authoring 组件在 Player 中不执行 `Update`、轮询、HAPI Upload 或 Recook。
- Editor-only HAPI 代码被 `PCGBike.Editor` 平台约束隔离。
- `PCGBike.Authoring` 仍引用 HoudiniEngineUnity，必须通过 Android/iOS Player Build 验证包裁剪、Assembly 依赖和 IL2CPP 编译。
- 当前没有证据表明重构引入 GC 热点；这些脚本不应进入逐帧大规模渲染路径。

## 11. 本版本验证记录

### 11.1 Git

- 当前 HEAD：`c768e6daf1e2a6838310e9873e822507f71b02b9`，分支 `main`。
- `4d1b550` 父提交：`3cee8043563d71e90ba57b03ba0135c029ac5cf0`。
- `c768e6d` 父提交：`4d1b550615b715986f855764202f68d76eb0359e`。
- `Track.hda`：56,621 → 55,789 → 58,898 bytes。
- `Terrain.hda` 在 `8` 中：98,490 → 99,844 bytes；差异仅为节点网络布局/说明。
- `PCG_Bike_Track.hip`：320,771 → 317,207 → 331,086 bytes。
- `PCG_Bike_Terrain.hip` 在 `8` 中：391,285 → 392,796 bytes。

### 11.2 Unity

2026-07-22 通过 Unity MCP 只读确认：

- Unity Editor `2022.3.62f2`。
- 未播放、未暂停、未编译、未处于 AssetDatabase 更新状态。
- `Assets/PCG/Scenes/PCG.unity` 已加载、有效、Build Index 0、Root Count 11。
- 当前场景为 Dirty；本次没有保存场景，Dirty 内容不归入提交 `8`。
- `Track1` 与 `Track4` 均激活并引用 `Track.hda`；`Terrain1` 当前未激活。
- `Track1` 的新 Cook Sync 类型与 `Terrain1` 的新 Display SOP Binding 类型可解析。
- Console Warning 为 0。
- Console 中有 2 条本次只读检查产生的 MCP `GameObject / Find` 查找不存在对象 `Track` 的工具错误；不是 C# 编译错误或提交 `8` 功能错误。

当前工作区的 `Assets/PCG/Scripts/Tests/` 是未跟踪目录，不属于 `脚本重构` 或 `8`。本日志没有把其中测试源码计为提交内容，也没有用它替代 Git 证据。

### 11.3 Houdini Live Scene

`Ensure-HoudiniMcp.ps1` 本次因只检测进程名 `houdini` 而未识别实际运行的 `houdinifx`，错误报告“Houdini is not running”。随后通过端口与 MCP 直接复核：

- `127.0.0.1:18811` RPC：可连接。
- `http://127.0.0.1:3055/health`：`healthy`。
- Houdini MCP 工具：当前会话可发现并调用。
- Houdini：21.0.440。
- 当前 HIP：`HoudiniProject/PCG_Track_21.0.440/PCG_Bike_Track.hip`。
- 当前唯一 Track：`/obj/Track1`，类型 `pcgbike::Track::1.0`。
- Definition：`Assets/PCG/HDA/Track.hda`。
- 强制 Cook：成功。
- 扫描 72 个节点：Error 0，Warning 0。

当前 Live HIP 有未保存修改；`Track1` 已解锁、`matchesCurrentDefinition=false`。因此本次没有保存 HIP/HDA，也没有把 Live 参数当成提交 `8` 的唯一事实源。Live 输出只作为兼容性检查：

| 输出 | Points | Primitives | Vertices |
|---|---:|---:|---:|
| `OUT_ROAD_MESH` | 32 | 30 | 90 |
| `OUT_ROAD_SHOULDERS` | 64 | 60 | 180 |
| `OUT_ROAD_COLLISION` | 64 | 90 | 270 |
| `OUT_ROAD_CENTERLINE` | 16 | 0 | 0 |
| `OUT_START_PREFAB_INSTANCE` | 0 | 0 | 0 |

Live Track 当前为固定采样 12 m、道路宽 20 m、横倾关闭、Width Ramp 1→1；这与提交场景的两个 Track 配置不完全相同。

### 11.4 隔离 HDA 验证

为了避免 Live HIP 未保存状态污染提交结论，另用 Houdini 21.0.440 `hython` 直接加载 Git 当前 `Track.hda` 并运行跟踪脚本：

```text
HoudiniProject/PCG_Track_21.0.440/scripts/tools/verify_curve_road_test.py
VERIFY_OK=1
```

该验证没有保存或修改项目 HDA/HIP。

## 12. 当前状态矩阵

| 功能 | 状态 | 当前结论 |
|---|---|---|
| Unity Spline 输入职责拆分 | 已完成 | Snapshot/Payload/Uploader/Interface 边界建立 |
| Authoring/Editor 程序集隔离 | 已完成 | Editor HAPI 不进入 Player 执行 |
| 组件序列化迁移 | 已完成 | `MovedFrom` + 原 `.meta` GUID，当前场景类型可解析 |
| Knot Contract V1 | 未改变 | Linear Carrier + 既有 Attribute 合约 |
| 多 Spline Transform | 待复验 | 非 Identity Root 下首分支/后续分支矩阵口径需专项测试 |
| 横倾公共参数术语 | 已完成 | UI 改为 Lateral Tilt/Knot Tilt |
| 内部 `road_bank_*` 兼容契约 | 已完成 Phase 8 | 刻意保留，避免下游断裂 |
| Road Width Ramp | 已完成 | 基准宽度×Ramp，主路最小 0.1 m，路肩固定米制 |
| 闭环 Width Ramp | 部分完成 | 支持闭环采样；首尾值需人工保持一致 |
| Authored-Up 节点整理 | 已完成 | 删除已 Bypass 冗余节点，直接接采样中心线 |
| Terrain 网络可读性 | 已完成 | 10 个命名分组与说明；生成算法未变 |
| HDA 自动验证 | 已完成 Phase 8 | 当前 `VERIFY_OK=1` |
| Unity EditMode 测试提交 | 未完成 | 本阶段只提交 `Tests.meta`，没有测试源码 |
| 双 Track 场景 | 部分完成 | 两套 HDA 输出存在；正式用途、同步与运行时保留策略未定义 |
| 起点龙门场景配置 | 待接入 | 接口仍在，但 Phase 8 提交场景已清空绑定 |
| Player Build 验证 | 未执行 | 需 Android/iOS + IL2CPP 检查 Authoring 依赖 |
| 移动端真机 Profiling | 未执行 | 需 Mali/Adreno/Apple GPU 数据 |

## 13. 下一阶段建议

1. 先修正 `Ensure-HoudiniMcp.ps1` 的 Houdini 进程检测，使其同时识别 `houdini` 与 `houdinifx`，避免 preflight 假失败。
2. 在不覆盖用户现场的前提下，对比当前未保存 `/obj/Track1` 与 `Track.hda` definition；明确保留或放弃 Live 修改后再保存 HIP/HDA。
3. 明确 `Track4` 的产品用途。若只是测试副本，应从主验证场景移除；若是正式第二赛道，应补独立 Spline 标记、Cook Sync、Bake 命名和可见性策略。
4. 恢复起点龙门时，只让明确的主 Track 输出 Start Prefab，并复验方向、路面贴合、净宽、碰撞和 Recook 稳定性。
5. 将当前需要的 EditMode 测试正式纳入 Git；至少覆盖 Snapshot 校验、坐标转换、Payload Contract 和多 Spline 非 Identity Transform。
6. 增加闭环 Width Ramp 首尾不一致的显式 Warning 或 Inspector 校验，不在 SOP 内静默篡改美术 Ramp。
7. 做 Android/iOS IL2CPP Player Build，确认 `PCGBike.Authoring` 的 HoudiniEngineUnity 引用不会引入不必要运行时代码或构建失败。
8. 继续将 Road/Shoulder/Collision/Start Prefab 转为可重现的 Bake 资源；移动端 Runtime 禁止依赖 HDA Cook。
9. 在 Mali、Adreno、Apple GPU 上比较双 Track 同时保留与单 Track Bake 的 DrawCall、顶点吞吐、Collider 内存和可见性成本。
