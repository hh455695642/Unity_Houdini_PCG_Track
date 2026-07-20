# Phase 7 开发日志：道路世界空间投影与起点龙门 Recook

> 文档类型：Phase 7 增量开发日志
>
> 记录日期：2026-07-20
>
> 关联提交：`4ef08c4cb35f510dad0065a497eea863bf5e6058`（提交说明：`7`）
>
> 基线版本：Phase 6 日志提交 `55955123cd33471dc45cb7918ca177921e282c1e`
>
> 记录范围：只记录提交 `4ef08c4` 相对其父提交 `5595512` 新增、调整、替换或移除的内容

## 1. 日志范围与证据

本文不是 Track/Terrain 全量快照。Track 曲线输入、Banking、Adaptive Sampling、拆分输出、起点 Prefab 输出接口，以及 Terrain 自适应土方能力以 Phase 1～Phase 6 日志为准。

证据标记：

- **[已验证]**：通过 Git 父子差异、Unity 场景 YAML、Unity MCP 的 Shader/Material/GameObject/Component 状态直接确认。
- **[提交已实现]**：功能已进入 `4ef08c4`，但当前缺 Houdini Live Cook、视觉方向或移动端真机数据。
- **[待复验]**：提交数据成立，但必须在 Houdini 恢复或目标设备上补做验证。
- **[未改变]**：沿用前一阶段实现，本提交没有修改对应资产或契约。

提交 `4ef08c4` 只修改 3 个文件：

| 文件 | Phase 6 | Phase 7 | 变化 |
|---|---:|---:|---|
| `Assets/PCG/Shaders/PCG_Road.shader` | 10,666 bytes | 11,207 bytes | +11/-3 行；非方向层改用 Unity 世界空间 XZ 投影 |
| `Assets/PCG/Materials/M_PCG_Road.mat` | 1,860 bytes | 1,882 bytes | +2/-1 行；启用世界投影并设置 4 m Tile Size |
| `Assets/PCG/Scenes/PCG.unity` | 2,604,415 bytes | 2,905,338 bytes | +15,801/-15,592 行；Track 调参、起点 Prefab 实例与完整 Recook 状态 |

本提交没有修改 `.meta`、HDA、HIP、C#、Renderer、RendererFeature、RenderPass、Texture、Prefab 源资产或测试文件。GUID 保持不变：

- `PCG_Road.shader`：`5c9761eda3f66d0409c6c334b7769705`
- `M_PCG_Road.mat`：`9c53944cb7afdd74599a7a985256a52e`
- `Track.hda`：`a8929706c44d3b04abb57a0bd73cac39`
- `Terrain.hda`：`15a73d0f61bb98040ae78ced958c3bf9`

## 2. Phase 7 提交概览

| 模块 | 本阶段增量 | 当前状态 |
|---|---|---|
| 道路 UV | 非方向纹理从 HDA `uv3` 插值切换为 Unity `positionWS.xz` 世界投影 | [已验证] |
| UV 开关 | `_UseLowDistortionUV` 从连续混合改为阈值 0.5 的二值 Uniform Toggle | [已验证] |
| 世界尺寸 | 新增 `_WorldUVTileSize`，材质当前为每 4 m 重复一次 | [已验证] |
| 道路材质 | `_UseLowDistortionUV` 从 `0.672` 规范化为 `1` | [已验证] |
| Track 参数 | 启用 Banking、设计速度调至 35 km/h、路宽调至 21 m | [已验证] |
| 起点资产 | 绑定 `SM_MarkerSigns_06.prefab` 并生成一个起点龙门实例 | [已验证结构；朝向与地面贴合待视觉复验] |
| 场景 Recook | Terrain/Track 重新连接 Houdini Session 并保存生成 Mesh/实例 | [已验证 Unity 序列化结果] |
| HDA 算法 | 没有修改 `Track.hda` 或 `Terrain.hda` | [未改变] |
| 运行时管线 | 无额外 Pass、RT、Blit、MRT 或自定义 keyword | [未改变] |

