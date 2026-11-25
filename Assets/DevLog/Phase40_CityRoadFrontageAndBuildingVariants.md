# Phase 40 开发日志：CityRoad 沿街建筑缺排修复与四风格整栋建筑库

> 记录日期：2026-11-25
>
> 主提交：`0bb206943103b5946a90b6eb86bb30919ca38510`（`40`）
>
> 对比基线：`deecd843c67781dc46c1b5138885dd3c999ef409`（`Phase39`）

提交 40 修复了微弯路段一侧可能整排缺少建筑的问题，并将 `PCG_City_Test.unity` 中原来的 8 个 Style2 整栋候选替换为 4 种风格、每种 8 个的专用建筑库。**最终场景引用 32 种 Prefab，不是提交目录中所有原型的总和。**

## 1. 版本与证据

环境为 Unity `6000.3.22f1`、URP `17.3.0`、Houdini `21.0.440`。生成端改动在 `Assets/PCG/HDA/City/CityRoad.hda`、`PCG_Bike_CityRoad.hip` 和 `cityroad_frontage.vfl`；本次没有修改 StreetBuilding HDA。以下资产与引用数量以提交 40 的 Git 树、场景序列化路径和 Prefab GUID 为准。专项 Cook 的结果与未验证事项分别列在第 5 节。

## 2. CityRoad：修复微弯长街一侧缺排

原实现先合并近共线的道路外边，再用源三角形的内部点判断合并后长边的哪侧朝外。遇到细长但有效的三角形与轻微转折时，内部点可能落在合并弦线的另一侧。结果是整段的外向被判反，而不是建筑候选不够。

提交 40 改为在**原始外边**上用相邻三角形的第三个顶点确定外向，再把这个方向保留到合并之后。即使合并时端点调换，最终垂线也会与原始外向对齐。排布时先让原来朝向正确的路段占用建筑用地，再让修复的路段填入剩余空间，避免它在路口抢占相邻街排的位置。这一修复在开发期 Houdini Cook 中完成，没有新增运行时组件或 HDA 公共参数。

## 3. 城市测试场景：哪些建筑真正接入

新资产根目录为 `Assets/PCG/Generated/Buildings/PCG_City_Test/CityRoad1/`。下表只统计各组 `Prefabs/` 下的整栋成品，不重复计算 `Native/` 下的 Bake 源、制作模块或同一编号的替代版本。

| 资产组 | 提交的整栋 Prefab | 主场景实际引用种数 | 主场景序列化实例数 |
|---|---:|---:|---:|
| 根目录 `Prefabs/`：S1–S4，各 V01–V08 | 32 | 21 | 389 |
| `DetailWidth/`：宽度与细节变体 | 9 | 9 | 154 |
| `StreetNotch/`：S2_V07、S3_V07 缺口变体 | 2 | 2 | 42 |
| `StreetscapeC/`、`StreetscapeD/`：独立街景原型 | 6 + 13 | 0 | 0 |
| **合计** | **62** | **32** | **585** |

9 个宽度／细节变体和 2 个缺口变体**替代**根目录的同编号建筑，并未把候选数从 32 增至 43。实例数按场景中指向这些成品 GUID 的 `m_SourcePrefab` 记录统计，不是同屏可见数或 Draw Call。C、D 组虽有各自的制作场景、网格和 Prefab，但主场景中没有其成品路径或 GUID 引用。

制作侧共提交五个场景：基础建筑库、DetailWidth、StreetNotch、StreetscapeC 和 StreetscapeD 各一个。基础组还保留了 CityRoad1 专用的 `SBStyle1_CityRoad1.asset`、8 个模块 Prefab 和 20 份材质，可从制作资产继续编辑，不必反拆整栋网格。

## 4. LOD、道路材质与工具

- **整栋 LOD**：基础库的 32 栋配有 64 份 Near／Far 网格。部分细节变体在中距离保留轮廓，例如 `DetailWidth/Prefabs/PF_CityRoad1_S2_V06.prefab` 使用 Near、DetailSilhouette、Far 三级；不能据此把所有建筑都记为三级 LOD。
- **道路外观**：人行道材质 `M_PCG_CityRoad_Sidewalk.mat` 的 `_TileMeters` 从 2 调至 0.3，使同一距离内的纹理重复更密；道路颜色贴图 `T_Mountainbike_Road_C.tga` 同步更新。沥青、路缘和标线材质仅新增序列化字段 `m_AllowLocking`，不计为新着色功能。本次没有新增 Shader、关键字或 RenderPass。
- **工具回归**：新增 `.agents/scripts/Test-UnityPipelineCompatibility.ps1`。它用模拟返回值检查生产适配器能否保留资产记录、场景脏标记以及 Error／Exception／Assert，能否拒绝截断日志，并检查主 Editor 进程识别。它不执行场景 Bake。

## 5. 验证记录与遗留事项

| 状态 | 检查方式与结果 |
|---|---|
| 已完成 · 已验证：沿街布置专项 | 用独立 Houdini 进程加载提交版 CityRoad HDA，运行 `validate_cityroad_frontage.validate`。新增微弯用例通过：受影响外侧至少 7 个正确朝向的点，首尾跨度超过 70 m。原有直路基准仍为两侧各 10 点，短分段、退距、间距、确定性和开关等断言均通过。 |
| 已完成 · 已验证：资产接入 | 对比父提交的 8 条 Style2 路径，以提交 40 的路径与 GUID 交叉核对，得到第 3 节的 32 种、585 个场景实例。 |
| 已完成 · 已验证：工具兼容 | 实际执行 `Test-UnityPipelineCompatibility.ps1`，8 项用例通过。Houdini 独立进程有 COP 偏好设置与 RPC 端口占用的启动诊断，但验证器执行完毕；未切换或保存当前图形会话中的 HIP。 |
| 待复验 | 本轮未执行完整 VerifyFull、Unity 场景重开或重新 Bake，也未做真机性能测试。应在稠密街段检查 LOD 过渡与人行道远景纹理闪烁，再用移动端实测判断批次、带宽和帧时变化。 |
