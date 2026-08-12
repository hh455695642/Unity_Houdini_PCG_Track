# Phase 19 开发日志：CityRoad 方形开放端、非终端圆角与人行道包含性

> 文档类型：提交增量快照  
> 记录日期：2026-08-12  
> 目标提交：`1d21d054701f6c22cd594e5e81751242cda3b153`（提交信息：`19`）  
> 父提交：`9a5f47281559eba4d58ad1c9843212922a1e0dcf`（Phase18 文档提交）  
> CityRoad HDA：`Assets/PCG/HDA/City/CityRoad.hda`  
> CityRoad HIP：`HoudiniProject/PCG_Track_21.0.440/PCG_Bike_CityRoad.hip`  
> Unity 场景：`Assets/PCG/Scenes/PCG_City.unity`（本提交未修改）

## 1. 日志范围与证据

本文只记录 Git 提交 `1d21d05` 相对父提交 `9a5f472` 的开发增量。Phase1～Phase18 已记录的 Track、Terrain、CityRoad 输入、Topology Piece、二维边界、确定性转角 Strip 和回归门禁基础不再重复。

Phase19 的实际开发链：

```text
V13 方形开放端
    -> 从未圆角中心线识别真实开放终端
    -> 开放端左右 Cap Corner 跳过 V9 圆角
    -> 以两条 Side Connector 约束 Sidewalk 左右区域
    -> 审计 Connector 覆盖率、Region 分区与道路孔洞拓扑

V14 非终端圆角恢复
    -> 修复 Detail Wrangle 同次 Cook 读取新 Point Attribute 的错误假设
    -> 使用局部数组保存开放端角点号
    -> 只跳过 14 个开放端角点，恢复其余 32 个圆角

V15 Sidewalk Terminal Front Containment
    -> 在开放端两条 Connector 与 Site Edge 之间构造排除区
    -> 只删除完全位于排除区内的约束三角形
    -> 删除后验证 Site Containment、边界穿越和残留面

累计回归闭环
    -> 修复 Phase18 的 V11/V12 合同连接滞后
    -> 新增 V13/V14/V15 独立行为合同
    -> Fresh Locked Instance 累计验证完整 PASS
```

证据等级：

- **[提交验证]**：目标提交元数据、文件清单、diff、合同 JSON、验证器与 v13/v14 patch。
- **[磁盘 HDA 独立验证]**：Houdini `21.0.440` 独立 `hython` 加载已提交 HIP/HDA，创建全新锁定实例，复制生产参数并执行完整累计合同；没有保存资产。
- **[Houdini Live 现场]**：`Ensure-HoudiniMcp.ps1` 通过后，只读检查当前 HIP、实例、节点与诊断；没有更新 Definition。
- **[Unity 现场]**：Unity MCP 检查 Editor、打开场景、HDA GUID 和 Console；本提交没有 Scene diff。
- **[未闭环]**：v15 的正式 HDA/合同已提交，但对应 patch 和 change manifest 未进入目标提交；Runtime Bake 和移动端真机仍未完成。

当前未跟踪的 `patch_cityroad_sidewalk_terminal_front_v15.py` 与 `cityroad_v15_sidewalk_terminal_front_containment.json` 不属于提交“19”，本文不会把它们列为已交付文件。v15 的功能事实只来自正式 HDA 结构与已提交累计验证器。

## 2. 提交概览

| 项目 | 数值 |
|---|---:|
| Commit | `1d21d054701f6c22cd594e5e81751242cda3b153` |
| Author / Date | `liyuan` / 2026-08-12 13:31:14 +08:00 |
| Changed Files | 8 |
| Added / Deleted Lines | `+1759 / -3` |
| CityRoad HDA | 261,133 → 268,227 bytes（+2.717%） |
| CityRoad HIP | 1,912,562 → 1,953,664 bytes（+2.149%） |
| CityRoadCore Children | 177 → 179（+2） |
| Public HDA Inputs / Outputs | 0 / 6（不变） |
| Unity Scene / C# / Shader / Material | 0 个文件修改 |
| Houdini Engine Unity 插件 | 0 个文件修改 |

