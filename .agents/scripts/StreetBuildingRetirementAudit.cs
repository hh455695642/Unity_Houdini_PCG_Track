using System;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using System.Security.Cryptography;
using Newtonsoft.Json;
using UnityEditor;
using UnityEditor.SceneManagement;
using UnityEngine;
using UnityEngine.SceneManagement;

/// <summary>
/// Read-only retirement audit. Never opens, closes, saves or deletes scenes/assets.
/// Execute through Pipeline script run, then use typed asset delete after reviewing the report.
/// </summary>
public static class StreetBuildingRetirementAudit
{
    static readonly string[] RetiredScenes = {
        "Assets/PCG/Scenes/StreetBuilding_AttachmentValidation.unity",
        "Assets/PCG/Scenes/StreetBuilding_ReferenceValidation.unity"
    };
    const string RetiredBakeRoot = "Assets/PCG/Generated/Buildings/ReferenceAttachments";
    static readonly HashSet<string> ExpectedCases = new HashSet<string>(new[] {
        "Benchmark", "FrontEscape", "HighParapetRoofAccess", "L0", "L1", "L2", "L3",
        "MultiEscape", "Narrow", "RoofAccess", "SecondaryEscape", "SideEscape",
        "SixFloors", "TwoFloors", "Wide", "Width4m"
    }, StringComparer.Ordinal);

    sealed class Reference
    {
        public string owner;
        public string target;
        public string property;
    }
    static bool IsRetired(string path) => RetiredScenes.Contains(path, StringComparer.Ordinal)
        || path == RetiredBakeRoot || path.StartsWith(RetiredBakeRoot + "/", StringComparison.Ordinal);
    static string Sha(string path)
    {
        if (!File.Exists(path)) return null;
        using (var algorithm = SHA256.Create())
        using (var stream = File.OpenRead(path))
            return string.Concat(algorithm.ComputeHash(stream).Select(value => value.ToString("x2")));
    }
    static string Hierarchy(Transform transform) => transform.parent == null ? transform.name
        : Hierarchy(transform.parent) + "/" + transform.name;

    static void InspectLiveObject(UnityEngine.Object value, string owner, List<Reference> references)
    {
        if (value == null) return;
        using (var serialized = new SerializedObject(value))
        {
            var iterator = serialized.GetIterator();
            while (iterator.Next(true))
            {
                if (iterator.propertyType != SerializedPropertyType.ObjectReference) continue;
                var target = iterator.objectReferenceValue;
                if (target == null) continue;
                string path = AssetDatabase.GetAssetPath(target);
                if (IsRetired(path)) references.Add(new Reference { owner = owner, target = path, property = iterator.propertyPath });
            }
        }
    }

    public static object Run(string outputPath)
    {
        string absolute = Path.GetFullPath(outputPath);
        string evidenceRoot = Path.GetFullPath(".codex_tmp") + Path.DirectorySeparatorChar;
        if (!absolute.StartsWith(evidenceRoot, StringComparison.OrdinalIgnoreCase)
            || !absolute.EndsWith(".json", StringComparison.OrdinalIgnoreCase))
            throw new InvalidOperationException("Audit output must be a JSON file under .codex_tmp");

        string[] allPaths = AssetDatabase.GetAllAssetPaths();
        var candidates = allPaths.Where(IsRetired).Distinct(StringComparer.Ordinal).OrderBy(path => path, StringComparer.Ordinal).ToArray();
        var external = new List<Reference>();
        int dependencyOwners = 0;
        // Direct dependencies expose their owner; scanning all owners also finds transitive chains.
        foreach (string owner in allPaths.Where(path => path.StartsWith("Assets/", StringComparison.Ordinal)
            && !IsRetired(path) && !AssetDatabase.IsValidFolder(path)))
        {
            dependencyOwners++;
            foreach (string target in AssetDatabase.GetDependencies(owner, false).Where(IsRetired))
                external.Add(new Reference { owner = owner, target = target, property = "AssetDatabase.GetDependencies(direct)" });
        }

