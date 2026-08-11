# Phase 18 开发日志：CityRoad 确定性转角拓扑与跨任务回归门禁

> 文档类型：提交增量快照  
> 记录日期：2026-08-11  
> 目标提交：`d2ad54dafee1b04838646fc8d084a65fa6b85d17`（提交信息：`18`）  
> 父提交：`ddec8e37d0267c581f007a86dabe2bddc233cf3a`（Phase17 文档提交）  
> CityRoad 场景：`Assets/PCG/Scenes/PCG_City.unity`  
> CityRoad HDA：`Assets/PCG/HDA/City/CityRoad.hda`  
> CityRoad HIP：`HoudiniProject/PCG_Track_21.0.440/PCG_Bike_CityRoad.hip`

## 1. 日志范围与证据

本文只记录 Git 提交 `d2ad54d` 相对父提交 `ddec8e3` 的开发增量，不重复 Phase1～Phase17 已记录的 Track、Terrain、CityRoad 单输入、Topology Piece、统一二维边界、Sidewalk Region、Curb、材质纹理和 Live Preview 基础。

Phase18 包含三条主线：

```text
CityRoad 路口范围与移动端转角拓扑
    -> v7：按 Junction Approach 建立精确分区切线和路口所有权
    -> v8：普通道路直角弯固定为五点、两条边界 Rail
    -> v9：最终二维道路边界同样限制为四段/五点
    -> v10：每组角点只生成一条横断面约束
    -> v11：移除直角 Cell 的 Delaunay 扇形，改为确定性 Quad Strip
    -> v12：所有消费者改用同一套清理后的五截面边界

跨任务回归保护
    -> 分层 AGENTS.md 规则
    -> Change Manifest 白名单
    -> Capture / VerifyFast / Persist / Restore
    -> CityRoad 累计行为合约与普通 Python 单元测试

Unity 同步
    -> HDA 重 Cook 后重写 PCG_City Scene 的生成对象与内嵌 Mesh
    -> Sidewalk Region、HEU Backing 和场景序列化规模收敛
```

证据等级：

- **[提交验证]**：读取目标提交元数据、文件清单、stat/numstat、Scene YAML、脚本、合同 JSON 与规则文件。
- **[磁盘 HDA 独立验证]**：使用 Houdini `21.0.440` 的独立 `hython` 进程加载目标 HIP、安装已提交 HDA、创建全新锁定实例并复制生产参数；没有保存 HDA/HIP。
- **[Houdini Live 现场]**：先执行 `Ensure-HoudiniMcp.ps1`；只读检查当前 HIP、实例状态、Cook error/warning 和关键节点，不修改、不更新 Definition、不保存。
- **[Unity 现场]**：使用 Unity MCP 检查 Editor、打开场景、HDA AssetDatabase GUID 和最近 Console；Scene 的提交前后计数则直接来自两版 Git YAML。
- **[自动测试]**：执行新增的 `test_pcg_regression_gate.py`；另分别运行 CityRoad 累计合同的 Live 与 Fresh 模式，保留真实失败结果。
- **[未闭环]**：合同配置与 v11/v12 正式连接不一致、统一 PowerShell 入口未纳入目标提交、正式 Runtime Bake 和移动端真机仍未完成。

本提交没有修改 `Assets/Plugins/HoudiniEngineUnity/`。所有项目规则、HDA、验证器和 Scene 变化均位于项目自有目录。

## 2. 提交概览

| 项目 | 数值 |
|---|---:|
| Commit | `d2ad54dafee1b04838646fc8d084a65fa6b85d17` |
| Author / Date | `liyuan` / 2026-08-11 17:13:20 +08:00 |
| Changed Files | 22 |
| Added / Deleted Lines | `+25028 / -22716` |
| CityRoad HDA | 247,051 → 261,133 bytes（+5.700%） |
| CityRoad HIP | 332,720 → 1,912,562 bytes（+474.826%） |
| Unity Scene | 4,335,996 → 2,982,942 bytes（-31.205%） |
| CityRoadCore Children | 167 → 177（+10） |
| Shader / Material / RendererFeature / RenderPass | 0 个新增或修改 |
| Houdini Engine Unity 插件 | 0 个文件修改 |

提交文件分组：

1. 协作与防回归规则：
   - `AGENTS.md`
   - `Assets/PCG/AGENTS.md` 及 `.meta`
   - `Assets/PCG/HDA/AGENTS.md` 及 `.meta`
   - `HoudiniProject/PCG_Track_21.0.440/AGENTS.md`
2. 正式资产：
   - `Assets/PCG/HDA/City/CityRoad.hda`
   - `HoudiniProject/PCG_Track_21.0.440/PCG_Bike_CityRoad.hip`
   - `Assets/PCG/Scenes/PCG_City.unity`
3. 行为合同与测试：
   - `scripts/contracts/change_manifest.schema.json`
   - `scripts/contracts/cityroad_contract.json`
   - `scripts/contracts/examples/cityroad_v10.example.json`
   - `scripts/tests/test_pcg_regression_gate.py`
   - `scripts/tools/pcg_regression_gate.py`
   - `scripts/tools/validate_cityroad_contract.py`
   - `scripts/tools/README.md`
