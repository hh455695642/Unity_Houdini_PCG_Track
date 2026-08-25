# Phase 24 开发日志：CityPark 解耦与 CityRoad 三层可读性重构

> 文档类型：Git 提交增量审计与当前现场复验  
> 记录日期：2026-08-25  
> 版本文件：`Phase24_CityParkDecouplingAndCityRoadReadability.md`  
> 目标提交：`9bb9b44561a406868203a79e2b29296dc136c1f5`（提交信息：`24`）  
> 直接父提交：`d6d424627a4fa07933e354ca096f0540102d2a15`（`修复地形材质失效`）  
> CityRoad HDA：`Assets/PCG/HDA/City/CityRoad.hda`  
> CityPark HDA：`Assets/PCG/HDA/City/CityPark.hda`  
> CityRoad HIP：`HoudiniProject/PCG_Track_21.0.440/PCG_Bike_CityRoad.hip`  
> Unity 场景：`Assets/PCG/Scenes/PCG_City.unity`

## 1. 日志范围与结论

本文只记录 Git 提交 `9bb9b445` 相对直接父提交 `d6d42462` 的开发增量。提交 `24` 的核心不是继续扩展 Phase23 的 City Park GPU 植被，而是进行一次架构收敛：

```text
CityRoad 内嵌 CR_CITY_PARK + Unity GPU 植被运行时
    -> 从 CityRoad 公共接口、HDA 输出和 Bake/Preview 逻辑中移除
    -> 删除 CityPark Runtime / Compute / Indirect Shader
    -> 新建独立 CityPark HDA
       -> Park Area 输入
       -> Park Road 多曲线输入
       -> Range Terrain
       -> Road + Shoulders
    -> CityRoad 网络重组为三层结构
       -> 注释规范化
       -> 死节点/死分支清理
       -> 恢复生成链路连接
```

最终交付状态可概括为：

- **CityRoad 与 CityPark 已在 Houdini 资产层解耦。** CityRoad 恢复为单一 `unity_road_network` 输入和 7 类道路输出。
- **CityPark v1 成为独立 HDA。** 当前只负责范围地形、园路和路肩，不包含水体、树木、植被实例或 GPU 渲染。
- **Phase23 的 GPU 植被链路被撤销。** Runtime C#、Compute Shader、Indirect Shader 和 Bake 编译逻辑均从提交中删除。
- **CityRoad 可读性和维护性提升。** V46～V51 完成三层网络、注释、死节点/死分支清理、CityPark 解耦与生成链路修复。
- **验证不是完整道路生成闭环。** Fresh CityRoad 验证因没有绑定有效 `unity_road_network` SOP，只通过结构与空输入合同；主要几何行为套件被跳过。
- **提交快照存在 URP 遗留引用。** 三套 RendererData 仍引用已删除的 `CityParkVegetationRendererFeature` 脚本 GUID；当前工作区已有未提交修改在清除此引用，但不属于提交 `24`。

## 2. 证据等级

- **[提交验证]**：目标提交元数据、90 个变更文件、Git diff、HDA/HIP、Unity Scene、C#、合同、patch、验证器与 `.gitignore`。
- **[Fresh HDA 独立验证]**：使用 Houdini `21.0.440` 从磁盘 HDA 创建全新锁定实例；CityPark 完成带测试几何的 5 项合同，CityRoad 完成 35 项累计合同的结构/空输入检查；没有保存资产。
- **[Unity 现场]**：Unity MCP 确认 Editor 未播放、未编译，`PCG_City` 已打开且 Dirty；AssetDatabase 可识别独立 CityPark HDA，场景中存在三类 CityPark 输出。
- **[Houdini 连接验证]**：`Ensure-HoudiniMcp.ps1` 确认 Houdini、18811 RPC 与 3055 health 正常；后续 Houdini MCP 查询因 RPyC `maximum recursion depth exceeded` 失败，因此没有取得可信 Live Scene 节点级复验。
- **[源码验证]**：检查 CityRoad V46～V51 合同、CityPark builder/validator、Safe Rebuild、Live Preview、Bake Workflow 和 URP RendererData 引用。
- **[未闭环]**：没有独立 CityPark Bake 工作流、移动端真机、GPU Profiler、RenderDoc、正式 CityRoad 输入 Fixture 或完整生成行为回归。