Phase 7 的核心是修复道路非方向层纹理坐标，并用现有 HDA 参数完成一次可见的 Track 场景配置与 Recook；不是新建 HDA 模块。

## 3. 道路世界空间 XZ 投影

### 3.1 Phase 6 方案的问题

**状态：[已验证]**

Phase 6 Shader 的非方向纹理坐标为：

```hlsl
float2 layerUV = lerp(directionalUV, input.surfaceUV, saturate(_UseLowDistortionUV));
```

其中：

- `directionalUV` 是 Track UV0，适合中心线、道路标记和沿赛道方向连续的内容。
- `surfaceUV` 来自 Houdini `uv3`，进入 Unity 后占用 Mesh UV2 / `TEXCOORD2`。
- `_UseLowDistortionUV` 在材质中为 `0.672`，导致两个不同坐标空间被连续插值。

对两个参数化空间做 0～1 连续插值没有稳定的物理语义，会产生纹理漂移、缩放不一致或随曲线位置变化的畸变。该问题不是纹理采样不足，而是 UV 选择逻辑把 Feature Toggle 当成了 Blend Weight。

### 3.2 Phase 7 实现

**状态：[已验证]**

Forward Pass 新增世界位置 varying：

```hlsl
float3 positionWS : TEXCOORD3;
```

Vertex Shader 通过 URP `GetVertexPositionInputs` 写入世界位置，Fragment Shader 计算：

```hlsl
float inverseWorldTileSize = rcp(max(_WorldUVTileSize, 0.01));
float2 worldPlanarUV = input.positionWS.xz * inverseWorldTileSize;
half useWorldPlanarUV = step(half(0.5), saturate(_UseLowDistortionUV));
float2 layerUV = lerp(directionalUV, worldPlanarUV, useWorldPlanarUV);
```

行为变化：

1. `_UseLowDistortionUV < 0.5`：非方向层使用 Track UV0。
2. `_UseLowDistortionUV >= 0.5`：非方向层使用 Unity 世界空间 XZ 平面投影。
3. `_WorldUVTileSize` 最小钳制为 `0.01 m`，避免零值除法。
4. 材质当前为 `4 m`，即世界 X/Z 每 4 m 重复一个纹理周期。

这里是单轴 XZ Planar Projection，不是 Triplanar。道路和路肩通常接近水平面，因此成本远低于三向投影；极端纵坡或大倾角 Banking 仍可能出现沿表面方向的投影压缩，需在极端赛道样例中观察。

### 3.3 纹理职责保持分离

**状态：[已验证]**

| 内容 | UV 来源 | 原因 |
|---|---|---|
| Base Road / 道路标记 | `directionalUV` / UV0 | 保持中心线居中并沿赛道连续 |
| Gravel / Mask R | `layerUV` | 非方向材质，当前使用世界 XZ |
| Stone / Mask G | `layerUV` | 非方向材质，当前使用世界 XZ |
| Grass / Mask B | `layerUV` | 非方向材质，当前使用世界 XZ |
| Blend Noise | `layerUV × _NoiseScale` | 与非方向材质锁定在同一空间 |

世界投影只改变非方向层与噪声，不会让道路标线失去赛道方向。

### 3.4 Transform 与 Instancing 语义

**状态：[已验证]**

`positionWS` 由 URP 的实例感知顶点变换获得，Forward Pass 继续执行 `UNITY_SETUP_INSTANCE_ID` / `UNITY_TRANSFER_INSTANCE_ID`。如果后续把道路拆为多个实例化 Chunk，每个实例的世界变换会正确参与世界 UV。

纹理将锁定 Unity 世界坐标：移动整个 Track GameObject 时，表面会在固定世界纹理上滑动，而不是纹理跟随 Mesh 局部坐标。这符合“世界投影”的定义，但若未来采用 Floating Origin，应同步评估原点重定位时的纹理跳变。

## 4. Shader 架构、Variant 与移动端成本

### 4.1 Pass 与 RenderPassEvent

**状态：[已验证]**

本提交没有 RendererFeature，因此没有新增自定义 `RenderPassEvent`。Shader 仍为 3 Pass：

