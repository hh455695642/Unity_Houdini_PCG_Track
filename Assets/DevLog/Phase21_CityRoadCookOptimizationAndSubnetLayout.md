# Phase 21 开发日志：CityRoad Cook 优化、单层 Subnet 重构与回归门禁增强

> 文档类型：提交增量快照  
> 记录日期：2026-08-13  
> 目标提交：`6a8978b85a15374f2966f61cb368270e20702942`（提交信息：`21`）  
> 父提交：`8b82394011df6377673fc7ebb72d94daa31b8d7e`（Phase20 日志提交）  
> Phase20 功能提交：`df1f5e7f1ef61ef68f5a054882a681191f69934d`  
> CityRoad HDA：`Assets/PCG/HDA/City/CityRoad.hda`  
> CityRoad HIP：`HoudiniProject/PCG_Track_21.0.440/PCG_Bike_CityRoad.hip`  
> Unity 主验证场景：`Assets/PCG/Scenes/PCG.unity`（本提交未修改）

## 1. 日志范围与证据

本文只记录 Git 提交 `6a8978b` 相对父提交 `8b82394` 的开发增量。Phase1～Phase20 已记录的 Track、Terrain、CityRoad 道路生成、Sidewalk、Marking、开放端、Terminal Front Containment 与 Street Furniture 功能不再重复。

Phase21 包含两个连续的 CityRoad 版本增量：

```text
V18 Cook Optimization
    -> 建立线段、路口中心、路口入口和走廊区间索引
    -> 用宽相位候选 + 精确相交替代重复全量扫描
    -> Road / Sidewalk / Marking / Street Furniture 消费共享索引
    -> 为 Marking、Lamp、Tree 增加早期 Feature Toggle 分支
    -> 以几何等价合同和基准门禁约束优化结果

V19 Subnet Layout
    -> 将 191 个原始叶节点迁入 27 个 CR_* 单层 Subnet
    -> 通过显式输入、输出和 Dot 保持依赖关系
    -> 保留对外输出、原节点名、参数、Flags 和逻辑连接
    -> 使用 5 个区域 Network Box 组织顶层阅读顺序
    -> 以成员合同、依赖 DAG 和布局前后签名防回归

Regression Gate
    -> CityRoad Capture/Verify 支持递归检查一层 CR_* Subnet
    -> 无公共参数变更时保留原 Definition 参数模板
    -> 支持 isolated snapshot / persist / restore
    -> 增加 StreetBuilding 独立模块入口，但未提交 StreetBuilding 资产
```

证据等级：

- **[提交验证]**：目标提交元数据、12 个变更文件、diff、HDA/HIP、manifest、patch、合同、验证器与基准脚本。
- **[Fresh HDA 独立验证]**：Houdini `21.0.440` 独立 `hython` 创建全新锁定实例，从生产 HIP 复制实例参数并执行 26 个累计合同；没有保存资产。
- **[Houdini Live 现场]**：`Ensure-HoudiniMcp.ps1` 通过后，Houdini MCP 对当前 HIP 和 `/obj/CityRoad_DEV` 进行只读审计；没有更新 Definition，也没有保存 HIP。
- **[Unity 现场]**：Unity MCP 核对 Editor、打开场景、主 HDA 的 AssetDatabase 身份与 Console；本提交没有 Unity Scene、C#、Shader、Material 或 Prefab 改动。
- **[本地审计产物]**：`.codex_tmp/benchmarks/` 中存在开发阶段留下的基准 JSON，可复算 V18/V19 门禁，但这些 JSON 不属于提交 `21`。
- **[未闭环]**：未完成 Unity Bake 产物、移动端真机、GPU Profiler、Mali/Adreno/Apple GPU、Chunk/Cluster、LOD、GPU Culling 或 Indirect Draw 验证。

当前工作区存在未跟踪的 StreetBuilding HDA/HIP、合同、脚本和 Unity 资产。提交 `21` 只增加了回归门禁对 `StreetBuilding` 模块的支持，这些未跟踪业务资产不是本阶段的提交交付物。

## 2. 提交概览

