#if UNITY_EDITOR
using System;
using System.Collections.Generic;
using System.Globalization;
using System.Linq;
using System.Security.Cryptography;
using System.Text;
using System.Text.RegularExpressions;
using HoudiniEngineUnity;
using PCGBike.Buildings;
using UnityEditor;
using UnityEditor.SceneManagement;
using UnityEngine;

namespace PCGBike.Editor.Buildings
{
    public sealed class StreetBuildingCatalogValidationReport
    {
        private readonly List<string> _errors = new();
        private readonly List<string> _warnings = new();

        public IReadOnlyList<string> Errors => _errors;
        public IReadOnlyList<string> Warnings => _warnings;
        public bool IsValid => _errors.Count == 0;

        internal void Error(string message) => _errors.Add(message);
        internal void Warning(string message) => _warnings.Add(message);

        public override string ToString()
        {
            var lines = new List<string> { IsValid ? "Catalog validation PASS" : "Catalog validation FAIL" };
            lines.AddRange(_errors.Select(item => "ERROR: " + item));
            lines.AddRange(_warnings.Select(item => "WARNING: " + item));
            return string.Join("\n", lines);
        }
    }

    public sealed class StreetBuildingCompiledCatalog
    {
        public StreetBuildingCompiledCatalog(string payload, string sha256, int moduleCount, int partCount)
        {
            Payload = payload;
            Sha256 = sha256;
            ModuleCount = moduleCount;
            PartCount = partCount;
        }

        public string Payload { get; }
        public string Sha256 { get; }
        public int ModuleCount { get; }
        public int PartCount { get; }
    }

    public static class StreetBuildingModuleCatalogValidator
    {
        private static readonly Regex StyleIdPattern =
            new("^[a-z][a-z0-9]*(?:_[a-z0-9]+)*$", RegexOptions.CultureInvariant);

        private static readonly string[] RequiredRev41Slots =
        {
            "Entrance|entrance_metal",
            "GroundShop|shop_metal",
            "GroundShop|shop_trim",
            "Cornice|brick_center",
            "MiddleWindow|trim",
            "MiddleWindow|trim_single",
            "FacadeColumn|trim_ground",
            "FacadeColumn|brick_upper",
        };

        public static StreetBuildingCatalogValidationReport Validate(
            StreetBuildingInstanceModuleCatalog catalog,
            bool requireRev41Compatibility = true)
        {
            var report = new StreetBuildingCatalogValidationReport();
            if (catalog == null)
            {
                report.Error("Catalog is null.");
                return report;
            }

            if (catalog.SchemaVersion != StreetBuildingInstanceModuleCatalog.CurrentSchemaVersion)
                report.Error($"SchemaVersion {catalog.SchemaVersion} is unsupported.");
            if (string.IsNullOrWhiteSpace(catalog.DisplayName))
                report.Error("DisplayName is empty.");
            if (string.IsNullOrWhiteSpace(catalog.StyleId) || !StyleIdPattern.IsMatch(catalog.StyleId))
                report.Error($"StyleId '{catalog.StyleId}' must be lowercase snake_case.");
            if (catalog.CellWidth <= 0 || catalog.GroundFloorHeight <= 0 || catalog.TypicalFloorHeight <= 0)
                report.Error("Cell and floor dimensions must be positive.");
            if (requireRev41Compatibility)
            {
                RequireNear(report, catalog.CellWidth, 2.0f, "CellWidth");
                RequireNear(report, catalog.GroundFloorHeight, 4.0f, "GroundFloorHeight");
                RequireNear(report, catalog.TypicalFloorHeight, 3.0f, "TypicalFloorHeight");
            }

            string[] roots = catalog.AllowedAssetRoots
                .Where(item => !string.IsNullOrWhiteSpace(item))
                .Select(NormalizeAssetPath)
                .Distinct(StringComparer.Ordinal)
                .ToArray();
            if (roots.Length == 0 && !string.IsNullOrWhiteSpace(catalog.SourceRoot))
                roots = new[] { NormalizeAssetPath(catalog.SourceRoot) };
            if (roots.Length == 0)
                report.Error("AllowedAssetRoots is empty.");

            var keys = new HashSet<string>(StringComparer.Ordinal);
            foreach (StreetBuildingInstanceModuleRecipe recipe in catalog.Modules)
            {
                if (recipe == null)
                {
                    report.Error("Modules contains a null recipe.");
                    continue;
                }

                string key = recipe.ModuleRole + "|" + recipe.VariantId;
                if (string.IsNullOrWhiteSpace(recipe.VariantId)
                    || recipe.VariantId.Contains("|") || recipe.VariantId.Contains("\n"))
                    report.Error($"{recipe.ModuleRole} has an invalid VariantId '{recipe.VariantId}'.");
                if (!keys.Add(key))
                    report.Error("Duplicate module key: " + key);
                if (recipe.CellWidth <= 0 || recipe.CellHeight <= 0 || recipe.Weight <= 0)
                    report.Error(key + " has non-positive dimensions or weight.");
                if (recipe.Parts == null || recipe.Parts.Count == 0)
                {
                    report.Error(key + " has no source parts.");
                    continue;
                }

                for (int partIndex = 0; partIndex < recipe.Parts.Count; partIndex++)
                    ValidatePart(report, key, partIndex, recipe.Parts[partIndex], roots);
            }

            if (requireRev41Compatibility)
            {
                foreach (string required in RequiredRev41Slots)
                {
                    if (!keys.Contains(required))
                        report.Error("REV4.1 required slot is missing: " + required);
                }
            }

            return report;
        }