| Pass | LightMode | 职责 | 额外 RenderTexture |
|---|---|---|---|
| Forward | `UniversalForward` | 四层颜色、噪声侵蚀、主光与 SH 环境光 | 无 |
| DepthOnly | `DepthOnly` | 深度写入与 Early-Z | 无 |
| ShadowCaster | `ShadowCaster` | 阴影深度 | 无 |

Unity MCP 当前读取结果：

```text
Shader Name: PCG_Track/Road
Supported: True
Render Queue: 2000
Render Type: Opaque
Property Count: 15
Pass Count: 3
Compilation Error: False
```

### 4.2 Instancing 与 Variant

- 三个 Pass 均保留 `#pragma multi_compile_instancing`。
- 没有新增 `shader_feature_local` 或功能 keyword。
- `_UseLowDistortionUV` 与 `_WorldUVTileSize` 都是 Uniform，不形成组合 Variant。
- 本项目自定义功能 Variant 增量为 0；风险仍来自 URP/平台基础 Variant 与 Instancing。
- 材质 `m_EnableInstancingVariants = 0` 没有变化；当前单条连续赛道不依赖材质实例化收益。

### 4.3 采样、ALU 与 varying

| 项目 | Phase 6 | Phase 7 | 结论 |
|---|---:|---:|---|
| Forward 最大纹理采样 | 5 | 5 | 无新增带宽采样 |
| 自定义 keyword | 0 | 0 | 无 Variant 爆炸 |
| World Position varying | 无 | `float3` | 增加插值寄存器/带宽 |
| World UV 运算 | 无 | `max + rcp + mul + step + lerp` | 少量 ALU |
| 透明/Overdraw | Opaque | Opaque | 无新增透明 Overdraw |

移动端主要增量不是纹理采样，而是 Forward Pass 的 `float3 positionWS` 插值。Track 约 1 km，使用 `float` 而不是 `half` 是合理的精度选择。

当前源代码仍声明并传递 `surfaceUV : TEXCOORD2`，但 Fragment 已不再读取它。编译器通常会剔除未使用 varying；后续可直接从 Shader Varyings 删除 `surfaceUV`，并把世界 XZ 在 Vertex 阶段计算为 `float2` 后传递，以减少一个分量和每像素除法。优化前应通过移动端编译产物或 RenderDoc 确认实际 varying 分配，避免只按源码推断。

## 5. 道路材质配置

### 5.1 参数变化

**状态：[已验证]**

`M_PCG_Road.mat` 只修改两个有效参数：

| 参数 | Phase 6 | Phase 7 |
|---|---:|---:|
| `_UseLowDistortionUV` | `0.672` | `1` |
| `_WorldUVTileSize` | 不存在 | `4 m` |

`_UseLowDistortionUV = 1` 与 Shader 的二值阈值语义一致，避免 Inspector 中保留“0.672 看似混合比例”的歧义。

### 5.2 当前完整材质状态

Unity MCP 已确认材质实际使用 `PCG_Track/Road`，关键 Uniform 为：

```text
Noise Scale       = 0.71
Noise Strength    = 0.461
Blend Feather     = 0.038
Noise Contrast    = 0.88
World Planar UV   = 1
World UV Tile     = 4 m
```

Base、Gravel、Stone、Grass 和 Blend Noise 五张纹理引用均未变化。本提交没有增加新纹理或法线贴图。

## 6. Track 场景参数调整

### 6.1 参数父子差异

**状态：[已验证]**

对 Phase 6/Phase 7 场景内 116 个 Terrain 参数记录和 48 个 Track 参数记录逐项比较，只有以下 6 个 Track 参数变化；Terrain 参数值没有变化：

| 参数 | Phase 6 | Phase 7 | 作用 |
|---|---:|---:|---|
| `enable_road_banking` | Off | On | 启用既有 Banking 链路 |
| `bank_design_speed_kph` | 25 | 35 | 以更高设计速度计算目标横坡 |
| `road_width` | 20 m | 21 m | 道路主体加宽 1 m |
| `shoulder_drop` | 0.296467 m | 0.28 m | 路肩下沉值规范化 |
| `start_prefab` | 空 | `SM_MarkerSigns_06.prefab` | 启用起点 Prefab 输出 |
| `start_prefab_yaw_offset` | -90° | 0° | 使用 Track 输出方向，不再额外旋转 -90° |

