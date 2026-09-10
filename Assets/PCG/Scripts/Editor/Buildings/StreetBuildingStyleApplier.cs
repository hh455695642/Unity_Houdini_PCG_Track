#if UNITY_EDITOR
using System;
using System.Collections.Generic;
using HoudiniEngineUnity;
using PCGBike.Buildings;
using UnityEditor;
using UnityEditor.SceneManagement;

namespace PCGBike.Editor.Buildings
{
    /// <summary>
    /// 编辑期事务桥：一次提交三层素材、默认规则和尺寸，然后请求一次 Cook。
    /// 实例已有的规则来源与覆盖保留；运行时只消费 Bake 结果。
    /// </summary>
    public static class StreetBuildingStyleApplier
    {
        internal static Func<HEU_HoudiniAsset, bool> RequestCook = DefaultRequestCook;
        internal static Func<UnityEngine.SceneManagement.Scene, bool> SaveScene = EditorSceneManager.SaveScene;

        private static readonly string[] IntParameters = { "module_source", "style_rule_source", "unified_ground_walls", "layout_seed", "previous_entrance_cell" };
        private static readonly string[] FloatParameters =
            { "floor_height_ground", "floor_height_typical" };
        private static readonly string[] StringParameters =
            { "unity_style_catalog", "unity_style_rules", "unity_bridge_end_marker" };

        public static string Validate(StreetBuildingStyleConfig style)
        {
            if (style == null) return "StyleConfig is missing.";
            StreetBuildingStyleValidationReport report = StreetBuildingStyleValidator.Validate(style);
            return report.IsValid ? string.Empty : report.ToString();
        }

        public static StreetBuildingCompiledStyle ApplyAndSave(
            HEU_HoudiniAssetRoot root, StreetBuildingAuthoring authoring, bool saveScene = true)
        {
            if (root == null || root.HoudiniAsset == null || authoring == null)
                throw new InvalidOperationException("StreetBuilding HDA root/Authoring is unavailable.");
            StreetBuildingStyleConfig style = authoring.ResolveStyle();
            string validation = Validate(style);
            if (!string.IsNullOrEmpty(validation)) throw new InvalidOperationException(validation);

            StreetBuildingCompiledStyle compiled = StreetBuildingStyleCompiler.Compile(style);
            HEU_HoudiniAsset asset = root.HoudiniAsset;
            HEU_Parameters parameters = asset.Parameters;
            ParameterSnapshot snapshot = ParameterSnapshot.Capture(parameters);
            string oldPayloadSha = authoring.LastAppliedPayloadSha256;
            string oldDiagnostic = authoring.LastCookDiagnostic;
            string oldMissingSummary = authoring.MissingModuleSummary;
            int oldLayoutSeed = authoring.LayoutSeed;
            int oldEntranceCell = authoring.EntranceCell;
            string oldTag = root.gameObject.tag;
            bool oldRuleSourceInitialized = authoring.StyleRuleSourceInitialized;
            try
            {
                Write(parameters, style, compiled.Payload);
                // The obsolete display parameter is hidden and omitted by HEU.
                // Generation diagnostics, rather than UI parameters, identify support.
                SetString(parameters, "unity_style_rules", compiled.RulesPayload);
                // Existing applied instances retain their HDA rules. A newly
                // bound instance starts from its style's layer defaults.
                if (!oldRuleSourceInitialized && string.IsNullOrEmpty(oldPayloadSha))
                    SetInt(parameters, "style_rule_source", 1);
                if (!RequestCook(asset))
                    throw new InvalidOperationException("StyleConfig cook failed: " + asset.LastCookResult);

                // Rebuild/domain reload can replace UnityEvent instances. Attach
                // synchronously before exposing freshly generated outputs to Bake.
                StreetBuildingPartialBake.Attach();

                authoring.SetEditorAppliedPayloadSha256(compiled.Sha256);
                authoring.SetEditorRuleSourceInitialized(true);
                int missing = StreetBuildingPartialBake.MissingSlotCount(asset, false);
                authoring.SetEditorMissingModuleSummary(StreetBuildingPartialBake.MissingSummary(asset));
                authoring.SetEditorCookDiagnostic("Cook PASS: " + asset.LastCookResult
                    + "；模块条目 " + compiled.ModuleCount
                    + (missing < 0 ? "；无可验证的真实模块输出，可继续预览；正式 Bake 需要有效输出。" : "；缺失位置 " + missing));
                root.gameObject.tag = "EditorOnly";
                EditorUtility.SetDirty(authoring);
                EditorSceneManager.MarkSceneDirty(root.gameObject.scene);
                if (saveScene && !SaveScene(root.gameObject.scene))
                    throw new InvalidOperationException("StyleConfig Scene save failed.");
                return compiled;
            }
            catch (Exception failure)
            {
                Exception rollbackFailure = null;
                try
                {
                    snapshot.Restore(parameters);
                    authoring.SetEditorAppliedPayloadSha256(oldPayloadSha);
                    authoring.SetEditorRuleSourceInitialized(oldRuleSourceInitialized);
                    authoring.SetEditorCookDiagnostic(oldDiagnostic);
                    authoring.SetEditorMissingModuleSummary(oldMissingSummary);
                    authoring.SetEditorLayout(oldLayoutSeed, oldEntranceCell);
                    root.gameObject.tag = oldTag;
                    EditorUtility.SetDirty(authoring);
                    using (StreetBuildingRecook.Suppress())
                        if (!RequestCook(asset))
                            throw new InvalidOperationException("rollback cook failed: " + asset.LastCookResult);
                }
                catch (Exception exception) { rollbackFailure = exception; }
                throw new InvalidOperationException(failure.Message + (rollbackFailure == null
                    ? " Style parameters were restored; Scene was not saved."
                    : " Rollback also failed: " + rollbackFailure.Message), failure);
            }
        }

