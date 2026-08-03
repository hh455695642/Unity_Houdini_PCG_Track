# Phase 14 开发日志：CityRoad 拓扑输出、Bake 工作流与移动端渲染

> 文档类型：提交增量快照  
> 记录日期：2026-08-03  
> 目标提交：`935190f9966e218a5b87342ffccd6da3e462906f`（提交信息：`14`）  
> 父提交：`4f7746c8c6c16983e4ca778fd6dbdc5bb3fdbdc7`（Phase13 文档提交）  
> CityRoad 场景：`Assets/PCG/Scenes/PCG_City.unity`  
> CityRoad HDA：`Assets/PCG/HDA/City/CityRoad.hda`  
> CityRoad HIP：`HoudiniProject/PCG_Track_21.0.440/PCG_Bike_CityRoad.hip`

## 1. 日志范围与证据

本文只记录 Git 提交 `935190f` 相对父提交 `4f7746c` 的开发增量，不重复 Phase 1～Phase 13 已记录的 Track、Terrain、Lake、TerrainLayer 和 CityRoad 基础道路网络。

本阶段对 Phase13 CityRoad 做了三项实质性架构调整：

```text
Phase13：128 m XZ Spatial Chunk
    -> Phase14：按 Corridor / Junction 稳定拓扑归属拆分
    -> Unity Live Preview：只显示 Presentation Renderer
    -> Safe Rebuild：保留 4 个 Unity 输入和生成开关
    -> Cook + Validate + Bake：生成/更新 Unity Prefab
    -> Build Guard：禁止 Live HDA 进入 Player Build
```

同时补齐：

- 四个 CityRoad Material。
- 三个移动端 URP Shader。
- HDA `.meta` 和材质路径默认值。
- 道路表面、路口、人行道、标线与碰撞的拓扑输出。
- Unity Editor 侧的 Rebuild、Live Preview、Bake 和 Build 校验工具。

证据等级：

- **[提交验证]**：直接读取目标提交 Git diff、C#、Shader、Material、HDA、HIP、Patch 脚本和场景 YAML。
- **[Unity 现场验证]**：通过 Unity MCP 读取 Editor、场景、Shader 导入/编译状态和 Console。
- **[隔离验证]**：使用独立 `hython` 加载目标提交 HIP/HDA 并 Force Cook；没有保存或覆盖 HIP/HDA。
- **[待修复]**：实现已存在，但目标提交的 Cook、Bake、输出合约、构建或版本管理仍未闭环。

本提交没有修改 `Assets/Plugins/HoudiniEngineUnity/`。所有 Houdini Engine 兼容逻辑均位于 `Assets/PCG/Editor/CityRoad/`，继续符合官方插件零侵入约束。

## 2. 提交概览

| 项目 | 数值 |
|---|---:|
| Commit | `935190f` |
| Author / Date | `liyuan` / 2026-08-03 18:01:08 +08:00 |
| Changed Files | 34 |
| Added / Deleted Lines | `+36291 / -401477` |
| 新增 CityRoad Editor C# | 3 个 / 1,855 行 |
| 新增 Shader | 3 个 / 557 行 |
| 新增 Material | 4 个 |
| 新增 Houdini Patch | 3 个 / 2,297 行 |
| CityRoad HDA | 166,375 → 185,760 bytes |
| CityRoad HIP | 1,469,228 → 1,612,465 bytes |
| Unity 场景 | 25,843,508 → 5,619,848 bytes |
| 新增 Render Feature / RT / Blit | 0 |

文件按职责分为六组：

1. **Unity Editor 工作流**
   - `CityRoadSafeRebuild.cs`
   - `CityRoadLivePreviewController.cs`
   - `CityRoadBakeWorkflow.cs`

2. **HDA/HIP 与定义修复**
   - `Assets/PCG/HDA/City/CityRoad.hda`
   - `Assets/PCG/HDA/City/CityRoad.hda.meta`
   - `Assets/PCG/HDA/City/backup.meta`
   - `PCG_Bike_CityRoad.hip`

3. **拓扑与路口增量 Patch**
   - `patch_cityroad_topology_outputs.py`
   - `patch_cityroad_topology_v4.py`
   - `patch_cityroad_junction_markings_v5.py`

4. **材质与移动端 Shader**
   - `M_PCG_CityRoad_Asphalt.mat`
   - `M_PCG_CityRoad_Sidewalk.mat`
   - `M_PCG_CityRoad_Curb.mat`
   - `M_PCG_CityRoad_Marking.mat`
   - `PCG_CityRoad_Asphalt.shader`
   - `PCG_CityRoad_SimpleSurface.shader`
   - `PCG_CityRoad_Marking.shader`

5. **Unity Live Cook 场景**
   - `Assets/PCG/Scenes/PCG_City.unity`

6. **版本管理补充/遗留**
   - `Assets/PCG/Editor.meta`
   - `Assets/PCG/Editor/CityRoad.meta`
   - `Assets/PCG/Materials/Terrain.meta`
   - 仓库根目录的第二份 `CityRoad.hda`

## 3. 从 Spatial Chunk 切换到拓扑 Piece

### 3.1 架构变化

