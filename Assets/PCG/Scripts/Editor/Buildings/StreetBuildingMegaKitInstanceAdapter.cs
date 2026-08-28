#if UNITY_EDITOR
using System;
using System.Collections.Generic;
using System.Globalization;
using System.IO;
using System.Linq;
using System.Security.Cryptography;
using System.Text;
using HoudiniEngineUnity;
using PCGBike.Buildings;
using UnityEditor;
using UnityEditor.SceneManagement;
using UnityEngine;
using UnityEngine.SceneManagement;

namespace PCGBike.Editor.Buildings
{
    /// <summary>
    /// REV4.1 adapter: compiles rules to unity_instance paths only. It never reads
    /// source vertex buffers and never creates Mesh, Material or Prefab assets.
    /// </summary>
    public static class StreetBuildingMegaKitInstanceAdapter
    {
        public const string StyleId = "na_brick_mixeduse_01";
        public const string SourceRoot =
            "Assets/PCG/Art/Downtown City MegaKit[Standard]";
        public const string SourceModels = SourceRoot + "/Exports/FBX (Unity)";
        public const string CatalogPath =
            "Assets/PCG/Art/StreetBuilding/NA_Brick_MixedUse_01/StreetBuildingInstanceModuleCatalog_NAB01.asset";
        public const string ScenePath = "Assets/PCG/Scenes/PCG_Building.unity";
        public const string CapturedSourceSha256 =
            "3cb8b581b271288307dfb39335153af41598459221f986b678f420b7dc071e9d";
        private const string LegacyCompiledRootName =
            "StreetBuilding_ModuleInput_EditorOnly";

        private static readonly string[] LegacyGeneratedPaths =
        {
            "Assets/PCG/Art/StreetBuilding/NA_Brick_MixedUse_01/NativeV2",
            "Assets/PCG/Art/StreetBuilding/NA_Brick_MixedUse_01/Meshes",
            "Assets/PCG/Art/StreetBuilding/NA_Brick_MixedUse_01/Prefabs",
            "Assets/PCG/Art/StreetBuilding/NA_Brick_MixedUse_01/StreetBuildingMegaKitStandardProfile.asset",
            "Assets/PCG/Art/StreetBuilding/NA_Brick_MixedUse_01/StreetBuildingModuleLibrary_NAB01.asset",
            "Assets/PCG/Materials/Buildings/NAB01",
            "Assets/PCG/Texture/StreetBuilding/NAB01",
        };

        [MenuItem("PCG/StreetBuilding/MegaKit Instances/Clean Legacy Derived Assets", priority = 2250)]
        public static void CleanLegacyMenu()
        {
            if (CleanLegacyGeneratedAssets(out string report))
                Debug.Log(report);
            else
                Debug.LogError(report);
        }

        [MenuItem("PCG/StreetBuilding/MegaKit Instances/Build Direct Instance Catalog", priority = 2251)]
        public static void BuildCatalogMenu()
        {
            if (BuildCatalog(out string report))
                Debug.Log(report);
            else
                Debug.LogError(report);
        }

        [MenuItem("PCG/StreetBuilding/MegaKit Instances/Apply To StreetBuilding1 + Save", priority = 2252)]
        public static void ApplyToStreetBuilding1Menu()
        {
            try
            {
                // The previous HEU auto-cook left a transient dirty hierarchy. Reload
                // the saved scene before REV4.1 so it cannot leak into the new result.
                Scene scene = EditorSceneManager.OpenScene(ScenePath, OpenSceneMode.Single);
                if (!CleanLegacyGeneratedAssets(out string cleanup))
                    throw new InvalidOperationException(cleanup);
                if (!BuildCatalog(out string build))
                    throw new InvalidOperationException(build);
                HEU_HoudiniAssetRoot root = scene.GetRootGameObjects()
                    .SelectMany(item => item.GetComponentsInChildren<HEU_HoudiniAssetRoot>(true))
                    .FirstOrDefault(item => item.name == "StreetBuilding1");
                if (root == null)
                    throw new InvalidOperationException("PCG_Building has no StreetBuilding1 HDA root.");
                if (!ApplyToExisting(root, out string apply))
                    throw new InvalidOperationException(apply);
                EditorSceneManager.SaveScene(scene);
                Selection.activeGameObject = root.gameObject;
                SceneView.lastActiveSceneView?.FrameSelected();
                Debug.Log($"StreetBuilding REV4.1 saved to {ScenePath}.\n{cleanup}\n{build}\n{apply}", root);
            }
            catch (Exception exception)
            {
                Debug.LogError("StreetBuilding REV4.1 apply failed.\n" + exception);
            }
        }

