# Phase 11 开发日志：手绘海岛海岸与湖面渲染接入

> 文档类型：提交增量快照  
> 记录日期：2026-07-28  
> 目标提交：`15dc472f1bcde6949ebf0f20ab0c9e5e60f70b13`（提交信息：`11`）  
> 父提交：`821f962e2929968c5c483cabf89d5b64696a0952`（Phase10 文档提交）  
> 主场景：`Assets/PCG/Scenes/PCG.unity`  
> Terrain HDA：`Assets/PCG/HDA/Terrain.hda`  
> Terrain HIP：`HoudiniProject/PCG_Track_21.0.440/PCG_Bike_Terrain.hip`

## 1. 日志范围与证据

本文只记录 Git 提交 `15dc472f` 相对父提交 `821f962e` 的开发增量，不重复 Phase 1～Phase 10 已记录的 Track、Terrain、Lake Constraint、Guide Mesh、Adaptive Earthwork、Track 输入守卫与道路净空保护。

本阶段实际包含两条相互独立但在场景中组合使用的链路：

```text
Unity 闭合 Spline
    -> Terrain HDA Island Boundary
    -> 编辑器期 Houdini Cook
    -> Island / Coast / Beach HeightField
    -> Unity Terrain

Unity Plane
    -> M_Map_Lake
    -> NewWorld/Env/Lake
    -> Camera Depth + Opaque Color + Cubemap
    -> 透明湖面预览
```

证据等级：

- **[提交验证]**：直接读取目标提交的 Git diff、场景 YAML、Shader、材质、纹理导入设置和验证脚本。
- **[现场验证]**：通过 Unity MCP、Houdini MCP、当前 Editor/HIP/HDA 现场读取。
- **[隔离验证]**：在独立 `hython` 进程中创建全新 Terrain HDA 实例并 Cook；不保存 HIP/HDA。
- **[待修复]**：实现已经存在，但当前不满足项目移动端、数据合约或端到端验收条件。

提交 11 没有修改 `Assets/Plugins/HoudiniEngineUnity/`，继续符合官方 Houdini Engine Unity 插件零侵入约束。

## 2. 提交概览

| 项目 | 数值 |
|---|---:|
| Commit | `15dc472f` |
| Author / Date | `liyuan` / 2026-07-28 17:03:06 +08:00 |
| Changed Files | 16 |
| Added / Deleted Lines | `+9036 / -10116` |
| 新增湖面资源 | 12 个文件（含 `.meta`） |
| Terrain HDA | 103399 → 118732 bytes |
| Terrain HIP | 841097 → 820388 bytes |
| Terrain 验证脚本 | `+90` |
| Unity 场景 | `+7451 / -10116` |

提交文件按职责分为四组：

1. **手绘海岛海岸**
   - `Assets/PCG/HDA/Terrain.hda`
   - `HoudiniProject/PCG_Track_21.0.440/PCG_Bike_Terrain.hip`

2. **Terrain 参数接口回归**
   - `HoudiniProject/PCG_Track_21.0.440/scripts/tools/validate_terrain_shape_params.py`

3. **湖面渲染资源**
   - `M_Map_Lake.mat`
   - `Lake.shader`
   - `LakeFunctions.hlsl`
   - `ReflectionProbe-1.exr`
   - `T_LakeNoise_5.png`
   - `T_LakeNormal_1.png`
   - 对应 `.meta`

4. **Unity 场景测试与 Recook 结果**
   - `Assets/PCG/Scenes/PCG.unity`

## 3. Terrain HDA 参数接口重组

### 3.1 四个顶级页签

Terrain HDA 参数面板被固定为四个顶级页签：

| 顶级页签 | 直接职责 |
|---|---|
| `Overview / 总览` | 输入/输出契约、Domain、Padding、唯一分辨率 |
| `Terrain Shape / 地形形态` | Seed、Macro/Mid/Detail Noise、Directional Ridge、Erosion |
| `Advanced / 高级` | Track、Guide Mesh、Island Coast、Lake |
| `Output Mask / 输出 Mask` | No Scatter、Cliff、Water Candidate Mask |

当前四页签共暴露 72 个可调值参数：

