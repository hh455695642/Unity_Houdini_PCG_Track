#if UNITY_EDITOR
using System;
using System.Collections.Generic;
using System.Globalization;
using System.Linq;
using System.Security.Cryptography;
using System.Text;
using HoudiniEngineUnity;
using PCGBike.Buildings;
using UnityEditor;
using UnityEngine;

namespace PCGBike.Editor.Buildings
{
    [Serializable] public sealed class StreetBuildingPanelInput
    {
        public string name, value;
        public bool floating;
        public bool textual;
    }

    [Serializable] public sealed class StreetBuildingPanelResult
    {
        public int version = 1, actualUse;
        public string inputHash, completedUtc, facades, attachments, summary, ruleRevision;
        public List<StreetBuildingPanelInput> inputs = new();
    }

    // 快照只用于比较和呈现；HDA 实例始终是生成参数事实源。
    // 性能关键点：仅选中实例节流检查；几何 metadata 仅在成功 Cook 后读取。
    [InitializeOnLoad]
    public static class StreetBuildingPanelState
    {
        internal const string RuleRevision = "active_fields_v2";
        internal sealed class State
        {
            public StreetBuildingPanelResult Result;
            public StreetBuildingAttachmentDiagnostics AttachmentDiagnostics;
            public List<StreetBuildingPanelInput> Current = new(), Submitted;
            public readonly Dictionary<string, string> DuringCook = new();
            public readonly HashSet<string> DuringCookFloats = new();
            public readonly HashSet<string> DuringCookStrings = new();
            public string CurrentHash, Error;
            public bool Cooking, Requested, Valid, Retained, ConnectionAvailable, NeedsResultValidation;
            public StreetBuildingOutputRetention Backup;
        }
        private static readonly Dictionary<StreetBuildingAuthoring, State> States = new();
        private static double nextPoll;
        static StreetBuildingPanelState()
        {
            EditorApplication.update += PollSelected;
            Undo.postprocessModifications += TrackNativeEdits;
        }

        private static UndoPropertyModification[] TrackNativeEdits(UndoPropertyModification[] modifications)
        {
            // Native HEU Inspector 通过 SerializedObject 编辑。事件发生时只读它的缓存，
            // 捕获小于轮询间隔的编辑；无需等待／查询正在 Cook 的 HAPI。
            foreach (var parameters in modifications.Select(m => m.currentValue.target).OfType<HEU_Parameters>().Distinct())
            {
                var owner = parameters.ParentAsset?.GetComponentInParent<StreetBuildingAuthoring>();
                if (owner == null || !States.TryGetValue(owner, out var state) || !state.Cooking || state.Submitted == null) continue;
                RecordDuringCook(state, CachedInputs(parameters));
            }
            return modifications;
        }

        internal static State Get(StreetBuildingAuthoring author)
        {
            if (States.TryGetValue(author, out var state)) return state;
            state = new State();
            if (!string.IsNullOrEmpty(author.PanelSuccessfulResultJson))
                try { state.Result = JsonUtility.FromJson<StreetBuildingPanelResult>(author.PanelSuccessfulResultJson); }
                catch { /* 旧／无效快照不可以冒充成功。 */ }
            if (author.LastCookDiagnostic?.StartsWith("Cook FAIL", StringComparison.Ordinal) == true)
                state.Error = "上次生成失败；结果保留状态需重新验证，上次成功记录见诊断。";
            state.NeedsResultValidation = state.Result != null && (author.PanelVerification != 3 || state.Result.ruleRevision != RuleRevision);
            if (state.Result != null) state.AttachmentDiagnostics = StreetBuildingAttachmentDiagnostics.Parse(state.Result.attachments);
            if (author.PanelVerification == 2) state.Error = "上次生成被会话或脚本重载中断；结果版本尚未验证，请重新生成。";
            States[author] = state;
            return state;
        }

