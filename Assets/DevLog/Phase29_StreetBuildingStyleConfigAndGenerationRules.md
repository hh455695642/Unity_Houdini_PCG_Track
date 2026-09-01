# Phase 29 开发日志：StreetBuilding StyleConfig、生成规则与 L 形建筑升级

> 文档类型：Git 提交增量审计与离线累计复验  
> 记录日期：2026-09-01  
> 版本文件：`Phase29_StreetBuildingStyleConfigAndGenerationRules.md`  
> 目标提交：`74ba4d2d8249bf698c1bc9e3cc7eec672692a35d`（提交信息：`29`）  
> 直接父提交：`60cec6bf2badc1a9090d0733d99abff52eb24795`  
> StreetBuilding HDA：`Assets/PCG/HDA/City/StreetBuilding.hda`  
> StreetBuilding HIP：`HoudiniProject/PCG_Track_21.0.440/PCG_Bike_StreetBuilding.hip`  
> Unity 场景：`Assets/PCG/Scenes/PCG_Building.unity`

## 1. 日志范围与阶段结论

本文只记录 Git 提交 `74ba4d2d` 相对直接父提交 `60cec6bf` 的开发增量。提交 29 是一次 StreetBuilding 大型架构升级，提交内部连续包含 V7、V8、V9 三层演进，最终合同锁定为：

```text
StreetBuilding.StyleConfig.9.0
    -> SBV4：只描述风格与 Prefab 模块
    -> SBR1：只描述体块、立面和附件生成规则
    -> HDA V9：解析两类 Payload 并完成容量分配与确定性选择
```

本阶段的主要开发结果：

- **风格与生成参数正式解耦。** 新增 `StreetBuildingStyleConfig`、`StreetBuildingStyleLibrary` 和 `StreetBuildingGenerationPreset`；旧 `StreetBuildingDesignPreset` 只保留为继承兼容壳，旧 Catalog/MegaKit Adapter/Pipeline 从正式工作流移除。
- **新增矩形与等高 L 形体块。** 支持后左、后右缺口，网格校验要求缺口尺寸对齐 Cell，并保留至少两格宽的两条建筑翼。
- **补齐 L 形阴角和墙面附件语义。** 新增 `CornerConcave`、`ParapetConcaveCorner`，修正阳角/阴角拓扑朝向；墙面 AC 按支撑面与立面 Cell 约束，避免落入 L 形缺口。
- **立面生成从比例参数升级为语义容量系统。** 新增 Auto、RandomRange、Manual 三种控制模式，支持按立面和楼层覆盖 Entrance、ShopDoor、Shopfront、Window、Blank 数量，并按功能优先级压缩超额需求。
- **附件按五组独立规则生成。** Awning、Sign、FireEscape、WallAC、RoofProps 分别拥有密度、最大数量、立面掩码和楼层范围，全栋总预算仍限制为 64。
- **两套 ProjectOwned 风格迁移到 Schema 4。** Brick 与 Stucco 各有 42 个模块定义，并由轻量 StyleLibrary 做基于 `BuildingId + Seed + UsageTag` 的稳定加权选择。
- **外壳资产转为单面 Mesh 基线。** 新增 XY/XZ/YZ 三个共享 UnitPlane，大量项目自有 Prefab 改为引用单面开放 Mesh；材质继续要求 URP/Lit、GPU Instancing、Cull Back、关闭 Double Sided GI。
- **六栋 Showcase 重新 Cook 并保存。** 最终保存为 2 栋矩形和 4 栋左右 L 形组合，六栋均引用 StyleConfig、StyleLibrary 与迁移后的 GenerationPreset。
- **累计合同升级到 V9。** HDA 新增五个职责明确的规则节点，Fresh Validator 实测通过 V1、V2、V6.1、V7、V8、V9 兼容与行为合同。

## 2. 证据等级与边界