| 页签 | 参数数 |
|---|---:|
| Overview | 4 |
| Terrain Shape | 16 |
| Advanced | 47 |
| Output Mask | 5 |

`Advanced / 高级` 内部进一步拆为：

```text
Track & Earthwork / 赛道与土方
Guide Mesh / 地形引导
Island Coast / 海岛海岸
Lake / 湖泊
```

`Island Coast` 再分为：

```text
Profile / 横截面
Beach Surface / 海滩表面
```

这次重组把输入、形态、约束和 Mask 输出分开，避免 Terrain 参数继续堆叠成单个超长面板。

### 3.2 清理失效参数

验证脚本明确禁止以下旧参数重新出现：

```text
height_range
min_domain_size
tile_count
```

同时继续检查 `HF_DOMAIN.sizex/sizey`：

- 不得引用已删除的 `use_bake_resolution`
- 不得引用已删除的 `bake_resolution`
- 必须由 `tile_resolution` 驱动

当前实例无 spare parameter-folder override，单一 Terrain Resolution 链路保持有效。

### 3.3 参数接口自动验证

`check_interface_contract()` 新增以下精确契约：

- 四个顶级页签名称和顺序不可漂移。
- Overview 只能直接包含契约、Domain 与 Resolution 参数。
- Advanced 四个子页签的名称和顺序不可漂移。
- Island Coast 必须保留 Profile 与 Beach Surface 两组。
- Output Mask 只包含五个 Mask 参数。
- 已删除参数不得重新进入 Definition 或实例。
- Terrain 实例不得残留 spare parameter override。

该验证对良性重命名也会报错，适合作为参数 UI 合约测试，但后续修改页签名称时必须同步更新脚本。

## 4. 手绘海岛海岸模块

### 4.1 输入与启用条件

新增公共参数：

| 参数 | 默认值 | 职责 |
|---|---:|---|
| `enable_island` | Off | 总开关 |
| `island_boundary` | Empty | 必需的闭合海岸边界 |
| `sea_level` | 0 m | 水平水面参考高度 |
| `coast_transition_width` | 24 m | 边界向岛内的地形融合宽度 |
| `beach_width` | 36 m | 边界向海侧接入海床的宽度 |
| `seabed_depth` | 12 m | 海床高度为 Sea Level - Depth |
| `coast_beach_profile` | 5-key Ramp | Coast/Boundary/Beach 横截面 |
| `coast_blend_sharpness` | 1 | Coast 与原地形的融合曲率 |
| `enable_beach_noise` | On | 海滩内部噪声开关 |
| `beach_noise_amplitude` | 0.6 m | 海滩噪声幅度 |
| `coast_noise_scale` | 18 m | 海滩噪声尺度 |
| `coast_seed` | 17 | 海滩噪声种子 |
| `enable_beach_erosion` | Off | 高成本海滩侵蚀 |
| `beach_erosion_strength` | 0.35 | 侵蚀回混强度 |
| `beach_erosion_feature_size` | 8 m | 侵蚀尺度 |
| `beach_erosion_iterations` | 3 | 侵蚀迭代次数 |
| `track_coast_protect` | 20 m | 赛道附近恢复原地形的保护半径 |

功能默认关闭。只有同时满足以下条件才进入海岛分支：

```text
enable_island == 1
terrain_island_boundary_valid_count > 0
```

无有效边界时直接旁路到原始 Terrain Shape，不会用默认圆或隐式 Bounds 生成岛屿。

### 4.2 边界校验

`ISLAND_BOUNDARY_VALIDATE` 对每条 primitive 执行：

- 至少包含 3 个点。
- Houdini intrinsic 为 closed，或首尾点距离不超过 0.25 m。
- 几何首尾已经重合但 intrinsic 未闭合时，重建为闭合 polygon。
- 开放曲线会被移除，不参与地形生成。
- 保存原始点 Y 到 `coast_curve_y`，作为局部海岸高度。

输出计数：

```text
terrain_island_boundary_input_count
terrain_island_boundary_valid_count
terrain_island_boundary_open_count
terrain_island_boundary_autoclosed_count
```

这使 Island Boundary 不只是 XZ Mask：曲线 Y 仍能塑造局部起伏海岸。

### 4.3 HeightField 生成链

