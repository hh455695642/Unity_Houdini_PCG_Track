# 最新修订：大块平面笔触（2026-09-22）

本节描述当前交付；下方保留上一版记录供审计。

- 用户反馈凹陷感后，目标材质 `_NormalMix` 改为 **0**，直接使用几何法线；不再用法线起伏表现笔触。
- 球体现场 `_ColorVoronoiScale=14.86` 导致细小斑点。本轮两个目标材质统一为 **1.8**，球体颜色笔触尺度扩大约 8.26 倍；`_ColorMix=0.32`。明暗围绕原几何光照做零中心偏移，不再把整片受光区域拉向随机灰值。
- 两份材质只写入上述三个参数；保留用户修改的曝光、LF 噪声、颜色、柔和度和轮廓参数。Shader 默认值同步更新；无新 keyword、Pass、RT 或 CPU 每帧工作。
- 默认法线分支跳过，Voronoi 搜索上限从上一版每像素 250 个候选降至 125。仍支持用户显式开启法线扰动，但当前预设关闭。
- 新 Capture 基线位于 `.agents/backups/PainterlyRoundness-20260922-155244/baseline`。原有 Temp 基线已随 Editor 重启消失，因此验证器改为使用 manifest 指定的持久目录，去噪合约使用固定高频上限，不依赖旧 Shader 源码。
- 新增几何法线一致性检查：完全不透明表面最大编码 RGB 误差约 **1.19e-7**；比较时排除轮廓裁切显露后方表面的像素。
- 球体高频 RMS **0.000199**（上限 0.003），硬边对照为 0.010953；原点不变性误差约 1.14e-7，单位缩放误差约 1.44e-8。
- Forward/Depth/DepthNormals：球体 3、鳄鱼 13 个边缘阈值像素差异，均不在完全不透明内部，仍满足 32 像素容差。
- VerifyFast、VerifyFull、保存后逐项参数核对与 48 项 GLES3/Vulkan/Metal 代表后端编译通过。当前组合计数仍为全部 50、使用集合 25。没有真机性能或完整 Player 构建结果；下方时间数据仅代表上一版。

复验仍使用下方相同的 manifest 命令。最新图片、preset 和机器报告位于 `.agents/backups/PainterlyRoundness-20260922-155244/`。当前 Scene 文件未修改，用户新增对象与既有工作区改动保留。

---

# 上一版实现与验证记录（非当前参数）

# Painterly 柔和笔触与表面去噪（2026-09-22）

## 已交付

当前 `Assets/Art/New Scene.unity` 的 Sphere 与 base (1) 使用原有两份 Shader、材质与 GUID。场景文件、FBX、原贴图未修改。两份 Shader 共用 `Assets/Art/PainterlyCommon.hlsl`，不增加 RendererFeature、运行时脚本、RT 或全屏 Pass。

根因：高频坐标畸变未经带宽过滤，把 Voronoi 单元打散成颗粒；把绝对特征位置混入法线使效果依赖模型原点与本地单位；鳄鱼本地最长边为 0.018994633，球体为 1，旧笔触参数相差约 53 倍。鳄鱼原贴图自带明暗，原材质调色板也是灰阶，不应靠强染色来补笔触。

已改为包围盒最长边归一化、相对单元偏移的切向法线扰动、低频变形，以及连续的 Voronoi 单元融合。高频畸变默认关闭，重新开启时也限制幅度与畸变，并按像素覆盖过滤噪声八度。轮廓始终使用几何法线，正视表面 coverage 精确为 1。

用户补充参考截图后，默认目标调整为柔和融合的大块笔触，不是硬切色块。未成功读取视频正文，不宣称与视频节点逐项一致。

## 参数与兼容性

| 参数 | 当前值/语义 |
|---|---|
| `_BrushSoftness` | 新增，0.6；控制单元交界融合宽度，不增加采样次数 |
| `_BrushContrast` | 新增，1；调节调色板输入明暗对比 |
| `_NormalMix` | 0.45；现在是相对于几何法线的笔触扰动强度 |
| `_CoordinateScale` | 2；归一化后的笔触密度，不再依赖 FBX 单位 |
| `_BoundsMin/Max` | 当前网格本地包围盒；替换不同网格时需编辑期更新 |
| `_PatternCenter` | 包围盒中心之外的额外本地偏移；现有目标材质保持零 |
| `_HFAmplitude / _HFDistortion` | 0；保留接口供受控调节 |
| `_ShadingSamples` | 1；保留 4 作为质量对照 |
| `_EdgeBandStart/Full` | 0.75 / 0.98 |
| `_EdgeStrength` | 0.3；轻微轮廓破碎 |
| `_EdgeBandEnabled` | 0 表示关闭轮廓破碎，不再回退到全表面裁切 |
| `_RampTintStrength` | 鳄鱼 0.08，保留原始绿色/紫色配色 |

`_DebugView` 使用 IntRange，无 keyword：0 最终、1 coverage、2 Fresnel、3 边缘噪声、4 shade、5 笔触法线、6 原色、7 几何法线。修复 Unity 的 Enum drawer 参数数量限制及换行格式警告。调试原色/遮罩时 Forward 与相机深度同步取消裁切。

保留 Forward / ShadowCaster / DepthOnly / DepthNormalsOnly 四个职责。DepthNormals 输出几何法线；阴影破碎按灯光方向计算，避免跟随相机运动。没有额外 RenderPassEvent。

所有 Pass 保留 `multi_compile_instancing`，不新增美术功能 keyword；去掉未使用的 `_CLUSTER_LIGHT_LOOP` 组合与目标材质上无意义的 Toggle keyword。Unity 查询每份 Shader 全部组合为 **50**、当前使用集合为 **25**。主灯阴影和软阴影仍使用必要的 URP multi_compile。Shader target 降至 3.5；坐标、hash 和导数使用 float，颜色及有界光照使用 half。