4. 一次性迁移/审计记录：
   - `patch_cityroad_junction_extent_v7.py`
   - `patch_cityroad_mobile_corner_v8.py`
   - `patch_cityroad_final_boundary_mobile_v9.py`
   - `patch_cityroad_corner_section_constraints_v10.py`
   - `patch_cityroad_deterministic_corner_strips_v11.py`
   - `patch_cityroad_shared_corner_boundary_v12.py`

这些 `patch_*_vN.py` 只说明本提交的迁移过程和设计意图，不是当前实现事实源，也不得在后续任务中按 v7→v12 顺序重放。当前实现事实源仍是正式 HDA/HIP，行为事实源应由独立累计合同提供。

## 3. v7：精确 Junction 范围与道路标线截断

### 3.1 原问题

Phase17 已用统一二维边界生成 Road、Sidewalk 和 Curb，但 Junction 的“几何范围”和“道路/标线归属”仍可能依赖最近旧片的 metadata。路口 Arm 的可见长度、横道线/停止线深度和最终道路分区线没有统一契约时，会出现：

- Junction Piece 没覆盖完整横道线或停止线。
- Corridor 纵向边线侵入 Junction。
- 二维三角形被最近旧道路错误标为 Corridor 或 Junction。
- 同一个路口的表面、标线和 Piece Bounds 不能稳定对账。

### 3.2 Junction 分区切线

新增节点链：

```text
CITYROAD_JUNCTION_APPROACH_METADATA
    -> CITYROAD_BUILD_JUNCTION_PARTITION_CUTS_V7
    -> CITYROAD_MERGE_ROAD_BOUNDARY_PARTITIONS_V7
    -> CITYROAD_FUSE_ROAD_BOUNDARY_PARTITIONS_V7
    -> ROAD_PLANAR_TRIANGULATE_FINAL_BOUNDARY
```

`CITYROAD_BUILD_JUNCTION_PARTITION_CUTS_V7` 为每个精确 Junction Approach 生成一条横跨道路的约束线。切线位置从 Mouth 沿 Approach outward 方向外推，距离由当前标线参数共同决定：

```text
extension = Crosswalk Setback
          + Crosswalk Depth
          + Stop Line Gap
          + Stop Line Width
          + max(0.25, Junction Sample Spacing * 0.5)
```

这使道路几何分区范围覆盖完整路口标线，而不是使用固定魔数。随后把最终道路外轮廓、Junction 切线和 v10 转角横断面约束 Merge/Fuse 后再进入 `Triangulate 2D`，避免 Corridor/Junction 接缝产生未焊接端点。

### 3.3 精确 Junction 所有权

`ROAD_PLANAR_METADATA_FROM_LEGACY` 增加 `CITYROAD_V7_EXACT_JUNCTION_OWNERSHIP` 逻辑：

- 旧道路只提供基础高度、Road ID、Level、宽度等参考 metadata。
- Junction Core/Arm Helper Polygon 负责最终空间所有权。
- Core 优先级高于 Arm；命中 Helper 的三角形强制标为 `junction_patch`。
- 未命中 Helper 的面保持 Corridor 归属，`junction_id = -1`。
- 同时为 Unity 手性转换准备 `road_planar_reverse_for_unity` 分组。

### 3.4 标线边界

v7 在静态标线生成中加入 Junction Surface/Approach Helper 判断：

- Corridor 纵向标线在 Junction 扩展区截断。
- Junction 内 Crosswalk、Stop Line 与 Road Surface Bounds 对账。
- 两车道配置不生成中央 Lane Divider。
- `marking_boundary_gap_max` 和 intrusion count 成为可验证 detail metadata。

目标 HDA 新锁定实例的测试图结果：

| 指标 | 数值 |
|---|---:|
| Junction Partition Cuts | 23 |
| Invalid Partition Cuts | 0 |
| Expected / Actual Approaches | 23 / 23 |
| Junction Arm Extent Errors | 0 |
| Longitudinal Marking Intrusions | 0 |
| Marking Boundary Gap Max | 0.0 m |

## 4. v8：移动端五点直角弯与连续边线

### 4.1 固定采样预算

Phase16/17 的自适应圆角会按弧长、内外半径和采样间距决定段数。对移动端道路 Mesh，直角弯不需要无限追求圆滑；更重要的是稳定控制顶点数、三角形长宽比和跨宽连接数量。

v8 修改现有节点而非增加新的超级节点：

- `ROAD_ROUND_CENTERLINE_CORNERS`：圆角最多 4 段。
- 右角在容差范围内固定为 4 段，即每侧 5 个采样点。
- `ROAD_CLASSIFY_CORNER_TOPOLOGY`：固定为一对边界 Rail，不再随宽度派生多条内部 Rail。
- `ROAD_BUILD_ADAPTIVE_CORNER_SURFACE`：使用左右两条边界生成角部，禁止额外跨宽 Strip。

目标 HDA 测试图：

| 指标 | 数值 |
|---|---:|
| Rounded Corner Max Segments | 4 |
| Adaptive Corner Max Half Strips | 1 |
| Cross-width Boundary Rails | 2 |
| Points Per Corner Side | 5 |
| Extra Cross-width Strips | 0 |

### 4.2 连续道路边线

`CITYROAD_BUILD_STATIC_MARKING_MESH` 的边线使用共享端点和连续边缘逻辑，避免每个角部小 Cell 独立生成一段边线。目标测试图的 `edge_line_join_error_max = 0`，同时延续 v7 的 Junction intrusion = 0。

性能意义：

