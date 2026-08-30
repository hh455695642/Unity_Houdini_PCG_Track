# Phase 28 开发日志：StreetBuilding Style Kit 验收闭环与参考资产丰富化

> 文档类型：Git 提交增量审计与当前现场复验  
> 记录日期：2026-08-30  
> 版本文件：`Phase28_StreetBuildingStyleKitAcceptanceAndEnrichment.md`  
> 目标提交：`ba11ba561c223952342a72f175650d696370f3ba`（提交信息：`28`）  
> 直接父提交：`a28fb30a2485e979164c1845c9a459667afff3cb`  
> StreetBuilding HDA：`Assets/PCG/HDA/City/StreetBuilding.hda`  
> StreetBuilding HIP：`HoudiniProject/PCG_Track_21.0.440/PCG_Bike_StreetBuilding.hip`  
> Unity 场景：`Assets/PCG/Scenes/PCG_Building.unity`

## 1. 日志范围与阶段结论

本文只记录 Git 提交 `ba11ba56` 相对直接父提交 `a28fb30a` 的开发增量。提交 28 没有修改 StreetBuilding HDA/HIP，也没有升级 V6.1 几何生成合同；它集中完成两条工作：

```text
Phase27 遗留验收项
    -> 六个 ArtAuthoring 合同 ID 纳入累计合同
    -> VerifyFull 接入 Unity 反射测试桥
    -> DesignPreset 保存失败回滚补全

ProjectOwned 参考风格丰富化
    -> 每套 28 个 Prefab/Recipe 扩展到 41 个
    -> 4×4 Checker 纹理升级为 128×128 确定性参考纹理
    -> 新增 Style Kit Auditor
    -> 重建并保存六栋 Showcase
```

本阶段有效开发结果：

- **两套 ProjectOwned Style Kit 增加视觉 Variant。** Brick 与 Stucco 各新增 13 个 Prefab/Recipe，覆盖玻璃入口、拱廊商铺、阳台窗、窄窗组合、装饰板、侧立面窗、后勤门、柱头、格栅雨棚、竖招牌、双联空调、天窗和烟囱。
- **参考纹理从颜色棋盘升级为表面语义纹理。** 每套风格仍复用 Wall/Accent/Roof/Glass/Metal 五材质，但五张纹理扩大到 128×128，并按砖墙、灰泥、玻璃、金属、屋顶和装饰表面生成不同确定性图案。
- **建立可直接运行的 Style Kit Auditor。** 审计 Role 覆盖、至少 40 个 Recipe、项目内依赖、五材质、URP/Lit、GPU Instancing、五张 128×128 纹理及 Catalog 编译确定性。
- **补全 DesignPreset 失败回滚。** Scene 保存失败时除 HDA 参数和 SHA 外，还恢复 Authoring Catalog 与 HDA Root Tag，并增加可测试的 Cook/Save seam。
- **累计合同声明补齐。** `streetbuilding_contract.json` 正式加入 Phase27 已声明的六个 ProjectOwned/DesignPreset 合同 ID。
- **VerifyFull 增加 Unity 合同入口。** StreetBuilding 完整验证在 AssetDatabase 同步导入后，通过反射调用 `StreetBuildingPhase4ContractBridge.Run`，要求返回 `PASS|6|...`。
- **HDA/HIP 保持字节级不变。** 本次是 Unity Authoring、Style Kit 和门禁闭环，不是 Houdini 生成网络变更。

必须保留的证据边界：提交中的 `Invoke-PcgRegression.ps1` 已依赖 `StreetBuildingPhase4ContractBridge`，但该 Bridge、NUnit Fixture 与 `PCGBike.Editor.Tests.asmdef` 当前仍位于未跟踪的 `Assets/PCG/Scripts/Tests/`，没有进入提交 `28`。因此当前工作区可以发现这些类型，不代表干净 Clone 能运行六项 Unity 合同；本阶段的“验收闭环”在版本完整性层面仍未真正闭合。

## 2. 证据等级

