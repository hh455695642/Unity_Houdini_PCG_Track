# Phase 15 开发日志：CityRoad 单输入迁移与 V6 圆角对齐

> 文档类型：提交增量快照  
> 记录日期：2026-08-10  
> 目标提交：`b2299831bde5c3cebd5171931c14d3850a59366c`（提交信息：`15`）  
> 父提交：`2c1d99a1d32ed3282d320c112f303bc4a41df0b6`（Phase14 文档提交）  
> CityRoad 场景：`Assets/PCG/Scenes/PCG_City.unity`  
> CityRoad HDA：`Assets/PCG/HDA/City/CityRoad.hda`  
> CityRoad HIP：`HoudiniProject/PCG_Track_21.0.440/PCG_Bike_CityRoad.hip`

## 1. 日志范围与证据

本文只记录 Git 提交 `b229983` 相对父提交 `2c1d99a` 的开发增量，不重复 Phase1～Phase14 已记录的 Track、Terrain、Lake、TerrainLayer、CityRoad 拓扑 Piece、Bake 工具和移动端 Shader 基础。

Phase15 的实际开发内容由两条主线组成：

```text
输入接口：4 个 HDA 对象 Connector
    -> 0 个对象 Connector
    -> 1 个 PARAMETER / SPLINE 参数输入 unity_road_network
    -> Road Network 曲线统一携带道路 metadata

几何接口：V5 Junction 独立边界/标线推导
    -> V6 精确 Junction Mouth 合约
    -> 路面、Arm、路缘、人行道、横道与停止线共享切点/方向/半径
    -> V6.2 普通道路使用真实圆心圆弧并保护内侧偏移
```

证据等级：

- **[提交验证]**：直接读取目标提交 Git diff、C#、Python Patch、场景 YAML 和二进制资产统计。
- **[HDA 隔离验证]**：使用 Houdini `21.0.440` 的独立 `hython` 进程加载目标 HIP/HDA、创建全新 HDA 实例并 Force Cook；没有保存或覆盖任何 HIP/HDA。
- **[Unity 现场验证]**：通过 Unity MCP 读取 Editor 编译状态和 Console；通过场景 YAML 确认输入绑定、材质、Mesh 与 Live/Bake 状态。
- **[Live Scene 只读验证]**：Houdini MCP preflight 已通过，但用户当前打开的是 `PCG_Bike_CityRoad_back.hip`，不是目标 HIP，因此没有切换、修改或保存当前 Houdini 现场。
- **[待修复]**：实现已存在，但输出索引、Bake 交付或事实源同步仍未完全闭环。

本提交没有修改 `Assets/Plugins/HoudiniEngineUnity/`。输入上传兼容逻辑仍全部位于项目自有 `Assets/PCG/Editor/CityRoad/` 中，保持 Houdini Engine Unity 官方插件零侵入。

## 2. 提交概览

| 项目 | 数值 |
|---|---:|
| Commit | `b2299831bde5c3cebd5171931c14d3850a59366c` |
| Author / Date | `liyuan` / 2026-08-10 06:47:55 +08:00 |
| Changed Files | 8 |
| Added / Deleted Lines | `+50086 / -47907` |
| CityRoadSafeRebuild | `+238 / -20`，当前 941 行 |
| 新增 V6 Patch | 1 个，1,305 行 |
| CityRoad HDA | 185,760 → 213,558 bytes |
| CityRoad HIP | 1,612,465 → 1,596,770 bytes |
| Terrain HIP | 912,543 → 909,543 bytes |
| Unity Scene | 5,619,848 → 4,075,735 bytes |
| Shader / Material / RendererFeature | 0 个新增或修改 |

本提交修改：

1. `.agents/scripts/Ensure-HoudiniMcp.ps1`
2. `.gitignore`
3. `Assets/PCG/Editor/CityRoad/CityRoadSafeRebuild.cs`
4. `Assets/PCG/HDA/City/CityRoad.hda`
5. `Assets/PCG/Scenes/PCG_City.unity`
6. `HoudiniProject/PCG_Track_21.0.440/PCG_Bike_CityRoad.hip`
7. `HoudiniProject/PCG_Track_21.0.440/PCG_Bike_Terrain.hip`
8. `HoudiniProject/PCG_Track_21.0.440/scripts/tools/patch_cityroad_corner_alignment_v6.py`

## 3. CityRoad 单输入接口迁移

### 3.1 正确的输入模型

Phase14 的 HDA 通过四个对象 Connector 接收输入。Phase15 改为：

```text
HDA Object Connectors = 0
Houdini Engine Parameter Inputs = 1
Parameter Name = unity_road_network
Node Type = PARAMETER
Object Type = SPLINE
Unity Source = SplineContainer
```

必须区分两个计数：

- `HDADefinition.minNumInputs/maxNumInputs = 0/0`，表示 HDA 顶层不再暴露对象 Connector。
- Unity 侧 `HEU_HoudiniAsset.InputNodes.Count = 1`，表示存在一个由字符串资产引用参数生成的 Houdini Engine 参数输入。

因此本阶段不是“一个 HDA Connector”，而是“零 Connector + 一个 Spline 参数输入”。