## 回归结果

- Capture 基线：`Temp/PainterlyRegression/baseline/`，包括本次任务前脏工作区哈希、目标文件备份、材质现场与历史 Console 精确签名。
- VerifyFast：白名单外无文件内容变化；未覆盖原有 URP、ProjectSettings、插件或 PCG 修改。
- VerifyFull：真实离屏渲染通过；材质 Shader / BaseMap 引用保持原值；保存后参数逐项核对并重新导入复验。
- 球体中心 128×128 区域高通 RMS：原版 0.056139 → 柔和版 0.001097，下降约 **98.0%**。这是固定视角下的高频指标，不代表全场景所有纹理都减少 98%。
- 同一效果关闭柔和融合时 RMS 为 0.034375；软边后的指标显著降低。
- 网格原点平移对比平均 RGB 误差约 2.95e-7；本地单位缩小 100 倍并补偿 Transform 后约 2.02e-8。
- Forward/Depth/DepthNormals coverage：球体 0 像素差异；鳄鱼 512² 图中 13 个 dither 阈值附近像素差异，全部位于非满 coverage 区域，完全不透明内部无差异。容差上限 32 像素（0.013%）。
- 近中远距离、非等比缩放及旋转生成检查图；有限值、内部 coverage、软边、引用等合约为自动检查。连续动画闪烁尚未真机验证。
- GLES3 / Vulkan / Metal：两份 Shader × 4 Pass × 顶点/片元，共 **48 项**实际后端源码编译成功，输出非空、无诊断；覆盖 Instancing、级联软阴影、点光阴影和法线编码代表变体。这不是完整 Player 构建或所有变体穷举。
- 最终验证阶段无新增 Console warning/error。开发过程中出现并已修复的 Enum/换行提示、同步命令超时保留在 Console 历史中，没有清空用户日志。

## 性能与限制

GPU 候选搜索上限从每像素 1000 次降到 250 次，软边融合在同一邻域循环内完成；零强度和不可解析的噪声跳过计算。CPU 不承担逐帧笔触计算。DrawCall 与 Pass 职责不增加；无新 RT 带宽开销，BaseColor 路径仍仅一次基础贴图采样（另有 URP 阴影采样）。轮廓 alpha clip 对 Tile GPU 的 Early-Z 仍有代价；需要完全不破碎时可以把 EdgeStrength 设为 0，但材质仍是 AlphaTest 队列。

RTX 3060 / D3D11、512² 球体、8 次暖机后样本中位数：CPU 命令提交约 0.045 → 0.053 ms；绘制加同步读回约 5.376 → 2.643 ms。后者包含驱动、GPU 等待和 ReadPixels，**不是独立 GPU timestamp，也不能外推移动端帧率**。没有 Mali、Adreno、Apple GPU 真机验收；iOS Player 构建也未执行。高分辨率大量覆盖时，125 邻域 × 两个场仍是 ALU 成本，应结合目标设备评估。

Unity MCP 本地端点拒绝连接，且日志显示其服务器完整性清单下载失败。未绕过其安全校验：主要操作使用健康的 Unity Pipeline 类型化命令，专用命令缺失的包围盒读取、离屏测试及后端编译使用 Pipeline C# 执行。没有修改该插件。

## 复验入口

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .agents/scripts/Ensure-UnityPipeline.ps1
powershell -NoProfile -ExecutionPolicy Bypass -File .agents/scripts/Invoke-PcgRegression.ps1 -Module Rendering -Stage VerifyFast -ChangeManifest .agents/scripts/painterly_rendering.manifest.json
powershell -NoProfile -ExecutionPolicy Bypass -File .agents/scripts/Invoke-PcgRegression.ps1 -Module Rendering -Stage VerifyFull -ChangeManifest .agents/scripts/painterly_rendering.manifest.json
```

`Apply` 内部阶段只允许写入已通过验证且源码哈希未变的 preset，写入后自动 VerifyFull；失败恢复 Capture 的任务资产，不恢复 Git HEAD。Capture 不覆盖已有基线；新任务应指定新的 baseline 目录。临时测试对象在 finally 中清理，原场景保持已保存状态。

图像与机器报告：`Temp/PainterlyRegression/` 下的 `sphere-before.png`、`sphere-after.png`、`crocodile-after.png`、`render-metrics.json`、`mobile-compile.json`、`benchmark.json`。所有截图均为 Unity 实际渲染。


## 2026-09-22 鳄鱼导入尺寸变更修复

本轮基线 `.agents/backups/PainterlyCrocodile-20260922-181930/baseline`。当前模型为 Crocodile_v2/base.fbx，Transform 为 1，网格最长边 1.8994634；材质旧 Bounds 最长边仅 0.0189946，造成约 100 倍坐标频率误差。保留用户当前 texture_diffuse.png、模型导入配置及其他材质颜色参数，仅修正鳄鱼材质 BoundsMin/Max，ColorVoronoiScale 从 0.6 校准为 1.8；NormalMix=0、ColorMix=0.32 保持。球体和 Shader 本轮未修改。

回归工具按 Capture 比较 Shader/贴图引用，替代旧 shaded.png 的硬编码 GUID；Apply 支持仅指定鳄鱼材质；保存后检查材质包围盒与实际导入网格一致，防止候选材质通过但 Live 仍使用旧 Bounds。网格再次重导入改变单位时须重新同步包围盒。

本轮不增加 CPU 每帧操作、GPU 采样、Pass 或 keyword；Instancing 与现有 50 个总组合 / 25 个当前使用组合保持。参数修正改变可见笔触频率，不声称 GPU 时间改善。移动端真机性能仍未验收。
