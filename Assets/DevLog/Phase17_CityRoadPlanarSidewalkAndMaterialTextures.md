# Phase 17 开发日志：CityRoad 统一边界、二维人行道分区与材质贴图

> 文档类型：提交增量快照  
> 记录日期：2026-08-10  
> 目标提交：`7928792fffc7fed7a762141a6aea5209cd153d20`（提交信息：`17`）  
> 父提交：`e4f9773a4bb333f01aab39c215187c84175e23fc`（Phase16 文档提交）  
> CityRoad 场景：`Assets/PCG/Scenes/PCG_City.unity`  
> CityRoad HDA：`Assets/PCG/HDA/City/CityRoad.hda`  
> CityRoad HIP：`HoudiniProject/PCG_Track_21.0.440/PCG_Bike_CityRoad.hip`

## 1. 日志范围与证据

本文只记录 Git 提交 `7928792` 相对父提交 `e4f9773` 的开发增量，不重复 Phase1～Phase16 已记录的 Track、Terrain、Lake、TerrainLayer、CityRoad 单输入迁移、Junction Mouth 合约、V7 自适应弯角布线、Bake 工具与移动端 Shader 基础。

Phase17 的实际开发内容由四条关联主线组成：

```text
最终道路拓扑
    -> 使用统一圆角闭环做道路专用二维约束三角化
    -> 旧道路只提供高度、UV 和分片 metadata
    -> Houdini 内统一 -Y 绕序，适配 HAPI 到 Unity 的手性转换

人行道/路牙
    -> 从 Corridor/Junction 条带拼接改为非道路空地区域直接填充
    -> 场地轮廓 + 最终道路孔洞 + 开放端 seam 组成二维约束
    -> 按封闭区域生成 SidewalkRegion，并从同一最终边界生成 Curb

Unity Live Preview
    -> 新增 SidewalkRegion_ Presentation 命名识别
    -> 继续只启用 Presentation Renderer，关闭 HEU backing duplicate

美术接入
    -> 新增 2 张 1024×1024 路面/墙面纹理
    -> Sidewalk/Curb 材质绑定正式 BaseMap
```

证据等级：

- **[提交验证]**：直接读取目标提交 Git diff、二进制资产大小、C#、材质、TextureImporter `.meta` 和场景 YAML。
- **[HDA 结构验证]**：使用 Houdini `21.0.440` 的独立 `hython` 进程分别安装父/目标 HDA、创建全新锁定实例并对比节点、连接、参数模板和 Output Flag；没有保存或覆盖 HDA/HIP。
- **[HDA 隔离 Cook]**：独立加载目标 HIP，Force Cook 关键中间节点和六个正式输出并读取 detail metadata。
- **[Houdini Live Scene 只读验证]**：Houdini MCP preflight 通过；当前 Live HIP 正是目标 `PCG_Bike_CityRoad.hip`，只读取 Scene、节点与 Warning，没有修改或保存。
- **[Unity 现场验证]**：使用 Unity MCP 读取 AssetDatabase 中的纹理/材质、打开场景、Editor 状态和 Console；通过场景 YAML复核 Renderer、Mesh、材质 GUID、HDA Path 与 Live/Bake 状态。
- **[待复验]**：当前实现和测试道路图已通过拓扑合约，但正式 Bake、Unity/Houdini 两种输入下的分包一致性、移动端纹理格式和真机性能仍未闭环。

本提交没有修改 `Assets/Plugins/HoudiniEngineUnity/`。项目专用 Live Preview 兼容逻辑仍位于 `Assets/PCG/Editor/CityRoad/`，保持官方 Houdini Engine Unity 插件零侵入。

## 2. 提交概览

| 项目 | 数值 |
|---|---:|
| Commit | `7928792fffc7fed7a762141a6aea5209cd153d20` |
| Author / Date | `liyuan` / 2026-08-10 21:37:22 +08:00 |
| Changed Files | 10 |
| Added / Deleted Lines | `+31814 / -33814` |
| CityRoad HDA | 224,485 → 247,051 bytes（+10.05%） |
| CityRoad HIP | 332,659 → 332,720 bytes（+0.0183%） |
| Unity Scene | 4,162,380 → 4,335,996 bytes（+4.17%） |
| 新增纹理源文件 | 2 张，共 6,891,234 bytes |
| Shader / RendererFeature / RenderPass | 0 个新增或修改 |

本提交修改：

1. `Assets/ArtResources_Mountainbike/Environment/SceneModels/Mountainbike/Texture/T_Tile_04_D.png`
2. `Assets/ArtResources_Mountainbike/Environment/SceneModels/Mountainbike/Texture/T_Tile_04_D.png.meta`
3. `Assets/ArtResources_Mountainbike/Environment/SceneModels/Mountainbike/Texture/T_Wall05B_D.png`
4. `Assets/ArtResources_Mountainbike/Environment/SceneModels/Mountainbike/Texture/T_Wall05B_D.png.meta`
5. `Assets/PCG/Editor/CityRoad/CityRoadLivePreviewController.cs`
6. `Assets/PCG/HDA/City/CityRoad.hda`
7. `Assets/PCG/Materials/M_PCG_CityRoad_Curb.mat`
8. `Assets/PCG/Materials/M_PCG_CityRoad_Sidewalk.mat`
9. `Assets/PCG/Scenes/PCG_City.unity`
10. `HoudiniProject/PCG_Track_21.0.440/PCG_Bike_CityRoad.hip`

本提交没有配套 Python Patch 入库。HDA 功能事实来自正式 HDA 结构、节点注释/VEX、目标 HIP 和 Unity Scene，而不是当前工作区的未跟踪测试文件。

## 3. 统一最终道路边界

### 3.1 Phase16 遗留结构

