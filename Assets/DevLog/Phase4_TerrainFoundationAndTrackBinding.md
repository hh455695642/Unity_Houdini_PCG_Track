# Phase 4 开发日志：Terrain HDA 基础、赛道贴合与 Unity 编辑器绑定

> 文档类型：Phase 4 增量开发日志
>
> 记录日期：2026-07-17
>
> 关联提交：`9305081cb364f3c35ac14a28e479d70e3d34e9ac`（提交说明：`4`）
>
> 基线版本：Phase 3 功能提交 `290457b`，Phase 3 日志提交 `6dc4234`
>
> 记录范围：只记录提交 `9305081` 相对其父提交 `6dc4234` 新增、调整或替换的内容

## 1. 日志范围与证据

本文不是项目全量快照。Track 曲线契约、自适应采样、道路分层输出和既有 URP 道路 Shader 以 Phase 1～3 日志为准。

证据标记：

- **[已验证]**：通过 Git 差异、当前 Houdini MCP 强制 Cook、节点/参数/Geometry 检查、Unity MCP、场景 YAML 或实际组件状态直接确认。
- **[提交已实现]**：代码或 HDA 网络已进入 `9305081`，但仍缺少完整 Bake、极端输入或移动端真机回归。
- **[接口预留]**：节点、参数或 metadata 契约已经建立，实际数据尚未进入稳定 Unity Runtime 资产链路。
- **[待修复]**：提交中已确认存在的状态、数据或维护性问题，不按完成功能计算。

本提交涉及的主要文件：

| 文件 | 主要内容 |
|---|---|
| `Assets/PCG/HDA/Terrain.hda` | 新增 `pcgbike::Terrain::1.0`，建立 HeightField 地形、赛道贴合、Guide/Lake 约束、Mask 与输出契约 |
| `HoudiniProject/PCG_Track_21.0.440/PCG_Bike_Terrain.hip` | 新增 Terrain 独立开发与验证现场 |
| `HoudiniProject/PCG_Track_21.0.440/PCG_Bike_Track.hip` | 更新 Track Houdini 现场 |
| `Assets/PCG/Scripts/Authoring/TerrainTrackDisplayBinding.cs` | 新增 Unity Editor 下 Track Display SOP 到 Terrain HDA 的路径绑定与事件驱动 Recook |
| `Assets/PCG/Scenes/PCG.unity` | 加入 Terrain HDA、Unity Terrain/TerrainCollider、Terrain Guide 根节点及绑定配置 |
| `Assets/PCG/Materials/M_PCG_Road.mat` | 调整道路混合羽化、噪声和低畸变 UV 混合参数 |
| `Packages/manifest.json`、`Packages/packages-lock.json` | Unity MCP 包由 `0.83.1` 升级到 `0.84.2` |
| `Assets/Plugins/NuGet/ReflectorNet.dll` | 随工具链更新替换二进制依赖 |

此外，提交新增了 `Terrain.hda.meta`，但同时存在没有对应 `Terrain.hda.bak` 文件的 `Terrain.hda.bak.meta`，属于孤立 `.meta`，见“已知问题”。

## 2. Phase 4 提交概览

