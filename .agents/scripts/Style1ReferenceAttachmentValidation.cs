using System;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using System.Reflection;
using System.Security.Cryptography;
using System.Globalization;
using System.Text.RegularExpressions;
using HoudiniEngineUnity;
using Newtonsoft.Json;
using PCGBike.Buildings;
using PCGBike.Editor.Buildings;
using UnityEditor;
using UnityEditor.SceneManagement;
using UnityEngine;
using UnityEngine.SceneManagement;

/// <summary>
/// Explicit editor-only acceptance harness. Creates independent HAPI instances,
/// bakes native Unity prefabs and keeps the artist's open scene/session intact.
/// </summary>
public static class Style1ReferenceAttachmentValidation
{
    const string Hda = "Assets/PCG/HDA/City/StreetBuilding.hda";
    const string Style = "Assets/PCG/Art/Building_Test/Style2/SBStyle2.asset";
    // Per-run ownership is derived from the evidence directory, never a permanent validation scene.
    static string RunRoot(string outputDir)
    {
        string full = Path.GetFullPath(outputDir).Replace('\\', '/');
        string permitted = Path.GetFullPath(".codex_tmp/regression").Replace('\\', '/').TrimEnd('/') + "/";
        Require(full.StartsWith(permitted, StringComparison.OrdinalIgnoreCase), "Evidence must be inside .codex_tmp/regression");
        using (var hash = SHA256.Create())
            return "Assets/__PCGValidation/SB_" + string.Concat(hash.ComputeHash(System.Text.Encoding.UTF8.GetBytes(full))
                .Take(8).Select(value => value.ToString("x2")));
    }
    static string ScenePath(string outputDir) => RunRoot(outputDir) + "/Attachment_" + Path.GetFileName(RunRoot(outputDir)) + ".unity";
    static string BakeRoot(string outputDir) => RunRoot(outputDir) + "/Bakes";
    static bool _runBakeUpdateProof;
    static string _bakeUpdateOutputDir;
    static string _bakeUpdateCaseName;

    public static object BuildUpdateCase(string outputDir, string caseName,
        float width, float depth, int floors, int shape, int notchSide)
    {
        Require(!_runBakeUpdateProof, "Nested Bake update validation is not allowed");
        RunRoot(outputDir); // Validate evidence ownership before setting static state.
        _runBakeUpdateProof = true;
        _bakeUpdateOutputDir = outputDir;
        _bakeUpdateCaseName = caseName;
        try { return BuildCase(outputDir, caseName, width, depth, floors, shape, notchSide); }
        finally
        {
            _runBakeUpdateProof = false;
            _bakeUpdateOutputDir = null;
            _bakeUpdateCaseName = null;
        }
    }

    sealed class BakeUpdateMeshSnapshot
    {
        public string path;
        public string guid;
        public string sha256;
    }

    static string UpdateFileSha(string path)
    {
        Require(File.Exists(path), "Bake update proof file is missing: " + path);
        using (var algorithm = SHA256.Create())
        using (var stream = File.OpenRead(path))
            return string.Concat(algorithm.ComputeHash(stream).Select(value => value.ToString("x2")));
    }

    static Dictionary<string, string> UpdateStyleFileHashes()
    {
        const string root = "Assets/PCG/Art/Building_Test/Style2";
        Require(Directory.Exists(root), "Formal Style2 directory is missing");
        return Directory.EnumerateFiles(root, "*", SearchOption.AllDirectories)
            .Concat(File.Exists(root + ".meta") ? new[] { root + ".meta" } : Array.Empty<string>())
            .Select(path => path.Replace('\\', '/'))
            .OrderBy(path => path, StringComparer.Ordinal)
            .ToDictionary(path => path, UpdateFileSha, StringComparer.Ordinal);
    }

    static void RequireUpdateStyleUnchanged(Dictionary<string, string> before,
        Dictionary<string, string> after)
    {
        var changed = before.Keys.Union(after.Keys, StringComparer.Ordinal)
            .Where(path => !before.TryGetValue(path, out string expected)
                || !after.TryGetValue(path, out string actual) || expected != actual)
            .OrderBy(path => path, StringComparer.Ordinal).ToArray();
        Require(changed.Length == 0,
            "Bake update changed formal Style2 files: " + string.Join(", ", changed));
    }

    static void RequireUpdateOldMeshesUnchanged(Dictionary<string, BakeUpdateMeshSnapshot> snapshots)
    {
        foreach (var pair in snapshots)
        {
            Require(AssetDatabase.LoadAssetAtPath<Mesh>(pair.Key) != null,
                "Bake update deleted an earlier merged Mesh: " + pair.Key);
            Require(AssetDatabase.AssetPathToGUID(pair.Key) == pair.Value.guid,
                "Bake update changed an earlier merged Mesh GUID: " + pair.Key);
            Require(UpdateFileSha(pair.Key) == pair.Value.sha256,
                "Bake update changed earlier merged Mesh bytes: " + pair.Key);
        }
    }

    static object UpdateMeshSnapshot(GameObject instance, AttachmentOutput output,
        string caseRoot, Dictionary<string, BakeUpdateMeshSnapshot> snapshots)
    {
        ValidateNativeInstance(instance);
        ValidateAttachmentMeshes(instance, output, true); // Includes oriented triangles, normals, UV and materials.
        ValidateActualRoofFootprints(instance, output);
        var visuals = instance.GetComponentsInChildren<Transform>(true)
            .Where(transform => transform.name.StartsWith("SB_PIPE_", StringComparison.Ordinal)).ToArray();
        Require(visuals.Length == output.actual["DrainPipe"],
            "Bake update retained duplicate/empty merged-pipe objects");
        foreach (var visual in visuals)
        {
            Require(visual.parent != null && visual.parent != instance.transform
                && visual.parent.name.Contains("OUT_DETAIL_INSTANCES")
                && visual.parent.name.EndsWith("_bakedClone", StringComparison.Ordinal),
                "Merged pipe is outside the replaceable detail part: " + visual.name);
            Require(visual.GetComponent<MeshFilter>() != null && visual.GetComponent<MeshRenderer>() != null,
                "Merged-pipe object lost its single Mesh/Renderer: " + visual.name);
        }
        Require(!instance.transform.Cast<Transform>()
            .Any(transform => transform.name.StartsWith("SB_PIPE_", StringComparison.Ordinal)),
            "Bake update left a root-level merged pipe");

        RequireUpdateOldMeshesUnchanged(snapshots);
        var rows = new List<object>();
        foreach (var visual in visuals.OrderBy(transform => transform.name, StringComparer.Ordinal))
        {
            var mesh = visual.GetComponent<MeshFilter>().sharedMesh;
            string path = AssetDatabase.GetAssetPath(mesh);
            Require(path.StartsWith(caseRoot + "/", StringComparison.Ordinal),
                "Updated merged pipe escaped this case's owned destination: " + path);
            // Acceptance must not repair/save the production output for it.
            Require(!EditorUtility.IsDirty(mesh), "Bake left an unsaved merged Mesh: " + path);
            string digest = UpdateFileSha(path);
            string guid = AssetDatabase.AssetPathToGUID(path);
            if (snapshots.TryGetValue(path, out var previous))
                Require(previous.guid == guid && previous.sha256 == digest,
                    "Bake update reused and overwrote an earlier merged Mesh: " + path);
            else snapshots.Add(path, new BakeUpdateMeshSnapshot { path = path, guid = guid, sha256 = digest });
            rows.Add(new { group = visual.name.Substring("SB_PIPE_".Length),
                parent = visual.parent.name, mesh = path, guid, sha256 = digest,
                triangles = Enumerable.Range(0, mesh.subMeshCount).Sum(index => (long)mesh.GetIndexCount(index) / 3) });
        }
        return rows;
    }

    static void UpdateProof(HEU_HoudiniAsset asset, GameObject prefab,
        AttachmentOutput output, Scene gallery)
    {
        Require(_runBakeUpdateProof && asset != null && prefab != null,
            "Bake update proof has no explicit owner or active HDA");
        string evidence = Path.Combine(_bakeUpdateOutputDir, _bakeUpdateCaseName + "-bake-update-proof.json");
        Require(!File.Exists(evidence), "Bake update proof evidence already exists: " + evidence);
        string prefabPath = AssetDatabase.GetAssetPath(prefab);
        string caseRoot = BakeRoot(_bakeUpdateOutputDir) + "/" + _bakeUpdateCaseName;
        Require(prefabPath.StartsWith(caseRoot + "/", StringComparison.Ordinal),
            "Bake update proof must own its dedicated Prefab/case directory");
        var styleBefore = UpdateStyleFileHashes();
        Dictionary<string, string> styleAfter = null;
        var snapshots = new Dictionary<string, BakeUpdateMeshSnapshot>(StringComparer.Ordinal);
        var steps = new List<object>();
        GameObject probe = null;
        Exception failure = null;
        try
        {
            // Initial proof and old Mesh byte/GUID inventory come from a real
            // Prefab instance, not output metadata or the HDA preview hierarchy.
            probe = (GameObject)PrefabUtility.InstantiatePrefab(prefab, gallery);
            Require(probe != null, "Cannot instantiate the initial update-proof Prefab");
            steps.Add(new { kind = "initial_prefab", iteration = 0,
                meshes = UpdateMeshSnapshot(probe, output, caseRoot, snapshots) });
            UnityEngine.Object.DestroyImmediate(probe); probe = null;

            for (int iteration = 1; iteration <= 2; iteration++)
            {
                Require(asset.BakeToExistingPrefab(prefab), "Public native Prefab update failed: " + iteration);
                prefab = AssetDatabase.LoadAssetAtPath<GameObject>(prefabPath);
                Require(prefab != null, "Updated Prefab disappeared");
                probe = (GameObject)PrefabUtility.InstantiatePrefab(prefab, gallery);
                Require(probe != null, "Cannot instantiate the updated Prefab");
                steps.Add(new { kind = "prefab_update", iteration,
                    meshes = UpdateMeshSnapshot(probe, output, caseRoot, snapshots) });
                UnityEngine.Object.DestroyImmediate(probe); probe = null;
                RequireUpdateStyleUnchanged(styleBefore, UpdateStyleFileHashes());
            }

            // Standalone update is tracked separately as a plugin limitation:
            // shared formal Prefabs make HEU infer Assets//Meshes. Do not modify
            // the plugin or mark that unsupported route as a passed contract.
            RequireUpdateOldMeshesUnchanged(snapshots);
        }
        catch (Exception error) { failure = error; }
        finally
        {
            try { if (probe != null) UnityEngine.Object.DestroyImmediate(probe); }
            catch (Exception error) { if (failure == null) failure = error; }
            try
            {
                styleAfter = UpdateStyleFileHashes();
                RequireUpdateStyleUnchanged(styleBefore, styleAfter);
                RequireUpdateOldMeshesUnchanged(snapshots);
            }
            catch (Exception error) { if (failure == null) failure = error; }
            Write(evidence, new {
                status = failure == null ? "PASS" : "FAIL", caseName = _bakeUpdateCaseName,
                prefab = prefabPath, requestedPrefabUpdates = 2, requestedStandaloneUpdates = 0,
                standaloneUpdateLimitation = "Native HEU update with shared formal sources infers Assets//Meshes; separate failure evidence retained",
                actualGeometry = "HAPI source transforms -> native Prefab; oriented triangles, normals, UV, material equality",
                sourceStyleRoot = "Assets/PCG/Art/Building_Test/Style2",
                styleBefore, styleAfter, preservedMergedMeshes = snapshots.Values.ToArray(), steps,
                temporaryProbeDestroyed = probe == null,
                error = failure?.ToString(), sceneSavedByProof = false
            });
        }
        if (failure != null) throw new InvalidOperationException("Native repeated Bake update proof failed; see " + evidence, failure);
    }

