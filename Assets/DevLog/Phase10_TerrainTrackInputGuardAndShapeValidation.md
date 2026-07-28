# Phase 10 开发日志：Terrain Track 输入守卫与 Shape 回归验证

> 文档类型：Phase 10 增量开发日志
>
> 记录日期：2026-07-28
>
> 关联提交：`afb356c9e56339af19925139f41df68e4c8cad2d`（提交说明：`10`）
>
> 基线版本：Phase 9 日志提交 `c98a6ca941e90582471a2a07f0435e0e4afea644`
>
> 记录范围：只记录 `afb356c` 相对父提交 `c98a6ca` 新增、调整、替换或移除的内容

## 1. 日志范围与证据

本文不是 Track/Terrain 全量快照。Phase 1～Phase 9 已有的 Unity Spline 输入、Knot Contract V1、道路横倾、宽度 Ramp、自适应采样、拆分输出、Terrain 基础生成、Guide Mesh、Lake Constraint、Terrain Track Display SOP 安全解绑、道路 Shader 与起点 Prefab 接口继续以前述阶段日志为准。

Phase 10 只记录四条增量主线：

1. 不修改官方 Houdini Engine Unity 插件，在项目 Editor 层限制 `Terrain.track_geometry` 的输入类型。
2. Terrain HDA 从“任意点/Primitive 即有效”升级为带来源证明的道路表面合约。
3. 修正 Directional Ridge 的方向、Seed 与参数敏感性，并把 Terrain 分辨率收敛为唯一入口。
4. 新增可重复的 Houdini Shape 回归工具，并把 Phase 9 的 Track Binding 迁移脚本正式纳入 Git。

证据标记：

- **[已验证]**：可由 Git 父子差异、文本源码、Unity 场景序列化数据、Unity MCP 或 Houdini MCP 直接确认。
- **[隔离验证]**：通过 Houdini 21.0.440 独立 `hython` 进程加载提交 HDA/HIP，未保存项目文件。
- **[提交已实现]**：功能已进入目标提交，但视觉质量、Player Build 或移动端结果尚未完整验收。
- **[当前现场]**：来自 2026-07-28 的 Unity/Houdini Live Session；若现场 Dirty 或 definition 不匹配，不用于覆盖 Git 历史事实。
- **[待修复]**：已经确认存在契约、表达式、验证脚本或可移植性问题。
- **[未改变]**：本提交没有修改对应 Shader、材质、Renderer、RenderPass 或移动端运行时路径。

提交链：

```text
c98a6ca  Phase9
    -> afb356c  10
```

## 2. 提交概览

提交时间：2026-07-28 10:39:15 +08:00。

Git 统计为 8 个文件、`+4,089/-3,215`。其中 `Assets/PCG/Scenes/PCG.unity` 为 `+3,041/-3,215`，主要来自 Houdini Engine Recook 后的 fileID、nodeID、session handle、参数缓存与生成对象重序列化；不能把场景行数等同于同规模业务代码。

| 模块 | Phase 10 增量 | 当前状态 |
|---|---|---|
| 项目架构规则 | 新增官方 Houdini Engine Unity 插件零侵入保护 | [已验证] |
| Unity 输入守卫 | `track_geometry` 只允许 HDA 与 Unity Mesh | [已验证；Console 有拒绝记录] |
| Terrain Track 合约 | 只接受 Track HDA Contract 或带 Unity Mesh 来源标记的闭合道路表面 | [隔离验证] |
| Directional Ridge | 新增前后旋转链、Seed Offset 与严格参数行为 | [隔离验证] |
| Terrain 分辨率 | 删除 Preview/Bake 双入口，保留单一 Unity Terrain 兼容菜单 | [已验证；迁移仍有残留引用] |
| 道路净空 | 新增最终 HeightField 道路穿入保护与统计 Metadata | [隔离验证] |
| Shape 验证 | 新增只读 Hash/结构/参数敏感性回归脚本 | [隔离验证 PASS] |
| Binding 迁移工具 | Phase 9 的 Fail-Closed patch 首次纳入 Git | [已验证代码；对 Phase 10 最终 HDA 已过期] |
| Unity 场景 | `track_geometry` 由空 HDA 改为连接 `Track1`；Binding 组件仍关闭 | [已验证] |
| Terrain HIP | 保存 Shape/Track Contract/净空链与验证现场 | [提交已实现] |
| 渲染 | Shader、Material、RendererFeature、RenderPass、RT、Keyword 均未修改 | [未改变] |