提交文件：

1. `Assets/PCG/HDA/City/CityRoad.hda`
2. `HoudiniProject/PCG_Track_21.0.440/PCG_Bike_CityRoad.hip`
3. `scripts/contracts/changes/cityroad_v13_square_open_ends.json`
4. `scripts/contracts/changes/cityroad_v14_nonterminal_rounding.json`
5. `scripts/contracts/cityroad_contract.json`
6. `scripts/tools/patch_cityroad_square_open_ends_v13.py`
7. `scripts/tools/patch_cityroad_nonterminal_rounding_v14.py`
8. `scripts/tools/validate_cityroad_contract.py`

文件指纹：

| 文件 | Phase19 SHA-256 |
|---|---|
| CityRoad HDA | `26B0E3695BD91169955F463AFFE7188C62F5A524CD74BE556AFB0B4DC9AF6540` |
| CityRoad HIP | `1EC72262F7E89830FAD1347CB3B730FDBBF912FC5A84005B260E2687A68D1B17` |

## 3. V13：真实开放端保持方形

### 3.1 原问题

V9 将最终道路边界的所有圆角限制为最多四段，解决移动端几何预算；但开放道路终点也会经过同一圆角逻辑，导致本应是垂直于道路方向的平直 Cap 被削成圆弧。后续 Sidewalk 会沿圆弧绕过道路端头，使道路左右两侧人行道错误连通。

V13 的目标不是关闭全部圆角，而是区分：

- **真实开放终端**：保留方形端头。
- **普通道路弯角和 Junction Corner**：继续使用 V9 圆角预算。

### 3.2 开放终端识别

`ROAD_UNION_ROUND_FINAL_BOUNDARY` 新增第二输入：未圆角的 `ROAD_ADAPTIVE_RESAMPLE` 中心线。对每条道路 Primitive 的首尾点：

1. 读取 `connected_road_count`，只处理没有连接的真实终点。
2. 使用端点与相邻点计算道路外向切线。
3. 根据道路宽度重建左右理想 Cap Corner。
4. 在预圆角 Union Boundary 中匹配对应边和点号。
5. 标记这两个角点为方形开放端目标；后续圆角循环遇到目标点直接保留原点。

detail metadata：

- `cityroad_square_open_end_patch = V13`
- `square_open_end_terminal_count`
- `square_open_end_corner_target_count`
- `square_open_end_corner_skip_count`
- `square_open_end_cap_edge_count`
- `square_open_end_occluded_terminal_count`

目标测试图结果：

| 指标 | 数值 |
|---|---:|
| Open Terminals | 8 |
| Square Cap Edges | 7 |
| Occluded Terminals | 1 |
| Square Corner Targets | 14 |
| Square Corner Skips | 14 |

7 个可见开放端各保留左右两个方角，共 14 个目标；另 1 个终端被道路/场地关系遮挡，不生成可见 Cap，但仍进入终端总数对账。

### 3.3 Sidewalk Connector 与 Seam

V13 延续 Phase17 的两条 Side Connector 方案，但把“是否存在一条边”升级为“Connector 全长是否被 Triangulate 2D 子边覆盖”的合同：

- 每个终端生成左右两条 Connector，共 16 条。
- 长 Connector 可能被三角化切成多段，使用投影参数累加唯一子边长度。
- 共享三角边会被访问两次，按端点对去重。
- 被道路遮挡的 Connector 计入 skipped occluded。
- 已落在 Site Silhouette 上的 1 mm sentinel Connector 计入 skipped boundary。
- 有效 Connector 覆盖率必须不低于 98.5%。

目标测试图：

| 指标 | 数值 |
|---|---:|
| Connector Count | 16 |
| Complete Connectors | 16 |
| Uncovered Connectors | 0 |
| Minimum Active Coverage | 0.9999994 |
| Region Partition Errors | 0 |
| Sidewalk Topology OK | 1 |