工作区原有 URP 配置、Terrain HIP 与大量未跟踪资源均被保留；它们不能写成提交 `24` 的正式交付。

## 3. 提交概览

| 项目 | 数值 |
|---|---:|
| Commit | `9bb9b44561a406868203a79e2b29296dc136c1f5` |
| Author / Date | `liyuan` / 2026-08-25 18:05:46 +08:00 |
| Changed Files | 90 |
| Added / Deleted Lines | `+232940 / -139637` |
| CityRoad HDA | 339,179 → 306,423 bytes（-9.657%） |
| CityRoad HIP | 2,399,887 → 2,231,551 bytes（-7.014%） |
| 新增 CityPark HDA | 27,999 bytes |
| PCG_City Scene | 10,717,464 → 18,198,820 bytes（+69.807%） |
| PCG_City Scene Lines | 236,262 → 323,869（+87,607） |
| CityRoad Core 顶层节点 | 13 |
| CityRoad Author Subnet | 26 |
| CityRoad Required Nodes | 63 |
| CityRoad 累计 Contract ID | 35 |
| CityRoad Public Interface SHA-256 | `326b3b34356b6b17b6fd3b98d7ef9d77adecebeb236c7a8f25daee04c1b8f660` |
| Houdini Engine Unity 插件 | 0 个文件修改 |

文件指纹：

| 文件 | Phase24 SHA-256 |
|---|---|
| CityRoad HDA | `AF860B0744442F091D9C86A6D90D4DC39601B06970EF92EA7D2D6426929C8C91` |
| CityPark HDA | `C437CCE22781F8819762A685B054F2552247DEE7331710B2B17DBD9427649AB3` |
| CityRoad HIP | `7BAD19142888DA50C9A845F0CAE48DCB49419D32EE267579A377A76F05236E07` |
| PCG_City Scene | `28C091EFA1B39C9B15EAB10E1972C4CF9F398A463DCC0C04D8F338582C189FFD` |

## 4. CityRoad V46～V51 重构

### 4.1 V46：三层可读性结构

`CityRoadCore` 的主要内部功能被收纳到 `CR_MAIN_PIPELINE`，形成稳定的阅读层级：

```text
Level 1：CityRoad HDA 公共参数与资产输入
Level 2：CityRoadCore 的主流程、输出与发布边界
Level 3：CR_MAIN_PIPELINE 内的职责 Subnet
```

本次迁移将 167 个叶节点移动到新的主流程层，同时通过 127 个 channel proxy 引用保持参数驱动关系。验证器记录：

- `CityRoadCore` 顶层 13 个节点、9 条连接；
- `CR_MAIN_PIPELINE` 逻辑依赖 12 条，DAG 检查通过；
- 26 个 Author Subnet；
- 单节点最大输入数 4；
- 输出数 7；
- 5 个阶段 Network Box：`01 Context`、`02 Surface`、`03 Finalize`、`04 Outputs`、`05 Publish`。

该改动只重排维护结构，不允许公共输出语义变化。V46 manifest 明确列出旧路径到 `CR_MAIN_PIPELINE` 新路径的映射，并限制可改节点、连接和参数范围。

### 4.2 V47：注释与阅读规范

新增 `cityroad_annotation_contract.json`，用合同约束网络注释质量：

- `CityRoadCore` 顶层保留 9 个说明 Sticky Note；
- `CR_MAIN_PIPELINE` 保留 1 个主流程阅读说明；
- 使用阶段 Box Label 表达职责边界；
- `always visible` 节点注释数量为 0，避免大网络长期显示文本造成视觉噪声。

### 4.3 V48：死节点清理

删除未接线、未被读取的：

```text
CR_MAIN_PIPELINE/IN_LAB_SIDEWALK_CANDIDATE
```

同时把有意保留的未接线调试出口和实验返回节点登记为保护项：

- 3 个 Debug Output Portal；
- 2 个 Lab Return。

这样验证器可以区分真正的死节点和设计上允许的诊断扩展点。

### 4.4 V49：死碰撞与可见壳分支清理

删除不再参与最终结果的分支：

- `CR_COLLISION_AUDIT` 及其内部节点；
- `ROAD_UNION_BOUNDARY_WALLS`；
- `ROAD_WALL_METADATA`；
- `ROAD_MERGE_VISIBLE_SHELL`。

