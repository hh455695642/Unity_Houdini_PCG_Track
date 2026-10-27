# Style1 Reference 主体模块升级交付与维护说明

日期：2026-10-24。范围：`StreetBuilding_MyTest` 当前使用的 `Assets/PCG/Art/Building_Test/Style1/SBStyle_Test.asset`。

本文主体记录 2026-10-24 的主体素材升级；以下原有计数、测试和截图均为该历史任务数据，不替代后续附件／布局修改的验收。固定展示场景 `Assets/PCG/Scenes/StreetBuilding_ReferenceValidation.unity` 已列为退役资产，由 2026-10-26 清理移除。现验证入口为 `Style1ReferenceAttachmentValidation.GetRunPaths(outputDir)`，从 Assets 外的证据目录产生唯一 `Assets/__PCGValidation/SB_<hash>/` 临时根；验证场景、Prefab 和 Bake 数据完成检查后卸载并删除，证据独立保留。

2026-10-26 本轮原生 Bake 已实现整条排水管合并。8×10m、3 层标杆的附件请求及实际为水塔 1、烟囱 2、消防梯组 1、落水管 2，整栋 124 个 Renderer、10,943 三角形；这是本轮单个标杆的资产计数，不是 DrawCall 或设备性能测量。完整矩阵与最终累计回归由本轮收尾记录确认，运行时 LOD 和 Android/iOS GPU 性能仍未验证。附件规则与本轮标杆证据见 `AttachmentReferenceUpgrade.md`。

**VerifyFull 状态：PASS。候选与生产新实例的 190 项 Houdini 累计合约通过，原有 Unity 全程序集两轮各 65/65 通过。随后视觉复核发现商业窗洞斜视漏缝，新增两项正式几何测试，旧几何 0/2、修复后 2/2、保存重开后再次 2/2；几何补面前后编译载荷哈希完全不变。最终素材审计及三个既有实例参数保留检查通过。生产 StreetBuilding HDA/HIP/meta 与 Capture 哈希一致，未更新 definition。**

## 本轮实际变化

新增 15 个 `Reference_*` 模块，用于红砖墙、浅拱/矩形窗、墨绿色商业店面、石材腰线和深色屋顶檐口。通过现有 SBStyle_Test 的模块引用接入，保留实例生成面板的职责。没有覆盖原始 FirstFloor、UpperLayer、Prop 和 Roof FBX；当前已跟踪原始素材中，本轮配置变更集中在 SBStyle_Test 的引用及适配设置。

目前结果是可用来继续精修的简化主体套件：已建立参考图的红砖、浅石窗楣、绿色商业首层和深色大檐口等主要识别元素。实际 Unity 标杆截图仍呈现较均匀的砖纹、简化木作、暗色不透明玻璃和较规则的窗位；不能表述为已经达到参考图的完整精致度或写实光照质量。参考图中的斑驳、藤蔓、垃圾桶和椅子未纳入主体效果交付。

## 模块清单与规格

模块 Prefab 位于 `Assets/PCG/Art/Building_Test/Style1/Prefabs/`，对应正式 Mesh 位于同套资产 `Models/` 下的同名 `.asset`。以下统计来自本轮 `evidence/asset-audit.json`；每个新模块当前为 1 个 MeshRenderer。

| 模块名 | 生成角色 | 顶点 | 三角形 | 材质数 |
|---|---|---:|---:|---:|
| Reference_BrickWall_2m | GroundWall / MiddleBlank | 4 | 2 | 1 |
| Reference_Window_Arch_2m | MiddleWindow | 453 | 231 | 3 |
| Reference_Window_ArchPair_4m | MiddleWindow | 906 | 462 | 3 |
| Reference_Window_Rect_2m | MiddleWindow | 208 | 104 | 3 |
| Reference_Shopfront_2m | GroundShop | 292 | 146 | 3 |
| Reference_Entrance_2m | Entrance | 364 | 182 | 3 |
| Reference_Column_Ground | FacadeColumn | 140 | 70 | 1 |
| Reference_Column_Upper | FacadeColumn | 60 | 30 | 1 |
| Reference_FloorBand_2m | FloorBand / Cornice 候选 | 40 | 20 | 1 |
| Reference_FloorBand_Corner | FloorBandCorner | 12 | 6 | 1 |
| Reference_Parapet_Straight | Parapet | 104 | 52 | 1 |
| Reference_Parapet_Corner | ParapetCorner | 208 | 104 | 1 |
| Reference_Parapet_ConcaveCorner | ParapetConcaveCorner | 208 | 104 | 1 |
| Reference_RoofSurface_2m | RoofSurface | 4 | 2 | 1 |
| Reference_ACUnit | ACUnit | 52 | 26 | 1 |