Banking、起点实例输出和道路拆分能力都来自既有 `Track.hda`；提交 7 只在 Unity 场景中启用和调参，没有修改 HDA 定义。

### 6.2 生成 Mesh 变化

**状态：[已验证 Unity 序列化结果；Houdini metadata 待复验]**

参数变化并 Recook 后，三份场景内 Mesh 顶点数同步增加约 14.4%：

| Mesh | Phase 6 | Phase 7 | 增量 |
|---|---:|---:|---:|
| Road Surface | 3,696 | 4,230 | +534 |
| Road Shoulders | 7,392 | 8,460 | +1,068 |
| Road Collision | 11,088 | 12,690 | +1,602 |

三份 Mesh 仍为 16-bit Index Format，顶点数远低于 65,535。增长与 Banking/设计速度/路宽组合调参后的 Recook 一致，但当前 Houdini 离线，无法进一步读取 `road_sample_count`、Banking 统计或确定具体由哪个参数贡献多少采样点。

Road/Shoulder/Collision 的 Y Extent 同时增大，符合 Banking 打开后道路横坡与局部高度范围扩大的预期。该结论来自 Unity Mesh AABB，不替代 Houdini 曲率/横坡数值验收。

## 7. 起点龙门 Prefab 实例

### 7.1 资产绑定

**状态：[已验证]**

Track 参数绑定的源资产为：

```text
Assets/ArtResources_Mountainbike/Environment/ScenePrefabs/Mountainbike/SM_MarkerSigns_06.prefab
GUID: b918b910333e6254baa26cf0e9fb8821
```

Prefab 与 `.meta` 已被 Git 跟踪，本提交只引用现有外部美术资产，没有复制或改写 Prefab 源文件。

### 7.2 输出层级

**状态：[已验证]**

Unity MCP 当前层级：

```text
Track1
  HDA_Data                         [EditorOnly]
  Track1_OUT_ROAD_MESH_OUT_ROAD_MESH_0
  Track1_OUT_ROAD_SHOULDERS_OUT_ROAD_SHOULDERS_0
  Track1_OUT_ROAD_COLLISION_OUT_ROAD_COLLISION_0
  Track1_OUT_START_PREFAB_INSTANCE_OUT_START_PREFAB_INSTANCE_0
    RaceStart_Instance1
```

`RaceStart_Instance1` 是对源 Prefab 的实例引用，包含 Transform、MeshFilter 和 MeshRenderer。Houdini Engine 的 instanced input 记录 1 个实例，不是把龙门合并进 Road Mesh。

场景序列化的实例局部位置约为 `(17, -2.3, -1)`，方向来自 Track 起点的 `orient`，额外 Yaw Offset 已设为 0。结构、资产引用和实例数量已验证；尚未通过 Scene View/目标相机确认正反面、地面穿插、道路净宽和自行车通过高度，因此视觉验收仍为待复验。

### 7.3 运行时成本

当前只有一个起点实例，采用普通 Prefab GameObject 合理，不需要为单实例引入 Indirect Draw。若后续检查点、路牌或装饰数量扩大，应转入 Decoration Chunk/Cluster 与 GPU Instancing 数据，而不是让 HDA 生成大量运行时 GameObject。

## 8. 场景 Recook 与序列化噪声

### 8.1 Cook 计数

**状态：[已验证]**

| HDA | Phase 6 `_totalCookCount` | Phase 7 `_totalCookCount` |
|---|---:|---:|
| Terrain1 | 15 | 18 |
| Track1 | 6 | 22 |

Track Cook 次数明显增加，与 Banking、道路宽度、起点 Prefab、材质绑定和多次 Reload/Recook 调试一致。

### 8.2 Houdini Session 重建

场景 `_sessionID` 从 `2242207906560` 变为 `2474810138544`。大量 `nodeId`、`objectNodeId`、String Handle、fileID、input node 和 volume cache 引用被重新分配，是 Houdini Engine 新 Session/Recook 的序列化结果，不是 15,000 行独立功能开发。

