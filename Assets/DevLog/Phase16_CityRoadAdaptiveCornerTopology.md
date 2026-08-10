# Phase 16 开发日志：CityRoad 自适应弯角布线与 HDA 事实源收敛

> 文档类型：提交增量快照  
> 记录日期：2026-08-10  
> 目标提交：`7587b616d741e79451b8525e5737a9df075ead74`（提交信息：`16`）  
> 父提交：`b2299831bde5c3cebd5171931c14d3850a59366c`（提交信息：`15`）  
> CityRoad 场景：`Assets/PCG/Scenes/PCG_City.unity`  
> CityRoad HDA：`Assets/PCG/HDA/City/CityRoad.hda`  
> CityRoad HIP：`HoudiniProject/PCG_Track_21.0.440/PCG_Bike_CityRoad.hip`

## 1. 日志范围与证据

本文只记录 Git 提交 `7587b61` 相对父提交 `b229983` 的开发增量，不重复 Phase1～Phase15 已记录的 Track、Terrain、Lake、TerrainLayer、CityRoad 单输入迁移、V6 Junction Mouth 合约、Unity Safe Rebuild、Bake 工具与移动端 Shader 基础。

Phase16 的实际开发内容集中在两条主线：

```text
普通道路圆角：V6.2 真实圆心圆弧
    -> V7 宽度驱动的内外半径
    -> 短同向弯角链合并与共享边预算
    -> 直线 / Transition / Corner 分类
    -> 弯角局部增加横向 Rail，Transition 使用 zipper 三角化
    -> Feature Toggle 可完整回退旧路面

事实源状态：HIP 中解锁且不匹配 Definition 的开发实例
    -> 锁定并匹配正式 CityRoad HDA Definition
    -> HIP 只保存测试输入和对正式 HDA 的引用
    -> 体积从 1.60 MB 收敛到 0.33 MB
```

证据等级：

- **[提交验证]**：直接读取目标提交 Git 元数据、二进制资产大小、场景 YAML 与父/目标 HDA 结构差异。
- **[HDA 隔离验证]**：使用 Houdini `21.0.440` 独立加载目标 HIP/HDA并 Force Cook；没有保存或覆盖任何 HIP/HDA。
- **[Houdini Live Scene 只读验证]**：Houdini MCP preflight 通过；当前现场正是目标 `PCG_Bike_CityRoad.hip`，只读取节点、Definition、参数、Cook 状态和输出，没有修改或保存。
- **[Unity 现场验证]**：通过 Unity MCP 刷新本日志并检查 Editor、Console；通过场景 YAML确认 HDA 路径、参数值、Renderer、Mesh 与 Live/Bake 状态。
- **[待复验]**：实现和目标测试图已经存在，但异常弯角图集、正式 Bake、Player 交付与移动端真机性能仍未闭环。

本提交没有修改 `Assets/Plugins/HoudiniEngineUnity/`，也没有新增或修改 C#、Shader、Material、RendererFeature、RenderPass 或运行时资源。

## 2. 提交概览

| 项目 | 数值 |
|---|---:|
| Commit | `7587b616d741e79451b8525e5737a9df075ead74` |
| Author / Date | `liyuan` / 2026-08-10 11:48:44 +08:00 |
| Changed Files | 3 |
| Scene Added / Deleted Lines | `+30433 / -30096` |
| CityRoad HDA | 213,558 → 224,485 bytes（+10,927） |
| CityRoad HIP | 1,596,770 → 332,659 bytes（-79.17%） |
| Unity Scene | 4,075,735 → 4,162,380 bytes（+2.13%） |
| Shader / Material / C# | 0 个新增或修改 |

本提交只修改：

1. `Assets/PCG/HDA/City/CityRoad.hda`
2. `Assets/PCG/Scenes/PCG_City.unity`
3. `HoudiniProject/PCG_Track_21.0.440/PCG_Bike_CityRoad.hip`

三个文件都属于 CityRoad 开发链路。没有配套 Python Patch 被提交，因此本日志以 HDA 结构 Diff、节点 VEX/注释、目标 HIP Cook 和场景序列化结果作为功能事实源，不能把未入库的当前工作区文件计入 Phase16。

## 3. Phase16 目标与问题背景

### 3.1 V6.2 已解决的问题