- **[提交验证]**：目标提交元数据、79 个文件、Git diff、C#、Prefab、Catalog、Texture、Scene、规范、合同与回归入口。
- **[Unity 当前现场]**：Unity MCP 读取 Editor、打开场景、AssetDatabase、Console，并通过反射执行 Style Kit Auditor。
- **[Auditor 实测]**：两套 ProjectOwned Style Kit 均通过 Role、Recipe、依赖、材质、纹理和 Catalog 编译审计。
- **[Python 单元验证]**：`test_pcg_regression_gate.py` 共 13 项通过。
- **[Git 对象验证]**：父提交与目标提交的 HDA/HIP Blob 完全相同，确认没有隐藏二进制变化。
- **[静态场景验证]**：六栋 Showcase、Catalog SHA、Design SHA、GameObject/Component/PrefabInstance 数量均从场景 YAML 读取。
- **[当前工作区可发现但非提交证据]**：六项 Unity EditMode Fixture 与反射 Bridge 当前能从未跟踪测试目录加载。
- **[未执行]**：本次文档审计没有调用会重新打开场景并触发 Houdini Cook 的六项 Bridge，也没有执行 StreetBuilding VerifyFull；避免把未提交测试代码产生的结果写成提交内自动化证据。
- **[未闭环]**：测试资产版本完整性、Runtime Bake、LOD、Collider、Chunk/Cluster、GPU Culling、Indirect Draw 和移动端真机性能。

当前工作区原有未跟踪 Terrain Shader、文档、`Assets/PCG/Scripts/Tests/` 与 ReferenceFinder；本文没有修改、移动或清理这些用户文件。

## 3. 提交概览

| 项目 | 数值 |
|---|---:|
| Commit | `ba11ba561c223952342a72f175650d696370f3ba` |
| Parent | `a28fb30a2485e979164c1845c9a459667afff3cb` |
| Author / Date | `liyuan` / 2026-08-30 19:35:13 +08:00 |
| Changed Files | 79 |
| Added / Modified / Deleted | 58 / 21 / 0 |
| Added / Deleted Lines | `+260282 / -243796` |
| 新增 Prefab | 26（每套风格 13） |
| 修改 Prefab | 2（两套 `Entrance_Metal`） |
| 新增 C# | 2（含各自 `.meta` 后共 4 个文件） |
| StreetBuilding HDA / HIP | 0 个文件修改 |
| Houdini Engine Unity 插件 | 0 个文件修改 |

按扩展名统计：

| 扩展名 | 文件数 |
|---|---:|
| `.meta` | 28 |
| `.prefab` | 28 |
| `.asset` | 12 |
| `.cs` | 4 |
| `.json` | 3 |
| `.md` / `.ps1` / `.py` / `.unity` | 各 1 |

本次行数变化主要来自 `PCG_Building.unity` 的 HDA Showcase 重建与 Unity YAML 重序列化：场景单文件产生 494323 行 diff，占全部增删行约 98%。这不应被误解为新增 50 万行手写逻辑。

关键文件当前 SHA-256：

| 文件 | Phase28 SHA-256 |
|---|---|
| `StreetBuilding.hda` | `820678EBC9A3B64745C046AFF1269901950E2B24BE9306F18673C46541F18D01` |
| `PCG_Bike_StreetBuilding.hip` | `B85B44A1F1F266ED1423E42F4EF7081077E3CE31073B3FEC7150B8715E78C811` |
| `PCG_Building.unity` | `5959103E2510EB7A6396E3F014E78BECBE7BBD7E0B7C61F2B8BC7A25C1456A53` |
| Brick Catalog | `FF1770A8CE4372DC681718A1BAF9E6232A1E27D5B36162DFC39E6160EB4B01E1` |
| Stucco Catalog | `F02383FB42F395E2342B7DAF2B70DB0D454B7720C5007192D62A55D00B121B86` |

父提交与目标提交的 HDA Blob 均为 `0cb6f579...c4a62`，HIP Blob 均为 `ac78022c...c811`，证明本阶段没有修改 Houdini 实现事实源。

