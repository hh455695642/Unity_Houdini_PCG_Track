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
    /// <summary>
    /// Transactional bridge from artist-friendly DesignPreset data to the
    /// existing HDA interface. Successful cooks are saved immediately; failed
    /// cooks restore every touched parameter and never save the Scene.
    /// </summary>
    public static class StreetBuildingDesignPresetApplier
    {
        // Editor-only seams used by the contract tests to prove that a failed
        // save never persists the Scene and that the parameter transaction is
        // rolled back. Production callers always use the defaults.
        internal static Func<HEU_HoudiniAsset, bool> RequestCook = DefaultRequestCook;
        internal static Func<UnityEngine.SceneManagement.Scene, bool> SaveScene =
            EditorSceneManager.SaveScene;

        private static readonly string[] IntParameters =
        {
            "module_source", "floor_count", "ground_use", "facade_rhythm",
            "rear_mode", "side_mode", "seed"
        };

        private static readonly string[] FloatParameters =
        {
            "internal_width", "internal_depth", "ground_floor_height",
            "typical_floor_height", "shopfront_ratio", "parapet_height", "detail_density"
        };

        private static readonly string[] BoolParameters =
        {
            "corner_building", "generate_roof", "generate_architectural_trim",
            "generate_attachments", "generate_lods"
        };

        private static readonly string[] StringParameters =
        {
            "unity_instance_catalog", "style_id"
        };

        public static string Validate(StreetBuildingDesignPreset preset)
        {
            if (preset == null || preset.Catalog == null)
                return "DesignPreset or Catalog is missing.";
            StreetBuildingCatalogValidationReport catalogReport =
                StreetBuildingModuleCatalogValidator.Validate(preset.Catalog);
            if (!catalogReport.IsValid)
                return catalogReport.ToString();
            if (preset.Width < 4 || preset.Depth < 4
                || Mathf.Abs(preset.Width * .5f - Mathf.Round(preset.Width * .5f)) > .001f
                || Mathf.Abs(preset.Depth * .5f - Mathf.Round(preset.Depth * .5f)) > .001f)
                return "Width and Depth must be exact 2m grid multiples and at least 4m.";
            if (preset.Floors < 2 || preset.DetailDensity < 0 || preset.DetailDensity > 1)
                return "Floors or DetailDensity is outside the supported range.";
            if (preset.ParapetHeight < 0)
                return "ParapetHeight cannot be negative.";
            if (preset.ParapetHeight > .001f)
            {
                StreetBuildingInstanceModuleRecipe straight = preset.Catalog.Modules.FirstOrDefault(
                    item => item.ModuleRole == StreetBuildingModuleRole.Parapet);
                StreetBuildingInstanceModuleRecipe corner = preset.Catalog.Modules.FirstOrDefault(
                    item => item.ModuleRole == StreetBuildingModuleRole.ParapetCorner);
                if (straight == null || corner == null
                    || Mathf.Abs(straight.CellHeight - preset.ParapetHeight) > .001f
                    || Mathf.Abs(corner.CellHeight - preset.ParapetHeight) > .001f)
                    return "Enabled parapet requires matching Parapet and ParapetCorner module heights.";
            }
            if (preset.Catalog.Modules.Any(item => item.ModuleRole == StreetBuildingModuleRole.RoofProp
                                                   && item.VariantId == "ac_unit"))
                return "RoofProp/ac_unit is forbidden; wall AC and roof equipment are separate roles.";
            return string.Empty;
        }

        public static StreetBuildingCompiledCatalog ApplyAndSave(
            HEU_HoudiniAssetRoot root, StreetBuildingAuthoring authoring)
        {
            if (root == null || root.HoudiniAsset == null || authoring == null)
                throw new InvalidOperationException("StreetBuilding HDA root/Authoring is unavailable.");
            StreetBuildingDesignPreset preset = authoring.DesignPreset;
            string validation = Validate(preset);
            if (!string.IsNullOrEmpty(validation))
                throw new InvalidOperationException(validation);

            StreetBuildingCompiledCatalog compiled =
                StreetBuildingModuleCatalogCompiler.Compile(preset.Catalog);
            HEU_HoudiniAsset asset = root.HoudiniAsset;
            HEU_Parameters parameters = asset.Parameters;
            ParameterSnapshot snapshot = ParameterSnapshot.Capture(parameters);
            StreetBuildingInstanceModuleCatalog oldCatalog = authoring.Catalog;
            string oldPayloadSha = authoring.LastAppliedPayloadSha256;
            string oldDesignSha = authoring.LastAppliedDesignSha256;
            string oldTag = root.gameObject.tag;
            try
            {
                Write(parameters, preset, authoring.VariationSeed, compiled.Payload);
                if (!RequestCook(asset))
                    throw new InvalidOperationException("DesignPreset cook failed: " + asset.LastCookResult);

                string designSha = ComputeDesignSha(preset, authoring.VariationSeed, compiled.Sha256);
                authoring.SetEditorCatalog(preset.Catalog);
                authoring.SetEditorAppliedPayloadSha256(compiled.Sha256);
                authoring.SetEditorAppliedDesignSha256(designSha);
                root.gameObject.tag = "EditorOnly";
                EditorUtility.SetDirty(authoring);
                EditorSceneManager.MarkSceneDirty(root.gameObject.scene);
                if (!SaveScene(root.gameObject.scene))
                    throw new InvalidOperationException("DesignPreset Scene save failed.");
                return compiled;
            }
            catch (Exception failure)
            {
                Exception rollbackFailure = null;
                try
                {
                    snapshot.Restore(parameters);
                    authoring.SetEditorCatalog(oldCatalog);
                    authoring.SetEditorAppliedPayloadSha256(oldPayloadSha);
                    authoring.SetEditorAppliedDesignSha256(oldDesignSha);
                    root.gameObject.tag = oldTag;
                    EditorUtility.SetDirty(authoring);
                    if (!RequestCook(asset))
                        throw new InvalidOperationException("rollback cook failed: " + asset.LastCookResult);
                }
                catch (Exception exception)
                {
                    rollbackFailure = exception;
                }
                throw new InvalidOperationException(
                    failure.Message + (rollbackFailure == null
                        ? " Parameters were restored; Scene was not saved."
                        : " Rollback also failed: " + rollbackFailure.Message), failure);
            }
        }

        public static string ComputeDesignSha(
            StreetBuildingDesignPreset preset, int variationSeed, string payloadSha)
        {
            string data = string.Join("|", new[]
            {
                payloadSha, F(preset.Width), F(preset.Depth), preset.Floors.ToString(CultureInfo.InvariantCulture),
                preset.CornerBuilding ? "1" : "0", ((int)preset.GroundUse).ToString(CultureInfo.InvariantCulture),
                ((int)preset.FacadeRhythm).ToString(CultureInfo.InvariantCulture), F(preset.ShopfrontRatio),
                ((int)preset.SideMode).ToString(CultureInfo.InvariantCulture),
                ((int)preset.RearMode).ToString(CultureInfo.InvariantCulture),
                preset.GenerateRoof ? "1" : "0", F(preset.ParapetHeight),
                preset.GenerateArchitecturalTrim ? "1" : "0",
                preset.GenerateAttachments ? "1" : "0", F(preset.DetailDensity),
                (preset.BaseSeed + variationSeed).ToString(CultureInfo.InvariantCulture)
            });
            using SHA256 sha = SHA256.Create();
            return string.Concat(sha.ComputeHash(Encoding.UTF8.GetBytes(data))
                .Select(value => value.ToString("x2", CultureInfo.InvariantCulture)));
        }

        private static void Write(HEU_Parameters parameters, StreetBuildingDesignPreset preset,
            int variationSeed, string payload)
        {
            SetInt(parameters, "module_source", 1);
            SetString(parameters, "unity_instance_catalog", payload);
            SetString(parameters, "style_id", preset.Catalog.StyleId);
            SetFloat(parameters, "internal_width", preset.Width);
            SetFloat(parameters, "internal_depth", preset.Depth);
            SetFloat(parameters, "ground_floor_height", preset.Catalog.GroundFloorHeight);
            SetFloat(parameters, "typical_floor_height", preset.Catalog.TypicalFloorHeight);
            SetInt(parameters, "floor_count", preset.Floors);
            SetBool(parameters, "corner_building", preset.CornerBuilding);
            SetInt(parameters, "ground_use", (int)preset.GroundUse);
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
        {
            if (!p.SetIntParameterValue(name, value)) throw new InvalidOperationException(name + " rejected.");
        }
        private static void SetFloat(HEU_Parameters p, string name, float value)
        {
            if (!p.SetFloatParameterValue(name, value)) throw new InvalidOperationException(name + " rejected.");
        }
        private static void SetBool(HEU_Parameters p, string name, bool value)
        {
            if (!p.SetBoolParameterValue(name, value)) throw new InvalidOperationException(name + " rejected.");
        }
        private static void SetString(HEU_Parameters p, string name, string value)
        {
            HEU_ParameterData data = p.GetParameter(name);
            if (data == null || data._stringValues == null || data._stringValues.Length == 0)
                throw new InvalidOperationException(name + " is unavailable.");
            p.SetStringParameterValue(name, value ?? string.Empty);
            data._stringValues[0] = value ?? string.Empty;
        }
        private static string F(float value) => value.ToString("R", CultureInfo.InvariantCulture);

        internal static void ResetTestHooks()
        {
            RequestCook = DefaultRequestCook;
            SaveScene = EditorSceneManager.SaveScene;
        }

        private static bool DefaultRequestCook(HEU_HoudiniAsset asset)
        {
            return asset.RequestCook(true, false, true, true)
                   && asset.LastCookResult == HEU_AssetCookResultWrapper.SUCCESS;
        }

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
                {
                    if (!p.GetIntParameterValue(name, out int value))
                        throw new InvalidOperationException("Cannot snapshot " + name);
                    result._ints[name] = value;
                }
                foreach (string name in FloatParameters)
                {
                    if (!p.GetFloatParameterValue(name, out float value))
                        throw new InvalidOperationException("Cannot snapshot " + name);
                    result._floats[name] = value;
                }
                foreach (string name in BoolParameters)
                {
                    if (!p.GetBoolParameterValue(name, out bool value))
                        throw new InvalidOperationException("Cannot snapshot " + name);
                    result._bools[name] = value;
                }
                foreach (string name in StringParameters)
                {
                    if (!p.GetStringParameterValue(name, out string value))
                        throw new InvalidOperationException("Cannot snapshot " + name);
                    result._strings[name] = value;
                }
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
