#if UNITY_EDITOR
using System;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using System.Text;
using HoudiniEngineUnity;
using UnityEditor;
using UnityEditor.SceneManagement;
using UnityEngine;
using UnityEngine.Rendering;

namespace PCG.CityRoad.Editor
{
    /// <summary>
    /// CityRoad authoring contract:
    /// HDA is an EditorOnly source; only the updated Bake prefab is rendered.
    /// The official Houdini Engine bake API is used without modifying the plugin.
    /// </summary>
    internal static class CityRoadBakeWorkflow
    {
        private const string BakeRoot = "Assets/PCG/Generated/Road/CityRoad";
        private const string OverridesName = "CityRoad_Overrides";
        private const string BakeSuffix = "_Bake";
        private const string AsphaltMaterialPath =
            "Assets/PCG/Materials/M_PCG_CityRoad_Asphalt.mat";
        private const string SidewalkMaterialPath =
            "Assets/PCG/Materials/M_PCG_CityRoad_Sidewalk.mat";
        private const string CurbMaterialPath =
            "Assets/PCG/Materials/M_PCG_CityRoad_Curb.mat";
        private const string MarkingMaterialPath =
            "Assets/PCG/Materials/M_PCG_CityRoad_Marking.mat";
        private const string AsphaltShaderName = "PCG/CityRoad/Asphalt";
        private const string SimpleSurfaceShaderName = "PCG/CityRoad/SimpleSurface";
        private const string MarkingShaderName = "PCG/CityRoad/Marking";
        private static readonly string[] s_StreetFurnitureOutputs =
        {
            "OUT_STREET_LAMPS",
            "OUT_STREET_TREES",
            "OUT_STREET_TREE_PITS",
        };
        [MenuItem("PCG/CityRoad/Cook + Validate + Update Bake Selected", priority = 2110)]
        private static void CookValidateAndBakeSelected()
        {
            List<HEU_HoudiniAssetRoot> targets = GetTargets();
            if (targets.Count == 0)
            {
                Debug.LogError(
                    "CityRoad Bake: select a CityRoad HDA, or keep exactly one CityRoad HDA loaded.");
                return;
            }

            int succeeded = 0;
            foreach (HEU_HoudiniAssetRoot target in targets)
            {
                if (CookValidateAndBake(target))
                    succeeded++;
            }

            Debug.LogFormat(
                "CityRoad Bake: completed {0}/{1} asset(s). Save the dirty scene after reviewing the Bake instance.",
                succeeded,
                targets.Count);
        }

        [MenuItem("PCG/CityRoad/Cook + Validate + Update Bake Selected", true)]
        private static bool ValidateCookValidateAndBakeSelected()
        {
            return GetTargets().Count > 0;
        }

        [MenuItem("PCG/CityRoad/Validate Loaded Bake Contract", priority = 2111)]
        private static void ValidateLoadedBakeContract()
        {
            List<HEU_HoudiniAssetRoot> targets = GetLoadedCityRoadRoots();
            if (targets.Count == 0)
            {
                Debug.LogWarning("CityRoad Bake: no loaded CityRoad HDA was found.");
                return;
            }

            foreach (HEU_HoudiniAssetRoot target in targets)
            {
                string prefabPath = GetPrefabPath(target);
                GameObject prefab = AssetDatabase.LoadAssetAtPath<GameObject>(prefabPath);
                if (prefab == null)
                {
                    Debug.LogErrorFormat(target, "CityRoad Bake: missing prefab {0}.", prefabPath);
                    continue;
                }

                if (ValidateGeneratedHierarchy(prefab, out string report))
                    Debug.LogFormat(target, "CityRoad Bake contract passed: {0}\n{1}", prefabPath, report);
                else
                    Debug.LogErrorFormat(target, "CityRoad Bake contract failed: {0}\n{1}", prefabPath, report);
            }
        }