## 4. Style Kit 从 28 扩展到 41 个模块

### 4.1 新增 Variant

Brick 与 Stucco 各新增相同的 13 个稳定 Variant：

| Role | VariantId | Prefab 后缀 | 视觉职责 |
|---|---|---|---|
| Entrance | `entrance_glass` | `Entrance_Glass` | 双玻璃门与入口 Portal |
| GroundShop | `shop_arcade` | `Shop_Arcade` | 双橱窗、中心 Pier 与 Header |
| MiddleWindow | `balcony` | `Window_Balcony` | 阳台板、栏杆与上层开窗 |
| MiddleWindow | `narrow_pair` | `Window_NarrowPair` | 双窄窗与水平装饰带 |
| MiddleBlank | `panel` | `Blank_Panel` | 凹凸墙板与顶部压条 |
| SideWall | `upper_c` | `Side_UpperC` | 侧立面窄窗变化 |
| RearWall | `service` | `Rear_Service` | 后勤门与墙灯体块 |
| FacadeColumn | `accent_capital` | `Column_Accent` | 柱身与柱头变化 |
| Awning | `slatted` | `Awning_Slatted` | 三段格栅雨棚 |
| Sign | `vertical` | `Sign_Vertical` | 支架与竖向招牌 |
| ACUnit | `twin` | `ACUnit_Twin` | 双联墙面空调 |
| RoofProp | `skylight` | `Roof_Skylight` | 基座与玻璃天窗 |
| RoofProp | `chimney` | `Roof_Chimney` | 烟囱体与压顶 |

现有 `Entrance_Metal` 也增加左右门框，使入口层次不再只有 Wall、Door 和 Transom。

### 4.2 Recipe 与权重

每套 Catalog 从 28 个 Recipe 增至 41 个，仍覆盖 17 个必需 Role。新 Variant 使用追加式稳定键，没有重命名既有 Role + VariantId。

典型权重：

- `entrance_glass = 0.45`；
- `shop_arcade = 0.55`；
- `balcony = 0.45`，`narrow_pair = 0.55`；
- `upper_c = 0.35`，`service = 0.30`；
- `slatted = 0.55`，`vertical = 0.45`；
- `twin = 0.40`；
- `skylight = 0.55`，`chimney = 0.40`。

原有 RoofProp `water_tank`、`roof_vent` 和 `mechanical_box` 继续保留，因此每套风格现有五种屋顶道具。新增 Variant 复用 Phase27 的确定性 Weighted Selection；相同 Catalog 与 Seed 应保持相同选择结果，Catalog 内容改变后 Payload SHA 会按设计变化。

当前 Editor Auditor 返回：

```text
PASS|2|
urban_brick_mixeduse_01:41:dc696c72b381;
urban_stucco_residential_01:41:747cc70f7da7
```

场景中保存的完整 Payload SHA：

```text
Brick  = dc696c72b381d16987b717a95d74798651237aee610717b5c800467ebd277ed3
Stucco = 747cc70f7da7fc38c516d865416628598a42eb5d5c4121f4f1a9b0d1f331a4bf
```

## 5. 128×128 确定性参考纹理

Phase27 每张参考纹理只有 4×4 Checker。本次 `EnsureMaterial` 将已有纹理重新初始化为 128×128 RGBA32，并由 `PopulateReferenceTexture` 按路径与表面语义生成像素：

| 表面 | 生成规则 |
|---|---|
| Brick Wall | 16px 行高、错缝砖块、2px 砂浆线与确定性微噪声 |
| Stucco Wall | 基色与低幅明暗噪声混合 |
| Glass | 每 32px 水平渐变 Band |
| Metal | 每 24px 接缝与轻微噪声 |
| Roof | 32px 网格接缝 |
| Accent | 32px 内嵌边线 |

噪声来自 `x`、`y` 与 `texturePath.Length` 的固定整数 Hash，不依赖 Unity 随机状态；相同路径和颜色输入会生成相同像素结果。