| 模块 | 本阶段增量 | 当前状态 |
|---|---|---|
| Terrain HDA | 新建独立 Terrain HDA，并按输入、Domain、基础地形、赛道贴合、约束、Mask、输出和 Debug 分区 | [已验证] |
| 地形 Domain | 可依据 Track 包围盒自动生成，也可回退到手动 512 m Domain | [已验证] |
| 基础地形 | 支持现有 HeightField/Mesh 输入或程序化 Base，叠加宏观、中观、细节和方向性山脊噪声 | [已验证] |
| 侵蚀 | 已提供 Feature Toggle，默认关闭 | [提交已实现] |
| 赛道贴合 | 从 Track Display Geometry 提取道路目标高度，生成道路核心、路肩、挖方、填方与禁散布区域 | [已验证] |
| Artist Guide | 支持 Unity Mesh Guide 约束地形，提供强度和过渡范围 | [已验证；场景中 Guide 根节点已接入] |
| Lake Curve | 仅闭合曲线参与湖床约束，开放曲线旁路 | [已验证；本次未验证复杂湖泊样例] |
| Mask 契约 | HDA 内部生成 9 个 Mask 名称及 metadata | [接口预留；稳定 Output 0 当前只输出 `height`] |
| Unity Terrain | Houdini HeightField 已在 `PCG.unity` 中生成原生 `Terrain` 与 `TerrainCollider` | [已验证] |
| Track→Terrain 绑定 | 新增编辑器事件驱动绑定脚本，可写入隐藏 SOP Path 并触发 Terrain Cook | [提交已实现；场景组件当前禁用] |
| 道路材质 | 低畸变 UV、混合羽化和噪声参数重新调优，不增加 Shader Variant | [已验证；视觉与真机待复验] |
| 工具链 | Unity MCP 升级至 `0.84.2` | [已验证] |

本阶段没有新增 RendererFeature、RenderPass、RenderTexture、Compute Shader 或运行时 Houdini 依赖。Terrain 生成仍属于 Houdini/Unity 编辑器期流程；移动端运行时应只消费 Bake 后的 Unity 原生地形及后续序列化数据。

## 3. Terrain HDA 架构

### 3.1 HDA 与现场

**状态：[已验证]**

- HDA 类型：`pcgbike::Terrain::1.0`
- HDA 定义：`Assets/PCG/HDA/Terrain.hda`
- 独立开发现场：`HoudiniProject/PCG_Track_21.0.440/PCG_Bike_Terrain.hip`
- 当前实例：`/obj/Terrain1`
- 核心子网：`/obj/Terrain1/TerrainCore`
- `TerrainCore` 直接子节点数：117
- HDA 当前为可编辑状态；本次验证没有执行 `allowEditingOfContents()`，也没有修改或保存 HDA/`.hip`

TerrainCore 采用可读 SOP/HeightField 节点网络实现，而不是运行 Python builder 重建 HDA。网络中已有 8 个职责分区和中文 Sticky Note，核心流程为：

```text
Track / Base Terrain / Guide Mesh / Lake Curve
  -> 输入验证与 Track 中心线整理
  -> Domain 与采样分辨率
  -> Base HeightField 与分层噪声
  -> Guide Mesh / Lake 约束
  -> Track 精确贴合与 Cut/Fill
  -> 地形 Mask 与 metadata
  -> HeightField / Metadata / Debug Preview 输出
```

当前前 7 个 Network Box 仍使用 `__netbox1`～`__netbox7` 的通用名称；只有第 8 个分区有明确中文说明。节点职责可从 Sticky Note 学习，但分区名称仍需标准化，避免后续 Terrain 模块继续扩展时降低可维护性。

### 3.2 四路正式输入

**状态：[已验证]**

| 输入 | 用途 | 规则 |
|---|---|---|
| Track Geometry | 赛道几何、中心线、宽度和高度上下文 | 必需；支持 Mesh/Curve 检测并整理为稳定道路目标 |
| Base Terrain | 复用已有 HeightField 或 Mesh 地形 | 可选；无输入时生成程序化基础地形 |
| Terrain Guide Meshes | 美术/地编通过 Unity Mesh 对局部地形做增量约束 | 可选；计算目标高度差、平滑 Mask 和 Delta 后混合 |
| Lake Curves | 生成湖床和岸坡过渡 | 可选；只接受闭合曲线，开放曲线旁路 |

旧 `artist_overrides` 参数仍以 Legacy 形式保留，没有作为新主接口继续扩展。该处理避免直接破坏已有序列化参数，但后续应明确迁移与废弃时间点。

### 3.3 Domain、采样与基础地形

**状态：[已验证]**

自动 Domain 使用 Track XZ Bounds 加 Padding；Track 无效时回退为手动 Domain。当前主要默认值：