Phase13 的输出按 128 m XZ 网格裁切并 Pack。Phase14 明确废弃该接口：

- HDA 公共参数中删除 `enable_chunking`、`chunk_size` 和 `chunk_origin`。
- HDA 内删除 `CITYROAD_CHUNK_OUTPUT`、`CITYROAD_PACK_ROAD` 等空间 Chunk 节点。
- `patch_cityroad_shading_markings_chunks.py` 的 `main()` 入口改为直接抛错，禁止重新引入旧 Chunk 输出。
- 新输出以道路拓扑归属为稳定单位，不再依赖世界网格位置。

旧脚本的保护错误为：

```text
CITYROAD_CHUNK_OUTPUT has been retired.
Spatial chunking must not be reintroduced.
```

这不是 Phase13 Chunk 的继续扩展，而是一次明确替换。

### 3.2 稳定命名与 metadata

拓扑 Piece 使用：

```text
CityRoad_Corridor_L<road_level>_<piece_id>_<Role>
CityRoad_Junction_L<road_level>_<junction_id>_<Role>
```

主要属性：

| 属性 | 职责 |
|---|---|
| `name` | Houdini Engine Unity 输出/实例稳定名称 |
| `instance_prefix` | 生成实例名前缀 |
| `topology_piece_kind` | `corridor` 或 `junction` |
| `topology_piece_id` | 稳定拓扑 Piece ID |
| `junction_id` | 路口归属 |
| `road_level` | 道路层级 |
| `city_part` | RoadSurface、Sidewalk/Curb、RoadMarkings 等角色 |
| `unity_material` | Unity Material 资产路径 |

拓扑合约版本写为：

```text
cityroad_topology_contract_version = 4.0.0
```

### 3.3 输出职责

| 输出 | Phase14 职责 |
|---|---|
| `OUT_ROAD_SURFACE` | Corridor/Junction 道路表面 Piece |
| `OUT_SIDEWALK_CURB` | 就近继承道路拓扑归属的人行道/路缘石 |
| `OUT_ROAD_MARKING_POINTS` | 标线点数据 |
| `OUT_ROAD_COLLISION` | 单一 `collision_geo` 碰撞输出，不参与可见渲染 |
| `OUT_ROAD_CENTERLINE_GRAPH` | 道路图/中心线数据 |
| `OUT_BUILDABLE_BLOCKS` | 可建设街区接口 |
| `OUT_ROAD_MARKINGS` | Corridor/Junction 实体标线 Piece |

Collision 会移除 `unity_material`，写入：

```text
cityroad_collision_contract = collision_geo
```

Unity 侧因此只创建 Collider，不应显示碰撞 Renderer。

### 3.4 当前测试场景拓扑规模

目标场景的 Presentation Piece：

| 类型 | Road Surface | Road Markings | Sidewalk/Curb |
|---|---:|---:|---:|
| Corridor | 18 | 18 | 18 |
| Junction | 7 | 7 | 0 |
| 合计 | 25 | 25 | 18 |

可见 Presentation Renderer 合计 68 个。Houdini Engine 还为相同 Mesh 保存了 Backing Renderer，因此场景中总 MeshRenderer 为 141，其中 68 Enabled、73 Disabled。`CityRoadLivePreviewController` 负责只启用名称包含 `Corridor_` 或 `Junction_` 的 Presentation Renderer，避免完全重叠的重复表面。

### 3.5 移动端取舍

拓扑 Piece 的优势：

- 命名不再随世界网格原点变化。
- Corridor/Junction 便于局部编辑、材质覆盖和按道路语义 Bake。
- 场景 Mesh、GameObject 和 Collider 数量显著下降。
- 每个 Piece 有独立 Bounds，可继续做视锥/距离剔除。

风险：

- 不再有固定 128 m 空间上限，超长 Corridor 可能形成过大的 Bounds。
- 当前 68 个可见 Renderer 至少对应相近规模的 Draw 提交；Material 开启 Instancing 不会自动合并这些不同 Mesh。
- 尚未实现 GPU Indirect Draw、GPU Culling 或运行时流式加载。
- 后续需要为超长 Corridor 增加“拓扑内部分段”，但不能恢复无语义的全局网格切块。

## 4. V4 道路、路口与人行道拓扑

### 4.1 曲线简化与重采样

`patch_cityroad_topology_v4.py` 调整道路采样：

- 删除全局 20 m 硬下限。
- 直线段最大边长 30 m。
- 弯道最大转角 8°。
- 按和弦偏差保留关键 Station。
- `ROAD_ADAPTIVE_RESAMPLE` 继续补齐最大边长。

目的不是无限降低顶点，而是在直线减少冗余 Station、在曲率变化处保留形状，降低 Unity Mesh 与 Collider 规模。

### 4.2 Corridor/Junction 道路面

V4 对道路壳体进行拓扑语义拆分：

- 普通道路段归为 Corridor。
- T 字和十字路口归为 Junction。
- 路段端点沿切线延伸进入 Junction Core。
- Junction 从原始道路 Strip Union 中提取，重叠区只保留一套表面。
- Junction 保留来源道路 UV0，并生成 City Local `uv3`。
- 仅反转朝下的 Junction 顶面，保持 Unity Winding 契约。

