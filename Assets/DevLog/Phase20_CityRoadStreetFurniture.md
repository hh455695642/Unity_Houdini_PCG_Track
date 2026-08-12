# Phase 20 开发日志：CityRoad 街道设施生成、包含性与 Unity Bake 接入

> 文档类型：提交增量快照  
> 记录日期：2026-08-12  
> 目标提交：`df1f5e7f1ef61ef68f5a054882a681191f69934d`（提交信息：`20`）  
> 父提交：`58f453a818542deb993c38a98954c73dd52fc79c`（Phase19 日志提交）  
> CityRoad HDA：`Assets/PCG/HDA/City/CityRoad.hda`  
> CityRoad HIP：`HoudiniProject/PCG_Track_21.0.440/PCG_Bike_CityRoad.hip`  
> Unity 场景：`Assets/PCG/Scenes/PCG_City.unity`（本提交未修改）

## 1. 日志范围与证据

本文只记录 Git 提交 `df1f5e7` 相对父提交 `58f453a` 的开发增量。Phase1～Phase19 已记录的 Track、Terrain、CityRoad 输入、道路拓扑、开放端、Sidewalk Connector 与 V15 Terminal Front Containment 不再重复。

Phase20 的实际开发链：

```text
街道设施公共接口
    -> 路灯开关、Prefab、间距与朝向
    -> 行道树 Multiparm、权重、间距、缩放与随机种子
    -> 树池概率、设施带内缩、最小人行道宽度与净距

独立点实例分支
    -> 从现有道路中心线和 Junction Metadata 采样
    -> 生成路灯、树木、树池 unity_instance 点
    -> 按 pcg_group_key 拆分可复用实例组
    -> 输出 OUT_STREET_LAMPS / TREES / TREE_PITS

包含性修复
    -> V2：以道路宽度扩展 Junction/Endpoint 排除范围
    -> V3：以最终道路三角面检查真实实例位置
    -> 路灯成对跳过，避免只保留道路一侧
    -> 树木逐点跳过，并让树池严格继承树木结果

Unity 编辑器接入
    -> Bake 前验证 HDA 参数和 Prefab 约束
    -> 验证三个设施输出层级及运行时组件
    -> Live Preview 把设施输出纳入可见角色
    -> 提交五套占位 Mesh / Material / Prefab

审计与维护
    -> 补交 V15 patch 与 manifest
    -> 新增街道设施 V1/V2/V3 manifest
    -> 修复回归门禁对 HDA 公共参数模板的持久化
    -> 整理 CityRoadCore Network Box 与阅读顺序
    -> Fresh Locked Instance 累计验证 PASS
```

证据等级：

- **[提交验证]**：目标提交元数据、52 个变更文件、diff、HDA/HIP、Unity 资产、C#、change manifest、patch、合同与验证器。
- **[Fresh HDA 独立验证]**：Houdini `21.0.440` 独立 `hython` 创建全新锁定实例，并从生产 HIP 复制实例参数后执行累计合同；没有保存资产。
- **[Houdini Live 现场]**：`Ensure-HoudiniMcp.ps1` 与 Houdini MCP 只读检查当前 HIP、实例、节点与诊断；没有更新 Definition。
- **[Unity 现场]**：Unity MCP 检查 Editor、打开场景、Prefab/Mesh/Material 的 AssetDatabase 导入和 Console。
- **[未闭环]**：提交没有 Scene/Bake 结果、Chunk/Cluster、LOD、GPU Culling、Indirect Draw 或移动端真机数据。

本文不把当前工作区中未跟踪的 `CityRoadStreetFurniturePlaceholders.cs`、`CityRoadStreetFurnitureTests.cs` 和统一 PowerShell 回归入口写成提交“20”已交付内容。

## 2. 提交概览

| 项目 | 数值 |
|---|---:|
| Commit | `df1f5e7f1ef61ef68f5a054882a681191f69934d` |
| Author / Date | `liyuan` / 2026-08-12 20:30:24 +08:00 |
| Changed Files | 52 |
| Added / Deleted Lines | `+5106 / -16` |
| CityRoad HDA | 268,227 → 278,476 bytes（+3.821%） |
| CityRoad HIP | 1,953,664 → 2,000,636 bytes（+2.404%） |
| CityRoadCore Children | 179 → 186（+7） |
| Required Nodes | 42 → 49（+7） |
| 累计 Contract ID | 22 → 24（+2） |
| Public HDA Inputs / Outputs | 0 / 6（不变） |
| 新增 Unity 设施资产 | 5 Mesh + 5 Material + 5 Prefab |
| 修改 Unity C# | 2 个 Editor 脚本 |
| Unity Scene / Shader / RendererFeature | 0 个文件修改 |
| Houdini Engine Unity 插件 | 0 个文件修改 |