- Houdini Cook 阶段直接限制几何预算，减少后续 Triangulate、Pack、HAPI 传输和 Unity Mesh 序列化规模。
- 运行时不执行该 VEX；移动端只消费 Bake/Scene 中的 Unity Mesh。
- 固定五点是当前直角弯拓扑合同，不代表所有曲率都被强制成低模折线；非直角仍保留上限内的自适应段数。

## 5. v9：最终二维边界同步移动端预算

### 5.1 为什么 v8 仍不够

v8 已限制自适应道路表面，但 Phase17 后段的 `ROAD_UNION_ROUND_FINAL_BOUNDARY` 会独立重建最终闭合边界，旧逻辑每个角最多可生成 12 段。Unity 实际消费的是最终二维边界再三角化的结果，因此只优化上游 Adaptive Surface 不能保证最终 Mesh 顶点预算。

### 5.2 最终边界合同

v9 在 `ROAD_UNION_ROUND_FINAL_BOUNDARY` 中加入硬预算：

- 任意最终圆角最多 4 段。
- 75°～105° 范围的近直角固定为 4 段。
- 每侧固定语义为 5 个边界点。
- 输出 `final_boundary_mobile_*` detail metadata 和 `cityroad_final_boundary_patch = V9`。

目标 HDA 测试图：

| 指标 | 数值 |
|---|---:|
| Final Boundary Max Segments | 4 |
| Final Boundary Points Per Side | 5 |
| Rounded Corners | 46 |
| Right-angle Corners | 24 |
| Patch Marker | `V9` |

这一步使“上游转角表面”和“最终 Unity 道路孔洞边界”共享同一移动端段数上限，但仍没有解决全局 Delaunay 在五点间选择对角线的不确定性；该问题由 v10/v11 继续处理。

## 6. v10：唯一横断面约束

### 6.1 道路角部约束

新增 `CITYROAD_BUILD_CORNER_SECTION_CONSTRAINTS_V10`：

```text
Input 0 = ROAD_BUILD_ADAPTIVE_CORNER_SURFACE
Input 1 = 最终道路边界
Output  = 每对左右角点的一条 cross-road polyline
```

一个四段直角弯有五组左右边界采样。v10 为每组采样只生成一条唯一横断线，并将端点吸附到真正参与最终 Triangulate 2D 的边界。约束线与 v7 Junction Partition Cuts 一起 Merge/Fuse，使全局二维三角化必须保留作者定义的截面。

目标 HDA 测试图：

| 指标 | 数值 |
|---|---:|
| Corner Section Constraints | 5 |
| Duplicate Constraints Removed | 3 |
| Lines Per Sample | 1 |
| Invalid Quads | 0 |
| Max Boundary Snap Distance | 0.19999999 m |

### 6.2 Sidewalk 约束

新增：

```text
CITYROAD_BUILD_CORNER_SECTION_CONSTRAINTS_V10
    -> CITYROAD_BUILD_SIDEWALK_SECTION_CONSTRAINTS_V10
    -> SIDEWALK_PLANAR_CONSTRAINT_MERGE
    -> SIDEWALK_PLANAR_TRIANGULATE
    -> CITYROAD_FUSE_SIDEWALK_TRIANGULATION_V10
```

道路五个截面向外延伸到 Sidewalk Site Boundary，为角部内外两侧分别建立连接约束。Fuse 节点负责把 Triangulate 结果中的重合端点焊接，避免后续 Sidewalk 分类得到悬空 Connector 或重复边。

v10 仍让全局 `Triangulate 2D` 决定每个 Cell 内部的对角线，因此“约束线存在”不等于“每个角部一定生成相同的两三角 Quad”。

## 7. v11：确定性 Road/Sidewalk Quad Strip

### 7.1 从约束 Delaunay 到显式拓扑

Spline 微调后，全局 Triangulate 2D 可能在近共圆点间切换对角线，重新出现扇形三角或细长 Cell。v11 保留全局二维三角化处理大面积道路/人行道，只替换 `road_corner_topology_class = 2` 的直角区域：

```text
Global Triangulate 2D
    -> 删除当前直角 Cell 内的 Delaunay 三角形
    -> 读取作者定义的五组 Section
    -> 相邻 Section 两两连接成 4 个 Quad
    -> 每 Quad 固定拆成 2 个 Triangle
    -> 保留其余平面三角化结果
```

新增节点：

- `CITYROAD_REPLACE_CORNER_WITH_QUAD_STRIPS_V11`
- `CITYROAD_REPLACE_SIDEWALK_CORNER_WITH_QUAD_STRIPS_V11`

道路节点输入最终 Road Triangulate、Adaptive Corner Surface 和 v10 Section；Sidewalk 节点输入 v10 Fuse 后的 Sidewalk Triangulate、Adaptive Corner、Sidewalk Section 和 Road Section。

### 7.2 目标拓扑统计

| 指标 | Road | Sidewalk |
|---|---:|---:|
| Quad Count | 4 | 8 |
| Triangle Count | 8 | 16 |
| Removed Delaunay Triangles | 8 | 8 |
| Invalid Quad Count | 0 | 0 |
| Missing Connector Count | - | 0 |
| Lines Per Section | 1 | 1 |
| Patch Marker | `V11` | `V11` |

当前测试图只有 1 个普通道路自适应直角弯，因此 Road 为 4 个 Quad；Sidewalk 分内外两侧，共 8 个 Quad。该节点输出专用 Primitive Group：

