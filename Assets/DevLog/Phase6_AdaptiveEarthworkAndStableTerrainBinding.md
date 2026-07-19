# Phase 6 开发日志：自适应土方约束与稳定 Terrain 绑定

> 文档类型：Phase 6 增量开发日志
>
> 记录日期：2026-07-19
>
> 关联提交：`fc1cf6a3c626821d15ae5148f329c09f662b1823`（提交说明：`6`）
>
> 基线版本：Phase 5 功能提交 `74bc0b0`，Phase 5 日志提交 `f6a1ad7`
>
> 记录范围：只记录提交 `fc1cf6a` 相对其父提交 `f6a1ad7` 新增、调整、替换或移除的内容

## 1. 日志范围与证据

本文不是 Terrain 系统全量快照。Terrain 基础 HeightField、Track 精确贴合、Guide Mesh、Lake 约束、三路固定输出和 Unity Terrain 接入分别以 Phase 4、Phase 5 日志为准。

证据标记：

- **[已验证]**：通过 Git 父子差异、HDA 独立结构快照、当前 Houdini Session 强制 Cook、Geometry/Metadata 读取、Unity MCP 或场景 YAML 直接确认。
- **[提交已实现]**：功能已经进入提交 `fc1cf6a`，但仍缺代表性压力样例、Bake 资产或移动端最终验收。
- **[待修复]**：实现已经存在，但当前数据链路存在可复现缺陷，不能按完整交付处理。
- **[未改变]**：沿用前一阶段契约，本阶段没有扩展对应交付范围。

提交 `fc1cf6a` 修改 5 个文件：

| 文件 | Phase 5 | Phase 6 | 变化 |
|---|---:|---:|---|
| `Assets/PCG/HDA/Terrain.hda` | 88,660 bytes | 98,490 bytes | +9,830 bytes；新增自适应土方、细节恢复与验证网络 |
| `Assets/PCG/HDA/Track.hda` | 56,621 bytes | 56,621 bytes | 二进制容器重写；HDA Section、节点和参数无功能差异 |
| `Assets/PCG/Scenes/PCG.unity` | 2,565,860 bytes | 2,604,415 bytes | 保存 Terrain/Track Recook 状态并启用绑定组件 |
| `Assets/PCG/Scripts/Authoring/TerrainTrackDisplayBinding.cs` | 353 行 | 348 行 | +19/-24；移除 Track 主动 Reload，整理状态与重试逻辑 |
| `HoudiniProject/PCG_Track_21.0.440/PCG_Bike_Terrain.hip` | 674,627 bytes | 391,285 bytes | 保存当前 Terrain 验证现场并压缩 HIP |

本提交没有修改上述资产的 `.meta`。主 HDA GUID 保持不变：

- `Terrain.hda`：`15a73d0f61bb98040ae78ced958c3bf9`
- `Track.hda`：`a8929706c44d3b04abb57a0bd73cac39`

## 2. Phase 6 提交概览

| 模块 | 本阶段增量 | 当前状态 |
|---|---|---|
| Road Conform | 改为核心精确贴合、Cut/Fill 低频塑形、外沿原始高频细节恢复 | [已验证] |
| 自适应土方 | 按最大坡度和最大半径传播 signed deformation 包络 | [已验证] |
| 细节恢复 | 路外恢复原始高频细节，并提供可关闭的低成本微地形噪声 | [已验证] |
| 安全约束 | 超坡、半径不足、Manual Domain 不足或道路净空失败时阻止有效 Cook/Bake | [已验证] |
| Metadata | 契约由 `1.3` 升级到 `1.5`，增加土方设置和质量指标 | [待修复：Output 1 指标当前被写成 0] |
| Unity 绑定 | 只在 Terrain 侧必要时 Reload，避免 Track Reload 循环和路径抖动 | [已验证] |
| Unity 场景 | 统一对象名为 `Terrain1` / `Track1`，启用自动绑定并保存 Recook 输出 | [已验证] |
| Track HDA | 没有节点、参数、连接或 Section 内容变化 | [未改变] |
| Shader/渲染 | 无 RendererFeature、RenderPass、RT、Shader 或 keyword 变化 | [未改变] |

