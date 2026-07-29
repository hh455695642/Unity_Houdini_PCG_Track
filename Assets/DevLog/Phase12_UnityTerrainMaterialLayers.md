# Phase 12 开发日志：Unity Terrain 四层材质权重接入

> 文档类型：提交增量快照  
> 记录日期：2026-07-28  
> 目标提交：`396c357a2f6b69fbf2a93f290d32712f2dfed717`（提交信息：`12`）  
> 父提交：`8fa6a1d5f35843b0a51d5dac88f8329c8835195f`（Phase11 文档提交）  
> 主场景：`Assets/PCG/Scenes/PCG.unity`  
> Terrain HDA：`Assets/PCG/HDA/Terrain.hda`  
> Terrain HIP：`HoudiniProject/PCG_Track_21.0.440/PCG_Bike_Terrain.hip`

## 1. 日志范围与证据

本文只记录 Git 提交 `396c357` 相对父提交 `8fa6a1d` 的开发增量，不重复 Phase 1～Phase 11 已记录的 Track、Terrain、Guide Mesh、Adaptive Earthwork、Track 输入守卫、道路净空保护、手绘海岸和湖面渲染功能。

本阶段的主链路为：

```text
既有 Terrain HeightField 与 Mask
    -> 60_MATERIAL_LAYERS
    -> Grass / Stone / Gravel / terrain_dirt 四层权重
    -> 优先级归一化
    -> unity_hf_terrainlayer_file
    -> Houdini Engine Unity Cook
    -> Unity TerrainData + 4 个 TerrainLayer
```

证据等级：

- **[提交验证]**：直接读取目标提交的 Git diff、HDA 解包结果、HIP、Unity 场景 YAML、TerrainLayer 和 `.meta`。
- **[现场验证]**：通过 Houdini MCP 和 Unity MCP 读取当前 Editor、HIP、HDA、TerrainData 与 Console 状态。
- **[隔离验证]**：在独立 `hython` 进程中加载提交 HIP，执行材质层开关、权重范围、权重和与 Cook 检查；不保存 HIP/HDA。
- **[待修复]**：实现已存在，但版本管理、测试合约、命名或端到端交付仍不完整。

提交 12 没有修改 `Assets/Plugins/HoudiniEngineUnity/`，继续符合官方 Houdini Engine Unity 插件零侵入约束。

## 2. 提交概览

| 项目 | 数值 |
|---|---:|
| Commit | `396c357` |
| Author / Date | `liyuan` / 2026-07-28 19:00:41 +08:00 |
| Changed Files | 13 |
| Added / Deleted Lines | `+17060 / -16399` |
| 新增 TerrainLayer | 5 个资产 + 5 个 `.meta` |
| Terrain HDA | 118,732 → 122,968 bytes |
| Terrain HIP | 820,388 → 912,543 bytes |
| Unity 场景 | `+16910 / -16399` |
| 新增 C# / Shader / Render Feature | 0 |

文件按职责分为三组：

1. **Terrain 材质权重生成**
   - `Assets/PCG/HDA/Terrain.hda`
   - `HoudiniProject/PCG_Track_21.0.440/PCG_Bike_Terrain.hip`

2. **Unity TerrainLayer 资产**
   - `TL_PCG_Grass.terrainlayer`
   - `TL_PCG_Stone.terrainlayer`
   - `TL_PCG_Gravel.terrainlayer`
   - `TL_PCG_Sand.terrainlayer`
   - `TL_PCG_Dirt.terrainlayer`
   - 对应 5 个 `.meta`

3. **Unity Cook/Recook 序列化结果**
   - `Assets/PCG/Scenes/PCG.unity`

## 3. Unity TerrainLayer 资产

### 3.1 资产配置

