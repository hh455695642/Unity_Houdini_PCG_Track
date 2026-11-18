#if UNITY_EDITOR
using System;
using System.Collections.Generic;
using HoudiniEngineUnity;
using PCGBike.Buildings;
using UnityEditor;
using UnityEngine;

namespace PCGBike.Editor.Buildings
{
    /// <summary>项目自有 Bake 门禁；使用插件公开事件，不修改插件。仅编辑期注册。</summary>
    [InitializeOnLoad]
    public static class StreetBuildingPartialBake
    {
        static StreetBuildingPartialBake()
        {
            EditorApplication.delayCall += Attach;
            EditorApplication.hierarchyChanged += Attach;
        }

        public static void Attach()
        {
            foreach (var authoring in Resources.FindObjectsOfTypeAll<StreetBuildingAuthoring>())
            {
                if (!authoring.gameObject.scene.IsValid()) continue;
                var asset = authoring.GetComponent<HEU_HoudiniAssetRoot>()?.HoudiniAsset;
                if (asset == null) continue;
                asset.PreAssetEvent.RemoveListener(BeforeBake);
                asset.PreAssetEvent.AddListener(BeforeBake);
                StreetBuildingPipeBake.Attach(asset);
            }
        }

        private static void BeforeBake(HEU_PreAssetEventData data)
        {
            if (data.AssetType != HEU_AssetEventType.BAKE_NEW && data.AssetType != HEU_AssetEventType.BAKE_UPDATE) return;
            var authoring = data.Asset.GetComponentInParent<StreetBuildingAuthoring>();
            if (authoring != null) EnsureCanBake(authoring);
        }

        public static void EnsureCanBake(StreetBuildingAuthoring authoring)
        {
            var report = StreetBuildingStyleValidator.Validate(authoring.ResolveStyle(), true);
            if (!report.IsValid) throw new InvalidOperationException("正式 Bake 需要完整风格：\n" + report);
            var asset = authoring.GetComponent<HEU_HoudiniAssetRoot>()?.HoudiniAsset;
            // A synchronous Apply -> Bake may occur before hierarchyChanged/delayCall.
            // Register here as well so public native Bake always receives pipe consolidation.
            if (asset != null) StreetBuildingPipeBake.Attach(asset);
            if (asset == null || asset.LastCookResult != HEU_AssetCookResultWrapper.SUCCESS)
                throw new InvalidOperationException("请先成功应用风格并 Cook，再执行 Bake。");
            if (StreetBuildingRandom.Enabled(asset))
            {
                StreetBuildingPanelState.Observe(authoring);
                var state = StreetBuildingPanelState.Get(authoring);
                if (state.Cooking || state.Requested || state.NeedsResultValidation || state.Result == null || state.Result.inputHash != state.CurrentHash)
                    throw new InvalidOperationException("当前随机配置尚未成功生成验证，请更新结果后 Bake。");
            }
            var compiled = StreetBuildingStyleCompiler.Compile(authoring.ResolveStyle());
            if (compiled.Sha256 != authoring.LastAppliedPayloadSha256)
                throw new InvalidOperationException("风格已变化，请重新应用后 Bake。");
            int missing = MissingSlotCount(asset);
            if (missing < 0)
                throw new InvalidOperationException("没有可验证的真实模块输出，请补齐兼容模块并重新应用后 Bake。");
            if (missing > 0)
                throw new InvalidOperationException($"仍有 {missing} 个位置缺少兼容模块，请补齐后 Bake。");
            // A configured role can still lack a compatible candidate at a slot.
            // Never bake visible placeholder geometry through native HEU buttons.
            foreach (var filter in authoring.GetComponentsInChildren<MeshFilter>(true))
                if (filter.name.Contains("OUT_BUILDING_PREVIEW") && filter.sharedMesh != null
                    && filter.sharedMesh.vertexCount > 0)
                    throw new InvalidOperationException("仍有缺项占位，请补齐兼容模块并重新生成后 Bake。");
            EnsureStyle3CanBake(asset, authoring);
        }

        private static void EnsureStyle3CanBake(HEU_HoudiniAsset asset, StreetBuildingAuthoring authoring)
        {
            if (asset.CookStatus != HEU_AssetCookStatusWrapper.NONE)
                throw new InvalidOperationException("建筑仍在生成，不能验证正式 Bake 输出。");
            bool requested = StreetBuildingPanelState.HasStyle3Request(asset);
            string report = ReadStyle3BakeDetail(asset, "style3_attachment_diagnostics");
            string hosts = ReadStyle3BakeDetail(asset, "style3_balcony_host_diagnostics");
            // Default-off old styles produce no new metadata; keep their existing contract.
            if (!requested && string.IsNullOrEmpty(report) && string.IsNullOrEmpty(hosts)) return;
            StreetBuildingPanelState.Observe(authoring);
            var state = StreetBuildingPanelState.Get(authoring);
            // A stale successful native Cook is not proof that subsequently edited
            // Style3 requests were generated. Reuse the existing input/result hash.
            if (!state.Valid || state.Cooking || state.Requested || state.NeedsResultValidation
                || state.Result == null || state.Result.inputHash != state.CurrentHash)
                throw new InvalidOperationException("壁灯／阳台配置尚未成功生成验证，请更新结果后 Bake。");
            int expectedPairs = ValidateStyle3BakeReports(report, hosts, requested);
            VerifyBalconyPairOutputs(asset, expectedPairs);
        }

