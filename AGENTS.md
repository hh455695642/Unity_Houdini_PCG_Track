# PCG Bike Unity 项目协作规范

## 项目身份与优先级

本项目是面向移动端的 Unity 6000.3.22f1 + URP 17.3.0 自行车竞速程序化场景项目。

优先级固定为：

1. 移动端性能（Android / iOS / Mali / Adreno / Apple GPU）
2. 数据与已有修复不丢失
3. 模块化、可扩展、可维护
4. 美术和地编可继续编辑、替换和 Bake
5. 控制系统复杂度

默认使用中文回答，默认用户是高级 Unity 开发者；涉及 Houdini 节点网络时，按 Houdini 初学者可维护、可学习的粒度补充必要中文说明。

## 全局硬边界

- 禁止修改 `Assets/Plugins/HoudiniEngineUnity/` 下任何文件、程序集、序列化结构、Inspector 或 `.meta`。唯一已授权例外是 Unity 6.3 兼容补丁：`HEU_HoudiniAsset.cs` 中 `WarnedPrefabNotSupported` 使用 `[field: SerializeField]`，并移除 `InstanceInputUIState` 属性上重复且非法的 `[SerializeField]`；不得借此扩展插件修改范围。
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

工作区存在未提交改动时，直接以当前磁盘文件为开发基线；目标编辑器存在未保存改动时，先记录并保全磁盘与 Live 状态，再保存有效现场、Capture 和开发。不得要求先提交、stash、清理或回退 Git。保存已有现场不代表验收本次开发结果；本次修改仍须通过 VerifyFast、VerifyFull 后保存。遇到来源不一致时，先分别备份磁盘、definition 与 Live 内容，再依据实际差异、修改记录及验证结果自主选择最新且有效的一侧同步另一侧；不得仅凭文件时间判断，不因不一致本身暂停征询。若两侧各有独立有效改动，先合并保留有效内容；选择依据和同步结果必须记录；未命名或空场景的保存、切换遵从用户明确指示。任务前已有 HDA 编辑须先保全 Live 内容，再核对并同步 definition，禁止用旧 definition 覆盖现场。

所有会修改 HDA、HIP、Scene、Prefab、Material、Shader、Renderer 或生成数据的任务，必须执行：

```text
确认工作区与 Live Scene
  -> 保全并保存目标范围内已有未保存现场（差异已备份、判定并同步后）
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
  -Module CityRoad|Track|Terrain|StreetBuilding `
  -Stage Capture|VerifyFast|VerifyFull `
  -ChangeManifest <json>
```

规则：

- `Capture` 前必须核对目标 HIP、HDA definition 和 Live Scene；不一致时先备份双方，自主依据内容新旧、有效性和累计验证选择或合并更优基线，同步后继续 Capture，无需仅因来源差异再次确认。禁止丢失任一侧独立有效修改；无法确定有效性时保留双方并报告具体技术阻塞。
- manifest 必须声明允许修改的文件、节点、连接、参数、公共接口和必须满足的累计合约。
- 白名单外的节点类型、连接、非默认参数、VEX、公共参数接口或目标文件变化必须使验证失败。
- 每个已修复 bug 必须新增能复现它的累计合约；只验证本次功能不算完成。
- 目标输出不允许新增 warning。历史 warning 只能按精确签名登记，禁止宽泛忽略。
- 本次开发修改验证失败不得保存；保存后复验失败必须恢复本次 Capture 备份并报告，保留任务前已有用户改动。此规则不禁止开发前保全并保存已有现场。
- HDA/HIP 是实现事实源，累计验证器是行为事实源，DevLog 和历史 patch 只用于审计。

## 历史 patch 与 builder

- `patch_*_vN.py` 是一次性迁移记录，不是可组合、可依次重放的当前事实源。
- 禁止运行旧 patch 来“补齐环境”或为新任务重建旧状态。
- 新 patch 必须基于当前 Live Scene，具有明确前置 marker/哈希、`save=False`、幂等性和失败回滚。
- 禁止盲目替换 VEX 文本；前置内容不匹配必须失败退出。
- `build_curve_road_test.py` 只允许在用户明确要求整套重建时使用；其清空 HIP、删除 HDA 和备份的逻辑默认禁止执行。