`SIDEWALK_PLANAR_MARK_SEAMS` 恢复 `sidewalk_partition_seam` Edge Group，供 Connectivity 将开放端左右人行道切成不同 Region。`SIDEWALK_REGION_METADATA` 再检查同一终端两侧 Region Pair 不得完全相同，防止人行道仍从端头绕行。

### 3.4 Triangulate 2D 行为

V13 将 `SIDEWALK_PLANAR_TRIANGULATE.removeoutsidesilhouette` 设为 0。原因是道路孔洞删除已由后续 `SIDEWALK_PLANAR_DELETE_ROAD` 执行；在 Triangulate 阶段提前移除外轮廓可能把贴近 Site Boundary 的开放端约束边一并丢弃。

该参数变化只影响 Houdini 编辑期几何生成，不增加 Unity 运行时 RenderPass 或 GPU 成本。

## 4. V14：恢复所有非终端圆角

### 4.1 V13 的同 Cook 读取问题

V13 第一版在同一个 Detail Wrangle 中：

1. 写入 `v13_open_terminal_id` Point Attribute。
2. 随后使用 `point()` 读取该 Attribute 决定是否跳过圆角。

VEX 在 Wrangle 中读取的是输入几何快照，不能可靠读取同次 Detail 执行刚写入的点属性。结果是未标记角点也可能被观察为默认值，全部 46 个候选边界角都跳过 V9 圆角，开放端方形正确了，但普通弯角也变成尖角。

### 4.2 局部数组控制流

V14 不再用新写 Point Attribute 驱动同次 Cook 控制流，而是在匹配开放端角点时同步记录：

```text
v14_square_corner_points[]
v14_square_corner_terminals[]
```

后续圆角循环用 `find()` 查询真实 Point Number：

- 命中数组：方形开放端，跳过圆角。
- 未命中数组：普通非终端角，继续 V9 圆角逻辑。
- Point Attribute 只保留为输出 metadata，不参与同次执行判断。

### 4.3 圆角统计

| 指标 | 数值 |
|---|---:|
| Total Rounding Candidates | 46 |
| Square Open-end Skips | 14 |
| Rounded Non-terminal Corners | 32 |
| Rounded Right-angle Corners | 10 |
| Mobile Max Segments | 4 |
| Patch Marker | `V14` |

`32 + 14 = 46` 成为累计行为合同。这一等式同时防止两种回归：开放端被重新圆角，或普通弯角再次全部失去圆角。

## 5. V15：Sidewalk 终端前方包含性

### 5.1 提交范围说明

提交“19”的正式 HDA 增加两个节点，累计合同也要求其 Marker、连接和行为结果：

- `CITYROAD_MARK_SIDEWALK_TERMINAL_FRONT_EXCLUSIONS_V15`
- `CITYROAD_VALIDATE_SIDEWALK_TERMINAL_FRONT_CONTAINMENT_V15`

但 v15 patch 与 change manifest 未包含在目标提交中。因此本节记录的是 **[正式 HDA 已验证功能]**，不是“v15 迁移脚本已完整交付”。

### 5.2 排除区构造

节点链：

```text
CITYROAD_REPLACE_SIDEWALK_CORNER_WITH_QUAD_STRIPS_V11
    + SIDEWALK_PLANAR_SITE_CLEAN
    + SIDEWALK_OPEN_END_SIDE_CONNECTORS
    -> CITYROAD_MARK_SIDEWALK_TERMINAL_FRONT_EXCLUSIONS_V15
    -> SIDEWALK_PLANAR_CLASSIFY
    -> SIDEWALK_PLANAR_DELETE_ROAD
    -> SIDEWALK_PLANAR_REMOVE_UNUSED_POINTS
    -> CITYROAD_VALIDATE_SIDEWALK_TERMINAL_FRONT_CONTAINMENT_V15
    -> SIDEWALK_PLANAR_MARK_SEAMS
```