| TerrainLayer | GUID | Diffuse Texture | Tile Size | Smoothness | 当前接入 |
|---|---|---|---:|---:|---|
| `TL_PCG_Grass` | `7372ee31191fedd4aa2f192232fd745c` | `T_Mountainbike_Grass_01_C.png` | 12 × 12 | 0.05 | 已接入 `terrain_grass` |
| `TL_PCG_Stone` | `51374dedd79f320409d579cc9d1d858c` | `T_Mountainbike_Stone_C.png` | 10 × 10 | 0.12 | 已接入 `terrain_stone` |
| `TL_PCG_Gravel` | `453d695c6dd4a6e40863927f72df93a7` | `T_Mountainbike_Gravel_C.png` | 6 × 6 | 0.08 | 已接入 `terrain_gravel` |
| `TL_PCG_Sand` | `48daa885518a13648a1c5c2c44a3576c` | `T_Mountainbike_02_C.png` | 12 × 12 | 0.04 | 已接入 `terrain_dirt` |
| `TL_PCG_Dirt` | `09fb796896ef8b549aaab3691e191fa1` | `T_Mountainbike_03_C.png` | 10 × 10 | 0.05 | **未接入** |

五个 TerrainLayer 的共同配置：

- Metallic：0。
- Specular：黑色。
- Normal Map：空。
- Mask Map：空。
- Normal Scale：1。
- Tile Offset：0。
- Diffuse/Mask Remap：默认 0～1。

对应 Diffuse Texture 继续使用既有导入配置：

- Mipmap：开启。
- Read/Write：关闭。
- Max Texture Size：2048。
- Android / iPhone 均存在平台配置，当前 Texture Compression 为普通压缩档。

本提交只新增 TerrainLayer 包装资产，没有修改原始 Texture 或导入设置。

### 3.2 Dirt 与 Sand 的兼容命名

HDA 的第四个权重层仍使用：

```text
terrain_dirt
```

但 `MATERIAL_bind_sand` 实际写入：

```text
Assets/PCG/Materials/Terrain/TL_PCG_Sand.terrainlayer
```

这是为了兼容当前 Houdini Engine Working preset/既有层名，语义上该层已经是 Sand，而不是 Dirt。

目标提交全树中，`TL_PCG_Dirt` 只在自身资产和 `.meta` 内出现：

- HDA 没有绑定它。
- Unity 场景没有引用它。
- 当前 TerrainData 没有装载它。

**状态：[待修复]**

后续必须二选一并固化数据契约：

1. 保留 `terrain_dirt` 兼容层名，但把 UI、Help、Sticky Note 和测试统一说明为 Sand。
2. 正式迁移为 `terrain_sand`，同时提供旧层名迁移和现有 Working Cache 重建。

不应长期同时保留“未使用 Dirt 资产”和“名为 Dirt、实际是 Sand 的权重层”。

### 3.3 目录 `.meta` 缺失

提交新增了目录：

```text
Assets/PCG/Materials/Terrain/
```

但目标提交没有包含：

```text
Assets/PCG/Materials/Terrain.meta
```

Unity 当前已经自动生成该文件：

```text
GUID: 999cc4630092ed345ab160a5a72ce49d
```

该文件在工作区中处于未跟踪状态。虽然现有 TerrainLayer 引用依赖各资产自身 GUID，不直接依赖目录 GUID，但缺少文件夹 `.meta` 仍会导致不同检出环境重新生成目录 GUID，属于 Unity 版本管理不完整。

**状态：[待修复]**

## 4. Terrain HDA 材质层模块

### 4.1 公共开关

Output Mask 页签下新增：

| 参数 | 默认值 | 职责 |
|---|---:|---|
| `material_layers_enabled` | On | 开启时输出 height + 4 个 Unity Terrain 权重层；关闭时只输出 height |

UI 路径：

```text
Output Mask / 输出 Mask
    -> Terrain Material / 地形材质
        -> Enable Terrain Material Layers / 启用地形材质层
```

这是开发期 Cook/Bake 开关，不是 Player Runtime Shader Keyword，也不会在运行时触发 Houdini Cook。

HDA 公共参数对象数量：

```text
159 -> 161
```

增加的两个对象分别是材质分组和 Toggle。

### 4.2 模块边界

TerrainCore 新增：

```text
60_MATERIAL_LAYERS
```

输入：

- `40_CONFORM_EARTHWORK` 的最终 HeightField。
- 已有 `cliff`。
- 已有 `coast_rock`。
- 已有 `beach`。
- 已有 `road`。
- 已有 `shoulder`。
- 已有 `cut`。
- 已有 `fill`。

输出：

```text
height
terrain_grass
terrain_stone
terrain_gravel
terrain_dirt
```

其中 `terrain_dirt` 实际绑定 Sand TerrainLayer。