文件按职责分为：

1. `Assets/PCG/Art/StreetFurniture/Placeholders/`：五套占位 Mesh、Material 与 Prefab。
2. `Assets/PCG/Editor/CityRoad/CityRoadBakeWorkflow.cs`：Bake 前后设施配置与层级验证。
3. `Assets/PCG/Editor/CityRoad/CityRoadLivePreviewController.cs`：设施输出可见性。
4. `Assets/PCG/HDA/City/CityRoad.hda` 与生产 HIP：正式节点、参数和输出。
5. 五个 change manifest：V15、设施 V1、道路包含性 V2、表面包含性 V3、Network Layout。
6. 五个一次性 patch/layout 脚本：V15、设施 V1/V2/V3 与布局整理。
7. `cityroad_contract.json`、`validate_cityroad_contract.py`、`pcg_regression_gate.py`：累计合同与持久化门禁。

文件指纹：

| 文件 | Phase20 SHA-256 |
|---|---|
| CityRoad HDA | `7DD023161158860E1CEC8E59CB1EB428A59ACED57164A746EBE761A3BAEE5D19` |
| CityRoad HIP | `B7076FA298F1673BA0D15B0360ACC26C51734459C1E6F3727473CAEA47CBC0CF` |

## 3. Street Furniture 公共参数

HDA 新增 `Street Furniture / 街道设施` 参数组。生产 HIP 当前使用的参数如下：

| 参数 | 生产值 | 职责 |
|---|---:|---|
| `enable_street_lamps` | 1 | 路灯总开关 |
| `lamp_prefab` | `PF_StreetLamp_Placeholder.prefab` | 路灯实例资产 |
| `lamp_spacing` | 25 m | 路灯纵向间距 |
| `lamp_yaw_offset` | 0° | Prefab 朝向修正 |
| `enable_street_trees` | 1 | 行道树总开关 |
| `tree_variants` | 3 | 树木 Multiparm 数量 |
| `tree_spacing_min/max` | 8 / 14 m | 确定性随机间距范围 |
| `tree_scale_min/max` | 0.85 / 1.25 | 实例缩放范围 |
| `tree_seed` | 1729 | 分布随机种子 |
| `tree_pit_prefab` | `PF_TreePit_Placeholder.prefab` | 树池实例资产 |
| `tree_pit_probability` | 1.0 | 树池生成概率 |
| `facility_edge_inset` | 0.5 m | 设施带相对道路/人行道边界内缩 |
| `minimum_sidewalk_width` | 1.0 m | 允许生成设施的最小人行道宽度 |
| `lamp_tree_clearance` | 3.0 m | 树与路灯最小净距 |
| `junction_endpoint_clearance` | 6.0 m | Junction/开放端额外净距 |

树木 Multiparm 支持每行独立 `tree_prefab#` 与 `tree_weight#`。生产 HIP 的三个实例参数分别指向 Round、Tall、Wide，占位权重均为 1；生成器会合并重复 Prefab 路径，并只消费正权重项。

公共接口 SHA-256 从 Phase19 的：

```text
6efd6f02eb08296b78ba60c75d8d35af8486ae1e385a71d963c165034eee555a
```

变为磁盘 Definition 的：

```text
42da45a4abd6c3c25fd88d773da8bf34255922fc4e22e759f39ba9dcc8208d7a
```

这是有意的公共 API 扩展，而非参数意外漂移。`pcg_regression_gate.py` 同步修复持久化流程：`definition.updateFromNode(asset)` 后显式执行 `definition.setParmTemplateGroup(asset.parmTemplateGroup())`，避免只保存内部节点、遗漏新增公共参数模板。

### 3.1 新实例默认值限制

Multiparm 的模板只能定义统一行默认值。Phase20 patch 在迁移 Live 实例时显式把三行写成 Round/Tall/Wide，但磁盘 HDA 的全新实例默认三行都会指向 Round。Fresh 累计验证之所以能得到三个变体，是因为验证器从生产 HIP 复制了已初始化的实例参数。

因此当前状态应区分：

- **生产 HIP 参数**：Round / Tall / Wide，累计合同通过。
- **全新 HDA 实例模板默认**：Round / Round / Round，需要用户手动修改或由后续初始化工具补齐。