Phase16 已实现宽度驱动的 V7 普通道路弯角和自适应 Corner Rail，但生产道路、人行道和路牙仍存在不同来源：

- Road Surface 主要来自 Corridor/Junction 的既有拓扑链。
- Sidewalk/Curb 由 Corridor 与 Junction 两条条带分支生成后 Merge。
- 各分支分别处理边界、端盖和圆角，容易在接缝处出现重叠、缝隙或绕序差异。
- Unity 侧 Sidewalk/Curb Presentation 按 Corridor/Junction 分包，不能表达“整块封闭空地”语义。

Phase17 的核心是让 Road、Sidewalk 和 Curb 消费同一套最终圆角边界。

### 3.2 道路专用约束三角化

新增道路链：

```text
SIDEWALK_PLANAR_ROAD_BOUNDARY_CLEAN
    -> ROAD_PLANAR_TRIANGULATE_FINAL_BOUNDARY
    -> ROAD_PLANAR_CLASSIFY_FROM_FINAL_BOUNDARY
    -> ROAD_PLANAR_DELETE_OUTSIDE
    -> ROAD_PLANAR_REMOVE_UNUSED_POINTS
    -> ROAD_PLANAR_PROJECT_AND_TRANSFER
    -> ROAD_PLANAR_METADATA_FROM_LEGACY
    -> ROAD_PLANAR_WINDING_FOR_UNITY
```

职责：

| 节点 | 职责 |
|---|---|
| `ROAD_PLANAR_TRIANGULATE_FINAL_BOUNDARY` | 只输入最终道路闭环做二维约束三角化，避免场地外轮廓和开放端 seam 干扰道路孔洞 |
| `ROAD_PLANAR_CLASSIFY_FROM_FINAL_BOUNDARY` | 按闭环偶奇规则标记道路内部三角并统计面积 |
| `ROAD_PLANAR_DELETE_OUTSIDE` | 在 Detail 分类结束后统一 Blast 外部三角，避免 Primitive 并行删除共享点 |
| `ROAD_PLANAR_REMOVE_UNUSED_POINTS` | 清理孤立点 |
| `ROAD_PLANAR_PROJECT_AND_TRANSFER` | 从旧道路采样高度、UV、`materialuv` 和切线 |
| `ROAD_PLANAR_METADATA_FROM_LEGACY` | 从旧道路转移 Road/Junction/Segment 分片 metadata |
| `ROAD_PLANAR_WINDING_FOR_UNITY` | 统一 Houdini 绕序以适配 HAPI 的手性转换 |

拓扑事实源变化：

```text
最终几何拓扑 = 最终圆角边界的二维约束三角化
高度 / UV / 切线 / 分片属性 = 旧道路最近面采样
```

旧道路不再作为最终面连接方式，只保留属性采样职责。这使道路几何边界与后续人行道孔洞、路牙偏移使用同一闭环。

### 3.3 Unity 手性与绕序

`ROAD_PLANAR_METADATA_FROM_LEGACY` 标记 Houdini 中朝 `+Y` 的三角，`ROAD_PLANAR_WINDING_FOR_UNITY` 只翻转这些面，使 HDA 最终道路面统一保持 `-Y` 绕序。HAPI 转换到 Unity 时发生手性转换，Unity 中才成为 `+Y` 正面。

这是几何导出合约，不是 Shader 双面渲染补丁：

- 继续使用 Back Face Culling。
- 不要求材质改为双面。
- 不增加 Shader Variant。
- 当前没有需要翻转的面时，Reverse SOP 会因可选组不存在报告 Warning；正式输出仍无 Error/Warning。

### 3.4 当前道路结果

目标 HIP：

| 指标 | 数值 |
|---|---:|
| Points | 442 |
| Triangles | 446 |
| Vertices | 1,338 |
| Planar Area | 67,117.75 m² |
| Inside Triangle Count | 446 |
| Error | 0 |

`CITYROAD_TOPOLOGY_CLASSIFY_ROAD` 改为消费 `ROAD_PLANAR_WINDING_FOR_UNITY`，因此 Road Presentation、Collision 和 Piece 分包都从新的最终道路拓扑继续向下游传递。

## 4. 二维约束人行道分区

### 4.1 从条带拼接改为区域直接填充

`CITYROAD_CURB_SIDEWALK_MERGE_V4` 的生产输入由：

```text
CITYROAD_CORRIDOR_CURB_SIDEWALK_V4
CITYROAD_JUNCTION_CURB_SIDEWALK_V4
```

改为：

```text
CURB_PART_ATTR_CLEAN
SIDEWALK_PART_ATTR_CLEAN
```

节点注释明确规定：生产人行道只合并“直接填充的空地区域”，旧 Corridor/Junction 条带分支保留为历史对照，不再作为正式输出事实源。

新模式的空间语义是：

- 道路以最终圆角边界作为孔洞。
- 非道路封闭区域作为 Sidewalk Region 直接填充。
- `sidewalk_width` 在 Fill Mode 中不再控制条带宽度，目标 metadata 写入 `sidewalk_width_ignored_in_fill_mode = 1`。
- Sidewalk 可在 Curb 下方保留覆盖以避免缝隙，目标 metadata 写入 `sidewalk_curb_underlay_overlap = 1`。

### 4.2 场地与约束输入

新增约束链：

```text
SIDEWALK_SITE_BOUNDARY_FROM_ROAD
    -> SIDEWALK_SITE_AT_HEIGHT

最终道路闭环
    -> SIDEWALK_PLANAR_ROAD_BOUNDARY_CLEAN

开放端连接
    -> SIDEWALK_OPEN_END_SIDE_CONNECTORS
    -> SIDEWALK_PLANAR_CONNECTOR_CLEAN

三类曲线合并
    -> SIDEWALK_PLANAR_CONSTRAINT_MERGE
    -> SIDEWALK_PLANAR_CONSTRAINT_HEIGHT
    -> SIDEWALK_PLANAR_CONSTRAINT_FUSE
    -> SIDEWALK_PLANAR_MARK_CONSTRAINT_EDGES
```