### 4.3 人行道与路缘石

V4 将人行道/路缘石拆成两条可读链：

```text
Corridor Curb/Sidewalk
    + Junction Curb/Sidewalk
    -> Merge
    -> 1 mm Fuse
    -> Triangulate Visible
```

关键规则：

- Corridor 两侧独立 Quad Strip。
- 只连接相邻 Station。
- 路口入口按同一 Mouth 裁断。
- Junction 只沿圆角和 T 路口背边生成路缘。
- Junction 入口 Cut Edge 不生成重复 Curb。
- Fuse 仅允许 1 mm 内对应 Station，禁止跨道路/跨路口焊接。

## 5. V5 Junction Arms 与 Approach Markings

### 5.1 Junction Surface Boundary

`patch_cityroad_junction_markings_v5.py` 增加：

- `CITYROAD_BUILD_JUNCTION_SURFACE_BOUNDARY_V5`
- `CITYROAD_BUILD_APPROACH_MARKINGS_V5`
- V5 Junction Core + Arm 提取逻辑
- Junction 标线显式拓扑所有权校验

Junction Surface 会保留圆角边界，并沿每个 Approach 延伸到停车线外侧，作为 Corridor 裁切与 Junction Arms 的共用 Cut Plane。

### 5.2 斑马线与停止线

V5 删除旧 Crosswalk/StopLine Quad，再从稳定 Approach metadata 重建：

- 斑马线长轴平行车辆方向。
- 整组条纹沿道路横向排列。
- 停止线方向与道路 Approach 对齐。
- Crosswalk/StopLine 全部明确归属 Junction。
- 标线的最近 RoadSurface 必须属于同一 Junction。

验证 metadata 包括：

```text
junction_marking_expected_approach_count
junction_marking_crosswalk_count
junction_marking_stopline_count
junction_marking_parallel_error_count
junction_marking_stop_orientation_error_count
junction_marking_coverage_error_count
```

### 5.3 Patch 脚本保存边界

| 脚本 | 现场修改 | 自动保存 | Definition 更新 | 保护 |
|---|---|---|---|---|
| `topology_v4.py` | 是 | 否 | 否 | 节点存在性/片段 Guard |
| `junction_markings_v5.py` | 是 | 否 | 否 | V4 节点与数据 Guard |
| `topology_outputs.py` | 是 | **是** | **是** | HIP/HDA 路径、备份、Cook/统计验证 |

`topology_outputs.py` 会：

1. 确认当前 HIP 和 Definition 路径。
2. 保存当前 HIP。
3. 备份 HDA 到 `Assets/PCG/HDA/City/backup/`。
4. 增量替换 Chunk 网络。
5. Force Cook 四类输出。
6. 校验 Corridor/Junction 和 Curb Return 数量。
7. 更新 HDA Definition 并再次保存 HIP。

它没有 `--dry-run` / `--save` 门禁；若中途验证失败，Definition 不更新，但当前 Live 实例可能已被修改。后续应补充显式 Dry Run、Save、Promote 和 Rollback。

## 6. CityRoad Safe Rebuild

`CityRoadSafeRebuild.cs` 提供菜单：

```text
PCG / CityRoad / Safe Rebuild Selected
```

工作流：

```text
选中 CityRoad HDA
    -> 捕获 4 个 Unity 输入绑定
    -> 校验 Input 0 道路网络非空
    -> 捕获 Road Markings / Crosswalk Toggle
    -> 同步 RequestReload
    -> 恢复输入绑定与 Toggle
    -> 写入四条 Material Path
    -> 强制上传 Input Network
    -> Cook 输入 Merge 与 HDA Reader
    -> 同步 RequestCook
    -> Scene 标脏
```

### 6.1 输入合约

代码强制：

```text
ExpectedInputCount = 4
Input 0 = Required Road Network
Input 1..3 = Optional/Existing Binding Preserved
```

四个 HDA Reader：

- `IN_ROAD_NETWORK`
- `IN_RACE_ROUTE`
- `IN_TERRAIN_SURFACE`
- `IN_CITY_BOUNDARY`

Reload 前后会恢复现有 GameObject 引用，并验证 Road Input 确实上传为非空 Houdini Geometry。

### 6.2 Houdini Engine 兼容桥

当前 Houdini Engine Unity 版本的公开 `RequestCook` 没有暴露 `bForceUploadInputs`。项目工具使用反射调用插件内部：

```text
HEU_HoudiniAsset.UploadInputNodes(
    HEU_SessionBase,
    bool bForceUpdate,
    bool bUpdateAll)
```

该逻辑：

- 位于项目自己的 Editor 目录。
- 没有修改官方插件。
- 会检查方法签名和返回类型，不匹配时 Fail Closed。

风险是插件升级后私有 API 可能变化。升级 Houdini Engine Unity 时必须先验证 Safe Rebuild，不能把该桥接视为稳定公开接口。

### 6.3 HDA 导入策略

`CityRoadHdaImportPostprocessor` 不会在 HDA Import 时自动 Reload/Cook 所有实例，只打印提示，要求用户显式运行 Safe Rebuild。

