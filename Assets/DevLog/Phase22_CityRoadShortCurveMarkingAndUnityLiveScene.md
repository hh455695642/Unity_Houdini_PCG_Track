# Phase 22 开发日志：CityRoad 短曲线标线修复、提交后验证与 Unity Live Scene 保存

> 文档类型：提交增量快照  
> 记录日期：2026-08-16  
> 目标提交：`56c52130818cc64ba4ebb8c8a3ca3d7b52bf773e`（提交信息：`22`）  
> 父提交：`e66db1de7938637285b5aa057131e467c5943a23`（Phase21 日志提交）  
> Phase21 功能提交：`6a8978b85a15374f2966f61cb368270e20702942`  
> CityRoad HDA：`Assets/PCG/HDA/City/CityRoad.hda`  
> CityRoad HIP：`HoudiniProject/PCG_Track_21.0.440/PCG_Bike_CityRoad.hip`  
> Unity 场景：`Assets/PCG/Scenes/PCG_City.unity`

## 1. 日志范围与证据

本文只记录 Git 提交 `56c5213` 相对父提交 `e66db1d` 的开发增量。Phase1～Phase21 已记录的 Track、Terrain、CityRoad 道路拓扑、Sidewalk、Marking、Street Furniture、V18 Cook 优化和 V19 Subnet 重构不再重复。

提交 `22` 的最终有效开发链为：

```text
Unity 中缩短五条道路 Spline
    -> 零圆角区段触发三处“count <= 0”硬错误
    -> 道路表面 / Sidewalk / 标线级联为空

V22 Zero Corner Tolerance
    -> 零个 Corner Section 视为合法直通路径
    -> 仍保留“存在但无效”的 Corner / Connector 错误检查
    -> 5 m L 型短路输出 Road / Sidewalk / Marking

V24 Post-Commit Marking Validation
    -> 标线 Builder 只负责删除源曲线并写入标线 Primitive
    -> 新增独立 Wrangle，读取已提交后的标线几何
    -> 再执行 Junction 侵入验证
    -> 五条 Unity 短曲线输出 25 个标线 Primitive，侵入为 0

Unity Scene Save
    -> 保存缩短后的五条 Spline
    -> 保存 Houdini Engine Street Furniture Live Preview 层级
    -> 序列化 596 路灯 + 1049 Round Tree + 1049 Tree Pit
    -> 未形成正式 Bake，Scene Save Gate 报错
```

提交还包含 V20 City Park 和 V21 Public Cleanup 的 manifest/patch 审计文件，但最终 HDA、HIP、合同和 Unity Scene 中均不存在 City Park 参数、Subnet 或输出。因此这些文件只能记为迁移工具/开发记录，不能记为 Phase22 已交付的 City Park 功能。

证据等级：

- **[提交验证]**：目标提交元数据、16 个变更文件、diff、HDA/HIP、Unity YAML Scene、四个 manifest、六个新增工具脚本和累计合同。
- **[Fresh HDA 独立验证]**：Houdini `21.0.440` 使用全新锁定实例执行 28 个累计合同；没有保存资产。
- **[独立短路回归]**：一次性 `hython` Session 加载生产 HIP，以 5 m L 型道路验证 V22；没有连接或修改 Live Session。
- **[Houdini Live 现场]**：Houdini MCP 以 Read-Only Policy 检查当前 HIP、节点、Definition 差异和全网络诊断；Scene Diff 为 0。
- **[Unity 现场]**：Unity MCP 检查 Editor、打开场景、AssetDatabase 身份和 Console；不保存 Dirty Scene。
- **[未闭环]**：提交没有正式 CityRoad Bake、移动端真机、GPU Profiler、Chunk/Cluster、LOD、GPU Culling 或 Indirect Draw 验证。

当前工作区中未跟踪的 CityPark C#、Shader、Compute Shader、Material、测试，以及 StreetBuilding HDA/HIP、合同与 Unity 资产都不属于提交 `22`。

## 2. 提交概览