基础 Bay 为 2m，墙面/门窗模块高度 3m；双窗为 4m 占宽，但在数量合约中仍计一个模块。屋面为 2×2m。根 Transform 归零，+Y 向上、+Z 朝外；普通立面模块保持底部中心 pivot，专门转角遵循现有边界 pivot 合约。柱与线脚尺寸不应由生成器非等比缩放来适配。

女儿墙及檐口保持 **0.6m 高**，通过横断面形成外挑、托座及屋顶可见内侧斜压顶。内侧斜压顶是有正确朝向的单面可见表面，并不是给整块外壳增加封闭背面，也没有开启双面材质。阳角/阴角有各自几何，不使用负缩放镜像。后续改截面需同步检查直段、阴阳角和屋面关系，不能只改直段。

当前配置中的 Cornice 候选引用 `Reference_FloorBand_2m`，用于满足现有素材 Validator 的完整角色检查；**当前 HDA 实际不发出该角色**，不能将这一候选描述成新的屋顶生成能力。顶部大檐口来自 Parapet 三类模块，Cornice 候选不是把首层 Cornice 强行放到屋顶。

## 材质、纹理与移动端取舍

新增共享材质位于 `Assets/PCG/Materials/`：

- `Style1_Reference_Brick.mat`：砖墙表面。
- `Style1_Reference_Trim.mat`：木作、石材、金属等共同使用六格色板。
- `Style1_Reference_Glass.mat`：暗色渐变玻璃表现，当前是不透明材质。

三者都使用 URP/Lit，Instancing 开启，Cull Back，Double Sided GI 关闭，Alpha Clip 关闭；未新增自定义 Shader、keyword、RendererFeature 或 RT。材质当前 enabled keyword 列表为空，不代表 URP 自身编译变体为零。

新纹理位于 `Assets/PCG/Texture/`：`Style1_Reference_Brick.png`（源文件 1254×1254）、`Style1_Reference_Trim.png`（384×64）、`Style1_Reference_Glass.png`（64×128）。纹理使用 sRGB、MipMap，Read/Write 关闭。Android 使用 ETC2_RGB4，iOS 使用 ASTC_6x6，平台最大尺寸 1024；实际平台导入尺寸以最终构建检查为准。源文件像素尺寸不等于 GPU 常驻尺寸，不能从 PNG 文件大小推导设备显存。

Brick UV 按米平铺；Trim UV 采样色板中心，避免为每种结构颜色拆材质；Glass 使用归一化坐标的暗部渐变。首轮没有法线/遮蔽细节贴图和完整室内，内凹与窗楣形体主要依靠几何表达。保留不透明玻璃能避免本套新增大面积透明叠层，但不构成实测的 GPU 毫秒收益。

“三材质”仅指新增 Reference 主体模块的共享表面族。旧雨棚、招牌、屋顶附件仍引用原有材质；开启这些附件后的整栋建筑材质数可以超过 3，不能将三材质宣传为整套历史素材或所有输出的全局上限。

## 可维护源文件与输出关系

当前维护入口：

- `.agents/scripts/build_style1_reference_kit.py`：九个主体模块的原生 Houdini SOP 源与几何规格生成器。
- `.agents/scripts/Style1ReferenceUpgrade.cs`：从 spec 构造 Unity 正式 Mesh/Prefab、配置材质并接入风格；同时包含屋顶边缘等六个补充模块的几何配方。
- `.agents/scripts/Style1ReferenceValidation.cs`：参数快照、网格检查和独立 HAPI 样例验证。
- `Assets/PCG/Tests/Editor/StreetBuildingReferenceGeometryTests.cs`：正式 EditMode 累计几何测试，通过真实三角形和正面斜射线检查店面窗洞与门缝。
- `Assets/PCG/Art/Building_Test/Style1/Models/ReferenceKit_Source.cpio`：九个主体模块的可编辑原生 Add / Attribute Wrangle / Normal SOP 网络。
- 同目录 `ReferenceKit_spec.json`：本轮导出的顶点、法线、UV、三角形和材质分组规格。
- 同目录九个 `Reference_*.fbx`：砖墙、三窗型、店面、入口、上下层柱和直腰线的 DCC 交换输出。

