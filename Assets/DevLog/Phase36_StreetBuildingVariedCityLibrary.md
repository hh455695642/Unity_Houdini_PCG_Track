# Phase 36 开发日志：StreetBuilding 多样化街屋库与 CityRoad 接入

> 文档类型：提交最终有效实现快照
>
> 记录日期：2026-10-24
>
> 当前主提交：`47dc8ccbc51f3128a591034e09c32e8494407c6a`（`36`）
>
> 对比基线：`30b06e1`（`Phase35`）
>
> 版本文件：`Phase36_StreetBuildingVariedCityLibrary.md`

## 1. 记录规则与范围

参照 Phase1 的环境、功能、问题、状态矩阵、性能与验证结构，记录提交 `36` 最终仍保留和使用的开发内容。重点是将 StreetBuilding 正式素材生成的多样化整栋建筑 Bake 为 Unity 原生资产，并接入 CityRoad 沿街建筑槽位。

- **[已验证：静态]**：本轮核对 Git 差异、Recipes、Prefab 和场景序列化数据；不等于重新 Cook、Bake 或运行场景验收。
- **[历史还原]**：提交内 README 与配方保存的开发记录，未作为本轮实际测试结果。
- **[待复验]**：需要 Unity/Houdini 实际行为、保存重开、累计回归或移动端真机确认的项目。
- **[未实现]**：本提交没有交付的系统，不把原生 LODGroup 或材质 Instancing 开关写成 GPU 驱动渲染管线。

最终 CityRoad 槽位使用 `MyTestCityVaried`。`MyTestCityFrontage` 中仍被复用的模块和材质属于有效依赖，但其 README 中较早的槽位接入描述不再代表最终场景状态。已删除的旧 `CityFrontage` 资产不作为本阶段现用建筑库记录。

## 2. 版本环境与事实源

| 项目 | 版本／路径 |
|---|---|
| Unity Editor | `6000.3.22f1` |
| URP | `17.3.0` |
| Unity Pipeline | `0.9.0-exp.1`；本轮 CLI 为 `1.0.0-beta.6` |
| Houdini | `21.0.440` |
| 建筑制作场景 | `Assets/PCG/Scenes/PCG_Building.unity` |
| 城市验证场景 | `Assets/PCG/Scenes/PCG_City_Test.unity` |
| 最终建筑库 | `Assets/PCG/Generated/Buildings/MyTestCityVaried/` |
| 共享模块来源 | `Assets/PCG/Generated/Buildings/MyTestCityFrontage/Modules/` |
| 材质目录 | `Assets/PCG/Materials/Buildings/MyTestCityFrontage/` |
| HDA | `Assets/PCG/HDA/City/CityRoad.hda`、`StreetBuilding.hda` |
| HIP | `HoudiniProject/PCG_Track_21.0.440/PCG_Bike_CityRoad.hip`、`PCG_Bike_StreetBuilding.hip` |

提交共涉及 592 个文件，主要是生成资产替换、Mesh／Prefab、场景和 HDA／HIP 保存状态，以及少量验证工具修改。序列化文件行数不代表新增算法规模；本提交没有 C# 或 Shader 源文件变更。

本轮只新增开发日志，不修改 HDA、HIP、场景、Prefab、材质和生成数据，不重放历史 patch，不把 Git 版本恢复到当前编辑器。工作区原有未跟踪资源、测试目录和操作手册不计入提交 `36` 的成果。

## 3. 最终开发成果

### 3.1 八种多样化街屋配方与持久化 Prefab

**状态：已完成资产交付；证据：[已验证：静态]。**

最终输出为 `PF_MyTestVaried_00.prefab` 至 `PF_MyTestVaried_07.prefab`。以下尺寸是生成配方的宽深，不是包含所有突出附件的精确包围盒；近景统计来自提交保存的 `Recipes.json`，不是本轮 GPU 实测。

