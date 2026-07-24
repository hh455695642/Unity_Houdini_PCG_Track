# Phase 5 开发日志：Guide Mesh 有限过渡与 Lake 湖岸约束重构

> 文档类型：Phase 5 增量开发日志
>
> 记录日期：2026-07-18
>
> 关联提交：`74bc0b0e16018a6d109cd47247c0b160ee8949da`（提交说明：`5`）
>
> 基线版本：Phase 4 功能提交 `9305081`，Phase 4 日志提交 `2390673`
>
> 记录范围：只记录提交 `74bc0b0` 相对其父提交 `2390673` 新增、调整、替换或移除的内容

## 1. 日志范围与证据

本文不是 Terrain 系统全量快照。Terrain HDA 的四路输入、基础 HeightField、Track 精确贴合、9 个内部 Mask、三路固定输出、Unity Terrain 接入和 Track Display SOP 编辑器绑定以 Phase 4 日志为准。

证据标记：

- **[已验证]**：通过 Git 差异、父子版本 HDA 独立结构快照、当前 Houdini MCP 强制 Cook、节点参数、Geometry、Unity MCP 或场景 YAML 直接确认。
- **[提交已实现]**：节点与参数已经进入 `74bc0b0`，但提交没有包含验证 HIP、Unity 场景 Recook/Bake 或自动化回归结果。
- **[待复验]**：算法已实现，仍缺 Guide/Lake 代表性输入、边界样例或移动端最终 Bake 验证。
- **[未改变]**：继续沿用 Phase 4 契约，本阶段没有扩展交付范围。

提交 `74bc0b0` 只修改一个文件：

| 文件 | Phase 4 | Phase 5 | 变化 |
|---|---:|---:|---|
| `Assets/PCG/HDA/Terrain.hda` | 82,281 bytes | 88,660 bytes | +6,379 bytes；Guide Mesh 与 Lake 约束网络重构 |

`Terrain.hda.meta` 没有变化，Unity GUID 继续保持 `15a73d0f61bb98040ae78ced958c3bf9`。本提交没有修改 `.hip`、Unity 场景、C#、Shader、Material、Package、测试脚本或 Bake 资产。

## 2. Phase 5 提交概览

| 模块 | 本阶段增量 | 当前状态 |
|---|---|---|
| Guide 输入清理 | 过滤近垂直侧壁，目标高度与真实覆盖 Mask 分开投影 | [已验证] |
| Guide 细节保留 | 引入低频 Base、归一化 Delta、核心权重和独立细节尺度 | [已验证；代表性美术 Mesh 待复验] |
| Guide 有限过渡 | 过渡只在指定边界带内扩散，并增加坡度安全包络 | [已验证] |
| Guide Road 保护 | Guide 在道路核心/路肩/Track Context 内提前卸载，避免 Road Exact Conform 产生深沟 | [已验证；极端高差待复验] |
| Lake 输入安全 | 无有效闭合曲线时切到远离 Domain 的占位闭环，避免空 PolyFill 链路 | [已验证] |
| Lake Mask | 不再用目标高度差推断湖区，改为独立 HeightField Project 记录真实覆盖 | [已验证] |
| Lake 湖岸 | 新增核心/边缘权重、归一化水位延拓、低通岸线和平坦度控制 | [已验证；复杂岸线待复验] |
| 临时层清理 | Guide/Lake 混合后立即删除 `guide_*` / `lake_*` 临时 Volume | [已验证] |
| 输出契约 | 三路 Output、`height` 主输出和 Metadata v1.3 保持不变 | [未改变] |
| Unity 集成 | HDA GUID 不变，但提交没有保存 Unity 场景 Recook/Bake 结果 | [待复验] |

本阶段仍然只影响 Houdini/Unity 编辑器期地形生成。没有新增 RendererFeature、RenderPass、RenderTexture、Compute Shader、Shader keyword 或移动端运行时 Houdini 依赖。

## 3. HDA 结构差异

### 3.1 父子版本只读对比

