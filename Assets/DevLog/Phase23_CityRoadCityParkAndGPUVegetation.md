# Phase 23 开发日志：CityRoad 城市公园与 GPU 植被链路

> 文档类型：Git 提交增量审计与当前现场复验  
> 记录日期：2026-08-24  
> 版本文件：`Phase23_CityRoadCityParkAndGPUVegetation.md`  
> 目标提交：`c49ed869496eaabd44042f4fb9d5430a79c43ff2`（提交信息：`23`）  
> 父提交：`06b102d3596b190ebfc561568c1a16fb4271f5d3`（`Terrain.hip` metadata / validation 冗余链路移除）  
> CityRoad HDA：`Assets/PCG/HDA/City/CityRoad.hda`  
> CityRoad HIP：`HoudiniProject/PCG_Track_21.0.440/PCG_Bike_CityRoad.hip`  
> Unity 场景：`Assets/PCG/Scenes/PCG_City.unity`

## 1. 日志范围与证据

本文只记录 Git 提交 `c49ed86` 相对直接父提交 `06b102d` 的开发增量。Phase1～Phase22 已记录的 Track、Terrain、CityRoad 道路拓扑、Sidewalk、Marking、Street Furniture、Cook 优化与 Subnet 重构不再重复。

提交 `23` 的最终有效开发链为：

```text
Unity 闭合 SplineContainer（unity_park_areas）
    -> CityRoad 参数输入与 Safe Rebuild 恢复
    -> CR_CITY_PARK
       -> CR_PARK_INPUT：HAPI Curve 转换与拓扑重建
       -> CR_PARK_MASTERPLAN：边界、功能分区、园路、林地、排除区
       -> CR_PARK_OUTPUTS：六类稳定输出与法线/metadata
    -> Unity Live Preview：显示 Surface/Tree，隐藏 Collision/Exclusion
    -> Cook + Validate + Update Bake
    -> CityRoadParkAssets 编译实例、Chunk、LOD、Exclusion 与 Fallback
    -> CityParkVegetationRendererFeature
    -> Compute Chunk/Instance Culling
    -> DrawMeshInstancedIndirect
```

证据等级：

- **[提交验证]**：目标提交元数据、46 个变更文件、Git diff、HDA/HIP、Unity YAML Scene、C#、Shader、Compute、RendererData、合同、V45 manifest/patch 与回归门禁。
- **[Fresh HDA 独立验证]**：Houdini `21.0.440` 从磁盘 HDA 创建全新锁定实例，执行 34 项累计合同；没有保存资产。
- **[Houdini Live 现场]**：Houdini MCP 使用 Read-Only Policy 检查生产 HIP、City Park Subnet、Definition 状态和全网诊断；Scene Diff 为 0。
- **[Unity 现场]**：Unity MCP 检查 Editor、打开场景、AssetDatabase、Shader 编译状态、RendererFeature 和 Console；未保存 Dirty Scene。
- **[源码验证]**：审查 Safe Rebuild、Live Preview、Bake Compiler、GPU Buffer、Compute Culling、Indirect Draw、Fallback 和 Shader Variant 边界。
- **[未闭环]**：提交没有正式 CityRoad Bake 产物、序列化的 `CityParkVegetationAnchor`、运行时 Indirect Draw 截帧、移动端真机、GPU Profiler 或 RenderDoc 结果。

当前工作区中的 City Park V25～V44 manifest/patch、StreetBuilding、Terrain 美术和脚本等未跟踪文件不属于提交 `23`，不得写成 Phase23 正式交付。

## 2. 提交概览

| 项目 | 数值 |
|---|---:|
| Commit | `c49ed869496eaabd44042f4fb9d5430a79c43ff2` |
| Author / Date | `liyuan` / 2026-08-24 10:54:30 +08:00 |
| Changed Files | 46 |
| Added / Deleted Lines | `+107150 / -132431` |
| CityRoad HDA | 315,924 → 335,539 bytes（+6.209%） |
| CityRoad HIP | 2,280,409 → 2,392,265 bytes（+4.905%） |
| PCG_City Scene | 10,728,395 → 10,717,464 bytes（-0.102%） |
| PCG_City Scene Lines | 266,235 → 236,262（-29,973） |
| CityRoad Core 顶层节点 | 45 → 50 |
| Author Subnet | 27 → 29 |
| Required Nodes | 64 → 104 |
| 累计 Contract ID | 28 → 34 |
| Public Interface SHA-256 | `476b2c...a65f` → `408bd6...5c8` |
| Houdini Engine Unity 插件 | 0 个文件修改 |

