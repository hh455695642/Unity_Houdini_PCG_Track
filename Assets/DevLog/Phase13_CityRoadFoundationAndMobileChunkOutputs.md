# Phase 13 开发日志：CityRoad 基础、路口系统与移动端分块输出

> 文档类型：提交增量快照  
> 记录日期：2026-07-31  
> 目标提交：`10d3ab1529e9bcc47878b55fcdd4e1ebe93c3489`（提交信息：`13`）  
> 父提交：`6538b53d23135bb7c5ba3a28a771b0f3ba9b613a`（Phase12 文档提交）  
> CityRoad 场景：`Assets/PCG/Scenes/PCG_City.unity`  
> CityRoad HDA：`Assets/PCG/HDA/City/CityRoad.hda`  
> CityRoad HIP：`HoudiniProject/PCG_Track_21.0.440/PCG_Bike_CityRoad.hip`

## 1. 日志范围与证据

本文只记录 Git 提交 `10d3ab1` 相对父提交 `6538b53` 的开发增量，不重复 Phase 1～Phase 12 已记录的 Track、Terrain、Lake、道路 Shader 和 Terrain 材质层功能。

本阶段新增的是一套独立 `CityRoad` 城市道路 HDA 与测试场景，主链路为：

```text
Unity 道路网络 / 比赛路线 / Terrain / 城市边界
    -> CityRoad 输入与道路图清洗
    -> 路段、路口与道路壳体
    -> 人行道 / 路缘石 / 碰撞 / 中心线图
    -> 静态实体道路标线
    -> 128 m XZ 网格裁切与稳定 Chunk 命名
    -> Houdini Engine Unity Cook
    -> PCG_City 场景中的 Mesh / Collider / HEU 序列化结果
```

证据等级：

- **[提交验证]**：直接读取目标提交 Git diff、HDA 类型定义、HIP、三个增量 Patch 脚本、调试 BGeo 和 Unity 场景 YAML。
- **[隔离验证]**：在独立 `hython` 进程中加载目标提交 HIP、Force Cook 并读取节点、输出几何与 metadata；没有保存 HIP/HDA。
- **[现场验证]**：通过 Unity MCP 读取当前 Editor、已打开场景与 Console；当前工作区状态不反向计入提交 `13`。
- **[待修复]**：实现已存在，但提交依赖、输出合约、Unity Bake 快照或自动验证尚未闭环。

本提交没有修改 `Assets/Plugins/HoudiniEngineUnity/`，继续符合 Houdini Engine Unity 插件零侵入约束。

## 2. 提交概览

| 项目 | 数值 |
|---|---:|
| Commit | `10d3ab1` |
| Author / Date | `liyuan` / 2026-07-31 14:35:25 +08:00 |
| Changed Files | 9 |
| Added / Deleted Lines | `+426333 / -0` |
| CityRoad HDA | 166,375 bytes |
| CityRoad HIP | 1,469,228 bytes |
| Unity 场景 | 25,843,508 bytes / 420,086 行 |
| 增量 Patch 脚本 | 3 个 / 6,232 行 |
| 调试几何 | 1 个 `.bgeo.sc` |
| 新增 C# / Shader / Render Feature | 0 |

提交文件按职责分为四组：

1. **CityRoad HDA 与目录**
   - `Assets/PCG/HDA/City.meta`
   - `Assets/PCG/HDA/City/CityRoad.hda`

2. **Houdini 开发现场**
   - `HoudiniProject/PCG_Track_21.0.440/PCG_Bike_CityRoad.hip`

3. **增量维护脚本**
   - `patch_cityroad_tutorial_v2.py`
   - `patch_cityroad_crossroad_v3.py`
   - `patch_cityroad_shading_markings_chunks.py`

4. **Unity Cook 结果与输入调试数据**
   - `Assets/PCG/Scenes/PCG_City.unity`
   - `Assets/PCG/Scenes/PCG_City.unity.meta`
   - `temp/CityRoad_UnityInput_Debug.bgeo.sc`

这是一个体量较大的首版 CityRoad 子系统提交。426,333 行增量中，420,086 行来自 Unity 场景序列化，而不是运行时代码。

## 3. CityRoad HDA 总体结构

### 3.1 类型与模块边界

HDA 类型：

```text
pcgbike::CityRoad::1.0
Label: City Road / 城市道路
Inputs: 0..4
Declared Outputs: 6
```

目标 HIP 中的开发实例：

