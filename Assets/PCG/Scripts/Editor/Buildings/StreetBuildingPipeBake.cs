#if UNITY_EDITOR
using System;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using System.Text.RegularExpressions;
using HoudiniEngineUnity;
using UnityEditor;
using UnityEngine;
using UnityEngine.Rendering;

namespace PCGBike.Editor.Buildings
{
    /// <summary>编辑期整管合并。通过插件公开 Bake 事件接入，不修改插件或增加运行时组件。</summary>
    public static class StreetBuildingPipeBake
    {
        static readonly Regex PartName = new Regex(@"SB_REF_(B\d+_DrainPipe_\d+_[A-Za-z_]+)_F\d+_P\d+", RegexOptions.CultureInvariant);

        internal static void Attach(HEU_HoudiniAsset asset)
        {
            asset.BakedDataEvent.RemoveListener(AfterBake);
            asset.BakedDataEvent.AddListener(AfterBake);
        }

        static void AfterBake(HEU_BakedEventData data)
        {
            if (!data.CookSuccess || data.OutputObjects == null) return;
            foreach (GameObject output in data.OutputObjects)
            {
                if (output == null) continue;
                string prefabPath = AssetDatabase.GetAssetPath(output);
                if (prefabPath.EndsWith(".prefab", StringComparison.OrdinalIgnoreCase))
                {
                    GameObject editable = PrefabUtility.LoadPrefabContents(prefabPath);
                    try
                    {
                        if (Combine(editable, Path.GetDirectoryName(prefabPath).Replace('\\', '/')) > 0)
                            PrefabUtility.SaveAsPrefabAsset(editable, prefabPath);
                    }
                    finally { PrefabUtility.UnloadPrefabContents(editable); }
                }
                else
                {
                    // Standalone native Bake has no prefab path. Keep its meshes persistent
                    // in a dedicated generated directory, never in a source art directory.
                    if (!HasParts(output)) continue;
                    string folder = ExistingNativeBakeFolder(output);
                    if (folder == null)
                    {
                        const string root = "Assets/PCG/Generated/Buildings";
                        EnsureFolder(root);
                        folder = AssetDatabase.GenerateUniqueAssetPath(root + "/PipeBake_" + Sanitize(output.name));
                        EnsureFolder(folder);
                    }
                    Combine(output, folder);
                    UnityEditor.SceneManagement.EditorSceneManager.MarkSceneDirty(output.scene);
                }
            }
        }

        static string GroupOf(Transform transform, Transform root)
        {
            while (transform != null && transform != root)
            {
                Match match = PartName.Match(transform.name);
                if (match.Success) return match.Groups[1].Value;
                transform = transform.parent;
            }
            return null;
        }

        static bool HasParts(GameObject root) => root.GetComponentsInChildren<MeshFilter>(true)
            .Any(filter => filter.sharedMesh != null && GroupOf(filter.transform, root.transform) != null);

        static string Sanitize(string name) => Regex.Replace(name, @"[^A-Za-z0-9_-]", "_");

        // Standalone updates report individual output parts. Reuse the nearest
        // native generated Meshes directory; never select an art/source folder.
        static string ExistingNativeBakeFolder(GameObject output)
        {
            for (Transform scope = output.transform; scope != null; scope = scope.parent)
            {
                string[] folders = scope.GetComponentsInChildren<MeshFilter>(true)
                    .Where(filter => filter.sharedMesh != null)
                    .Select(filter => AssetDatabase.GetAssetPath(filter.sharedMesh))
                    .Where(path => (path.StartsWith("Assets/PCG/Generated/", StringComparison.Ordinal)
                        || path.StartsWith("Assets/__PCGValidation/", StringComparison.Ordinal)
                        || path.StartsWith("Assets/HoudiniEngineAssetCache/Baked/", StringComparison.Ordinal))
                        && path.EndsWith("_meshes.asset", StringComparison.Ordinal)
                        && Path.GetDirectoryName(path).Replace('\\', '/').EndsWith("/Meshes", StringComparison.Ordinal))
                    .Select(path => Path.GetDirectoryName(Path.GetDirectoryName(path)).Replace('\\', '/'))
                    .Distinct(StringComparer.Ordinal).ToArray();
                if (folders.Length == 1) return folders[0];
                if (folders.Length > 1) return null;
            }
            return null;
        }

        static Transform CommonContainer(MeshFilter[] filters, Transform root)
        {
            Transform container = filters[0].transform;
            while (container != null && !filters.All(filter => filter.transform == container
                || filter.transform.IsChildOf(container))) container = container.parent;
            if (container == null || (container != root && !container.IsChildOf(root)))
                throw new InvalidOperationException("Pipe group crosses Bake output roots.");
            // A part itself is valid when the update event reports that part.
            // A full building must retain ownership in its original instancer.
            if (container == root && !root.name.EndsWith(HEU_Defines.HEU_BAKED_CLONE, StringComparison.Ordinal))
                throw new InvalidOperationException("Pipe group must belong to one native instancer output.");
            return container;
        }

        static void EnsureFolder(string path)
        {
            if (AssetDatabase.IsValidFolder(path)) return;
            string parent = Path.GetDirectoryName(path).Replace('\\', '/');
            EnsureFolder(parent);
            if (string.IsNullOrEmpty(AssetDatabase.CreateFolder(parent, Path.GetFileName(path))))
                throw new InvalidOperationException("Unable to create pipe Bake folder: " + path);
        }

