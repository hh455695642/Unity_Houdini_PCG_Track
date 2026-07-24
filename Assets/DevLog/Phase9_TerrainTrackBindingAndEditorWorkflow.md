# Phase 9 开发日志：Terrain Track 安全绑定与编辑器工作流

> 文档类型：Phase 9 增量开发日志
>
> 记录日期：2026-07-24
>
> 关联提交：`d9ce99b325b41535bbba5fc53f2d3bcdd71f7101`（提交说明：`9`）
>
> 基线版本：Phase 8 日志提交 `646dc6f94d4c34e1f1e31cbfbd3e0322e2f18a6e`
>
> 记录范围：只记录 `d9ce99b` 相对父提交 `646dc6f` 新增、调整、替换或移除的内容

## 1. 日志范围与证据

本文不是 Track/Terrain 全量快照。Phase 1～Phase 8 已有的 Unity Spline 输入、Knot Contract V1、赛道横倾、道路宽度 Ramp、自适应采样、拆分输出、Terrain 生成、Guide Mesh、Lake Constraint、道路 Shader 与起点 Prefab 接口继续以前述阶段日志为准。

本阶段只回答一个增量问题：当 Unity 中的 Track HDA 被重载、Cook、禁用、删除或暂时失去有效 Display SOP 时，Working Terrain 如何安全地绑定当前 Track、合并异步 Cook，并在解绑后恢复基础地形。

证据标记：

- **[已验证]**：可由 Git 父子差异、文本源码、Unity 场景序列化数据或 HDA 可提取参数契约直接确认。
- **[已验证代码结构]**：控制流与保护逻辑已进入提交，但本次没有重新执行 Unity/Houdini Live Cook。
- **[提交已实现]**：二进制 HDA/HIP 或 Recook 后场景已经进入提交，但不能仅凭二进制大小或 YAML 行数推导视觉质量。
- **[历史还原]**：由当前 HDA 参数、提交场景和工作区迁移脚本共同还原；迁移脚本本身未被提交，不计入 Phase 9 正式文件。
- **[待复验]**：需要 Unity Editor、Houdini Session、Player Build 或目标设备上的专项验证。
- **[未改变]**：本提交没有修改对应 Shader、材质、渲染管线或运行时渲染路径。

提交链：

```text
646dc6f  Phase_8
    -> d9ce99b  9
```

## 2. 提交概览

提交时间：2026-07-24 14:49:32 +08:00。

Git 统计为 12 个文件、`+23,290/-23,695`。其中绝大多数行数来自 `Assets/PCG/Scenes/PCG.unity` 的 Houdini Engine Recook 与 YAML 重排；不能把约 4.6 万行场景差异等同于同规模的独立业务代码。

| 模块 | Phase 9 增量 | 当前状态 |
|---|---|---|
| Terrain 绑定组件 | 从“写入路径并请求 Cook”扩展为绑定、解绑、恢复、状态与重试完整生命周期 | [已验证代码结构] |
| Fail-Closed | Track 不可用、Cook 失败或 Display SOP 无效时，不再继续消费陈旧路径 | [已验证代码结构] |
| Cook 调度 | 合并重复请求，识别 Cook/Reload 占用，并保留一次替换 Cook | [已验证代码结构] |
| 组件禁用/删除 | 禁用即解绑；删除后由短生命周期恢复队列完成基础地形 Cook | [已验证代码结构] |
| Terrain HDA | 新增隐藏绑定门控，精简为 Track/Guide/Lake 三输入与 HeightField/Metadata 两输出 | [提交已实现；内部节点按历史还原] |
| 自定义 Inspector | 新增绑定/解绑按钮、状态提示与 Debug 折叠区 | [已验证] |
| 测试可见性 | Authoring 程序集向 `PCGBike.Editor.Tests` 开放 internal 成员 | [已验证；本提交没有测试源码] |
| Unity 场景 | Binding 最终保存为禁用、路径清空、Auto Cook 开启、基础地形恢复成功 | [已验证] |
| 历史日志 | Phase 4/5 将 Terrain Preview Mesh Output 2 修正为历史已移除输出 | [已验证] |
| 渲染 | Shader、Material、RendererFeature、RenderPass、RT 与 Keyword 均未修改 | [未改变] |

## 3. Terrain Track Display SOP 绑定重构