    public static object GetRunPaths(string outputDir) => new { runRoot = RunRoot(outputDir), scenePath = ScenePath(outputDir), sceneName = Path.GetFileNameWithoutExtension(ScenePath(outputDir)),
        bakeRoot = BakeRoot(outputDir), ownership = "Explicit per-run validation output; caller must close owned scene and use Pipeline typed asset delete in finally",
        cases = new[] { "Benchmark", "Width4m", "Narrow", "Wide", "L0", "L1", "L2", "L3", "TwoFloors", "SixFloors", "RoofAccess", "HighParapetRoofAccess", "FrontEscape", "SideEscape", "MultiEscape", "SecondaryEscape" } };
    const string TransientCache = "Assets/HoudiniEngineAssetCache/";
    static readonly BindingFlags PrivateStatic = BindingFlags.Static | BindingFlags.NonPublic;

    sealed class AttachmentOutput
    {
        public string diagnostic;
        public Dictionary<string, int> requested;
        public Dictionary<string, int> actual;
        public Dictionary<string, string> reasons;
        public int detailPoints;
        public int detailParts;
        public Dictionary<string, int> roles;
        public string[] sourcePrefabs;
        public string[] referenceSourcePrefabs;
        public Dictionary<string, int> sourcePrefabCounts;
        public Dictionary<string, int> verifiedGroups;
        public Dictionary<int, int> subtypePoints;
        public int fireEscapeFaceMask;
        public Dictionary<string, int[]> actualFaceIds;
        public Dictionary<string, string[]> actualSurfaceRoles;
        public Dictionary<string, PipeGroupEvidence> pipeGroups;
    }
    sealed class PipeTriangleEvidence
    {
        public string material;
        public float[] positions;
        public float[] normals;
        public float[] uv;
    }
    sealed class PipeGroupEvidence
    {
        public int sourcePoints;
        public int sourceMeshFilters;
        public Dictionary<int, int> subtypes = new Dictionary<int, int>();
        public List<PipeTriangleEvidence> triangles = new List<PipeTriangleEvidence>();
    }
    sealed class SavedCase
    {
        public string status { get; set; }
        public string caseName { get; set; }
        public AttachmentOutput output { get; set; }
        public HighWallEvidence highWallFixture { get; set; }
    }
    sealed class HighWallEvidence
    {
        public float requestedHeight;
        public float measuredHeight;
        public float roofY;
        public float wallTop;
        public float ladderTop;
        public float ladderCapClearance;
        public int actualWallInstances;
        public int actualRoofLadders;
        public int upperLadderTrianglesChecked;
        public string[] fixturePrefabPaths;
        public string[] fixtureMeshPaths;
    }

    static void Require(bool condition, string message)
    { if (!condition) throw new InvalidOperationException(message); }
    static object Write(string path, object result)
    {
        Directory.CreateDirectory(Path.GetDirectoryName(Path.GetFullPath(path)));
        File.WriteAllText(path, JsonConvert.SerializeObject(result, Formatting.Indented));
        return result;
    }
    static bool IsPersistentAsset(string path) =>
        !string.IsNullOrEmpty(path) && path.StartsWith("Assets/", StringComparison.Ordinal)
        && !path.StartsWith(TransientCache, StringComparison.OrdinalIgnoreCase);

    static Scene FindGallery(string outputDir)
    {
        // Typed Pipeline commands create/open this exact owned scene before adding cases.
        var matches = Enumerable.Range(0, SceneManager.sceneCount).Select(SceneManager.GetSceneAt)
            .Where(scene => scene.IsValid() && scene.isLoaded
                && scene.path == ScenePath(outputDir))
            .ToArray();
        Require(matches.Length <= 1, "Multiple attachment galleries are open; refusing to split validation cases");
        return matches.FirstOrDefault();
    }