Phase15 的 V6.2 已将普通道路中心线弯角改为真实圆心圆弧，并保证内侧 Offset 不反转。目标测试图可得到真实圆弧、固定最大分段数和最小内侧半径。

但“中心线圆了”不等于“路面拓扑已经适合宽道路弯角”：

- 旧 `ROAD_BUILD_SURFACE` 仍按中心线相邻 Ring 直接连接路面边界。
- 内外弧长度差较大时，同一 Ring Budget 会让外弧面片过长、内弧面片拥挤。
- 连续短同向弯角若分别取半径，Transition 区间可能互相争抢长度。
- 单纯全局增加中心线采样会同时抬高直路、碰撞、场景序列化和移动端顶点成本。

### 3.2 Phase16 设计目标

Phase16 不采用全路段固定高细分，而是把额外拓扑限定在普通弯角附近：

```text
中心线 V7 圆角
    -> 分类每个截面：Straight / Transition / Corner
    -> Straight 保持低成本横向结构
    -> Corner 根据道路宽度和弧长最多使用 4 个半幅 Rail
    -> Transition 在不同 Rail 数之间渐进并用 zipper 三角化
    -> 输出给原有 Corridor Fuse、属性清理、碰撞与 Piece 链
```

这是一项编辑器期/Houdini Cook 几何改进。运行时仍应只渲染 Bake 后的 Unity Mesh，不允许在移动端运行 Houdini Cook。

## 4. 新增 HDA 参数接口

Phase16 在 CityRoad HDA Type Properties 中增加 3 个参数，没有删除或重命名 Phase15 的既有参数。

| 参数 | 类型 | 默认/场景值 | 职责 |
|---|---|---:|---|
| `enable_adaptive_corner_topology` | Toggle | On | 启用 V7 自适应弯角路面；关闭后完整回退旧 `ROAD_BUILD_SURFACE` |
| `road_corner_inner_radius_ratio` | Float | `0.2` | 普通二度节点弯角内半径比例，`Ri = road_width × ratio` |
| `debug_show_corner_topology` | Toggle | Off | 只给分类预览写颜色，不把 `Cd` 复制到最终路面 |

半径合约：

```text
Ri = road_width * road_corner_inner_radius_ratio
Ro = Ri + road_width
```

`Ro - Ri` 恒等于道路宽度，使弯角内外边界保持恒宽。参数默认 `0.2`，不是运行时 Shader 参数，也不产生 Shader Variant。

### 4.1 Feature Toggle 与回退

新增 `ROAD_SELECT_ADAPTIVE_CORNER_SURFACE` Switch：

- Input 0：Phase15 旧 `ROAD_BUILD_SURFACE`。
- Input 1：Phase16 `ROAD_BUILD_ADAPTIVE_CORNER_SURFACE`。
- 选择条件：`enable_adaptive_corner_topology`。

`CITYROAD_CORRIDOR_TOPO_FUSE` 与 `ROAD_STRIP_MERGE_ATTR_CLEAN` 改为消费这个 Selector，而不是直接消费旧路面。因此关闭开关时不是“近似旧逻辑”，而是直接走原有 Surface 分支，便于 A/B、回归定位和紧急回退。

### 4.2 Debug 边界

`debug_show_corner_topology` 的预览语义：

- 蓝色：Straight。
- 黄色：Transition。
- 红色：Corner。

颜色只属于分类器预览，最终 Road Surface 不继承该 `Cd`。Debug 默认关闭，不进入发布 Shader，不新增 Overlay、RenderPass、RenderTexture 或 Player 常驻调试成本。

## 5. V7 中心线圆角算法

`ROAD_ROUND_CENTERLINE_CORNERS` 在原节点上由 V6.2 升级到 V7/V7.1，VEX 长度约从 8,590 增至 22,961 字符。

节点注释明确记录：

```text
V7：Ri=W×Ratio，Ro=Ri+W；短同向角链合并；共享边预算；弧向最多4段。
V7.1：Transition 宽度受限；外弧长宽比保护允许在内侧预算上额外增加 1 段，最终仍为 2～4 段。
```

### 5.1 宽度驱动半径

Phase16 把道路宽度直接纳入普通弯角半径：

- 内侧半径 `Ri` 由道路宽度和比例控制。
- 外侧半径 `Ro` 由 `Ri + road_width` 推导。
- 相比只按中心线半径构造，可让宽路与窄路获得相对一致的横向拓扑密度。
- 半径仍受可用直线长度和相邻弯角 Transition 预算约束，不能无限扩大。