```text
/obj/CityRoad_DEV
    -> /obj/CityRoad_DEV/CityRoadCore
```

隔离读取结果：

- `CityRoadCore` 直属子节点：286。
- HDA 全部子节点：327。
- Network Box：14。
- HDA 根节点 Cook Error / Warning：0 / 0。
- 实例处于 Unlocked 状态，且 `matchesCurrentDefinition = false`。
- Definition 指向 `Assets/PCG/HDA/City/CityRoad.hda`。

主要 Network Box：

| 模块 | 职责 |
|---|---|
| Input / Contract | 四类 Unity 输入、输入校验与基础 metadata |
| Graph Preparation | 端点吸附、短段过滤、节点/边图准备 |
| Road Segments | 路段采样、宽度/车道与道路截面 |
| Road Union / Shell | 道路与路口合并、道路壳体和拓扑整理 |
| Sidewalk / Curb | 人行道、路缘石及其校验 |
| Marking Points | 标线点数据接口 |
| Collision | 道路碰撞输出 |
| Block Extraction | 可建设街区提取 |
| Output Contract | 输出职责、版本与统计 metadata |
| Tutorial V2 | 道路重叠裁剪、固定宽度与人行道流程 |
| Tutorial V3 | 十字/T 字路口区域、圆角与 Unity 面序 |
| Shading Contract | 道路 UV、城市局部 UV 与磨损 Mask |
| Static Marking Mesh | 中线、车道线、边线、斑马线和停止线 |
| Mobile Chunk Output | XZ 网格裁切、分块统计和 Pack |

这些模块仍位于一个 CityRoad HDA 内，但职责已经用 Network Box 和命名节点拆分。后续扩展应继续以独立模块和独立输出维护，避免把建筑、植被、交通设施继续堆入该 HDA。

### 3.2 Unity 输入

公共输入页提供四类输入：

| 参数 | 输入语义 |
|---|---|
| `unity_road_network` | 城市道路网络 |
| `unity_race_route` | 比赛路线 |
| `unity_terrain_surface` | Unity Terrain / 地表 |
| `unity_city_boundary` | 城市生成边界 |

本阶段把道路网络作为主事实输入，Race Route、Terrain 和 Boundary 为后续道路分级、贴地、城市范围裁切和比赛路线语义预留接口。所有 Houdini Cook 均属于编辑器期流程；移动端 Player 不应依赖 HDA 或 Houdini Engine Runtime Cook。

### 3.3 公共参数

City Road 页签的主要参数如下：

| 分组 | 参数 | 默认值 |
|---|---|---:|
| Graph | Endpoint Snap Tolerance | 0.25 m |
| Graph | Intersection Detect Radius | 0.5 m |
| Graph | Default Road Level | 0 |
| Graph | Remove Short Segments | On |
| Graph | Minimum Segment Length | 1 m |
| Road | Default Road Width | 7 m |
| Road | Default Lane Count | 2 |
| Road | Default Lane Width | 3.5 m |
| Road | Sample Spacing | 2 m |
| Road | Adaptive Sampling | On |
| Road | Maximum Chord Error | 0.1 m |
| Road | Crossfall | 2% |
| Road | Thickness | 0.2 m |
| Intersection | Enabled | On |
| Intersection | Corner Radius | 4 m |
| Intersection | Sample Spacing | 1 m |
| Intersection | UV Scale | 0.25 |
| Intersection | T / Cross | On / On |
| Sidewalk | Sidewalk / Curb | On / On |
| Sidewalk | Width / Height | 2 m / 0.15 m |
| Curb | Width / Height | 0.18 m / 0.15 m |
| Terrain | Conform | Off |
| Terrain | Offset | 0.02 m |
| Terrain | Maximum Grade | 15% |
| Chunk | Enabled | On |
| Chunk | Size | 128 m |
| Chunk | Origin | (0, 0, 0) |

道路、人行道、路缘石与标线 Material Path 默认均为空，避免把具体 Unity 美术资产硬编码为 HDA 类型默认值。目标 HIP 的开发实例中已写入四条 CityRoad 材质路径，但这些材质资产没有包含在提交 `13`，详见第 8 节。

### 3.4 道路标线参数

| 参数 | 默认值 |
|---|---:|
| Enable Road Markings | Off |
| Enable Crosswalks | On |
| Center / Lane / Edge Width | 0.12 / 0.10 / 0.10 m |
| Dash / Gap Length | 3 / 6 m |
| Marking Height | 0.015 m |
| Crosswalk Depth | 4 m |
| Stripe / Gap Width | 0.5 / 0.5 m |
| Crosswalk Side Margin | 0.35 m |
| Crosswalk Setback | 1 m |
| Stop Line Width | 0.3 m |
| Stop Line Gap | 1 m |