- `corner_quad_strip_v11`
- `sidewalk_corner_quad_strip_v11`

这组 Group 是调试和累计合同的扩展点，可用于检查连通分量、重复质心、边数、顶点数和每角固定 Cell 数。

## 8. v12：共享五截面最终边界

### 8.1 原问题

v11 替换了四个内部 Road Cell，但 `ROAD_UNION_ROUND_FINAL_BOUNDARY` 在第一/第五截面前后仍可能保留小于 0.5 m 的短边界点簇。Road、Curb、Sidewalk 如果各自消费或清理这些点，会形成：

- 端部三条近乎平行的 Cap Edge。
- Curb 与 Road 的角点不完全重合。
- Sidewalk 孔洞边界和道路分类边界分叉。
- 相同五截面在不同消费者中产生不同点序。

### 8.2 Snap + Fuse

新增：

```text
ROAD_UNION_ROUND_FINAL_BOUNDARY
    + ROAD_BUILD_ADAPTIVE_CORNER_SURFACE
    -> CITYROAD_SNAP_FINAL_BOUNDARY_TO_CORNER_SECTIONS_V12
    -> CITYROAD_FUSE_FINAL_BOUNDARY_CORNER_SECTIONS_V12
```

v12 只处理该直角弯对应的 10 个作者 Rail 目标点：将端部短点簇吸附到五组左右截面端点，再 Fuse 重复点。它不改变 HDA 公共参数，也不重建全网。

清理后的共享边界同时接入：

1. `ROAD_PLANAR_CLASSIFY_FROM_FINAL_BOUNDARY`
2. `SIDEWALK_TOPOLOGY_VALIDATE`
3. `SIDEWALK_PLANAR_ROAD_BOUNDARY_CLEAN`
4. `SIDEWALK_PLANAR_CLASSIFY`
5. `SIDEWALK_SITE_BOUNDARY_FROM_ROAD`
6. `ROAD_UNION_BOUNDARY_WALLS`
7. `ROAD_UNION_SHIFT_PIECES_FOR_TRIANGULATION`
8. `CURB_SIDEWALK_BUILD_FROM_FINAL_BOUNDARY`

目标 HDA 测试图：

| 指标 | 数值 |
|---|---:|
| Authored Rail Targets | 10 |
| Snapped Point Operations | 50 |
| Road Sections | 5 |
| Boundary Points After Fuse | 198 |
| Road Strip Triangles | 8 |
| Sidewalk Strip Triangles | 16 |
| Patch Marker | `V12` |

“Snapped Point Operations = 50”是处理计数，不表示边界新增 50 个点；Fuse 后最终共享边界仍为 198 点。

## 9. 正式 HDA、HIP 与公共接口

### 9.1 节点增量

| 指标 | Phase17 | Phase18 |
|---|---:|---:|
| CityRoadCore Children | 167 | 177 |
| HDA Inputs | 0 | 0 |
| HDA Outputs | 6 | 6 |
| Public Interface SHA-256 | - | `6efd6f02eb08296b78ba60c75d8d35af8486ae1e385a71d963c165034eee555a` |

新增 10 个节点正好对应：

- v7：Partition Cuts、Constraint Merge、Fuse，共 3 个。
- v10：Road Section、Sidewalk Section、Sidewalk Fuse，共 3 个。
- v11：Road/Sidewalk 确定性 Strip，共 2 个。
- v12：Shared Boundary Snap/Fuse，共 2 个。

v8/v9 只增量修改现有 Wrangle，不增加节点。独立 `hython` 新实例为锁定状态、`matchesCurrentDefinition = true`，说明上述 177 节点存在于已提交正式 HDA，而不是只存在于当前 GUI 的可编辑 Contents。

### 9.2 文件指纹

| 文件 | Phase17 SHA-256 | Phase18 SHA-256 |
|---|---|---|
| CityRoad HDA | `90CB5ABAF38EFC6BB8B4EEDED1756F34D01AF02EBDB910103B0A71C66CC56442` | `C041A876FADD115C5E154C03AAE85EB0FC5961703B98F6F275A493FD2EBDED62` |
| CityRoad HIP | `F618CEF2D67644E9363B2194F81497035978713289676F45C3DBA8F7C3E1442A` | `368C79C9A6844DDE32FCA8F1C3BBF5AE1EDBD63572817033E2D4CD3DB7834EE4` |
| PCG_City Scene | - | `980AA89BD3FF79A11658F8A8AE7475055D8496C8609702122599204B429D3FD7` |

HIP 从约 325 KiB 增长到约 1.82 MiB。目标提交的磁盘 HDA 已包含正式网络，但 HIP 大幅增长仍应在后续检查是否保存了额外可编辑 Contents、测试节点状态或 Cook 数据；仅凭文件变大不能当作功能证据。

### 9.3 正式输出

独立锁定实例、复制生产参数后的输出：

| Output | Points | Primitives | Vertices | Error | Warning |
|---|---:|---:|---:|---:|---:|
| `OUT_ROAD_SURFACE` | 21 | 21 | 21 | 0 | 0 |
| `OUT_SIDEWALK_CURB` | 13 | 13 | 13 | 0 | 0 |
| `OUT_ROAD_COLLISION` | 255 | 274 | 822 | 0 | 0 |
| `OUT_ROAD_MARKINGS` | 21 | 21 | 21 | 0 | 0 |