| 参数 | 默认值 | 说明 |
|---|---:|---|
| Auto Domain | On | 根据 Track Bounds 自动确定地形范围 |
| Manual Size | 512 × 512 m | 自动 Domain 无效时的回退范围 |
| Domain Padding | 128 m | 赛道外扩边界 |
| Minimum Domain Size | 512 m | 避免过小地形 |
| Preview/Base Resolution | 513 | 日常 Cook 分辨率 |
| Final Bake Resolution | 1025 | 高质量 Bake 预留；默认未启用 |
| Height Range | 500 m | 用于搜索/投射范围，不是高度硬 Clamp |
| Tile Count | 1 × 1 | 当前仅为实验性采样倍率，不是真正 Unity Terrain 分块 |

采样公式为：

```text
sample_count = tile_count * (tile_resolution - 1) + 1
```

因此当前 `tile_count` 不会生成多块独立 Terrain，也不提供 Chunk Streaming、独立 Bounds 或分块 LOD。它只提高单块 HeightField 的采样数，增大后会直接提高 Houdini Cook、内存和 Unity TerrainData 成本，不能作为移动端大世界分块方案。

基础地形支持以下可独立关闭的层：

- 宏观噪声：默认幅度 80 m、尺度 300 m。
- 中观噪声：默认幅度 22 m、尺度 90 m。
- 细节噪声：默认幅度 4 m、尺度 20 m。
- 方向性山脊：默认方向 35°、强度 0.5。
- 山体高度缩放：默认 8。
- HeightField Erosion：默认关闭，迭代 20；只应在编辑器高质量 Bake 时按需开启。

所有高成本地形层都有 Feature Toggle，符合开发期快速预览与最终 Bake 分离的方向。

## 4. 赛道贴合、Guide 与 Lake 约束

### 4.1 Track 精确贴合

**状态：[已验证]**

Track 输入经过有效性检查、标准化、中心线提取、去重和顺序整理后，在 XZ 平面形成道路目标。主要契约：

- 自动读取 Track 宽度；无有效属性时回退到 8 m。
- Road Core 额外扩展默认 0.5 m，垂直 Clearance 默认 0.05 m。
- Shoulder Blend 默认 4 m。
- Cut/Fill 最大影响距离默认 60 m。
- Cut Slope 默认 24°，Fill Slope 默认 30°。
- 道路精确贴合的优先级高于 Guide Mesh 和 Lake 约束。
- `artist_lock` 用于恢复或保护局部原始地形，避免后续约束无提示覆盖美术锁定区域。

当前内部生成以下 Terrain Contract 层：

```text
height
road
shoulder
cut
fill
slope
no_scatter
cliff
water_candidate
artist_lock
```

其中 `road`、`shoulder`、`cut`、`fill`、`no_scatter` 服务道路与后续散布；`slope`、`cliff`、`water_candidate` 服务植被、水体和地貌判定；`artist_lock` 是后续局部覆盖扩展点。

### 4.2 Guide Mesh 约束

**状态：[已验证]**

Guide Mesh 链路将 Unity/外部 Mesh 投射成目标高度，计算 Delta，再通过 Guide Mask 与平滑范围混合到基础地形。当前参数包括：

- Guide Strength：默认 1.0。
- Guide Blend Distance：HDA 默认 40 m；当前验证实例为 100 m。
- Track Context：默认关闭；开启时可在道路外围以默认 60 m 宽度、0.65 强度、最大 40 m 高差影响地形。

Unity 场景已新增 `TerrainGuideMeshes` 根对象，标记为 `EditorOnly`，并连接到 Terrain HDA 的 Terrain Guide Meshes 输入。该组织允许地编继续添加或替换局部代理 Mesh，而不会把编辑代理带入发布构建。

### 4.3 Lake Curve 约束

**状态：[提交已实现；复杂样例待复验]**

Lake 链路先检查闭合状态，再执行重采样、填充、目标高度投射、岸线 Mask 和平滑混合。当前默认参数：