材质继续固定为每套五个共享 URP/Lit：Wall、Accent、Roof、Glass、Metal。BaseColor 设为白色，让纹理承载颜色；Smoothness 保持约 0.18，GPU Instancing 保持开启。

这些纹理是验证色彩、节奏与材质分层的参考资产，不是正式 PBR 贴图：没有 Normal、Mask/Metallic、AO、压缩平台设置或移动端 Mip/内存预算闭环。

## 6. StreetBuilding Style Kit Auditor

新增：

```text
Assets/PCG/Scripts/Editor/Buildings/StreetBuildingStyleKitAuditor.cs
```

菜单入口：

```text
PCG/StreetBuilding/Project Owned/Open Style Kit Auditor
PCG/StreetBuilding/Project Owned/Audit Reference Style Kits
```

Auditor 对两套风格执行：

1. Catalog 必须存在，`SchemaVersion = 2`、`SourceKind = ProjectOwned` 且 StyleId 与目录一致；
2. Catalog Validator 必须通过；
3. Recipe 数量至少 40；
4. Entrance、GroundShop、GroundWall、Cornice、MiddleWindow、MiddleBlank、SideWall、RearWall、FacadeColumn、RoofSurface、Parapet、ParapetCorner、Awning、Sign、FireEscape、ACUnit、RoofProp 共 17 个 Role 全覆盖；
5. Catalog 与 Prefab 依赖只能来自当前 Style 目录、对应材质目录、项目 Building 脚本或 Package；
6. 明确禁止引用 Downtown City MegaKit；
7. 每套必须恰好五个共享材质，全部使用 URP/Lit 并开启 Instancing；
8. 每套必须恰好五张 Texture2D，尺寸严格为 128×128；
9. 最后重新编译 Catalog 并返回 ModuleCount 与 SHA 前缀。

Auditor 注释明确把 LOD、Collider 和运行时合批排除在本阶段之外，因此它证明的是 Authoring 正确性，不是移动端运行时性能。

## 7. DesignPreset 保存失败回滚补全

`StreetBuildingDesignPresetApplier` 增加两个 Editor-only 测试 seam：

```csharp
internal static Func<HEU_HoudiniAsset, bool> RequestCook;
internal static Func<Scene, bool> SaveScene;
```

生产默认值仍调用真实 `asset.RequestCook(...)` 与 `EditorSceneManager.SaveScene`。测试可以让 SaveScene 稳定返回 false，验证 Cook 成功但保存失败的事务路径。

回滚快照从原有参数与 SHA 扩展为：

- 所有被修改的 HDA Int / Float / Bool / String 参数；
- Authoring 原 Catalog；
- 原 Payload SHA；
- 原 Design SHA；
- HDA Root 原 Tag。

失败后恢复上述状态并重新 Cook，错误消息区分“参数已恢复、场景未保存”和“回滚 Cook 也失败”。`ResetTestHooks` 在测试结束后恢复生产默认委托，避免测试 seam 污染后续 Editor 操作。

此修复关闭了 Phase27 中 Catalog 与 Tag 未纳入回滚的缺口，但提交内缺少实际 Fixture 文件，Clean Clone 仍不能独立证明该路径。

## 8. 累计合同与 VerifyFull

### 8.1 六个合同 ID 正式入表

`streetbuilding_contract.json` 新增：

```text
StreetBuilding.ArtAuthoring.ProjectOwnedStyleCoverage
StreetBuilding.ArtAuthoring.DesignPresetSchema
StreetBuilding.ArtAuthoring.PresetDeterminism
StreetBuilding.ArtAuthoring.NoExternalAssetDependency
StreetBuilding.ArtAuthoring.DirectSaveRollback
StreetBuilding.ArtAuthoring.UnityVariationShowcase
```

新增两个 Change Manifest：

- `streetbuilding_phase4_acceptance_closure_20260830.json`；
- `streetbuilding_phase5_art_stylekit_enrichment_20260830.json`。