## 3. 官方插件零侵入架构

### 3.1 新增强制保护规则

**状态：[已验证]**

`AGENTS.md` 新增“Houdini Engine Unity 插件保护（强制）”：

- 禁止修改 `Assets/Plugins/HoudiniEngineUnity/` 下的 Runtime、Editor、HAPI、程序集定义与 `.meta`。
- 官方 Inspector、通用输入类型、序列化结构和插件行为保持默认实现。
- 项目输入限制、兼容逻辑与数据合约必须落在 `Assets/PCG/`、HDA 网络或项目自有工具。
- 若功能只能通过侵入插件实现，必须停止并重新取得明确授权。
- 插件目录已有未提交修改时，视为用户或外部插件更新，不得擅自覆盖或还原。

这项规则决定了 Phase 10 的输入限制不去裁剪官方 Inspector 下拉菜单，而采用：

```text
官方 HEU Inspector 保持原样
    -> 用户可以看到通用输入类型
    -> 项目 Editor Guard 检查 Terrain.track_geometry
    -> HDA Contract 再做几何来源与表面级 Fail-Closed
```

两层防线分别负责 Unity 输入类型与 Houdini 几何内容，不形成侵入式插件 Fork。

## 4. Unity Terrain Track Geometry Input Guard

### 4.1 目标实例与允许类型

**状态：[已验证]**

新增：

`Assets/PCG/Scripts/Editor/Houdini/Terrain/TerrainTrackGeometryInputGuard.cs`

该类是 `[InitializeOnLoad]` Editor-only 静态守卫，不挂载为场景 MonoBehaviour。它只处理同时满足以下条件的对象：

- 场景中的 `HEU_HoudiniAssetRoot`，不是 Project 中的持久资产。
- `AssetOpName == pcgbike::Object/Terrain::1.0`。
- HDA 路径以 `Assets/PCG/HDA/Terrain.hda` 结尾。
- HEU InputNode 的 `ParamName == track_geometry`。

允许类型：

```text
HDA
UNITY_MESH
```

不允许的通用类型包括但不限于：

```text
SPLINE
CURVE
TERRAIN
BOUNDING_BOX
TILEMAP
```

守卫通过 Unity `SerializedObject` 读取 HEU InputNode 的 `_inputObjectType` 与 `_pendingInputObjectType`。这是项目代码对插件序列化实现的只读耦合，没有修改插件源文件。

### 4.2 拒绝后的 Fail-Closed 流程

**状态：[已验证代码结构；Unity Console 有实测证据]**

发现不支持类型后执行：

```text
Undo.RecordObject(input)
    -> RemoveAllInputEntries(false)
    -> PendingObjectType = HDA
    -> 当前类型切回 HDA
    -> track_binding_enabled = 0
    -> track_display_sop_path = ""
    -> TerrainTrackDisplaySopBinding.DetachAndRestoreBaseNow()
    -> 标记 Input/Asset/Root/Scene Dirty
    -> RequestCook(bUploadParameters: false)
```

核心约束：

- 旧输入连接被清空，不允许曲线或 Terrain 数据继续残留。
- Display SOP 自动绑定也同步关闭，避免通用输入被拒绝后仍由隐藏路径继续形变 Terrain。
- Cook 使用 `bUploadParameters=false`，防止 HEU 旧序列化参数缓存覆盖刚由 HAPI 写入的解绑值。
- Warning 按 Input instance ID 与被拒绝类型去重，避免同一错误每 0.25 秒刷屏。

2026-07-28 Unity Console 可确认 `SPLINE`、`CURVE`、`TERRAIN`、`BOUNDING_BOX`、`TILEMAP` 均触发：

```text
old connection cleared
input reset to an empty HDA
base-terrain cook requested
```

当前 Console 最近 120 分钟为 Error 0、Exception 0；上述记录是预期 Warning，不是编译错误。

### 4.3 调度与 Editor 成本

**状态：[已验证代码结构；性能待 Profile]**

守卫订阅：

- `EditorApplication.update`
- `EditorApplication.hierarchyChanged`
- `Undo.undoRedoPerformed`

在编译、AssetDatabase 更新、进入 Play Mode 或重入扫描时跳过。事件触发后立即重扫；稳定状态仍每 0.25 秒调用一次：

