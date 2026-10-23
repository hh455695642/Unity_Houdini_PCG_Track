# Phase 35 开发日志：CityRoad 沿街建筑与直接 Prefab 布置

> 文档类型：提交最终有效实现快照
>
> 记录日期：2026-10-23
>
> 当前主提交：`8b6d1a578dac52aa85e340e676738785a353f2a3`（`35`）
>
> 对比基线：`4117663`（`Phase34`）
>
> 版本文件：`Phase35_CityRoadFrontageBuildings.md`

## 1. 记录规则与范围

参照 Phase1 的环境、功能、问题、验证、性能与状态矩阵结构，记录提交 `35` 最终仍使用的开发内容。本阶段重点从独栋 StreetBuilding 转向 CityRoad 对整栋 Prefab 的沿街布置。

- **[已验证]**：本轮 Git 差异、最终源码／序列化资产检查，以及独立 Houdini 进程实际执行的测试；静态检查不等于 Unity 场景行为验收。
- **[历史还原]**：提交保存状态与开发工具中的审计信息，不视为本轮重新执行结果。
- **[待复验]**：实现存在，但本轮未执行的 Unity 实例化、保存重开、Bake、完整累计回归或移动端测试。
- **[未实现]**：本阶段没有交付的能力，不把接口、材质开关或示例资产当成完整运行时系统。

只描述最终“CityRoad HDA 直接指定 Prefab”路径，不把开发过程中已被替代的目录拼接、Catalog 或 Link 中间方案作为并存功能。历史 patch 只用于审计，本轮未运行或重放。

## 2. 版本环境与事实源

| 项目 | 当前版本／路径 |
|---|---|
| Unity Editor | `6000.3.22f1` |
| URP | `17.3.0` |
| Unity Pipeline | `0.9.0-exp.1`；本轮 CLI 为 `1.0.0-beta.6` |
| Houdini | `21.0.440` |
| 主 HDA | `Assets/PCG/HDA/City/CityRoad.hda`，类型 `pcgbike::CityRoad::1.0` |
| Houdini 工程 | `HoudiniProject/PCG_Track_21.0.440/PCG_Bike_CityRoad.hip` |
| 更新场景 | `Assets/PCG/Scenes/PCG_City.unity` |
| 新增验证场景 | `Assets/PCG/Scenes/PCG_City_Test.unity` |
| 建筑资产根 | `Assets/PCG/Generated/Buildings/CityFrontage/` |
| 生成源码 | `HoudiniProject/PCG_Track_21.0.440/scripts/tools/cityroad_frontage.vfl` |

提交日期为 2026-10-23，共涉及 139 个文件，主要包括 HDA／HIP、两个场景、建筑 Prefab／Mesh、CityRoad 编辑器桥接与验证工具。场景 YAML 变化量不代表新增算法规模。

本轮开始时无已跟踪文件的未提交修改，因此磁盘 HDA 可用于该提交的独立检查；未据此假定 Houdini Live Scene 与 definition 完全相同，也未同步或保存现场。

## 3. 已开发功能

### 3.1 CityRoad 独立沿街建筑分支

**状态：已完成；证据：[已验证：最终 HDA 结构、源码一致性及独立合约]。**

在 `CityRoadCore` 下新增 `CR_BUILDINGS`，通过 `OUT_STREET_BUILDINGS` 输出建筑实例点，输出索引为 **10**。该分支由 CityRoad 自己决定布置，Unity 不另写一套位置算法。

独立加载锁定 HDA 确认内部为八个节点：

| 节点 | 职责 |
|---|---|
| `ROAD_SURFACE` | 引入道路表面 |
| `UNPACK_ROAD` | 解包道路几何 |
| `FUSE_ROAD_VERTICES` | 合并道路顶点，建立边界邻接基础 |
| `REMOVE_THIN_TRIANGLES` | 清理影响边界判断的薄三角形 |
| `CENTERLINE_GRAPH` | 引入原道路中心线图 |
| `EMPTY_POINTS` | 提供可执行的初始输入 |
| `BUILD_FRONTAGE` | 边界提取、候选布置、避让、朝向与 Prefab 选择 |
| `OUT_INSTANCE_POINTS` | 输出专用实例点数据 |