这是正确的性能边界：HDA Import 不应递归触发高成本 Cook，也不应在 Definition 尚未稳定时自动覆盖场景输出。

## 7. Live Preview、Bake 与 Build Guard

### 7.1 Live Preview Controller

`CityRoadLivePreviewController` 使用 `[InitializeOnLoad]`，监听：

- Editor Update。
- Hierarchy Change。
- HDA Cooked Event。
- HDA Reload Event。
- Scene Saving。
- Assembly Reload。

成功 Cook/Reload 后：

- HDA Root 标记 `EditorOnly`。
- 仅启用 Road、Sidewalk/Curb、RoadMarkings 的 Presentation Renderer。
- Collision Renderer 保持关闭。
- Backing Renderer 保持关闭，避免重叠 Mesh。
- 关闭同级 Bake 实例，进入 Live Preview。
- Visible CityRoad 不投射阴影、继续接收阴影。

成功 Bake 后：

- HDA Source Renderer 全部关闭。
- 激活同级 `<HDA Name>_Bake`。
- 退出 Live Preview。

Controller 每秒扫描一次已加载的 CityRoad HDA。它只存在于 Editor Assembly，不进入 Player Runtime，但超大编辑场景仍应关注 Editor Update 扫描成本。

### 7.2 Cook + Validate + Bake

菜单：

```text
PCG / CityRoad / Cook + Validate + Update Bake Selected
PCG / CityRoad / Validate Loaded Bake Contract
```

默认 Bake 路径：

```text
Assets/PCG/Generated/Road/CityRoad/
    <SceneName>/
        <HDAName>/
            <HDAName>.prefab
```

流程使用 Houdini Engine 官方 `BakeToNewPrefab` / `BakeToExistingPrefab`，没有 Patch 插件。

Bake 前后校验：

- 至少存在一个 Enabled Renderer。
- Road/Sidewalk/Curb/Marking 使用指定项目 Material。
- Material Shader 名称正确且启用 GPU Instancing。
- 输出中不再存在 `Chunk` 名称。
- Collision 没有 Enabled Renderer。
- `OUT_ROAD_COLLISION` 至少存在一个 MeshCollider。
- Road Collider 非 Convex、非 Trigger、Shared Mesh 非空。
- 可见 Piece 名称包含 Corridor/Junction。
- 不存在相同 Mesh/Bounds/Transform 的重叠 Renderer。
- Visible Road/Marking/Sidewalk 不投射阴影、继续接收阴影。

完成后创建/激活 Bake 实例，并保留同级：

```text
CityRoad_Overrides
```

供地编放置不会被 Recook/Bake 覆盖的人工覆盖内容。

### 7.3 Build Guard

`CityRoadBuildGuard : IProcessSceneWithReport` 在构建处理场景时检查：

- 是否仍处于 Live Preview。
- 是否缺少活动 Bake 实例。

不满足条件时抛出 `BuildFailedException`。Scene Save 只记录 Error，不阻止保存；真正的 Player Build 会被阻断。

### 7.4 当前提交没有 Bake 交付

目标提交全树中没有：

```text
Assets/PCG/Generated/Road/CityRoad/**/*.prefab
```

目标 `PCG_City.unity` 中：

```text
CityRoad1_Bake = 0
PrefabInstance = 0
CityRoad_Overrides = 1
```

Unity Console 已明确报告：

```text
CityRoad1 is still in Live Preview or has no active Bake instance.
```

因此本阶段的准确状态是：**Bake 工具链已实现，正式 Bake Prefab 尚未交付，当前场景不可进入 Player Build。**

## 8. 移动端 URP Shader

### 8.1 Pass、Render Queue 与采样

| Shader | Queue | Forward 采样 | Pass | ShadowCaster |
|---|---:|---:|---|---|
| `PCG/CityRoad/Asphalt` | 2000 | 3 | Forward + DepthOnly | 无 |
| `PCG/CityRoad/SimpleSurface` | 2000 | 1 | Forward + DepthOnly | 无 |
| `PCG/CityRoad/Marking` | 2001 | 0 | Forward + DepthOnly | 无 |

共同设置：

- URP Opaque。
- `Cull Back`。
- `ZWrite On`。
- `ZTest LEqual`。
- Shader Model `2.0`。
- Forward 与 DepthOnly 都支持 `#pragma multi_compile_instancing`。
- 主光 + SH 环境光 + 低成本 Scalar Specular。
- 无 Additional Light Loop。
- 无 Normal/ORM 采样。
- 无透明混合和 Alpha Clip。
- 无 Geometry Shader。

### 8.2 Asphalt

输入数据：

- Houdini `uv3` → Unity `TEXCOORD2`，作为 City Metric UV。
- `Cd.r` 作为确定性道路边缘磨损 Mask。

固定三次纹理采样：

| Texture | 资产 | 作用 |
|---|---|---|
| Base | `T_Mountainbike_Road_C.tga` | 沥青基础色 |
| Aggregate | `T_Mountainbike_Gravel_C.png` | 骨料细节 |
| Macro Mask | `T_Road_ErosionBlendMask_RGBA.png` | 骨料、暗斑和平滑度变化 |

