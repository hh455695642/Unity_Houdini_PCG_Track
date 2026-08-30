# Phase 27 开发日志：StreetBuilding 完整建筑壳体、模块化细节与项目自有风格

> 文档类型：Git 提交增量审计与当前现场复验  
> 记录日期：2026-08-30  
> 版本文件：`Phase27_StreetBuildingFullEnvelopeAndProjectOwnedStyles.md`  
> 目标提交：`936ff4d690279490372db8ece235d8c5beffca39`（提交信息：`27`）  
> 直接父提交：`1e333771615c0d72bcbf1edd97649c374eaff5e5`（`PHASE26`）  
> StreetBuilding HDA：`Assets/PCG/HDA/City/StreetBuilding.hda`  
> StreetBuilding HIP：`HoudiniProject/PCG_Track_21.0.440/PCG_Bike_StreetBuilding.hip`  
> Unity 场景：`Assets/PCG/Scenes/PCG_Building.unity`

## 1. 日志范围与阶段结论

本文只记录 Git 提交 `936ff4d6` 相对直接父提交 `1e333771` 的开发增量。提交 27 不是单一小功能，而是 StreetBuilding 从 Phase26 的“正面 Catalog Authoring”推进到完整建筑生成与项目自有样式展示的合并阶段，包含以下连续版本：

```text
Catalog Schema V2
    -> V5 完整建筑壳体（Front / Left / Right / Rear / Roof）
    -> V6 独立模块化细节流
    -> V6.1 屋顶、女儿墙和屋顶道具对齐
    -> ProjectOwned 风格生成器
    -> DesignPreset 参数事务
    -> 六栋确定性 Unity Showcase
```

本阶段已形成的有效开发结果：

- **完整建筑外壳。** StreetBuilding 不再只输出正立面；V5 增加左右侧、后立面、屋面、连续女儿墙及转角模块，并支持 2m / 4m 模块跨度与确定性加权选型。
- **细节与主体解耦。** V6 将 Awning、Sign、FireEscape、ACUnit、RoofProp 放入独立 `OUT_DETAIL_INSTANCES`，提供开关、密度、表面合法性、稳定随机和最多 64 个实例的预算。
- **修正屋顶空间合同。** V6.1 统一 `roofY`，保证 2m × 2m 屋面覆盖、壳体顶部贴合、直线/转角女儿墙连续以及屋顶道具落地。
- **Catalog 升级到 Schema V2。** 新 Payload 携带 Style、网格与楼层高度头信息，模块行增加尺寸和权重；同时保留 Schema V1 精确兼容路径。
- **新增 DesignPreset。** 建筑尺寸、层数、用途、节奏、侧后立面模式、屋顶、女儿墙、装饰和随机种子可以由 ScriptableObject 统一应用；失败时恢复旧参数并重新 Cook。
- **新增两套项目自有风格与六栋展示。** `urban_brick_mixeduse_01` 和 `urban_stucco_residential_01` 各含 28 个 Prefab、5 个材质、5 个纹理资产、3 个 Preset 和 1 个 Catalog。
- **Inspector 保存策略发生变化。** Phase26 的 `Apply & Cook (No Auto Save)` 被替换为显式的 `Apply, Cook & Save Scene` 与 `Apply Design Preset, Cook & Save Scene`。成功会立即保存场景；失败不保存并执行参数回滚。
- **回归门禁继续扩展。** 新增 V5、V6、V6.1 和 ProjectOwned Style 的变更 Manifest，Houdini fresh-instance 累计验证覆盖 V1/V2、完整壳体、细节、屋顶与非法尺寸。

必须保留的阶段边界：两套 ProjectOwned 资产由 Unity Primitive Cube 子网格自动生成，是无外部依赖的**灰盒/参考风格包**，不是最终美术交付；提交内的累计合同目前也没有把六个 ProjectOwned/DesignPreset 合同 ID 纳入自动化断言，因此不能把“场景中已存在六栋展示”写成完整行为闭环。

## 2. 证据等级