### 3.2 保留的生产输入

保留：

| 项目 | 内容 |
|---|---|
| 参数 | `unity_road_network` |
| Label | `Road Network / 道路网络` |
| 内部读取节点 | `IN_ROAD_NETWORK` |
| Unity 输入对象 | `SplineContainer` |
| 生产默认来源 | `External / IN_ROAD_NETWORK` |

Road Network 曲线继续通过 primitive/point/detail attribute 携带道路语义，例如：

- `road_width`
- `lane_count`
- `road_level`
- `is_race_route`
- `allow_junction`
- 道路 ID、段 ID 和后续拓扑 metadata

`is_race_route` 语义没有删除；删除的是独立 Race Route 输入对道路网络属性的二次覆盖。后续比赛路线应作为统一道路图数据契约的一部分维护。

### 3.3 外部生产源与内部调试源

HDA 新增显式菜单参数：

```text
road_network_source
  0 = external / IN_ROAD_NETWORK
  1 = internal / INTERNAL_ROAD_NETWORK_CURVE
```

`SELECT_ROAD_NETWORK_SOURCE` 通过表达式读取该参数：

```hscript
ch("../../road_network_source")
```

用途边界：

- 新建 HDA Definition 默认 `external`，用于 Unity/Houdini Engine 生产链路。
- 目标 CityRoad HIP 的开发实例当前使用 `internal`，绑定 `/obj/CITYROAD_TEST_INPUT/OUT_TEST_ROAD_GRAPH` 做 Houdini 独立测试。
- Unity Safe Rebuild 每次重载后强制把来源恢复为 `external`，避免误用 HIP 内部测试曲线。

### 3.4 移除的输入与职责

移除参数输入：

- `unity_race_route`
- `unity_terrain_surface`
- `unity_city_boundary`

同步移除：

- `IN_RACE_ROUTE`
- `IN_TERRAIN_SURFACE`
- `IN_CITY_BOUNDARY`
- `TERRAIN_CONFORM_GROUND_ROADS`
- `enable_terrain_conform`
- `terrain_offset`
- `maximum_ground_grade`
- 独立 Race Route 的 `nearpoint(1, ...)` 属性覆盖分支
- 仅由 City Boundary 驱动的 `BLOCK_*` 可建造街区提取链
- `OUTPUT_CONTRACT_BUILDABLE_BLOCKS`
- `OUT_BUILDABLE_BLOCKS`

职责变化：

| 旧职责 | Phase15 处理 |
|---|---|
| 比赛路线 | 合并进 Road Network 的 `is_race_route` metadata |
| Terrain Surface 贴合 | 从 CityRoad HDA 移除，避免道路生成器承担地形耦合职责 |
| City Boundary / Exclusion | 从 CityRoad HDA 移除，未来应由独立城市街区/地形模块消费 |
| Buildable Blocks 输出 | 删除，不再由道路 HDA 同时承担街区生成 |

这是模块边界收敛，不代表 Terrain Conform 或 Buildable Blocks 已由其他模块重新实现；在新的独立模块交付前，这两项能力应标记为未提供。

### 3.5 必填输入校验

新增 `VALIDATE_ROAD_NETWORK_REQUIRED` Python SOP：

- 只校验 `SELECT_ROAD_NETWORK_SOURCE` 选择后的曲线是否存在。
- 不 Merge、不复制几何。
- 外部 Road Network 缺失时给出明确中英文错误。
- 普通 Unity Spline 只要求有效 `P` 和曲线拓扑；道路 metadata 可由后续默认规则补齐。

这比让空 Object Merge 继续流入下游 VEX 更易定位，也避免把缺输入误判为路口/拓扑算法错误。

## 4. Unity Safe Rebuild 单输入适配

### 4.1 双层合约校验

`CityRoadSafeRebuild` 新增两组独立断言：

```csharp
ExpectedAssetConnectorCount = 0;
ExpectedParameterInputCount = 1;
RoadNetworkParameterName = "unity_road_network";
```

Rebuild 前检查：

1. `asset.NodeInfo.inputCount == 0`。
2. `asset.InputNodes.Count == 1`。
3. 唯一输入的 `NodeType == PARAMETER`。
4. 唯一输入的 `ObjectType == SPLINE`。
5. `ParamName == unity_road_network`。
6. 输入 Entry 0 必须绑定有效 GameObject。

任一条件不满足立即 Fail Closed，不尝试改变绑定或继续 Cook。

### 4.2 Rebuild 顺序

```text
捕获 Spline 参数输入绑定
    -> 捕获 Road Markings / Crosswalk 开关
    -> RequestReload（同步）
    -> 重新获取 HEU_HoudiniAsset 引用
    -> 恢复唯一 Spline 参数输入
    -> 恢复生成开关
    -> road_network_source = external
    -> 恢复 4 个项目 Material 参数
    -> 反射调用 UploadInputNodes(session, true, true)
    -> Cook 上传后的 merge/readers
    -> 公共 RequestCook 同步验证
```