### 3.1 从一次性路径同步升级为显式状态机

**状态：[已验证代码结构]**

`TerrainTrackDisplaySopBinding` 新增五态：

| 状态 | 含义 |
|---|---|
| `Detached` | Track 影响已关闭，Working Terrain 使用基础 HeightField |
| `WaitingForSession` | Houdini Session、Terrain HDA、绑定参数或 Track Display SOP 尚未就绪 |
| `Bound` | 已绑定当前 Track Display SOP，且没有待处理 Terrain Cook |
| `CookPending` | 绑定或解绑已发生，Terrain Cook 正在等待、提交或执行 |
| `Error` | 参数读写或 Cook 失败，需要检查 Houdini Engine 与 Unity Console |

组件额外保存以下调试状态：

- `_lastBoundPath`
- `_lastBindingStatus`
- `_lastCookSummary`
- `_pendingDetach`
- `_manualDetach`

Inspector 和外部工具可通过 `BindingState`、`HasPendingCook`、`LastBindingStatus`、`LastCookSummary` 读取状态，不再只能依赖一条自由文本 `_status`。

### 3.2 双参数绑定契约

**状态：[已验证]**

旧版本只写：

```text
track_display_sop_path
```

Phase 9 要求 Terrain HDA 同时存在：

```text
track_display_sop_path
track_binding_enabled
```

绑定顺序：

```text
解析当前 Track Display SOP
    -> 写入 track_display_sop_path
    -> 写入 track_binding_enabled = 1
    -> 合并并请求一次 Terrain Cook
```

解绑顺序：

```text
track_binding_enabled = 0
    -> 清空 track_display_sop_path
    -> 请求一次恢复基础地形的 Terrain Cook
```

先关门控、再清路径是有意设计。即使第二步写入失败，旧 Display SOP 路径也已失去生产作用，不会继续静默影响 Terrain。

如果 Terrain HDA 尚未暴露这两个参数，组件不会把旧契约当作可用绑定，而是请求 Terrain Reload 并保持 `WaitingForSession`。

### 3.3 Track 来源解析与 Fail-Closed

**状态：[已验证代码结构]**

可用 Track 必须同时满足：

- `_trackAssetRoot` 存在且所属 GameObject 在 Hierarchy 中激活。
- `HEU_HoudiniAsset` 存在且其 GameObject 激活。
- Track `AssetID` 有效。
- HAPI 能返回有效 Display Geo、节点 ID 与非空节点路径。

以下情况会转入解绑/恢复基础地形，而不是保留最后一次成功路径：

- Track Root 被禁用或删除。
- Track HDA 尚未加载出有效 Asset ID。
- Track Cook 失败。
- Track Reload/Cook 期间没有有效 Display SOP。
- HAPI 无法解析 Display SOP 节点路径。

成功的 Track Cook/Reload 会设置 `_forceRebind`，即使路径字符串没有变化，也会安排一次 Terrain 重建，从而消费 Track 的新几何。

### 3.4 禁用、删除、Undo 与 Hierarchy 生命周期

**状态：[已验证代码结构]**

生命周期变化：

- `OnEnable`：刷新 Track/Terrain 事件订阅，并恢复未完成的绑定或解绑任务。
- `OnDisable`：不再只是停止轮询；改为显式安排“解绑 Track 并恢复基础地形”。
- `OnDestroy`：先尝试立即解绑，再把 Terrain Root 交给 `TerrainTrackDetachRecovery`。
- `OnValidate`：字段变化后重新绑定引用与调度。
- `hierarchyChanged`：Track/Terrain 层级变化后重新评估来源。
- `Undo.undoRedoPerformed`：撤销/重做后重新评估绑定状态。

`TerrainTrackDetachRecovery` 是 Editor-only 静态恢复队列。组件已经销毁、无法再接收 Cook 事件时，它仍会等待有效 Session 和 Terrain 参数，写入：

```text
track_binding_enabled = 0
track_display_sop_path = ""
```

待 Terrain 空闲后，以 `bUploadParameters=false` 请求一次异步 Cook，然后从队列移除该 Terrain。

该队列只存在于当前 Editor 进程内，不是跨 Unity 重启的持久任务。如果关闭 Editor 前 Houdini Session 始终不可用，仍需下次打开项目后专项确认基础地形状态。

