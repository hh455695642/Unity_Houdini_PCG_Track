#if UNITY_EDITOR
using System;
using System.Collections.Generic;
using HoudiniEngineUnity;
using PCGBike.Buildings;
using UnityEditor;
using UnityEditor.SceneManagement;
using UnityEngine;

namespace PCGBike.Editor.Buildings
{
    // 编辑期事件桥。无运行时 Update，不在 Cook 回调内再次请求 Cook。
    [InitializeOnLoad]
    public static class StreetBuildingRecook
    {
        private sealed class Pending
        {
            public StreetBuildingStyleApplier.ParameterSnapshot Snapshot;
            public StreetBuildingCompiledStyle Compiled;
            public StreetBuildingAuthoring Authoring;
            public int Seed;
        }
        private static readonly Dictionary<HEU_HoudiniAsset, Pending> PendingCooks = new();
        private static int suppress;
        public static IDisposable Suppress()
        { suppress++; return new Scope(); }
        private sealed class Scope : IDisposable { public void Dispose() { suppress--; } }
        static StreetBuildingRecook()
        {
            EditorApplication.delayCall += Attach;
            EditorApplication.hierarchyChanged += Attach;
        }
        public static void Attach()
        {
            foreach (var a in Resources.FindObjectsOfTypeAll<StreetBuildingAuthoring>())
            {
                if (!a.gameObject.scene.IsValid()) continue;
                var asset = a.GetComponent<HEU_HoudiniAssetRoot>()?.HoudiniAsset;
                if (asset == null) continue;
                asset.PreAssetEvent.RemoveListener(BeforeCook);
                asset.PreAssetEvent.AddListener(BeforeCook);
                asset.CookedDataEvent.RemoveListener(AfterCook);
                asset.CookedDataEvent.AddListener(AfterCook);
            }
        }
        private static void BeforeCook(HEU_PreAssetEventData data)
        {
            if (suppress != 0 || data.AssetType != HEU_AssetEventType.COOK) return;
            var asset = data.Asset;
            var a = asset.GetComponentInParent<StreetBuildingAuthoring>();
            if (a == null || a.ResolveStyle() == null) return;
            // 旧 HDA 保持原行为，正式导入新版接口后启用。禁止猜测 HAPI 参数索引。
            if (asset.Parameters.GetParameter("unified_ground_walls") == null) return;
            if (PendingCooks.ContainsKey(asset)) throw new InvalidOperationException("StreetBuilding Cook already pending.");
            var style = a.ResolveStyle();
            if (style.MigrateGroundWalls() | style.MigrateUpperWalls()) EditorUtility.SetDirty(style);
            var compiled = StreetBuildingStyleCompiler.Compile(style);
            int seed = a.LayoutSeed;
            if (a.RandomizeOnRecook || seed < 0)
            {
                do { seed = BitConverter.ToUInt16(Guid.NewGuid().ToByteArray(), 0); }
                while (seed == a.LayoutSeed);
            }
            var pending = new Pending { Authoring = a, Compiled = compiled, Seed = seed,
                Snapshot = StreetBuildingStyleApplier.ParameterSnapshot.Capture(asset.Parameters) };
            try
            {
                StreetBuildingStyleApplier.Write(asset.Parameters, style, compiled.Payload);
                StreetBuildingStyleApplier.SetString(asset.Parameters, "unity_style_rules", compiled.RulesPayload);
                if (!a.StyleRuleSourceInitialized && string.IsNullOrEmpty(a.LastAppliedPayloadSha256))
                    StreetBuildingStyleApplier.SetInt(asset.Parameters, "style_rule_source", 1);
                StreetBuildingStyleApplier.SetInt(asset.Parameters, "unified_ground_walls", 1);
                StreetBuildingStyleApplier.SetInt(asset.Parameters, "layout_seed", seed);
                // 锁定模式必须使用同一个排除条件，否则同种子也会改变结果。
                if (a.RandomizeOnRecook || a.LayoutSeed < 0)
                    StreetBuildingStyleApplier.SetInt(asset.Parameters, "previous_entrance_cell", a.EntranceCell);
                PendingCooks.Add(asset, pending);
            }
            catch { pending.Snapshot.Restore(asset.Parameters); throw; }
        }
        private static void AfterCook(HEU_CookedEventData data)
        {
            if (!PendingCooks.Remove(data.Asset, out var pending)) return;
            var a = pending.Authoring;
            if (!data.CookSuccess)
            {
                pending.Snapshot.Restore(data.Asset.Parameters);
                a.SetEditorCookDiagnostic("Cook FAIL：参数已恢复，保留上次有效输出；禁止 Bake。 ");
                EditorUtility.SetDirty(a);
                return;
            }
            int cell = ReadEntranceCell(data.Asset);
            a.SetEditorLayout(pending.Seed, cell);
            a.SetEditorAppliedPayloadSha256(pending.Compiled.Sha256);
            a.SetEditorRuleSourceInitialized(true);
            a.SetEditorMissingModuleSummary(StreetBuildingPartialBake.MissingSummary(data.Asset));
            a.SetEditorCookDiagnostic("Cook PASS：配置已同步；布局种子 " + pending.Seed);
            EditorUtility.SetDirty(a);
            EditorSceneManager.MarkSceneDirty(a.gameObject.scene);
        }
        internal static int ReadEntranceCell(HEU_HoudiniAsset asset)
        {
            var core = asset.GetObjectNodeByName("StreetBuildingCore");
            var session = asset.GetAssetSession(false);
            if (core == null || session == null) return -1;
            foreach (var geo in core.GeoNodes)
            foreach (var part in geo.GetParts())
            {
                var info = new HAPI_AttributeInfo { owner = HAPI_AttributeOwner.HAPI_ATTROWNER_POINT };
                if (!session.GetAttributeInfo(geo.GeoID, part.PartID, "is_building_entrance", HAPI_AttributeOwner.HAPI_ATTROWNER_POINT, ref info) || !info.exists) continue;
                var entries = new int[info.count * info.tupleSize];
                if (!session.GetAttributeIntData(geo.GeoID, part.PartID, "is_building_entrance", ref info, entries, 0, info.count)) continue;
                var cellsInfo = new HAPI_AttributeInfo { owner = HAPI_AttributeOwner.HAPI_ATTROWNER_POINT };
                if (!session.GetAttributeInfo(geo.GeoID, part.PartID, "cell_index", HAPI_AttributeOwner.HAPI_ATTROWNER_POINT, ref cellsInfo) || !cellsInfo.exists) continue;
                var cells = new int[cellsInfo.count * cellsInfo.tupleSize];
                if (!session.GetAttributeIntData(geo.GeoID, part.PartID, "cell_index", ref cellsInfo, cells, 0, cellsInfo.count)) continue;
                for (int i = 0; i < entries.Length && i < cells.Length; i++) if (entries[i] == 1) return cells[i];
            }
            return -1;
        }
    }
}
#endif