这是 Phase20 尚未闭环的默认配置问题；不能仅以 `tree_variants = 3` 推断新实例已包含三种不同树形。

## 4. 独立点实例生成分支

### 4.1 节点与连接

新增七个正式节点：

```text
OUT_ROAD_CENTERLINE_GRAPH
    + CITYROAD_JUNCTION_APPROACH_METADATA
    + CITYROAD_TOPOLOGY_CLASSIFY_ROAD
    -> CITYROAD_STREET_BUILD_LAMPS_V1
    -> OUT_STREET_LAMPS

OUT_ROAD_CENTERLINE_GRAPH
    + CITYROAD_STREET_BUILD_LAMPS_V1
    + CITYROAD_JUNCTION_APPROACH_METADATA
    + CITYROAD_TOPOLOGY_CLASSIFY_ROAD
    -> CITYROAD_STREET_BUILD_TREES_V1
    -> OUT_STREET_TREES

CITYROAD_STREET_BUILD_TREES_V1
    -> CITYROAD_STREET_BUILD_TREE_PITS_V1
    -> CITYROAD_STREET_FURNITURE_V1
    -> OUT_STREET_TREE_PITS
```

三个 `attribwrangle` 分别只负责路灯、树木和树池；`CITYROAD_STREET_FURNITURE_V1` 是说明/汇合 Null，三个 `output` 独立暴露实例点。该结构没有侵入道路 Mesh 的 Topology 输出，也没有把三类生成职责塞入一个“超级节点”。

### 4.2 输出数据契约

每个设施点至少携带：

- `unity_instance`：Unity Prefab 的 `Assets/*.prefab` 路径。
- `orient`、`pscale`：实例朝向与缩放。
- `pcg_kind`：lamp / tree / tree_pit。
- `pcg_group_key`：按种类与 Prefab 路径分组。
- `pcg_distance`、`pcg_corridor_length`：沿道路的位置和所属走廊长度。
- `unity_split_attr = pcg_group_key`：要求 Houdini Engine 按实例组拆分输出。

路灯按道路两侧成对生成；树木使用种子、间距范围、权重和净距做确定性分布；树池直接继承已接受的树木点，从而保证数量、位置、朝向与缩放一一对应。

### 4.3 开关与退化输入

设施生成同时受自身开关与 `enable_sidewalk` 控制。验证器还覆盖：

- Sidewalk 关闭时设施输出为空。
- Sidewalk 宽度不足时设施输出为空。
- 相同参数重复 Cook 的输出签名稳定。
- 修改 `tree_seed` 后树木分布签名发生变化。
- 重复树 Prefab 路径会合并权重，不产生重复实例组。

这些计算全部发生在 Houdini 编辑/Cook 阶段，移动端运行时仍只允许消费 Bake 后的 Unity 数据。

## 5. V2/V3 道路与表面包含性

### 5.1 V2：道路宽度参与 Junction 排除

设施 V1 最初只按中心线端点与 Junction Metadata 的固定净距排除，不能覆盖真实道路宽度。V2 将排除半径扩展为：

```text
0.5 * road_width + junction_endpoint_clearance
```

并把路灯/树木生成节点的道路分类结果作为额外输入。这样设施点不会仅仅“远离中心点”，而是先离开道路 footprint，再叠加用户要求的 6 m 净距。

### 5.2 V3：以最终道路三角面做真实位置审计

不规则 Junction Corner、开放端和边界形状不能只用中心距离可靠描述。V3 在最终实例位置投影到道路高度后，以 `xyzdist` 对最终道路 Top Triangle 做平面包含测试：

- 任一侧路灯落入道路表面时，整对路灯都跳过，防止道路只剩一侧灯。
- 树木逐点检查真实位置，落入道路表面的候选直接跳过。
- 树池从最终树木输出派生，不会为被删除的树保留孤立树池。

Fresh 生产参数结果：

| 指标 | 数值 |
|---|---:|
| Lamp Instances | 230 |
| Lamp Pairs | 115 |
| Tree Instances | 415 |
| Tree-pit Instances | 415 |
| Effective Tree Variants | 3 |
| Road Surface Intrusions | 0 |
| Lamp Pairs Skipped by Surface | 9 |
| Trees Skipped by Surface | 17 |
| Deterministic Signature | `1b0cffae018a22b468a4a792131dc56c7193ace4daa50c4c5febf1fc01152f81` |

累计合同同时确认“无 Sidewalk”和“窄 Sidewalk”测试的 lamps/trees/tree_pits 都为 `0/0/0`。