`SIDEWALK_SITE_BOUNDARY_FROM_ROAD` 根据道路最外端点生成不额外扩张的场地轮廓。道路端盖与场地边界重合，避免场地区域绕过道路末端后重新连通。

约束输入在 Merge 前通过三个 Attribute Delete 节点瘦身，只保留位置、拓扑和 Primitive Group，降低属性不匹配和不必要的 Cook 数据量。

### 4.3 开放道路末端 seam

`SIDEWALK_OPEN_END_SIDE_CONNECTORS` 为每个真实开放端生成左右两条二维连接：

1. 从道路末端沿局部切线命中局部场地边。
2. 将最终道路边界上的真实左右端角分别连接到同侧端点。
3. 禁止使用全局最近角点配对，避免长道路或复杂场地中左右连接交叉。
4. 使用最终可见道路的非共享边做近点/向内探测吸附，避开内部拼接边。

目标测试图：

| 指标 | 数值 |
|---|---:|
| Open End Terminals | 8 |
| Connector Count | 16 |
| Partition Seam Edges | 8 |
| Unmatched Connectors | 0 |
| Local Ray Miss | 0 |
| Connector Contract | Pass |

`SIDEWALK_OPEN_END_SEAM_SHATTER` 保留一条 Boolean Shatter 辅助路径，用 Connector Plane 做分片；正式最终人行道仍由后续二维约束三角化和显式 seam 分区验收。

### 4.4 约束三角化与分类

```text
SIDEWALK_PLANAR_MARK_CONSTRAINT_EDGES
    -> SIDEWALK_PLANAR_TRIANGULATE
    -> SIDEWALK_PLANAR_CLASSIFY
    -> SIDEWALK_PLANAR_DELETE_ROAD
    -> SIDEWALK_PLANAR_REMOVE_UNUSED_POINTS
    -> SIDEWALK_PLANAR_MARK_SEAMS
    -> SIDEWALK_TOPOLOGY_VALIDATE
    -> SIDEWALK_REGION_CONNECTIVITY
    -> SIDEWALK_REGION_METADATA
```

- 场地轮廓、最终道路孔洞和开放端 seam 都是不可跨越边。
- 分类使用二维轮廓内外关系，不再依赖“Primitive 质心接近 Road Surface”作为最终删除逻辑。
- 删除道路内部三角后统一清理孤立点，避免 Primitive 并行 `removeprim(..., 1)` 级联删除共享三角。
- Connectivity 使用 seam 将开放端两侧区域分开。
- Region Metadata 写入稳定 Region ID、`city_part`、Material、UV 与 Unity Presentation 名称。

### 4.5 拓扑 Fail Closed 验证

`SIDEWALK_TOPOLOGY_VALIDATE` 断言：

- 道路内部顶点数必须为 0。
- 穿越道路边界的边数必须为 0。
- 与道路存在正面积重叠的三角数必须为 0。
- 每个真实开放端必须生成左右 Connector。
- Connector/Seam 数与 Terminal 数必须满足合约。

目标 HIP：

| 指标 | 数值 |
|---|---:|
| Points / Triangles / Vertices | 423 / 411 / 1,233 |
| Filled Regions | 9 |
| Region Partitions | 9 |
| Road-inside Vertices | 0 |
| Boundary-crossing Edges | 0 |
| Positive-overlap Triangles | 0 |
| Topology OK | 1 |
| Validation Method | `constrained_2d_final_boundary_exact_audit` |

## 5. 从最终边界生成路牙

### 5.1 统一边界生成

`CURB_SIDEWALK_BUILD_FROM_FINAL_BOUNDARY` 继续从 `ROAD_UNION_ROUND_FINAL_BOUNDARY` 构造路牙，但新增第二输入 `ROAD_ADAPTIVE_RESAMPLE`，用于识别真正的开放端：

- 只跳过 `connected_road_count <= 0` 的真实开放端端盖。
- Junction 连接端不再因近似位置判断被误删。
- Exterior/Interior Loop 分别统计。
- Curb Riser、Top 与可选 Connector Face 继续写入独立组和 `city_desired_normal`。

### 5.2 退化面与绕序校验

新增 `CURB_SIDEWALK_REMOVE_DEGENERATE`：

- 在 Boolean/三角化后删除面积 `<= 1e-4` 的近零面积面。
- 避免 Houdini Double 到 Unity Float 转换后出现退化三角和错误绕序。

`CURB_SIDEWALK_ORIENT_METADATA` 扩展为：

- 显式 Curb/Sidewalk Top 继续按 Y 法线修正。
- 对分区产生但未保留旧 Group 的水平侧面也进行 Top 朝向识别。
- 垂直面继续使用生成阶段写入的 `city_desired_normal`。

`CURB_SIDEWALK_STATS` 新增强制验收：

- `remaining_reversed_top_face_count` 必须为 0。
- `degenerate_primitive_count` 必须为 0。
- 否则主动 `error()`，阻止错误几何进入 Unity。

### 5.3 当前路缘/人行道结果

| 指标 | 数值 |
|---|---:|
| Points / Primitives / Vertices | 1,334 / 1,863 / 5,589 |
| Curb Loops | 4（Exterior 1 / Interior 3） |
| Curb Top Faces | 365 |
| Curb Vertical Faces | 730 |
| Curb Endcap Skipped Edges | 77 |
| Corrected Top Faces | 731 |
| Corrected Vertical Faces | 298 |
| Remaining Reversed Top / Vertical | 0 / 0 |
| Degenerate Primitives | 0 |
| Error / Warning | 0 / 0 |