兼容桥仍只反射调用当前 Houdini Engine 版本的私有 `UploadInputNodes(HEU_SessionBase, bool, bool)`。调用前检查完整签名与返回类型；插件升级后签名不匹配会停止并输出错误，不会静默退化。

### 4.3 输入上传验证加强

Phase15 不再允许参数输入“没有连接但继续 Cook”：

- 必须能从 HAPI 参数取得有效 `connectedMergeId`。
- 立即 Cook 上传的输入 Merge 与直接上游节点。
- 只允许索引 0 映射到 `IN_ROAD_NETWORK`。
- `IN_ROAD_NETWORK` Cook 后必须包含几何。
- 输入 Reader 映射越界直接失败。

这使 Reload 成功、输入上传失败、Reader 为空和 HDA Cook 失败可以分别诊断。

### 4.4 Unity Spline 修改追踪

新增 `[InitializeOnLoad] CityRoadSplineInputUploadTracker`：

- 订阅 `UnityEngine.Splines.Spline.Changed`。
- 当被修改的 Spline 属于 CityRoad 当前绑定的 `SplineContainer` 时，重新写入 `unity_road_network` Asset Reference，使 Houdini Engine 参数进入 Dirty 状态。
- 不自动 RequestCook。
- 不使用 Editor Update 循环。
- 不进入 Player Build。

性能边界：每次 Spline 编辑事件会用 `Resources.FindObjectsOfTypeAll<HEU_HoudiniAssetRoot>()` 扫描已加载 HDA。它没有逐帧运行时成本，但大型编辑器场景中仍应观察 Spline 连续拖拽时的编辑器响应；后续可通过维护 CityRoad Root 注册表降低扫描范围。

## 5. HDA 网络清理与输出合约

### 5.1 网络规模变化

| 指标 | Phase14 | Phase15 |
|---|---:|---:|
| CityRoadCore 子节点 | 315 | 123 |
| HDA 大小 | 185,760 bytes | 213,558 bytes |

节点数量下降 192，但 HDA 体积上升约 27.8 KB，原因是 Phase15 将 V6/V6.2 的几何校验和圆角构造 VEX 写入现有 Wrangle。节点数量下降并不等于逻辑复杂度同比下降；VEX 仍需保持节点级注释和增量 Patch Guard。

主要删除内容：

- 三个旧可选输入 Reader。
- Terrain Conform 分支。
- City Boundary / Buildable Blocks 分支。
- 与四输入合约绑定的多余中间节点。

主要保留/新增内容：

- `IN_ROAD_NETWORK`
- `INTERNAL_ROAD_NETWORK_CURVE`
- `SELECT_ROAD_NETWORK_SOURCE`
- `VALIDATE_ROAD_NETWORK_REQUIRED`
- Corridor/Junction 拓扑输出
- V6 Mouth、圆角、标线和路缘/人行道共享合约

### 5.2 当前六类输出

移除 Buildable Blocks 后，当前保留六个 Output SOP：

| Output SOP | 当前 Index | 职责 |
|---|---:|---|
| `OUT_ROAD_SURFACE` | 0 | 道路表面拓扑 Piece |
| `OUT_SIDEWALK_CURB` | 1 | 路缘与人行道 Piece |
| `OUT_ROAD_MARKING_POINTS` | 2 | 标线/路线辅助点数据 |
| `OUT_ROAD_COLLISION` | 3 | 合并碰撞几何 |
| `OUT_ROAD_CENTERLINE_GRAPH` | 4 | 道路中心线图与 metadata |
| `OUT_ROAD_MARKINGS` | 6 | 可见标线 Mesh Piece |

### 5.3 输出索引仍有缺口

HDA Definition 当前声明：

```text
Inputs  = 0 to 0
Outputs = 6
```

但内部输出索引为：

```text
0, 1, 2, 3, 4, 6
```

`OUT_BUILDABLE_BLOCKS` 被删除后没有把 `OUT_ROAD_MARKINGS` 从 Index 6 重编号为 5。Phase14 的“七个 SOP / 六个声明”已收敛为六个 SOP，但仍留下索引空洞；第六个正式 HDA Connector 是否稳定暴露 Markings 不能视为已闭环。

验收条件：

1. 将 `OUT_ROAD_MARKINGS.outputidx` 调整为 5，或明确恢复七输出声明并补齐 Index 5。
2. HDA Definition 输出数、Output SOP 索引、Unity HEU Geo 输出和 Bake Validator 使用同一自动断言。
3. Unity Reload/Recook 后标线输出仍存在且材质引用稳定。

## 6. CityRoad V6/V6.2 转角与路口对齐

### 6.1 Phase14 问题回顾

Phase14 的 V5 目标 HIP Force Cook 在 `CITYROAD_EXTRACT_JUNCTION_STRIPS_V4/attribvop1` 出现 6 个 Junction Winding Error。路口 Core、辅助 Arm、路缘、人行道和横道分别推导边界，容易产生：

- 同一 Junction 不同入口使用不同有效半径。
- Mouth 左右端点方向不一致。
- Arm 独立扩宽，产生 Gap/Overlap。
- 横道按近似圆弧或局部宽度裁切，与真实路口切点偏移。
- 普通道路圆角内侧 Offset 在半径不足时翻转。