    static void ValidateNativeInstance(GameObject instance)
    {
        Require(instance != null && instance.GetComponentInChildren<HEU_HoudiniAssetRoot>(true) == null,
            "Bake still contains Houdini runtime components");
        Require(instance.GetComponentsInChildren<Component>(true).All(component => component != null
            && component.GetType().Namespace != "HoudiniEngineUnity"),"Bake contains missing or residual Houdini components");
        var filters = instance.GetComponentsInChildren<MeshFilter>(true);
        var renderers = instance.GetComponentsInChildren<MeshRenderer>(true);
        Require(filters.Length > 0 && renderers.Length > 0, "Bake has no renderable geometry");
        Require(filters.All(filter => filter.sharedMesh != null
            && IsPersistentAsset(AssetDatabase.GetAssetPath(filter.sharedMesh))),
            "Bake has missing or transient meshes");
        Require(renderers.All(renderer => renderer.sharedMaterials.Length > 0
            && renderer.sharedMaterials.All(material => material != null
                && IsPersistentAsset(AssetDatabase.GetAssetPath(material)))),
            "Bake has missing or transient materials");
    }
    static readonly Regex PipePartPattern = new Regex(@"SB_REF_(B\d+_DrainPipe_\d+_[A-Za-z_]+)_F\d+_P\d+", RegexOptions.CultureInvariant);
    static string PipeGroupOf(Transform transform, Transform root)
    {
        while (transform != null && transform != root)
        {
            if (transform.name.StartsWith("SB_PIPE_", StringComparison.Ordinal)) return transform.name.Substring("SB_PIPE_".Length);
            var match = PipePartPattern.Match(transform.name);
            if (match.Success) return match.Groups[1].Value;
            transform = transform.parent;
        }
        return null;
    }
    static string MaterialProof(Material material, Dictionary<Material, string> cache)
    {
        Require(material != null && material.shader != null, "Pipe geometry has no material/shader");
        if (cache.TryGetValue(material, out string saved)) return saved;
        var values = new List<string> { material.shader.name, material.renderQueue.ToString(CultureInfo.InvariantCulture),
            material.enableInstancing.ToString(), string.Join(",", material.shaderKeywords.OrderBy(keyword => keyword, StringComparer.Ordinal)) };
        string Number(float value) => value.ToString("R", CultureInfo.InvariantCulture);
        string Vector(Vector4 value) => string.Join(",", new[] { value.x, value.y, value.z, value.w }.Select(Number));
        for (int index = 0; index < material.shader.GetPropertyCount(); index++)
        {
            string name = material.shader.GetPropertyName(index);
            string value;
            switch (material.shader.GetPropertyType(index))
            {
                case UnityEngine.Rendering.ShaderPropertyType.Color: value = Vector(material.GetColor(name)); break;
                case UnityEngine.Rendering.ShaderPropertyType.Vector: value = Vector(material.GetVector(name)); break;
                case UnityEngine.Rendering.ShaderPropertyType.Texture:
                    var texture = material.GetTexture(name);
                    string path = texture == null ? "null" : AssetDatabase.GetAssetPath(texture);
                    bool builtIn = texture != null && !string.IsNullOrEmpty(path)
                        && !path.StartsWith("Assets/", StringComparison.Ordinal) && EditorUtility.IsPersistent(texture);
                    Require(texture == null || IsPersistentAsset(path) || builtIn, "Pipe material has a transient texture");
                    var scale = material.GetTextureScale(name); var offset = material.GetTextureOffset(name);
                    value = path + (texture == null ? "" : "#" + texture.name + ":" + texture.GetType().FullName)
                        + "|" + Vector(new Vector4(scale.x, scale.y, offset.x, offset.y)); break;
                case UnityEngine.Rendering.ShaderPropertyType.Int: value = material.GetInteger(name).ToString(CultureInfo.InvariantCulture); break;
                default: value = Number(material.GetFloat(name)); break;
            }
            values.Add(name + "=" + value);
        }
        using (var hash = SHA256.Create()) saved = string.Concat(hash.ComputeHash(System.Text.Encoding.UTF8.GetBytes(string.Join("\n", values)))
            .Select(value => value.ToString("x2")));
        cache.Add(material, saved); return saved;
    }
    static List<PipeTriangleEvidence> PipeTriangles(MeshFilter filter, Matrix4x4 matrix, Dictionary<Material, string> materials)
    {
        var mesh = filter.sharedMesh; var renderer = filter.GetComponent<MeshRenderer>();
        Require(mesh != null && renderer != null && matrix.determinant > 0, "Pipe geometry is missing or mirrored");
        Require(renderer.sharedMaterials.Length == mesh.subMeshCount, "Pipe material slots differ from actual submeshes: " + filter.name);
        var vertices = mesh.vertices; var normals = mesh.normals; var uv = mesh.uv;
        Require(normals.Length == vertices.Length && uv.Length == vertices.Length, "Pipe geometry lost its source normals/UV0");
        var normalMatrix = matrix.inverse.transpose;
        var result = new List<PipeTriangleEvidence>();
        for (int submesh = 0; submesh < mesh.subMeshCount; submesh++)
        {
            Require(mesh.GetTopology(submesh) == MeshTopology.Triangles, "Pipe submesh is not triangle geometry");
            string material = MaterialProof(renderer.sharedMaterials[submesh], materials);
            var indices = mesh.GetTriangles(submesh);
            for (int triangle = 0; triangle < indices.Length; triangle += 3)
            {
                var proof = new PipeTriangleEvidence { material = material, positions = new float[9], normals = new float[9], uv = new float[6] };
                for (int corner = 0; corner < 3; corner++)
                {
                    int vertex = indices[triangle + corner];
                    Vector3 point = matrix.MultiplyPoint3x4(vertices[vertex]);
                    Vector3 normal = normalMatrix.MultiplyVector(normals[vertex]).normalized;
                    for (int axis = 0; axis < 3; axis++) { proof.positions[corner * 3 + axis] = point[axis]; proof.normals[corner * 3 + axis] = normal[axis]; }
                    proof.uv[corner * 2] = uv[vertex].x; proof.uv[corner * 2 + 1] = uv[vertex].y;
                }
                result.Add(proof);
            }
        }
        Require(result.Count > 0, "Pipe source contains no triangles");
        return result;
    }
    static Vector3 TriangleCenter(PipeTriangleEvidence triangle) => new Vector3(
        (triangle.positions[0] + triangle.positions[3] + triangle.positions[6]) / 3,
        (triangle.positions[1] + triangle.positions[4] + triangle.positions[7]) / 3,
        (triangle.positions[2] + triangle.positions[5] + triangle.positions[8]) / 3);
    static string TriangleBucket(string material, Vector3Int cell) => material + "/" + cell.x + "/" + cell.y + "/" + cell.z;
    static Vector3Int TriangleCell(Vector3 value) => new Vector3Int(Mathf.FloorToInt(value.x * 100), Mathf.FloorToInt(value.y * 100), Mathf.FloorToInt(value.z * 100));
    static bool SameOrientedTriangle(PipeTriangleEvidence first, PipeTriangleEvidence second)
    {
        // Cyclic index rotation is harmless; reversing winding is not.
        for (int rotation = 0; rotation < 3; rotation++)
        {
            bool equal = true;
            for (int corner = 0; corner < 3 && equal; corner++)
            {
                int other = (corner + rotation) % 3;
                for (int axis = 0; axis < 3; axis++)
                    if (Mathf.Abs(first.positions[corner * 3 + axis] - second.positions[other * 3 + axis]) > .0005f
                        || Mathf.Abs(first.normals[corner * 3 + axis] - second.normals[other * 3 + axis]) > .001f) equal = false;
                for (int axis = 0; axis < 2; axis++)
                    if (Mathf.Abs(first.uv[corner * 2 + axis] - second.uv[other * 2 + axis]) > .0001f) equal = false;
            }
            if (equal) return true;
        }
        return false;
    }
    static void RequireSamePipeGeometry(string group, List<PipeTriangleEvidence> expected, List<PipeTriangleEvidence> actual)
    {
        Require(expected.Count == actual.Count, "Pipe group lost/duplicated triangles: " + group + "; expected " + expected.Count + ", actual " + actual.Count);
        var expectedMaterials = expected.GroupBy(triangle => triangle.material).ToDictionary(items => items.Key, items => items.Count());
        var actualMaterials = actual.GroupBy(triangle => triangle.material).ToDictionary(items => items.Key, items => items.Count());
        Require(expectedMaterials.Count == actualMaterials.Count && expectedMaterials.All(pair => actualMaterials.GetValueOrDefault(pair.Key) == pair.Value),
            "Pipe group material triangle totals changed: " + group + "; expected "
            + string.Join(",", expectedMaterials.Select(pair => pair.Key.Substring(0, 12) + ":" + pair.Value))
            + "; actual " + string.Join(",", actualMaterials.Select(pair => pair.Key.Substring(0, 12) + ":" + pair.Value)));
        var buckets = new Dictionary<string, List<int>>(StringComparer.Ordinal);
        for (int index = 0; index < expected.Count; index++)
        {
            string key = TriangleBucket(expected[index].material, TriangleCell(TriangleCenter(expected[index])));
            if (!buckets.TryGetValue(key, out var list)) buckets.Add(key, list = new List<int>());
            list.Add(index);
        }
        var used = new bool[expected.Count];
        foreach (var triangle in actual)
        {
            var cell = TriangleCell(TriangleCenter(triangle)); bool found = false;
            for (int x = -1; x <= 1 && !found; x++) for (int y = -1; y <= 1 && !found; y++) for (int z = -1; z <= 1 && !found; z++)
            {
                if (!buckets.TryGetValue(TriangleBucket(triangle.material, cell + new Vector3Int(x, y, z)), out var entries)) continue;
                foreach (int candidate in entries)
                    if (!used[candidate] && SameOrientedTriangle(expected[candidate], triangle)) { used[candidate] = true; found = true; break; }
            }
            Require(found, "Pipe group geometry/normal/UV or winding differs from actual HAPI source transforms: "
                + group + "; unmatched triangle center=" + TriangleCenter(triangle));
        }
        Require(used.All(value => value), "Pipe group has unmatched expected geometry: " + group);
    }
    static string[] ValidatePipeMeshes(GameObject instance, AttachmentOutput output, bool requireCombined)
    {
        Require(output.pipeGroups != null && output.pipeGroups.Count == output.actual["DrainPipe"], "Missing persisted per-group pipe geometry evidence");
        var filters = instance.GetComponentsInChildren<MeshFilter>(true).Where(filter => filter.sharedMesh != null)
            .Select(filter => new { filter, group = PipeGroupOf(filter.transform, instance.transform) })
            .Where(item => item.group != null).GroupBy(item => item.group, StringComparer.Ordinal)
            .ToDictionary(group => group.Key, group => group.Select(item => item.filter).ToArray(), StringComparer.Ordinal);
        Require(filters.Count == output.pipeGroups.Count && output.pipeGroups.Keys.All(filters.ContainsKey), "Actual pipe mesh groups differ from HAPI complete groups");
        var materials = new Dictionary<Material, string>();
        foreach (var pair in output.pipeGroups)
        {
            var group = filters[pair.Key];
            if (requireCombined)
                Require(group.Length == 1 && group[0].name == "SB_PIPE_" + pair.Key
                    && group[0].GetComponent<MeshRenderer>() != null && group[0].sharedMesh.name == "SB_PIPE_" + pair.Key,
                    "Baked pipe group must have exactly one combined Mesh/Renderer: " + pair.Key);
            else Require(group.Length == pair.Value.sourceMeshFilters, "Generated pipe source filter count differs from actual HAPI pieces: " + pair.Key);
            Require(group.All(filter => IsPersistentAsset(AssetDatabase.GetAssetPath(filter.sharedMesh))), "Pipe group has a transient/missing Mesh reference");
            var triangles = group.SelectMany(filter => PipeTriangles(filter,
                instance.transform.worldToLocalMatrix * filter.transform.localToWorldMatrix, materials)).ToList();
            RequireSamePipeGeometry(pair.Key, pair.Value.triangles, triangles);
        }
        return filters.Values.SelectMany(group => group).Select(filter => AssetDatabase.GetAssetPath(filter.sharedMesh)).Distinct().ToArray();
    }
    static string[] ValidateAttachmentMeshes(GameObject instance, AttachmentOutput output, bool requireCombinedPipes = false)
    {
        Require(instance != null && output?.sourcePrefabCounts != null,
            "Attachment mesh verification requires actual HAPI point/path evidence");
        var expected = new Dictionary<Mesh, int>();
        var pipePaths = output.pipeGroups?.Values == null ? new HashSet<string>() : AssetDatabase.LoadAssetAtPath<StreetBuildingStyleConfig>(Style)
            .EnumerateLayerModules().Where(entry => entry.Module.Prefab != null && (int)entry.Module.AttachmentSubtype >= 8 && (int)entry.Module.AttachmentSubtype <= 12)
            .Select(entry => AssetDatabase.GetAssetPath(entry.Module.Prefab)).ToHashSet();
        foreach (var pair in output.sourcePrefabCounts.Where(pair => !pipePaths.Contains(pair.Key)))
        {
            Require(pair.Value > 0 && IsPersistentAsset(pair.Key), "Invalid attachment source count: " + pair.Key);
            var prefab = AssetDatabase.LoadAssetAtPath<GameObject>(pair.Key);
            Require(prefab != null, "Attachment source Prefab cannot be loaded: " + pair.Key);
            var filters = prefab.GetComponentsInChildren<MeshFilter>(true);
            Require(filters.Length > 0 && filters.All(filter => filter.sharedMesh != null
                && IsPersistentAsset(AssetDatabase.GetAssetPath(filter.sharedMesh))),
                "Attachment source has missing or transient Mesh references: " + pair.Key);
            foreach (var filter in filters)
                expected[filter.sharedMesh] = expected.GetValueOrDefault(filter.sharedMesh) + pair.Value;
        }
        var actual = instance.GetComponentsInChildren<MeshFilter>(true).Where(filter => filter.sharedMesh != null)
            .GroupBy(filter => filter.sharedMesh).ToDictionary(group => group.Key, group => group.Count());
        foreach (var pair in expected)
            Require(actual.GetValueOrDefault(pair.Key) >= pair.Value,
                "Generated/Baked attachment Mesh reference is missing or incomplete: "
                + AssetDatabase.GetAssetPath(pair.Key) + "; expected at least " + pair.Value
                + ", actual " + actual.GetValueOrDefault(pair.Key));
        return expected.Keys.Select(AssetDatabase.GetAssetPath).Concat(ValidatePipeMeshes(instance, output, requireCombinedPipes))
            .Distinct().OrderBy(path => path).ToArray();
    }
    static void ValidateActualRoofFootprints(GameObject instance, AttachmentOutput output)
    {
        // Read the actual instantiated Mesh transforms. Point metadata and
        // placement diagnostics cannot prove that source geometry is separated.
        var style=AssetDatabase.LoadAssetAtPath<StreetBuildingStyleConfig>(Style);
        var paths=style.EnumerateLayerModules().Where(entry=>entry.Module.Prefab!=null
            && entry.Module.AttachmentSubtype is StreetBuildingAttachmentSubtype.WaterTower or StreetBuildingAttachmentSubtype.Chimney)
            .Select(entry=>AssetDatabase.GetAssetPath(entry.Module.Prefab)).Distinct().ToArray();
        var meshes=paths.SelectMany(path=>AssetDatabase.LoadAssetAtPath<GameObject>(path)
            .GetComponentsInChildren<MeshFilter>(true).Select(filter=>filter.sharedMesh)).ToHashSet();
        var actual=instance.GetComponentsInChildren<MeshFilter>(true).Where(filter=>meshes.Contains(filter.sharedMesh)).ToArray();
        Require(actual.Length==output.actual["WaterTower"]+output.actual["Chimney"],"Actual roof geometry count differs from complete equipment units");
        var bounds=actual.Select(filter=>
        {
            var local=filter.sharedMesh.bounds;var world=new Bounds();bool first=true;
            for(int corner=0;corner<8;corner++)
            {
                var p=filter.transform.TransformPoint(local.center+Vector3.Scale(local.extents,
                    new Vector3((corner&1)==0?-1:1,(corner&2)==0?-1:1,(corner&4)==0?-1:1)));
                if(first){world=new Bounds(p,Vector3.zero);first=false;}else world.Encapsulate(p);
            }
            return world;
        }).ToArray();
        for(int i=0;i<bounds.Length;i++)for(int j=i+1;j<bounds.Length;j++)
        {
            float x=Mathf.Min(bounds[i].max.x,bounds[j].max.x)-Mathf.Max(bounds[i].min.x,bounds[j].min.x);
            float z=Mathf.Min(bounds[i].max.z,bounds[j].max.z)-Mathf.Max(bounds[i].min.z,bounds[j].min.z);
            Require(x<=.001f||z<=.001f,"Actual tower/chimney footprints overlap: "+actual[i].sharedMesh.name+" / "+actual[j].sharedMesh.name);
        }
    }
    static bool IsParapet(StreetBuildingModuleRole role) => role is StreetBuildingModuleRole.Parapet
        or StreetBuildingModuleRole.ParapetCorner or StreetBuildingModuleRole.ParapetConcaveCorner;

    static int GallerySlot(string caseName, int fallback)
    {
        // Rebuilding one case must not move it onto a surviving case's slot.
        string[] ordered = { "Benchmark", "Width4m", "Narrow", "Wide", "L0", "L1", "L2", "L3",
            "TwoFloors", "SixFloors", "RoofAccess", "HighParapetRoofAccess", "FrontEscape",
            "SideEscape", "MultiEscape", "SecondaryEscape" };
        int index = Array.IndexOf(ordered, caseName);
        return index >= 0 ? index : fallback;
    }