```csharp
Resources.FindObjectsOfTypeAll<HEU_HoudiniAssetRoot>()
```

该扫描只存在于 Editor，不进入 Android/iOS Runtime，但场景中 HDA 数量增加后会形成固定 Editor CPU 成本。后续应改成事件驱动候选集合或缓存目标 Root，并用 Editor Profiler 验证。

### 4.4 已知实现风险

- 依赖 HEU 私有序列化字段名与枚举字符串，插件升级后可能失效。
- `_pendingInputObjectType` 读取为空时，当前判断可能提前把结果视为空字符串，掩盖 current type 的非法值。
- HAPI 参数写入、Binding Detach、Input Undo 与已经发出的 Cook 不是同一个原子 Undo 事务。
- `LastRejectedTypeByInput` 没有对销毁对象显式清理，长期编辑可能残留少量字典项；Instance ID 复用还可能抑制一次 Warning。
- `RequestCook` 返回值没有被检查，当前只保证发出请求，不保证每次请求都被 HEU 接受。

## 5. Terrain Track Surface Contract

### 5.1 从“有几何即有效”收紧为来源合约

**状态：[隔离验证]**

Phase 9 的 `TRACK_validate_contract` 只检查：

```text
npoints > 1 || nprimitives > 0
```

因此 Curve、Polyline、任意 Houdini Geometry 都可能被误认为可用于道路贴合。

Phase 10 要求输入来源满足二选一：

| 来源 | 必要证据 |
|---|---|
| Track HDA | Detail `road_input_valid`、Detail `road_total_width`、Point `road_generated_center` |
| Unity Mesh | Primitive/Detail/Point 任一层存在 `unity_input_mesh_name` |

输出来源写为：

```text
terrain_input_source = TRACK_HDA | UNITY_MESH | REJECTED
terrain_input_rejected = 0 | 1
```

只把“Object Type 是 HDA”当作 Unity 输入层白名单还不够；Houdini 层仍要求 HDA 输出携带 Track Contract，防止普通 HDA 几何绕过语义校验。

### 5.2 道路表面过滤

**状态：[隔离验证]**

通过来源校验后，Primitive 还必须满足：

- 类型为闭合 `Poly`。
- 顶点数至少为 3。
- 面法线与世界 Y 的绝对点积大于 0.05，排除近垂直面。
- 不属于 `skirt_l` 或 `skirt_r`。

Curve、Line、Open/退化面、近垂直面和道路 Skirt 会从送往下游的 Track Geometry 中删除。

道路宽度来源优先级：

```text
Track HDA road_total_width
    -> road_width
    -> Point width
    -> fallback_road_width
```

无合法输入时：

```text
terrain_input_valid = 0
terrain_input_rejected = 1（存在几何但来源不合法时）
terrain_input_source = REJECTED
Terrain 输出基础地形，不执行 Track 形变
```

### 5.3 Unity 与 HDA 双层边界

```text
Unity Editor Guard
    输入类型只允许 HDA / UNITY_MESH
        -> Terrain HDA Contract
           HDA 必须有 Track provenance
           Unity Mesh 必须有 unity_input_mesh_name
              -> Surface Filter
                 只保留闭合、非 Skirt、可作为高度目标的道路面
                    -> Conform / Track Context / Adaptive Earthwork
```

这套边界不接受 Curve/Spline 直接作为 Terrain 路面。Unity Spline 必须先经过 Track HDA 生成稳定道路表面与 Metadata，再进入 Terrain。

## 6. Terrain Shape 与 Directional Ridge

### 6.1 Directional Ridge 旋转链

**状态：[隔离验证]**

旧链路：

```text
BASE_detail_switch
    -> BASE_directional_ridge
       flowrot = ridge_angle
    -> BASE_ridge_switch
```

Phase 10：

```text
BASE_detail_switch
    -> BASE_ridge_pre_rotate
       HeightField Transform Y = +ridge_angle
    -> BASE_directional_ridge
       Sparse Convolution
       flowrot = 0
       elementscalex = 0.35
    -> BASE_ridge_post_rotate
       HeightField Transform Y = -ridge_angle
    -> BASE_ridge_switch
```

Terrain HDA 内部节点总数由 184 增至 192；新增的 8 个节点由 Directional Ridge 两个 Transform 与最终道路净空保护链构成。