**状态：[已验证]**

本次使用独立 `hython` 进程分别加载父提交 `2390673` 与当前提交 `74bc0b0` 的 `Terrain.hda`，没有切换分支、覆盖当前 HDA 或修改正在打开的 Houdini 场景。

| 项目 | Phase 4 | Phase 5 |
|---|---:|---:|
| `TerrainCore` 直接子节点 | 117 | 140 |
| 新增节点 | - | 25 |
| 移除节点 | - | 2 |
| HDA `Contents.gz` Section | 52,020 bytes | 56,879 bytes |
| HDA `DialogScript` Section | 25,468 bytes | 26,523 bytes |
| HDA 类型 | `pcgbike::Terrain::1.0` | 不变 |
| Metadata Contract | `1.3` | 不变 |

移除节点：

```text
LAKE_MASK
LAKE_MASK_BLUR
```

新增节点集中在 Guide 和 Lake 两条链路：

```text
Guide：12 个新增节点
  SURFACE_FILTER / PROJECT_MASK
  CORE_SEED / CORE_FEATHER / CORE_WEIGHT
  BASE_BLUR / NORM_BLUR
  TRANSITION_DELTA_BUILD / TRANSITION_NORM_BLUR / TRANSITION_DELTA_BLUR
  EDGE_FEATHER / TEMP_CLEANUP

Lake：13 个新增节点
  EMPTY_CLOSED / POLYFILL_INPUT / PROJECT_MASK
  TRANSITION_LAYERS
  CORE_SEED / CORE_FEATHER / CORE_WEIGHT
  BASE_BLUR / EDGE_FEATHER / NORM_BLUR / LEVEL_BLUR
  LEVEL_BUILD / TEMP_CLEANUP
```

注：上面的职责分组按功能描述；实际新增节点总数以 Git 父子 HDA 快照得到的 25 个为准。

### 3.2 网络组织

**状态：[已验证]**

前 7 个 Network Box 仍使用 `__netbox1`～`__netbox7` 的通用名称，没有在本阶段规范化。第 8 个约束分区由 20 个节点扩展到 43 个节点，说明更新为：

```text
原生 Mesh + Closed Spline 地形约束
Guide 归一化差值保细节 + 有限过渡 + Road 保护
Lake 平缓湖岸
```

约束 Sticky Note 同步补充了 Guide 真实命中、Lake 独立 Mask、Bank Width 内外过渡语义、Shore Flatness 和临时层清理说明。核心生成逻辑继续保留为可读 SOP/HeightField/VEX 网络，没有引入 Python builder 黑盒。

## 4. Guide Mesh 约束重构

### 4.1 真实表面与覆盖范围分离

**状态：[已验证]**

Phase 4 使用“目标高度与基础高度是否存在差值”推断 Guide Mask。这会漏掉与原地形高度接近的有效 Guide 区域，也可能把侧壁或投影缝隙当成需要扩散的边界。

Phase 5 改为：

```text
IN_terrain_guide_meshes
  -> GUIDE_MESH_SURFACE_FILTER
       ├─ GUIDE_MESH_PROJECT_TARGET   // 目标高度
       └─ GUIDE_MESH_PROJECT_MASK     // 真实覆盖 Mask
```

`GUIDE_MESH_SURFACE_FILTER` 按 Primitive Normal 清理近垂直面：

```text
abs(normal.y) < 0.05 或法线无效
  -> 删除 Primitive
```

该规则保留可作为地形表面的朝上/朝下近水平面，排除封闭 Mesh 侧壁对高度投影的干扰。Target 与 Mask 两个 HeightField Project 均启用 3 Rays、Jitter 和中值合并，降低缝隙与单射线尖刺。

### 4.2 细节保留与归一化 Delta

**状态：[已验证]**

Guide 中间层从 Phase 4 的单一 `guide_delta` 扩展为：

