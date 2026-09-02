# StreetBuilding 美术资产制作规范（V12 / 一 HDA 一 StyleConfig / 面板生成规则）

本规范定义 StreetBuilding 模块化立面资产的长期自建标准。Downtown City MegaKit 仅作为只读验证源，不是项目正式资产模板。

## 1. 目录与命名

每套资产创建一个独立 `StreetBuildingStyleConfig`。配置资产引用本身就是身份；目录名仅用于人工组织，不进入 Payload，也不要求额外维护 Style Id 或 Display Name。

| 内容 | 路径 |
|---|---|
| 模型 | `Assets/PCG/Art/StreetBuilding/<StyleFolder>/Models/` |
| Prefab | `Assets/PCG/Art/StreetBuilding/<StyleFolder>/Prefabs/` |
| 验证细节 Prefab | `Assets/PCG/Art/StreetBuilding/<StyleFolder>/Prefabs/ValidationDetails/` |
| StyleConfig | `Assets/PCG/Art/StreetBuilding/<StyleFolder>/` |
| 材质 | `Assets/PCG/Materials/Buildings/<StyleFolder>/` |
| 纹理 | `Assets/PCG/Art/StreetBuilding/<StyleFolder>/Textures/` |

- 模型：`SM_SB_<Style>_<Role>_<Variant>`
- Prefab：`PF_SB_<Style>_<Role>_<Variant>`
- 材质：`M_SB_<Style>_<Surface>`
- 纹理：`T_SB_<Style>_<Surface>_<Map>`

不得用文件名表达楼层号或建筑实例号；楼层、Cell 和实例身份由生成数据提供。

## 2. 交付单元

- 正式交付单元以 Prefab 为主，裸 FBX Model Prefab 保持兼容。
- 一个逻辑模块可以由 Prefab 内多个 FBX 子节点组成，例如门框与门扇。
- StyleConfig 只保存资产引用、逻辑角色、尺寸和权重，不复制 Mesh、Material 或 Texture。`module_variant` 自动取该条目 `Prefab.name` 的精确文件名（不含 `.prefab` 扩展名），美术不填写额外 VariantId。
- Prefab 根只允许 `Transform`；可见子节点只允许 `Transform`、`MeshFilter`、`MeshRenderer`。
- 当前效果验证 Prefab 禁止脚本、Collider、LODGroup、Light、Animator 和其他运行时行为。

## 3. 坐标、Pivot 与尺寸

- 1 Unity Unit = 1 米。
- `+Y` 向上。
- 面向街道观察立面时，`+X` 向右，`+Z` 为立面朝外方向。
- 建筑内部位于立面平面的 `-Z` 一侧。
- 模块根 Pivot 位于对应网格单元的底部中心，根 Transform 必须为 Position `(0,0,0)`、Rotation `(0,0,0)`、Scale `(1,1,1)`。
- 复合模块的组合偏移和旋转放在 Prefab 子节点内完成；一个模块条目引用一个完整 Prefab。
- 左右边缘立柱的 Pivot 位于建筑边界线，不占用 2m Bay。

当前 `StreetBuilding.HdaPanelGeneration.12.0` 网格：

- Bay 宽度：2m
- 首层高度：4m
- 标准层高度：3m
- 正面、侧面、背面均按 2m Cell 排布，屋顶按 2×2m Tile 排布。
- 允许 2m 单格和 4m 双格立面模块；4m 模块必须声明 `CellWidth=4`，不得与已有占用重叠。
- 建筑保持单个正面入口，侧面和背面禁止入口。
- 体块只允许 `Rectangle` 与等高 `LShape`，不制作 U 形、退台或分层高度模块。
- L 形缺口固定在后左或后右，缺口宽/深均为 2m 倍数，并至少保留 4m 宽的两条翼。

## 4. 无版本 StyleConfig

StyleConfig 编译结果使用 UTF-8、Invariant Culture 和稳定排序：