        private static void PollSelected()
        {
            if (EditorApplication.timeSinceStartup < nextPoll || EditorApplication.isCompiling) return;
            nextPoll = EditorApplication.timeSinceStartup + .35;
            var author = Selection.activeGameObject?.GetComponent<StreetBuildingAuthoring>();
            if (author != null) Observe(author);
            foreach (var dead in States.Keys.Where(a => a == null).ToArray())
            {
                States[dead].Backup?.Dispose();
                States.Remove(dead);
            }
        }

        internal static void Observe(StreetBuildingAuthoring author)
        {
            var state = Get(author);
            var asset = author.GetComponent<HEU_HoudiniAssetRoot>()?.HoudiniAsset;
            var session = asset?.GetAssetSession(false);
            state.ConnectionAvailable = session?.IsSessionValid() == true || HEU_SessionManager.GetDefaultSession()?.IsSessionValid() == true;
            state.Valid = asset != null && asset.AssetID >= 0 && session != null && session.IsSessionValid();
            if (!state.Valid) return;
            try
            {
                if (state.Cooking)
                {
                    // Cook 期间只观察 HEU 缓存；不阻塞 HAPI、不读取几何。
                    RecordDuringCook(state, CachedInputs(asset.Parameters));
                    return;
                }
                if (author.PanelVerification == 3 && (author.PanelVerifiedSession != asset.SessionID
                    || author.PanelVerifiedNode != asset.NodeInfo.uniqueHoudiniNodeId)) MarkNeedsValidation(author);
                state.Current = CaptureInputs(asset, author); state.CurrentHash = Hash(state.Current);
            }
            catch { state.Valid = false; }
        }

        internal static List<StreetBuildingPanelInput> CachedInputs(HEU_Parameters parameters) => parameters.GetParameters()
            .Where(p => IsInput(p._name)).Select(p => new StreetBuildingPanelInput
            {
                name = p._name, floating = p._parmInfo.type == HAPI_ParmType.HAPI_PARMTYPE_FLOAT,
                textual = p._parmInfo.type == HAPI_ParmType.HAPI_PARMTYPE_STRING,
                value = p._parmInfo.type == HAPI_ParmType.HAPI_PARMTYPE_MULTIPARMLIST ? p._parmInfo.instanceCount.ToString(CultureInfo.InvariantCulture)
                    : p._parmInfo.type == HAPI_ParmType.HAPI_PARMTYPE_TOGGLE ? (p._toggle ? "1" : "0")
                    : p._parmInfo.type == HAPI_ParmType.HAPI_PARMTYPE_STRING ? p._stringValues?.FirstOrDefault()
                    : p._floatValues?.Length > 0 ? p._floatValues[0].ToString("R", CultureInfo.InvariantCulture)
                    : p._intValues?.Length > 0 ? p._intValues[0].ToString(CultureInfo.InvariantCulture) : null
            }).Where(r => r.value != null).ToList();

        private static void RecordDuringCook(State state, List<StreetBuildingPanelInput> rows)
        {
            var submitted = state.Submitted.ToDictionary(r => r.name, r => r.value);
            foreach (var row in rows)
            {
                if (submitted.TryGetValue(row.name, out string value) && value == row.value)
                { state.DuringCook.Remove(row.name); state.DuringCookFloats.Remove(row.name); state.DuringCookStrings.Remove(row.name); }
                else
                {
                    state.DuringCook[row.name] = row.value;
                    if (row.floating) state.DuringCookFloats.Add(row.name); else state.DuringCookFloats.Remove(row.name);
                    if (row.textual) state.DuringCookStrings.Add(row.name); else state.DuringCookStrings.Remove(row.name);
                }
            }
        }

        internal static void MarkNeedsValidation(StreetBuildingAuthoring author)
        {
            Get(author).NeedsResultValidation = true;
            SetAudit(author, 1);
        }
        private static void SetAudit(StreetBuildingAuthoring author, int value)
        {
            var asset = author.GetComponent<HEU_HoudiniAssetRoot>()?.HoudiniAsset;
            author.SetEditorPanelVerification(value, asset?.SessionID ?? 0, asset?.NodeInfo.uniqueHoudiniNodeId ?? -1);
            EditorUtility.SetDirty(author);
            if (author.gameObject.scene.IsValid()) UnityEditor.SceneManagement.EditorSceneManager.MarkSceneDirty(author.gameObject.scene);
        }

