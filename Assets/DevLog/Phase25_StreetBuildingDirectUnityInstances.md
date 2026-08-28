# Phase 25 开发日志：StreetBuilding REV4.1 与 MegaKit 原始资产直接实例

> 文档类型：Git 提交增量审计与当前现场复验  
> 记录日期：2026-08-28  
> 版本文件：`Phase25_StreetBuildingDirectUnityInstances.md`  
> 目标提交：`4ba262981b58d34bccb1ff2f7125d1f0643707dc`（提交信息：`25_building`）  
> 直接父提交：`3795a5dd71123d4ae02c7e33880e7d9be5a836f0`（`Phase24`）  
> StreetBuilding HDA：`Assets/PCG/HDA/City/StreetBuilding.hda`  
> StreetBuilding HIP：`HoudiniProject/PCG_Track_21.0.440/PCG_Bike_StreetBuilding.hip`  
> Unity 场景：`Assets/PCG/Scenes/PCG_Building.unity`  
> 外部模块资源：`Assets/PCG/Art/Downtown City MegaKit[Standard]/`

## 1. 日志范围与结论

本文只记录 Git 提交 `4ba26298` 相对直接父提交 `3795a5dd` 的开发增量。Phase25 首次把 StreetBuilding 作为独立 PCG 模块正式纳入 Unity/Houdini 工程，并完成 REV4.1 正立面原型：

```text
Downtown City MegaKit 原始 FBX
    -> Unity ScriptableObject 模块目录
    -> 确定性文本 Catalog Payload
    -> StreetBuilding HDA unity_instance_catalog
    -> DIRECT_UNITY_INSTANCE_FACADE
    -> 2m 原生立面单元编排
    -> unity_instance 点输出
    -> Houdini Engine Unity 原始 FBX 实例
    -> PCG_Building EditorOnly 预览场景
```

提交的有效开发结果是：

- **新增独立 StreetBuilding HDA/HIP。** HDA 类型为 `pcgbike::StreetBuilding::1.0`，保留 Internal Proxy 和 Unity Asset Instances 两种模块来源。
- **建立外部模块直接实例链路。** Houdini 只生成变换、角色与 `unity_instance` 路径，不复制第三方 FBX 的顶点、材质或 Prefab。
- **完成 REV4.1 单正立面。** 12m 宽、4 层样例按 2m 单元生成 39 个实例点，包含单一建筑入口、5 个首层商铺窗、6 个檐口、18 个上层窗和 8 个边缘立柱。
- **建立 Unity 模块目录和适配器。** 8 个 Recipe、9 个原始 FBX Part，包含源目录 SHA-256 防篡改、确定性 Payload 和遗留派生资产清理。
- **建立合同与 Fresh 验证。** 验证公共接口、可读网络、稳定输出、原始路径、确定性、单入口、边缘立柱和合法面宽。
- **当前仍是 Editor-only 立面原型。** 侧面、后立面、屋顶、LOD1/2、附件、碰撞和正式 Runtime Bake 均关闭或为空。

该提交同时导入完整 Downtown City MegaKit 外部资源包。资源包能力属于第三方资产，不计为项目自研功能；本项目自研部分是模块目录、HDA 立面规则、Unity 适配器、合同和回归门禁。

## 2. 证据等级