- **[提交验证]**：提交元数据、父子 diff、167 条原始文件状态记录、C#、资产、Prefab、Scene、HDA/HIP、合同、Patch 与回归脚本。
- **[Fresh HDA 验证]**：使用 Houdini 21.0.440 `hython` 从当前 `StreetBuilding.hda` 新建锁定验证实例并执行累计合同，结果 `PASS`。
- **[Python 单元验证]**：`test_pcg_regression_gate.py` 13 项通过。
- **[Preflight 验证]**：18811 RPC、3055 health 与 Houdini 21.0.440 进程可用；Codex 工具发现为 43 项。
- **[静态 Unity 证据]**：StyleConfig、GenerationPreset、StyleLibrary、Prefab 与 `PCG_Building.unity` 的序列化内容及 SHA 均从当前磁盘读取。
- **[历史保存证据]**：场景中的九个 `StreetBuildingAuthoring` 均保存了 `Cook PASS: SUCCESS`；这是提交保存结果，不等于本轮重新 Cook。
- **[当前工作区可发现但非提交证据]**：V9 的七项 Unity Bridge 测试存在于未跟踪的 `Assets/PCG/Scripts/Tests/`。
- **[待复验]**：本轮 Unity MCP 服务未启动，无法读取 Editor 状态、打开场景、AssetDatabase、Console，也无法执行 Style Kit Auditor 或七项 Bridge。
- **[待复验]**：Houdini Preflight 发现当前 Live HIP 为 `C:/Users/ruze/untitled.hip`，不是生产 `PCG_Bike_StreetBuilding.hip`，因此没有执行生产 HIP 的 Live Scene 一致性确认。
- **[未实现]**：Runtime Bake、Chunk/Cluster、GPU Culling、LOD、DrawMeshInstancedIndirect 与移动端真机性能闭环。

当前工作区原有未跟踪 Terrain Shader、三份操作手册、`Assets/PCG/Scripts/Tests/` 与 ReferenceFinder；本文没有修改、移动或清理这些用户文件。

## 3. 提交概览

| 项目 | 数值 |
|---|---:|
| Commit | `74ba4d2d8249bf698c1bc9e3cc7eec672692a35d` |
| Parent | `60cec6bf2badc1a9090d0733d99abff52eb24795` |
| Author / Date | `liyuan` / 2026-09-01 13:57:39 +08:00 |
| Git rename-aware Changed Paths | 142 |
| Raw Added / Modified / Deleted | 51 / 75 / 41，共 167 条 |
| Added / Deleted Lines | `+272959 / -239733` |
| `PCG_Building.unity` | `+265706 / -233845` |
| 新增正式 C# | 7 个 Runtime/Data + Editor 文件组中的 7 个新实现文件 |
| 删除旧 C# | 2 个：MegaKit Adapter、Module Catalog Pipeline |
| 新增 Change Manifest | 3 个：V7 / V8 / V9 |
| HDA / HIP | 各修改 1 个二进制文件 |
| Houdini Engine Unity 插件 | 0 个文件修改 |

Git 在启用 rename detection 时把多组目录迁移识别为重命名，因此显示 142 个 changed paths；禁用重命名检测后为 51 Added、75 Modified、41 Deleted。场景单文件占文本增删约 97%，主要来自六栋 HDA Showcase 重建与 Unity YAML 重序列化，不代表新增约 50 万行手写逻辑。

关键文件当前 SHA-256：

| 文件 | Phase29 SHA-256 |
|---|---|
| `StreetBuilding.hda` | `3E70D094F0367A7A9151D77C8E613D1186FA41B29D56C33FC6C1EBB91B055D1B` |
| `PCG_Bike_StreetBuilding.hip` | `277C049F5B1BDBFE3EAC95ECE7ABEFCC733C4DD92CDBD1BDD194D62BD7D8A7D7` |
| `PCG_Building.unity` | `FC142A46821E635FC012107A0126BABC408D4AD1F14D5413C0DDD0A1B66278E5` |
| Brick StyleConfig | `11B34F819F7CE7E40E70D9C8B0506B47117F8E62F3ED155C736B50D6B8920121` |
| Stucco StyleConfig | `0073F6E522C705D28C33261DE9682EF78C403BDEA3EEB885BC2B6241391075D5` |

## 4. 最终 Authoring 架构：SBV4 与 SBR1

### 4.1 StreetBuildingStyleConfig：美术唯一事实源