两者都声明 HDA 节点、连接、公共参数与输出不允许变化，并要求包含从基础接口到 V6.1 及六项 ArtAuthoring 的累计合同。

### 8.2 VerifyFull 的 Unity 合同桥

`.agents/scripts/Invoke-PcgRegression.ps1` 新增 `Invoke-StreetBuildingContractTests`：

```text
reflection-method-call
    -> PCGBike.Tests.Editor.Buildings.StreetBuildingPhase4ContractBridge.Run()
    -> 要求返回 PASS|6|...
```

StreetBuilding VerifyFull 的顺序变为：

```text
Houdini VerifyFast
    -> Persist
    -> Fresh StreetBuilding Validator
    -> AssetDatabase ForceSynchronousImport
    -> Unity Ready / Asset-only 检查
    -> 六项 Unity ArtAuthoring 合同
    -> 再次等待 Unity Ready
    -> 比较本次操作时间窗内的新诊断
```

旧流程在 VerifyFast 与 Persist 前额外调用 `build_streetbuilding_contract.py --save false`；提交 28 移除了这两次 Builder 调用，避免验证入口在比较/持久化阶段重新构造 StreetBuilding 网络。Fresh Validator 仍在 Persist 后执行。

Python 门禁新增两项测试：

- 六个 Phase4 合同 ID 必须累计存在；
- VerifyFull 脚本必须引用合同函数、Bridge 与 `reflection-method-call`。

这两项是结构测试，只证明 JSON/PowerShell 中存在入口，不执行六个 Unity 行为合同。

## 9. 版本完整性缺口：测试桥未提交

Manifest 把 `Assets/PCG/Scripts/Tests/*` 列入允许修改文件，但目标提交的 79 个文件中没有任何该目录文件。当前工作区存在以下未跟踪文件：

```text
Assets/PCG/Scripts/Tests/Editor/PCGBike.Editor.Tests.asmdef
Assets/PCG/Scripts/Tests/Editor/Buildings/StreetBuildingArtAuthoringEditModeTests.cs
Assets/PCG/Scripts/Tests/Editor/Buildings/StreetBuildingPhase4ContractBridge.cs
及对应 .meta
```

Bridge 预期执行六项测试：

1. ProjectOwned Style Kit Role Coverage；
2. DesignPreset Schema；
3. Preset Determinism；
4. No External Asset Dependency；
5. Direct Save Failure Rollback；
6. Exactly Six Saved Showcase Buildings。

当前 Unity 会话因为磁盘上存在未跟踪目录，可以加载 Bridge；但团队成员、CI 或新工作树只检出提交 `28` 时将缺少测试程序集与类型，`reflection-method-call` 无法找到目标，VerifyFull 会失败。

因此 Phase28 的准确状态是：**合同 ID、生产 seam 和门禁调用入口已提交；实际 Unity 合同实现尚未纳入版本管理。** 修复方式应是确认这些测试属于正式交付后连同 `.asmdef` 和 `.meta` 一并提交，而不是在回归脚本中降低或跳过测试要求。

## 10. Unity Showcase 与场景变化

Builder 不再在检测到六栋 Showcase 完整时直接 Skip，而是删除旧 Showcase、按新 Catalog 重建六栋建筑、重新 Cook 并保存场景。这样可确保新增 Variant 和新 Payload SHA 真正写入场景。

当前场景：

- `PCG_Building` 已加载、有效、未 Dirty；
- Root Count `15`，Build Index `-1`；
- 六个 ProjectOwned Building 与一个 `Phase4_ProjectOwned_Showcase` 标记各存在且仅存在一次；
- 共 9 个 `StreetBuildingAuthoring`；
- Brick 三栋共用 Payload SHA `dc696c72...27ed3`；
- Stucco 三栋共用 Payload SHA `747cc70f...31a4bf`；
- 六栋保存了各自独立 Design SHA。

静态 YAML 统计：

