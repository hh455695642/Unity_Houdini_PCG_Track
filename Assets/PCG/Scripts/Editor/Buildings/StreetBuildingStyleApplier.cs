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
    /// StyleConfig 到 HDA 的窄事务桥。体块、立面、附件和随机参数完全由 HDA 面板持有，
    /// 本类只同步模块目录和 StyleConfig 拥有的尺寸。
    /// </summary>
    public static class StreetBuildingStyleApplier
    {
        internal static Func<HEU_HoudiniAsset, bool> RequestCook = DefaultRequestCook;
        internal static Func<UnityEngine.SceneManagement.Scene, bool> SaveScene = EditorSceneManager.SaveScene;

        private static readonly string[] IntParameters = { "module_source" };
        private static readonly string[] FloatParameters =
            { "floor_height_ground", "floor_height_typical" };
        private static readonly string[] StringParameters =
            { "unity_style_catalog", "unity_bridge_end_marker" };

        public static string Validate(StreetBuildingStyleConfig style)
        {
            if (style == null) return "StyleConfig is missing.";
            StreetBuildingStyleValidationReport report = StreetBuildingStyleValidator.Validate(style);
            return report.IsValid ? string.Empty : report.ToString();
        }

        public static StreetBuildingCompiledStyle ApplyAndSave(
            HEU_HoudiniAssetRoot root, StreetBuildingAuthoring authoring)
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
            string oldTag = root.gameObject.tag;
            try
            {
                Write(parameters, style, compiled.Payload);
                if (!RequestCook(asset))
                    throw new InvalidOperationException("StyleConfig cook failed: " + asset.LastCookResult);

                authoring.SetEditorAppliedPayloadSha256(compiled.Sha256);
                authoring.SetEditorCookDiagnostic("Cook PASS: " + asset.LastCookResult);
                root.gameObject.tag = "EditorOnly";
                EditorUtility.SetDirty(authoring);
                EditorSceneManager.MarkSceneDirty(root.gameObject.scene);
                if (!SaveScene(root.gameObject.scene))
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
                    authoring.SetEditorCookDiagnostic(oldDiagnostic);
                    root.gameObject.tag = oldTag;
                    EditorUtility.SetDirty(authoring);
                    if (!RequestCook(asset))
                        throw new InvalidOperationException("rollback cook failed: " + asset.LastCookResult);
                }
                catch (Exception exception) { rollbackFailure = exception; }
                throw new InvalidOperationException(failure.Message + (rollbackFailure == null
                    ? " Style parameters were restored; Scene was not saved."
                    : " Rollback also failed: " + rollbackFailure.Message), failure);
            }
        }

        private static void Write(
            HEU_Parameters parameters, StreetBuildingStyleConfig style, string stylePayload)
        {
            SetInt(parameters, "module_source", 1);
            SetString(parameters, "unity_style_catalog", stylePayload);
            SetString(parameters, "unity_bridge_end_marker", "END");
            SetFloat(parameters, "floor_height_ground", style.GroundFloorHeight);
            SetFloat(parameters, "floor_height_typical", style.TypicalFloorHeight);
        }

        private static void SetInt(HEU_Parameters p, string name, int value)
        { if (!p.SetIntParameterValue(name, value)) throw new InvalidOperationException(name + " rejected."); }
        private static void SetFloat(HEU_Parameters p, string name, float value)
        { if (!p.SetFloatParameterValue(name, value)) throw new InvalidOperationException(name + " rejected."); }
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
            private readonly Dictionary<string, string> _strings = new();

            public static ParameterSnapshot Capture(HEU_Parameters p)
            {
                var result = new ParameterSnapshot();
                foreach (string name in IntParameters)
                    if (p.GetIntParameterValue(name, out int value)) result._ints[name] = value;
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
