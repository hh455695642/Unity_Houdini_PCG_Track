# Phase 30 开发日志：StreetBuilding 素材配置与实例生成参数收敛

> 文档类型：指定提交范围的最终有效功能快照  
> 记录日期：2026-09-28  
> 版本文件：`Phase30_StreetBuildingInstanceAuthoring.md`  
> 最终提交：`a06ec586a758f32c7a9e8f613b802f69610e6e10`（提交信息：`30`）  
> 范围：`aec7b92` 至 `a06ec58`，共 18 次提交；比较基线为 `e22d894`  
> HDA：`Assets/PCG/HDA/City/StreetBuilding.hda`  
> HIP：`HoudiniProject/PCG_Track_21.0.440/PCG_Bike_StreetBuilding.hip`  
> Unity 场景：`Assets/PCG/Scenes/PCG_Building.unity`

## 1. 记录口径与阶段结论

本文按 Phase1 的功能快照、证据等级、问题与验证方式组织，只记录截图所列提交中截至提交 `30` 仍然使用的最终实现。中途被删除的系统不展开为开发成果，同一功能多次改写时只记录提交 `30` 的行为。

当前 StreetBuilding 的职责分配已经收敛：

```text
显式绑定的 StyleConfig
    -> 首层 / 上层 / 屋顶素材、尺寸、权重、适用范围
    -> 编译 STYLE 素材目录
                                        ┐
HDA 实例面板                            ├-> HDA 规则求解与模块选择
    -> 体块、数量、用途、排列、开关       │       -> 真实模块实例
    -> 显式楼层/立面覆盖、附件覆盖       │       -> 独立缺项预览与诊断
外部地块与临街输入                     ┘       -> 完整性检查后允许 Bake
```

本阶段有效成果包括：三层素材配置与中文 Inspector、实例面板生成参数、门窗模块数量计算、四种排列、四角 L 形缺口、统一墙面与侧背面窗、实墙 AC 挂接、屋顶/女儿墙/线脚独立控制、自动缺项预览、Bake 完整性门禁，以及 Unity 6 与 Pipeline CLI 工具链升级。

特别约定：素材权重和尺寸只影响候选筛选，不是生成配额；StyleConfig 不保存或编译门窗数、用途、排列、密度和生成开关。普通 Recook 在种子和输入不变时保持结果一致。

## 2. 证据等级、环境与资产

### 2.1 证据等级

- **[已验证·静态]**：直接核对提交 `30` 的 C#、资产、场景、参数接口和累计验证器；可证明实现存在，不等同于完整运行验收。
- **[已验证·现场]**：本次通过 Unity Pipeline CLI 读取的 Editor、AssetDatabase 和场景状态。
- **[已验证·Fresh HDA]**：本次在独立 Houdini 进程中新建锁定实例运行累计合约；不等同于 Unity 生命周期或移动端验收。
- **[历史还原]**：仅用于界定截图中的提交范围和查明修改来源；正文功能以最终代码为准。
- **[待复验]**：实现存在，但当前完整行为、保存重开、Player 或目标设备验证尚未完成。
- **[未实现]**：本范围没有形成可交付运行链路的能力。

### 2.2 版本环境

| 项目 | 提交 30 的状态 | 证据 |
|---|---|---|
| Unity | `6000.3.22f1` | ProjectVersion 与本轮 Editor 版本一致 |
| URP | `17.3.0` | `Packages/manifest.json` |
| Unity Pipeline | `0.7.0-exp.1` | Manifest 与前置门禁 |
| Unity CLI | 本轮 `1.0.0-beta.6` | 前置门禁；属于本机工具版本 |
| Unity MCP | `0.91.0` | Manifest |
| Splines | `2.9.1` | Manifest |
| Test Framework | `1.6.0` | Manifest |
| Houdini | `21.0.440` | RPC 预检 |
| StreetBuilding 类型 | `pcgbike::StreetBuilding::1.0` | 合同与验证器 |