### 5.2 短同向弯角链合并

连续的短同向转角不再完全按互相独立的圆角处理。V7 会识别同向短角链并共享可用边预算，降低两个相邻 Transition 互相侵占造成的折返、短边和不连续 Rail 风险。

目标 HIP 当前统计：

| 指标 | 数值 |
|---|---:|
| Rounded Corners | 1 |
| True Arcs | 1 |
| Same-turn Chain Merges | 1 |
| Shared Budget Clamp | 0 |
| Radius Clamp | 0 |
| Chamfer Fallback | 0 |
| Collinear Points Pruned | 172 |
| Minimum Inner Radius | 4.0 m |
| Max Segments / Corner | 4 |

### 5.3 外弧长宽比保护

V7.1 允许外弧在必要时比内侧预算多 1 个弧向段，但总段数仍限制为 2～4。目的不是追求高模，而是避免外弧单个面片过长、宽高比过差。

该策略保持了明确上限：不会根据曲率无限细分，也没有把普通弯角改为全局高密度 Mesh。

## 6. 自适应弯角拓扑节点链

CityRoadCore 直接子节点由 123 增至 126，只新增 3 个职责明确的节点。

### 6.1 `ROAD_CLASSIFY_CORNER_TOPOLOGY`

类型：Attribute Wrangle  
输入：`ROAD_POLYFRAME`  
职责：只在中心线写入弯角拓扑 metadata，不直接生成最终路面。

分类规则：

| 分类 | Rail 预算 | 说明 |
|---|---:|---|
| Straight | 每半幅 1 | 保持低成本横向结构 |
| Transition | 渐进变化 | 连接 Straight 与 Corner 的不同 Rail 数 |
| Corner | 每半幅最多 4 | 只在弯角局部提高横向拓扑密度 |

分类 metadata 通过 `CITYROAD_JUNCTION_ATTR_ALIGN` 补齐到 Junction 合并链，新增/对齐字段包括 `road_corner_topology_class`、`road_corner_half_*` 等。这样 Junction 与 Corridor Merge 时不会因某一侧缺少新属性而丢失合约。

### 6.2 `ROAD_BUILD_ADAPTIVE_CORNER_SURFACE`

类型：Attribute Wrangle  
输入 0：弯角分类中心线  
输入 1：`CITYROAD_BUILD_JUNCTION_SURFACE_BOUNDARY_V5`  
职责：构建局部自适应 Road Surface。

生成策略：

- Straight 维持低横向分段。
- Corner 在内外弧之间加入宽度驱动的局部 Rail。
- Transition 根据两端 Rail 数差异进行 zipper 三角化。
- Junction Mouth 继续复用 Phase15 的统一边界合约，不在本节点重新推导一套近似入口。
- 目标是用局部面数换取弯角面片形状，而不是提高整张道路网采样密度。

### 6.3 `ROAD_SELECT_ADAPTIVE_CORNER_SURFACE`

类型：Switch  
职责：在旧 Surface 与自适应 Surface 之间做 A/B 选择。

这是明确的功能开关和扩展点。后续若增加不同等级的道路弯角策略，应继续拆成独立 Surface 分支并由小型 Selector 选择，不应把所有道路、路口、路缘和标线逻辑堆进一个全能 Wrangle。

## 7. 路缘、人行道与面朝向校验

Phase16 同时加强了 CityRoad V4 路缘/人行道链的面朝向 metadata，目标是把“生成时知道的期望朝向”传到线性校验阶段。

### 7.1 生成阶段写入期望方向

以下节点的 VEX/注释发生变化：

- `CITYROAD_CORRIDOR_CURB_SIDEWALK_V4`
- `CITYROAD_JUNCTION_CURB_SIDEWALK_V4`

它们在生成顶面和竖直侧面时记录期望法线/面朝向，不再依赖后续节点对每个 Primitive 重新做最近点查询。

### 7.2 `CURB_SIDEWALK_ORIENT_METADATA`

该节点从只处理顶部朝向扩展为区分：

- Top Surface。
- Vertical Side。

校验使用生成阶段写入的 `city_desired_normal`。`CURB_SIDEWALK_REVERSE_MARKED_TOPS` 的反转组从单一 `reverse_top` 扩展为：