Macro Mask：512、Linear、Mipmap On、Read/Write Off；Base/Aggregate：2048、sRGB、Mipmap On、Read/Write Off。三张纹理均已有 Android/iPhone 压缩配置。

### 8.3 Simple Surface

供 Sidewalk 与 Curb 共用：

- Sidewalk 使用 Gravel Texture。
- Curb 当前无纹理，使用灰色 Tint。
- 每像素最多一次纹理采样。
- 通过 `_TileMeters` 使用米制 UV 密度。

它只覆盖低成本硬质表面，不继续扩展为“全能城市材质 Shader”。

### 8.4 Marking

Marking Shader：

- 无纹理采样。
- 使用 Vertex `Cd.r` 在白色/黄色间插值。
- Queue `Geometry+1`，配合实体标线高度偏移覆盖道路。
- Opaque + Depth Write，避免透明 Decal Overdraw。

仍需在远距离、倾斜摄像机和移动端深度精度下检查 Z-Fighting。

### 8.5 阴影契约

三个 Shader 都没有 `ShadowCaster` Pass；Editor 工具同时强制 Road、Marking、Sidewalk/Curb：

```text
shadowCastingMode = Off
receiveShadows = true
```

这是显式移动端策略：避免低矮道路 Cap、斑马线 Quad 和路缘三角面产生长条自阴影，并减少 ShadowCaster Variant/Draw。代价是这些几何不会向其他物体投影；若未来桥面、高架或高路缘需要投影，应拆独立高成本 Shader/Renderer，不应给全部 CityRoad 恢复 ShadowCaster。

### 8.6 Shader Variant

三个 Shader 没有项目自定义 `shader_feature_local`。Forward 使用：

```text
multi_compile_instancing                       = 2
main light shadow mode                         = 4
soft shadow                                    = 2
fog                                            = 4
```

理论源组合：

```text
Forward   = 2 × 4 × 2 × 4 = 64
DepthOnly = 2
单 Shader 约 66 组
三个 Shader 合计约 198 组
```

该值是平台/URP Strip 前的源码组合估算，单 Shader 低于移动端建议的 200，但三个 Shader 重复了相同全局阴影/雾组合。风险为中等：

- `multi_compile` 仅用于 Instancing、URP 主光阴影和 Fog，没有业务功能组合爆炸。
- 若项目不使用 Screen Shadow、Cascade 或多种 Fog，应通过 URP/Build Strip 收敛，而不是新增本地 Keyword。
- 不应为湿地、积雪、裂纹等继续叠加 A×B×C Keyword；高成本功能应拆 Shader。

Unity MCP 验证三个 Shader 均 `IsSupported = true`、`HasErrors = false`，各 2 Pass。

## 9. Material 合约

| Material | Shader | Instancing | Texture |
|---|---|---|---|
| Asphalt | `PCG/CityRoad/Asphalt` | On | 3 |
| Sidewalk | `PCG/CityRoad/SimpleSurface` | On | 1 |
| Curb | `PCG/CityRoad/SimpleSurface` | On | 0 |
| Marking | `PCG/CityRoad/Marking` | On | 0 |

HDA 类型默认值和 Safe Rebuild 同时固定以下项目路径：

```text
Assets/PCG/Materials/M_PCG_CityRoad_Asphalt.mat
Assets/PCG/Materials/M_PCG_CityRoad_Sidewalk.mat
Assets/PCG/Materials/M_PCG_CityRoad_Curb.mat
Assets/PCG/Materials/M_PCG_CityRoad_Marking.mat
```

目标场景中不再出现 `HEU_DEFAULT_MATERIAL_*`，四个 Material GUID 均有场景引用。

当前耦合点：HDA 保存字符串路径，Editor 工具也保存同一组常量；若移动/重命名 Material，必须同步 HDA 默认值、C# 合约、场景和 Bake，不可只依赖 GUID 自动迁移。

## 10. Unity 场景收敛

### 10.1 序列化规模对比

| 指标 | Phase13 | Phase14 | 变化 |
|---|---:|---:|---:|
| 文件大小 | 25,843,508 B | 5,619,848 B | -78.25% |
| YAML 行数 | 420,086 | 49,824 | -88.14% |
| GameObject | 2,118 | 218 | -89.71% |
| MonoBehaviour | 2,131 | 167 | -92.16% |
| Mesh | 707 | 74 | -89.53% |
| MeshRenderer | 1,409 | 141 | -89.99% |
| MeshFilter | 1,409 | 141 | -89.99% |
| 内联 Material | 707 | 5 | -99.29% |
| MeshCollider | 707 | 1 | -99.86% |

这是 Phase14 最明确的 Unity 数据收益：旧的 464/476 细碎 Part 和 707 个 Collider/默认材质被拓扑 Piece、共享 Material 与单一碰撞输出替代。

### 10.2 提交 14 的序列化 Scene 数据

```text
Root Count          = 6
GameObject          = 218
EditorOnly GO       = 208
Mesh                = 74
Total Mesh Vertices = 39,148
Max Mesh Vertices   = 5,520
UInt32 Mesh         = 0
MeshRenderer        = 141 (68 Enabled / 73 Disabled)
MeshCollider        = 1
```