- **[提交验证]**：目标提交元数据、440 个变更文件、Git diff、HDA/HIP、Scene YAML、C#、ScriptableObject、合同、patch、验证器和回归入口。
- **[Fresh HDA 验证]**：Houdini `21.0.440` 从磁盘 HDA 创建全新锁定实例，验证 Internal Proxy、Direct Instances、宽度合同和确定性；没有保存生产文件。
- **[Unity 当前现场]**：Unity MCP 检查 Editor、打开场景、AssetDatabase、`StreetBuilding1` 层级和最近 Console；没有修改或保存场景。
- **[Houdini 连接验证]**：`Ensure-HoudiniMcp.ps1` 确认 Houdini 21.0.440、生产 StreetBuilding HIP、18811 RPC 与 3055 health 正常。
- **[Houdini Live 待复验]**：当前 Codex 会话没有热加载 Houdini MCP 工具，不能把 Preflight 成功写成 Live Scene 节点级检查；本文以 Fresh HDA 验证为行为证据。
- **[源码验证]**：审查 Catalog、Adapter、V4/V4.1 manifest、HDA validator、场景序列化参数、FBX Importer 和移动端边界。
- **[未闭环]**：没有正式 Bake 产物、运行时建筑数据、LOD/Collider、侧后立面、屋顶、URP 材质兼容报告、DrawCall/SetPass 数据或移动端真机结果。

当前工作区另有 `PCG_City.unity`、URP RendererData、CityRoad/Terrain HIP 和未跟踪测试等用户改动；它们不属于提交 `25_building`，本文不把它们混入 Phase25 正式交付。

## 3. 提交概览

| 项目 | 数值 |
|---|---:|
| Commit | `4ba262981b58d34bccb1ff2f7125d1f0643707dc` |
| Author / Date | `liyuan` / 2026-08-28 11:21:13 +08:00 |
| Changed Files | 440 |
| Added / Modified / Deleted | 438 / 2 / 0 |
| Added / Deleted Lines | `+38857 / -3` |
| MegaKit 提交文件 | 411（含根 `.meta`） |
| MegaKit 磁盘体积 | 156,737,729 bytes（约 149.48 MiB） |
| MegaKit FBX | 153 |
| MegaKit Texture | 42 PNG + 4 JPG + 3 HDR |
| StreetBuilding HDA | 61,510 bytes |
| StreetBuilding HIP | 86,709 bytes |
| PCG_Building Scene | 342,063 bytes |
| Module Catalog | 3,249 bytes |
| Houdini Engine Unity 插件 | 0 个文件修改 |

提交中只有两个既有文件被修改：

- `.agents/scripts/Invoke-PcgRegression.ps1`；
- `HoudiniProject/PCG_Track_21.0.440/scripts/tools/pcg_regression_gate.py`。

其余 438 个文件均为新增资产、代码、合同或 `.meta`。

文件指纹：

| 文件 | Phase25 SHA-256 |
|---|---|
| StreetBuilding HDA | `9893B801D91AA34AF35AA2B831C0EE6F8C6C9803A63DD4CB3586E773738530BD` |
| StreetBuilding HIP | `87459AE8C6D1C2323A2A94A140C2BDD2520D446A304ACB5BE7CFCC505ADAF7A6` |
| PCG_Building Scene | `F2BF59526973CF8D015407F5BBADBC5EA7650D56A2D19D489B5201785A35AAD7` |
| Module Catalog | `8D4162BF9D91515CAF1A621E2EBE3867E2C387BD6F10C72D185C5152E3BF91F2` |

## 4. Downtown City MegaKit 外部资源接入

### 4.1 资源范围

新增资源根：

```text
Assets/PCG/Art/Downtown City MegaKit[Standard]/
```

包含：

- 153 个 Unity FBX：Brick、Metal、Trim、Cornice、Door、Roof、Street、Sidewalk、Prop 等模块；
- 42 张 PNG、4 张 JPG、3 张 HDR；
- 预览图和 `License_Standard.txt`；
- 与 Unity 导入状态对应的 `.meta`。

Phase25 的 StreetBuilding Catalog 只使用其中 9 个 FBX Part：

1. `DoorFrame_Metal_Single.fbx`；
2. `Door_2.fbx`；
3. `Metal_FirstFloor_Window.fbx`；
4. `Trim_FirstFloor_Window_001.fbx`；
5. `Cornice_Brick_Center.fbx`；
6. `Brick_Window_Trim.fbx`；
7. `Brick_Window_Trim_Single.fbx`；
8. `Trim_Column_Center.fbx`；
9. `Brick_Column_Small.fbx`。