Phase15 的核心不是继续增加补丁分支，而是建立统一几何事实源。

### 6.2 Junction 统一圆角

`JUNCTION_BUILD_PATCHES` V6.1：

- 只接受真正穿过已分类 Junction 点的道路图线段，避免半径容差吸附附近道路形成伪支路。
- 沿语义道路支路累计可用长度，不再只依赖某个重采样 Edge 的长度。
- 同一 Junction 的全部入口共享一个 `junction_effective_corner_radius`。
- 每个圆角最多 4 段 / 5 点。
- 写入精确：
  - `junction_mouth_center`
  - `junction_mouth_left`
  - `junction_mouth_right`
  - `junction_mouth_outward`
  - 左右圆角切点和段数
- 输出方向、半径 Clamp、伪支路裁除和统一半径错误统计。

目标 HIP 验证：

| 指标 | 数值 |
|---|---:|
| Junction Core | 6 |
| 有效 Approach | 23 |
| Junction Corner Arc | 22 |
| 最大圆角段数 | 4 |
| 有效半径 Min / Max | 4 m / 4 m |
| 半径 Clamp | 0 |
| Orientation Error | 0 |
| Uniform Radius Error | 0 |
| Spurious Branch Prune | 1 |

### 6.3 精确 Mouth metadata

`CITYROAD_JUNCTION_APPROACH_METADATA` V6.1 为每个有效入口输出一个点，统一传递：

- Junction / Road / Segment / Approach ID
- Mouth Center
- Mouth Left / Right
- Outward
- 左右切点
- Effective Radius

目标 HIP：

```text
Expected Approaches = 23
Actual Approaches   = 23
Missing Contract    = 0
Alignment Error     = 0
Max Alignment Error = 0.0000008047 m
Contract Pass       = 1
```

最大误差约 0.8 微米，低于 1 mm 合约阈值。

### 6.4 Junction Surface Core 与 Arm

`CITYROAD_BUILD_JUNCTION_SURFACE_BOUNDARY_V5` 被升级为 V6 语义：

- Core 与辅助 Arm 直接复用同一组 Mouth Left/Right。
- Arm 保持矩形，不再独立扩宽。
- Core 和 Corridor 在入口边共享几何锚点。
- 校验 Arm 数量、Extent 和 Mouth Contract。

目标 HIP：

| 指标 | 数值 |
|---|---:|
| Surface Core | 6 |
| Surface Arm | 23 |
| Expected / Actual Approaches | 23 / 23 |
| Arm Extent Error | 0 |
| Arm Mouth Contract Error | 0 |
| Surface Extension | 6.8 m |

### 6.5 横道与停止线

`CITYROAD_BUILD_APPROACH_MARKINGS_V5` V6：

- 横道使用矩形白条，不按路口圆弧再次裁切。
- 横道和停止线锚定精确 Mouth Left/Right。
- 横向轴与 Outward 直接来自 Approach 合约。
- 标线覆盖、平行性、方向、Mouth 对齐和 Stop Line 方向均有错误计数。

目标 HIP：

| 指标 | 数值 |
|---|---:|
| Expected / Actual Approach | 23 / 23 |
| Crosswalk Primitives | 437 |
| Stop Lines | 23 |
| Parallel Error | 0 |
| Mouth Alignment Error | 0 |
| Stop Line Orientation Error | 0 |
| Coverage Error | 0 |
| Corridor Gap / Overlap | 0 / 0 |

### 6.6 普通道路真实圆心圆弧

`ROAD_ROUND_CENTERLINE_CORNERS` V6.2：

- 先剔除近共线采样点，避免圆角半径依赖采样相位。
- 使用真实圆心构建中心线圆弧。
- 中心线最小半径考虑道路半宽，保证内侧 Offset 不反转。
- 空间不足时退化为两点倒角，而不是生成反向内弧。
- 每角最多 4 段 / 5 点，严格控制移动端几何增量。

目标 HIP：

```text
Rounded Corners        = 2
True Arcs              = 2
Collinear Points Pruned= 172
Radius Clamp           = 0
Inner Chamfer Fallback = 0
Minimum Inner Radius   ≈ 4.0 m
Max Segments / Corner  = 4
```

### 6.7 路缘/人行道共享边界

- `CITYROAD_JUNCTION_CURB_SIDEWALK_V4` 直接消费 Junction 低面数圆角边界。
- Mouth Edge 保持开放，不在横道入口横跨生成路缘。
- `CITYROAD_SIDE_MATERIAL_ASSIGN` 从旧 `IN_LAB_SIDEWALK_CANDIDATE` 改接 `CURB_SIDEWALK_STATS`。
- 生产输出不再回退到独立直角街区边界。

这使 Road、Collision、Markings、Curb 和 Sidewalk 消费同一套圆角事实，而不是各自推导近似轮廓。

## 7. V6 增量 Patch 工具

新增：

`HoudiniProject/PCG_Track_21.0.440/scripts/tools/patch_cityroad_corner_alignment_v6.py`

### 7.1 Patch 范围

