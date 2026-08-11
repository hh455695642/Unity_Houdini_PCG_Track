# PCG Bike Unity 项目协作规范

## 项目身份与优先级

本项目是面向移动端的 Unity 2022.3.62f2 + URP 14.0.12 自行车竞速程序化场景项目。

优先级固定为：

1. 移动端性能（Android / iOS / Mali / Adreno / Apple GPU）
2. 数据与已有修复不丢失
3. 模块化、可扩展、可维护
4. 美术和地编可继续编辑、替换和 Bake
5. 控制系统复杂度

默认使用中文回答，默认用户是高级 Unity 开发者；涉及 Houdini 节点网络时，按 Houdini 初学者可维护、可学习的粒度补充必要中文说明。

## 全局硬边界

- 禁止修改 `Assets/Plugins/HoudiniEngineUnity/` 下任何文件、程序集、序列化结构、Inspector 或 `.meta`。
- 项目专用兼容逻辑必须放在 `Assets/PCG/`、项目自有工具或 HDA 节点网络中。
- 禁止覆盖、回退、格式化或清理与当前任务无关的用户改动和未跟踪文件。
- 禁止把 Git HEAD、历史提交、备份 HDA、旧 patch 或 builder 当作当前现场的默认事实源。
- 禁止在移动端运行时依赖 Houdini Cook；运行时只消费 Bake 后的 Unity 原生或 GPU 可直接消费的数据。
- Unity 资产移动、删除、重命名必须保留 `.meta`，优先使用 Unity AssetDatabase / Unity MCP。

若功能只能通过侵入 Houdini Engine Unity 插件或破坏上述边界实现，必须停止并说明限制，等待用户重新明确授权。

## 当前事实源

- Unity 主验证场景：`Assets/PCG/Scenes/PCG.unity`
- Track HDA：`Assets/PCG/HDA/Track.hda`，类型 `pcgbike::Track::1.0`
- CityRoad HDA：`Assets/PCG/HDA/City/CityRoad.hda`，类型 `pcgbike::CityRoad::1.0`
- Houdini 主工程目录：`HoudiniProject/PCG_Track_21.0.440/`
- Houdini 版本：21.0.440
- PCG 资产根：`Assets/PCG/`
- Road Bake 根：`Assets/PCG/Generated/Road/`

旧路径 `Assets/Generated/Road` 不得继续使用；发现引用时应迁移并验证 Unity 场景引用。

## 跨任务防回归门禁（强制）

核心资产存在未提交修改时，当前磁盘文件与已确认的 Live Scene 是不可丢失基线。不得要求为了继续工作而先提交，也不得退回 Git HEAD。

所有会修改 HDA、HIP、Scene、Prefab、Material、Shader、Renderer 或生成数据的任务，必须执行：

```text
确认工作区与 Live Scene
  -> Capture 基线
  -> 声明本任务修改白名单与验收合约
  -> 仅做白名单内增量修改
  -> VerifyFast 范围检查
  -> VerifyFull 累计回归
  -> 保存 definition / HIP / Unity 资产
  -> 新实例、Unity 导入和 Console 复验
```

统一入口：

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .agents\scripts\Invoke-PcgRegression.ps1 `
  -Module CityRoad|Track|Terrain `
  -Stage Capture|VerifyFast|VerifyFull `
  -ChangeManifest <json>
```

规则：

- `Capture` 前必须确认目标 HIP、HDA definition 和 Live Scene 一致；不一致时停止，不能擅自选择一侧覆盖另一侧。
- manifest 必须声明允许修改的文件、节点、连接、参数、公共接口和必须满足的累计合约。
- 白名单外的节点类型、连接、非默认参数、VEX、公共参数接口或目标文件变化必须使验证失败。
- 每个已修复 bug 必须新增能复现它的累计合约；只验证本次功能不算完成。
- 目标输出不允许新增 warning。历史 warning 只能按精确签名登记，禁止宽泛忽略。
- 验证失败不得保存；保存后复验失败必须恢复 Capture 备份并报告。
- HDA/HIP 是实现事实源，累计验证器是行为事实源，DevLog 和历史 patch 只用于审计。

## 历史 patch 与 builder

- `patch_*_vN.py` 是一次性迁移记录，不是可组合、可依次重放的当前事实源。
- 禁止运行旧 patch 来“补齐环境”或为新任务重建旧状态。
- 新 patch 必须基于当前 Live Scene，具有明确前置 marker/哈希、`save=False`、幂等性和失败回滚。
- 禁止盲目替换 VEX 文本；前置内容不匹配必须失败退出。
- `build_curve_road_test.py` 只允许在用户明确要求整套重建时使用；其清空 HIP、删除 HDA 和备份的逻辑默认禁止执行。

## MCP 与验证

涉及 Unity Editor、Scene、GameObject、Component、Prefab、Material、URP、测试或 Console 时，必须主动使用 Unity MCP 获取真实状态并验证。

涉及 Houdini、HDA、HIP、SOP、Cook、Bake 或 Houdini 到 Unity 数据链路时，必须先运行：

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .agents\scripts\Ensure-HoudiniMcp.ps1
```

Preflight 必须确认 18811 RPC、3055 health、当前 HIP 和 Codex Houdini 工具发现。连接层正常但工具未热加载时，必须明确要求重启 Codex，不能假装已通过 MCP 操作。

Houdini 修改后必须验证目标节点 Cook、error/warning、输出统计与关键 metadata；Unity 修改后必须验证 Editor 状态、Console、场景对象和资产引用。涉及 HDA 时两侧验证都必须完成。

## 作用域规则

- 修改 `Assets/PCG/` 前，读取并遵守 `Assets/PCG/AGENTS.md`。
- 修改 `Assets/PCG/HDA/` 前，额外读取并遵守 `Assets/PCG/HDA/AGENTS.md`。
- 修改 `HoudiniProject/PCG_Track_21.0.440/` 前，读取并遵守该目录的 `AGENTS.md`。
- 目录规则只能收紧根规则，不能放宽全局硬边界或防回归门禁。

## 交付要求

- 默认提供可直接使用的实现和关键注释，不写基础教学废话。
- 报告实际改动、保存路径、验证命令和结果，以及仍未验证的风险。
- 不把“编译成功”或“Cook 成功”单独当作验收；必须同时满足累计行为合约。
- 若存在脏工作区，交付时区分本次改动与原有用户改动，不得把两者混为一谈。