`CURB_PART_ATTR_CLEAN` 和 `SIDEWALK_PART_ATTR_CLEAN` 在进入正式 Merge 前只保留 Unity 分包、材质、法线和基础 Road/Region Metadata，避免将 Boolean/验证辅助属性带进运行时 Mesh。

## 6. Piece 分包与 Output 行为

### 6.1 SidewalkRegion 分包

`CITYROAD_TOPOLOGY_TRANSFER_SIDEWALKCURB` 改为按：

```text
sidewalk_region_id + city_part
```

进行分包，目的：

- 每块空地保留连续 Sidewalk Top。
- Curb Vertical/Top 使用独立材质包。
- Presentation 命名从 Road Corridor/Junction 语义改为 `SidewalkRegion_*`。

目标 Unity 场景包含：

```text
17 个 CityRoad_SidewalkRegion_*_sidewalk_Instance1
 4 个 CityRoad_SidewalkRegion_*_curb_Instance1
合计 21 个 SidewalkRegion Presentation
```

### 6.2 Sidewalk Output Render Flag

`OUT_SIDEWALK_CURB` 的 Render Flag 从 Off 改为 On，Display Flag 保持 Off。提交内注释说明目的是在多输出 HDA 中保持该输出可供 Houdini Engine 正确导入，避免 Packed Instance 被创建为 Disabled Renderer。

独立新建 HDA 实例验证：

```text
OUT_SIDEWALK_CURB.outputidx = 1
Render Flag = On
Display Flag = Off
```

其他 Output Flag 没有变化。

### 6.3 六类输出

目标 HIP 的 Internal Test Graph：

| Output SOP | Index | Points | Primitives | Vertices | Error / Warning |
|---|---:|---:|---:|---:|---:|
| `OUT_ROAD_SURFACE` | 0 | 21 | 21 | 21 | 0 / 0 |
| `OUT_SIDEWALK_CURB` | 1 | 13 | 13 | 13 | 0 / 0 |
| `OUT_ROAD_MARKING_POINTS` | 2 | 51 | 0 | 0 | 0 / 0 |
| `OUT_ROAD_COLLISION` | 3 | 442 | 446 | 1,338 | 0 / 0 |
| `OUT_ROAD_CENTERLINE_GRAPH` | 4 | 17 | 4 | 17 | 0 / 0 |
| `OUT_ROAD_MARKINGS` | 6 | 21 | 21 | 21 | 0 / 0 |

相对 Phase16 Internal Test Graph：

- RoadSurface Packed Piece：21 → 21。
- Sidewalk/Curb Packed Piece：21 → 13。
- Marking Points：51 → 51。
- Collision：397/352/1,056 → 442/446/1,338。
- Centerline：17/4/17，保持不变。
- Markings Packed Piece：21 → 21。

Houdini HIP 使用 Internal Test Graph，Unity 场景使用 `unity_road_network` Parameter/Spline 输入；目标 HIP 的 13 个 Packed Sidewalk/Curb 与 Unity Scene 的 21 个 `SidewalkRegion_` Presentation 不是同一输入/同一统计口径。正式 Bake 前必须建立自动对账，不能把两者直接当作相同 Piece 数。

### 6.4 输出索引缺口仍存在

```text
Definition Outputs = 6
Output SOP Indexes  = 0, 1, 2, 3, 4, 6
```

Phase17 仍未把 `OUT_ROAD_MARKINGS` 从 6 调整为 5。Render Flag 修复只解决 Sidewalk Output 导入状态，不代表六输出索引合约已经闭环。

## 7. Unity Live Preview 适配

### 7.1 修改内容

`CityRoadLivePreviewController.HasTopologyPieceName()` 原来只识别：

- `Corridor_`
- `Junction_`

Phase17 新增：

- `SidewalkRegion_`

因此 `EnterLivePreview()` 的可见 Renderer 判断继续成立：

```text
可见 Output Role
    && 位于 Corridor_/Junction_/SidewalkRegion_ Presentation 下
    && 不是 Collision
```

### 7.2 性能与作用域

- 文件位于 `Assets/PCG/Editor/` 并受 `#if UNITY_EDITOR` 包围，不进入 Player Runtime。
- 没有新增 Update 中的大规模几何扫描；只扩展父级名称判断的一个字符串条件。
- 继续避免 HEU backing Renderer 与 Presentation Renderer 重叠渲染。
- 不修改 Houdini Engine Unity 插件。

如果没有该适配，新 `SidewalkRegion_` Renderer 会被识别为非 Presentation，Cook 后可能保持 Disabled；因此 C# 小改动是 HDA 分包语义迁移的必要 Unity 侧桥接。

## 8. 新增纹理与材质绑定

### 8.1 新增纹理

| Texture | GUID | Source Bytes | Unity 状态 |
|---|---|---:|---|
| `T_Tile_04_D.png` | `217c0982f8f3aeb43810b67fe2010ec6` | 5,785,630 | 1024×1024，DXT5，11 Mips |
| `T_Wall05B_D.png` | `d29872285eed5194c98695448976e234` | 1,105,604 | 1024×1024，DXT5，11 Mips |

AssetDatabase 只读验证：

- `Texture2D` 尺寸：1024×1024。
- 当前 Windows Editor 格式：DXT5。
- `isReadable = false`，不保留 CPU 可读副本。
- Mipmap Count：11。
- Filter：Bilinear。
- Wrap：Repeat。
- Aniso：1。

TextureImporter：

