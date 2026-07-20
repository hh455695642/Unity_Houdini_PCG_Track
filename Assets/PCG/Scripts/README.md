# PCG Bike Scripts

本目录按业务模块组织。开发期 Houdini Cook 与移动端运行时数据必须保持分离。

## 目录职责

- `Track/Authoring`：赛道曲线输入标记，以及曲线变更后的 Houdini Cook 调度。
- `Terrain/Authoring`：Terrain HDA 与 Track Display SOP 的编辑器期绑定。
- `Editor/Houdini/TrackSplineInput`：Knot Contract V1 的 Unity → HAPI 输入适配；不会进入 Player。
- `Tests/Editor`：不依赖 Houdini Session 的快照、坐标转换与 payload 合约测试。

## 程序集边界

- `PCGBike.Authoring`：场景可序列化组件。Player 中无轮询、Cook 或每帧逻辑。
- `PCGBike.Editor`：仅 Editor，负责 HAPI 上传和自定义 Inspector。
- `PCGBike.Editor.Tests`：仅 EditMode 测试，通过 `InternalsVisibleTo` 检查内部数据合约。

## Track Spline 数据流

```text
SplineContainer + TrackSplineHoudiniInputAuthoring
  -> TrackSplineInputSnapshotBuilder（校验并快照 Knot）
  -> TrackSplineHapiPayloadBuilder（坐标、旋转、handle、索引数组）
  -> TrackSplineHapiUploader（HAPI curve、attribute、merge、CommitGeo）
  -> Track.hda / Knot Contract V1
```

Knot Contract V1 使用 linear carrier curve。闭环使用 `isClosed=true`、`isPeriodic=false`；
Houdini 通过 `P`、`rot`、`unity_tangent_in/out` 等 metadata 重建 cubic Bezier，再执行唯一的生产 Resample。

## 场景挂载

- `Spline`：`TrackSplineHoudiniInputAuthoring`
- `Track1`：`TrackSplineHoudiniCookSync`
- `Terrain1`：`TerrainTrackDisplaySopBinding`

扩展新的输入合约时应新增独立 Builder/Uploader，不把 Terrain、Bake 或运行时渲染逻辑并入当前输入接口。