其余资源只是已导入的候选模块，不能视为已被 StreetBuilding 规则使用。

### 4.2 只读源目录合同

Unity Adapter 固定源目录哈希：

```text
3cb8b581b271288307dfb39335153af41598459221f986b678f420b7dc071e9d
```

构建 Catalog 前后都会重新计算源目录 SHA-256：

- 构建前不匹配则立即停止；
- Catalog 编译后再次检查，防止适配过程修改第三方源资产；
- 不创建派生 Mesh、Material 或 Prefab；
- 旧 `NativeV2`、`Meshes`、`Prefabs`、NAB01 材质/纹理派生目录由显式清理命令移除。

该策略保护原始资源，但哈希覆盖资源路径和文件内容，对 `.meta` 或合法导入设置变化也敏感。未来若需要移动端 Importer 优化，应先修订并版本化源基线，不能绕过哈希检查。

### 4.3 FBX 导入边界

抽查已使用 FBX 的 Importer：

- `isReadable = 0`，不会为运行时保留 CPU 可读 Mesh 副本；
- `addColliders = 0`；
- `meshCompression = 0`；
- `generateSecondaryUV = 0`；
- `importAnimation = 1`；
- Camera、Light、BlendShape 导入保持默认开启；
- Material 位于 FBX 内部，没有外部 Material Remap。

这不是面向移动端的最终 Importer 策略。当前只读哈希合同阻止 Adapter 自动改源 `.meta`，因此静态模块的 Animation/Camera/Light/BlendShape、压缩和 Lightmap UV 优化仍待专门资产导入阶段处理。

## 5. StreetBuilding HDA 基础架构

### 5.1 公共接口

HDA 类型：

```text
pcgbike::StreetBuilding::1.0
```

最大输入数固定为 3：

1. Site Parcels；
2. Frontage Guides；
3. Module Library。

公共来源模式：

| 参数 | 模式 |
|---|---|
| `site_source` | `internal` / `external` |
| `module_source` | `internal_proxy` / `unity_asset_instances` |

`unity_instance_catalog` 是 String Transport 参数，负责从 Unity 向 Houdini 传递确定性模块目录；不会把 Unity Mesh 顶点上传为 Houdini 几何。

### 5.2 可读网络

`StreetBuildingCore` 按 9 个 Network Box 分层：

```text
00_INPUT_VALIDATE
10_FRONTAGE_RESOLVE
20_MASSING
30_FACADE_GRAMMAR
40_GRAYBOX_MODULES
50_VISIBLE_SHELL
60_LOD_BUILD
70_UNITY_CONTRACT
80_OUTPUT_VALIDATE
```

合同要求 25 个关键节点，包括输入、Parcel 规范化、Frontage、Massing、Facade Grammar、Graybox Library、LOD0/1/2、Direct Unity Instances、Detail、Collision、Metadata 和 6 个稳定输出。

### 5.3 稳定输出

HDA 保留 6 类输出名称：

1. `OUT_BUILDING_LOD0`；
2. `OUT_BUILDING_LOD1`；
3. `OUT_BUILDING_LOD2`；
4. `OUT_DETAIL_INSTANCES`；
5. `OUT_BUILDING_COLLISION`；
6. `OUT_BUILDING_METADATA`。

REV4.1 直接实例模式只启用 LOD0：

```text
Internal Proxy Geometry ----[0]-->
                              LOD0_MODULE_SOURCE_SWITCH -> OUT_BUILDING_LOD0
Direct Unity Instance Points [1]-->

EMPTY_GEOMETRY -> LOD1 / LOD2 / Detail / Collision / Metadata
```

这不是六类输出全部完成，而是用稳定接口隔离当前正立面原型和后续扩展。

## 6. Unity 模块目录与适配器

### 6.1 ScriptableObject 数据模型

新增 `StreetBuildingInstanceModuleCatalog`，数据结构为：