主要文件按职责分为：

1. `CityRoad.hda`、生产 HIP、累计合同与验证器：正式加入 City Park 公共参数、HAPI 输入兼容、V41 Masterplan、六类输出和 V45 可读性结构。
2. `CityRoadSafeRebuild.cs`：按参数名恢复 Road/Park 两个 Spline 输入，保留 City Park 参数，并刷新依赖 Park 的节点阶段。
3. `CityRoadLivePreviewController.cs`、`CityRoadBakeWorkflow.cs`：City Park Live Preview、碰撞/排除输出隐藏、阴影合同、Bake 前后验证。
4. `CityRoadParkAssets.cs`：把 Houdini 树实例和排除边界编译为 Runtime ScriptableObject、Chunk、LOD、Indirect Material 与兼容 Fallback。
5. `CityPark` Runtime、Compute Shader、Indirect Shader：RendererFeature + 独立 RenderPass + GPU 剔除 + Indirect Draw。
6. 三套 URP RendererData：Balanced、HighFidelity、Performant 均注入并启用 City Park Feature。
7. `.agents/scripts/Invoke-PcgRegression.ps1` 与 `pcg_regression_gate.py`：统一 Capture / VerifyFast / VerifyFull 门禁，并支持权威 Dirty Live Scene 的安全备份。
8. `PCG_City.unity`：保存 Park 参数输入和 `OUT_PARK_*` Live Preview 层级；仍不是正式 Bake。

文件指纹：

| 文件 | Phase23 SHA-256 |
|---|---|
| CityRoad HDA | `42731E359AE14D2D91848DFAD5E26203DB84E939C82DD461BDD538BE0D886455` |
| CityRoad HIP | `6D3E1D9F38F39661EDE0EB9227835887BCF0B32AEB1226AC00B122D035D308D6` |
| PCG_City Scene | `DAB3FD5033E4B215BB5C57EC78C8D5588816777E3092DA7897160535468CC13F` |

## 3. City Park 公共接口与输入合同

### 3.1 公共参数

Phase23 正式恢复并提交 City Park 参数页：

| 类别 | 参数 |
|---|---|
| 总开关 / 输入 | `enable_city_park`、`unity_park_areas` |
| 确定性 | `park_seed` |
| 边界 | `park_boundary_inset` |
| 水体 | `enable_park_water`、`park_lake_count`、`park_lake_area_ratio` |
| 园路 | `enable_park_paths`、`park_path_width`、`park_path_branch_count`、`park_path_jitter` |
| 树木 | `enable_park_trees`、`park_tree_density_per_hectare`、`park_tree_min_spacing`、`park_tree_clearance` |
| Unity 材质 | `park_ground_unity_material`、`park_path_unity_material`、`park_water_unity_material` |

`unity_park_areas` 是 Houdini Engine 参数输入，不占用 HDA Connector，因此 Fresh 合同中的 `max_inputs` 仍为 0。Unity Scene 已序列化该参数输入和中文标签。

### 3.2 Safe Rebuild 兼容

`CityRoadSafeRebuild` 不再假设只有 Road 输入：

- 以 `unity_road_network` / `unity_park_areas` 参数名捕获和恢复绑定，不依赖易漂移的序号。
- 新创建但为空的 Park 输入若仍是 `UNITY_MESH`，在 Reload 后规范化为 `PARAMETER/SPLINE`。
- 空 Park 输入属于合法状态，不强制建立 Houdini Merge 连接，也不会把空输入误判为 Cook 失败。
- Reload 前捕获四个 Bool、三个 Int、七个 Float 和三个 Material Path；Reload 后逐项恢复。
- Unity 上传参数输入发生在初次 HDA Cook 之后，因此显式刷新 Input Switch、HAPI Curve Convert、Topology Rebuild 和 `PARK_CONTRACT_V41`。
- Road/Park 任一绑定 Spline 发生变化时都会标记对应 Parameter Input Dirty。

这部分解决了 HDA Definition 更新后 Park 输入类型、绑定和参数值丢失，以及 HEU 首次 Cook 早于输入上传的问题。

