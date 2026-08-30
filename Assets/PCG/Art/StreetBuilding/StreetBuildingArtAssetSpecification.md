# StreetBuilding 美术资产制作规范（阶段 5 / Catalog V2）

本规范定义 StreetBuilding 模块化立面资产的长期自建标准。Downtown City MegaKit 仅作为只读验证源，不是项目正式资产模板。

## 1. 目录与命名

每个风格使用稳定的小写 snake_case `StyleId`，例如 `na_brick_mixeduse_01`。

| 内容 | 路径 |
|---|---|
| 模型 | `Assets/PCG/Art/StreetBuilding/<StyleId>/Models/` |
| Prefab | `Assets/PCG/Art/StreetBuilding/<StyleId>/Prefabs/` |
| 验证细节 Prefab | `Assets/PCG/Art/StreetBuilding/<StyleId>/Prefabs/ValidationDetails/` |
| Catalog | `Assets/PCG/Art/StreetBuilding/<StyleId>/` |
| 材质 | `Assets/PCG/Materials/Buildings/<StyleId>/` |
| 纹理 | `Assets/PCG/Art/StreetBuilding/<StyleId>/Textures/` |

- 模型：`SM_SB_<Style>_<Role>_<Variant>`
- Prefab：`PF_SB_<Style>_<Role>_<Variant>`
- 材质：`M_SB_<Style>_<Surface>`
- 纹理：`T_SB_<Style>_<Surface>_<Map>`

不得用文件名表达楼层号或建筑实例号；楼层、Cell 和实例身份由生成数据提供。

## 2. 交付单元

- 正式交付单元以 Prefab 为主，裸 FBX Model Prefab 保持兼容。
- 一个逻辑模块可以由 Prefab 内多个 FBX 子节点组成，例如门框与门扇。
- Catalog 只保存资产引用、逻辑角色、Variant、尺寸、权重和局部偏移，不复制 Mesh、Material 或 Texture。
- Prefab 根只允许 `Transform`；可见子节点只允许 `Transform`、`MeshFilter`、`MeshRenderer`。
- 当前效果验证 Prefab 禁止脚本、Collider、LODGroup、Light、Animator 和其他运行时行为。

## 3. 坐标、Pivot 与尺寸

- 1 Unity Unit = 1 米。
- `+Y` 向上。
- 面向街道观察立面时，`+X` 向右，`+Z` 为立面朝外方向。
- 建筑内部位于立面平面的 `-Z` 一侧。
- 模块根 Pivot 位于对应网格单元的底部中心，根 Transform 必须为 Position `(0,0,0)`、Rotation `(0,0,0)`、Scale `(1,1,1)`。
- 复合模块的组合偏移和旋转优先在 Prefab 子节点内完成；Catalog 允许记录 Part Position，Part Rotation 保持零旋转。
- 左右边缘立柱的 Pivot 位于建筑边界线，不占用 2m Bay。

当前 `StreetBuilding.DirectInstances.6.1` 网格：

- Bay 宽度：2m
- 首层高度：4m
- 标准层高度：3m
- 正面、侧面、背面均按 2m Cell 排布，屋顶按 2×2m Tile 排布。
- 允许 2m 单格和 4m 双格立面模块；4m 模块必须声明 `CellWidth=4`，不得与已有占用重叠。
- 建筑保持单个正面入口，侧面和背面禁止入口。

## 4. Catalog V2 与必需模块槽位

Catalog 编译结果使用 UTF-8、Invariant Culture 和稳定排序：

```text
SBV2|<StyleId>|<CellWidth>|<GroundFloorHeight>|<TypicalFloorHeight>
M|Role|Variant|PartIndex|AssetPath|PosX|PosY|PosZ|EulerX|EulerY|EulerZ|CellWidth|CellHeight|Weight
```

- `Weight` 必须大于 0；相同 Role 内按权重做确定性选择。
- 同一 `Role + VariantId` 的 PartIndex 从 0 连续递增。
- Payload 内容直接参与 SHA-256，修改尺寸、权重、路径或局部偏移都会产生新版本。
- HDA 同时接受旧 V1 10 字段 Payload；V1 仅用于 REV4.1 精确回归，不作为新 Catalog 默认格式。

