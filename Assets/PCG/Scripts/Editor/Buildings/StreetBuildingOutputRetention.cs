#if UNITY_EDITOR
using System;
using System.Collections.Generic;
using System.Linq;
using HoudiniEngineUnity;
using UnityEditor;
using UnityEngine;
using Object = UnityEngine.Object;

namespace PCGBike.Editor.Buildings
{
    // 编辑期一次 Cook 的输出事务。只保全 HEU 输出，不触碰人工场景对象。
    // 性能关键点：备份只在显式生成时创建；不在 Inspector 重绘或运行时执行。
    internal sealed class StreetBuildingOutputRetention : IDisposable
    {
        private sealed class Root
        {
            public GameObject original, copy;
            public Transform parent;
            public Vector3 position, scale;
            public Quaternion rotation;
            public bool active;
            public string signature;
        }
        private readonly HEU_HoudiniAsset asset;
        private readonly List<Root> roots = new();
        private readonly List<HEU_GeneratedOutput> outputs = new();
        private readonly Dictionary<GameObject, GameObject> replacements = new();
        private readonly Dictionary<Mesh, Mesh> meshes = new();
        private readonly Dictionary<Material, Material> materials = new();
        private readonly List<(MeshFilter Filter, Mesh Mesh)> filters = new();
        private readonly List<(MeshCollider Collider, Mesh Mesh)> colliders = new();
        private readonly List<(Renderer Renderer, Material[] Materials)> renderers = new();
        private readonly List<(HEU_GeneratedOutputData Data, GameObject Original)> bindings = new();
        private readonly GameObject container;
        private bool restoredCopies;

        private StreetBuildingOutputRetention(HEU_HoudiniAsset source)
        {
            asset = source;
            container = new GameObject("StreetBuilding Cook output backup") { hideFlags = HideFlags.HideAndDontSave };
            container.SetActive(false);
            var objects = new List<GameObject>();
            source.GetOutputGameObjects(objects); source.GetOutput(outputs);
            foreach (var output in outputs)
            {
                bindings.Add((output._outputData, output._outputData._gameObject));
                foreach (var child in output._childOutputs) bindings.Add((child, child._gameObject));
            }
            var set = new HashSet<GameObject>(objects.Where(g => g != null));
            foreach (var go in set.Where(g => !set.Any(p => p != g && g.transform.IsChildOf(p.transform))))
            {
                var copy = Object.Instantiate(go, container.transform, false);
                copy.name = go.name;
                var root = new Root { original = go, copy = copy, parent = go.transform.parent,
                    position = go.transform.localPosition, rotation = go.transform.localRotation,
                    scale = go.transform.localScale, active = go.activeSelf, signature = Signature(go) };
                roots.Add(root);
                Map(go.transform, copy.transform);
                foreach (var filter in copy.GetComponentsInChildren<MeshFilter>(true)) { BackupMesh(filter.sharedMesh); filters.Add((filter, filter.sharedMesh)); }
                foreach (var collider in copy.GetComponentsInChildren<MeshCollider>(true)) { BackupMesh(collider.sharedMesh); colliders.Add((collider, collider.sharedMesh)); }
                foreach (var renderer in copy.GetComponentsInChildren<Renderer>(true))
                {
                    renderers.Add((renderer, renderer.sharedMaterials));
                    foreach (var material in renderer.sharedMaterials)
                        if (material != null && !EditorUtility.IsPersistent(material) && !materials.ContainsKey(material))
                            materials[material] = Object.Instantiate(material);
                }
            }
        }
        public static StreetBuildingOutputRetention Capture(HEU_HoudiniAsset asset) => new(asset);
        private void Map(Transform a, Transform b)
        {
            replacements[a.gameObject] = b.gameObject;
            for (int i = 0; i < a.childCount; i++) Map(a.GetChild(i), b.GetChild(i));
        }
        private void BackupMesh(Mesh mesh)
        {
            if (mesh != null && !EditorUtility.IsPersistent(mesh) && !meshes.ContainsKey(mesh)) meshes[mesh] = Object.Instantiate(mesh);
        }
        internal static string Signature(GameObject root) => root == null ? "destroyed" : string.Join("\n",
            root.GetComponentsInChildren<Transform>(true).Select(t => t.name + "|" + t.GetInstanceID() + "|" + t.localPosition + "|" + t.localRotation + "|" + t.localScale)
                .Concat(root.GetComponentsInChildren<MeshFilter>(true).Select(f => "mesh|" + (f.sharedMesh == null ? 0 : f.sharedMesh.GetInstanceID())))
                .Concat(root.GetComponentsInChildren<Renderer>(true).Select(r => "materials|" + string.Join(",", r.sharedMaterials.Select(m => m == null ? 0 : m.GetInstanceID())))));