## 4. 异步 Cook 合并与恢复

### 4.1 从超时退出改为持续收敛

**状态：[已验证代码结构]**

旧实现使用 15 秒 deadline：超时后清理陈旧路径、停止绑定并打印一次 Warning。Phase 9 移除固定 deadline，改为每 0.25 秒检查一次，直到：

- Session 与 Terrain 就绪；
- 绑定/解绑参数写入成功；
- 待处理 Cook 已完成；
- 或组件进入可稳定停止调度的状态。

这避免大型 HDA Reload 超过固定时限后绑定永久停止，但也意味着异常状态下 Editor 会持续进行低频就绪检查。后续仍需用 Profiler 确认长期断开 HARS 时的编辑器开销。

### 4.2 一次在途、一次替换

**状态：[已验证代码结构]**

Cook 状态由三个布尔量表达：

```text
_pendingCook       有业务变化等待提交
_cookRequestIssued 已向 HEU 提交 Cook
_cookAfterCurrent  当前 Cook 完成后还需一次替换 Cook
```

当 Track 在 Terrain Cook 期间再次变化时，不会为每个事件无限追加请求；只合并为“当前一次 + 后续一次”。这能覆盖快速连续 Track Recook，同时抑制 Cook 风暴。

### 4.3 HEU Busy、Reload 与漏事件恢复

**状态：[已验证代码结构；版本兼容性待复验]**

提交 Cook 前同时检查：

- 公共 `HEU_HoudiniAsset.CookStatus`
- 私有 `_requestBuildAction` 的反射值

只有 Terrain 不在 Cook/Reload 且待处理 Build Action 为 `NONE` 时才调用 `RequestCook`。

参数通过 HAPI 直接写入，因此请求 Cook 使用：

```csharp
bUploadParameters: false
```

这样可以避免 HEU 序列化参数缓存中的旧路径在 Cook 前重新上传，复活已经解绑的 Track。

完成路径有两条：

- 正常收到 `CookedDataEvent`。
- 提交 0.75 秒后，轮询发现私有 Build Action 已返回 `NONE`，则用 `LastCookResult` 收敛状态。

如果 Reload 抢占资产，`ReloadDataEvent` 会清除 `_cookRequestIssued`，保留 `_pendingCook`，使合并后的请求能够在 Reload 后重新提交。

反射读取 `_requestBuildAction` 属于 Houdini Engine Unity 插件内部实现依赖。代码在字段不存在时回退为 `NONE`，但升级 HEU 包后必须专项复验 Cook 合并和漏事件恢复。

## 5. Terrain HDA 门控与接口整理

### 5.1 自动绑定、公共输入与空输入优先级

**状态：[提交已实现；内部节点按历史还原]**

`Terrain.hda` 从 99,844 bytes 增至 101,169 bytes。二进制中可直接确认新增隐藏参数：

```text
track_binding_enabled
Label: Track Binding Enabled (Internal)
```

其 Help 明确说明：门控关闭时忽略隐藏 Display SOP 路径，公共 Track 输入仍可使用。

工作区未跟踪迁移脚本记录的预期 Track 来源优先级为：

```text
track_binding_enabled != 0
且 track_display_sop_path 非空
且目标 SOP 存在
    -> 自动绑定的 Track Display SOP
否则若公共 track_geometry 非空且目标存在
    -> 公共 Track Geometry 参数
否则若 HDA Input 0 有效
    -> HDA Input 0
否则
    -> EMPTY_TRACK_FALLBACK
```

因此契约意图是：“Unity 自动解绑”只关闭隐藏自动路径，不错误禁止 Terrain HDA 的公共 Track 输入能力。该优先级表达式没有从提交 HDA 的压缩 SOP Contents 中独立导出复核，不能把具体内部节点拓扑标为已验证。

### 5.2 输入、输出与参数面板精简

**状态：[已验证 HDA 参数脚本；内部 SOP 拓扑待复验]**

提交前后公共输入：

| Input | Phase 8 | Phase 9 |
|---:|---|---|
| 1 | Track Geometry | Track Geometry |
| 2 | Base Terrain | Terrain Guide Meshes |
| 3 | Terrain Guide Meshes | Lake Curves |
| 4 | Lake Curves | 已移除 |

