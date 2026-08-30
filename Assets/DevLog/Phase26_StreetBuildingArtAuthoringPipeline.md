# Phase 26 开发日志：StreetBuilding 美术 Authoring 与确定性 Catalog 管线

> 文档类型：Git 提交增量审计与当前现场复验
> 记录日期：2026-08-28
> 版本文件：`Phase26_StreetBuildingArtAuthoringPipeline.md`
> 目标提交：`b446fb0481eefc22b328495776dcd8ba75d1092f`（提交信息：`26`）
> 直接父提交：`13e50b9767aa9205bdfaff4eed0ee23190afb0f4`（`Phase25`）
> StreetBuilding HDA：`Assets/PCG/HDA/City/StreetBuilding.hda`
> StreetBuilding HIP：`HoudiniProject/PCG_Track_21.0.440/PCG_Bike_StreetBuilding.hip`
> Unity 场景：`Assets/PCG/Scenes/PCG_Building.unity`

## 1. 日志范围与结论

本文只记录 Git 提交 `b446fb04` 相对直接父提交 `13e50b97` 的开发增量。Phase26 没有修改 StreetBuilding HDA Definition，而是在 Phase25 的 REV4.1 直接实例链路上建立可复用的美术 Authoring 层：

```text
项目自有 Prefab / 只读外部 FBX
    -> StreetBuildingInstanceModuleCatalog Schema V1
    -> Catalog Validator
    -> 确定性 Payload Compiler + SHA-256
    -> StreetBuildingAuthoring Inspector
    -> Transactional Applier
    -> 仅写 module_source / unity_instance_catalog / style_id
    -> Houdini Engine Cook（不自动保存 Scene）
    -> 失败时恢复旧参数并重新 Cook
```

提交的有效开发结果是：

- **建立正式美术资产规范。** 定义 StyleId、目录、命名、坐标、Pivot、尺寸、Prefab 组件白名单和移动端材质约束。
- **Catalog 升级为 Schema V1。** 新增显示名、来源类型、允许资源根、网格尺寸和楼层高度；模块 Part 从仅支持 FBX 扩展为 Prefab 或 Model Prefab。
- **拆出通用校验、编译与应用管线。** 校验资源结构，按稳定顺序生成 Payload 和 SHA-256，只更新三个 Catalog 传输参数，并提供失败回滚。
- **建立显式 Inspector 工作流。** 场景组件提供 `Validate Catalog`、`Compile Preview` 和 `Apply & Cook (No Auto Save)`，没有 `Update`、自动 Cook 或自动保存。
- **重构 MegaKit 适配器。** 旧的一次性参数覆盖流程改为复用通用 Applier，不再重载 HDA 或重写宽度、楼层、侧后立面、屋顶、LOD 等结构参数。
- **扩展回归门禁。** `StreetBuilding` 被加入 Change Manifest Schema；Unity-only 任务允许 HDA/HIP 均不进入白名单，但必须保持 Capture 哈希不变。
- **当前仍是 Editor Authoring 阶段。** 没有 Runtime Bake、城市级 GPU 渲染、完整建筑体、正式项目自有建筑模块或移动端真机性能结果。

## 2. 证据等级

- **[提交验证]**：目标提交元数据、20 个变更文件、Git diff、场景 YAML、Catalog、C#、美术规范、合同、Manifest 和回归门禁。
- **[Fresh HDA 验证]**：Houdini `21.0.440` 从磁盘 HDA 创建全新锁定实例，验证 Phase25 的 Direct Instance 和宽度合同；没有保存生产文件。
- **[Houdini Live 验证]**：当前生产 HIP、`/obj/StreetBuilding_DEV`、Definition 路径、锁定状态、未保存状态和 Cook 诊断均通过 MCP 读取。
- **[Unity 当前现场]**：Unity MCP 检查 Editor、打开场景、`StreetBuilding1` 组件和 AssetDatabase；没有保存或修改场景。
- **[源码验证]**：审查 Validator、Compiler、Applier、Inspector、MegaKit Adapter、Catalog 序列化迁移和门禁逻辑。
- **[声明但未形成提交内自动化证据]**：新增三个 ArtAuthoring 合同 ID，但目标提交没有包含对应 EditMode Test，也没有在 Houdini Validator 中实现这三个合同的独立断言。
- **[未闭环]**：项目自有正式建筑模块、Runtime Bake、LOD/Collider、材质与 Shader 审计、DrawCall/SetPass、包体和移动端真机数据。