    static StreetBuildingStyleConfig CreateHighWallFixture(StreetBuildingStyleConfig source, string destination,
        int floors, out HighWallEvidence evidence)
    {
        // Validation input only: current production modules have a fixed .6m
        // height. A 1.2m parameter alone cannot prove real high-wall clearance.
        const float targetHeight = 1.2f;
        string folder = destination + "/ValidationInputs";
        Require(!AssetDatabase.IsValidFolder(folder), "High-wall validation inputs already exist");
        Require(!string.IsNullOrEmpty(AssetDatabase.CreateFolder(destination, "ValidationInputs")),
            "Cannot create owned high-wall validation input folder");
        var replacements = new Dictionary<GameObject, GameObject>();
        var meshPaths = new List<string>();
        var prefabPaths = new List<string>();
        foreach (var entry in source.EnumerateLayerModules().Where(entry => entry.Module.Enabled
            && IsParapet(entry.Module.ModuleRole)))
        {
            var prefab = entry.Module.Prefab;
            Require(prefab != null, "High-wall source module is missing");
            if (replacements.ContainsKey(prefab)) continue;
            var filters = prefab.GetComponentsInChildren<MeshFilter>(true);
            Require(filters.Length == 1 && filters[0].sharedMesh != null,
                "High-wall fixture expects one complete source Mesh per parapet module");
            var sourceRenderer = filters[0].GetComponent<MeshRenderer>();
            Require(sourceRenderer != null && sourceRenderer.sharedMaterials.All(material => material != null),
                "High-wall source materials are missing");
            var mesh = UnityEngine.Object.Instantiate(filters[0].sharedMesh);
            mesh.name = prefab.name + "_ValidationHeight1_2m";
            Matrix4x4 sourceMatrix = prefab.transform.worldToLocalMatrix * filters[0].transform.localToWorldMatrix;
            Vector3[] vertices = mesh.vertices;
            for (int index = 0; index < vertices.Length; index++) vertices[index] = sourceMatrix.MultiplyPoint3x4(vertices[index]);
            float minimum = vertices.Min(point => point.y), maximum = vertices.Max(point => point.y);
            Require(Mathf.Abs(minimum) < .001f && maximum > .001f, "Parapet fixture pivot must touch the roof plane");
            for (int index = 0; index < vertices.Length; index++)
                vertices[index].y = (vertices[index].y - minimum) * targetHeight / (maximum - minimum);
            mesh.vertices = vertices;
            mesh.RecalculateNormals(); mesh.RecalculateTangents(); mesh.RecalculateBounds();
            string meshPath = folder + "/" + mesh.name + ".asset";
            string prefabPath = folder + "/" + mesh.name + ".prefab";
            Require(AssetDatabase.LoadMainAssetAtPath(meshPath) == null && AssetDatabase.LoadMainAssetAtPath(prefabPath) == null,
                "High-wall fixture assets would overwrite existing content");
            AssetDatabase.CreateAsset(mesh, meshPath);
            GameObject fixture = null;
            try
            {
                fixture = new GameObject(mesh.name);
                fixture.AddComponent<MeshFilter>().sharedMesh = mesh;
                fixture.AddComponent<MeshRenderer>().sharedMaterials = sourceRenderer.sharedMaterials;
                var saved = PrefabUtility.SaveAsPrefabAsset(fixture, prefabPath);
                Require(saved != null, "High-wall validation Prefab creation failed");
                replacements.Add(prefab, saved);
            }
            finally { if (fixture != null) UnityEngine.Object.DestroyImmediate(fixture); }
            meshPaths.Add(meshPath); prefabPaths.Add(prefabPath);
        }
        Require(replacements.Count == 3, "Expected independent straight/convex/concave high-wall sources");
        var clone = UnityEngine.Object.Instantiate(source);
        try
        {
            clone.name = source.name + "_HighWallValidationOnly";
            var serialized = new SerializedObject(clone);
            var property = serialized.GetIterator();
            int changed = 0;
            while (property.Next(true))
            {
                if (property.name != "_prefab" || property.propertyType != SerializedPropertyType.ObjectReference
                    || property.objectReferenceValue is not GameObject original || !replacements.TryGetValue(original, out var replacement)) continue;
                string parent = property.propertyPath.Substring(0, property.propertyPath.Length - "._prefab".Length);
                property.objectReferenceValue = replacement;
                serialized.FindProperty(parent + "._heightType").enumValueIndex = (int)StreetBuildingModuleHeightType.Absolute;
                serialized.FindProperty(parent + "._absoluteHeight").floatValue = targetHeight;
                changed++;
            }
            Require(changed == 3, "High-wall fixture did not replace exactly three material entries");
            serialized.ApplyModifiedPropertiesWithoutUndo();
            Require(StreetBuildingStyleValidator.Validate(clone, true).IsValid, "High-wall validation material clone is invalid");
            evidence = new HighWallEvidence {
                requestedHeight = targetHeight,
                roofY = source.GroundFloorHeight + (floors - 1) * source.TypicalFloorHeight,
                fixtureMeshPaths = meshPaths.ToArray(), fixturePrefabPaths = prefabPaths.ToArray()
            };
            return clone;
        }
        catch { UnityEngine.Object.DestroyImmediate(clone); throw; }
    }

    static Bounds InRootBounds(GameObject instance, MeshFilter filter)
    {
        Matrix4x4 matrix = instance.transform.worldToLocalMatrix * filter.transform.localToWorldMatrix;
        var local = filter.sharedMesh.bounds;
        var bounds = new Bounds();
        for (int corner = 0; corner < 8; corner++)
        {
            Vector3 point = matrix.MultiplyPoint3x4(local.center + Vector3.Scale(local.extents,
                new Vector3((corner & 1) == 0 ? -1 : 1, (corner & 2) == 0 ? -1 : 1, (corner & 4) == 0 ? -1 : 1)));
            if (corner == 0) bounds = new Bounds(point, Vector3.zero); else bounds.Encapsulate(point);
        }
        return bounds;
    }