Phase 9 删除 `base_terrain` 参数与 Base Terrain 输入，Guide/Lake 的 HDA Input 索引分别从 3/4 前移到 2/3。工具、说明和后续 HAPI 接入不能继续假定 Input 2 是 Base Terrain。

公共输出由三路精简为两路：

| Output | Phase 8 | Phase 9 |
|---:|---|---|
| 0 | HeightField | HeightField |
| 1 | Metadata | Metadata |
| 2 | Preview Mesh | 已移除 |

同时删除 `debug_preview` 与 `preview_resolution`，避免参数面板继续暴露已经不存在的 Preview Mesh 能力。

本阶段还移除以下旧参数：

- `height_range`
- `min_domain_size`
- `tile_count`
- `auto_base_from_track`
- `base_height`
- `track_height_offset`
- `enable_earthwork_micro_detail`
- `earthwork_micro_detail_amplitude`
- `earthwork_micro_detail_size`

参数 UI 重组为：

```text
Overview
Terrain Shape
  -> Macro / Mid / Detail / Ridge / Erosion
Track & Earthwork
  -> Exact Conform / Track Context / Adaptive Earthwork
Guide Mesh
Lake
Output
Internal
```

大量 Label、Help、范围和 `disablewhen` 同步规范化。尤其需要更正：

| 参数 | Phase 9 正确语义 | 当前默认 |
|---|---|---:|
| `cut_slope` | Cut Transition Width：从路肩向原地形过渡的宽度，不是坡度角 | 24 m |
| `fill_slope` | Fill Transition Width：从路肩向原地形过渡的宽度，不是坡度角 | 30 m |
| `maximum_earthwork_slope` | 真正的最大土方坡度角 | 28° |

`cut_slope` / `fill_slope` 的 UI 范围扩为 0～300 m。Phase 4 中“Cut Slope 24° / Fill Slope 30°”属于旧参数命名造成的历史误读；Phase 9 起应统一按 24 m / 30 m 过渡宽度理解。

### 5.3 无有效 Track 时旁路 Track 形变

**状态：[历史还原；Live Cook 待复验]**

未跟踪迁移脚本显示，本阶段的目标实现将 Track 合约有效性作为两个分支的额外条件：

- Adaptive Earthwork
- Track Context

无有效 Track 时，Adaptive Earthwork 选择关闭分支；Track Context 通过新增 `TRACK_CONTEXT_enable_switch` 回到进入 Earthwork 前的基础 Terrain。目标是让以下状态收敛到同一个结果：

```text
组件禁用
组件删除
自动路径为空
自动路径已失效
Track 暂时没有 Display SOP
Track 合约校验失败
    -> 不执行 Track Context / Adaptive Earthwork
    -> 输出基础地形
```

Track 校验 Warning 语义也从 Manual Domain 特例改为“Track 输入不可用，已生成不含 Track 形变的基础地形”，更贴近实际 Fail-Closed 行为。

工作区当前存在未跟踪的 `patch_terrain_track_binding_safety.py`，其节点路径和表达式与上述 HDA 参数/场景结果一致，但该脚本不属于提交 `9`。本文只把它作为二进制 HDA 的历史还原证据，不把它列为 Phase 9 正式工具或已提交自动化测试；本次也没有借此宣称压缩 SOP 拓扑已独立验证。

## 6. 自定义 Inspector 与程序集边界

### 6.1 面向设计人员的 Inspector

**状态：[已验证]**

新增：

`Assets/PCG/Scripts/Editor/Houdini/Terrain/TerrainTrackDisplaySopBindingEditor.cs`

Inspector 提供：

- `Track Source`
- `Working Terrain`
- `Auto Cook Terrain`
- 当前 `BindingState`
- 状态说明 HelpBox
- “绑定并重建地形”
- “解绑并恢复基础地形”
- Debug 折叠区：Display SOP Path、Pending Cook、Last Cook

支持多对象编辑。多选时隐藏单对象状态详情，但两个操作按钮会遍历所有选中 Binding，并通过 `Undo.RecordObject` 记录操作。

进入或即将进入 Play Mode 时，按钮被禁用。Inspector 顶部明确提示：取消勾选组件会停止 Track 影响并自动恢复 Working Terrain 的基础地形。

### 6.2 Editor-only 与 Player 边界

**状态：[已验证代码结构]**