| 项目 | 数值 |
|---|---:|
| Commit | `56c52130818cc64ba4ebb8c8a3ca3d7b52bf773e` |
| Author / Date | `liyuan` / 2026-08-16 09:52:11 +08:00 |
| Changed Files | 16 |
| Added / Deleted Lines | `+247176 / -24471` |
| CityRoad HDA | 314,532 → 315,924 bytes（+0.443%） |
| CityRoad HIP | 2,275,208 → 2,280,409 bytes（+0.229%） |
| PCG_City Scene | 2,982,942 → 10,728,395 bytes（+259.658%） |
| PCG_City Scene Lines | 45,529 → 266,235（净增 220,706） |
| CityRoad 顶层节点 | 44 → 45（新增 V24 Validator） |
| Required Nodes | 63 → 64 |
| 累计 Contract ID | 26 → 28 |
| Public Interface SHA-256 | `476b2c...a65f`（不变） |
| Unity C# / Shader / Material / RendererFeature | 0 个已提交文件修改 |
| Houdini Engine Unity 插件 | 0 个文件修改 |

文件按职责分为：

1. `CityRoad.hda`、生产 HIP：V22 三处零圆角容错和 V24 提交后标线 Validator。
2. `PCG_City.unity`：五条短曲线及 Street Furniture Live Preview 的序列化现场。
3. `cityroad_v23_zero_corner_tolerance_20260814.json` 与 `patch_cityroad_short_road_markings_v23.py`：V22 零圆角修复白名单和迁移脚本。
4. `validate_cityroad_zero_corner_regression.py`：5 m L 型道路独立复现合同。
5. `cityroad_v24_post_commit_marking_validation_20260816.json` 与对应 patch/validator：提交后标线验证。
6. `cityroad_contract.json`、`cityroad_subnet_layout_contract.json`、`validate_cityroad_contract.py`：新增节点、连接、Marker、合同和 Fresh 短曲线 Fixture。
7. `cityroad_v20_city_park_20260813.json`、`patch_cityroad_city_park_v20_20260813.py`：未进入最终 HDA 的 City Park 迁移工具。
8. `cityroad_v21_public_cleanup_scene_20260813.json`、`patch_cityroad_public_cleanup_v21_20260813.py`：依赖 V20 Park 前置状态的公共参数清理工具。

文件指纹：

| 文件 | Phase22 SHA-256 |
|---|---|
| CityRoad HDA | `28601DDAAF25797605124BA2A95B64CAC81E0D23BA33400497252EB0D54788EB` |
| CityRoad HIP | `9E33FF30E1727DC46BFAC5801CCD06646867CD84CBD280EF030A6A71E1967A9D` |
| PCG_City Scene | `B28E0AB5DC2AF5DA5914CC5BDDAF0552ADA58352F18563F9E924DC7A6E3739A4` |

## 3. V22：零圆角区段合法直通

### 3.1 问题根因

当道路短于 Corner Arc 阈值时，圆角阶段会合理地折叠该 Corner，后续 Corner Section 数量变为 0。原实现有三处将“0 个 Section”与“Section 数据损坏”合并处理：

```text
0 Corner Section
    -> Final Boundary Snap 报错
    -> Road Corner Quad Replace 报错
    -> Sidewalk Corner Quad Replace 报错
    -> Road Surface 为空
    -> CITYROAD_BUILD_STATIC_MARKING_MESH 的 Road 输入为空
    -> Road Markings 全部消失
```

这不是标线生成公式本身失败，而是上游把合法的无圆角直路误判为错误。

### 3.2 三处白名单修改

修复只修改三个 Detail Wrangle 的 `snippet`：

| 节点 | 修改语义 |
|---|---|
| `CITYROAD_REPLACE_CORNER_WITH_QUAD_STRIPS_V11` | `adaptive_quad_count == 0` 时直通；只对 `invalid_quad_count > 0` 报错 |
| `CR_UNION_BOUNDARY/CITYROAD_SNAP_FINAL_BOUNDARY_TO_CORNER_SECTIONS_V12` | `targets == 0` 时直通；只有存在 Target 且未全部命中才报错 |
| `CR_SIDEWALK_CONSTRAINT_BUILD/CITYROAD_REPLACE_SIDEWALK_CORNER_WITH_QUAD_STRIPS_V11` | `sidewalk_quad_count == 0` 时直通；仍检查非法 Quad 和缺失 Connector |

三个节点写入统一 Marker：