对每个开放端，v15 使用方形 Cap、左右 Connector 端点及其共享 Site Edge 构造 Terminal Front Exclusion Polygon。只标记完整位于排除区内的约束三角形；若三角形跨越排除区边界，则视为上游约束失败，而不是用质心猜测并局部删除。

三种终端状态：

- **Active**：前方存在需要删除的人行道区域。
- **Sealed**：方形端头已经由 Site Boundary 封闭，不需删除。
- **Occluded**：端头被道路/场地遮挡。

### 5.3 删除后累计审计

`CITYROAD_VALIDATE_SIDEWALK_TERMINAL_FRONT_CONTAINMENT_V15` 在删除后检查：

- Terminal Front 是否还有正面积残留三角形。
- 是否产生非约束形状或跨边界三角形。
- Sidewalk 顶点是否落到 Site 外。
- 是否有边穿越 Site Boundary。
- 是否有 Site 外正面积三角形。
- Connector Seam 是否仍完整。

目标测试图：

| 指标 | 数值 |
|---|---:|
| Active / Sealed / Occluded | 3 / 4 / 1 |
| Invalid Terminal Fronts | 0 |
| Marked / Deleted Triangles | 4 / 4 |
| Residual / Nonconforming Triangles | 0 / 0 |
| Outside Vertices | 0 |
| Site Boundary Crossing Edges | 0 |
| Outside Positive-area Triangles | 0 |
| Sidewalk Primitives | 167 |
| Sidewalk Regions | 9 |
| Complete / Uncovered Connectors | 16 / 0 |
| Containment OK | 1 |
| Patch Marker | `V15` |

## 6. 累计合同修复与扩展

### 6.1 Phase18 合同缺口已修复

Phase18 的正式 HDA 已把：

```text
SIDEWALK_PLANAR_CLASSIFY[0]
    -> CITYROAD_REPLACE_SIDEWALK_CORNER_WITH_QUAD_STRIPS_V11
```

但旧 `cityroad_contract.json` 仍要求 v10 Fuse，导致 Live/Fresh 累计验证失败。Phase19 更新 required nodes/connections/markers，使正式链继续经 v15 标记节点后进入 Classify，并把 v12 Shared Boundary 接入 `SIDEWALK_PLANAR_CLASSIFY[2]`。

Phase19 Fresh Locked Instance 验证结果：`status = PASS`。

### 6.2 合同覆盖范围

累计 Contract ID 从 Phase18 的 17 个扩展为 22 个，新增：

- `CityRoad.V11.DeterministicSidewalkCornerStrips`
- `CityRoad.V12.FinalBoundaryCornerSections`
- `CityRoad.V13.SquareOpenEnds`
- `CityRoad.V14.NonTerminalRounding`
- `CityRoad.V15.SidewalkTerminalFrontContainment`

required node 数为 42，公共接口 SHA-256 仍为：

```text
6efd6f02eb08296b78ba60c75d8d35af8486ae1e385a71d963c165034eee555a
```

因此本阶段没有修改 HDA 公共参数 name、label、default、menu、range 或可见性。

### 6.3 Change Manifest

新增两个已提交白名单：

- `cityroad_v13_square_open_ends.json`
- `cityroad_v14_nonterminal_rounding.json`

V13 Manifest 只允许修改开放端 Boundary/Connector/Seam/Topology/Region 链、少量连接和 Triangulate 的 `removeoutsidesilhouette`；V14 Manifest 只允许修改 `ROAD_UNION_ROUND_FINAL_BOUNDARY`。两者都禁止公共参数变化，且 `allowed_warning_signatures = []`。

v15 对应 manifest 没有进入目标提交，这是当前审计缺口。

## 7. HDA、HIP 与输出状态

### 7.1 正式结构

| 指标 | Phase18 | Phase19 |
|---|---:|---:|
| CityRoadCore Children | 177 | 179 |
| Added Nodes | - | 2 个 v15 Wrangle |
| HDA Inputs | 0 | 0 |
| HDA Outputs | 6 | 6 |
| Public Interface Hash | 不变 | 不变 |