HAPI、Editor 事件、反射状态、Cook 队列与恢复队列均位于 `#if UNITY_EDITOR` 内。Player 中只保留无操作的公开方法和状态占位：

```text
BindingState = Detached
HasPendingCook = false
LastBindingStatus = "Houdini binding is editor-only."
```

因此本阶段没有把 Houdini 轮询或 Cook 引入每帧 Runtime 路径。

### 6.3 测试程序集可见性

**状态：[已验证；测试未提交]**

新增 `Assets/PCG/Scripts/Terrain/Authoring/AssemblyInfo.cs`：

```csharp
[assembly: InternalsVisibleTo("PCGBike.Editor.Tests")]
```

这为 Editor 测试读取 `PathParameter`、`EnabledParameter` 和 `IsCookBusy` 等 internal 成员提供边界。本提交没有新增 `PCGBike.Editor.Tests` 测试源码，当前工作区的未跟踪 `Assets/PCG/Scripts/Tests/` 不能计入提交 `9`。

## 7. Unity 场景、HDA/HIP 与历史日志

### 7.1 场景最终状态

**状态：[已验证提交序列化结果]**

父提交中 `Terrain1` 的 Binding 为：

```text
m_Enabled: 1
_autoCookTerrain: 0
_lastBoundPath: /obj/Track1/Road
```

提交 `9` 保存为：

```text
m_Enabled: 0
_autoCookTerrain: 1
_lastBoundPath: ""
_bindingState: Detached
_lastBindingStatus: Detached; Working Terrain uses its base heightfield.
_lastCookSummary: Terrain cook completed successfully.
_pendingDetach: 0
_manualDetach: 0
```

这证明提交场景的最终配置是“自动 Cook 打开，但 Binding 组件关闭，Track 路径已清空，基础地形恢复 Cook 已成功”，不是“场景启动时持续自动绑定 Track”。

场景中仍有 `Track1` 与 `Track4` 两个 Track 根对象。一次 HDA Reload/Recook 后，`Track1` 的内部 Houdini Asset/输出对象名保存为 `Track9`，但 Unity 根 GameObject 仍叫 `Track1`。这属于 Session/Recook 序列化身份变化，不应解释为新增第三条正式赛道。

`Track9` 保存时同时记录：

```text
_cookStatus: 0
_lastCookResult: 1
_isCookingAssetReloaded: 1
```

即普通 Cook 状态为空闲、最后结果成功，但 Reload 标志仍为真。因此提交场景证明 Terrain 完成过一次成功恢复 Cook，不等同于整个 Houdini 现场已经完全静止并完成全部回归。

场景还新增了一个根级 `Quad`：

```text
m_IsActive: 0
m_LocalScale: {x: 10000, y: 10000, z: 10000}
Components: Transform + MeshRenderer + MeshFilter + MeshCollider
```

它未激活，且没有提交内说明把它定义为 Terrain 正式输入或交付资产。本文将其记录为场景杂项/待清理风险，不包装为 Phase 9 核心功能。

### 7.2 二进制资产与序列化噪声

**状态：[提交已实现]**

| 文件 | 父提交 | 提交 `9` | 结论 |
|---|---:|---:|---|
| `Terrain.hda` | 99,844 bytes | 101,169 bytes | 新增安全绑定契约与内部门控 |
| `PCG_Bike_Terrain.hip` | 392,796 bytes | 788,334 bytes | 保存 Terrain 开发现场；体积增长不能直接换算为算法规模 |
| `PCG.unity` | `+22,522/-23,570` | 约 4.6 万行父子差异 | 主要为 HEU Recook、Mesh/组件块重排与参数重序列化 |

`UserSettings/Search.settings` 只有编辑器搜索状态变化，不属于 PCG 功能。

### 7.3 Phase 4/5 事实修订

**状态：[已验证]**

Phase 4 和 Phase 5 的输出表各修正一行：

```text
OUT_TERRAIN_PREVIEW_MESH
历史输出；已于 2026-07-23 从当前 Terrain HDA 移除
```

这是历史事实修订，不代表提交 `9` 新增或重新交付 Terrain Preview Mesh。

## 8. 性能、兼容性与运行时边界

### 8.1 CPU、Houdini 与 GPU

