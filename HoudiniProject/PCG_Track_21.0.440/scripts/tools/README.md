# Houdini PCG 工具分类

## 当前事实源

- `.hda` / 当前 Live Scene：实现事实源。
- `scripts/contracts/` 与 `validate_*`：行为事实源。
- `patch_*_vN.py`：一次性迁移和审计记录。

历史 patch 不具备可组合性，不得为新任务按版本重放。新任务必须先创建 change manifest，再通过根目录统一入口执行 Capture、VerifyFast、VerifyFull。

## 统一入口

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .agents\scripts\Invoke-PcgRegression.ps1 `
  -Module CityRoad `
  -Stage Capture `
  -ChangeManifest HoudiniProject\PCG_Track_21.0.440\scripts\contracts\examples\cityroad_v10.example.json
```

Capture 输出的 snapshot 路径会按 manifest 自动登记；后续 VerifyFast / VerifyFull 使用同一个 manifest 即可。

`VerifyFull` 是明确的持久化阶段：它先执行范围检查和 Live 合约，再更新目标 HDA definition、保存目标 HIP、创建全新锁定实例并触发 Unity 导入。持久化后的任一步失败都会从本次 Capture 备份恢复 HDA/HIP。

累计合约 ID：

- CityRoad：见 `scripts/contracts/cityroad_contract.json` 的 `contract_ids`。
- Track：`Track.All`，执行现有 `verify_curve_road_test.py` 全套验证。
- Terrain：`Terrain.All`，执行现有 `validate_terrain_shape_params.py` 全套验证。

## 新 patch 最低要求

- 读取当前 Live Scene，不从旧 patch 重建。
- 对所有被替换内容检查 marker 或哈希。
- 提供 `save=False`。
- 重复执行无变化。
- 异常时恢复原连接、参数和本次新增节点。
- 把 bug 的复现条件加入独立累计 validator，禁止从 validator 导入 patch。