截图范围内累计 diff 为 195 个 changed paths，`+346372 / -285704` 行。大量行数来自 Unity 场景序列化，不代表等量手写功能代码。

### 2.3 当前素材与验证场景

AssetDatabase 本轮找到三份 StyleConfig：

- `Assets/PCG/Art/Building_Test/Style1/SBStyle_Test.asset`；
- `Assets/PCG/Art/StreetBuilding/urban_brick_mixeduse_01/SBStyle_urban_brick_mixeduse_01.asset`；
- `Assets/PCG/Art/StreetBuilding/urban_stucco_residential_01/SBStyle_urban_stucco_residential_01.asset`。

`Building_Test/Style1` 接入首层门、墙、窗、标准层单宽/双宽窗、屋面与空调 FBX，用于实际素材尺寸及不完整素材生成验证。`SBStyle_Test` 当前首层和标准层高度均为 3m，Cell 宽度为 2m。

场景保存数据包含 Brick/Stucco 展示建筑、三栋既有 StreetBuilding 和新增 `StreetBuilding_MyTest`；对象名称只用于定位，最终生成参数来自各自 HDA 实例。

## 3. 三层 StyleConfig：只管理素材

**状态：已完成；[已验证·静态]。**

### 3.1 数据结构

`StreetBuildingStyleConfig` 按首层、上层、屋顶组织模块。每层可容纳墙面/门窗、转角、柱/腰线/檐口、屋面/女儿墙、附件等适用分组。

当前对美术开放的数据为：

- Cell 宽度、首层高度和标准层高度；
- Prefab 或 FBX Model Prefab 引用；
- 模块用途、启用状态、候选权重；
- 横向占格、固定高度或跟随层高、包围盒适配方式；
- 可用立面；楼层归属从所在首层/上层/屋顶分组派生。

同一个模块的组合几何由 Prefab 自身承载。隐藏的层迁移字段只服务于旧资产迁移；其存在不代表恢复风格生成规则。

### 3.2 无版本素材载荷

编译器输出：

```text
STYLE|CellWidth|GroundFloorHeight|TypicalFloorHeight
M|Group|Role|PrefabName|AssetPath|WidthSpan|DepthSpan|HeightType|ResolvedHeight|
  Weight|AllowedFacades|Floor|BoundsSizeXYZ|BoundsMinXYZ
```

模块行按 Ordinal 稳定排序，浮点使用 Invariant Culture，完整载荷计算 SHA-256。模块变体名称直接使用 `Prefab.name`；Prefab 名称和路径不得包含分隔符或换行。重复检查按楼层、用途、Prefab 名称和立面范围进行。

素材层不再需要额外填写风格标识、发布版本或手工 VariantId，也不要求填写允许的 Prefab 目录。导入模型作为 Unity Model Prefab 可直接参与校验；现有项目自有参考风格 Auditor 仍单独检查依赖归属。

### 3.3 校验与无损迁移

- Prefab 根 Transform 必须归零；仅接受 Transform、MeshFilter、MeshRenderer，不接受 Missing Script 或额外行为组件。
- 校验实际 Bounds 与声明的网格跨度、高度和 Pivot；不会靠生成端非等比缩放掩盖不合规素材。
- 保留 URP/Lit 材质要求；正式完整性检查还要求 Instancing，超过三个不同材质给出移动端提示。
- 三层迁移先构造目标列表再替换旧列表，不复制 Prefab 或改变 GUID。
- 首层侧背墙迁移为 GroundWall，上层侧背墙迁移为 MiddleBlank；方向、权重与引用保留，由可用立面限制候选。
- 批量迁移提供 Undo 与失败恢复，迁移工具不会自动保存资产。

## 4. 素材 Inspector 与实例操作入口

**状态：已完成；[已验证·静态]。**

StyleConfig Inspector 按“首层、上层、屋顶”折叠显示模块数量。模块标题展示 Prefab 名称、用途、占格和权重，支持启停、上下移动、删除与添加。