`StreetBuildingStyleConfig` 的 `CurrentSchemaVersion = 4`。每个 StyleConfig 只保存：

- `StyleId`、显示名、Cell 宽度、首层/标准层高度；
- 允许引用的项目资产根目录；
- GroundFacade、UpperFacade、SideRear、ConvexConcaveCorner、ColumnTrimCornice、RoofParapet、Attachments 七个模块组；
- 每个模块的一份 Prefab、稳定 VariantId、Role、宽/深 Span、高度类型、权重、启用状态、立面掩码和楼层掩码。

复合几何在 Prefab 内组织，不再由 Catalog Recipe 保存多 Part 组合。编译结果使用稳定排序与 Invariant Culture：

```text
SBV4|StyleId|CellWidth|GroundFloorHeight|TypicalFloorHeight
M|Group|Role|VariantId|PrefabPath|WidthSpan|DepthSpan|HeightType|ResolvedHeight|
  Weight|AllowedFacades|AllowedFloors|BoundsSizeXYZ|BoundsMinXYZ
```

Payload 全文参与 SHA-256。修改 Prefab 路径、尺寸、权重、适用立面/楼层或 Bounds 都会改变 Style SHA。

Validator 约束：

- SchemaVersion 必须为 4，StyleId/VariantId 必须是稳定小写 snake_case；
- Prefab 必须位于 AllowedAssetRoots，根 Transform 必须归零；
- 可见节点只允许 Transform、MeshFilter、MeshRenderer，不允许 Missing Script 或运行时行为组件；
- Bounds 不得超出声明网格跨度，非附件模块 Pivot 必须贴放置平面；
- 材质必须是 URP/Lit 并开启 GPU Instancing；
- 单模块超过 3 个不同材质时报告 Warning，而非静默忽略；
- Entrance、GroundWall、MiddleWindow、MiddleBlank、SideWall、RearWall、Cornice、RoofSurface、Parapet 为必需 Role；专用阳角/阴角缺失时允许语义 fallback，但报告 Warning。

### 4.2 StreetBuildingGenerationPreset：与风格无关的生成规则

`StreetBuildingGenerationPreset` 不保存 Style 或 Prefab 引用，只保存：

- Width、Depth、Rectangle/LShape、NotchWidth/Depth/Side；
- Floors、CornerBuilding、GroundUse；
- FacadeControlMode、FacadeRhythm、ShopfrontRatio、Side/RearMode；
- Roof、Parapet、Trim、Attachments、DetailDensity、BaseSeed；
- 按立面与楼层的语义数量覆盖；
- 五类附件的密度、最大数量、立面与楼层范围。

编译输出为：

```text
SBR1
G|...                  # 全局体块与生成规则
O|Facade|FloorRange|... # 立面/楼层覆盖，稳定排序
A|Kind|Density|Max|...  # 附件规则，按 Kind 稳定排序
```

相同 Preset 与 VariationSeed 产生相同 SHA；更换 StyleConfig 不改变 SBR1 Payload。旧六个 `StreetBuildingDesignPreset` 资产保留 GUID，并通过继承兼容壳迁移到 `GenerationPresets/`，避免场景引用丢失。

### 4.3 StyleLibrary 与确定性风格选择

`StreetBuildingStyleLibrary` 只持有 StyleConfig、权重、Enabled 和 UsageTags。候选项先按 StyleId 排序，再用 FNV-1a 对：

```text
BuildingId | VariationSeed | UsageTag
```

生成稳定采样值并执行加权选择。每个 Style 仍是独立资产，避免巨型 ScriptableObject 导致无关风格一起 Dirty。

当前 Library 包含两套正式参考风格：

| StyleId | Schema | Cell / 层高 | 模块数 |
|---|---:|---|---:|
| `urban_brick_mixeduse_01` | 4 | 2m / 4m / 3m | 42 |
| `urban_stucco_residential_01` | 4 | 2m / 4m / 3m | 42 |

## 5. HDA V7：矩形 / L 形体块与风格族过渡

提交内的 V7 改造首先扩展了 Rectangle 与 LShape：