- Lake Depth：2 m。
- Bank Blend：12 m。
- Lake Strength：1.0。

开放曲线不会误切地形而是直接旁路；道路精确贴合仍拥有更高优先级。当前提交建立了输入和 SOP 网络，但没有提交独立湖泊回归场景或自动化测试，因此不能把多湖、相交岸线、跨 Tile 湖泊记为已完成。

## 5. 输出与 Metadata 契约

### 5.1 三路固定输出

**状态：[已验证]**

| Output Index | 节点 | 当前内容 | 用途 |
|---:|---|---|---|
| 0 | `OUT_TERRAIN_HEIGHTFIELD` | `height` HeightField Volume | Unity Terrain 主输出 |
| 1 | `OUT_TERRAIN_METADATA` | 8 个 Bounds 角点及 Detail/Point Metadata | Bake 工具、边界、输入与契约信息 |
| 2 | `OUT_TERRAIN_PREVIEW_MESH` | Debug Preview Mesh | 历史输出；已于 2026-07-23 从当前 Terrain HDA 移除 |

当前 Output 0 的 Geometry 统计：

- 1 Point / 1 Primitive / 1 Vertex（HeightField Volume 表示）。
- XZ 尺寸约 `511.002 × 511.002 m`。
- Y 范围约 `-112.548 ～ 123.191 m`。

Output 1 当前有 8 个 Bounds 角点和 `terrain_metadata_order`、`terrain_metadata_role` Point 属性。Detail Metadata 包括：

- Terrain Contract Version、Tile Mode、Internal Mask Names。
- 三路输出名称、Unity Tag。
- Domain Bounds、尺寸、采样数、Tile Count。
- Track 输入有效性、来源、宽度与高度统计。
- Guide Mesh、Lake Curve 统计。
- Base Height 与道路上下文参数。

### 5.2 Mask 输出的实际边界

**状态：[接口预留]**

虽然 `OUTPUT_contract_layers` 内部合并了 `height + 9 masks`，metadata 也声明了全部 Mask 名称，但稳定 Output 0 当前连接的是 `OUTPUT_keep_height`，只导出 `height`。这些 Mask 目前只进入内部 Quick Shade/Preview 分支，没有作为 Unity 可稳定消费的独立 HeightField Layer、Texture 或序列化 Mask 资产交付。

因此本阶段完成的是 Mask 生成逻辑与命名契约，不是 Unity 侧 Mask Bake 管线。后续 Vegetation、Water、Decoration 不能假定已经可以在运行时直接读取 `road`、`no_scatter` 或 `water_candidate`；必须先补充明确的 Bake 格式、分辨率、压缩、分块和 GUID 稳定策略。

## 6. Unity 场景集成

### 6.1 Terrain HDA 与原生 Terrain

**状态：[已验证]**

`Assets/PCG/Scenes/PCG.unity` 当前包含：

```text
Terrain1
  ├─ HDA_Data                 (EditorOnly)
  └─ TerrainCore_OUT_TERRAIN_HEIGHTFIELD_OUT_TERRAIN_HEIGHTFIELD_0
       ├─ UnityEngine.Terrain
       └─ UnityEngine.TerrainCollider
```

- Terrain HDA 路径：`Assets/PCG/HDA/Terrain.hda`。
- HDA Asset Operator：`pcgbike::Object/Terrain::1.0`。
- 当前场景内部 Asset Name：`Terrain14`。
- Working Cache：`Assets/HoudiniEngineAssetCache/Working/Terrain`。
- Unity TerrainData GUID：`d4e45b44006984e43bc32e236be6b10a`。
- `Terrain` 与 `TerrainCollider` 均启用。

该结果满足“开发期 Houdini Cook、运行时 Unity 原生资产”的方向，但仍应在正式移动端 Build 前将 Houdini 工作缓存转成稳定 Bake 目录，并确认场景不依赖 Houdini Session 才能恢复 TerrainData。

### 6.2 Track Display SOP 自动绑定

**状态：[提交已实现；场景 Feature Toggle 当前关闭]**

