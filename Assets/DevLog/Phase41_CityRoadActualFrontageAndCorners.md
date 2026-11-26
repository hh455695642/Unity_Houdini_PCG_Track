# Phase 41 开发日志：CityRoad 按真实立面排楼、路口角楼与局部商业街

> 记录日期：2026-11-26
>
> 主提交：`62290cd7f30160d896b18dc317780dd322aeed2e`（`41`）
>
> 对比基线：`fc013c5f5b77a2a95492e9521936b230e2e843e1`（`Phase 40`）

Phase 40 为城市测试场景接入了四风格整栋建筑库；Phase 41 改变的是**这些楼如何沿街排布**。CityRoad 不再用统一假定宽度推算墙缝，而是按每个 Prefab 的首层临街墙面量距，另用完整占地判断碰撞。路口可放双临街面角楼，指定街段也可用地编制作的商业街替换。三者是不同机制，不等于测试场景已启用所有效果。

## 1. 版本与职责

Unity `6000.3.22f1`、URP `17.3.0`、Houdini `21.0.440`。提交更新了 `Assets/PCG/HDA/City/CityRoad.hda`、`PCG_Bike_CityRoad.hip` 和测试场景 `Assets/PCG/Scenes/PCG_City_Test.unity`。Unity MCP 从 `1.13.0` 升至 `1.14.3`，Unity Pipeline 从 `1.0.0` 升至 `1.0.1`。

生成请求保存在 **CityRoad HDA 实例**，由 SOP `CityRoadCore/CR_BUILDINGS/BUILD_FRONTAGE` 求值。Unity 编辑器只提供 Prefab 素材规格，以及特定场景的局部替换关系；不保存第二套间距、退距或抽样规则。

## 2. 普通街段：把墙缝和占地分开计算

- **临街墙面**：`CityRoadFrontageCatalog` 在 Prefab 根局部坐标中，以 +Z 为朝街方向。未人工标注时，从有效 BoxCollider 的最前侧提取最长连续墙段；凹入部分不虚增墙宽。碰撞占地则另计碰撞盒及启用 Renderer 的外挑范围。非对称 Prefab 在转换到 Houdini 时处理 X 轴反向；既无可测墙面又无有效标注时报告缺失，不沿用旧规格。
- **沿街接排**：沿街测量相邻两栋首层主立面的端点，每条接缝只抽样一次。某个候选放不下时，在同一站位试换规格，不重新抽缝。算法按最小墙缝预判哪些规格能接下一栋，避免一栋外挑建筑截断整排；普通街段遇实体障碍可在障碍后重新起排。障碍断点、主动留空及街段尾余量单独记录，不混入正常墙缝。
- **诊断与重放**：输出点同时记录请求净距 `frontage_gap_requested` 和实际净距 `frontage_gap_measured`；明细另有缺失规格、未排满街段、约束断点和留空地块。布局抽样与外观选择分开，同规格更换外观不应移动地块。

| HDA 实例参数 | 提交 41 的最终语义 | 城市测试场景保存值 |
|---|---|---|
| 楼与楼净间距 | 绝对最小／最大值，单位米；等端点固定，不等端点每条墙缝抽一次。不是中心距或额外间距。 | 0.7–2.4 m |
| 人行道外退距 | 始终使用相对人行道外缘的绝对区间。仅当两端不等时，普通楼才可按组共享退距基准并叠加组内偏移。 | 2–约 5.968 m；分组关闭 |
| 留空概率 | 以百分比区间表达，实际留空地块另记 ID、位置和宽度，不计作超宽墙缝。 | 0–0% |
| 基座高度 | 普通楼、角楼共用一个相对路面的固定竖向偏移；正值抬高、负值下沉，新实例默认 0 m。 | 保留已有实例的 +0.6 m |

旧固定宽深、间距增量、模式开关及高度区间不再是新的生成入口。区间倒置或超出合法范围时，SOP 报出具体字段，不通过悄悄交换、截断端点来继续生成。