目标 HIP 实例已开启 `enable_road_markings` 和 `enable_crosswalks`。道路标线通过实体不透明 Polygon 输出，不使用透明 Decal、Geometry Shader 或运行时 CPU 逐条生成。

## 4. 道路图、路口与人行道

### 4.1 输入清洗

隔离 Cook 的输入统计：

```text
input_road_count             = 18
valid_road_count             = 17
invalid_road_count           = 1
short_segment_count          = 1
junction_count               = 4
t_junction_count             = 3
cross_junction_count         = 1
complex_junction_count       = 0
```

HDA 会在进入道路壳体生成前过滤无效或过短线段，并记录统计，而不是让非法输入继续进入 Boolean、PolyPath 和人行道模块。目标测试输入的 18 条道路中有 1 条被判定无效。

当前 metadata 仍存在 `missing_attribute_count = 72`。这说明输入数据没有完全提供 HDA 期望的道路属性，当前结果依赖默认宽度、默认车道数等回退值；不应把“Cook 成功”理解成“输入合约已经完整”。

### 4.2 路口生成

Tutorial V3 增量模块将道路区域划分为：

```text
cross
crossroad
road_body
outer_boundary
```

随后完成：

- T 字与十字路口识别。
- 路口区域合并。
- 外边界提取。
- 路口转角圆滑。
- 道路本体与路口壳体连接。
- 人行道环与路口的避让。
- Unity 左手坐标/面序输出校验。

隔离验证：

```text
road_width_validation_pass       = 1
failed_width_sample_count        = 0
invalid_cross_section_count      = 0
road_shell_validation_pass       = 1
v3_road_validation_pass          = 1
final_overlap_validation_pass    = 1
unity_export_winding_validation_pass = 1
```

道路顶面在 Houdini 中的朝向与 Unity 导出朝向采用显式反转契约。隔离统计中 Houdini Up 与 Unity Export Down 均为 1457 个面，最终 Unity 面序校验通过；这是坐标系转换约定，不是误翻面。

### 4.3 人行道与路缘石

人行道模块从道路/路口外边界生成闭合环，随后构造 Sidewalk 与 Curb：

```text
expected_sidewalk_loop_count  = 12
generated_sidewalk_loop_count = 12
sidewalk_validation_pass      = 1
```

重叠、自交和缺失材质统计均为 0。人行道与路缘石在输出合约中保持独立角色，后续可使用独立材质、碰撞策略、LOD 或 Bake 规则。

### 4.4 可建设街区

`OUT_BUILDABLE_BLOCKS` 已建立正式输出职责和 metadata，但本测试输入 Cook 结果为空：

```text
Points / Primitives / Vertices = 0 / 0 / 0
```

因此 Buildable Blocks 当前状态是 **接口已建立、有效结果未验证**，不能视为可交付的街区生成模块。

## 5. Shading、实体标线与移动端 Chunk

### 5.1 道路 Shading 数据契约

Shading Contract 增加：

| 属性 | 语义 |
|---|---|
| `uv` | 沿道路方向的米制 UV |
| `uv3` | City Local XZ 米制投影 |
| `Cd.r` | 确定性的道路外缘磨损 Mask |

这些数据只负责描述道路表面，不把材质功能塞入 HDA。Unity Shader 应读取稳定属性，并使用 runtime uniform 控制强度/缩放；如需高成本湿地、积雪或复杂破损，应拆成独立 Shader，而不是在一个 CityRoad 超级 Shader 中叠加 keyword。

提交 `13` 没有提交任何 Shader，因此：

- Instancing 支持：本提交无法验证。
- 自定义 keyword：0。
- Shader Variant 增量：0。
- 纹理采样与 half/float 精度：无法从本提交验证。
- Render Feature / RenderPass / RenderTexture / Blit / MRT：0。

### 5.2 静态实体道路标线

标线模块生成：

- 道路中心线。
- 车道分隔线。
- 道路边线。
- 人行横道。
- 停止线。

隔离 Cook 结果：

```text
marking_primitive_count             = 1228
crosswalk_approach_count            = 11
marking_junction_overlap_count      = 0
unsupported_lane_direction_count   = 0

Static Marking Mesh:
Points / Primitives / Vertices
4912 / 1228 / 4912
```

