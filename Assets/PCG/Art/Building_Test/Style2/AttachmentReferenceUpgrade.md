# StreetBuilding Style1 参考附件

本套素材提供参考图中的架高木水塔、砖烟囱、连续消防梯和落水管。正式输出位于同目录的 `Prefabs/Reference_*`，由 StreetBuilding 的 StyleConfig 编译为 `M` 行、`X|1` 素材语义行，以及可选的 `A|1` 挂点／`P|1` 管道端点规格。数量、立面、楼层和开关由 **HDA 实例**控制；`SBStyle_Test` 仅保存可用素材和约束。

## 模块规格

| 生成单位 | 正式素材 | 连接与落位 | 单件三角形 / Renderer / 材质槽 |
|---|---|---|---|
| 水塔 | `Reference_WaterTower_A` | 支架四脚在屋面 y=0；完整占地 1.8×1.8m，含锥顶高 3.5m | 574 / 1 / 1 |
| 烟囱 | `Reference_Chimney_Brick_A`、`Reference_Chimney_TwinFlue_B` | 底座 y=0，帽檐和双烟管纳入真实 Bounds | 60、112 / 各 1 / 2 |
| 连续消防梯 | `Reference_FireEscape_Storey_A` 与 `Storey_Right_B`、`TopTermination`、`BottomTermination` | 单层连接高 3m；平台近墙通道与两端落脚面围成真实梯井；左右梯段均正缩放 | 816 / 每段 1 / 1；顶部 356；底部 140 |
| 屋顶检修梯 | `Reference_FireEscape_RoofAccessLadder` | pivot 为屋面 y=0；下探 3m 接顶层平台，上延 1.6m 越过女儿墙；仅在 HDA 实际屋顶连接检查通过时启用 | 420 / 1 / 1 |
| 落水管 | `Straight_1m`、`TopInlet`、`BottomOutlet`、`Elbow`、`Offset` | 一条管线只选一次墙面走廊；直段连接高 1m，直径 0.1m，顶/底收口在不同楼层分组；弯头共享截面，无开裂端面 | 直段 16；顶 72；底 76；偏移 48 / 源件各 1 / 1 |

全部正式 Prefab 根 Transform 为单位变换，只有 Transform、MeshFilter、MeshRenderer；没有运行时组件。复用 `Style1_Reference_Brick.mat` 和 `Style1_Reference_Trim.mat`，URP/Lit、Opaque、Cull Back、GPU Instancing，新增自定义 Shader keyword 为零。排水管直段不带可被轴向拉伸的管箍，只允许在已声明的 0.05～1m 长度范围适配，X/Z 管径比例始终为 1；固定弯头与上下端保持单位比例。项目自有 Bake 事件将每条管线的同材质几何合并为一个 `SB_PIPE_…` Renderer，保留组名和持久 Mesh。实际三角形数量随局部绕行段变化，验收使用 Bake 前后的有向三角形、法线、UV 和材质属性比对。运行时 LOD 接入和设备 GPU 时间另行验证。

同一 `Straight_1m` Prefab 分别登记在首层和标准层素材中；顶部接水口与屋顶检修梯登记在屋顶素材中。它们的物理立面仍是墙面，输出校验依据零件子类型识别屋顶端件，管段楼层按真实高度计算。缺少首层直管素材时整条管线拒绝，并保留实例请求。

## 可编辑源与同步

**确定性几何配方** `.agents/scripts/build_style1_reference_attachments.py` 是源事实。它生成 `Models/ReferenceAttachments_spec.json`、`ReferenceAttachments_Source.cpio` 和每件 FBX；CPIO 内为命名 Add 点/面、UV Wrangle 与 Normal SOP，无 Python SOP，便于在 Houdini 中查看、修改轮廓。FBX/CPIO 是生成的源交换件；手工修改必须同步回配方并重新导出，否则下一次重建会覆盖手工结果。

Unity `Models/Reference_*.asset` 是按 spec 重建的正式 Mesh，`Prefabs/Reference_*` 引用这些 Mesh 和共享材质。重新生成顺序：运行配方导出至任务外部 staging；核对 spec 的 marker、法线、面数和 Bounds；通过 Unity Pipeline `asset import` 更新 FBX/CPIO/spec 并保留 `.meta`；运行 `.agents/scripts/Style1ReferenceAttachmentUpgrade.cs` 的 `BuildMeshSources`、`CloseMeshSources` 和 `AuditAssets`；最后 `AuditStyle` 校验编译载荷。不得只替换 FBX 而留下旧 Mesh `.asset`。