当前工作区另有未跟踪 Terrain Shader、文档、`Assets/PCG/Scripts/Tests/` 和 ReferenceFinder 等用户文件；它们不属于提交 `26`，本文不把它们计入 Phase26 正式交付。

## 3. 提交概览

| 项目 | 数值 |
|---|---:|
| Commit | `b446fb0481eefc22b328495776dcd8ba75d1092f` |
| Parent | `13e50b9767aa9205bdfaff4eed0ee23190afb0f4` |
| Author / Date | `liyuan` / 2026-08-28 17:54:53 +08:00 |
| Changed Files | 20 |
| Added / Modified / Deleted | 10 / 10 / 0 |
| Added / Deleted Lines | `+2870 / -2054` |
| Houdini Engine Unity 插件 | 0 个文件修改 |
| StreetBuilding HDA | 0 个文件修改 |

关键文件指纹：

| 文件 | Phase26 SHA-256 |
|---|---|
| `PCG_Building.unity` | `9C7594C732A3B46185B51C2BB4FCFEF7CB7C59FAE608BD13D927F1E19AA2EEBA` |
| Module Catalog | `205BFE815E1E19388F75ECFD9DEA4DF0677EA2D33EE5D84AD07212665B1AD0A8` |
| StreetBuilding HIP | `0D5A8C719CC314C9FCD47D0EABA083335AEAEB94AB3042E7B9E93EE7C6018472` |
| `URP-Balanced.asset` | `8DFCB6FE5EF5487E2F8CEDE2FDA298FEE322A153102F1C90E78C302886B91BC9` |
| `URP-Performant.asset` | `D4EB06C7E83B3FC718DC1B5F1FE9E5F55453C869F721F94DA66690B9B3BDE65F` |

## 4. StreetBuilding 美术资产规范

新增：

```text
Assets/PCG/Art/StreetBuilding/StreetBuildingArtAssetSpecification.md
```

### 4.1 目录与命名

每种风格使用稳定的小写 `snake_case` StyleId，例如 `na_brick_mixeduse_01`。模型、Prefab、材质和纹理分别进入项目自有目录：

```text
Assets/PCG/Art/StreetBuilding/<StyleId>/Models/
Assets/PCG/Art/StreetBuilding/<StyleId>/Prefabs/
Assets/PCG/Materials/Buildings/<StyleId>/
Assets/PCG/Texture/StreetBuilding/<StyleId>/
```

命名统一为 `SM_SB_*`、`PF_SB_*`、`M_SB_*` 和 `T_SB_*`。文件名不编码楼层、Cell 或建筑实例号，这些身份继续由 PCG 生成数据提供。

### 4.2 资产结构合同

- 正式交付以 Prefab 为主，同时兼容裸 FBX Model Prefab。
- Prefab 根只允许 `Transform`；可见子节点只允许 `Transform`、`MeshFilter` 和 `MeshRenderer`。
- 阶段 1 禁止脚本、Collider、LODGroup、Light、Animator 和其他运行时行为。
- 根 Transform 必须是 Position `0`、Rotation `0`、Scale `1`。
- Catalog 传输层禁止旋转 Part；复合模块的旋转与组合偏移应在 Prefab 子节点内部完成。
- 当前 REV4.1 网格固定为 2m Bay、4m 首层和 3m 标准层。

### 4.3 移动端边界

- 只接受兼容 URP 的 Shader。
- 可实例材质应开启 GPU Instancing。
- 透明只用于必要玻璃区域，避免大面积透明叠层和 Overdraw。
- 单模块材质槽建议不超过 3；当前 Validator 超过预算只警告，不阻断。
- 三角形、贴图尺寸、透明面积、LOD、Collider 和 Runtime GPU 渲染仍是后续阶段。