| 临时层 | 职责 |
|---|---|
| `guide_edge` | Guide 的有限外沿权重 |
| `guide_norm` | Delta 归一化分母 |
| `guide_delta` | Guide 核心的预乘高度差 |
| `guide_base_low` | 基础地形低频高度 |
| `guide_core_weight` | 核心精确约束权重 |
| `guide_transition_norm` | 过渡区归一化分母 |
| `guide_transition_delta` | 过渡区预乘高度差 |

核心 Delta 使用：

```text
guide_delta = (target_height - guide_base_low) * core_mask
```

而不是直接对 Target Height 做无界模糊。Blur 后由 `norm` 解预乘，可避免边缘权重降低时高度被错误拉向 0。

新增参数：

| 参数 | 默认值 | 范围 | 职责 |
|---|---:|---:|---|
| `guide_mesh_detail_scale` | 20 m | 1～200 m | 基础高度与 Guide Delta 的低通尺度 |
| `guide_mesh_detail_preserve` | 1.0 | 0～1 | 在核心区从精确目标差过渡到“相对低频 Base”的细节保留差值 |
| `guide_mesh_transition_slope` | 30° | 5～60° | 只限制边缘 Delta 的坡度安全包络，不扩大 Guide 影响范围 |

`guide_mesh_detail_preserve = 1` 时，Guide 更偏向保留目标表面相对低频地形的局部细节；设为 0 时更接近直接贴合目标高度。

### 4.3 有限过渡与 Road 保护

**状态：[已验证；极端输入待复验]**

新链路把核心与边缘分开处理：

```text
真实覆盖 Mask
  -> Core Seed / Feather / Smooth Weight
  -> Edge Feather
  -> Transition Norm + Delta Blur
  -> GUIDE_MESH_BLEND
```

`guide_mesh_blend_width` 只定义有限软边，不再通过反除权重把目标高度无限延拓。`guide_mesh_transition_slope` 根据半个外沿宽度限制边缘 Delta，作用是安全 Clamp，不负责扩大 Mask。

`GUIDE_MESH_BLEND` 新增第 4 路 `TRACK_road_target_xz` 输入，并计算 Road Keep：

```text
保护内边界 = road_half_width + shoulder_blend
保护外边界 = max(track_context_width, 保护内边界 + 0.01)

道路核心与路肩：Guide 权重卸载
保护外边界之外：Guide 完整生效
中间区域：平滑过渡
```

目的不是替代最终 Road Exact Conform，而是在它之前卸载 Guide 大高差，避免 Road Pass 从被 Guide 强行抬高/压低的地形中切出深直沟。

混合完成后，`GUIDE_MESH_TEMP_CLEANUP` 删除所有 `@name=guide_*` 临时层，再进入 Lake 约束。Phase 4 的 `GUIDE_MESH_MASK_BLUR` 被标记为 Legacy 并 Bypass，不再参与当前边缘计算。

## 5. Lake 约束重构

### 5.1 闭环输入与空输入安全链

**状态：[已验证]**

Lake 继续只接受闭合 Curve。Phase 5 在 PolyFill 前增加：

```text
LAKE_VALIDATE_CLOSED
  -> LAKE_POLYFILL_INPUT Switch
       0: LAKE_EMPTY_CLOSED
       1: 有效闭合 Lake Curves
  -> LAKE_RESAMPLE
  -> LAKE_POLYFILL
```

当有效 Lake 数量为 0 时，Switch 使用位于 `(100000, 0, 100000)`、半径 10 m 的闭合占位圆。它远离当前 Terrain Domain，既保证 PolyFill/Project 节点获得合法闭环输入，也不会在正常 512 m 地形中产生假湖泊。

`LAKE_POLYFILL` 由 Quad + Smooth/Subdivide 改为 Triangle Fill，并关闭 Smooth/Subdivide，减少不必要的拓扑处理和曲面偏移。

### 5.2 独立 Lake Mask 与归一化水位

**状态：[已验证]**