| 项目 | 数值 |
|---|---:|
| Commit | `6a8978b85a15374f2966f61cb368270e20702942` |
| Author / Date | `liyuan` / 2026-08-13 07:36:10 +08:00 |
| Changed Files | 12 |
| Added / Deleted Lines | `+3494 / -52` |
| CityRoad HDA | 278,476 → 314,532 bytes（+12.947%） |
| CityRoad HIP | 2,000,636 → 2,275,208 bytes（+13.724%） |
| CityRoad 顶层节点 | 44 |
| V19 Author Subnet | 27 |
| 迁移原始叶节点 | 191 |
| Required Nodes | 49 → 63（+14） |
| 累计 Contract ID | 24 → 26（+2） |
| HDA Type Max Inputs / Outputs | 0 / 6（不变） |
| Unity Scene / C# / Shader / Material / Prefab | 0 个文件修改 |
| Houdini Engine Unity 插件 | 0 个文件修改 |

文件按职责分为：

1. `CityRoad.hda` 与 `PCG_Bike_CityRoad.hip`：V18 索引化 Cook 路径和 V19 单层 Subnet 正式实现。
2. `cityroad_cook_v2_20260812.json`：V18 优化白名单与累计验收合约。
3. `patch_cityroad_cook_v2_20260812.py`：V18 一次性、幂等、前置校验和失败回滚的迁移脚本。
4. `benchmark_cityroad_cook.py`：确定性规模图基准、阶段计时与性能门禁。
5. `cityroad_subnet_layout_20260813.json`：V19 布局修改白名单。
6. `cityroad_subnet_layout_contract.json`：27 个 Subnet 的成员、接口与 DAG 合同。
7. `patch_cityroad_subnet_layout_20260813.py`：V19 单层 Subnet 迁移和回滚脚本。
8. `capture_cityroad_layout_signatures.py`：布局前后几何与确定性签名捕获。
9. `cityroad_contract.json`、`validate_cityroad_contract.py`：新增 V18/V19 累计行为合同与验证逻辑。
10. `pcg_regression_gate.py`：递归范围、参数模板持久化和 isolated module 能力。

文件指纹：

| 文件 | Phase21 SHA-256 |
|---|---|
| CityRoad HDA | `D41B7FF24F6A979241049BD9519F5C48F1630EE1D64B4E302955CCA64A33B751` |
| CityRoad HIP | `4896A66C3B208E0E84EBCE6EA136BD97FF90A435C23BB0B262E31C2FF84F8FD2` |

## 3. V18：共享空间索引与 Cook 优化

### 3.1 Segment Index：把重复线段扫描变为共享数据

新增 `GRAPH_SEGMENT_INDEX_V2`。它把道路中心线采样成紧凑点云，每个点代表一个 XZ 线段，并按源 Primitive 与局部线段顺序稳定编号。索引点携带：

- 线段两个端点与方向。
- 道路宽度、源 Primitive、局部线段编号和稳定 ID。
- 供 `pcfind` 使用的中心位置与 `pscale` 宽相位半径。

`GRAPH_CLASSIFY_JUNCTIONS` V2 不再对所有线段执行重复的二重全量扫描，而是先用 `pcfind` 获取空间候选，再对候选执行精确线段相交测试。生产累计验证中的索引统计为：

| 指标 | 生产验证值 |
|---|---:|
| Graph Segment Count | 178 |

100 Edge 合成基准对应 133 个 Segment、2,677 个宽相位候选和 1,081 次精确相交测试，详见第 4 节。性能关键点是候选生成与精确测试分层；索引只保存必要字段，避免把完整道路几何复制到每个下游分支。该实现仍是 Houdini Editor/Bake 阶段优化，不进入移动端运行时。

### 3.2 Junction 与 Corridor 的确定性索引

新增三个共享索引：

- `JUNCTION_APPROACH_INDEX_V2`：按道路层级、位置和稳定 ID 生成密集的 Approach/Junction ID，消除不同分支各自排序带来的漂移。
- `JUNCTION_CENTER_INDEX_V2`：将路口中心压缩为唯一点云，供设施排除区直接执行 `nearpoint` 查询。
- `CORRIDOR_INTERVAL_INDEX_V2`：集中保存源 Primitive/Segment、区间起止、边界、Approach 与切线，Road 和设施分支复用同一份走廊区间表。

生产合同统计：

| 索引 | Count |
|---|---:|
| Approach | 23 |
| Junction | 6 |
| Corridor | 24 |
| Corridor Source Segment | 13 |
| Unbound Boundary | 0 |

稳定 ID 和共享区间是后续扩展点：增加新的道路附属物时应消费这些索引，不应恢复到每个功能独立扫描全部道路段。

### 3.3 Road / Sidewalk 的 V1-V2 双路径

新增 `ROAD_BUILD_SURFACE_V2` 及对应 Adaptive Surface 路径，通过：