```text
STYLE|<CellWidth>|<GroundFloorHeight>|<TypicalFloorHeight>
M|Group|Role|Variant|PrefabPath|WidthSpan|DepthSpan|HeightType|ResolvedHeight|Weight|FacadeMask|FloorMask|BoundsX|BoundsY|BoundsZ|BoundsMinX|BoundsMinY|BoundsMinZ
```

- 每个 StreetBuilding HDA 必须显式引用一个独立 StyleConfig，不提供自动风格库或跨风格随机选择。
- 每套资产只维护自己的 StyleConfig；两套风格分别创建、分别维护，HDA 不在 StyleConfig 之间交叉选择。同一 Role 内的不同 Prefab 由 HDA 按生成 Seed 和权重确定性选择。
- `Weight` 必须大于 0；`Role + Prefab.name` 在单个 StyleConfig 内必须唯一。这里的 `Prefab.name` 是精确文件名（不含 `.prefab`），并自动写入 Payload 的 `Variant` 列。
- Payload 不包含 Schema、Style Id、Display Name 或 Module Family；HDA 只接受上述 `STYLE` 头和 18 字段模块行。
- Payload 内容直接参与 SHA-256，修改尺寸、权重、Prefab 路径、Prefab 文件名或局部偏移都会产生新版本。
- 不保留旧版本 Payload 兼容分支；旧格式必须由 Unity 重新编译并写回场景后才能 Cook。
- 不维护人工 VariantId、稳定语义键或跨资产映射；Prefab 的文件名就是本条目的唯一 Variant 值。新增模块时直接登记其 Prefab 引用、Role、尺寸和权重即可。
- Prefab 改名、移动目录或替换后，都必须重新执行“应用风格、Cook 并保存场景”。仅移动目录且不改文件名时，`module_variant` 保持不变，但 Payload 中的路径会变化；改名或替换会使 Payload/SHA-256 与确定性选择基线变化，需以重新 Cook 的结果为准。

完整外壳还需要：

- `GroundWall`、`MiddleBlank`、`SideWall`、`RearWall`
- `RoofSurface`：2×2m 平屋顶 Tile
- `Parapet`：2m 直线女儿墙，根 Pivot 位于底部中心，标准高度 0.6m
- `ParapetCorner`：90° L 形转角，根 Pivot 位于外侧精确转角，局部形体沿 `+X/-Z` 向内延伸
- `ParapetConcaveCorner`：L 形唯一阴角，Pivot 位于凹入轮廓交点；不得用阳角资产靠负缩放镜像。
- `RoofProp` 已从 LOD0 外壳移入独立 `OUT_DETAIL_INSTANCES`

无版本 StyleConfig 模式在 `parapet_height > 0` 时生成连续女儿墙。`Parapet` 与
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
- HDA 只接受 StyleConfig 提供的原始资产路径，输出 `scale=(1,1,1)` 与归一化 `orient`；美术不得依赖生成端非等比缩放。
- Prefab 文件名是自动生成的 `module_variant`，不是人工维护的稳定键。升级资产仍须保持其 Role、占地和挂接面与配置声明一致；若改名、移动或替换 Prefab，必须重新 Apply StyleConfig + Cook。
- `attachment_global_density` 仅控制细节概率，不得改变 LOD0 外壳；`attachments_enabled=false` 或密度为 0 时细节输出必须为空。
- 每栋最多 64 个细节实例；新增细节种类应使用独立 Role 与 Prefab 配方，并复用现有选择种子，不得在 Prefab 内添加运行时脚本。

## 6. 材质与移动端约束