- sRGB：On。
- Mipmap：On。
- Streaming Mipmaps：Off。
- Max Texture Size：2048；源图实际只有 1024。
- Default/Standalone/iPhone/WebGL/Android 都没有启用 Override。
- Crunch Compression：Off。
- Compression Quality：50。

### 8.2 Curb 材质

`M_PCG_CityRoad_Curb.mat`：

| 参数 | Phase16 | Phase17 |
|---|---|---|
| `_BaseMap` | None | `T_Wall05B_D.png` |
| `_TileMeters` | 2.0 | 2.61 |
| `_Smoothness` | 0.25 | 0.25 |
| `_BaseTint` | `(0.52, 0.54, 0.55)` | 不变 |

### 8.3 Sidewalk 材质

`M_PCG_CityRoad_Sidewalk.mat`：

| 参数 | Phase16 | Phase17 |
|---|---|---|
| `_BaseMap` | 旧 Asphalt/Gravel 纹理 GUID `4587...` | `T_Tile_04_D.png` |
| `_TileMeters` | 2.0 | 2.0 |
| `_Smoothness` | 0.18 | 0.18 |
| `_BaseTint` | White | 不变 |

两个材质均：

- Shader：`PCG/CityRoad/SimpleSurface`。
- Render Queue：2000 / Opaque。
- GPU Instancing：On。
- Double Sided GI：Off。

### 8.4 移动端纹理风险

当前 Unity MCP 报告的 DXT5 是 Windows Editor 导入结果，不代表 Android/iOS 最终格式。由于两个 `.meta` 没有 Android/iPhone Override：

- 移动端格式由项目默认平台压缩策略决定。
- 不能确认最终是 ETC2 RGBA、ASTC 还是其他格式。
- 两张纹理都带 Alpha/DXT5 路径，若实际不需要 Alpha，应在后续检查源 Alpha 和移动端格式，避免无意义的 RGBA 带宽。
- Streaming Mipmaps 关闭；1024² 两张纹理规模仍可控，但大量城市材质继续增加时需要统一 Streaming/Mipmap Limit 策略。
- 当前 DXT5 全 Mip 链理论显存约 1.33 MiB/张、合计约 2.67 MiB；这是桌面格式估算，不是移动端实测。

## 9. Unity 场景重 Cook 结果

### 9.1 Scene 序列化规模

| 指标 | Phase16 | Phase17 | 变化 |
|---|---:|---:|---:|
| Scene Bytes | 4,162,380 | 4,335,996 | +4.17% |
| YAML Lines | 50,814 | 48,505 | -2,309 |
| GameObject / Transform | 239 / 239 | 227 / 227 | -12 / -12 |
| MonoBehaviour | 178 | 170 | -8 |
| Mesh | 81 | 77 | -4 |
| MeshRenderer / MeshFilter | 155 / 155 | 147 / 147 | -8 / -8 |
| MeshCollider | 1 | 1 | 不变 |
| Total Vertices | 24,895 | 26,869 | +1,974（+7.93%） |
| Max Vertices / Mesh | 1,788 | 3,078 | +1,290 |
| UInt32 Mesh | 0 | 0 | 不变 |
| EditorOnly GameObject | 229 | 217 | -12 |
| Root Count | 6 | 6 | 不变 |
| PrefabInstance | 0 | 0 | 不变 |

场景行数、对象和 Mesh 数下降，但文件字节和顶点数上升。原因是 Sidewalk 从多个小 Corridor/Junction 条带合并为更连续的区域 Mesh，单 Mesh 承载了更多顶点数据。

最大 Mesh 从 Road Markings 的 1,788 顶点变为：

```text
OUT_SIDEWALK_CURB_1_mesh = 3,078 vertices
OUT_SIDEWALK_CURB_13_mesh = 1,224 vertices
```

仍远低于 65,535，可继续使用 UInt16 Index。

### 9.2 Presentation 层级变化

| Presentation | Phase16 | Phase17 |
|---|---:|---:|
| Corridor Road/Marking/Side | 18 × 3 | Road/Marking 18 × 2 |
| Junction Road/Marking/Side | 7 × 3 | Road/Marking 7 × 2 |
| SidewalkRegion | 0 | 21 |
| Enabled Presentation Renderer | 75 | 71 |
| Disabled Backing Renderer | 80 | 76 |

净变化：原 25 个 Corridor/Junction SidewalkCurb Presentation 被 21 个 `SidewalkRegion_` Presentation 替代，因此可见 Renderer 减少 4 个；Backing Renderer 同步减少 4 个。

### 9.3 阴影策略

```text
Cast Shadows Off = 142（Phase16 为 150）
Cast Shadows On  = 5（不变）
Receive Shadows  = 沿用 Phase16 合约
```

减少的 8 个 Cast Off Renderer 与总 Renderer 减少量一致。本提交没有改变 Shader Shadow Pass 或材质透明状态。

### 9.4 材质引用

场景 YAML 中材质 GUID 出现次数：

| Material | Phase16 | Phase17 |
|---|---:|---:|
| Asphalt | 76 | 76 |
| Marking | 76 | 76 |
| Sidewalk | 76 | 52 |
| Curb | 76 | 13 |

这是场景序列化 GUID 出现次数，包含 HEU Material Cache、Backing 和 Presentation 引用，不等于 DrawCall。变化与 Sidewalk/Curb 新分包方式一致。

### 9.5 HDA 与 Live/Bake 状态

- `_assetPath` 仍为 `Assets/PCG/HDA/City/CityRoad.hda`。
- HDA GUID 仍为 `67d84be2a5065e14493d6b0d83e29db8`。
- 单 `unity_road_network` Parameter/Spline 输入仍存在。
- Phase16 三个 Adaptive Corner 参数仍为 `0.2 / On / Off`。
- 没有 `CityRoad1_Bake`。
- PrefabInstance 数量为 0。
- Live HDA 输出仍为 `EditorOnly`。
- 当前 Unity 打开的 `PCG_City` 场景已加载、Root Count 6，但为 Dirty；本次日志任务没有保存该场景。

