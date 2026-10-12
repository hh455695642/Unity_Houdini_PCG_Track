# Phase 33 开发日志：StreetBuilding 女儿墙与屋顶设备素材收敛

> 文档类型：提交最终状态快照
>
> 记录日期：2026-10-12
>
> 版本文件：`Phase33_StreetBuildingRoofAssets.md`
>
> 当前主提交：`02b51389fba593ef23a68b4ef5c3c8270374ca8a`（`33`）
>
> 对比基线：`3d215502f6f38ecbfb8a5e19f642c2f637d11af0`（`Phase32`）
>
> 适用范围：提交 33 新增的屋顶示例素材、StyleConfig 接入、制作与审计工具，以及两项编辑器稳定性修复

## 1. 记录规则与证据等级

参照 Phase1 的环境、功能、问题、验证、性能和遗留事项结构，记录提交 `33` 最终保留的开发内容。前一阶段已有的生成算法不重复计为本阶段新增功能。

- **[已验证]**：本轮直接核对的 Git 差异、源码、序列化资产或实际执行结果；文件核对不等同于场景行为验收。
- **[历史还原]**：提交配套说明与本地历史验证记录。`.codex_tmp/` 中的报告不是本轮执行结果，也不是提交 33 新增的可复现测试交付。
- **[待复验]**：已有实现，但本轮未覆盖对应 Live Scene、重开、Bake 或真机链路。
- **[未实现]**：本次提交没有交付的能力，不将制作脚本或材质选项当作运行时系统。

只记录最终红砖／石材女儿墙和最终屋顶设备造型；中间灰白版、被覆盖的网格与临时调试方案不列为最终功能。

## 2. 版本环境与事实源

| 项目 | 版本／路径 | 证据 |
|---|---|---|
| Unity | `6000.3.22f1` | [已验证] ProjectVersion 与 Pipeline 门禁 |
| URP | `17.3.0` | [已验证] Packages/manifest.json |
| Unity CLI / Pipeline | `1.0.0-beta.11` / `0.7.0-exp.1` | [已验证] 本轮门禁 |
| Houdini | `21.0.440` | 本地独立验证程序版本；GUI 本轮未运行 |
| StreetBuilding HDA | `Assets/PCG/HDA/StreetBuilding.hda` | 提交内更新的二进制资产 |
| Houdini 工程 | `HoudiniProject/PCG_Track_21.0.440/PCG_Bike_StreetBuilding.hip` | 提交内同步保存的工程 |
| Unity 示例场景 | `Assets/PCG/Scenes/PCG_Building.unity` | 提交内更新的场景 |
| 示例素材 | `Assets/PCG/Art/Building_Test/Style1/` | Models、Prefabs、SBStyle_Test 与制作规范 |
| 共享材质 | `Assets/PCG/Materials/Buildings/` | 四个新增材质及其引用 |

本次开发变化集中于素材制作、接入和验证辅助，不根据 HDA/HIP 二进制文件变化量推断新增生成算法。场景 YAML 的大量增删也不等于同等规模的功能代码改写。

## 3. Phase 33 开发内容

### 3.1 女儿墙直段、阳角、阴角三件套

**状态：已完成；证据：[已验证：资产与制作规范]，场景拼接另见验证记录。**

新增三组 Mesh 与 Prefab，分别登记 `Parapet`、`ParapetCorner`、`ParapetConcaveCorner`：

| Prefab | Pivot 与方向 | 顶点／三角形 |
|---|---|---:|
| `PF_SB_Style1_Parapet_Straight_A` | 底部中心，X=-1～1，外侧 +Z | 12 / 6 |
| `PF_SB_Style1_Parapet_Corner_A` | 阳角轮廓交点，两臂沿 +X、-Z 各 2m | 24 / 12 |
| `PF_SB_Style1_Parapet_ConcaveCorner_A` | 阴角交点，两臂沿 +X、+Z 各 2m | 24 / 12 |

最终尺寸与外壳规范：