全部 Mesh 低于 65,535 顶点，当前序列化结果可使用 UInt16 Index。

根对象：

- `Main Camera`
- `Directional Light`
- `Global Volume`
- `CityRoad1`
- `SplineContainer`
- `CityRoad_Overrides`

### 10.3 仍是 Live HDA 场景

`CityRoad1` 和绝大多数 HDA 输出均标记 `EditorOnly`。这意味着：

- 编辑器能预览当前 Cook 输出。
- Player Build 不应包含 Live HDA。
- 没有 Bake 时，道路会被剥离。
- Build Guard 会先阻止该错误构建。

场景当前不在 Build Settings：

```text
Build Index = -1
```

所以本提交只能作为 CityRoad Authoring/Test Scene，不是可发布场景。

## 11. HDA、HIP 与版本管理状态

### 11.1 HDA `.meta` 已修复

Phase13 缺失的：

```text
Assets/PCG/HDA/City/CityRoad.hda.meta
```

已提交，GUID：

```text
67d84be2a5065e14493d6b0d83e29db8
```

与 `PCG_City.unity` 的 `_assetFileObject` 一致，干净检出 HDA 引用阻断已修复。

### 11.2 Terrain 文件夹 `.meta` 已补交

Phase12 遗留的：

```text
Assets/PCG/Materials/Terrain.meta
GUID: 999cc4630092ed345ab160a5a72ce49d
```

已纳入提交，TerrainLayer 文件夹 GUID 现在稳定。该文件不属于 CityRoad 功能，但关闭了 Phase12 的版本管理缺口。

### 11.3 重复 CityRoad HDA

提交在仓库根目录额外新增：

```text
CityRoad.hda
```

两份 HDA 对比：

| 路径 | 大小 | Core 子节点 | V4/V5 | SHA-256 |
|---|---:|---:|---|---|
| `Assets/PCG/HDA/City/CityRoad.hda` | 185,760 | 315 | 有 | `CAAA967F...B0504` |
| `/CityRoad.hda` | 161,995 | 287 | 缺失 V4/V5 | `178617F2...DFFF` |

两者定义相同类型 `pcgbike::CityRoad::1.0`，但内容与时间不同。Unity 只引用 Assets 下的正式 HDA；根目录版本是旧副本。

**状态：[待清理]**

若在 Houdini 中安装根目录副本，可能覆盖/抢占同名类型定义，导致节点缺失或 Cook 结果回退。正式事实源必须保持为 `Assets/PCG/HDA/City/CityRoad.hda`。

### 11.4 Backup 目录

提交只包含 `Assets/PCG/HDA/City/backup.meta`，当前工作区 `backup/` 中另有 159 个 HDA + 159 个 `.meta`，约 20.9 MB，全部未跟踪。

当前 `.gitignore` 只忽略：

```text
Assets/PCG/HDA/backup/
```

并不覆盖：

```text
Assets/PCG/HDA/City/backup/
```

这批备份不得擅自删除，但存在误提交风险。后续应明确保留策略并补正确 Ignore；不能在策略确定前批量清理。

## 12. Cook 与输出合约验证

### 12.1 Houdini Preflight

本次 preflight 结果：

```text
Houdini GUI: not running
18811 RPC: unavailable
3055 MCP: not started/verified
Live Scene tools: unavailable
```

因此没有读取或修改当前 Houdini Live Scene，也没有执行 `allowEditingOfContents()`、Definition 更新或 HIP/HDA 保存。恢复 Houdini 后需要补做完整 MCP preflight 与现场复验。

### 12.2 HDA 静态审计

正式 HDA：

```text
Type           = pcgbike::CityRoad::1.0
Inputs         = 0..4
Max Outputs    = 6
Core Children  = 315
Chunk Params   = removed
V4/V5 Nodes    = present
Material Paths = project defaults
```

### 12.3 隔离 Hython Force Cook

目标提交 HIP 加载后：

- `/obj/CityRoad_DEV` 指向正式 HDA。
- HDA Root 初始 Error / Warning：0 / 0。
- 实例为 Unlocked，`matchesCurrentDefinition = false`。
- Force Cook 后以下输出失败：
  - `OUT_ROAD_SURFACE`
  - `OUT_SIDEWALK_CURB`
  - `OUT_ROAD_COLLISION`
  - `OUT_ROAD_MARKINGS`

共同错误：

```text
CITYROAD_EXTRACT_JUNCTION_STRIPS_V4
CityRoad V5 low-poly Junction winding errors=6
```

仍可 Cook 的输出：

| Output | Points | Primitives | Vertices |
|---|---:|---:|---:|
| `OUT_ROAD_MARKING_POINTS` | 207 | 0 | 0 |
| `OUT_ROAD_CENTERLINE_GRAPH` | 194 | 20 | 141 |
| `OUT_BUILDABLE_BLOCKS` | 0 | 0 | 0 |

这说明场景中的拓扑 Mesh 是之前保存的成功/缓存结果，但目标 HIP/HDA 当前状态无法在隔离环境中稳定重建同一输出。

**状态：[待修复，阻断可重复 Recook/Bake]**

