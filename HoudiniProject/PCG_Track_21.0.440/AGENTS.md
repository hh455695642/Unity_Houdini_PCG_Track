# HoudiniProject/PCG_Track_21.0.440 作用域规则

本目录以当前 Houdini/HDA 节点网络为事实源。核心生成逻辑优先使用可读的 SOP/HDA 节点，不得变成 Python 黑盒。

## Live Scene 工作流

- 开始前运行 `.agents/scripts/Ensure-HoudiniMcp.ps1`，确认 18811 RPC、3055 MCP health、当前 HIP 和工具发现。
- 默认操作当前 Houdini session；不得创建新 HIP、清空场景或整包重建 HDA。
- 默认使用当前选中 HDA；无选择时按类型查找目标实例。存在多个候选时必须列出路径并让用户确认。
- 修改前记录 HIP 路径、未保存状态、实例路径、类型、definition、节点树、关键连接、参数接口和 error/warning。
- 锁定实例需要编辑时可调用 `allowEditingOfContents()`，但仍必须先 Capture。

## 节点与 Python

- 赛道、地形、散布、桥梁和水体核心逻辑优先使用 SOP/HDA 节点、Network Box、Sticky Note 和清晰中文注释。
- Python 只用于增量 patch、自动化、迁移、导入导出、验证和测试胶水。
- 只允许修改 manifest 白名单内的节点、连接和参数；禁止顺手整理白名单外网络。
- 新 patch 必须验证前置 marker/哈希，支持 `save=False`，重复执行无变化，并在异常时恢复连接、参数和本次新增节点。
- 历史 `patch_*_vN.py` 只用于审计，不得按版本重放，不得成为累计验证器依赖。
- `build_curve_road_test.py` 含清空 HIP、删除 HDA 和清理备份风险，除用户明确要求整套重建外禁止运行。

## 累计验证与保存

- 快速验证必须比较 Capture 快照，白名单外节点类型、连接、关键参数、VEX 和公共接口不得变化。
- 完整验证必须运行当前模块全部历史合约，而不是只调用本次 patch 的 `_validate()`。
- 目标输出 force cook 后不得有 error 或新增 warning，并检查输出几何、边界、winding、关键 metadata 和退化数据。
- VerifyFull 通过后才可更新 HDA definition 和保存 HIP；随后在独立 hython 进程使用全新锁定实例复验。
- 每个 bug 修复必须先增加独立于 patch 脚本的回归合约。

## 输出与学习维护

涉及复杂节点链时，交付需说明节点职责、输入输出、关键参数、人工可调位置、Bake 结果和可覆盖内容。说明面向 Houdini 初学者，但不得牺牲节点可维护性、移动端 Bake 策略或运行时性能。

完成后报告：修改节点/参数、是否解锁、HDA 保存路径、HIP 是否保存、Cook error/warning、输出统计、累计合约和 Unity 复验结果。