六个补充模块是 Parapet 直段/阳角/阴角、FloorBand 转角、RoofSurface 与 ACUnit，其当前几何源在 C# 的 `BuildEdges()` / `BuildSupportModules()`，不是九模块 CPIO/FBX 的一部分。因此当前不是“15 个模块全部已有 FBX 或 Houdini SOP 源”。如果美术需要在 DCC 内精修全部屋顶配方，应先把这六个模块另行导出或迁移到可编辑 DCC 资产，保持角色/尺寸不变并履行回归门禁。

当前 Prefab 消费的是正式 Unity `.asset` Mesh。FBX 是可编辑交换输出；修改 FBX 不会自动改写已经存在的 Reference Prefab 的 Mesh 引用。当前 `BuildModules()` 从 spec 构造 `.asset`，所以 DCC 修改应明确选择：导出并同步更新规格/正式网格，或有意识地把 Prefab 引用切换为经验证的 FBX Mesh。不能同时保留两个互相漂移的事实源。

## 再生成与编辑流程

1. 重新运行 Unity/Houdini preflight，记录当前磁盘与 Live，保全目标场景、StyleConfig、Reference 资产及其 `.meta`；按任务白名单 Capture。不要复制历史备份覆盖当前有效资产。
2. 九主体模块如需程序化调整，修改当前 `build_style1_reference_kit.py` 配方，再用独立 hython 输出到新的 staging 目录：

   ```powershell
   & 'D:/Software/Side Effects Software/Houdini 21.0.440/bin/hython.exe' .agents/scripts/build_style1_reference_kit.py --output .codex_tmp/regression/<本次任务>/staging
   ```

   `--geometry-only` 仅导出并检查 JSON，不导出 Houdini CPIO 或 FBX。该脚本拒绝输出到生产 Assets，不加载/保存项目 HIP，不整包重建 HDA。人工编辑 CPIO 后需明确对应导出/规格同步方式；重新运行生成器会以当前 Python 配方为准。
3. 屋顶/转角等补充模块修改当前 `Style1ReferenceUpgrade.cs`，由 `BuildModules()` 调用对应配方。核对 spec 所在 staging 路径；当前 C# 常量指向本次任务目录，后续任务不能无检查地读取残留 spec。
4. 通过 Pipeline 类型化资产命令导入/创建资源。对于目录中不存在的特定复杂几何配方命令，使用当前 C# 维护源执行构建，记录调用方法和缺失的类型化能力；不要通过旧 patch 重放来生成新状态。
5. `StageTextures()` 只提供 Trim 和 Glass 暂存 PNG，不重建 Brick 的美术内容；Brick PNG 必须独立保留并维护。替换纹理后复核 Mip、sRGB、压缩、平台 override，避免脚本复写人工材质参数。
6. `BuildModules()` 会重建本任务 Reference 命名的 `.asset` 和 Prefab 内容；`Apply()` 会按 Role 重绑 SBStyle_Test，且含 Cornice 启用和 FloorBand 适配范围处理。若后续做了人工模块替换，应先审查当前 Apply 配方，不能当作无副作用的普通 Recook。
7. 已绑定的目标实例使用 `StreetBuildingStyleApplier.ApplyAndSave(root, authoring, false)` 同步素材并 Cook，保存前比较参数快照，检查真实输出与缺项。尺寸、窗数、门数、用途、排列、密度和附件开关继续在实例面板维护。
8. 运行素材审计、验证样例、VerifyFast/VerifyFull，通过后再保存正式资产/场景并从磁盘复验。辅助保存入口只应在验收通过后调用；核对其当前签名和明确传入的临时验证路径，不再保存到已退役的固定展示场景。

不得运行历史 `patch_*_vN.py` 或旧 builder 来“补环境”。当前 Python/C#/CPIO/spec 的职责必须保持清楚，人工编辑内容先保全，禁止重生成无提示覆盖。

## 参数保留与样例证据

本轮 `parameters-after.json` 记录 `status=PASS`、3 个既有 Authoring 实例、`differences=[]`。目标仅豁免素材桥接三字段 `module_source`、`unity_style_catalog`、`unity_bridge_end_marker`；窗门配额、用途、排列、seed、变换等仍参与对比。非目标冷态实例不为审计强制 Cook，按完整缓存和身份状态核对，不能把缓存对比描述成已验证所有非目标实例的实时 HAPI 输出。