Road、Sidewalk/Curb 和 Markings 的正式输出包含 Packed Piece，因此这里的 Point/Primitive 主要反映 HDA 输出分包数量，不等同于解包后 Unity Mesh 的真实顶点/三角形数。Collision 输出是展开几何，不能直接与前三者横向比较。

## 10. Unity Scene 重 Cook 结果

### 10.1 序列化规模

| 指标 | Phase17 Scene | Phase18 Scene | 变化 |
|---|---:|---:|---:|
| 文件大小 | 4,335,996 bytes | 2,982,942 bytes | -31.205% |
| YAML Lines | 48,505 | 45,529 | -2,976 |
| GameObject | 227 | 209 | -18 |
| Transform | 227 | 209 | -18 |
| MeshFilter | 147 | 135 | -12 |
| MeshRenderer | 147 | 135 | -12 |
| MeshCollider | 1 | 1 | 0 |
| Serialized Mesh | 77 | 71 | -6 |
| Serialized Material | 5 | 5 | 0 |

这说明 v7～v12 的几何变化和重新分区后，Unity Live Scene 的生成对象与内嵌 Mesh 总量下降。但该 Scene 仍是 Houdini Engine 开发期生成/Live Preview 数据，不是最终移动端 Bake 资产。

### 10.2 Presentation 对象

| 类型 | Phase17 | Phase18 |
|---|---:|---:|
| Corridor RoadSurface | 18 | 18 |
| Corridor RoadMarkings | 18 | 18 |
| Junction RoadSurface | 7 | 7 |
| Junction RoadMarkings | 7 | 7 |
| SidewalkRegion Sidewalk | 17 | 11 |
| SidewalkRegion Curb | 4 | 4 |
| `CityRoadCore_OUT_*` HEU Backing GameObject | 149 | 137 |

GameObject 减少 18 个，正好由 Sidewalk Presentation 减少 6 个、HEU Backing 减少 12 个组成。Corridor/Junction 数量不变，说明道路分包主结构没有被 v11/v12 意外吞并。

Junction 名称从旧的 `2055..2061` 演变为 `2056..2062`，数量仍为 7。该变化属于重 Cook 后的 Piece ID/实例命名变化；外部系统不得把这些自动生成的具体数字当作稳定业务 ID。

### 10.3 材质、Shader 与运行时

本提交没有修改任何 Material、Texture、Shader、RendererFeature 或 RenderPass：

- Phase17 的 Road/Sidewalk/Curb 材质继续使用。
- 没有新增 Shader keyword，Variant 数量不变。
- 没有新增全屏 Pass、RenderTexture、MRT 或 Blit。
- Instancing 能力和材质开关没有变化。
- Unity Scene 仍由大量 MeshRenderer 表达开发预览，不是 `DrawMeshInstancedIndirect`/GPU Culling 的最终移动端结构。

## 11. 跨任务回归门禁

### 11.1 分层规则

提交新增/扩展四层规则文件：

- 根 `AGENTS.md`：定义当前事实源、硬边界、Capture→VerifyFast→VerifyFull、历史 patch 隔离和双端验证。
- `Assets/PCG/AGENTS.md`：约束 Unity 资产、URP、Shader Variant、大规模实例和移动端带宽。
- `Assets/PCG/HDA/AGENTS.md`：约束 Definition、公共接口、备份恢复、Fresh Locked Instance 和 Unity 引用。
- Houdini 工程 `AGENTS.md`：约束 Live Scene、SOP 优先、patch 幂等/回滚和累计合同。

关键原则从“本次功能能 Cook”升级为：任何新改动都必须证明没有破坏已经修复过的全部行为。

### 11.2 Change Manifest

`change_manifest.schema.json` 定义任务白名单：

- 可修改文件。
- 可修改/新增/删除节点。
- 可修改连接和参数。
- 可修改公共参数接口。
- 是否允许 Output 变化。
- 允许的精确 Warning 签名。
- 必须执行的累计 Contract ID。

`cityroad_v10.example.json` 演示只允许修改 v10 三个节点和少量连接，并要求回归 v7、v8、v9、v10。它是示例 manifest，不是 Phase18 所有 v7～v12 变化的完整历史 manifest。

### 11.3 Gate 生命周期

`pcg_regression_gate.py` 实现四个底层阶段：

```text
Capture
    -> 读取 Live 节点/接口/连接/参数/输出/诊断
    -> 核对 HDA、HIP、实例身份
    -> 记录 Git 状态和文件 SHA-256
    -> 逐字节备份 scoped HDA/HIP

VerifyFast
    -> 与 Capture 快照比较
    -> 白名单外节点、连接、参数、公共接口、输出和新 Warning 变化即失败

Persist
    -> 仅持久化已经验证过的 Live Scene
    -> updateFromNode + 保存 HIP

Restore
    -> 只从本次 Capture 备份恢复 scoped HDA/HIP
    -> 校验备份哈希并重新加载
```

普通 Python 单元测试覆盖 7 类比较行为：

1. 未变化快照通过。
2. 白名单内 v10 参数变化通过。
3. v8 非白名单回归被阻止。
4. 非白名单连接变化被阻止。
5. 公共参数变化被阻止。
6. 新 Houdini Warning 被阻止。
7. Output 变化必须显式授权。

本次实测：`Ran 7 tests ... OK`。