因此 Phase17 仍是 Live Preview/开发期 Cook 结果，不是 Runtime Bake 交付。

## 10. HDA Definition 与 HIP 状态

### 10.1 HDA 结构

| 指标 | Phase16 | Phase17 |
|---|---:|---:|
| CityRoadCore Children | 126 | 167 |
| 新增 / 删除节点 | - | +41 / 0 |
| HDA Inputs | 0..0 | 0..0 |
| HDA Outputs | 6 | 6 |
| Parameter Templates | Phase16 | 无新增、删除或修改 |
| DialogScript SHA | Phase16 | 不变 |

新增 41 个节点主要分为：

- 道路二维约束三角化：8 个。
- Sidewalk 场地/道路薄体与辅助分区：7 个。
- Sidewalk 最终二维约束、分类、清理、Connectivity 和 Metadata：18 个。
- 开放端边界/Connector/Seam：5 个。
- Curb/Sidewalk 清理与退化面保护：3 个。

这是模块化节点链，不是把全部逻辑塞进单个 Python 黑盒；复杂判断仍位于职责明确的 Attribute Wrangle 中，并通过中文节点注释说明输入、输出和维护边界。

### 10.2 HIP/Definition 同步

```text
HIP                   = PCG_Bike_CityRoad.hip
Asset                 = /obj/CityRoad_DEV
Type                  = pcgbike::CityRoad::1.0
Definition            = Assets/PCG/HDA/City/CityRoad.hda
Asset Locked          = true
Matches Definition    = true
CityRoadCore Children = 167
```

Phase16 已完成的 HDA 事实源收敛没有回退。HIP 只增加 61 bytes，说明本阶段主要增量正确保存在正式 HDA，而不是重新把可编辑 HDA Contents 整包嵌入 HIP。

### 10.3 文件指纹

| 文件 | Phase16 SHA-256 | Phase17 SHA-256 |
|---|---|---|
| CityRoad HDA | `D86746F78E1D16F58EF548368783490EBAF16376BC7E3A09FF892210084025DA` | `90CB5ABAF38EFC6BB8B4EEDED1756F34D01AF02EBDB910103B0A71C66CC56442` |
| CityRoad HIP | `7CE3DAED1F1B4707E03F6F7E4C355AE0770F9A95C2809438F8AE1092FC3698A5` | `F618CEF2D67644E9363B2194F81497035978713289676F45C3DBA8F7C3E1442A` |

## 11. Cook Warning 与遗留拓扑风险

六个正式 Output SOP Force Cook 都是 0 Error / 0 Warning；Sidewalk/Curb 强校验也通过。但完整网络 Force Cook 后仍有 6 个非阻断 Warning：

| 节点 | Warning |
|---|---|
| `CITYROAD_LOCAL_ROAD_MERGE` | 输入属性不一致 |
| `CITYROAD_MARKING_HELPERS_MERGE` | Approach/Junction Mouth 辅助属性不一致 |
| `CITYROAD_ROAD_FIX_REVERSED_FACES` | 可选组 `cityroad_road_final_reversed` 不存在 |
| `CITYROAD_ORIENT_JUNCTION_TOP_V4` | 可选组 `v4_reverse_top_faces` 不存在 |
| `ROAD_PLANAR_WINDING_FOR_UNITY` | 可选组 `road_planar_reverse_for_unity` 不存在 |
| `TUTORIAL_V2_ROAD_MERGE_SHELL` | Tutorial Lab 输入属性不一致 |

相对 Phase16：

- 正式 Curb/Sidewalk Merge 的 `road_corner_*` 属性 Warning 已通过输入瘦身消除。
- Marking Helper 属性 Warning 仍存在。
- 新 Road Winding Reverse 在“没有需要翻转的面”时产生空组 Warning。
- Tutorial Lab Warning 不进入正式输出，但应继续与生产链隔离。

建议对可选 Reverse Group 使用显式 Bypass/组存在检查，并在 Merge 前初始化统一属性，避免 Warning 掩盖真实回归。

## 12. 性能、渲染与兼容性

### 12.1 CPU / GPU 分工

| 阶段 | CPU / Houdini / Editor | GPU / Unity | 结论 |
|---|---|---|---|
| Road/Sidewalk 生成 | Triangulate2D、分类、Connectivity、属性转移、少量 Boolean | 无 | 开发期 Cook 成本增加 |
| 拓扑验证 | 检查穿界边、重叠、开放端合约、绕序和退化面 | 无 | Bake 前 Fail Closed |
| Live Preview | Editor C# 识别 Presentation/Backing | 渲染 Live Mesh | 不进入 Player |
| Runtime | 禁止 Houdini Cook | 应只渲染 Bake Mesh | 正式 Bake 尚未完成 |

CPU 侧：

- 41 个新 SOP 会增加 Cook 调度和几何内存。
- Triangulate2D/Boolean 属于编辑器生成成本，可接受但必须建立 Cook 时间基线。
- 最终道路属性转移使用 `xyzdist`，运行在 Houdini Cook，不进入移动端 Runtime。
- Attribute Delete 在约束 Merge 前瘦身，可降低属性传播成本。

GPU/运行时侧：