        internal static bool CookValidateAndBake(HEU_HoudiniAssetRoot root)
        {
            if (!CityRoadSafeRebuild.IsCityRoad(root))
                return false;

            if (!EnsureProjectMaterialContract())
                return false;
            var sceneRootsBeforeCook = new HashSet<GameObject>(
                root.gameObject.scene.GetRootGameObjects());
            HashSet<string> palettePaths = CaptureTreePalettePaths(root.HoudiniAsset);

            if (!CityRoadSafeRebuild.Rebuild(root))
            {
                Debug.LogError("CityRoad Bake: cook/reload failed; Bake was not changed.", root);
                return false;
            }
            CleanupNewOrphanedTreePrefabRoots(
                root,
                sceneRootsBeforeCook,
                palettePaths);

            // Existing scene instances do not receive newly-added HDA
            // parameters until Reload/Rebuild. Validate configuration after
            // that migration, but before touching the existing Bake prefab.
            if (!ValidateStreetFurnitureConfiguration(root.HoudiniAsset, out string furnitureReport))
            {
                Debug.LogErrorFormat(
                    root,
                    "CityRoad Bake: street-furniture configuration is invalid; Bake was not changed.\n{0}",
                    furnitureReport);
                return false;
            }

            CityRoadLivePreviewController.EnterLivePreview(root);
            ApplyCollisionOutputContract(root.gameObject);
            ApplyShadowContract(root.gameObject);
            if (!ValidateGeneratedHierarchy(root.gameObject, out string liveReport))
            {
                Debug.LogErrorFormat(
                    root,
                    "CityRoad Bake: live output contract failed; Bake was not changed.\n{0}",
                    liveReport);
                return false;
            }

            string folder = GetBakeFolder(root);
            string prefabPath = GetPrefabPath(root);
            EnsureAssetFolder(folder);

            HEU_HoudiniAsset asset = root.HoudiniAsset;
            GameObject prefab = AssetDatabase.LoadAssetAtPath<GameObject>(prefabPath);
            if (prefab == null)
            {
                prefab = asset.BakeToNewPrefab(folder);
                if (prefab == null)
                {
                    Debug.LogErrorFormat(root, "CityRoad Bake: failed to create prefab in {0}.", folder);
                    return false;
                }

                string createdPath = AssetDatabase.GetAssetPath(prefab);
                if (!string.Equals(createdPath, prefabPath, StringComparison.OrdinalIgnoreCase))
                {
                    string moveError = AssetDatabase.MoveAsset(createdPath, prefabPath);
                    if (!string.IsNullOrEmpty(moveError))
                    {
                        Debug.LogErrorFormat(
                            root,
                            "CityRoad Bake: prefab was created at {0}, but could not be moved to {1}: {2}",
                            createdPath,
                            prefabPath,
                            moveError);
                        return false;
                    }

                    prefab = AssetDatabase.LoadAssetAtPath<GameObject>(prefabPath);
                }
            }
            else if (!asset.BakeToExistingPrefab(prefab))
            {
                Debug.LogErrorFormat(root, "CityRoad Bake: failed to update {0}.", prefabPath);
                return false;
            }

            prefab = AssetDatabase.LoadAssetAtPath<GameObject>(prefabPath);
            if (prefab != null)
            {
                ApplyShadowContract(prefab);
                PrefabUtility.SavePrefabAsset(prefab);
            }
            AssetDatabase.SaveAssets();
            prefab = AssetDatabase.LoadAssetAtPath<GameObject>(prefabPath);
            string bakeReport = "Prefab asset is missing after Bake.";
            if (prefab == null
                || !ValidateGeneratedHierarchy(prefab, out bakeReport))
            {
                Debug.LogErrorFormat(
                    root,
                    "CityRoad Bake: updated prefab failed post-bake validation.\n{0}",
                    bakeReport);
                return false;
            }

            EnsureBakeInstanceAndOverrides(root, prefab);
            MakeAuthoringSourceEditorOnly(root);
            CityRoadLivePreviewController.MarkBaked(root);

            Debug.LogFormat(
                root,
                "CityRoad Bake updated: {0}\nLive: {1}\nBake: {2}",
                prefabPath,
                liveReport,
                bakeReport);
            return true;
        }

        private static List<HEU_HoudiniAssetRoot> GetTargets()
        {
            var selected = new HashSet<HEU_HoudiniAssetRoot>();
            foreach (GameObject gameObject in Selection.gameObjects)
            {
                if (gameObject == null)
                    continue;

                HEU_HoudiniAssetRoot root = gameObject.GetComponentInParent<HEU_HoudiniAssetRoot>();
                if (root == null)
                    root = gameObject.GetComponentInChildren<HEU_HoudiniAssetRoot>(true);
                if (CityRoadSafeRebuild.IsCityRoad(root))
                    selected.Add(root);
            }

            if (selected.Count > 0)
                return selected.ToList();

            List<HEU_HoudiniAssetRoot> loaded = GetLoadedCityRoadRoots();
            return loaded.Count == 1 ? loaded : new List<HEU_HoudiniAssetRoot>();
        }

        private static List<HEU_HoudiniAssetRoot> GetLoadedCityRoadRoots()
        {
            return Resources.FindObjectsOfTypeAll<HEU_HoudiniAssetRoot>()
                .Where(root =>
                    root != null
                    && !EditorUtility.IsPersistent(root)
                    && root.gameObject.scene.IsValid()
                    && root.gameObject.scene.isLoaded
                    && CityRoadSafeRebuild.IsCityRoad(root))
                .OrderBy(root => root.gameObject.scene.path, StringComparer.Ordinal)
                .ThenBy(root => root.name, StringComparer.Ordinal)
                .ToList();
        }