该模块拥有独立 Network Box、Sticky Note 和 `pcg_terrain_material_module=v1` User Data，职责没有侵入 Track 输入、地形形态、海岸或土方模块。

### 4.3 节点链

模块内部共 19 个节点：

```text
MATERIAL_seed_layers
    -> MATERIAL_generate_raw_weights
    -> MATERIAL_blur_stone
    -> MATERIAL_blur_gravel
    -> MATERIAL_blur_sand
    -> MATERIAL_priority_normalize
    -> MATERIAL_keep_* / MATERIAL_bind_*
    -> MATERIAL_merge_unity_layers
    -> MATERIAL_enable_switch
    -> OUT_UNITY_TERRAIN_LAYERS
```

节点职责：

| 节点组 | 职责 |
|---|---|
| `MATERIAL_seed_layers` | 从 height 复制出四个同分辨率权重层 |
| `MATERIAL_generate_raw_weights` | 使用既有 Mask 计算初始权重 |
| `MATERIAL_blur_*` | 对 Stone、Gravel、Sand 各做 2 voxel、1 pass 平滑 |
| `MATERIAL_priority_normalize` | 按优先级消除重叠并归一化 |
| `MATERIAL_keep_*` | 每个分支只保留一个 HeightField 层 |
| `MATERIAL_bind_*` | 写入 `unity_hf_terrainlayer_file` |
| `MATERIAL_merge_unity_layers` | 合并 height 与四个权重层 |
| `MATERIAL_enable_switch` | 根据 HDA Toggle 选择只输出 height 或五层输出 |
| `OUT_UNITY_TERRAIN_LAYERS` | 独立模块出口 |

HDA 全部内部子节点数量：

```text
220 -> 241
```

增量为 21：

- `60_MATERIAL_LAYERS` Subnet：1。
- Subnet 内部节点：19。
- `70_OUTPUT/OUTPUT_material_layers` Object Merge：1。

### 4.4 初始权重规则

核心规则等价于：

```text
stone =
    max(
        smooth(0.35, 0.80, cliff),
        coast_rock
    )

sand =
    beach

gravel =
    max(road, shoulder)
    + max(cut, fill) * 0.10

grass =
    1 - stone - gravel - sand
```

设计意图：

- Grass 是默认地表。
- 真正陡峭的 cliff 和海岸岩壁进入 Stone。
- Beach 直接进入 Sand。
- Road/Shoulder 进入 Gravel。
- Cut/Fill 只贡献少量 Gravel，避免大面积土方全部变成碎石。

当前规则全部复用既有 Mask，没有新增昂贵地形分析节点，也没有重复计算坡度、海岸距离或道路距离。

### 4.5 优先级与归一化

三层 Blur 后使用固定优先级：

```text
Stone > Sand > Gravel > Grass
```

处理顺序：

1. Stone 直接 Clamp。
2. Sand 乘以 `(1 - Stone)`。
3. Gravel 乘以 `(1 - Stone) * (1 - Sand)`。
4. Grass 使用剩余权重。
5. 四层除以总和，避免数值漂移。

隔离验证结果：

```text
四层权重和 Min: 0.9999998799
四层权重和 Max: 1.0000000894
最大绝对误差:   1.2014e-7
```

归一化满足 Unity Terrain Splat Weight 的基本要求。

### 4.6 Unity TerrainLayer 路径绑定

每个材质层分支写入 Primitive String Attribute：

```text
unity_hf_terrainlayer_file
```

绑定关系：

```text
terrain_grass  -> TL_PCG_Grass.terrainlayer
terrain_stone  -> TL_PCG_Stone.terrainlayer
terrain_gravel -> TL_PCG_Gravel.terrainlayer
terrain_dirt   -> TL_PCG_Sand.terrainlayer
height         -> 空路径
```

Height 层明确清空 `unity_hf_terrainlayer_file`，避免它被 Houdini Engine 误识别成可视 TerrainLayer。

### 4.7 Output 接线

`70_OUTPUT` 新增：

```text
OUTPUT_material_layers
```

该 Object Merge 指向：

```text
../../60_MATERIAL_LAYERS
```

最终接线：