本轮核对 `BUILD_FRONTAGE` 内嵌 VEX 与提交的 `cityroad_frontage.vfl` 完全一致。建筑分支不改写原有道路生成职责，既有道路网络检查继续保留。

### 3.2 基于道路外边界的两侧布置与避让

**状态：已完成；证据：[已验证：源码与独立夹具输出]。**

- 从清理后的道路三角面提取只有一侧相邻面的边界边，用来源三角形内部点判断朝外方向。
- 合并共线的细分边界段，避免道路细分成短边后整排建筑缺失。
- 结合原中心线端点识别真正道路终端；相邻曲线重合端点抵消，不把连接处误判为道路末端。
- 沿边界以 4m 步长尝试候选，最终是否保留由占地、净距和道路避让决定；4m 是试探步长，不是最终楼间距。
- 建筑前缘按人行道宽度和退距外移，中心再外移半个进深，朝向道路。
- 以最大占地矩形加侧向间隔和后方预留区做道路三角面／已接受建筑的分离轴检查，避免矩形侵入道路或互相重叠。
- 当前后方额外预留为代码中的 5m，不属于新增公开滑杆。

输出包含 `P`、`orient`、`N`、`up`、`unity_instance`、`building_id`、`building_variant`、占地尺寸、前缘位置与道路边界位置；detail 记录 `building_count`、`placement_owner`、`boundary_runs`、`rejected_road`。

生成责任标记为 `CityRoad/CR_BUILDINGS`。本阶段是道路边界上的建筑矩形布置，不应扩写为地块产权划分、任意建筑轮廓碰撞或自动地形贴合系统。

### 3.3 原生 Prefab 列表直接接入

**状态：已完成；证据：[已验证：最终 HDA 接口与空槽／任意名称合约]。**

HDA 的“Street Buildings / 沿街建筑”面板提供 `building_prefabs` 多重参数列表，每项为 `building_prefab#`，带 `heuassetpath=1` 标签，供 Houdini Engine 原生资产选择控件使用。

- 新 HDA 默认列表数量为 0，不硬编码项目示例素材。
- 忽略空白槽；全部为空或列表数量为 0 时输出 0 个建筑点。
- 非空路径直接写入 `unity_instance`，不根据目录和编号合成 Prefab 文件名。
- 艺术资源可以使用任意文件名，替换候选不改变基础布置的空间规则。
- 最大占地宽度／进深由用户填写，必须覆盖所有候选 Prefab 的实际占地；当前没有自动测量每个 Prefab 包围盒并分别求解。
- Prefab 约定：原点位于占地中心、基座 Y=0、正面朝本地 +Z。

职责边界保持明确：StreetBuilding 或人工流程制作整栋素材，CityRoad 面板指定整栋候选并负责沿街布局；不把街道布置数量和开关放进 StreetBuilding 的 StyleConfig。

### 3.4 基础公开参数

**状态：已完成；证据：[已验证：HDA 默认值、表达式及行为合约]。**

| 参数 | 默认值 | 最终语义 |
|---|---:|---|
| `building_enabled` | 1 | 沿街建筑总开关；无候选仍不生成 |
| `building_setback` | 3m | 基础退距，与人行道宽度共同形成道路侧间隔 |
| `building_spacing` | 2m | 最小建筑净间距 |
| `building_junction_margin` | 0m | 边界段端部候选避让距离 |
| `building_ground_height` | 0.6m | 建筑基座高度偏移，不是地形采样高度 |
| `building_seed` | 1729 | 随机种子；规则布置下只改变 Prefab 选择 |
| `building_width` / `building_depth` | 8m / 8m | 所有候选的最大占地宽度／进深 |
| `building_prefabs` | 0 | 直接指定的 Prefab 槽数 |

