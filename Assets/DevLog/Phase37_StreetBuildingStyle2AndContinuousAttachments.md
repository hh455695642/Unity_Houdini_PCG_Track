# Phase 37 开发日志：Style2 参考建筑与连续附件、城市 Bake

> 文档类型：提交最终有效实现快照
>
> 记录日期：2026-10-27
>
> 当前主提交：`03d36c5aed81f056d5405512af21834dd06b2006`（`37`）
>
> 对比基线：`97c7eefe1e9f17c6b4a2582ca7e1bba43d0fd854`（`Phase36`）
>
> 版本文件：`Phase37_StreetBuildingStyle2AndContinuousAttachments.md`

## 1. 记录规则与范围

参照 Phase1，记录环境、功能、问题、资产状态、验证与性能边界。以提交 `37` 的最终源码、资产和保存场景为本阶段审计对象，不把中间开发记录中的旧命名、旧 Bake 计数或已退役路径当作现状。

- **[已验证：静态]**：本轮通过 Git 差异、源码及序列化文件直接核对；不代表运行场景验收。
- **[已验证：本轮测试]**：本轮实际执行的独立单元测试与模拟故障测试。
- **[历史还原]**：提交内交付说明记载的 Cook、Bake、截图与累计回归结果，不等于本轮重跑。
- **[待复验]**：当前链路、重新 Bake、冷重开或设备性能仍需实际验证。
- **[未实现]**：本提交未交付的能力，不把素材源、接口或开关写成完整运行时系统。

本轮只新增 Markdown，不改生产源码、素材、HDA、HIP、场景或插件；不执行历史 patch／builder，也不覆盖当前 Live Scene。原有未跟踪美术、测试目录和操作手册保持不动，不计入提交成果。

## 2. 环境与最终资产入口

| 项目 | 最终版本／位置 |
|---|---|
| Unity / URP | `6000.3.22f1` / `17.3.0` |
| Unity Pipeline | `0.9.0-exp.1` |
| Houdini | `21.0.440` |
| 建筑 HDA | `Assets/PCG/HDA/City/StreetBuilding.hda` |
| 建筑 HIP | `HoudiniProject/PCG_Track_21.0.440/PCG_Bike_StreetBuilding.hip` |
| 原风格配置 | `Assets/PCG/Art/Building_Test/Style1/SBStyle1.asset` |
| 参考风格配置 | `Assets/PCG/Art/Building_Test/Style2/SBStyle2.asset` |
| 参考风格素材 | `Assets/PCG/Art/Building_Test/Style2/Models/`、`Prefabs/` |
| 制作场景 | `Assets/PCG/Scenes/PCG_Building.unity` |
| 城市最终 Prefab 库 | `Assets/PCG/Generated/Buildings/Style2/` |
| 城市测试场景 | `Assets/PCG/Scenes/PCG_City_Test.unity` |

提交共涉及 1,008 个文件。主要变化为参考素材、生成资产替换、建筑参数与附件桥接、HDA/HIP、三个场景及累计验证工具；大型 Mesh/spec/场景的行数不代表新增算法规模。

### 2.1 最终命名与历史说明的区别

**状态：已完成；证据：[已验证：静态]。**

原 `Style1/SBStyle_Test.asset` 改名为 `SBStyle1.asset`，其 `.meta` GUID 保留。参考红砖套件最终位于 **Style2**，配置为 `SBStyle2.asset`。建筑场景保存 `StreetBuilding_Style1` 与 `StreetBuilding_Style2`，分别引用对应配置。

`ReferenceUpgrade.md`、`AttachmentReferenceUpgrade.md` 和若干 `Style1Reference*` 工具仍保留开发时的名称或旧路径。本文仅提取最终仍有效的能力；这些历史工具不是无检查可重放的当前制作入口。使用前应核对输出目录、配置引用和规格来源，不能按文档旧路径重新创建第二套风格。

## 3. 已开发功能

### 3.1 Style2 参考主体与共享表面素材

**状态：已完成素材交付；证据：[已验证：静态]。**

形成红砖墙、浅拱／矩形窗、双宽窗、商业橱窗、入口、首层／上层柱、腰线、女儿墙直段／凸角／凹角、屋面和空调等 Reference 模块。商业雨棚和招牌也保留独立 Prefab，便于后续替换。