        private static HashSet<string> CaptureTreePalettePaths(
            HEU_HoudiniAsset asset)
        {
            var result = new HashSet<string>(StringComparer.OrdinalIgnoreCase);
            if (asset == null || asset.Parameters == null)
                return result;
            for (int index = 1; index <= 3; index++)
            {
                string path;
                if (asset.Parameters.GetStringParameterValue(
                        "tree_prefab" + index,
                        out path)
                    && !string.IsNullOrEmpty(path))
                    result.Add(path.Replace('\\', '/'));
            }
            return result;
        }

        private static void CleanupNewOrphanedTreePrefabRoots(
            HEU_HoudiniAssetRoot source,
            HashSet<GameObject> rootsBeforeCook,
            HashSet<string> palettePaths)
        {
            if (source == null || rootsBeforeCook == null || palettePaths == null)
                return;
            foreach (GameObject candidate in source.gameObject.scene.GetRootGameObjects())
            {
                if (candidate == null
                    || rootsBeforeCook.Contains(candidate)
                    || candidate == source.gameObject)
                    continue;
                string path = PrefabUtility.GetPrefabAssetPathOfNearestInstanceRoot(candidate)
                    .Replace('\\', '/');
                if (palettePaths.Contains(path))
                    UnityEngine.Object.DestroyImmediate(candidate);
            }
        }

        private static Transform FindNamedOutput(GameObject root, string outputName)
        {
            return root.GetComponentsInChildren<Transform>(true)
                .FirstOrDefault(transform => IsUnderNamedOutput(transform, outputName));
        }

        private static bool ValidateGeneratedHierarchy(GameObject root, out string report)
        {
            var issues = new List<string>();
            Renderer[] renderers = root.GetComponentsInChildren<Renderer>(true);
            MeshFilter[] filters = root.GetComponentsInChildren<MeshFilter>(true);
            MeshCollider[] colliders = root.GetComponentsInChildren<MeshCollider>(true);
            Renderer[] activeRenderers = renderers
                .Where(renderer =>
                    renderer != null
                    && renderer.enabled
                    && IsEffectivelyActive(renderer.gameObject, root))
                .ToArray();

            if (activeRenderers.Length == 0)
                issues.Add("No enabled render output was found.");

            ValidateRendererMaterials(activeRenderers, issues);
            ValidateRendererShadowContract(activeRenderers, issues);
            ValidateStreetFurnitureHierarchy(root, activeRenderers, issues);

            Transform chunkTransform = root.GetComponentsInChildren<Transform>(true)
                .FirstOrDefault(transform =>
                    transform.name.IndexOf("Chunk", StringComparison.OrdinalIgnoreCase) >= 0);
            if (chunkTransform != null)
                issues.Add("Spatial chunk output remains: " + GetHierarchyPath(chunkTransform));

            int collisionRendererCount = activeRenderers.Count(renderer =>
                IsUnderNamedOutput(renderer.transform, "OUT_ROAD_COLLISION"));
            if (collisionRendererCount > 0)
                issues.Add("OUT_ROAD_COLLISION still contains enabled Renderer(s): " + collisionRendererCount);

            MeshCollider[] roadColliders = colliders
                .Where(collider => IsUnderNamedOutput(collider.transform, "OUT_ROAD_COLLISION"))
                .ToArray();
            if (roadColliders.Length == 0)
                issues.Add("OUT_ROAD_COLLISION contains no MeshCollider.");

            foreach (MeshCollider collider in roadColliders)
            {
                if (collider.sharedMesh == null)
                    issues.Add("MeshCollider has no shared mesh: " + GetHierarchyPath(collider.transform));
                if (collider.convex)
                    issues.Add("Road MeshCollider must remain non-convex: " + GetHierarchyPath(collider.transform));
                if (collider.isTrigger)
                    issues.Add("Road MeshCollider must not be a trigger: " + GetHierarchyPath(collider.transform));
            }

            foreach (MeshFilter filter in filters)
            {
                if (filter.sharedMesh == null || !IsEffectivelyActive(filter.gameObject, root))
                    continue;
                Renderer renderer = filter.GetComponent<Renderer>();
                if (renderer == null || !renderer.enabled)
                    continue;

                if (IsUnderAnyNamedOutput(
                        filter.transform,
                        "OUT_ROAD_SURFACE",
                        "OUT_SIDEWALK_CURB",
                        "OUT_ROAD_MARKINGS")
                    && !HasTopologyPieceName(filter.transform))
                {
                    issues.Add("Render piece is not named as Corridor/Junction: " + GetHierarchyPath(filter.transform));
                    break;
                }
            }

            var overlapKeys = new Dictionary<string, Transform>(StringComparer.Ordinal);
            foreach (MeshFilter filter in filters)
            {
                MeshRenderer renderer = filter.GetComponent<MeshRenderer>();
                Mesh mesh = filter.sharedMesh;
                if (mesh == null
                    || renderer == null
                    || !renderer.enabled
                    || !IsEffectivelyActive(renderer.gameObject, root))
                    continue;

                string key = BuildOverlapKey(renderer, mesh);
                if (overlapKeys.TryGetValue(key, out Transform first))
                {
                    issues.Add(
                        "Overlapping render meshes detected: "
                        + GetHierarchyPath(first)
                        + " <-> "
                        + GetHierarchyPath(filter.transform));
                    break;
                }
                overlapKeys.Add(key, filter.transform);
            }

            report = string.Format(
                "renderers={0} enabled={1}, meshFilters={2}, roadColliders={3}, issues={4}",
                renderers.Length,
                activeRenderers.Length,
                filters.Length,
                roadColliders.Length,
                issues.Count);
            if (issues.Count > 0)
                report += "\n- " + string.Join("\n- ", issues);
            return issues.Count == 0;
        }