```text
reverse_top reverse_vertical
```

### 7.3 清理与强校验

`CURB_SIDEWALK_CLEAR_ORIENT_HELPER` 不再只清理少量临时属性，而是：

1. 检查反转后是否仍有竖直侧面方向错误。
2. 残留数量大于 0 时主动报错，阻止错误几何静默流入输出。
3. 校验通过后清理期望方向等辅助属性。

目标节点 Force Cook 统计：

| 节点 | Points | Primitives | Vertices | Error / Warning |
|---|---:|---:|---:|---:|
| `CURB_SIDEWALK_ORIENT_METADATA` | 953 | 1,248 | 3,744 | 0 / 0 |
| `CURB_SIDEWALK_CLEAR_ORIENT_HELPER` | 953 | 1,248 | 3,744 | 0 / 0 |

这部分是 Houdini Cook 线性 Primitive 校验，不是 Unity 运行时逐面检查。它避免使用 `xyzdist`/near 查询作为每 Primitive 的主要方向判定，适合继续留在离线 Bake 链路。

## 8. HDA Definition 与 HIP 事实源收敛

### 8.1 Phase15 状态

Phase15 目标 HIP 的 `/obj/CityRoad_DEV`：

- 已解锁。
- `matchesCurrentDefinition() = false`。
- HIP 体积为 1,596,770 bytes。

这意味着 HIP 内保存了可编辑 HDA Contents 副本。即使关键节点看起来与正式 HDA 一致，仍存在 HIP 现场与 Definition 双事实源风险。

### 8.2 Phase16 状态

Phase16 目标 HIP 与当前 Live Scene 均确认：

```text
Asset                 = /obj/CityRoad_DEV
Type                  = pcgbike::CityRoad::1.0
Definition            = Assets/PCG/HDA/City/CityRoad.hda
Asset Locked          = true
Matches Definition    = true
Definition Inputs     = 0 to 0
Definition Outputs    = 6
CityRoadCore Children = 126
```

HIP 体积从 1,596,770 bytes 降至 332,659 bytes，下降 79.17%。结合锁定且匹配 Definition 的状态，可以确认主要变化是移除 HIP 内嵌的可编辑 HDA 内容副本，让正式 `Assets/PCG/HDA/City/CityRoad.hda` 重新成为网络事实源，而不是删除 CityRoad 功能。

### 8.3 文件指纹

| 文件 | Phase15 SHA-256 | Phase16 SHA-256 |
|---|---|---|
| CityRoad HDA | `F04FAC9C821E5DBE7C03166B5BD9264A6B0B347A3109BC4F69FBE352A4A7BFD2` | `D86746F78E1D16F58EF548368783490EBAF16376BC7E3A09FF892210084025DA` |
| CityRoad HIP | `B3064A06A1FA99EC075F44E5CF2AF35ADBC607B9689F8856012C88298E286BF9` | `7CE3DAED1F1B4707E03F6F7E4C355AE0770F9A95C2809438F8AE1092FC3698A5` |

后续修改仍必须 Live Scene 优先：先读取当前 HIP、目标实例、Definition、参数和 Cook 状态；只有确需修改时才对目标实例 `allowEditingOfContents()`，完成增量 Patch、Force Cook、更新 Definition 后再恢复锁定/匹配状态。禁止用全量 Builder 覆盖该 HDA。

## 9. 目标 HIP/HDA Cook 验证

### 9.1 当前开发参数

目标 HIP 的 `/obj/CityRoad_DEV`：

```text
road_network_source              = internal
unity_road_network               = /obj/CITYROAD_TEST_INPUT/OUT_TEST_ROAD_GRAPH
enable_adaptive_corner_topology  = 1
road_corner_inner_radius_ratio   = 0.2
debug_show_corner_topology       = 0
```

这里的 Internal 是 Houdini 开发测试现场；HDA Definition 的生产接口仍为 Phase15 的零 Object Connector + 一个 `unity_road_network` Parameter/Spline 输入。Unity Safe Rebuild 应继续把生产场景恢复为 External 数据源。

### 9.2 新旧 Surface A/B

目标测试道路图的中间结果：

| Surface | Points | Primitives | Vertices |
|---|---:|---:|---:|
| Phase15 旧 `ROAD_BUILD_SURFACE` | 192 | 48 | 192 |
| Phase16 自适应 Surface | 428 | 132 | 428 |
| Selector 当前输出 | 428 | 132 | 428 |