有效场景语义变化应以以下内容为准：

1. 6 个 Track 参数变化。
2. Road/Shoulder/Collision Mesh 重建。
3. 新增独立 Start Prefab Output 与 1 个 PrefabInstance。
4. Terrain 被同一 Session 重新 Cook，但 131 个 Terrain 参数值没有变化。
5. Road 与 Shoulder Renderer 继续引用 `M_PCG_Road.mat`，材质绑定关系本身不是 Phase 7 新增。

### 8.3 材质引用验证

Unity MCP 当前确认 Road Surface 与 Road Shoulders 两个 MeshRenderer：

```text
sharedMaterial = Assets/PCG/Materials/M_PCG_Road.mat
GUID           = 9c53944cb7afdd74599a7a985256a52e
enabled        = true
```

因此 Phase 7 的 Shader/Material 参数会实际作用于两份可视输出，而不是只修改一个未被场景使用的孤立材质。

## 9. 性能、兼容性与风险

### 9.1 CPU vs GPU

| 阶段 | CPU/Houdini | GPU/Unity | 主要风险 |
|---|---|---|---|
| 编辑器生成 | Banking、采样、Sweep、拆分输出、Prefab 点实例 | 仅预览 | Track Cook 次数和 Mesh 顶点增长 |
| Bake/场景保存 | Houdini Engine 序列化 Mesh 与实例 | 无额外 Pass | 场景 YAML 体积与可重现性 |
| 移动端运行时 | 不应执行 Houdini Cook | 5 次纹理采样 + world varying | 纹理带宽、varying、顶点数 |

### 9.2 Tile-Based GPU

- 没有额外 RenderTexture、全屏 Blit、MRT 或 Tile Flush。
- Opaque、Cull Back、ZWrite On，透明 Overdraw 风险没有增加。
- Forward 纹理采样仍为 5，带宽成本与 Phase 6 相同。
- 新增 `float3 positionWS` varying，会增加片元插值带宽；移动端应优先优化成 `float2 worldXZ/worldUV`。
- 顶点数增加约 14.4%，对单条赛道通常可控，但应结合赛道 Chunk、可见性剔除和真机顶点吞吐评估。

### 9.3 精度与兼容性

- 世界坐标与长距离 UV 使用 `float`，适合约 1 km 赛道；改成 `half` 可能在远离原点时产生纹理抖动。
- 颜色、Mask、噪声、光照继续使用 `half`，符合移动端精度策略。
- Shader Target 仍为 2.0，没有 Geometry Shader、Compute 依赖或平台专属指令。
- `step`、`rcp`、`max` 和 `lerp` 在 Mali/Adreno/Apple GPU 上均为常规兼容运算。
- 世界 XZ 投影在非常陡的路面上会压缩纹理；不建议为此直接升级为三向采样，除非视觉收益在目标机上明确大于额外采样成本。

## 10. 本版本验证记录

### 10.1 Git

- 目标提交：`4ef08c4cb35f510dad0065a497eea863bf5e6058`。
- 父提交：`55955123cd33471dc45cb7918ca177921e282c1e`。
- 提交日期：2026-07-20 11:56:33 +08:00。
- 仅 3 个文件变化；Shader/Material/HDA GUID 无变化。
- 场景 164 个 HDA 参数逐项比较后，仅 6 个 Track 参数值变化。
- `Track.hda`、`Terrain.hda`、HIP 和 Prefab 源资产未变化。

### 10.2 Unity

- Unity Editor：`2022.3.62f2`，MCP Server 可连接。
- Editor：未播放、未暂停、未编译、未处于 AssetDatabase 更新状态。
- Shader：受支持、无编译错误、15 属性、3 Pass、Opaque Queue 2000。
- Material：实际绑定 `PCG_Track/Road`，世界投影为 1，Tile Size 为 4 m。
- `Track1`：激活，包含 Road/Shoulder/Collision/Start Prefab 四份输出。
- `RaceStart_Instance1`：激活，源 Prefab GUID 正确。
- Road/Shoulder Renderer：均启用并绑定 `M_PCG_Road.mat`。
- 近 30 分钟 Console Error：0。
- 近 30 分钟 Console Warning：0。
- 当前打开的 `PCG.unity` 有未保存 Editor 改动；本次只读验证没有保存场景，不能把当前 Dirty 内容归入提交 7。