当前 `TerrainCore/10_TERRAIN_SOURCE` 直接包含 42 个节点。相对 Phase10 记录的 192 个 Terrain 内部直接节点，本阶段增至 212 个，新增部分集中在 Island Coast 链。

主要节点职责：

```text
IN_ISLAND_BOUNDARY
    -> ISLAND_BOUNDARY_VALIDATE
    -> ISLAND_BOUNDARY_FLATTEN
    -> ISLAND_BOUNDARY_RESAMPLE
    -> ISLAND_BOUNDARY_FILL
    -> ISLAND_BOUNDARY_PROJECT
    -> ISLAND_MANUAL_DISTANCE
    -> ISLAND_HEIGHT_BUILD
    -> ISLAND_MASK_BUILD
    -> COAST_MASK_BUILD
    -> BEACH_MASK_BUILD
    -> optional BEACH_ERODE
    -> ISLAND_TEMP_CLEANUP
    -> ISLAND_ENABLE_SWITCH
```

高度构造规则：

- 边界内侧为 Island。
- Coast 区域在原始地形与曲线 Y 之间按 Ramp 和 Sharpness 混合。
- 边界外侧在 Beach Width 内从曲线 Y 过渡到平坦海床。
- 海床目标高度为 `sea_level - seabed_depth`。
- Beach Noise 只影响海滩内部，在海岸边界和海床接缝处衰减为 0。
- Track 存在时，在 `track_coast_protect` 范围内平滑恢复为原始地形。

核心逻辑只修改 Terrain HeightField，不修改 Track Geometry。

### 4.4 可选海滩侵蚀

`BEACH_ERODE` 使用 `heightfield_erode::3.0`，再由 `BEACH_ERODE_REBLEND` 仅在 Beach Mask 内按强度回混。

默认 `enable_beach_erosion = Off`，符合编辑器响应与移动端 Bake 工作流要求。该节点只应在高质量编辑器 Cook/Bake 时开启，不允许进入移动端运行时链路。

### 4.5 输出层与扩展占位

启用有效边界后，Base HeightField 包含：

```text
height
island
coast
beach
coast_rock
coast_conflict
mask
```

当前状态：

- `island`、`coast`、`beach` 已由实际 HeightField 逻辑生成。
- `coast_rock` 当前固定为 0。
- `coast_conflict` 当前固定为 0。

因此 Rock 分布和 Coast Constraint 冲突检测仍是扩展占位，不应按已完成功能统计。

### 4.6 Metadata 1.13

Terrain Metadata 由 `1.12` 升至 `1.13`，新增或保留：

```text
terrain_island_enabled
terrain_island_boundary_input_count
terrain_island_boundary_valid_count
terrain_island_boundary_open_count
terrain_island_boundary_autoclosed_count
terrain_sea_level
terrain_coast_transition_width
terrain_beach_width
terrain_seabed_depth
terrain_track_coast_protect
```

`terrain_internal_mask_names` 同步加入：

```text
island,coast,beach,coast_rock,coast_conflict
```

Metadata 仍明确标注为 Editor 验证数据，不等同于已完成 Runtime Bake Contract。

### 4.7 Metadata 遗留引用

`METADATA_write_contract` 仍读取以下已经不在当前公共接口中的参数：

```text
coastline_mode
coastal_reserve
beach_rise
beach_coverage
```

并读取尚未形成实际生成链的：

```text
terrain_beach_include_valid_count
terrain_beach_exclude_valid_count
```

这些值当前退化为 0。它们属于旧接口或未完成扩展，不应继续作为可靠外部合约。下一阶段应选择：

1. 完全删除这些 Metadata 字段；或
2. 恢复明确的生成逻辑、公共参数和自动化测试。

禁止继续保留“字段存在但永远为 0”的模糊状态。

## 5. 湖面渲染资源

### 5.1 新增资产

| 资产 | 用途 | 源文件大小 |
|---|---|---:|
| `M_Map_Lake.mat` | 湖面材质 | 文本资产 |
| `Lake.shader` | URP 透明湖面 Shader | 426 行 |
| `LakeFunctions.hlsl` | 深度、法线、岸线、折射、波浪函数 | 444 行 |
| `ReflectionProbe-1.exr` | Cubemap Reflection | 300173 bytes |
| `T_LakeNoise_5.png` | Shoreline Dissolve | 1024×1024 / 236944 bytes |
| `T_LakeNormal_1.png` | 双向流动法线 | 1024×1024 / 956514 bytes |