- `CITYROAD_ROAD_SURFACE_V1_V2`
- `CITYROAD_ADAPTIVE_SURFACE_V1_V2`

在旧、新实现之间切换，正式 Definition 默认选择 V2。V2 直接消费 Corridor Interval Index，避免重复重建道路分段和端点约束。

Sidewalk 保留精确旧路径用于合同审计，生产路径使用更快的 Seam 结果，并由 `CITYROAD_SIDEWALK_AUDIT_V1_V2` 选择。验证器不是只检查“能 Cook”，而是比较 V1/V2 输出签名。

V18 几何等价结果：

| 输出 | Points / Primitives | 最大点误差 | Bounds 误差 | 相对面积误差 |
|---|---:|---:|---:|---:|
| Road Surface（Unpacked） | 324 / 236 | `1.52587890625e-05` | 0 | `1.4825e-08` |
| Sidewalk | 446 / 707 | 0 | 0 | 0 |
| Collision | 198 / 220 | 0 | 0 | 0 |
| Marking | 3,264 / 1,632 | 0 | 0 | 0 |
| Sidewalk Audit | 162 / 167 | 0 | 0 | 0 |

Road Surface 的微小点误差处于浮点计算顺序变化范围，Bounds 不变，面积相对误差约 `1.48e-8`；其余受检输出精确一致。

### 3.4 Marking 与 Street Furniture 的早期 Feature Toggle

Marking 分支将静态道路标线与 Junction Approach 标线职责拆开：

- Static Marking 不再重复执行 Junction 工作。
- Approach Marking 独立负责 Crosswalk 与 Stopline。
- Center、Lane、Edge、Junction 通过 V2 Blast 节点分离角色。
- `CITYROAD_CROSSWALK_ENABLE_V2` 与 `CITYROAD_MARKING_ENABLE_V2` 在昂贵生成链前接入空分支。

Street Furniture 优化包括：

- 路灯排除区改为查询唯一 Junction Center 点云。
- 树木/路灯同 Corridor 净距改用稳定排序的双指针合并，并保留精确空间查询回退。
- Lamp、Tree 开关提前到生成链入口；Tree Pit 严格消费开关后的 Tree 输出。

这些开关继续使用已有 HDA 公共参数，通过 Switch/Uniform 风格控制，不新增 Shader Keyword，也不涉及 Shader Variant 数量。关闭功能时能够绕过对应 Houdini 生成成本，但不会改变 Unity 运行时渲染管线。

## 4. V18 性能基准与门禁

`benchmark_cityroad_cook.py` 可生成 25、100、225 Edge 的确定性测试图。默认 100 Edge 图由 `8 × 7` 网格与 3 条 Feeder Edge 组成，并交替扰动内部顶点；每个样本强制 Cook 七个正式输出。

开发阶段保留在 `.codex_tmp/benchmarks/` 的 100 Edge 基准可复算出：

| 版本 | Median | P95 |
|---|---:|---:|
| V1 Baseline | 7,238.715 ms | 7,825.918 ms |
| V18 Candidate | 4,229.074 ms | 4,408.561 ms |
| Candidate / Baseline | 58.423% | 56.333% |
| 改善 | 41.577% | 43.667% |

V18 门禁要求：

- Candidate Median 不高于 Baseline 的 70%。
- P95 不得劣化。
- 任一阶段同时出现大于 10% 且大于 1 ms 的回退时失败。

本地审计结果为 `PASS`。同一套脚本的规模抽样还记录：

| Edge | Median | P95 | Segment / Broadphase / Exact |
|---|---:|---:|---:|
| 25 | 583.830 ms | 623.413 ms | 34 / 570 / 232 |
| 100 | 4,229.074 ms | 4,408.561 ms | 133 / 2,677 / 1,081 |
| 225 | 17,701.674 ms | 17,987.924 ms | 275 / 5,860 / 2,352 |

基准脚本在可丢弃的临时 Asset 实例中运行。为了让合成输入脱离生产 HIP Fixture，脚本只在临时克隆中屏蔽嵌入节点里的 Fixture 专用 error/warning 检查，不改算法链和输出链。该结果适合做同机相对回归门禁，不等同于 Unity Bake 总耗时，也不是移动端运行时性能数据。

## 5. V19：一层 Subnet 网络重构

### 5.1 结构结果

V19 将 191 个原始叶节点迁移到 27 个 `CR_*` Author Subnet。顶层保留 44 个节点，并用五个区域 Network Box 表达从输入到输出的阅读顺序：