当前 REV4.1 Catalog 至少包含以下稳定键：

- `Entrance / entrance_metal`
- `GroundShop / shop_metal`
- `GroundShop / shop_trim`
- `Cornice / brick_center`
- `MiddleWindow / trim`
- `MiddleWindow / trim_single`
- `FacadeColumn / trim_ground`
- `FacadeColumn / brick_upper`

后续可以增加 Variant，但不得重用或静默改写已发布的 `Role + VariantId`。

完整外壳还需要：

- `GroundWall`、`MiddleBlank`、`SideWall`、`RearWall`
- `RoofSurface`：2×2m 平屋顶 Tile
- `Parapet`：2m 直线女儿墙，根 Pivot 位于底部中心，标准高度 0.6m
- `ParapetCorner`：90° L 形转角，根 Pivot 位于外侧精确转角，局部形体沿 `+X/-Z` 向内延伸
- `RoofProp` 已从 LOD0 外壳移入独立 `OUT_DETAIL_INSTANCES`

Direct V2 在 `parapet_height > 0` 时生成连续女儿墙。Catalog 模式下 `Parapet` 与
`ParapetCorner` 的声明高度必须等于 `parapet_height`，禁止生成端缩放；设为 0 时只关闭
屋顶边缘模块，不改变墙面和屋面 Tile。

## 5. 模块化细节角色与替换规则

五类细节均通过独立实例点输出，不得合入外壳 Mesh：

| Role | 标准尺寸 | Pivot / 挂接面 | 朝向与限制 |
|---|---:|---|---|
| `Awning` | 2×1m | 根 Pivot 位于首层正面 Cell 中心，生成器提供檐口高度 | `+Z` 朝外；不得占用入口 Cell |
| `Sign` | 2×1m | 根 Pivot 位于首层正面墙面 | `+Z` 朝外；不得占用入口 Cell |
| `FireEscape` | 4×6m | 根 Pivot 位于后墙、首个标准层底部 | `+Z` 朝外；至少三层，每栋最多一个 |
| `ACUnit` | 2×1m | 根 Pivot 位于设备背板中心，贴侧墙或后墙上层 | `+Z` 朝外；不得用于正面和首层 |
| `RoofProp` | 2×2m | 根 Pivot 位于屋顶接触面的底部中心 | 保持单位旋转；距屋顶边缘至少一个 2m Cell |

- 项目验证用 `Awning`、`Sign`、`FireEscape` 必须放在 `ValidationDetails`，只使用 Unity 内置 Cube 与共享 `M_SB_ValidationDetail`。
- `ACUnit` 只允许贴在上层侧墙或后墙，禁止出现在正面、首层和屋顶。
- `RoofProp` 只允许使用屋顶语义明确的项目自有资产；当前验证槽位为 `water_tank`、
  `roof_vent`、`mechanical_box`，禁止复用 `ac_unit`。根 Pivot 的 `minY` 必须为 0，生成点
  直接位于 roofY，且至少退让屋顶边缘一个 2m Cell。
- 根 Transform 必须归零；形体偏移、支架布局和局部旋转全部放在可见子节点内。
- HDA 只接受 Catalog 提供的原始资产路径，输出 `scale=(1,1,1)` 与归一化 `orient`；美术不得依赖生成端非等比缩放。
- 已发布 `Role + VariantId` 是稳定键。升级资产可以替换引用，但不得把同一键静默改成另一种角色、占地或挂接面。
- `detail_density` 仅控制细节概率，不得改变 LOD0 外壳；`generate_attachments=false` 或密度为 0 时细节输出必须为空。
- 每栋最多 64 个细节实例；新增细节种类应复用独立 Role/Variant 配方和现有选择种子，不得在 Prefab 内添加运行时脚本。

## 6. 材质与移动端约束