Downtown City MegaKit 在本规范中被明确降级为只读验证源，不是项目正式资产模板。

## 5. Catalog Schema V1

`StreetBuildingInstanceModuleCatalog` 新增：

```text
SchemaVersion = 1
DisplayName
SourceKind = ProjectOwned | ExternalReadOnly
AllowedAssetRoots[]
CellWidth
GroundFloorHeight
TypicalFloorHeight
```

原有字段 `StyleId`、`SourceRoot`、`SourceSha256` 和模块 Recipe 继续保留。

Part 字段从 `_sourceFbx` 改为 `_sourceAsset`：

- 使用 `[FormerlySerializedAs("_sourceFbx")]` 保留既有 Catalog 的序列化引用；
- 新 API `SourceAsset` 同时支持 `.prefab` 和 `.fbx`；
- 旧 `SourceFbx` 属性保留为 `[Obsolete]` 兼容入口，避免一次性破坏调用方。

现有 MegaKit Catalog 被迁移为：

| 字段 | 值 |
|---|---|
| Schema | `1` |
| Display Name | `North American Brick Mixed Use 01 (MegaKit Validation)` |
| Source Kind | `ExternalReadOnly` |
| Style | `na_brick_mixeduse_01` |
| Allowed Root | `Assets/PCG/Art/Downtown City MegaKit[Standard]/Exports/FBX (Unity)` |
| Cell / Floor | `2m / 4m / 3m` |
| Recipe / Part | `8 / 9` |

## 6. Validator、Compiler 与 Applier

### 6.1 Catalog Validator

`StreetBuildingModuleCatalogValidator` 对以下内容 Fail-Closed：

- Schema 版本、DisplayName 和 StyleId 格式；
- 正数 Cell/Floor 尺寸；REV4.1 必须严格为 2m / 4m / 3m；
- 8 个 REV4.1 稳定 `Role + VariantId` 槽位；
- Module Key 唯一、Variant 合法、尺寸与权重大于零；
- 每个 Module 至少包含一个 Part；
- SourceAsset 必须是 Prefab 或 FBX，并位于 AllowedAssetRoots；
- 资产根 Transform 必须归一；Catalog Part Rotation 必须为 Identity；
- 组件只允许 Transform / MeshFilter / MeshRenderer；
- Mesh、Material 和 Shader 引用不得缺失。

材质槽大于 3 当前只产生 Warning。这适合阶段 1 美术接入，但不能代替移动端材质、三角形和 Overdraw 预算验证。

### 6.2 确定性 Compiler

Compiler 按固定 REV4.1 顺序排列已发布槽位，再按 Role 和 Variant 排列扩展项；浮点数使用 `InvariantCulture` 和 round-trip 格式。Payload 行格式保持：

```text
Role|Variant|PartIndex|AssetPath|PositionXYZ|EulerXYZ
```

编译结果同时返回：

- Payload；
- SHA-256；
- Module Count；
- Part Count。

当前场景序列化的最后应用 SHA-256 为：

```text
a8177f23deeb21b2960fd8f54edbb9088a5b269945d81ef12c7e55f580542d90
```

### 6.3 Transactional Applier

Applier 只接受 `pcgbike::StreetBuilding::1.0`，并在写入前读取旧值：

1. `module_source`；
2. `unity_instance_catalog`；
3. `style_id`。

成功路径只把 `module_source` 切到 Unity Catalog、写入 Payload 与 StyleId，然后请求 Cook。它不会修改宽度、深度、层数、层高、立面节奏、侧后立面、屋顶、LOD、附件或建筑装饰参数。

成功后仅记录 Payload SHA、标记组件和场景 Dirty，不自动保存。失败时尝试恢复三个旧参数并重新 Cook；若回滚也失败，会把第二个失败一并报告。

该回滚是 Editor 参数级事务，不是完整 Scene/HDA 快照事务。若 Houdini Engine 会话、源资产或生成层级在失败期间发生外部变化，仍需依靠 Capture/Verify 门禁和显式场景保存策略防止污染。

## 7. Inspector 与场景集成

