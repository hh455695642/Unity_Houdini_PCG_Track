# Style1 女儿墙示例制作规范

这套示例供 `StreetBuilding.hda` 的屋顶层使用，外观接续当前立面的红砖与暖色石材收口。所有尺寸单位为米；示例是游戏资产规范，不作为建筑工程尺寸标准。

| Prefab | Role | 外形与 Pivot |
|---|---|---|
| `PF_SB_Style1_Parapet_Straight_A` | `Parapet` | 2m 直段，底部中心，X=-1～1，外侧 +Z |
| `PF_SB_Style1_Parapet_Corner_A` | `ParapetCorner` | 阳角，轮廓交点为 Pivot，两臂分别沿 +X 与 -Z 各 2m |
| `PF_SB_Style1_Parapet_ConcaveCorner_A` | `ParapetConcaveCorner` | 阴角，凹角交点为 Pivot，两臂分别沿 +X 与 +Z 各 2m |

## 网格与材质

- +Y 向上；根 Transform 为位置 0、旋转 0、缩放 1。一个 `Visual` 子节点挂 MeshFilter 与 MeshRenderer。
- 墙身 Y=0～0.50；压顶前沿 Y=0.50～0.6；压顶顶面 Y=0.6，宽 0.24，朝建筑内部延伸。直段压顶 Z=-0.24～0。红砖复用当前立面 BaseColor，UV 密度每米 0.5；石材复用 Style1_Stone_BaseColor。
- 阳角外侧法线分别为 +Z、-X；阴角外侧法线分别为 +Z、+X。不能用负缩放镜像阳角代替。
- 只保留外侧墙面与顶部压顶可见面；无背面、底面、端面或不可见厚度。屋内侧观察时外墙面被背面剔除，这是项目外壳规范的预期结果。
- 阳角压顶两臂在 0.24×0.24m 交汇区只保留一份顶面，防止重复面与闪烁；阴角压顶向 -Z／-X 退让，并覆盖屋内侧的交汇方块。臂端截面与直段一致。
- 直段 12 顶点／6 三角形，转角各 24 顶点／12 三角形。每款一个 Renderer、两个 SubMesh，分别引用共享 Wall 与 Coping 材质。
- 材质位于 `Assets/PCG/Materials/Buildings/`，使用 URP/Lit、Opaque、Cull Back、GPU Instancing；Double Sided GI 关闭。没有新增 Shader 或功能 keyword；URP 自身 variants 仍须按项目构建策略裁剪，未宣称全管线 variant 数量低于 200。

## StyleConfig 登记与替换

1. 模型和 Prefab 分别放在本目录的 Models、Prefabs 中。外部 DCC 替换时保持上述单位、Pivot、方向、端面截面和尺寸。
2. 在 `SBStyle_Test` 的屋顶层“屋面／女儿墙及转角”登记三个对应 Role。WidthSpan=1、DepthSpan=1、HeightType=Absolute、AbsoluteHeight=0.6、Weight=1、Enabled=true、AllowedFacades=All。
3. 在 HDA **实例面板**设置女儿墙启用和高度 0.6；该值不保存在 StyleConfig 中，不允许生成端缩放补偿高度差。
4. 执行 Validate、Compile Preview，随后应用风格与 Cook。仅在本次验证通过后保存场景。
5. Prefab 文件名自动成为 module_variant；改名、移动或替换后重新 Apply／Cook。后续增加外观款式使用同 Role 的额外 Prefab 与权重，不添加生成配额。

每条屋顶边的首尾各一个 2m 格由转角臂覆盖，直段填充中间格。不能把转角做成很小的接头，否则会缺少两段边缘。

## 验收与维护

- 12×10m 矩形：14 个直段、4 个阳角。相同外框与 4×4m 缺口的左右 L 形：10 个直段、5 个阳角、1 个阴角。
- 检查整圈外墙面、压顶拼接、屋顶接触面、输出 scale=(1,1,1) 和实际 Unity Prefab 引用。
- 女儿墙开关与高度 0 只关闭女儿墙；屋面开关独立。重复 Apply／Recook、保存重开均不得改写其他实例生成参数。
- 本任务的 Capture、manifest、真实几何合约与截图记录在 `.codex_tmp/parapet_20261012/`。累计验证使用 `.agents/scripts/Invoke-PcgRegression.ps1` 的 StreetBuilding VerifyFast／VerifyFull。
- 编辑期制作和示例允许 Prefab 实例；移动端发布只消费 Bake 后的数据。两个材质槽可能产生两次材质提交，最终按现有 Bake／批处理路径处理，不增加运行时 Cook 或 CPU 实例更新循环。

维护工具：`.agents/scripts/StreetBuildingParapetExample.cs`。通过 Unity Pipeline `run_script` 调用 `Audit` 检查素材、`Preview` 更新模块图；`Build` 拒绝覆盖已经存在的素材。示例工具中的目标路径和目标楼名只服务于本验证样例，不进入运行时配置。

## 屋顶风格修订

- 五款 `Roof_*_A` 保留现有 Prefab 与 Mesh GUID：砖烟囱、低矮通风帽、带箍金属水箱、双坡天窗、百叶设备箱。替换的是示例模型和材质；数量、位置、Seed、开关仍由原有实例控制。
- 金属使用本套共享材质 `M_SB_Style1_Roof_Metal` 与 256×256 做旧底色；天窗及深色凹槽使用 Opaque 材质 `M_SB_Style1_Roof_RoofGlass`，没有透明混合、法线贴图 keyword 或新增 Shader。
- 每款设备一个 Renderer、两个共享材质槽；烟囱 36 三角形、通风帽 144、水箱 288、天窗 52、设备箱 180。底部 Pivot 接地，XZ 外包围盒不超过 2m，不在运行时执行制作循环。
- 修订工具 `.agents/scripts/StreetBuildingRoofStyleExample.cs` 的 `Build` 仅替换上述已备份素材的网格与引用；`Audit` 验证尺寸、法线、材质和风格配置；`Apply` 严格对比场景全部楼栋的生成参数。
- 本轮 Capture、回归、截图与接缝验证记录位于 `.codex_tmp/parapet_style_20261012/`。原灰白版任务前现场已另行保全。