- 可见 Renderer 从 75 降至 71，理论上减少最多 4 个 Draw 提交，但实际需要 Frame Debugger 验证。
- 总顶点增加 7.93%，顶点读取和 Mesh 内存上升。
- 最大 Sidewalk Mesh 增至 3,078 顶点；仍为 UInt16，但更大连续 Region 会降低小粒度 Frustum Culling 能力。
- 当前顶点规模仍很低，移动端主要风险更可能来自 Renderer/材质状态、阴影、纹理带宽和未来城市规模扩张，而不是单个 3K 顶点 Mesh。

### 12.2 RenderPass 与带宽

本提交没有 RendererFeature 或 RenderPass：

- `RenderPassEvent`：不适用。
- 新增 RenderTexture：0。
- Blit / MRT / Fullscreen Pass：0。
- 不引入 Tile-Based GPU 中途 Flush。

带宽新增来自两张 BaseMap 和场景顶点增加，而不是额外 Pass。

### 12.3 Shader、Instancing 与 Variant

本提交没有修改 `PCG_CityRoad_SimpleSurface.shader`：

- Instancing 支持方式不变；两个目标材质 `enableInstancing = true`。
- 自定义 keyword 数量不变。
- Variant 风险不变。
- Pass、half/float 精度、纹理采样与 Overdraw 策略不变。
- 新贴图只是替换 `_BaseMap` 资源，不新增纹理采样。

因此不能把新的贴图接入写成 Shader 功能新增；它是既有单 BaseMap Shader 的美术资源绑定。

### 12.4 移动端兼容性

- 不使用 Geometry Shader。
- 不新增平台特定 GPU API。
- 全部 Mesh 仍为 UInt16 Index。
- TextureImporter 没有 Android/iOS Override，需要在目标平台确认格式和 Alpha。
- Mipmap 已开启，有利于远距离带宽和缓存；Aniso 1 对道路斜视角清晰度较保守。
- 真机尚未验证 Mali/Adreno/Apple GPU 的纹理格式、带宽、DrawCall、顶点吞吐和内存。

## 13. 问题与状态变化

### 13.1 已解决当前测试图：Road/Sidewalk/Curb 边界来源不一致

- Phase16：三类几何仍可能来自不同 Corridor/Junction 分支。
- Phase17：最终道路闭环同时驱动 Road Triangulation、Sidewalk Hole 与 Curb Offset。
- 验证：道路内 Sidewalk 顶点、跨边界边和正面积重叠均为 0。

### 13.2 已解决当前测试图：开放端左右区域错误连通

- 使用局部切线探测和左右同侧 Connector。
- 8 个开放端得到 16 Connector、8 Seam。
- Unmatched 与 Local Ray Miss 都为 0。

### 13.3 已解决：新 Region Presentation 被错误关闭

- Live Preview 识别新增 `SidewalkRegion_`。
- `OUT_SIDEWALK_CURB` Render Flag 开启。
- Unity Scene 已序列化 21 个启用的 Region Presentation 结构。

### 13.4 已解决当前测试图：退化面和残留反向 Top

- 面积 `<= 1e-4` 的 Primitive 在方向校验前删除。
- `remaining_reversed_top_face_count = 0`。
- `remaining_reversed_vertical_face_count = 0`。
- `degenerate_primitive_count = 0`。

### 13.5 已完成：Sidewalk/Curb 正式纹理绑定

- Sidewalk 改用 `T_Tile_04_D`。
- Curb 新增 `T_Wall05B_D`。
- 材质仍使用现有 SimpleSurface Shader，没有增加 Variant。

### 13.6 待评估：Region Mesh 变大

- Mesh 数减少 4。
- 可见 Renderer 减少 4。
- 总顶点增加 7.93%。
- 最大 Mesh 从 1,788 增至 3,078 顶点。

当前仍安全，但更大城市图可能形成超大连续 Sidewalk Region，需建立 Chunk/Region 上限，避免 Culling 粒度和局部 Bake 更新范围失控。

### 13.7 未解决：Houdini/Unity Piece 数对账

- Internal Test HIP：Sidewalk/Curb Packed Piece = 13。
- Unity Scene：SidewalkRegion Presentation = 21。
- 输入源和统计口径不同，尚无自动映射报告。

### 13.8 未解决：输出索引 5 缺失

- Definition 声明六输出。
- Markings 仍使用 Index 6。
- 必须在正式 Bake 前修正并建立自动断言。

### 13.9 未解决：没有 Runtime Bake

- 无 Bake Prefab。
- 无活动 Bake Instance。
- Scene 仍为 Live HDA/EditorOnly。
- Player Build 仍应被 Guard 阻止。

### 13.10 延续风险：同名旧 HDA

仓库根目录旧 `CityRoad.hda` 不在本提交变化中。Unity、HIP 和任何 Patch 必须继续固定正式路径：

`Assets/PCG/HDA/City/CityRoad.hda`

## 14. 验证记录

### 14.1 Git

- 目标提交与标题精确匹配：`7928792...` / `17`。
- 父提交：`e4f9773...` / `Phase16`。
- 10 个文件变化；新增两张纹理及 `.meta`。
- 没有修改 Houdini Engine Unity 插件。
- 当前 HDA/HIP/Scene/C#/Material/Texture 与目标提交一致。

### 14.2 Houdini

- Preflight：通过。
- Houdini：`21.0.440`。
- RPC `18811`：connected。
- MCP `3055`：healthy。
- Tool Discovery：available。
- 当前 Live HIP：目标 `PCG_Bike_CityRoad.hip`。
- 当前 Asset：`/obj/CityRoad_DEV`。
- Asset 锁定且匹配正式 Definition。
- 本次只读验证没有执行 `allowEditingOfContents()`，没有修改、更新或保存 HDA/HIP。
- 独立 Force Cook 六个正式输出：0 Error / 0 Warning。
- 全网 Force Cook：0 Error 节点，6 个非阻断 Warning 节点。

### 14.3 Unity