新增 `TerrainTrackDisplayBinding`，职责限定为 Unity Editor 下的 Track/Terrain HDA 协调：

```text
Track Cooked / Reloaded
  -> 查找 Track Display GeoInfo
  -> 解析当前 SOP Node Path
  -> 写入 Terrain 隐藏参数 track_display_sop_path
  -> 可选请求 Terrain 异步 Cook
```

实现细节：

- `[ExecuteAlways]`，但实际逻辑包在 `#if UNITY_EDITOR` 中，不进入 Player 运行时轮询或 Cook。
- 订阅 Track `Cooked/Reloaded` 与 Terrain `Reloaded` 事件。
- 使用 `EditorApplication.update` 进行低频重试，间隔 0.25 s、超时 15 s。
- 提供 `Rebind Track Display SOP Now` Context Menu。
- 路径失效时会清理旧值，避免 Terrain 长期指向失效 Session Node。
- `_autoCookTerrain` 已序列化为开启。

但是 `PCG.unity` 中该 MonoBehaviour 的 `m_Enabled: 0`，所以当前场景不会自动执行上述绑定。场景仍保留上次绑定路径 `/obj/Track13/Road`。这应视为“绑定能力已实现、默认开关未启用”，不能写成 Unity 已持续自动同步。

另外，Track/Terrain 的 Session 内部名称已经增长为 `Track13`、`Terrain14`。绑定脚本通过事件动态解析路径，方向正确；其他工具不得硬编码这些临时数字名称。

### 6.3 绑定脚本诊断文本问题

**状态：[待修复]**

`TerrainTrackDisplayBinding.cs` 中 `_status` 的中文字符串已被保存为大量字面量 `?`，Inspector 状态不可读。核心事件、路径写入和 Cook 调用没有因此失效，英文 Warning 仍可输出，但编辑器诊断体验不合格。后续应以 UTF-8 恢复可读状态文本，并增加一次 EditMode 测试覆盖成功绑定、Session 重载和超时清理。

## 7. 道路材质调优

**状态：[已验证；视觉与移动端真机待复验]**

`M_PCG_Road.mat` 调整如下：

| 参数 | Phase 3 | Phase 4 | 影响 |
|---|---:|---:|---|
| `_BlendFeather` | 0.5 | 0.038 | 大幅收紧材质层混合边界 |
| `_NoiseContrast` | 0.1 | 0.88 | 提高噪声侵蚀对比度 |
| `_NoiseScale` | 12 | 0.71 | 显著增大噪声空间尺度 |
| `_NoiseStrength` | 0.468 | 0.461 | 基本保持原强度 |
| `_UseLowDistortionUV` | 0 | 0.672 | 在方向 UV 与低畸变 Surface UV 间做 67.2% 连续混合 |

`_UseLowDistortionUV` 在 Shader 中通过以下 uniform 路径工作：

```hlsl
float2 layerUV = lerp(directionalUV, input.surfaceUV, saturate(_UseLowDistortionUV));
```

因此 `0.672` 不是布尔开关，而是两套坐标的连续插值。它不增加 keyword 或 Variant，但混合两套参数化坐标可能在部分弯道产生非线性拉伸，需要与 Phase 3 的弧长/横向米制 UV 一起做视觉回归。

本提交没有修改 Shader 源码，所以：

- GPU Instancing 支持方式与 Phase 3 相同。
- Shader keyword 与 Variant 数量不变。
- 纹理采样数量、Pass 数量和 overdraw 风险不变。
- 没有新增 RenderTexture、Blit、MRT 或 Tile GPU 带宽开销。
- 材质参数仍通过 Runtime Uniform 控制，符合 Variant 控制规则。

## 8. 性能与移动端边界

### 8.1 CPU / GPU 成本划分