## 4. Houdini City Park 生成网络

### 4.1 可维护 Subnet 结构

最终 `CR_CITY_PARK` 只保留九个直接成员：六个 Subnet Output 和三个职责 Subnet。

```text
CR_CITY_PARK
├─ CR_PARK_INPUT
│  ├─ EMPTY_PARK_AREAS
│  ├─ IN_UNITY_PARK_AREAS
│  ├─ PARK_ENABLE_INPUT_SWITCH
│  ├─ PARK_CONVERT_HAPI_CURVE_V32
│  └─ PARK_REBUILD_HAPI_TOPOLOGY_V29
├─ CR_PARK_MASTERPLAN
│  ├─ PARK_BOUNDARY_ANALYZE_V41
│  ├─ PARK_SURFACE_ZONES_V41
│  ├─ PARK_CONNECTED_PATHS_V41
│  ├─ PARK_WOODLAND_LAYERS_V41
│  ├─ PARK_EXCLUSION_V41
│  ├─ PARK_ASSEMBLE_V41
│  └─ PARK_CONTRACT_V41
└─ CR_PARK_OUTPUTS
   ├─ Ground / Paths / Water Keep + Contract + Normal
   ├─ Collision / Trees / Exclusion Keep + Contract
   └─ 6 个 Subnet Output
```

V45 只重排 `CR_CITY_PARK` 内部节点、连接、位置、颜色和注释，不增加公共参数或改变六个输出语义。其 manifest 使用 `authoritative_live_scene = true`，允许 Capture 先用 `saveAsBackup()` 保护已确认的 Dirty Live Scene，再执行白名单修改。

### 4.2 Masterplan 与稳定输出

V41 将公园拆为可审计的功能层：

- Ground Zone：`active_lawn`、`entrance_lawn`、`quiet_lawn`、`woodland_edge`。
- Path Class：`entrance`、`loop`、`plaza`、`primary`，同一 Park 内保持连通。
- Vegetation Layer：至少包含 `woodland_core`、`woodland_edge`。
- Exclusion：生成供后续建筑/地块系统消费的 Site Boundary，而不是可见渲染面。
- `park_id`、分区/路径/植被类别和确定性签名进入输出 metadata，供 Unity Bake 编译与后续系统解耦消费。

V43/V44 处理 Unity 场景中公园被人行道遮挡的问题。Fresh Fixture 的最终高度为：

| 输出 | Y（m） |
|---|---:|
| Ground | 0.65 |
| Paths | 0.67 |
| Water | 0.61 |
| Collision | 0.65 |
| Trees | 0.65 |
| Exclusion | 0.65 |

`surface_lift = 0.65 m`，园路高于 Ground，Water 略低于 Ground；V44 合同继续验证可见面高于 Sidewalk 遮挡层。

### 4.3 六类输出

| Output | Unity 职责 |
|---|---|
| `OUT_PARK_GROUND` | 草地/功能分区可见面 |
| `OUT_PARK_PATHS` | 连通园路和入口/广场可见面 |
| `OUT_PARK_WATER` | 湖面可见面 |
| `OUT_PARK_COLLISION` | 隐藏 MeshCollider 数据源 |
| `OUT_PARK_TREES` | 树木 Prefab 实例源，Bake 后编译为实例 Buffer |
| `OUT_PARK_EXCLUSION` | 隐藏 Site Exclusion 数据源 |

关闭总开关或没有 Boundary 时，六个输出全部为空。Open、明显非水平、过小和自交 Boundary 也必须失败关闭全部 Park 输出，避免带病数据进入 Bake。

## 5. Unity Live Preview 与 Bake 合同

### 5.1 Live Preview

`CityRoadLivePreviewController` 已识别四类可见 Park 输出：Ground、Paths、Water、Trees，并把 Collision/Exclusion 归为隐藏技术输出。

- 可见 Park Renderer 保持 `receiveShadows = true`，但 `shadowCastingMode = Off`。
- Collision 自动关闭 Renderer，并补齐非 Trigger、非 Convex 的 `MeshCollider`。
- Exclusion Renderer 始终隐藏。
- Park 直接输出不再依赖 `CityPark_` Presentation Piece 命名才能显示。
- HDA Cook 遗留的孤立预览根会在编辑/Play Mode 切换流程中清理。