### 11.4 CityRoad 累计合同

`cityroad_contract.json` 和 `validate_cityroad_contract.py` 设计为不导入历史 patch，当前登记 17 个 Contract ID，覆盖：

- Public Interface 与正式 Output 网络。
- Phase13 Shading/Chunk。
- Phase14 Topology Output。
- Phase15 Single Input。
- Phase16 Adaptive Corner。
- Phase17 Final Boundary。
- v7 Junction Extent/Marking Clip。
- v8 Mobile Corner/Edge Line。
- v9 Final Boundary Budget。
- v10 Road/Sidewalk Section。
- Output 无诊断、几何合法性和 Winding。

验证器支持：

- Live 实例累计验证。
- 独立进程创建全新锁定实例并复制生产配置。
- 公共接口 SHA-256。
- 必需节点、连接和 VEX Marker。
- Output Force Cook、非空几何和 Warning。
- Phase17/v7～v10 的行为统计。

## 12. 回归门禁的未闭环问题

### 12.1 累计合同落后于正式 v11 网络

提交中的正式 HDA 连接为：

```text
SIDEWALK_PLANAR_CLASSIFY[0]
    = CITYROAD_REPLACE_SIDEWALK_CORNER_WITH_QUAD_STRIPS_V11
```

但 `cityroad_contract.json` 仍要求：

```text
SIDEWALK_PLANAR_CLASSIFY[0]
    = CITYROAD_FUSE_SIDEWALK_TRIANGULATION_V10
```

因此目标提交的累计验证器在 Live 和 Fresh Locked Instance 两种模式下都失败：

```text
CONTRACT_FAIL: CityRoad connection changed:
SIDEWALK_PLANAR_CLASSIFY[0]=CITYROAD_REPLACE_SIDEWALK_CORNER_WITH_QUAD_STRIPS_V11
expected=CITYROAD_FUSE_SIDEWALK_TRIANGULATION_V10
```

这不是当前未提交现场造成的差异；独立进程直接读取已提交 HDA/HIP 也可稳定复现。结果是：

- HDA 正式输出可以 Cook 且 0 error/0 warning。
- 但提交声称的累计 VerifyFull 无法通过。
- v11/v12 节点、连接、Marker 和几何统计没有进入 `cityroad_contract.json` 的 required nodes/connections/contracts。
- 7 个普通单元测试只验证快照比较器，不能发现“合同文件本身落后于正式网络”。

状态：**[未闭环，P0]**。

### 12.2 统一 PowerShell 入口没有进入提交

规则与 `scripts/tools/README.md` 都要求调用：

```powershell
.agents/scripts/Invoke-PcgRegression.ps1
```

但该文件不在提交 `d2ad54d` 的 22 个变更文件中；当前工作区虽存在同名未跟踪文件，但不能把未跟踪现场当作提交“18”的交付内容。单独 checkout 目标提交时，文档中的统一入口缺失。

状态：**[未闭环，P0]**。

### 12.3 历史 patch 默认仍会保存

六个本次入库的迁移脚本多数声明：

```python
apply_live_patch(save: bool = True, ...)
```

而同一提交新增的规则要求新 patch 默认 `save=False`。这些脚本已经完成迁移，只应作为审计记录；后续不得直接运行。若继续保留可执行入口，应把默认保存关闭，并让持久化只通过 VerifyFull。

状态：**[风险，P1]**。

## 13. 当前现场与目标提交的边界

### 13.1 Houdini Live Scene

本次文档审计开始时：

- Houdini `21.0.440`，RPC `18811` connected。
- MCP `3055` healthy，工具可发现。
- 当前 HIP 为目标 `PCG_Bike_CityRoad.hip`。
- `/obj/CityRoad_DEV` 当前为 unlocked。
- `matchesCurrentDefinition = false`。
- HIP 报告 `hasUnsavedChanges = true`。
- 当前 CityRoadCore 为 177 个节点。

这表示当前 Live Scene 与磁盘 HDA 不能互相覆盖。本文没有调用 `allowEditingOfContents()`、`updateFromNode()`、Save 或 Restore，也没有擅自决定 Live 与磁盘哪一侧应当保留。提交几何统计全部来自独立 Fresh Locked Instance，避免把当前 Dirty Live Scene 冒充 Git 目标状态。

Live 全网只读扫描没有 Cook error 节点，但 `CITYROAD_TOPOLOGY_CLASSIFY_ROAD` 及其内部 VOP 显示同一条道路 Winding Warning。Force Cook 后 detail metadata 为 down-facing 269、up-facing 0、winding error 0，Warning 与计数不一致，需单独清理/复核 Warning 触发逻辑。

### 13.2 Unity Editor

本次现场检查：

- Unity `2022.3.62f2`。
- 未播放、未暂停、未编译、未刷新 AssetDatabase。
- 当前打开 `Assets/PCG/Scenes/PCG_City.unity`，Loaded/Valid，Root Count 6。
- Editor 内 Scene 为 Dirty；本次文档任务不保存 Scene。
- AssetDatabase 唯一找到 `Assets/PCG/HDA/City/CityRoad.hda`。
- HDA GUID：`67d84be2a5065e14493d6b0d83e29db8`。
- 最近 10 分钟 Console Error = 0，Warning = 0。

Scene YAML 的 Phase17/Phase18 计数来自 Git 磁盘版本，不将 Dirty Editor 中未保存的对象状态计入提交“18”。

