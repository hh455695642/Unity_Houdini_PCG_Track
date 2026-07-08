# PCG Bike Unity 项目协作规范

## 项目身份

本项目是一个面向移动端的 Unity URP 自行车竞速程序化场景生成项目。

长期目标是在 Unity 中创建一条可编辑的闭环曲线作为赛道路径，并围绕该路径生成完整可玩的竞速场景，包括但不限于：

- 沥青公路、土路、碎石路等混合路面赛道
- 地形、山体、坡道、桥梁、湖泊、河流
- 植被、岩石、路边设施、装饰物和性能友好的远景元素
- 可被美术、地编同学在 Unity 中继续编辑、替换、调参和 Bake 的内容

核心优先级：

1. 移动端性能优先
2. Android / iOS / Mali / Adreno / Apple GPU 兼容
3. 生成系统模块化、可扩展、可维护
4. 可控复杂度，禁止堆叠失控的超级系统

## 当前项目状态

- 当前根目录已有 `PCG_Bike_Unity.hip`，作为 Houdini 侧程序化内容探索与 HDA 生成的起点。
- Unity 工程结构后续补齐。不要把尚未存在的 `Assets/`、`Packages/`、`ProjectSettings/` 写成既成事实。
- 后续当 Unity 工程创建后，需要根据实际目录继续补充更细的目录级规则。

## Houdini + Unity 开发期工作流

推荐主流程：

```text
Houdini / HDA
  -> 生成赛道、地形、道路边界、散布点、metadata

Unity Editor + Houdini Engine
  -> 调参、Cook、Bake Mesh / Prefab / Collider / Material / Metadata

Unity Runtime
  -> 只使用 Bake 后的数据
  -> 大规模对象使用 GPU Instancing / Indirect Draw / Chunk Culling
```

强制要求：

- Houdini Cook 只允许作为开发期、编辑器期流程，不允许成为移动端运行时依赖。
- 运行时场景数据必须转成 Unity 原生资源、序列化数据或 GPU 可直接消费的数据。
- HDA 输出必须尽量包含稳定 metadata，例如道路段类型、宽度、坡度、曲率、路肩区域、植被散布 mask、河流/桥梁控制点等。
- Bake 后内容必须可由美术和地编继续替换素材、调整参数和局部覆盖。

### Houdini 节点优先与学习友好原则

Houdini 侧功能开发必须优先考虑可视化节点网络，而不是把生成逻辑全部写成 Python 黑盒。

规则：

- 赛道、地形、散布、桥梁、水体等核心生成逻辑，默认优先使用 SOP / HDA 节点、参数、节点网络和可视化组织方式实现。
- Python 主要用于自动化、批处理、导入导出、参数同步、验证、测试辅助，以及少量节点难以清晰表达的胶水逻辑。
- 禁止把核心生成逻辑全部塞进 Python，除非节点方案明显不可维护、性能不可接受，或 Houdini 节点无法合理表达；这种情况必须先说明原因。
- 节点网络必须可读、可学习、可人工维护：节点命名清晰，必要时使用 Network Box 分组、Sticky Note 注释和关键参数中文说明。
- 复杂节点链输出时必须说明节点职责、输入数据、输出数据、关键参数、可手动调整的位置，以及 Bake 后哪些内容可被美术或地编覆盖。
- 面向用户解释 Houdini 节点方案时，默认按 Houdini 初学者可学习的粒度编写：提供必要中文注释、操作路径、维护提示和容易踩坑的位置，但不写低质量入门废话。
- 若使用 Python 创建或修改节点，也必须尽量生成清晰的节点结构、中文注释和可编辑参数，而不是只留下难以理解的脚本结果。

## MCP 主动调用规则

Agent 后续工作必须主动使用 MCP 获取真实状态和执行验证，不应把可自动确认的步骤交给用户手动完成。

### Unity MCP

当任务涉及以下内容时，Agent 必须主动调用 Unity MCP：

- Unity Editor 状态、编译状态、Console 错误
- Scene / GameObject / Component / Prefab / Material / Asset 状态
- URP Pipeline Asset、Renderer、RendererFeature、RenderPass 配置
- 摄像机截图、Scene View 检查、Frame Debugger 相关验证
- Unity Test Framework、PlayMode / EditMode 测试
- 包管理、Houdini Engine 插件状态、渲染统计或资源验证

建议流程：

```text
读取 editor state
  -> 检查 scene / project / pipeline 资源
  -> 执行必要操作
  -> 等待编译或导入完成
  -> 检查 Console
  -> 需要视觉确认时截图验证
```

### Houdini MCP

当任务涉及以下内容时，Agent 必须主动调用 Houdini MCP：