## 6. Unity 占位资产

### 6.1 资产组成

提交新增五套占位 Prefab：

| Prefab | Mesh | SubMesh | Vertices | Triangles | Materials |
|---|---|---:|---:|---:|---|
| Street Lamp | 独立灯杆 Mesh | 1 | 136 | 104 | Lamp |
| Tree Pit | 独立树池 Mesh | 1 | 96 | 48 | Tree Pit |
| Tree Round | Round 树 Mesh | 2 | 603 | 848 | Bark + Leaf A |
| Tree Tall | Tall 树 Mesh | 2 | 638 | 912 | Bark + Leaf B |
| Tree Wide | Wide 树 Mesh | 2 | 603 | 848 | Bark + Leaf B |

每个 Prefab 的根对象只有：

```text
Transform
MeshFilter
MeshRenderer
```

没有 Collider、LODGroup、Animator、Animation、ParticleSystem 或运行时 MonoBehaviour。五个 Material 均使用 URP Lit，占位材质已开启 GPU Instancing；路灯材质额外启用 `_EMISSION`。

### 6.2 AssetDatabase 验证

Unity MCP 已找到：

- 5 个 Prefab。
- 5 个 Mesh。
- 5 个 Material。
- Prefab、Mesh、Material 的 GUID 引用均可解析。

这证明提交资产可被当前 Unity `2022.3.62f2` 正常导入，但不等于正式美术、运行时 Bake 或移动端性能已经完成。

### 6.3 移动端资产风险

这些资产明确是 Placeholder，当前仍存在以下交付限制：

- 五个 Mesh 均为 `m_IsReadable = 1`，运行时可能保留 CPU 侧 Mesh 数据。
- 五个 Mesh 均序列化为 32-bit Index Format；当前最高只有 638 Vertices，没有使用 32-bit Index 的必要。
- 树木每实例两个 SubMesh/Material，会把每个树种拆成至少两个渲染批次。
- Prefab 没有 LOD；415 棵树全部使用单一网格层级。
- 没有 Chunk/Cluster、GPU Culling 或 `DrawMeshInstancedIndirect` 数据结构。

Material 的 `Enable GPU Instancing` 只能降低相同 Mesh/Material 的批次数，不能替代实例数据压缩、GPU 剔除、LOD、Chunk Culling 和 GameObject 数量控制。按 Fresh 输出，路灯、树和树池合计 1,060 个实例点；直接 Bake 为独立 GameObject/Renderer 不应视为移动端最终方案。

## 7. Unity Bake 与 Live Preview

### 7.1 Bake 前配置验证

`CityRoadBakeWorkflow` 在 Reload/Rebuild 完成、但尚未触碰现有 Bake Prefab 前执行 `ValidateStreetFurnitureConfiguration`：

- 路灯、树池和所有树变体必须是 `Assets/*.prefab`。
- Prefab 必须可由 AssetDatabase 加载。
- 每个 Prefab 必须恰好包含一个 MeshRenderer 和一个 MeshFilter，且位于同一 GameObject。
- MeshFilter 必须绑定有效 Mesh。
- 禁止 Collider、LOD、动画、粒子和运行时脚本。
- `tree_variants` 至少一项，所有权重必须为正数。

失败时流程在修改旧 Bake 前退出，保留已有交付结果。

### 7.2 生成层级验证

Cook 后验证器要求三个输出根都存在：

- `OUT_STREET_LAMPS`
- `OUT_STREET_TREES`
- `OUT_STREET_TREE_PITS`

每个输出必须至少包含一个启用的 Prefab Renderer，并继续禁止 Collider、LODGroup、Animator 和 ParticleSystem。原有 presentation piece 判定同时扩展到 `SidewalkRegion_`，避免合法 Sidewalk Region 被误判为隐藏 backing renderer。

### 7.3 Live Preview 可见性

`CityRoadLivePreviewController` 将三个设施输出加入 visible role：

- Live Preview 中设施实例可见。
- Collision 输出继续保持隐藏。
- 有 Active Bake 时仍遵循 Source/Bake 互斥显示。
- 设施不要求 Corridor/Junction/SidewalkRegion 的 Topology Piece 命名即可显示。

本提交没有修改 `PCG_City.unity`，因此只交付了编辑器工作流能力，没有交付已保存的街道设施 Scene 或正式 Bake Prefab。

## 8. 累计合同与回归门禁

### 8.1 合同扩展