| 项目 | Phase27 | Phase28 | 变化 |
|---|---:|---:|---:|
| GameObject | 1642 | 1649 | +7 |
| Transform | 1642 | 1649 | +7 |
| MonoBehaviour | 402 | 442 | +40 |
| PrefabInstance | 1604 | 1611 | +7 |
| Scene Bytes | 8481053 | 8686198 | +205145 |

这些数字反映 Editor HDA 展示场景的序列化结果，不代表 Runtime Bake 后的对象数量或 DrawCall。

## 11. 验证记录

### 11.1 Python 门禁单元测试

执行：

```powershell
python HoudiniProject/PCG_Track_21.0.440/scripts/tests/test_pcg_regression_gate.py
```

结果：

```text
Ran 13 tests in 0.005s
OK
```

相对 Phase27 的 11 项，新增两项合同 ID 与 VerifyFull 入口结构测试。

### 11.2 Unity Style Kit Auditor

通过 Unity MCP 先查找 `StreetBuildingStyleKitAuditor.AuditProjectOwnedStyles` 的精确反射签名，再在主线程调用。结果：

```text
PASS|2|urban_brick_mixeduse_01:41:dc696c72b381;
urban_stucco_residential_01:41:747cc70f7da7
```

这证明当前磁盘资产满足 Auditor 的 17 Role、41 Recipe、项目内依赖、五材质、URP/Lit、Instancing、五张 128×128 纹理与 Catalog 编译要求。

### 11.3 Unity 当前现场

- Unity `2022.3.62f2`；
- 未播放、未暂停、未编译、未刷新；
- `PCG_Building.unity` 已加载、有效、未 Dirty；
- AssetDatabase 分别找到 Brick 41 个 Prefab、Stucco 41 个 Prefab；
- 最近 10 分钟 Error / Exception / Warning 均为 0。

### 11.4 未执行项

- 没有运行完整 StreetBuilding VerifyFull；
- 没有调用未跟踪 Bridge 的六项 Unity Contract；
- 没有重新 Cook 或保存场景；
- 没有重复 Phase27 的 Fresh HDA Validator，因为 Git Blob 已证明本提交没有修改 HDA/HIP；
- 没有运行移动端 Build、Frame Debugger、RenderDoc 或真机 Profiling。

## 12. 移动端性能与渲染边界

### 12.1 本阶段没有新增渲染管线复杂度

- 没有新增 Shader；
- 没有新增 RendererFeature 或 RenderPass；
- 没有新增 RenderTexture、Blit 或 MRT；
- 没有新增项目自定义 Keyword；
- 没有改变 HDA 输出合同或 Runtime 渲染路径。

Shader Variant 风险仍来自 URP/Lit 自带 Variant 和 GPU Instancing 基础 Variant；本提交没有形成新的 A×B×C 自定义组合。

### 12.2 资产侧已有约束

- 每套只使用五个共享材质；
- 单模块最多 3 个不同材质，由 Catalog Validator/Auditor 约束；
- 材质统一 URP/Lit 并开启 GPU Instancing；
- Prefab 根只有 Transform，可见子对象只含 Transform、MeshFilter、MeshRenderer；
- 不带 Collider、脚本、Light、Animator 或 LODGroup；
- 纹理固定 128×128，适合作为低成本参考图案。

### 12.3 仍不等于移动端 Runtime 方案

- 82 个项目自有 Prefab 仍由多个 Cube 子 MeshRenderer 组合，直接运行会产生大量 GameObject、Renderer 和提交开销；
- GPU Instancing 开关不等于实际命中 Instanced Draw，更不等于 DrawMeshInstancedIndirect；
- 没有 Chunk/Cluster、Compute Culling、GPU LOD 或间接绘制；
- 没有 Runtime Bake，把 Editor HDA 输出转成 Unity 原生合批数据；
- 参考纹理没有平台压缩、Mip、采样带宽和显存审计；
- 没有 Mali、Adreno、Apple GPU 数据。