- 仅使用兼容 URP 的 Shader；不得依赖 Built-in Shader。
- 支持 GPU Instancing 的材质应开启 Instancing。
- 透明材质仅用于玻璃等必要区域，避免大面积透明叠层和过度 Overdraw。
- 单模块不超过 3 个材质槽；项目自有资产超出时 Authoring Validator 必须阻断。
- 正式贴图尺寸、三角形数和透明面积在当前阶段记录为审计信息，不阻断效果验证。
- LOD、Collider、合批与运行时 GPU 渲染不属于阶段 5，由后续 Bake/Runtime 阶段处理。

## 7. 阶段 5 Style Kit 交付基线

阶段 5 的目标不是把某个第三方包“改成可用”，而是验证一套可持续自建的模块语言。项目内
`urban_brick_mixeduse_01` 与 `urban_stucco_residential_01` 是可替换参考实现，不是最终美术锁定稿。

每个正式 Style Kit 至少满足：

| 项目 | 最低要求 |
|---|---:|
| Catalog | 1 个，`SchemaVersion=2`、`SourceKind=ProjectOwned` |
| 基础/外壳/细节 Role | 覆盖当前 17 个必需 Role |
| 参考 Recipe | 40 个；新增 Variant 只能追加稳定键 |
| DesignPreset | Compact / Standard / Corner Tall 各 1 个 |
| 共享材质 | 5 个：Wall / Accent / Roof / Glass / Metal |
| 参考贴图 | 5 张 128×128 可平铺程序纹理，仅用于验证色彩、节奏与材质分层 |

参考几何需要主动表现以下视觉层次：首层商业或住宅入口、标准层窗型变化、空白墙节奏、檐口、
边缘立柱、完整侧背立面、连续女儿墙，以及独立输出的雨棚、招牌、消防梯、墙面设备和屋顶设备。
同一风格内不能只靠随机颜色制造差异；至少要通过多个稳定 Variant 改变开窗、分格、挑檐、
阳台/凹槽、后勤门和屋顶轮廓。

参考贴图仅是占位质量基线。正式美术可替换为外部 DCC 导出的 FBX 和正式 PBR 贴图，但 Prefab
路径、Role + VariantId、Pivot、声明尺寸与 Catalog 结构必须保持稳定，或通过显式版本迁移升级。

提交前运行：

1. `PCG/StreetBuilding/Project Owned/Build Rich Styles + Six Building Showcase`，重建两套参考 Style Kit，重新 Cook 六栋展示建筑并直接保存场景。
2. `PCG/StreetBuilding/Project Owned/Audit Reference Style Kits`，确认依赖只来自当前 Style、对应材质目录、项目 Authoring 脚本与 URP Package。
3. 检查 `PCG_Building` 的正面、侧背面与屋顶；六栋建筑应在体量、层数、首层用途、立面节奏和细节密度上可辨识。
4. 运行 StreetBuilding `VerifyFast` 与 `VerifyFull`，确保 HDA/HIP 累计合同没有变化。

## 8. Authoring 流程

1. 美术按本规范创建 FBX 与 Prefab。
2. 在 `StreetBuildingInstanceModuleCatalog` 中登记 Style、允许目录和模块槽位。
3. 在 `StreetBuildingAuthoring` Inspector 执行 `Validate Catalog`。
4. 执行 `Compile Preview`，确认 Payload 和 SHA-256 稳定。
5. 执行 `Apply, Cook & Save Scene`；该操作更新 `module_source`、`unity_instance_catalog` 和 `style_id`，Cook 成功后直接保存 Scene。
6. 检查前、后、左、右和鸟瞰视图，确认墙顶不越过 roofY、屋面完整覆盖 footprint、
   女儿墙连续，并能看到不同密度的雨棚、招牌、消防梯、墙面 AC 与落地屋顶设备。

任何校验或 Cook 失败都不得保存场景；Applier 会尝试恢复原参数与原 Payload。程序化地块、CityRoad 相邻遮挡、LOD、Collider 和运行时 Cook 均不属于阶段 5。