新增 `Directional_Ridge_Frame` Network Box 与学习说明，使节点职责可在 Houdini Network View 中直接阅读。

前后相反旋转把方向控制作用到 HeightField 坐标域，同时将结果恢复到原地形坐标；关闭 Ridge 时 Switch 仍直接旁路 `BASE_detail_switch`。

### 6.2 Seed、Strength 与高度倍率

**状态：[隔离验证]**

Ridge Noise 新增：

```text
offsetx = (seed - 1) * 101.03
offsetz = (seed - 1) * 53.17
```

回归契约：

- `ridge_angle`：0°、45°、90°输出不同，0°与 360°一致。
- `ridge_strength = 0` 与关闭 Ridge 等价。
- Strength 0.5 与 1.0 输出不同。
- Seed 0/1/2 输出不同；重复 Seed 100000 确定。
- 关闭 Ridge 后，angle/strength/seed 不再污染输出。
- `mountain_height_scale` 同时影响 Macro 与 Ridge。

### 6.3 参数 UI 条件

**状态：[已验证]**

| 参数 | Disable When |
|---|---|
| `seed` | Macro/Mid/Detail/Ridge/Erosion 全部关闭 |
| `ridge_angle` | `enable_ridge == 0` |
| `mountain_height_scale` | Macro 与 Ridge 均关闭 |

Seed 不再在所有随机模块关闭时保持无意义的可编辑状态。

## 7. 单一 Terrain Resolution

### 7.1 删除 Preview/Bake 双入口

**状态：[已验证]**

删除公共参数：

- `use_bake_resolution`
- `bake_resolution`

HDA 公共参数模板总数由 115 减至 113，没有新增公共参数，也没有确定的内部 name 重命名。

`tile_resolution` 内部 name 保持，UI 改为：

```text
Terrain Resolution / 地形分辨率
129 / 257 / 513 / 1025 / 2049
Default: 513
```

这些档位符合 Unity Terrain 的 `2^n + 1` 高度图要求。`terrain_effective_resolution` 直接读取 `tile_resolution`，不再在 Preview/Base 与 Final Bake 两套入口之间切换。

Unity 提交场景实例由历史数值 256 修正为 257，Terrain Volume Cache 的 X/Y Length 同步为 257。

### 7.2 未完成的表达式迁移

**状态：[待修复]**

虽然两个公共参数已删除，当前 Live 全树扫描仍发现 `HF_DOMAIN/height_volume1` 与 `mask_volume2` 的 Domain Size 表达式引用：

```text
use_bake_resolution
bake_resolution
```

结果是 `Bad parameter reference` Warning。目标 Shape 输出和最终 HeightField 仍可 Cook，且没有 error，但“单一分辨率迁移”不能标成完全完成。

修复时应把 HF_DOMAIN 的 X/Z Size 与所有 Resample/Metadata 统一改为只依赖 `tile_resolution`，再对 129/257/513/1025/2049 五档做 Domain、Volume、Unity TerrainData 一致性测试。

## 8. 最终道路净空保护

### 8.1 新增保护链

**状态：[隔离验证]**

Terrain HDA 新增 6 个最终保护节点：

- `FINAL_road_clearance_guard`
- `FINAL_seed_clearance_layers`
- `FINAL_clearance_metrics`
- 两个 Volume Reduce
- `FINAL_cleanup_clearance_layers`

`OUT_FINAL_HEIGHTFIELD_LAYERS` 从原 `MASK_apply_water_exclusions` 改接清理节点。

保护逻辑以 0.5 voxel 半径的九点邻域读取最低道路目标，只允许降低最终 Terrain，不抬高地形；目的是消除低分辨率重建或滤波后道路穿入地形的问题。

临时 `__terrain_clearance_*` Layer 在稳定输出前清理，不扩大正式 Layer 合约。

### 8.2 Metadata 1.12

**状态：[隔离验证]**

`terrain_contract_version` 从 `1.11` 升级为 `1.12`。

新增：

- `terrain_input_rejected`
- `terrain_input_source`
- `terrain_road_penetration_sample_count`
- `terrain_clearance_guard_voxel_radius`
- `terrain_clearance_guard_reconstruction_margin`

移除：

- `terrain_input_is_curve`

`terrain_max_road_clearance_error` 改为最终保护后的 `terrain_max_final_road_clearance_error` 来源。