新增 `StreetBuildingAuthoring`：

- 挂在 HDA Root；
- 保存 Catalog 引用与最后应用的 Payload SHA；
- 没有 `Update`、自动 Cook 或运行时循环；
- 修改入口位于 `UNITY_EDITOR` 条件编译区。

自定义 Inspector 提供三个显式按钮：

1. `Validate Catalog`；
2. `Compile Preview`；
3. `Apply & Cook (No Auto Save)`。

当前 `PCG_Building.unity` 的 `StreetBuilding1`：

- 保持 `EditorOnly` Tag；
- 同时包含 `HEU_HoudiniAssetRoot` 和 `StreetBuildingAuthoring`；
- Authoring 引用 `StreetBuildingInstanceModuleCatalog_NAB01`；
- 保存最后应用 SHA `a8177f23...42d90`；
- 仍保留 Phase25 的 39 个直接实例结果。

Unity 当前现场为 Unity `2022.3.62f2`，未播放、未暂停、未编译、未刷新；打开的 `PCG_Building` 有效、已加载、未 Dirty，Root Count 为 5，Build Index 仍为 `-1`。

## 8. MegaKit Adapter 重构

Phase25 Adapter 内部原有一整套私有校验、Payload 拼接、HDA Reload 和大量参数覆盖。Phase26 改为：

```text
Build Catalog
    -> 写入 Schema V1 / ExternalReadOnly / Allowed Root / 2m-4m-3m
    -> 通用 Validator

Apply
    -> 获取或添加 StreetBuildingAuthoring
    -> 绑定 Catalog
    -> 通用 Transactional Applier
    -> 实例来源与组件审计
```

被移除的 Apply 行为包括：

- 将旧 Definition 暂时切到 Internal Proxy；
- 断开旧 Module Library 输入；
- 清理旧场景对象并 Reload HDA；
- 强制覆盖 Site Source、宽度、层高、层数、用途、节奏、侧后立面、屋顶、LOD 和附件参数。

这使美术模块替换和建筑结构参数解耦，避免一次应用 Catalog 就静默重置地编已经调好的建筑参数。

## 9. 回归门禁与合同

### 9.1 Change Manifest Schema

`StreetBuilding` 被加入 `change_manifest.schema.json` 的合法 Module 枚举。

新增 Phase0 Baseline Manifest 和 Phase1 Authoring Manifest。Phase1 白名单覆盖：

- 美术规范；
- Catalog 与场景；
- Authoring、Validator、Compiler、Applier 和 Adapter；
- 测试路径；
- Contract、Schema 和 Regression Gate。

Manifest 明确禁止 HDA 节点、连接、公共参数和输出变化。

### 9.2 Unity-only VerifyFull

`pcg_regression_gate.py` 新增双文件授权规则：

- HDA Definition 与 HIP 必须同时进入白名单，或同时不进入；
- 只授权其中一个会直接失败；
- 两者都不授权时，以 Capture SHA-256 检查二进制文件没有变化；
- 哈希不变则返回 `persistence = not-required`，不调用历史 Builder 重新保存 HIP；
- 真正允许 HDA/HIP 修改的任务仍返回 `persistence = completed`。

这项改动避免 Unity-only Authoring 任务为了通过 VerifyFull 而重建或重写 Houdini 二进制文件。

### 9.3 合同覆盖缺口

`streetbuilding_contract.json` 新增三个 ID：

```text
StreetBuilding.ArtAuthoring.CatalogSchema
StreetBuilding.ArtAuthoring.DeterministicPayload
StreetBuilding.ArtAuthoring.MegaKitCompatibility
```

但提交内没有新增执行这些断言的 Unity Test 文件，Houdini `validate_streetbuilding_contract.py` 也没有读取或逐项执行这些 ArtAuthoring ID。Manifest 的 `required_contracts` 目前主要是声明与审计信息，不能单独证明 Catalog Schema、Payload 或 MegaKit 兼容性已自动化验证。