- L 形只允许等高体块，缺口位于 rear_left 或 rear_right；
- 缺口宽/深必须是 Style Cell 的整数倍；
- 缺口后必须保留至少两个 Cell 的两条翼；
- 屋面、墙面、女儿墙沿真实 L 形 footprint 生成，不允许把矩形屋顶覆盖在缺口上；
- L 形轮廓应产生 5 个凸角和 1 个凹角；
- 左右缺口使用独立确定性选择结果；非法缺口必须拒绝 Cook。

V7 曾引入 Catalog V3 / ModuleFamily 与 StyleLibrary 兼容层；同一提交后续 V9 已把最终美术事实源收敛为 StyleConfig SBV4。Catalog V3 因而属于提交内迁移过程，不是 Phase29 最终推荐 Authoring 表面。

## 6. HDA V8：阴角拓扑、朝向与墙面 AC

V8 重点关闭 L 形几何与附件的空间错误：

- `CornerConvex` 与 `CornerConcave` 使用明确拓扑语义，不能通过负缩放镜像阳角资产伪造阴角；
- 新增 Brick / Stucco 两个 `Parapet_ConcaveCorner` Prefab；
- 阴角 Orient 与相邻两条轮廓边一致，保持单面法线朝建筑外部；
- WallAC 从通用点位选择改为墙面支撑平面语义；
- AC 必须落在有效立面 Cell 内，并排除 L 形缺口区域；
- Validator 同时检查左右缺口、阴角资产与 AC Cell containment。

Fresh Validator 对 rear_left / rear_right 分别得到 157 个点、26 个屋顶 Tile、10 段直女儿墙、5 个凸角、1 个凹角和 16 个 AC；两侧阴角资产均与阳角不同，非法缺口被拒绝。

## 7. HDA V9：语义容量分配与规则驱动生成

HDA 新增五个独立职责节点：

```text
PARSE_GENERATION_RULES
    -> BUILD_FACADE_CELLS
    -> ALLOCATE_FACADE_CAPACITY
    -> SELECT_FACADE_MODULES
    -> SELECT_ATTACHMENT_MODULES
```

职责边界：

1. 解析 SBR1 全局、覆盖和附件规则；
2. 把建筑轮廓拆为可寻址的立面/楼层 Cell；
3. 按 Entrance、ShopDoor、Shopfront、Window、Blank 的功能优先级分配容量，超额时输出压缩诊断；
4. 从 SBV4 中按 Role、FacadeMask、FloorMask、Span 与权重稳定选择模块；
5. 独立选择五类附件，不污染 LOD0 外壳选择。

新增或正式公开的参数组：

- `massing_shape`、`notch_width`、`notch_depth`、`notch_side`；
- `facade_control_mode = auto / random_range / manual`；
- Entrance、ShopDoor、Shopfront、Window、Blank 的 Min/Max；
- `facade_overrides` 多参数覆盖；
- 五组 `attachment_N_density / attachment_N_max`；
- `attachment_rules` 多参数规则。

预算保持不变：LOD0 每栋 12k 三角形、LOD1 比例 0.35、LOD2 每栋 200 三角形、每 LOD 3 材质、每栋 64 个细节实例。

## 8. Unity Authoring、编译器与事务桥

新增 Editor 工具：

- `StreetBuildingStyleCompiler`：校验并编译 SBV4；
- `StreetBuildingGenerationCompiler`：校验并编译 SBR1；
- `StreetBuildingStyleConfigEditor`：中文分组 Inspector、稳定 VariantId、缺失定位、Validate 与 Compile Preview；
- `StreetBuildingStyleLibraryWindow`：StyleLibrary 与 StyleConfig 聚合入口；
- `Create-only StyleConfig Wizard`：只创建新 StyleConfig，不覆盖 Prefab、材质、纹理、Preset 或 Scene。

`StreetBuildingAuthoring` 现在支持：

```text
Fixed StyleConfig
    或 StyleLibrary(BuildingId, UsageTag, VariationSeed)
    + optional GenerationPreset
```

`StreetBuildingDesignPresetApplier` 将 SBV4 写入 `unity_instance_catalog`，将 SBR1 写入 `unity_generation_rules`，并写入最终 `style_id` 与 HDA 可见参数。Apply 是显式 Editor 操作，不含 Update 循环，也不在移动端运行时 Cook。