隔离提交 HIP 的有效 Track 结果：

```text
terrain_input_valid = 1
terrain_input_source = TRACK_HDA
terrain_input_rejected = 0
terrain_max_final_road_clearance_error = 0
terrain_road_penetration_sample_count = 0
terrain_clearance_guard_voxel_radius = 0.5
terrain_clearance_guard_reconstruction_margin ≈ 0.030656
terrain_contract_version = 1.12
terrain_effective_resolution = 513
```

稳定输出名仍为 `OUT_TERRAIN_HEIGHTFIELD` 与 `OUT_TERRAIN_METADATA`。

## 9. Houdini 自动化工具

### 9.1 Track Binding Safety Patch 正式纳入 Git

**状态：[代码已提交；不再兼容 Phase 10 最终 HDA]**

新增：

`HoudiniProject/PCG_Track_21.0.440/scripts/tools/patch_terrain_track_binding_safety.py`

该脚本把 Phase 9 的一次性迁移过程正式保存为源码：

- 增量修改已有 `pcgbike::Terrain::1.0`，不使用 builder 重建全网。
- 隐藏 `track_binding_enabled` 与工作流说明。
- 自动 Display SOP、公共 `track_geometry`、HDA Input 0、Empty Fallback 优先级。
- Adaptive/Track Context 的 `terrain_input_valid` 门控。
- Metadata 1.10→1.11 与 `terrain_track_binding_enabled`。
- HeightField 逐 voxel SHA-256。
- 正式模式创建时间戳 HDA 备份；dry-run 使用临时副本。
- 异常恢复磁盘 HDA；不保存 HIP。

但它针对 Phase 9 的旧 Track Validator：

- `_patch_nodes()` 期待旧 Warning 文本。
- `_create_validation_track()` 只创建普通 Add Curve，没有 Track HDA provenance，也不是带 `unity_input_mesh_name` 的闭合 Unity Mesh。

在 Phase 10 最终 HDA 上：

```text
terrain_input_source = REJECTED
terrain_input_rejected = 1
terrain_input_valid = 0
warning = Terrain accepts only Track HDA contract geometry or Unity Mesh geometry
```

因此该脚本现在只能作为 Phase 9 迁移历史和回滚参考，不能继续标成 Phase 10 当前 HDA 的可重复回归测试。需要升级测试夹具为合法 Track HDA Surface 或带 Unity Mesh provenance 的闭合 Polygon。

### 9.2 Terrain Shape 只读验证

**状态：[隔离验证 PASS]**

新增：

`HoudiniProject/PCG_Track_21.0.440/scripts/tools/validate_terrain_shape_params.py`

脚本默认加载：

```text
HIP: PCG_Bike_Terrain.hip
Node: /obj/Terrain1
Output: TerrainCore/10_TERRAIN_SOURCE/OUT_BASE_HEIGHTFIELD
```

验证范围：

- Directional Ridge 拓扑、类型、连接、表达式与 Network Box。
- Ridge angle/strength/seed 的敏感性、旁路等价与确定性。
- Macro/Mid/Detail 的 Amp/Size 确实改变 HeightField。
- Erosion 开启时 Iterations 1/2 不同，关闭时被忽略。
- `mountain_height_scale` 对 Macro/Ridge 生效。
- 分辨率、Layer、点/面/顶点结构在参数敏感性测试中保持稳定。
- HeightField 不含 NaN/Inf。

脚本在 `finally` 中恢复触碰参数并重新 Cook，不保存 HIP/HDA。

### 9.3 本次隔离运行结果

**状态：[隔离验证]**

对全新 `Terrain.hda` definition 实例运行：

```text
Status: PASS
Definition matches current: true
Resolution: 513 × 513 × 1
Layers: height + mask
Points / Primitives / Vertices: 2 / 2 / 2
Warnings on verified output: 0
Five-run median: 37.3589 ms
Saved: false
```

对提交 `PCG_Bike_Terrain.hip` 实例运行同样为 PASS，五次中位约 36.2428 ms。

这些时间包含强制 Cook、HeightField 读取、有限值扫描与 SHA-256，不是纯 SOP Cook Profiler 数据；样本仅 5 次，只能用于开发机回归，不能当移动端或最终 Bake 性能指标。

验证脚本仍有边界：