用途和高度菜单按当前层与分组筛选；高级区承载高度适配及立面限制。进深占格保留为只读预留字段，避免把它误作模型厚度调节。未知旧值保持可见，只有明确操作才改写，不在 Inspector 重绘时静默修正。

“配置审计”只读报告问题；“修复可确定的问题”支持 Undo，可修正最小占格、可确定的立面交集及隐藏楼层标记。Prefab、用途、权重和高度等无法判断意图的配置仍交给美术处理。

`StreetBuildingAuthoringEditor` 提供显式 StyleConfig 绑定、验证、编译预览、定位配置、Apply/Cook/Save、完整建筑检查、重抽布局种子，以及实际用途、门数、缺项与门窗分配诊断。

## 5. HDA 实例面板：生成参数的基础来源

**状态：已完成；[已验证·静态]，完整 Unity 生命周期行为待复验。**

最终面板按任务组织：

| 分组 | 当前用途 |
|---|---|
| 建筑体块 | 宽、深、矩形/L 形、缺口格数和方向、总楼层、后立面 |
| 首层门窗 | 随机/住宅/商业用途、住宅门、商业门数、橱窗数量或比例、首层排列 |
| 标准层门窗 | 固定数量/随机范围、每层每立面窗模块数、标准层排列 |
| 屋顶与线脚 | 屋顶、女儿墙、女儿墙高度、建筑线脚 |
| 附件 | 总开关、全局密度、五组附件密度和上限 |
| 局部覆盖 | 楼层/立面覆盖、附件覆盖 |
| 随机与预览 | 用途/素材变化种子、门位和门窗布局种子 |
| 输出与诊断 | LOD 输出、调试 metadata |
| 高级输入 | 自动地块来源、输入来源、模块来源与代理材质 |

内部传输和迁移字段隐藏。固定数量、随机范围、橱窗比例模式互斥，未启用模式的隐藏参数不干扰当前模式。

`StreetBuildingStyleApplier.Write` 只同步模块来源、`unity_style_catalog` 和桥接结束标记。Apply、Recook、Rebuild、首次绑定、Domain Reload 的素材同步路径不能从 StyleConfig 写入实例配额和生成开关。

局部覆盖与外部地块规则继续保留约定的高优先级；诊断记录规则来源。覆盖行新增时应保持无操作语义，不能仅因点击添加而改变建筑结果。

## 6. 门窗数量、用途与容量

### 6.1 标准层按模块计数

**状态：已完成；[已验证·静态]。**

标准层数量单位为“每层、每个物理立面的窗模块数”：单宽窗计 1，双宽窗也计 1。模块跨度用于容量适配，不转换为额外数量。

- 正、左、右、后分别计算配额；后立面关闭时不参与。
- L 形同方向的多个墙段共享一份物理立面额度。
- 固定模式只读取固定数量；隐藏的随机最大值不参与。
- 随机模式在最小/最大模块数之间按种子选择。
- 窗占用后自动填充其余墙面，无须配置空白墙数量。
- 在连续空间和模块跨度允许时达到目标数量，避免只按总格数估算造成空洞或重叠。
- 容量不足或无兼容窗时记录 `requested`、`actual`、`source` 和原因，不改写面板请求值。

### 6.2 首层住宅与商业

**状态：已完成；[已验证·静态]。**

首层用途为随机、住宅、商业。住宅窗与适用高度走住宅生成逻辑，住宅门由显式开关决定，开启时保留一个正面入口。

商业门按“整栋首层”计数；门分配到不同的可用物理立面，正面保留一个，额外门位由布局种子选择。L 形次正面不会被重复计算为第二个物理正面。关闭后立面会减少可用门位；固定请求超过实际容量时产生明确错误，随机模式受可用容量约束。

用途随机使用 `variation_seed`，门位布局使用独立 `layout_seed`。调整商业门数或重抽门位不会意外切换随机首层用途。素材不足时的用途回退带原因；显式商业用途缺少必要素材不会被静默当作成功的商业结果。

