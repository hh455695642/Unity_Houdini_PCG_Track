# Phase 39 开发日志：Style4 建筑套件、半格女儿墙与 Bake 目录归档

> 主提交：`7d36880ab51eb43070495a705350229b823f0bb1`（`39`，2026-11-20）
>
> 对比基线：`8f7a8938b7183005ba192c47423d799827d05452`（`Phase_38`）

提交 39 解决了两件与建筑制作直接相关的事：Style4 可以在同一套 2 m 网格上使用两种首层高度；屋顶女儿墙可以按转角模型的实际臂长排布直段。已有 Style2、Style3 的整栋 Bake 也随各自风格归档。**Style4 本次交付到模块和建筑制作场景，没有替换城市测试场景的 Style2 整栋库。**

## 1. 环境与证据

Unity `6000.3.22f1`、URP `17.3.0`、Houdini `21.0.440`。本次更新了 `Assets/PCG/HDA/City/StreetBuilding.hda` 和 `HoudiniProject/PCG_Track_21.0.440/PCG_Bike_StreetBuilding.hip`。工具依赖中，Unity MCP 从 `1.11.3` 升至 `1.13.0`，Unity Splines 从 `2.9.1` 升至 `2.9.2`。

下文的素材数量、路径和场景绑定按**提交 39 的文件**核对，不含工作区未提交的美术资源或迁移脚本。第 5 节单列本次实际执行的 HDA 检查，不把场景中存在样例等同于 Bake 或真机验收。

## 2. Style4：两种首层高度，共用标准层和屋顶

资产位于 `Assets/PCG/Art/Building_Test/Style4/`，包含 **21 个模块 Prefab 和 21 个对应 Mesh**。`SBStyle4_3m.asset`、`SBStyle4_4m.asset` 的格宽均为 **2 m**，标准层高均为 **3 m**；名称中的 3 m／4 m 指**首层高度**，不是模块宽度。

| 模块组 | 数量 | 本次提交内容 |
|---|---:|---|
| 首层 | 12 | 凹角、凸角、门、普通橱窗、带辐条橱窗、实墙六类，各有 3 m 和 4 m 高度版本。 |
| 标准层 | 4 | `MiddleBlank`、`MiddleRearWindow`、`MiddleTimber`、`MiddleWindow`，两套配置共用。 |
| 檐口与屋顶 | 5 | 檐口、女儿墙直段、凹角、凸角、屋面，两套配置共用。 |

`PCG_Building.unity` 保存了 `Style4_Sources` 素材组和四个制作样例：`Style4_N3`、`Style4_L3`、`Style4_W3` 引用 3 m 配置，`Style4_W4` 引用 4 m 配置。提交中未包含 Style4 整栋 Bake Prefab。

Style4 新增 Ivory、OpaqueGlazing、PaintedMetal、Roof、Timber 五份共享材质，使用同一张 `T_Style4_Color.png` 调色板。五份材质均使用现有 URP Lit、不透明、开启 Instancing，未启用材质关键字；贴图启用 sRGB 和 mipmap，关闭 Read/Write。本次没有新增 Shader、RenderPass 或自定义变体，也没有实测 Draw Call 或移动端 GPU 耗时。

## 3. 女儿墙：半格转角如何与直段接合

Style4 的转角模型沿相邻两条边各伸出半格（本套件为 1 m）。HDA 按这个尺寸放置凹凸角，并将直段中心放在格线上，补齐两个转角之间的边。该约定只改变女儿墙的拼接位置，**不改变屋面铺砖，也不决定是否生成女儿墙**。

- **素材声明**：`StreetBuildingStyleConfig` 的屋顶分组新增 `_halfBayParapetCorners`。两份 Style4 配置均启用；它描述模型尺寸约定，不向 HDA 实例写入生成数量或开关。
- **编译检查**：启用时，`StreetBuildingStyleCompiler` 检查直段、凸角和凹角三种屋顶角色是否齐全、是否各占一格，以及 Mesh 边界是否在 0.002 m 容差内达到相应半格尺寸。即使不要求整套素材完整，也会执行此检查。
- **向后兼容**：编译器仅在启用时向素材数据写入 `R|1|half_bay_parapet`。没有该标记的风格仍使用原排布；HDA 不靠缩放模块来填补边长。

## 4. 整栋 Bake：按风格归档，城市仍用 Style2

| 风格 | 提交 39 的归档目录 | 实际内容 |
|---|---|---|
| Style2 | `Assets/PCG/Art/Building_Test/Style2/Baked/` | 8 个整栋 Prefab（00–07），各带 Near、Far 两份网格。 |
| Style3 | `Assets/PCG/Art/Building_Test/Style3/Baked/` | 6 个整栋 Prefab，各带一份 Near 网格；本次没有增加 Far。 |

对比迁移前后的 Git 文件内容，两个目录中的 Prefab、网格和对应元数据均未改变。这是**移动已有产物**，不是重新 Bake。`PCG_City_Test.unity` 中八条路径均改指 Style2 的新目录。提交另补入 Style3 的 `M_SB_Style3_Surface.mat`、`M_SB_Style3_OpaqueGlass.mat` 及其元数据。

`StreetBuildingPipeBake` 同步更新了原生 Bake 目录识别和写入目标检查：在美术目录中只接受 `Assets/PCG/Art/Building_Test/Style<正整数>/Baked/` 及其子目录，不把旁边的模块源目录当作输出目录。查找已有原生 Bake 时仍需匹配网格资产；路径中的上级跳转不视为合法目标。

## 5. 验证结果与边界

新增累计合约 `StreetBuilding.Roof.HalfBayCornerContinuity`。本次用 Houdini 21.0.440 的独立 `hython` 进程加载已提交的 HDA，新建实例执行 `assert_half_bay_parapet`。测试地块为 12 × 10 m、三层、2 m 格宽；验证器从占用格独立计算外露边，与实际 Cook 输出逐边比对。

| 测试轮廓 | 转角数 | 直段数：原排布 → 半格排布 | 屋面块数 | 结果 |
|---|---:|---:|---:|---|
| 矩形 | 4 | 14 → 18 | 30 | 通过 |
| L 形：前左、前右、后左、后右缺口 | 每种 6 | 每种 11 → 16 | 每种 28 | 四种均通过 |

- **已验证**：外露边无遗漏或重复，凹凸角角色、朝向、屋顶高度和单位缩放符合合约；切换拼接方式不改变屋面块数或原有直段的素材选择，重复 Cook 结果一致。
- **已验证**：关闭屋面仍可保留女儿墙，关闭女儿墙不再输出其模块；移除半格标记后恢复原排布。
- **待复验**：专项使用合约测试素材，不能代替真实 Style4 模型接缝的目视验收。本次未连接 Houdini 图形会话，未执行完整累计回归、Unity 整栋 Bake／重开或移动端性能测试。
