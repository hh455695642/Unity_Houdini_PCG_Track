# Phase 2 开发日志：道路 Banking 与 Unity Spline Knot Contract

> 文档类型：Phase 2 增量开发日志
>
> 记录日期：2026-07-14
>
> 关联提交：`9abb625`（2.1）、`9404214`（2.2）
>
> 当前主提交：`9404214`（2.2）
>
> 基线版本：Phase 1 `ce4bfe2`
>
> 记录范围：只记录 Phase 1 之后在 2.1、2.2 中新增、调整、替换或移除的内容

## 1. 日志范围

本文不是项目全量快照。Unity/URP/Houdini 版本、既有道路 Sweep、UV3、材质混合、起点 Prefab、目录结构和移动端通用约束以 `Phase1_PCGTrackFoundation.md` 为准，不在此重复。

证据标记：

- **[已验证]**：通过提交差异、Unity MCP、Houdini MCP 或当前 HDA 强制 Cook 确认。
- **[提交已实现]**：实现已进入 2.1/2.2，但本次没有在干净联调环境重新执行完整测试。
- **[待复验]**：已有实现，仍缺干净 Houdini Engine Session、Bake 或目标设备验证。
- **[已移除]**：Phase 1 或 2.1 中存在，2.2 已删除，不属于当前接口。

## 2. 阶段提交概览

| 版本 | 提交 | 本次增量 |
|---|---|---|
| 2.1 | `9abb625` | 新增道路 Grade/Curvature/Banking Frame、Spline Knot Roll、Banking Debug、最终道路碰撞分组；调整道路 Shader 的方向性/非方向性 UV 分工 |
| 2.2 | `9404214` | 新增 Unity Knot Contract V1、Spline 自动 Recook、HDA Bezier 重建与 authored-up 传播；重构 Profile；移除自动急弯改线、材质边界补样和手工 Banking Ramp；整理 Road SOP 网络 |

## 3. 2.1 开发内容

### 3.1 道路 Grade、Curvature 与 Banking

**状态：[已验证]**

Road 主链新增独立姿态模块：

```text
FRAME_decode_unity_rotation
  -> FRAME_compute_grade_bank
  -> FRAME_apply_grade_bank
  -> TOPO_rebuild_road_quads
```

- `FRAME_decode_unity_rotation`：从输入点 `rot` 解码 authored-up 与 Knot Roll。
- `FRAME_compute_grade_bank`：计算三维切线、纵坡、曲率、目标倾角和平滑后的最终 Frame。
- `FRAME_apply_grade_bank`：只按最终 tangent/lateral/up 重建横截面，不承担倾角策略计算。
- `DEBUG_bank_frames`：可选显示 tangent、lateral、up，默认关闭。
- 起点 Prefab 朝向改为使用 `road_start_forward + road_start_up`，支持纵坡和 Banking。

新增 HDA 参数：

| 参数 | 默认/当前接口 | 职责 |
|---|---:|---|
| `enable_road_banking` | Off | Banking 总开关 |
| `bank_design_speed_kph` | 25 | 自动倾角设计速度 |
| `bank_auto_strength` | 1 | 自动 Banking 强度 |
| `bank_max_angle_deg` | 8° | 最大绝对倾角 |
| `bank_transition_length_m` | 24 m | 倾角过渡距离 |
| `bank_use_spline_knot_roll` | On | 使用 Unity Knot Roll |
| `debug_bank_frames` | Off | 调试 Frame 输出 |

自动 Banking 根据设计速度和曲率生成目标角度，经过最大角度 Clamp 与按道路距离限制的过渡平滑后应用。关闭总开关时不改变道路顶点。

新增主要数据契约：

- Point：`road_bank_deg`、`road_bank_target_deg`、`road_grade_deg`、`road_curvature_inv_m`。
- Point：`road_spline_roll_deg`、`road_has_spline_roll`。
- Point：`road_frame_tangent`、`road_frame_lateral`、`road_frame_up`、`road_authored_up`。
- Detail：`road_banking_enabled`、`road_spline_knot_roll_enabled`、`road_bank_design_speed_kph`、`road_bank_transition_length_m`。
- Detail：`road_max_abs_bank_deg`、`road_max_abs_grade_deg`、`road_max_abs_spline_roll_deg`。
- Detail：`road_start_up`、`road_start_bank_deg`、`road_start_grade_deg`、`road_start_spline_roll_deg`。

### 3.2 最终道路碰撞分组

**状态：[提交已实现]**

- 新增 `rendered_collision_geo` primitive group。
- 验证脚本要求该分组覆盖最终道路全部三角形。
- 后续 Bake Pipeline 可直接按该 group 生成与渲染面一致的 MeshCollider。

### 3.3 Shader UV 策略调整

**状态：[已验证；真机待测]**

本次只记录相对 Phase 1 的变化：