脚本增量更新五个 Wrangle：

1. `JUNCTION_BUILD_PATCHES`
2. `CITYROAD_JUNCTION_APPROACH_METADATA`
3. `CITYROAD_BUILD_JUNCTION_SURFACE_BOUNDARY_V5`
4. `CITYROAD_BUILD_APPROACH_MARKINGS_V5`
5. `ROAD_ROUND_CENTERLINE_CORNERS`

同时调整：

- `ROAD_POLYFRAME` 改为消费圆角后的中心线。
- `CITYROAD_JUNCTION_CURB_SIDEWALK_V4` 补充 V6 职责注释。
- `CITYROAD_SIDE_MATERIAL_ASSIGN` 改接 V4/V6 路缘人行道链。

### 7.2 安全边界

- 固定目标 `/obj/CityRoad_DEV`。
- 固定 HDA 类型 `pcgbike::CityRoad::1.0`。
- Definition 必须指向 `Assets/PCG/HDA/City/CityRoad.hda`。
- 目标节点缺失立即失败。
- VEX Signature 不匹配时拒绝盲 Patch。
- 关键连接不在允许的旧/新节点集合内时拒绝 Rewire。
- HDA 锁定时只对目标实例执行 `allowEditingOfContents()`。
- 修改放入 Houdini Undo Group。
- 默认在 HIP 同级 `backups/` 备份 HDA。
- 保存前 Force Cook RoadSurface、SidewalkCurb、RoadMarkings。
- Cook 有 Error 时不更新 Definition、不保存 HIP。

### 7.3 使用风险

`apply_live_patch()` 默认：

```python
save=True
create_backup=True
```

脚本作为主程序执行时会修改当前 Houdini Live Scene、更新 HDA Definition 并保存 HIP。它不是只读验证脚本；只有当前 HIP、节点路径、Definition 和签名全部符合预期时才能运行。

本次日志审计只做 AST 解析和隔离 HIP/HDA Cook，没有执行 `apply_live_patch()`，没有更新或保存任何用户 Houdini 现场。

## 8. Unity 场景结果

### 8.1 Scene 序列化规模

| 指标 | Phase14 | Phase15 | 变化 |
|---|---:|---:|---:|
| Scene Bytes | 5,619,848 | 4,075,735 | -27.48% |
| YAML Lines | 49,825 | 50,478 | +1.31% |
| GameObject | 218 | 239 | +21 |
| MonoBehaviour | 167 | 178 | +11 |
| Mesh | 74 | 81 | +7 |
| MeshRenderer / MeshFilter | 141 / 141 | 155 / 155 | +14 / +14 |
| MeshCollider | 1 | 1 | 不变 |
| 内联 Material | 5 | 5 | 不变 |
| EditorOnly GameObject | 208 | 229 | +21 |

场景文件字节下降但行数略增，主要因为新 Cook 的 Mesh 数据更轻，同时补齐了 Junction Sidewalk/Curb Presentation 层级。

### 8.2 拓扑 Piece 与 Renderer

```text
Corridor Presentation
  RoadSurface   = 18
  SidewalkCurb  = 18
  RoadMarkings  = 18

Junction Presentation
  RoadSurface   = 7
  SidewalkCurb  = 7
  RoadMarkings  = 7

Enabled Renderer = 75
Disabled backing Renderer = 80
```

Phase14 的 Junction 只序列化了 RoadSurface 与 RoadMarkings Presentation；Phase15 新增 7 个 Junction Sidewalk/Curb Presentation，使三个职责在 Corridor/Junction 上对称。

### 8.3 Mesh 与材质

```text
Mesh Count          = 81
Total Vertices      = 24,105
Max Vertices / Mesh = 1,788
UInt32 Mesh         = 0
MeshCollider        = 1
```

相对 Phase14：

- 总顶点从 39,148 降为 24,105，下降约 38.43%。
- 单 Mesh 最大顶点从 5,520 降为 1,788，下降约 67.61%。
- 全部 Mesh 继续低于 65,535 顶点，可保持 UInt16 Index。
- 碰撞继续收敛为单个非可见 Collision 输出。

四个项目 Material 均稳定引用，场景没有 `HEU_DEFAULT_MATERIAL_*`：

| Material | Scene GUID 引用计数 |
|---|---:|
| Asphalt | 76 |
| Sidewalk | 76 |
| Curb | 76 |
| Marking | 76 |

### 8.4 Unity 输入序列化

场景中只剩一个 HEU InputNode：

```text
_inputNodeType   = PARAMETER
_inputObjectType = SPLINE
_inputName       = unity_road_network
_paramName       = unity_road_network
Input Entry 0    = SplineContainer
```

旧 `unity_race_route`、`unity_terrain_surface`、`unity_city_boundary` 均不再出现在目标场景 YAML。

### 8.5 Live/Bake 状态未改变