CPU 与 GPU 分工仍应保持：Houdini/Editor 负责生成和 Bake，移动端只消费 Bake 资产；城市级建筑应按 Chunk 组织并在 GPU 侧完成可见性和 LOD，禁止运行时 CPU 遍历大量建筑模块。

## 13. 状态矩阵

| 功能 | 状态 | 当前结论 |
|---|---|---|
| StreetBuilding V6.1 HDA | 已完成且本提交未改 | HDA/HIP Blob 与 Phase27 相同 |
| Catalog V2 | 已完成 | 两套 ProjectOwned Catalog 各 41 Recipe |
| Rich Style Variant | 已完成参考实现 | 每套新增 13 个稳定 Variant，仍非最终美术 |
| 128×128 参考纹理 | 已完成参考实现 | 五种表面语义、确定性生成 |
| Style Kit Auditor | 已完成 | 当前两套 Style 实测 PASS |
| DesignPreset Save Rollback | 生产代码已补全 | Catalog/SHA/Tag/参数均进入恢复路径 |
| 六个合同 ID | 已写入累计合同 | JSON 与 Python 结构测试通过 |
| VerifyFull 反射入口 | 已实现 | 要求 `PASS|6|...` |
| 六项 Unity 合同实现 | 未纳入提交 | 当前只存在于未跟踪 Tests 目录 |
| 六栋 Showcase | 已保存并复验 | 场景未 Dirty，Payload/Design SHA 已更新 |
| Runtime Bake | 未实现 | 仍为 Editor HDA 验证场景 |
| GPU Driven 建筑渲染 | 未实现 | 无 Indirect Draw/Culling/LOD |
| 移动端真机性能 | 未执行 | 无 Android/iOS 数据 |

## 14. 后续优先级

1. 将 `Assets/PCG/Scripts/Tests/` 中的 `.asmdef`、Fixture、Bridge 和全部 `.meta` 正式纳入版本管理，在干净工作树验证类型可发现；
2. 从干净 Clone 执行 StreetBuilding Capture、VerifyFast、VerifyFull，确认六项 Bridge 返回 `PASS|6|...` 且无新 Unity/Houdini 诊断；
3. 为回归脚本增加“Bridge 类型不存在”的明确错误，以及 Test Assembly 是否为 tracked file 的预检；
4. 控制场景重序列化噪声，区分 Builder 真实生成差异与 Unity YAML 顺序变化，避免大型二进制式 Review；
5. 将 Style Kit Auditor 扩展到 Renderer 数、材质槽、Mesh 顶点/三角形、透明面积和纹理导入设置，但保持 Authoring 与 Runtime 性能审计分层；
6. 设计 StreetBuilding Runtime Bake 与 Chunk 数据结构，再接入 GPU Culling、LOD 和 Indirect Draw；
7. 用正式 FBX/PBR 资产逐个替换 Cube 参考 Prefab，保持 Role + VariantId、Pivot、尺寸与 Catalog V2 合同稳定；
8. 在 Mali、Adreno 和 Apple GPU 上建立 DrawCall、SetPass、Overdraw、显存、带宽和帧耗基线。

## 15. 总结

Phase28 的核心价值是把 StreetBuilding ProjectOwned Authoring 从“有两套可生成灰盒风格”推进到“每套具有 41 个稳定模块、128×128 表面语义纹理、独立 Auditor，并在回归入口中声明六项 Unity 行为合同”。同时，DesignPreset 保存失败的事务恢复范围补齐到 Catalog、SHA、Tag 和 HDA 参数。

但版本审计发现一个必须优先处理的问题：六项行为合同的 NUnit Fixture 与反射 Bridge 没有包含在提交 28 中。当前工作区可运行不代表提交可复现。因而本阶段可以确认 Style Kit 资产丰富化、Auditor 和生产回滚代码已经交付，不能确认 Clean Clone 的 VerifyFull 验收闭环已经完成。正式进入 Runtime Bake 或移动端 GPU Driven 阶段前，应先补齐测试版本完整性并完成一次干净环境累计回归。
