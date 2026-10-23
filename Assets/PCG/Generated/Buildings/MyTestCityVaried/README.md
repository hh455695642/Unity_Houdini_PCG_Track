# StreetBuilding 多样化街屋库

用于 `PCG_City_Test/CityRoad1` 的 8 个建筑槽位。源为 `PCG_Building/MyTest_Varied_Authoring`，实例生成参数与 HAPI preset 保存在 `Recipes.json`；`SBStyle_MyTestCityVaried.asset` 只负责素材与适配约束。

| 索引 | 宽×深 | 层数 | 轮廓 / 首层 |
|---|---|---|---|
| 00 | 4×6 m | 2 | 矩形住宅 |
| 01 | 8×6 m | 3 | 矩形商业 |
| 02 | 6×8 m | 5 | 矩形住宅 |
| 03 | 8×8 m | 8 | 矩形住宅 |
| 04 | 8×8 m | 4 | L 形，前侧缺口，转角商业 |
| 05 | 8×8 m | 6 | L 形，后侧缺口，住宅 |
| 06 | 4×8 m | 7 | 矩形窄高住宅 |
| 07 | 8×8 m | 2 | 矩形宽面商铺 |

差异还包括门窗数量和排列、商业橱窗覆盖、雨棚/招牌、空调/消防梯、女儿墙和屋顶附件。所有方案都经过正式素材可行性与 Bake 检查，原始 `StreetBuilding_MyTest` 与上一轮工作副本的实例参数、素材绑定保持不变。

近景按共享材质合并为 6–12 个 Renderer；远景每栋 1 个 Renderer，矩形 12 三角形、L 形 24 三角形。碰撞体为 1/2 个 BoxCollider。近景 LOD 阈值按包围盒最大尺寸 / 160 计算，并限制在 0.045–0.18；远景剔除阈值为 0.015。移动端预算仍应按最终摄像机、可见数量和设备做性能验收。

预设只依赖 Unity 持久化 Mesh、共享 URP/Lit 材质和原生组件，不依赖运行时 Houdini Cook。继续复用 `MyTestCityFrontage/Modules` 与原有共享材质，不应删除这两个依赖目录。本次没有新增 Shader、keyword 或材质副本。

CityRoad 实例密度：`building_spacing=1.2`、`building_gap_max=0.8`、`building_empty_ratio=0.015`、`building_group_length=55`、`building_within_group_jitter=0.1`、`building_setback_max=1`。保留已有地块预留宽深、种子、道路输入和道路范围。密度设置属于 CityRoad 实例，不属于素材 StyleConfig。

如需继续调整：在工作源实例中按配方恢复生成参数，改实例面板后重新检查实际数量、缺失模块和输出；增量 Bake 为新预设，再替换 CityRoad 槽位。不要覆盖原始 MyTest 或把配额写入 StyleConfig。