- Root Count 仍为 6，包含 `CityRoad1`、`SplineContainer` 和 `CityRoad_Overrides`。
- 场景没有 `CityRoad1_Bake`。
- PrefabInstance 数量为 0。
- `Assets/PCG/Generated/Road/CityRoad/` 中没有本提交生成的正式 Bake Prefab。
- Live HDA 输出继续使用 `EditorOnly`。
- `CityRoadLivePreviewController` 的 Scene Save / Build Guard 仍会阻止未 Bake 内容作为 Player 交付。

因此 Phase15 改进的是开发期 Cook 与 Live Preview 结果，不是 Runtime Bake 完成状态。

## 9. Houdini/HDA 验证

### 9.1 HDA Definition

```text
Type          = pcgbike::CityRoad::1.0
Label         = City Road / 城市道路
Inputs        = 0 to 0
Outputs       = 6
Core Children = 123
HDA SHA-256   = F04FAC9C821E5DBE7C03166B5BD9264A6B0B347A3109BC4F69FBE352A4A7BFD2
```

独立创建的全新 HDA 实例：

- 锁定状态：是。
- `matchesCurrentDefinition()`：是。
- 默认 `road_network_source = external`。
- 旧三输入参数和旧 Reader 均不存在。
- V6/V6.2 节点存在。

### 9.2 目标 CityRoad HIP

```text
HIP = PCG_Bike_CityRoad.hip
Houdini = 21.0.440
Asset = /obj/CityRoad_DEV
Definition = Assets/PCG/HDA/City/CityRoad.hda
Core Children = 123
Source = internal test road graph
Asset Error / Warning after Force Cook = 0 / 0
HIP SHA-256 = B3064A06A1FA99EC075F44E5CF2AF35ADBC607B9689F8856012C88298E286BF9
```

隔离 Force Cook：

| Output | Points | Primitives | Vertices | Error / Warning |
|---|---:|---:|---:|---:|
| `OUT_ROAD_SURFACE` | 21 | 21 | 21 | 0 / 0 |
| `OUT_SIDEWALK_CURB` | 21 | 21 | 21 | 0 / 0 |
| `OUT_ROAD_MARKING_POINTS` | 54 | 0 | 0 | 0 / 0 |
| `OUT_ROAD_COLLISION` | 366 | 288 | 864 | 0 / 0 |
| `OUT_ROAD_CENTERLINE_GRAPH` | 18 | 4 | 18 | 0 / 0 |
| `OUT_ROAD_MARKINGS` | 21 | 21 | 21 | 0 / 0 |

Phase14 的 6 个 V5 Junction Winding Error 在目标 Phase15 HIP 中已不再出现。

目标 HIP 的 `/obj/CityRoad_DEV` 当前已解锁且 `matchesCurrentDefinition() = false`。虽然核心节点数量、关键节点和 V6 内容与新建 Definition 实例一致，但仍说明 HIP 开发实例存在 Definition 未完全匹配的现场状态；后续正式维护前应对比节点连接、参数模板、注释和隐藏内容，再决定更新 Definition 或还原实例，不应直接盲目 Match Current Definition。

### 9.3 当前 Houdini Live Scene

2026-08-10 preflight：

```text
RPC 18811 = connected
MCP 3055  = healthy
Tool Discovery = available
Current HIP = PCG_Bike_CityRoad_back.hip
Current Asset = /obj/CityRoad_DEV
```

当前 Live Scene 不是目标提交 HIP。本次没有：

- 加载或替换当前 HIP。
- 执行 `allowEditingOfContents()`。
- 修改节点、参数、连线或注释。
- 更新 HDA Definition。
- 保存 HIP/HDA。

### 9.4 Terrain HIP

`PCG_Bike_Terrain.hip` 在本提交中发生二进制变化，体积减少 3,000 bytes。独立加载结果：

- `/obj/TEST_Track` 指向正式 `Assets/PCG/HDA/Track.hda`，锁定且匹配 Definition。
- `/obj/Terrain1` 指向正式 `Assets/PCG/HDA/Terrain.hda`，解锁且不匹配 Definition。
- 顶层节点当前无 Error/Warning。

Git 无法对 HIP 二进制内容提供语义 Diff，本提交也没有配套 Terrain Patch 或 Terrain HDA 修改，因此只能确认 Terrain HIP 保存状态发生变化并能正常加载，不能把它写成新的 Terrain 功能。

## 10. 工具链与版本管理

### 10.1 Houdini 进程识别

`Ensure-HoudiniMcp.ps1` 原来只识别 `houdini.exe`，Phase15 扩展为：

- `houdini`
- `houdinifx`
- `houdinicore`
- `hindie`
- `heducation`
- `happrentice`

这使 FX、Core、Indie、Education 和 Apprentice 可执行文件也能通过 preflight 进程检测。RPC/HIP/Health/Endpoint 校验逻辑不变。

### 10.2 忽略规则

新增：

```gitignore
Assets/PCG/HDA/City/backup/
.codex_tmp/
```

收益：

- Phase14 暴露的 CityRoad HDA 备份误提交风险得到处理。
- 当前 CityRoad backup 目录约 180 份 HDA + 180 份 `.meta`、总计约 25.1 MB，不再污染普通 `git status`。
- Agent 隔离审计脚本/临时数据不会进入正式提交。

备份只是被忽略，没有被删除；仍符合历史 HDA 备份保护规则。