### 5.2 Bake 前验证与编译

`CityRoadBakeWorkflow` 新增 fail-closed 顺序：

```text
验证 Park Material / Shader / Compute
    -> Safe Rebuild + Cook
    -> 应用 Collision / Shadow Contract
    -> 验证 Live Park 输出
    -> Houdini Engine Bake Prefab
    -> CityRoadParkAssets.CompilePrefab
    -> 验证最终 Prefab 不含 Raw Tree/Exclusion Root
    -> 验证 Anchor / Data / Profile / Exclusion 完整
```

启用 Park 且已绑定有效 Boundary 时，`OUT_PARK_GROUND` 必须产生三角形；否则保留旧 Bake，不替换为损坏结果。

### 5.3 Bake Compiler

`CityRoadParkAssets` 把编辑期 HEU 层级编译为运行时数据：

- 从 `OUT_PARK_TREES` 提取实例矩阵、Variant、LOD0/LOD1 Mesh 和 Material。
- 以 64 m Chunk 建立包围盒，写入 `CityParkVegetationData`。
- 最多编译 3 个树种 Variant、每 LOD 最多 2 个 Submesh。
- 创建 Indirect 专用材质，并写入 `CityParkVegetationProfile`。
- 从 `OUT_PARK_EXCLUSION` Mesh 拓扑恢复 Boundary，规范绕序和起点；无 Houdini `park_id` 时对 1 cm 量化点集做稳定哈希。
- 创建 `PCGSiteExclusionData`，供建筑或其他 Site Consumer 使用。
- 以 64 m Chunk + Variant + Submesh 合并低成本 Fallback Mesh。
- 编译完成后删除 Raw Tree/Exclusion Root，给 Prefab 添加 `CityParkVegetationAnchor`。

提交没有生成上述 ScriptableObject、Fallback Mesh 或最终 Prefab；这里只能确认编译器实现和 Unity 编译状态，不能声称正式 Bake 已完成。

## 6. GPU 植被运行时

### 6.1 RendererFeature / RenderPass

`CityParkVegetationRendererFeature` 是独立、可关闭的 URP RendererFeature：

| 项目 | Phase23 实现 |
|---|---|
| RenderPassEvent | `AfterRenderingOpaques` |
| Feature Toggle | RendererData `settings.Enabled` + Profile `featureEnabled` |
| RenderTexture / Blit / MRT | 无 |
| CommandBuffer | 通过 `CommandBufferPool` 复用 |
| Profiler Marker | `City Park Vegetation Indirect` |
| Preview Camera | 跳过 |
| 扩展点 | 后续模式以独立 Pass 加入，不扩成全能 Feature |

Balanced、HighFidelity、Performant 三套 RendererData 都已嵌入并启用该 Feature。Balanced/HighFidelity 保留既有 SSAO，Performant 只有 City Park Feature。

### 6.2 GPU Culling 与 Indirect Draw

运行时数据流：

```text
Instance Buffer（Matrix + Variant + Chunk）
    -> CullCityParkChunks：64 线程，距离 + Frustum 粗剔除
    -> Chunk Visibility Buffer
    -> 每 Variant 执行 CullCityParkInstances：64 线程
    -> Append LOD0 / LOD1 Matrix Buffer
    -> CopyCounterValue 写入 Indirect Args
    -> DrawMeshInstancedIndirect
```

默认参数：LOD0 距离 55 m、最大距离 180 m、实例包围半径 3.5 m。最大理论 Draw 数为：

```text
3 Variants × 2 LOD × 2 Submeshes = 12 Draw / Anchor / Camera
```

CPU 只在 Bake/初始化阶段整理实例与 Chunk；每帧 CPU 仍需收集少量 Anchor、计算六个 Frustum Plane，并遍历 Anchor 提交 CommandBuffer。大规模实例的逐个剔除、LOD 和 Draw Count 均在 GPU 完成，没有每帧 CPU 实例 for-loop。

当前剔除只有 Frustum + Distance + Chunk，没有 Hi-Z/Occlusion。公园被建筑大面积遮挡时仍可能提交被遮挡实例，后续应把 Hi-Z 作为独立可选阶段，而不是侵入当前 Pass。

### 6.3 兼容 Fallback

以下条件任一不满足时，Anchor 自动启用 64 m 合并 Fallback：

