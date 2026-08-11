# Assets/PCG 作用域规则

本目录存放项目自有 Unity、URP、PCG、材质、Shader、HDA 和生成资产。根目录 `AGENTS.md` 的防回归门禁始终有效。

## Unity 与资产

- 使用 Unity URP，不使用 Built-in Render Pipeline。
- Shader 放在 `Assets/PCG/Shaders/`，Material 放在 `Assets/PCG/Materials/`，Texture 放在 `Assets/PCG/Texture/`。
- 生成 Road Bake 资产放在 `Assets/PCG/Generated/Road/`。
- 移动、删除、重命名必须通过 AssetDatabase / Unity MCP 并保留 GUID 与 `.meta`。
- Bake 输出结构必须允许美术和地编局部锁定、替换、覆盖；重新生成不得无提示覆盖人工修改。
- 资产引用不得硬编码具体美术资源，配置优先使用 ScriptableObject。

## URP 扩展

- 新渲染功能默认使用独立 `ScriptableRendererFeature + ScriptableRenderPass`。
- 禁止侵入 RenderPipeline 主流程，禁止全能型 Feature；所有功能必须有 Feature Toggle。
- 每个 Render Feature 必须说明职责、RenderPassEvent、输入/输出、是否创建 RT、带宽风险、移动端兼容性和扩展点。
- 默认顺序：必要的 Depth Prepass、Opaque、Alpha Test、Transparent、少量 PostProcess、仅 Debug 启用的 Overlay。
- 避免多次全屏 Blit、高分辨率中间 RT、频繁 RT 切换和 MRT，防止 Tile GPU 中途 flush。

## Shader 与 Variant

- HLSL 必须兼容 URP，并支持 `#pragma multi_compile_instancing`。
- 优先 `half`，只在世界坐标、深度或确有精度需求时使用 `float`。
- 明确 Forward、Depth、Shadow 职责；控制分支、纹理采样、overdraw 和透明物体数量。
- 禁止 Geometry Shader 和移动端兼容性差的特性。
- 可选功能默认使用 `#pragma shader_feature_local`；能用 uniform 控制的强度、阈值和开关不得增加 keyword。
- 植被、角色、特效使用独立 Shader，单 Shader variant 建议少于 200。
- Shader 交付必须标注 Instancing、keyword、variant 风险、精度、采样数、overdraw 和替代优化。

## 大规模实例与运行时

- 植被、岩石和路边小物件默认使用 DrawMeshInstancedIndirect、Compute GPU Culling、Chunk/Cluster、每 Chunk bounds 和 GPU/低频 CPU LOD。
- 禁止 CPU 每帧 for-loop 驱动大量实例，禁止用大量 GameObject 作为最终运行时表示。
- 编辑期可以保留代理对象，Bake 后必须转换为批量渲染结构。
- 带宽优先于 ALU；优先降低 DrawCall、SetPass、overdraw、RT 读写、运行时生成和 GC。
- Debug 默认关闭，只允许轻量显示 DrawCall、Instance/Chunk/LOD/Culling 统计，不得影响发布构建。

## 模块与数据合约

Track Path、Road Surface、Terrain、Water、Bridge、Vegetation、Decoration、Bake Pipeline、Runtime Rendering 必须保持模块边界。

每个模块应明确输入、输出、可编辑参数、Bake 结果、Runtime 成本和扩展点。HDA 输出应提供稳定 metadata，例如段类型、宽度、坡度、曲率、路肩、散布 mask 和桥梁/水体控制信息。

## Unity 验证

完成修改后必须通过 Unity MCP：

1. 检查 Editor 是否编译或 domain reload。
2. 检查相关场景、资产、Renderer 和引用。
3. 检查 Console error/warning。
4. 运行相关 EditMode / PlayMode 测试。
5. 涉及视觉或渲染时使用 Scene/Game View 截图、Frame Debugger 或 RenderDoc 复核。

渲染优化报告必须区分 CPU、GPU、带宽、overdraw 和内存瓶颈，并给出 CPU 与 GPU 方案对比。