累计 Contract ID 从 22 个增加到 24 个：

- `CityRoad.V16.StreetFurniture`
- `CityRoad.V17.StreetFurnitureSurfaceContainment`

required node 数从 42 增至 49，正式 output node 从四个道路/人行道输出扩展为七个，新增三个设施输出。原有 V13～V15、几何健康、绕序与 Output 无诊断合同继续保留。

### 8.2 Change Manifest

本提交新增：

- `cityroad_v15_sidewalk_terminal_front_containment.json`
- `cityroad_street_furniture_20260812.json`
- `cityroad_street_furniture_road_containment_20260812.json`
- `cityroad_street_furniture_surface_containment_20260812.json`
- `cityroad_core_layout_cleanup_20260812.json`

这补齐了 Phase19 缺失的 V15 patch/manifest。设施 V1 允许新增参数、节点、连接和输出；V2/V3 只允许增量修改路灯/树木节点的特定连接和 VEX；Layout Manifest 禁止节点、连接、参数、公共接口和输出变化。

所有 manifest 的 `allowed_warning_signatures` 都为空，表示目标是“不接受新增 Warning”，而不是宽泛忽略历史诊断。

### 8.3 Manifest 与提交边界缺口

`cityroad_street_furniture_20260812.json` 的白名单还声明了：

- `Assets/PCG/Editor/CityRoad/CityRoadStreetFurniturePlaceholders.cs`
- `Assets/PCG/Scripts/Tests/Editor/CityRoad/CityRoadStreetFurnitureTests.cs`
- `Assets/PCG/Generated/Road/CityRoad/**`

前两个文件没有进入提交 `df1f5e7`，当前只存在于未跟踪工作区；第三项是允许生成的 Bake 路径，本提交没有实际生成文件。因此：

- 干净 checkout 可以获得五套占位资产，但没有提交对应的资产生成工具源码。
- 干净 checkout 没有街道设施专项 Unity Test。
- 本提交没有正式 Generated/Road Bake 结果。

白名单表示“允许修改”，不能反向证明对应文件已经提交或已经通过测试。

## 9. CityRoadCore 布局整理

`layout_cityroad_core_20260812.py` 是布局专用迁移：

- 以 179 节点和内容哈希作为严格前置条件。
- 统一 V7/V11/V12 Network Box 命名。
- 将缺失节点补入现有 Sidewalk、Curb、2D Partition Box。
- 按输入、道路构建、边界 Feature、Topology、Sidewalk、Output 的阅读顺序排列 Box。
- 使用 input / road / feature / sidewalk / unity / output 颜色区分职责。
- 不创建、删除、重命名或重连 SOP，不修改 SOP 参数。
- 默认 `save=False`，失败时恢复全部编辑器布局状态。

随后新增的街道设施节点形成独立分支，因此最终 Core Children 为 186。布局变化只提升 Houdini 初学者对网络的可读性，不影响 Cook 几何或 Unity 运行时性能。

## 10. HDA、HIP 与 Fresh 输出

### 10.1 正式结构

| 指标 | Phase19 | Phase20 |
|---|---:|---:|
| CityRoadCore Children | 179 | 186 |
| Required Nodes | 42 | 49 |
| HDA Inputs | 0 | 0 |
| HDA Outputs | 6 | 6 |
| 正式几何/实例 Output Node | 4 | 7 |
| Public Interface Hash | `6efd…` | `42da…` |

HDA 对外连接槽数量仍为 0/6；新增的是 Houdini Engine 可消费的内部 Output SOP，不是 HDA 节点连接槽数量的扩展。

### 10.2 Fresh Locked Output

| Output | Points | Primitives | Vertices |
|---|---:|---:|---:|
| `OUT_ROAD_SURFACE` | 21 | 21 | 21 |
| `OUT_SIDEWALK_CURB` | 13 | 13 | 13 |
| `OUT_ROAD_COLLISION` | 198 | 220 | 660 |
| `OUT_ROAD_MARKINGS` | 21 | 21 | 21 |
| `OUT_STREET_LAMPS` | 230 | 0 | 0 |
| `OUT_STREET_TREES` | 415 | 0 | 0 |
| `OUT_STREET_TREE_PITS` | 415 | 0 | 0 |

前三个设施输出是实例点流，不是已经展开的 Mesh。Fresh 累计合同结果：

```text
status = PASS
locked = true
source = fresh_locked_instance
contracts = 24
required_node_count = 49
road_surface_intrusions = 0
```

原有累计几何结果继续通过：

