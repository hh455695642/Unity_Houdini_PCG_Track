# MyTest 城市建筑库

来自 `PCG_Building/StreetBuilding_MyTest` 的 8 个独立 Unity 预设：`PF_MyTestCity_00.prefab` 至 `PF_MyTestCity_07.prefab`。`PCG_City_Test/CityRoad1` 已使用这 8 个输入槽位。

`PCG_Building/MyTest_CityAuthoring_00` 是本次保留的制作工作实例，绑定同目录 `SBStyle_MyTestCity.asset`；原始 MyTest 与 SBStyle_Test 保留。尺寸、窗门数量、用途、排列、密度与开关都在 HDA 实例中编辑；StyleConfig 只维护素材和候选适配约束。

`Recipes.json` 是每栋制作记录，含宽深、楼层、种子及完整 HAPI preset。工作实例最后停留在 07 配方。预设是本次 Bake 的固定结果，编辑制作源不会自动更新已经 Bake 的网格。重新制作请派生工作实例并写入新版本目录；本次合并脚本会拒绝覆盖已有网格，避免丢失人工修改。

| 序号 | 宽×深(m) | 层数 | variation seed | layout seed |
|---|---|---|---|---|
| 00 | 6×6 | 3 | 183014 | 45060 |
| 01 | 8×6 | 3 | 183115 | 45197 |
| 02 | 6×8 | 4 | 183216 | 45334 |
| 03 | 8×8 | 4 | 183317 | 45471 |
| 04 | 6×6 | 5 | 183418 | 45608 |
| 05 | 8×6 | 5 | 183519 | 45745 |
| 06 | 6×8 | 6 | 183620 | 45882 |
| 07 | 8×8 | 6 | 183721 | 46019 |

预设地面中心为 pivot，前脸 +Z，单位缩放。近景按材质合并为 11–13 Renderer；远景为 1 Renderer / 12 三角形的共享轮廓。使用原生 LODGroup 和简化 BoxCollider；所有引用持久化，无 HDA、HEU 组件或临时缓存依赖。新材质使用 URP/Lit 并启用 Instancing，未增加 Shader/keyword。

新近景比旧占位楼细节更高、成本也更高。当前城市场景保留编辑期 GameObject 预览，移动端最终运行数据应接入项目的批量 Bake/Cluster/剔除管线；本次未测 Android/iOS 真机帧耗。

完整迁移、清理、验证和性能记录：项目根 `.codex_tmp/mytest-city-migration/DELIVERY.md`。本次源脚本与审计记录保留在同目录，脚本有现场和路径前置条件，不应直接盲目重放。
