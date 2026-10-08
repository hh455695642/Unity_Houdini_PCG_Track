# Phase 31 开发日志：StreetBuilding 线脚、首层转角与门窗附件

> 文档类型：指定提交范围的最终有效功能快照
>
> 记录日期：2026-10-08
>
> 版本文件：`Phase31_StreetBuildingTrimAndCorner.md`
>
> 最终提交：`effbf2c5c2f57f8bf09ce5676734b108155aa7a5`（提交信息：`31`）
>
> 比较基线：`daad8ae`（Phase30 日志）；范围为其后的 5 次提交

## 1. 记录规则与阶段结论

本文沿用 Phase1 的环境、关联提交、功能、问题与方案、验证、性能和遗留事项结构。只记录截图范围内截至提交 `31` 仍有效的实现；同一功能以最终 HDA、HIP、Unity 代码和启用素材为准，不把中间方案、已取消输出或被替换的素材重复写成成果。

本阶段重点是：整理 StreetBuilding 节点网络；修复立面线脚端点与重复下沿；补齐首层临街侧面柱、腰线和凸角收口；为雨棚、招牌提供真实门窗挂点及独立随机选择；接入当前启用的测试素材；改善 Unity Cook 状态与失败信息。

素材和生成职责继续分离：StyleConfig 只保存素材及适配约束；实例面板控制街角开关、挂点方式、附件概率和数量上限。新增立面适配位不能反过来决定实例生成开关。

证据等级：

- **[已验证·静态]**：核对提交文件、最终 HDA definition 或保存的 HIP；证明实现存在，不代表端到端验收。
- **[已验证·专项]**：2026-10-08 在独立 `hython` 进程中，从最终 HDA 创建实例并运行行为合约；不保存生产资产，也不操作当前 Houdini Live Scene。
- **[已验证·现场]**：本轮通过 Unity Pipeline CLI 读取的实际 Editor 状态。
- **[历史还原]**：仅用于界定提交范围和问题来源，不以旧 patch 代替最终实现。
- **[待复验]**：未完成 Unity 生命周期、正式 Bake、干净检出或目标设备验证。

本轮六组专项合约通过，但完整累计验证在节点清单检查处失败，附件诊断专项也失败。因此不能把本阶段标记为“完整回归全部通过”。

## 2. 提交范围、环境与资产

### 2.1 关联提交

| 提交 | 日期 | 原始提交信息 | 本文采用的最终内容 |
|---|---|---|---|
| `12f623d` | 2026-09-28 | 节点整理 | 九阶段平铺网络、中文维护说明、稳定输出接口 |
| `e5e4975` | 2026-09-29 | 修复踢脚线一侧没有的问题 | 不依赖窗模块跨度的立面端柱 |
| `9bf16a0` | 2026-09-29 | 踢脚线移除效果修复 | 首层交界只保留有效腰线，开关及缺项预览一致 |
| `600cd24` | 2026-09-30 | 修复踢脚线屋顶部分 | 最终屋顶边缘输出及其独立开关行为 |
| `effbf2c` | 2026-10-08 | 31 | 首层转角、凹入腰线、门窗挂点、Cook 信息及启用素材收敛 |

范围净变更为 84 个文件，`+30636 / -17689` 行；其中大量为 Unity 场景序列化，不等同于手写代码规模。

### 2.2 环境和事实源

| 项目 | 当前值或路径 |
|---|---|
| Unity / URP | `6000.3.22f1` / `17.3.0` |
| Pipeline Package | `0.7.0-exp.1` |
| 本轮 Unity CLI | `1.0.0-beta.11`，属于本机工具版本，不计为本阶段项目升级 |
| Houdini | `21.0.440` |
| HDA 类型 | `pcgbike::StreetBuilding::1.0` |
| 主 HDA | `Assets/PCG/HDA/City/StreetBuilding.hda` |
| 主 HIP | `HoudiniProject/PCG_Track_21.0.440/PCG_Bike_StreetBuilding.hip` |
| 验证场景 | `Assets/PCG/Scenes/PCG_Building.unity` |
| 测试配置 | `Assets/PCG/Art/Building_Test/Style1/SBStyle_Test.asset` |

开始整理时，已跟踪文件无工作区差异，当前 HEAD 即提交 `31`。既有未跟踪资源不计入该提交的完整交付；本次不会提交、删除或补齐这些资源。

## 3. 节点网络整理与输出边界

**状态：已完成；[已验证·静态]。完整结构合约存在不同步问题，见第 9 节。**