| 阶段 | Phase 9 成本 | 运行时影响 |
|---|---|---|
| Editor 空闲且状态稳定 | 无持续 Pump；事件订阅等待变化 | 无 |
| Session/资产未就绪 | 每 0.25 秒进行一次低频就绪检查 | 无 |
| Track 快速连续 Recook | 当前 Cook + 最多一次合并替换 Cook | 无 |
| 禁用/删除 Binding | HAPI 参数写入 + 一次基础地形恢复 Cook | 无 |
| Bake 后 Player | 不应存在 HAPI、轮询或 Terrain Recook | 只消费最终 Unity 资产 |

Cook 合并减少的是编辑器/Houdini 重复工作，不改变 Bake Mesh 的 GPU 顶点数、纹理采样数或 DrawCall。

### 8.2 URP 与渲染资源

本阶段没有修改 Shader、Material、RendererFeature、ScriptableRenderPass 或 URP Renderer：

- 新增 RenderPass：0。
- 新增 RenderTexture：0。
- 新增 Blit/MRT：0。
- 新增 Shader Keyword/Variant：0。
- 新增每帧纹理采样：0。

Terrain HDA 的 Track 门控发生在编辑器 Cook/Bake 阶段，不增加移动端每帧 ALU 或带宽。

### 8.3 兼容性风险

- `_requestBuildAction` 通过反射访问 HEU 私有字段，升级 Houdini Engine Unity 包后必须复验。
- 恢复队列只在 Editor 进程内存中存在，不跨 Editor 重启持久化。
- 持续重试取消了 15 秒上限；HARS 长期不可用时需确认低频 Pump 不产生 Console 噪声或编辑器 GC。
- `RequestCook` 的返回值没有用于判定提交是否被接受；0.75 秒轮询兜底仍需验证不会读取旧 `LastCookResult` 而提前收敛。
- Inspector 的 `Undo.RecordObject` 只记录 MonoBehaviour；HAPI 参数写入和已经发出的 Houdini Cook 不是完整可逆事务。
- `PCGBike.Authoring` 仍依赖 `HoudiniEngineUnity` 类型；本阶段没有执行 Android/iOS IL2CPP Player Build。
- 场景保存的是 Binding 关闭状态。若正式工作流要求打开场景即自动绑定，需要明确启用组件并完成一次闭环验收。

## 9. 本版本验证记录

### 9.1 Git 与文本源码

**状态：[已验证]**

- HEAD：`d9ce99b325b41535bbba5fc53f2d3bcdd71f7101`。
- 父提交：`646dc6f94d4c34e1f1e31cbfbd3e0322e2f18a6e`。
- 提交信息：`9`。
- 12 个文件变化，新增 5 个文件。
- `TerrainTrackDisplaySopBinding.cs`：Git 统计 `+627/-122`。
- 新增自定义 Inspector：105 个 Git 新增行。
- 新增 `AssemblyInfo.cs` 与 `InternalsVisibleTo`。

### 9.2 Unity 场景序列化

**状态：[已验证提交文件；Live Editor 未复验]**

- `Terrain1` Binding 组件类型 GUID 保持不变，旧场景引用没有因本阶段重构丢失。
- Binding 最终为禁用、Detached、路径为空、Auto Cook 开启。
- Last Cook 保存为成功。
- Track/Terrain HDA 与生成对象发生 Recook 后重序列化。
- 本次编写日志没有启动 Play Mode、没有保存场景，也没有把当前未跟踪资产写入提交事实。

### 9.3 Houdini HDA/HIP

**状态：[提交文件已确认；隔离 Cook 未执行]**

- `Terrain.hda` 与 `PCG_Bike_Terrain.hip` 均进入提交。
- HDA 二进制字符串可确认 `track_binding_enabled`、`track_display_sop_path` 与绑定工作流说明。
- HDA 参数脚本可确认 Base Terrain 输入、Preview Mesh 输出与旧参数已经移除，Guide/Lake 输入前移。
- 压缩 SOP Contents 没有通过可用 Houdini 会话独立导出，因此本文不把具体内部 Switch 节点名列为已验证事实。
- 本次没有通过 Houdini 21.0.440 对提交 HDA 重新执行“有效 Track 形变、无效路径回退、禁用后 Hash 等于基础地形”的隔离 Cook。
- 工作区未跟踪迁移脚本包含上述验证逻辑，但不属于提交证据，不能代替正式纳入 Git 的测试。