Collision 输出改为直接使用 `CR_ROAD_OUTPUT_CLASSIFY` 的第 2 路输出。Road Shell Audit、Sidewalk Seam Shatter 与 Street Furniture 等仍有用途的链路被列为保护分支，没有被误删。

### 4.5 V50：CityPark 从 CityRoad 解耦

CityRoad 中以下内容被正式移除：

- `CR_CITY_PARK` 及其内部节点；
- `OUT_PARK_GROUND`、`OUT_PARK_PATHS`、`OUT_PARK_WATER`；
- `OUT_PARK_COLLISION`、`OUT_PARK_TREES`、`OUT_PARK_EXCLUSION`；
- `enable_city_park`、`unity_park_areas`、水体、园路、树木和材质等 18 个公共参数。

CityRoad 输出合同恢复为 7 类：

1. Road；
2. Sidewalk；
3. Collision；
4. Markings；
5. Street Furniture 实例输出 1；
6. Street Furniture 实例输出 2；
7. Street Furniture 实例输出 3。

Unity 侧同步改为 Road-only：

- `CityRoadSafeRebuild` 只捕获和恢复 `unity_road_network`；
- 期望参数输入数恢复为 1；
- 移除 Park 空输入归一化和 Park 阶段二次 Cook；
- `CityRoadLivePreviewController` 不再识别或控制 `OUT_PARK_*`；
- `CityRoadBakeWorkflow` 不再验证 Park 材质、编译 Park Prefab、输出 Park Collision/Exclusion 或生成植被 Runtime 数据。

### 4.6 V51：恢复生成链路

三层重排后补回一处断开的 Subnet Output：

```text
CR_GRAPH_INDEX/GRAPH_CLASSIFY_JUNCTIONS
    -> SUBNET_OUT_GRAPH_CLASSIFY_JUNCTIONS_0
```

同时在 `CITYROAD_TOPOLOGY_CLASSIFY_ROAD` 中补充：

```c
addprimattrib(0, "name", "");
```

这使拓扑分类节点在空输入下也具备稳定的 `name` Primitive Attribute，避免空几何打包阶段报错。Fresh 验证确认：

- Graph 输出已连接；
- 断开的 Subnet Output 为 0；
- Empty Pack Error 为 0。

## 5. 独立 CityPark HDA v1

### 5.1 资产与输入

新增：

```text
Assets/PCG/HDA/City/CityPark.hda
```

Unity GUID：`38d95d7228f877d49aadb865fa15d351`。Unity Scene 中独立序列化为：

- Asset Name：`CityPark2`；
- Asset Op Name：`pcgbike::Object/CityPark::1.0`；
- Asset Path：`Assets/PCG/HDA/City/CityPark.hda`；
- 参数输入：`unity_park_areas`、`unity_park_roads`。

`citypark_contract.json` 的规范类型名为 `pcgbike::CityPark::1.0`，而 Houdini/Unity 实例返回带类别前缀的 `pcgbike::Object/CityPark::1.0`。验证器兼容这两种表示；这属于类型名展示差异，不是两个 HDA Definition。

### 5.2 公共参数

| 类别 | 参数与默认值 |
|---|---|
| Ground | `enable_ground=1` |
| 输入 | `unity_park_areas`、`unity_park_roads` |
| 地形采样 | `terrain_mesh_size=5.0`，范围 1～20 |
| 起伏 | `terrain_height_amplitude=0.6`，范围 0～3 |
| 噪声波长 | `terrain_noise_wavelength=45.0`，范围 5～200 |
| 边缘衰减 | `terrain_edge_fade=8.0`，范围 0.1～50 |
| 随机种子 | `terrain_seed=1`，范围 0～999999 |
| 道路压地 | `road_ground_sink=0.25`，范围 0～2 |
| 道路融合 | `road_ground_blend=1.5`，范围 0.1～10 |
| Road | `enable_road=1`、`road_width=4.0`、`sample_spacing=2.0` |
| Shoulder | `enable_shoulders=1`、`shoulder_width=0.75`、`shoulder_drop=0.12` |
| 表面与 UV | `road_surface_offset=0.05`、`uv_tile_length=4.0` |

材质默认绑定：

- Ground：`M_PCG_CityPark_Grass.mat`；
- Road / Shoulder：`M_PCG_CityPark_Path.mat`。

### 5.3 网络职责