- Compute Shader 支持。
- GPU Instancing 支持。
- Indirect Arguments Buffer 支持。
- Graphics API 不是 OpenGLES2。

Fallback 使用 Bake 时合并的 LOD1 优先 Mesh 和原始材质，不依赖 Indirect Shader。该路径已实现，但提交没有实际 Bake Prefab，因此 Mali、Adreno、Apple GPU 和低端 Fallback 仍需真机复验。

## 7. Shader、Pass 与 Variant 风险

Shader：`PCG/CityPark/VegetationIndirect`

| Pass | LightMode | 职责 | ShadowCaster |
|---|---|---|---|
| Forward | `UniversalForward` | Base Map、Tint、主光、SH、Fog | 无 |
| DepthOnly | `DepthOnly` | 深度写入 | 无 |

Unity AssetDatabase 当前确认 Shader 为 Opaque、Render Queue 2000、2 Pass、3 Properties、当前平台支持且无编译错误。

Keyword / Variant：

```hlsl
#pragma multi_compile_instancing
#pragma multi_compile _ _MAIN_LIGHT_SHADOWS _MAIN_LIGHT_SHADOWS_CASCADE _MAIN_LIGHT_SHADOWS_SCREEN
#pragma multi_compile_fragment _ _SHADOWS_SOFT
#pragma multi_compile_fog
```

- 没有项目自定义功能 Keyword；强度与材质参数走 Uniform。
- Forward 理论原始组合约 `2 × 4 × 2 × 4 = 64`，DepthOnly 约 2，总计约 66 个 Variant，尚未计平台和 URP 额外环境，也未扣除 URP Stripping。
- 当前数量低于项目建议的 200，但 Shadow/Fog 使用全局 `multi_compile`，仍应以 Android/iOS Player 构建后的实际 Variant Report 为准。
- Shader 使用 `#pragma target 4.5` 与 StructuredBuffer；不支持的设备走 Fallback，不应继续向该 Shader 叠加 Wind、Cutout、Additional Light 等组合。
- 没有 ShadowCaster 可降低移动端树木阴影图 Draw/Overdraw，但公园植被不会投射动态阴影；这是当前明确的性能取舍。
- 无透明 Alpha/Cutout，当前只适合低模不透明树冠；若未来需要叶片裁剪，应拆成独立高成本 Shader。

## 8. Unity Scene 提交增量

提交前后 YAML 对象计数：

| Unity Class | Parent | Phase23 | Delta |
|---|---:|---:|---:|
| GameObject (`!u!1`) | 2,909 | 2,291 | -618 |
| Transform (`!u!4`) | 2,909 | 2,291 | -618 |
| PrefabInstance (`!u!1001`) | 2,694 | 2,060 | -634 |
| MonoBehaviour (`!u!114`) | 167 | 186 | +19 |
| Mesh | 71 | 76 | +5 |
| MeshFilter / MeshRenderer | 135 / 135 | 140 / 140 | +5 / +5 |
| MeshCollider | 1 | 1 | 0 |

Phase23 Scene 包含：

- `enable_city_park` 和 `unity_park_areas` 参数序列化。
- 六类 `OUT_PARK_*` Live Preview 输出标识。
- 596 个 Street Lamp Prefab、1,049 个 Tree Pit Prefab、414 个 Round Tree Prefab，以及 1 个无法在提交的项目 `.meta` 中反查来源的 Prefab GUID。
- 仍没有 `CityParkVegetationAnchor` 序列化记录。

与 Phase22 的 2,694 个 PrefabInstance 相比，Round Tree 从 1,049 降至 414，Tree Pit 仍为 1,049。Scene 内的 Live Preview 实例数量不应被当作正式树木 Bake 统计；缺少 Anchor 和 Generated Asset 说明 GPU Runtime 数据尚未编译。

当前 Unity 内存现场可看到 `OUT_PARK_TREES`、Park ID、Woodland/Quiet Grove/Scattered Lawn 和 Variant 实例层级，但场景为 Dirty。本文不保存该现场，也不以它覆盖提交 YAML。

## 9. 统一回归门禁

新增统一入口：

```powershell
powershell -NoProfile -ExecutionPolicy Bypass `
  -File .agents\scripts\Invoke-PcgRegression.ps1 `
  -Module CityRoad|Track|Terrain|StreetBuilding `
  -Stage Capture|VerifyFast|VerifyFull `
  -ChangeManifest <json>
```