在解决 6 个 Junction Winding Error 前，不应把 Scene Cache 当成可重建事实源。

### 12.4 Output 数量仍未修复

HDA 类型仍声明：

```text
Max Outputs = 6
```

内部仍有七个 Output SOP，`OUT_ROAD_MARKINGS` 使用 Index 6。Unity 当前确实序列化了 Road Markings Geo/Part，但正式 HDA 输出声明仍与内部索引不一致。

**状态：[待修复]**

应把 HDA Output 数量、七个索引、Houdini Engine Unity Geo 输出和 Bake Validator 统一为自动断言。

## 13. 性能、兼容性与扩展边界

### 13.1 CPU / GPU 分工

| 阶段 | CPU / Houdini / Editor | GPU / Unity | 结论 |
|---|---|---|---|
| Authoring | 拓扑、路口、标线、材质归属、Safe Rebuild | Live Preview | 仅开发期 |
| Bake | HEU Bake + C# 合约校验 | Prefab 资源准备 | 工具已实现，资产未交付 |
| Runtime | 禁止 Houdini Cook；Editor C# 不进入 Player | 渲染 Bake Mesh | 目标正确 |
| 大规模城市 | 不应逐帧 CPU 遍历 Piece | 需 Culling/LOD/Indirect | 本提交未实现 |

### 13.2 DrawCall / SetPass

- 当前 Live Preview 有 68 个 Enabled Renderer。
- 共享 4 个 Material，SetPass 已比 707 个默认内联 Material 大幅收敛。
- 但不同拓扑 Piece 使用不同 Mesh，Material Instancing On 不保证合批。
- 需要用 Frame Debugger/Profiler 记录真实 DrawCall、SRP Batcher 与 Instancing 命中。
- 如果 Corridor 数量扩展到数百，需按可见性/材质进行离线合并或 GPU 驱动，而不是恢复每对象 GameObject 方案。

### 13.3 带宽与 RenderPass

本提交：

```text
RendererFeature = 0
自定义 RenderPass = 0
RenderTexture = 0
Blit = 0
MRT = 0
透明标线 = 0
```

没有额外 Tile Flush 或全屏带宽成本。主要 GPU 成本来自：

- 68 个 Renderer/Draw 提交。
- Asphalt 固定 3 次纹理采样。
- Main Light Shadow 接收。
- 道路/标线/路缘实体几何。

### 13.4 Collider

707 个 MeshCollider 已收敛为一个非 Convex、非 Trigger 的 Road Collider。这显著减少组件和 Broadphase 对象，但单个大 MeshCollider 的 Cook/内存/查询成本仍需真机验证。

后续应为 Runtime Bake 输出独立简化碰撞 Mesh；不要直接用最高细分渲染 Mesh。

### 13.5 扩展点

- Corridor/Junction metadata：局部重 Bake、道路规则、LOD 和调试。
- `CityRoad_Overrides`：地编人工覆盖，不被生成流程覆盖。
- Bake Validator：继续加入顶点上限、Bounds、LOD、Collider 面数和移动端资源检查。
- Build Guard：后续可验证 Bake Prefab GUID、版本号和输入 Hash，防止使用过期 Bake。
- Shader 分层：桥面/高架如需 ShadowCaster，应使用独立 Shader/Renderer。

## 14. 验证记录

### 14.1 Git

- 目标提交：`935190f9966e218a5b87342ffccd6da3e462906f`。
- 父提交：`4f7746c8c6c16983e4ca778fd6dbdc5bb3fdbdc7`。
- 34 个文件变化。
- 未修改 Houdini Engine Unity 插件。
- Python Patch AST 全部解析成功。
- 当前工作区已有 `.agents/scripts/Ensure-HoudiniMcp.ps1`、UserSettings 和多项未跟踪资产；本文没有覆盖或计入它们。

### 14.2 Unity MCP

```text
Unity Editor       = 2022.3.62f2
Scene              = Assets/PCG/Scenes/PCG_City.unity
Loaded / Valid     = true / true
Dirty              = true
Root Count         = 5（当前已加载 Dirty 现场）
Build Index        = -1
Playing / Paused   = false / false
Compiling/Updating = false / false
```

Console：

- C# 编译错误：未发现。
- Exception：0。
- CityRoad Scene Save Error：存在，原因是仍在 Live Preview/缺少活动 Bake。
- 最近 Warning 主要来自 Unity Package Export 对 URP Package 依赖的提示，不是 Shader 编译错误。
- AssetDatabase 强制同步刷新后，当前已加载的 Dirty Scene 暂缺 `CityRoad_Overrides`，因此 Live Root Count 为 5；Git 提交与磁盘基线仍包含该根节点，序列化 Root Count 为 6。保存当前 Dirty Scene 前需要确认是否应保留该 Override 根节点。

### 14.3 Shader MCP

| Shader | Supported | Errors | Pass Count | Queue |
|---|---|---|---:|---:|
| Asphalt | Yes | No | 2 | 2000 |
| SimpleSurface | Yes | No | 2 | 2000 |
| Marking | Yes | No | 2 | 2001 |

### 14.4 Houdini