        private static void ValidatePart(
            StreetBuildingCatalogValidationReport report,
            string key,
            int partIndex,
            StreetBuildingInstancePart part,
            IReadOnlyList<string> roots)
        {
            string label = $"{key} part {partIndex}";
            if (part == null || part.SourceAsset == null)
            {
                report.Error(label + " has a missing SourceAsset.");
                return;
            }
            if (part.LocalEulerRotation.sqrMagnitude > 1e-8f)
                report.Error(label + " must use identity catalog rotation; rotate children inside a Prefab.");

            string path = NormalizeAssetPath(AssetDatabase.GetAssetPath(part.SourceAsset));
            if (string.IsNullOrEmpty(path) || path.Contains("|") || path.Contains("\n"))
            {
                report.Error(label + " has an invalid asset path: " + path);
                return;
            }
            bool supportedExtension = path.EndsWith(".prefab", StringComparison.OrdinalIgnoreCase)
                                      || path.EndsWith(".fbx", StringComparison.OrdinalIgnoreCase);
            if (!supportedExtension)
                report.Error(label + " must reference a Prefab or FBX Model Prefab: " + path);
            if (!roots.Any(root => path.Equals(root, StringComparison.Ordinal)
                                   || path.StartsWith(root + "/", StringComparison.Ordinal)))
                report.Error(label + " is outside AllowedAssetRoots: " + path);

            Transform rootTransform = part.SourceAsset.transform;
            if (rootTransform.localPosition.sqrMagnitude > 1e-8f
                || Quaternion.Angle(rootTransform.localRotation, Quaternion.identity) > 0.001f
                || (rootTransform.localScale - Vector3.one).sqrMagnitude > 1e-8f)
                report.Error(label + " asset root Transform must be position 0, rotation 0, scale 1.");

            Component[] components = part.SourceAsset.GetComponentsInChildren<Component>(true);
            foreach (Component component in components)
            {
                if (component == null)
                {
                    report.Error(label + " contains a missing script component.");
                    continue;
                }
                if (component is Transform || component is MeshFilter || component is MeshRenderer)
                    continue;
                report.Error(label + " contains unsupported component " + component.GetType().Name + ".");
            }

            MeshFilter[] filters = part.SourceAsset.GetComponentsInChildren<MeshFilter>(true);
            MeshRenderer[] renderers = part.SourceAsset.GetComponentsInChildren<MeshRenderer>(true);
            if (filters.Length == 0 || renderers.Length == 0)
                report.Error(label + " must contain visible MeshFilter and MeshRenderer components.");
            if (filters.Any(filter => filter.sharedMesh == null))
                report.Error(label + " contains a MeshFilter without a mesh.");
            if (renderers.Any(renderer => renderer.sharedMaterials.Any(material => material == null)))
                report.Error(label + " contains a missing material reference.");

            int materialSlots = renderers.Sum(renderer => renderer.sharedMaterials.Length);
            if (materialSlots > 3)
                report.Warning(label + $" uses {materialSlots} material slots; mobile target recommends <= 3.");
            if (renderers.SelectMany(renderer => renderer.sharedMaterials)
                .Where(material => material != null)
                .Any(material => material.shader == null))
                report.Error(label + " contains a material without a shader.");
        }