公开控件通过相对参数表达式驱动 `BUILD_FRONTAGE`，不是仅用于显示的字段。默认值与实例已保存值分别处理，不用新默认值覆盖已有艺术输入。

### 3.5 可关闭的错落布置

**状态：已完成；证据：[已验证：最终源码、HDA 默认值与开关回归]。**

新增错落布置开关，**definition 默认关闭**；关闭后保持规则布置输出。新增配置如下：

| 参数 | 默认值 | 职责 |
|---|---:|---|
| `building_layout_enabled` | 0 | 启用错落布局 |
| `building_setback_max` | 2.5m | 最大额外退距 |
| `building_gap_max` | 3m | 最大额外净距 |
| `building_empty_ratio` | 0.08 | 候选槽留空概率，不保证精确空置比例 |
| `building_group_length` | 30m | 沿街分组长度 |
| `building_within_group_jitter` | 0.35m | 组内退距扰动幅度 |
| `building_layout_seed_offset` | 0 | 布局种子偏移 |

同组共享基础额外退距，再叠加局部扰动并限制在 0～最大额外退距；净距与留空由独立键抽样。候选经同样的道路／建筑占地检查后才输出。

错落模式追加 `setback_applied`、`gap_applied`、`requested_slots` 与 `empty_by_rule` 诊断。布局键与 Prefab 选择键分开；布局种子实际由 `building_seed + building_layout_seed_offset` 构成，因此“改主种子只换外观不改位置”的保证只适用于错落关闭的规则模式。

重复 Cook 保持确定性。建筑 ID 基于边界端点与候选槽构造，不应宣称道路拓扑任意变化后仍保持永久身份。

Unity 增加 `PCG/CityRoad/Enable Varied Layout Selected` 菜单，只对选中的 CityRoad 实例启用公开开关、请求 Cook 并标记场景脏；Cook 失败恢复开关值，不自动保存场景。该动作不是修改 HDA 默认值，也不等同于完整输出事务回滚。

### 3.6 Unity 预览与发布边界