核心能力：

- Capture 同时记录 Houdini Live/Disk、HDA/HIP、Unity Editor、打开场景、HDA GUID 引用和 Console 诊断基线。
- Manifest 必须声明 Module、文件/节点/连接/参数白名单、输出变更和累计合同。
- `authoritative_live_scene` 强制为 Boolean；设为 `true` 时先序列化 Dirty Live Scene 备份，不改变当前 HIP Path。
- 每份 Backup 单独记录 SHA-256；Restore 优先验证 Backup Hash，避免用已变化的磁盘 Hash 错判权威 Live 备份。
- VerifyFull 完成 Live 验证、受控持久化、Fresh HDA/HIP 回归、Unity Refresh、资产 GUID/Scene 引用和新增 Console 诊断比较。
- Persist 后失败会恢复 Capture 的 HDA/HIP 备份。

`test_pcg_regression_gate.py` 当前 8 项单元测试全部通过，包括 `authoritative_live_scene` 非 Boolean 时 fail-closed。

## 10. Fresh HDA 累计验证

命令：

```powershell
& "D:\Software\Side Effects Software\Houdini 21.0.440\bin\hython.exe" `
  "HoudiniProject\PCG_Track_21.0.440\scripts\tools\validate_cityroad_contract.py" `
  --source fresh
```

结果：`PASS`。累计合同从 28 增至 34：

- `CityRoad.V20.CityPark`
- `CityRoad.V38.CoreReadability`
- `CityRoad.V41.ParkMasterplan`
- `CityRoad.V43.ParkSurfaceLift`
- `CityRoad.V44.ParkVisibleAboveSidewalk`
- `CityRoad.V45.ParkReadability`

Fresh 生产配置没有绑定 Park Boundary，因此六个 `OUT_PARK_*` 都为 0；Validator 会另外创建独立 Park Fixture 验证真实生成结果：

| City Park Fixture | 结果 |
|---|---:|
| Ground Primitives | 1,114 |
| Path Primitives | 350 |
| Water Primitives | 385 |
| Tree Points | 9 |
| 800 点 HEU Boundary 保留样本 | 400 |
| Path Components / Park | 1 |
| Open / Height / Small / Self-intersection 非法输入 | 六输出全部 0 |
| 相同 Seed 确定性签名 | 稳定 |
| 修改 Seed 签名 | 发生变化 |

其他累计结果继续通过：

- Public Interface SHA-256：`408bd642613842797ff4cb417242ebc838edcacd371b396ecc8126fe33a8c5c8`。
- Required Node Count：104。
- V19 布局：50 个顶层节点、29 个 Author Subnet、217 个移动叶节点、依赖 DAG 为 `true`。
- Road/Sidewalk/Collision/Marking、V22 Zero Corner、V24 Post-Commit Marking、Street Furniture 与 V18 等价合同均通过。
- Fresh 实例在等价比较前保持 Locked，验证没有保存 HDA/HIP。

## 11. Houdini / Unity 当前现场

### 11.1 Houdini Live

Houdini MCP Read-Only 结果：

| 项目 | 结果 |
|---|---|
| HIP | 生产 `PCG_Bike_CityRoad.hip` |
| HIP Unsaved | `false` |
| Node | `/obj/CityRoad_DEV` |
| Locked | `false` |
| Matches Current Definition | `false` |
| CityRoad Core Top-level | 50 |
| `CR_CITY_PARK` Direct Children | 9 |
| Descendant Nodes | 1,136 |
| Error / Warning | 0 / 0 |
| Read-Only Scene Changes | 0 |

Live HIP 已保存但实例 Unlocked 且不匹配当前 Definition。后续 HDA 修改前仍必须 Capture 并检查 Live/Disk 差异，不能直接 Reload 或用 Git HEAD 覆盖。

### 11.2 Unity Editor

- Unity `2022.3.62f2` 当前未 Play、Pause、Compile 或 Asset Update。
- 打开场景为 `PCG_City`，Dirty、8 个 Root、Build Index `-1`。
- City Park Indirect Shader 当前平台支持且无编译错误。
- 本日志执行 `AssetDatabase.Refresh()` 后没有新增 Error，但 Houdini Engine 自动重建 CityRoad 时新增一次 `CR_SIDEWALK_OUTPUT No geometry generated` Cook Warning。Console 还保留提交当日上午同签名 Cook Warning和 Unity MCP Skill 文件写入共享冲突，因此不能表述为 Console 全绿。