本阶段仍属于 Houdini/Unity 编辑器期生成。移动端运行时只应消费 Bake 后的 Unity 原生 Terrain/Mesh/Collider/Metadata，不允许依赖 Houdini Cook。

## 3. Terrain HDA 结构差异

### 3.1 父子版本只读对比

**状态：[已验证]**

本次使用独立 `hython` 进程分别加载父提交与当前提交的 `Terrain.hda`。对比过程没有切换分支、覆盖项目 HDA 或修改当前 Houdini 场景。

| 项目 | Phase 5 | Phase 6 |
|---|---:|---:|
| `TerrainCore` 直接子节点 | 140 | 170 |
| 新增节点 | - | 33 |
| 移除节点 | - | 3 |
| HDA `Contents.gz` | 56,879 bytes | 65,439 bytes |
| HDA `DialogScript` | 26,523 bytes | 27,583 bytes |
| HDA 类型 | `pcgbike::Terrain::1.0` | 不变 |
| Metadata Contract | `1.3` | `1.5` |

新增节点按职责分为：

```text
基础贴合
  CONFORM_BASE_LOW

自适应约束与传播
  ADAPTIVE_enable_switch
  ADAPT_measure_grid
  ADAPT_seed_layers
  ADAPT_seed_constraints
  ADAPT_conflict_detect
  ADAPT_SLOPE_LOOP_BEGIN / END
  ADAPT_slope_propagate
  ADAPT_slope_propagate_upper
  ADAPT_apply_height

细节恢复与微地形
  ADAPT_detail_prepare
  ADAPT_detail_measure_original
  ADAPT_detail_measure_final
  ADAPT_detail_final_copy
  ADAPT_detail_final_blur
  ADAPT_delta_lowpass
  ADAPT_delta_recompose
  ADAPT_micro_detail_noise

最终约束、统计与清理
  ADAPT_FINAL_LOOP_BEGIN / END
  ADAPT_final_slope_project
  ADAPT_measure_clearance_layer
  ADAPT_reduce_slope
  ADAPT_reduce_radius
  ADAPT_reduce_conflict
  ADAPT_reduce_clearance
  ADAPT_reduce_detail_original
  ADAPT_reduce_detail_final
  ADAPT_reduce_micro_peak
  ADAPT_validate_error
  ADAPT_cleanup_internal_layers
```

移除节点：

```text
DEBUG_quickshade
DEBUG_quickshade_switch
GUIDE_MESH_MASK_BLUR（旧旁路节点）
```

### 3.2 网络可维护性

**状态：[已验证]**

新增两组具名 Network Box：

- `ADAPTIVE_EARTHWORK`：网格测量、约束种子、坡度传播、冲突检测和最终验证。
- `ADAPT_DETAIL_RESTORE`：原始细节测量、低频变形重组、细节恢复和微地形。

Road Conform 分区说明更新为：

```text
Road Conform / 道路贴合：核心精确净空 + Cut/Fill 低频塑形 + 外沿地形细节恢复
```

新增 Sticky Note 明确算法边界：

```text
自适应缓坡：道路核心保持 clearance；8 邻域传播 signed deformation 包络；
超出最大坡度 / 最大半径 / Manual Domain 时阻止 Bake。Track 不参与修改。
```

现有其他分区仍有 `__netboxN` 通用名称，网络命名债务没有在本阶段全部清理。

## 4. 两尺度 Road Conform

### 4.1 核心精确净空

**状态：[已验证]**

`CONFORM_core_exact_height` 继续保证道路核心按 Track 目标高度减去 Terrain Clearance 精确贴合。道路本身只作为只读约束输入，自适应土方不会反向修改 Track 曲线、路面 Mesh 或 Track HDA。

### 4.2 Cut/Fill 低频塑形

**状态：[已验证]**

