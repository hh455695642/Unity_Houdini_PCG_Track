# Assets/PCG/HDA 作用域规则

本目录的 `.hda` 是项目核心二进制事实源。除根规则外，以下规则强制执行。

## Definition 与现场保护

- 修改前确认当前 HIP、目标实例、节点类型、definition `libraryFilePath()`、锁定/可编辑状态和磁盘 HDA 完全对应。
- 当前 Live Scene 与磁盘内容必须作为 Capture 基线；不得从 Git HEAD、DevLog、备份或 patch 脚本恢复当前实现。
- 公共参数的 name、label、default、menu、range、folder、condition 和可见性默认不可修改；确需修改时必须列入 manifest 并取得用户明确同意。
- 保存前先以 `save=False` 在 Live Scene 完成完整验证；只有 VerifyFull 通过后才能 `definition.updateFromNode()`。
- 保存后必须在独立 hython 进程中创建全新锁定实例并重新执行累计合约。

## 备份与恢复

- Capture 必须将目标 HDA/HIP 备份到 `.codex_tmp/regression/<task>/backup/`，并记录 SHA-256。
- 验证失败时不得更新 definition；保存后复验失败时只允许从本次 Capture 备份精确恢复。
- `Assets/PCG/HDA/backup/Track_bak*.hda` 和 `Assets/PCG/HDA/City/backup/` 是历史备份，不得批量清理。
- 备份只用于失败恢复和审计，不得作为新任务的实现事实源。

## Unity 引用

- HDA 修改后必须确认 Unity AssetDatabase 已完成导入，Console 无新增错误。
- 涉及 Track 时确认 `Assets/PCG/Scenes/PCG.unity` 仍引用 `Assets/PCG/HDA/Track.hda`。
- 涉及 CityRoad 时确认目标 CityRoad 场景引用仍指向 `Assets/PCG/HDA/City/CityRoad.hda`。
- 禁止通过修改 Houdini Engine Unity 插件来适配项目 HDA 接口。