- +Y 向上，根 Transform 为零位移、零旋转、单位缩放；一个 `Visual` 子节点承载 MeshFilter 和 MeshRenderer。
- 红砖墙身高 0.50m；石材压顶前沿从 Y=0.50 到 0.60m，顶部高度 0.60m。
- 压顶宽 0.24m，向建筑内部延伸；直段压顶 Z=-0.24～0。
- 阳角两外侧法线为 +Z、-X；阴角为 +Z、+X。阴角是独立网格，不用负缩放镜像阳角替代。
- 只保留外侧墙面与压顶可见面，不制作背面、底面、端面等不可见厚度。这是轻量外壳，不是封闭实体墙；屋内侧观察到背面剔除不属于漏面修复目标。
- 阳角压顶交汇区只保留一份 0.24×0.24m 顶面，避免叠面闪烁；阴角压顶向 -Z／-X 退让并覆盖屋内交汇区域。
- 每款一个 Renderer、两个 SubMesh，共享墙身与压顶材质。红砖复用立面底色，UV 密度为 0.5/m；压顶复用 `Style1_Stone_BaseColor`。

模块沿用现有屋顶边格约定：每条边首尾各一个 2m 格由转角臂覆盖，直段填充中间格。外部 DCC 替换必须维持 Pivot、臂长、外向法线和端部截面，不能将转角缩成小接头。

### 3.2 五款屋顶设备素材

**状态：已完成；证据：[已验证：资产、制作代码与规范]。**

提交正式加入五组 Mesh／Prefab，形成可辨识的屋顶设备，而不只是通用方盒占位：

| 资产名 | 最终外形 | 三角形数 |
|---|---|---:|
| `Roof_Chimney_A` | 红砖烟囱与石材收口 | 36 |
| `Roof_Vent_A` | 低矮通风帽 | 144 |
| `Roof_WaterTank_A` | 带箍金属水箱 | 288 |
| `Roof_Skylight_A` | 双坡天窗 | 52 |
| `Roof_MechanicalBox_A` | 百叶设备箱 | 180 |

每款底部 Pivot 接地、根 Transform 为单位变换、XZ 外包围盒不超过 2m，使用一个 Renderer 与两个共享材质槽。烟囱复用墙身／压顶材质，其余使用金属／深色玻璃材质。

天窗的“玻璃”是 Opaque 深色表面，不代表透明、折射或专用玻璃渲染功能。设备建模循环仅在编辑器制作工具中执行，不进入移动端逐帧逻辑。

### 3.3 共享材质与小尺寸纹理

**状态：已完成；证据：[已验证：材质与制作代码]。**

新增共享材质：

- `M_SB_Style1_Parapet_Wall`：红砖墙身。
- `M_SB_Style1_Parapet_Coping`：暖色石材压顶。
- `M_SB_Style1_Roof_Metal`：屋顶设备做旧金属。
- `M_SB_Style1_Roof_RoofGlass`：天窗及设备深色凹槽。

新增 `Assets/PCG/Texture/Style1_Roof_AgedMetal_BaseColor.png`，尺寸 256×256。制作工具配置 sRGB、MipMap、Repeat、Bilinear 与压缩导入，用共享小纹理提供表面变化。

四个材质使用 URP/Lit、Opaque、Cull Back，启用 GPU Instancing，关闭 Double Sided GI。没有新增 Shader、自定义功能 keyword 或法线贴图 keyword，也没有新增 RendererFeature／RenderPass／中间 RT。

### 3.4 接入 SBStyle_Test，保持素材与生成参数边界

**状态：已完成；证据：[已验证：StyleConfig 差异]。**

`SBStyle_Test.asset` 的屋顶配置保留原有屋面素材，增加三款女儿墙及五款设备：

- 三款女儿墙登记到屋顶屋面／女儿墙组，Role 分别为 9、20、21；WidthSpan=1、DepthSpan=1，绝对素材高度 0.6，Weight=1、Enabled=true、AllowedFacades=All。
- 五款设备登记到屋顶附件组，Role 为 18（RoofProp），使用模型包围盒高度，WidthSpan=1、DepthSpan=1、Weight=1、Enabled=true。
- 上述数据是素材尺寸、用途、可用范围与选择权重，不是生成数量或密度。
- 女儿墙生成开关、目标高度、设备数量、位置、Seed 等仍归 HDA 实例参数；素材登记不拥有这些值，也不授权 Apply 覆盖它们。