十个样例由独立 HAPI 会话创建当前 HDA 新实例、绑定同一 SBStyle_Test、Cook 并执行正式 Bake 可行性门禁。展示快照引用正式 Mesh/Material，只包含 Transform、MeshFilter、MeshRenderer，不依赖验证实例的 HEU 缓存；这是一组原生可查看快照，不是已优化的移动端最终渲染批次。

| 样例 | 尺寸 / 层数 | 附件 | 三角形 | Renderer | 共享材质种数 |
|---|---|---|---:|---:|---:|
| Reference_00_Benchmark | 8×10m / 3 | 关 | 6542 | 112 | 3 |
| Reference_01_Attachments | 8×10m / 3 | 开 | 7216 | 116 | 6 |
| Reference_02_Narrow | 4×8m / 3 | 关 | 4184 | 70 | 3 |
| Reference_03_Wide | 16×10m / 3 | 关 | 9410 | 166 | 3 |
| Reference_04_L_Left | 16×12m / 3，左 L 缺口 | 关 | 9574 | 178 | 3 |
| Reference_05_L_Right | 16×12m / 3，右 L 缺口 | 关 | 9574 | 178 | 3 |
| Reference_06_Low | 8×10m / 2 | 关 | 4333 | 92 | 3 |
| Reference_07_Tall | 8×10m / 6 | 关 | 13169 | 172 | 3 |
| Reference_08_SeedRepeat | 8×10m / 3，同 seed 29 | 关 | 6542 | 112 | 3 |
| Reference_09_SeedVariation | 8×10m / 3，seed 47 | 关 | 6746 | 110 | 3 |

本表来自各 `evidence/gallery/Reference_*.json`，十项均为 PASS。每样例重复 Apply 检查确定性和实例参数 tuple；08 样例额外与 00 样例比较两次独立新实例的输出指纹。完整 VerifyFull 另行通过。证据包含升级前后、标杆五视图、左右 L 形/宽版/高层斜视与屋顶、模块展示，以及最终 Scene/Game View 实拍；没有宣称十栋的所有观察角度都已拍摄。

历史展示场景为 `Assets/PCG/Scenes/StreetBuilding_ReferenceValidation.unity`，原先默认仅启用 00 标杆，其余九个样例保留但关闭；`ReferencePresentation` 仅提供展示灯光与相机，不属于模块。该场景未加入 Build Settings，现已列入退役清理，不再作为可打开的现用入口。复验应使用 `Style1ReferenceAttachmentValidation.GetRunPaths(outputDir)` 返回的唯一临时场景，完成后删除临时资产；历史十样例 JSON 与截图保留在原证据目录。逐模块展示对象没有被声明为最终移动端渲染批次。

## 性能解释与仍未测量项

新增模块将原有部分 4 材质源模块压到不超过 3 材质，例如入口从 309 三角形/4 材质变为 182/3，弧顶双窗从 554/4 变为 462/3；原有实墙从 6 三角形变为 2。与此同时，原来简化的商业橱窗从 18 三角形变为 146，女儿墙直段从 6 变为 52，阴阳角从 12 变为 104。这是将几何预算投向建筑层次和檐口轮廓，并不是全面减少面数。

历史无附件标杆的 6542 三角形、12958 顶点和 112 Renderer 反映当时的编辑/展示粒度，不作为本轮含附件标杆的当前计数。主体共享三材质能降低材质离散程度，但 Renderer/SubMesh 数不是实际 DrawCall/SetPass。勾选 Instancing 也不能证明 Unity 已合批；URP SRP Batcher 与 Instancing 的实际选择需使用 Frame Debugger 检查。

CPU 主要风险是大量模块 Renderer 和绘制提交；后续进入移动端内容时应复用现有 Bake，按空间与材质组织可剔除批次。GPU 主要增加窗楣与托座几何，受益于低成本不透明玻璃和单面外壳；仍需评估阴影绘制、带宽、overdraw 与远景 LOD。此轮不新增逐帧 CPU 实例驱动，也不重写 GPU 间接绘制框架。

原有目标的最新计数见 `source-performance-comparison.json`，包含其原实例形体、现有附件和辅助输出，不能拿它与 8×10m 无附件标杆直接宣称整体降幅。该记录材质列表含辅助输出的空资产路径，应视作 Editor/临时引用审计限制，不能当作最终运行时资产集合已全部合规的证明。