- **[提交验证]**：目标提交元数据、228 个变更文件、Git diff、HDA/HIP、场景 YAML、C#、Catalog、Preset、Prefab、材质、纹理、合同、Manifest 和验证脚本。
- **[Fresh HDA 验证]**：Houdini `21.0.440` 从磁盘 HDA 创建全新锁定实例，验证 V1 兼容、V2 完整壳体、V6.1 细节、种子确定性、实例预算和非法尺寸拒绝；没有保存生产文件。
- **[Unity 当前现场]**：Unity MCP 检查 Editor 状态、打开场景、六个展示根对象和最近 Console；没有保存或修改场景。
- **[源码与资产静态验证]**：审查 Catalog V2、Validator、Compiler、Applier、DesignPreset、Builder、场景序列化引用及项目自有资产结构。
- **[回归门禁单元验证]**：`test_pcg_regression_gate.py` 共 11 项通过。
- **[声明但未形成提交内累计自动化证据]**：ProjectOwned Style、Preset Schema、Preset Determinism、No External Dependency、Direct Save Rollback、Unity Variation Showcase 六项在 Phase4 Manifest 中声明，但未进入当前 `streetbuilding_contract.json` 与 Houdini Validator 的累计 ID 集合。
- **[未完成 Live Houdini 节点级复验]**：Houdini MCP Preflight 已确认 RPC 与当前 HIP，3055 服务重启后健康；当前 Codex 会话没有热加载 Houdini 工具，按项目规则需重启 Codex 后才能读取 Live 节点、Cook 警告和 Definition 状态。本文不把 fresh-instance 验证冒充 Live MCP 验证。
- **[未闭环]**：最终美术模块、Runtime Bake、城市级 GPU Driven/Indirect 渲染、LOD、Collider、移动端 DrawCall/SetPass/带宽、包体与 Android/iOS 真机性能。

当前工作区另有未跟踪 Terrain Shader、文档、`Assets/PCG/Scripts/Tests/` 和 ReferenceFinder 等用户文件；它们不属于提交 `27`，本文不把它们计入 Phase27 正式交付，也未修改或清理它们。

## 3. 提交概览

| 项目 | 数值 |
|---|---:|
| Commit | `936ff4d690279490372db8ece235d8c5beffca39` |
| Parent | `1e333771615c0d72bcbf1edd97649c374eaff5e5` |
| Author / Date | `liyuan` / 2026-08-30 12:24:53 +08:00 |
| Changed Files | 228 |
| Added / Modified / Deleted | 214 / 14 / 0 |
| Added / Deleted Lines | `+302020 / -3211` |
| 新增 Prefab | 64 |
| 新增 C# | 8 |
| 新增 HDA / HIP | 0 / 0（各修改 1） |
| Houdini Engine Unity 插件 | 0 个文件修改 |

关键文件当前指纹：

| 文件 | Phase27 SHA-256 |
|---|---|
| `StreetBuilding.hda` | `820678EBC9A3B64745C046AFF1269901950E2B24BE9306F18673C46541F18D01` |
| `PCG_Bike_StreetBuilding.hip` | `B85B44A1F1F266ED1423E42F4EF7081077E3CE31073B3FEC7150B8715E78C811` |
| `PCG_Building.unity` | `6B233676B412E034EC49EF79EC97B4E08AED141D615D6AC831CEDB190FBCAFFD` |
| Brick Catalog | `80BA897FC5F796D3EA1502F6B31CB59823CE54F986F2673A682298F3EAD2B9D3` |
| Stucco Catalog | `EC302FFB8A1F6D6962F3E412294C9C223215B3B28D2E9BF057B83DEF973767BE` |

提交的主要修改面：

```text
Assets/PCG/HDA/City/StreetBuilding.hda
HoudiniProject/PCG_Track_21.0.440/PCG_Bike_StreetBuilding.hip
Assets/PCG/Scenes/PCG_Building.unity
Assets/PCG/Art/StreetBuilding/
Assets/PCG/Materials/Buildings/
Assets/PCG/Scripts/Editor/StreetBuilding/
HoudiniProject/PCG_Track_21.0.440/scripts/
.agents/scripts/Invoke-PcgRegression.ps1
```

## 4. Catalog Schema V2 与完整模块角色

### 4.1 Schema V2 Payload