纹理导入状态：

- 全部启用 Mipmap。
- `Streaming Mipmaps = Off`。
- 默认最大尺寸 2048。
- 没有针对 Android/iOS 的明确平台覆盖。
- Normal Texture 使用 `textureType = Normal Map`、`sRGB = Off`。
- Noise Texture 使用 `sRGB = On`。
- EXR 以 Cubemap Shape 导入，`sRGB = On`。

移动端仍需补充 ASTC 档位、最大尺寸和 Cubemap HDR 精度验证。

### 5.2 材质状态

`M_Map_Lake`：

- Shader：`NewWorld/Env/Lake`
- 有效 keyword：`_ENABLESHORELINE`
- 无效 keyword：`_ENABLEREFRACTION`
- `_ENABLEWAVE = 0`
- `_ENABLEGRADATION = 0`
- `m_EnableInstancingVariants = 0`

材质绑定：

```text
_Cubemap          -> ReflectionProbe-1.exr
_Normal_Map       -> T_LakeNormal_1.png
_SL_Dissolve_Mask -> T_LakeNoise_5.png
```

`_ENABLEREFRACTION` 已从 Shader 编译指令和条件分支中注释，但材质仍保留无效 keyword；当前折射代码实际无条件执行。

## 6. Lake Shader 渲染架构

### 6.1 Pass 职责

| 项目 | 当前实现 |
|---|---|
| SubShader | 1 |
| Pass | 1 |
| Pass Name | `Universal Forward` |
| Render Queue | Transparent / 3000 |
| Render Type | Transparent |
| Cull | Back |
| ZWrite | Off |
| Blend | SrcAlpha / OneMinusSrcAlpha |
| RenderTexture | Shader 本身不创建 |
| RendererFeature | 无 |
| RenderPassEvent | 不适用；使用 URP 默认透明阶段 |
| Depth Pass | 无 |
| ShadowCaster Pass | 无 |

Shader 标记为 `UniversalMaterialType = Unlit`，但内部自行采样主光阴影、计算高光、反射、雾和折射。

### 6.2 输入资源

Forward Pass 依赖：

```text
Camera Depth Texture
Camera Opaque Texture
Normal Map
Shoreline Dissolve Texture
Reflection Cubemap
Main Light Shadow / Shadow Mask
```

当前三个 URP Pipeline Asset：

```text
URP-Performant
URP-Balanced
URP-HighFidelity
```

均配置：

```text
m_RequireDepthTexture = 0
m_RequireOpaqueTexture = 0
```

主摄像机使用 Pipeline Settings：

```text
m_RequiresDepthTextureOption = 2
m_RequiresOpaqueTextureOption = 2
```

因此提交本身没有为 Lake Shader 提供必需的 Depth/Opaque Texture。岸线深度、浅深水渐变和屏幕空间折射可能得到无效数据。

直接全局开启两张纹理虽然能恢复效果，但会为移动端增加 Depth/Color Copy 与带宽开销。应先确定水面可见摄像机和目标机成本，再决定全局、Camera Override 或独立 Feature。

### 6.3 纹理采样与带宽

以当前材质“Shoreline On、Wave Off、Gradation Off”为例，每像素至少包含：

| 采样 | 数量 |
|---|---:|
| Normal Map | 2 |
| Scene Depth | 2 |
| Camera Opaque Texture | 1 |
| Shoreline Dissolve | 1 |
| Reflection Cubemap | 1 |
| Main Light Shadow / Shadow Mask | 视光照配置增加 |

基础纹理读取约 7 次，阴影过滤可能继续增加采样。透明湖面覆盖大面积屏幕时，主要瓶颈会是：

```text
透明 Overdraw
Camera Color/Depth 带宽
Cubemap + Normal 采样
Shadow 采样
全屏级覆盖范围
```

移动端应优先控制带宽，而不是只评估 Shader ALU。

### 6.4 当前代码问题

#### Water Depth UV 不一致

Fragment 中先令：