标线采用略高于道路表面的不透明几何：

- 优点：没有透明混合 Overdraw、没有运行时 Decal 投射和逐条 CPU 更新。
- 成本：增加顶点、三角形、MeshRenderer 与 DrawCall；如果每个标线类型或每个小段拆成独立 Renderer，会抵消 Chunk 收益。
- 移动端策略：按 Chunk 合并、使用单一低成本 Opaque 标线材质，并依赖 Chunk Bounds 剔除。

### 5.3 真正的几何裁切

Chunk 模块不是只按包围盒给整块道路打标签，而是在 128 m XZ 网格边界执行 Polygon 裁切，再按稳定键 Pack：

```text
chunk_key:
-1_-1
-1_0
0_-1
0_0
1_-1
1_0
```

稳定命名格式：

```text
CityRoad_<Role>_Chunk_<chunk_key>
```

四类 Mesh 输出都生成 6 个 Chunk：

| 输出角色 | 裁切后 Vertices | 最大单 Chunk Vertices | 超限 Chunk | 未分配 Primitive |
|---|---:|---:|---:|---:|
| Road Surface | 7,185 | 1,713 | 0 | 0 |
| Sidewalk / Curb | 9,594 | 2,448 | 0 | 0 |
| Road Collision | 4,752 | 1,044 | 0 | 0 |
| Road Markings | 7,836 | 2,262 | 0 | 0 |

所有 Chunk 都远低于 65,535 顶点，可使用 UInt16 Index；稳定名称和独立 Bounds 为后续移动端视锥剔除、距离 LOD、局部加载和 Bake 覆盖提供了扩展点。

### 5.4 正式输出几何

隔离 Force Cook：

| Output SOP | Points | Primitives | Vertices | 说明 |
|---|---:|---:|---:|---|
| `OUT_ROAD_SURFACE` | 6 | 6 | 6 | 6 个 Packed Chunk |
| `OUT_SIDEWALK_CURB` | 6 | 6 | 6 | 6 个 Packed Chunk |
| `OUT_ROAD_MARKING_POINTS` | 1,449 | 0 | 0 | 点数据接口 |
| `OUT_ROAD_COLLISION` | 6 | 6 | 6 | 6 个 Packed Chunk |
| `OUT_ROAD_CENTERLINE_GRAPH` | 531 | 17 | 485 | 道路图数据 |
| `OUT_BUILDABLE_BLOCKS` | 0 | 0 | 0 | 当前测试为空 |
| `OUT_ROAD_MARKINGS` | 6 | 6 | 6 | 6 个 Packed Chunk |

七个 Output SOP 均为 Error 0 / Warning 0。

## 6. 输出槽位合约问题

HDA 类型定义声明：

```text
Maximum Outputs = 6
```

但内部存在 7 个正式 Output SOP，且 `OUT_ROAD_MARKINGS` 使用 Output Index 6：

```text
0  OUT_ROAD_SURFACE
1  OUT_SIDEWALK_CURB
2  OUT_ROAD_MARKING_POINTS
3  OUT_ROAD_COLLISION
4  OUT_ROAD_CENTERLINE_GRAPH
5  OUT_BUILDABLE_BLOCKS
6  OUT_ROAD_MARKINGS
```

这会导致第七输出无法稳定地作为 HDA 正式输出暴露给 Houdini Engine Unity。目标 Unity 场景虽然包含 `_geoName = OUT_ROAD_MARKINGS`，但其下没有序列化 Part，不能证明第七输出合约有效。

**状态：[待修复]**

应在 HDA Type Properties 中把输出数量正式提升到 7，并执行：

1. HDA Definition 保存与重新安装验证。
2. Houdini Engine Unity Recook。
3. 七个 Geo Output 的名称、索引和 Part 数断言。
4. Bake 后 Renderer / Mesh / Material / Collider 职责检查。

在输出数量修复前，不应依赖 `OUT_ROAD_MARKINGS` 的第七槽位做生产 Bake。

## 7. 三个增量 Patch 脚本

### 7.1 `patch_cityroad_tutorial_v2.py`

职责：

- 对既有命名 `TUTORIAL_V2` 节点做增量 Patch。
- 修复道路重叠裁剪、固定宽度校验、外边界、人行道与 Curb。
- 为 Unity 输入为空的 Cold Start 状态提供安全 Switch。
- 在保存前执行完整验证并 Fail Closed。

保存策略：

```text
默认不保存
--save 才保存
--promote 依赖 --save
```