主体主要使用 `Style2_Reference_Brick.mat`、`Style2_Reference_Trim.mat`、`Style2_Reference_Glass.mat` 及对应纹理。三种材质静态配置均为 Opaque、Cull Back、Alpha Clip 关闭、Instancing 开启，当前材质有效 keyword 列表为空。玻璃是低成本不透明表现，不是透明室内系统。

参考几何保留 Unity 正式 `.asset` Mesh、JSON spec，以及部分模块的 FBX／原生 Houdini CPIO 交换源。Prefab 当前消费正式 Mesh；单独修改 FBX 不会自动同步 `.asset`。主体补充模块中有 C# 几何配方，不能将所有模块都描述为已有完整 DCC 源。

参考套件是可继续精修的简化建筑素材，不包含完整写实光照、藤蔓、垃圾桶等参考图全部内容。三个主体共享材质也不是整栋输出材质槽的固定上限。

### 3.2 附件素材语义与连接规格

**状态：已完成源码与资产接口；证据：[已验证：静态]。**

在既有角色末尾追加 `DrainPipe`（编号 23），保留旧角色编号。新增明确的附件子类型，区分水塔、烟囱、左右梯段、平台、上下终止件、屋顶检修梯和管道直段／端件／偏移件，不按文件名猜测语义。

StyleConfig 模块增加连接高度、可选挂点、连接起止点、半径与允许长度范围。复制楼层素材时一并保留这些规格；编辑器按素材角色开放相关字段。

| 编译行 | 职责 |
|---|---|
| `M` | 原有素材候选规格；保留原格式 |
| `X|1` | 附件子类型与连接高度 |
| `A|1` | 显式附件挂点 |
| `P|1` | 管件端点、半径、长度范围 |

编译器检查有限数值、正半径、合法长度范围、角色与子类型匹配，同一 Prefab 的冲突规格直接报错。Generic 候选保持旧生成语义。以上属于**素材适配约束**，不存放数量、密度、用途或生成开关。

### 3.3 实例附件面板与单一参数来源

**状态：已完成；证据：[已验证：静态]。**

新控制项直接读写 HDA 实例原生字段：

- 屋顶附件可选择旧概率散布或按设备类型计数；水塔、烟囱各自选择固定数量或随机范围，位置可选择兼容固定扫描或按建筑种子分布。
- 消防梯可选择旧概率散布或连续梯组；梯组数量按整栋共享，另设物理立面集合、起止楼层和屋顶检修梯开关。
- 落水管有独立开关、整栋完整管线数量和物理立面集合。
- 固定附件不经过通用密度抽样；旧概率字段与新模式互斥，隐藏字段不参与当前模式。

`StreetBuildingGenerationPolicy` 从通用区间／候选采样中排除这些原生控制字段，避免形成第二套请求来源。屋顶随机范围仍由其原生数量模式处理，不等于所有新附件都只能固定数量。

立面 mask 为正面、次正面、侧面、背面四类语义；侧面覆盖左／右物理侧面，bit2 的“次正面”不是“右侧”。多选提供固定可用集合，不能因为选择多个面而增加整栋配额。

### 3.4 连续消防梯、完整排水管与屋顶设备布局

**状态：已实现并纳入累计合约；证据：[静态源码／合约]、[历史还原]；本轮未重 Cook。**

附件网络职责拆分为支承候选、连续布局、屋顶设备规划、零件装配与诊断验证。提交说明中的节点包括 `ATTACHMENT_SUPPORT_CANDIDATES`、`PLAN_CONTINUOUS_ATTACHMENTS`、`PLAN_TYPED_ROOF_PROPS`、`ASSEMBLE_CONTINUOUS_ATTACHMENTS`、`VALIDATE_REFERENCE_ATTACHMENTS` 和 `ATTACHMENT_DIAGNOSTICS`。本轮未从 Live 逐节点验证网络，不用历史 patch 代替当前 definition。

- **连续消防梯**：同一物理墙段逐层连接，显式区分左右梯段、平台和收口；层高不匹配、范围不完整或屋顶检修连接不可用时拒绝并报告，不用负缩放镜像掩盖连接问题。
- **排水管**：以完整管线为单位选择墙面走廊，使用真实墙体表面和源件端点；局部偏移绕过腰线／檐口后回到贴墙位置，不是任意障碍路径规划。
- **管件适配**：直管只在声明长度范围内沿轴向适配，管径比例不变；固定偏移件和端件保持单位比例。合约覆盖非整数高度、端点连续性与真实墙面距离。
- **屋顶设备**：按源素材完整 Bounds、屋面边界、L 形凹口和已接受设备预留区域布置。规划器用局部占地数组处理同次生成的互相避让，不能依赖 `point()` 回读同一 Wrangle 刚添加的点。
- **确定性与容量**：水塔和烟囱具有独立随机域；支持相同种子重现、V2 附件组重抽及旧扫描兼容。空间不足保留请求，输出实际数量与容量原因。