- `.hip` 文件、Houdini 节点、SOP 网络、HDA 参数
- 赛道曲线、地形生成、散布规则、桥梁/河流/湖泊生成逻辑
- HDA 导出、参数暴露、Cook 结果检查
- Houdini 到 Unity 的数据约定和 metadata 输出

若 MCP 当前不可用，Agent 必须明确说明：

- 哪个 MCP 不可用
- 当前无法验证的具体状态
- 可采用的临时降级方案
- 后续恢复 MCP 后需要补做的验证

#### Houdini MCP 开发前 Preflight

当任务涉及 Houdini、HDA、`.hip`、SOP 网络、Cook、Bake 或 Houdini 到 Unity 数据链路时，Agent 在开始实质性开发前必须先运行：

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .agents\scripts\Ensure-HoudiniMcp.ps1
```

该 preflight 必须确认：

- Houdini GUI 已启动，且 `18811` RPC 可通过 `hrpyc` 连接。
- `http://127.0.0.1:3055/health` 返回 healthy。
- Codex 用户配置包含 `[mcp_servers.houdini]`，URL 为 `http://127.0.0.1:3055`。
- 当前会话能发现 Houdini MCP 工具；若 Codex 未热加载新 MCP，说明需要重启 Codex 后复验。

若 preflight 失败，Agent 不得假设 Houdini 状态正确；必须说明失败点、当前不可验证范围，以及恢复后需要补做的检查。

## Unity / URP 架构约束

- 使用 Unity URP，不使用 Built-in Render Pipeline。
- 熟悉并遵循 SRP 架构：`ScriptableRenderer`、`ScriptableRendererFeature`、`ScriptableRenderPass`。
- 所有新渲染功能默认基于 `ScriptableRendererFeature + ScriptableRenderPass` 实现。
- 禁止直接侵入 RenderPipeline 主流程，除非有明确必要且先说明原因。
- 每个功能必须拆成独立 RenderPass，不允许写“全能型超级 Feature”。
- 配置优先使用 `ScriptableObject` 管理。
- 所有功能必须有 Feature Toggle。
- 必须标注扩展点，方便后续叠加功能。

涉及 Render Feature 的输出必须包含：

- Feature 职责
- RenderPass 职责
- `RenderPassEvent`
- 输入 / 输出资源
- 是否创建 RenderTexture
- 带宽风险
- 移动端兼容性说明
- 后续扩展点

## RenderPass 顺序与移动端带宽控制

移动端 Tile-Based GPU 以带宽控制优先，ALU 通常不是第一瓶颈。

默认顺序原则：

```text
Depth Prepass（仅必要时）
Opaque（利用 Early-Z）
Alpha Test / Cutout（控制 overdraw）
Transparent（最后）
PostProcess（尽量少）
Debug Overlay（仅 Debug 开关启用）
```

规则：

- 控制 RenderPass 数量，能合并就合并。
- 减少 RenderTexture 使用，禁止滥用高分辨率中间 RT。
- 避免频繁切换 RT，避免中途 flush tile。
- 避免多次全屏 Blit。
- 避免 MRT，除非收益明确且移动端目标机验证通过。
- Debug Pass 必须可关闭，默认不进入发布构建。

## Shader 编写规范

Shader 使用 HLSL，并兼容 URP。

强制要求：

- 必须支持 GPU Instancing：`#pragma multi_compile_instancing`。
- 默认优先使用 `half` 精度，只有必要时使用 `float`。
- 明确 Pass 职责：Forward、Depth、Shadow。
- 控制分支、纹理采样和 overdraw。
- 不使用 Geometry Shader。
- 不使用移动端兼容性差的特性。
- 植被、角色、特效等高差异对象必须拆分 Shader，不共用超级 Shader。

每次输出 Shader 必须标注：

- Instancing 支持方式
- 使用的 keyword
- Variant 数量风险
- 移动端精度风险
- 纹理采样数量
- overdraw 风险
- 可替代优化方案

## Shader Variant 控制

目标是严格控制 variant 数量，避免编译爆炸和包体膨胀。移动端单个 Shader 的 variant 建议控制在 200 内。

规则：

- 默认使用 `#pragma shader_feature_local`。
- 禁止滥用 `multi_compile`。
- 能 runtime uniform 控制的功能，不使用 keyword。
- 强度、阈值、颜色、距离、开关等优先使用 uniform。
- 避免 A x B x C 式 keyword 组合爆炸。
- 高成本功能应拆成独立 Shader。
- 必须考虑 URP 自带 keyword 已经很多，禁止继续无控制叠加。

功能分层：

- 基础功能：常驻，无 keyword 或少量 uniform 控制。
- 可选功能：少量、可预测的 local keyword。
- 高成本功能：独立 Shader 或独立渲染路径。

## 大规模实例渲染规范

植被、石头、路边小物件等大规模对象默认使用 GPU 驱动方案。

默认方案：