        public static bool BuildCatalog(out string report)
        {
            try
            {
                string sourceHashBefore = ComputeSourceHash();
                if (!string.Equals(sourceHashBefore, CapturedSourceSha256, StringComparison.Ordinal))
                    throw new InvalidOperationException(
                        "MegaKit source SHA-256 differs from the captured read-only baseline: " + sourceHashBefore);

                EnsureAssetFolder(Path.GetDirectoryName(CatalogPath)?.Replace('\\', '/'));
                List<StreetBuildingInstanceModuleRecipe> recipes = CreateRecipes();
                StreetBuildingInstanceModuleCatalog catalog =
                    AssetDatabase.LoadAssetAtPath<StreetBuildingInstanceModuleCatalog>(CatalogPath);
                if (catalog == null)
                {
                    catalog = ScriptableObject.CreateInstance<StreetBuildingInstanceModuleCatalog>();
                    AssetDatabase.CreateAsset(catalog, CatalogPath);
                }
                catalog.SetEditorData(
                    StreetBuildingInstanceModuleCatalog.CurrentSchemaVersion,
                    "North American Brick Mixed Use 01 (MegaKit Validation)",
                    StreetBuildingAssetSourceKind.ExternalReadOnly,
                    StyleId,
                    SourceModels,
                    sourceHashBefore,
                    new[] { SourceModels },
                    2.0f,
                    4.0f,
                    3.0f,
                    recipes);
                EditorUtility.SetDirty(catalog);
                AssetDatabase.SaveAssets();
                ValidateCatalog(catalog);
                string payloadA = CompilePayload(catalog);
                string payloadB = CompilePayload(catalog);
                if (!string.Equals(payloadA, payloadB, StringComparison.Ordinal))
                    throw new InvalidOperationException("Catalog compilation is not deterministic.");
                string sourceHashAfter = ComputeSourceHash();
                if (!string.Equals(sourceHashBefore, sourceHashAfter, StringComparison.Ordinal))
                    throw new InvalidOperationException("Catalog build modified the MegaKit source directory.");
                Selection.activeObject = catalog;
                report = $"Built {recipes.Count} recipes / {recipes.Sum(item => item.Parts.Count)} original FBX parts; "
                         + $"payload SHA-256 {Hash(Encoding.UTF8.GetBytes(payloadA))}; no Mesh/Prefab/Material generated.";
                return true;
            }
            catch (Exception exception)
            {
                report = exception.ToString();
                return false;
            }
        }

