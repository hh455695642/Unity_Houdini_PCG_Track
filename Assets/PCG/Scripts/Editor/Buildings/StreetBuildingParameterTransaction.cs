#if UNITY_EDITOR
using System;
using System.Globalization;
using System.Linq;
using HoudiniEngineUnity;
using PCGBike.Buildings;
using UnityEditor;
using UnityEditor.SceneManagement;

namespace PCGBike.Editor.Buildings
{
    // 单一参数事务入口。只操作实例原生参数和插件已有缓存／preset，不维护第二份生成配置。
    [InitializeOnLoad]
    internal static class StreetBuildingParameterTransaction
    {
        static StreetBuildingParameterTransaction() => Undo.undoRedoPerformed += SyncUndo;
        internal static void Run(HEU_HoudiniAsset asset, string label, Action mutation, bool structural = false)
        {
            var owner = asset?.GetComponentInParent<StreetBuildingAuthoring>();
            var session = asset?.GetAssetSession(false);
            if (owner == null || asset.AssetID < 0 || session?.IsSessionValid() != true)
                throw new InvalidOperationException("实例未连接，参数尚未写入。");
            if (!session.GetPreset(asset.AssetID, out byte[] native)) throw new InvalidOperationException("无法保全原生参数。");
            string cacheJson = EditorJsonUtility.ToJson(asset.Parameters);
            var nodeInfo = asset.NodeInfo; bool auto = asset.AutoCookOnParameterChange, sync = asset.SessionSyncAutoCook;
            var cache = asset.Parameters;
            var cacheReferences = StreetBuildingInstanceParameters.CaptureReferences(cache);
            int group = -1;
            try
            {
                // 先上传原生 Inspector 尚未提交的缓存值，避免结构刷新吞掉用户输入。
                var pending = StreetBuildingPanelState.CaptureInputs(asset, owner);
                Apply(asset, pending, false);
                StreetBuildingInstanceParameters.SavePreset(asset);
                Undo.IncrementCurrentGroup(); group = Undo.GetCurrentGroup();
                Undo.RegisterCompleteObjectUndo(new UnityEngine.Object[] { asset, asset.Parameters }, label);
                asset.AutoCookOnParameterChange = false; asset.SessionSyncAutoCook = false;
                mutation();
                // 删除中间行之后以 HAPI 的移位结果为准，绝不回写旧索引的参数。
                if (structural) StreetBuildingInstanceParameters.RefreshCache(asset);
                StreetBuildingInstanceParameters.SavePreset(asset);
                Dirty(asset, owner); Undo.FlushUndoRecordObjects();
            }
            catch (Exception failure)
            {
                string rollback = null;
                if (group >= 0) Undo.RevertAllDownToGroup(group);
                // 只恢复本事务写入的技术字段；全量 JSON 回填会丢失 HEU 对象引用。
                asset.AutoCookOnParameterChange = auto; asset.SessionSyncAutoCook = sync;
                typeof(HEU_HoudiniAsset).GetField("_nodeInfo", System.Reflection.BindingFlags.Instance | System.Reflection.BindingFlags.NonPublic).SetValue(asset, nodeInfo);
                EditorJsonUtility.FromJsonOverwrite(cacheJson, cache);
                StreetBuildingInstanceParameters.RestoreReferences(cache, cacheReferences);
                try { if (!session.SetPreset(asset.AssetID, native)) rollback = "原生参数回滚失败"; }
                catch (Exception e) { rollback = e.Message; }
                StreetBuildingPanelState.Observe(owner);
                throw new InvalidOperationException(failure.Message + (rollback == null ? "；参数已回滚。" : "；" + rollback), failure);
            }
        }

        internal static void Apply(HEU_HoudiniAsset asset, System.Collections.Generic.IEnumerable<StreetBuildingPanelInput> input, bool refresh)
        {
            var rows = input.Where(r => !r.name.StartsWith("__", StringComparison.Ordinal)).ToArray();
            foreach (var row in rows.Where(r => IsStructure(r.name))) Write(asset, row);
            if (refresh) StreetBuildingInstanceParameters.RefreshCache(asset);
            foreach (var row in rows.Where(r => !IsStructure(r.name)))
                if (StreetBuildingInstanceParameters.Exists(asset, row.name)) Write(asset, row);
        }
        internal static bool IsStructure(string name) => name == "facade_overrides" || name == "attachment_overrides";
        private static void Write(HEU_HoudiniAsset asset, StreetBuildingPanelInput row)
        {
            if (row.textual) StreetBuildingInstanceParameters.SetString(asset, row.name, row.value);
            else if (row.floating) StreetBuildingInstanceParameters.SetFloat(asset, row.name, float.Parse(row.value, CultureInfo.InvariantCulture));
            else StreetBuildingInstanceParameters.SetInt(asset, row.name, int.Parse(row.value, CultureInfo.InvariantCulture));
        }
        private static void SyncUndo()
        {
            // Domain Reload 后不依赖旧静态 Edited 集合。仅处理已载入的项目实例，绝不创建会话。
            foreach (var owner in UnityEngine.Resources.FindObjectsOfTypeAll<StreetBuildingAuthoring>())
            {
                if (!owner.gameObject.scene.IsValid()) continue;
                var asset = owner.GetComponent<HEU_HoudiniAssetRoot>()?.HoudiniAsset;
                if (asset == null || asset.AssetID < 0 || asset.GetAssetSession(false)?.IsSessionValid() != true) continue;
                try
                {
                    StreetBuildingInstanceParameters.RestorePreset(asset);
                    var rows = StreetBuildingPanelState.CaptureInputs(asset, owner);
                    Apply(asset, rows, true);
                    StreetBuildingInstanceParameters.SavePreset(asset);
                    Dirty(asset, owner);
                }
                catch (Exception failure) { StreetBuildingPanelState.Get(owner).Error = "撤销同步失败：" + failure.Message; }
            }
        }
        internal static void Dirty(HEU_HoudiniAsset asset, StreetBuildingAuthoring owner)
        {
            EditorUtility.SetDirty(asset); EditorUtility.SetDirty(asset.Parameters);
            EditorSceneManager.MarkSceneDirty(owner.gameObject.scene); StreetBuildingPanelState.Observe(owner);
        }
    }
}
#endif