| 阶段 | CPU 成本 | GPU/带宽成本 | 结论 |
|---|---|---|---|
| Houdini 编辑器 Cook | HeightField 噪声、约束、Mask、可选侵蚀；分辨率增长时成本显著增加 | 非移动端运行时成本 | 用 513 日常预览，1025 只用于最终 Bake；侵蚀默认关闭 |
| Unity 编辑器 HDA 同步 | Track 事件、SOP Path 解析、Terrain 异步 Recook | 无新增渲染 Pass | 事件驱动，避免每帧重 Cook；当前组件禁用 |
| Unity Runtime Terrain | 不应包含 Houdini Cook；主要为 Terrain LOD、物理与可见性管理 | 原生 Terrain 绘制、地形纹理和几何带宽 | 必须 Bake；需真机验证 TerrainData、材质层和 Collider 成本 |
| Mask 后续消费 | 当前尚未进入 Runtime | 未定义 Texture/Buffer 格式 | 在确定分块和压缩前，不应直接输出大量全分辨率 Mask RT |

### 8.2 移动端风险

- 当前是单块约 512 m Terrain，不是真正 Chunk/Tile；扩大 Domain 或采样倍率会放大单资源内存和 Cook 峰值。
- `TerrainCollider` 已启用，应在真机验证物理内存与碰撞精度；远距离或不可达块应支持关闭 Collider。
- 1025 高度图对当前范围可作为最终 Bake 候选，但应以道路贴合误差、设备内存和摄像机视距共同确定，不能仅按视觉最大分辨率选择。
- 9 个 Mask 若全部以全分辨率无压缩纹理输出，会产生明显包体和带宽成本。后续应按用途分级：道路/禁散布保留高精度，Slope/Cliff/Water 可降低分辨率或离线量化。
- 本阶段没有新增透明 Pass、全屏 Pass、MRT 或 Shader Variant，URP/Tile-Based GPU 渲染架构风险没有被扩大。

## 9. 工具链更新

**状态：[已验证]**

- `com.ivanmurzak.unity.mcp`：`0.83.1 -> 0.84.2`。
- `ReflectorNet.dll` 随工具链被替换，文件大小未明显变化。
- 当前外部 `unity-mcp-cli` 工具报告为 `0.84.3`，项目锁定包仍以 `manifest.json/packages-lock.json` 中的 `0.84.2` 为事实源。

该更新属于编辑器协作工具，不应进入移动端 Runtime 依赖。后续升级应继续检查 Editor-only Assembly、Build stripping 和包锁定差异。

## 10. 验证记录

### 10.1 Houdini MCP

**最终状态：[已验证，但内部 Warning 未清零]**

- Houdini GUI：21.0.440。
- 当前 `.hip`：`PCG_Bike_Terrain.hip`。
- RPC `18811` 与 MCP Health `3055`：最终均正常。
- `/obj/Terrain1` 强制 Cook 成功，顶层 Error/Warning 均为空。
- 三路输出均 Cook 成功；Preview 因默认关闭而为空。
- 当前 `.hip` 报告有未保存变更；本次仅做只读验证，没有保存或覆盖 HDA。

内部完整扫描结果为 0 Error、18 Warning：

- `HF_DOMAIN/volumevisualization1`：找不到 `Alpha` Volume。
- 17 个 HeightField 内部 For-Each 节点出现 `Invalid attribute specification "name"`，涉及宏观/中观/细节/山脊噪声以及 road、shoulder、cut、fill、no_scatter、slope、cliff、water_candidate 分支。

这些 Warning 没有阻止当前输出，但说明网络还未达到“全量节点无警告”的稳定标准。后续应先确认是 Houdini 21.0 HeightField HDA 内部兼容问题还是节点参数写法问题，再进入批量 Bake。

验证开始时一次并发节点扫描导致 Houdini Session 退出；已重启 Houdini、重新加载 Terrain HIP，并通过串行查询完成最终验证。上述统计均来自恢复后的有效 Session。

### 10.2 Unity MCP

**状态：[已验证；Console 含历史工具日志]**