**状态：已完成；证据：[已验证：C# 差异]；真实 Unity 操作待复验。**

`CityRoadBakeWorkflow.IsBuildingOutput` 识别 `OUT_STREET_BUILDINGS` 后代；Live Preview 的可见性判定纳入建筑分支，不要求建筑节点符合道路拓扑片命名。

建筑沿用直接 Prefab 的网格与材质引用，接入已有预览／Bake 工作流，不新增 Unity 侧布置脚本。

编辑场景保存时不再要求先 Bake，也不因保存 Live Preview 直接报发布错误。`CityRoadBuildGuard` 仍在构建处理阶段调用 `ValidateBakedScene`，编辑保存与发布验收分离。移除保存时提示不代表允许将 Houdini Live Cook 作为移动端运行时依赖。

### 3.7 示例资产与测试场景

**状态：已完成；证据：[已验证：提交文件与静态结构]。**

- 新增 `Building_00.prefab`～`Building_07.prefab` 共 8 个整栋示例及 meta。
- 同目录提交 `SB_00_0.asset`～`SB_07_5.asset` 共 48 个 Mesh 资产及 meta；不能据文件数认定全部网格都被当前 Prefab 使用。
- 本轮静态检查 8 个 Prefab 均为 5 个 MeshFilter／MeshRenderer，引用独立 Mesh 资产与共享材质；没有新增建筑运行时控制脚本。
- 新增 `PCG_City_Test.unity`，提交中保留 `StreetBuilding_ManualSources` 与八项 Prefab 参数；人工源保留、隐藏及 EditorOnly 要求由 Unity 验证脚本检查，未在本轮执行该场景测试。
- `PCG_City.unity`、CityRoad HDA 与 HIP 同步提交保存状态；本轮未打开、切换或保存这些场景。

## 4. 问题与最终解决方案

| 问题 | 最终方案 | 证据／限制 |
|---|---|---|
| 薄三角形复用边界导致一整侧建筑缺失 | 提取边界前清理薄三角形 | 本轮退化三角形夹具通过 |
| 边界细分过短导致布置断续 | 合并共线边段，再按固定步长试探 | 本轮 3m 短段夹具通过 |
| 建筑朝向或道路末端封堵错误 | 用三角形内部点判外侧，中心线真实终端判禁区 | 本轮两侧朝向与终端检查通过 |
| 素材名称／目录绑定过强 | 原生 Prefab 多重参数与直接路径 | 任意名称、空槽及零槽检查通过 |
| 布置过于整齐但不能破坏已有结果 | 默认关闭的额外退距、净距、留空及分组扰动 | 关闭恢复规则输出、重复确定性检查通过 |
| 建筑输出未纳入 Live Preview 可见性 | 独立输出角色识别 | C# 已核对，Unity 操作待复验 |
| 正常保存编辑场景误触发布验收 | 保存允许 Live Preview，构建保留 Bake 门禁 | C# 已核对，实际构建待复验 |

## 5. 参数维护与累计验证工具

`cityroad_parameter_layout.py` 对现有完整参数模板做分组移动：Unity Inputs 在前、City Road 在后；道路来源、转角与调试参数归入对应页，街道设施／建筑使用 Tabs。它保留定义和已有值，而非重新创建同名参数。

回归门禁规范化 Houdini 自动生成的 Folder 标识，但继续比较子参数；原有公共接口哈希单独保护既有道路字段，新增建筑页由严格独立合约检查。保存时规范化 Prefab 多重参数模板、保全已指定路径，并检查清理后槽位值一致。

累计入口接入以下合约标识：

- `CityRoad.V52.StreetBuildingPlacement`：沿街布置、朝向、末端、移动与几何异常。
- `CityRoad.V53.BuildingControls`：公开控件、默认值与参数表达式。
- `CityRoad.V54.DirectPrefabAssignment`：原生选择标签、直接路径、空槽和任意名称。
- `CityRoad.V55.BuildingLayout`：错落布置与关闭回归。

`verify_cityroad_prefabs.cs` 是另一个 Unity 集成检查入口，会改写测试场景实例参数并 Cook，再在 finally 中恢复；覆盖直接引用、位置／朝向对齐 HAPI、共享 Mesh、材质及人工源隔离。它不是只读脚本，本轮没有运行，也没有把源码中的 `DIRECT_PREFABS_PASS` 当成实际测试结果。

`Invoke-PcgRegression.ps1` 对历史 HEU 重载时空 `CR_MAIN_PIPELINE` 的 warning 登记精确规范化签名，不是忽略所有 Cook warning；目标输出错误与其他新 warning 仍受门禁约束。

## 6. 本轮验证记录

### 6.1 已执行检查

1. 初始 `Ensure-UnityPipeline.ps1` 通过：Editor 版本匹配、Pipeline 可达、`editorStatus=ready`。
2. `Ensure-HoudiniMcp.ps1` 通过：18811 RPC、CityRoad HIP、3055 health、Codex 配置解析及服务端 43 项工具发现正常。预检没有证明当前会话原生工具已调用；本轮未执行 Live MCP 操作。
3. 使用 Houdini 21.0.440 的 `hython.exe` 在独立进程加载磁盘 HDA，新建锁定临时实例；核对八节点建筑分支、输出索引 10、内嵌 VEX 与源码一致。
4. 导入并执行 `validate_cityroad_frontage.validate(asset)`：通过，基础夹具输出 20 点，两侧各 10 栋。
5. 执行 `cityroad_parameter_layout.validate(asset.parmTemplateGroup())`：返回 True。
6. 结束时再次运行 `Ensure-UnityPipeline.ps1`：通过，Editor 为 ready；新增文档 `git diff --no-index --check` 无空白错误。

沿街独立合约实际覆盖：直接 Prefab／空槽／零槽、规则模式种子只换外观、间距、退距、端部避让、高度、错落退距与净距范围、全留空、重复确定性、错落关闭恢复、薄三角形、短边细分、总开关和道路平移传播。

这些测试使用独立夹具，不加载或保存生产 HIP／Scene，不等同于生产城市路网完整空间验收或累计 VerifyFull。

### 6.2 待复验边界

- `PCG_City_Test` 真实 Prefab 实例化、HAPI 到 Unity 坐标转换、Renderer 可见性与素材引用。
- 保存重开、HEU Reload、多重参数槽位保全及启用错落菜单的失败路径。
- 完整 `Invoke-PcgRegression.ps1` 的 VerifyFast／VerifyFull 与全部原有道路行为。
- 完整 Bake、发布构建门禁与移动端无 Houdini 依赖检查。
- 生产路网的复杂路口／坡度、不同占地候选与高密度建筑的碰撞和性能验收。

## 7. 性能、兼容性与扩展风险

| 阶段 | 当前分工与成本 |
|---|---|
| 编辑期 Houdini | CPU／VEX 完成边界、候选、道路三角形与建筑矩形检查；不在移动端逐帧执行 |
| Unity 编辑预览 | 复用整栋 Prefab 的 Mesh／材质，但仍有实例层级与 Renderer 成本 |
| 运行时 | 必须消费 Bake 后 Unity 原生数据；本阶段没有运行时 Houdini Cook |

当前求解包含边段合并的成对搜索、候选对道路三角面的扫描、候选与已接受建筑的比较；不能称为已完成空间索引或大路网性能优化。后续大规模扩展应先测 Cook 时间，再考虑空间分区／邻域查询。

每栋示例有 5 个 Renderer，大量重复实例仍可能产生较高 DrawCall、SetPass 和阴影成本。共享材质或 Instancing 开关不等于实际合批；本轮未取得 Frame Debugger、Profiler 或 Mali／Adreno／Apple GPU 数据。

本提交未新增 Shader、RendererFeature、RenderPass、功能 keyword、全屏 Blit 或中间 RT，沿用 URP 既有渲染路径；总 Variant 数仍需构建统计，不能承诺低于 200。未新增 Indirect Draw、Compute Culling 或建筑 LOD。

扩展点是 `CR_BUILDINGS` 的独立布置分支、公开实例参数和实例点 metadata。新增候选适配规则应明确占地约束与发布成本，不把 CityRoad 变成完整 StreetBuilding 素材生成器，也不把布置责任移到运行时 CPU 循环。

## 8. 当前状态矩阵与交付边界

| 功能 | 状态 | 结论 |
|---|---|---|
| CityRoad 两侧沿街建筑与输出槽 10 | 已完成 | 最终 HDA 与独立行为合约已确认 |
| 原生 Prefab 多重参数直接接入 | 已完成 | 空槽、任意名称与引用传输已测；Unity 实例待复验 |
| 公开布置参数与面板分类 | 已完成 | 默认值、表达式、分类与行为检查通过 |
| 可关闭错落布局 | 已完成 | 默认关闭；独立开关／范围／确定性检查通过 |
| 8 个示例 Prefab 与测试场景 | 已完成 | 已提交，静态结构已核对 |
| Unity 预览／编辑保存兼容 | 已完成 | 实现已核对，实际操作待复验 |
| 完整 Bake／发布／累计回归 | 待复验 | 本轮未执行完整链路 |
| 大路网 Cook 与移动端渲染性能 | 待复验 | 没有本轮性能基准 |
| 自动 Prefab 占地测量、运行时 GPU 剔除／LOD | 未实现 | 不属于当前交付能力 |

后续优先验证真实城市场景的直接 Prefab 链路、重开与 Bake，再测大规模布置和移动端渲染成本。本轮只新增 Phase35 文档，不改代码或资产，不提交 Git；任务前已有 Art、Terrain Shader、三份 HDA 手册、PCG Tests、ReferenceFinder 等未跟踪文件原样保留，不计入本次交付。

结束检查时另发现 `Assets/PCG/Scenes/PCG_City_Test.unity` 出现已跟踪修改；它在初始检查中尚未出现。本轮未执行该场景写入／保存，修改来源未确认，已保留且未纳入本次文档改动或提交 35 的事实依据。