        public static bool ApplyToExisting(HEU_HoudiniAssetRoot root, out string report)
        {
            try
            {
                if (root == null || root.HoudiniAsset == null)
                    throw new InvalidOperationException("StreetBuilding HDA root is null or uninitialized.");
                StreetBuildingInstanceModuleCatalog catalog =
                    AssetDatabase.LoadAssetAtPath<StreetBuildingInstanceModuleCatalog>(CatalogPath);
                ValidateCatalog(catalog);
                StreetBuildingAuthoring authoring = root.GetComponent<StreetBuildingAuthoring>();
                if (authoring == null)
                    authoring = Undo.AddComponent<StreetBuildingAuthoring>(root.gameObject);
                authoring.SetEditorCatalog(catalog);
                EditorUtility.SetDirty(authoring);
                StreetBuildingCompiledCatalog compiled =
                    StreetBuildingModuleCatalogApplier.Apply(root, authoring);

                DirectInstanceAudit audit = AuditGeneratedInstances(root);
                root.gameObject.tag = "EditorOnly";
                EditorSceneManager.MarkSceneDirty(root.gameObject.scene);
                report = $"Cooked original MegaKit instances: {audit.InstanceRoots} point roots, "
                         + $"{audit.MeshFilters} MeshFilters, {audit.Renderers} Renderers, "
                         + $"{audit.UniqueMeshes} original FBX meshes, {audit.UniqueMaterials} original materials. "
                         + $"Payload SHA-256 {compiled.Sha256}. "
                         + "Only Catalog parameters changed; structural HDA parameters were preserved.";
                return true;
            }
            catch (Exception exception)
            {
                report = exception.ToString();
                return false;
            }
        }

        public static string CompilePayload(StreetBuildingInstanceModuleCatalog catalog)
        {
            return StreetBuildingModuleCatalogCompiler.Compile(catalog).Payload;
        }

        public static bool CleanLegacyGeneratedAssets(out string report)
        {
            try
            {
                if (!string.Equals(ComputeSourceHash(), CapturedSourceSha256, StringComparison.Ordinal))
                    throw new InvalidOperationException("Source hash mismatch; cleanup stopped before deleting anything.");
                var deleted = new List<string>();
                foreach (string path in LegacyGeneratedPaths)
                {
                    if (AssetDatabase.LoadMainAssetAtPath(path) == null && !AssetDatabase.IsValidFolder(path))
                        continue;
                    if (!AssetDatabase.DeleteAsset(path))
                        throw new InvalidOperationException("AssetDatabase failed to delete generated path: " + path);
                    deleted.Add(path);
                }
                AssetDatabase.SaveAssets();
                AssetDatabase.Refresh(ImportAssetOptions.ForceSynchronousImport);
                report = deleted.Count == 0
                    ? "No legacy generated MegaKit assets remained."
                    : "Deleted legacy generated assets:\n- " + string.Join("\n- ", deleted);
                return true;
            }
            catch (Exception exception)
            {
                report = exception.ToString();
                return false;
            }
        }

        public static string ComputeSourceHash()
        {
            string absoluteRoot = Path.GetFullPath(Path.Combine(
                Directory.GetCurrentDirectory(), SourceRoot.Replace('/', Path.DirectorySeparatorChar)));
            if (!Directory.Exists(absoluteRoot))
                throw new DirectoryNotFoundException(absoluteRoot);
            var payload = new StringBuilder();
            foreach (string path in Directory.GetFiles(absoluteRoot, "*", SearchOption.AllDirectories)
                         .OrderBy(item => item, StringComparer.OrdinalIgnoreCase))
            {
                payload.Append(path.Substring(absoluteRoot.Length + 1).Replace('\\', '/')).Append('|')
                    .Append(Hash(File.ReadAllBytes(path))).Append('\n');
            }
            return Hash(Encoding.UTF8.GetBytes(payload.ToString()));
        }