本测试输入上，自适应分支增加 236 Points 和 84 Primitives。该增量是为弯角局部布线质量付出的编辑器生成/运行时 Mesh 成本，不能仅凭一个测试图判断最终收益。必须在正式 Bake 后用弯角变形、顶点缓存、Overdraw、DrawCall 和真机 GPU 时间共同验收。

### 9.3 六类输出

| Output SOP | Index | Points | Primitives | Vertices | Error / Warning |
|---|---:|---:|---:|---:|---:|
| `OUT_ROAD_SURFACE` | 0 | 21 | 21 | 21 | 0 / 0 |
| `OUT_SIDEWALK_CURB` | 1 | 21 | 21 | 21 | 0 / 0 |
| `OUT_ROAD_MARKING_POINTS` | 2 | 51 | 0 | 0 | 0 / 0 |
| `OUT_ROAD_COLLISION` | 3 | 397 | 352 | 1,056 | 0 / 0 |
| `OUT_ROAD_CENTERLINE_GRAPH` | 4 | 17 | 4 | 17 | 0 / 0 |
| `OUT_ROAD_MARKINGS` | 6 | 21 | 21 | 21 | 0 / 0 |

RoadSurface、SidewalkCurb 与 Markings 输出为 Packed Geometry，因此 SOP 层显示 21 个 packed primitive，而不是 Presentation Mesh 内部总顶点数。

相对 Phase15：

- Marking Points：54 → 51。
- Collision：366/288/864 → 397/352/1,056。
- Centerline：18/4/18 → 17/4/17。
- Packed Piece 数仍为 21。
- Junction Core / Arm 仍为 6 / 23。
- `junction_trim_miss_count = 0`。
- `cityroad_topology_contract_version` 仍为 `4.0.0`，本提交没有升级外部拓扑合约版本。

### 9.4 非阻断 Warning

目标 HIP 全部正式 Output SOP Force Cook 均为 0 Error / 0 Warning；Root 也没有 Error/Warning。但遍历全部中间节点可见 6 个非阻断 Warning：

| 节点 | Warning 类型 |
|---|---|
| `CITYROAD_LOCAL_ROAD_MERGE` | Merge 输入属性不一致 |
| `CITYROAD_MARKING_HELPERS_MERGE` | Approach/Junction Mouth 辅助属性不一致 |
| `CITYROAD_MARKING_FIX_REVERSED_QUADS` | 可选组 `cityroad_marking_source_reversed` 无效/不存在 |
| `CITYROAD_ROAD_FIX_REVERSED_FACES` | 可选组 `cityroad_road_final_reversed` 无效/不存在 |
| `CITYROAD_CURB_SIDEWALK_MERGE_V4` | `road_corner_*` 属性在部分输入上不一致 |
| `CITYROAD_ORIENT_JUNCTION_TOP_V4` | 可选组 `v4_reverse_top_faces` 无效/不存在 |

这些 Warning 当前没有传播为正式输出错误，但不应长期忽略。应在 Merge 前统一初始化属性，并让可选 Group 节点在组为空时显式绕过，避免未来输入变化时由 Warning 演化为属性默认值错误。

### 9.5 输出索引缺口仍未解决

Phase15 已记录的输出索引问题继续存在：

```text
Definition Outputs = 6
Output SOP Indexes  = 0, 1, 2, 3, 4, 6
```

Phase16 没有把 `OUT_ROAD_MARKINGS` 从 6 改为 5。Unity Reload、HEU Geo 输出与 Bake Validator 是否始终把 Markings 当作第六个正式输出，仍不能视为已闭环。

## 10. Unity 场景结果

### 10.1 Scene 序列化规模

| 指标 | Phase15 | Phase16 | 变化 |
|---|---:|---:|---:|
| Scene Bytes | 4,075,735 | 4,162,380 | +2.13% |
| YAML Lines | 50,477 | 50,814 | +337 |
| GameObject / Transform | 239 / 239 | 239 / 239 | 不变 |
| Mesh | 81 | 81 | 不变 |
| MeshRenderer / MeshFilter | 155 / 155 | 155 / 155 | 不变 |
| MeshCollider | 1 | 1 | 不变 |
| Total Vertices | 24,105 | 24,895 | +790（+3.28%） |
| Max Vertices / Mesh | 1,788 | 1,788 | 不变 |
| EditorOnly GameObject | 229 | 229 | 不变 |
| PrefabInstance | 0 | 0 | 不变 |