## 12. 审计边界与已知限制

1. **没有正式 Bake**：提交和当前工作区都没有 `Assets/PCG/Generated/Road`，Scene 中也没有 Anchor；Indirect 运行时链没有可消费的数据资产。
2. **迁移审计链不完整**：最终 HDA/合同包含 V20、V38、V41、V43、V44、V45，但 V25～V44 多数 manifest/patch 仍是未跟踪文件。Phase23 可确认最终行为，不能确认这些中间迁移脚本已正式归档。
3. **Unity Live/Disk 与 Houdini Definition 均非干净交付现场**：Unity Scene Dirty；Houdini Live 虽已保存但 Unlocked 且不匹配 Definition。
4. **Scene 实例仍不适合发布**：2,060 个 PrefabInstance 是编辑期 Live Preview 序列化，不是 Chunk/Indirect Bake。
5. **Tree / Tree Pit 数量不一致**：414 Round Tree 对 1,049 Tree Pit，需要在正式 Bake 前确认旧预览残留和 Street/Park 实例归属。
6. **Prefab GUID 未完全可追踪**：Scene 中有 1 个 Source Prefab GUID 无法在提交的项目 `.meta` 中反查。
7. **GPU 剔除缺少 Occlusion**：目前只有 Chunk/Frustum/Distance/LOD；密集城市遮挡下仍可能浪费 GPU。
8. **Variant 仅做源码估算**：约 66 个原始组合不等于 Android/iOS Player 的最终编译数量。
9. **没有 ShadowCaster**：移动端成本较低，但植被没有动态投影；这是功能限制而非遗漏的 Pass。
10. **没有真机性能结果**：尚未验证 Mali、Adreno、Apple GPU 的 Compute/Indirect 兼容、Buffer 内存、带宽、Dispatch 和 Draw 时间。
11. **提交包含审计噪声**：`UserSettings/EditorUserSettings.asset` 被提交；Git 还将原空目录 `Assets/PCG/Scripts/Tests.meta` 的删除与 `Materials/CityPark.meta` 创建识别为 77% rename。二者都不是 City Park 功能本体。

建议下一阶段顺序：

```text
Capture Houdini Live / Definition / HIP + Unity Dirty Scene
    -> 对齐并解释 Live/Disk 差异
    -> 归档 V25～V44 必要 manifest/patch 或明确废弃
    -> Cook + Validate + Update Bake
    -> 验证 Anchor / Data / Profile / Exclusion / Fallback 资产
    -> 清理 Scene Live Preview 与 Tree/Tree Pit 残留
    -> Frame Debugger / RenderDoc 验证 Pass 与 Draw Count
    -> Android Mali / Adreno + iOS Metal 真机
    -> 记录 Variant Report、GPU Buffer、Dispatch、Draw、带宽和内存
```

## 13. 阶段结论

提交 `23` 将 Phase22 仅存在于迁移草案中的 City Park 正式合入 CityRoad HDA、累计合同和 Unity 编辑链。HDA 已具备闭合 Park Boundary 输入、确定性 Masterplan、Ground/Path/Water/Collision/Tree/Exclusion 六输出、非法输入 fail-closed、Surface Lift 和可维护 Subnet。Fresh 锁定实例通过 34 项累计合同，独立 Park Fixture 输出 1,114 Ground、350 Path、385 Water 和 9 Tree Points。

Unity 侧已提交 Safe Rebuild、Live Preview、Bake 验证、数据编译器、独立 RendererFeature、Compute Chunk/Instance Culling、双 LOD、Indirect Draw 和 64 m Fallback Chunk；三套 URP RendererData 均已启用 Feature，Shader 当前平台无编译错误。但提交没有正式 Bake 数据、Anchor、运行时截帧或移动端真机结果，Scene 中仍是 2,060 个 Live Preview PrefabInstance。

因此 Phase23 的准确结论是：**City Park 的 HDA 生成、Unity 编辑链和 GPU 运行时架构已实现并通过磁盘合同/编译验证；正式 Bake、GPU 实际执行和移动端发布验收尚未闭环。**