        private static List<StreetBuildingInstanceModuleRecipe> CreateRecipes()
        {
            StreetBuildingInstancePart Part(string name, Vector3 position) =>
                new(LoadSourceFbx(name), position, Vector3.zero);
            return new List<StreetBuildingInstanceModuleRecipe>
            {
                new(StreetBuildingModuleRole.Entrance, "entrance_metal", 2, 3, 1,
                    new[] { Part("DoorFrame_Metal_Single", Vector3.zero), Part("Door_2", new Vector3(-.5f, 0, -.12f)) }),
                new(StreetBuildingModuleRole.GroundShop, "shop_metal", 2, 3, 1,
                    new[] { Part("Metal_FirstFloor_Window", Vector3.zero) }),
                new(StreetBuildingModuleRole.GroundShop, "shop_trim", 2, 3, 1,
                    new[] { Part("Trim_FirstFloor_Window_001", Vector3.zero) }),
                new(StreetBuildingModuleRole.Cornice, "brick_center", 2, 1, 1,
                    new[] { Part("Cornice_Brick_Center", Vector3.zero) }),
                new(StreetBuildingModuleRole.MiddleWindow, "trim", 2, 3, 1,
                    new[] { Part("Brick_Window_Trim", Vector3.zero) }),
                new(StreetBuildingModuleRole.MiddleWindow, "trim_single", 2, 3, 1,
                    new[] { Part("Brick_Window_Trim_Single", Vector3.zero) }),
                new(StreetBuildingModuleRole.FacadeColumn, "trim_ground", 2, 3, 1,
                    new[] { Part("Trim_Column_Center", Vector3.zero) }),
                new(StreetBuildingModuleRole.FacadeColumn, "brick_upper", 2, 3, 1,
                    new[] { Part("Brick_Column_Small", Vector3.zero) }),
            };
        }

        private static GameObject LoadSourceFbx(string name)
        {
            string path = SourceModels + "/" + name + ".fbx";
            GameObject asset = AssetDatabase.LoadAssetAtPath<GameObject>(path);
            if (asset == null)
                throw new InvalidOperationException("Original MegaKit FBX is missing: " + path);
            return asset;
        }

        private static void ValidateCatalog(StreetBuildingInstanceModuleCatalog catalog)
        {
            StreetBuildingCatalogValidationReport validation =
                StreetBuildingModuleCatalogValidator.Validate(catalog);
            if (!validation.IsValid)
                throw new InvalidOperationException(validation.ToString());
            if (catalog.StyleId != StyleId || catalog.SourceRoot != SourceModels
                || catalog.SourceKind != StreetBuildingAssetSourceKind.ExternalReadOnly)
                throw new InvalidOperationException("MegaKit validation Catalog identity mismatch.");
            if (catalog.Modules.Count != 8 || catalog.Modules.Sum(item => item.Parts.Count) != 9)
                throw new InvalidOperationException("REV4.1 catalog must contain 8 recipes / 9 source parts.");
        }

        private static DirectInstanceAudit AuditGeneratedInstances(HEU_HoudiniAssetRoot root)
        {
            MeshFilter[] filters = root.GetComponentsInChildren<MeshFilter>(true)
                .Where(item => item.sharedMesh != null).ToArray();
            MeshRenderer[] renderers = root.GetComponentsInChildren<MeshRenderer>(true);
            if (filters.Length == 0 || renderers.Length == 0)
                throw new InvalidOperationException("Direct-instance cook produced no visible FBX renderers.");
            foreach (MeshFilter filter in filters)
            {
                string path = AssetDatabase.GetAssetPath(filter.sharedMesh);
                if (!path.StartsWith(SourceModels + "/", StringComparison.Ordinal)
                    || !path.EndsWith(".fbx", StringComparison.OrdinalIgnoreCase))
                    throw new InvalidOperationException("Cook produced a derived/non-MegaKit mesh: " + path);
            }
            Material[] materials = renderers.SelectMany(item => item.sharedMaterials)
                .Where(item => item != null).Distinct().ToArray();
            foreach (Material material in materials)
            {
                string path = AssetDatabase.GetAssetPath(material);
                if (!path.StartsWith(SourceRoot + "/", StringComparison.Ordinal))
                    throw new InvalidOperationException("Cook replaced an original MegaKit material: " + path);
            }
            string[] materialNames = materials.Select(item => item.name).ToArray();
            if (!materialNames.Any(name => name.IndexOf("Glass", StringComparison.OrdinalIgnoreCase) >= 0)
                || !materialNames.Any(name => name.IndexOf("FakeInterior", StringComparison.OrdinalIgnoreCase) >= 0))
                throw new InvalidOperationException("Original Glass/FakeInterior materials were not preserved.");
            if (root.GetComponentsInChildren<LODGroup>(true).Length != 0
                || root.GetComponentsInChildren<Collider>(true).Length != 0)
                throw new InvalidOperationException("REV4.1 facade-only output unexpectedly contains LODGroup/Collider.");
            int instanceRoots = root.GetComponentsInChildren<Transform>(true)
                .Count(item => item.name.StartsWith("SB_B0000_", StringComparison.Ordinal));
            if (instanceRoots < 32)
                throw new InvalidOperationException("Expected at least 32 named direct-instance roots, got " + instanceRoots);
            return new DirectInstanceAudit(
                instanceRoots,
                filters.Length,
                renderers.Length,
                filters.Select(item => item.sharedMesh).Distinct().Count(),
                materials.Length);
        }