## 10. 当前状态矩阵

| 功能 | 状态 | 当前结论 |
|---|---|---|
| Terrain 绑定显式状态机 | 已完成 | Detached/Waiting/Bound/CookPending/Error 五态 |
| 双参数绑定契约 | 已完成 | 路径 + Enabled 门控 |
| 无效 Track Fail-Closed | 已完成代码 | 自动转入解绑并恢复基础地形 |
| Track 成功 Recook 后 Terrain 重建 | 已完成代码 | 路径不变也强制安排一次重建 |
| Track Cook 失败处理 | 已完成代码 | 关闭 Track 影响，不继续消费旧路径 |
| 组件禁用恢复 | 已完成代码 | OnDisable 持续完成解绑 |
| 组件删除恢复 | 已完成代码 | 静态恢复队列接管最终 Cook |
| Cook 请求合并 | 已完成代码 | 一次在途 + 最多一次替换 |
| HEU 漏事件恢复 | 已完成代码 | 0.75 秒后用 Build Action/LastCookResult 收敛 |
| 自定义 Inspector | 已完成 | 状态、按钮、Debug、多选与 Undo |
| Player 每帧 Houdini 成本 | 未引入 | 核心逻辑限制在 Editor |
| Terrain HDA 自动路径门控 | 已完成 | Enabled 关闭时忽略隐藏路径 |
| Terrain HDA 公共输入 | 已完成 | Track/Guide/Lake 三路；Guide/Lake 前移至 Input 2/3 |
| Terrain HDA 公共输出 | 已完成 | HeightField/Metadata 两路；Preview Mesh 已移除 |
| Cut/Fill 参数语义 | 已完成 | 24 m/30 m 过渡宽度；真正坡度角由 `maximum_earthwork_slope` 控制 |
| 无 Track 时基础地形一致性 | 待复验 | 提交场景显示成功；尚缺纳入 Git 的 Hash 自动测试 |
| Editor Tests | 未完成 | 只开放 internal，可执行测试源码未提交 |
| HEU 私有字段兼容 | 待复验 | 包升级后需检查 `_requestBuildAction` |
| Editor 重启恢复 | 部分完成 | 组件重启后会重评估；删除恢复队列本身不持久化 |
| Player Build | 未执行 | Android/iOS IL2CPP 仍需验证 |
| 移动端真机 Profiling | 未执行 | 本阶段无新渲染成本，但整体 Bake 资产仍需测量 |

## 11. 下一阶段建议

1. 将 Terrain 绑定测试正式纳入 `PCGBike.Editor.Tests`，覆盖 Enabled/Path 写入顺序、Busy 判定、Cook 合并与状态转换。
2. 提交并整理 HDA 增量迁移脚本；运行 dry-run 和正式验证，记录基础 HeightField Hash、无效路径 Hash、有效 Track 形变 Hash 与禁用恢复 Hash。
3. 增加 Domain Reload/关闭 Unity 前仍无 HARS 的恢复测试，明确跨 Editor 重启的持久恢复策略。
4. 为 `_requestBuildAction` 反射封装增加版本检测或替代的公共 API 路径，并覆盖字段不存在时的行为。
5. 对快速连续 Track Cook、Track Reload、Terrain Reload、Undo/Redo、Hierarchy 禁用/删除执行压力测试，确认只产生一次在途和一次替换 Cook。
6. 明确主场景是否应默认启用 Binding。若需要自动绑定，保存启用状态后复验打开场景、重载 HDA、禁用组件、删除组件四条闭环。
7. 复核 `Track1` 内部输出保存为 `Track9_*` 的命名漂移；Bake 工具应使用稳定语义/GUID，不依赖临时 Session 节点名。
8. 判断根级 10000 倍禁用 `Quad` 是否只是临时验证对象；若无正式用途，从主场景清理并复核 Collider。
9. 更新依赖 Terrain 输入索引的工具与说明：Guide Mesh 使用 Input 2，Lake 使用 Input 3，不再保留 Base Terrain Input 2 假设。
10. 执行 Android/iOS IL2CPP Player Build，确认 Editor-only HAPI/Cook/反射代码不会进入 Player。
11. 继续将最终 Terrain、Road、Shoulder、Collision 与 Metadata 转为可重现 Bake 资产；移动端 Runtime 禁止依赖 Houdini Cook。