场景没有增加新的 Presentation GameObject 或 Renderer；文件增长来自新增 HDA 参数序列化与重新 Cook 后的 Mesh 数据。

### 10.2 Renderer 与阴影策略

```text
Enabled Presentation Renderer = 75
Disabled backing Renderer      = 80
Cast Shadows Off               = 150
Cast Shadows On                = 5
Receive Shadows On             = 155
```

这些计数与 Phase15 完全一致。Phase16 没有改变移动端阴影策略、材质职责拆分、Renderer 数量或 Live/Presentation 层级。

### 10.3 HDA 参数与引用

场景 YAML 已序列化：

```text
_assetPath = Assets/PCG/HDA/City/CityRoad.hda
unity_road_network = Spline Parameter Input
road_corner_inner_radius_ratio = 0.2
enable_adaptive_corner_topology = 1
debug_show_corner_topology = 0
```

正式 HDA GUID 引用仍为 `67d84be2a5065e14493d6b0d83e29db8`。输入接口仍是 Phase15 的单 `PARAMETER / SPLINE` 模型，没有恢复旧 Race Route、Terrain Surface 或 City Boundary 输入。

### 10.4 Live/Bake 状态未改变

- Root Count 仍为 6。
- 场景包含 `CityRoad1`、`SplineContainer` 和 `CityRoad_Overrides`。
- 没有 `CityRoad1_Bake`。
- PrefabInstance 数量为 0。
- Live HDA 输出仍是 `EditorOnly`。
- 本提交没有新增正式 Bake Prefab 或 Player Runtime 数据。

因此 Phase16 交付的是开发期 HDA、HIP 与 Live Scene 结果，不是可直接进入移动端 Player 的 Bake 完成状态。Scene Save / Build Guard 仍应阻止未 Bake 内容进入正式构建。

## 11. 性能、渲染与兼容性

### 11.1 CPU / GPU 分工

| 阶段 | CPU / Houdini / Editor | GPU / Unity | 结论 |
|---|---|---|---|
| V7 圆角与分类 | VEX 计算半径、角链、共享预算和分类 metadata | 无 | 开发期 Cook 成本 |
| 自适应 Surface | Houdini 局部建 Rail 与 zipper 面 | Live Preview | 只在弯角增量，不全局高细分 |
| 朝向校验 | Houdini 线性遍历 Primitive | 无 | Bake 前 Fail Closed，不进 Runtime |
| Runtime | 禁止 Houdini Cook | 渲染 Bake Mesh | 本提交尚未完成正式 Bake |

### 11.2 移动端收益与成本

收益：

- 额外横向细分只发生在 Corner/Transition，直路保持低成本。
- 弧向段数固定在 2～4，避免按曲率无限增加。
- 通过生成期方向 metadata 做线性校验，避免昂贵的几何最近点搜索。
- 没有新增 GameObject、Renderer、Material、Pass 或 DrawCall 来源。
- 最大单 Mesh 顶点仍为 1,788，继续保持 UInt16 Index 安全余量。

成本：

- 目标场景总顶点增加 790（+3.28%）。
- 目标测试图自适应中间 Surface 相对旧分支增加 84 Primitives。
- Collision 从 288 增至 352 Primitives，移动端物理成本需要在正式 Bake Collider 上验证。
- HDA VEX 复杂度显著增加，Houdini Cook 时间和维护成本尚无自动化基线。

### 11.3 RenderPass / 带宽

本提交没有 RendererFeature 或 RenderPass：

- `RenderPassEvent`：不适用。
- 新增 RenderTexture：0。
- Blit / MRT / 全屏 Pass：0。
- Tile-Based GPU 中途 Flush 风险：无阶段新增。

场景顶点增加主要影响顶点读取、缓存和内存，不会直接增加全屏带宽；但必须结合 Bake 后 Mesh 拆分和实际 DrawCall 评估。

### 11.4 Shader、Instancing 与 Variant

本提交没有修改 Phase14 的 CityRoad Shader：

- `#pragma multi_compile_instancing` 支持方式不变。
- 自定义 keyword 数量不变。
- Variant 风险不变。
- half/float 精度、纹理采样数量、Opaque/Depth/Shadow Pass 和 Overdraw 风险不变。