v13/v14 都增量修改既有节点；两个新节点全部属于 v15 的“标记排除区”和“删除后审计”职责，没有形成全能型单节点。

### 7.2 Fresh Locked Output

| Output | Points | Primitives | Vertices |
|---|---:|---:|---:|
| `OUT_ROAD_SURFACE` | 21 | 21 | 21 |
| `OUT_SIDEWALK_CURB` | 13 | 13 | 13 |
| `OUT_ROAD_COLLISION` | 198 | 220 | 660 |
| `OUT_ROAD_MARKINGS` | 21 | 21 | 21 |

相对 Phase18，Collision 从 255 Points / 274 Primitives / 822 Vertices 降至 198 / 220 / 660。前三个 Packed Output 的点/Primitive 数代表 Piece 数，不等于解包后 Mesh 顶点数。

累计几何合同同时确认：

- Phase17 退化 Primitive = 0。
- 剩余反向 Top/Vertical Face = 0。
- Road Triangles = 236。
- Houdini +Y Road Triangles = 0，符合 HAPI 到 Unity 的绕序合同。

### 7.3 Fresh 全网 Warning

四个正式 Output 本身满足累计验证器的 0 Error / 0 Warning 要求，但 Fresh 全网扫描仍有 0 Error、11 个 Warning 条目，主要是：

- Merge 输入属性不一致。
- 可选 Reverse Group 不存在。
- `CITYROAD_TOPOLOGY_CLASSIFY_ROAD` 的 Winding Warning 与最终统计 `+Y = 0` 不一致。
- Tutorial Lab 的历史 Merge 属性 Warning。

这些不是本提交新增 Output Error，但与 Manifest 的 `allowed_warning_signatures = []` 目标仍不一致；后续应初始化 Merge 属性、对可选 Group 做存在检查，并修复 Winding Warning 的触发条件。

## 8. Patch 安全性

v13/v14 patch 相比早期历史 patch 已符合新门禁的大部分要求：

- 默认 `save=False`，只有显式 `--save` 才更新 Definition/HIP。
- 校验目标 Asset Type、Definition Path 和 HIP Path。
- 使用精确前置文本替换，匹配数量不是 1 时 Fail Closed。
- Marker 已存在时只验证并返回 `idempotent = true`。
- 异常时恢复原 Snippet、连接和参数。
- 不导入历史 patch，不清空 HIP，不重建 HDA。

这些脚本仍属于一次性迁移/审计记录。后续任务应基于当前 Live Scene + Manifest + Capture，不得重放 v13/v14 来“补齐”环境。

## 9. Unity 与渲染状态

### 9.1 提交边界

提交“19”没有修改：

- `Assets/PCG/Scenes/PCG_City.unity`
- Unity C# / Editor Tool。
- Material / Texture / Shader。
- RendererFeature / RenderPass / URP Asset。

因此本文不把当前 Unity Dirty Scene 中的 Live Cook 结果写成已提交 Scene 成果。正式 HDA 已被 Unity AssetDatabase 找到，GUID 保持：

```text
67d84be2a5065e14493d6b0d83e29db8
```

### 9.2 当前 Unity 现场

- Unity `2022.3.62f2`。
- 未播放、未暂停、未编译、未刷新 AssetDatabase。
- 当前打开 `Assets/PCG/Scenes/PCG_City.unity`，Loaded/Valid，Root Count 6。
- Scene 为 Dirty；本日志任务不会保存。
- 最近 10 分钟 Console Error = 0，Warning = 0。

### 9.3 移动端渲染评估

- 新增 Shader、keyword、variant：0。
- 新增 RenderPass、RT、Blit、MRT：0。
- V13～V15 计算全部发生在 Houdini 编辑期 CPU Cook，不进入移动端运行时。
- 方形 Cap、恢复非终端圆角和 Sidewalk 删除会改变 Bake Mesh，但不增加材质采样或 overdraw 功能。
- Runtime 仍应只消费 Bake 后 Unity Mesh/Collider；禁止移动端运行 Houdini Cook。
- 当前仍没有 Android Mali/Adreno、iOS Metal 的真机 DrawCall、内存、加载与碰撞性能结论。