```text
60_MATERIAL_LAYERS
    -> 70_OUTPUT/OUTPUT_material_layers
    -> 70_OUTPUT/OUT_HEIGHTFIELD
    -> TerrainCore/OUT_TERRAIN_HEIGHTFIELD
```

既有 `OUTPUT_contract_layers` 仍保留 height、road、shoulder、cut、fill、slope、no_scatter、cliff、water_candidate、artist_lock 等内部数据契约；本阶段只把 Unity 主 Terrain HeightField 输出切换到材质层模块。

### 4.8 Toggle 隔离验证

独立 `hython` 未保存测试：

| `material_layers_enabled` | Primitive Count | Layer Names | Error / Warning |
|---:|---:|---|---|
| 0 | 1 | `height` | 0 / 0 |
| 1 | 5 | `height`, `terrain_grass`, `terrain_stone`, `terrain_gravel`, `terrain_dirt` | 0 / 0 |

Toggle 能完整切断四个权重层输出，不会留下空 Layer Primitive。

## 5. Unity Terrain 接入

### 5.1 场景语义变化

场景发生大规模 YAML 重排，但 GameObject 名称多重集合没有增减：

```text
新增 GameObject: 0
删除 GameObject: 0
```

真正的类型级增量是：

```text
MonoBehaviour: 44 -> 48
```

新增的 4 个 MonoBehaviour 是 Houdini Engine 为四个 Terrain 权重层生成的 Volume Part 数据，不是四个额外 GameObject。

### 5.2 HEU Volume Cache

父提交只序列化：

```text
height
```

提交 12 序列化：

```text
height
terrain_grass
terrain_stone
terrain_gravel
terrain_dirt
```

五层共同状态：

- Resolution：513 × 513。
- Tile：0。
- Strength：1。
- Geo：`OUT_TERRAIN_HEIGHTFIELD`。
- Object：`TerrainCore`。
- TerrainData GUID：`d4e45b44006984e43bc32e236be6b10a`。

四个可视层均通过稳定 TerrainLayer GUID 绑定到 `Assets/PCG/Materials/Terrain/`。

### 5.3 当前 TerrainData

Unity MCP 从 AssetDatabase 读取：

```text
Path:
Assets/HoudiniEngineAssetCache/Working/Terrain/
TerrainCore/OUT_TERRAIN_HEIGHTFIELD/Terrain/Tile0/TerrainData.asset

Heightmap Resolution: 513
Alphamap Resolution:  513
Alphamap Layers:      4
Size:                 (3069, 458.385101, 3069)
```

TerrainLayer 顺序：

```text
0 Grass
1 Stone
2 Gravel
3 Sand
```

Terrain 组件继续保持：

- `m_DrawInstanced = 1`。
- `m_HeightmapPixelError = 5`。
- `m_SplatMapDistance = 1000`。
- TerrainCollider 继续引用同一 TerrainData。

### 5.4 当前权重分布

提交 HIP 的 513 × 513 输出统计：

| Layer | Min | Max | Mean |
|---|---:|---:|---:|
| Grass | 0 | 1 | 0.526448 |
| Stone | 0 | 1 | 0.330070 |
| Gravel | 0 | 1 | 0.143482 |
| Sand / `terrain_dirt` | 0 | 0 | 0 |

当前场景的 Beach Mask 没有产生非零 Sand 权重，因此：

- Sand 绑定链已经存在。
- Unity TerrainData 已经装载 Sand TerrainLayer。
- 但当前提交没有用非零 Sand 区域验证最终视觉。

**状态：[功能接入完成，Sand 视觉覆盖待验证]**

### 5.5 Working Cache 可移植性

TerrainData 仍位于：

```text
Assets/HoudiniEngineAssetCache/Working/
```

该目录被 `.gitignore` 排除。场景 YAML 保存了 TerrainData GUID，但目标提交没有提交对应 TerrainData 资产。

因此干净检出后的真实恢复路径仍是：

```text
打开场景
    -> Houdini Engine 可用
    -> Terrain HDA Recook
    -> 重建 Working Cache TerrainData
```

这与“移动端运行时只消费 Bake 后 Unity 原生资源”的长期目标仍有差距。正式交付必须 Bake 到受版本控制的稳定目录，例如：

```text
Assets/PCG/Generated/Terrain/
```