## 3. 路口：按两面临街墙放角楼

`CityRoadCornerCatalog` 为候选 Prefab 标注主墙、次墙和左右侧别。SOP 在同标高路口合并重复进路，检查有真实街边的近直角扇区（90° ± 6°）；T 形路口的敞开侧不放角楼。通过占地和道路检查后，角楼两侧分别按对应街边退距定位，再从角楼向街段接排普通楼。双端都有角楼时，远端放不下的长度单列为尾余量。

**资产已接入，测试场景未启用自动角楼**：提交的 `Authoring/CityRoadCornerFrontages.asset` 有 3 条角楼素材标注；`PCG_City_Test.unity` 保存 32 个普通楼槽、2 个角楼槽，但 `building_corners_enabled` 为关。素材条数、实例候选数、实际生成数不能互换。

## 4. 局部商业街：保留人工替换，又能回到原排布

- **资产**：`Assets/PCG/Generated/Buildings/PCG_City_Test/CityRoad1/WideShops/` 新增 `Shop14`、`Shop18`、`RoofAc12` 三个整栋 Prefab、六份 Near／Far 网格，以及原生 Bake 素材和独立制作场景。主测试场景按 Prefab GUID 可查到三者分别有 2、2、3 条实例记录；这不是七栋可见建筑的证明。
- **场景**：`Commercial Street - West Junction` 下的 `Local Frontage Authoring` 是 EditorOnly 描述对象，记录 25 栋原楼的源 Prefab 与局部位置、旋转、缩放。提交时替换组 `Buildings` 的 `m_IsActive` 为 0，不能仅凭组名或引用断言商业街已显示。
- **预览与 Bake**：编辑器按源 Prefab 和变换匹配原楼，不依赖 Recook 后可能改变的实例编号。匹配唯一且无覆盖冲突时才隐藏原楼、显示替换组；无效绑定关闭替换并恢复能识别的原楼。Bake 前校验 Live 绑定，更新后再校验原生实例。冷 Recook、Reload 和安全 Rebuild 则负责重新同步素材规格，不覆盖实例的生成请求。

## 5. 验证、性能与交付边界

| 状态与证据 | 结果 |
|---|---|
| 已完成 · 已验证：HIP 普通楼排布 | 用 Houdini 21.0.440 的独立 `hython` 加载提交版 HIP，强制 Cook `/obj/CityRoad_DEV/CityRoadCore/CR_BUILDINGS/BUILD_FRONTAGE`。136 条边界段、8 种有效规格，输出 688 个点，目标节点无 error／warning。该 HIP 实例使用固定 0.3 m 墙缝：653 条有效接缝的输出净距为 0.299988–0.300003 m，与请求最大偏差约 0.0000123 m；另报 16 个约束断点。此结果不是 Unity 测试场景 0.7–2.4 m 请求的验收。 |
| 已完成 · 已验证：提交内容与接线 | 从提交树、Unity 序列化场景及 Prefab GUID 核对第 2–4 节的配置、绑定及资产数。未修改或保存当前 Live HIP、Unity 场景或 Bake 产物。 |
| 部分完成 · 待复验：累计回归可复现性 | 提交登记 V56 净间距、V57 街段参数区间、V58 始终按真实立面、V59 街排续接；门禁也将 CityRoad 的 HDA／HIP 持久化纳入授权检查。但验证入口依赖的 `validate_cityroad_gap_range.py`、`validate_cityroad_layout_ranges.py`、`validate_cityroad_corners.py` 在工作区未跟踪，不在提交 41 中。本轮未将它们计作交付，也未宣称干净检出可跑通 VerifyFull。 |

本期新增计算在编辑器与 Houdini Cook 侧。移动端仍消费 Bake 后的 Unity 资产，没有新增运行时 Houdini 依赖、Shader、关键字或 RenderPass。尚待验证的是 Unity 保存重开与重新 Bake 后的局部替换、启用角楼后的两侧实测墙缝，以及街排加密对移动端可见建筑数、Draw Call 和帧时的影响。