```hlsl
float2 RefractedUV = 0;
```

随后在真正计算折射前调用：

```hlsl
DepthFadeWorldPosition(_Water_Depth, RefractedUV, rawDepth, input.positionWS);
```

这会用 `(0,0)` 重建世界位置，却搭配当前像素采样得到的 `rawDepth`。浅水/深水颜色的世界位置重建不一致，应改用 `screenUV`，或先完成折射 UV 与深度重新采样。

#### Refraction 无法关闭

`_ENABLEREFRACTION` 的 Property、keyword 和条件分支已经不一致：

- 材质认为 Refraction 开启。
- Shader 不再编译该 keyword。
- 折射采样始终执行。

应在移动端基线中提供真正的关闭路径。若只需要运行时开关，可使用 uniform 并让“关闭分支”完全跳过 Opaque/Depth 采样；若两种成本差异过大，应拆为独立低成本 Shader。

#### Wave 重复计算

开启 `_ENABLEWAVE` 后：

- Vertex 中计算两组 Gerstner Wave 用于位移。
- Fragment 中再次计算两组 Gerstner Wave 用于波峰颜色。
- Vertex 输出的 `wave` 当前没有被 Fragment 使用。

建议直接插值 Vertex 波浪结果，避免每像素重复执行 `sin/cos/sqrt`。

#### 精度

大量位置、颜色、Mask、反射与临时变量使用 `float`。世界位置与深度重建保留 `float` 合理，但颜色、Mask、法线强度和大部分照明中间值应评估改为 `half`。

### 6.5 Instancing 与 Variant

Shader 没有：

```hlsl
#pragma multi_compile_instancing
```

因此不满足项目 Shader 强制 Instancing 规范。材质本身也未启用 Instancing。

自定义 local keyword：

```text
_ENABLESHORELINE
_ENABLEWAVE
_ENABLEGRADATION
```

基础 local 组合为 `2³ = 8`。

同时存在：

```text
LIGHTMAP_SHADOW_MIXING             2
SHADOWS_SHADOWMASK                2
FOG                               4
MAIN_LIGHT_SHADOWS                4
REFLECTION_PROBE_BLENDING         2
REFLECTION_PROBE_BOX_PROJECTION   2
FORWARD_PLUS                      2
```

理论源码组合上限：

```text
8 × 2 × 2 × 4 × 4 × 2 × 2 × 2 = 8192
```

Unity 会按材质、平台与 Stripping 设置剔除部分 Variant，但源定义已经远高于单 Shader 建议小于 200 的移动端目标。

优化方向：

1. 删除当前实现未使用的 Reflection Probe Blending、Box Projection、Forward+ keyword。
2. 对湖面不使用的 Lightmap/Shadowmask 组合执行明确裁剪。
3. Shoreline/Gradation 优先用 uniform 或独立低成本 Shader。
4. Wave 若只用于少量高质量水体，拆为独立高成本 Shader。
5. 补充 `multi_compile_instancing`，同时由实际 Draw 结构决定材质是否启用 Instancing。

### 6.6 Unity 编译状态

Unity Shader 资产读取结果：

```text
IsSupported = true
HasErrors = false
PassCount = 1
PropertyCount = 59
RenderQueue = 3000
```

D3D 编译存在 11 条 Warning，均为 vector implicit truncation，涉及：

- `GerstnerWave`
- `ShoreLineGenerator`
- `lerp`
- `StylizedSpecular`
- 若干隐式向量截断

当前不是编译失败，但应显式修正类型，避免在 Metal、Mali 和 Adreno 编译器上产生不同精度或寄存器行为。

## 7. Unity 场景变更

### 7.1 场景序列化规模

| 指标 | 父提交 | 提交 11 |
|---|---:|---:|
| YAML Documents | 150 | 118 |
| GameObjects | 24 | 20 |
| Root Objects | 11 | 11 |
| Embedded Meshes | 6 | 3 |

提交移除了额外的 `Track4`、`Spline (1)` 及其重复输出，只保留 `Track1` 的三类 Mesh：

| Mesh | Vertex Count |
|---|---:|
| Road | 2148 |
| Shoulders | 4296 |
| Collision | 6444 |