        private static string ReadStyle3BakeDetail(HEU_HoudiniAsset asset, string name)
        {
            var session = asset.GetAssetSession(false);
            if (session == null) throw new InvalidOperationException("Houdini session unavailable for Style3 Bake validation.");
            var core = asset.GetObjectNodeByName("StreetBuildingCore");
            if (core == null) throw new InvalidOperationException("建筑真实输出缺失，不能验证壁灯／阳台 Bake。");
            foreach (var geo in core.GeoNodes)
            {
                if (geo.GeoName != "OUT_BUILDING_METADATA") continue;
                foreach (var part in geo.GetParts())
                {
                    var info = new HAPI_AttributeInfo();
                    if (!session.GetAttributeInfo(geo.GeoID, part.PartID, name, HAPI_AttributeOwner.HAPI_ATTROWNER_DETAIL, ref info))
                        throw new InvalidOperationException("无法读取壁灯／阳台 Bake 诊断：" + name);
                    if (!info.exists) continue;
                    if (info.count != 1 || info.tupleSize != 1)
                        throw new InvalidOperationException("壁灯／阳台 Bake 诊断属性格式无效：" + name);
                    var handles = new int[1];
                    if (!session.GetAttributeStringData(geo.GeoID, part.PartID, name, ref info, handles, 0, 1))
                        throw new InvalidOperationException("无法读取壁灯／阳台 Bake 诊断内容：" + name);
                    return HEU_SessionManager.GetString(handles[0], session);
                }
            }
            return null;
        }

        // Pure report policy: material/anchor failures block Bake; valid placement
        // limits remain diagnostics, matching the existing optional attachment path.
        internal static int ValidateStyle3BakeReports(string report, string hosts, bool required)
        {
            if (!required && string.IsNullOrEmpty(report) && string.IsNullOrEmpty(hosts)) return 0;
            var parsed = StreetBuildingAttachmentDiagnostics.ParseStyle3(report);
            if (parsed.Error != null) throw new InvalidOperationException(parsed.Error);
            string hostError = StreetBuildingAttachmentDiagnostics.ValidateStyle3Hosts(hosts, parsed.Balcony);
            if (hostError != null) throw new InvalidOperationException(hostError);
            var placement = new HashSet<string>(StringComparer.Ordinal) {
                "none", "disabled", "no_eligible_host", "pair_capacity", "budget_truncated",
                "collision", "scope_restricted", "capacity", "no_blank_host"
            };
            foreach (var row in parsed.Rows)
            {
                if (row.Kind == "BalconyDoor") continue; // ParseStyle3 checks this component mirrors its whole pair.
                foreach (string reason in row.Reasons.Split(','))
                {
                    if (reason is "no_material" or "missing_anchor" or "no_compatible_host_material")
                        throw new InvalidOperationException("正式 Bake 仍缺少壁灯／阳台兼容素材或挂点：\n" + row.Text);
                    if (!placement.Contains(reason))
                        throw new InvalidOperationException("壁灯／阳台 Bake 诊断原因不可确认：" + reason);
                }
                if (row.Actual < row.Requested && row.Reasons == "none")
                    throw new InvalidOperationException("壁灯／阳台 Bake 短缺没有有效原因：\n" + row.Text);
            }
            return parsed.Balcony.Actual;
        }

        private static void VerifyBalconyPairOutputs(HEU_HoudiniAsset asset, int expected)
        {
            var session = asset.GetAssetSession(false);
            var core = asset.GetObjectNodeByName("StreetBuildingCore");
            var doors = new HashSet<string>(StringComparer.Ordinal);
            var platforms = new HashSet<string>(StringComparer.Ordinal);
            foreach (var geo in core.GeoNodes)
            {
                if (!(geo.GeoName is "OUT_BUILDING_LOD0" or "OUT_DETAIL_INSTANCES")) continue;
                foreach (var part in geo.GetParts())
                {
                    var roles = ReadPointStrings(session, geo.GeoID, part.PartID, "module_role");
                    if (Array.IndexOf(roles, "BalconyDoor") < 0 && Array.IndexOf(roles, "Balcony") < 0) continue;
                    var ids = ReadPointStrings(session, geo.GeoID, part.PartID, "style3_host_id");
                    if (ids.Length != roles.Length) throw new InvalidOperationException("阳台实际输出缺少配对标识。");
                    for (int i = 0; i < roles.Length; i++)
                    {
                        if (!(roles[i] is "BalconyDoor" or "Balcony")) continue;
                        bool door = roles[i] == "BalconyDoor";
                        if (door != (geo.GeoName == "OUT_BUILDING_LOD0")
                            || string.IsNullOrEmpty(ids[i]) || !(door ? doors : platforms).Add(ids[i]))
                            throw new InvalidOperationException("阳台实际输出含无效或重复的配对构件。");
                    }
                }
            }
            if (doors.Count != expected || !doors.SetEquals(platforms))
                throw new InvalidOperationException("阳台门与平台的实际配对数量与生成诊断不一致。");
        }

