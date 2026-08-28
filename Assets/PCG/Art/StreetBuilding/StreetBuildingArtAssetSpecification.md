# StreetBuilding 美术资产制作规范（阶段 1）

本规范定义 StreetBuilding 模块化立面资产的长期自建标准。Downtown City MegaKit 仅作为只读验证源，不是项目正式资产模板。

## 1. 目录与命名

每个风格使用稳定的小写 snake_case `StyleId`，例如 `na_brick_mixeduse_01`。

| 内容 | 路径 |
|---|---|
| 模型 | `Assets/PCG/Art/StreetBuilding/<StyleId>/Models/` |
| Prefab | `Assets/PCG/Art/StreetBuilding/<StyleId>/Prefabs/` |
| Catalog | `Assets/PCG/Art/StreetBuilding/<StyleId>/` |
| 材质 | `Assets/PCG/Materials/Buildings/<StyleId>/` |
| 纹理 | `Assets/PCG/Texture/StreetBuilding/<StyleId>/` |

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
- 阶段 1 禁止脚本、Collider、LODGroup、Light、Animator 和其他运行时行为。

## 3. 坐标、Pivot 与尺寸

- 1 Unity Unit = 1 米。
- `+Y` 向上。
- 面向街道观察立面时，`+X` 向右，`+Z` 为立面朝外方向。
- 建筑内部位于立面平面的 `-Z` 一侧。
- 模块根 Pivot 位于对应网格单元的底部中心，根 Transform 必须为 Position `(0,0,0)`、Rotation `(0,0,0)`、Scale `(1,1,1)`。
- 复合模块的组合偏移和旋转必须在 Prefab 子节点内完成；Catalog/HDA 传输层保持零旋转。
- 左右边缘立柱的 Pivot 位于建筑边界线，不占用 2m Bay。

当前 `StreetBuilding.DirectInstances.4.1` 兼容网格：

- Bay 宽度：2m
- 首层高度：4m
- 标准层高度：3m
- 当前验证建筑：12m、4 层、单入口

## 4. 必需模块槽位

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

## 5. 材质与移动端约束

- 仅使用兼容 URP 的 Shader；不得依赖 Built-in Shader。
- 支持 GPU Instancing 的材质应开启 Instancing。
- 透明材质仅用于玻璃等必要区域，避免大面积透明叠层和过度 Overdraw。
- 单模块建议不超过 3 个材质槽；超过时 Authoring Validator 给出警告。
- 贴图尺寸、三角形数、透明面积和材质槽在阶段 1 记录为警告，不阻断效果验证。
- LOD、Collider、合批与运行时 GPU 渲染不属于阶段 1，由后续 Bake/Runtime 阶段处理。

## 6. Authoring 流程

1. 美术按本规范创建 FBX 与 Prefab。
2. 在 `StreetBuildingInstanceModuleCatalog` 中登记 Style、允许目录和模块槽位。
3. 在 `StreetBuildingAuthoring` Inspector 执行 `Validate Catalog`。
4. 执行 `Compile Preview`，确认 Payload 和 SHA-256 稳定。
5. 执行 `Apply & Cook (No Auto Save)`；该操作只更新 `module_source`、`unity_instance_catalog` 和 `style_id`。
6. 检查场景、Console 和引用后，由开发者显式保存 Scene。

任何校验或 Cook 失败都不得保存场景；Applier 会尝试恢复原参数与原 Payload。