脚本内保留了旧的全量复制/重建辅助函数，但主入口明确不调用。该脚本最接近安全的可重复增量维护工具。

### 7.2 `patch_cityroad_crossroad_v3.py`

职责：

- 只对当前 Live CityRoad 实例做增量修改。
- 增加 `cross`、`crossroad`、`road_body` 分类。
- 构建路口外边界、转角、人行道环与 Unity Winding 验证。
- 清理命名诊断节点和 V3 临时节点。

风险：

- 脚本不主动加载/清空 HIP，符合 Live Scene 原则。
- 但主流程结束时会更新 HDA Definition 并保存当前 HIP。
- 没有 `--save` / Dry Run 门禁。

因此它只能在 Houdini MCP preflight、目标 HIP/HDA/实例路径确认和备份完成后运行，不适合直接批处理。

### 7.3 `patch_cityroad_shading_markings_chunks.py`

职责：

- 增加 `uv`、`uv3`、`Cd.r` Shading Contract。
- 增加道路标线 UI 与 Marking Material Path。
- 生成静态实体标线。
- 对 Road、Sidewalk、Collision、Markings 执行 128 m 网格裁切与 Pack。
- 写入 Chunk 统计和 UInt16 顶点上限检查。

风险：

- 只处理命名 CityRoad 节点，不修改 Track HDA。
- 但完成后会无条件更新 HDA Definition 并保存 HIP。
- 没有与 Tutorial V2 相同的 CLI 保存门禁。
- 保存前缺少统一的输出槽位、Unity Recook 和依赖完整性验证。

后续应给 V3 和 Shading/Chunk 脚本补充统一参数：

```text
--dry-run
--save
--promote-definition
--expected-hip
--expected-hda
```

并在 Save 前断言 7 个输出、无 Cook Error/Warning、无超限 Chunk、目标路径匹配。

## 8. Unity 场景接入

### 8.1 场景结构

`PCG_City.unity` 是提交 `13` 新增的独立 CityRoad 场景。主要顶层对象：

- `Main Camera`
- `Directional Light`
- `Global Volume`
- `SplineContainer`
- `HDA_Data`
- `CityRoad1`

场景 YAML 类型数量：

| 类型 | 数量 |
|---|---:|
| GameObject | 2,118 |
| Transform | 2,118 |
| MonoBehaviour | 2,131 |
| Mesh | 707 |
| MeshRenderer | 1,409 |
| MeshFilter | 1,409 |
| Material | 707 |
| MeshCollider | 707 |
| Camera / Light | 1 / 1 |

该场景是 Houdini Engine Working/Cook 快照，不是精简的 Player Runtime Bake。大量 GameObject、MonoBehaviour 和内联 Mesh/Material 不适合直接作为移动端最终运行结构。

### 8.2 场景中的 Geo / Part

场景中七个 `_geoName` 各出现一次：

```text
OUT_ROAD_SURFACE
OUT_SIDEWALK_CURB
OUT_ROAD_MARKING_POINTS
OUT_ROAD_COLLISION
OUT_ROAD_CENTERLINE_GRAPH
OUT_BUILDABLE_BLOCKS
OUT_ROAD_MARKINGS
```

但 `_partName` 分布为：

| 输出 | Scene Part 数 |
|---|---:|
| `OUT_SIDEWALK_CURB_*` | 476 |
| `OUT_ROAD_SURFACE_*` | 464 |
| `OUT_ROAD_COLLISION_*` | 464 |
| `OUT_ROAD_CENTERLINE_GRAPH_0` | 1 |
| `OUT_ROAD_MARKINGS_*` | 0 |
| `OUT_ROAD_MARKING_POINTS_*` | 0 |
| `OUT_BUILDABLE_BLOCKS_*` | 0 |

这与目标 HIP/HDA 隔离 Cook 后“Road、Sidewalk、Collision、Markings 各 6 个 Packed Chunk”的状态明显不一致。说明 `PCG_City.unity` 保存的是较早阶段的 Cook 结果，没有同步最终实体标线和 Chunk 输出。

**状态：[待修复]**

必须在输出槽位修复后重新 Recook/Bake，并确认最终场景不再保留 464/476 个细碎 Part。

### 8.3 默认材质快照

场景序列化了 707 个 `HEU_DEFAULT_MATERIAL_*` 内联材质。目标提交没有包含 CityRoad 自定义材质和 Shader，因此场景只证明 Houdini Engine 生成结果存在，不能证明最终道路、人行道、路缘石和标线着色已接入。

