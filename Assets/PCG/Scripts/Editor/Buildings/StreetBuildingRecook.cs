#if UNITY_EDITOR
using System;
using System.Collections.Generic;
using System.Globalization;
using System.Text.RegularExpressions;
using HoudiniEngineUnity;
using PCGBike.Buildings;
using UnityEditor;
using UnityEditor.SceneManagement;
using UnityEngine;

namespace PCGBike.Editor.Buildings
{
    // 编辑期桥：只同步素材与技术字段。数量、用途、排列只读取实例面板。
    [InitializeOnLoad]
    public static class StreetBuildingRecook
    {
        private sealed class Pending
        {
            public StreetBuildingStyleApplier.ParameterSnapshot Snapshot;
            public StreetBuildingCompiledStyle Compiled;
            public StreetBuildingAuthoring Authoring;
            public int Seed, SchemaBefore;
        }
        private static readonly Dictionary<HEU_HoudiniAsset, Pending> PendingCooks = new();
        private static readonly Dictionary<HEU_HoudiniAsset, (int Min, int Max)> ObservedDoors = new();
        private static readonly Dictionary<HEU_HoudiniAsset, Dictionary<string, int>> RebuildInts = new();
        private static int suppress;
        public static IDisposable Suppress() { suppress++; return new Scope(); }
        private sealed class Scope : IDisposable { public void Dispose() { suppress--; } }
        static StreetBuildingRecook()
        {
            EditorApplication.delayCall += Attach;
            EditorApplication.hierarchyChanged += Attach;
        }
        public static void Attach()
        {
            foreach (var author in Resources.FindObjectsOfTypeAll<StreetBuildingAuthoring>())
            {
                if (!author.gameObject.scene.IsValid()) continue;
                var asset = author.GetComponent<HEU_HoudiniAssetRoot>()?.HoudiniAsset;
                if (asset == null) continue;
                if (!ObservedDoors.ContainsKey(asset)) ObservedDoors[asset] = DoorValues(asset);
                asset.PreAssetEvent.RemoveListener(BeforeCook); asset.PreAssetEvent.AddListener(BeforeCook);
                asset.CookedDataEvent.RemoveListener(AfterCook); asset.CookedDataEvent.AddListener(AfterCook);
                asset.ReloadDataEvent.RemoveListener(AfterReload); asset.ReloadDataEvent.AddListener(AfterReload);
            }
        }
        // Rebuild replaces the HAPI node and event cache. Synchronize materials
        // after HEU finishes restoring its preset; never overwrite instance quotas.
        private static void AfterReload(HEU_ReloadEventData data)
        {
            if (suppress != 0 || !data.CookSuccess) return;
            var asset = data.Asset;
            if (RebuildInts.Remove(asset, out var values))
                foreach (var pair in values)
                    if (StreetBuildingInstanceParameters.Exists(asset, pair.Key))
                        StreetBuildingInstanceParameters.SetInt(asset, pair.Key, NormalizeLegacyPanelValue(pair.Key, pair.Value));
            ObservedDoors[asset] = DoorValues(asset);
            EditorApplication.delayCall += () =>
            {
                if (asset == null || asset.GetComponentInParent<StreetBuildingAuthoring>()?.ResolveStyle() == null) return;
                Attach();
                asset.RequestCook(true, false, true, true);
            };
        }

        private static (int Min, int Max) DoorValues(HEU_HoudiniAsset a) =>
            (StreetBuildingInstanceParameters.Int(a,"entrance_count_min",1),StreetBuildingInstanceParameters.Int(a,"entrance_count_max",1));