        private static void RequireNear(
            StreetBuildingCatalogValidationReport report, float actual, float expected, string label)
        {
            if (Mathf.Abs(actual - expected) > 0.001f)
                report.Error($"REV4.1 requires {label}={expected:R}, got {actual:R}.");
        }

        private static string NormalizeAssetPath(string path) =>
            (path ?? string.Empty).Trim().TrimEnd('/').Replace('\\', '/');
    }

    public static class StreetBuildingModuleCatalogCompiler
    {
        private static readonly Dictionary<string, int> Rev41Order = new(StringComparer.Ordinal)
        {
            ["Entrance|entrance_metal"] = 0,
            ["GroundShop|shop_metal"] = 10,
            ["GroundShop|shop_trim"] = 11,
            ["Cornice|brick_center"] = 20,
            ["MiddleWindow|trim"] = 30,
            ["MiddleWindow|trim_single"] = 31,
            ["FacadeColumn|trim_ground"] = 40,
            ["FacadeColumn|brick_upper"] = 41,
        };

        public static StreetBuildingCompiledCatalog Compile(
            StreetBuildingInstanceModuleCatalog catalog,
            bool requireRev41Compatibility = true)
        {
            StreetBuildingCatalogValidationReport report =
                StreetBuildingModuleCatalogValidator.Validate(catalog, requireRev41Compatibility);
            if (!report.IsValid)
                throw new InvalidOperationException(report.ToString());

            var rows = new List<string>();
            IEnumerable<StreetBuildingInstanceModuleRecipe> recipes = catalog.Modules
                .OrderBy(recipe => SortOrder(recipe))
                .ThenBy(recipe => recipe.ModuleRole)
                .ThenBy(recipe => recipe.VariantId, StringComparer.Ordinal);
            foreach (StreetBuildingInstanceModuleRecipe recipe in recipes)
            {
                for (int index = 0; index < recipe.Parts.Count; index++)
                {
                    StreetBuildingInstancePart part = recipe.Parts[index];
                    string path = AssetDatabase.GetAssetPath(part.SourceAsset).Replace('\\', '/');
                    Vector3 position = part.LocalPosition;
                    Vector3 rotation = part.LocalEulerRotation;
                    rows.Add(string.Join("|",
                        recipe.ModuleRole,
                        recipe.VariantId,
                        index.ToString(CultureInfo.InvariantCulture),
                        path,
                        F(position.x), F(position.y), F(position.z),
                        F(rotation.x), F(rotation.y), F(rotation.z)));
                }
            }

            string payload = string.Join("\n", rows);
            return new StreetBuildingCompiledCatalog(
                payload,
                Sha256(payload),
                catalog.Modules.Count,
                rows.Count);
        }

        private static int SortOrder(StreetBuildingInstanceModuleRecipe recipe)
        {
            string key = recipe.ModuleRole + "|" + recipe.VariantId;
            return Rev41Order.TryGetValue(key, out int order) ? order : 1000;
        }

        private static string F(float value) => value.ToString("R", CultureInfo.InvariantCulture);