- 32 个非终端圆角 + 14 个方形开放端跳过 = 46。
- 16/16 Connector 完整，0 Uncovered。
- V15 标记/删除 4/4 个 Terminal Front Triangle，Residual = 0。
- Site 外顶点、边界穿越、外部正面积三角形均为 0。
- Phase17 退化 Primitive 和剩余反向面均为 0。

## 11. 当前 Houdini Live 现场

本日志审计时：

- Houdini `21.0.440`，RPC `18811`、MCP `3055` 正常。
- 当前 HIP 为生产 `PCG_Bike_CityRoad.hip`，`hasUnsavedChanges = false`。
- `/obj/CityRoad_DEV` 为 unlocked，`matchesCurrentDefinition = false`。
- Live CityRoadCore 为 186 个节点，七个设施节点全部存在。
- 全场扫描为 0 Error、2 个 Warning Node；两项均来自 `CITYROAD_TOPOLOGY_CLASSIFY_ROAD` 的绕序 Warning。
- Live 累计验证在公共接口阶段失败：当前实际接口哈希 `43d302…`，与提交合同记录的 Live 哈希 `2577c…` 不同。

这说明当前 Live Scene 已与提交 `20` 的 Live 审计基线发生变化。根据项目防回归门禁，本日志任务不会把磁盘 HDA 覆盖到 Live，也不会用当前 Live 更新 Definition。提交结论来自 commit diff 与独立 Fresh locked HDA；当前 Live 的后续处理必须先重新 Capture 并明确保留侧。

## 12. Unity 与渲染状态

### 12.1 当前 Unity 现场

- Unity `2022.3.62f2`。
- 未播放、未暂停、未编译、未刷新 AssetDatabase。
- 当前打开 `Assets/PCG/Scenes/PCG_City.unity`，Loaded/Valid，Root Count 6。
- Scene 为 Dirty；本日志任务不会保存。
- 最近 30 分钟 Console Error = 0。
- 最近 30 分钟存在 3 条同签名 Houdini Cook Warning：V11 节点 `No geometry generated!`。
- 五套 Prefab/Mesh/Material 均可由 AssetDatabase 找到。

这些 Warning 早于本日志写入且不是 C# 编译错误，但它们与 manifest 的“无允许 Warning”目标不一致，后续 Bake 验收不能忽略。

### 12.2 渲染管线与 Variant

- 新增自定义 Shader：0。
- 新增 RendererFeature / RenderPass：0。
- 新增 RenderTexture / Blit / MRT：0。
- 五个 Material 使用现有 URP Lit，均开启 GPU Instancing。
- 路灯材质启用 `_EMISSION`；这是 URP Lit 现有 Keyword，不是新 Shader 自定义 Keyword。
- 树叶占位材质当前为 Opaque，不使用 Alpha Clip，不产生叶片透明 Overdraw，但视觉仅为占位。

Variant 风险主要来自 URP Lit 自身和路灯 `_EMISSION`。提交没有引入新的 A×B×C 自定义 Keyword 组合，但正式美术替换时仍应避免把风动画、叶片裁剪、季节、湿润等全部堆叠到同一超级 Shader。

### 12.3 CPU 与 GPU 路径评估

| 路径 | Phase20 当前状态 | 移动端结论 |
|---|---|---|
| Houdini 设施散布 | 编辑期 CPU Cook | 合理，不进入 Runtime |
| Unity Prefab Bake | 尚无正式 Bake 结果 | 未闭环 |
| Material GPU Instancing | 已开启 | 只能降低相同批次 DrawCall |
| GameObject/Renderer Culling | 预计 CPU 参与 | 1,060 实例规模存在风险 |
| Chunk / Cluster | 未实现 | 必须补齐 |
| GPU Culling | 未实现 | 必须补齐 |
| DrawMeshInstancedIndirect | 未实现 | 大规模正式方案应采用 |
| LOD | 未实现 | 树木正式资产必须补齐 |
| Android/iOS 真机 | 未测试 | 无性能结论 |

Phase20 完成的是“编辑期规则生成 + Unity Prefab 接入契约”，不是移动端大规模实例渲染终局。

## 13. Patch 安全性

新增 patch/layout 脚本总体遵循当前门禁：

- 当前 Live `/obj/CityRoad_DEV` 是实现基线。
- 校验 Asset Type、Definition Path、HIP Path 与前置 HDA/VEX 哈希。
- 默认 `save=False`，只有显式保存才更新 Definition/HIP。
- Marker 已存在时进行幂等验证。
- VEX 替换要求精确前置块或精确 SHA，不匹配时 Fail Closed。
- 失败时恢复参数模板、Snippet、连接、新增节点或布局状态。
- 不导入并重放旧 patch，不清空 HIP，不重建 HDA。