事务路径：

```text
Validate Style + Rules
    -> Compile SBV4 / SBR1
    -> Snapshot HDA 参数与 Authoring 状态
    -> 写入参数并 RequestCook
    -> Cook 成功后写入 Style SHA / Design SHA / 诊断并保存 Scene
    -> 任一步失败则恢复参数和 Authoring 状态，再执行 rollback cook
```

完整 Design SHA 为 `SHA256(StyleSha + "|" + GenerationSha)`，便于区分美术风格变化和生成规则变化。

## 9. 资产迁移与单面 Mesh 策略

本提交删除：

- 旧 `StreetBuildingMegaKitInstanceAdapter`；
- 旧 `StreetBuildingModuleCatalogPipeline`；
- 两套风格原 `StreetBuildingInstanceModuleCatalog.asset`；
- 各风格内部六个旧 Preset，迁移为全局 `GenerationPresets/`；
- `NA_Brick_MixedUse_01` 验证 Catalog、验证细节与相关 Prefab。

新增 `_Shared/Meshes/`：

```text
M_SB_UnitPlane_XY.asset
M_SB_UnitPlane_XZ.asset
M_SB_UnitPlane_YZ.asset
```

大量 Brick / Stucco Prefab 改为复用上述单面 Mesh，减少外壳不可见背面和封闭厚度。约束为：立面法线朝局部 `+Z`，屋面法线朝 `+Y`，转角各片朝建筑外侧；材质必须 Cull Back，不允许双面 Shader 或负缩放修复错误法线。空调、水箱等真实体积附件仍可使用闭合 Mesh。

两套 StyleConfig 各保存 42 个 Prefab 引用，比 Phase28 的 41 个模块多出专用阴角语义。Style Kit Auditor 进一步要求：恰好 42 个定义、必需 Role 完整、项目内依赖、五个共享 URP/Lit 材质、GPU Instancing、Cull Back、关闭 Double Sided GI，以及五张 128×128 参考纹理。

## 10. GenerationPreset 与六栋 Showcase

六个资产统一迁移到：

```text
Assets/PCG/Art/StreetBuilding/GenerationPresets/
```

| Preset | 体块 | Width × Depth | Floors | BaseSeed |
|---|---|---:|---:|---:|
| Brick Mixed Compact | Rectangle | 10 × 8 | 3 | 101 |
| Brick Retail Standard | Rectangle | 12 × 10 | 4 | 131 |
| Brick Corner Tall | LShape rear_left | 16 × 12 | 5 | 173 |
| Stucco Residential Compact | LShape | 10 × 10 | 3 | 211 |
| Stucco Mixed Standard | LShape | 12 × 8 | 4 | 251 |
| Stucco Corner Tall | LShape | 16 × 10 | 5 | 293 |

每个 Preset 均保存五类 AttachmentRule。典型规则为：首层正面/次正面的 Awning 与 Sign、二层以上侧背面的 FireEscape、全立面的 WallAC，以及顶层以上的 RoofProps。最大数量总和受编译器 64 实例预算约束。

场景静态结果：

- `Phase4_ProjectOwned_Showcase` 仍包含六栋正式参考建筑；
- 三栋 Brick 使用相同 Style SHA `d1e56d39...2179a`；
- 三栋 Stucco 使用相同 Style SHA `ded41114...8442`；
- 六栋拥有各自 GenerationPreset 与独立 Design SHA；
- Scene 中另有三栋 Legacy StreetBuilding，继续固定解析到 Brick StyleConfig；
- 共保存 9 个 `StreetBuildingAuthoring` 与 `Cook PASS: SUCCESS`；
- 静态 YAML：1563 GameObject、1563 Transform、436 MonoBehaviour、1515 PrefabInstance，文件大小 9,383,696 bytes。

这些是提交保存的 Editor HDA 场景结果，不是 Runtime Bake 后的对象数、DrawCall 或移动端提交开销。

## 11. 累计合同升级

最终合同：