`StreetBuildingInstanceModuleCatalog.CurrentSchemaVersion` 从 `1` 升为 `2`。V2 Payload 由一个头和多条模块 Part 行组成：

```text
SBV2|StyleId|CellWidth|GroundFloorHeight|TypicalFloorHeight
M|Role|Variant|PartIndex|AssetPath|PosXYZ|EulerXYZ|CellWidth|CellHeight|Weight
```

相对 V1，HDA 可以直接从 Payload 获得网格、层高、模块跨度和选型权重，而不需要由调用方隐式约定。编译继续使用稳定顺序、InvariantCulture 和确定性 SHA-256。

V1 兼容路径被显式保留：旧 Payload 仍按原格式解析，并在 fresh-instance 验证中产生与历史合同一致的 39 点、9 个资源路径和固定 SHA。枚举新角色采用 append-only 方式加入，避免旧 Catalog 的整数序列化值发生漂移。

### 4.2 新增模块角色

提交增加或正式接入以下完整建筑角色：

- `RoofSurface`：2m × 2m 屋面单元，局部顶面位于 Y=0，并向下延伸；
- `Parapet`：2m 直线女儿墙；
- `ParapetCorner`：女儿墙转角模块；
- Side / Rear 的 Ground 与 Upper 组合；
- `Awning`、`Sign`、`FireEscape`、`ACUnit` 和 `RoofProp` 细节角色。

模块跨度支持 2m 和 4m。求解器在剩余宽度允许时选择 4m 模块，否则回落到 2m；选型使用 Style、Role、Face、Cell、Floor 与 Seed 构造稳定随机键，并按 Catalog Weight 选取 Variant。

### 4.3 Validator 收紧

Catalog Validator 同时接受 Schema 1 与当前 Schema 2，并新增以下 Fail-Closed 约束：

- 模块根/Pivot 必须位于规定的放置平面；
- 屋面模块的顶面必须为 Y=0 且几何向下延伸；
- 模块宽、高不能越出声明 Cell，女儿墙转角使用独立例外范围；
- 同一女儿墙 Style 的直线与转角模块高度必须匹配；
- ProjectOwned Catalog 使用的 Shader 必须是 `Universal Render Pipeline/Lit`；
- ProjectOwned 材质必须开启 GPU Instancing；
- ProjectOwned 单模块超过 3 个不同材质直接报错；ExternalReadOnly 仍只警告。

Catalog 对 HDA 字符串参数的同步同时写入 Houdini Engine 参数 API 与序列化 `_stringValues[0]`，避免复制 HDA Root 后旧序列化字符串覆盖新 Cook Payload。

## 5. StreetBuilding V5：完整建筑壳体

V5 将原先以正立面为核心的直接实例网络扩展到五个建筑表面：

| Face Index | 表面 | 主要职责 |
|---:|---|---|
| 0 | Front | 入口、商铺、首层与上层正立面 |
| 1 | Left | 左侧 Ground / Upper 模块 |
| 2 | Right | 右侧 Ground / Upper 模块 |
| 3 | Rear | 后立面 Ground / Upper 模块 |
| 4 | Roof | 屋面、女儿墙与屋顶道具 |

新增/要求的 HDA 网络节点包括：

```text
PARSE_UNITY_INSTANCE_CATALOG
BUILD_DIRECT_SIDE_REAR_INSTANCES
BUILD_DIRECT_ROOF_INSTANCES
BUILD_DIRECT_ROOF_EDGE_INSTANCES
MERGE_DIRECT_BUILDING_INSTANCES
VALIDATE_DIRECT_BUILDING_INSTANCES
```

直接实例数据增加 `face_index`、`module_span`、`selection_seed` 和 `catalog_schema` 等属性，使朝向、表面身份、跨度与确定性来源可以在输出中审计。

侧面和后立面继续使用模式参数控制，可选择完整、简化或关闭；Corner 建筑仍由明确参数控制，不通过场景位置猜测。RoofSurface 按 2m 网格覆盖整个宽度和深度，避免只生成外围立面却留下空屋顶。

## 6. StreetBuilding V6 / V6.1：细节解耦与屋顶对齐