1. `AREA_INPUT_GRAPH`
2. `AREA_ROAD`
3. `AREA_JUNCTION_SIDEWALK`
4. `AREA_MARKING_STREET`
5. `AREA_OUTPUT_DEBUG`

布局合同验证：

| 指标 | 结果 |
|---|---:|
| Author Subnet | 27 |
| Moved Leaf Nodes | 191 |
| Top-level Nodes | 44 |
| Max Subnet Inputs | 4 |
| Max Subnet Outputs | 7 |
| Network Boxes | 5 |
| Dependency DAG | `true` |

重构只允许一层 `CR_*` Subnet，不把 VOP 等实现内部继续纳入项目级布局合同。每个 Subnet 使用显式间接输入、Subnet Output 与 Dot 暴露依赖，避免隐藏跨区连接。

### 5.2 迁移保持项

`patch_cityroad_subnet_layout_20260813.py` 在单个 Undo Group 内执行迁移，并保持：

- 原始叶节点名称。
- 节点类型、非默认参数、VEX、Flags 与注释。
- 逻辑连接和正式 HDA 输出顺序。
- 现有公共 HDA 参数与外部 Unity 接口。
- CityRoadCore 内部相对参数引用；对受层级变化影响的引用通过 Core 代理参数稳定访问。

脚本默认 `save=False`，带前置 Marker/Hash、幂等检查和失败回滚。只有 VerifyFull 通过后才允许持久化 Definition 与 HIP。

### 5.3 布局行为签名

`capture_cityroad_layout_signatures.py` 在迁移前后捕获：

- 六个正式输出的几何统计与属性签名。
- Street Furniture 的确定性签名。
- Subnet 成员和顶层依赖图。

V19 布局性能门禁允许结构调整带来最多 `+3%` Median、`+5%` P95，阶段级回退仍按“大于 10% 且大于 1 ms”失败。本地审计产物结果：

| 布局 | Median | P95 |
|---|---:|---:|
| Fair Baseline | 4,044.457 ms | 4,288.677 ms |
| V19 Final | 4,005.115 ms | 4,081.456 ms |
| Final / Baseline | 99.027% | 95.168% |

门禁结果为 `PASS`。V19 的目标是降低网络维护复杂度，不把布局重构包装成算法性能提升。

## 6. 回归门禁增强

### 6.1 CityRoad 一层递归范围

`pcg_regression_gate.py` 的 CityRoad Capture/Verify 从只扫描 `CityRoadCore` 顶层改为：

- 顶层节点全部纳入范围。
- 对 `CR_*` Author Subnet 精确递归一层。
- 不递归进入 VOP 等实现网络。
- 输出比较排除瞬时 `needs_cook` 状态，避免无行为意义的假回归。

对应 `cityroad_subnet_layout_contract.json` 固定 27 个 Subnet 的精确成员、接口上限、顶层保留节点和依赖 DAG，防止后续节点被静默移出合同范围。

### 6.2 公共参数模板持久化规则

Phase20 为新增 Street Furniture 公共参数引入了 `setParmTemplateGroup` 持久化。Phase21 将规则进一步收紧：

- Manifest 没有声明允许新增/修改公共参数时，保存 Definition 必须保留原始 Definition Parm Template Group。
- 禁止把 Live 实例的临时 BaseParm、Folder ID 或实例专用模板泄漏到磁盘 HDA。
- 只有公共参数白名单明确允许时，才可提升 Live 参数模板。

V18/V19 两份 Manifest 的 `allowed_public_parameters` 均为空，表示本阶段没有有意增加用户公共参数。Fresh/Live 验证时磁盘与 Live 公共接口 SHA-256 均为：

```text
476b2cbe5a054b5abade2433826431ab229eb88c77026889d3819b177584a65f
```

该哈希与 Phase20 日志中的磁盘哈希不同，因此审计时必须以 Phase21 Definition 与合同一致性为准；提交证据可以确认没有声明公共参数增量，但不能把哈希变化忽略为“完全未变化”。Phase20 已记录的全新实例 Tree Multiparm 默认 Round/Round/Round 限制仍然存在，本提交未修复该默认配置问题。

### 6.3 Isolated Module 与 StreetBuilding 边界

门禁新增 `isolated_snapshot`、`persist_isolated`、`restore` 处理，可在可丢弃的独立 Houdini 进程中构造和验证新模块；缺失的新文件也能纳入备份/恢复语义。