新增 `CONFORM_BASE_LOW` 对原始 `height` 生成低频基底，模糊半径至少为 1，并受 `Shoulder Blend` 控制。道路核心外的挖方/填方主要作用于低频地形，而不是直接抹平完整高度场。

该设计把地形拆为：

```text
原始地形 = 低频基底 + 高频残差
最终地形 = 受约束的低频土方 + 按距离恢复的原始高频残差 + 可选微地形
```

相对 Phase 5，主要收益是道路附近仍可维持净空与可控坡度，远离道路后原有山体纹理和细节逐渐恢复，避免整片土方区变成过度光滑的平面。

### 4.3 Domain 自动扩展

**状态：[已验证]**

`HF_DOMAIN` 的自动 Domain 表达式会在启用自适应土方时计入 `Maximum Adaptive Radius`，并预留约两个 voxel 的安全边界。Manual Domain 模式不会静默扩展；若人工范围不足，会进入约束冲突并由验证节点阻止 Bake。

## 5. 自适应土方算法

### 5.1 新增公开参数

**状态：[已验证]**

`Terrain.hda` 新增 `Adaptive Earthwork` 参数组：

| 参数 | HDA 默认值 | 作用 |
|---|---:|---|
| `Enable Adaptive Earthwork` | On | Feature Toggle；关闭时旁路整条自适应链 |
| `Maximum Earthwork Slope` | 28° | 允许的最大生成土方坡度 |
| `Maximum Adaptive Radius` | 128 m | 道路外最大土方搜索与传播半径 |
| `Earthwork Detail Preserve` | 1 | 原始高频细节恢复比例 |
| `Earthwork Detail Restore Width` | 24 m | 道路外细节渐进恢复宽度 |
| `Enable Earthwork Micro Detail` | On | 微地形噪声开关 |
| `Earthwork Micro Detail Amplitude` | 0.5 m | 微地形最大振幅 |
| `Earthwork Micro Detail Size` | 10 m | 微地形空间尺度 |

同时移除公开调试参数 `Debug Quickshade` 与 `Debug Mask`。保留的 Preview/Debug 输出仍为可关闭编辑器功能，不进入移动端发布运行时。

### 5.2 约束种子与所需半径

**状态：[已验证]**

`ADAPT_seed_constraints` 保存未修改的原始高度 `__earthwork_base`，并建立上下两套 signed deformation 约束：

- 道路核心固定为 Track 目标高度减 Clearance。
- 路肩与 Cut/Fill 区提供初始低频变形。
- 自适应范围外环固定为零变形，防止边界漂移。
- 所需半径由路肩结束位置、最小挖填过渡宽度、道路与原地形高差及最大坡度共同决定。

核心关系可概括为：

```text
Required Radius = Shoulder End
                + max(Minimum Grade Width,
                      abs(Target Delta) / tan(Maximum Slope))
```

若所需半径超过 `Maximum Adaptive Radius`，或 Manual Domain 无法容纳该范围，`ADAPT_conflict_detect` 会记录冲突，而不是在边界处强行截断并生成不可控陡坡。

### 5.3 8 邻域 signed deformation 传播

**状态：[已验证]**

`ADAPT_measure_grid` 根据 HeightField voxel 大小计算迭代次数：

```text
Iteration Count = ceil(Maximum Adaptive Radius / Voxel Size) + 2
```

随后使用两个 HeightField Feedback Loop 分别传播下界与上界包络。每轮检查 8 邻域，坡度约束使用 `tan(Maximum Slope - 0.1°)` 留出数值容差。

算法只约束“生成的土方变形量”，不把原始山体自身的自然陡坡错误地判定为违规。核心与外环固定区在传播中保持不变。

### 5.4 高度合成、细节恢复与微地形

**状态：[已验证]**

`ADAPT_apply_height` 将低频土方、原始高频残差和可选微地形重新合成，并将 signed deformation 限制在上下包络内。优先级为：

1. 道路核心精确净空最高优先。
2. 路肩和近路过渡受土方坡度包络约束。
3. 原始高频细节在 `Earthwork Detail Restore Width` 内渐进恢复。
4. 微地形只在路肩外启用，并在最大半径固定外环前淡出。