- Unity Editor：未进入 Play Mode、未暂停、未编译、未更新。
- 打开场景：`Assets/PCG/Scenes/PCG.unity`，Loaded/Valid，场景未标记 Dirty。
- Terrain HDA、原生 Terrain、TerrainCollider、Track HDA 和 Terrain Guide 根对象均可找到。
- `TerrainTrackDisplayBinding` 编译并挂载成功，但组件禁用。
- Unity Console 中保留了历史工具错误，包括 MCP 日志文件锁定、一次动态 Script Execute 类型解析失败和 Domain Reload Assert；它们不是本提交脚本的当前编译错误，但 Console 不是干净基线。

本提交没有新增 Terrain 自动化测试，也没有执行 Android/iOS 真机 Profiling、RenderDoc 或最终 Player Build，因此移动端结论仍是架构评估，不是性能验收。

## 11. 已知问题与 Phase 5 前置事项

按优先级整理：

1. **P0：补齐稳定 Mask Bake。** 目前 Output 0 只含 `height`；需要定义 Mask 的 Unity 资产格式、分辨率、量化、压缩、分块和版本契约。
2. **P0：建立真正 Terrain Tile/Chunk。** 当前 `tile_count` 只是采样倍率，不能承担移动端分块加载、独立 Bounds、LOD 或 Collider 管理。
3. **P1：修复 18 个 Houdini 内部 Warning。** 在批量 Bake 前达到 0 Error，并对可消除 Warning 建立验证脚本。
4. **P1：决定并验证绑定组件默认状态。** 若自动同步是主工作流，应启用 `TerrainTrackDisplayBinding` 并回归 Session 重载；若刻意禁用，应在 Inspector/文档明确手动绑定流程。
5. **P1：修复绑定脚本乱码状态文本。** 同时添加 EditMode 测试覆盖路径更新、自动 Cook、超时清理和禁用状态。
6. **P1：建立 Terrain 回归测试。** 至少覆盖无 Track、开放/闭合 Track、极端高差、Guide 重叠、开放/闭合 Lake、1025 Bake 和输出契约。
7. **P1：稳定 Bake 目录。** 将工作缓存转为 `Assets/PCG/Generated/...` 下可版本化资产，并验证脱离 Houdini Session 后场景仍完整。
8. **P2：清理孤立 `Assets/PCG/HDA/Terrain.hda.bak.meta`。** 删除前需确认没有待恢复的 `.bak` 资产，且通过 Unity AssetDatabase 操作保持 GUID 安全。
9. **P2：规范 Network Box 与 Session 名称依赖。** Terrain 分区改为固定语义名；所有 Unity 工具继续按对象引用/动态路径解析，不硬编码 `Track13`、`Terrain14`。
10. **P2：道路材质视觉回归。** 重点检查 `_UseLowDistortionUV = 0.672` 的连续 UV 插值、窄羽化边界和低频噪声在弯道/坡道上的拉伸与闪烁。
11. **P2：移动端真机验收。** 在 Mali、Adreno、Apple GPU 上记录 Terrain DrawCall、SetPass、内存、Collider、道路 overdraw 和带宽，不以 Editor 结果代替。

## 12. Phase 4 结论

Phase 4 的核心成果是从“只有赛道生成”推进到“赛道可约束的地形基础设施”：新增独立 Terrain HDA，完成可开关的基础地貌、赛道贴合、Guide/Lake 约束、地形 metadata 和 Unity 原生 Terrain/TerrainCollider 落地，并建立 Track Display SOP 到 Terrain 的编辑器事件绑定能力。

当前阶段仍是 Terrain Foundation，而不是完整移动端 Terrain Pipeline。最关键的未完成项是：Mask 尚未稳定输出到 Unity、`tile_count` 尚不是真分块、绑定组件当前关闭、Houdini 内部仍有 18 个 Warning、缺少自动化与移动端真机验收。后续应优先完成可版本化 Bake + Mask/Tile 契约，再叠加植被、水体和 Runtime GPU 驱动模块，避免在单块高分辨率 Terrain 上继续堆叠不可控成本。