最终 `StreetBuildingCore` 保持平铺 SOP 网络，共 40 个节点、9 个阶段分组。分组以职责组织，而非继续增加深层嵌套。

| 阶段 | 职责与主要节点 |
|---|---|
| `00_INPUT_VALIDATE` | 地块、临街、素材输入；备用地块；来源选择与规范化 |
| `10_RULES_AND_CATALOG` | 临街解析、实例生成规则和 Unity 素材目录解析 |
| `20_FACADE_CAPACITY` | 原始立面格与配额容量分配 |
| `30_FACADE_SELECTION` | 变体、线脚及最终立面模块选择 |
| `40_BUILDING_INSTANCES` | 正立面、侧背面、屋面和屋顶边缘实例 |
| `50_ATTACHMENT_INSTANCES` | 附件候选和实际附件实例点 |
| `60_PROXY_MODEL` | 体块、语法、素材校验及主代理模型 |
| `70_UNITY_CONTRACT` | 真实实例过滤、校验、缺项预览、metadata 和输出来源切换 |
| `80_OUTPUT_VALIDATE` | 统一输出接口 |

分组配套中文职责、输入、输出、修改注意和扩展说明，供后续手工维护。输入解析、容量分配、选型和附件输出仍各自独立。

七个输出的名称和索引保持稳定：

| 索引 | 输出 | 提交 31 的实际职责 |
|---|---|---|
| 0 | `OUT_BUILDING_LOD0` | 主建筑实例或代理模型 |
| 1 / 2 | `OUT_BUILDING_LOD1` / `OUT_BUILDING_LOD2` | 连接空几何的兼容出口，不是可交付 LOD |
| 3 | `OUT_DETAIL_INSTANCES` | 附件实例 |
| 4 | `OUT_BUILDING_COLLISION` | 连接空几何的兼容出口，不是可交付碰撞 |
| 5 | `OUT_BUILDING_METADATA` | 建筑生成诊断与 metadata |
| 6 | `OUT_BUILDING_PREVIEW` | 独立缺项预览 |

`lod_outputs_enabled` 隐藏，仅保留兼容字段。本文不把未输出的 LOD 或碰撞能力列为已开发成果。

## 4. 线脚端点、交界腰线与屋顶边缘

### 4.1 立面两端独立生成

**状态：已完成；[已验证·专项]。**

原问题是线脚端点随门窗选型遍历生成，双宽窗吞并原始格后可能漏掉一侧端柱。最终 `SELECT_FACADE_VARIANTS` 从原始立面格识别每条墙段起点和宽度，独立发射两端 `FacadeColumn`，不依赖门窗实际占格遍历。

- 主正面和 L 形凹入的次正面分别保留两端柱。
- 各层使用对应素材和层高，端点采用不与墙模块冲突的稳定标识。
- 缺少端柱素材时保留端点缺项槽；占位不混入真实实例。
- 关闭建筑线脚时同时移除相关实例和预览，不改变门窗、墙面等非线脚输出。

专项覆盖矩形、四角 L 形、双宽窗、完整/缺项素材以及开关隔离，共 20 项通过。

### 4.2 首层只保留有效交界腰线

**状态：已完成；[已验证·专项]。**

最终首层交界使用 `FloorBand`，从原始网格独立分配，放置基准为有效首层高度减去 `0.10m`。宽窗不会吞掉腰线格，重复位置不额外发射。

本阶段用户所指“踢脚线”涉及不同模块职责：端柱是 `FacadeColumn`，交界腰线是 `FloorBand`。已取消的首层额外 `Cornice` 不再作为生成能力描述，也不会残留在真实实例或缺项预览里。

40 项专项检查通过：住宅/商业、矩形/四角 L 形、完整/缺项素材、稳定重 Cook 及线脚开关往返。

### 4.3 屋顶保留屋面与女儿墙，不额外产生下沿

**状态：已完成；[已验证·专项]。**

最终屋顶保留 `RoofSurface`、女儿墙直段及阴阳角；屋顶下方不再输出额外 `Cornice` 实例或占位。屋顶和女儿墙仍按各自开关工作，关闭再恢复后结果保持一致。

专项同时确认屋面高度、女儿墙、首层交界腰线、立面端柱不被误删，40 项通过。这里记录的是最终保留结构，不保留中途“首层取消但屋顶下沿仍存在”的过渡行为。

## 5. 首层临街侧面、转角和凹入腰线

### 5.1 实例决定侧面装饰范围

**状态：已完成；[已验证·专项]。**