当前工作区存在未跟踪的 `StreetBuildingArtAuthoringEditModeTests.cs`，其中覆盖 Payload 稳定、Schema、Prefab 接入、非法 Style/重复键/缺失资产、非归一根/非法组件和源哈希不变。当前 Unity 现场执行结果为 6/6 PASS、0 Failed、0 Skipped；但由于测试资产不在目标提交中，本文只把结果作为当前现场旁证和待提交候选，不计为 Phase26 的可复现提交内交付。

```text
StreetBuildingArtAuthoringEditModeTests
Total 6 / Passed 6 / Failed 0 / Skipped 0
Duration 00:00:02.9805836
```

回归门禁自身的 Python 单元测试结果：

```text
Ran 11 tests in 0.006s
OK
```

## 10. Houdini 验证结果

### 10.1 Live Scene

`Ensure-HoudiniMcp.ps1` 与 Houdini MCP 确认：

- Houdini `21.0.440`；
- 当前 HIP 为 `PCG_Bike_StreetBuilding.hip`；
- 生产节点 `/obj/StreetBuilding_DEV`；
- 类型 `pcgbike::StreetBuilding::1.0`；
- Definition 指向 `Assets/PCG/HDA/City/StreetBuilding.hda`；
- 节点匹配当前 Definition，保持 Locked；
- HIP 无未保存改动；
- 扫描 43 个节点，Error 0、Warning 0。

Live HIP 当前保存的是 Internal Proxy 默认参数状态，而不是 Unity 场景中的 Catalog 实例状态：`module_source=0`、12m 宽、4 层、4.2m / 3.2m 层高、3m Bay。Unity Scene Instance 与 Houdini 生产 HIP 是两套实例状态，不能互相替代。

目标提交确实修改了 HIP 二进制，但没有修改 HDA。仅凭 Git 二进制 diff 无法说明 HIP 内部每个节点变化；当前 Live 复验只证明提交后的 HIP 干净、锁定并引用正确 Definition。

### 10.2 Fresh HDA

执行：

```powershell
& 'D:\Software\Side Effects Software\Houdini 21.0.440\bin\hython.exe' `
  'HoudiniProject/PCG_Track_21.0.440/scripts/tools/validate_streetbuilding_contract.py'