- 第一次 isolated 参数写入与 reference snapshot 位于 `try/finally` 之前，若此前异常，内存参数不一定恢复。
- Warning 被记录但不作为失败条件。
- 只识别 `hou.Volume` Height，不覆盖 VDB Height。
- 节点名、表达式与 UI 条件为精确字符串契约；良性重命名也会导致失败。

## 10. Unity 场景与 Terrain HIP

### 10.1 场景对象结构

**状态：[已验证 Git 与 Unity MCP]**

`PCG.unity` 前后均为：

- 150 个 YAML Document。
- 24 个普通 GameObject。
- 12 个 Scene Root。
- `Track1`、`Track4`、`Terrain1` 层级保持。

没有净增/净删 GameObject 或 Component。Guard 是静态 Editor 类，没有被错误挂入场景。

### 10.2 Track 输入改为通用 HDA 连接

**状态：[已验证]**

父提交的 `Terrain1.track_geometry` 是空 HDA。提交 `10` 仍保存为允许的 HDA 类型，但 `_inputAssetInfos` 已连接 `Track1`。

与此同时 `TerrainTrackDisplaySopBinding` 保持：

```text
m_Enabled = 0
_bindingState = Detached
_lastBoundPath = ""
_lastCookSummary = Terrain cook completed successfully.
```

因此 Phase 10 场景的正式 Track→Terrain 链路是：

```text
Track1 HDA
    -> Terrain1.track_geometry 通用 HDA Input
    -> Terrain HDA Track Surface Contract
```

不是 Phase 9 的隐藏 Display SOP 自动绑定。

`terrain_guide_meshes` 仍为空；`lake_curves` 仍连接 `Spline (1)`。

### 10.3 Terrain 输出与位置

**状态：[提交场景序列化结果]**

Terrain 输出对象名称与组件集合保持：

```text
TerrainCore_OUT_TERRAIN_HEIGHTFIELD_OUT_TERRAIN_HEIGHTFIELD_0
Transform + Terrain + TerrainCollider
```

真实变化：

- Terrain Resolution 256→257。
- 输出 Local Position：`(-255, 0, -255)` → `(-802.99744, -4.995182, -527.07043)`。
- HEU Terrain Offset 与 HDA Last Synced Transform 同步更新。

Terrain Material 只更换 YAML fileID；移除 fileID Header 后内容一致。

### 10.4 Track Recook 噪声

**状态：[已验证]**

`Track1` 内部 Session 名 `Track9`→`Track7`，三个生成对象同步改为 `Track7_OUT_ROAD_*`，但 Unity 根对象仍为 `Track1`。

道路 Mesh 几何 payload 未改变：

| 输出 | Vertices | 结论 |
|---|---:|---|
| Road | 2,148 | 父子 payload、Bounds 一致 |
| Shoulders | 4,296 | 父子 payload、Bounds 一致 |
| Collision | 6,444 | 父子 payload、Bounds 一致 |

`_isCookingAssetReloaded` 从 1 变为 0，多个 `hasGeoChanged` 从 1 变为 0，说明提交场景保存时比 Phase 9 更接近 post-cook settled 状态。

### 10.5 HIP 与缓存边界

**状态：[提交已实现；可移植性待修复]**

`PCG_Bike_Terrain.hip`：

```text
788,334 -> 841,097 bytes
Terrain1 internal children: 183 -> 191
```

提交 HIP 额外保存 `_mcp_cam_center` 与 `_mcp_render_cam` 及其内部节点；这些是 MCP 预览/截图工具残留，不属于 Terrain 输出契约。

Unity 场景中的 TerrainData GUID 指向被 `.gitignore` 排除的：

```text
Assets/HoudiniEngineAssetCache/Working/.../TerrainData.asset
```

干净检出后仍需要 Recook 才能恢复 TerrainData。场景直接引用 ignored Working Cache 是既有但仍未解决的可移植性风险，正式交付应 Bake 到 `Assets/PCG/Generated/Terrain/` 等受版本控制的稳定路径。

## 11. 性能、兼容性与运行时边界

### 11.1 CPU 与 GPU