`ADAPT_delta_lowpass` 的低通半径取细节恢复宽度和 `0.18 × Maximum Adaptive Radius` 的较大值。`ADAPT_delta_recompose` 在上下约束场中值附近重组变形，减少道路外土方区的机械平滑感。

### 5.5 最终投影与 Fail-Closed 验证

**状态：[已验证]**

最终 Feedback Loop 对“生成变形量”再执行 8 邻域坡度投影，迭代次数为测量值的两倍。道路核心、路肩、细节恢复固定区和外环不会被最终投影破坏。

`ADAPT_validate_error` 在以下任一条件成立时产生 Houdini Error，阻止不合格结果继续 Bake：

- 约束冲突数大于 0；
- 最大生成土方坡度超过参数值约 1° 的容差；
- 道路最大净空误差超过 `0.05 m`。

验证消息同时明确 Track 没有被修改。完成统计后，`ADAPT_cleanup_internal_layers` 删除 `__earthwork_*` 临时层，稳定 Output 0 继续只交付 `height`。

## 6. Metadata Contract 1.5

### 6.1 新增设置与质量指标

**状态：[提交已实现]**

Metadata Contract 从 `1.3` 升级为 `1.5`，新增：

```text
terrain_adaptive_earthwork_enabled
terrain_maximum_earthwork_slope_deg
terrain_maximum_adaptive_radius
terrain_earthwork_detail_preserve
terrain_earthwork_detail_restore_width
terrain_earthwork_micro_detail_enabled
terrain_earthwork_micro_detail_amplitude
terrain_earthwork_micro_detail_size

terrain_earthwork_voxel_size
terrain_earthwork_iteration_count
terrain_max_generated_delta_slope_deg
terrain_max_generated_slope_deg        # 兼容别名，Phase 6 起语义为 delta slope
terrain_required_radius_max
terrain_constraint_conflict_count
terrain_max_road_clearance_error
terrain_original_detail_rms
terrain_final_detail_rms
terrain_detail_preservation_ratio
terrain_micro_detail_peak
```

内部 Mask 名单增加 `earthwork_conflict`。该层用于内部诊断，不进入稳定 Output 0 的 `height` 主交付。

### 6.2 当前 Metadata 指标写入缺陷

**状态：[待修复]**

当前 Houdini Cook 可在 `ADAPT_reduce_micro_peak` 和 Output 0 的 detail attributes 读到真实指标：

| 指标 | 当前现场值 |
|---|---:|
| Voxel Size | `0.998046875 m` |
| Iteration Count | `131` |
| Max Generated Delta Slope | `27.900768°` |
| Required Radius Max | `107.100914 m` |
| Constraint Conflict Count | `0` |
| Max Road Clearance Error | `0.00028877 m` |
| Original Detail RMS | `0.5801113` |
| Final Detail RMS | `0.5873049` |
| Detail Preservation Ratio | 约 `1.0124` |
| Micro Detail Peak | `0.1469516 m` |

但 Output 1 Metadata 上述测量指标当前全部写成 0，只有设置值正确；`terrain_detail_preservation_ratio` 因零值保护表现为 1。父子 HDA 与现场读取表明，`METADATA_write_contract` 对上游 detail 数据的引用没有把真实测量值传递到 Metadata 输出。

因此本阶段只能确认“字段和内部测量已实现”，不能宣称 Output 1 的土方质量指标可被 Unity/Bake 工具可靠消费。后续应修正引用路径或显式合并 detail attributes，并增加非零断言测试。

## 7. Unity 编辑器绑定改进

### 7.1 `TerrainTrackDisplayBinding` 调整

**状态：[已验证]**

脚本保留 Track Cooked/Reloaded 与 Terrain Reloaded 事件订阅、`0.25 s` 重试间隔和 `15 s` 超时，但修改了 Reload 所有权：