- Base 层固定使用道路流向 UV0，保证车道线和方向性纹理连续、居中。
- Mask R/G/B 非方向性层可通过 `_UseLowDistortionUV` 在 UV0 与世界投影 UV3 间切换。
- `_UseLowDistortionUV` 的 Shader 默认值和 `M_PCG_Road.mat` 提交值改为 0。
- 开关仍为 runtime uniform，没有增加自定义 keyword 或 Shader Variant。
- Forward 采样数量没有增加，仍为最多 5 次。

## 4. 2.2 开发内容

### 4.1 Unity Knot Contract V1

**状态：[提交已实现；当前现场验证成功]**

新增项目自有 `PCGTrackSplineInputInterface`。它以更高优先级接入 Houdini Engine 输入系统，但只处理显式挂载并启用 `TrackSplineHoudiniInputSettings` 的 `SplineContainer`；未启用对象继续使用 Houdini Engine 官方 Spline 接口。

Unity 不再为项目自定义接口预采样密集折线，只上传原始 Knot 数据：

| Owner | 属性 | 内容 |
|---|---|---|
| Point | `P` | Knot 位置 |
| Point | `rot` | 归一化 Knot 朝向 |
| Point | `unity_tangent_in/out` | 旋转并变换后的相对 Handle |
| Point | `unity_knot_index` | Knot 序号 |
| Point/Primitive | `unity_spline_index` | Spline 序号 |
| Primitive | `unity_spline_closed` | 开闭环状态 |
| Primitive | `unity_spline_knot_count` | 原始 Knot 数 |
| Detail | `unity_spline_contract_version` | 当前为 1 |
| Detail | `unity_spline_contract_valid` | 上传端校验标记 |
| Detail | `unity_spline_contract_source` | `UnitySplineContainer` |

输入使用 Linear Carrier Curve 承载 Knot 属性：

- `isPeriodic = false`。
- 闭环只由 `isClosed` 表达，避免 periodic 与 closed 组合造成额外周期点或原生 HAPI 不稳定。
- 开环最少 2 个 Knot，闭环最少 3 个 Knot。
- 支持单个 `SplineContainer` 内多条 Spline 分支上传并 Merge。
- 上传前检查 Position、Rotation、Handle 的有限数值与四元数单位长度。

### 4.2 HDA Bezier 重建与 authored-up 传播

**状态：[已验证]**

新增节点链：

```text
CONTRACT_validate_unity_knots
  -> CONTRACT_prepare_direction
  -> CONTRACT_decode_knot_frames
  -> CENTERLINE_rebuild_unity_bezier
  -> CENTERLINE_source_switch
  -> CENTERLINE_resample
  -> FRAME_normalize_authored_up
```

- 校验 Knot Contract 版本、有效标记、Spline/Knot 索引和闭环状态。
- 使用 `P + TangentIn + TangentOut` 在 Houdini 中重建 Cubic Bezier。
- 解码 Knot Rotation，向后续 Banking 传播 authored-up/roll。
- `CENTERLINE_source_switch` 保留官方输入/fallback 兼容路径。
- `sample_spacing` 成为唯一生产采样控制；Unity 的 `_legacySamplingResolution` 只用于旧序列化数据迁移。

### 4.3 Spline 编辑自动 Recook

**状态：[提交已实现；提交快照默认关闭]**

新增 `TrackSplineHoudiniSync`：

- 只在 Unity Editor 工作，不进入 Player 运行逻辑。
- 监听 `Spline.Changed`，不使用运行时 `Update` 轮询。
- 默认 Debounce 0.35 秒，合并连续 Knot 编辑事件。
- HDA/Session 未就绪时异步请求 Reload，15 秒超时后停止并报警。
- 重新绑定 `unity_curve_input` 后请求异步 Cook。
- 提供 `Cook Bound Spline Now` 手动入口。

`9404214` 场景提交快照中：

- `TrackSplineHoudiniSync` 已挂载，但组件关闭。
- `TrackSplineHoudiniInputSettings` 已挂载，但 `EnableKnotDataUpload = false`。
- 相关功能以 Feature Toggle 接入，没有在提交中强制启用。

### 4.4 Profile 原生 SOP 重构

**状态：[已验证]**

Phase 1 的集中式截面生成被拆为：

```text
PROFILE_compute_dimensions
  -> PROFILE_clear_centerline (Blast)
  -> PROFILE_build_polyline (Add)
  -> PROFILE_assign_attributes
  -> PROFILE_cross_section (Null)
```

- 固定输出左肩、车道左、车道右、右肩 4 点开放 polyline。
- `road_band`、`profile_section`、`road_lateral_t` 和宽度 metadata 分步写入。
- 验证脚本新增肩部启停、零肩宽、宽路面、肩部下沉和闭环宽路组合检查。
- 主要拓扑使用 Blast/Add/Null 等原生 SOP，减少黑盒生成逻辑。