```text
Catalog
  -> Style ID
  -> Source Root
  -> Source SHA-256
  -> Module Recipe[]
       -> Module Role
       -> Variant ID
       -> Cell Width / Height
       -> Weight
       -> Part[]
            -> Source FBX
            -> Local Position
            -> Local Euler Rotation
```

`StreetBuildingModuleRole` 预留 Ground、Entrance、Window、Corner、Cornice、Parapet、Side/Rear Wall、Column、Band、Awning、Sign、Fire Escape、AC 和 Roof Prop 等角色。枚举顺序被声明为序列化合同，不允许随意重排。

### 6.2 REV4.1 Catalog

当前 Catalog：

- Style：`na_brick_mixeduse_01`；
- 8 个 Recipe；
- 9 个原始 FBX Part；
- 所有单元宽度为 2m；
- 所有 Part Rotation 为 Identity；
- Entrance Recipe 由 Door Frame + Door 两个 Part 组成；
- 其余 Recipe 各引用一个原始 FBX。

| Role | Variant | Part 数 |
|---|---|---:|
| Entrance | `entrance_metal` | 2 |
| GroundShop | `shop_metal` | 1 |
| GroundShop | `shop_trim` | 1 |
| Cornice | `brick_center` | 1 |
| MiddleWindow | `trim` | 1 |
| MiddleWindow | `trim_single` | 1 |
| FacadeColumn | `trim_ground` | 1 |
| FacadeColumn | `brick_upper` | 1 |

### 6.3 确定性 Payload

Adapter 将 Catalog 编译为逐行文本：

```text
Role|Variant|PartIndex|AssetPath|PositionXYZ|EulerXYZ
```

编译两次并比较结果，不一致则失败。Houdini 输出保留以下关键点属性：

- `unity_instance`、`orient`、`instance_prefix`、`name`；
- `building_id`、`floor_index`、`cell_index`；
- `module_role`、`module_variant`、`surface_role`、`facade_band`；
- `is_building_entrance`、`is_shop_entrance`；
- `lod`、`chunk_id`、`pcg_kind`、`pcg_variant`。

这些属性是后续 Bake、Chunk、LOD 和调试工具的扩展点。

### 6.4 Unity 菜单工作流

Adapter 提供三个 Editor Menu：

1. `Clean Legacy Derived Assets`；
2. `Build Direct Instance Catalog`；
3. `Apply To StreetBuilding1 + Save`。

Apply 流程会：

- 重新打开已保存的 `PCG_Building`，隔离旧 HEU Auto Cook 的瞬时 Dirty Hierarchy；
- 清理旧派生资产并重建 Catalog；
- 先把旧 Definition 切到 Internal Proxy 并 Cook；
- 断开旧 Module Library 输入；
- Reload REV4.1 HDA；
- 设置直接实例参数并 Cook；
- 审计所有 Mesh 和 Material 是否仍来自原始 MegaKit；
- 拒绝意外的 LODGroup 或 Collider；
- 把 HDA Root 标记为 `EditorOnly` 后保存场景。

## 7. REV4.1 正立面规则

### 7.1 当前场景参数

`PCG_Building.unity` 当前序列化：

| 参数 | 值 |
|---|---:|
| `site_source` | Internal |
| `module_source` | Unity Asset Instances |
| `style_id` | `na_brick_mixeduse_01` |
| `internal_width` | 12m |
| `internal_depth` | 10m |
| `floor_count` | 4 |
| `ground_floor_height` | 4m |
| `typical_floor_height` | 3m |
| `target_bay_width` | 2m |
| `ground_use` | Mixed |
| `facade_rhythm` | Paired |
| `rear_mode` | Off |
| `side_mode` | Off |
| Roof / LOD / Attachment / Architectural Trim | Off |

合同文件中的 HDA默认层高仍是 4.2m / 3.2m，Adapter 应用到样例场景时显式覆盖为 4m / 3m。文档必须区分 Definition Default 和 Scene Instance Value。