### 6.3 商业橱窗：数量与比例

**状态：已完成；[已验证·静态]。**

橱窗有两种互斥控制方式：

| 方式 | 最终语义 |
|---|---|
| 按模块数量 | 固定数量或随机范围；每个选中且启用的物理立面各有一份配额；单双宽均计一个模块 |
| 按占格比例 | 按扣除门位后的可用格数计算橱窗占用；比例不解释为模块个数 |

正、左、右、后可独立选择。L 形分段共享该方向额度；改变排列不得额外增加橱窗。零数量/零比例不应要求不存在的橱窗素材；容量不足要报告原因。显式首层立面覆盖可改变目标立面的数量，并在诊断中标出覆盖来源。

## 7. 四种排列与随机稳定性

**状态：已完成；[已验证·静态]。**

首层与标准层分别提供随机、均匀分布、左右对称、成组四种排列。排列求解与数量分配分离，变更排列保持已分配数量和跨度，并维持立面连续覆盖。

- 均匀分布：把窗/墙按目标数量分散布置。
- 左右对称：可行时配对位置、角色、跨度和素材，使两侧模块一致。
- 成组：按组组织窗墙节奏。
- 随机：种子固定时复现同一结果。

相同规则的标准层保持竖向对齐；排列切换不移动既定入口。四种排列都要经过实际实例数量、位置与覆盖检查，不能只看中间语义点。

Recook 的最终规则是：初次缺少布局种子时生成种子；启用“商业门数变更时重抽布局种子”后，检测到商业门数变化才重抽。普通重复 Recook 保持种子。用户也可显式点击“重抽布局种子并 Cook”。

## 8. 体块、四角缺口与高度来源

**状态：已完成；[已验证·静态]。**

矩形与等高 L 形继续作为当前体块范围。L 形缺口支持前左、前右、后左、后右，宽深使用整数格数，实际米制尺寸由当前 Cell 宽度换算。

有效缺口受建筑格数约束并保留建筑翼，超大输入被约束到可行范围。屋顶 Tile、墙段、女儿墙阴阳角、门和附件都使用真实缺口轮廓；前方凹入段保留自然次正面语义，雨棚和招牌跟随凹入支撑面。

建筑楼层参数表达总层数，范围 1–12，首层计入总数。素材尺寸提供首层/标准层高度，经当前用途解析后用于楼面、屋面及附件定位；模型保持原始缩放。通用高度关系为：

```text
屋面高度 = 有效首层高度 + (总层数 - 1) × 标准层高度
```

临街方向由轮廓与外部临街输入决定；侧立面自动生成。后立面只提供关闭或完整立面，两种值保持明确的持久化语义。

## 9. 墙面、屋顶、女儿墙与附件修复

### 9.1 统一墙面与侧背窗

**状态：已完成；[已验证·静态]。**

首层和标准层统一用当前层墙面候选覆盖正、侧、背面，候选通过立面范围筛选。侧背面可使用适配的标准层窗，双宽窗要求连续空间；无窗候选时按当前规则补墙或进入缺项诊断，不借用错误楼层素材。

### 9.2 AC 必须挂在实际实墙

**状态：已完成；[已验证·静态]。**

AC 挂接读取最终选中的实墙记录，排除窗、门和缺项位置。跨多格 AC 要求完整、连续的墙面支撑，L 形缺口和不适用临街面不能产生悬空附件。

没有可用实墙、只有窗、跨度不足或楼层不适用时不生成 AC。附件总开关、全局密度、AC 密度和上限只影响附件，不重新改写墙窗布局。

### 9.3 屋顶、女儿墙、线脚独立控制

**状态：已完成；[已验证·静态]。**

- 屋面、女儿墙、建筑线脚各有独立开关。
- 女儿墙高度为零时不生成女儿墙；关闭屋面不妨碍独立设置女儿墙。
- 关闭屋面时不保留屋顶设备。
- 柱、腰线和檐口使用对应模块位置；上层与屋顶不重复分配同一檐口。
- 关闭某项功能时，其真实模块和缺项预览都应消失。
- 模块不足时由独立预览展示缺失位置，而不是输出无效资产实例路径。