        private static void BeforeCook(HEU_PreAssetEventData data)
        {
            if (suppress != 0) return;
            if (data.AssetType == HEU_AssetEventType.RELOAD)
            {
                // HEU menu presets can fall back to index zero when old tokens retire.
                // Preserve numeric instance semantics independently of the menu index.
                if (!RebuildInts.ContainsKey(data.Asset))
                {
                    var values = new Dictionary<string, int>();
                    foreach (var p in data.Asset.Parameters.GetParameters())
                        if (p.IsInt() && p._intValues?.Length == 1) values[p._name] = p._intValues[0];
                    RebuildInts[data.Asset] = values;
                }
                return;
            }
            if (data.AssetType != HEU_AssetEventType.COOK) return;
            var asset=data.Asset;
            var author=asset.GetComponentInParent<StreetBuildingAuthoring>();
            if (author?.ResolveStyle() == null) return;
            // An old loaded definition must be rebuilt before the new bridge can migrate it.
            if (!StreetBuildingInstanceParameters.Exists(asset,"ground_quantity_mode")) return;
            if (PendingCooks.ContainsKey(asset)) throw new InvalidOperationException("StreetBuilding Cook already pending.");
            StreetBuildingPanelState.Begin(asset, author);
            StreetBuildingCompiledStyle compiled;
            try { compiled = StreetBuildingStyleCompiler.Compile(author.ResolveStyle()); }
            catch (Exception failure) { StreetBuildingPanelState.Fail(author, failure.Message); throw; }
            var current=DoorValues(asset);
            bool observed=ObservedDoors.TryGetValue(asset,out var previous);
            int seed=StreetBuildingInstanceParameters.Int(asset,"layout_seed",author.LayoutSeed);
            if (seed < 0 && author.InstanceRuleSchema == 0 && author.LayoutSeed >= 0) seed = author.LayoutSeed;
            if (ShouldRerollLayoutSeed(seed,author.RandomizeOnRecook,observed,previous.Min,previous.Max,current.Min,current.Max))
                seed=DrawDistinctLayoutSeed(seed);
            var pending=new Pending { Snapshot=StreetBuildingStyleApplier.ParameterSnapshot.Capture(asset),
                Compiled=compiled,Authoring=author,Seed=seed,SchemaBefore=author.InstanceRuleSchema };
            try
            {
                // One-time migration copies only the instance's previous public mode, never style rules.
                if (author.InstanceRuleSchema==0 && !string.IsNullOrEmpty(author.LastAppliedPayloadSha256))
                {
                    StreetBuildingInstanceParameters.SetInt(asset,"ground_quantity_mode",StreetBuildingInstanceParameters.Int(asset,"facade_layout_mode"));
                    StreetBuildingInstanceParameters.SetInt(asset,"ground_rhythm",StreetBuildingInstanceParameters.Int(asset,"facade_rhythm"));
                    StreetBuildingInstanceParameters.SetInt(asset,"shopfront_control",1);
                }
                StreetBuildingStyleApplier.Write(asset,author.ResolveStyle(),compiled.Payload);
                StreetBuildingInstanceParameters.SetInt(asset,"ground_rule_schema_version",2);
                StreetBuildingInstanceParameters.SetInt(asset,"unified_ground_walls",1);
                StreetBuildingInstanceParameters.SetInt(asset,"layout_seed",seed);
                PendingCooks.Add(asset,pending);
                // 提交版本包含本次已确定的布局种子和一次迁移；之后的编辑不归入此结果。
                StreetBuildingPanelState.Get(author).Submitted = StreetBuildingPanelState.CaptureInputs(asset, author);
            }
            catch (Exception failure) { RollbackFailure(asset, pending, failure.Message); throw; }
        }
        internal static int NormalizeLegacyPanelValue(string name, int value) =>
            name == "ground_floor_use" && value == 3 ? 2 :
            (name == "facade_rhythm" || name == "ground_rhythm") && value == 2 ? 1 :
            (name == "facade_layout_mode" || name == "ground_quantity_mode") && value == 2 ? 0 : value;

        internal static bool ShouldRerollLayoutSeed(int seed,bool enabled,bool observed,int oldMin,int oldMax,int newMin,int newMax)
            => seed<0 || enabled && observed && (oldMin!=newMin || oldMax!=newMax);
        private static int DrawDistinctLayoutSeed(int previous)
        {
            int seed; do { seed=BitConverter.ToUInt16(Guid.NewGuid().ToByteArray(),0); } while(seed==previous); return seed;
        }
        private static void AfterCook(HEU_CookedEventData data)
        {
            if (!PendingCooks.Remove(data.Asset,out var pending)) return;
            var author=pending.Authoring;
            if (!data.CookSuccess)
            {
                string reason = "Cook 失败";
                try { reason = data.Asset.GetAssetSession(false)?.ComposeNodeCookResult(data.Asset.AssetID, HAPI_StatusVerbosity.HAPI_STATUSVERBOSITY_ERRORS); }
                catch (Exception e) { reason += "；会话诊断不可读：" + e.Message; }
                RollbackFailure(data.Asset, pending, reason);
                return;
            }
            try { StreetBuildingPanelState.Commit(data.Asset, author); }
            catch (Exception failure)
            {
                RollbackFailure(data.Asset, pending, failure.Message);
                return;
            }
            ObservedDoors[data.Asset]=DoorValues(data.Asset);
            int cell=ReadEntranceCell(data.Asset);
            author.SetEditorLayout(pending.Seed,cell);
            author.SetEditorGroundDoorMigrationComplete(true);
            author.SetEditorInstanceRuleSchema(1);
            author.SetEditorAppliedPayloadSha256(pending.Compiled.Sha256);
            author.SetEditorMissingModuleSummary(StreetBuildingPartialBake.MissingSummary(data.Asset));
            author.SetEditorCookDiagnostic("Cook PASS：素材已同步；生成规则：实例面板／显式局部覆盖；"+ReadGroundSummary(data.Asset,cell,pending.Seed));
            EditorUtility.SetDirty(author);EditorSceneManager.MarkSceneDirty(author.gameObject.scene);
        }