        internal static bool ValidateStreetFurnitureConfiguration(
            HEU_HoudiniAsset asset,
            out string report)
        {
            var issues = new List<string>();
            if (asset == null || asset.Parameters == null)
            {
                report = "HDA parameters are unavailable.";
                return false;
            }

            ValidateConfiguredPrefab(asset, "lamp_prefab", "lamp", issues);
            ValidateConfiguredPrefab(asset, "tree_pit_prefab", "tree pit", issues);

            HEU_ParameterData variants = asset.Parameters.GetParameter("tree_variants");
            int variantCount = variants != null && variants.IsMultiParam()
                ? variants._parmInfo.instanceCount
                : 0;
            if (variantCount <= 0)
            {
                issues.Add("tree_variants must contain at least one entry.");
            }
            else
            {
                for (int index = 1; index <= variantCount; index++)
                {
                    ValidateConfiguredPrefab(
                        asset,
                        "tree_prefab" + index,
                        "tree variant " + index,
                        issues);
                    float weight;
                    if (!asset.Parameters.GetFloatParameterValue(
                            "tree_weight" + index,
                            out weight)
                        || weight <= 0f)
                    {
                        issues.Add("tree_weight" + index + " must be positive.");
                    }
                }
            }

            report = issues.Count == 0
                ? "Street-furniture prefab configuration passed."
                : "- " + string.Join("\n- ", issues);
            return issues.Count == 0;
        }

        private static void ValidateConfiguredPrefab(
            HEU_HoudiniAsset asset,
            string parameterName,
            string label,
            List<string> issues)
        {
            string path;
            if (!asset.Parameters.GetStringParameterValue(parameterName, out path))
            {
                issues.Add("Missing HDA parameter " + parameterName + ".");
                return;
            }

            path = (path ?? string.Empty).Replace('\\', '/');
            if (!path.StartsWith("Assets/", StringComparison.Ordinal)
                || !path.EndsWith(".prefab", StringComparison.OrdinalIgnoreCase))
            {
                issues.Add(label + " path must be an Assets/*.prefab path: " + path);
                return;
            }

            GameObject prefab = AssetDatabase.LoadAssetAtPath<GameObject>(path);
            if (prefab == null)
            {
                issues.Add(label + " prefab does not exist: " + path);
                return;
            }

            if (!ValidateStreetFurniturePrefab(prefab, out string prefabIssue))
                issues.Add(label + " prefab is unsupported: " + path + " (" + prefabIssue + ")");
        }