示例素材高度 0.6 与示例实例女儿墙高度 0.6 是两个职责不同的值，不能据此恢复 StyleConfig 到实例的隐式参数继承。

### 3.5 编辑器制作、审计与示例应用工具

**状态：已完成；证据：[已验证：源码]，具体执行结果见第 6 节。**

新增两个开发辅助脚本，位于 `.agents/scripts/`，不进入运行时程序集：

| 工具 | 职责与边界 |
|---|---|
| `StreetBuildingParapetExample.cs` | 示例资产初建、审计、预览与女儿墙示例应用；Build 拒绝覆盖已有素材 |
| `StreetBuildingRoofStyleExample.cs` | 收敛最终网格／材质、审计、预览与风格应用；在既有素材上更新网格及引用 |

风格修订工具在制作迭代中保留 Mesh／Prefab GUID，避免重新创建导致引用断裂；从 Git 基线看，这八组素材均是提交 33 的新增文件，不能误写成提交 32 已经交付了这些正式资产。

审计覆盖根 Transform、底部接地、设备尺寸、Renderer／材质槽、URP 材质状态、退化三角形、面序与法线，以及 StyleConfig 有效性。天窗还检查玻璃子网格朝向。

最终风格 Apply 针对示例楼栋，临时抑制 Recook 随机化并恢复原开关；应用前后快照比较全部 StreetBuildingAuthoring 楼栋的生成参数。示例工具里的固定楼名与资产路径不是新增运行时配置接口。

工具的 Build、Apply、Preview、Audit 会按职责修改资产、场景或输出审计文件，不是无副作用的查询命令。本轮日志整理没有运行这些制作／应用方法，也没有用旧工具重建现场。

## 4. 问题、原因与最终解决方案

### 4.1 冷加载 HDA 尚无有效 AssetID 时查询参数

**状态：已完成；证据：[已验证：代码差异]，重开时序专项仍待复验。**

- 场景重开／Domain Reload 后，HDA 在 HEU 重新加载完成前可能保持 `AssetID = -1`。
- Session Sync 可能在该间隙触发 BeforeCook；此时不应向不存在的 HAPI 节点查询参数。
- `StreetBuildingInstanceParameters.Exists` 新增 `a != null && a.AssetID >= 0` 前置条件，再进行 Session 与参数 ID 查询。
- 无有效节点时返回参数不存在，不在这个阶段改写实例值。

这是项目自有桥接层的最小保护，没有修改 Houdini Engine Unity 插件。该修复不等于所有 Domain Reload、Session 丢失和首次绑定问题都已获得完整验收。

### 4.2 测试结果 XML 写入途中被读取

**状态：已完成；证据：[已验证：代码差异]，竞争时序专项仍待复验。**

- 测试结果写入器可能先截断文件再写入内容，轮询期间会读到空文本、半份 XML 或非预期根节点。
- `Invoke-PcgRegression.ps1` 先读取文本，空白则继续轮询；XML 解析失败则继续；根节点不是 `test-run` 也不接受。
- 只有完整结果才继续执行既有测试用例全名、数量及结果检查；原有时间戳与验收逻辑没有被放宽。

本修复处理结果读取的中间态，不是忽略测试失败，也不代表本次提交新增了 Unity 测试用例。

### 4.3 女儿墙拼接与设备造型收敛

**状态：已完成；证据：[已验证：最终网格规范与制作实现]、[历史还原：场景验收]。**

最终方案通过独立阴角、统一 2m 臂长、压顶交汇区去重、统一端部截面与外向法线解决示例素材的拼接要求；通过共享材质和各设备专用低面数外形提升识别度。早期被覆盖的造型不保留为额外功能或独立版本分支。

## 5. 主要资产与代码变更