**Frame Debugger DrawCall/SetPass、移动设备 GPU 毫秒、Mali/Adreno/Apple GPU 性能、最终显存均未实测。** 本轮报告只使用资产计数和已完成行为证据，不用 Editor 帧率代替移动端性能结论。

## 兼容与遗留 Bake

`Assets/PCG/Generated/Buildings/MyTestCityFrontage` 和 `MyTestCityVaried` 是既有 Bake 库，本次没有自动更新。它们可能继续使用原有烘焙 Mesh 与材质；源素材升级不会自动保证城市现有实例同步。需要更新时应单独审计手工覆盖、引用和布局，在新白名单/Capture 下重新 Bake，不能直接覆盖美术或地编已编辑的旧 Prefab。

现有雨棚、招牌、烟囱、水塔等附件继续复用，关闭附件时主体仍可单独展示。当前完整素材检查记录了缺少专用 CornerConvex/CornerConcave 时使用语义角落 fallback 的提示，这与新增 Parapet 阴阳角是不同角色；不能把该提示误述为本轮没有屋顶转角，也不能宣称所有 validator 提示均为零。

## 验收记录位置

证据根：`.codex_tmp/regression/streetbuilding-mytest-reference-upgrade-20261024/evidence/`。

- `asset-audit-final.json`：补齐商业窗洞内侧后的 15 模块、法线/UV/winding、材质与 bounds 审计。
- `parameters-before.json`、`parameters-after.json`：3 实例参数保留。
- `asset-replacements.json`、`style-payload.txt`：本轮映射与编译目录；审计时 StyleConfig 25 个有效条目，SHA256 为 `4856a4aad7de23772613a68884879bf034613c7606cecd6edecd4139646b9567`，后续变更应重新编译，不将此哈希当永久常量。
- `gallery/Reference_*.json`：十个真实生成样例、输出元数据、参数与确定性。
- `geometry-before-fix-status.json`、`geometry-after-fix-status.json`、`geometry-saved-reopen-status.json`：真实斜射线测试旧几何失败、修复通过及磁盘重开通过。
- `gallery-geometry-after-fix.json`：补面前后 HDA 编译载荷相同、十个原生快照几何计数更新；历史计数另外保存在 `gallery-before-aperture-fix/`。
- `before-*.png`、`benchmark-*.png`、`module-lineup.png`：Unity 截图；完整性和审美质量应由实际图片评审。
- `source-performance-comparison.json`：源模块与当前实例计数，带有未测量说明。
- `verify-full.log`：完整 VerifyFull PASS，候选/生产两轮 Unity 各 65 passed，`persistence=not-required`；源 HDA/HIP/meta 哈希不变。
- `asset-audit-after-reopen.json`、`parameters-after-reopen.json`：磁盘保存重开后的 15 模块审计及三个既有实例参数保留 PASS。
- `console-final.json`：最终重开及本任务资产操作的日志增量；Editor 原先已有 CityRoad/服务错误历史，漏缝复现阶段另有两项预期失败的 NUnit 结果，均保留原始记录，本次没有清除日志。
- `console-infrastructure-history.json`：新增测试触发编译重载时，AI 工具日志器出现一条 `BufferedFileLogStorage: Flush called but already disposed, ignored.` 警告。已保留精确原文与 seq=527，不将其归为建筑 Cook 警告，也未修改或宽泛忽略插件日志；随后操作从该检查点继续采样。
- `final-game.png`、`final-scene.png`：最终 Unity 实拍。`benchmark-*.png` 等为实际生成快照的 Unity PreviewRenderUtility 多视图。
- 开工、收尾都执行 `.agents/scripts/Ensure-UnityPipeline.ps1`；最终机器可读记录为 `pipeline-final.json`。

本轮不修改原城市 Bake 库，不修改 Houdini 插件文件。工作区原有未跟踪美术、Terrain、文档和测试文件保留；本次新增资产与改动以本任务 manifest 和独立文件备份为准。Unity 自动序列化的场景 diff 较大，未为减少 diff 人工清理 YAML。

Houdini 当前会话没有原生工具绑定，实际通过 `.codex_tmp/houdini_mcp_client.py`（uv 使用 `E:/HoudiniProject/oculairmedia_houdini_mcp` 环境）连接同一 `http://127.0.0.1:3055/mcp`；未声称原生工具恢复。任务前 CityRoad 的磁盘和未保存 Live 分别保全至本任务 `backup/CityRoad-disk-before.hip`、`backup/CityRoad-live-before.hip`，收尾恢复原 Live 内容与原工程文件名，原 CityRoad 磁盘文件不覆盖。