        internal static bool ValidateStreetFurniturePrefab(GameObject prefab, out string issue)
        {
            if (prefab == null)
            {
                issue = "Prefab is null.";
                return false;
            }

            string path = AssetDatabase.GetAssetPath(prefab).Replace('\\', '/');
            if (!path.StartsWith("Assets/", StringComparison.Ordinal)
                || !path.EndsWith(".prefab", StringComparison.OrdinalIgnoreCase))
            {
                issue = "Asset is not an Assets/*.prefab.";
                return false;
            }

            MeshRenderer[] renderers = prefab.GetComponentsInChildren<MeshRenderer>(true);
            MeshFilter[] filters = prefab.GetComponentsInChildren<MeshFilter>(true);
            if (renderers.Length != 1 || filters.Length != 1)
            {
                issue = string.Format(
                    "Expected exactly one MeshRenderer + MeshFilter, found {0} + {1}.",
                    renderers.Length,
                    filters.Length);
                return false;
            }
            if (renderers[0].gameObject != filters[0].gameObject || filters[0].sharedMesh == null)
            {
                issue = "MeshRenderer/MeshFilter must share one GameObject and a valid mesh.";
                return false;
            }
            if (prefab.GetComponentsInChildren<Collider>(true).Length > 0)
            {
                issue = "Collider is not supported.";
                return false;
            }
            if (prefab.GetComponentsInChildren<LODGroup>(true).Length > 0
                || prefab.GetComponentsInChildren<Animator>(true).Length > 0
                || prefab.GetComponentsInChildren<Animation>(true).Length > 0
                || prefab.GetComponentsInChildren<ParticleSystem>(true).Length > 0
                || prefab.GetComponentsInChildren<MonoBehaviour>(true).Length > 0)
            {
                issue = "LOD, animation, particles, and runtime scripts are not supported.";
                return false;
            }

            issue = "OK";
            return true;
        }

        private static void ValidateStreetFurnitureHierarchy(
            GameObject root,
            Renderer[] activeRenderers,
            List<string> issues)
        {
            foreach (string output in s_StreetFurnitureOutputs)
            {
                Transform outputRoot = root.GetComponentsInChildren<Transform>(true)
                    .FirstOrDefault(transform => transform.name.IndexOf(
                        output,
                        StringComparison.OrdinalIgnoreCase) >= 0);
                if (outputRoot == null)
                {
                    issues.Add("Missing street-furniture output: " + output);
                    continue;
                }

                Renderer[] instances = activeRenderers
                    .Where(renderer => IsUnderNamedOutput(renderer.transform, output))
                    .ToArray();
                if (instances.Length == 0)
                {
                    issues.Add("Street-furniture output contains no enabled prefab instances: " + output);
                    continue;
                }
                if (outputRoot.GetComponentsInChildren<Collider>(true).Length > 0)
                    issues.Add(output + " contains Collider components.");
                if (outputRoot.GetComponentsInChildren<LODGroup>(true).Length > 0
                    || outputRoot.GetComponentsInChildren<Animator>(true).Length > 0
                    || outputRoot.GetComponentsInChildren<ParticleSystem>(true).Length > 0)
                    issues.Add(output + " contains unsupported runtime components.");
            }
        }

        private static void ValidateRendererMaterials(
            Renderer[] renderers,
            List<string> issues)
        {
            bool hasAsphalt = false;
            bool hasSidewalk = false;
            bool hasCurb = false;
            bool hasMarking = false;

            foreach (Renderer renderer in renderers)
            {
                string expectedOutput = null;
                if (IsUnderNamedOutput(renderer.transform, "OUT_ROAD_SURFACE"))
                    expectedOutput = "road";
                else if (IsUnderNamedOutput(renderer.transform, "OUT_SIDEWALK_CURB"))
                    expectedOutput = "side";
                else if (IsUnderNamedOutput(renderer.transform, "OUT_ROAD_MARKINGS"))
                    expectedOutput = "marking";
                else
                    continue;

                foreach (Material material in renderer.sharedMaterials)
                {
                    string path = material != null
                        ? AssetDatabase.GetAssetPath(material).Replace('\\', '/')
                        : string.Empty;
                    if (material == null
                        || material.name.StartsWith(
                            "HEU_DEFAULT_MATERIAL_",
                            StringComparison.OrdinalIgnoreCase)
                        || string.IsNullOrEmpty(path))
                    {
                        issues.Add(
                            "Default or missing material remains on: "
                            + GetHierarchyPath(renderer.transform));
                        return;
                    }

                    if (expectedOutput == "road")
                    {
                        if (!string.Equals(
                                path,
                                AsphaltMaterialPath,
                                StringComparison.OrdinalIgnoreCase))
                        {
                            issues.Add("Unexpected road material: " + path);
                            return;
                        }
                        ValidateMaterialShaderAndInstancing(
                            material,
                            AsphaltShaderName,
                            issues);
                        hasAsphalt = true;
                    }
                    else if (expectedOutput == "side")
                    {
                        if (string.Equals(
                                path,
                                SidewalkMaterialPath,
                                StringComparison.OrdinalIgnoreCase))
                        {
                            ValidateMaterialShaderAndInstancing(
                                material,
                                SimpleSurfaceShaderName,
                                issues);
                            hasSidewalk = true;
                        }
                        else if (string.Equals(
                                path,
                                CurbMaterialPath,
                                StringComparison.OrdinalIgnoreCase))
                        {
                            ValidateMaterialShaderAndInstancing(
                                material,
                                SimpleSurfaceShaderName,
                                issues);
                            hasCurb = true;
                        }
                        else
                        {
                            issues.Add("Unexpected sidewalk/curb material: " + path);
                            return;
                        }
                    }
                    else
                    {
                        if (!string.Equals(
                                path,
                                MarkingMaterialPath,
                                StringComparison.OrdinalIgnoreCase))
                        {
                            issues.Add("Unexpected marking material: " + path);
                            return;
                        }
                        ValidateMaterialShaderAndInstancing(
                            material,
                            MarkingShaderName,
                            issues);
                        hasMarking = true;
                    }
                }
            }

            if (!hasAsphalt)
                issues.Add("Asphalt material was not found on Road Surface.");
            if (!hasSidewalk)
                issues.Add("Sidewalk material was not found on Sidewalk/Curb output.");
            if (!hasCurb)
                issues.Add("Curb material was not found on Sidewalk/Curb output.");
            if (!hasMarking)
                issues.Add("Marking material was not found on Road Markings output.");
        }