### 5.6 Track Recook 噪声

提交场景同时重新序列化了 Track 输出：

| 输出 | Vertex Count | Index Buffer | Vertex Payload |
|---|---:|---|---|
| Road | 2,148 | 拓扑 Hash 不变 | 数据 Hash 改变 |
| Shoulders | 4,296 | 拓扑 Hash 不变 | 数据 Hash 改变 |
| Collision | 6,444 | 拓扑 Hash 不变 | 数据 Hash 改变 |

Road AABB 保持一致；Shoulders/Collision AABB 有小幅变化：

```text
Center Y: 72.78116 -> 72.530716
Extent X: 516.5584 -> 516.99207
Extent Y: 77.47807 -> 77.728516
Extent Z: 512.0154 -> 512.4509
```

提交没有修改 Track HDA 或 Track HIP，因此这些变化属于场景 Recook/序列化伴随内容，不是 Phase 12 材质层算法的直接实现。

## 6. HIP 与 HDA 保存状态

### 6.1 提交资产

```text
Terrain.hda:
118,732 -> 122,968 bytes

PCG_Bike_Terrain.hip:
820,388 -> 912,543 bytes
```

目标 HDA Definition：

```text
Type: pcgbike::Terrain::1.0
Library: Assets/PCG/HDA/Terrain.hda
```

提交 HIP 保存了新增材质模块、输出接线和 Cook 结果。

### 6.2 当前 Houdini Live Scene

只读现场：

```text
HIP: PCG_Bike_Terrain.hip
Node: /obj/Terrain1
Definition: Assets/PCG/HDA/Terrain.hda
Root Error: 0
Root Warning: 0
Material Output Cook State: cooked
```

当前实例：

- 已解锁。
- `matchesCurrentDefinition=false`。
- HIP 存在未保存修改。

因此本文没有把 Live Dirty 状态当作提交事实，也没有执行 `allowEditingOfContents()`、保存 HIP 或更新 HDA Definition。

全树只读扫描：

```text
Scanned Nodes: 1431
Errors: 0
Warnings: 18
```

18 个 Warning 仍来自既有 HeightField `name` 属性和 Alpha Volume Visualization，不是材质层节点；`60_MATERIAL_LAYERS` 与其输出节点自身 Error/Warning 均为 0。

## 7. 参数接口回归

Phase 11 的验证脚本：

```text
HoudiniProject/PCG_Track_21.0.440/
scripts/tools/validate_terrain_shape_params.py
```

对 Output Mask 页签使用严格参数列表：

```text
no_scatter_extra
cliff_start
cliff_full
water_max_slope
water_max_height
```

提交 12 在该页签新增：

```text
terrain_material_output_folder
    -> material_layers_enabled
```

但没有同步修改验证脚本，实际执行结果：

```text
FAIL: Output Mask parameters changed
```

这不是 HDA Cook 失败，也不代表材质权重错误；它表示 Phase 11 建立的参数接口测试合约已经与新 UI 不一致。

**状态：[待修复]**

推荐修复方式：

1. 明确材质层配置应属于 Output Mask、Overview，还是独立顶级/高级页签。
2. 更新 `check_interface_contract()` 的允许结构。
3. 增加 `material_layers_enabled` 的存在、默认值和 Disable/Enable 输出断言。
4. 新增权重层名、路径、分辨率、范围和总和自动验证。
5. 保证旧的五个 Mask 参数仍按原顺序存在。

不能简单删除旧断言；应把“允许的新结构”变成新的明确合约。

## 8. 性能、渲染与移动端边界

### 8.1 CPU / Houdini Editor

| 阶段 | CPU / Editor 成本 | Runtime 成本 |
|---|---|---|
| Seed Layers | 复制四个 513² HeightField | 0 |
| Raw Weights | 1 次 Volume Wrangle | 0 |
| Blur | 3 个串行 Volume Blur，2 voxel、1 pass | 0 |
| Normalize | 1 次 Volume Wrangle | 0 |
| Split / Bind | 5 个 Blast + 5 个 Attribute Wrangle | 0 |
| HEU Import | 构建 Alphamap 与 TerrainLayer 引用 | 0 |
| Bake 后 Player | 无 HAPI、无 Houdini Cook | Unity Terrain 渲染成本 |