- 墙面、门窗底板、侧/背墙、屋面、檐口、阳角/阴角和女儿墙全部交付为单面开放 Mesh；不得封背、不得额外制作不可见厚度。
- 单面朝向：立面法线朝局部 `+Z`，屋面法线朝 `+Y`；转角各片法线朝建筑外侧。Unity 材质必须 `Cull Back`，`Double Sided GI` 关闭。
- 需要真实体积的独立细节（空调、水箱、烟囱等）可以是闭合 Mesh；“单面”约束只作用于建筑外壳 Role。
- 不允许用双面 Shader、关闭剔除或生成端负缩放补救错误法线；导入后必须检查 Scene View Backface 与 Mesh 法线。
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
| StyleConfig | 1 个，直接覆盖本套资产的全部必需 Role，不包含 Schema、Style Id、Display Name 或 Family |
| 基础/外壳/细节 Role | 覆盖当前 17 个必需 Role |
| 参考 Recipe | 40 个；同一 StyleConfig 内每个 `Role + Prefab.name` 唯一 |
| HDA 示例配置 | Compact / Standard / Corner Tall 直接保存在各 HDA 参数上，不创建 Preset 资产 |
| 共享材质 | 5 个：Wall / Accent / Roof / Glass / Metal |
| 参考贴图 | 5 张 128×128 可平铺程序纹理，仅用于验证色彩、节奏与材质分层 |

参考几何需要主动表现以下视觉层次：首层商业或住宅入口、标准层窗型变化、空白墙节奏、檐口、
边缘立柱、完整侧背立面、连续女儿墙，以及独立输出的雨棚、招牌、消防梯、墙面设备和屋顶设备。
同一风格内不能只靠随机颜色制造差异；至少要通过多个不同 Prefab 改变开窗、分格、挑檐、
阳台/凹槽、后勤门和屋顶轮廓。

参考贴图仅是占位质量基线。正式美术可替换为外部 DCC 导出的 FBX 和正式 PBR 贴图，但 Prefab
路径、Prefab 文件名、Role、Pivot、声明尺寸与 StyleConfig 结构必须保持稳定。若路径、文件名或引用替换，按第 8 节重新 Apply StyleConfig + Cook。

提交前运行：

1. 六栋展示建筑直接维护各自 HDA 面板参数；不得通过 GenerationPreset 或 DesignPreset 覆盖。
2. `PCG/StreetBuilding/Project Owned/Audit Reference Style Kits`，确认依赖只来自当前 Style、对应材质目录、项目 Authoring 脚本与 URP Package。
3. 检查 `PCG_Building` 的正面、侧背面与屋顶；展示固定为 2 栋矩形 + 4 栋左右 L 形，不生成 U 形。
4. 运行 StreetBuilding `VerifyFast` 与 `VerifyFull`，确保 HDA/HIP 累计合同没有变化。

## 8. Authoring 流程

1. 美术按本规范创建 FBX 与 Prefab。
2. 为这套资产创建独立 `StreetBuildingStyleConfig`，登记 Prefab、Role、权重与单面模块；`module_variant` 会自动采用 `Prefab.name`，无需填写 VariantId。将该 StyleConfig 在目标 HDA 的 `StreetBuildingAuthoring` 上显式指定。
3. 在 HDA 参数面板调整体块、立面、附件及唯一的 `Variation Seed`；高级楼层/附件覆盖默认折叠。`Site Source=Internal` 时外部地块 payload 不得覆盖面板，只有 `External` 时允许覆盖。
4. 在 `StreetBuildingAuthoring` Inspector 执行 `验证 / Validate`。
5. 执行 `编译预览 / Compile Preview`，确认 Style Payload 和 SHA-256 稳定。
6. 执行 `应用风格、Cook 并保存场景`；该操作只更新 `module_source`、`unity_style_catalog`、StyleConfig 所属层高和 `unity_bridge_end_marker`，不得改写任何生成参数。
7. 检查前、后、左、右和鸟瞰视图，确认墙顶不越过 roofY、屋面完整覆盖 footprint、
   女儿墙连续，并能看到不同密度的雨棚、招牌、消防梯、墙面 AC 与落地屋顶设备。

任何校验或 Cook 失败都不得保存场景；Applier 会尝试恢复原参数与原 Payload。程序化地块、CityRoad 相邻遮挡、LOD、Collider 和运行时 Cook 均不属于阶段 5。