| 索引 | 宽×深（米） | 层数 | 最终轮廓／首层用途 | 近景 Renderer | 近景三角形 | 远景三角形 |
|---|---|---|---|---|---|---|
| 00 | 4×6 | 2 | 矩形住宅 | 6 | 4,028 | 12 |
| 01 | 8×6 | 3 | 矩形商业 | 10 | 8,301 | 12 |
| 02 | 6×8 | 5 | 矩形住宅 | 12 | 12,408 | 12 |
| 03 | 8×8 | 8 | 矩形住宅 | 9 | 15,943 | 12 |
| 04 | 8×8 | 4 | L 形、前侧缺口、转角商业 | 10 | 8,238 | 24 |
| 05 | 8×8 | 6 | L 形、后侧缺口、住宅 | 10 | 17,604 | 24 |
| 06 | 4×8 | 7 | 矩形窄高住宅 | 9 | 8,928 | 12 |
| 07 | 8×8 | 2 | 矩形宽面商铺 | 10 | 5,722 | 12 |

差异不再只有尺寸和楼层，还包含门窗数量与排列、橱窗覆盖、雨棚／招牌、空调／消防梯、女儿墙和屋顶附件。它们是已有 StreetBuilding 能力的配方应用，不应全部重复算作本提交新增生成算法。

### 3.2 制作源、配方与素材配置分离

**状态：已保存工作源与配方；证据：[已验证：静态]、[历史还原]。**

建筑场景保存 `MyTest_Varied_Authoring` 工作源，同时仍存在原始 `StreetBuilding_MyTest` 和先前的 `MyTest_CityAuthoring_00`。

- `Recipes.json` 保存实例生成参数、变化种子、布局种子、完整 HAPI preset、Prefab 路径、包围盒和 Bake 统计。
- `SBStyle_MyTestCityVaried.asset` 负责素材及适配约束；建筑尺寸、门窗配额、用途和排列由实例配方管理。
- 按配方恢复工作源、调整实例参数、检查真实输出后再增量 Bake，最后替换 CityRoad 槽位。
- Bake 后的 Mesh 是持久化结果，修改制作源不等于自动更新已保存的建筑 Prefab。

提交 README 记录正式素材可行性与 Bake 检查，以及原始 MyTest 和前一工作副本保持不变；这些属于历史记录。本轮确认对象与配方存在，未重新执行完整 preset 恢复、素材不覆盖实例参数和保存重开合约。

### 3.3 共享材质近景合并、远景壳体与原生 LOD

**状态：已完成序列化配置；证据：[已验证：静态]。**

近景按共享材质组织合并 Mesh，最终每栋 6–12 个 Renderer；远景使用独立低模，每栋 1 个 Renderer。矩形远景为 12 三角形，L 形为 24 三角形，保留轮廓差异。

8 个最终 Prefab 各有一个 Unity 原生 `LODGroup`。本轮 YAML 检查得到：

| 索引 | 近景切换阈值 | 远景剔除阈值 | Prefab 全部 Renderer | BoxCollider |
|---|---|---|---|---|
| 00 | 0.045 | 0.015 | 7 | 1 |
| 01 | 0.06 | 0.015 | 11 | 1 |
| 02 | 0.1038125 | 0.015 | 13 | 1 |
| 03 | 0.15374999 | 0.015 | 10 | 1 |
| 04 | 0.07875 | 0.015 | 11 | 2 |
| 05 | 0.11624999 | 0.015 | 11 | 2 |
| 06 | 0.13499999 | 0.015 | 10 | 1 |
| 07 | 0.057796884 | 0.015 | 11 | 1 |

全部 Renderer 数包含近景与远景，不是两级同时渲染的 DrawCall 数。README 记录阈值计算为包围盒最大尺寸 / 160，并限制在 0.045–0.18；这里的阈值是屏幕相对高度，不是固定世界距离。

矩形使用一个 BoxCollider，L 形使用两个 BoxCollider。最终 8 个 Prefab 均未序列化 MonoBehaviour，使用原生 Mesh、Renderer、LODGroup 和碰撞组件，不依赖运行时 Houdini Cook。实际 LOD 切换、碰撞贴合与遮挡效果仍需目标场景复验。

### 3.4 CityRoad 最终槽位与街区密度

**状态：已接入保存场景；证据：[已验证：静态]。**

`PCG_City_Test.unity` 保存的 8 个建筑路径已指向 `MyTestCityVaried/PF_MyTestVaried_00..07.prefab`，并存在对应实例输出路径。沿用 Phase35 的 CityRoad 直接指定整栋 Prefab 链路，不另建一套 Unity 布置算法。