## 10. 当前现场与目标提交边界

### 10.1 Houdini Live

本次审计时：

- HIP 为目标 `PCG_Bike_CityRoad.hip`，RPC/MCP 正常。
- `/obj/CityRoad_DEV` 为 unlocked、`matchesCurrentDefinition = false`。
- HIP `hasUnsavedChanges = false`。
- Live CityRoadCore 为 179 个节点。
- Live 累计合同 PASS。

Live 虽未脏，但实例 Contents 与 Definition 不匹配；不能据此自动更新 HDA，也不能用磁盘 HDA覆盖现场。本文的提交结论来自独立 Fresh Locked Instance。

### 10.2 未跟踪文件

写日志前已有用户未跟踪内容包括：

- `.agents/scripts/Invoke-PcgRegression.ps1`。
- Terrain Shader、Track/Terrain Word 文档与临时文件。
- Unity Tests 和 FBX 资产。
- v15 patch 与 v15 change manifest。

这些文件没有被移动、覆盖、暂存或计入提交“19”。

## 11. 问题与状态变化

### 11.1 已解决：开放道路端头被错误圆角

8 个真实开放终端中，7 个可见 Cap 保持方形，1 个遮挡端被明确计数。

### 11.2 已解决：人行道绕过方形道路端头

16 条 Connector 全部完成覆盖，0 Uncovered；Region Partition Error = 0。

### 11.3 已解决：V13 导致全部边界角失去圆角

V14 使用局部数组替代同 Cook Point Attribute 回读，恢复 32 个非终端圆角，只跳过 14 个开放端角点。

### 11.4 已解决当前测试图：终端前方 Sidewalk 越界

v15 标记并删除 4 个三角形，删除后残留、非约束面、Site 外顶点、边界穿越均为 0。

### 11.5 已解决：Phase18 累计合同与 v11/v12 网络不同步

Fresh 和 Live 累计合同现均 PASS，合同覆盖到 v15。

### 11.6 未闭环：v15 迁移记录没有进入提交

正式 HDA/合同/验证器包含 v15，但其 patch 和 manifest 仍是未跟踪文件。干净 checkout 可以验证结果，却不能完整审计 v15 的白名单和迁移过程。

### 11.7 未闭环：统一回归入口仍未提交

`.agents/scripts/Invoke-PcgRegression.ps1` 继续只存在于当前未跟踪工作区。单独 checkout 提交“19”仍不能执行规则文档声明的统一 PowerShell 入口。

### 11.8 延续风险：全网非 Output Warning

Fresh 全网仍存在属性 Merge、空 Reverse Group 和 Winding Warning；虽然累计几何合同通过，但 Warning 噪声可能掩盖未来回归。

### 11.9 未完成：Unity Scene Bake 与移动端真机

本提交没有 Scene/Bake 资产变化，也没有移动端性能验证。

## 12. 验证记录

### 12.1 Git

- 标题 `19` 唯一匹配提交 `1d21d05`：通过。
- 父提交 `9a5f472`：通过。
- 8 个文件变化，未修改插件/Scene/Shader：通过。
- 当前磁盘 HDA/HIP 与 HEAD 无 tracked diff：通过。
- v15 patch/manifest 是否属于提交：否。

### 12.2 Houdini

- `Ensure-HoudiniMcp.ps1`：通过。
- Houdini `21.0.440`、RPC `18811`、MCP `3055`：通过。
- Fresh Instance：locked、matches Definition、179 Core Children。
- Fresh 累计合同：`PASS`，22 个 Contract ID。
- Live 累计合同：`PASS`。
- 四个正式 Output：累计验证通过。
- Fresh 全网：0 Error，11 个 Warning 条目。
- 本次没有保存或更新 HDA/HIP。

### 12.3 自动测试