实际门禁命令：

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .agents/scripts/Invoke-PcgRegression.ps1 -Module StreetBuilding -Stage Capture -ChangeManifest .codex_tmp/regression/streetbuilding-mytest-reference-upgrade-20261024/change-manifest.json
powershell -NoProfile -ExecutionPolicy Bypass -File .agents/scripts/Invoke-PcgRegression.ps1 -Module StreetBuilding -Stage VerifyFast -ChangeManifest .codex_tmp/regression/streetbuilding-mytest-reference-upgrade-20261024/change-manifest.json
powershell -NoProfile -ExecutionPolicy Bypass -File .agents/scripts/Invoke-PcgRegression.ps1 -Module StreetBuilding -Stage VerifyFull -ChangeManifest .codex_tmp/regression/streetbuilding-mytest-reference-upgrade-20261024/change-manifest.json
python -m unittest discover -s HoudiniProject/PCG_Track_21.0.440/scripts/tests -p test_pcg_regression_gate.py -q
```

最后一项 gate 单元测试 20/20 通过。纯美术 manifest 的 no-save 分支是本次安全修复，仍执行全部累计合约和两轮 Unity 测试，不以跳过验证换取不写 HDA。


2026-10-26 验收范围：原生 **Prefab Bake**、重复 Prefab 更新和保存重开已验收。原生 Standalone 更新遇到 Houdini Engine 将共享素材目录推导为 `Assets//Meshes` 的错误；失败证据保留在本轮 `evidence/native/Benchmark_BakeUpdate-bake-update-proof.json`，本轮未修改插件，也未把这条更新路线标为通过。运行时 LOD 与移动设备 GPU 性能仍未验证。


## 2026-10-26 本轮最终验收与退役结果

完整累计门禁通过：227 项登记合约；保存／导入前后两轮 Unity EditMode 均为 90/90。Pipeline 状态查询另有 10 项真实 PowerShell AST 故障注入合约，使用独立 mock 验证暂时断连、第三次失败上限、旧 XML、错误测试身份、失败及跳过结果；不以旧轮次 XML 代替当前轮次。正式入口为 `.agents/scripts/Invoke-PcgRegression.ps1`，状态恢复检查为 `.agents/scripts/Test-UnityPipelineStatusRecovery.ps1`。

实际原生几何验收共 30 个独立实例：16 功能案例、12 街景案例、2 个重复 Prefab 更新／持久化补验。每条管的实际源 Mesh × HAPI 变换、HEU 实例与合并 Prefab 逐有向三角形／法线／UV／材质比对；HAPI 关闭、29 例批量冷重开及最后 1 例独立冷重开均通过。两补验各执行两次原生 Prefab 更新；旧整管 Mesh 的 GUID 和字节均保留，新 Mesh 在生产流程中即时落盘，验收代码不替生产输出补保存。

两个指定旧场景及 `Generated/Buildings/ReferenceAttachments` 专用树已通过 AssetDatabase 类型化删除：106 个候选 GUID、162 个文件和 meta 已在 Assets 外备份。两个旧场景和专用目录的永久缺失合约已加入；活动验证入口使用唯一临时根，验收后临时场景／资产也已归档并删除。正式 Style1、其他城市 Bake 和历史 HDA 备份保留。

证据根：`.codex_tmp/regression/streetbuilding-placement-20261026/`。最终完整门禁日志为 `evidence/native-retirement-verify-full-status-retry.log`；旧状态查询中断日志与原生 Standalone 更新失败均保留，不能标记为成功。清理逐项清单与可恢复哈希在 `retirement-final/cleanup-manifest.json`；8 张真实 Unity 截图在 `evidence/screenshots/`；实际 Mesh 统计在 `evidence/native/mesh-metrics.json`；保存范围和证明限制在 `evidence/final-disk-preservation-audit.json`。

标杆 8×10m／3 层为 124 Renderer、198 材质槽、10,943 三角形；Editor 已加载独立 Mesh 估算 560,808 bytes。2／3／6 层各有 2 条管，合并后均为 2 个管道 Renderer。此数据不代表设备 DrawCall、SetPass、GPU 时间或 VRAM；当前没有接入运行时 LOD/GPU 批量系统。