        private static string[] ReadPointStrings(HEU_SessionBase session, int geo, int part, string name)
        {
            var info = new HAPI_AttributeInfo();
            if (!session.GetAttributeInfo(geo, part, name, HAPI_AttributeOwner.HAPI_ATTROWNER_POINT, ref info))
                throw new InvalidOperationException("无法读取阳台实际输出属性：" + name);
            if (!info.exists || info.count == 0) return Array.Empty<string>();
            var handles = new int[info.count];
            if (info.tupleSize != 1 || !session.GetAttributeStringData(geo, part, name, ref info, handles, 0, info.count))
            {
                throw new InvalidOperationException("无法读取阳台实际输出内容：" + name);
            }
            return Array.ConvertAll(handles, handle => HEU_SessionManager.GetString(handle, session));
        }

        // Read the generated contract, not the preview renderer visibility.
        // Called only by explicit Apply/Bake, never in a runtime update loop.
        public static int MissingSlotCount(HEU_HoudiniAsset asset, bool requireSession = true)
        {
            var core = asset.GetObjectNodeByName("StreetBuildingCore");
            if (core == null) return -1;
            var session = asset.GetAssetSession(false);
            if (session == null)
            {
                if (requireSession) throw new InvalidOperationException("Houdini session unavailable for Bake validation.");
                return -1; // Diagnostics may run with a mocked Cook; Bake remains strict.
            }
            foreach (string output in new[] { "OUT_BUILDING_METADATA", "OUT_BUILDING_LOD0" })
            foreach (var geo in core.GeoNodes)
            {
                if (geo.GeoName != output) continue;
                foreach (var part in geo.GetParts())
                {
                    var info = new HAPI_AttributeInfo();
                    HEU_GeneralUtility.GetAttributeInfo(session, geo.GeoID, part.PartID, "preview_missing_count", ref info);
                    if (!info.exists) continue; // Legacy complete outputs have no preview branch.
                    var values = new int[info.count * info.tupleSize];
                    if (!session.GetAttributeIntData(geo.GeoID, part.PartID, "preview_missing_count", ref info, values, 0, info.count))
                        throw new InvalidOperationException("Unable to validate missing module count.");
                    return values.Length > 0 ? values[0] : 0;
                }
            }
            // HEU omits zero-point output parts. Unknown must fail closed for Bake.
            return -1;
        }
        public static string MissingSummary(HEU_HoudiniAsset asset)
        {
            var session = asset.GetAssetSession(false);
            var core = asset.GetObjectNodeByName("StreetBuildingCore");
            if (session == null || core == null) return "缺项统计不可用，请重新应用。";
            foreach (var geo in core.GeoNodes)
            {
                if (geo.GeoName != "OUT_BUILDING_METADATA") continue;
                foreach (var part in geo.GetParts())
                {
                    var info = new HAPI_AttributeInfo();
                    if (!session.GetAttributeInfo(geo.GeoID, part.PartID, "preview_missing_summary",
                        HAPI_AttributeOwner.HAPI_ATTROWNER_DETAIL, ref info) || !info.exists) continue;
                    var handles = new int[info.count * info.tupleSize];
                    if (!session.GetAttributeStringData(geo.GeoID, part.PartID, "preview_missing_summary",
                        ref info, handles, 0, info.count) || handles.Length == 0) continue;
                    string raw = HEU_SessionManager.GetString(handles[0], session);
                    string result = $"缺失位置：{MissingSlotCount(asset)}";
                    foreach (string line in raw.Split('\n'))
                    {
                        var fields = line.Split('|');
                        if (fields.Length == 3)
                            result += $"\n楼层索引 {fields[0]} · {fields[1]}：{fields[2]}";
                    }
                    var arrangement = new HAPI_AttributeInfo();
                    if (session.GetAttributeInfo(geo.GeoID, part.PartID, "arrangement_report",
                        HAPI_AttributeOwner.HAPI_ATTROWNER_DETAIL, ref arrangement) && arrangement.exists)
                    {
                        var reportHandles = new int[arrangement.count * arrangement.tupleSize];
                        if (reportHandles.Length > 0 && session.GetAttributeStringData(geo.GeoID, part.PartID,
                            "arrangement_report", ref arrangement, reportHandles, 0, arrangement.count))
                            result += "\n排列报告：\n" + HEU_SessionManager.GetString(reportHandles[0], session);
                    }
                    return result;
                }
            }
            return "此实例尚未加载自动占位诊断，请 Rebuild 后应用。";
        }
    }
}
#endif