## 布局与性能边界

HDA/HIP 网络是布局实现事实源。附件支路由 `ATTACHMENT_SUPPORT_CANDIDATES`、`PLAN_CONTINUOUS_ATTACHMENTS`、`PLAN_TYPED_ROOF_PROPS`、`ASSEMBLE_CONTINUOUS_ATTACHMENTS`、`VALIDATE_REFERENCE_ATTACHMENTS`、`ATTACHMENT_DIAGNOSTICS` 六个节点负责候选、整组布局、装配和验证。`PROJECT_REFERENCE_METADATA_INPUT` 仅服务元数据合并，保留最终点用于准确计数，并移除该支路不使用的连接属性。

- 新模式的水塔/烟囱按整件、消防梯按整组、管线按整条计数。容量不足时保留请求，输出实际值和原因。
- 消防梯沿同一物理墙段逐层连接；管线竖向共用同一横向坐标。窄楼、L 形凹口、屋顶关闭和缺素材时可合法少生成，必须在诊断中说明。
- 移动端只消费 Bake 后的 Unity 资产，不在运行时 Houdini Cook 或每帧组合附件。源件各一个 Renderer，原生 Bake 后每条管线合并为一个 Renderer；实际 DrawCall、SetPass、阴影和 GPU ms 需在目标 Android/iOS 设备及最终 Bake 方案上测量。
- 本轮不实现任意障碍寻路、真实建筑通行或物理给排水。自动管线使用直段、上下收口及局部偏移管件绕过腰线／檐口，再返回贴墙；复杂障碍处若没有合法走廊应拒绝并报告。

屋顶水塔和烟囱在同一 Detail Wrangle 中生成。VEX 的 `point()`/`npoints()` 不能读取本次运算刚由 `addpoint()` 写入的零件，因此不能依赖输出点回读实现彼此避让。`PLAN_TYPED_ROOF_PROPS` 使用局部 Bounds 数组记录已接受的完整占地，每接受一个零件立即预留，并用输入点数加新增数检查预算；保留屋面边界、L 形凹口与已有附件的检查，不改写实例请求。

## 使用与当前验收口径

在建筑实例的附件参数中将屋顶附件切为 `TypedCounts`，设置 `water_tower_count=1`、`chimney_count=2`；消防梯切为 `Continuous`，设置整栋 `fire_escape_group_count=1`、起始层 2、终止层为实际顶层；需要屋顶检修梯时单独启用。落水管使用 `drainpipe_enabled` 与每栋 `drainpipe_count=2`。旧实例默认保持 Legacy 和原有数量，素材 Apply 不会自动开启这些生成模式。

消防梯立面 mask 是固定可用集合：正面 1、次正面 2、侧面 4、背面 8；多选按位相加，整栋共享数量。具体次正面以物理墙段语义为准，不能把 bit2 当作“右侧”。不满足请求时读取参考附件诊断中的请求、实际与原因；不要通过增大素材权重绕过容量。

本轮贴墙排水与整管合并后的真实原生 Bake 标杆为 8×10m、商业首层、3 层：水塔 1、烟囱 2、消防梯组 1、落水管 2；整栋为 124 个 MeshRenderer、10,943 三角形。证据位于 `.codex_tmp/regression/streetbuilding-placement-20261026/evidence/native/Benchmark.json`。Renderer 数不是设备 DrawCall 测量值；完整矩阵、冷重开和最终累计回归结果由本轮收尾记录确认。

历史分件 Bake 在同类基准中记录四类附件 28 个 MeshRenderer、3,622 三角形，整栋 144 个 MeshRenderer、11,775 三角形；这些数据属于旧附件任务，不代表本轮结果。

固定场景 `Assets/PCG/Scenes/StreetBuilding_AttachmentValidation.unity` 和专用 Bake 树 `Assets/PCG/Generated/Buildings/ReferenceAttachments/` 已列为退役资产，由本轮清理移除，不再作为验证入口。现入口 `Style1ReferenceAttachmentValidation.GetRunPaths(outputDir)` 从 `.codex_tmp/regression/<run>/…` 证据目录产生唯一 `Assets/__PCGValidation/SB_<hash>/` 临时根，场景、原生 Prefab 和 Bake 数据均放在其下，验收后卸载并删除本次临时根，证据保留在 Assets 外。窄楼容量反例使用合法的 4×4m 体块，明确请求 2 组背面消防梯，并按真实输出检查容量诊断；不使用违反素材网格约束的 2m 宽输入伪造容量反例。