CityPark v1 使用四个职责区：Input、Terrain、Road、Outputs。

```text
unity_park_areas
    -> HAPI Area Boundary Convert / Rebuild
    -> Triangulate / Remesh
    -> 低频高度扰动 + 边缘衰减
    -> Road Sink / Blend
    -> Normal / up / park_role / unity_material
    -> OUT_PARK_GROUND

unity_park_roads
    -> HAPI Road Curve Convert
    -> Resample
    -> Multi-Curve Road + Shoulder
    -> path_id / UV / park_role / unity_material
    -> OUT_PARK_ROAD
    -> OUT_PARK_SHOULDERS
```

多曲线合同要求每条来源曲线有独立 `path_id`，允许同一公园区域中存在多条园路。地面在道路范围内下沉并使用 Blend Width 平滑过渡，减少道路与地面 Z-Fighting。

### 5.4 明确不属于 v1 的功能

`CityPark.V1.NoVegetationOrWater` 合同明确禁止当前网络出现以下功能：

- Water / Lake；
- Tree / Vegetation；
- Instance；
- Road Marking；
- Sidewalk。

因此场景中现有 Water Material 只是可用资源，不代表提交 `24` 已实现水体。Phase23 的树木、排除区、Chunk、LOD 与 GPU Indirect Draw 也不能视为 Phase24 能力。

## 6. Unity 场景集成

提交后的 `PCG_City.unity` 增长到 18.20 MB，序列化对象变化如下：

| Unity YAML 对象 | 父提交 | Phase24 | 变化 |
|---|---:|---:|---:|
| GameObject | 2,291 | 2,916 | +625 |
| Transform | 2,291 | 2,916 | +625 |
| MonoBehaviour | 186 | 186 | 0 |
| PrefabInstance | 2,060 | 2,694 | +634 |
| Mesh | 76 | 74 | -2 |
| MeshFilter | 140 | 138 | -2 |
| MeshRenderer | 140 | 138 | -2 |
| Collider | 1 | 1 | 0 |

当前 Unity MCP 现场确认：

- Unity `2022.3.62f2`，未播放、未暂停、未编译、未刷新 AssetDatabase；
- 打开的场景是 `Assets/PCG/Scenes/PCG_City.unity`；
- Scene 为 Dirty，Root Count 为 9，本次审计未保存；
- `CityPark.hda` 可由 AssetDatabase 找到，GUID 与提交一致；
- `CityPark` 根对象包含 `HEU_HoudiniAssetRoot`；
- 子对象包含 Ground、Road、Shoulders 三类输出；
- `HDA_Data` 标记为 `EditorOnly`。

这些输出仍属于 Houdini Engine Live Preview 现场。提交没有为独立 CityPark 增加与 CityRoad 等价的正式 Bake / Validate / Update Bake 流程，因此不能直接认定已满足移动端运行时“只消费 Bake 数据”的交付要求。

## 7. Phase23 GPU 植被链路撤销

提交删除整个 `Assets/PCG/Scripts/CityPark/` Runtime 目录，包括：

- `CityParkVegetationAnchor`；
- `CityParkVegetationData`；
- `CityParkVegetationProfile`；
- `CityParkVegetationRendererFeature`；
- `PCGSiteExclusionData`；
- `PCGBike.CityPark.Runtime.asmdef`。

同时删除：

- `PCG_CityPark_Culling.compute`；
- `PCG_CityPark_VegetationIndirect.shader`；
- `CityRoadParkAssets.cs`；
- CityRoad Bake 中的 Park Runtime Data、Chunk、LOD、Collision、Exclusion 和 Fallback 编译逻辑。

渲染结论：

- Phase24 没有新增 RendererFeature 或 RenderPass；
- Phase23 的 GPU Culling、`DrawMeshInstancedIndirect` 和低成本风动画不再是当前正式链路；
- 自定义 CityPark Shader 被删除，因此不再引入其 `multi_compile_instancing` 或其他 Variant；
- 独立 CityPark 当前只生成静态网格，应在后续 Bake 后使用 URP 移动端材质与常规批处理策略。

### 7.1 URP RendererData 遗留引用

提交快照的三套 RendererData 仍序列化以下已删除脚本 GUID：

```text
b6d50fe5800b11e458c91fc4b44ff5a3
```

涉及：