### 3.5 商业挂点与可解释诊断

**状态：已实现诊断接入与验证规则；证据：[已验证：静态]。**

商业雨棚／招牌的累计检查增加实际门窗宿主、素材 pivot／显式挂点、宽度适配及几何净空验证，防止“跟随门窗”模式仍将附件落在实墙上。L 形凹进首层的柱素材适用面补入次正面，不改写门窗或柱的请求数量。

新增 `reference_attachment_diagnostics`，格式为带版本的四类请求／实际报告。Unity 面板、Recook 摘要和状态缓存读取该输出，分别标明水塔／烟囱“件”、消防梯“组”、落水管“条”，以及请求来源、关闭、容量、缺素材、层高或屋顶连接等原因。

解析器拒绝重复类别、损坏记录、实际值超过请求或缺少类别。面板明确显示“上次成功生成结果”，不把改参数前的旧结果当作当前容量。

### 3.6 原生 Bake 的整管合并与输出分类

**状态：已完成项目侧实现；证据：[已验证：静态]、[历史还原]。**

`StreetBuildingPipeBake` 通过 Houdini Engine 公开 `BakedDataEvent` 接入，在编辑期按管线 group 合并源 Mesh，同材质形成一个 submesh，每条管线形成一个 `SB_PIPE_…` Renderer。挂接同时覆盖层级更新与同步 Apply→Bake，避免事件注册时序漏掉合并。

合并先检查材质／submesh、变换行列式与所属原生输出容器，再构建持久化 Mesh。重复更新使用唯一资产路径，保留旧 Mesh GUID 和人工编辑；合并对象留在原生 instancer 所属层级中，避免根节点留下重复管线。没有修改 Houdini Engine 插件，也没有新增运行时合并组件。

`StreetBuildingCityBakeOutputs` 明确区分：

- 近景视觉：`OUT_BUILDING_LOD0`、`OUT_DETAIL_INSTANCES`。
- 不参与近景合并：metadata、collision、独立 LOD1/LOD2、footprint 与 debug 输出。
- 未分类的可见输出、空 Mesh 或整栋无可用视觉几何：报错，不静默丢弃。

**保留限制：**提交说明记录 Prefab Bake、重复 Prefab 更新及冷重开曾通过；Standalone 更新仍遇到插件推导 `Assets//Meshes` 的错误。本阶段不修改插件，不把这条失败路线写为已修复。

### 3.7 最终 Style2 整栋城市库

**状态：已完成资产与保存场景接入；证据：[已验证：静态]。**

`PCG_City_Test.unity` 的八个槽位和实例路径最终指向 `PF_Style2_00.prefab` 至 `PF_Style2_07.prefab`。不再使用 Phase36 的 `MyTestCityVaried` 槽位。每栋均为原生组件，无 MonoBehaviour，近景和远景各一个 MeshRenderer、一个 LODGroup。

下表三角形由当前 Mesh 的各 submesh `indexCount / 3` 汇总；仅为序列化资产统计，不是设备测量。

| 索引 | 近景三角形 | 近景 submesh | 远景三角形 | BoxCollider | 近景切换阈值 |
|---|---|---|---|---|---|
| 00 | 4,521 | 3 | 24 | 2 | 0.06068158 |
| 01 | 8,044 | 3 | 586 | 1 | 0.078125 |
| 02 | 15,038 | 4 | 770 | 2 | 0.134375 |
| 03 | 9,801 | 4 | 12 | 1 | 0.07875 |
| 04 | 12,274 | 4 | 12 | 1 | 0.11625 |
| 05 | 10,347 | 4 | 72 | 1 | 0.1215 |
| 06 | 9,028 | 4 | 12 | 1 | 0.078962825 |
| 07 | 10,202 | 4 | 598 | 2 | 0.096875 |

八栋远景均为 2 个 submesh，远景剔除阈值均为 `0.015`。阈值是屏幕相对高度，不是米制距离。“每级一个 Renderer”也不等于一个 DrawCall，因为近景包含 3–4 个 submesh，另有阴影等 Pass。