最终实例面板提供：

- `corner_building`：街角建筑（首层侧面装饰），默认关闭；
- `corner_street_side`：首层临街侧面，左侧 / 右侧 / 两侧，默认右侧，街角关闭时隐藏。

这是本阶段最终保留的首层装饰控制，不是旧的全建筑街角生成规则。它不改变道路识别、墙体、门窗分配、上层或屋顶。

StyleConfig 新增 `StreetSide = 1 << 4` 适配位，Inspector 显示“临街侧面（首层转角）”。它只表示素材可以匹配实例选中的首层临街侧面；既有 `All` 仍保持原四类立面位，不静默扩张历史素材范围。

### 5.2 柱去重与腰线凸角收口

选中的外侧墙段可获得首层端柱和腰线。正面与侧面共享的柱端点按空间位置去重，避免同一转角叠两根柱。

新增模块用途 `FloorBandCorner`，枚举值追加为 `22`，不重排既有载荷编号。首层线脚分组和编译器允许该用途；当正面与外侧临街面的有效腰线形成凸角、且存在兼容收口素材时，生成独立收口实例。L 形凹口不自动当作外侧凸角发柱或收口。

### 5.3 凹入段腰线与真实缺项区分

腰线与外侧端柱采用不同的适用判断：选定方向的 L 形凹入侧段仍需接续腰线，但不因此自动成为外侧柱/凸角挂点。

- 仅配置 `StreetSide` 腰线时，未选中的侧面没有装饰请求，不制造无意义缺项占位。
- 原有通用 `Side` 素材仍可按其范围覆盖侧面，不被新开关意外收窄。
- 素材目录真正缺少腰线时，继续报告缺项并输出预览，不能以“可选装饰”为由隐藏真实缺失。
- 上层端柱按上层素材解析，测试配置使用独立的细柱 Prefab。

20 项专项通过；保存的 MyTest 体块参数复现为 11 段腰线：正面 6、外侧右面 3、凹入右面 2。

## 6. 首层雨棚和招牌：实际门窗挂点

**状态：已完成；[已验证·专项]。Unity 真实 Prefab/Bake 链路待复验。**

实例参数 `ground_attachment_placement` 提供“网格随机”和“跟随实际门窗”，默认仍为网格随机。只改变首层雨棚与招牌的挂点来源，不改变标准层附件规则和立面配额。

“跟随实际门窗”直接读取 `SELECT_FACADE_MODULES` 的最终已分配模块，仅接受真实的 `Entrance`、`GroundShopDoor`、`GroundShop`，排除墙面与缺项位置。双宽商铺模块仍只算一个挂点。

输出携带 `attachment_host_id`、`attachment_host_role`、`attachment_host_span`，便于核对附件实际跟随哪个模块。挂点还须满足主/次正面、选中的外侧临街面、素材适配及实例覆盖范围。

概率和上限规则：

1. 每个挂点对雨棚、招牌独立抽样，可以都没有、仅雨棚、仅招牌或两者都有。
2. 每类附件在同一挂点不重复生成。
3. 上限截断按稳定身份和种子选择，不由 SOP 点遍历顺序决定，不长期偏向先遍历的正面。
4. 全局密度、各类概率、数量上限、附件总开关及显式覆盖继续生效；零概率、零密度或关闭时不残留附件。
5. 同输入同种子可复现，切换挂点模式不重写墙面和门窗分配。

挂点专项 10 项通过；转角/挂点组合 17 项通过，另验证 64 个概率种子与 32 个数量上限种子。50% 配置下，两类附件样本命中率约为 48.21% / 48.66%；正、左、右三个临街方向均能被选中。反转挂点流顺序后，截断选择保持不变。这些数据仅是合约样本，不是性能指标。

## 7. 当前启用素材与可编辑来源

**状态：部分完成；[已验证·静态]。材质依赖未全部纳入 Git。**

当前 `SBStyle_Test` 在本阶段新增内容中启用以下 Prefab；被替换或停用的候选不列为有效配置成果：

| 模块用途 | 当前启用 Prefab |
|---|---|
| 首层端柱 | `FirstFloor_Column_A` |
| 首层交界腰线 | `FirstFloor_FloorBand_A` |
| 腰线凸角收口 | `FirstFloor_FloorBand_Corner90_A` |
| 上层细柱 | `UpperLayer_Column_Slim_A` |
| 条纹雨棚 | `FirstFloor_Awning_Striped_B` |
| 侧挂招牌 | `FirstFloor_Sign_Blade_B` |
| 立体店招 | `FirstFloor_Sign_Workshop_C` |