        internal static void Write(
            HEU_Parameters parameters, StreetBuildingStyleConfig style, string stylePayload)
        {
            SetInt(parameters, "module_source", 1);
            SetString(parameters, "unity_style_catalog", stylePayload);
            SetString(parameters, "unity_bridge_end_marker", "END");
            SetFloat(parameters, "floor_height_ground", style.GroundFloorHeight);
            SetFloat(parameters, "floor_height_typical", style.TypicalFloorHeight);
        }

        internal static void SetInt(HEU_Parameters p, string name, int value)
        { if (!p.SetIntParameterValue(name, value)) throw new InvalidOperationException(name + " rejected."); }
        private static void SetFloat(HEU_Parameters p, string name, float value)
        { if (!p.SetFloatParameterValue(name, value)) throw new InvalidOperationException(name + " rejected."); }
        internal static void SetString(HEU_Parameters p, string name, string value)
        {
            HEU_ParameterData data = p.GetParameter(name);
            if (data == null || data._stringValues == null || data._stringValues.Length == 0)
                throw new InvalidOperationException(name + " is unavailable.");
            p.SetStringParameterValue(name, value ?? string.Empty);
            data._stringValues[0] = value ?? string.Empty;
        }

        internal static void ResetTestHooks()
        { RequestCook = DefaultRequestCook; SaveScene = EditorSceneManager.SaveScene; }
        private static bool DefaultRequestCook(HEU_HoudiniAsset asset) =>
            asset.RequestCook(true, false, true, true)
            && asset.LastCookResult == HEU_AssetCookResultWrapper.SUCCESS;

        internal sealed class ParameterSnapshot
        {
            private readonly Dictionary<string, int> _ints = new();
            private readonly Dictionary<string, float> _floats = new();
            private readonly Dictionary<string, string> _strings = new();

            public static ParameterSnapshot Capture(HEU_Parameters p)
            {
                var result = new ParameterSnapshot();
                foreach (string name in IntParameters)
                    if (p.GetParameter(name) != null && p.GetIntParameterValue(name, out int value)) result._ints[name] = value;
                foreach (string name in FloatParameters)
                    if (p.GetFloatParameterValue(name, out float value)) result._floats[name] = value;
                foreach (string name in StringParameters)
                    if (p.GetStringParameterValue(name, out string value)) result._strings[name] = value;
                return result;
            }

            public void Restore(HEU_Parameters p)
            {
                foreach (var pair in _ints) SetInt(p, pair.Key, pair.Value);
                foreach (var pair in _floats) SetFloat(p, pair.Key, pair.Value);
                foreach (var pair in _strings) SetString(p, pair.Key, pair.Value);
            }
        }
    }
}
#endif