```

结果：PASS。

| 项目 | 结果 |
|---|---|
| Asset Type | `pcgbike::StreetBuilding::1.0` |
| Fresh Instance | `/obj/VERIFY_STREETBUILDING_REV4_LOCKED` |
| Definition Locked | `true` |
| Internal Proxy | 604 points / 151 prims |
| Direct Instances | 39 points / 9 unique assets |
| Direct Output SHA-256 | `41e385768526b8876699eae0990a6a51f8486044ceee835f09b7bd7a08360f19` |
| 10m / 12m | 34 / 39 points |
| 7m / 11m / 15m | rejected |

该验证证明 Phase25 的 HDA 行为没有被 Phase26 回归；它不验证 Unity Catalog Inspector 和 Applier 的 Editor 事务行为。

## 11. URP 资产序列化变化

提交修改 `URP-Balanced.asset` 和 `URP-Performant.asset`：

- Asset Version 从 9 升到 11；
- 补齐 HDR Buffer Precision、Upscaling、LOD Cross Fade、SH Eval、Shadow、Light Cookie、Lens Flare、RenderGraph 和 Shader Prefilter 等 URP 14 序列化字段；
- `m_EnableRenderGraph` 保持关闭；
- SRP Batcher 保持开启，Dynamic Batching 保持关闭；
- 没有新增 RendererFeature、RenderPass、RenderTexture、Blit、MRT、Shader Keyword 或自研 Shader。

这部分更接近 Unity 对 URP Asset 的版本迁移和字段补全，不应记为 Phase26 新渲染功能。

Unity 当前 Console 较长时间窗口仍包含 `URP-Balanced-Renderer`、`URP-Performant-Renderer` 和 `URP-HighFidelity-Renderer is missing RendererFeatures` 错误，以及 CScape 遗留脚本警告。RendererFeature 错误时间早于目标提交时间；最终 Test/Refresh 后最近 2 分钟 Error 0、Warning 0，但较长窗口并非全绿，因此不能把 Phase26 写成 Unity Console 历史缓存完整通过。RendererData 缺失 Feature 引用需要单独清理和复验。

## 12. 移动端与运行时评估

### 12.1 CPU / GPU 边界

| 阶段 | Phase26 方案 | 移动端评价 |
|---|---|---|
| Catalog 校验/编译 | Unity Editor C# | 不进入 Player 热路径 |
| HDA Cook | 显式 Editor 操作 | 符合运行时禁止 Houdini Cook 的边界 |
| 场景预览 | 39 个 EditorOnly 原始实例 | 适合 Authoring，不适合城市级运行时 |
| Runtime Bake | 未实现 | 尚不可发布 |
| GPU Instancing / Indirect / Culling | 未实现 | 城市规模仍缺核心渲染链路 |

`StreetBuildingAuthoring` 虽位于运行时程序集，但没有 Update 或自动 Cook；实际操作代码位于 Editor Inspector 和 Editor Pipeline。正式 Player 构建前仍应确认 Authoring 组件是否需要通过 Bake 后剥离，避免保留无意义场景数据。

### 12.2 Shader 与 Variant

Phase26 没有新增 Shader，因此：

- 没有新增 `multi_compile` 或 `shader_feature_local`；
- Variant 数量没有因本阶段代码直接增加；
- 没有新增全屏 Pass 或 Tile-Based GPU 带宽开销。

Validator 只检查 Shader 引用非空，没有检查 URP 兼容、GPU Instancing、透明队列、Keyword 数量或移动端 `half` 精度。正式项目自有建筑材质仍需独立 Shader/Variant 审计，建议单 Shader Variant 控制在可预期范围并避免多个高成本功能交叉组合。

## 13. 已知问题与后续验收

1. **项目自有正式模块尚未交付。** 当前唯一 Catalog 仍引用 ExternalReadOnly MegaKit；规范和 Prefab 支持只是生产接口。
2. **提交内缺 EditMode Test。** Manifest 白名单写入了测试路径，但目标提交未包含这些文件；三个 ArtAuthoring 合同尚未形成可重复的提交内自动化证据。
3. **Apply 事务不包含场景快照。** 参数回滚可降低失败污染，但仍需 Capture/Verify 和显式保存门禁。
4. **HIP 二进制变化不可文本审计。** HDA 未修改且 Live/Fresh 验证通过，但无法从 Git diff 解释 HIP 内部全部变化。
5. **Runtime Bake 缺失。** `StreetBuilding1` 和生成实例仍为 EditorOnly，移动端不能直接消费。
6. **建筑输出仍不完整。** Side、Rear、Roof、Detail、Collision、Metadata、LOD1/2 尚未交付。
7. **移动端预算只做浅层提示。** 当前只对材质槽大于 3 告警，没有 Triangles、Texture、Overdraw、Mesh/Material Count 或内存硬门禁。
8. **RendererData 仍有缺失 Feature 错误。** 必须修复丢失的 RendererFeature 引用并清空 Console 后复验，不能把 URP Asset 版本迁移视为渲染配置完成。
9. **场景未进入 Build Settings。** `PCG_Building` Build Index 仍为 `-1`。
10. **缺移动端真机验证。** 仍需 Mali、Adreno、Apple GPU 的 DrawCall、SetPass、带宽、内存、加载峰值和热量数据。

## 14. Phase26 最终状态

提交 `26` 已把 Phase25 的 StreetBuilding 直接实例原型升级为可维护的 Editor 美术 Authoring 基础：Catalog Schema V1 同时支持项目 Prefab 和只读外部 FBX，Validator/Compiler/Applier 提供稳定 Payload、SHA-256、参数级回滚和不自动保存的显式工作流；MegaKit Adapter 不再重载 HDA 或覆盖建筑结构参数，Unity-only 回归任务也不再强制重写 HDA/HIP。

本阶段可标记为：

> **StreetBuilding 阶段 1 美术 Authoring 接口、确定性 Catalog 管线与 Unity-only 回归隔离已建立；提交内 EditMode 测试、项目自有正式模块、Runtime Bake、完整建筑输出和移动端渲染闭环仍待完成。**