        private static void ValidateMaterialShaderAndInstancing(
            Material material,
            string expectedShader,
            List<string> issues)
        {
            string actualShader = material != null && material.shader != null
                ? material.shader.name
                : "<missing>";
            if (!string.Equals(actualShader, expectedShader, StringComparison.Ordinal))
            {
                issues.Add(
                    string.Format(
                        "Unexpected shader on {0}: expected {1}, actual {2}.",
                        material != null ? material.name : "<missing>",
                        expectedShader,
                        actualShader));
            }

            if (material != null && !material.enableInstancing)
                issues.Add("GPU Instancing is disabled on material: " + material.name);
        }

        internal static bool EnsureProjectMaterialContract()
        {
            var contracts = new[]
            {
                new { Path = AsphaltMaterialPath, Shader = AsphaltShaderName },
                new { Path = SidewalkMaterialPath, Shader = SimpleSurfaceShaderName },
                new { Path = CurbMaterialPath, Shader = SimpleSurfaceShaderName },
                new { Path = MarkingMaterialPath, Shader = MarkingShaderName }
            };

            bool valid = true;
            foreach (var contract in contracts)
            {
                Material material = AssetDatabase.LoadAssetAtPath<Material>(contract.Path);
                Shader shader = Shader.Find(contract.Shader);
                if (material == null || shader == null)
                {
                    Debug.LogErrorFormat(
                        "CityRoad material contract missing asset/shader: {0} -> {1}.",
                        contract.Path,
                        contract.Shader);
                    valid = false;
                    continue;
                }

                if (material.shader != shader)
                    material.shader = shader;
                material.enableInstancing = true;
                EditorUtility.SetDirty(material);
            }

            if (valid)
            {
                AssetDatabase.SaveAssets();
                AssetDatabase.Refresh();
            }
            return valid;
        }

        internal static void ApplyCollisionOutputContract(GameObject root)
        {
            foreach (MeshFilter filter in root.GetComponentsInChildren<MeshFilter>(true))
            {
                bool roadCollision = IsUnderNamedOutput(
                    filter.transform,
                    "OUT_ROAD_COLLISION");
                Renderer renderer = filter.GetComponent<Renderer>();
                if (renderer != null && roadCollision)
                {
                    renderer.enabled = false;
                    EditorUtility.SetDirty(renderer);
                }
                if (!roadCollision || filter.sharedMesh == null)
                    continue;

                MeshCollider collider = filter.GetComponent<MeshCollider>();
                if (collider == null)
                    collider = filter.gameObject.AddComponent<MeshCollider>();
                collider.sharedMesh = filter.sharedMesh;
                collider.convex = false;
                collider.isTrigger = false;
                EditorUtility.SetDirty(collider);
            }
            EditorUtility.SetDirty(root);
        }

        /// <summary>
        /// Visible CityRoad geometry receives world shadows but never writes the
        /// mobile shadow map. This removes self-shadow wedges from road caps,
        /// zebra quads and low sidewalk/curb triangulation.
        /// </summary>
        internal static void ApplyShadowContract(GameObject root)
        {
            foreach (Renderer renderer in root.GetComponentsInChildren<Renderer>(true))
            {
                if (IsUnderNamedOutput(renderer.transform, "OUT_ROAD_SURFACE")
                    || IsUnderNamedOutput(renderer.transform, "OUT_ROAD_MARKINGS")
                    || IsUnderNamedOutput(renderer.transform, "OUT_SIDEWALK_CURB"))
                {
                    renderer.shadowCastingMode = ShadowCastingMode.Off;
                }
                else
                {
                    continue;
                }

                renderer.receiveShadows = true;
                EditorUtility.SetDirty(renderer);
                if (!EditorUtility.IsPersistent(renderer)
                    && PrefabUtility.IsPartOfPrefabInstance(renderer))
                {
                    PrefabUtility.RecordPrefabInstancePropertyModifications(renderer);
                }
            }

            EditorUtility.SetDirty(root);
        }