        private static void CleanLegacySceneObjects(Transform root)
        {
            Transform[] transforms = root.GetComponentsInChildren<Transform>(true);
            foreach (Transform child in transforms.Where(item => item != root).Reverse())
            {
                if (child.name == LegacyCompiledRootName
                    || child.name.StartsWith("SBMSTYLE__", StringComparison.Ordinal))
                    UnityEngine.Object.DestroyImmediate(child.gameObject);
            }
        }

        private static void SetStringParameter(HEU_Parameters parameters, string name, string value)
        {
            if (parameters.SetStringParameterValue(name, value))
                return;
            HEU_ParameterData data = parameters.GetParameter(name);
            if (data == null || data._stringValues == null || data._stringValues.Length == 0)
                throw new InvalidOperationException("StreetBuilding string parameter is missing: " + name);
            data._stringValues[0] = value;
        }

        // HEU 21.0.440 rejects HAPI path/file parms through its public string
        // setter. Updating the serialized cache is the official project-side
        // compatibility path; RequestCook uploads the cached value.
        private static void SetSerializedStringParameter(
            HEU_Parameters parameters, string name, string value)
        {
            HEU_ParameterData data = parameters.GetParameter(name);
            if (data == null || data._stringValues == null || data._stringValues.Length == 0)
                throw new InvalidOperationException("StreetBuilding path parameter is missing: " + name);
            data._stringValues[0] = value;
        }

        private static void RequireParameter(bool success, string name)
        {
            if (!success)
                throw new InvalidOperationException("StreetBuilding parameter is missing or rejected: " + name);
        }

        private static void EnsureAssetFolder(string path)
        {
            if (string.IsNullOrEmpty(path) || AssetDatabase.IsValidFolder(path))
                return;
            string parent = Path.GetDirectoryName(path)?.Replace('\\', '/');
            EnsureAssetFolder(parent);
            AssetDatabase.CreateFolder(parent, Path.GetFileName(path));
        }

        private static string F(float value) => value.ToString("R", CultureInfo.InvariantCulture);

        private static string Hash(byte[] bytes)
        {
            using SHA256 sha = SHA256.Create();
            return string.Concat(sha.ComputeHash(bytes)
                .Select(value => value.ToString("x2", CultureInfo.InvariantCulture)));
        }

        private readonly struct DirectInstanceAudit
        {
            public readonly int InstanceRoots;
            public readonly int MeshFilters;
            public readonly int Renderers;
            public readonly int UniqueMeshes;
            public readonly int UniqueMaterials;

            public DirectInstanceAudit(
                int instanceRoots,
                int meshFilters,
                int renderers,
                int uniqueMeshes,
                int uniqueMaterials)
            {
                InstanceRoots = instanceRoots;
                MeshFilters = meshFilters;
                Renderers = renderers;
                UniqueMeshes = uniqueMeshes;
                UniqueMaterials = uniqueMaterials;
            }
        }
    }
}
#endif