这些脚本仍是一次性迁移和审计材料，后续功能不得按顺序重放 V1→V2→V3 来“补齐”当前环境；必须基于新的 Live Capture 与 change manifest 做增量修改。

## 14. 问题与状态变化

### 14.1 已完成：CityRoad 路灯、树木、树池点实例输出

三个独立输出已进入正式 HDA；生产参数 Fresh 结果为 230 / 415 / 415 点。

### 14.2 已完成当前生产测试图：道路表面侵入清零

V2 道路宽度净距与 V3 最终三角面包含性共同把设施道路侵入降为 0；9 对路灯和 17 棵树因表面检测被跳过。

### 14.3 已完成：Unity Bake 前置验证与 Live Preview 接入

Prefab 路径、组件组成、树权重和输出层级已纳入编辑器失败前置检查；三个设施输出可在 Live Preview 中显示。

### 14.4 已完成：Phase19 的 V15 审计材料补交

V15 patch 与 change manifest 已进入提交，干净 checkout 可以审计其迁移白名单和脚本。

### 14.5 已完成：公共参数模板持久化门禁

回归门禁现在同时保存 HDA Contents 与已验证的 ParmTemplateGroup，避免接口只留在 Live Instance。

### 14.6 未闭环：全新 HDA 实例三种树默认值退化为同一路径

生产 HIP 为 Round/Tall/Wide，但 Definition 新实例为 Round/Round/Round。需要后续提供稳定的新实例初始化策略，并增加直接验证 Definition 默认值的合同。

### 14.7 未闭环：Unity 资产生成器和专项测试未进入提交

Manifest 白名单中的 `CityRoadStreetFurniturePlaceholders.cs` 与 `CityRoadStreetFurnitureTests.cs` 仍是未跟踪文件，不能算提交“20”的交付。

### 14.8 未闭环：正式 Bake 与移动端 GPU 驱动渲染

提交没有 Generated/Road 成果、Chunk、Cluster、LOD、GPU Culling、Indirect Draw 或真机数据。当前占位 Prefab 路径不应直接成为最终 1,060 Renderer 的 Runtime 架构。

### 14.9 当前现场阻塞：Live 接口与提交基线不同

Live 累计合同在公共接口哈希阶段失败；下一次修改前必须 Capture 并比较 Live/Definition，禁止自动覆盖。

### 14.10 延续风险：Houdini/Unity Cook Warning

当前 Houdini Live 有绕序 Warning，Unity Console 有 V11 `No geometry generated!` Warning。Fresh 累计合同通过不等于这些现场 Warning 已消除。

## 15. 验证记录

### 15.1 Git

- 标题 `20` 唯一匹配提交 `df1f5e7`：通过。
- 父提交 `58f453a`：通过。
- 52 个文件变化，未修改插件、Scene、Shader 或 RendererFeature：通过。
- 当前磁盘 HDA/HIP 与 HEAD 无 tracked diff：通过。
- 设施资产生成器/专项测试是否属于提交：否。

### 15.2 Houdini

- `Ensure-HoudiniMcp.ps1`：通过。
- Houdini `21.0.440`、RPC `18811`、MCP `3055`：通过。
- Fresh Instance：locked、matches Definition、186 Core Children。
- Fresh 累计合同：`PASS`，24 个 Contract ID。
- Fresh 正式输出：4 个 Mesh/Packed 输出 + 3 个实例点输出均通过。
- Fresh Street Furniture：230 Lamps、415 Trees、415 Pits、0 Road Intrusion。
- Live 结构：186 Core Children，设施节点完整。
- Live 累计合同：失败于公共接口哈希漂移；没有修改现场。
- Live 全场诊断：0 Error、2 Warning Node。
- 本次没有保存或更新 HDA/HIP。

### 15.3 Unity

- Editor Ready：通过。
- 5 Prefab / 5 Mesh / 5 Material AssetDatabase 导入：通过。
- C# 编译状态：未编译中，最近 30 分钟 0 Error。
- `PCG_City` Loaded/Valid：通过，但 Dirty。
- Scene 提交 diff：无。
- Unity Console Warning：3 条同签名 V11 Cook Warning。
- Runtime Bake / 真机：未验证。

### 15.4 未执行项