        public bool Restore()
        {
            if (roots.Count == 0) return false;
            foreach (var pair in meshes) if (pair.Key != null) EditorUtility.CopySerialized(pair.Value, pair.Key);
            foreach (var pair in materials) if (pair.Key != null) EditorUtility.CopySerialized(pair.Value, pair.Key);
            // HEU 的 Cook 错误通常不会替换输出；保留原对象身份与引用。
            if (roots.All(r => r.original != null && Signature(r.original) == r.signature)) return true;
            var current = new List<GameObject>(); asset.GetOutputGameObjects(current);
            var currentSet = new HashSet<GameObject>(current.Where(g => g != null));
            // 先物化待删除列表；DestroyImmediate 会使后续延迟枚举中的 Unity 引用失效。
            var currentRoots = currentSet.Where(g => !currentSet.Any(p => p != g && g.transform.IsChildOf(p.transform))).ToArray();
            var survivingRoots = new HashSet<GameObject>(roots.Where(r => r.original != null).Select(r => r.original));
            foreach (var go in currentRoots.Where(g => !survivingRoots.Contains(g))) Object.DestroyImmediate(go);
            foreach (var root in roots)
            {
                var copy = root.copy;
                if (root.original != null)
                {
                    // HEU 通常保留输出根而替换其网格或子节点；保留根对象身份和外部引用。
                    var target = root.original;
                    foreach (Transform child in target.transform.Cast<Transform>().ToArray()) Object.DestroyImmediate(child.gameObject);
                    foreach (var component in target.GetComponents<Component>().Where(c => !(c is Transform))) Object.DestroyImmediate(component);
                    foreach (var component in copy.GetComponents<Component>().Where(c => !(c is Transform)))
                    {
                        var restored = target.AddComponent(component.GetType());
                        EditorUtility.CopySerialized(component, restored);
                        for (int i = 0; i < filters.Count; i++) if (filters[i].Filter == component) filters[i] = ((MeshFilter)restored, filters[i].Mesh);
                        for (int i = 0; i < colliders.Count; i++) if (colliders[i].Collider == component) colliders[i] = ((MeshCollider)restored, colliders[i].Mesh);
                        for (int i = 0; i < renderers.Count; i++) if (renderers[i].Renderer == component) renderers[i] = ((Renderer)restored, renderers[i].Materials);
                    }
                    foreach (Transform child in copy.transform.Cast<Transform>().ToArray()) child.SetParent(target.transform, false);
                    replacements[root.original] = target;
                    root.copy = target;
                }
                root.copy.transform.SetParent(root.parent, false);
                root.copy.transform.localPosition = root.position; root.copy.transform.localRotation = root.rotation; root.copy.transform.localScale = root.scale;
                root.copy.hideFlags = HideFlags.None; root.copy.SetActive(root.active);
            }
            foreach (var pair in filters) pair.Filter.sharedMesh = pair.Mesh != null ? pair.Mesh : RestoreMeshReference(pair.Mesh);
            foreach (var pair in colliders) pair.Collider.sharedMesh = pair.Mesh != null ? pair.Mesh : RestoreMeshReference(pair.Mesh);
            foreach (var pair in renderers) pair.Renderer.sharedMaterials = pair.Materials.Select(m => m != null ? m : RestoreMaterialReference(m)).ToArray();
            foreach (var binding in bindings)
                if (binding.Data != null && !ReferenceEquals(binding.Original, null) && replacements.TryGetValue(binding.Original, out var restored))
                {
                    binding.Data._gameObject = restored;
                    binding.Data._colliders = restored.GetComponents<Collider>().ToList();
                    var renderer = restored.GetComponent<Renderer>();
                    binding.Data._renderMaterials = renderer != null ? renderer.sharedMaterials : null;
                }
            restoredCopies = true;
            // 不能仅凭父节点正确就声称保留成功：验证实际网格与材质引用。
            return roots.All(r => r.copy != null && r.copy.transform.parent == r.parent)
                && filters.All(p => p.Filter != null && p.Filter.sharedMesh != null)
                && colliders.All(p => p.Collider != null && (ReferenceEquals(p.Mesh, null) || p.Collider.sharedMesh != null))
                && renderers.All(p => p.Renderer != null && p.Renderer.sharedMaterials.Length == p.Materials.Length
                    && p.Renderer.sharedMaterials.Select((m, i) => ReferenceEquals(p.Materials[i], null) || m != null).All(ok => ok));
        }
        private Mesh RestoreMeshReference(Mesh old)
        {
            foreach (var pair in meshes) if (ReferenceEquals(pair.Key, old)) return pair.Value;
            return old;
        }
        private Material RestoreMaterialReference(Material old)
        {
            foreach (var pair in materials) if (ReferenceEquals(pair.Key, old)) return pair.Value;
            return old;
        }
        public void Dispose()
        {
            if (container != null) Object.DestroyImmediate(container);
            var usedMeshes = restoredCopies ? new HashSet<Mesh>(filters.Where(p => p.Filter != null).Select(p => p.Filter.sharedMesh)
                .Concat(colliders.Where(p => p.Collider != null).Select(p => p.Collider.sharedMesh))) : new HashSet<Mesh>();
            var usedMaterials = restoredCopies ? new HashSet<Material>(renderers.Where(p => p.Renderer != null).SelectMany(p => p.Renderer.sharedMaterials)) : new HashSet<Material>();
            foreach (var mesh in meshes.Values) if (mesh != null && !usedMeshes.Contains(mesh)) Object.DestroyImmediate(mesh);
            foreach (var material in materials.Values) if (material != null && !usedMaterials.Contains(material)) Object.DestroyImmediate(material);
        }
    }
}
#endif