Phase 4 的 `LAKE_MASK + LAKE_MASK_BLUR` 被移除。Phase 5 使用独立 `LAKE_PROJECT_MASK` 记录 PolyFill 的真实 XZ 覆盖，避免用 Target/Base 高差猜测湖区。该投影同样启用 3 Rays + Jitter + 中值合并。

Lake 临时层：

| 临时层 | 职责 |
|---|---|
| `lake_edge` | 湖岸总软过渡权重 |
| `lake_norm` | 水位延拓归一化分母 |
| `lake_level` | 预乘湖面高度 |
| `lake_core_weight` | 湖内核心/湖岸分离权重 |
| `lake_base_low` | 湖岸原地形低频高度 |

`lake_level` 由投影湖底高度加 `lake_depth` 构建，再与 `lake_norm` 同半径模糊并解预乘，得到岸线附近连续的 Water Level，避免湖面高度在 Mask 边缘衰减到 0。

### 5.3 湖岸宽度与平坦度

**状态：[已验证；复杂湖岸待复验]**

`lake_bank_width` 的语义进一步明确为总软过渡宽度：

- 约 50% 位于湖内：从湖底逐步卸载到水位/岸线参考。
- 约 50% 位于湖外：从岸线参考回归原始地形。

新增参数：

| 参数 | 默认值 | 范围 | 职责 |
|---|---:|---:|---|
| `lake_shore_flatness` | 0.75 | 0～1 | 在原地形与低通岸线/水位参考之间控制湖岸平缓程度 |

最终 Lake Blend 组合以下高度：

```text
base_height       // 当前 Guide 后地形
base_low          // 湖岸低频地形
water_height      // 归一化延拓的水位
bed_height        // 只允许向下的湖底目标
core / edge       // 湖内核心与总岸线权重
```

岸线允许的局部填高被限制为 `Lake Depth * 0.5`，用于避免平坦化过程生成突兀高台；湖底仍通过 `min(projected_bed, base_height)` 保持只向下切割。

混合完成后，`LAKE_TEMP_CLEANUP` 删除所有 `@name=lake_*` 临时层，再交给 Track Context、道路贴合和最终输出链路。

## 6. 参数与 Metadata 变化

### 6.1 新增公开参数

**状态：[已验证]**

本阶段共新增 4 个 Terrain HDA 参数，均位于 `Terrain Constraints / 地形约束`：

| 参数 | 默认值 | 当前验证实例 | 是否进入 Metadata |
|---|---:|---:|---|
| `guide_mesh_detail_scale` | 20 m | 20 m | 否 |
| `guide_mesh_detail_preserve` | 1.0 | 1.0 | 否 |
| `guide_mesh_transition_slope` | 30° | 30° | 否 |
| `lake_shore_flatness` | 0.75 | 0.75 | 是：`terrain_lake_shore_flatness` |

Guide 的三个新参数目前没有写入 Output 1 Metadata。若后续 Bake 需要可追溯地还原生成配置，应补充对应 Detail 属性或统一参数快照，而不是只记录 Strength/Blend Width。

### 6.2 未改变的输出契约

**状态：[已验证]**

三路输出保持：

| Output | 当前内容 | Phase 5 变化 |
|---:|---|---|
| 0 | `OUT_TERRAIN_HEIGHTFIELD`：仅 `height` | 无 |
| 1 | `OUT_TERRAIN_METADATA`：Bounds 点与 Detail Metadata | 新增 `terrain_lake_shore_flatness` |
| 2 | `OUT_TERRAIN_PREVIEW_MESH`：Debug Preview | 历史输出；已于 2026-07-23 从当前 Terrain HDA 移除 |

Phase 4 的 Mask 交付边界没有改变：HDA 内部仍生成 `road/shoulder/cut/fill/slope/no_scatter/cliff/water_candidate/artist_lock`，但稳定 Output 0 仍只输出 `height`。Phase 5 没有完成 Unity Mask Bake。

## 7. Unity 与版本化状态

### 7.1 Unity 资产引用

**状态：[已验证]**