- 移除 `_trackReloadRequested` 状态。
- `TryRequestReloads()` 收敛为 `TryRequestTerrainReload()`。
- Track AssetID 无效时不再主动调用 `track.RequestReload()`。
- 只在 Terrain Session/AssetID 无效或隐藏参数尚不可用时请求 Terrain Reload。
- 当 Track Display SOP 路径已经一致时，明确记录“不需要 Terrain Cook”。
- 原乱码状态字符串替换为可读英文状态，便于 Inspector 和 Console 定位等待原因。

该修改减少 Track 重载、Houdini 节点重命名和 Display SOP 路径变化互相触发的循环。脚本位于 Editor-only authoring 链路，没有 Player 运行时成本。

### 7.2 Unity 场景 Recook 状态

**状态：[已验证]**

`Assets/PCG/Scenes/PCG.unity` 保存了新的 HDA 现场：

| 项目 | Phase 5 | Phase 6 |
|---|---|---|
| Terrain Asset Name | `Terrain14` | `Terrain1` |
| Terrain Total Cook Count | 5 | 15 |
| Terrain Always Overwrite On Load | Off | On |
| Track Asset Name | `Track13` | `Track1` |
| Track Total Cook Count | 4 | 6 |
| Binding Component | Disabled | Enabled |
| Last Track Display SOP Path | `/obj/Track13/Road` | `/obj/Track1/Road` |

Track 生成对象名称同步规范化为：

```text
Track1_OUT_ROAD_MESH_OUT_ROAD_MESH_0
Track1_OUT_ROAD_SHOULDERS_OUT_ROAD_SHOULDERS_0
Track1_OUT_ROAD_COLLISION_OUT_ROAD_COLLISION_0
```

Terrain 输出仍为单个 `513 × 513` HeightField/Terrain，高度主输出只包含 `height`。场景 HDA GUID 与主 `Terrain.hda` / `Track.hda` 的 `.meta` 保持一致。

提交中的 Unity Terrain 参数并非全部采用 HDA 默认值，特别是：

```text
Maximum Earthwork Slope = 28°
Maximum Adaptive Radius = 400 m
Detail Preserve = 1
Detail Restore Width = 24 m
Micro Detail = On, 0.5 m / 10 m
Shoulder Blend = 40 m
Cut Slope = 9.325398°
Fill Slope = 10°
```

`Maximum Adaptive Radius = 400 m` 会显著放大编辑器 Cook 成本，应视为场景调参而不是推荐默认值。

### 7.3 Bake/版本管理遗留

**状态：[待修复]**

场景引用的 TerrainData GUID 为 `d4e45b44006984e43bc32e236be6b10a`，但当前 Git 跟踪文件中没有对应的 TerrainData 资产或 `.meta`。提交保存了 Recook 场景状态，不等于已经形成可在干净工作区稳定还原的 Unity 原生 Bake 交付。

后续必须把 TerrainData、Collider、Material 和 Metadata 纳入明确的 `Assets/PCG/Generated/...` Bake 路径，并验证 Recook 不覆盖地编锁定内容。

## 8. Houdini 验证 HIP

**状态：[已验证]**

`PCG_Bike_Terrain.hip` 保存为当前 Terrain 验证现场，主要对象：

```text
/obj/TEST_Track
/obj/TEST_Track_Output
/obj/Terrain1
```

相对 Phase 5 HIP，Terrain1 主要调参变化包括：

- `Terrain Clearance`：`0.05 → 0.2 m`
- `Core Extra Width`：`0.5 → 0.75 m`
- `Shoulder Blend`：`4 → 6 m`
- `Cut Slope`：`24 → 18°`
- `Fill Slope`：`30 → 22°`
- Track Context：Off → On
- Context Width：`60 → 40 m`
- Context Strength：`0.65 → 0.2`
- Context Max Delta：`40 → 6 m`
- `track_geometry` 指向 `/obj/TEST_Track_Output/OUT_TRACK_FOR_TERRAIN`
- Terrain HDA 实例由解锁状态恢复为锁定状态