这些数值与父提交中较大的 Track 输出一致，主要变化是清理重复实例与 Session 命名，而不是改变保留 Mesh 的规模。

### 7.2 Island Boundary 测试夹具

场景新增根对象：

```text
__CoastHapiInspect
```

状态：

- Active。
- Unity Spline。
- 20 个 Knot。
- Closed。
- Transform Position：`(-733.4761, -29, 1243.1318)`。
- 绑定到 Terrain 的 `island_boundary`。
- Houdini Input Type 为 `UNITY_SPLINE`。

Terrain 提交参数为测试调参状态：

```text
enable_island = 1
sea_level = -80
coast_transition_width = 170.39235
beach_width = 279.59128
seabed_depth = 12
enable_beach_noise = 1
beach_noise_amplitude = 7.6131716
coast_noise_scale = 52.33745
enable_beach_erosion = 0
```

对象名带有 `Inspect`，参数也明显偏向大范围测试。正式场景应重命名为业务语义名称，或迁移到专用验证场景，避免测试夹具成为主场景长期事实源。

### 7.3 Terrain 输入状态

提交中的 Terrain 输入：

| 输入 | Input Type | 对象 |
|---|---|---|
| Terrain Guide Meshes | None | Empty |
| Lake Curves | Unity Spline | Empty |
| Island Boundary | Unity Spline | `__CoastHapiInspect` |
| Track Geometry | None | `_inputObjects` Empty |

Track Geometry 仍保留 `_inputAssetInfos` 指向 `Track1` 的 Session 信息，但公开输入类型和对象列表为空。这是 Phase10 安全解绑后的序列化残留，不应视为稳定绑定。

### 7.4 Terrain 输出与缓存

Terrain 输出位置：

```text
父提交：(-802.99744, -4.995182, -527.07043)
提交 11：(-1316.0173, -103.71282, -1040.0636)
```

位置变化与大范围 Island Boundary/自动 Domain 扩张一致。

TerrainData 仍引用 GUID：

```text
d4e45b44006984e43bc32e236be6b10a
```

但该 GUID 只存在于场景引用中，`Assets/HoudiniEngineAssetCache/Working/` 没有被 Git 跟踪。其他机器检出提交后仍存在 Missing TerrainData 或重新 Cook 才能恢复的可移植性风险。

### 7.5 湖面 Plane

场景新增 Active 根对象：

```text
Plane
Position = (0, -37, 0)
Scale = (10000, 10000, 10000)
Material = M_Map_Lake
MeshCollider = Enabled
```

风险：

- Unity 内置 Plane 原始尺寸约 10×10 m，10000 倍缩放会形成约 100 km 级水面。
- 透明面基本覆盖摄像机所有可见方向时，会放大 Overdraw 和 Camera Copy 成本。
- 视觉水面使用完整 MeshCollider，会扩大 Physics Bounds；若只需要水体触发，应使用简化 Trigger/Box，而不是渲染 Plane Collider。
- HDA 场景参数 `sea_level = -80`，但水面 Plane 位于 `Y = -37`，两者没有形成自动数据绑定。

当前还有一个旧 `Quad` 根对象，缩放同为 10000，但处于 Inactive，不参与运行时渲染。

## 8. CPU、GPU 与移动端成本

| 阶段 | CPU / Houdini | GPU / Unity | 结论 |
|---|---|---|---|
| Island Coast Cook | 曲线校验、HeightField、Mask、可选 Erosion | 无 | 仅编辑器/Bake 允许 |
| Runtime Terrain | 不应 Cook | 渲染 Bake 后 Terrain | 符合目标，但 Bake 可移植性未完成 |
| Lake Base | 极少 CPU | 大面积透明 Forward | GPU 带宽/Overdraw 风险高 |
| Refraction | 无持续 CPU 生成 | Depth + Opaque Copy + Scene Color Sample | Tile GPU 带宽高 |
| Shoreline | 无持续 CPU 生成 | Depth 重建 + Dissolve Sample | 可考虑离线 Coast Mask |
| Water Collider | Physics Broadphase/查询 | 无 | 视觉 Plane 不应保留超大 MeshCollider |

### 8.1 推荐移动端水面分层

建议拆成两套 Shader，而不是继续向单个 Lake Shader 堆功能：