Style2 还提供附件独立 LOD1 交换源。但这些源的 `runtime_lod_connected=false` 与**整栋城市 Prefab 已配置两级 LODGroup**是不同事实，不能沿用较早说明笼统写成“本提交没有 LOD”，也不能推断各源附件已自动独立切换。

### 3.8 资源退役与验证资产生命周期

**状态：最终资源路径已收敛；证据：[已验证：静态]、[历史还原]。**

旧 `MyTestCityFrontage`、`MyTestCityVaried` 整栋库及旧 `Art/StreetBuilding` 下两套 urban 示例和共享资源在本提交中移除／替换。最终有效入口是 `Building_Test/Style1`、`Building_Test/Style2` 和城市 `Generated/Buildings/Style2`。不能继续照抄 Phase36 的旧目录依赖结论。

固定 Reference／Attachment 验证场景及 `Generated/Buildings/ReferenceAttachments` 专用树退役。验证脚本改为从任务证据目录推导唯一 `Assets/__PCGValidation/SB_<hash>/` 临时根，执行结束后卸载并清理本轮测试场景和资产，证据保留在 Assets 外。退役资产永久缺失检查进入累计验证。

## 4. 回归与持久化门禁增强

**状态：已完成工具实现；部分独立测试本轮通过。**

1. **精确 HDA 查询**：资产搜索使用目标完整路径 `glob:`，限制返回量；结果截断直接失败，避免历史 HDA 备份挤占搜索结果。
2. **状态查询恢复**：`test_status` 支持临时不可达、`no_tests` 和遗留 running 状态；只读失败最多三次，仍保留 900 秒总截止和严格测试结果要求。
3. **本轮 XML 身份**：回退结果必须是本轮新文件，`start-time` 属于本轮，测试 fullname、数量、结果完整匹配；拒绝旧轮次、失败或跳过用例。只在确认 running 时重置遗留 collector。
4. **附件接口晋升**：候选验证与生产保存共用 `streetbuilding_attachment_interface.py`。检查准确字段集合、Menu／Toggle／Int 类型、非静态隐藏；仅对有明确 definition/tag 依据的内部 switcher 别名做只读规范化，不改实例 raw value 或任意父目录。
5. **纯美术任务保护**：白名单不授权 HDA/HIP 写入时，完整回归仍执行，但 persist 只核对受保护文件哈希，不保存 definition/HIP、不重载 Live；单边授权和越界变更继续受门禁限制。

最终合约清单包含 227 个 ID。本提交新增参考附件、屋顶数量／随机域、商业宿主、管线真实连接、退役资产和 Pipeline 传输检查。登记数量不等于本轮执行通过数量。

## 5. 问题与最终处理

| 问题 | 最终处理与边界 |
|---|---|
| 附件名称无法表达连接语义 | 显式子类型、挂点与端点规格；StyleConfig 仍只管素材 |
| 新固定／范围请求被旧随机策略覆盖 | 原生字段独立管理，按模式排除无效旧字段 |
| 屋顶同次新增设备互相穿插 | 用真实占地与局部预留集合检查；独立 Bounds 合约验证 |
| 管线悬空、连接裂缝或绕线后不回墙 | 真实墙面、源端点、局部偏移、限制轴向长度；非法路线报告容量 |
| 管段过多、重复 Bake 留旧输出 | 编辑期整管合并，持久 Mesh 与原生容器归属，旧资产不覆盖 |
| 城市近景混入 metadata／碰撞／其他 LOD | 显式视觉输出分类，未知可见输出失败 |
| 状态查询失败误用旧测试 XML | 三次只读恢复、本轮时间戳与测试身份联合检查 |
| 历史文档仍写 Style1 和旧目录 | Phase37 采用最终 Style2 路径；维护脚本执行前需重新核对 |

## 6. 性能、兼容性与扩展边界