```text
CITYROAD_V22_ZERO_CORNER_TOLERANCE
```

修改没有增加公共参数、节点、连接或输出，也没有放宽真实数据损坏检查。Patch 预先快照三个 Snippet，前置文本必须唯一匹配；Cook 验证失败时恢复原 Snippet，默认 `save=False`。

### 3.3 版本命名审计

文件名使用 `v23`：

- `cityroad_v23_zero_corner_tolerance_20260814.json`
- `patch_cityroad_short_road_markings_v23.py`

但脚本说明、Marker 和累计合同都使用 V22：

- `CITYROAD_V22_ZERO_CORNER_TOLERANCE`
- `CityRoad.V22.ZeroCornerTolerance`

本文以最终合同 ID 的 V22 为准，并保留文件名差异供后续审计。V23 manifest 的 `allowed_files` 没有列出同提交新增的 patch/独立 validator 脚本，因此该 manifest 更接近 HDA 修改白名单，不是完整提交文件清单。

### 3.4 独立短路回归

`validate_cityroad_zero_corner_regression.py` 在独立 Houdini 进程创建单条 5 m + 5 m 的 L 型道路，并强制 Cook：

- `OUT_ROAD_SURFACE`
- `OUT_ROAD_MARKINGS`
- `OUT_SIDEWALK_CURB`

验证结果：

| 项目 | 结果 |
|---|---:|
| Marker Nodes | 3 / 3 |
| Marking Primitive Count | 3 |
| Road Surface Errors / Warnings | 0 / 0 |
| Road Marking Errors / Warnings | 0 / 0 |
| Sidewalk Errors / Warnings | 0 / 0 |
| Status | `PASS` |

## 4. V24：在已提交几何上验证标线

### 4.1 同一 Detail Wrangle 的读写时序问题

`CITYROAD_BUILD_STATIC_MARKING_MESH` 是 Detail Wrangle。它会删除上传的源曲线，并在同一次执行中新增标线 Primitive。原 V7 侵入检查继续在这个 Wrangle 内遍历 Input 0 时，读取到的是写入提交前的输入视图，可能把源道路曲线误读为 `marking_type = 0` 的纵向标线。

结果是几何已经正确生成，但同节点内的验证得到一次假阳性：

```text
longitudinal marking intrusion count = 1
    -> Builder Error
    -> OUT_ROAD_MARKINGS 为空
```

### 4.2 独立 Post-Commit Validator

V24 从 Builder 中移除纵向标线 Primitive 扫描，只保留标线生成和通用 Detail 属性写入。新增顶层节点：

```text
CITYROAD_VALIDATE_STATIC_MARKING_JUNCTION_CLIP_V24
```

连接为：

```text
Input 0 <- CITYROAD_BUILD_STATIC_MARKING_MESH
Input 1 <- CITYROAD_TAG_JUNCTION_MOUTH_EDGES_V4
Input 2 <- CR_MARKING_HELPERS

Validator Output
    -> CR_MARKING_APPROACH Input 1
    -> CR_MARKING_FINAL Input 0
    -> CITYROAD_CROSSWALK_ENABLE_V2 Input 0
```

Validator 在 Builder 写入已经提交后再遍历真实标线 Primitive，并写入：

- `longitudinal_marking_primitive_count`
- `longitudinal_marking_junction_intrusion_count`
- `marking_validation_stage = post_commit_v24`

只有真实纵向标线中心落入同层级 Junction Polygon 或 Approach Extension 时才报错。V7/V8 的 Boundary Gap、Edge Join 和 Lane Primitive 合同继续保留。

### 4.3 Unity 五曲线 Fixture

`validate_cityroad_short_curve_markings_v24.py` 独立创建五条曲线，坐标对应提交场景中的缩短版 `SplineContainer`，并对 Unity/Houdini X 轴手性做反转。Fresh 锁定实例验证结果：

| 项目 | 结果 |
|---|---:|
| Input Curve Count | 5 |
| Output Marking Primitives | 25 |
| Builder Errors | 0 |
| V24 Validator Errors | 0 |
| Longitudinal Junction Intrusion | 0 |
| Asset Locked During Validation | `true` |
| Status | `PASS` |