## MCP 与验证

### Unity Pipeline CLI 强制前置门禁

每次在本项目开始任何任务时，无论任务是否预计修改 Unity 内容，都必须先执行：

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .agents\scripts\Ensure-UnityPipeline.ps1
```

该脚本必须验证 Unity CLI、项目对应的 Editor 主进程、`com.unity.pipeline` Server 和 `editor_status`。Editor 未运行时由脚本自动执行 `unity open <project>` 并等待正确 Unity 版本、首次导入、编译和 domain reload 完成，不要求用户手动启动。Editor 已运行但 Pipeline Server 不可达时，脚本允许用 Unity MCP 自动刷新 AssetDatabase，并在仍不可达时调用 `Window/Pipeline/Start Server` 完成自举；这些恢复动作只允许改变 Editor 会话状态，不得修改场景或资产。门禁未通过时禁止继续 Unity 修改，也禁止仅因 CLI/Server 未启动而直接回退 Unity MCP。不得把 AssetImportWorker 当成 Editor 主实例。

门禁通过后，`unity command` 已有类型化命令能够完成的操作必须优先使用 Unity Pipeline CLI；禁止用通用 `eval` 绕过已有命令。只有 Pipeline 已健康但确实缺少目标命令时才允许回退 Unity MCP，并记录缺失命令和回退原因。每次任务结束后必须再次运行 `Ensure-UnityPipeline.ps1`，确认本次修改没有破坏 CLI 链路。

首次修复导致 Pipeline Server 无法启动的编译错误属于引导例外：允许先应用已经明确授权的最小源码补丁，再立即恢复上述 CLI 门禁。脚本不得自动关闭、强制终止或重启已有 Editor，不得丢弃未保存 Scene，也不得删除 `Library/`。

Pipeline 健康且目标操作缺少 CLI 命令时，必须主动使用 Unity MCP 获取真实状态并验证；CLI 能完成的状态、Console、编译、测试与资产操作仍以 CLI 为准。

涉及 Houdini、HDA、HIP、SOP、Cook、Bake 或 Houdini 到 Unity 数据链路时，必须先运行：

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .agents\scripts\Ensure-HoudiniMcp.ps1
```

连接分为两层，端口不可互换：

- Houdini 内运行 `import hrpyc; hrpyc.start_server(port=18811)`，启动的是 Houdini RPC 服务，不是 HTTP/MCP 服务。
- 独立 Python 包 `houdini_mcp` 提供 MCP 转接服务；当前 HTTP 配置监听 3055，`/mcp` 接收 MCP 请求，`/health` 仅检查转接服务存活。转接服务再连接 Houdini 的 18811。
- 当前链路为 `Codex -> HTTP MCP :3055 -> hrpyc RPC :18811 -> Houdini Live Scene`。不要将 Codex MCP URL 改成 18811，也不要把 3055 当作 Houdini 内部服务。

Preflight 必须分别确认 18811 RPC 与当前 HIP、3055 health、转接服务协议工具发现和 Codex 配置解析。脚本的 `tools/list` 成功只证明服务端可发现工具，不证明当前 Codex 会话已加载工具；后者必须由当前会话工具列表及实际调用另行验证。连接层正常但当前会话工具未加载或握手失败时，明确报告该层故障并要求重启 Codex，不能把服务端预检成功报告成当前会话 MCP 操作成功。

Houdini 修改后必须验证目标节点 Cook、error/warning、输出统计与关键 metadata；Unity 修改后必须验证 Editor 状态、Console、场景对象和资产引用。涉及 HDA 时两侧验证都必须完成。

本次 StreetBuilding 三层配置任务已获用户明确授权：当前会话原生 Houdini 工具不可调用时，允许使用标准 MCP 客户端连接现有 `http://127.0.0.1:3055/mcp`，通过协议工具读取和修改现场后继续开发，无需等待会话工具重载。必须报告实际使用的客户端路径，不得声称原生工具已恢复；不得绕过服务端策略。Capture、白名单、累计回归、保存与失败恢复门禁全部保留。

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