        internal static bool IsInput(string name) => name.StartsWith("facade_override", StringComparison.Ordinal)
            || name.StartsWith("attachment_override", StringComparison.Ordinal)
            || InputNames.Contains(name);
        private static readonly HashSet<string> InputNames = new(StringComparer.Ordinal)
        {
            "building_width", "building_depth", "massing_shape", "l_notch_width_cells", "l_notch_depth_cells",
            "l_notch_units", "l_notch_width", "l_notch_depth", "l_notch_side", "floor_count", "rear_facade_mode",
            "ground_floor_use", "residential_door_enabled", "ground_quantity_mode", "entrance_count_min", "entrance_count_max",
            "shopfront_control", "shopfront_quantity_mode", "shopfront_count", "shopfront_count_min", "shopfront_count_max",
            "shopfront_ratio", "shopfront_face_0", "shopfront_face_1", "shopfront_face_2", "shopfront_face_3", "ground_rhythm",
            "facade_layout_mode", "window_count_min", "window_count_max", "facade_rhythm", "roof_enabled", "parapet_enabled",
            "parapet_height", "architectural_trim_enabled", "corner_building", "corner_street_side", "attachments_enabled",
            "attachment_global_density", "ground_attachment_placement", "awning_density", "awning_max_count", "sign_density",
            "sign_max_count", "fire_escape_density", "fire_escape_max_count", "wall_ac_density", "wall_ac_max_count",
            "roof_props_density", "roof_props_max_count", "variation_seed", "layout_seed", "site_source_auto", "site_source"
            , StreetBuildingGenerationPolicy.Parameter, StreetBuildingGenerationPolicy.SequenceParameter
        };

        internal static List<StreetBuildingPanelInput> CaptureInputs(HEU_HoudiniAsset asset, StreetBuildingAuthoring author)
        {
            var session = asset.GetAssetSession(false);
            var node = new HAPI_NodeInfo();
            if (session == null || !session.GetNodeInfo(asset.AssetID, ref node, false))
                throw new InvalidOperationException("HAPI instance unavailable");
            var parms = new HAPI_ParmInfo[node.parmCount];
            var ints = new int[node.parmIntValueCount];
            var floats = new float[node.parmFloatValueCount];
            if (!session.GetParams(asset.AssetID, parms, 0, parms.Length)
                || !session.GetParamIntValues(asset.AssetID, ints, 0, ints.Length)
                || !session.GetParamFloatValues(asset.AssetID, floats, 0, floats.Length))
                throw new InvalidOperationException("HAPI parameters unreadable");
            var rows = new List<StreetBuildingPanelInput>();
            foreach (var p in parms)
            {
                string name = HEU_SessionManager.GetString(p.nameSH, session);
                if (!IsInput(name)) continue;
                var cached = asset.Parameters.GetParameter(name);
                string value;
                if (p.type == HAPI_ParmType.HAPI_PARMTYPE_FLOAT && p.floatValuesIndex >= 0 && p.floatValuesIndex < floats.Length && p.size > 0)
                    value = (cached?._floatValues?.Length > 0 ? cached._floatValues[0] : floats[p.floatValuesIndex]).ToString("R", CultureInfo.InvariantCulture);
                else if ((p.type == HAPI_ParmType.HAPI_PARMTYPE_INT || p.type == HAPI_ParmType.HAPI_PARMTYPE_TOGGLE || p.type == HAPI_ParmType.HAPI_PARMTYPE_MULTIPARMLIST)
                    && p.intValuesIndex >= 0 && p.intValuesIndex < ints.Length && p.size > 0)
                    value = (p.type == HAPI_ParmType.HAPI_PARMTYPE_MULTIPARMLIST && cached != null ? cached._parmInfo.instanceCount
                        : p.type == HAPI_ParmType.HAPI_PARMTYPE_TOGGLE && cached != null ? (cached._toggle ? 1 : 0)
                        : cached?._intValues?.Length > 0 ? cached._intValues[0] : ints[p.intValuesIndex]).ToString(CultureInfo.InvariantCulture);
                else if (p.type == HAPI_ParmType.HAPI_PARMTYPE_STRING && p.size > 0)
                    value = StreetBuildingInstanceParameters.String(asset, name);
                else continue;
                rows.Add(new StreetBuildingPanelInput { name = name, value = value, floating = p.type == HAPI_ParmType.HAPI_PARMTYPE_FLOAT,
                    textual = p.type == HAPI_ParmType.HAPI_PARMTYPE_STRING });
            }
            var style = author.ResolveStyle();
            rows.Add(new StreetBuildingPanelInput { name = "__material", value = style == null ? "missing" : MaterialFingerprint(style) });
            for (int i = 0; i < 2; i++)
            {
                var input = asset.GetInputNodeByIndex(i);
                var objects = input?.GetInputEntryGameObjects();
                string descriptor = objects == null ? "none" : string.Join(";", objects.Select(go => go == null ? "null" :
                    GlobalObjectId.GetGlobalObjectIdSlow(go) + "|" + go.transform.localToWorldMatrix.ToString("R") + "|"
                    + (go.GetComponent<MeshFilter>()?.sharedMesh == null ? "" : AssetDatabase.GetAssetDependencyHash(AssetDatabase.GetAssetPath(go.GetComponent<MeshFilter>().sharedMesh)).ToString())));
                rows.Add(new StreetBuildingPanelInput { name = "__input" + i, value = descriptor });
            }
            return rows.OrderBy(r => r.name, StringComparer.Ordinal).ToList();
        }