| 阶段 | CPU/Houdini/Editor | GPU/移动端 Runtime |
|---|---|---|
| Input Guard | 每 0.25 秒扫描已加载 HDA；非法输入时清理与 Cook | 无 |
| Track Contract | Houdini Cook 时做 Primitive 来源/表面过滤 | 无 |
| Directional Ridge | 两次 HeightField Transform + Sparse Noise | 无 |
| Clearance Guard | Houdini HeightField 邻域处理、Reduce 与清理 | 无 |
| Shape Validator | 离线多次 Cook、全体素扫描与 Hash | 无 |
| Bake 后 Player | 只消费 Unity Terrain/Mesh/Metadata | 最终资产渲染成本 |

Phase 10 增加的是开发期 CPU/Houdini 成本，不增加移动端逐帧 HAPI、Compute、RenderPass 或 Shader ALU。

### 11.2 URP、Pass、带宽与 Variant

本阶段没有修改 Shader、Material、RendererFeature、ScriptableRenderPass 或 URP Renderer：

- 新增 RenderPass：0。
- `RenderPassEvent`：不适用。
- 新增 RenderTexture：0。
- 新增 Blit/MRT：0。
- 新增 Shader Keyword：0。
- 新增 Shader Variant：0。
- 新增运行时纹理采样：0。

Directional Ridge 与 Clearance Guard 都在 Houdini Cook/Bake 阶段，不增加 Mali、Adreno 或 Apple GPU 的逐帧带宽。移动端性能仍取决于最终 Terrain Resolution、Bake Mesh、Collider、DrawCall 与材质层数量。

### 11.3 兼容性

- Guard 依赖当前 HEU InputNode 私有字段与枚举名，升级 Houdini Engine Unity 插件后必须复验。
- Terrain Resolution 使用 Unity Terrain 兼容档位，但 1025/2049 会显著增加 Editor Cook、TerrainData 内存与移动端采样成本；默认不应直接把高档位当移动端运行质量。
- 不使用 Geometry Shader、MRT、额外全屏 Pass 或运行时 Houdini Cook。
- 尚未执行 Android/iOS IL2CPP Player Build 与 Mali/Adreno/Apple GPU 真机 Profiling。

## 12. 本版本验证记录

### 12.1 Git

- 目标提交：`afb356c9e56339af19925139f41df68e4c8cad2d`。
- 父提交：`c98a6ca941e90582471a2a07f0435e0e4afea644`。
- 8 个文件变化，新增 4 个文件。
- `Terrain.hda`：101,169→103,399 bytes。
- Terrain HDA：公共参数 115→113，内部节点 184→192。
- `PCG_Bike_Terrain.hip`：788,334→841,097 bytes。
- `TerrainTrackGeometryInputGuard.cs`：239 个 Git 新增行。
- Binding patch：412 个 Git 新增行。
- Shape validator：378 个 Git 新增行。

### 12.2 Unity MCP

2026-07-28 只读确认：

- Unity Editor：2022.3.62f2。
- 未播放、未暂停、未编译、未进行 AssetDatabase 更新。
- `Assets/PCG/Scenes/PCG.unity` 已加载、有效、Build Index 0、Root Count 12。
- 当前场景为 Dirty；本文没有保存场景，提交结论以 Git YAML 为准。
- `Terrain1` 激活；其 `TerrainTrackDisplaySopBinding` 组件关闭。
- 最近 120 分钟 Error 0、Exception 0。
- Console 存在 Guard 对不支持类型的预期 Warning。

### 12.3 Houdini MCP 与隔离 Hython

Preflight：

```text
Houdini RPC: 21.0.440
18811: connected
3055 health: healthy
Codex Houdini MCP tools: discovered
Current HIP: PCG_Bike_Terrain.hip
```

当前 Live `/obj/Terrain1`：

- Definition 指向 `Assets/PCG/HDA/Terrain.hda`。
- 当前实例已解锁，`matchesCurrentDefinition=false`。
- 当前 HIP 有未保存修改。
- Root error 0。
- 全树只读扫描发现 20 个 Warning，其中包含已删除 Resolution 参数的 Bad Reference，以及既有 HeightField `name`/Alpha Visualization Warning。

由于 Live 现场 Dirty，本文没有保存 HIP/HDA，也没有用 Live 参数覆盖提交事实。

隔离 `hython`：