| CityRoad 实例参数 | 最终值 | 含义 |
|---|---|---|
| `building_spacing` | 1.2 | 最小建筑净间距，米 |
| `building_gap_max` | 0.8 | 最大额外净距，米 |
| `building_empty_ratio` | 0.015 | 留空槽概率 |
| `building_group_length` | 55 | 沿街组长，米 |
| `building_within_group_jitter` | 0.1 | 组内退距扰动，米 |
| `building_setback_max` | 1 | 最大额外退距，米 |

上述值逐项与场景序列化参数核对一致。密度属于 CityRoad 实例，不属于建筑素材 StyleConfig。保存的预览引用不等于已经完成整个城市的运行时 Bake 或移动端验收。

### 3.5 共享依赖与材质接入

**状态：已保留有效依赖；证据：[已验证：静态]、[历史还原]。**

最终多样化库继续复用 `MyTestCityFrontage/Modules` 和既有共享材质，不能因为 CityRoad 换成 Varied 槽位就删除整个早期目录。该模块目录包含女儿墙直段、外角和凹角 Prefab 等制作依赖。

本提交的 `Materials/Buildings/MyTestCityFrontage` 目录包含 7 个材质，覆盖沥青、假室内、玻璃、内墙、装饰和 Trim；静态检查均启用 `m_EnableInstancingVariants`。最终 Varied 库 README 的“不新增材质副本”描述的是这一步继续复用素材，不能扩展理解为整个提交没有新增材质。

本阶段没有新增 Shader 源码或自研 Shader keyword。URP/Lit 的材质状态和管线变体仍有自身成本，未执行完整 variant 数量审计。

### 3.6 回归工具超时与隔离合约登记

**状态：工具与合约登记已修改；实际集成行为待复验。**

- `.agents/scripts/Invoke-PcgRegression.ps1` 将 StreetBuilding Pipeline EditMode 测试调用超时和轮询截止时间由 300 秒同步延长为 900 秒，为逐案例原生 HARS 进程启动／退出保留时间；此处没有删减既有行为断言。
- `streetbuilding_contract.json` 新增 `StreetBuilding.Tests.PerCaseHapiIsolation`、`StreetBuilding.Tests.NativeCookThreadIsolation`、`StreetBuilding.Tests.FileLibraryIdentity` 三个合约 ID。
- `validate_streetbuilding_contract.py` 新增前两个隔离合约 ID 必须存在的检查。

合约登记检查不等于实际完成 HAPI／线程隔离测试；本次 Python 增量也没有新增 `FileLibraryIdentity` 的对应执行断言。提交没有 C# 测试实现变更，不能把工作区未跟踪的 `Assets/PCG/Tests/` 当作已随 `36` 交付的内容。

## 4. 问题、处理与边界

| 问题 | 最终处理 | 保留边界 |
|---|---|---|
| 街屋外形与首层用途重复 | 使用矩形／L 形、2–8 层、住宅／商业的 8 种配方 | 不把配方应用写成新生成算法 |
| 模块化近景 Renderer 较多 | 按共享材质合并，增加独立低模远景 | 近景仍有 6–12 个 Renderer，必须评估整街预算 |
| 建筑碰撞成本与轮廓差异 | 矩形一个、L 形两个 BoxCollider | 不等于精确外立面碰撞 |
| 替换建筑库易误删制作依赖 | 明确最终槽位与共享 Modules／材质各自职责 | 不按目录名称推断资源已退役 |
| 较重集成测试受 300 秒截止限制 | 调用与轮询均延长至 900 秒，登记隔离合约 | 超时增加不是测试成功证明 |

HDA／HIP 二进制文件确有变化，但本轮没有对内部网络逐节点比较；不从二进制差异臆测新的道路或建筑算法。

## 5. 当前状态矩阵