- 未运行未提交的 `CityRoadStreetFurnitureTests.cs`。
- 未执行当前未跟踪的统一 `Invoke-PcgRegression.ps1` 入口。
- 未保存当前 Dirty Unity Scene。
- 未更新或覆盖 unlocked Houdini Live Instance。
- 未做 Mali/Adreno/Metal Profiler、RenderDoc 或 Frame Debugger 验证。

## 16. 当前状态矩阵

| 功能 | 状态 | 当前结论 |
|---|---|---|
| Street Furniture Public API | 已进入正式 HDA | 17 个核心参数/Multiparm 接口 |
| Lamp Point Output | 已通过生产测试图 | 230 Points / 115 Pairs |
| Tree Point Output | 已通过生产测试图 | 415 Points / 3 有效生产变体 |
| Tree-pit Output | 已通过 | 415，与树一一对应 |
| Road Surface Containment | 已通过生产测试图 | Intrusion = 0 |
| No/Narrow Sidewalk Fallback | 已通过 | 设施输出均为 0 |
| Determinism / Seed Response | 已通过 | 签名稳定且 Seed 可改变分布 |
| Unity Placeholder Assets | 已导入 | 5 Mesh + 5 Material + 5 Prefab |
| Prefab Configuration Guard | 已实现 | Bake 前 Fail Closed |
| Live Preview | 已接入 | 三个设施输出可见 |
| V15 Patch + Manifest | 已补交 | Phase19 审计缺口关闭 |
| Fresh Cumulative Contract | 已通过 | 24 个 Contract ID |
| New-instance Tree Defaults | **未闭环** | Round / Round / Round |
| Placeholder Generator/Test | **未进入提交** | 当前为未跟踪文件 |
| Unity Scene/Bake | 本提交未交付 | 当前 Scene Dirty |
| Chunk/LOD/GPU Culling/Indirect | 未实现 | 不满足最终移动端规模方案 |
| Live Cumulative Contract | **当前失败** | Public Interface Hash 漂移 |
| Mobile Device Validation | 未执行 | 无真机数据 |

## 17. 下一阶段建议

1. **P0：先处理 Live/Definition 基线分叉**  
   对当前 unlocked Live 与磁盘 HDA 执行新的 Capture 和接口 diff，明确保留侧；未确认前不得保存 Definition。
2. **P0：修复新实例树变体默认值**  
   将 Round/Tall/Wide 的初始化变成可重复、可验证的新实例流程，并新增“直接从 Definition 创建实例”的累计合同，不能只复制生产 HIP 参数验证。
3. **P0：补交资产生成器与专项测试**  
   审核当前未跟踪 C# 与测试是否与已提交资产一致，验证后再纳入版本管理；不要把 manifest 白名单当作交付证明。
4. **P0：完成正式 Bake 数据合同**  
   在 `Assets/PCG/Generated/Road/` 生成稳定 ID、Prefab Source、实例矩阵和 Chunk Metadata，并验证重复 Bake 不破坏艺术覆盖。
5. **P1：切换到 GPU 驱动运行时路径**  
   Bake 时按 Chunk/Cluster 聚合实例矩阵，使用 `DrawMeshInstancedIndirect`、Compute Culling 和 GPU/CPU LOD Fallback；禁止 1,060 个 GameObject 直接成为最终移动端方案。
6. **P1：优化占位/正式 Mesh**  
   关闭不需要的 Read/Write，使用 16-bit Index，补充 LOD，控制树叶 SubMesh/材质和阴影距离；正式植被 Shader 独立于路灯/树池 Shader。
7. **P1：清零现场 Warning**  
   修复 Live 绕序 Warning 与 Unity V11 空几何 Warning，使实际 Cook 满足 manifest 的 `allowed_warning_signatures = []`。
8. **P2：移动端真机闭环**  
   在 Mali/Adreno/Apple GPU 上记录 DrawCall、SetPass、实例 Buffer、Mesh/Index 内存、CPU Culling、GPU Culling、阴影和加载时间。

Phase20 已把 CityRoad 从“只有道路/人行道几何输出”扩展到“可参数化生成路灯、行道树和树池实例点，并以最终道路表面合同阻止设施侵入，再由 Unity Bake/Preview 工作流验证 Prefab”。但当前交付仍停留在编辑期点实例和占位资产层：新实例默认变体、正式 Bake、Chunk/LOD/GPU Culling/Indirect Draw、现场 Warning 与移动端真机均未闭环，后续必须先解决基线与运行时数据架构，再扩大设施规模。