### 7.2 12m / 4 层实例组成

12m 面宽按 2m 分为 6 个 Cell。当前输出 39 个 Part Point：

| 角色 | 数量 | 规则 |
|---|---:|---|
| Entrance | 2 | Cell 3 的 Frame + Door；全楼唯一建筑入口 |
| GroundShop | 5 | 除入口 Cell 外每格一个首层商铺窗 |
| Cornice | 6 | 每个 Cell 一个檐口 |
| MiddleWindow | 18 | 3 个上层 × 6 Cell |
| FacadeColumn | 8 | 左右边界 × 首层及 3 个上层 |
| 合计 | 39 | 9 个唯一原始 FBX |

入口规则：

- `is_building_entrance` 只允许 Cell 3；
- `GroundShopDoor` 数量为 0；
- `is_shop_entrance` 为空；
- 避免首层同时出现多个建筑入口或商铺门。

上层窗节奏：

```text
Cell 0..5 = A A B B A A
A = trim
B = trim_single
```

边缘立柱：

- X 位于 `-6m / +6m` 立面边界；
- Y 行为 `0m / 4m / 7m / 10m`；
- 首层使用 `trim_ground`；
- 上层使用 `brick_upper`。

### 7.3 面宽 Fail-Closed

REV4.1 使用 2m 原生模块，不对 FBX 做非等比拉伸：

- 10m：有效，输出 34 点；
- 12m：有效，输出 39 点；
- 7m、11m、15m：不是 2m 整数单元，验证器要求 Cook 失败关闭。

该策略优先保护模块比例与确定性。后续若支持任意面宽，应引入边缘填充模块或离散 Width Solver，不能直接拉伸门窗资产。

## 8. Unity 场景与现场

### 8.1 提交场景序列化

新增 `PCG_Building.unity`，主要 YAML 对象：

| 对象类型 | 数量 |
|---|---:|
| GameObject | 45 |
| Transform | 45 |
| MonoBehaviour | 26 |
| PrefabInstance | 40 |
| 序列化 MeshFilter / MeshRenderer | 0 / 0 |
| 序列化 Collider | 0 |
| `SB_B0000_*` Instance Root | 39 |

场景中的 39 个建筑模块由 PrefabInstance 引用原始 FBX，因此 Scene YAML 不复制 Mesh/Renderer 数据。额外一个 PrefabInstance 属于 HDA/场景基础引用。

HDA 序列化标识：

- `_assetName = StreetBuilding3`；
- `_assetOpName = pcgbike::Object/StreetBuilding::1.0`；
- `_assetPath = Assets/PCG/HDA/City/StreetBuilding.hda`。

### 8.2 Unity MCP 现场

2026-08-28 当前现场：

- Unity `2022.3.62f2`；
- 未播放、未暂停、未编译、未刷新 AssetDatabase；
- 打开的场景为 `PCG_Building`，有效、已加载、未 Dirty、Root Count 5；
- Build Index 为 `-1`，尚未加入 Build Settings；
- `StreetBuilding1` Root 存在并包含 `HEU_HoudiniAssetRoot`；
- Root、`HDA_Data`、LOD0 Output 和 39 个模块实例均标记 `EditorOnly`；
- LOD0 层级中的 39 个名称与 HDA 输出角色/楼层/Cell 一致；
- Catalog 被 AssetDatabase 识别为 `StreetBuildingInstanceModuleCatalog`，GUID 为 `b0a2e379c21659245936afea8903a205`；
- 最近 30 分钟 Console Error 为 0，当前 Warning 为 0。

LogCollector 仍保存更早的 Dirty Scene 测试尝试错误；它们发生在当前复验前，当前场景已经保存。Phase25 回归脚本因此新增 StreetBuilding 专用时间窗口，只把本次验证开始后的诊断计为新增错误。

