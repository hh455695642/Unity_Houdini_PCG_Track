# Phase 38 开发日志：Style3 壁灯与阳台、附件参数统一

> 记录日期：2026-11-18
>
> 主提交：`2f56c87624c677ea6f119eb506bd2c2da14b7581`（`38`）
>
> 对比基线：`8d861a1028a95fd602d94d21a557146453bf0e63`（`Phase37`）

提交 38 把壁灯和“门＋平台”成套阳台接入 StreetBuilding，并在建筑制作场景保存了六种 Style3 样例。另一个变化是附件不再单独使用一套固定数量控件：生成数值、生成候选和楼层作用域各有明确语义。**这次交付的是建筑制作与近景 Bake，不是用 Style3 替换 CityRoad 的 Style2 街屋库。**

## 1. 环境与证据

Unity `6000.3.22f1`、URP `17.3.0`、Houdini `21.0.440`。本次差异涉及 194 个文件；建筑生成资产为 `Assets/PCG/HDA/City/StreetBuilding.hda` 和 `HoudiniProject/PCG_Track_21.0.440/PCG_Bike_StreetBuilding.hip`，变更的 Unity 场景为 `Assets/PCG/Scenes/PCG_Building.unity`。

下文的资产数量、场景引用、接口和 Bake 判定来自提交树、序列化文件与源码的**静态核对**。合约描述的是应当满足的行为；只有第 6 节列为本轮执行的检查才记为测试结果。未跟踪依赖单列，不作为提交成果。

## 2. 实例参数：数值用区间，开关与枚举用候选

| 参数 | 提交 38 的有效语义 |
|---|---|
| 水塔、烟囱数量 | 面板直接编辑整栋设备数的区间。整数两端相等即固定，不等即在闭区间取值；不再额外选择“固定／随机”。原生 `count_mode/min/max` 仍用于兼容、传值，不是第二份用户请求。 |
| 消防梯、落水管数量 | 分别按**整栋几组梯、几条完整管**计数，也使用数值区间；不按零件数或选中立面数翻倍。 |
| 生成开关、布局 | 单候选固定，多候选在显式生成时选择。先解析总开关和父模式，再解析有效子项；关闭或未采用模式的字段不参与抽样。 |
| 消防梯、落水管立面 | 候选先与 `12` 求交，只允许侧面（`4`）和背面（`8`）。单面固定，两面候选抽非空子集；交集为空报告冲突并保留请求。不是对位掩码做数值随机。 |
| 技术字段与作用域 | 种子、随机序号、调试、覆盖目标、梯组和阳台的服务起止楼层直接编辑，不作为生成区间。 |

迁移从当前 HDA 实例读取旧数量和立面请求，不从 StyleConfig 拉取默认配额。`StreetBuildingGenerationPolicy` 管理区间、候选和依赖顺序；`StreetBuildingRandom` 把壁灯、阳台、管线及屋顶设备归入 V2 附件随机组，使单独重抽附件不必重抽体块和门窗。

## 3. Style3：壁灯按盏，阳台按整套

**壁灯。** 新角色 `WallLamp`（24）按整栋首层计盏数，可单灯挂接，也可在入口两侧配对。入口素材提供左右灯位和开口范围，灯具提供安装点。成对布局不增加配额；奇数请求或合法挂点不足时保留请求并报告实际数。新实例默认关闭壁灯。

**阳台。** `Balcony`（25）是平台、栏杆与托臂，`BalconyDoor`（26）是独立的单格门洞素材。唯一配额是整栋标准层的阳台套数，起止楼层限制可服务范围。合约将 `balcony_door_count` 列为隐藏兼容字段；面板内仍有旧提示提及单独设置宿主数量，不能据此把门数记为第二个配额。新实例默认关闭阳台。

| 环节 | 如何保证一套阳台完整 |
|---|---|
| 选择宿主 | 在剩余合法单格实墙上检查门槛、开口与平台安装点，不消耗普通窗请求。合约覆盖 L 形同物理面和多栋各自计数。 |
| 规划与提交 | 合约将 `PLAN_STYLE3_ATTACHMENTS` 放入附件阶段，`COMMIT_STYLE3_BALCONY_PAIRS` 放入正式输出阶段。位置与现有附件冲突时重试；不能成套时保留原墙，不留下孤门或平台。 |
| Bake 前验证 | 用本次输入哈希排除过期 Cook。读取附件及宿主诊断，再从 `OUT_BUILDING_LOD0` 读取门、从 `OUT_DETAIL_INSTANCES` 读取平台，按 `style3_host_id` 比较两个集合与实际套数。缺配对、重复标识、缺素材／锚点或未知短缺原因会阻止正式 Bake；有明确容量原因可以少于请求。 |

**素材与实例的边界。** `SBStyle3.asset` 描述素材适配，不保存生成配额。编译器用 `S3|1` 行传递命名局部锚点，如 `lamp_left/right`、`mount`、`threshold`、`opening_min/max`。阳台可以声明最多三个连续编号的实体盒及门槛下方的墙面接触区；编译时检查源三角形确实被实体盒覆盖。未声明时按整件 Bounds 保守避让，不放宽开口净空。