## 10. 自动缺项预览与正式 Bake 检查

**状态：部分完成；预览和阻断逻辑已实现，完整 Bake/Runtime 链路待复验。**

### 10.1 不完整素材也能迭代

空素材目录或稀疏素材目录可以用于编辑预览。已有兼容模块进入真实实例输出，缺少素材的位置进入 `OUT_BUILDING_PREVIEW`。

预览使用 `SB_MissingCell.mat` 与 `SB_MissingCellEdge.mat`，带楼层、立面、Cell、模块角色和槽位信息；`preview_missing_count` 与分组摘要便于从 Inspector 定位缺失。

预览输出带 `streetbuilding_preview_only` 标记，真实输出不混入占位 Mesh。自动缺项方式无需再手动选择缺项模式；被关闭的功能不分配无意义占位。

地块来源可自动判断：无连接时使用独栋体块参数，有有效连接时消费地块。已连接但为空或非法的输入明确报错，不静默切回独栋。

### 10.2 Bake 前检查

`StreetBuildingPartialBake` 通过 Houdini Engine 的公开事件挂接 Bake New / Bake Update。正式 Bake 要求：

1. 风格通过完整性校验；
2. 最近一次 Cook 成功；
3. 当前素材载荷 SHA 与上次成功应用一致；
4. 能读取真实输出的缺项统计且缺失数为零；
5. 生成层级中没有非空的缺项预览 Mesh。

读取不到可信缺项统计时阻止 Bake。该实现是编辑期完整性门禁，不代表已实现自动合批、LOD 资产发布或 GPU 实例数据 Bake。

## 11. Unity 桥接、参数保留与失败恢复

**状态：已完成实现；[已验证·静态]，完整生命周期回归待复验。**

`StreetBuildingInstanceParameters` 对 Inspector 缓存未暴露的隐藏字段，通过 HAPI 参数接口读写真实节点，并同步存在的缓存。兼容逻辑位于项目自有 Editor 代码。

`StreetBuildingRecook` 监听 Cook 和 Reload 事件：Cook 前编译并同步素材；Rebuild 时保留整数参数语义，在 HAPI 节点重建后恢复并重新挂接事件。旧菜单迁移按语义值处理，避免菜单索引变化把实例值复位。

Apply 事务记录将要写入的参数及 Authoring 的 SHA、诊断、缺项摘要、布局种子、入口位置、迁移标记和 Tag。失败后恢复快照，再在抑制自动重抽的作用域内执行恢复 Cook；失败路径不保存 Scene。

成功 Cook 从真实输出读取住宅/商业用途、门数、橱窗数、可用格、布局种子及标准层窗诊断，减少界面参数与生成结果不一致时的排查成本。

## 12. Unity 6 与开发工具链

**状态：已完成接入；[已验证·现场] CLI 可用。**

项目升级到 Unity `6000.3.22f1` 和 URP `17.3.0`，同步 Package、Renderer/URP 设置及相关资产序列化。

Houdini Engine Unity 的 Unity 6 兼容修改仅涉及两处序列化注解：自动属性 `WarnedPrefabNotSupported` 使用 `[field: SerializeField]`，`InstanceInputUIState` 属性移除非法重复 `[SerializeField]`。第三方插件能力不计为项目自研生成能力。

新增 `Ensure-UnityPipeline.ps1`，检查 CLI、正确项目的 Editor 主进程、版本、Pipeline Server 和 `editor_status`；必要时启动 Editor 或恢复 Server 会话连接。

回归入口优先使用 Pipeline 的状态、场景、资产、Console、刷新和 Test Runner 命令。StreetBuilding 完整验证接入 `list_tests / run_tests / test_status`，并处理 domain reload 后结果收集状态。