本阶段新增成本集中在编辑器 Cook/Recook。当前 513² 分辨率可控，但 1025/2049 档位会按像素数近似平方增长，三个串行 Blur 会成为明显的开发期 CPU 成本。

扩展时应优先：

- 继续复用既有 Mask。
- 合并可合并的权重处理。
- 避免每新增一种材质就复制完整独立分析链。
- 高分辨率只用于最终 Bake，不作为日常交互默认档。

### 8.2 Unity Terrain GPU 与带宽

当前正好四个可视 TerrainLayer：

- Grass。
- Stone。
- Gravel。
- Sand。

按 Unity Terrain 常规四层分组，四层可由一张 RGBA Control Map 表达，不会因为第五层触发额外 Add Pass。是否保持单 Terrain Draw Pass 仍应通过 Frame Debugger 和目标设备验证。

当前 TerrainLayer 只有 Diffuse：

- 无 Normal Map 采样。
- 无 Mask Map 采样。
- 无 Metallic 纹理。
- Smoothness 为常量。

这对 Mali、Adreno 和 Apple GPU 的带宽较友好，但地表法线细节和材质响应较弱。移动端优先保持四层上限；如果后续加入第五层，应先评估额外 Terrain Pass、Control Map、纹理采样和 Tile GPU 带宽。

### 8.3 RenderPass、RT 与 Shader Variant

本提交没有修改：

- Shader。
- HLSL。
- Material Shader Keyword。
- RendererFeature。
- ScriptableRenderPass。
- URP Renderer。

因此：

```text
新增 RenderPass: 0
RenderPassEvent: 不适用
新增 RenderTexture: 0
新增 Blit/MRT: 0
新增 Shader Keyword: 0
新增 Shader Variant: 0
```

`#pragma multi_compile_instancing` 与 Variant 数量在本提交中不适用，因为没有新增或修改 Shader。Terrain 组件自身继续启用 `Draw Instanced`。

### 8.4 内存与资源

当前 Alphamap：

```text
513 × 513 × 4 channels
```

四层权重可容纳在一张 Control Map 中。TerrainLayer Diffuse Texture 均保留 Mipmap、Read/Write Off 和平台压缩，有利于移动端内存；但五个 TerrainLayer 资产中只有四个进入运行链，未使用 Dirt 应清理或正式接入，避免无效资源长期进入构建依赖分析。

尚未执行：

- Android/iOS IL2CPP Build。
- Frame Debugger Terrain Pass 验证。
- Mali/Adreno/Apple GPU 真机 Profiling。
- 四层与五层 Terrain 的 DrawCall/带宽对照测试。

## 9. 验证记录

### 9.1 Git

- 目标提交：`396c357a2f6b69fbf2a93f290d32712f2dfed717`。
- 父提交：`8fa6a1d5f35843b0a51d5dac88f8329c8835195f`。
- 13 个文件变化。
- 新增 5 个 TerrainLayer 和 5 个资产 `.meta`。
- 未修改 Houdini Engine Unity 插件。
- 未提交 `Assets/PCG/Materials/Terrain.meta`。

### 9.2 Houdini MCP Preflight

```text
Houdini Version: 21.0.440
18811 RPC: connected
3055 health: healthy
Codex Houdini MCP tools: discovered
Current HIP: PCG_Bike_Terrain.hip
```

没有出现“连接层已通但当前会话未热加载工具”的问题。

### 9.3 HDA 解包对比

使用 Houdini `hotl -t` 对父提交和目标提交进行 VCS-friendly 解包：

```text
HDA Size: 118,732 -> 122,968 bytes
Public Parm Objects: 159 -> 161
All Subchildren: 220 -> 241
New Module: 60_MATERIAL_LAYERS
New Output Bridge: OUTPUT_material_layers
```

没有整包重建或覆盖当前 HDA；解包只用于只读审计。

### 9.4 隔离 Hython

目标提交 HIP：

- `OUT_UNITY_TERRAIN_LAYERS` Force Cook：Error 0，Warning 0。
- Primitive：5。
- Point：5。
- 五层分辨率均为 513 × 513。
- 四个材质权重范围均在 0～1。
- 权重和最大绝对误差约 `1.2e-7`。
- Toggle Off：只输出 height。
- Toggle On：输出 height + 4 层。
- 测试过程未保存 HIP/HDA。