### 6.1 独立细节流

V6 新增：

```text
VALIDATE_DIRECT_DETAIL_INSTANCES
DETAIL_MODULE_SOURCE_SWITCH
OUT_DETAIL_INSTANCES
```

主体壳体和细节实例保持独立输出。关闭细节只应清空 `OUT_DETAIL_INSTANCES`，不能改变主体实例数量、选择 SHA 或壳体拓扑。细节选取遵循以下表面规则：

| 角色 | 合法表面/楼层 | 约束 |
|---|---|---|
| Awning | Front Ground | 排除 Entrance Cell |
| Sign | Front Ground | 排除 Entrance Cell |
| FireEscape | Rear Upper | 最多一个 |
| ACUnit | Side / Rear Upper | 禁止正立面与首层 |
| RoofProp | Roof | 离屋顶边缘至少一个 Cell |

细节受 `attachments` 总开关和 `detail_density` 控制，随机选择由稳定 Seed 驱动；单栋建筑硬预算不超过 64 个细节实例。

`RoofProp` 语义被进一步限制：`ac_unit` 不能作为屋顶道具 Variant，屋顶只接受 water_tank、roof_vent、mechanical_box 等明确语义，防止同一个资源跨表面角色混用后产生尺寸与朝向错误。

### 6.2 V6.1 屋顶对齐修复

V6.1 的合同版本为：

```text
Revision = STREETBUILDING_V6_1_ROOF_ALIGNMENT
Version  = StreetBuilding.DirectInstances.6.1
Schema   = 2
```

修复点：

- `roofY` 成为壳体、屋面、女儿墙和屋顶道具的统一基准；
- 2m × 2m RoofSurface Tile 覆盖完整 footprint；
- 墙体最高点与屋面基准贴合，避免浮空或穿插；
- 四边直线女儿墙与四角 Corner 连续闭合；
- RoofProp 以资产底部落在 `roofY`，不再使用中心点直接定位；
- 新增屋顶、女儿墙和道具 bounds 检查，越界直接使验证失败。

## 7. DesignPreset 与事务式保存

新增 `StreetBuildingDesignPreset`，将一栋建筑的设计输入收敛为 ScriptableObject：

```text
Catalog
Width / Depth / Floors
Corner
GroundUse / FacadeRhythm / ShopRatio
SideMode / RearMode
Roof / ParapetHeight / Trim / Attachments / DetailDensity
BaseSeed
```

`StreetBuildingAuthoring` 新增 DesignPreset 引用、Variation Seed 和最后应用的 Design SHA。`StreetBuildingDesignPresetApplier` 在写入前验证：

- 宽度、深度必须大于等于 4m 且严格为 2m 整倍数；
- Floors 与 DetailDensity 必须在合法范围；
- 女儿墙高度不能为负；
- 启用女儿墙时，直线与转角模块必须存在且高度匹配；
- RoofProp 与 ACUnit 的角色语义不能混用。

应用过程为参数级事务：

```text
Validate Catalog + Preset
    -> Snapshot 所有将修改的 HDA 参数与旧 SHA
    -> 写入 Catalog、尺寸、楼层、用途、节奏、侧后模式、屋顶、细节和 Seed
    -> 强制 generate_lods = false
    -> RequestCook
    -> 计算 Design SHA
    -> 保持 EditorOnly
    -> 立即保存 Scene

任何失败
    -> 恢复参数与 SHA
    -> 重新 Cook
    -> 不保存 Scene
```

这里与 Phase26 有关键行为差异：成功路径不再只标记 Dirty，而是立即保存场景。该行为适合批量建立确定性展示，但也扩大了误操作影响面；后续应把“保存前验证生成结果”和“场景是否允许被当前任务写入”纳入提交内 EditMode Test 与 Change Manifest 自动门禁。

## 8. ProjectOwned 风格包

### 8.1 资产组成

提交新增两套项目自有、无第三方运行时依赖的风格：

| StyleId | Prefab | URP/Lit 材质 | Texture `.asset` | Preset | Catalog |
|---|---:|---:|---:|---:|---:|
| `urban_brick_mixeduse_01` | 28 | 5 | 5 | 3 | 1 |
| `urban_stucco_residential_01` | 28 | 5 | 5 | 3 | 1 |