        private static void ValidateRendererShadowContract(
            Renderer[] renderers,
            List<string> issues)
        {
            foreach (Renderer renderer in renderers)
            {
                bool isRoad = IsUnderNamedOutput(renderer.transform, "OUT_ROAD_SURFACE");
                bool isMarking = IsUnderNamedOutput(renderer.transform, "OUT_ROAD_MARKINGS");
                bool isSidewalk = IsUnderNamedOutput(renderer.transform, "OUT_SIDEWALK_CURB");
                if (!isRoad && !isMarking && !isSidewalk)
                    continue;

                ShadowCastingMode expectedMode = ShadowCastingMode.Off;
                if (renderer.shadowCastingMode != expectedMode)
                {
                    issues.Add(
                        "Unexpected shadow casting mode on "
                        + GetHierarchyPath(renderer.transform)
                        + ": expected "
                        + expectedMode
                        + ", actual "
                        + renderer.shadowCastingMode);
                    return;
                }

                if (!renderer.receiveShadows)
                {
                    issues.Add(
                        "Renderer must continue receiving shadows: "
                        + GetHierarchyPath(renderer.transform));
                    return;
                }
            }
        }

        private static string BuildOverlapKey(Renderer renderer, Mesh mesh)
        {
            Bounds bounds = mesh.bounds;
            long indexCount = 0;
            for (int subMesh = 0; subMesh < mesh.subMeshCount; subMesh++)
                indexCount += (long)mesh.GetIndexCount(subMesh);

            Matrix4x4 matrix = renderer.transform.localToWorldMatrix;
            return string.Format(
                System.Globalization.CultureInfo.InvariantCulture,
                "{0}:{1}:{2}:{3}:{4}:{5}:{6}:{7}:"
                + "{8}:{9}:{10}:{11}:{12}:{13}:{14}:{15}:"
                + "{16}:{17}:{18}:{19}:{20}:{21}:{22}:{23}",
                mesh.vertexCount,
                indexCount,
                Quantize(bounds.center.x),
                Quantize(bounds.center.y),
                Quantize(bounds.center.z),
                Quantize(bounds.size.x),
                Quantize(bounds.size.y),
                Quantize(bounds.size.z),
                Quantize(matrix.m00), Quantize(matrix.m01),
                Quantize(matrix.m02), Quantize(matrix.m03),
                Quantize(matrix.m10), Quantize(matrix.m11),
                Quantize(matrix.m12), Quantize(matrix.m13),
                Quantize(matrix.m20), Quantize(matrix.m21),
                Quantize(matrix.m22), Quantize(matrix.m23),
                Quantize(matrix.m30), Quantize(matrix.m31),
                Quantize(matrix.m32), Quantize(matrix.m33));
        }

        private static bool IsEffectivelyActive(GameObject gameObject, GameObject validationRoot)
        {
            if (!EditorUtility.IsPersistent(validationRoot))
                return gameObject.activeInHierarchy;

            for (Transform current = gameObject.transform;
                current != null;
                current = current.parent)
            {
                if (!current.gameObject.activeSelf)
                    return false;
                if (current.gameObject == validationRoot)
                    return true;
            }
            return false;
        }

        private static long Quantize(float value)
        {
            return (long)Math.Round(value * 1000.0f, MidpointRounding.AwayFromZero);
        }

        private static bool HasTopologyPieceName(Transform transform)
        {
            for (Transform current = transform; current != null; current = current.parent)
            {
                if (current.name.IndexOf("Corridor_", StringComparison.OrdinalIgnoreCase) >= 0
                    || current.name.IndexOf("Junction_", StringComparison.OrdinalIgnoreCase) >= 0
                    || current.name.IndexOf("SidewalkRegion_", StringComparison.OrdinalIgnoreCase) >= 0)
                {
                    return true;
                }
            }
            return false;
        }

        private static bool IsUnderAnyNamedOutput(Transform transform, params string[] outputNames)
        {
            return outputNames.Any(outputName => IsUnderNamedOutput(transform, outputName));
        }

        internal static bool IsUnderNamedOutput(Transform transform, string outputName)
        {
            for (Transform current = transform; current != null; current = current.parent)
            {
                if (current.name.IndexOf(outputName, StringComparison.OrdinalIgnoreCase) >= 0)
                    return true;
            }
            return false;
        }