接口回归：

```text
validate_terrain_shape_params.py
FAIL: Output Mask parameters changed
```

### 9.5 Unity MCP

Unity AssetDatabase 已识别：

- 5 个 TerrainLayer。
- 2 个 Working Cache TerrainData。
- 主 TerrainData GUID 与场景引用一致。
- 主 TerrainData Heightmap 513。
- 主 TerrainData Alphamap 513、4 Layers。
- TerrainLayer 顺序为 Grass、Stone、Gravel、Sand。

文档生成后的交付验证：

- `AssetDatabase.Refresh(ForceSynchronousImport)`：成功。
- Unity Editor：2022.3.62f2。
- Play / Pause：False / False。
- Compiling / Updating：False / False。
- `Assets/PCG/Scenes/PCG.unity`：已加载、有效、Build Index 0、Root Count 11。
- 当前场景为 Dirty；本文没有保存或覆盖场景。
- 最近 30 分钟 Console Error：0。
- 最近 30 分钟 Console Exception：0。

## 10. 当前状态矩阵

| 功能 | 状态 | 当前结论 |
|---|---|---|
| Terrain 材质模块边界 | 已完成 | 独立 `60_MATERIAL_LAYERS` |
| 材质层 Feature Toggle | 已完成 | Off 仅 height，On 输出五层 |
| Grass 权重 | 已完成 | 默认剩余地表 |
| Stone 权重 | 已完成 | Cliff + Coast Rock |
| Gravel 权重 | 已完成 | Road/Shoulder + 少量 Cut/Fill |
| Sand 权重 | 已接入 | 绑定正确，当前提交权重全 0 |
| 四层归一化 | 已验证 | 最大误差约 `1.2e-7` |
| Unity TerrainLayer 引用 | 已完成 | Grass/Stone/Gravel/Sand |
| Dirt TerrainLayer | 未使用 | 当前没有任何运行链引用 |
| TerrainData Alphamap | 已生成 | 513，4 Layers |
| TerrainData 稳定 Bake | 未完成 | 仍位于 ignored Working Cache |
| 文件夹 `.meta` | 未完成 | `Assets/PCG/Materials/Terrain.meta` 未提交 |
| Phase11 Shape Validator | 回归 | Output Mask 严格合约未同步 |
| 材质层自动测试 | 未完成 | 无 Layer 名称/路径/权重测试脚本 |
| Shader / Variant | 无变更 | 没有新增 Shader 风险 |
| RenderPass / RT | 无变更 | 没有新增带宽 Pass |
| Android/iOS Build | 未执行 | 待验证 |
| 移动端真机 Profiling | 未执行 | Mali/Adreno/Apple GPU 待验证 |

## 11. 下一阶段建议

1. 提交 `Assets/PCG/Materials/Terrain.meta`，保证 Unity 文件夹 GUID 稳定。
2. 修复 `validate_terrain_shape_params.py` 的 Output Mask 合约，并把材质 Toggle 纳入自动验证。
3. 新增材质层验证脚本，断言五层名称、513 分辨率、TerrainLayer 路径、0～1 范围和权重和。
4. 明确 Dirt/Sand 数据契约：删除未使用 Dirt，或正式增加 Dirt 权重；不要继续保留语义冲突。
5. 为 Beach Mask 准备确定性测试夹具，确保 Sand 产生非零权重并在 Unity 中可见。
6. 将 TerrainData 从 HoudiniEngineAssetCache Working Bake 到 `Assets/PCG/Generated/Terrain/`，验证干净检出无需临时 Cache 即可打开场景。
7. 将 Track Recook 与 Terrain 材质层提交拆分，避免无关 Vertex Payload 和场景 YAML 噪声进入功能提交。
8. 用 Frame Debugger 确认四层 Terrain 没有额外 Add Pass，并记录 DrawCall、SetPass 和 Control Map。
9. 对 257/513/1025 分辨率记录 Cook 时间、TerrainData 内存和 Collider 成本，移动端默认保持 513 或更低。
10. 执行 Android/iOS IL2CPP Build 与 Mali/Adreno/Apple GPU 真机 Profiling，再决定是否增加 Normal/Mask Map。