每套风格覆盖 Entrance、Shop、GroundWall、Cornice、Window、Blank、Side、Rear、Column、RoofSurface、Parapet、ParapetCorner、Awning、Sign、FireEscape、ACUnit 和三种 RoofProp。Window 包含 4m `curved_double` 组合模块，用于验证混合跨度求解。

材质位于：

```text
Assets/PCG/Materials/Buildings/urban_brick_mixeduse_01/
Assets/PCG/Materials/Buildings/urban_stucco_residential_01/
```

每套包含 Wall、Roof、Metal、Glass、Accent 五个 URP/Lit 材质，开启 GPU Instancing，Smoothness 为低成本的约 `0.18`。纹理是 Builder 生成的 4 × 4 Checker `Texture2D .asset`，用于验证完全项目自有的引用链。

### 8.2 Builder 实现边界

`StreetBuildingProjectOwnedStyleBuilder` 使用 Unity Primitive Cube 子节点组合 Prefab：

- Prefab 根只保留 Transform；
- 自动移除 Collider；
- MeshFilter / MeshRenderer 位于可见子节点；
- 构建 Catalog、纹理、材质和 Preset；
- Showcase 菜单按根对象名去重，可重复执行；
- 不依赖 Downtown City MegaKit 或其他第三方源资产。

这些 Prefab 的目的，是验证角色覆盖、Pivot、Bounds、Catalog V2、无外部依赖和六套变体工作流。它们没有最终建模、LOD、碰撞、贴图分辨率分级或移动端美术预算，不能替代正式建筑资产生产。

## 9. 六栋确定性 Showcase

`PCG_Building.unity` 新增 `Phase4_ProjectOwned_Showcase` 标记和六栋 HDA 根：

| GameObject / Preset | Style | 尺寸 | 楼层 | 用途 / 节奏 | Detail | Seed |
|---|---|---:|---:|---|---:|---:|
| `Brick_Mixed_Compact` | Brick | 10 × 8 | 3 | Mixed / Uniform | 0.35 | 101 |
| `Brick_Retail_Standard` | Brick | 12 × 10 | 4 | Retail / CenterAccent | 0.65 | 131 |
| `Brick_Corner_Tall` | Brick | 16 × 12 | 5 | Mixed / Alternating | 0.85 | 173 |
| `Stucco_Residential_Compact` | Stucco | 10 × 10 | 3 | Residential / Uniform | 0.30 | 211 |
| `Stucco_Mixed_Standard` | Stucco | 12 × 8 | 4 | Mixed / Paired | 0.55 | 251 |
| `Stucco_Corner_Tall` | Stucco | 16 × 10 | 5 | Residential / CenterAccent | 0.80 | 293 |

六栋建筑均启用 Side、完整 Rear、Roof、Trim 和 Attachments，女儿墙高度为 0.6m。场景序列化中六个 Root 均带 Catalog/Preset 引用和独立 Design SHA；Brick 与 Stucco 分别使用各自稳定 Catalog Payload SHA。

Unity MCP 当前现场验证：

- Unity `2022.3.62f2`，未播放、未暂停、未编译、未更新；
- `PCG_Building` 已加载、有效、未 Dirty；
- Root Count 为 `15`，Build Index 为 `-1`；
- 六个 Showcase GameObject 均能按名称解析到有效实例；
- 最近 10 分钟 Error / Exception / Warning 均为 0。

场景静态统计为 1642 个 GameObject、1642 个 Transform、402 个 MonoBehaviour、1604 个 PrefabInstance、9 个 HDA Root 与 9 个 StreetBuildingAuthoring。该统计说明展示数据规模较大，但不等于运行时可接受；场景仍是 Editor Authoring/验证场景，未进入移动端 Runtime Bake 验收。

## 10. 回归门禁与增量 Patch

提交新增六个 StreetBuilding Change Manifest：

```text
full_envelope_phase2
modular_details_phase3
roof_alignment_phase31
roof_alignment_phase31b
project_owned_styles_phase4
project_owned_styles_phase4b
```

