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
using UnityEditor.SceneManagement;
using UnityEngine;

namespace PCGBike.Editor.Buildings
{
    /// <summary>StyleConfig + GenerationPreset 到 HDA 的事务桥；失败时恢复全部参数且不保存场景。</summary>
    public static class StreetBuildingDesignPresetApplier
    {
        internal static Func<HEU_HoudiniAsset, bool> RequestCook = DefaultRequestCook;
        internal static Func<UnityEngine.SceneManagement.Scene, bool> SaveScene = EditorSceneManager.SaveScene;

        private static readonly string[] IntParameters =
        {
            "module_source", "floor_count", "ground_use", "facade_rhythm", "facade_control_mode",
            "rear_mode", "side_mode", "seed", "massing_shape", "notch_side"
        };
        private static readonly string[] FloatParameters =
        {
            "internal_width", "internal_depth", "ground_floor_height", "typical_floor_height",
            "shopfront_ratio", "parapet_height", "detail_density", "notch_width", "notch_depth"
        };
        private static readonly string[] BoolParameters =
        {
            "corner_building", "generate_roof", "generate_architectural_trim",
            "generate_attachments", "generate_lods"
        };
        private static readonly string[] StringParameters =
        {
            "unity_instance_catalog", "unity_generation_rules"
        };

        public static string Validate(
            StreetBuildingGenerationPreset preset, StreetBuildingStyleConfig style)
        {
            if (style == null) return "StyleConfig is missing.";
            StreetBuildingStyleValidationReport styleReport = StreetBuildingStyleValidator.Validate(style);
            if (!styleReport.IsValid) return styleReport.ToString();
            string generation = StreetBuildingGenerationCompiler.Validate(preset, style);
            if (!string.IsNullOrEmpty(generation)) return generation;
            if (preset != null && preset.ParapetHeight > .001f)
            {
                StreetBuildingModuleDefinition straight = style.EnumerateModules().Select(item => item.Module)
                    .FirstOrDefault(item => item != null && item.Enabled
                                            && item.ModuleRole == StreetBuildingModuleRole.Parapet);
                StreetBuildingModuleDefinition corner = style.EnumerateModules().Select(item => item.Module)
                    .FirstOrDefault(item => item != null && item.Enabled
                                            && item.ModuleRole == StreetBuildingModuleRole.ParapetCorner);
                if (straight == null || corner == null
                    || Mathf.Abs(straight.ResolveHeight(style) - preset.ParapetHeight) > .001f
                    || Mathf.Abs(corner.ResolveHeight(style) - preset.ParapetHeight) > .001f)
                    return "Enabled parapet requires matching Parapet and ParapetCorner heights.";
                if (preset.MassingShape == StreetBuildingMassingShape.LShape
                    && !style.EnumerateModules().Any(item => item.Module != null && item.Module.Enabled
                        && item.Module.ModuleRole == StreetBuildingModuleRole.ParapetConcaveCorner))
                    return "L massing requires a ParapetConcaveCorner module.";
            }
            return string.Empty;
        }

        public static StreetBuildingCompiledStyle ApplyAndSave(
            HEU_HoudiniAssetRoot root, StreetBuildingAuthoring authoring)
        {
            if (root == null || root.HoudiniAsset == null || authoring == null)
                throw new InvalidOperationException("StreetBuilding HDA root/Authoring is unavailable.");
            StreetBuildingStyleConfig style = authoring.ResolveStyle();
            StreetBuildingGenerationPreset preset = authoring.GenerationPreset;
            string validation = Validate(preset, style);
            if (!string.IsNullOrEmpty(validation)) throw new InvalidOperationException(validation);

            StreetBuildingCompiledStyle compiledStyle = StreetBuildingStyleCompiler.Compile(style);
            StreetBuildingCompiledGeneration compiledGeneration =
                StreetBuildingGenerationCompiler.Compile(preset, style, authoring.VariationSeed);
            HEU_HoudiniAsset asset = root.HoudiniAsset;
            HEU_Parameters parameters = asset.Parameters;
            ParameterSnapshot snapshot = ParameterSnapshot.Capture(parameters);
            StreetBuildingStyleConfig oldStyle = authoring.FixedStyleConfig;
            string oldPayloadSha = authoring.LastAppliedPayloadSha256;
            string oldDesignSha = authoring.LastAppliedDesignSha256;
            string oldDiagnostic = authoring.LastCookDiagnostic;
            string oldTag = root.gameObject.tag;
            try
            {
                Write(parameters, preset, style, authoring.VariationSeed,
                    compiledStyle.Payload, compiledGeneration.Payload);
                if (!RequestCook(asset))
                    throw new InvalidOperationException("GenerationPreset cook failed: " + asset.LastCookResult);

                string designSha = ComputeDesignSha(compiledStyle.Sha256, compiledGeneration.Sha256);
                authoring.SetEditorFixedStyle(style);
                authoring.SetEditorAppliedPayloadSha256(compiledStyle.Sha256);
                authoring.SetEditorAppliedDesignSha256(designSha);
                authoring.SetEditorCookDiagnostic("Cook PASS: " + asset.LastCookResult);
                root.gameObject.tag = "EditorOnly";
                EditorUtility.SetDirty(authoring);
                EditorSceneManager.MarkSceneDirty(root.gameObject.scene);
                if (!SaveScene(root.gameObject.scene))
                    throw new InvalidOperationException("GenerationPreset Scene save failed.");
                return compiledStyle;
            }
            catch (Exception failure)
            {
                Exception rollbackFailure = null;
                try
                {
                    snapshot.Restore(parameters);
                    authoring.SetEditorFixedStyle(oldStyle);
                    authoring.SetEditorAppliedPayloadSha256(oldPayloadSha);
                    authoring.SetEditorAppliedDesignSha256(oldDesignSha);
                    authoring.SetEditorCookDiagnostic(oldDiagnostic);
                    root.gameObject.tag = oldTag;
                    EditorUtility.SetDirty(authoring);
                    if (!RequestCook(asset))
                        throw new InvalidOperationException("rollback cook failed: " + asset.LastCookResult);
                }
                catch (Exception exception) { rollbackFailure = exception; }
                throw new InvalidOperationException(failure.Message + (rollbackFailure == null
                    ? " Parameters were restored; Scene was not saved."
                    : " Rollback also failed: " + rollbackFailure.Message), failure);
            }
        }