- Houdini GUI 未运行，Live MCP/RPC 未验证。
- 正式 HDA 静态读取成功。
- 隔离 HIP Force Cook 发现 6 个 V5 Junction Winding Error。
- 本次没有保存 HIP/HDA。

## 15. 当前状态矩阵

| 功能 | 状态 | 当前结论 |
|---|---|---|
| Spatial Chunk | 已退役 | 参数/节点移除，旧脚本主动阻断 |
| Corridor/Junction 拓扑输出 | 已实现 | Scene 有 18 Corridor + 7 Junction |
| 稳定拓扑命名/metadata | 已实现 | Role、Piece ID、Junction ID、Level |
| 曲线简化/8°采样 | 已实现 | V4 节点存在，最终 Recook 被 V5 阻断 |
| V4 人行道/路缘石 | 已实现 | Scene 输出已保存，需修复后 Recook |
| V5 Junction Arms | 部分完成 | 目标 Force Cook 出现 6 个 Winding Error |
| V5 Crosswalk/StopLine | 部分完成 | Scene 有输出，隔离 Recook 未通过 |
| CityRoad HDA `.meta` | 已修复 | GUID 与场景一致 |
| Terrain 文件夹 `.meta` | 已修复 | 关闭 Phase12 缺口 |
| 四个 CityRoad Material | 已完成 | Scene 已绑定，无 HEU 默认材质 |
| 三个 URP Shader | 已完成 Phase14 | Unity Supported，无编译错误 |
| Instancing | Shader/Material 支持 | unique Mesh 是否命中批处理待验证 |
| Safe Rebuild | 已实现 | 4 输入、Toggle、材质和强制上传 |
| Live Preview | 已实现 | 68 Presentation Enabled，Backing Disabled |
| Bake Workflow | 已实现工具 | 提交中没有 Bake Prefab |
| Build Guard | 已实现 | 当前场景会被阻断 |
| CityRoad_Overrides | 已建立但 Live 现场有偏差 | 提交/磁盘基线中存在；当前已加载 Dirty Scene 暂缺，保存前需确认 |
| Player Runtime Bake | 未完成 | 无 Prefab/活动 Bake |
| Build Settings | 未接入 | PCG_City Build Index -1 |
| HDA Output 数量 | 未修复 | 声明 6，内部 7 |
| Buildable Blocks | 未完成 | 0 Point / 0 Primitive |
| 根目录重复 HDA | 待清理 | 旧同名类型定义 |
| HDA Backup 管理 | 待处理 | 159 份未跟踪 HDA，Ignore 未覆盖 |
| GPU Indirect/Culling/LOD | 未实现 | 当前仍为 Renderer/GO 驱动 |
| Android/iOS Build | 未执行 | 待验证 |
| 移动端真机 Profiling | 未执行 | Mali/Adreno/Apple GPU 待验证 |

## 16. 下一阶段建议

1. 首先修复 `CITYROAD_EXTRACT_JUNCTION_STRIPS_V4` 的 6 个 V5 Winding Error，要求隔离 HIP 和 Houdini Live Scene 七个输出均 Error/Warning 0。
2. 把 HDA 正式输出数量从 6 修正为 7，并给全部 Output Index 增加自动断言。
3. 删除或迁移仓库根目录旧 `CityRoad.hda`，避免同名 HDA Definition 抢占；正式事实源只保留 Assets 下版本。
4. 给 `topology_v4.py`、`junction_markings_v5.py` 和 `topology_outputs.py` 增加统一 `--dry-run`、`--save`、`--promote-definition`、Expected HIP/HDA 和失败回滚门禁。
5. 修正 `.gitignore` 以覆盖 `Assets/PCG/HDA/City/backup/`；保留现有备份，不在策略确定前批量删除。
6. 在 Cook 修复后运行 `Cook + Validate + Update Bake Selected`，提交 `Assets/PCG/Generated/Road/CityRoad/...` 的 Prefab、Mesh、Collider 和 `.meta`。
7. 保存场景并确认 `CityRoad1_Bake` Active、HDA Source EditorOnly/Renderer Disabled、Console 不再出现 Live Preview Save Error。
8. 为 Bake 增加事务保护：更新现有 Prefab 前先备份/临时 Bake，Post Validation 通过后再替换正式资产。
9. 为 4 输入、25 拓扑道路 Piece、Material GUID、68 可见 Renderer、单 Collider、无重叠 Mesh 和 UInt16 Index 建立 EditMode 自动测试。
10. 用 Frame Debugger/Profiler 记录 DrawCall、SetPass、SRP Batcher、Instancing、Shadow Receive 和 3/1/0 纹理采样成本。
11. 对超长 Corridor 增加拓扑内部分段/LOD 规则，避免 Bounds 过大；不要恢复无语义的全局 Spatial Chunk。
12. 使用简化 Collision Bake，并记录单一大 MeshCollider 在 Android/iOS 上的内存、Cook 与查询成本。
13. 对三个 Shader 配置 URP Variant Stripping，确认单 Shader最终 Variant < 200，并执行 Android/iOS Shader 编译。
14. 完成 Android/iOS IL2CPP Build 与 Mali、Adreno、Apple GPU 真机 Profiling后，再决定是否加入 GPU Culling/Indirect Draw。