当前 HIP 使用 HDA 默认 `Maximum Adaptive Radius = 128 m`，与 Unity 场景保存的 `400 m` 不同；两者分别用于 Houdini 验证和 Unity 场景调参，不能混为同一组性能数据。

本次编写日志只进行了读取与强制 Cook，没有执行 `allowEditingOfContents()`，没有保存 HDA 或 HIP。当前 Live Session 在验证后报告有未保存变化，因此不把“现场脏状态”计入提交内容。

## 9. Track HDA 差异结论

**状态：[已验证；未改变]**

虽然 Git 把 `Track.hda` 记录为二进制变化，但独立父子快照确认：

- 54 个递归节点完全一致；
- 无新增、移除或修改节点；
- 参数、连接、注释、Bypass 状态完全一致；
- `Contents.gz`、`DialogScript`、Create/ExtraFile 等 HDA Section 内容与哈希一致；
- 类型继续为 `pcgbike::Track::1.0`。

因此该文件变化属于 HDA 二进制容器/库元数据重写，不应写成 Phase 6 的 Track 功能开发。

## 10. 性能、URP 与移动端结论

### 10.1 CPU/Houdini 与 GPU/Unity 分工

| 阶段 | CPU/Houdini | GPU/Unity | 结论 |
|---|---|---|---|
| 编辑器 Cook | HeightField 多轮传播、细节测量、冲突验证 | 仅预览 | 本阶段主要成本，允许离线但需控制迭代规模 |
| Bake | 转换 TerrainData/Mesh/Collider/Metadata | 无额外渲染逻辑 | 当前自动化和资产落盘仍不完整 |
| 移动端运行时 | 禁止 Houdini Cook | 渲染 Bake 后原生 Terrain/Mesh | Phase 6 不新增运行时 CPU 生成 |

### 10.2 主要性能风险

**状态：[已验证；真机与大场景待测]**

迭代次数与 `Maximum Adaptive Radius / Voxel Size` 近似线性增长。当前 Houdini 验证现场为：

```text
128 m / 0.998 m ≈ 129
测量迭代数 = 131
初始传播约 131 轮
最终投影约 262 轮
合计约 393 轮 HeightField Feedback 迭代
```

Unity 场景保存的 `400 m` 半径在约 1 m voxel 下会进一步放大到数百轮初始传播和约两倍最终投影，是当前最显著的编辑器 CPU/Cook 风险。

优化顺序建议：

1. 先按道路 Chunk/局部 Domain 限制处理范围。
2. 将场景半径收敛到实际所需值，避免把 400 m 作为常规默认。
3. 评估多分辨率传播或低分辨率约束场，再回写高分辨率细节。
4. 为 128/256/400 m 半径建立 Cook 时间、内存和峰值 voxel 数基准。

### 10.3 URP/Shader/Variant

- 本提交没有新增 `ScriptableRendererFeature`、`ScriptableRenderPass` 或 RenderTexture。
- 没有新增全屏 Blit、MRT 或 Tile-Based GPU 中途 flush 风险。
- 没有修改 Shader、`multi_compile_instancing` 或 `shader_feature_local`。
- 自适应土方是编辑器期几何生成，不增加移动端 Shader Variant、纹理采样或 overdraw。
- 最终移动端成本取决于 Bake 后 Terrain 分辨率、Collider、材质层数、DrawCall 和地形 Shader，而不是本阶段的 Houdini 迭代本身。

## 11. 本版本验证记录

### 11.1 Houdini

- Preflight：通过。
- Houdini：`21.0.440`，RPC `127.0.0.1:18811` 正常。
- MCP Health：`http://127.0.0.1:3055/health` 返回 healthy。
- 当前 HIP：`HoudiniProject/PCG_Track_21.0.440/PCG_Bike_Terrain.hip`。
- Terrain 节点：`/obj/Terrain1`，类型 `pcgbike::Terrain::1.0`。
- Definition：`Assets/PCG/HDA/Terrain.hda`。
- 强制 Cook：成功；顶层 error/warning 为 0/0。
- 递归节点扫描：0 error，19 warning。
- Warning 构成：1 个 Volume Visualize 缺 Alpha；18 个节点存在无效 `name` 属性规格警告，新增 `ADAPT_micro_detail_noise` 也在其中。
- Output 0：1 point / 1 primitive，稳定 `height` 输出。
- Output 1：23 points / 0 primitives，Metadata Contract `1.5`；土方测量指标写 0 的缺陷已复现。
- Output 2：Debug Preview 关闭，因此为空。
- 当前约束结果：Conflict 0，最大 delta slope `27.900768°`，道路净空误差 `0.00028877 m`，未触发验证 Error。
- 本次未解锁 HDA、未保存 `.hda`、未保存 `.hip`。