- 全新 HDA definition：Shape 回归 PASS，`matchesCurrentDefinition=true`，未保存。
- 提交 HIP 实例：Shape 回归 PASS，未保存。
- 提交 HIP 全链 Root Cook：Error 0。
- 合法 Track Contract 输出：`terrain_input_valid=1`、`source=TRACK_HDA`、最终道路穿入计数 0。
- Binding patch 自带的旧 Add Curve 验证夹具：被 Phase 10 新合约正确拒绝，因此该工具当前不是 PASS。

## 13. 当前状态矩阵

| 功能 | 状态 | 当前结论 |
|---|---|---|
| 官方 HEU 插件保护规则 | 已完成 | 禁止项目需求侵入插件源码 |
| Terrain Input Guard | 已完成代码 | HDA/UNITY_MESH 白名单，非法类型 Fail-Closed |
| Guard Unity 实测 | 已完成 | 多种非法类型均被拒绝；Console Error 0 |
| Guard 自动化测试 | 未完成 | 没有提交 Unity EditMode Tests |
| Track HDA provenance | 已完成 | 要求 Track Contract Metadata |
| Unity Mesh provenance | 已完成 | 要求 `unity_input_mesh_name` |
| Surface Filter | 已完成 | 只保留闭合、非 Skirt、可作为高度目标的 Polygon |
| Curve/Spline 直接输入 | 禁止 | 必须先生成道路 Surface |
| Terrain Contract 1.12 | 已完成 | 新增 input source/rejected 与 clearance 指标 |
| Directional Ridge 旋转链 | 已完成 | Pre Rotate → Sparse Ridge → Post Rotate |
| Ridge 参数敏感性 | 已验证 | Angle/Strength/Seed/Height Scale 均通过回归 |
| 单一 Terrain Resolution UI | 部分完成 | 公共参数已收敛；HF_DOMAIN 仍有旧引用 |
| Final Road Clearance Guard | 已完成 | 隔离结果误差 0、穿入计数 0 |
| Shape Validator | 已完成 | HDA definition 与提交 HIP 均 PASS |
| Binding Safety Patch | 已提交但过期 | Phase 9 迁移可追溯；验证夹具不兼容 Phase 10 合约 |
| Unity Track→Terrain HDA Input | 已接入 | 提交场景 `track_geometry` 连接 `Track1` |
| Display SOP Binding | 关闭 | 场景继续保存 Detached 状态 |
| Scene Working Cache 可移植性 | 未完成 | TerrainData 仍在 ignored HEU cache |
| Player Build | 未执行 | Android/iOS IL2CPP 待验证 |
| 移动端真机 Profiling | 未执行 | Mali/Adreno/Apple GPU 待验证 |

## 14. 下一阶段建议

1. 修复 HF_DOMAIN 所有 `use_bake_resolution` / `bake_resolution` 残留表达式，并对五档 Terrain Resolution 做结构与 Unity TerrainData 验证。
2. 升级 `patch_terrain_track_binding_safety.py`：识别 Contract 1.12，使用合法 Track HDA Surface 测试夹具，并把 Phase 9 一次性迁移与当前回归检查拆成两个脚本。
3. 为 `TerrainTrackGeometryInputGuard` 增加 EditMode Tests，覆盖 HDA/UNITY_MESH 放行、所有非法类型拒绝、空 Pending Type、Warning 去重和 Undo 边界。
4. 将 Guard 从固定 `Resources.FindObjectsOfTypeAll` 扫描改为事件驱动缓存，保留低频兜底，并记录 Editor CPU/GC。
5. 对 HDA 合法 Track、Unity Mesh、无 provenance HDA、Curve、Open Poly、Skirt、近垂直面建立完整 Contract 测试矩阵。
6. 把 Clearance Guard 的 voxel radius、margin、penetration count 纳入 Metadata 自动断言，并覆盖 129/257/513/1025/2049。
7. 清理 `PCG_Bike_Terrain.hip` 中 `_mcp_cam_center`、`_mcp_render_cam` 工具残留；保存前确认 Terrain1 是否应保持 editable/mismatch definition。
8. 将 Unity TerrainData 从 ignored Working Cache Bake 到受版本控制的稳定目录，验证干净检出无需临时 Cache 即可打开主场景。
9. 明确 257/513/1025 在移动端的质量档位；对 Terrain 内存、Collider、主线程 Cull、DrawCall 与带宽做 Android/iOS 真机 Profiling。
10. 执行 Android/iOS IL2CPP Player Build，确认 Guard、HAPI 与 Houdini 验证代码完全限制在 Editor/开发期。