| 范围 | 提交 33 的变化 |
|---|---|
| `Assets/PCG/Art/Building_Test/Style1/Models/` | 8 个新增 Mesh 资产及 meta |
| 同目录 `Prefabs/` | 8 个新增 Prefab 及 meta |
| 同目录 `ParapetExample.md` | 尺寸、Pivot、法线、材质、接缝与替换规范及 meta |
| `SBStyle_Test.asset` | 屋顶三款女儿墙、五款设备素材登记 |
| `Assets/PCG/Materials/Buildings/` | 四个共享材质及 meta |
| `Assets/PCG/Texture/` | 金属底色纹理及 meta |
| StreetBuilding HDA、HIP、`PCG_Building.unity` | 本阶段示例接入后的保存状态 |
| `.agents/scripts/` | 两个示例制作工具、测试 XML 读取保护 |
| `StreetBuildingInstanceParameters.cs` | 冷 AssetID 参数查询保护 |

提交共变更 52 个文件。没有新增自研 Shader、运行时 GPU 剔除系统或移动端 Cook 链路；历史本地报告不算作该提交新增的自动化合约文件。

## 6. 验证记录与证据边界

### 6.1 开发期历史现场记录

**证据：[历史还原]，不是本轮复测。**

本地 `.codex_tmp/parapet_style_20261012/` 保留最终风格阶段的报告：

- `mesh-audit.json`：最终八款网格的顶点／三角形、包围盒及材质审计；数量与本节上文列出的最终规格对应。
- `shape-contracts.json`：矩形、左右 L 形拼接记录为 PASS，并检查连续轮廓、外向法线、压顶位于屋内、单位缩放、确定性与独立开关。
- 12×10m 矩形：14 个直段、4 个阳角、0 个阴角；同外框带 4×4m 缺口的左右 L 形：10 个直段、5 个阳角、1 个阴角。
- `scene-verify-reply.json`：最终 Unity 示例记录为 PASS，女儿墙直段 10、阳角 5、阴角 1、RoofProp 1，匹配 Unity 实例共 17，屋顶 Y=18。
- `scope-changes.json`：制作迭代中的既有 meta 未改变。该结论针对本地 Capture 范围，不等同于全部资产在上一 Git 提交已存在。

这些报告可帮助追溯开发，但部分位于未纳入版本管理的临时目录。提交 33 没有新增相应独立合约源码／JSON；仅拉取提交不能假设完整历史报告仍然存在。

### 6.2 本轮日志整理的复验

- 初始 Unity 门禁：`Ensure-UnityPipeline.ps1 -TimeoutSeconds 30` 通过；Editor 主进程、版本、Pipeline Server 与 `editor_status=ready` 正常。
- Houdini 门禁：`Ensure-HoudiniMcp.ps1` 报告 GUI 未运行，本轮不能验证 Live Scene 或宣称原生 MCP 调用成功。
- 本轮核对提交差异、制作工具、配置与资产规格；未运行素材 Build／Apply，没有保存 HDA、HIP 或 Unity 场景。
- 独立 `hython` 执行 `HoudiniProject/PCG_Track_21.0.440/scripts/tools/validate_streetbuilding_contract.py --source fresh`：退出码 0、总状态 PASS，验证新建锁定实例 `/obj/VERIFY_STREETBUILDING_V12_LOCKED`，类型 `pcgbike::StreetBuilding::1.0`。
- 本轮 fresh 输出确认矩形女儿墙直段 14、阳角 4；左右 L 形分别为直段 10、阳角 5、阴角 1，且阴阳角素材区分有效。累计实例规则 36 例、窗模块数量 48 例、屋顶线脚 64 例、首层单线脚 40 例与屋顶下沿线脚 40 例等检查通过。这些是既有累计合约复验，不计为提交 33 新增功能。
- fresh 验证使用既有合约测试素材／数据，不能替代本阶段全部最终 Prefab 的 Unity 可见面、接缝与真实实例引用验收，也不证明 GUI Live Scene 状态。
- 结束时再次执行 `Ensure-UnityPipeline.ps1 -TimeoutSeconds 30`：通过，Pipeline 可达、Editor 为 ready。
- 本轮没有重跑 Unity EditMode 测试、完整 VerifyFast／VerifyFull 或移动端真机测试；不能以 Pipeline 连通替代行为验收。