## 9. 回归门禁接入

`Invoke-PcgRegression.ps1` 和 `pcg_regression_gate.py` 的 StreetBuilding Builder 从旧的整包 Graybox Builder 改为：

```text
patch_streetbuilding_direct_unity_instances_rev4.py
```

意义：

- 不再用旧 Builder 重建并覆盖当前 StreetBuilding；
- 以现有 HDA/HIP 为事实源执行 REV4 增量 patch；
- `save=false` 时比较 HDA/HIP SHA-256，发现文件变化即失败；
- Verify 时只接收当前操作时间窗口产生的 Unity Console 诊断，避免历史缓存造成误报。

V4 manifest 约束 Direct Instance 节点、LOD0 Switch、空输出连接和两个新增公共参数；V4.1 manifest 进一步把修改范围收紧到 `DIRECT_UNITY_INSTANCE_FACADE` 的 snippet，新增 Single Entrance 与 Edge Columns 合同。

门禁测试：

```text
Ran 11 tests in 0.003s
OK
```

## 10. Fresh HDA 验证结果

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
| Direct Instances | 39 points / 0 polygon prims |
| Unique Source Assets | 9 |
| Direct Output SHA-256 | `41e385768526b8876699eae0990a6a51f8486044ceee835f09b7bd7a08360f19` |
| 10m Width | 34 points |
| 12m Width | 39 points |
| 7m / 11m / 15m | rejected |

验证器还确认：

- Fresh 实例保持 Locked；
- 3 个 HDA 输入和公共参数/菜单合同正确；
- Direct 模式不产生重建 Polygon/Packed Geometry；
- `unity_instance` 全部指向原始 MegaKit FBX；
- 17 个必需点属性存在；
- 单入口、商铺窗、檐口、窗节奏、边缘立柱和楼层高度满足合同；
- LOD1/2、Detail、Collision、Metadata 输出为空；
- 相同输入重复 Cook 的几何签名一致；
- 没有保存 HDA、HIP 或 Fresh 实例。

Houdini Preflight 同时确认当前 GUI 使用 `PCG_Bike_StreetBuilding.hip`。由于本次会话未热加载 Houdini MCP 工具，没有进一步声明生产 Live Node 与 Definition 完全一致。

## 11. 移动端与渲染架构评估

### 11.1 当前 CPU / GPU 边界

| 阶段 | 当前方案 | 评价 |
|---|---|---|
| 模块选择 | Unity Editor 编译 Catalog | 确定性且不复制顶点 |
| 立面规则 | Houdini Editor Cook | 可接受，但禁止进入移动端运行时 |
| Unity 预览 | 39 个原始 FBX PrefabInstance | 适合原型，不是城市级 Runtime 结构 |
| Runtime Bake | 未实现 | 未达到发布闭环 |
| LOD / Culling | 当前关闭 | 城市规模不可直接使用 |
| Collider | 当前无 | 需要按玩法单独设计低成本代理 |

直接引用原始 Mesh/Material 的优势：

- 不产生重复 Mesh/Material 资产；
- 原始 GUID 稳定；
- FBX `isReadable=0`，避免运行时 CPU Mesh 副本；
- HDA 输出只是点和路径，Cook 数据量可控。

但每栋 12m 建筑产生 39 个模块实例。若直接扩展到整座城市，会带来大量 GameObject、Transform、Renderer、DrawCall 和 SetPass。移动端正式方案应在 Bake 阶段：

- 按 Building / Block / Chunk 分组；
- 对相同 Mesh + Material 使用 GPU Instancing；
- 大规模重复模块采用 GPU Culling + Indirect Draw；
- 构建 HLOD/低模替代；
- Collider 使用独立简化代理，禁止逐窗口 Collider；
- 保留可编辑源实例与运行时优化数据的双层结构。

### 11.2 Shader 与 Variant

提交没有新增自研 Shader、Compute Shader、RendererFeature 或 RenderPass，因此：