- Unity Editor：`2022.3.62f2`。
- 当前未播放、未暂停、未编译、未刷新 AssetDatabase。
- 当前打开场景：`Assets/PCG/Scenes/PCG_City.unity`，Loaded/Valid，Root Count 6，Dirty，Build Index -1。
- AssetDatabase 已找到两张纹理和两份材质，GUID 与目标 `.meta` 一致。
- Unity MCP 路径读取通用 `mainTexture` 时，因为 `PCG/CityRoad/SimpleSurface` 只有 `_BaseMap`、没有 `_MainTex`，产生两条工具反射 Error；它不是项目编译错误。随后使用材质 YAML 的 `_BaseMap` 做事实验证。
- 两次调用 `console-clear-logs` 均因 Unity MCP 自身占用 `Temp/mcp-server/ai-editor-logs.txt` 而失败，并由清理工具本身写入 Error/Exception；这是 MCP 日志存储文件锁问题，不是 Phase17 C# 编译、HDA Cook 或资产导入错误。
- Phase17 文档已通过 `AssetDatabase.Refresh(ForceSynchronousImport)` 导入；刷新后 Editor 未播放、未暂停、未编译且未更新 AssetDatabase。
- 因日志缓存无法清空，任务收尾使用新的时间窗口隔离检查项目日志，并单独保留上述 MCP 工具错误说明。
- 最终隔离窗口最近 1 分钟 Unity Console Error / Exception / Warning 均为 0。

### 14.4 工作区保护

写日志前已有用户未跟踪内容：

- `Assets/ArtResources_Mountainbike/Shaders/Terrain/`。
- `Assets/PCG/Generated/`。
- Track/Terrain 操作文档及 Word 临时文件。
- Tests、FBX 与既有模型文件。

目标提交中的两张纹理已被 Git 跟踪，不属于当前未跟踪工作区。其余既有未跟踪内容没有被移动、覆盖或计入 Phase17 开发成果。

## 15. 当前状态矩阵

| 功能 | 状态 | 当前结论 |
|---|---|---|
| 最终道路统一边界 | 已完成当前测试图 | 约束三角化决定最终拓扑 |
| 旧道路属性转移 | 已完成 | 只转移高度/UV/切线/metadata |
| Unity 手性绕序 | 已完成当前测试图 | HDA -Y → Unity +Y |
| Sidewalk 直接填充 | 已完成当前测试图 | 9 个 Filled Region |
| 开放端 Connector/Seam | 已完成当前测试图 | 8 Terminal / 16 Connector / 8 Seam |
| Sidewalk 拓扑验收 | 已通过 | Inside/Crossing/Overlap/Unmatched 均为 0 |
| Curb 最终边界生成 | 已完成当前测试图 | 4 Loops，真实开放端跳过端盖 |
| 退化面/反向面保护 | 已通过 | Remaining/degenerate 均为 0 |
| SidewalkRegion 分包 | 已完成 Unity Live Scene | 17 Sidewalk + 4 Curb Presentation |
| Live Preview Region 识别 | 已完成 | Editor-only 字符串识别扩展 |
| Sidewalk Output Render Flag | 已完成 | Render On / Display Off |
| Sidewalk/Curb 贴图 | 已接入 | 1024² BaseMap，Mipmap On |
| 移动端纹理格式 | 待验证 | 无 Android/iPhone Override |
| HDA/HIP 事实源 | 已保持 | 锁定且匹配正式 HDA |
| HDA 中间 Warning | 待清理 | Full Cook 6 个 Warning |
| HDA Output 索引 | 未完成 | 缺 Index 5 |
| Unity/Houdini Piece 对账 | 未完成 | 13 Packed vs 21 Presentation，输入口径不同 |
| Runtime Bake Prefab | 未完成 | 无 Bake 资产/实例 |
| Shader/Variant | 无阶段变化 | 无新增 keyword/Pass/RT |
| 移动端真机 Profiling | 未执行 | 需 Mali/Adreno/Apple GPU 数据 |

## 16. 下一阶段建议

1. 建立 Sidewalk 自动化回归图集：单开放端、双开放端、十字路口、T 路口、封闭街区、凹场地、窄缝、相邻平行路和不同 Road Level。
2. 对每个图断言 Road-inside Vertex、Boundary Crossing、Positive Overlap、Connector/Seam、Region Count、Degenerate 和 Winding 全部合约。
3. 给直接填充 Region 增加最大面积/最大顶点/最大 Bounds 阈值；超限时按稳定 Region/Chunk 拆分，避免城市扩大后形成超大不可剔除 Mesh。
4. 修复三个生产链空组 Reverse Warning，并在 Merge 前统一 Marking/Junction 辅助属性；Tutorial Lab Warning 与正式输出隔离。
5. 将 `OUT_ROAD_MARKINGS.outputidx` 从 6 修正为 5，并统一 Definition、SOP、HEU Geo、Scene Presentation 与 Bake Validator 断言。
6. 建立 Houdini Internal Test Graph 与 Unity `unity_road_network` 的 Piece 对账报告，记录 Region ID、`city_part`、Packed Count、Renderer Count、材质和 Bounds。
7. 完成 `Cook + Validate + Update Bake`，Player 只消费原生 Mesh/Collider/Material/Metadata，不依赖 Houdini Cook。
8. 检查两张新纹理的 Alpha 是否必要，并为 Android/iOS 明确 ASTC/ETC2、Max Size、Compression Quality 与 Streaming 策略。
9. 在 Mali/Adreno/Apple GPU 上对比 Phase16/17：DrawCall、SetPass、顶点数、纹理带宽、显存、Region Culling 和 Collider 成本，确认减少 4 个 Renderer 是否足以抵消 +7.93% 顶点及新增纹理带宽。