### 13.3 工作区保护

写日志前已有未跟踪内容包括：

- `.agents/scripts/Invoke-PcgRegression.ps1`。
- Terrain Shader 目录。
- Track/Terrain 操作文档与 Word 临时文件。
- `Assets/PCG/Scripts/Tests/`。
- 多个 FBX 资产及 `.meta`。

这些内容都没有被移动、覆盖、暂存或计入 Phase18 开发成果。本文只新增 Phase18 Markdown 与其 `.meta`。

## 14. 性能、渲染与移动端评估

### 14.1 CPU 与 GPU 分工

| 阶段 | 当前职责 | Phase18 影响 |
|---|---|---|
| Houdini CPU / 编辑期 | Junction 分区、二维约束、Delaunay、确定性 Strip、Curb/Sidewalk、Pack | Cook 节点增加，但顶点预算和角部拓扑更稳定 |
| HAPI / Unity Editor | 传输 Packed Piece、生成 Mesh/GameObject、序列化 Scene | Scene 缩小 31.205%，Renderer 减少 12 个 |
| Unity Runtime CPU | 当前仍管理开发期生成的 GameObject/MeshRenderer | 未形成最终 Chunk/Bake 运行时数据 |
| Unity Runtime GPU | URP 绘制 Road/Sidewalk/Curb/Markings | Shader/Pass/Variant 无变化 |

v11 的“全局三角化 + 局部替换”比简单 Triangulate 多一次角部判定与重建，但成本发生在编辑期 Cook；它换来确定性 Mesh、减少重 Cook 拓扑漂移和更可控的移动端顶点预算，当前取舍合理。

### 14.2 带宽与 DrawCall

- 本提交没有增加 RT、全屏 Pass 或纹理采样，Tile-Based GPU 带宽没有新增渲染管线负担。
- Scene 中 MeshRenderer 从 147 降至 135，开发预览 DrawCall 上限有所下降，但仍不是最终移动端验收。
- 21 Road Pack、13 Sidewalk/Curb Pack 和 21 Marking Pack 在 Unity 展开后仍形成大量对象；后续 Bake 应按 Chunk/Material 合并，并保留地编可覆盖边界。
- Collision 是独立输出，运行时应按 Chunk 生成简化 MeshCollider，不能直接复制所有渲染拓扑。

### 14.3 Shader Variant 与兼容性

- 新增 Shader keyword：0。
- 新增 Shader Variant 风险：0。
- GPU Instancing 配置：无变化。
- Geometry Shader、Compute Shader、Indirect Draw：本阶段均未新增。
- HDA 使用普通 SOP/VEX、Triangulate 2D、Fuse 和 Attribute Wrangle；运行时不依赖 Houdini Cook，Android/iOS 兼容性取决于后续 Bake 后 Unity Mesh/Material。

## 15. 问题与状态变化

### 15.1 已解决当前测试图：Junction Surface 未覆盖完整标线

23 个 Approach 生成 23 条有效分区切线；Arm Extent Error、Marking Intrusion 和 Boundary Gap 都为 0。

### 15.2 已解决当前测试图：普通道路直角弯顶点预算不稳定

上游 Adaptive Corner 和最终 Road Boundary 都限制为 4 段/5 点；不再由 12 段最终边界抵消移动端优化。

### 15.3 已解决当前测试图：直角 Cell 的 Delaunay 扇形

Road 使用 4 Quad/8 Triangle，Sidewalk 使用 8 Quad/16 Triangle；Invalid Quad 与 Missing Connector 均为 0。

### 15.4 已解决当前测试图：Road/Curb/Sidewalk 消费不同角点

v12 Snap/Fuse 后，8 个最终边界消费者共享同一套 198 点边界。

### 15.5 已建立：跨任务快照比较与失败恢复框架

Manifest、Capture、VerifyFast、Persist、Restore、文件哈希、备份和普通单元测试已存在。

### 15.6 未解决：累计合同无法验证正式 v11/v12 网络

合同仍要求 v10 旧连接；Live/Fresh 都失败。必须先修复合同和新增 v11/v12 Contract，才能宣称 VerifyFull 闭环。

### 15.7 未解决：统一入口脚本未进入目标提交

当前只有未跟踪工作区副本，目标提交不可独立复现 README 中的统一命令。

### 15.8 未解决：当前 Live Scene 与 Definition 不一致

Live 为 unlocked/dirty/non-matching。下一次 HDA 任务必须先人工确认事实源并 Capture，禁止直接用磁盘覆盖 Live 或反向更新 Definition。

### 15.9 未解决：Runtime Bake

Unity Scene 仍是开发期 Cook/Live Preview 表示；没有可版本化 Chunk Bake、重生成保护、艺术覆盖清单和移动端真机性能数据。

### 15.10 延续风险：自动生成 Piece ID 不稳定

Junction 名称整体平移一位说明重 Cook 可改变实例名。外部引用应使用稳定 metadata/GUID 映射，不能绑定 `CityRoad_Junction_L0_20xx_*` 的具体数字。

## 16. 验证记录

### 16.1 Git

- 目标提交唯一匹配标题 `18`：通过。
- 父提交：`ddec8e3`。
- 22 个文件变化，未修改插件：通过。
- HDA/HIP/Scene 当前磁盘文件与目标提交一致：通过。
- 统一入口 `Invoke-PcgRegression.ps1` 是否属于提交：失败，目标提交未跟踪该文件。