移动端最终 Bake 应把材质收敛到少量共享资产，而不是每个 Part/Chunk 复制内联 Material；否则会增加 SetPass、资源体积和版本噪声。

### 8.4 HDA `.meta` 缓存引用缺失

目标场景的 `_assetFileObject` 引用了：

```text
GUID: 67d84be2a5065e14493d6b0d83e29db8
```

当前工作区的 `Assets/PCG/HDA/City/CityRoad.hda.meta` 正好使用该 GUID，但该 `.meta` 没有包含在提交 `13`。因此在干净检出中：

- Unity 会为 `CityRoad.hda` 生成新 GUID。
- `PCG_City.unity` 中的 HDA 引用会失效。
- Scene 可能出现 Missing HDA Asset 或无法稳定 Recook。

**状态：[待修复，阻断干净检出]**

提交 `City.meta` 不能替代 `CityRoad.hda.meta`；必须把 HDA 资产自身的 `.meta` 纳入版本管理。

## 9. 未提交依赖与版本边界

目标 HIP 的 CityRoad 实例写入了以下路径：

```text
Assets/PCG/Materials/M_PCG_CityRoad_Asphalt.mat
Assets/PCG/Materials/M_PCG_CityRoad_Sidewalk.mat
Assets/PCG/Materials/M_PCG_CityRoad_Curb.mat
Assets/PCG/Materials/M_PCG_CityRoad_Marking.mat
```

当前工作区还存在对应的四个 Material、三个 CityRoad Shader 及其 `.meta`：

```text
PCG_CityRoad_Asphalt.shader
PCG_CityRoad_Marking.shader
PCG_CityRoad_SimpleSurface.shader
```

但它们都不属于提交 `10d3ab1`。因此 Phase13 对这些资源的准确结论是：

| 内容 | 提交 13 状态 |
|---|---|
| Material Path 参数接口 | 已完成 |
| HIP 实例材质路径 | 已配置 |
| 四个 Material 资产 | 未提交 |
| 三个 Shader 资产 | 未提交 |
| 场景自定义材质绑定 | 未完成 |
| Shader Instancing / Pass / Variant 验证 | 无法执行 |

本文没有修改、移动、提交或把这些既有未跟踪文件计入 Phase13。

## 10. Unity 输入调试 BGeo

`CityRoad_UnityInput_Debug.bgeo.sc` 是一次 Houdini Engine Unity 输入抓取：

```text
Points / Primitives / Vertices = 6023 / 5 / 6023
Bounds Min = (-8293.7715, 0, -8461.9531)
Bounds Max = ( 3238.2627, 0,  3444.9260)
Point Attributes = P(float3), rot(float4)
Detail Attribute = hapi_input_curve_coords
```

它用于诊断 HAPI Curve/Input 坐标与旋转，不是 Player Runtime 资产。当前问题：

- 文件位于 `HoudiniProject/.../temp/`，但被正式提交。
- 空间范围超过 11 km，远离原点区域会放大 float 精度、UV 和 Bounds 风险。
- 缺少来源场景、生成时间、用途和是否可删除的旁车说明。

建议将调试夹具迁移到明确的 `Tests/Fixtures` 或不进入版本管理；若保留，应补充输入合约与自动测试，不应让 `temp` 目录成为长期事实源。

## 11. 性能、渲染与移动端边界

### 11.1 CPU / GPU 分工

| 阶段 | CPU / Houdini | GPU / Unity | 结论 |
|---|---|---|---|
| 编辑器生成 | 道路图、Boolean、路口、人行道、标线、裁切、Pack | 预览 | 允许高 Cook 成本，但必须 Bake |
| Unity Working Scene | HEU 维护大量节点/Part/组件 | 渲染大量细碎 Mesh | 仅开发期，不适合作为 Player 结构 |
| 最终 Runtime | 禁止 Houdini Cook、禁止逐道路 CPU 生成 | 渲染 Bake Chunk，按 Bounds 剔除 | 目标正确，正式 Bake 尚未完成 |
| 大规模装饰/植被 | 不应每帧 CPU for-loop | Indirect Draw + GPU Culling | 本提交未实现 |

### 11.2 Chunk 收益与风险

当前 128 m Chunk 的收益：

- 稳定 Name 和 Grid Key。
- Road/Sidewalk/Collision/Markings 共享相同 Chunk 空间。
- 单 Chunk 顶点数远低于 UInt16 上限。
- 可做视锥、距离、流式加载和局部重 Bake。