- `Assets/PCG/HDA/Terrain.hda` 已由 Unity AssetDatabase 识别。
- GUID 保持 `15a73d0f61bb98040ae78ced958c3bf9`，没有因二进制更新破坏场景引用。
- 当前打开场景仍为 `Assets/PCG/Scenes/PCG.unity`，Build Index 0。
- `Terrain1` 仍包含 `HEU_HoudiniAssetRoot`、Phase 4 的 HeightField 输出子对象和禁用状态的 `TerrainTrackDisplayBinding`。

### 7.2 本提交没有保存的内容

**状态：[待复验]**

提交 `74bc0b0` 没有修改：

- `HoudiniProject/PCG_Track_21.0.440/PCG_Bike_Terrain.hip`
- `Assets/PCG/Scenes/PCG.unity`
- Houdini Engine Working Cache、TerrainData 或正式 Generated/Bake 资产
- Guide/Lake 自动化验证脚本

因此可以确认的是“HDA 定义已经升级”，不能确认“Phase 5 的新 Guide/Lake 结果已经被提交到 Unity 场景”。当前 Unity 场景在 Editor 中处于 Dirty 状态，但工作树中的场景文件没有修改；该未保存现场不属于提交 `74bc0b0`，本次没有保存或覆盖。

## 8. 性能、兼容性与扩展边界

### 8.1 CPU / GPU 成本

| 阶段 | Phase 5 变化 | 影响 |
|---|---|---|
| Houdini Guide Cook | 新增独立 Mask Project、多层 Copy、Feather、Blur 与归一化 Delta | 编辑器 CPU/内存成本上升，但影响范围和高度传播更可控 |
| Houdini Lake Cook | 新增 Mask Project、核心/边缘权重、Base/Norm/Level Blur | 编辑器 CPU/内存成本上升，换取稳定湖岸与水位 |
| Unity Editor HDA | HDA 文件变大 6,379 bytes；场景未提交 Recook | 需对 513/1025 分辨率重新记录 Cook 时间 |
| Unity Runtime | 无新增代码、Pass、Shader、Texture 或 Buffer | Bake 后 Runtime 渲染成本理论上不变 |

新增的 HeightField Project、Volume Blur 和 Feather 都随 HeightField 分辨率增长。日常仍应使用 513；1025 只用于最终 Bake 候选。不能因为这些节点只在编辑器运行就忽略迭代时间和峰值内存，否则 Guide/Lake 数量增加后会拖慢地编工作流。

### 8.2 移动端与 URP

- 本提交不涉及 RendererFeature 或 RenderPass，`RenderPassEvent` 不适用。
- 不创建 RenderTexture、不执行 Blit、不使用 MRT，不增加 Tile-Based GPU 带宽切换。
- 不修改 Shader；GPU Instancing、keyword、Variant、纹理采样和 overdraw 风险均沿用 Phase 4。
- 运行时仍必须只使用 Bake 后的 Unity 原生 Terrain/Collider/数据，不允许移动端触发 Houdini Cook。
- Guide/Lake 的新增临时 Volume 已在 SOP 内清理，不应进入最终 Unity Terrain 输出。

## 9. 验证记录

### 9.1 Houdini MCP

**状态：[已验证；内部 Warning 未清零]**

- Preflight：Houdini 21.0.440、RPC `18811`、MCP Health `3055` 均正常。
- 当前 HIP：`PCG_Bike_Terrain.hip`。
- 当前 HDA：`Assets/PCG/HDA/Terrain.hda`，类型 `pcgbike::Terrain::1.0`。
- 当前实例 `/obj/Terrain1` 已解锁；本次没有执行 `allowEditingOfContents()`。
- `/obj/Terrain1` 强制 Cook 成功，顶层 Error/Warning 为空。
- Output 0：1 Point / 1 Primitive，XZ 约 `511.002 × 511.002 m`。
- Output 1：8 个 Bounds 点，已出现 `terrain_lake_shore_flatness` Detail 属性。
- Output 2：默认关闭，0 Point / 0 Primitive。
- 当前 `.hip` 有未保存变更；本次只读检查，没有保存 HIP 或 HDA。