### 16.2 Houdini

- MCP Preflight：通过。
- Fresh Locked HDA：锁定、匹配正式 Definition。
- Public Interface SHA-256：匹配合同。
- CityRoadCore Children：177。
- 四个正式输出：0 Error / 0 Warning。
- v7～v12 关键统计：通过本文所列测试图数值。
- CityRoad 累计合同 Live：失败，v11 实际连接与 v10 旧合同不一致。
- CityRoad 累计合同 Fresh：同一位置失败，可稳定复现。
- 当前 Live Scene：Dirty/Unlocked/Non-matching，仅记录，未保存。

### 16.3 自动测试

```text
python scripts/tests/test_pcg_regression_gate.py
.......
Ran 7 tests in 0.001s
OK
```

这 7 个测试证明快照比较器的白名单行为正确，不证明 CityRoad 累计合同与正式 HDA 同步。

### 16.4 Unity

- Editor 就绪：通过。
- `PCG_City` Loaded/Valid：通过。
- Scene 当前 Dirty：已记录，本任务未保存。
- CityRoad HDA AssetDatabase 路径/GUID：通过。
- 最近 10 分钟 Console Error/Warning：0/0。
- 正式 Runtime Bake：未验证。
- Android/iOS/Mali/Adreno/Apple GPU 真机：未验证。

## 17. 当前状态矩阵

| 功能 | 状态 | 当前结论 |
|---|---|---|
| v7 Junction Partition | 已完成当前测试图 | 23/23 Approach，0 Invalid |
| v7 Marking Clip | 已完成当前测试图 | 0 Intrusion，0 Boundary Gap |
| v8 Mobile Corner Budget | 已完成当前测试图 | 4 段、5 点、2 Rail、0 Extra Strip |
| v9 Final Boundary Budget | 已完成当前测试图 | 最终边界同样最多 4 段 |
| v10 Road Section | 已完成当前测试图 | 5 条唯一截面，0 Invalid |
| v10 Sidewalk Section | 已接入 | 进入 Sidewalk Triangulate/Fuse |
| v11 Deterministic Road Strip | 已完成当前测试图 | 4 Quad / 8 Triangle |
| v11 Deterministic Sidewalk Strip | 已完成当前测试图 | 8 Quad / 16 Triangle |
| v12 Shared Boundary | 已完成当前测试图 | 8 个消费者共享清理边界 |
| HDA Public Interface | 未变化 | 0 Input / 6 Output，Hash 稳定 |
| Fresh Locked Outputs | 通过 | 四个正式 Output 0 Error/Warning |
| Snapshot Compare Unit Tests | 通过 | 7/7 |
| CityRoad Cumulative Contract | **失败** | 合同仍要求 v10 旧连接 |
| Unified PowerShell Entry | **未交付到提交** | 当前仅有未跟踪副本 |
| Current Houdini Live Baseline | 需保护 | Dirty/Unlocked/Non-matching |
| Unity Scene Re-cook | 已提交 | Scene 缩小 31.205% |
| Runtime Bake | 未实现 | 仍为 Live Preview/Scene 数据 |
| Mobile Device Validation | 未执行 | 无真机性能和兼容性结论 |

## 18. 下一阶段建议顺序

1. **P0：修复累计合同与正式网络同步**  
   将 v11/v12 required nodes、connections、markers、detail contracts 和独立 Contract ID 纳入 `cityroad_contract.json`/validator；新增测试保证 HDA 新连接与合同共同演进。
2. **P0：把统一入口纳入版本管理**  
   提交 `.agents/scripts/Invoke-PcgRegression.ps1`，或删除所有对不存在入口的规则引用；在干净 checkout 上验证 Capture/VerifyFast/VerifyFull。
3. **P0：在下一次 HDA 修改前处理 Live/Definition 分歧**  
   先比较当前 Dirty Live、磁盘 HDA 和目标 HIP，明确保留侧后再 Capture；不得自动更新或回退。
4. **P1：让 patch 默认不保存**  
   历史脚本保持审计用途；仍保留执行能力的脚本默认 `save=False`，持久化只经 VerifyFull。
5. **P1：修复 Winding Warning 与统计不一致**  
   在全新锁定实例和 Live Scene 分别 Force Cook，确认 Warning 是旧消息、Wrangle 条件错误还是 Packed/Unpacked 分支差异，并加入精确累计合同。
6. **P1：完成 CityRoad Runtime Bake**  
   建立稳定 Piece ID、Chunk/Material 合并、Collider 简化、艺术覆盖保护和重新生成清单。
7. **P2：移动端性能闭环**  
   在 Android Mali/Adreno 与 iOS Metal 上测 DrawCall、SetPass、Mesh/Index 内存、overdraw、加载时间和 Chunk Culling；不要用 Editor Scene 对象数替代真机结论。

Phase18 的几何成果已经把当前测试图的普通道路直角弯从“全局三角化可能漂移”收敛为“作者五截面驱动的确定性 Road/Sidewalk Strip”，并把 Junction 范围和标线纳入明确合同。与此同时，本阶段首次建立跨任务回归门禁，但提交本身尚未完成“合同覆盖 v11/v12 + 统一入口可从干净 checkout 运行”的闭环；在这两项 P0 修复完成前，不应把 Phase18 标记为完整 VerifyFull 通过。