        private static string Sha256(string value)
        {
            using SHA256 sha = SHA256.Create();
            return string.Concat(sha.ComputeHash(Encoding.UTF8.GetBytes(value))
                .Select(item => item.ToString("x2", CultureInfo.InvariantCulture)));
        }
    }

    public static class StreetBuildingModuleCatalogApplier
    {
        public static StreetBuildingCompiledCatalog Apply(
            HEU_HoudiniAssetRoot root,
            StreetBuildingAuthoring authoring)
        {
            if (root == null || root.HoudiniAsset == null)
                throw new InvalidOperationException("StreetBuilding HDA root is null or uninitialized.");
            if (authoring == null || authoring.Catalog == null)
                throw new InvalidOperationException("StreetBuildingAuthoring has no Catalog.");

            HEU_HoudiniAsset asset = root.HoudiniAsset;
            if (string.IsNullOrEmpty(asset.AssetOpName)
                || asset.AssetOpName.IndexOf("StreetBuilding::1.0", StringComparison.Ordinal) < 0)
                throw new InvalidOperationException("Target is not pcgbike::StreetBuilding::1.0: " + asset.AssetOpName);

            StreetBuildingCompiledCatalog compiled =
                StreetBuildingModuleCatalogCompiler.Compile(authoring.Catalog);
            HEU_Parameters parameters = asset.Parameters;
            if (!parameters.GetIntParameterValue("module_source", out int oldModuleSource)
                || !parameters.GetStringParameterValue("unity_instance_catalog", out string oldPayload)
                || !parameters.GetStringParameterValue("style_id", out string oldStyleId))
                throw new InvalidOperationException("StreetBuilding authoring parameters are unavailable.");

            try
            {
                Require(parameters.SetIntParameterValue("module_source", 1), "module_source");
                SetString(parameters, "unity_instance_catalog", compiled.Payload);
                SetString(parameters, "style_id", authoring.Catalog.StyleId);
                if (!asset.RequestCook(false, false, true, true)
                    || asset.LastCookResult != HEU_AssetCookResultWrapper.SUCCESS)
                    throw new InvalidOperationException("StreetBuilding Catalog cook failed: " + asset.LastCookResult);

                authoring.SetEditorAppliedPayloadSha256(compiled.Sha256);
                EditorUtility.SetDirty(authoring);
                EditorSceneManager.MarkSceneDirty(authoring.gameObject.scene);
                return compiled;
            }
            catch (Exception applyFailure)
            {
                Exception rollbackFailure = null;
                try
                {
                    Require(parameters.SetIntParameterValue("module_source", oldModuleSource), "module_source rollback");
                    SetString(parameters, "unity_instance_catalog", oldPayload);
                    SetString(parameters, "style_id", oldStyleId);
                    if (!asset.RequestCook(false, false, true, true)
                        || asset.LastCookResult != HEU_AssetCookResultWrapper.SUCCESS)
                        throw new InvalidOperationException("Rollback cook failed: " + asset.LastCookResult);
                }
                catch (Exception exception)
                {
                    rollbackFailure = exception;
                }

                string suffix = rollbackFailure == null
                    ? " Previous parameters were restored."
                    : " Rollback also failed: " + rollbackFailure;
                throw new InvalidOperationException(applyFailure.Message + suffix, applyFailure);
            }
        }

        private static void SetString(HEU_Parameters parameters, string name, string value)
        {
            if (parameters.SetStringParameterValue(name, value))
                return;
            HEU_ParameterData data = parameters.GetParameter(name);
            if (data == null || data._stringValues == null || data._stringValues.Length == 0)
                throw new InvalidOperationException("StreetBuilding string parameter is missing: " + name);
            data._stringValues[0] = value ?? string.Empty;
        }

        private static void Require(bool success, string name)
        {
            if (!success)
                throw new InvalidOperationException("StreetBuilding parameter was rejected: " + name);
        }
    }
}
#endif