仍需验证：

- Chunk Bounds 是否紧贴几何，避免过度保守剔除。
- 128 m 是否适合城市街区尺度和目标摄像机。
- 6 Chunk 测试规模不足以代表完整城市。
- Renderer、Material 和 Collider 是否按角色/Chunk 合并。
- MeshCollider 是否需要全分辨率；移动端应优先使用简化碰撞。
- 道路 Chunk 通常几何唯一，不应盲目套用 GPU Instancing；收益主要来自剔除和合并。

### 11.3 带宽与 Overdraw

- 本提交没有新增 RendererFeature、RenderPass、RenderTexture、Blit 或 MRT。
- 标线为 Opaque 实体几何，不产生透明叠加 Overdraw。
- 标线有轻微高度偏移，需检查远距离 Z-Fighting 与深度精度。
- CityRoad Shader 未提交，无法验证纹理采样、half 精度、Forward/Depth/Shadow Pass 和 Instancing。
- 当前场景大量内联默认材质与 Renderer 会增加 SetPass/DrawCall；必须通过正式 Bake 收敛。

### 11.4 Shader Variant

提交 `13` 的 Shader 变化为 0，因此没有新增 keyword 或 Variant。但这不等于 CityRoad 最终 Shader 已满足项目规范。

后续提交 CityRoad Shader 时必须单独记录：

- `#pragma multi_compile_instancing` 的 Pass 覆盖。
- `shader_feature_local` 列表与理论 Variant 数。
- URP 基础 keyword 叠加风险。
- 每 Pass 纹理采样数。
- half/float 精度边界。
- Opaque/Cutout/Transparent 与 Overdraw。
- Android Mali/Adreno、iOS Metal 编译和真机 Profiling。

## 12. 验证记录

### 12.1 Git

- 目标提交：`10d3ab1529e9bcc47878b55fcdd4e1ebe93c3489`。
- 父提交：`6538b53d23135bb7c5ba3a28a771b0f3ba9b613a`。
- 9 个新增文件，未删除既有文件。
- 未修改 Houdini Engine Unity 插件。
- 未提交 `CityRoad.hda.meta`。
- 未提交 CityRoad Material / Shader。
- 当前工作区存在大量与本日志无关的既有修改/未跟踪文件，本文没有覆盖它们。

### 12.2 Houdini MCP Preflight

```text
Houdini Version: 21.0.440
18811 RPC: connected
Current HIP: PCG_Bike_CityRoad.hip
3055 health: healthy
Codex Houdini MCP tools: not discovered in current session
```

连接层已通，但当前 Codex 会话没有热加载 Houdini MCP 工具，因此本次没有声称通过 Houdini MCP 操作 Live Scene，也没有修改或保存当前 HIP/HDA。需在重启 Codex 后重新执行 preflight，补做 Live Scene 路径、Definition、Cook 和保存状态复验。

### 12.3 HDA 类型与隔离 Hython

目标提交 HDA：

```text
Type: pcgbike::CityRoad::1.0
Inputs: 0..4
Declared Outputs: 6
Internal Output SOPs: 7
```

目标提交 HIP 隔离 Force Cook：

- CityRoad 根节点 Error / Warning：0 / 0。
- 七个 Output SOP Error / Warning：全部 0 / 0。
- Road / Sidewalk / Collision / Markings：各 6 个 Packed Chunk。
- Road、Sidewalk、Collision 和 Markings 最大单 Chunk 顶点均低于 2,500。
- 道路宽度、道路壳体、人行道、V3 重叠与 Unity Winding 验证通过。
- Buildable Blocks 输出为空。
- 测试过程没有保存 HIP/HDA。

### 12.4 Unity Scene YAML

- `PCG_City.unity` 包含 CityRoad HDA 和七类 Geo 名称。
- 场景 Part 仍为旧的 464/476 细分输出。
- `OUT_ROAD_MARKINGS` 没有 Part。
- 场景包含 707 个 HEU 默认内联材质。
- 场景引用的 HDA GUID 对应未提交的 `CityRoad.hda.meta`。

### 12.5 Unity MCP

文档交付验证：

- `AssetDatabase.Refresh(ForceSynchronousImport)`：成功。
- Unity Editor：2022.3.62f2。
- Play / Pause：False / False。
- Compiling / Updating：False / False。
- 当前打开场景：`Assets/PCG/Scenes/PCG.unity`。
- 场景：Loaded、Valid、Dirty、Build Index 0、Root Count 11。
- 最近 30 分钟 Console Error：0。
- 最近 30 分钟 Console Exception：0。
- 本文没有打开、保存或覆盖 `PCG_City.unity`。