    static void ValidateHighWallGeometry(GameObject instance, HighWallEvidence evidence)
    {
        if (evidence == null) return;
        Require(evidence.fixtureMeshPaths?.Length == 3 && evidence.fixturePrefabPaths?.Length == 3,
            "High-wall case lacks persistent validation input evidence");
        var meshes = evidence.fixtureMeshPaths.Select(path => AssetDatabase.LoadAssetAtPath<Mesh>(path)).ToHashSet();
        Require(meshes.Count == 3 && !meshes.Contains(null), "High-wall source Mesh references did not survive");
        foreach (string path in evidence.fixturePrefabPaths)
            Require(AssetDatabase.LoadAssetAtPath<GameObject>(path) != null, "High-wall source Prefab is missing: " + path);
        var walls = instance.GetComponentsInChildren<MeshFilter>(true).Where(filter => meshes.Contains(filter.sharedMesh)).ToArray();
        Require(walls.Length > 0, "High-wall source geometry is absent from the actual generated/Baked building");
        var wallBounds = walls.Select(filter => InRootBounds(instance, filter)).ToArray();
        foreach (var bounds in wallBounds)
            Require(Mathf.Abs(bounds.min.y - evidence.roofY) <= .001f
                && bounds.size.y >= evidence.requestedHeight - .001f
                && Mathf.Abs(bounds.max.y - evidence.roofY - evidence.requestedHeight) <= .001f,
                "Actual high-wall Mesh does not reach the requested 1.2m above the roof");
        var style = AssetDatabase.LoadAssetAtPath<StreetBuildingStyleConfig>(Style);
        var ladderMeshes = style.EnumerateLayerModules().Where(entry => entry.Module.Enabled
            && entry.Module.AttachmentSubtype == StreetBuildingAttachmentSubtype.RoofAccess)
            .SelectMany(entry => entry.Module.Prefab.GetComponentsInChildren<MeshFilter>(true)).Select(filter => filter.sharedMesh).ToHashSet();
        var ladders = instance.GetComponentsInChildren<MeshFilter>(true).Where(filter => ladderMeshes.Contains(filter.sharedMesh)).ToArray();
        Require(ladders.Length > 0, "High-wall case has no actual roof-access ladder Mesh");
        float wallTop = wallBounds.Max(bounds => bounds.max.y);
        int checkedTriangles = 0;
        foreach (var ladder in ladders)
        {
            Require(InRootBounds(instance, ladder).max.y >= wallTop + .01f,
                "Actual roof-access ladder does not extend beyond the actual high-wall top");
            Matrix4x4 matrix = instance.transform.worldToLocalMatrix * ladder.transform.localToWorldMatrix;
            var vertices = ladder.sharedMesh.vertices.Select(point => matrix.MultiplyPoint3x4(point)).ToArray();
            for (int submesh = 0; submesh < ladder.sharedMesh.subMeshCount; submesh++)
            {
                var indices = ladder.sharedMesh.GetTriangles(submesh);
                for (int index = 0; index < indices.Length; index += 3)
                {
                    var triangle = new Bounds(vertices[indices[index]], Vector3.zero);
                    triangle.Encapsulate(vertices[indices[index + 1]]); triangle.Encapsulate(vertices[indices[index + 2]]);
                    if (triangle.max.y < evidence.roofY - .001f) continue;
                    checkedTriangles++;
                    // Conservative triangle AABB proof: every upper ladder
                    // triangle must stay outside every actual wall volume.
                    foreach (var wall in wallBounds)
                        Require(!(triangle.max.x > wall.min.x + .001f && triangle.min.x < wall.max.x - .001f
                            && triangle.max.y > wall.min.y + .001f && triangle.min.y < wall.max.y - .001f
                            && triangle.max.z > wall.min.z + .001f && triangle.min.z < wall.max.z - .001f),
                            "An actual upper roof-ladder triangle enters the high-wall/cap envelope");
                }
            }
        }
        Require(checkedTriangles > 0, "No actual upper ladder geometry was checked");
        evidence.measuredHeight = wallBounds.Min(bounds => bounds.size.y);
        evidence.wallTop = wallTop;
        evidence.ladderTop = ladders.Min(filter => InRootBounds(instance, filter).max.y);
        evidence.ladderCapClearance = evidence.ladderTop - wallTop;
        evidence.actualWallInstances = walls.Length;
        evidence.actualRoofLadders = ladders.Length;
        evidence.upperLadderTrianglesChecked = checkedTriangles;
    }
    static void SetInt(HEU_HoudiniAsset asset, string name, int value)
    {
        var session=asset.GetAssetSession(false);
        var parameter = asset.Parameters.GetParameter(name);
        var native = parameter?._parmInfo ?? default;
        if (parameter == null)
        {
            var node=new HAPI_NodeInfo();Require(session.GetNodeInfo(asset.AssetID,ref node,false),"HAPI node unavailable");
            var parameters=new HAPI_ParmInfo[node.parmCount];Require(session.GetParams(asset.AssetID,parameters,0,parameters.Length),"HAPI parameter schema unavailable");
            var matches=parameters.Where(p=>HEU_SessionManager.GetString(p.nameSH,session)==name).ToArray();
            Require(matches.Length==1,"Missing or duplicate HAPI parameter: "+name);native=matches[0];
        }
        Require((int)native.type>=(int)HAPI_ParmType.HAPI_PARMTYPE_INT_START && (int)native.type<=(int)HAPI_ParmType.HAPI_PARMTYPE_INT_END
            && native.intValuesIndex>=0,"Invalid integer parameter storage: "+name+" / "+native.type);
        var values=new[]{value};Require(session.SetParamIntValues(asset.AssetID,ref values,native.intValuesIndex,1),"HAPI rejected "+name);
        if (parameter == null) return;
        if (parameter._intValues?.Length > 0) parameter._intValues[0] = value;
        parameter._toggle = value != 0;
        if (parameter._choiceIntValues != null) parameter._choiceValue = Array.IndexOf(parameter._choiceIntValues, value);
        else parameter._choiceValue = value;
        if (parameter._parmInfo.type == HAPI_ParmType.HAPI_PARMTYPE_MULTIPARMLIST) parameter._parmInfo.instanceCount = value;
    }
    static void SetFloat(HEU_HoudiniAsset asset, string name, float value)
    {
        Require(asset.GetAssetSession(false).SetParamFloatValue(asset.AssetID, name, 0, value), "HAPI rejected " + name);
        var parameter = asset.Parameters.GetParameter(name);
        if (parameter?._floatValues?.Length > 0) parameter._floatValues[0] = value;
    }
    static string DetailString(HEU_SessionBase session, int geoId, int partId, string name)
    {
        var info = new HAPI_AttributeInfo();
        if (!session.GetAttributeInfo(geoId, partId, name, HAPI_AttributeOwner.HAPI_ATTROWNER_DETAIL, ref info) || !info.exists)
            return null;
        var handles = new int[info.count * info.tupleSize];
        if (handles.Length == 0 || !session.GetAttributeStringData(geoId, partId, name, ref info, handles, 0, info.count))
            return null;
        return HEU_SessionManager.GetString(handles[0], session);
    }
    static string[] PointStrings(HEU_SessionBase session, int geoId, int partId, string name)
    {
        var info = new HAPI_AttributeInfo();
        if (!session.GetAttributeInfo(geoId, partId, name, HAPI_AttributeOwner.HAPI_ATTROWNER_POINT, ref info) || !info.exists)
            return Array.Empty<string>();
        var handles = new int[info.count * info.tupleSize];
        Require(session.GetAttributeStringData(geoId, partId, name, ref info, handles, 0, info.count), "Unreadable point attribute " + name);
        return handles.Select(handle => HEU_SessionManager.GetString(handle, session)).ToArray();
    }
    static int[] PointInts(HEU_SessionBase session, int geoId, int partId, string name)
    {
        var info = new HAPI_AttributeInfo();
        if (!session.GetAttributeInfo(geoId, partId, name, HAPI_AttributeOwner.HAPI_ATTROWNER_POINT, ref info) || !info.exists)
            return Array.Empty<int>();
        Require(info.tupleSize == 1, "Unexpected tuple size for point attribute " + name);
        var values = new int[info.count];
        Require(session.GetAttributeIntData(geoId, partId, name, ref info, values, 0, info.count),
            "Unreadable point attribute " + name);
        return values;
    }
    static float[] PointFloats(HEU_SessionBase session, int geoId, int partId, string name, int tupleSize)
    {
        var info = new HAPI_AttributeInfo();
        Require(session.GetAttributeInfo(geoId, partId, name, HAPI_AttributeOwner.HAPI_ATTROWNER_POINT, ref info)
            && info.exists && info.tupleSize == tupleSize, "Missing/wrong-size actual pipe transform attribute: " + name);
        var values = new float[info.count * tupleSize];
        Require(session.GetAttributeFloatData(geoId, partId, name, ref info, values, 0, info.count), "Cannot read actual pipe transform: " + name);
        return values;
    }
    static void CapturePipePoint(Dictionary<string, PipeGroupEvidence> groups, string group, string path, int subtype,
        float[] positions, float[] orientations, float[] scales, int pointIndex, Dictionary<Material, string> materialProofs)
    {
        var scale = new Vector3(scales[pointIndex * 3], scales[pointIndex * 3 + 1], scales[pointIndex * 3 + 2]);
        if (subtype == 8)
            Require(Mathf.Abs(scale.x - 1) < .0001f && Mathf.Abs(scale.z - 1) < .0001f
                && scale.y >= .05f - .0001f && scale.y <= 1.0001f, "Straight pipe changed radial diameter or exceeded supported axial length");
        else Require((scale - Vector3.one).sqrMagnitude < .00000001f, "Pipe elbow/inlet/outlet must retain unit scale");
        var source = AssetDatabase.LoadAssetAtPath<GameObject>(path);
        Require(source != null && source.transform.localScale == Vector3.one && source.transform.localRotation == Quaternion.identity,
            "Pipe source has a missing or unsupported root transform: " + path);
        var filters = source.GetComponentsInChildren<MeshFilter>(true);
        Require(filters.Length > 0 && filters.All(filter => filter.sharedMesh != null && IsPersistentAsset(AssetDatabase.GetAssetPath(filter.sharedMesh))),
            "Pipe source is missing persistent geometry: " + path);
        var hapi = new HAPI_Transform(true);
        Array.Copy(positions, pointIndex * 3, hapi.position, 0, 3);
        Array.Copy(orientations, pointIndex * 4, hapi.rotationQuaternion, 0, 4);
        Array.Copy(scales, pointIndex * 3, hapi.scale, 0, 3);
        var placement = HEU_HAPIUtility.GetMatrixFromHAPITransform(ref hapi);
        if (!groups.TryGetValue(group, out var evidence)) groups.Add(group, evidence = new PipeGroupEvidence());
        evidence.sourcePoints++; evidence.sourceMeshFilters += filters.Length;
        evidence.subtypes[subtype] = evidence.subtypes.GetValueOrDefault(subtype) + 1;
        foreach (var filter in filters)
            evidence.triangles.AddRange(PipeTriangles(filter,
                placement * source.transform.worldToLocalMatrix * filter.transform.localToWorldMatrix, materialProofs));
    }
    static string AttachmentKind(int subtype) => subtype switch {
        1 => "WaterTower", 2 => "Chimney", >= 3 and <= 7 => "FireEscape",
        >= 8 and <= 12 => "DrainPipe", >= 13 and <= 15 => "FireEscape", _ => null
    };
    static int FireEscapeFaceMask(string caseName)
    {
        if (caseName.IndexOf("SecondaryEscape", StringComparison.OrdinalIgnoreCase) >= 0) return 2;
        if (caseName.IndexOf("FrontEscape", StringComparison.OrdinalIgnoreCase) >= 0) return 1;
        if (caseName.IndexOf("SideEscape", StringComparison.OrdinalIgnoreCase) >= 0) return 4;
        if (caseName.IndexOf("MultiEscape", StringComparison.OrdinalIgnoreCase) >= 0) return 5;
        return 8;
    }
    static bool AllowsFireEscapeFace(int mask, int face, string surface)
    {
        // Physical face ids and semantic mask bits differ for secondary frontage.
        int bit = surface == "secondary_front" ? 2
            : face == 0 ? 1 : face == 1 || face == 2 ? 4 : face == 3 ? 8 : 0;
        return bit != 0 && (mask & bit) != 0;
    }
    static AttachmentOutput Output(HEU_HoudiniAsset asset, int fireEscapeFaceMask)
    {
        var session = asset.GetAssetSession(false);
        var core = asset.GetObjectNodeByName("StreetBuildingCore");
        Require(session != null && core != null, "HAPI output unavailable");
        var roles = new List<string>();
        var paths = new List<string>();
        var referencePoints = new List<(string role, string path, int subtype, string group, int face, string surface)>();
        var pipeGroups = new Dictionary<string, PipeGroupEvidence>(StringComparer.Ordinal);
        var pipeMaterials = new Dictionary<Material, string>();
        int detailParts = 0, detailPoints = 0;
        string diagnostic = null;
        foreach (var geo in core.GeoNodes)
        foreach (var part in geo.GetParts())
        {
            if (geo.GeoName == "OUT_DETAIL_INSTANCES")
            {
                var info = new HAPI_PartInfo();
                Require(session.GetPartInfo(geo.GeoID, part.PartID, ref info), "Cannot inspect actual detail HAPI part");
                if (info.pointCount <= 0) continue;
                detailParts++; detailPoints += info.pointCount;
                var partRoles = PointStrings(session, geo.GeoID, part.PartID, "module_role");
                var partPaths = PointStrings(session, geo.GeoID, part.PartID, "unity_instance");
                var subtypes = PointInts(session, geo.GeoID, part.PartID, "attachment_subtype");
                var groups = PointStrings(session, geo.GeoID, part.PartID, "attachment_group_id");
                var faces = PointInts(session, geo.GeoID, part.PartID, "face_index");
                var surfaces = PointStrings(session, geo.GeoID, part.PartID, "surface_role");
                Require(partRoles.Length == info.pointCount && partPaths.Length == info.pointCount,
                    "Actual detail point count differs from role/path attribute counts");
                Require((subtypes.Length == 0 && groups.Length == 0)
                    || (subtypes.Length == info.pointCount && groups.Length == info.pointCount),
                    "Incomplete attachment subtype/group point attributes");
                Require(subtypes.Length == 0 || (faces.Length == info.pointCount && surfaces.Length == info.pointCount),
                    "Reference attachment output lacks complete physical face/surface attributes");
                bool hasPipes = subtypes.Any(subtype => subtype >= 8 && subtype <= 12);
                var positions = hasPipes ? PointFloats(session, geo.GeoID, part.PartID, "P", 3) : null;
                var orientations = hasPipes ? PointFloats(session, geo.GeoID, part.PartID, "orient", 4) : null;
                var scales = hasPipes ? PointFloats(session, geo.GeoID, part.PartID, "scale", 3) : null;
                Require(!hasPipes || (positions.Length == info.pointCount * 3 && orientations.Length == info.pointCount * 4 && scales.Length == info.pointCount * 3),
                    "Actual HAPI pipe transform arrays are incomplete");
                roles.AddRange(partRoles); paths.AddRange(partPaths);
                for (int index = 0; index < subtypes.Length; index++)
                {
                    if (subtypes[index] == 0)
                    {
                        Require(string.IsNullOrEmpty(groups[index]), "A reference attachment group has no subtype");
                        continue;
                    }
                    Require(AttachmentKind(subtypes[index]) != null && !string.IsNullOrEmpty(groups[index]),
                        "Reference attachment point has an unknown subtype or missing group");
                    referencePoints.Add((partRoles[index], partPaths[index], subtypes[index], groups[index], faces[index], surfaces[index]));
                    if (subtypes[index] >= 8 && subtypes[index] <= 12)
                        CapturePipePoint(pipeGroups, groups[index], partPaths[index], subtypes[index], positions, orientations, scales, index, pipeMaterials);
                }
            }
            if (geo.GeoName == "OUT_BUILDING_METADATA")
                diagnostic = DetailString(session, geo.GeoID, part.PartID, "reference_attachment_diagnostics") ?? diagnostic;
        }
        Require(roles.Count == paths.Count && roles.Count == detailPoints, "Role/path point count mismatch");
        Require(roles.All(role => !string.IsNullOrEmpty(role)) && paths.All(path => path.StartsWith("Assets/", StringComparison.Ordinal)),
            "Generated attachment paths are not stable Unity assets");
        Require(!string.IsNullOrEmpty(diagnostic) && diagnostic.StartsWith("v1\n",StringComparison.Ordinal),
            "Missing reference attachment diagnostics");
        var rows = new Dictionary<string,(int requested,int actual,string reason)>(StringComparer.Ordinal);
        foreach (var line in diagnostic.Split('\n').Skip(1).Where(line=>!string.IsNullOrWhiteSpace(line)))
        {
            var columns = line.Split('|');
            Require(columns.Length==6 && columns[0]=="R" && !rows.ContainsKey(columns[1])
                && int.TryParse(columns[2],out int _) && int.TryParse(columns[3],out int __)
                && !string.IsNullOrEmpty(columns[4]) && !string.IsNullOrEmpty(columns[5]),
                "Malformed reference attachment diagnostic: " + line);
            int requested=int.Parse(columns[2]), actual=int.Parse(columns[3]);
            Require(requested>=0 && actual>=0 && actual<=requested,"Invalid requested/actual count: "+line);
            Require(actual == requested || columns[4] != "none", "Rejected attachment lacks a reason: " + line);
            rows.Add(columns[1],(requested,actual,columns[4]));
        }
        Require(new[]{"WaterTower","Chimney","FireEscape","DrainPipe"}.All(rows.ContainsKey) && rows.Count==4,
            "Incomplete reference attachment diagnostics");
        Require(!rows.Values.Any(row => row.actual > 0) || (detailParts > 0 && detailPoints > 0 && referencePoints.Count > 0),
            "Attachment diagnostics report generated groups, but OUT_DETAIL_INSTANCES has no actual reference points");
        var style = AssetDatabase.LoadAssetAtPath<StreetBuildingStyleConfig>(Style);
        Require(style != null, "Cannot resolve actual attachment material metadata");
        var materialSubtypes = style.EnumerateLayerModules().Where(entry => entry.Module.Prefab != null)
            .GroupBy(entry => AssetDatabase.GetAssetPath(entry.Module.Prefab), StringComparer.Ordinal)
            .ToDictionary(group => group.Key, group => group.Select(entry => (int)entry.Module.AttachmentSubtype).Distinct().ToArray(), StringComparer.Ordinal);
        foreach (var point in referencePoints)
        {
            Require(materialSubtypes.TryGetValue(point.path, out var declared) && declared.Length == 1 && declared[0] == point.subtype,
                "Actual attachment path/subtype differs from its material metadata: " + point.path);
            string kind = AttachmentKind(point.subtype);
            string expectedRole = kind is "WaterTower" or "Chimney" ? "RoofProp" : kind;
            Require(point.role == expectedRole, "Actual attachment role/subtype mismatch: " + point.path);
            if (kind == "FireEscape")
                Require(AllowsFireEscapeFace(fireEscapeFaceMask, point.face, point.surface),
                    "Actual fire escape point is outside selected whole-building face mask " + fireEscapeFaceMask
                    + ": face=" + point.face + ", surface=" + point.surface + ", group=" + point.group + ", path=" + point.path);
        }
        var verifiedGroups = rows.Keys.ToDictionary(kind => kind,
            kind => referencePoints.Where(point => AttachmentKind(point.subtype) == kind).Select(point => point.group).Distinct().Count(),
            StringComparer.Ordinal);
        foreach (var pair in verifiedGroups)
            Require(pair.Value == rows[pair.Key].actual,
                "Attachment diagnostic/actual group mismatch for " + pair.Key + ": report " + rows[pair.Key].actual + ", points " + pair.Value);
        foreach (var group in referencePoints.GroupBy(point => point.group, StringComparer.Ordinal))
        {
            string[] kinds = group.Select(point => AttachmentKind(point.subtype)).Distinct().ToArray();
            Require(kinds.Length == 1, "Attachment group mixes unrelated subtypes: " + group.Key);
            if (kinds[0] is "WaterTower" or "Chimney")
                Require(group.Count() == 1, "Complete roof attachment was counted as several pieces: " + group.Key);
            if (kinds[0] == "FireEscape")
            {
                Require(group.Count(point => point.subtype == 5) == 1 && group.Count(point => point.subtype == 6) == 1,
                    "Continuous fire escape group is missing a unique top/bottom termination: " + group.Key);
                Require(group.Select(point => (point.face, point.surface)).Distinct().Count() == 1,
                    "One whole-building fire escape group spans unrelated physical walls: " + group.Key);
            }
            if (kinds[0] == "DrainPipe")
                Require(group.Count(point => point.subtype == 9) == 1 && group.Count(point => point.subtype == 10) == 1
                    && group.Any(point => point.subtype == 8), "Drain pipe group is missing its complete actual path: " + group.Key);
        }
        return new AttachmentOutput {
            diagnostic = diagnostic,
            requested = rows.ToDictionary(pair=>pair.Key,pair=>pair.Value.requested),
            actual = rows.ToDictionary(pair=>pair.Key,pair=>pair.Value.actual),
            reasons = rows.ToDictionary(pair=>pair.Key,pair=>pair.Value.reason),
            detailPoints = detailPoints,
            detailParts = detailParts,
            roles = roles.GroupBy(role => role).ToDictionary(group => group.Key, group => group.Count()),
            sourcePrefabs = paths.Distinct().OrderBy(path => path).ToArray(),
            referenceSourcePrefabs = referencePoints.Select(point => point.path).Distinct().OrderBy(path => path).ToArray(),
            sourcePrefabCounts = paths.GroupBy(path => path, StringComparer.Ordinal).ToDictionary(group => group.Key, group => group.Count(), StringComparer.Ordinal),
            verifiedGroups = verifiedGroups,
            subtypePoints = referencePoints.GroupBy(point => point.subtype).ToDictionary(group => group.Key, group => group.Count()),
            fireEscapeFaceMask = fireEscapeFaceMask,
            actualFaceIds = rows.Keys.ToDictionary(kind => kind,
                kind => referencePoints.Where(point => AttachmentKind(point.subtype) == kind).Select(point => point.face).Distinct().OrderBy(face => face).ToArray(),
                StringComparer.Ordinal),
            actualSurfaceRoles = rows.Keys.ToDictionary(kind => kind,
                kind => referencePoints.Where(point => AttachmentKind(point.subtype) == kind).Select(point => point.surface).Distinct().OrderBy(surface => surface).ToArray(),
                StringComparer.Ordinal),
            pipeGroups = pipeGroups
        };
    }
    static void AssertCaseCounts(string caseName, AttachmentOutput output)
    {
        int expectedGroups = caseName.IndexOf("Narrow", StringComparison.OrdinalIgnoreCase) >= 0 ? 2 : 1;
        Require(output.fireEscapeFaceMask == FireEscapeFaceMask(caseName) && output.requested["FireEscape"] == expectedGroups
            && output.verifiedGroups["FireEscape"] <= expectedGroups,
            "Selected fire escape faces multiplied the whole-building request: " + output.diagnostic);
        if (caseName.IndexOf("FrontEscape", StringComparison.OrdinalIgnoreCase) >= 0
            || caseName.IndexOf("SecondaryEscape", StringComparison.OrdinalIgnoreCase) >= 0
            || caseName.IndexOf("SideEscape", StringComparison.OrdinalIgnoreCase) >= 0
            || caseName.IndexOf("MultiEscape", StringComparison.OrdinalIgnoreCase) >= 0)
            Require(output.actual["FireEscape"] == 1 && output.verifiedGroups["FireEscape"] == 1,
                "Positive selected-face case did not emit exactly one complete fire escape group: " + output.diagnostic);
        if (caseName.IndexOf("Benchmark", StringComparison.OrdinalIgnoreCase) >= 0)
        {
            var exact = new Dictionary<string, int> {
                ["WaterTower"] = 1, ["Chimney"] = 2, ["FireEscape"] = 1, ["DrainPipe"] = 2
            };
            foreach (var pair in exact)
                Require(output.requested[pair.Key] == pair.Value && output.actual[pair.Key] == pair.Value,
                    "Benchmark request/output mismatch for " + pair.Key + ": " + output.diagnostic);
        }
        if (caseName.IndexOf("Narrow", StringComparison.OrdinalIgnoreCase) >= 0)
            Require(output.requested.Keys.Any(key => output.actual[key] < output.requested[key]
                && output.reasons[key] != "none"),
                "Narrow case did not exercise a reported capacity rejection: " + output.diagnostic);
        if (caseName.IndexOf("RoofAccess", StringComparison.OrdinalIgnoreCase) >= 0)
            Require(output.actual["FireEscape"] == output.requested["FireEscape"] && output.actual["FireEscape"] > 0
                && output.subtypePoints.GetValueOrDefault((int)StreetBuildingAttachmentSubtype.RoofAccess) == output.actual["FireEscape"],
                "Positive roof-access case did not generate one actual roof ladder per complete group: " + output.diagnostic);
        if (caseName.IndexOf("HighParapet", StringComparison.OrdinalIgnoreCase) >= 0)
            Require(output.actual.All(pair => pair.Value == output.requested[pair.Key] && pair.Value > 0),
                "High-parapet case did not retain complete actual attachment groups: " + output.diagnostic);
    }
    static void Configure(HEU_HoudiniAsset asset, float width, float depth, int floors, int shape, int notchSide)
    {
        foreach (var pair in new Dictionary<string, int> {
            ["random_algorithm"]=1,["site_source"]=0,["site_source_auto"]=0,
            ["massing_shape"]=shape,["floor_count"]=floors,
            ["l_notch_units"]=1,["l_notch_width_cells"]=2,["l_notch_depth_cells"]=2,["l_notch_side"]=notchSide,
            ["variation_seed"]=29,["layout_seed"]=137,["ground_rule_schema_version"]=2,
            ["ground_floor_use"]=2,["ground_quantity_mode"]=0,["entrance_count_min"]=1,["entrance_count_max"]=1,
            ["shopfront_control"]=0,["shopfront_quantity_mode"]=0,["shopfront_count"]=3,
            ["shopfront_face_0"]=1,["shopfront_face_1"]=0,
            ["shopfront_face_2"]=0,["shopfront_face_3"]=0,["facade_layout_mode"]=0,
            ["facade_rhythm"]=1,["lod_outputs_enabled"]=0,["window_count_min"]=2,
            ["window_count_max"]=3,["facade_overrides"]=0,["attachment_overrides"]=0,["attachments_enabled"]=1,
            ["roof_enabled"]=1,["parapet_enabled"]=1,["architectural_trim_enabled"]=1,["rear_facade_mode"]=2,
            ["roof_props_layout_mode"]=1,["water_tower_count"]=1,["chimney_count"]=2,
            ["fire_escape_layout_mode"]=1,["fire_escape_group_count"]=1,["fire_escape_face_mask"]=8,
            ["fire_escape_floor_start"]=2,["fire_escape_floor_end"]=floors,["fire_escape_roof_access"]=0,
            ["drainpipe_enabled"]=1,["drainpipe_count"]=2,["drainpipe_face_mask"]=12
        }) SetInt(asset, pair.Key, pair.Value);
        SetFloat(asset,"building_width",width);
        SetFloat(asset,"building_depth",depth);
        SetFloat(asset,"parapet_height",.6f);
        SetFloat(asset,"shopfront_ratio",0f); // Inactive ratio must not alter fixed commercial frontage.
        SetFloat(asset,"attachment_global_density",1f);
        SetFloat(asset,"fire_escape_density",0f); // Prove fixed mode ignores legacy sampling.
        SetFloat(asset,"roof_props_density",0f);
        SetFloat(asset,"wall_ac_density",0f);
    }
    public static object Probe(string outputDir)
    {
        var gallery = FindGallery(outputDir);
        Require(gallery.IsValid() && SceneManager.GetActiveScene() == gallery, "Activate the saved gallery first");
        var oldSession = HEU_SessionManager.GetDefaultSession();
        var field = typeof(HEU_SessionManager).GetField("_defaultSession", PrivateStatic);
        var session = HEU_SessionManager.CreateSessionObject();
        GameObject temporary = null;
        object result;
        try
        {
            var listener = new System.Net.Sockets.TcpListener(System.Net.IPAddress.Loopback, 0);
            listener.Start(); int port = ((System.Net.IPEndPoint)listener.LocalEndpoint).Port; listener.Stop();
            string oldThreads = Environment.GetEnvironmentVariable("HOUDINI_MAXTHREADS");
            try { Environment.SetEnvironmentVariable("HOUDINI_MAXTHREADS", "1"); Require(session.CreateThriftSocketSession(false,"localhost",port,true,10000,true),"HARS startup failed"); }
            finally { Environment.SetEnvironmentVariable("HOUDINI_MAXTHREADS",oldThreads); }
            field.SetValue(null,session);
            string probeHda=SessionState.GetString("PCG.StreetBuilding.ContractHda",Hda);
            temporary = HEU_HAPIUtility.InstantiateHDA(probeHda,Vector3.zero,session,false,bLoadFromMemory:false,bAlwaysOverwriteOnLoad:true);
            Require(temporary != null,"Probe HDA unavailable");
            SceneManager.MoveGameObjectToScene(temporary,gallery);
            var root = temporary.GetComponent<HEU_HoudiniAssetRoot>();
            var asset = root.HoudiniAsset;
            var author = temporary.AddComponent<StreetBuildingAuthoring>();
            author.SetEditorFixedStyle(AssetDatabase.LoadAssetAtPath<StreetBuildingStyleConfig>(Style));
            var so = new SerializedObject(author); so.FindProperty("_randomizeOnRecook").boolValue=false; so.ApplyModifiedPropertiesWithoutUndo();
            Configure(asset,8,10,3,0,0);
            var beforeModes=new Dictionary<string,object>();
            foreach(string key in new[]{"roof_props_layout_mode","fire_escape_layout_mode","drainpipe_enabled","attachments_enabled","water_tower_count"})
            { session.GetParamIntValue(asset.AssetID,key,0,out int value);var p=asset.Parameters.GetParameter(key);beforeModes[key]=new{value,cacheExists=p!=null,choice=p?._choiceValue,choices=p?._choiceIntValues,ints=p?._intValues,toggle=p?._toggle}; }
            var probeStyle=author.ResolveStyle();
            var compiled=StreetBuildingStyleCompiler.Compile(probeStyle);
            typeof(StreetBuildingStyleApplier).GetMethod("Write",PrivateStatic).Invoke(null,new object[]{asset,probeStyle,compiled.Payload});
            Require(asset.RequestCook(true,false,true,true),"Raw probe cook failed");
            var geos = new List<object>();
            foreach(var geo in asset.GetObjectNodeByName("StreetBuildingCore").GeoNodes)
            foreach(var part in geo.GetParts())
            {
                var info = new HAPI_PartInfo(); session.GetPartInfo(geo.GeoID,part.PartID,ref info);
                geos.Add(new {geo.GeoName,geo.GeoID,part.PartID,info.type,info.pointCount,info.vertexCount,info.faceCount,
                    roles=PointStrings(session,geo.GeoID,part.PartID,"module_role"),
                    paths=PointStrings(session,geo.GeoID,part.PartID,"unity_instance"),
                    reference=DetailString(session,geo.GeoID,part.PartID,"reference_attachment_diagnostics")});
            }
            var internalGeos = new List<object>();
            int childCount=0;
            session.ComposeChildNodeList(asset.AssetID,(int)HAPI_NodeType.HAPI_NODETYPE_SOP,(int)HAPI_NodeFlags.HAPI_NODEFLAGS_ANY,true,ref childCount);
            var ids=new int[childCount];session.GetComposedChildNodeList(asset.AssetID,ids,childCount);
            foreach(int id in ids)
            {
                var ni=new HAPI_NodeInfo();session.GetNodeInfo(id,ref ni,false);
                string name=HEU_SessionManager.GetString(ni.nameSH,session);
                if(!name.StartsWith("OUT_",StringComparison.Ordinal) && name!="ATTACHMENT_DIAGNOSTICS" && name!="VALIDATE_DIRECT_DETAIL_INSTANCES" && name!="DETAIL_MODULE_SOURCE_SWITCH")continue;
                var gi=new HAPI_GeoInfo(); bool readable=session.GetGeoInfo(id,ref gi,false);
                var parts=new List<object>();
                for(int p=0;readable && p<gi.partCount;p++)
                { var pi=new HAPI_PartInfo();session.GetPartInfo(id,p,ref pi);parts.Add(new{pi.type,pi.pointCount,pi.vertexCount,paths=PointStrings(session,id,p,"unity_instance")}); }
                int selected=-99;bool hasInput=name=="DETAIL_MODULE_SOURCE_SWITCH" && session.GetParamIntValue(id,"input",0,out selected);
                internalGeos.Add(new{name,id,readable,gi.partCount,parts,hasInput,selected});
            }
            session.GetParamIntValue(asset.AssetID,"module_source",0,out int source);
            var ai=new HAPI_AssetInfo();session.GetAssetInfo(asset.AssetID,ref ai);
            var afterModes=new Dictionary<string,int>();
            foreach(string key in beforeModes.Keys){session.GetParamIntValue(asset.AssetID,key,0,out int value);afterModes[key]=value;}
            var nodeInfo=new HAPI_NodeInfo();session.GetNodeInfo(asset.AssetID,ref nodeInfo,false);
            var parameters=new HAPI_ParmInfo[nodeInfo.parmCount];session.GetParams(asset.AssetID,parameters,0,parameters.Length);
            var rawParameters=new List<object>();
            foreach(var p in parameters){string name=HEU_SessionManager.GetString(p.nameSH,session);if(!beforeModes.ContainsKey(name))continue;var values=new int[1];if(p.intValuesIndex>=0)session.GetParamIntValues(asset.AssetID,values,p.intValuesIndex,1);rawParameters.Add(new{name,p.id,p.parentId,p.intValuesIndex,p.type,p.invisible,value=values[0]});}
            result = new {probeHda,asset.AssetPath,assetName=HEU_SessionManager.GetString(ai.nameSH,session),operatorName=HEU_SessionManager.GetString(ai.fullOpNameSH,session),loadedLibrary=HEU_SessionManager.GetString(ai.filePathSH,session),beforeModes,afterModes,rawParameters,source,cookDiagnostic=session.ComposeNodeCookResult(asset.AssetID,HAPI_StatusVerbosity.HAPI_STATUSVERBOSITY_ALL),geos,internalGeos,meshes=temporary.GetComponentsInChildren<MeshFilter>(true).Select(f=>AssetDatabase.GetAssetPath(f.sharedMesh)).Distinct().ToArray()};
        }
        finally
        {
            try { if(temporary!=null) UnityEngine.Object.DestroyImmediate(temporary); }
            finally { try { field.SetValue(null,oldSession); } finally { session.CloseSession(); } }
        }
        return Write(Path.Combine(outputDir,"hapi-probe.json"),result);
    }
    public static object BuildCase(string outputDir, string caseName, float width, float depth, int floors, int shape, int notchSide)
    {
        Require(!string.IsNullOrWhiteSpace(caseName) && caseName != "." && caseName != ".."
            && caseName == Path.GetFileName(caseName)
            && caseName.IndexOfAny(Path.GetInvalidFileNameChars()) < 0, "Unsafe case name");
        string destination = BakeRoot(outputDir) + "/" + caseName;
        Require(AssetDatabase.IsValidFolder(destination), "Create bake destination first: " + destination);
        Require(!Directory.EnumerateFileSystemEntries(destination).Any(),
            "Bake destination already contains assets: " + destination);
        Directory.CreateDirectory(outputDir);
        string resultPath = Path.Combine(outputDir, caseName + ".json");
        Require(!File.Exists(resultPath), "Case evidence already exists: " + resultPath);
        var style = AssetDatabase.LoadAssetAtPath<StreetBuildingStyleConfig>(Style);
        Require(style != null && StreetBuildingStyleValidator.Validate(style, true).IsValid, "Style2 is incomplete");
        var previousScene = SceneManager.GetActiveScene();
        var gallery = FindGallery(outputDir);
        Require(gallery.IsValid() && gallery.path == ScenePath(outputDir),
            "Create/open the saved validation scene with Pipeline's scene command first");
        Require(previousScene == gallery, "Activate the validation scene through Pipeline before adding cases");
        Require(!gallery.GetRootGameObjects().Any(root => root.name == caseName),
            "Gallery already contains case: " + caseName);
        int gallerySlot = GallerySlot(caseName, gallery.rootCount);
        var previousSession = HEU_SessionManager.GetDefaultSession();
        var defaultSessionField = typeof(HEU_SessionManager).GetField("_defaultSession", PrivateStatic);
        Require(defaultSessionField != null, "Independent HAPI session adapter unavailable");
        var session = HEU_SessionManager.CreateSessionObject();
        GameObject temporary = null;
        GameObject bakedInstance = null;
        AttachmentOutput output = null;
        string prefabPath = null;
        StreetBuildingStyleConfig highWallStyle = null;
        var ownedWorkingCaches = new HashSet<string>(StringComparer.Ordinal);
        HighWallEvidence highWallFixture = null;
        float requestedParapetHeight = 0;
        try
        {
            bool highParapet = caseName.IndexOf("HighParapet", StringComparison.OrdinalIgnoreCase) >= 0;
            if (highParapet) highWallStyle = CreateHighWallFixture(style, destination, floors, out highWallFixture);
            var listener = new System.Net.Sockets.TcpListener(System.Net.IPAddress.Loopback, 0);
            listener.Start(); int port = ((System.Net.IPEndPoint)listener.LocalEndpoint).Port; listener.Stop();
            // Match the isolated cumulative tests: limit only this owned HARS startup.
            string previousThreads = Environment.GetEnvironmentVariable("HOUDINI_MAXTHREADS");
            try
            {
                Environment.SetEnvironmentVariable("HOUDINI_MAXTHREADS", "1");
                Require(session.CreateThriftSocketSession(false, "localhost", port, true, 10000, true),
                    "Independent HAPI session startup failed");
            }
            finally { Environment.SetEnvironmentVariable("HOUDINI_MAXTHREADS", previousThreads); }
            defaultSessionField.SetValue(null, session);
            temporary = HEU_HAPIUtility.InstantiateHDA(Hda, Vector3.zero, session, false, bLoadFromMemory:false, bAlwaysOverwriteOnLoad:true);
            Require(temporary != null, "Fresh locked HDA instance unavailable");
            SceneManager.MoveGameObjectToScene(temporary, gallery);
            var root = temporary.GetComponent<HEU_HoudiniAssetRoot>();
            Require(root != null && root.HoudiniAsset != null, "New HDA has no authorable asset root");
            var asset = root.HoudiniAsset;
            if(!string.IsNullOrEmpty(asset.AssetCacheFolder))ownedWorkingCaches.Add(asset.AssetCacheFolder.Replace('\\','/'));
            var author = temporary.GetComponent<StreetBuildingAuthoring>() ?? temporary.AddComponent<StreetBuildingAuthoring>();
            author.SetEditorFixedStyle(highWallStyle != null ? highWallStyle : style);
            var serializedAuthor = new SerializedObject(author);
            var randomize = serializedAuthor.FindProperty("_randomizeOnRecook");
            Require(randomize != null, "Authoring randomize control is unavailable");
            randomize.boolValue = false;
            serializedAuthor.ApplyModifiedPropertiesWithoutUndo();
            Configure(asset,width,depth,floors,shape,notchSide);
            if (caseName.StartsWith("Street_", StringComparison.Ordinal))
            {
                Require(int.TryParse(caseName.Substring(7), out int index) && index >= 0 && index < 32, "Invalid street sample identity");
                foreach (var item in new Dictionary<string,int> {
                    ["layout_seed"]=1009+index*137,["ground_attachment_placement"]=1,
                    ["water_tower_count_mode"]=1,["water_tower_count_min"]=0,["water_tower_count_max"]=1,
                    ["chimney_count_mode"]=1,["chimney_count_min"]=0,["chimney_count_max"]=3,
                    ["roof_prop_position_mode"]=1 }) SetInt(asset,item.Key,item.Value);
                string identity="StreetPresentation_"+index.ToString("D2",CultureInfo.InvariantCulture);
                Require(asset.GetAssetSession(false).SetParamStringValue(asset.AssetID,"random_instance_id",identity,0), "Cannot set stable street identity");
                var identityParameter=asset.Parameters.GetParameter("random_instance_id");
                if(identityParameter?._stringValues?.Length>0)identityParameter._stringValues[0]=identity;
            }
            int fireEscapeFaceMask = FireEscapeFaceMask(caseName);
            SetInt(asset,"fire_escape_face_mask",fireEscapeFaceMask);
            // A legal 4m rear wall has one 4m corridor. Request two groups to
            // exercise capacity reporting without violating the Style Cell grid.
            if (caseName.IndexOf("Narrow", StringComparison.OrdinalIgnoreCase) >= 0)
                SetInt(asset,"fire_escape_group_count",2);
            if (caseName.IndexOf("Benchmark", StringComparison.OrdinalIgnoreCase) >= 0)
            {
                SetInt(asset,"window_count_min",4);
                SetInt(asset,"window_count_max",4);
            }
            bool roofAccessEnabled = caseName.IndexOf("RoofAccess", StringComparison.OrdinalIgnoreCase) >= 0;
            if (roofAccessEnabled) SetInt(asset,"fire_escape_roof_access",1);
            if (highParapet) SetFloat(asset,"parapet_height",1.2f);
            StreetBuildingStyleApplier.ApplyAndSave(root,author,false);
            if(!string.IsNullOrEmpty(asset.AssetCacheFolder))ownedWorkingCaches.Add(asset.AssetCacheFolder.Replace('\\','/'));
            Require(session.GetParamFloatValue(asset.AssetID,"parapet_height",0,out requestedParapetHeight),
                "Actual HDA parapet height request is unreadable");
            output = Output(asset,fireEscapeFaceMask);
            AssertCaseCounts(caseName, output);
            if(caseName.StartsWith("Street_",StringComparison.Ordinal))
            {
                Require(output.requested["WaterTower"]>=0 && output.requested["WaterTower"]<=1
                    && output.requested["Chimney"]>=0 && output.requested["Chimney"]<=3,"Street roof quota escaped active range");
                Require(!output.actualFaceIds["FireEscape"].Contains(0)
                    && !output.actualSurfaceRoles["FireEscape"].Contains("secondary_front"),"Street sample put fire escape on frontage");
                foreach(var renderer in temporary.GetComponentsInChildren<MeshRenderer>(true))
                {
                    bool awning=false;
                    for(var transform=renderer.transform;transform!=null && transform!=temporary.transform;transform=transform.parent)
                        if(transform.name.Contains("Awning"))awning=true;
                    if(awning)Require(renderer.bounds.min.y>=2.35f-.001f,"Actual street awning has insufficient clearance");
                }
            }
            ValidateAttachmentMeshes(temporary, output); // Metadata cannot substitute for actual HEU instances.
            ValidateActualRoofFootprints(temporary,output);
            ValidateHighWallGeometry(temporary,highWallFixture);
            Require(StreetBuildingPartialBake.MissingSlotCount(asset) == 0,
                StreetBuildingPartialBake.MissingSummary(asset));
            StreetBuildingPartialBake.EnsureCanBake(author);
            // The caller creates this exact folder with Pipeline's typed asset
            // command; HEU's public Bake API is the only part without a typed command.
            var prefab = asset.BakeToNewPrefab(destination);
            Require(prefab != null, "Native HEU Bake failed");
            prefabPath = AssetDatabase.GetAssetPath(prefab);
            Require(IsPersistentAsset(prefabPath) && prefabPath.StartsWith(destination + "/", StringComparison.Ordinal),
                "Bake prefab is missing or outside the requested destination");
            bakedInstance = (GameObject)PrefabUtility.InstantiatePrefab(prefab,gallery);
            Require(bakedInstance != null, "Cannot instantiate baked prefab");
            bakedInstance.name = caseName;
            bakedInstance.transform.position = new Vector3((gallerySlot%5)*24,0,(gallerySlot/5)*26);
            ValidateNativeInstance(bakedInstance);
            ValidateAttachmentMeshes(bakedInstance, output, true);
            ValidateActualRoofFootprints(bakedInstance,output);
            ValidateHighWallGeometry(bakedInstance,highWallFixture);
            if (_runBakeUpdateProof) UpdateProof(asset, prefab, output, gallery);
            EditorSceneManager.MarkSceneDirty(gallery);
        }
        finally
        {
            // Every cleanup step must run even if the previous step throws; never write PASS first.
            try { if (temporary != null) UnityEngine.Object.DestroyImmediate(temporary); }
            finally
            {
                try { defaultSessionField.SetValue(null,previousSession); }
                finally
                {
                    try { session.CloseSession(); }
                    finally
                    {
                        try
                        {
                            if(previousScene.IsValid() && previousScene.isLoaded && SceneManager.GetActiveScene() != previousScene)
                                Require(SceneManager.SetActiveScene(previousScene), "Cannot restore original active scene");
                        }
                        finally { if (highWallStyle != null) UnityEngine.Object.DestroyImmediate(highWallStyle); }
                    }
                }
            }
        }
        ValidateNativeInstance(bakedInstance); // Baked references must survive closing this HAPI session.
        string[] attachmentMeshAssets = ValidateAttachmentMeshes(bakedInstance, output, true);
        ValidateActualRoofFootprints(bakedInstance,output);
        ValidateHighWallGeometry(bakedInstance,highWallFixture);
        var filters = bakedInstance.GetComponentsInChildren<MeshFilter>(true);
        var renderers = bakedInstance.GetComponentsInChildren<MeshRenderer>(true);
        var result = new { status="PASS",caseName,width,depth,floors,shape,notchSide,output,
            roofAccessEnabled = caseName.IndexOf("RoofAccess", StringComparison.OrdinalIgnoreCase) >= 0,
            parapetRequestedHeight = requestedParapetHeight, highWallFixture,
            prefab=prefabPath,meshRenderers=renderers.Length,
            vertices=filters.Sum(filter=>filter.sharedMesh.vertexCount),
            triangles=filters.Sum(filter=>Enumerable.Range(0,filter.sharedMesh.subMeshCount)
                .Sum(index=>(long)filter.sharedMesh.GetIndexCount(index)/3)),
            materials=renderers.SelectMany(renderer=>renderer.sharedMaterials).Distinct().Select(AssetDatabase.GetAssetPath).ToArray(),
            meshAssets=filters.Select(filter=>AssetDatabase.GetAssetPath(filter.sharedMesh)).Distinct().ToArray(),
            ownedWorkingCaches=ownedWorkingCaches.OrderBy(path=>path,StringComparer.Ordinal).ToArray(), attachmentMeshAssets };
        return Write(resultPath,result);
    }
    public static object SaveGallery(string outputDir)
    {
        var gallery = FindGallery(outputDir);
        Require(gallery.IsValid() && gallery.isLoaded, "Attachment validation scene is not open");
        Require(!File.Exists(ScenePath(outputDir)) || gallery.path == ScenePath(outputDir),
            "An existing gallery would be overwritten; open it additively first");
        var roots = gallery.GetRootGameObjects();
        Require(roots.Length > 0, "Attachment gallery has no baked cases");
        foreach (var root in roots)
        {
            ValidateNativeInstance(root);
            string path = Path.Combine(outputDir,root.name + ".json");
            Require(File.Exists(path), "Saved gallery case has no actual HAPI evidence: " + root.name);
            var saved = JsonConvert.DeserializeObject<SavedCase>(File.ReadAllText(path));
            Require(saved != null && saved.status == "PASS" && saved.caseName == root.name,
                "Saved gallery case evidence is invalid: " + root.name);
            ValidateAttachmentMeshes(root,saved.output,true);
            ValidateActualRoofFootprints(root,saved.output);
            Require(root.name.IndexOf("HighParapet", StringComparison.OrdinalIgnoreCase) < 0 || saved.highWallFixture != null,
                "High-parapet evidence must include measured actual validation Mesh geometry");
            ValidateHighWallGeometry(root,saved.highWallFixture);
        }
        Require(!gallery.isDirty, "Save the gallery with Pipeline's typed scene save command before auditing it");
        Require(gallery.path == ScenePath(outputDir), "Saved gallery path mismatch");
        return Write(Path.Combine(outputDir,"gallery-save.json"),
            new{status="PASS",scene=ScenePath(outputDir),roots=roots.Select(root=>root.name).ToArray()});
    }
}