### 10.3 Houdini

**状态：[待复验；当前不可用]**

2026-07-20 执行 `Ensure-HoudiniMcp.ps1` 失败：

- Houdini GUI 未运行。
- 仅 `hserver` 进程存在。
- `127.0.0.1:18811` RPC 无当前 GUI Session 可连接。
- `http://127.0.0.1:3055/health` 无法连接。
- 无法读取当前 `.hip`、`/obj/Track1`、Cook error/warning、Banking 统计、道路 metadata 或起点输出点属性。

由于提交 7 没有修改 HDA/HIP，本日志可通过 Git + Unity 还原提交内容；但以下验证必须在 Houdini 恢复后补做：

1. 强制 Cook `Track1` 并确认 0 error/warning。
2. 读取 `road_sample_count`、Banking 最大角度/过渡和碰撞输出统计。
3. 检查 `OUT_START_PREFAB_INSTANCE` 的 `unity_instance`、`orient`、`N`、`up` 与实例数量。
4. 确认 Track 输出仍能被 Terrain Display/Conform 链路消费。

## 11. 当前状态矩阵

| 功能 | 状态 | 当前结论 |
|---|---|---|
| Unity 世界 XZ 路面投影 | 已完成 | 非方向层与噪声已切换到 `positionWS.xz` |
| 二值 UV Toggle | 已完成 | 0.5 阈值，不再插值两个坐标空间 |
| 世界 Tile Size | 已完成 | 新增 Uniform，材质当前 4 m |
| Shader 编译 | 已完成 | Unity 当前平台受支持且无错误 |
| Shader Variant 控制 | 已完成 Phase 7 | 无新增 keyword，增量 Variant 为 0 |
| 移动端 varying 优化 | 部分完成 | 功能正确，仍可由 `float3` 优化为 `float2` |
| Road Banking 场景启用 | 已完成配置 | 35 km/h；Houdini 数值输出待复验 |
| Road/Shoulder/Collision Recook | 已完成 | Mesh 已重建，顶点约增加 14.4% |
| 起点 Prefab 引用与实例 | 已完成结构 | 1 个实例；视觉朝向/穿插待复验 |
| Road/Shoulder 材质绑定 | 已完成 | 两个 Renderer 均引用 `M_PCG_Road.mat` |
| HDA 算法 | 未改变 | 本提交未修改 Track/Terrain HDA |
| Houdini Live Cook | 未执行 | GUI、RPC、3055 均不可用 |
| 移动端真机 Profiling | 未执行 | Mali/Adreno/Apple GPU 数据待补 |

## 12. 下一阶段建议

1. Houdini 恢复后补跑 Track 强制 Cook，记录 Banking、Adaptive Sampling、输出 Mesh 与起点点实例 metadata。
2. 用 Scene View/游戏相机确认 `RaceStart_Instance1` 正反面、路面贴合、净宽和碰撞，必要时只调整 `start_prefab_yaw_offset`。
3. 将 Forward varying 从 `float3 positionWS` 收敛为 Vertex 阶段计算的 `float2 worldUV`，并移除 Shader 中未使用的 `surfaceUV` 传递。
4. 为世界 UV 增加 1 km、远离原点、移动 Track Root 和 Floating Origin 样例，验证纹理稳定性。
5. 在极端 Banking/纵坡样例中检查 XZ Planar 压缩；优先调整材质 Tile，而不是增加 Triplanar 三倍采样。
6. 在 Mali、Adreno、Apple GPU 上记录 Forward varying、5 次采样、4,230/8,460 顶点输出的 GPU 时间和带宽。
7. 继续把最终道路、碰撞与起点实例纳入可重现的 Bake Pipeline，避免运行时依赖 Houdini Engine 场景对象。