## 13. 当前状态矩阵

| 功能 | 状态 | 当前结论 |
|---|---|---|
| CityRoad HDA 基础结构 | 已完成 Phase13 基础 | 独立 HDA/HIP，模块边界清晰 |
| Unity 四类输入接口 | 已建立 | Road 主输入有效，其余为扩展接口 |
| 道路输入清洗 | 已验证 | 18 条输入，17 有效，1 条被过滤 |
| T / Cross 路口 | 已验证 | 3 个 T、1 个 Cross |
| 道路壳体与固定宽度 | 已验证 | Width/Shell Validation Pass |
| 人行道与路缘石 | 已验证 | 12/12 Loop，无重叠/自交 |
| Unity 面序 | 已验证 | 左右手转换契约通过 |
| 道路 Shading Contract | 已完成 | `uv`、`uv3`、`Cd.r` |
| 实体道路标线 | 已验证 Houdini 输出 | 1,228 个 Primitive |
| 128 m 几何裁切 | 已验证 | 四类 Mesh 各 6 Chunk |
| UInt16 顶点控制 | 已验证当前样例 | 最大 Chunk < 2,500 Vertices |
| Road Marking 正式输出 | 待修复 | 第七 SOP 超出 HDA 声明的 6 Outputs |
| Buildable Blocks | 未完成 | 输出接口存在，测试结果为空 |
| PCG_City 最终 Recook | 未完成 | 场景仍是 464/476 Part 旧快照 |
| CityRoad HDA `.meta` | 未提交 | 干净检出会断引用 |
| CityRoad Material / Shader | 未提交 | HIP 路径已配，但资源不在提交 |
| Unity 自定义材质绑定 | 未完成 | 场景仍为 HEU 默认内联材质 |
| Player Runtime Bake | 未完成 | 当前场景是 HEU Working 快照 |
| RendererFeature / RenderPass | 无变更 | 未新增 Pass/RT/Blit/MRT |
| Shader Variant | 无法验证 | 提交中没有 CityRoad Shader |
| Android/iOS Build | 未执行 | 待验证 |
| 移动端真机 Profiling | 未执行 | Mali/Adreno/Apple GPU 待验证 |

## 14. 下一阶段建议

1. 提交 `Assets/PCG/HDA/City/CityRoad.hda.meta`，首先修复场景 HDA GUID 的干净检出阻断。
2. 将 HDA 声明输出数从 6 修正为 7，明确 `OUT_ROAD_MARKINGS` 的正式索引和 Houdini Engine Unity 输出。
3. 给三个 Patch 脚本统一增加 Dry Run、Save、Promote、Expected HIP/HDA 门禁；默认禁止无条件保存。
4. 补充自动验证脚本，断言输入清洗、4 类路口统计、7 个输出、Chunk Key、UInt16 上限、材质路径和 Buildable Blocks 状态。
5. 将四个 CityRoad Material、三个 Shader 及全部 `.meta` 作为独立渲染提交纳入版本管理，并完整记录 Instancing、Pass、采样和 Variant 风险。
6. 在输出槽位和材质依赖完整后重新 Recook `PCG_City.unity`，确认 Road/Sidewalk/Collision/Markings 各为 6 个 Chunk，不再保留 464/476 个细碎 Part。
7. 建立正式 Bake Pipeline，把 HEU Working 输出转换到 `Assets/PCG/Generated/CityRoad/` 的 Mesh/Prefab/Collider/Metadata；保护地编覆盖，禁止 Recook 无提示覆盖。
8. 将 707 个默认内联材质收敛为少量共享 Material，并按 Role + Chunk 合并 Renderer。
9. 为 Collision 使用简化 Mesh，评估 64/128/256 m Chunk 对 Cook、DrawCall、Culling、Collider 和内存的影响。
10. 将 `CityRoad_UnityInput_Debug.bgeo.sc` 迁移为有说明的测试夹具或从正式版本移除，不再长期放在 `temp`。
11. 重启 Codex 后重新运行 Houdini MCP preflight，补做 Live HIP/HDA/Definition/Cook 状态验证；未经复验不保存现场。
12. 完成 Android/iOS IL2CPP Build，并在 Mali、Adreno、Apple GPU 上记录 DrawCall、SetPass、三角形、Chunk Culling、Overdraw、内存与帧耗。