L 形第 2/3 缺口方向的凹进首层正面需要柱件支持 `SecondaryFront`。首层柱素材范围由 `Front|StreetSide` 补为 `Front|SecondaryFront|StreetSide`；不改变柱、门或窗的请求值。真实 Style1 正向和内存克隆恢复旧 mask 的缺项反例均纳入累计 Unity 测试。

屋顶穿插验收要求独立于规划器的接受数量和 `attachment_bounds` 输出：Houdini 合约 `StreetBuilding.Reference.RoofPropSeparation` 根据测试源尺寸与实际点位重建占地，覆盖 1 座水塔+2 座烟囱及 2 座水塔+4 座烟囱；Unity 从真实 Mesh 的 Bounds 八角点与实际 Transform 计算 XZ 包围，逐对检查，容差 1mm。原生 Bake 生成前后、HAPI 会话关闭后及场景重开均需执行真实 Mesh 检查。历史附件任务的 16 组样例记录了 45 对实际屋顶 Mesh 检查通过；其 4×4m 容量反例只容纳水塔，烟囱请求 2、实际 0、原因 `capacity`，消防梯请求 2、实际 1。这些是历史验收数据，不替代本轮复验；旧穿插样例已在历史任务证据目录归档并标记失效。

高女儿墙验收使用真正 1.2m 高的直段、凸角、凹角测试模块，现放在本次唯一临时根下的 `Bakes/HighParapetRoofAccess/ValidationInputs/`，随本次验证资产一并清理；历史固定 `Generated/Buildings/ReferenceAttachments/HighParapetRoofAccess/ValidationInputs/` 路径已退役。生产素材的女儿墙实际高 0.6m；模块实例保持单位缩放，仅修改 `parapet_height` 不会把现有 Mesh 拉高。验证脚本仅在内存克隆的 Style 中替换这 3 个测试模块，不改生产 Style。历史附件任务记录的 14 个墙件高度为 1.20000076m、梯顶高出墙顶约 0.425m、192 个上部梯面通过保守不相交检查，均为历史测量；本轮需重新验证生成、Bake、关闭 HAPI 和场景重开。测试用固定槽位保证局部重建不移动到其他案例位置。

独立 LOD1 源位于 `Models/LOD1/`：16 个 FBX、原生 Mesh `.asset`、可编辑 CPIO 与 spec。`source_name` 显式对应 LOD0；pivot、实际包围与连接高度保持，材质槽继续按 spec 的 Brick/Trim 家族绑定同名 LOD0 材质。历史源统计为 16 件合计 4,846→2,210 三角形、水塔 574→262、标准层梯段 816→372、完整三层管线 756→312；其中管件已在本轮换为贴墙源，旧合计及管线数据不作为当前面数。使用生成器的 `--lod1-only` 独立导出；FBX Importer 使用 `useFileScale=false`、`globalScale=1` 保持米制，并关闭动画、相机和灯光导入；原生 Mesh 直接按 spec 构造，避免交换格式转换影响正式连接。LOD1 不登记为随机素材候选，不改变实例数量；spec 明确标记 `runtime_lod_connected=false`，源几何的降幅不代表展示 Bake 已按距离自动替换为 LOD1。

本轮已实现项目自有原生 Bake 事件中的整管合并，保留可编辑低模源。运行时 LOD/批量绘制接入及 Android/iOS 设备 DrawCall、SetPass、GPU ms 仍未验证；材质 Instancing 开关和 Renderer 计数不替代这些验证。历史附件任务检查过中性光照、原场景灯光、45m 观察距离和附件连接近景，不代表本轮全部观察角度已经复验，也不代表任意替换素材或任意檐口尺寸都无穿插。

## 历史附件任务验证入口与证据

以下命令、通过数量、场景恢复状态和截图均归属 `streetbuilding-reference-attachments-20261024` 历史任务，不代表本轮布局与验证资产退役任务的最终结果；历史白名单不能用于验证后续修改。本轮使用 `streetbuilding-placement-20261026` 下的当前白名单与证据。