### 4.5 删除自动急弯改线

**状态：[已移除]**

2.2 删除 Phase 1 的 Tight Turn Guard 自动外移方案：

- 删除 `tight_turn_guard_enable`、`tight_turn_min_inner_radius`、`tight_turn_transition_length`、`tight_turn_max_offset`。
- 删除 `road_tight_turn` 属性/分组和 Guard 专用统计。
- 删除 `patch_track_tight_turn_guard.py`，历史 backup/recovery 保留。
- `SURFACE_reproject_layout` 不再移动生成中心线。
- 宽发卡弯验证改为检查 `road_generated_center == road_original_center`。

当前策略是保留地编 Spline 作为事实源。极端路宽/小半径问题只做诊断，不允许 HDA 静默改线。

### 4.6 删除材质边界补样

**状态：[已移除]**

- 删除 `CENTERLINE_material_segment_samples`。
- 删除 `road_material_boundary_sample_count`。
- 材质 Start/End 与 Blend Distance 只在现有均匀 Ring 上计算 Mask。
- 材质配置不再改变中心线点数和最终 Mesh 拓扑。

需要更细的材质过渡时，由用户显式减小 `sample_spacing`。

### 4.7 删除手工 Banking Ramp

**状态：[已移除]**

- 2.1 曾加入 `bank_manual_offset_ramp`，2.2 已删除。
- 当前 Banking 来源只保留自动曲率 Banking 与可开关的 Unity Knot Roll。
- 验证脚本同步删除 Manual Ramp 和 additive ramp 用例，并检查旧参数不再存在。

### 4.8 Road SOP 网络整理

**状态：[提交已实现；当前网络已验证]**

新增 `organize_track_road_network.py`，按以下顺序组织节点、Network Box、颜色和 Sticky Note：

```text
01 Centerline / Contract
  -> 02 Profile / Sweep
  -> 03 Layout / Banking
  -> 04 Unity Output
  -> 05 Start Prefab
```

该脚本只允许修改可视化布局和注释：

- 执行前保存 HIP Backup、HDA Backup 和 JSON recovery。
- 记录输出 geometry signature。
- 整理后强制 Cook；若 geometry signature 变化则失败。
- 保存回 `Assets/PCG/HDA/Track.hda`，不调用全量 builder。

新增 `patch_track_road_banking.py` 作为 Banking 的 Live Scene 增量 Patch，采用同样的备份、recovery、Cook 与 definition 保存流程。

## 5. 相对 Phase 1 的变更清单

| Phase 1 状态 | Phase 2 处理 | 当前结果 |
|---|---|---|
| 曲线主要携带位置与基础 `rot` | 新增 Knot Contract V1 | 上传原始 Knot、Handle、Rotation、闭环和索引 |
| Houdini 直接消费输入曲线 | HDA 内重建 Unity Cubic Bezier | `sample_spacing` 成为唯一生产采样入口 |
| 无完整 Banking 主链 | 2.1 新增 Frame/Grade/Curvature/Banking | 2.2 保留 Auto Bank + Knot Roll |
| Tight Turn Guard 自动外移道路 | 2.2 删除 | 保持用户中心线，不再静默改线 |
| 材质边界局部增加 Ring | 2.2 删除 | 材质参数不改变拓扑 |
| 集中式 Profile 生成 | 2.2 拆为原生 SOP 链 | 4 点开放截面契约更可读 |
| 低畸变 UV 可影响所有路面层 | 2.1 拆分 UV 职责 | Base 固定 UV0，非方向层可选 UV3 |
| 手工 Banking Ramp | 2.1 新增、2.2 删除 | 当前接口不再包含 Ramp |
| Spline 修改后手动处理 Cook | 2.2 新增事件同步 | Editor Debounce Recook，Feature 默认关闭 |

## 6. 本阶段验证记录

### 6.1 Houdini

**状态：[已验证]**

- Preflight：18811 RPC、3055 MCP Health、当前会话 Houdini MCP 工具发现均通过。
- 当前 HIP：`HoudiniProject/PCG_Track_21.0.440/PCG_Bike_Track.hip`。
- 当前节点：`/obj/Track1`，类型 `pcgbike::Track::1.0`。
- Definition：`Assets/PCG/HDA/Track.hda`。
- 当前节点已解锁；本次仅只读检查，没有保存 HIP/HDA。
- 强制 Cook 成功。
- `/obj/Track1` 扫描 60 个节点，Error 0，Warning 0。
- Road 当前包含 38 个直接子节点。
- `OUT_ROAD_MESH`：32 Points、42 Primitives、126 Vertices。
- 当前输出包含 Banking/Frame 属性与 `rendered_collision_geo` group。
- 当前 `enable_road_banking = Off`，即接口存在但现场输出未启用自动倾斜。