**保存生成实例。** 成功 Cook 后，项目侧只在两个正式视觉输出中记录生成 Prefab 实例的名称和 Transform 覆盖，使源 Prefab 更新后仍可保留生成位置；不冻结素材自身的属性，也不引入逐帧遍历。

## 4. 素材、样例与性能边界

`Assets/PCG/Art/Building_Test/Style3/` 提交了 `SBStyle3.asset`、27 个模块 Prefab 和 27 个同名模型 Mesh。模块包括首层店面与入口、拱窗、标准层墙窗、阴阳角、腰线、屋面和女儿墙，以及壁灯、阳台门／平台、雨棚、空调与五类管件。表面色板纹理为 `Assets/PCG/Texture/Style3_SurfacePalette.png`。

制作场景新增 `Style3_Samples` 和六个使用 `SBStyle3` 的样例，原 Style1、Style2 配置绑定仍在。对应整栋输出位于 `Assets/PCG/Generated/Buildings/Style3/`；下表按各 `*_Near.asset` 的 submesh 索引数计算，不是运行时采样。

| 整栋 Prefab | 近景三角形 |
|---|---:|
| PF_Style3_Hero | 7,367 |
| PF_Style3_Narrow | 5,810 |
| PF_Style3_Wide | 10,969 |
| PF_Style3_LShape | 12,026 |
| PF_Style3_Balcony | 8,418 |
| PF_Style3_BalconyFront | 9,024 |

六栋均为 **1 个 MeshRenderer、2 个 submesh**，无 LODGroup、BoxCollider 或 MonoBehaviour；此次只提交 Near 网格。`PCG_City_Test.unity` 未变，仍使用 Style2 槽位。不能把 Phase37 的远景壳体、距离剔除或碰撞能力套用到这六个样例。

合并发生在编辑期，运行时渲染原生 Mesh，不需要 Houdini Cook。单 Renderer 不等于单 DrawCall；六个 Mesh 都保留 `m_IsReadable: 1`。本提交没有新增 Shader、项目 keyword 或 RendererFeature，也没有移动端帧时、阴影开销、内存或实际 Instancing 数据。

## 5. Pipeline 与回归工具

- Pipeline 从 `0.9.0-exp.1` 升到 `1.0.0`，Unity MCP 从 `1.3.0` 升到 `1.11.3`；同步更新 NuGet 依赖与 MCP 编译符号。URP 版本不变。
- `Ensure-UnityPipeline.ps1` 按项目路径识别真实 Unity Editor 主进程并排除 AssetImportWorker，避免崩溃后遗留的 `isRunning` 状态阻止启动。回归入口适配新版类型化命令的参数名、超时参数位置及结果结构。
- StreetBuilding 合约从 **227 项增至 253 项**：附件参数统一与侧背面子集 7 项、Style3 壁灯／阳台 18 项、Pipeline 类型化命令兼容 1 项。覆盖旧实例默认关闭、成对提交、避碰后保墙、与管线共存、结构接触、净空及 Bake 身份；登记不等于在干净检出上已跑通。

## 6. 验证、资产状态与遗留事项

| 项目 | 状态与依据 |
|---|---|
| Style3 素材、六栋样例和制作场景 | **已完成（静态核对）**：配置 GUID、模块数量、Mesh 和组件均能在提交树中定位。 |
| 材质依赖 | **部分完成**：Prefab 引用的两个 GUID 对应工作区中的 `M_SB_Style3_Surface.mat` 和 `M_SB_Style3_OpaqueGlass.mat`；两份材质及其 meta 未进入提交 38。仅检出该提交不能据此还原完整外观。 |
| 累计验证与维护源 | **部分完成**：已提交的回归入口调用 `Test-UnityPipelineCompatibility.ps1`，候选验证／保存代码导入 `validate_streetbuilding_style3.py`、`streetbuilding_style3_attachments.py`；三者均只在本地未跟踪。两份 Style3 宿主／附件 VEX 文本也未随提交交付。这不等于已提交 HDA 缺少内嵌实现，但独立检出不能复跑完整入口。 |
| 本轮工具验证 | `Test-UnityPipelineStatusRecovery.ps1` 的 **11/11** 个模拟故障案例通过（报告：`.codex_tmp/regression/phase38-devlog-ed698bfe/report.json`）。这不是 Unity EditMode 全集。`Ensure-HoudiniMcp.ps1` 已确认 Houdini RPC、建筑 HIP 与 MCP 服务端工具发现；本轮未操作 Live 节点。 |
| 运行行为与性能 | **待复验**：本轮未执行 Cook、Bake、保存重开、VerifyFull 或 Android／iOS 真机测试。城市槽位替换、Style3 整栋远景与碰撞均非本次交付。 |

下一次复验应先在干净检出核对材质 GUID 和回归入口依赖，再验证成对壁灯的奇数请求、阳台避碰失败时原墙是否保留，以及源素材更新／场景重开后的门台配对。若要将样例投放到 CityRoad，应另行验收远景、碰撞和目标设备预算。