```text
Mobile Lake
    Cubemap
    双法线或单法线
    Uniform Fresnel
    无 Camera Opaque Texture
    无屏幕空间 Refraction
    无 Wave Fragment 重算

High Quality Lake
    可选 Shoreline
    可选 Refraction
    独立 Variant 预算
    仅高端设备或近景水体启用
```

如果必须保留屏幕空间折射，建议实现独立：

```text
LakeRefractionRendererFeature
    -> LakeRefractionPass
    -> RenderPassEvent.AfterRenderingOpaques
```

要求：

- 独立 Feature Toggle。
- 配置由 ScriptableObject 管理。
- 最多一张可降分辨率的中间 RT。
- 只在存在可见水面时执行。
- 避免多次全屏 Blit。
- 明确 Android Mali/Adreno 与 iOS Metal fallback。

当前提交没有 RendererFeature，也没有额外自定义 RenderPass。

### 8.2 静态海岸优化

海岛与湖岸是编辑器期生成的静态数据。移动端优先方案应是：

```text
HDA coast/beach mask
    -> Bake 为 Terrain Layer / 低分辨率 Mask / 水面顶点色
    -> Runtime Shader 直接读取
```

这比每像素依赖 Scene Depth 重建岸线更稳定，也能避免为了静态海岸长期启用 Camera Depth/Opaque Texture。

## 9. 验证记录

### 9.1 Git

- 目标提交：`15dc472f`。
- 父提交：`821f962e`。
- 16 个文件，`+9036 / -10116`。
- 未修改官方 Houdini Engine Unity 插件。
- 当前工作区已有用户未提交的 `Assets/PCG/Scenes/PCG.unity` 大规模 Recook 变化和若干未跟踪资源；本文未覆盖或还原。

### 9.2 Houdini MCP Preflight

```text
Houdini = 21.0.440
RPC 18811 = Connected
MCP 3055 = Healthy
Codex Houdini Tools = Discovered
HIP = PCG_Bike_Terrain.hip
```

当前 Houdini 场景：

```text
/obj/TEST_Track
/obj/TEST_Track_Output
/obj/Terrain1
```

现场状态：

- HIP 无未保存修改。
- `/obj/Terrain1` 可编辑。
- Definition 指向 `Assets/PCG/HDA/Terrain.hda`。
- 当前实例 `matchesCurrentDefinition = false`。
- Terrain 根节点无 error/warning。
- 全场景扫描：0 Error，18 个既有 HeightField `name`/Volume Visualization `Alpha` Warning。

本次只读检查没有保存或修改现场 HIP/HDA。

### 9.3 Terrain Shape 验证

对提交 HIP 执行：

```text
validate_terrain_shape_params.py
Status = PASS
Resolution = 513×513×1
Layers = height, mask
Median Cook = 41.2001 ms
Warnings = 0
Saved = false
```

对 `Terrain.hda` 创建全新实例执行：

```text
Status = PASS
matchesCurrentDefinition = true
Resolution = 513×513×1
Layers = height, mask
Median Cook = 36.5134 ms
Warnings = 0
Saved = false
```

脚本验证了：

- Directional Ridge 拓扑与表达式。
- Seed/Angle/Strength 确实改变输出。
- Disabled 模块不会消费无效参数。
- Macro/Mid/Detail/Erosion 参数敏感性。
- 四页签 UI 与单一分辨率接口。

### 9.4 Island Coast 隔离验证

在全新 HDA 实例中创建 64 段闭合椭圆边界：

```text
Island Disabled Hash != Island Enabled Hash
matchesCurrentDefinition = true
Errors = 0
Warnings = 0
Saved = false
```

Disabled Layers：

```text
height, mask
```

Enabled Layers：

```text
height, island, coast, beach, coast_rock, coast_conflict, mask
```

说明 HDA Definition 本身已能根据有效闭合边界改变 HeightField。该检查目前是本次文档审计的隔离测试，尚未提交为长期自动化测试脚本。

### 9.5 Unity MCP

现场 Unity：

```text
Unity = 2022.3.62f2
Scene = Assets/PCG/Scenes/PCG.unity
Loaded = true
Valid = true
Dirty = true
Build Index = 0
Root Count = 11
Playing = false
Compiling = false
Updating = false
```