并保留三段可审计的一次性增量迁移脚本：

```text
patch_streetbuilding_full_envelope_v5.py
patch_streetbuilding_modular_details_v6.py
patch_streetbuilding_roof_alignment_v61.py
```

这些脚本采用精确 Marker/前置内容检查、幂等 Marker、`save=False` 字节干净检查、临时 Hython 实例验证，并只允许在验证通过后保存。它们是本次迁移记录，不应在未来任务中按顺序重放来重建当前资产；当前 HDA/HIP 仍是实现事实源。

`streetbuilding_contract.json` 当前声明：

```text
schema_version = 2
revision       = STREETBUILDING_V6_1_ROOF_ALIGNMENT
version        = StreetBuilding.DirectInstances.6.1
```

累计 HDA 合同覆盖 V1、V5、V6、V6.1。`project_owned_styles_phase4*` Manifest 额外声明的六个合同 ID 尚未合并进合同 JSON 与 Validator 的 expected ID set，这是本阶段最明确的自动化缺口。

## 11. 验证记录

### 11.1 Houdini Preflight

执行：

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .agents\scripts\Ensure-HoudiniMcp.ps1
```

结果：

- Houdini RPC `18811` 已连接，版本 `21.0.440`；
- 当前 HIP 为 `PCG_Bike_StreetBuilding.hip`；
- 3055 MCP Health 在脚本重启服务后通过；
- 当前 Codex 会话未热加载 Houdini MCP 工具，因此没有进行 Live 节点级读回；需要重启 Codex 后补做。

### 11.2 Fresh HDA Validator

执行：

```powershell
& 'D:\Software\Side Effects Software\Houdini 21.0.440\bin\hython.exe' `
  HoudiniProject/PCG_Track_21.0.440/scripts/tools/validate_streetbuilding_contract.py
```

结果：`PASS`。验证器从磁盘 HDA 创建 `/obj/VERIFY_STREETBUILDING_V6_1_LOCKED` 新实例，Definition 保持锁定，主要结果如下：

| 合同 | 结果 |
|---|---|
| Internal 基线 | 604 Points / 151 Primitives |
| V1 兼容 | 39 Points / 9 Assets，SHA `75630d4e...57d4` |
| V2 完整壳体 | 161 Points / 5 Faces / 15 Unique Assets |
| V2 Roof | 30 Tiles / 14 Straight Parapets / 4 Corners |
| V2 相同 Seed | SHA `c5ee0be6...90ed` 稳定 |
| V2 不同 Seed | SHA `417163c5...64e8`，结果发生变化 |
| V6.1 Details | 16 Points，含五种 Detail Role，预算 64 |
| Details 相同 Seed | SHA `a06d8911...6192` 稳定 |
| Details 不同 Seed | SHA `103443ef...e9aa`，结果发生变化 |
| Detail Toggle | 与 Shell 隔离，关闭细节不改变主体 |
| 尺寸 10×8 / 12×10 / 16×12 | 分别 130 / 161 / 215 Points |
| 非法宽度 7 / 11 / 15 | 全部拒绝 |

### 11.3 Python 门禁单元测试

执行：

```powershell
python HoudiniProject/PCG_Track_21.0.440/scripts/tests/test_pcg_regression_gate.py
```

结果：

```text
Ran 11 tests in 0.006s
OK
```

### 11.4 Unity 当前现场

通过 Unity MCP 读取：

- Editor 状态正常，场景未 Dirty；
- `PCG_Building.unity` 是唯一打开场景；
- 六个 ProjectOwned Showcase 根全部存在；
- 最近 10 分钟无 Error、Exception 或 Warning；
- Phase27 文档创建前 AssetDatabase 中不存在同名资产。

本次没有运行未跟踪目录 `Assets/PCG/Scripts/Tests/` 中的 Unity Test，也没有触发场景保存或重序列化。原因不是将其视为失败，而是这些 Test 不属于提交 27 的可审计内容，且本日志任务必须保护当前已确认的 Live Scene。

## 12. 移动端性能与渲染边界

### 12.1 已具备的约束