在项目根目录执行，使用本任务的 Capture 和修改白名单；不能用重新 Capture 掩盖回归：

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .agents/scripts/Ensure-UnityPipeline.ps1
powershell -NoProfile -ExecutionPolicy Bypass -File .agents/scripts/Ensure-HoudiniMcp.ps1
powershell -NoProfile -ExecutionPolicy Bypass -File .agents/scripts/Invoke-PcgRegression.ps1 -Module StreetBuilding -Stage VerifyFast -ChangeManifest .codex_tmp/regression/streetbuilding-reference-attachments-20261024/change-manifest.json
powershell -NoProfile -ExecutionPolicy Bypass -File .agents/scripts/Invoke-PcgRegression.ps1 -Module StreetBuilding -Stage VerifyFull -ChangeManifest .codex_tmp/regression/streetbuilding-reference-attachments-20261024/change-manifest.json
```

Unity 状态、资产和测试使用 Pipeline CLI 类型化命令。当前会话未加载原生 Houdini 工具；实际 Live 调用使用 `.codex_tmp/houdini_mcp_client.py`，以标准 MCP Python SDK 连接同一个 `http://127.0.0.1:3055/mcp` 转接服务，再由服务连接 18811 RPC。这是客户端回退路径，不能表述为原生工具已恢复。预检、握手和实际工具调用需要分别验证，服务端工具发现成功不等于 Live 修改成功。

本轮屋顶修复的累计验证日志为 `.codex_tmp/regression/streetbuilding-reference-attachments-20261024/evidence/verify-full-roof-separation.log`。2026-10-26 验收结果：205 项累计合约通过，保存前后两轮 Unity EditMode 均为 83/83，接口辅助单元测试 15/15；保存后的全新锁定 HDA、Unity 导入、16 组原生 Bake、关闭 HAPI 后引用、真实 Mesh 分离检查、实际高墙越墙和展示场景冷重开均通过。最终范围检查 `verify-fast-delivery.log` 通过。

HDA 保存于 `Assets/PCG/HDA/City/StreetBuilding.hda`，HIP 保存于 `HoudiniProject/PCG_Track_21.0.440/PCG_Bike_StreetBuilding.hip`。生产 HDA、HIP、Style 与源素材在 Full 通过后哈希保持不变；随后仅加强验收脚本的真实高墙夹具和固定展示槽位，并重新 Bake/冷重开复验。原生结果见 `evidence/final-native-acceptance.json`、`actual-roof-bounds-audit.json`、`HighParapetRoofAccess.json`，15 张实际 Bake 截图位于 `evidence/screenshots/`。所有 `evidence/` 路径均相对于上述任务目录。

最终 Unity Console 为 0 error、0 warning，Pipeline 链路健康。过程中 Unity 云服务曾出现两条 `services-gateway` 配置字典异常，堆栈位于 `UnityEditor.Connect.ServicesConfiguration`，已保留在 `console-before-rebake.json` / `console-after-owned-cleanup.json`；Windows PowerShell 5 的一次 CLI JSON 参数转义失败也已留档，改用 pwsh 7 后重跑通过。上述诊断与最终生成验收分开记录，不宣称它们从未发生。Style 校验中既有的 `CornerConvex` / `CornerConcave` 可选素材缺项仍走原有语义回退，不属于本轮新增输出 warning。

原 Unity `PCG_Building` 已恢复为唯一打开的干净场景，20 个根对象；文件与任务前已保全的 Live/Capture 基线一致。原 CityRoad 磁盘 HIP 字节未改，已恢复其备份中的 Live 内容、原文件名、选中节点和 dirty 状态，未将该未保存现场写回 CityRoad 磁盘文件。保护范围和未捕获目录的证明限制见 `evidence/final-scope-preservation-audit.json`。


## 2026-10-26 布局规则与素材连接规范

- 首层“跟随实际门窗”模式只使用最终分配的 Entrance / GroundShop / GroundShopDoor。默认挂点取实际宿主顶部和外表面；不通过层高减固定常量推算，也不对普通墙格挂商业雨棚。旧网格模式仍可显式读取。
- 横招牌默认底边位于宿主顶部 +0.02m；雨棚顶部位于宿主顶部 -0.04m；侧挂招牌顶部位于宿主顶部 -0.02m。所有位置仍检查真实素材最低点 ≥2.35m 和实际宿主宽度，不暗改层高或配额。显式挂点可覆盖源坐标连接位置。
- `A|1|PrefabPath|x|y|z` 是源模块局部安装点；可同时描述宿主顶部点与附件安装点。字段位于素材高级约束，不保存数量或布局。
- `P|1|PrefabPath|sx|sy|sz|ex|ey|ez|radius|min|max` 描述源管件端点、半径与允许长度范围。新直管中心 local Z=0.10m；生成时先求真实承载墙外表面，再加 0.10m，管外壁距平墙约 0.05m。腰线／檐口使用局部偏移，经过后返回贴墙。进水斗和支架计入实际包围。
- 没有 P 的旧目录仅支持原有 0.55m 几何规范；复制旧 Style 却改用新版贴墙 Prefab 时必须显式补齐连接规格，否则输出 connection_spec 容量诊断，不能套用旧连接点导致断管。
- 新几何同步入口为 `Style1ReferenceAttachmentUpgrade.UpgradePipeSources(taskDirectory, save)`，只处理五类管件、LOD1 和素材端点。先以 save=false 暂存，完整验收后以 save=true 保存，不重放历史整套升级。
- 水塔／烟囱分别使用 Fixed 或 RandomRange，每栋完整模块计数。Fixed 复用原 count，RandomRange 只读取 min/max；隐藏字段不影响当前模式。新增模式默认 Fixed，不修改原实例值。
- `roof_prop_position_mode` 为 Legacy 或 Seeded。Seeded 的数量、位置、选材使用独立稳定域，V2 同时读取已有 master seed 和附件重抽样序号；旧 Legacy 固定扫描保留。
- 商业街景消防梯使用既有 Rear 或 Rear|Side 立面配置，主／次商业正面排除。功能测试可明确开启其他立面，不应将其当作街景预设。