提交同时登记了 `StreetBuilding` 模块入口：

- StreetBuilding 作为独立目标运行。
- Live CityRoad 只能作为观察依赖，不能被 StreetBuilding 门禁修改。
- Capture/Verify/Persist 应在 disposable `hython` 会话完成。

提交 `21` 没有包含 StreetBuilding HDA、HIP、builder、contract、Unity 材质或建筑脚本。当前工作区出现的这些未跟踪文件属于提交后的现场开发，不能反向计入 Phase21。

## 7. 累计合同验证

Fresh Locked Instance 与 Live Source 均通过 26 个累计 Contract ID。Phase21 新增：

- `CityRoad.V18.CookOptimization`
- `CityRoad.V19.SubnetLayout`

Fresh 验证命令：

```powershell
& "D:\Program Files\Side Effects Software\Houdini 21.0.440\bin\hython.exe" `
  "HoudiniProject\PCG_Track_21.0.440\validate_cityroad_contract.py" `
  --source fresh
```

Live 验证命令：

```powershell
& "D:\Program Files\Side Effects Software\Houdini 21.0.440\bin\hython.exe" `
  "HoudiniProject\PCG_Track_21.0.440\validate_cityroad_contract.py" `
  --source live
```

两次结果均为 `PASS`，正式输出统计一致：

| Output | Points | Primitives | Vertices |
|---|---:|---:|---:|
| Road Surface | 21 | 21 | 21 |
| Sidewalk Curb | 13 | 13 | 13 |
| Collision | 198 | 220 | 660 |
| Markings | 21 | 21 | 21 |
| Street Lamps | 230 | — | — |
| Street Trees | 415 | — | — |
| Tree Pits | 415 | — | — |

累计行为继续满足：

- 32 个 Rounded Corner 与 14 个 Skipped Corner。
- 16/16 Sidewalk Connector。
- V15 Terminal Front Containment 4/4。
- 115 组 Street Lamp Pair，路口/道路表面侵入为 0。
- 3 个 Tree Variant；9 组 Lamp Pair 和 17 棵 Tree 因净距/包含性被确定性跳过。
- Street Furniture 确定性签名保持 `1b0c...` 开头的既有签名，布局前后相等。
- V18 Locked Validation 在几何等价比较前完成。

`required_node_count` 从 49 增至 63，用于把新增索引、V1/V2 Switch 和早期 Toggle 纳入累计门禁。

## 8. Houdini Live 现场状态与诊断

Preflight 结果：

- Houdini `21.0.440` 正在运行。
- RPC `18811` 可连接。
- MCP Health `3055` 正常。
- 当前 HIP：`PCG_Bike_CityRoad.hip`。

验证结束后的只读现场审计发现：

- `/obj/CityRoad_DEV` 当前为 Unlocked。
- Live 实例 `matchesCurrentDefinition = false`。
- HIP 当前显示 Unsaved。
- 顶层 44 个节点、27 个 `CR_*` Subnet 与合同一致。
- 本日志任务没有保存 Live HIP，也没有用磁盘 Definition 覆盖该实例。

全网络诊断未发现 Error Node，但发现 9 个 Warning Node，主要为无效 Group 与 Merge Attribute Mismatch，涉及道路朝向、道路/边界 Merge、Sidewalk、Marking 以及 Tutorial Lab 支路。26 个正式累计合同仍通过，但提交没有提供可用于证明“这些 Warning 全部是历史 Warning”的逐签名基线，因此不能把“无新增 Warning”视为已闭环结论。

## 9. Unity 资产与编辑器状态

提交 `21` 不修改 Unity 场景和运行时代码。Unity AssetDatabase 中主 HDA 身份保持：

| 项目 | 值 |
|---|---|
| Asset Path | `Assets/PCG/HDA/City/CityRoad.hda` |
| Asset Type | `UnityEditor.DefaultAsset` |
| GUID | `67d84be2a5065e14493d6b0d83e29db8` |

审计时 Unity `2022.3.62f2` 未处于 Play、Compile 或 Update 状态。打开场景包含 `PCG_City` 和一个未命名的 Dirty Scene；本任务不保存、不关闭，也不将其归因于提交 `21`。

新增日志经 `AssetDatabase.Refresh()` 后成功导入为 `UnityEngine.TextAsset`，GUID 与 `.meta` 一致；刷新完成后近 5 分钟 Console 的 Error / Warning 均为 0。