        public static string ComputeDesignSha(string styleSha, string generationSha)
        {
            using SHA256 sha = SHA256.Create();
            return string.Concat(sha.ComputeHash(Encoding.UTF8.GetBytes(
                    (styleSha ?? string.Empty) + "|" + (generationSha ?? string.Empty)))
                .Select(value => value.ToString("x2", CultureInfo.InvariantCulture)));
        }

        private static void Write(HEU_Parameters parameters, StreetBuildingGenerationPreset preset,
            StreetBuildingStyleConfig style, int variationSeed, string stylePayload, string generationPayload)
        {
            SetInt(parameters, "module_source", 1);
            SetString(parameters, "unity_instance_catalog", stylePayload);
            SetString(parameters, "unity_generation_rules", generationPayload);
            SetFloat(parameters, "ground_floor_height", style.GroundFloorHeight);
            SetFloat(parameters, "typical_floor_height", style.TypicalFloorHeight);
            if (preset == null) return;
            SetFloat(parameters, "internal_width", preset.Width);
            SetFloat(parameters, "internal_depth", preset.Depth);
            SetInt(parameters, "massing_shape", (int)preset.MassingShape);
            SetFloat(parameters, "notch_width", preset.NotchWidth);
            SetFloat(parameters, "notch_depth", preset.NotchDepth);
            SetInt(parameters, "notch_side", (int)preset.NotchSide);
            SetInt(parameters, "floor_count", preset.Floors);
            SetBool(parameters, "corner_building", preset.CornerBuilding);
            SetInt(parameters, "ground_use", (int)preset.GroundUse);
            SetInt(parameters, "facade_control_mode", (int)preset.FacadeMode);
            SetInt(parameters, "facade_rhythm", (int)preset.FacadeRhythm);
            SetFloat(parameters, "shopfront_ratio", preset.ShopfrontRatio);
            SetInt(parameters, "side_mode", (int)preset.SideMode);
            SetInt(parameters, "rear_mode", (int)preset.RearMode);
            SetBool(parameters, "generate_roof", preset.GenerateRoof);
            SetFloat(parameters, "parapet_height", preset.ParapetHeight);
            SetBool(parameters, "generate_architectural_trim", preset.GenerateArchitecturalTrim);
            SetBool(parameters, "generate_attachments", preset.GenerateAttachments);
            SetFloat(parameters, "detail_density", preset.DetailDensity);
            SetBool(parameters, "generate_lods", false);
            SetInt(parameters, "seed", preset.BaseSeed + variationSeed);
        }

        private static void SetInt(HEU_Parameters p, string name, int value)
        { if (!p.SetIntParameterValue(name, value)) throw new InvalidOperationException(name + " rejected."); }
        private static void SetFloat(HEU_Parameters p, string name, float value)
        { if (!p.SetFloatParameterValue(name, value)) throw new InvalidOperationException(name + " rejected."); }
        private static void SetBool(HEU_Parameters p, string name, bool value)
        { if (!p.SetBoolParameterValue(name, value)) throw new InvalidOperationException(name + " rejected."); }
        private static void SetString(HEU_Parameters p, string name, string value)
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

        private sealed class ParameterSnapshot
        {
            private readonly Dictionary<string, int> _ints = new();
            private readonly Dictionary<string, float> _floats = new();
            private readonly Dictionary<string, bool> _bools = new();
            private readonly Dictionary<string, string> _strings = new();

            public static ParameterSnapshot Capture(HEU_Parameters p)
            {
                var result = new ParameterSnapshot();
                foreach (string name in IntParameters)
                    if (p.GetIntParameterValue(name, out int value)) result._ints[name] = value;
                foreach (string name in FloatParameters)
                    if (p.GetFloatParameterValue(name, out float value)) result._floats[name] = value;
                foreach (string name in BoolParameters)
                    if (p.GetBoolParameterValue(name, out bool value)) result._bools[name] = value;
                foreach (string name in StringParameters)
                    if (p.GetStringParameterValue(name, out string value)) result._strings[name] = value;
                return result;
            }

            public void Restore(HEU_Parameters p)
            {
                foreach (var pair in _ints) SetInt(p, pair.Key, pair.Value);
                foreach (var pair in _floats) SetFloat(p, pair.Key, pair.Value);
                foreach (var pair in _bools) SetBool(p, pair.Key, pair.Value);
                foreach (var pair in _strings) SetString(p, pair.Key, pair.Value);
            }
        }
    }
}
#endif