### 6.2 Unity

**状态：[现场功能通过；提交快照与当前 Dirty 状态不同]**

- Editor 未播放、未暂停、未编译、未刷新 AssetDatabase。
- 主场景已加载且有效，但当前为 Dirty。
- 当前 Dirty 现场中 Knot Contract 已启用。
- 上传诊断：1 条 Spline、73 个 Knot、Closed、`Valid: Knot Contract V1 committed.`。
- `TrackSplineHoudiniSync` 当前已启用，Auto Cook 为 true，Debounce 为 0.35 秒。
- 场景中的 HDA path 仍为 `Assets/PCG/HDA/Track.hda`。
- Console 保留提交前 Houdini Engine Session invalid、No curve 和闭环探针错误；本次未清空历史日志，因此不能记录为干净 Console 验收。

提交与现场差异：

| 项目 | `9404214` 提交 | 当前 Dirty 现场 |
|---|---|---|
| Knot Contract Toggle | Off | On |
| Auto Recook Component | Disabled | Enabled |
| 上传诊断 | Not uploaded | 1 Spline / 73 Knots / Closed / Valid |

当前 Dirty 现场不属于 `9404214` 的已提交内容；是否启用为默认状态需要在后续提交中明确。

### 6.3 验证脚本增量

`verify_curve_road_test.py` 在本阶段新增或调整：

- Grade-only 道路不应产生横向 Banking。
- Knot Roll 解码、开关和最大倾角 Clamp。
- 常半径弯道自动 Banking 公式和外侧抬高方向。
- S 弯正负 Banking 与 Transition Length 变化率。
- 闭环 Banking 接缝。
- Frame 单位长度、正交性、左右手性与有限数值。
- Profile 4 点开放截面及肩部组合。
- 宽发卡弯不改变美术中心线。
- 已删除的 Guard、材质补样和 Manual Ramp 契约不得残留。

本次文档更新只检查脚本内容和当前主 HDA Cook，没有运行会创建临时测试节点的完整验证脚本。

## 7. 本阶段性能影响

只记录相对 Phase 1 的增量：

| 变化 | CPU / 编辑器影响 | GPU / Runtime 影响 |
|---|---|---|
| 原始 Knot 上传 | HAPI 数据量与美术 Knot 数相关，避免 Unity 预采样点膨胀 | 无 |
| HDA Bezier 重建 | 增加编辑器 Cook 计算 | Bake 后无运行时成本 |
| Banking | 随道路 Ring 数近似线性增加 Cook 成本 | 只改变 Bake Mesh 顶点/法线，无逐帧变形 |
| Spline 自动 Recook | Debounce 后触发异步编辑器 Cook | Player 中不执行 |
| 删除材质边界补样 | 拓扑数量更稳定，减少隐式 Cook/顶点增长 | Mesh 带宽更可预测 |
| Shader UV 调整 | 无额外 CPU 工作 | 无新增采样、Pass、RT 或 Variant |

本阶段没有新增 RendererFeature、RenderPass、RenderTexture、Compute Shader、Geometry Shader、透明 Pass 或移动端运行时 Houdini 依赖。

## 8. 当前遗留事项

1. 在干净 Houdini Engine Session 中重新验证 Open、Closed、Multi-Spline、Transform、Rotation 和 Handle 上传。
2. 清空 Unity Console 后执行完整 Knot Contract/Recook 验收，确认没有新的 Session 或 Curve 错误。
3. 在备份场景运行完整 `verify_curve_road_test.py` 并保存结果。
4. 决定 Knot Contract 与 Auto Recook 是否在正式场景默认启用，并提交对应场景状态。
5. 验证 Recook 后材质引用、地编覆盖和 HDA 输出对象命名是否稳定。
6. 后续 Bake Pipeline 消费 `rendered_collision_geo`、道路 Mesh 与 Phase 2 新增 metadata。
7. 道路 Shader 的 UV 策略变化仍需在 Mali、Adreno、Apple GPU 上做带宽和视觉验证。

## 9. Phase 2 结论

Phase 2 的核心交付是两条增量链路：

1. 2.1 建立道路 Grade/Curvature/Banking Frame，并调整方向性与非方向性路面纹理的 UV 职责。
2. 2.2 建立 Unity Knot Contract V1 与 HDA Bezier 重建，使原始 Knot、Handle、Rotation 和闭环语义可稳定进入道路生成链。

同时，2.2 删除自动急弯改线、材质边界隐式补样和手工 Banking Ramp，使地编中心线、道路拓扑和 Banking 来源更可控。当前 HDA 强制 Cook 无 error/warning；Unity Dirty 现场已完成一次 73 Knot 闭环上传，但正式提交默认仍关闭相关 Feature，干净 Session 联调与 Bake 验证尚未完成。