- `DrawMeshInstancedIndirect`
- Compute Shader GPU Culling
- Chunk / Cluster 分组
- GPU 或低频 CPU LOD
- 每 Chunk 独立 bounds
- 低成本风动画
- 可选 Debug 输出 Instance Count / DrawCall

禁止：

- CPU 每帧 for-loop 驱动大量实例
- 每实例 GameObject 方案用于大规模植被
- 为方便编辑牺牲运行时批处理结构

编辑器期可以保留可视化代理对象，但 Bake / Runtime 数据必须转换为批量渲染友好的结构。

## 程序化场景生成模块边界

后续系统必须按模块拆分，不允许把所有逻辑堆到一个生成器里。

建议模块：

- Track Path：闭环曲线、宽度、坡度、曲率、采样点、赛道方向
- Road Surface：路面类型、材质段、路肩、边界、UV 和碰撞
- Terrain：高度场、切坡、填方、山体、远景地形
- Water：湖泊、河流、岸线和桥梁约束
- Bridge：桥段识别、桥体生成、护栏和碰撞
- Vegetation：mask、密度、Cluster、LOD、GPU Instance 数据
- Decoration：路牌、护栏、广告牌、岩石和地编替换点
- Bake Pipeline：HDA Cook 结果到 Unity 原生资源
- Runtime Rendering：移动端批处理、剔除、LOD 和 Debug

每个模块必须说明：

- 输入数据
- 输出数据
- 可编辑参数
- Bake 结果
- Runtime 成本
- 扩展点

## 美术与地编可编辑性

生成结果必须服务团队协作，不只是一次性生成。

要求：

- 关键参数暴露给 Unity Editor。
- 生成内容可局部锁定、覆盖、替换。
- 素材引用必须可替换，不把具体美术资源硬编码进生成逻辑。
- Bake 输出应结构清晰，便于 Prefab 化和版本管理。
- 生成 metadata 必须稳定，方便后续工具、Debug 和二次处理。
- 地编修改后的内容不能被下一次生成无提示覆盖。

## 移动端性能红线

优先降低：

- DrawCall
- SetPass
- Overdraw
- 带宽读写
- 高分辨率中间 RT
- 运行时 CPU 生成和 GC

移动端默认策略：

- 静态内容优先 Bake。
- 大规模重复内容 GPU Instancing / Indirect。
- 远景用低成本 Mesh / Billboard / Impostor。
- 透明物体数量严格控制。
- 后处理尽量少，避免多次全屏 Pass。
- Shader 优先 half 精度和少采样。
- 运行时只做必要的局部变化，不做完整场景重生成。

涉及渲染优化时必须提供 CPU vs GPU 对比，指出瓶颈在 CPU、GPU、带宽、overdraw 还是内存。

## Debug 与验证

必须兼容：

- Unity Profiler
- Frame Debugger
- RenderDoc
- Unity Console
- 移动端真机 Profiling

Debug 系统必须轻量：

- 所有 Debug 开关默认关闭。
- 可选显示 DrawCall、Instance Count、Chunk Count、LOD、Culling 结果。
- 不允许引入复杂常驻 Debug 框架。
- Debug Overlay 不得影响发布性能。

每次完成 Unity 相关实现后，Agent 应主动检查：

- 编译状态
- Console error / warning
- 相关场景或资源状态
- 必要时截图或运行测试

## Agent 输出要求

默认使用中文回答。

除非用户明确要求基础教学，否则不要写入门解释。默认用户是高级开发者。

例外：涉及 Houdini 节点、HDA、SOP 网络或 Houdini 生成逻辑时，默认用户为 Houdini 初学者。输出必须增加必要中文注释、节点学习说明、操作路径和维护提示，同时保持方案可维护、可扩展，不牺牲移动端性能目标。

输出代码时：

- 优先提供可直接使用的代码。
- 必须包含关键注释。
- 标注性能关键点。
- 标注扩展点。
- 涉及 Shader 时标注 Instancing + Variant 风险。
- 涉及 Render Feature 时标注 `RenderPassEvent`。
- 涉及大规模渲染时默认 GPU 驱动方案。

规划或架构输出时：

- 简要说明设计思路。
- 主动指出性能、兼容性、扩展性问题。
- 不推荐低性能方案作为主方案。
- 不生成超级 Shader、超级 Feature 或不可拆分系统。

## 禁止行为

- 不忽略移动端限制。
- 不使用 Built-in Render Pipeline。
- 不使用 Geometry Shader。
- 不写不可扩展的一次性代码。
- 不生成“全能型超级 Feature”。
- 不生成“全能型超级 Shader”。
- 不堆叠无控制 Shader Variant。
- 不用 CPU 重度参与大规模渲染逻辑。
- 不把 Houdini Cook 放入移动端运行时链路。
- 不要求用户手动检查 MCP 可自动确认的状态。