完整内部扫描：0 Error、18 Warning，与 Phase 4 相同：

- 1 个 `volumevisualization1` 找不到 `Alpha` Volume。
- 17 个 HeightField 内部 For-Each 节点报告 `Invalid attribute specification: "name"`。

Phase 5 没有修复这些既有 Warning。无 Guide/Lake 有效输入的当前输出可 Cook，不等于真实 Guide Mesh、多个湖泊、嵌套岸线或极端高差已回归通过。

### 9.2 Unity MCP

**状态：[已验证；场景现场未保存]**

- Unity Editor 未播放、未暂停、未编译、未刷新。
- `PCG.unity` 已加载且有效，但当前为 Dirty。
- Terrain HDA 主资产 GUID 正常，`Terrain1` 仍可解析。
- 最近 10 分钟 Console 无日志。
- 本次没有触发 Terrain Recook、保存场景、运行 Player Build 或修改用户现场。

## 10. 已知问题与下一阶段前置事项

1. **P0：提交可复现的 Guide/Lake 验证现场。** 当前只有 HDA 定义；需要将代表性输入、参数和结果写入独立 HIP 或自动化验证脚本，避免算法只能在未保存 Session 中复现。
2. **P0：完成 Unity Recook/Bake 验证。** 确认 HDA 升级后原生 Terrain、TerrainCollider、TerrainData 和 Track 精确贴合均保持稳定，并提交可版本化结果。
3. **P1：补极端输入回归。** 覆盖开放 Lake、多个闭环、重叠/嵌套湖区、非平面 Curve、Guide 侧壁、Guide 缝隙、Guide 与 Road 大高差相交。
4. **P1：记录 Cook 性能。** 分别测量 513/1025、无约束/Guide/Lake/Guide+Lake 的 Cook 时间和峰值内存，确认新增 Blur/Feather 的可接受范围。
5. **P1：修复 18 个 Houdini 内部 Warning。** Phase 5 没有降低 Warning 数量，批量 Bake 前仍需处理或建立明确豁免依据。
6. **P1：补 Guide 参数 Metadata。** `detail_scale/detail_preserve/transition_slope` 目前无法从 Output 1 还原。
7. **P1：完成稳定 Mask Bake。** Phase 5 改善的是内部约束质量，仍没有向 Unity 交付 9 个地形 Mask。
8. **P2：规范 Network Box 名称。** `__netbox1`～`__netbox7` 继续存在；第 8 分区已扩展到 43 个节点，更需要固定模块名称和更细职责分组。
9. **P2：处理 Legacy 节点。** `GUIDE_MESH_MASK_BLUR` 已 Bypass，仅为兼容保留；确认无回退需求后应通过增量 Patch 安全清理。
10. **P2：移动端真机验收。** Terrain 几何、Collider、材质层、Mask 资产和分块方案完成后，再在 Mali、Adreno、Apple GPU 上验证；本阶段无 Runtime 性能验收结论。

## 11. Phase 5 结论

Phase 5 没有扩大 Terrain 系统的外部交付范围，而是针对 Phase 4 的两个约束质量问题进行内部重构：Guide Mesh 从“高度差猜 Mask + 无界模糊”升级为“真实覆盖 + 归一化 Delta + 有限边界 + 细节保留 + Road 保护”；Lake 从“高度差 Mask + 简单模糊”升级为“独立覆盖投影 + 核心/边缘权重 + 归一化水位 + 可控平坦湖岸”。

HDA 结构和公开参数已经完成，输出索引、HDA 类型、Metadata v1.3 和 Unity GUID 保持兼容。但提交只包含二进制 HDA，没有提交 HIP、Unity Recook/Bake 或测试结果，且既有 18 个内部 Warning、Mask Bake、真分块和移动端验收仍未解决。下一阶段应优先把这次算法重构变成可复现、可自动验证、可版本化 Bake 的资产链路，再继续叠加植被、水体渲染或运行时系统。