        private static string MaterialFingerprint(StreetBuildingStyleConfig style)
        {
            // 使用稳定资产标识，避免重开后 Unity instanceID 改变造成伪修改。
            var properties = new SerializedObject(style); var iterator = properties.GetIterator();
            var text = new StringBuilder();
            while (iterator.Next(true))
            {
                string value = iterator.propertyType switch
                {
                    SerializedPropertyType.ObjectReference => iterator.objectReferenceValue == null ? "null" : GlobalObjectId.GetGlobalObjectIdSlow(iterator.objectReferenceValue).ToString(),
                    SerializedPropertyType.Integer => iterator.longValue.ToString(CultureInfo.InvariantCulture),
                    SerializedPropertyType.Boolean => iterator.boolValue ? "1" : "0",
                    SerializedPropertyType.Float => iterator.doubleValue.ToString("R", CultureInfo.InvariantCulture),
                    SerializedPropertyType.Enum => iterator.enumValueIndex.ToString(CultureInfo.InvariantCulture),
                    SerializedPropertyType.String => iterator.stringValue,
                    _ => null
                };
                if (value != null) text.Append(iterator.propertyPath).Append('=').Append(value).Append('\n');
            }
            return text.ToString();
        }

        internal static string Hash(List<StreetBuildingPanelInput> rows)
        {
            using var hash = SHA256.Create();
            return BitConverter.ToString(hash.ComputeHash(Encoding.UTF8.GetBytes(string.Join("\n", rows.Select(r => r.name + "=" + r.value))))).Replace("-", "").ToLowerInvariant();
        }

        internal static void Begin(HEU_HoudiniAsset asset, StreetBuildingAuthoring author)
        {
            var state = Get(author);
            if (state.Cooking) throw new InvalidOperationException("生成中，请等待本次结果。");
            state.Submitted = CaptureInputs(asset, author);
            state.DuringCook.Clear();
            state.DuringCookFloats.Clear();
            state.DuringCookStrings.Clear();
            state.Requested = false;
            state.Backup?.Dispose();
            state.Backup = StreetBuildingOutputRetention.Capture(asset);
            state.Cooking = true; state.Error = null; state.Retained = false;
            SetAudit(author, 2);
        }