模型和 Prefab 位于 `Assets/PCG/Art/Building_Test/Style1/Models/`、`Prefabs/`；保存的 HIP 含 `STYLE1_GROUND_DETAIL_KIT` 与 `STYLE1_SHOP_DETAILS_20261007` 素材网络。三款店铺配件保留原生 SOP 可编辑结构，采用独立模型、Prefab 和图集接入，不将美术几何塞入建筑规则网络。

已提交纹理包括 `Style1_Stone_BaseColor.png`、`Style1_Cycle_Sign.png` 和 `Style1_ShopDetails_Atlas.png`。但对应 4 个材质及 `.meta` 当前仍为未跟踪文件：

- `Assets/PCG/Materials/Style1_Stone_Trim.mat`
- `Assets/PCG/Materials/Style1_Cycle_Sign.mat`
- `Assets/PCG/Materials/Style1_Green_Awning.mat`
- `Assets/PCG/Materials/Style1_ShopDetails.mat`

提交的 Prefab 确实引用这些材质 GUID。因此本机显示正常不代表干净检出可完整复现；本文不将未提交材质算作提交 `31` 的正式交付。

## 8. Unity 侧 Cook 状态与回归工具

### 8.1 当前结果和历史诊断分开显示

**状态：已完成；[已验证·静态]，生命周期行为待复验。**

`StreetBuildingRecook.CurrentCookDiagnostic` 区分会话无效、正在生成、本次失败和已完成输出。未更新时明确显示“结果未更新”，历史成功信息加上历史标识，避免旧 PASS 被误当作本次结果。

Inspector 重绘只查询公开的会话/资产状态，不创建 Houdini Session，不读 HAPI 几何，也不追加警告日志。

Apply 请求失败时，`StreetBuildingStyleApplier` 在恢复事务前读取失败节点的 Cook 信息，先用 `ComposeNodeCookResult`，为空时再读取 HAPI Cook 状态字符串，避免恢复 Cook 覆盖最初失败原因。参数和已有事务数据仍按原有快照恢复。

### 8.2 资产搜索保持目标目录约束

**状态：已完成；[已验证·静态]。**

`Invoke-PcgRegression.ps1` 把输入的 HDA 搜索目录传给 Pipeline `find_assets --search_in`，避免不相关 Houdini Engine 缓存先占满结果上限而漏掉生产 HDA。

保存/候选导出辅助逻辑保留新首层街角参数和隐藏的 LOD 兼容字段；首层/标准层高度仍来自素材尺寸，不恢复旧的重复高度输入。

## 9. 本轮验证结果与明确缺口

### 9.1 完整 Fresh 合约未通过

执行：

```powershell
& 'D:/Software/Side Effects Software/Houdini 21.0.440/bin/hython.exe' `
  HoudiniProject/PCG_Track_21.0.440/scripts/tools/validate_streetbuilding_contract.py --source fresh
