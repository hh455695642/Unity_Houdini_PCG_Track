#if UNITY_EDITOR
using System;
using System.Collections.Generic;
using System.Globalization;
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
            var compiled=StreetBuildingStyleCompiler.Compile(author.ResolveStyle());
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
            }
            catch { pending.Snapshot.Restore(asset); throw; }
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
                pending.Snapshot.Restore(data.Asset);
                author.SetEditorInstanceRuleSchema(pending.SchemaBefore);
                author.SetEditorCookDiagnostic("Cook FAIL：本次生成失败，结果未更新；保留实例参数。\n上次成功 Cook／历史诊断：\n" + author.LastCookDiagnostic);
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
            if (!string.IsNullOrWhiteSpace(shopReport)) summary += "\n首层橱窗：\n" + shopReport;
            if (!string.IsNullOrWhiteSpace(upperWindows))
                summary += "\n标准层窗模块（F 为从 1 开始的楼层；Face 0/1/2/3 为正/左/右/后）：\n" + upperWindows;
            if (!string.IsNullOrWhiteSpace(attachments)) summary += "\n附件（实际生成过程）：\n" + FormatAttachments(attachments);
            return summary;
        }
        // Only format metadata from the completed Cook. Do not duplicate HDA
        // placement rules or read StyleConfig as a second generation authority.
        internal static string FormatAttachments(string report)
        {
            string[] names = { "雨棚", "招牌", "消防梯", "墙面空调", "屋顶配件" };
            var text = new System.Text.StringBuilder();
            foreach (string row in report.Split('\n'))
            {
                var f = row.Split('|');
                if (f.Length == 6 && f[0] == "G")
                {
                    text.AppendLine($"全局附件密度：基础 {f[1]}，生效 {f[2]}；来源 {(f[3] == "instance" ? "基础面板" : "地块全局覆盖第 " + f[3].Substring("parcel_global:".Length) + " 行")}；附件开关：基础 {f[4]}，生效 {f[5]}");
                    continue;
                }
                if (f.Length != 16 || !int.TryParse(f[0], out int kind) || kind < 0 || kind >= names.Length) continue;
                int band = int.Parse(f[1], CultureInfo.InvariantCulture);
                int actual = int.Parse(f[14], CultureInfo.InvariantCulture);
                if (actual == 0 && band != (kind < 2 ? 0 : kind == 4 ? 2 : 1) && f[11] == "0") continue;
                string source = f[6] == "instance" ? "基础面板" : f[6].StartsWith("attachment_override:")
                    ? "附件覆盖第 " + f[6].Substring("attachment_override:".Length) + " 条"
                    : f[6].StartsWith("parcel:") ? "地块覆盖第 " + f[6].Substring(7) + " 条" : f[6];
                string reason = f[15].TrimEnd(',').Replace("attachments_disabled", "附件关闭")
                    .Replace("probability_zero", "概率为零").Replace("maximum_zero", "上限为零")
                    .Replace("no_material", "缺少素材").Replace("material_scope", "无适用素材（楼层／立面范围）")
                    .Replace("scope_restricted", "楼层／立面限制").Replace("rear_facade_condition", "后立面条件未满足（须为消防梯模式）")
                    .Replace("floor_condition", "至少需要三层").Replace("no_eligible_host", "无合格挂点")
                    .Replace("random_miss", "随机未命中").Replace("budget_truncated", "预算截断")
                    .Replace("maximum_truncated", "数量上限截断").Replace("none", "无阻止原因");
                text.AppendLine($"{names[kind]} [{(band == 0 ? "首层" : band == 1 ? "标准层" : "屋顶")}] 实际 {actual}；基础概率 {f[2]}／上限 {f[3]}；生效概率 {f[4]}／上限 {f[5]}；来源：{source}；楼层 {f[8]}～{f[9]}，立面掩码 {f[7]}；素材 {f[10]}／适用 {f[11]}；挂点 {f[12]}，命中 {f[13]}；{reason}");
            }
            return text.ToString().TrimEnd();
        }
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