- 项目自有材质固定使用 URP/Lit 并开启 GPU Instancing；
- 单模块不同材质数硬限制为 3，避免过多 SetPass；
- Prefab 不带脚本、Collider、Light、Animator 或运行时行为；
- 细节独立开关和密度参数，可按平台关闭；
- 细节硬预算 64，防止无界增长；
- HDA Root 保持 `EditorOnly`，移动端运行时不依赖 Houdini Cook；
- 本提交没有新增自定义 Shader、Keyword 或 RendererFeature，因此没有新增项目自定义 Shader Variant 组合。

### 12.2 尚未达到运行时交付标准

- 56 个项目自有 Prefab 是由多个 Cube 子 Mesh 组成的灰盒模块，直接保留为大量 GameObject/MeshRenderer 会放大 CPU 提交、DrawCall 和场景序列化体积；
- GPU Instancing 材质开关不等于城市级 GPU Driven，当前没有 DrawMeshInstancedIndirect、GPU Culling、Chunk/Cluster 或 GPU LOD；
- URP/Lit 本身仍携带 URP Keyword/Variant 成本，虽然本阶段没有新增 Keyword，仍需构建期 Shader Variant Collection/Strip 审计；
- 没有移动端三角形、Overdraw、纹理内存、带宽、SetPass、SRP Batcher/Instancing 实际命中率数据；
- 没有 Runtime Bake 数据格式，不能让 HDA 生成层级直接进入 Android/iOS 正式场景；
- 没有 Mali、Adreno、Apple GPU 真机验证。

因此合理的下一阶段方向不是继续增加灰盒模块数量，而是将 Editor HDA 输出 Bake 为 Unity 原生、可按 Chunk 合批的数据，建立 Mesh/Material 合并策略、GPU Culling/LOD 和移动端性能预算，再替换为正式美术模块。

## 13. 阶段完成定义与后续优先级

Phase27 可以确认完成：

- Catalog V2 与 V1 精确兼容；
- 五表面完整建筑壳体；
- 2m/4m 模块跨度与确定性加权选型；
- 独立模块化细节流及 64 实例预算；
- V6.1 屋顶、女儿墙、RoofProp 对齐；
- DesignPreset 参数事务与显式场景保存工作流；
- 两套无第三方依赖的项目自有灰盒风格；
- 六栋确定性 Unity Showcase；
- HDA fresh-instance 累计验证和 Python 门禁单元测试。

后续优先级：

1. 将六个 ProjectOwned/DesignPreset 合同 ID 纳入 `streetbuilding_contract.json` 与提交内自动化测试，补齐 Direct Save Rollback 和 Preset Determinism 的失败路径验证；
2. 重启 Codex 后补做 Houdini Live 节点、Definition、Cook Error/Warning 与当前 HIP 未保存状态复验；
3. 为 ProjectOwned Builder 增加生成结果的资源引用审计、材质槽/Renderer 数、Mesh bounds 和幂等重建测试；
4. 设计 StreetBuilding Runtime Bake 数据，不让移动端运行时依赖 HDA 或大量场景 GameObject；
5. 按 Chunk/Cluster 接入 GPU Driven Culling/LOD，并建立 Android/iOS 的 DrawCall、SetPass、Overdraw、显存与带宽基线；
6. 用正式项目自有美术资产替换 Primitive Cube 灰盒模块，同时保持 Catalog V2、Pivot、尺寸和角色合同不变。

## 14. 总结

Phase27 把 StreetBuilding 从“可替换正立面模块的 Editor Authoring 工具”推进为“可由 Catalog V2 和 DesignPreset 确定性生成完整建筑、细节与项目自有风格展示”的系统。核心价值不是六栋灰盒建筑本身，而是完整壳体、角色分层、V1/V2 兼容、稳定种子、参数回滚和可审计验证链路已经建立。

当前 HDA 几何行为证据充分，Unity 场景与资产引用也已落盘并可读取；但 ProjectOwned/DesignPreset 的累计自动化合同、Live Houdini MCP 复验和移动端 Runtime Bake/GPU Driven 性能闭环仍未完成。后续开发应优先补齐这些验证与运行时边界，避免把 Editor 展示场景直接当作移动端生产方案。