三个 HDA Toggle/Float 都是编辑器生成参数，不是 Shader keyword，不会形成 A×B×C Variant 组合。

### 11.5 兼容性

- 不使用 Geometry Shader。
- 不新增 Compute Shader、平台特定 API 或移动端不通用特性。
- 输出仍为普通 Unity Mesh/Packed Piece，理论上兼容 Android Mali/Adreno 与 iOS Metal。
- 真机顶点吞吐、Collider、内存和 Bake Mesh 带宽尚未测试，不能仅凭编辑器场景统计给出最终兼容/性能结论。

## 12. 问题与状态变化

### 12.1 已解决：宽道路弯角缺少局部横向布线

- 原问题：中心线圆角已存在，但旧 Surface 仍只按统一 Ring 连接，外弧面片可能过长。
- Phase16：新增 Straight/Transition/Corner 分类、弯角局部 Rail 与 zipper 三角化。
- 验证：Selector 当前输出自适应 Surface，正式 RoadSurface Cook 无 Error/Warning。

### 12.2 已解决：连续短同向弯角争抢 Transition 长度

- Phase16：V7 合并短同向角链并使用共享边预算。
- 当前测试：`Same-turn Chain Merges = 1`，`Shared Budget Clamp = 0`。
- 边界：仍需更多连续 S 弯、极短边和宽度突变样例。

### 12.3 已解决：HIP 开发实例与 Definition 不匹配

- Phase15：目标 HIP 解锁且不匹配 Definition。
- Phase16：目标与 Live Scene 均锁定、匹配正式 HDA Definition。
- 结果：HIP 缩小 79.17%，正式 HDA 恢复为网络事实源。

### 12.4 已加强：路缘/人行道竖直侧面朝向

- 生成时记录期望朝向。
- 顶部与竖直侧面分组修复。
- 清理节点在残留方向错误时主动报错。
- 当前目标测试节点 0 Error / 0 Warning。

### 12.5 未解决：中间节点 Warning

- 6 个节点仍报告属性不一致或可选组不存在。
- 当前未传播到六个正式输出。
- 后续应统一属性初始化并对空组显式 Bypass。

### 12.6 未解决：输出索引 5 缺失

- Definition 声明 6 输出。
- 内部索引仍为 `0,1,2,3,4,6`。
- Markings Connector/Unity Geo/Bake 的稳定性仍需修复和自动断言。

### 12.7 未解决：没有 Runtime Bake

- 没有正式 Bake Prefab。
- 没有活动 Bake Instance。
- 场景仍是 Live HDA/EditorOnly。
- Player 构建仍应被 Guard 阻止。

### 12.8 延续风险：同名旧 HDA 副本

仓库根目录旧 `CityRoad.hda` 不在本提交变化中。若被额外安装，仍可能与正式 HDA 使用相同类型名并抢占 Definition。Unity、HIP 与任何 Patch 必须固定使用：

`Assets/PCG/HDA/City/CityRoad.hda`

## 13. 验证记录

### 13.1 Git

- 目标提交与标题精确匹配：`7587b616...` / `16`。
- 父提交：`b2299831...` / `15`。
- 3 个文件变化，全部属于 CityRoad。
- 当前目标三文件 Blob 与提交 `7587b616` 一致。
- 未修改 Houdini Engine Unity 插件。

### 13.2 Houdini

- Preflight：通过。
- Houdini：`21.0.440`。
- RPC `18811`：connected。
- MCP `3055`：healthy。
- MCP 工具发现：可用。
- 当前 Live HIP：`PCG_Bike_CityRoad.hip`。
- 当前 Asset：`/obj/CityRoad_DEV`。
- Definition：正式 `Assets/PCG/HDA/City/CityRoad.hda`。
- Asset 锁定且匹配 Definition。
- 本次只读验证没有执行 `allowEditingOfContents()`，没有更新节点、参数、Definition 或保存 HIP/HDA。
- 目标 HIP 隔离 Force Cook：六个 Output SOP 均 0 Error / 0 Warning。
- 全网扫描：0 个 Error 节点，6 个非阻断 Warning 节点。

### 13.3 Unity