- `URP-Balanced-Renderer.asset`；
- `URP-HighFidelity-Renderer.asset`；
- `URP-Performant-Renderer.asset`。

其名称仍为 `City Park Vegetation Indirect`。这会形成 Missing RendererFeature / Missing Script 风险，说明“删除运行时代码”和“清理 RendererData 子资产”没有在同一提交中闭环。

当前磁盘工作区对这三份 RendererData 已存在未提交删除引用的修改，因此 Unity 当前现场没有再检索到该 GUID；这只能视为后续现场修复，不能回写成提交 `24` 已完成的内容。

## 8. 合同、迁移记录与仓库清理

### 8.1 正式合同

新增或更新：

- `citypark_contract.json`；
- `cityroad_annotation_contract.json`；
- `cityroad_dead_node_contract.json`；
- `cityroad_dead_branch_contract.json`；
- `cityroad_contract.json`；
- `cityroad_subnet_layout_contract.json`；
- `validate_citypark_contract.py`；
- `validate_cityroad_contract.py`。

CityPark 合同共 5 项：

1. `CityPark.Interface.Public`；
2. `CityPark.Network.Outputs`；
3. `CityPark.V1.RangeTerrain`；
4. `CityPark.V1.MultiCurveRoad`；
5. `CityPark.V1.NoVegetationOrWater`。

### 8.2 历史迁移归档

提交一次性归档 CityRoad V25～V44 的多份 manifest/patch，并新增 V46～V51 的正式变更记录。还加入 StreetBuilding v1/v2 与 Terrain v1～v4 manifest。

这些旧 patch 是迁移审计记录，不是可依次重放的当前事实源；StreetBuilding/Terrain manifest 的纳入也不等于提交 `24` 实现了这些模块的资产功能。

### 8.3 本地文件清理

- `.gitignore` 新增 `UserSettings/`、Houdini recovery、City HDA backup 与 `.codex_tmp/` 忽略规则；
- 删除 `CityRoad_UnityInput_Debug.bgeo.sc` 临时调试缓存；
- 删除三份已被跟踪的 `UserSettings` 文件。

## 9. Fresh 验证结果

### 9.1 CityPark

执行：

```powershell
& 'D:\Software\Side Effects Software\Houdini 21.0.440\bin\hython.exe' `
  'HoudiniProject/PCG_Track_21.0.440/scripts/tools/validate_citypark_contract.py' `
  --source fresh
```

结果：PASS。

| 项目 | 结果 |
|---|---:|
| Asset | `/obj/VERIFY_CITYPARK_LOCKED` |
| Type | `pcgbike::Object/CityPark::1.0` |
| Definition Locked | `true` |
| Ground | 613 points / 1,160 prims |
| Road | 254 points / 125 prims |
| Shoulders | 508 points / 250 prims |
| Path IDs | `[0, 1, 2]` |
| Ground Minimum Y | `-0.25` |
| Saved | `false` |

这验证了独立 HDA 的实际范围地形、多曲线园路和路肩生成，不只是节点存在性。

### 9.2 CityRoad

Fresh CityRoad 验证结果：PASS，但验证范围受限。

- 35 项累计合同通过；
- HDA Definition Locked；
- 公共接口哈希为 `326b3b...f660`；
- Required Nodes 为 63；
- 三层结构、注释、死节点、死分支、V50 解耦与 V51 连接恢复均通过；
- 所有主要几何输出为 0；
- V7～V18 与 V24 几何行为套件因没有有效 `unity_road_network` SOP Fixture 被跳过；
- `saved=false`。

因此本次结果只能证明 CityRoad **结构合同和空输入安全性**，不能证明道路、路口、路缘、人行道、标线和街具的累计几何行为没有回归。后续必须用有效道路输入重新执行 VerifyFull。

### 9.3 门禁单元测试

执行：

```powershell
& 'D:\Software\Side Effects Software\Houdini 21.0.440\bin\hython.exe' `
  'HoudiniProject/PCG_Track_21.0.440/scripts/tests/test_pcg_regression_gate.py'