Shader 资产：

```text
NewWorld/Env/Lake
Supported = true
Compile Error = 0
D3D Warning = 11
Pass = 1
```

文档写入并刷新 AssetDatabase 后：

```text
IsCompiling = false
IsUpdating = false
最近 10 分钟 Error = 0
最近 10 分钟 Exception = 0
```

Unity Console 在 17:08～17:09 曾记录 Terrain1 Adaptive Earthwork Cook Failure 和 `No geometry generated`。当前 Houdini 现场与隔离 HDA 验证均已无 Error，但为了保护用户的 Dirty Scene，本次没有再次触发 Unity HEU Recook。

因此：

- HDA Definition 隔离 Cook 已通过。
- Unity Shader 编译已通过但有 Warning。
- Unity HEU 主场景端到端成功 Recook 仍需在场景状态稳定后补验。

## 10. 当前状态矩阵

| 功能 | 状态 | 结论 |
|---|---|---|
| Terrain 四页签参数接口 | 已完成 | 有脚本精确验证 |
| 单一 Terrain Resolution | 已完成 | 不再出现旧分辨率参数 |
| Island Boundary 闭合校验 | 已完成 | 闭合/自动闭合/开放计数已存在 |
| Island/Coast/Beach HeightField | 已完成 | 全新 HDA 隔离 Cook 已验证 |
| Beach Noise | 已完成 | 边界内衰减，默认开启 |
| Beach Erosion | 部分完成 | 节点存在且默认关闭，缺独立回归测试 |
| Track Coast Protect | 部分完成 | 逻辑存在，缺 Track+Coast 组合测试 |
| Coast Rock Mask | 模块骨架 | 当前固定为 0 |
| Coast Conflict Mask | 模块骨架 | 当前固定为 0 |
| Island Metadata 1.13 | 部分完成 | 核心计数有效，仍有失效参数引用 |
| Lake Constraint HDA | 延续既有能力 | 本提交主要调整 UI，未新增水体 Mesh 输出 |
| Lake Material / Shader | 部分完成 | 可编译，但移动端架构不合格 |
| Lake Instancing | 未实现 | Shader 与材质均未启用 |
| Lake Variant 控制 | 未完成 | 理论组合 8192 |
| Camera Depth/Opaque 依赖 | 未接入 | 当前 URP Asset 均关闭 |
| Lake Runtime Plane | 待复验 | 超大透明面、Collider、Sea Level 不同步 |
| Unity HEU 端到端 Recook | 待复验 | Console 曾出现 Cook Failure |
| TerrainData 可移植 Bake | 未实现 | Working Cache 未纳入 Git |
| 移动端真机 Profiling | 未执行 | Mali/Adreno/Metal 均待测 |

## 11. 下一阶段建议

1. 修复 `WaterDepth` 使用 `(0,0)` Refracted UV 的错误，统一 Depth Reconstruction 数据。
2. 明确 Camera Depth/Opaque Texture 策略；移动端基线优先去除屏幕空间折射。
3. 将 Lake Shader 拆分为 Mobile 与 High Quality 两套，Variant 分别预算。
4. 补充 `multi_compile_instancing`，删除无实际用途的 URP `multi_compile` 组合。
5. 修正 11 条 vector truncation Warning，并按用途将颜色/Mask/照明中间量降为 `half`。
6. 移除 Plane 的超大 MeshCollider，水体交互改为简化 Trigger/Volume。
7. 让水面高度、范围和 Terrain `sea_level`/Domain 由 Bake 数据自动同步。
8. 将 `__CoastHapiInspect` 移入独立验证场景，主场景只保留正式命名与正式参数。
9. 为 Island Coast 增加长期测试：闭合、开放、自动闭合、Ramp 端点、Beach Noise、Erosion、Track Protect。
10. 删除或实现 `coastline_mode/coastal_reserve/beach_rise/beach_coverage` 等失效 Metadata 字段。
11. 在 Unity HEU 场景稳定后重新 Recook，确认 Terrain 输出、Console、HDA GUID 和材质引用全部通过。
12. 建立正式 TerrainData/Bake 输出目录，停止依赖未跟踪的 Houdini Working Cache。