该 Fixture 同时验证 V22 的零圆角直通和 V24 的真实提交后标线检查，不再只依赖生产 HIP 的长道路样例。

## 5. Unity `PCG_City` Scene 增量

### 5.1 Scene 结构变化

提交前后 Unity YAML 对象计数：

| Unity Class | Phase21 | Phase22 | Delta |
|---|---:|---:|---:|
| GameObject (`!u!1`) | 209 | 2,909 | +2,700 |
| Transform (`!u!4`) | 209 | 2,909 | +2,700 |
| PrefabInstance (`!u!1001`) | 0 | 2,694 | +2,694 |
| MonoBehaviour (`!u!114`) | 158 | 167 | +9 |
| Mesh / MeshFilter / MeshRenderer | 71 / 135 / 135 | 71 / 135 / 135 | 0 / 0 / 0 |

新增的 6 个非 Prefab GameObject 是三类 Houdini Engine 输出的 Geo/Part 层级：

- `OUT_STREET_LAMPS`
- `OUT_STREET_TREES`
- `OUT_STREET_TREE_PITS`

新增的 9 个 MonoBehaviour 分别是三组 `HEU_GeoNode`、`HEU_PartData` 和 `HEU_ObjectInstanceInfo`。提交没有修改 Houdini Engine Unity 插件源码。

### 5.2 Street Furniture 实例

Prefab GUID 统计可确定场景序列化了：

| Prefab | GUID | Count |
|---|---|---:|
| `PF_StreetLamp_Placeholder` | `f0e55e3fc166a384ea8f94e1bdf60d12` | 596 |
| `PF_Tree_Round_Placeholder` | `0cc579a3d94d2fd4aaac6808e797e0c0` | 1,049 |
| `PF_TreePit_Placeholder` | `825cb3033f5ecb3439793ff69bcbc0b5` | 1,049 |
| 合计 |  | 2,694 |

Scene 内 `tree_variants = 3`，但 `tree_prefab1/2/3` 三行都序列化为 Round Prefab，因此场景只包含 Round Tree，没有 Tall/Wide。这与 Phase20 已记录的 Multiparm 新实例默认限制一致；不能把 `tree_variants = 3` 解释为场景已有三种树形。

### 5.3 Live Preview，不是正式 Bake

提交前 2026-08-16 09:44:03 和 09:44:04，Unity Console 两次记录：

```text
CityRoad scene save validation: Live Preview is editor-only.
Run Cook + Validate + Update Bake before building.
CityRoad1 is still in Live Preview or has no active Bake instance.
```

错误来自 `CityRoadLivePreviewController.OnSceneSaving`。因此这 2,694 个 PrefabInstance 是 Scene 内的 Houdini Engine Live Preview 现场，不是 Bake 根目录下的发布数据。场景文件从约 2.98 MB 增至 10.73 MB，会显著增加序列化、加载和 Git 合并成本。

当前 Unity 现场仍打开 `PCG_City`，状态为 Dirty、6 个 Root、Build Index `-1`。本日志任务没有保存或关闭该场景。

## 6. V20/V21 City Park 审计边界

### 6.1 已提交的迁移工具

`patch_cityroad_city_park_v20_20260813.py` 描述了一套编辑期 City Park 草案：

- 闭合、非自交、近水平的 Unity Park Boundary 输入。
- 规则网格生成互斥的 Ground、Path、Water Surface。
- Path Collision、Tree Instance Point 和 Building Exclusion Boundary。
- 以稳定 `park_id`、`unity_material`、`unity_instance`、`pcg_group_key` 输出 Bake metadata。
- 单 CityRoad 树点上限 4,096、单 Park 上限 2,048。
- 六个计划输出：Ground、Paths、Water、Collision、Trees、Exclusion。

`patch_cityroad_public_cleanup_v21_20260813.py` 的目标是移除误暴露的原生 `stdswitcher9_1 / Subnet` 参数页，同时要求 V20 Park 参数和 `CR_CITY_PARK` 仍然存在。

### 6.2 最终提交状态

Fresh HDA、磁盘合同和 Houdini Live Read-Only 审计共同确认：