```text
revision         = STREETBUILDING_V9_STYLECONFIG_SBV4_RULES
contract_version = StreetBuilding.StyleConfig.9.0
asset_type       = pcgbike::StreetBuilding::1.0
```

V7 新增合同：

- RectangleAndLShapeOnly；
- LShapeConcaveCorner；
- LShapeRoofAndParapetCoverage；
- CatalogV3FamilyCompatibility；
- DeterministicFamilySelection；
- StyleLibraryIsolation；
- SingleSidedAssetPolicy；
- UnitySixBuildingShowcase。

V8 新增合同：

- CornerTopologyOrientation；
- DedicatedConcaveCornerAsset；
- ACWallSupportPlane；
- ACLShapeCellContainment。

V9 新增合同：

- SBV4StylePayload；
- GenerationModes；
- FacadeFloorOverrides；
- FunctionPriorityCompression；
- ParcelFrontageRulePayload；
- AttachmentGroups；
- RuleDeterminism；
- UnityBridgeHapiVisible。

三份 Change Manifest 分别记录 V7、V8、V9 白名单。V9 只允许新增上述五个规则节点，并要求从基础接口、V4/V5/V6/V6.1、ArtAuthoring 到 V7/V8/V9 的全部累计合同继续成立。

## 12. 验证记录

### 12.1 Houdini MCP Preflight

执行：

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .agents\scripts\Ensure-HoudiniMcp.ps1
```

结果：

- Houdini 21.0.440，RPC 18811 可连接；
- 3055 服务重新启动后 health 正常；
- Codex Houdini 协议发现 43 个工具；
- 当前 HIP 为 `C:/Users/ruze/untitled.hip`，与生产 HIP 不一致。

因此连接层通过，但生产 HIP Live Scene 不计为已验证。

### 12.2 Fresh HDA 累计验证

执行：

```powershell
& 'D:\Software\Side Effects Software\Houdini 21.0.440\bin\hython.exe' `
  HoudiniProject/PCG_Track_21.0.440/scripts/tools/validate_streetbuilding_contract.py
```

结果 `PASS`，关键数据：

| 合同组 | 实测结果 |
|---|---|
| Internal Proxy | 604 points / 151 primitives |
| V1 compatibility | 35 points / 9 unique assets |
| V2 full envelope | 163 points / 5 faces / 30 roof tiles / 14 straight parapets / 4 corners |
| V6.1 details | 28 points，五种附件 Role，预算 64，LOD0 toggle isolation 通过 |
| V7 rear_left | 157 points / 26 roof tiles / 5 convex / 1 concave / 16 AC |
| V7 rear_right | 157 points / 26 roof tiles / 5 convex / 1 concave / 16 AC |
| Invalid notch | rejected |
| V9 manual counts | blank 2 / shopfront 2 / entrance 1 / shop_door 1 |
| V9 override | third-floor windows = 2 |
| V9 determinism | 同 Seed SHA 相同，不同 Seed SHA 不同 |
| V9 attachments | ACUnit / Awning / FireEscape / RoofProp / Sign 全覆盖 |
| Parcel priority | true |
| Dimension contract | 10×8、12×10、16×12 通过；7、11、15 非网格尺寸拒绝 |

Validator 从 HDA definition 新建 `/obj/VERIFY_STREETBUILDING_V9_LOCKED` 锁定实例，证明当前 HDA 文件的累计行为；它不证明当前未匹配生产 HIP 的 Live Scene。

### 12.3 回归门禁单元测试

执行：

```powershell
python HoudiniProject/PCG_Track_21.0.440/scripts/tests/test_pcg_regression_gate.py
powershell -NoProfile -ExecutionPolicy Bypass -File .agents/scripts/Test-Ensure-HoudiniMcp.ps1
```

结果：

```text
Ran 13 tests in 0.007s
OK
Ensure-HoudiniMcp.ps1 static validation passed.
```

### 12.4 Unity 当前现场

尝试调用 Editor 状态、打开场景、AssetDatabase、反射查找时，Unity MCP `localhost:29808` 返回 Connection refused。因此本轮没有执行：