### 11.2 Unity

- Unity Editor：`2022.3.62f2`，未播放、未暂停、未编译、未更新 AssetDatabase。
- 主场景：`Assets/PCG/Scenes/PCG.unity` 已加载、有效、未脏，Build Index 0。
- `Terrain1`：激活；包含 `HEU_HoudiniAssetRoot` 和已启用的 `TerrainTrackDisplayBinding`。
- `Track1`：激活；包含 `HEU_HoudiniAssetRoot` 和已启用的 `TrackSplineHoudiniSync`。
- 主 `Terrain.hda` / `Track.hda` 已由 Unity AssetDatabase 找到，GUID 与场景引用一致。
- 近 30 分钟 Console Error：0。
- 近 30 分钟 Console Warning：0。

### 11.3 Git 工作区

编写日志前，工作区已有与本任务无关的未跟踪 Terrain Shader 目录和自行车 FBX。本文未修改、移动、删除或纳入这些用户资产。

## 12. 当前状态矩阵

| 功能 | 状态 | 当前结论 |
|---|---|---|
| 两尺度 Road Conform | 已完成 | 核心净空、低频土方和外沿细节恢复链路已验证 |
| 自适应坡度包络 | 已完成 | 8 邻域上下界传播与最终投影可工作 |
| 最大半径/Domain 冲突 | 已完成 | Fail-Closed Error 可阻止超约束 Bake |
| 原始细节恢复 | 已完成 | RMS 测量和距离恢复已实现 |
| 微地形 | 已完成 | 有独立 Toggle、振幅和尺度参数 |
| Metadata 1.5 字段 | 部分完成 | 设置字段正确，测量字段 Output 1 当前为 0 |
| Unity Terrain/Track 绑定 | 已完成 Phase 6 | Terrain 负责必要 Reload，Track 不再被绑定器主动 Reload |
| Unity Recook 场景 | 已完成 | 对象、组件和输出层级已保存 |
| Unity 原生 Bake 交付 | 未完成 | TerrainData 未纳入 Git 跟踪的稳定生成路径 |
| Track HDA 功能 | 未改变 | 二进制重写但无结构或参数差异 |
| 运行时渲染 | 未改变 | 无新增 Pass、RT、Shader 或 Variant |
| 移动端真机 Profiling | 未执行 | 需在 Bake 后 Terrain 上验证 GPU/带宽/内存 |

## 13. 下一阶段建议

1. 修复 `METADATA_write_contract` 的土方测量值传递，给 Output 1 增加非零指标自动断言。
2. 为最大坡度、半径不足、Manual Domain 不足、极端挖方/填方建立 Houdini 自动化回归样例。
3. 对 `128 / 256 / 400 m` 半径与不同 voxel 尺寸做 Cook 时间、内存峰值和迭代次数基准。
4. 评估局部 Chunk Domain 或多分辨率约束传播，避免 400 m 高分辨率全域迭代成为编辑器瓶颈。
5. 把 TerrainData、Collider、Material 和 Metadata 纳入 `Assets/PCG/Generated/` 下的稳定 Bake Pipeline，并保留地编覆盖。
6. 清理剩余 HeightField 节点的无效 `name` 属性警告和 Volume Visualize Alpha 警告。
7. 在 Android Mali/Adreno 与 iOS Metal 上验证 Bake 后 Terrain 的 DrawCall、SetPass、带宽、内存和地形 Shader 成本。