- `enable_city_park` 参数不存在。
- `unity_park_areas` 参数不存在。
- `CR_CITY_PARK` Subnet 不存在。
- 六个 `OUT_PARK_*` 输出不存在。
- `CityRoad.V20.CityPark` 不在最终累计 Contract ID 中。
- 公共接口 SHA-256 与 Phase21 相同。
- Unity Scene 中没有 `enable_city_park`、`unity_park_areas` 或 `OUT_PARK_*` 序列化数据。

V20/V21 manifest 的 `allowed_files` 包含大量当前未跟踪的 CityPark C#、Shader、Compute、Material、Tests 和 Settings。Allowlist 只表示允许范围，不表示这些文件已被提交。Phase22 不具备可用 City Park 交付链。

## 7. 累计合同验证

Fresh Locked Instance 命令：

```powershell
& "D:\Software\Side Effects Software\Houdini 21.0.440\bin\hython.exe" `
  "HoudiniProject\PCG_Track_21.0.440\scripts\tools\validate_cityroad_contract.py" `
  --source fresh
```

结果为 `PASS`，累计合同从 26 增至 28：

- `CityRoad.V22.ZeroCornerTolerance`
- `CityRoad.V24.PostCommitMarkingValidation`

生产配置输出与 Phase21 保持一致：

| Output | Points | Primitives | Vertices |
|---|---:|---:|---:|
| Road Surface | 21 | 21 | 21 |
| Sidewalk Curb | 13 | 13 | 13 |
| Collision | 198 | 220 | 660 |
| Markings | 21 | 21 | 21 |
| Street Lamps | 230 | 0 | 0 |
| Street Trees | 415 | 0 | 0 |
| Tree Pits | 415 | 0 | 0 |

累计关键结果：

- Public Interface Hash：`476b2cbe5a054b5abade2433826431ab229eb88c77026889d3819b177584a65f`。
- Required Node Count：64。
- V19 布局：45 个顶层节点、27 个 Author Subnet、191 个原叶节点、依赖 DAG 为 `true`。
- V24 `marking_validation_stage = post_commit_v24`。
- Junction Approach 23，标线 Boundary Gap 0，Edge Join Error 0。
- Street Furniture：230 Lamp、415 Tree、415 Tree Pit、Surface Intrusion 0，确定性签名不变。
- V18 Road/Sidewalk/Collision/Marking 等价合同继续通过。
- Fresh 锁定验证在 V18 解锁等价比较之前完成。

## 8. Houdini Live 现场状态

Preflight：

- Houdini `21.0.440`，RPC `18811` 可连接。
- Houdini MCP `3055` Health 正常。
- 当前 HIP 为生产 `PCG_Bike_CityRoad.hip`。

Read-Only MCP 审计：

| 项目 | 结果 |
|---|---|
| HIP Unsaved | `false` |
| `/obj/CityRoad_DEV` Locked | `false` |
| Matches Current Definition | `false` |
| CityRoadCore Top-level Nodes | 45 |
| Error Nodes | 0 |
| Warning Nodes | 0 |
| Scanned Nodes | 1,077 |
| Read-Only Scene Changes | 0 |

Live 实例虽无未保存修改和诊断，但仍为 Unlocked 且不匹配 Definition。Fresh 锁定实例是本阶段磁盘交付验证事实；后续修改前仍需 Capture 并明确 Live/Disk 差异，不能直接用一侧覆盖另一侧。

## 9. Unity 资产与编辑器状态

AssetDatabase 身份：

| Asset | Type | GUID |
|---|---|---|
| `Assets/PCG/HDA/City/CityRoad.hda` | `UnityEditor.DefaultAsset` | `67d84be2a5065e14493d6b0d83e29db8` |
| `Assets/PCG/Scenes/PCG_City.unity` | `UnityEditor.SceneAsset` | `6b534bb0e64ba7c4a96ec8df13461451` |

Unity `2022.3.62f2` 当前未处于 Play、Compile、Pause 或 Asset Update。最近 60 分钟没有 Warning，但保留前述两条 Scene Save Error。由于打开场景当前 Dirty，本日志不以当前内存场景替代提交 `56c5213` 的磁盘 YAML 事实。

新增日志经 `AssetDatabase.Refresh()` 后成功导入为 `UnityEngine.TextAsset`，GUID `e88a2227716d4b9ca2056628f31dc246` 与 `.meta` 一致；最终刷新后近 5 分钟没有新增 Error 或 Warning。