由于本提交没有 Bake 和 Scene 变更，当前验证只能确认 HDA 文件已被 AssetDatabase 识别，不能证明新的 Subnet Definition 已在 Unity 中完成一次成功 Cook/Bake。该项应在安全保存 Live 基线后，由后续专门的 Unity/Houdini 联合验收执行。

## 10. 移动端与架构评估

### 10.1 CPU / GPU 边界

| 阶段 | Phase21 方案 | 移动端影响 |
|---|---|---|
| Houdini Editor/Bake | Segment/Approach/Junction/Corridor 共享索引，减少重复扫描 | 缩短离线 Cook，不进入 Player |
| Unity Import/Bake | 仍消费 HDA Cook 后结果 | 本提交未测总耗时 |
| 移动端运行时 | 继续消费 Bake 后 Unity 原生数据 | 不依赖 Houdini Cook |
| 大规模设施渲染 | 本提交未实现 GPU Culling / Indirect Draw | 仍需后续 GPU 驱动方案 |

V18 优化的是 Houdini CPU Cook。它不会直接降低移动端 DrawCall、SetPass、Overdraw 或带宽，也不能替代 Chunk/Cluster、LOD 和 `DrawMeshInstancedIndirect`。

### 10.2 URP / Shader Variant / RenderPass

- 没有新增 RendererFeature 或 RenderPass，RenderPassEvent 不变。
- 没有新增 Shader、Keyword 或 Variant。
- 没有新增 RenderTexture、全屏 Blit 或 MRT。
- 没有侵入 URP 主流程。
- 没有修改 `Assets/Plugins/HoudiniEngineUnity/`。

因此 Phase21 不增加移动端 Shader Variant 爆炸或 Tile-Based GPU 带宽风险。其主要风险集中在 Houdini Definition 持久化、Live/Disk 一致性和网络维护。

## 11. 已知限制与后续建议

1. **Live/Disk 尚未完全一致**：当前 Live 实例 Unlocked、`matchesCurrentDefinition = false` 且 HIP Unsaved。后续任何 HDA 保存前必须先完成 Capture，对比并明确选择事实源，禁止直接 Update Definition。
2. **Warning 门禁证据不足**：全网络有 9 个 Warning Node，缺少父版本逐签名基线，无法证明本提交没有新增 Warning。
3. **Unity Cook/Bake 未闭环**：提交未包含场景或 Bake 结果；需验证 Unity 新实例、HDA Cook、六个输出层级、材质/Prefab 引用和 Console。
4. **Tree Multiparm 新实例默认仍有问题**：全新实例仍可能得到 Round/Round/Round，而非 Round/Tall/Wide。
5. **基准只代表同机相对 Cook**：临时克隆屏蔽 Fixture 专用诊断，且 JSON 不在提交内；不能外推为 Unity 或真机帧时间。
6. **运行时规模化渲染未实现**：Street Furniture 仍需 Chunk/Cluster、LOD、GPU Culling 与 Indirect Draw 才适合大规模移动端场景。
7. **StreetBuilding 不属于本提交**：提交只提供门禁基础设施；当前未跟踪业务资产必须独立 Capture、VerifyFast、VerifyFull 和记录。

建议下一阶段优先顺序：

```text
确认 CityRoad Live / Definition / HIP 一致性
    -> Capture 当前不可丢失基线
    -> 修复或登记 9 个 Warning 的精确签名
    -> Fresh 新实例默认参数验收
    -> Unity Cook + Bake + Console + 资产引用验收
    -> 100 / 225 Edge 基准在固定机器重新留档
    -> Street Furniture GPU Chunk / LOD / Culling / Indirect Draw
```

## 12. 阶段结论

提交 `21` 的核心价值不是增加新的道路视觉功能，而是把 CityRoad 的离线生成链从多个分支重复扫描，推进为共享的 Segment、Junction 与 Corridor 索引，并用 V1/V2 几何等价合同约束性能优化；随后将 191 个叶节点整理进 27 个单层 Subnet，使大型 HDA 网络具备更可控的模块边界和阅读顺序。

在当前审计中，Fresh Locked Instance 与 Live Source 均通过 26 个累计合同；100 Edge 本地基准显示 V18 Median 约降低 41.6%、P95 约降低 43.7%，V19 布局重构没有触发性能回退门禁。与此同时，Live/Disk 一致性、全网络 Warning、Unity Cook/Bake、新实例 Tree 默认值与移动端 GPU 渲染链仍未闭环，不能仅以 Contract PASS 或 Cook 性能改善替代这些验收。