- Style Kit Auditor；
- 七项 `StreetBuildingPhase4ContractBridge`；
- AssetDatabase 导入确认；
- Unity Console Error / Warning 检查；
- 场景 Dirty 状态检查；
- Unity 侧重新 Cook 与保存。

这些项目保持 **[待复验]**，不能用场景中的历史 `Cook PASS` 替代。

## 13. 版本完整性与文档一致性风险

### 13.1 Unity Bridge 测试仍未纳入 Git

`Invoke-PcgRegression.ps1` 当前要求反射调用：

```text
PCGBike.Tests.Editor.Buildings.StreetBuildingPhase4ContractBridge.Run()
    -> 返回 PASS|7|...
```

但 `git ls-files Assets/PCG/Scripts/Tests/**` 仍为空。当前工作区未跟踪目录中确实存在更新后的 Fixture、Bridge、asmdef 和 `.meta`，包含：

1. 两套 StyleConfig 各 42 模块并通过校验；
2. SBV4 稳定排序与原 Prefab 路径；
3. StyleLibrary 确定性解析且不再持有 Catalog；
4. 六个 GenerationPreset 无 Style 依赖；
5. SBR1 与 Style 无关且 Seed 确定；
6. 场景正式 Style 解析及三栋 Legacy 兼容；
7. 两套正式 Style 通过 Auditor。

Clean Clone 只检出提交 `29` 时没有 Bridge 类型，StreetBuilding VerifyFull 会在 Unity 反射阶段失败。准确结论是：**生产代码、回归入口和测试意图已更新，但 Unity 测试实现仍未形成可复现的版本闭环。**

### 13.2 美术规范仍停留在 Catalog V3 叙述

本提交修改的 `StreetBuildingArtAssetSpecification.md` 标题和流程仍以 “V7 / Catalog V3 / ModuleFamily” 为主，提交最终实现则已经收敛为 StyleConfig Schema 4 与 SBV4，并删除旧 Catalog Pipeline。该规范同时还引用已不存在的旧 Builder 菜单与 Catalog Authoring 步骤。

因此规范可用于单面 Mesh、L 形轮廓、Pivot、法线和移动端材质约束，但 Style 数据结构与操作流程部分已过期，应在后续提交改写为 StyleConfig / StyleLibrary / GenerationPreset / SBV4 / SBR1。

## 14. 移动端性能与渲染边界

### 14.1 本阶段的正向约束

- 外壳改用单面开放 Mesh，减少不可见背面几何与无效片元；
- 材质统一 URP/Lit、Cull Back、关闭 Double Sided GI、开启 GPU Instancing；
- 单模块推荐不超过 3 个材质，超出由 Validator 报告；
- 附件每栋上限 64，避免细节密度失控；
- 立面与附件选择在 Houdini/Editor 阶段完成，移动端不依赖运行时 Cook；
- 本提交没有新增 Shader、RendererFeature、RenderPass、RenderTexture、Blit、MRT 或自定义 Keyword。

Shader Variant 风险仍主要来自 URP/Lit 内建 Variant 与 Instancing 基础 Variant，本提交没有形成新的自定义 Keyword 组合爆炸。

### 14.2 尚未形成 GPU Driven Runtime

- 当前 Showcase 是 Editor HDA 输出，仍包含大量 GameObject、PrefabInstance 与 Renderer；
- `enableInstancing = true` 只表示材质具备 Instancing 条件，不证明实际合批命中；
- 没有 Runtime Bake、Chunk/Cluster、Compute Culling、GPU LOD 或 Indirect Draw；
- 没有 Frame Debugger、RenderDoc、Android/iOS 真机 DrawCall、SetPass、Overdraw、带宽或显存数据。

CPU / GPU 分工仍应保持：Houdini 与 Unity Editor 负责规则求解和 Bake；移动端只消费 Bake 后的原生 Mesh/Material/实例数据。城市级建筑渲染应按 Chunk 组织并走 GPU 可见性与 LOD，不允许 CPU 每帧遍历模块。

## 15. 状态矩阵