## 10. 移动端与渲染架构评估

### 10.1 CPU / GPU 边界

| 阶段 | Phase22 状态 | 移动端判断 |
|---|---|---|
| Houdini Cook | V22/V24 修复短曲线与标线验证 | 编辑期 CPU 修复，不进入 Player |
| Unity Live Preview | 2,694 个独立 PrefabInstance | 只适合编辑预览，不适合直接作为移动端发布结构 |
| Unity Bake | 未形成 Active Bake | 未闭环 |
| Runtime GPU | 无 Chunk/Cluster、LOD、GPU Culling、Indirect Draw | 未交付 |

2,694 个显式 GameObject/PrefabInstance 会增加 Scene 反序列化、Transform、Culling 和潜在 DrawCall/SetPass 成本。正式移动端链路应把 Street Furniture 编译为 Chunk/Cluster 和 GPU 可直接消费的实例 Buffer，默认走 `DrawMeshInstancedIndirect` + GPU Culling + LOD，不应直接发布当前 Live Preview 层级。

### 10.2 URP / Shader Variant / RenderPass

- 提交没有 Shader、Compute Shader、Material、RendererFeature 或 RenderPass 修改。
- 没有新增 Keyword 或 Shader Variant。
- 没有新增 RenderTexture、全屏 Blit 或 MRT。
- 没有侵入 URP 主流程。
- 当前未跟踪的 CityPark Shader/Compute 不能计为 Phase22 交付。

## 11. 已知限制与后续建议

1. **提交 Scene 不是正式 Bake**：保存门禁明确报错，`CityRoad1` 仍处于 Live Preview 或没有 Active Bake。
2. **Scene 体积增长 259.658%**：2,694 个 PrefabInstance 直接进入 YAML，移动端运行和 Git 维护成本都不可接受。
3. **树木仍只有 Round**：三行 Tree Multiparm 都指向 Round，Tall/Wide 没有进入场景实例。
4. **Live/Disk 不匹配**：Houdini Live Unlocked 且 `matchesCurrentDefinition = false`，后续必须先 Capture。
5. **City Park 未交付**：只提交迁移脚本/manifest，最终 HDA、合同、Scene 和配套 Unity 文件均不完整。
6. **V22/V23 命名不一致**：文件名 V23，正式 Marker/Contract 为 V22，后续应统一迁移编号。
7. **V23 Manifest 文件白名单不完整**：没有列出同提交新增的 patch 和独立 validator，需补齐审计范围。
8. **没有真机性能数据**：合同只证明几何行为，不证明 Mali、Adreno、Apple GPU 上的帧时间、带宽或内存。

建议下一阶段优先顺序：

```text
Capture Houdini Live / Definition / HIP 基线
    -> 对齐 Live 与磁盘 Definition
    -> Unity Cook + Validate + Update Bake
    -> 确认 Active Bake 并消除 Scene Save Error
    -> 修复 Tree Multiparm Round/Tall/Wide 初始化
    -> 清理 Scene 内 Live Preview 序列化实例
    -> Street Furniture Chunk / LOD / GPU Culling / Indirect Draw
    -> Android / iOS 真机与 RenderDoc 验证
```

## 12. 阶段结论

提交 `22` 的可靠交付是两项 CityRoad 稳定性修复：V22 允许零 Corner Section 的短道路沿合法直通路径继续生成 Road、Sidewalk 和 Marking；V24 把纵向标线 Junction 侵入检查移到 Builder 写入提交后的真实几何，消除同一 Detail Wrangle 读取旧输入造成的假阳性。Fresh 锁定实例通过 28 个累计合同，5 m L 型回归输出 3 个标线 Primitive，Unity 五曲线 Fixture 输出 25 个 Primitive 且侵入为 0。

Unity 场景提交保存了 2,694 个 Street Furniture Live Preview PrefabInstance，但 Scene Save Gate 明确指出它不是 Active Bake。V20/V21 City Park 文件也只达到迁移工具/审计记录层级。Phase22 因此不能被描述为 City Park 或移动端设施渲染已完成；后续必须先完成 Live/Disk 对齐、正式 Bake 和 GPU 驱动实例链路。