- Unity Editor：`2022.3.62f2`。
- 目标场景 HDA Path 仍为 `Assets/PCG/HDA/City/CityRoad.hda`。
- 单 `unity_road_network` Parameter/Spline 输入仍存在。
- Phase16 三个 HDA 参数已序列化，值为 `0.2 / On / Off`。
- Scene Renderer、阴影、Material Cache 和 EditorOnly 结构无阶段变化。
- Phase16 文档已通过 `AssetDatabase.Refresh(ForceSynchronousImport)` 导入。
- 刷新后 Editor 未播放、未暂停、未编译且未更新 AssetDatabase。
- 刷新后最近 10 分钟 Unity Console Error / Exception / Warning 均为 0。

### 13.4 工作区保护

写日志前已存在多项用户未跟踪内容，包括：

- 美术 Texture/Shader。
- `Assets/PCG/Generated/` 及其内容。
- Track/Terrain 文档与 Word 临时文件。
- 测试脚本、FBX 和既有模型文件。

这些内容不属于目标提交 `16`，本文没有移动、覆盖或计入 Phase16 开发成果。临时二进制审计文件在日志生成后清理，不进入版本管理。

## 14. 当前状态矩阵

| 功能 | 状态 | 当前结论 |
|---|---|---|
| V7 宽度驱动圆角 | 已完成当前测试图 | `Ri=W×0.2`，`Ro=Ri+W` |
| 短同向角链合并 | 已完成当前测试图 | 1 次 Merge，无 Shared Budget Clamp |
| 弧向 Segment Guard | 已完成 | 最终限制 2～4 段 |
| Straight/Transition/Corner 分类 | 已完成 | 中心线 metadata 已生成 |
| 自适应 Corner Rail | 已完成当前测试图 | 弯角局部增加横向布线 |
| Transition Zipper | 已完成当前测试图 | 连接不同 Rail 数 |
| Legacy Surface A/B | 已完成 | Toggle 关闭可完整回退 |
| Debug 分类预览 | 已完成 | 默认关闭，不污染最终 `Cd` |
| 路缘/人行道朝向校验 | 已加强 | 顶部+竖直侧面，残留错误 Fail Closed |
| HIP/Definition 同步 | 已完成 | 锁定且匹配正式 HDA |
| HDA Force Cook | 已通过目标 HIP | 六个正式输出 0 Error/Warning |
| 中间节点 Warning | 待修复 | 6 个属性/空组 Warning |
| HDA Output 索引 | 未完成 | 声明 6，索引缺 5、Markings 仍为 6 |
| Unity Scene ReCook | 已完成 Live 结果 | 顶点 +3.28%，Renderer 数不变 |
| Runtime Bake Prefab | 未完成 | 无 Bake 资产/实例 |
| Shader/Variant | 无阶段变化 | 无新增 keyword/Pass/RT |
| 移动端真机 Profiling | 未执行 | 仍需 Mali/Adreno/Apple GPU 数据 |

## 15. 下一阶段建议

1. 建立普通道路弯角自动化图集：单弯、短同向角链、连续 S 弯、宽度突变、极短边、接近共线、闭环和多层道路。
2. 为 V7 断言 `Ri/Ro`、Rail 数、Transition 长度、Segment 2～4、共享预算、面朝向、非流形边和退化三角形。
3. 对 Legacy/Adaptive 两条分支做 A/B：弯角面片长宽比、法线连续性、UV、Collision、Cook 时间、顶点数和场景体积。
4. 在 Merge 前补齐 `road_corner_*`、Approach/Mouth 辅助属性，并让可选 Reverse Group 在空组时显式 Bypass，消除 6 个中间 Warning。
5. 把 `OUT_ROAD_MARKINGS.outputidx` 从 6 修正为 5，并建立 Definition Output、SOP Index、Unity HEU Geo 与 Bake Validator 的统一断言。
6. 完成 `Cook + Validate + Update Bake` 正式 Prefab 交付；Player 只消费 Bake Mesh/Collider/Material/Metadata。
7. 在 Bake 后重新评估 Collision 由 288 增至 352 Primitive 的移动端 PhysX 成本，必要时使用独立低模 Collider，而不是直接复用渲染拓扑。
8. 在 Android Mali/Adreno 与 iOS Metal 上记录 DrawCall、SetPass、顶点吞吐、带宽、内存、Collider 和帧时间，确认 +3.28% 顶点增量是否换来足够的弯角视觉/拓扑收益。