| 项目 | 状态 | 证据边界 |
|---|---|---|
| 8 种最终街屋配方与 Prefab | 已完成资产交付 | 配方、文件及序列化结构已核对 |
| CityRoad 最终建筑槽位和密度 | 已配置 | 保存场景已核对，未重 Cook |
| 原生近远 LOD 与 BoxCollider | 已配置 | 组件及阈值已核对，运行效果待复验 |
| 工作源、完整 preset 与素材职责分离 | 已保存／待行为复验 | 不覆盖实例参数等累计合约未重跑 |
| 回归超时与隔离合约登记 | 已完成工具修改 | 完整集成测试未重跑 |
| GPU Culling／Indirect／Chunk 渲染 | 本提交未新增 | 不以 Instancing 开关替代该能力 |
| Android／iOS 真机性能 | 待复验 | 没有本轮 GPU、带宽或帧时间数据 |

## 6. 性能、兼容性与扩展风险

当前优化以离线 Bake、材质合并、原生 LOD 和简单碰撞为主。生成与素材整理在编辑期完成，运行时不需要 CPU 逐模块生成建筑，也不需要 Houdini Cook；但沿街大量 GameObject／Renderer 的 CPU 管理和提交成本仍然存在。

- **CPU**：检查可见建筑数量、Renderer 管理、碰撞体数量和实际 DrawCall／SetPass；材质开启 Instancing 不保证所有 Mesh 都能合批。
- **GPU**：远景壳体明显降低几何复杂度；近景最高配方仍有 17,604 个三角形。玻璃、室内表现、阴影和过绘制需按移动端摄像机实测。
- **带宽与 Pass**：本提交没有新增 RendererFeature、RenderPass 或中间 RT；不能据此认定 URP 整帧带宽已经达标。
- **兼容性**：使用 Unity 原生组件和共享 URP 材质；Android Mali／Adreno 与 iOS Metal 的外观、LOD 和性能仍须真机确认。
- **扩展点**：需要扩大城市规模时，可在 Bake 后增加 Chunk／Cluster、GPU 剔除与间接绘制数据层。本阶段尚未交付该层。

## 7. 本轮验证记录

本轮是日志整理任务，验证对象为提交事实与文档准确性，不是重新开发或重新 Bake。

| 检查 | 结果 |
|---|---|
| `git show`／`git diff HEAD^ HEAD` | 确认主提交 `36`、父提交 `Phase35` 及资产／工具变更范围 |
| Recipes JSON 解析 | 确认 8 条最终配方、近远景统计与尺寸楼层 |
| 最终 Prefab YAML 检查 | 确认 8 个 LODGroup、各级阈值、Renderer 与 BoxCollider 数量，以及无 MonoBehaviour |
| 城市场景静态检查 | 确认最终 8 个 Varied 路径和 6 项密度参数 |
| 材质序列化检查 | 7 个目标材质的 Instancing 开关均已启用 |
| `Ensure-UnityPipeline.ps1` | 任务开始和文档完成后均通过，Editor 为 ready，Pipeline 可达 |
| `Ensure-HoudiniMcp.ps1` | RPC、当前 HIP、HTTP health、配置解析与服务端 43 个工具发现通过 |
| Houdini 会话工具实际调用 | 本轮未执行；服务端发现成功不等于当前会话已加载原生工具 |
| Cook／Bake、VerifyFast／VerifyFull、EditMode 集成测试 | 本轮未执行，不引用 README 代替测试通过结果 |
| 保存重开、移动端构建与真机 | 本轮未执行 |

## 8. 后续验证建议

1. 从最终工作源恢复各配方，检查门窗真实计数、缺失模块和“素材不覆盖实例参数”，覆盖保存重开与重新 Bake。
2. 在 CityRoad 最终场景验证槽位、建筑朝向、退距、碰撞和 LOD 切换；确认共享 Modules／材质依赖完整。
3. 执行 StreetBuilding 累计回归，确认逐案例 HAPI／线程隔离及文件库身份行为，而非只检查合约名称存在。
4. 以目标赛车摄像机和整街可见数量，测量 Android／iOS 的 CPU 提交、GPU 帧时、阴影和透明过绘制，再确定可用密度与 LOD 阈值。

本阶段交付结论：提交 `36` 将正式素材的多样化街屋配方、原生近远 LOD／碰撞和 CityRoad 最终接入保存为可复用资产；性能收益与完整累计行为仍按上述证据边界区分，不以资产存在代替运行验收。