        /// <summary>扩展点：按整管 group 分块；相同材质形成一个 submesh，Renderer 数与米数无关。</summary>
        public static int Combine(GameObject root, string destination)
        {
            if (root == null) throw new ArgumentNullException(nameof(root));
            destination = destination.Replace('\\', '/').TrimEnd('/');
            if (!destination.StartsWith("Assets/", StringComparison.Ordinal)
                || destination.Contains("/../") || destination.Contains("/Art/"))
                throw new ArgumentException("Pipe Bake requires a generated output directory", nameof(destination));
            var groups = root.GetComponentsInChildren<MeshFilter>(true)
                .Where(filter => filter.sharedMesh != null && filter.GetComponent<MeshRenderer>() != null)
                .Select(filter => new { Filter = filter, Group = GroupOf(filter.transform, root.transform) })
                .Where(item => item.Group != null)
                .GroupBy(item => item.Group, StringComparer.Ordinal)
                .OrderBy(group => group.Key, StringComparer.Ordinal).ToArray();
            if (groups.Length == 0) return 0;
            string meshFolder = destination + "/PipeMeshes";
            EnsureFolder(meshFolder);
            foreach (var group in groups)
            {
                var materials = new List<Material>();
                var perMaterial = new List<List<CombineInstance>>();
                var filters = group.Select(item => item.Filter).ToArray();
                Transform container = CommonContainer(filters, root.transform);
                Matrix4x4 toRoot = container.worldToLocalMatrix;
                foreach (MeshFilter filter in filters)
                {
                    Mesh mesh = filter.sharedMesh;
                    var renderer = filter.GetComponent<MeshRenderer>();
                    if (renderer.sharedMaterials.Length != mesh.subMeshCount)
                        throw new InvalidOperationException("Pipe source material/submesh mismatch: " + filter.name);
                    Matrix4x4 matrix = toRoot * filter.transform.localToWorldMatrix;
                    if (matrix.determinant <= 0)
                        throw new InvalidOperationException("Pipe Bake cannot mirror source geometry: " + filter.name);
                    for (int submesh = 0; submesh < mesh.subMeshCount; submesh++)
                    {
                        Material material = renderer.sharedMaterials[submesh];
                        if (material == null) throw new InvalidOperationException("Pipe material missing: " + filter.name);
                        int slot = materials.IndexOf(material);
                        if (slot < 0) { slot = materials.Count; materials.Add(material); perMaterial.Add(new List<CombineInstance>()); }
                        perMaterial[slot].Add(new CombineInstance { mesh = mesh, subMeshIndex = submesh, transform = matrix });
                    }
                }
                // Build all geometry before replacing the source renderers.
                var temporary = new List<Mesh>();
                Mesh combined = new Mesh { name = "SB_PIPE_" + group.Key, indexFormat = IndexFormat.UInt32 };
                try
                {
                    foreach (var entries in perMaterial)
                    {
                        Mesh part = new Mesh { indexFormat = IndexFormat.UInt32 };
                        part.CombineMeshes(entries.ToArray(), true, true, false); temporary.Add(part);
                    }
                    // Set format before assigning indices: indexFormat changes clear them.
                    combined.indexFormat = temporary.Sum(mesh => mesh.vertexCount) <= 65535 ? IndexFormat.UInt16 : IndexFormat.UInt32;
                    combined.CombineMeshes(temporary.Select(mesh => new CombineInstance { mesh = mesh, transform = Matrix4x4.identity }).ToArray(), false, false, false);
                    combined.RecalculateBounds();
                    // CreateAsset normalizes Mesh.name to the filename. Keep the
                    // persisted group identity stable through Bake and cold reopen.
                    string path = meshFolder + "/" + Sanitize(combined.name) + ".asset";
                    // Preserve existing Mesh assets, including artist edits made after a prior Bake.
                    // A repeated generated output gets a new asset; no source or old GUID is overwritten.
                    path = AssetDatabase.GenerateUniqueAssetPath(path);
                    AssetDatabase.CreateAsset(combined, path);
                    // Repeated Bake may append a unique filename suffix; semantic
                    // group names must still match the generated hierarchy.
                    combined.name = "SB_PIPE_" + group.Key;
                    EditorUtility.SetDirty(combined);
                    AssetDatabase.SaveAssetIfDirty(combined);
                    GameObject visual = new GameObject("SB_PIPE_" + group.Key);
                    // HEU replaces this part's generated children on update.
                    // Keeping the pipe here prevents stale root-level duplicates.
                    visual.transform.SetParent(container, false);
                    visual.AddComponent<MeshFilter>().sharedMesh = combined;
                    visual.AddComponent<MeshRenderer>().sharedMaterials = materials.ToArray();
                    // Only unpack baked pipe instances; source Prefabs stay editable and untouched.
                    foreach (GameObject instance in filters.Select(filter => PrefabUtility.GetOutermostPrefabInstanceRoot(filter.gameObject))
                        .Where(instance => instance != null && instance != root).Distinct().ToArray())
                        if (PrefabUtility.IsPartOfPrefabInstance(instance))
                            PrefabUtility.UnpackPrefabInstance(instance, PrefabUnpackMode.Completely, InteractionMode.AutomatedAction);
                    foreach (MeshFilter filter in filters)
                    {
                        UnityEngine.Object.DestroyImmediate(filter.GetComponent<MeshRenderer>());
                        UnityEngine.Object.DestroyImmediate(filter);
                    }
                }
                finally
                {
                    foreach (Mesh mesh in temporary) UnityEngine.Object.DestroyImmediate(mesh);
                    if (combined != null && !EditorUtility.IsPersistent(combined)) UnityEngine.Object.DestroyImmediate(combined);
                }
            }
            return groups.Length;
        }
    }
}
#endif