Phase18 回归比较器单元测试再次执行：

```text
.......
Ran 7 tests in 0.001s
OK
```

### 12.4 Unity

- Editor Ready：通过。
- CityRoad HDA AssetDatabase 路径/GUID：通过。
- `PCG_City` Loaded/Valid：通过，但 Dirty。
- 最近 10 分钟 Console Error/Warning：0/0。
- Scene 提交 diff：无。
- Runtime Bake / 真机：未验证。

## 13. 当前状态矩阵

| 功能 | 状态 | 当前结论 |
|---|---|---|
| V13 Open Terminal Detection | 已完成当前测试图 | 8 个终端 |
| V13 Square Caps | 已完成当前测试图 | 7 Cap + 1 Occluded |
| V13 Sidewalk Connectors | 已通过 | 16/16 Complete，0 Uncovered |
| V13 Region Partition | 已通过 | Error = 0，Topology OK = 1 |
| V14 Non-terminal Rounding | 已通过 | 32 Rounded + 14 Skipped = 46 |
| V14 Mobile Segment Budget | 延续通过 | Max 4 |
| V15 Terminal Front Exclusion | 已通过当前测试图 | 4 Marked / 4 Deleted |
| V15 Site Containment | 已通过 | Outside/Crossing/Residual 均为 0 |
| HDA Public Interface | 未变化 | Hash 稳定，0 Input / 6 Output |
| Fresh Cumulative Contract | 已通过 | 22 个 Contract ID |
| Phase18 v11/v12 Contract Gap | 已修复 | Fresh/Live 都 PASS |
| v15 Patch + Manifest | **未进入提交** | 当前仅未跟踪文件 |
| Unified Regression Entry | **未进入提交** | 当前仅未跟踪脚本 |
| Fresh Full-network Warnings | 待清理 | 0 Error / 11 Warning 条目 |
| Unity Scene | 本提交未修改 | 当前 Live Scene Dirty |
| Runtime Bake | 未完成 | 无正式 Chunk/Bake 交付 |
| Mobile Device Validation | 未执行 | 无真机数据 |

## 14. 下一阶段建议

1. **P0：提交 v15 的正式审计材料**  
   核对当前未跟踪 v15 patch/manifest 是否与正式 HDA 完全一致，先按当前事实源验证；确认后纳入版本管理，不能直接把未跟踪脚本当事实源。
2. **P0：提交统一回归入口**  
   将 `.agents/scripts/Invoke-PcgRegression.ps1` 纳入干净 checkout，并实际跑通 Capture→VerifyFast→VerifyFull。
3. **P0：处理 Live/Definition 不匹配**  
   下一次 HDA 修改前比较 Live 和磁盘 Definition，明确保留侧后 Capture，禁止自动覆盖。
4. **P1：清理全网 Warning**  
   Merge 前统一初始化 v13/v15 metadata；可选 Reverse Group 不存在时 Bypass；修复 Winding Warning 与最终 `+Y = 0` 统计不一致。
5. **P1：将开放端/包含性纳入参数化测试图**  
   增加不同 Site 轮廓、道路宽度、斜向终端、遮挡终端和相邻 Junction 的累计用例，避免合同只锁死当前单张测试图。
6. **P1：完成 Unity Runtime Bake**  
   输出稳定 Chunk ID、合并渲染 Mesh、简化 Collision、记录艺术覆盖和重新生成策略。
7. **P2：移动端真机闭环**  
   在 Mali/Adreno/Metal 上验证 Mesh/Index 内存、DrawCall、SetPass、Collider、加载时间和 Chunk Culling。

Phase19 已把开放端从“统一圆角导致 Sidewalk 绕行”收敛为“只对真实终端保留方形 Cap，并用完整 Connector/Containment 合同切断人行道”；同时修复了 Phase18 累计合同落后于正式网络的问题。当前最重要的交付缺口不是几何结果，而是 v15 与统一门禁入口仍未完整进入 Git，后续必须先完成可审计性闭环再扩展新功能。