验证入口接收 `.codex_tmp/regression/<run>/…` 证据目录，通过 GetRunPaths 返回唯一 `Assets/__PCGValidation/SB_<hash>/` 临时资产路径。调用者负责 finally 卸载本次场景并使用 AssetDatabase 类型化删除临时资产。历史累计用例和证据保留，不再默认生成常驻验证场景。


2026-10-26 验收范围：原生 **Prefab Bake**、重复 Prefab 更新和保存重开已验收。原生 Standalone 更新遇到 Houdini Engine 将共享素材目录推导为 `Assets//Meshes` 的错误；失败证据保留在本轮 `evidence/native/Benchmark_BakeUpdate-bake-update-proof.json`，本轮未修改插件，也未把这条更新路线标为通过。运行时 LOD 与移动设备 GPU 性能仍未验证。


## 2026-10-26 本轮最终验收与退役结果

完整累计门禁通过：227 项登记合约；保存／导入前后两轮 Unity EditMode 均为 90/90。Pipeline 状态查询另有 10 项真实 PowerShell AST 故障注入合约，使用独立 mock 验证暂时断连、第三次失败上限、旧 XML、错误测试身份、失败及跳过结果；不以旧轮次 XML 代替当前轮次。正式入口为 `.agents/scripts/Invoke-PcgRegression.ps1`，状态恢复检查为 `.agents/scripts/Test-UnityPipelineStatusRecovery.ps1`。

实际原生几何验收共 30 个独立实例：16 功能案例、12 街景案例、2 个重复 Prefab 更新／持久化补验。每条管的实际源 Mesh × HAPI 变换、HEU 实例与合并 Prefab 逐有向三角形／法线／UV／材质比对；HAPI 关闭、29 例批量冷重开及最后 1 例独立冷重开均通过。两补验各执行两次原生 Prefab 更新；旧整管 Mesh 的 GUID 和字节均保留，新 Mesh 在生产流程中即时落盘，验收代码不替生产输出补保存。

两个指定旧场景及 `Generated/Buildings/ReferenceAttachments` 专用树已通过 AssetDatabase 类型化删除：106 个候选 GUID、162 个文件和 meta 已在 Assets 外备份。两个旧场景和专用目录的永久缺失合约已加入；活动验证入口使用唯一临时根，验收后临时场景／资产也已归档并删除。正式 Style1、其他城市 Bake 和历史 HDA 备份保留。

证据根：`.codex_tmp/regression/streetbuilding-placement-20261026/`。最终完整门禁日志为 `evidence/native-retirement-verify-full-status-retry.log`；旧状态查询中断日志与原生 Standalone 更新失败均保留，不能标记为成功。清理逐项清单与可恢复哈希在 `retirement-final/cleanup-manifest.json`；8 张真实 Unity 截图在 `evidence/screenshots/`；实际 Mesh 统计在 `evidence/native/mesh-metrics.json`；保存范围和证明限制在 `evidence/final-disk-preservation-audit.json`。

标杆 8×10m／3 层为 124 Renderer、198 材质槽、10,943 三角形；Editor 已加载独立 Mesh 估算 560,808 bytes。2／3／6 层各有 2 条管，合并后均为 2 个管道 Renderer。此数据不代表设备 DrawCall、SetPass、GPU 时间或 VRAM；当前没有接入运行时 LOD/GPU 批量系统。