        var live = new List<Reference>();
        var scenes = new List<object>();
        for (int index = 0; index < SceneManager.sceneCount; index++)
        {
            var scene = SceneManager.GetSceneAt(index);
            scenes.Add(new { scene.name, scene.path, scene.isLoaded, scene.isDirty,
                isActive = scene == SceneManager.GetActiveScene(), scene.rootCount });
            if (scene.isLoaded && IsRetired(scene.path))
                live.Add(new Reference { owner = "Open Scene", target = scene.path,
                    property = scene.isDirty ? "Unsaved retired scene" : "Loaded retired scene" });
            if (!scene.isLoaded || IsRetired(scene.path)) continue;
            foreach (var root in scene.GetRootGameObjects())
                foreach (var transform in root.GetComponentsInChildren<Transform>(true))
                {
                    string owner = scene.path + ":/" + Hierarchy(transform);
                    var prefab = PrefabUtility.GetCorrespondingObjectFromSource(transform.gameObject);
                    string prefabPath = prefab != null ? AssetDatabase.GetAssetPath(prefab) : null;
                    if (prefabPath != null && IsRetired(prefabPath))
                        live.Add(new Reference { owner = owner, target = prefabPath, property = "Prefab instance source" });
                    foreach (var component in transform.GetComponents<Component>())
                        InspectLiveObject(component, owner, live);
                }
        }
        var prefabStage = PrefabStageUtility.GetCurrentPrefabStage();
        if (prefabStage != null)
        {
            if (IsRetired(prefabStage.assetPath)) live.Add(new Reference {
                owner = "Open PrefabStage", target = prefabStage.assetPath, property = "Current stage" });
            if (prefabStage.prefabContentsRoot != null)
                foreach (var component in prefabStage.prefabContentsRoot.GetComponentsInChildren<Component>(true))
                    InspectLiveObject(component, "PrefabStage:" + prefabStage.assetPath, live);
        }
        var buildReferences = EditorBuildSettings.scenes.Where(scene => IsRetired(scene.path))
            .Select(scene => new { scene.path, scene.enabled }).ToArray();
        var unknownCases = candidates.Where(path => path.StartsWith(RetiredBakeRoot + "/", StringComparison.Ordinal))
            .Select(path => path.Substring(RetiredBakeRoot.Length + 1).Split('/')[0])
            .Where(name => !ExpectedCases.Contains(name)).Distinct().OrderBy(name => name).ToArray();
        var rows = candidates.Select(path => new {
            path, guid = AssetDatabase.AssetPathToGUID(path), folder = AssetDatabase.IsValidFolder(path),
            type = AssetDatabase.GetMainAssetTypeAtPath(path)?.FullName,
            sha256 = Sha(path), metaSha256 = Sha(path + ".meta"),
            dependencies = AssetDatabase.GetDependencies(path, false),
            reason = IsRetired(path) ? "Explicit retired scene or its dedicated validation output tree" : "Keep"
        }).ToArray();
        var report = new {
            status = external.Count == 0 && live.Count == 0 && buildReferences.Length == 0 && unknownCases.Length == 0
                ? "NO_EXTERNAL_REFERENCES_FOUND" : "REVIEW_REQUIRED",
            readOnly = true, candidateCount = rows.Length, dependencyOwners,
            retiredScenes = RetiredScenes, retiredBakeRoot = RetiredBakeRoot,
            candidates = rows, externalReferences = external, liveReferences = live,
            buildSettingsReferences = buildReferences, unknownCases, scenes,
            limitations = "Build Profile/Addressables serialized assets are covered by AssetDatabase direct dependency scan. Dynamic string paths require a separate source scan. No deletion is performed."
        };
        Directory.CreateDirectory(Path.GetDirectoryName(absolute));
        File.WriteAllText(absolute, JsonConvert.SerializeObject(report, Formatting.Indented));
        return report;
    }

    public static object AssertRetired(string outputPath)
    {
        var remaining = AssetDatabase.GetAllAssetPaths().Where(IsRetired).ToArray();
        var files = RetiredScenes.Concat(new[] { RetiredBakeRoot }).Where(path => File.Exists(path) || Directory.Exists(path)
            || File.Exists(path + ".meta")).ToArray();
        if (remaining.Length > 0 || files.Length > 0)
            throw new InvalidOperationException("Retired assets remain: " + string.Join(", ", remaining.Concat(files).Distinct()));
        return Run(outputPath);
    }
}
