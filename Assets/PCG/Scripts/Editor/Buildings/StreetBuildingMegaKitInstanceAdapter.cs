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
    /// V6 adapter: keeps the MegaKit source read-only, creates only project-owned
    /// validation detail Prefabs, and compiles every module to unity_instance paths.
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
        public const string ValidationDetailPrefabRoot =
            "Assets/PCG/Art/StreetBuilding/NA_Brick_MixedUse_01/Prefabs/ValidationDetails";
        public const string ValidationDetailMaterialPath =
            "Assets/PCG/Materials/Buildings/na_brick_mixeduse_01/M_SB_ValidationDetail.mat";
        public const string ValidationAwningPath =
            ValidationDetailPrefabRoot + "/PF_SB_NAB01_Awning_Validation.prefab";
        public const string ValidationSignPath =
            ValidationDetailPrefabRoot + "/PF_SB_NAB01_Sign_Validation.prefab";
        public const string ValidationFireEscapePath =
            ValidationDetailPrefabRoot + "/PF_SB_NAB01_FireEscape_Validation.prefab";
        public const string ValidationParapetPath =
            ValidationDetailPrefabRoot + "/PF_SB_NAB01_Parapet_Straight.prefab";
        public const string ValidationParapetCornerPath =
            ValidationDetailPrefabRoot + "/PF_SB_NAB01_Parapet_Corner.prefab";
        public const string ValidationRoofWaterTankPath =
            ValidationDetailPrefabRoot + "/PF_SB_NAB01_Roof_WaterTank.prefab";
        public const string ValidationRoofVentPath =
            ValidationDetailPrefabRoot + "/PF_SB_NAB01_Roof_Vent.prefab";
        public const string ValidationRoofMechanicalBoxPath =
            ValidationDetailPrefabRoot + "/PF_SB_NAB01_Roof_MechanicalBox.prefab";
        public const string CapturedSourceSha256 =
            "3cb8b581b271288307dfb39335153af41598459221f986b678f420b7dc071e9d";
        private const string LegacyCompiledRootName =
            "StreetBuilding_ModuleInput_EditorOnly";

        private static readonly string[] LegacyGeneratedPaths =
        {
            "Assets/PCG/Art/StreetBuilding/NA_Brick_MixedUse_01/NativeV2",
            "Assets/PCG/Art/StreetBuilding/NA_Brick_MixedUse_01/Meshes",
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

        [MenuItem("PCG/StreetBuilding/MegaKit Instances/Build Phase 3 Details + Save", priority = 2253)]
        public static void BuildPhase3ShowcaseMenu()
        {
            try
            {
                Scene scene = EditorSceneManager.OpenScene(ScenePath, OpenSceneMode.Single);
                if (!BuildCatalog(out string build))
                    throw new InvalidOperationException(build);
                HEU_HoudiniAssetRoot main = scene.GetRootGameObjects()
                    .SelectMany(item => item.GetComponentsInChildren<HEU_HoudiniAssetRoot>(true))
                    .FirstOrDefault(item => item.name == "StreetBuilding1");
                if (main == null)
                    throw new InvalidOperationException("PCG_Building has no StreetBuilding1 HDA root.");

                ConfigureSample(main, 12, 10, 4, 29, 4, 2, .60f);
                if (!ApplyToExisting(main, out string mainApply))
                    throw new InvalidOperationException(main.name + ": " + mainApply);
                StreetBuildingAuthoring mainAuthoring = main.GetComponent<StreetBuildingAuthoring>();
                if (mainAuthoring == null || mainAuthoring.Catalog == null
                    || string.IsNullOrEmpty(mainAuthoring.LastAppliedPayloadSha256))
                    throw new InvalidOperationException("StreetBuilding1 authoring metadata is incomplete.");

                // Duplicate only after the long Catalog payload has been uploaded
                // successfully. HEU then clones matching _paramStrings and HAPI
                // state; duplicate cooks can upload only their changed numeric
                // parameters instead of retrying the Path/File payload.
                DestroyShowcaseDuplicate(scene, "StreetBuilding2_Compact");
                DestroyShowcaseDuplicate(scene, "StreetBuilding3_Accent");
                HEU_HoudiniAssetRoot compact = DuplicateRoot(main, "StreetBuilding2_Compact", -17.0f);
                HEU_HoudiniAssetRoot accent = DuplicateRoot(main, "StreetBuilding3_Accent", 19.0f);
                ConfigureSample(compact, 10, 8, 3, 11, 1, 1, .35f);
                ConfigureSample(accent, 16, 12, 5, 47, 3, 2, .85f);
                CookConfiguredDuplicate(compact, mainAuthoring.Catalog,
                    mainAuthoring.LastAppliedPayloadSha256);
                CookConfiguredDuplicate(accent, mainAuthoring.Catalog,
                    mainAuthoring.LastAppliedPayloadSha256);
                if (!EditorSceneManager.SaveScene(scene))
                    throw new InvalidOperationException("Failed to save the phase 3 showcase Scene.");
                Selection.activeGameObject = main.gameObject;
                SceneView.lastActiveSceneView?.FrameSelected();
                Debug.Log("StreetBuilding V6.1 phase 3 roof/detail showcase saved.\n"
                          + build + "\n" + mainApply, main);
            }
            catch (Exception exception)
            {
                Debug.LogError("StreetBuilding V6.1 detail showcase build failed.\n" + exception);
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
                BuildValidationDetailAssets();
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
                    new[] { SourceModels, ValidationDetailPrefabRoot },
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
                report = $"Built {recipes.Count} recipes / {recipes.Sum(item => item.Parts.Count)} FBX or Prefab parts; "
                         + $"payload SHA-256 {Hash(Encoding.UTF8.GetBytes(payloadA))}; "
                         + "MegaKit remained read-only and validation detail Prefabs were saved under project-owned paths.";
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

        private static void DestroyShowcaseDuplicate(Scene scene, string name)
        {
            foreach (GameObject root in scene.GetRootGameObjects())
            {
                if (root.name == name)
                    UnityEngine.Object.DestroyImmediate(root);
            }
        }

        private static HEU_HoudiniAssetRoot DuplicateRoot(
            HEU_HoudiniAssetRoot source, string name, float positionX)
        {
            GameObject duplicate = UnityEngine.Object.Instantiate(
                source.gameObject, source.transform.parent);
            duplicate.name = name;
            duplicate.transform.position = new Vector3(positionX, source.transform.position.y, source.transform.position.z);
            HEU_HoudiniAssetRoot result = duplicate.GetComponent<HEU_HoudiniAssetRoot>();
            if (result == null || result.HoudiniAsset == null)
                throw new InvalidOperationException("Duplicated StreetBuilding has no Houdini asset: " + name);
            return result;
        }

        private static void CookConfiguredDuplicate(
            HEU_HoudiniAssetRoot root,
            StreetBuildingInstanceModuleCatalog catalog,
            string payloadSha256)
        {
            HEU_HoudiniAsset asset = root.HoudiniAsset;
            if (!asset.RequestCook(true, false, true, true)
                || asset.LastCookResult != HEU_AssetCookResultWrapper.SUCCESS)
                throw new InvalidOperationException(root.name + " cook failed: " + asset.LastCookResult);
            AuditGeneratedInstances(root);
            StreetBuildingAuthoring authoring = root.GetComponent<StreetBuildingAuthoring>();
            if (authoring == null)
                authoring = Undo.AddComponent<StreetBuildingAuthoring>(root.gameObject);
            authoring.SetEditorCatalog(catalog);
            authoring.SetEditorAppliedPayloadSha256(payloadSha256);
            EditorUtility.SetDirty(authoring);
            root.gameObject.tag = "EditorOnly";
            EditorSceneManager.MarkSceneDirty(root.gameObject.scene);
        }

        private static void ConfigureSample(
            HEU_HoudiniAssetRoot root,
            float width,
            float depth,
            int floors,
            int seed,
            int rhythm,
            int rearMode,
            float detailDensity)
        {
            HEU_Parameters parameters = root.HoudiniAsset.Parameters;
            RequireParameter(parameters.SetFloatParameterValue("internal_width", width), "internal_width");
            RequireParameter(parameters.SetFloatParameterValue("internal_depth", depth), "internal_depth");
            RequireParameter(parameters.SetIntParameterValue("floor_count", floors), "floor_count");
            RequireParameter(parameters.SetFloatParameterValue("ground_floor_height", 4), "ground_floor_height");
            RequireParameter(parameters.SetFloatParameterValue("typical_floor_height", 3), "typical_floor_height");
            RequireParameter(parameters.SetIntParameterValue("facade_rhythm", rhythm), "facade_rhythm");
            RequireParameter(parameters.SetFloatParameterValue("detail_density", detailDensity), "detail_density");
            RequireParameter(parameters.SetIntParameterValue("rear_mode", rearMode), "rear_mode");
            RequireParameter(parameters.SetIntParameterValue("side_mode", 2), "side_mode");
            RequireParameter(parameters.SetBoolParameterValue("generate_roof", true), "generate_roof");
            RequireParameter(parameters.SetBoolParameterValue("generate_attachments", true), "generate_attachments");
            RequireParameter(parameters.SetBoolParameterValue("generate_lods", false), "generate_lods");
            RequireParameter(parameters.SetIntParameterValue("seed", seed), "seed");
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
            StreetBuildingInstancePart ValidationPart(string path) =>
                new(LoadValidationPrefab(path), Vector3.zero, Vector3.zero);
            return new List<StreetBuildingInstanceModuleRecipe>
            {
                new(StreetBuildingModuleRole.Entrance, "entrance_metal", 2, 3, 1,
                    new[] { Part("DoorFrame_Metal_Single", Vector3.zero), Part("Door_2", new Vector3(-.5f, 0, -.12f)) }),
                new(StreetBuildingModuleRole.Entrance, "entrance_trim", 2, 3, .6f,
                    new[] { Part("DoorFrame_Trim", Vector3.zero), Part("Door_1", new Vector3(-.5f, 0, 0)) }),
                new(StreetBuildingModuleRole.GroundShop, "shop_metal", 2, 3, 1,
                    new[] { Part("Metal_FirstFloor_Window", Vector3.zero) }),
                new(StreetBuildingModuleRole.GroundShop, "shop_trim", 2, 3, 1,
                    new[] { Part("Trim_FirstFloor_Window_001", Vector3.zero) }),
                new(StreetBuildingModuleRole.GroundWall, "brick_ground", 2, 4, 1,
                    new[] { Part("Brick_Plain_4", Vector3.zero) }),
                new(StreetBuildingModuleRole.Cornice, "brick_center", 2, 1, 1,
                    new[] { Part("Cornice_Brick_Center", Vector3.zero) }),
                new(StreetBuildingModuleRole.Cornice, "metal_center", 2, 1, .3f,
                    new[] { Part("Cornice_Metal_Center", Vector3.zero) }),
                new(StreetBuildingModuleRole.Cornice, "trim_center", 2, 1, .3f,
                    new[] { Part("Cornice_Trim_Center", Vector3.zero) }),
                new(StreetBuildingModuleRole.MiddleWindow, "trim", 2, 3, 1,
                    new[] { Part("Brick_Window_Trim", Vector3.zero) }),
                new(StreetBuildingModuleRole.MiddleWindow, "trim_single", 2, 3, 1,
                    new[] { Part("Brick_Window_Trim_Single", Vector3.zero) }),
                new(StreetBuildingModuleRole.MiddleWindow, "square_single", 2, 3, 1,
                    new[] { Part("Brick_Window_Square_Single", Vector3.zero) }),
                new(StreetBuildingModuleRole.MiddleWindow, "curved_double", 4, 3, .35f,
                    new[] { Part("Brick_Window_CurvedDouble", Vector3.zero) }),
                new(StreetBuildingModuleRole.MiddleBlank, "brick_plain", 2, 3, 1,
                    new[] { Part("Brick_Plain_3", Vector3.zero) }),
                new(StreetBuildingModuleRole.MiddleBlank, "brick_clean", 2, 3, .5f,
                    new[] { Part("Brick_Plain_3_noWear", Vector3.zero) }),
                new(StreetBuildingModuleRole.MiddleBlank, "metal_plain", 2, 3, .35f,
                    new[] { Part("Metal_Plain_3", Vector3.zero) }),
                new(StreetBuildingModuleRole.MiddleBlank, "trim_plain", 2, 3, .35f,
                    new[] { Part("Trim_Plain_3", Vector3.zero) }),
                new(StreetBuildingModuleRole.SideWall, "brick_ground", 2, 4, 1,
                    new[] { Part("Brick_Plain_4", Vector3.zero) }),
                new(StreetBuildingModuleRole.SideWall, "brick_upper", 2, 3, 1,
                    new[] { Part("Brick_Plain_3", Vector3.zero) }),
                new(StreetBuildingModuleRole.SideWall, "brick_upper_clean", 2, 3, .5f,
                    new[] { Part("Brick_Plain_3_noWear", Vector3.zero) }),
                new(StreetBuildingModuleRole.RearWall, "brick_ground", 2, 4, 1,
                    new[] { Part("Brick_Plain_4", Vector3.zero) }),
                new(StreetBuildingModuleRole.RearWall, "brick_upper", 2, 3, 1,
                    new[] { Part("Brick_Plain_3", Vector3.zero) }),
                new(StreetBuildingModuleRole.RearWall, "brick_upper_clean", 2, 3, .5f,
                    new[] { Part("Brick_Plain_3_noWear", Vector3.zero) }),
                new(StreetBuildingModuleRole.FacadeColumn, "trim_ground", 2, 3, 1,
                    new[] { Part("Trim_Column_Center", Vector3.zero) }),
                new(StreetBuildingModuleRole.FacadeColumn, "brick_upper", 2, 3, 1,
                    new[] { Part("Brick_Column_Small", Vector3.zero) }),
                new(StreetBuildingModuleRole.RoofSurface, "roof_2x2", 2, 2, 1,
                    new[] { Part("Roof_2x2", new Vector3(0, .2f, 0)) }),
                new(StreetBuildingModuleRole.Parapet, "straight_2m", 2, .6f, 1,
                    new[] { ValidationPart(ValidationParapetPath) }),
                new(StreetBuildingModuleRole.ParapetCorner, "corner_90", 2, .6f, 1,
                    new[] { ValidationPart(ValidationParapetCornerPath) }),
                new(StreetBuildingModuleRole.Awning, "validation_canopy", 2, 1, 1,
                    new[] { ValidationPart(ValidationAwningPath) }),
                new(StreetBuildingModuleRole.Sign, "validation_board", 2, 1, 1,
                    new[] { ValidationPart(ValidationSignPath) }),
                new(StreetBuildingModuleRole.FireEscape, "validation_two_floor", 4, 6, 1,
                    new[] { ValidationPart(ValidationFireEscapePath) }),
                new(StreetBuildingModuleRole.ACUnit, "wall_unit", 2, 1, 1,
                    new[] { Part("Prop_ACUnit", Vector3.zero) }),
                new(StreetBuildingModuleRole.RoofProp, "water_tank", 2, 2, 1,
                    new[] { ValidationPart(ValidationRoofWaterTankPath) }),
                new(StreetBuildingModuleRole.RoofProp, "roof_vent", 2, 2, .7f,
                    new[] { ValidationPart(ValidationRoofVentPath) }),
                new(StreetBuildingModuleRole.RoofProp, "mechanical_box", 2, 2, .5f,
                    new[] { ValidationPart(ValidationRoofMechanicalBoxPath) }),
            };
        }

        private static void BuildValidationDetailAssets()
        {
            EnsureAssetFolder(ValidationDetailPrefabRoot);
            EnsureAssetFolder(Path.GetDirectoryName(ValidationDetailMaterialPath)?.Replace('\\', '/'));
            Material material = AssetDatabase.LoadAssetAtPath<Material>(ValidationDetailMaterialPath);
            if (material == null)
            {
                Shader shader = Shader.Find("Universal Render Pipeline/Lit");
                if (shader == null)
                    throw new InvalidOperationException("URP/Lit shader is unavailable.");
                material = new Material(shader) { name = "M_SB_ValidationDetail", enableInstancing = true };
                material.SetColor("_BaseColor", new Color(.16f, .34f, .48f, 1));
                AssetDatabase.CreateAsset(material, ValidationDetailMaterialPath);
            }
            else
            {
                material.enableInstancing = true;
                material.SetColor("_BaseColor", new Color(.16f, .34f, .48f, 1));
                EditorUtility.SetDirty(material);
            }

            SaveValidationPrefab(ValidationAwningPath, material, root =>
            {
                AddBox(root, "Canopy", new Vector3(0, .08f, .42f), new Vector3(1.8f, .16f, .85f), material);
                AddBox(root, "LeftBracket", new Vector3(-.72f, -.18f, .18f), new Vector3(.08f, .55f, .08f), material);
                AddBox(root, "RightBracket", new Vector3(.72f, -.18f, .18f), new Vector3(.08f, .55f, .08f), material);
            });
            SaveValidationPrefab(ValidationSignPath, material, root =>
            {
                AddBox(root, "Board", new Vector3(0, .35f, .12f), new Vector3(1.4f, .65f, .10f), material);
                AddBox(root, "LeftMount", new Vector3(-.55f, .35f, -.04f), new Vector3(.07f, .07f, .32f), material);
                AddBox(root, "RightMount", new Vector3(.55f, .35f, -.04f), new Vector3(.07f, .07f, .32f), material);
            });
            SaveValidationPrefab(ValidationFireEscapePath, material, root =>
            {
                AddBox(root, "LowerPlatform", new Vector3(0, 1.6f, .32f), new Vector3(3.2f, .12f, .75f), material);
                AddBox(root, "UpperPlatform", new Vector3(0, 4.6f, .32f), new Vector3(3.2f, .12f, .75f), material);
                AddBox(root, "LeftRail", new Vector3(-1.48f, 3.1f, .52f), new Vector3(.08f, 3.1f, .08f), material);
                AddBox(root, "RightRail", new Vector3(1.48f, 3.1f, .52f), new Vector3(.08f, 3.1f, .08f), material);
                AddBox(root, "Diagonal", new Vector3(0, 3.1f, .52f), new Vector3(.10f, 3.8f, .10f), material, new Vector3(0, 0, -27));
            });
            SaveValidationPrefab(ValidationParapetPath, material, root =>
            {
                AddBox(root, "Wall", new Vector3(0, .275f, 0), new Vector3(2.0f, .55f, .18f), material);
                AddBox(root, "Coping", new Vector3(0, .575f, .02f), new Vector3(2.0f, .05f, .30f), material);
            });
            SaveValidationPrefab(ValidationParapetCornerPath, material, root =>
            {
                AddBox(root, "WallX", new Vector3(1.0f, .275f, 0), new Vector3(2.0f, .55f, .18f), material);
                AddBox(root, "WallZ", new Vector3(0, .275f, -1.0f), new Vector3(.18f, .55f, 2.0f), material);
                AddBox(root, "CopingX", new Vector3(1.0f, .575f, .02f), new Vector3(2.0f, .05f, .30f), material);
                AddBox(root, "CopingZ", new Vector3(-.02f, .575f, -1.0f), new Vector3(.30f, .05f, 2.0f), material);
            });
            SaveValidationPrefab(ValidationRoofWaterTankPath, material, root =>
            {
                AddBox(root, "Tank", new Vector3(0, .85f, 0), new Vector3(1.2f, 1.4f, 1.2f), material);
                AddBox(root, "Base", new Vector3(0, .10f, 0), new Vector3(1.5f, .20f, 1.5f), material);
            });
            SaveValidationPrefab(ValidationRoofVentPath, material, root =>
            {
                AddBox(root, "Duct", new Vector3(0, .35f, 0), new Vector3(.45f, .70f, .45f), material);
                AddBox(root, "Cap", new Vector3(0, .76f, 0), new Vector3(.70f, .12f, .70f), material);
            });
            SaveValidationPrefab(ValidationRoofMechanicalBoxPath, material, root =>
            {
                AddBox(root, "Plinth", new Vector3(0, .10f, 0), new Vector3(1.35f, .20f, 1.15f), material);
                AddBox(root, "Housing", new Vector3(0, .55f, 0), new Vector3(1.15f, .90f, .95f), material);
            });
            AssetDatabase.SaveAssets();
            AssetDatabase.Refresh(ImportAssetOptions.ForceSynchronousImport);
        }

        private static void SaveValidationPrefab(
            string path, Material material, Action<GameObject> populate)
        {
            var root = new GameObject(Path.GetFileNameWithoutExtension(path));
            try
            {
                populate(root);
                if (PrefabUtility.SaveAsPrefabAsset(root, path) == null)
                    throw new InvalidOperationException("Failed to save validation detail Prefab: " + path);
            }
            finally
            {
                UnityEngine.Object.DestroyImmediate(root);
            }
        }

        private static void AddBox(
            GameObject parent, string name, Vector3 position, Vector3 scale,
            Material material, Vector3? rotation = null)
        {
            GameObject child = GameObject.CreatePrimitive(PrimitiveType.Cube);
            child.name = name;
            child.transform.SetParent(parent.transform, false);
            child.transform.localPosition = position;
            child.transform.localRotation = Quaternion.Euler(rotation ?? Vector3.zero);
            child.transform.localScale = scale;
            UnityEngine.Object.DestroyImmediate(child.GetComponent<Collider>());
            child.GetComponent<MeshRenderer>().sharedMaterial = material;
        }

        private static GameObject LoadValidationPrefab(string path)
        {
            GameObject asset = AssetDatabase.LoadAssetAtPath<GameObject>(path);
            if (asset == null)
                throw new InvalidOperationException("Validation detail Prefab is missing: " + path);
            return asset;
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
            if (catalog.Modules.Count != 34 || catalog.Modules.Sum(item => item.Parts.Count) != 36)
                throw new InvalidOperationException("V6.1 catalog must contain 34 recipes / 36 source parts.");
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
                bool originalFbx = path.StartsWith(SourceModels + "/", StringComparison.Ordinal)
                                   && path.EndsWith(".fbx", StringComparison.OrdinalIgnoreCase);
                bool validationPrimitive = filter.sharedMesh.name == "Cube";
                if (!originalFbx && !validationPrimitive)
                    throw new InvalidOperationException("Cook produced a derived/non-MegaKit mesh: " + path);
            }
            Material[] materials = renderers.SelectMany(item => item.sharedMaterials)
                .Where(item => item != null).Distinct().ToArray();
            foreach (Material material in materials)
            {
                string path = AssetDatabase.GetAssetPath(material);
                if (!path.StartsWith(SourceRoot + "/", StringComparison.Ordinal)
                    && !string.Equals(path, ValidationDetailMaterialPath, StringComparison.Ordinal))
                    throw new InvalidOperationException("Cook produced an unauthorized material: " + path);
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