### 6.3 工作区保护

任务开始时没有已跟踪文件的未提交修改，但已有 Art、Terrain Shader、StreetBuilding／Terrain／Track 手册、PCG Tests、ReferenceFinder 等未跟踪文件。本轮仅新增 Phase33 文档，不将这些既有文件算作本次交付，不清理或覆盖它们。

## 7. 性能、兼容性与扩展风险

### 7.1 CPU 与 GPU 分工

| 阶段 | CPU 职责 | GPU／运行时边界 |
|---|---|---|
| 编辑期素材制作 | 构建网格、UV、法线、写入素材与审计 | 不进入逐帧更新 |
| 编辑期楼栋生成 | Houdini Cook 与实例参数处理 | 仅开发预览，发布前 Bake |
| 发布后渲染 | 消费 Bake 数据，不运行 Houdini 或制作循环 | 使用原生 Mesh／共享材质；批处理收益需实测 |

女儿墙只保留外壳可见面，设备控制在 36～288 三角形；共享 256×256 金属纹理限制纹理规模。Opaque 与背面剔除避免新增透明排序及透明叠加成本。

### 7.2 Instancing、Variant 与移动端

- 材质启用 Instancing 不等于场景实际形成 GPU Instancing 批次；两个 SubMesh／材质槽可能产生两次材质提交，需用 Frame Debugger 检查。
- 本阶段新增自定义 Shader keyword 为 0，但沿用 URP/Lit 自带变体，不能据此承诺总 Variant 数量低于 200。
- 没有新增全屏 Blit、MRT、RenderTexture 或 RenderPass，未增加额外渲染管线带宽环节。
- Android Mali／Adreno 与 iOS Metal 的 DrawCall、SetPass、纹理带宽和阴影开销未实测。高密度楼群仍需要按 Bake 后批处理、Chunk／LOD 与剔除策略验收。
- 不将本阶段示例 Prefab 实例化写成已经交付 Indirect Draw、Compute Culling 或自动 LOD。

### 7.3 扩展点

新增同 Role 素材通过 StyleConfig 候选与权重扩展；保持单位、Pivot、跨度和高度约束。数量、分布、开关等生成需求继续进入 HDA 实例参数，不塞回素材配置。复杂透明天窗如未来确有需求，应另行定义性能预算，不扩大当前 Opaque 示例的职责。

## 8. 当前状态矩阵与后续验收

| 项目 | 状态 | 结论 |
|---|---|---|
| 女儿墙三件套 | 已完成 | 最终规格、网格与材质已交付；拼接有历史报告 |
| 五款屋顶设备 | 已完成 | 低面数模型、共享材质与配置已交付 |
| 素材／实例职责分离 | 已完成 | 配置保留素材约束；最终 Apply 有参数快照保护 |
| 编辑器制作与审计工具 | 已完成 | 供示例维护，不是运行时系统 |
| 冷 AssetID 查询保护 | 已完成 | 代码已加入；重开／Domain Reload 时序待专项复验 |
| XML 中间态读取保护 | 已完成 | 不放宽原有验收；真实竞争时序待专项复验 |
| 当前 Live Scene 与 Unity 全链路 | 待复验 | 历史结果与本轮验证严格区分 |
| 移动端 Bake／批处理与性能 | 待复验 | 不以低面数或 Instancing 选项代替实测 |
| 本阶段新增 GPU Culling／Indirect Draw／LOD | 未实现 | 不属于本次素材交付范围 |

后续优先补齐：保存重开与 Domain Reload 的冷实例回归；矩形及左右 L 形的新实例 Apply／Recook／Bake；其他楼栋参数不变与开关独立性；测试结果文件截断／半写入时的门禁行为。最后再用移动端 Frame Debugger／Profiler 验证共享材质、批次和阴影成本。