- 没有新增自定义 `shader_feature_local` / `multi_compile` 组合；
- 没有新增全屏 Blit、RenderTexture、MRT 或 Tile Memory Flush；
- 不能把外部 FBX 内嵌材质视为已验证的 URP Shader 能力。

Adapter 只验证 Material 仍来自 MegaKit，并检查 Glass / FakeInterior 名称；没有验证 Shader 是否兼容 URP 14、是否支持 Instancing、Variant 数量或移动端精度。完整 URP 材质迁移和 Shader Variant 审计仍待执行。

### 11.3 资源体积

完整 MegaKit 约 149.48 MiB，虽然 Unity Player 通常只打入被场景、Resources 或 Addressables 引用的资产，但整个资源包会增加仓库、导入、Library 和 CI 成本。正式构建前应：

- 审计 9 个已用 FBX 的实际纹理依赖；
- 隔离未使用的 144 个 FBX；
- 根据平台设置纹理压缩、Max Size 和 Mipmap；
- 避免把预览图、Unreal Normals 和未使用 HDR 纳入构建；
- 使用 Build Report 验证最终包体，而不是按 Assets 目录体积推断。

## 12. 已知问题与后续验收

1. **缺正式 Bake。** 当前全部建筑模块和 HDA Root 都是 `EditorOnly`，没有可供移动端运行时直接消费的 Unity 原生建筑数据。
2. **只有 Front Facade。** Side、Rear、Roof、Detail、Collision、Metadata、LOD1 和 LOD2 尚未交付。
3. **Build Settings 未接入。** `PCG_Building` 的 Build Index 为 `-1`，目前只是一张验证场景。
4. **URP 材质兼容待验证。** 外部资源名为 Standard 版本，FBX 内嵌材质没有完成 URP Shader、Glass、Fake Interior 和 Instancing 审计。
5. **城市级 DrawCall 风险。** 39 个实例/栋只适合样例；必须用 Chunk、HLOD、GPU Instancing/Indirect 和剔除收敛。
6. **Importer 仍偏通用。** 静态 FBX 的 Animation、Camera、Light、BlendShape 导入未关闭，Mesh Compression 与 Secondary UV 未配置。
7. **宽度只支持 2m 整数格。** 这是当前 Fail-Closed 合同，不是任意地块自适应能力。
8. **合同预算尚未落地。** `lod0_triangles_per_building=12000`、LOD1 比例、LOD2 200 Tris 和每 LOD 三材质只是接口预算；Direct Instance Validator 没有统计原始 FBX 实际三角形/材质成本。
9. **测试资产未随提交纳入。** 当前工作区能发现未跟踪的 StreetBuilding EditMode Test，但目标提交没有包含 `Assets/PCG/Scripts/Tests/`；不能把它记为 Phase25 正式测试交付。
10. **Houdini Live MCP 待复验。** RPC/health 正常，但 Codex 工具未热加载；重启 Codex 后应检查生产节点、Definition、Cook Error/Warning 和 Scene Diff。
11. **移动端未测试。** 需要 Mali、Adreno、Apple GPU 的 DrawCall、SetPass、内存、纹理带宽、加载峰值和热量数据。

## 13. Phase25 最终状态

提交 `25_building` 已建立 StreetBuilding 的第一条可复验生产链：完整第三方模块资源进入 Unity，项目侧使用只读源哈希、ScriptableObject Catalog、确定性 Payload 和 Houdini `unity_instance` 点生成 12m / 4 层 REV4.1 正立面；Fresh HDA 与当前 Unity 场景都确认 39 个原始 FBX 实例的角色、楼层、Cell、入口和边缘立柱符合合同。

本阶段可标记为：

> **StreetBuilding REV4.1 原始 Unity 资产直接实例与 Editor 验证场景已完成；Runtime Bake、完整建筑体、LOD/碰撞、URP 材质和城市级移动端渲染仍未闭环。**