```

退出码为 `1`，失败于 `validate_core_cleanup`：`Core node inventory differs from the 40-node contract`。

实际 HDA 为 40 个节点；验证器的 `STAGES` 清单额外要求 `METADATA_ATTACHMENT_INPUTS`，因此清单实际比最终资产多一个节点。独立读取提交 HIP 中的 `StreetBuilding_DEV` 也得到 40 个节点且无该节点，不是只读 definition 时漏掉已保存的 HIP 实现。

### 9.2 独立专项结果

不修改原验证器。在独立 `hython` 进程安装最终 HDA、创建测试实例，逐项调用以下现有函数；每项异常单独记录，不将后续通过项冒充完整累计 PASS：

| 验证函数 | 结果 |
|---|---|
| `validate_trim_endpoints` | PASS，20 项 |
| `validate_single_ground_trim` | PASS，40 项 |
| `validate_roof_lower_trim` | PASS，40 项 |
| `validate_ground_attachment_hosts` | PASS，10 项 |
| `validate_ground_corner` | PASS，17 项，64 个概率种子、32 个上限种子 |
| `validate_trim_missing` | PASS，20 项，MyTest 11 段腰线 |
| `assert_attachment_diagnostics` | FAIL，读取不存在的属性：`No attribute with this name exists` |

前六个函数分别位于 `scripts/tools/validate_streetbuilding_<主题>.py`，最后一个位于 `validate_streetbuilding_contract.py`。专项操作仅发生在独立进程中的验证实例，不保存生产 HDA/HIP；没有重放历史 patch。

### 9.3 附件诊断尚未形成提交内闭环

Unity 端已加入 `attachment_diagnostics` 字段读取和中文格式化代码，合约也加入附件实际计数、规则来源、零概率、上限和挂点原因检查。但提交的 HDA 与 HIP 都未包含该字段的生成逻辑，专项读取因此失败。

所以“完整附件原因诊断”不是提交 `31` 已可用的功能，本文不将其写入已完成成果。已有 Cook 状态/失败信息改善与这条未闭合链路需分别评价。后续应核对并保全 Live 内容后单独补齐，不能通过删除断言或执行旧 patch 宣称通过。

### 9.4 Unity 与连接现场

- 初始 Unity Pipeline 门禁通过：正确版本的 Editor、Server 可达、状态 ready。
- 当前打开 `PCG_Building.unity`，19 个根对象，场景 Dirty；本次未保存或重新生成场景。
- Console 基线为 3 条 Error、8 条 Warning；采样时未编译、未编译失败。既有诊断不视为本次日志引入，也不能据此宣称现场无错误。
- Houdini RPC 与 HTTP health 正常，主 HIP 路径正确；预检在本机 Codex 配置解析 `service_tier = default` 时失败。本次没有通过原生 Houdini MCP 操作 Live Scene，未改动全局配置。
- CLI `1.0.0-beta.11` 拒绝技能文档中的 `--caller/--skill` 参数；只读状态检查去掉这两个标记后成功，无须修改项目或工具配置。
- 本次未执行会保存场景的完整 VerifyFull，也未完成 Unity Apply/Rebuild/Domain Reload、保存重开、正式 Bake 或移动端验证。

## 10. 性能、兼容性与扩展边界

本阶段没有增加 RendererFeature、RenderPass、RT、全屏 Blit 或自定义 Shader keyword；不产生本阶段新增的 Shader 功能组合。既有 URP 材质的 Instancing 命中、Variant 总量仍需在真实发布资产上核验。

CPU/Houdini 编辑期承担端点、装饰范围、挂点筛选和稳定随机分配；GPU 运行时只应消费 Bake 后的资产。省去无用线脚和重复转角可减少实例及重叠几何，但没有真机 DrawCall、SetPass、Overdraw 或带宽测量，不能量化帧耗收益。

每类附件继续受上限及既有总预算约束。新增图集配件不等于已经完成城市级合批、Chunk、GPU 剔除或 LOD；大量模块 GameObject 不应直接作为移动端最终运行结构。

扩展点继续保持独立：

- 素材用途和立面位只追加兼容语义，不重排旧编号。
- 实例面板承载生成开关，`SELECT_FACADE_VARIANTS` 承载线脚选型，`DETAIL_INSTANCE_POINTS` 承载附件挂点与选择。
- `attachment_host_*` 可用于 Bake 后追踪，未来诊断输出应与生成共享真实结果，不在 Inspector 重算一套规则。
- 模型网络、建筑生成和 Runtime 渲染分离；移动端不得运行 Houdini Cook。

## 11. 当前状态矩阵与后续事项

| 功能 | 状态 | 证据与边界 |
|---|---|---|
| 九阶段网络与稳定输出 | 已完成 | 最终资产静态确认；结构验证器清单不同步 |
| 立面端柱与首层交界腰线 | 已完成 | 专项通过 |
| 最终屋顶边缘与开关 | 已完成 | 专项通过 |
| 首层街角、凸角收口、凹入腰线 | 已完成 | 专项通过；不改变墙窗及上层 |
| 实际门窗挂点与独立随机选择 | 已完成 | 专项通过；真实 Prefab/Bake 待复验 |
| 启用的测试素材接入 | 部分完成 | Prefab/模型已提交，材质依赖尚未全部提交 |
| Cook 状态与失败信息 | 待复验 | C# 实现存在，Unity 生命周期未重新验收 |
| 完整附件原因诊断 | 部分完成 | Unity 消费端存在，HDA/HIP 生产端缺失 |
| 完整累计合约 | 待复验 | 本轮实际失败，不能以专项通过替代 |
| LOD / 碰撞出口 | 模块骨架 | 当前连接空几何 |
| 移动端真机性能 | 待复验 | 本阶段无设备测试结果 |

下一步应先对齐提交中的 HDA/HIP 与附件诊断合约，补齐正式素材依赖，再在保全现有场景的前提下执行完整双侧回归、保存重开和 Bake 检查。上述内容属于后续工作，本日志任务不代为实现或提交。