        internal static void Commit(HEU_HoudiniAsset asset, StreetBuildingAuthoring author)
        {
            var state = Get(author);
            var result = ReadResult(asset);
            var outputs = new List<GameObject>(); asset.GetOutputGameObjects(outputs);
            if (outputs.Count == 0 || outputs.Any(o => o == null)
                || outputs.SelectMany(o => o.GetComponentsInChildren<MeshFilter>(true)).Any(f => f.sharedMesh == null))
                throw new InvalidOperationException("生成输出或网格引用未通过校验。");
            result.inputs = state.Submitted ?? CaptureInputs(asset, author);
            result.inputHash = Hash(result.inputs);
            result.completedUtc = DateTime.UtcNow.ToString("o");
            // 先完成 metadata、后续输入和 preset 提交；任一步失败仍保有上次真实输出备份。
            RestoreDuringCookInputs(asset, state);
            author.SetEditorPanelSuccessfulResult(JsonUtility.ToJson(result));
            state.Result = result; state.AttachmentDiagnostics = StreetBuildingAttachmentDiagnostics.Parse(result.attachments);
            state.Cooking = false; state.Requested = false; state.Error = null;
            state.NeedsResultValidation = false; SetAudit(author, 3);
            state.Backup?.Dispose(); state.Backup = null;
            Observe(author);
        }

        private static void RestoreDuringCookInputs(HEU_HoudiniAsset asset, State state)
        {
            // HEU 下载完成时可能重建参数缓存；保留已经观察到的 Native 后续编辑。
            var rows = state.DuringCook.Select(p => new StreetBuildingPanelInput { name = p.Key, value = p.Value, floating = state.DuringCookFloats.Contains(p.Key), textual = state.DuringCookStrings.Contains(p.Key) }).ToArray();
            StreetBuildingParameterTransaction.Apply(asset, rows, rows.Any(r => StreetBuildingParameterTransaction.IsStructure(r.name)));
            StreetBuildingInstanceParameters.SavePreset(asset);
            state.DuringCook.Clear(); state.DuringCookFloats.Clear(); state.DuringCookStrings.Clear();
        }

        internal static void Fail(StreetBuildingAuthoring author, string error)
        {
            var state = Get(author);
            state.Cooking = false; state.Requested = false;
            state.Error = string.IsNullOrWhiteSpace(error) ? "生成失败；未能读取错误详情。" : error;
            MarkNeedsValidation(author);
            try { state.Retained = state.Backup != null && state.Backup.Restore(); }
            catch (Exception failure) { state.Error += "\n上次结果恢复失败：" + failure.Message; state.Retained = false; }
            finally { state.Backup?.Dispose(); state.Backup = null; }
            var asset = author.GetComponent<HEU_HoudiniAssetRoot>()?.HoudiniAsset;
            try
            {
                if (asset != null && asset.AssetID >= 0 && asset.GetAssetSession(false)?.IsSessionValid() == true) RestoreDuringCookInputs(asset, state);
                else if (asset != null)
                {
                    // 原生会话不可写时仍保全缓存中的最终用户请求，恢复连接时再上传。
                    foreach (var pair in state.DuringCook)
                    {
                        var p = asset.Parameters.GetParameter(pair.Key); if (p == null) continue;
                        if (state.DuringCookStrings.Contains(pair.Key) && p._stringValues?.Length > 0) p._stringValues[0] = pair.Value;
                        else if (state.DuringCookFloats.Contains(pair.Key) && p._floatValues?.Length > 0) p._floatValues[0] = float.Parse(pair.Value, CultureInfo.InvariantCulture);
                        else if (StreetBuildingParameterTransaction.IsStructure(pair.Key)) p._parmInfo.instanceCount = int.Parse(pair.Value, CultureInfo.InvariantCulture);
                        else { int value = int.Parse(pair.Value, CultureInfo.InvariantCulture); if (p._intValues?.Length > 0) p._intValues[0] = value; p._toggle = value != 0; }
                    }
                    EditorUtility.SetDirty(asset.Parameters);
                }
            }
            catch (Exception failure) { state.Error += "\n用户参数同步失败：" + failure.Message; }
            Observe(author);
        }