        internal static bool IsStreetFurnitureOutput(Transform transform)
        {
            return s_StreetFurnitureOutputs.Any(output => IsUnderNamedOutput(transform, output));
        }

        private static string GetHierarchyPath(Transform transform)
        {
            var names = new Stack<string>();
            for (Transform current = transform; current != null; current = current.parent)
                names.Push(current.name);
            return string.Join("/", names);
        }

        private static void EnsureBakeInstanceAndOverrides(
            HEU_HoudiniAssetRoot source,
            GameObject prefab)
        {
            Transform parent = source.transform.parent;
            GameObject instance = FindPrefabInstance(source, prefab, parent);
            if (instance == null)
            {
                instance = PrefabUtility.InstantiatePrefab(prefab, source.gameObject.scene) as GameObject;
                if (instance == null)
                    throw new InvalidOperationException("CityRoad Bake: failed to instantiate the Bake prefab.");

                instance.name = source.name + BakeSuffix;
                instance.transform.SetParent(parent, false);
                CopyLocalTransform(source.transform, instance.transform);
            }

            instance.SetActive(true);
            ApplyShadowContract(instance);

            Transform overrides = FindSiblingByName(
                source,
                parent,
                OverridesName);
            if (overrides == null)
            {
                GameObject overridesObject = new GameObject(OverridesName);
                overridesObject.transform.SetParent(parent, false);
                CopyLocalTransform(source.transform, overridesObject.transform);
                overrides = overridesObject.transform;
            }

            EditorUtility.SetDirty(instance);
            EditorUtility.SetDirty(overrides.gameObject);
            EditorSceneManager.MarkSceneDirty(source.gameObject.scene);
        }

        private static Transform FindSiblingByName(
            HEU_HoudiniAssetRoot source,
            Transform parent,
            string siblingName)
        {
            IEnumerable<Transform> siblings = parent != null
                ? parent.Cast<Transform>()
                : source.gameObject.scene.GetRootGameObjects()
                    .Select(gameObject => gameObject.transform);
            return siblings.FirstOrDefault(transform =>
                string.Equals(
                    transform.name,
                    siblingName,
                    StringComparison.Ordinal));
        }

        private static GameObject FindPrefabInstance(
            HEU_HoudiniAssetRoot source,
            GameObject prefab,
            Transform parent)
        {
            IEnumerable<Transform> siblings = parent != null
                ? parent.Cast<Transform>()
                : source.gameObject.scene.GetRootGameObjects().Select(gameObject => gameObject.transform);
            foreach (Transform sibling in siblings)
            {
                GameObject instanceRoot = PrefabUtility.GetNearestPrefabInstanceRoot(sibling.gameObject);
                if (instanceRoot == null || instanceRoot.transform != sibling)
                    continue;
                if (PrefabUtility.GetCorrespondingObjectFromSource(instanceRoot) == prefab)
                    return instanceRoot;
            }
            return null;
        }

        private static void MakeAuthoringSourceEditorOnly(HEU_HoudiniAssetRoot root)
        {
            root.gameObject.tag = "EditorOnly";
            foreach (Renderer renderer in root.GetComponentsInChildren<Renderer>(true))
            {
                renderer.enabled = false;
                EditorUtility.SetDirty(renderer);
            }
            EditorUtility.SetDirty(root.gameObject);
            EditorSceneManager.MarkSceneDirty(root.gameObject.scene);
        }

        private static void CopyLocalTransform(Transform source, Transform destination)
        {
            destination.localPosition = source.localPosition;
            destination.localRotation = source.localRotation;
            destination.localScale = source.localScale;
        }

        private static string GetBakeFolder(HEU_HoudiniAssetRoot root)
        {
            return string.Format(
                "{0}/{1}/{2}",
                BakeRoot,
                SanitizePathPart(root.gameObject.scene.name),
                SanitizePathPart(root.name));
        }

        private static string GetPrefabPath(HEU_HoudiniAssetRoot root)
        {
            return GetBakeFolder(root) + "/" + SanitizePathPart(root.name) + ".prefab";
        }

        private static string SanitizePathPart(string value)
        {
            var builder = new StringBuilder(value.Length);
            char[] invalid = Path.GetInvalidFileNameChars();
            foreach (char character in value)
                builder.Append(invalid.Contains(character) ? '_' : character);
            return builder.ToString();
        }

        private static void EnsureAssetFolder(string folder)
        {
            string[] parts = folder.Split('/');
            string current = parts[0];
            for (int index = 1; index < parts.Length; index++)
            {
                string next = current + "/" + parts[index];
                if (!AssetDatabase.IsValidFolder(next))
                    AssetDatabase.CreateFolder(current, parts[index]);
                current = next;
            }
        }
    }
}
#endif