## 11. 性能、渲染与兼容性

### 11.1 CPU / GPU 分工

| 阶段 | CPU / Houdini / Editor | GPU / Unity | 结论 |
|---|---|---|---|
| Spline 编辑 | `Spline.Changed` 标记参数输入 Dirty | 无 | 仅编辑器事件，无 Update 循环 |
| Safe Rebuild | Reload、输入上传、Houdini Cook、合约验证 | Live Preview | 开发期成本 |
| V6 几何 | Houdini 构造圆角、Mouth、Arm、标线 | 渲染 Bake Mesh | 正确的离线生成边界 |
| Runtime | 禁止 Houdini Cook 和 Editor C# | 应只消费 Bake 资产 | 本提交仍缺正式 Bake |

### 11.2 移动端收益

- 总顶点下降约 38.43%。
- 单 Mesh 最大顶点下降约 67.61%。
- 仍无 UInt32 Index Mesh。
- 每个普通道路圆角与 Junction 圆角限制最多 4 段，避免按固定高细分生成。
- Arm、Curb、Sidewalk 和 Marking 共享边界，减少重叠几何和 Overdraw 风险。
- 场景仍使用 4 个共享 Material，未恢复默认内联材质。
- 无新增 RenderTexture、Blit、MRT、RendererFeature 或全屏 Pass。

### 11.3 Shader 与 Variant

本提交没有修改 Phase14 的三个 CityRoad Shader：

- Instancing 策略不变。
- 自定义 keyword 数量不变。
- URP Variant 风险不变。
- 纹理采样、精度、Pass 数和 Shadow 策略不变。

因此不能把本提交的 Scene 减重归因于 Shader 优化；收益来自 HDA 几何和场景序列化结果。

### 11.4 编辑器扩展风险

- Spline 编辑事件会扫描全部已加载 `HEU_HoudiniAssetRoot`，大项目需要观察编辑器 CPU 峰值。
- `UploadInputNodes` 仍依赖私有反射签名，Houdini Engine 插件升级必须重新验证。
- Patch 内 VEX 体积较大，后续应保持功能节点分离，不应继续扩成单个全能 Wrangle。
- `CityRoadCore` 节点数虽下降，但脚本/VEX 复杂度仍需自动测试约束。

## 12. 问题与状态变化

### 12.1 已解决：四输入合约复杂且易失配

- 原问题：Race Route、Terrain、Boundary 与 Road Network 同时由 CityRoad 管理，Unity Reload 需要保存/恢复四套输入。
- Phase15：统一为一个 Road Network Spline 参数输入，其他职责从 CityRoad 移除。
- 验证：HDA 0 Connector；Unity 场景只有一个 `PARAMETER/SPLINE` InputNode；Safe Rebuild 严格断言。

### 12.2 已解决：V5 Junction Winding Cook 阻塞

- Phase14：隔离 Cook 出现 6 个 Winding Error。
- Phase15：统一 Mouth/Radius/Arm 合约，目标 HIP 所有六个 Output SOP Force Cook Error/Warning 0。
- 注意：只证明当前目标测试道路图通过，仍需 T/Cross/Complex、极短支路、不同宽度和不同层级的自动化样例。

### 12.3 已解决：Junction Sidewalk Presentation 缺失

- Phase14：7 个 Junction 只有 RoadSurface 和 RoadMarkings Presentation。
- Phase15：增加 7 个 Junction SidewalkCurb Presentation，三类职责对称。

### 12.4 未解决：输出索引 5 缺失

- Definition 声明六输出。
- 内部仍使用 `0,1,2,3,4,6`。
- `OUT_ROAD_MARKINGS` 是否稳定作为第六个 Connector 暴露仍需修复与 Unity Reload 验证。

### 12.5 未解决：没有 Runtime Bake

- 没有 Bake Prefab。
- 没有活动 Bake Instance。
- 场景仍是 Live HDA/EditorOnly。
- Console 仍存在 `Live Preview or no active Bake` 的 Scene Save Error。
- Build Guard 会按设计阻止构建。

### 12.6 待复验：HIP 开发实例与 Definition 不匹配

- 新建 HDA 实例匹配 Definition。
- 目标 HIP 的可编辑 `/obj/CityRoad_DEV` 不匹配 Definition。
- 必须先做结构 Diff，再决定保存方向，避免覆盖用户现场。

### 12.7 延续风险：同名旧 HDA 副本

仓库根目录的旧 `CityRoad.hda` 在本提交中没有删除或迁移。它与正式 HDA 使用同一类型名，仍可能在被安装时抢占 Definition。Unity 和 Patch 必须继续固定使用：

`Assets/PCG/HDA/City/CityRoad.hda`

## 13. 验证记录

### 13.1 Git

- 目标提交与标题精确匹配：`b229983...` / `15`。
- 父提交：`2c1d99a...` / `Phase14`。
- 8 个文件变化。
- 未修改 Houdini Engine Unity 插件。
- V6 Python Patch AST 解析成功，1,305 行。

### 13.2 Houdini