        internal static string Status(State state)
        {
            if (state.Cooking || state.Requested) return "生成中";
            if (!string.IsNullOrEmpty(state.Error)) return (state.Retained ? "失败，保留上次结果" : "失败；上次结果未能确认保留")
                + (state.Valid ? "" : "；会话不可用，请恢复实例连接");
            if (!state.Valid) return state.ConnectionAvailable ? "实例未载入；请恢复实例连接" : "Houdini Engine 会话不可用；请恢复实例连接";
            if (state.Result == null) return "结果版本无法确认；请生成一次";
            if (state.Result.ruleRevision != RuleRevision) return "规则版本待生成验证；请重建当前实例后生成";
            if (state.NeedsResultValidation) return "实例连接已恢复；上次结果待生成验证";
            return state.CurrentHash == state.Result.inputHash ? "结果已更新" : "参数已修改";
        }

        internal static StreetBuildingPanelResult ReadResult(HEU_HoudiniAsset asset)
        {
            var session = asset.GetAssetSession(false);
            var core = asset.GetObjectNodeByName("StreetBuildingCore");
            if (session == null || core == null) throw new InvalidOperationException("输出对象不可读");
            foreach (var geo in core.GeoNodes.Where(g => g.GeoName == "OUT_BUILDING_METADATA"))
            foreach (var part in geo.GetParts())
            {
                string revision = DetailString(session, geo.GeoID, part.PartID, "panel_rule_revision");
                if (revision != RuleRevision) throw new InvalidOperationException("当前实例定义未更新，请重建当前实例后生成。");
                string mapping = DetailString(session, geo.GeoID, part.PartID, "panel_facade_segments");
                // 旧 definition 可以呈现历史诊断，但不能伪装成已验证的新版本。
                if (!mapping.StartsWith("v1\n", StringComparison.Ordinal)) throw new InvalidOperationException("墙段 metadata 不可读；请 Rebuild 新 definition。");
                var segments = StreetBuildingFacadeDiagram.Parse(mapping);
                if (segments.Count == 0) throw new InvalidOperationException("墙段 metadata 为空");
                return new StreetBuildingPanelResult
                {
                    actualUse = DetailInt(session, geo.GeoID, part.PartID, "effective_ground_use"), facades = mapping, ruleRevision = revision,
                    attachments = DetailString(session, geo.GeoID, part.PartID, "attachment_diagnostics"),
                    summary = StreetBuildingRecook.ReadGroundSummary(asset, StreetBuildingRecook.ReadEntranceCell(asset), StreetBuildingInstanceParameters.Int(asset, "layout_seed"))
                };
            }
            throw new InvalidOperationException("缺少可验证的 metadata 输出");
        }

        internal static string DetailString(HEU_SessionBase session, int geo, int part, string name)
        {
            var info = new HAPI_AttributeInfo { owner = HAPI_AttributeOwner.HAPI_ATTROWNER_DETAIL };
            if (!session.GetAttributeInfo(geo, part, name, info.owner, ref info) || !info.exists || info.count < 1) return string.Empty;
            var handles = new int[info.count * info.tupleSize];
            return session.GetAttributeStringData(geo, part, name, ref info, handles, 0, info.count)
                ? HEU_SessionManager.GetString(handles[0], session) : string.Empty;
        }
        private static int DetailInt(HEU_SessionBase session, int geo, int part, string name)
        {
            var info = new HAPI_AttributeInfo { owner = HAPI_AttributeOwner.HAPI_ATTROWNER_DETAIL };
            if (!session.GetAttributeInfo(geo, part, name, info.owner, ref info) || !info.exists || info.count < 1) return 0;
            var values = new int[info.count * info.tupleSize];
            return session.GetAttributeIntData(geo, part, name, ref info, values, 0, info.count) ? values[0] : 0;
        }
    }
}
#endif