        private static void RollbackFailure(HEU_HoudiniAsset asset, Pending pending, string reason)
        {
            var author = pending.Authoring;
            try { pending.Snapshot.Restore(asset); }
            catch (Exception e) { reason += "\n技术参数恢复失败：" + e.Message; }
            author.SetEditorInstanceRuleSchema(pending.SchemaBefore);
            author.SetEditorCookDiagnostic("Cook FAIL：本次生成失败，结果未更新。\n上次诊断：\n" + author.LastCookDiagnostic);
            // 无论技术参数能否恢复，都执行真实输出保全，不能由断线异常跳过。
            StreetBuildingPanelState.Fail(author, reason);
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
        internal static string ReadGroundSummary(HEU_HoudiniAsset asset, int entranceCell, int seed)
        {
            var core = asset.GetObjectNodeByName("StreetBuildingCore");
            var session = asset.GetAssetSession(false);
            if (core == null || session == null) return "输出元数据不可读；布局种子 " + seed;
            int use = 0, commercialDoors = 0, shops = 0, eligible = 0;
            float ratio = 0;
            string fallback = string.Empty, upperWindows = string.Empty, shopReport = string.Empty, attachments = string.Empty;
            bool hasUse = false, hasRatio = false;
            int? outputLayoutSeed = null;
            foreach (var geo in core.GeoNodes)
            foreach (var part in geo.GetParts())
            {
                if (ReadDetailString(session, geo.GeoID, part.PartID, "attachment_diagnostics", out string a) && !string.IsNullOrEmpty(a))
                    attachments = a;
                if (ReadDetailInt(session, geo.GeoID, part.PartID, "effective_ground_use", out int u))
                { use = u; hasUse = true; }
                if (ReadDetailInt(session, geo.GeoID, part.PartID, "commercial_door_count", out int d))
                    commercialDoors = d;
                if (ReadDetailInt(session, geo.GeoID, part.PartID, "shopfront_count", out int c))
                    shops = c;
                if (ReadDetailInt(session, geo.GeoID, part.PartID, "eligible_shopfront_count", out int e))
                    eligible = e;
                // BUILD_METADATA publishes the ground allocator's seed as
                // layout_seed. effective_seed is the independent variation seed.
                if (ReadDetailInt(session, geo.GeoID, part.PartID, "layout_seed", out int s))
                    outputLayoutSeed = s;
                if (ReadDetailFloat(session, geo.GeoID, part.PartID, "effective_shopfront_ratio", out float r))
                { ratio = r; hasRatio = true; }
                if (ReadDetailString(session, geo.GeoID, part.PartID, "ground_fallback_reason", out string f))
                    fallback = f;
                if (ReadDetailString(session, geo.GeoID, part.PartID, "ground_shopfront_report", out string shopsReport) && !string.IsNullOrEmpty(shopsReport)) shopReport = shopsReport;
                if (ReadDetailString(session, geo.GeoID, part.PartID, "upper_window_report", out string windows)
                    && !string.IsNullOrWhiteSpace(windows)) upperWindows = windows;
            }
            seed = ResolveReportedLayoutSeed(seed, outputLayoutSeed);
            if (!hasUse) return "输出元数据不可读；布局种子 " + seed;
            string summary = use == 2
                ? $"实际首层：商业；商业门 {commercialDoors} 个；橱窗 {shops} 个模块；可用格 {eligible}"
                    + (StreetBuildingInstanceParameters.Int(asset,"shopfront_control") == 1
                        ? "；面板比例 " + (hasRatio ? ratio.ToString("0.###", CultureInfo.InvariantCulture) : "未知") : "；按模块数量")
                : $"实际首层：住宅；入户门 {(entranceCell >= 0 ? 1 : 0)}";
            summary += "；布局种子 " + seed;
            if (!string.IsNullOrWhiteSpace(fallback) && fallback != "none")
                summary += "；回退原因 " + fallback;
            if (!string.IsNullOrWhiteSpace(shopReport)) summary += "\n首层橱窗：\n" + FormatQuantityReport(shopReport);
            if (!string.IsNullOrWhiteSpace(upperWindows))
                summary += "\n标准层窗模块：\n" + FormatQuantityReport(upperWindows);
            if (!string.IsNullOrWhiteSpace(attachments)) summary += "\n附件（实际生成过程）：\n" + FormatAttachments(attachments);
            return summary;
        }
        internal static string FormatQuantityReport(string report)
        {
            string result = Regex.Replace(report, @"source=instance_override:(\d+)", m => "来源=局部覆盖第" + m.Groups[1].Value + "条");
            result = Regex.Replace(result, @"source=parcel_override:(\d+)", m => "来源=地块覆盖第" + m.Groups[1].Value + "行");
            result = result.Replace("source=instance+parcel", "来源=基础参数及地块全局覆盖").Replace("source=instance", "来源=基础参数");
            result = Regex.Replace(result, @"\bF(\d+)\b", m => "第" + m.Groups[1].Value + "层");
            result = result.Replace("Face0", "正面").Replace("Face1", "左侧").Replace("Face2", "右侧").Replace("Face3", "背面")
                .Replace("mode=precise", "模式=固定数量").Replace("mode=random", "模式=随机范围").Replace("mode=ratio", "模式=占格比例")
                .Replace("requested=", "请求=").Replace("actual=", "实际模块=").Replace("occupied=", "占格=")
                .Replace("eligible=", "可用格=").Replace("resolved_metric=", "实际指标=").Replace("reason=", "原因=")
                .Replace("none", "无阻止原因").Replace("no_candidate", "无适用素材").Replace("span_infeasible", "连续空间不足");
            return result;
        }
        // Only format metadata from the completed Cook. Do not duplicate HDA
        // placement rules or read StyleConfig as a second generation authority.
        internal static string FormatAttachments(string report) => StreetBuildingAttachmentDiagnostics.Parse(report).Format();
        internal static string FormatCookState(string history, bool validSession, bool cooking, bool failed)
        {
            string state = !validSession ? "会话无效：结果未更新。" : cooking ? "正在生成：结果未更新。"
                : failed ? "本次 Cook 失败：结果未更新。" : "已完成的输出记录；修改参数后请 Cook。";
            return state + (string.IsNullOrEmpty(history) ? "\n尚无成功 Cook 记录。" : "\n上次成功 Cook／历史诊断：\n" + history);
        }
        internal static string CurrentCookDiagnostic(HEU_HoudiniAsset asset, string history)
        {
            // No session creation, no warning logging, and no HAPI geometry reads
            // in Inspector repaint. Native validity is supplied by the public API.
            var session = asset?.GetAssetSession(false);
            bool valid = session != null && session.IsSessionValid() && session.IsAssetRegistered(asset);
            bool cooking = asset != null && (asset.CookStatus.ToString() == "COOKING" || asset.CookStatus.ToString() == "LOADING" || PendingCooks.ContainsKey(asset));
            bool failed = asset != null && (asset.LastCookResult == HEU_AssetCookResultWrapper.ERRORED || history?.StartsWith("Cook FAIL") == true);
            return FormatCookState(history, valid, cooking, failed);
        }
        internal static int ResolveReportedLayoutSeed(int cookSeed, int? outputLayoutSeed)
            => outputLayoutSeed ?? cookSeed;
        private static bool ReadDetailInt(HEU_SessionBase session, int geo, int part, string name, out int value)
        {
            value = 0;
            var info = new HAPI_AttributeInfo { owner = HAPI_AttributeOwner.HAPI_ATTROWNER_DETAIL };
            if (!session.GetAttributeInfo(geo, part, name, HAPI_AttributeOwner.HAPI_ATTROWNER_DETAIL, ref info)
                || !info.exists || info.count < 1 || info.tupleSize < 1) return false;
            var values = new int[info.count * info.tupleSize];
            if (!session.GetAttributeIntData(geo, part, name, ref info, values, 0, info.count)) return false;
            value = values[0];
            return true;
        }
        private static bool ReadDetailFloat(HEU_SessionBase session, int geo, int part, string name, out float value)
        {
            value = 0;
            var info = new HAPI_AttributeInfo { owner = HAPI_AttributeOwner.HAPI_ATTROWNER_DETAIL };
            if (!session.GetAttributeInfo(geo, part, name, HAPI_AttributeOwner.HAPI_ATTROWNER_DETAIL, ref info)
                || !info.exists || info.count < 1 || info.tupleSize < 1) return false;
            var values = new float[info.count * info.tupleSize];
            if (!session.GetAttributeFloatData(geo, part, name, ref info, values, 0, info.count)) return false;
            value = values[0];
            return true;
        }
        private static bool ReadDetailString(HEU_SessionBase session, int geo, int part, string name, out string value)
        {
            value = string.Empty;
            var info = new HAPI_AttributeInfo { owner = HAPI_AttributeOwner.HAPI_ATTROWNER_DETAIL };
            if (!session.GetAttributeInfo(geo, part, name, HAPI_AttributeOwner.HAPI_ATTROWNER_DETAIL, ref info)
                || !info.exists || info.count < 1 || info.tupleSize < 1) return false;
            var values = new int[info.count * info.tupleSize];
            if (!session.GetAttributeStringData(geo, part, name, ref info, values, 0, info.count)) return false;
            value = HEU_SessionManager.GetString(values[0], session);
            return true;
        }
    }
}
#endif