- **CPU**：附件规划与 Mesh 合并在编辑期完成。最终城市每栋每级一个 Renderer，降低模块级对象提交粒度；未实现运行时逐实例 GPU 剔除或 Indirect 绘制。
- **GPU**：近景为 4,521–15,038 三角形，远景为 12–770 三角形；不能沿用 Phase36“远景一律 12／24 面”的结论。仍需测量阴影、材质 Pass 和实际可见数量。
- **内存**：16 个最终近远景 Mesh 均序列化为 `m_IsReadable: 1`，不能宣称已消除 CPU Mesh 副本；后续需结合编辑／碰撞需求审计 Read/Write 和构建内存。
- **材质／variant**：本阶段未新增自定义 Shader／RendererFeature／RT。三种 Reference 材质开启 Instancing，但实际合批、URP 自带 variant 数和 DrawCall 尚未在本轮测量。
- **移动端**：不透明玻璃、简单碰撞、离线 Bake 和整栋 LOD 有利于控制成本；Android Mali／Adreno、iOS Metal 的 GPU 帧时、带宽和显存仍待真机验收。
- **扩展点**：新附件通过素材子类型与连接规格扩展；新 HDA 输出需登记视觉职责；更大城市应另建 Bake 后 Chunk／Cluster 与 GPU 驱动数据层，不把它混入单栋生成器。

## 7. 本轮验证与历史证据

### 7.1 本轮实际执行

| 项目 | 结果 |
|---|---|
| Git 主提交、父提交、差异范围 | 已核对 |
| Style1／Style2 配置 GUID 与制作场景绑定 | 已核对 |
| 城市八槽位、Prefab 组件、Mesh 面数与 LOD 阈值 | 静态检查完成 |
| `python -B -m unittest discover -s HoudiniProject/PCG_Track_21.0.440/scripts/tests -p test_streetbuilding_attachment_interface.py` | **17/17 通过** |
| 同目录 `test_pcg_regression_gate.py` | **20/20 通过** |
| `Test-UnityPipelineStatusRecovery.ps1` | **10/10 通过**；隔离 mock，不操作 Unity/Houdini |
| `Ensure-HoudiniMcp.ps1` | RPC、HIP 身份、HTTP health 与服务端 43 工具发现通过；未执行 Live 修改或当前会话原生工具调用 |
| `Ensure-UnityPipeline.ps1` 前后门禁 | 均通过，Editor 为 ready；前置检查经脚本刷新及 Start Server 自举恢复，结束检查直接通过 |
| Cook／Bake、VerifyFast／VerifyFull、真实 Unity EditMode 全集 | 本轮未执行 |
| Android／iOS 构建与设备性能 | 本轮未执行 |

故障注入报告保存在 `.codex_tmp/regression/phase37-devlog-20261027-status-recovery/report.json`。这些测试验证接口与门禁逻辑，不代替真实附件输出、保存重开或完整 Unity 场景验收。

### 7.2 提交中的历史验收记录

`Style2/AttachmentReferenceUpgrade.md` 的 2026-10-26 收尾记录记载：227 项登记合约、两轮 Unity EditMode 各 90/90、30 个原生实例案例，以及管线源几何／HAPI／Prefab 比对、重复更新和冷重开检查。该记录也明确保留 Standalone 更新失败和未完成设备测量。

其中 8×10m／3 层标杆的 124 Renderer、198 材质槽和 10,943 三角形属于当时模块化原生 Bake 样例，**不代表最终 `PF_Style2_00..07` 的计数**。本文采用第 3.7 节直接核对的最终资产数据，不将不同样例拼接成性能降幅。

## 8. 状态矩阵与后续复验

| 能力 | 状态 |
|---|---|
| Style2 主体与附件素材、Style1／Style2 分离 | 已完成；静态证据 |
| 原生附件参数、素材语义编译与诊断 | 已完成实现；实际全链路待运行复验 |
| 连续梯组、贴墙排水、屋顶数量与布局 | 已实现并有历史验收；本轮未重 Cook |
| 整管合并、城市视觉输出分类 | 已完成实现；Prefab 更新有历史验收 |
| 八栋 Style2 城市 LOD Prefab 与槽位 | 已完成保存资产接入；运行效果待复验 |
| 原生 Standalone 更新 | 部分完成；已知插件路径错误仍保留 |
| 接口／门禁独立测试 | 本轮 17 + 20 + 10 项通过 |
| GPU Culling／Indirect 城市系统 | 本提交未实现 |
| 移动端性能达标 | 待复验 |

后续应先核对历史维护工具中的最终 Style2 路径，再按新任务白名单执行真实附件请求计数、素材不覆盖实例参数、Prefab 重复更新与保存重开累计合约；随后验证城市 LOD／碰撞、实际 DrawCall／SetPass 和 Mesh 内存。不得为继续使用旧脚本重建已退役目录或覆盖当前有效现场。