- Preflight：通过。
- Houdini：`21.0.440`。
- RPC / MCP：connected / healthy。
- 工具发现：可用。
- 当前 Live HIP 与目标 HIP 不同，因此只做只读现场确认。
- 目标 CityRoad HIP 隔离 Force Cook：六个 Output SOP Error/Warning 0。
- V6 Approach、Arm、Mouth、Crosswalk、StopLine 校验计数均通过。
- 没有保存或修改 Live Scene、目标 HIP 或 HDA。

### 13.3 Unity

- Unity Editor：`2022.3.62f2`。
- 当前未播放、未暂停、未编译、未更新 AssetDatabase。
- Phase15 文档同步导入后，最近 5 分钟 Unity Console Error / Exception = 0 / 0。
- 目标场景 HDA Path 仍为 `Assets/PCG/HDA/City/CityRoad.hda`。
- 场景输入已收敛为一个 `unity_road_network` Spline 参数输入。
- Console Log Cache 含历史 MCP 工具错误/Exception，不代表项目 C# 编译失败。
- 当前仍有 CityRoad Live Preview 未 Bake 的 Scene Save Error，属于有效交付阻断。

### 13.4 工作区保护

写日志前已有用户工作区内容：

- `UserSettings/EditorUserSettings.asset` 修改。
- 多个美术 Texture/Shader、Terrain/Track 文档、测试脚本和 FBX 未跟踪。
- 既有未跟踪 Phase15 草稿与 `.meta`。

本文保留 Phase15 `.meta` GUID `02114d7289b3a6d42b0378e266c0c473`，只扩充 Markdown，不覆盖、移动或计入其他用户文件。

## 14. 当前状态矩阵

| 功能 | 状态 | 当前结论 |
|---|---|---|
| HDA Object Connector | 已完成迁移 | 0 个 |
| Unity Parameter/Spline Input | 已完成 | 1 个 `unity_road_network` |
| Road Network Source Switch | 已完成 | 生产默认 External；HIP 可用 Internal 调试 |
| Race Route 语义 | 已保留 | 由 Road Network `is_race_route` 提供 |
| 独立 Race Route Input | 已移除 | 不再二次覆盖 |
| Terrain Conform in CityRoad | 已移除 | 未由本提交替代实现 |
| City Boundary / Buildable Blocks | 已移除 | 应由独立模块重新实现 |
| Safe Rebuild 单输入适配 | 已完成 | 严格断言 0 Connector + 1 Parameter/Spline |
| Spline 修改脏标记 | 已完成 | Editor Event，无自动 Cook/Update Loop |
| V6 Junction 统一半径/Mouth | 已完成当前测试图 | 23 Approach，错误计数 0 |
| V6 Junction Surface Arms | 已完成当前测试图 | 6 Core / 23 Arm，无 Gap/Overlap |
| V6 Crosswalk/StopLine | 已完成当前测试图 | 437 横道 Primitive / 23 StopLine |
| V6.2 普通道路圆角 | 已完成当前测试图 | 2 True Arc，无 Clamp/Fallback |
| Junction Sidewalk/Curb Presentation | 已完成 | 7 个 Junction 已补齐 |
| HDA Force Cook | 已通过目标 HIP | 六个 SOP Error/Warning 0 |
| HDA Output 索引 | 未完成 | 声明 6，索引缺 5、Markings 仍为 6 |
| HIP/Definition 同步 | 待复验 | 目标 HIP 开发实例不匹配 Definition |
| Runtime Bake Prefab | 未完成 | 无 Bake 资产/实例 |
| Player Build | 被正确阻断 | Live HDA 不允许进入 Player |
| Shader/Variant | 无阶段变化 | 沿用 Phase14 |
| 移动端真机 Profiling | 未执行 | 仍需 Mali/Adreno/Apple GPU 数据 |

## 15. 下一阶段建议

1. 把 `OUT_ROAD_MARKINGS.outputidx` 从 6 修正为 5，并建立 Output 数量/索引/Unity Geo/Bake 的自动测试。
2. 在不覆盖用户现场的前提下，对比目标 HIP `/obj/CityRoad_DEV` 与正式 HDA Definition，明确同步方向。
3. 为单输入合约增加 Unity EditMode 测试：0 Connector、1 Parameter/Spline、输入绑定恢复、Source 强制 External、缺输入 Fail Closed。
4. 建立 Houdini 回归图集：T Junction、Cross、Complex、短支路、不同宽度、不同道路层级、接近平行支路和连续普通弯道。
5. 对每个样例断言 Mouth 误差、统一半径、Arm Extent、Gap/Overlap、Crosswalk/StopLine 方向和最大圆角段数。
6. 完成 `Cook + Validate + Update Bake` 的正式 Prefab 交付，确保 Live HDA 全部为 EditorOnly、Player 只消费 Bake 资产。
7. 为 Spline.Changed Tracker 增加 Root 注册/缓存，避免大型编辑器场景每次曲线事件扫描全部 HDA。
8. 在 Android Mali/Adreno 与 iOS Metal 上验证 75 个 Presentation Renderer 的 DrawCall、SetPass、带宽、阴影接收和 Collider 成本。