| 功能 | 状态 | 结论 |
|---|---|---|
| StyleConfig Schema 4 | 已实现 | 两套正式风格，各 42 模块 |
| SBV4 编译器 | 已实现 | 稳定排序、Bounds/材质/依赖校验、SHA-256 |
| GenerationPreset / SBR1 | 已实现 | 风格解耦、覆盖与附件规则、确定性 SHA |
| StyleLibrary | 已实现 | BuildingId + Seed + UsageTag 稳定加权选择 |
| Rectangle / LShape | Fresh HDA 已验证 | 左右缺口、非法缺口拒绝 |
| 阴角拓扑与专用资产 | Fresh HDA 已验证 | 5 凸角 + 1 凹角，资产区分通过 |
| AC 支撑面与 Cell containment | Fresh HDA 已验证 | 左右 L 形各 16 个 AC，未进入缺口 |
| V9 立面容量分配 | Fresh HDA 已验证 | Manual、Override、压缩、Seed 规则通过 |
| 六栋 Showcase | 已保存，当前现场待复验 | 2 Rectangle + 4 LShape，历史 Cook PASS |
| Unity Style Kit Auditor | 本轮待复验 | Unity MCP 未启动 |
| Unity Bridge 7 项合同 | 未形成版本闭环 | 测试文件仍未跟踪 |
| 美术规范最终架构 | 部分过期 | 仍描述 Catalog V3，需迁移到 SBV4/SBR1 |
| Runtime Bake | 未实现 | 仍是 Editor HDA 验证资产 |
| GPU Driven 建筑渲染 | 未实现 | 无 Chunk/Culling/LOD/Indirect Draw |
| 移动端真机性能 | 未执行 | 无 Mali / Adreno / Apple GPU 数据 |

## 16. 后续优先级

1. 将 `Assets/PCG/Scripts/Tests/` 的 asmdef、Fixture、Bridge 和全部 `.meta` 正式纳入版本管理，在 Clean Clone 验证 `PASS|7|...`；
2. 启动 Unity MCP，打开 `PCG_Building.unity`，执行 AssetDatabase Refresh、Style Kit Auditor、Bridge、Console 与 Scene Dirty 检查；
3. 让 Houdini 当前 HIP 对齐 `PCG_Bike_StreetBuilding.hip` 后执行 Capture / VerifyFast / VerifyFull，并确认 HDA definition 与 Live Scene 一致；
4. 把 `StreetBuildingArtAssetSpecification.md` 从 Catalog V3 / ModuleFamily 流程更新为 StyleConfig Schema 4、SBV4、SBR1 和 Create-only Wizard；
5. 清理 StyleLibrary 资产中遗留的空 `_catalog` 序列化字段，并确认重序列化不破坏 GUID 或场景引用；
6. 为 Style Validator 增加单面法线、三角形数、Renderer 数、透明面积与纹理导入设置的可量化审计；
7. 设计 StreetBuilding Runtime Bake 与 Chunk 数据格式，再接入 Compute Culling、GPU LOD 和 DrawMeshInstancedIndirect；
8. 在 Mali、Adreno、Apple GPU 上建立 DrawCall、SetPass、Overdraw、带宽、显存与帧耗基线。

## 17. 总结

Phase29 将 StreetBuilding 从 Catalog/DesignPreset 混合式 Authoring 推进为清晰的双数据链：SBV4 只负责美术风格，SBR1 只负责建筑生成规则。HDA 同步获得矩形/L 形体块、专用阴角、墙面 AC 支撑语义、立面 Cell 容量分配、楼层覆盖和五组附件规则；两套 ProjectOwned Style 迁移为各 42 个单 Prefab 模块，并通过单面 Mesh 与移动端材质约束降低无效几何和双面渲染风险。

Fresh HDA Validator 与 13 项 Python 门禁均通过，证明当前 HDA 文件的 V1 至 V9 累计合同成立。但本轮 Unity MCP 不可用、Live HIP 不是生产工程，且七项 Unity Bridge 仍只存在于未跟踪目录，因此不能把 Unity 现场和 Clean Clone VerifyFull 写成已闭环。下一阶段应优先补齐测试版本完整性、Unity/Houdini 双侧现场复验和规范文档迁移，再进入 Runtime Bake 与移动端 GPU Driven 渲染。