Houdini 预检分别检查 RPC 18811、HTTP MCP 3055、协议发现和 Codex 配置，显式区分“服务端可发现工具”与“当前 Codex 会话可调用工具”。

## 13. 本轮核验结果与遗留事项

### 13.1 已确认的文件和现场

- 当前 HEAD 是 `a06ec58`，开始整理时已跟踪文件无本地差异，故本次静态读取对应提交 `30`。
- Unity Pipeline 前置门禁通过：正确 Editor 版本、Server 可达、状态 ready。
- AssetDatabase 可找到三份 StyleConfig。
- 当前打开 `PCG_Building.unity`，Root Count 19，场景 Dirty；本次文档任务未保存或重新生成该场景。
- Console 状态采样显示未编译失败、未处于编译中；已有 8 条 Error、16 条 Warning，不能声明当前现场无诊断。

### 13.2 Fresh HDA 累计验证

本轮使用独立 `hython` 进程读取提交中的 HIP/HDA，执行：

```powershell
& 'D:/Software/Side Effects Software/Houdini 21.0.440/bin/hython.exe' `
  HoudiniProject/PCG_Track_21.0.440/scripts/tools/validate_streetbuilding_contract.py --source fresh
```

结果：进程退出码 `0`，总状态 `PASS`，验证实例为 `/obj/VERIFY_STREETBUILDING_V12_LOCKED`，`locked = true`。主要覆盖如下（各组可能重叠，不相加为总用例数）：

| 合约组 | 本轮结果 |
|---|---|
| 实例生成规则 | 36 项通过 |
| 自动侧立面与后立面 | 10 项覆盖、6 项旧载荷检查通过 |
| 层高与四角缺口 | 9 组层高、2 种 Cell 宽度 × 4 个缺口方向通过 |
| 标准层窗模块计数 | 48 项通过，单位为每层/每物理立面的模块数 |
| 侧背窗与连续跨度 | 24 项通过 |
| 四种排列 | 65 项通过；数量覆盖、竖向对齐和入口固定通过 |
| 屋顶、女儿墙与线脚 | 64 项与 24 项灰盒检查通过 |
| AC 实墙支撑 | 47 项、669 个实例检查通过 |
| 不完整素材预览 | 空目录、稀疏素材、真实实例/占位隔离通过 |
| 用途与门位种子 | 用途隔离通过，48 个布局种子的侧门分布检查通过 |

上述结果提供 **[已验证·Fresh HDA]** 证据。该命令在独立进程中建立验证实例，不保存生产 HIP/HDA，不操作用户当前 Live Scene；不能替代 Unity 的 Apply/Rebuild/Domain Reload、保存重开、真实 Bake 和真机验证。

### 13.3 门禁测试与可复现性

执行 `python HoudiniProject/PCG_Track_21.0.440/scripts/tests/test_pcg_regression_gate.py`，14 项中 13 项通过、1 项失败。失败项仍断言旧 `Invoke-StreetBuildingContractTests`、反射 Bridge 和 `reflection-method-call` 名称，而当前回归入口已采用 `Invoke-StreetBuildingPipelineTests`；测试入口断言尚未同步。

当前 `Assets/PCG/Tests/` 为未跟踪目录，`git ls-files` 在该目录及旧 Tests 目录都没有测试文件。现场能发现的 Unity 测试不应直接视为提交 `30` 可在干净检出中复现。本轮没有运行会保存场景或重新生成资产的完整 VerifyFull。

合同 JSON 和部分接口辅助脚本仍残留中间版本的风格规则说明。本日志按最终素材编译器、实例桥接以及 `validate_streetbuilding_instance_rules.py` 的“素材不覆盖实例”行为口径记录；这些残留文字需要另行同步。

### 13.4 Houdini 连接限制

预检确认 Houdini 21.0.440 已打开生产 `PCG_Bike_StreetBuilding.hip`，RPC 可达；HTTP MCP health 恢复正常。但本机 Codex CLI 拒绝配置中的 `service_tier = default`，预检在配置解析阶段失败。本轮未执行原生 Houdini MCP Live 操作，也未据此宣称 definition 与未保存现场一致。

## 14. 性能、兼容性与扩展边界

| 阶段 | CPU / 编辑期职责 | GPU / 运行时职责 |
|---|---|---|
| 素材组织 | 校验、载荷编译、配置迁移 | 无逐帧工作 |
| 建筑生成 | Houdini 完成配额、排列、跨度、附件和缺项求解 | Editor 预览已有输出 |
| 发布检查 | 验证完整素材、有效输出和无占位 | 消费后续 Bake 的原生资产 |
| 大规模建筑 | 本阶段没有完成城市级 Runtime 数据管线 | Chunk、GPU Culling、LOD、Indirect Draw 仍待接入 |

本阶段没有新增 StreetBuilding 自定义 Shader、RendererFeature、RenderPass、RT 或全屏 Blit。材质继续使用 URP/Lit；Instancing 支持与实际批处理命中需要区分。URP 升级后的真实 Variant、DrawCall、SetPass、Overdraw 和纹理带宽尚无本阶段真机结论。

自动缺项 Mesh 是开发期诊断几何，应被 Bake 门禁排除。场景里的大量模块 GameObject 和 Renderer 不能直接等同于移动端成品渲染结构。

扩展应继续沿素材候选、实例参数、HDA 分配、输出诊断、Bake 数据和 Runtime 渲染分层进行。新增数量或密度控制进入实例；新增美术适配信息进入 StyleConfig。

## 15. 当前状态矩阵

| 功能 | 状态 | 当前结论 |
|---|---|---|
| 首层/上层/屋顶素材分组 | 已完成 | 素材与生成职责分离 |
| STYLE 载荷与 Prefab 名称标识 | 已完成 | 稳定排序、路径与 Bounds、SHA |
| 中文 Inspector 与配置审计 | 已完成 | 分组编辑、受限菜单、可撤销修复 |
| HDA 实例参数 | 已完成实现 | 数量、用途、排列和开关直接参与求解 |
| 门窗数量与 L 形共享配额 | 已完成实现 | 单双宽按模块计数，诊断请求/实际/来源 |
| 四种排列与分离种子 | 已完成实现 | 排列不增加数量，普通 Recook 可复现 |
| 四角网格缺口与层高 | 已完成实现 | 网格单位、自然临街、素材尺寸驱动 |
| AC 实墙与屋顶线脚修复 | 已完成实现 | 真实支撑、独立开关、缺项诊断 |
| Fresh HDA 累计合约 | 已完成验证 | 本轮总状态 PASS，独立锁定实例 |
| 自动占位与 Bake 阻断 | 部分完成 | 编辑链路已实现，发布链路待复验 |
| Unity 6 / Pipeline CLI | 已完成接入 | 本轮前置健康检查通过 |
| 累计测试版本完整性 | 待复验 | Unity Tests 未跟踪，Python 有旧断言失败 |
| 端到端 Runtime Bake / GPU Driven | 未实现 | 本范围无完整交付证据 |
| Android / iOS 真机性能 | 待复验 | 无本阶段设备测试结果 |

## 16. 后续验证重点

1. 同步 Pipeline 测试入口断言，并将正式 Unity 合约测试及 `.meta` 纳入版本管理，验证干净检出可运行。
2. 完成 Apply、Recook、Rebuild、Domain Reload、保存重开的累计检查，特别确认素材修改不覆盖实例值。
3. 用真实 Prefab/FBX 复验门窗数量、跨度不足诊断、四角 L 形、侧背窗、AC 支撑面及零缺项 Bake。
4. 同步合同和操作说明中的中间版本文字，保持“素材只描述素材、面板控制基础生成”的单一口径。
5. 在原有场景改动得到保全后完成双侧完整回归；随后再建设建筑 Bake、Chunk、GPU 剔除/LOD 和移动端性能基线。