```

结果：`Ran 11 tests`，全部通过。

### 9.4 Unity Console

当前 Console 中存在两条与交付状态有关的历史信息：

- Error：`CityRoad1 is still in Live Preview or has no active Bake instance`；
- Warning：`CityRoad1/CityRoadCore/CR_MAIN_PIPELINE No geometry generated`。

它们与当前缺少正式 Bake、道路输入未形成有效输出的现场一致。没有执行清空 Console 后的重新 Cook，因此不能声称 Phase24 达到“零新增警告”。

## 10. 移动端与架构评估

### 10.1 CPU / GPU 边界

| 阶段 | Phase24 实际方案 | 移动端评价 |
|---|---|---|
| CityPark 生成 | Houdini Editor Cook | 可接受，但必须 Bake 后发布 |
| Runtime Geometry | 当前无独立正式 Bake 产物 | 未闭环 |
| 植被渲染 | Phase23 GPU Indirect 系统已删除 | 当前无大规模植被能力 |
| Road / Ground | HDA 静态 Mesh 输出 | Bake 后可使用常规 URP 路径 |
| 剔除 / LOD | 未提供 CityPark 专用实现 | 后续植被恢复时应重新采用 GPU Chunk/Cluster 方案 |

Phase24 降低了系统耦合和脚本复杂度，但也主动移除了已有 GPU 驱动植被能力。后续若恢复大规模植被，应以独立 CityPark RendererFeature + 独立 RenderPass + ScriptableObject 配置实现，并保持 Feature Toggle、GPU Culling、Chunk/Cluster 与 LOD；不应重新塞回 CityRoad Bake Workflow。

### 10.2 RenderPass 与带宽

提交删除 CityPark 自定义 RenderPass，本身不会新增全屏 Blit、RenderTexture、MRT 或 Shader Variant。对 Tile-Based GPU 的即时风险降低，但提交快照中的 Missing RendererFeature 引用必须先清理，才能把 RendererData 视为有效发布配置。

### 10.3 Shader Variant

Phase24 没有新增 Shader。被删除的 Indirect Shader 原有 Instancing 支持也随之失效。未来恢复植被时仍需：

- 保留 `multi_compile_instancing`；
- 可选功能优先 `shader_feature_local`；
- 强度/开关优先 uniform；
- 控制 URP keyword 叠加，目标 Variant 数量小于 200；
- 植被 Shader 与道路/角色/特效 Shader 分离。

## 11. 已知问题与后续验收

1. **清理 RendererData 遗留引用。** 把当前工作区三套 URP RendererData 的引用清理作为独立提交，并检查所有 Quality Level 使用的 RendererData。
2. **补独立 CityPark Bake。** 输出 Unity 原生 Mesh、Material、Collider（如需要）和稳定目录；运行时禁止依赖 Houdini Cook。
3. **为 CityRoad 提供有效 Fixture。** 绑定 `unity_road_network` 后执行 VerifyFull，覆盖 V7～V18、V24 和最终 7 类输出。
4. **保存前处理 Live Preview 错误。** `PCG_City` 当前仍 Dirty，且 CityRoad 没有 active Bake instance。
5. **重新清空并复验 Console。** 分别验证 CityRoad、CityPark Cook/Reload/Bake 后无新增 Error/Warning。
6. **控制场景体积。** Scene 增长约 69.8%，PrefabInstance 增加 634；应确认这些对象是否必须直接序列化，避免编辑器和版本控制成本继续上升。
7. **补移动端验证。** Android Mali/Adreno 与 iOS Metal 真机检查 Mesh 精度、材质、阴影、Overdraw、带宽和场景加载峰值。
8. **修复 Houdini MCP 连接层。** Preflight 健康但 RPyC 查询递归溢出，修复后重新核对 Live HIP、Definition、Cook Error/Warning 和 Scene Diff。

## 12. Phase24 最终状态

提交 `24` 完成了 CityRoad/CityPark 职责拆分：CityRoad 通过 V46～V51 获得更清晰的三层网络、注释合同、死节点清理和生成链路修复；CityPark 则以独立 HDA v1 提供范围地形、多曲线道路与路肩。

本阶段是一次**架构收敛与功能降级并存**的提交：解耦方向正确，Fresh CityPark 几何验证有效，但 Phase23 GPU 植被、Park Bake 和水体/树木能力已经移除；CityRoad 完整几何回归因缺少输入而未执行；提交快照还遗留三套 URP RendererFeature 的 Missing Script 风险。

因此 Phase24 可标记为：

> **CityPark 独立 HDA v1 与 CityRoad 结构重构已提交；移动端可发布 Bake、完整 CityRoad 行为回归和 URP 引用清理仍待闭环。**
