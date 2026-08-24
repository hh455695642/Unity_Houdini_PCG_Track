#if UNITY_EDITOR
using System;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using PCG.CityPark;
using UnityEditor;
using UnityEngine;
using UnityEngine.Rendering;
using UnityEngine.Rendering.Universal;

namespace PCG.CityRoad.Editor
{
    internal static class CityRoadParkAssets
    {
        internal const string GroundMaterialPath =
            "Assets/PCG/Materials/CityPark/M_PCG_CityPark_Grass.mat";
        internal const string PathMaterialPath =
            "Assets/PCG/Materials/CityPark/M_PCG_CityPark_Path.mat";
        internal const string WaterMaterialPath =
            "Assets/PCG/Materials/CityPark/M_PCG_CityPark_Water.mat";
        private const string ComputeShaderPath =
            "Assets/PCG/Shaders/PCG_CityPark_Culling.compute";
        private const string VegetationShaderName =
            "PCG/CityPark/VegetationIndirect";
        private const float FallbackChunkSize = 64f;
        private static readonly string[] s_RendererDataPaths =
        {
            "Assets/Settings/URP-Performant-Renderer.asset",
            "Assets/Settings/URP-Balanced-Renderer.asset",
            "Assets/Settings/URP-HighFidelity-Renderer.asset"
        };

        private sealed class SourceInstance
        {
            internal Transform Transform;
            internal Mesh Mesh;
            internal Mesh Lod1Mesh;
            internal Material[] Materials;
            internal int Variant;
        }

        private readonly struct ChunkKey : IEquatable<ChunkKey>
        {
            internal readonly int X;
            internal readonly int Z;
            internal readonly int Variant;
            internal readonly int SubMesh;

            internal ChunkKey(int x, int z, int variant, int subMesh)
            {
                X = x;
                Z = z;
                Variant = variant;
                SubMesh = subMesh;
            }

            public bool Equals(ChunkKey other)
            {
                return X == other.X && Z == other.Z
                    && Variant == other.Variant && SubMesh == other.SubMesh;
            }

            public override bool Equals(object obj)
            {
                return obj is ChunkKey other && Equals(other);
            }

            public override int GetHashCode()
            {
                unchecked
                {
                    int hash = X;
                    hash = hash * 397 ^ Z;
                    hash = hash * 397 ^ Variant;
                    return hash * 397 ^ SubMesh;
                }
            }
        }

        private readonly struct MeshEdge : IEquatable<MeshEdge>
        {
            internal readonly int A;
            internal readonly int B;

            internal MeshEdge(int left, int right)
            {
                A = Mathf.Min(left, right);
                B = Mathf.Max(left, right);
            }

            public bool Equals(MeshEdge other)
            {
                return A == other.A && B == other.B;
            }

            public override bool Equals(object obj)
            {
                return obj is MeshEdge other && Equals(other);
            }

            public override int GetHashCode()
            {
                unchecked
                {
                    return A * 397 ^ B;
                }
            }
        }

        internal static bool ValidateMaterialContract(out string report)
        {
            var issues = new List<string>();
            ValidateMaterial(GroundMaterialPath, issues);
            ValidateMaterial(PathMaterialPath, issues);
            ValidateMaterial(WaterMaterialPath, issues);
            if (Shader.Find(VegetationShaderName) == null)
                issues.Add("Missing shader " + VegetationShaderName + ".");
            if (AssetDatabase.LoadAssetAtPath<ComputeShader>(ComputeShaderPath) == null)
                issues.Add("Missing compute shader " + ComputeShaderPath + ".");
            report = issues.Count == 0
                ? "City Park material/GPU assets passed."
                : "- " + string.Join("\n- ", issues);
            return issues.Count == 0;
        }

        [MenuItem("PCG/CityRoad/Install City Park Renderer Features", priority = 2112)]
        internal static void InstallRendererFeatures()
        {
            foreach (string path in s_RendererDataPaths)
            {
                ScriptableRendererData data =
                    AssetDatabase.LoadAssetAtPath<ScriptableRendererData>(path);
                if (data == null)
                    throw new InvalidOperationException("Renderer Data is missing: " + path);
                if (data.rendererFeatures.Any(feature =>
                        feature is CityParkVegetationRendererFeature))
                {
                    continue;
                }

                CityParkVegetationRendererFeature feature =
                    ScriptableObject.CreateInstance<CityParkVegetationRendererFeature>();
                feature.name = "City Park Vegetation Indirect";
                feature.Create();
                AssetDatabase.AddObjectToAsset(feature, data);
                AssetDatabase.TryGetGUIDAndLocalFileIdentifier(
                    feature,
                    out string ignoredGuid,
                    out long localId);

                var serializedData = new SerializedObject(data);
                SerializedProperty features = serializedData.FindProperty("m_RendererFeatures");
                SerializedProperty map = serializedData.FindProperty("m_RendererFeatureMap");
                int index = features.arraySize;
                features.InsertArrayElementAtIndex(index);
                features.GetArrayElementAtIndex(index).objectReferenceValue = feature;
                map.InsertArrayElementAtIndex(index);
                map.GetArrayElementAtIndex(index).longValue = localId;
                serializedData.ApplyModifiedPropertiesWithoutUndo();
                EditorUtility.SetDirty(feature);
                EditorUtility.SetDirty(data);
            }
            AssetDatabase.SaveAssets();
            AssetDatabase.Refresh();
        }

        private static void ValidateMaterial(string path, List<string> issues)
        {
            Material material = AssetDatabase.LoadAssetAtPath<Material>(path);
            if (material == null)
            {
                issues.Add("Missing City Park material " + path + ".");
                return;
            }
            if (material.shader == null
                || !string.Equals(
                    material.shader.name,
                    "PCG/CityRoad/SimpleSurface",
                    StringComparison.Ordinal))
            {
                issues.Add("Unexpected City Park shader at " + path + ".");
            }
            if (material.renderQueue >= (int)RenderQueue.Transparent)
                issues.Add("City Park material must remain opaque: " + path + ".");
            if (!material.enableInstancing)
                issues.Add("City Park material must enable instancing: " + path + ".");
        }

        internal static bool CompilePrefab(
            GameObject prefab,
            string assetFolder,
            out string report)
        {
            Transform treeRoot = FindOutput(prefab, "OUT_PARK_TREES");
            Transform exclusionRoot = FindOutput(prefab, "OUT_PARK_EXCLUSION");
            if (treeRoot == null && exclusionRoot == null)
            {
                report = "City Park outputs are absent; no park bake data was emitted.";
                return true;
            }

            EnsureAssetFolder(assetFolder);
            string dataPath = assetFolder + "/CityParkVegetationData.asset";
            string profilePath = assetFolder + "/CityParkVegetationProfile.asset";
            string exclusionPath = assetFolder + "/PCGSiteExclusionData.asset";

            CityParkVegetationData data = LoadOrCreate<CityParkVegetationData>(dataPath);
            CityParkVegetationProfile profile = LoadOrCreate<CityParkVegetationProfile>(profilePath);
            PCGSiteExclusionData exclusions = LoadOrCreate<PCGSiteExclusionData>(exclusionPath);

            List<SourceInstance> instances = CollectInstances(treeRoot);
            var records = new CityParkVegetationData.InstanceRecord[instances.Count];
            var chunkIndices = new Dictionary<Vector2Int, int>();
            var chunkBounds = new List<Bounds>();
            Bounds localBounds = new Bounds(Vector3.zero, Vector3.zero);
            bool hasBounds = false;
            for (int index = 0; index < instances.Count; index++)
            {
                Matrix4x4 matrix = prefab.transform.worldToLocalMatrix
                    * instances[index].Transform.localToWorldMatrix;
                records[index] = new CityParkVegetationData.InstanceRecord
                {
                    LocalToAnchor = matrix,
                    Variant = instances[index].Variant
                };
                Vector3 point = matrix.GetColumn(3);
                var chunkKey = new Vector2Int(
                    Mathf.FloorToInt(point.x / FallbackChunkSize),
                    Mathf.FloorToInt(point.z / FallbackChunkSize));
                if (!chunkIndices.TryGetValue(chunkKey, out int chunkIndex))
                {
                    chunkIndex = chunkBounds.Count;
                    chunkIndices.Add(chunkKey, chunkIndex);
                    chunkBounds.Add(new Bounds(point, Vector3.one * 7f));
                }
                else
                {
                    Bounds bounds = chunkBounds[chunkIndex];
                    bounds.Encapsulate(new Bounds(point, Vector3.one * 7f));
                    chunkBounds[chunkIndex] = bounds;
                }
                records[index].Chunk = chunkIndex;
                if (!hasBounds)
                {
                    localBounds = new Bounds(point, Vector3.one);
                    hasBounds = true;
                }
                else
                {
                    localBounds.Encapsulate(point);
                }
            }
            CityParkVegetationData.ChunkRecord[] chunks = chunkBounds
                .Select(bounds => new CityParkVegetationData.ChunkRecord
                {
                    Center = bounds.center,
                    Extents = bounds.extents
                })
                .ToArray();
            data.ReplaceBakeData(records, localBounds, chunks);

            CityParkVegetationProfile.Variant[] variants = instances
                .GroupBy(instance => instance.Variant)
                .OrderBy(group => group.Key)
                .Take(CityParkVegetationProfile.MaxVariants)
                .Select(group => new CityParkVegetationProfile.Variant
                {
                    Lod0Mesh = group.First().Mesh,
                    Lod1Mesh = group.First().Lod1Mesh != null
                        ? group.First().Lod1Mesh
                        : group.First().Mesh,
                    Materials = CreateIndirectMaterials(
                        group.First().Materials,
                        assetFolder,
                        group.Key)
                })
                .ToArray();
            profile.ReplaceBakeData(
                AssetDatabase.LoadAssetAtPath<ComputeShader>(ComputeShaderPath),
                variants);

            exclusions.ReplaceBakeData(CollectExclusions(prefab, exclusionRoot));

            GameObject fallbackRoot = BuildFallback(prefab, treeRoot, instances, assetFolder);
            if (treeRoot != null)
                UnityEngine.Object.DestroyImmediate(treeRoot.gameObject);
            if (exclusionRoot != null)
                UnityEngine.Object.DestroyImmediate(exclusionRoot.gameObject);

            CityParkVegetationAnchor anchor = prefab.GetComponent<CityParkVegetationAnchor>();
            if (anchor == null)
                anchor = prefab.AddComponent<CityParkVegetationAnchor>();
            anchor.AssignBakeData(profile, data, exclusions, fallbackRoot);
            EditorUtility.SetDirty(data);
            EditorUtility.SetDirty(profile);
            EditorUtility.SetDirty(exclusions);
            EditorUtility.SetDirty(anchor);
            AssetDatabase.SaveAssets();

            report = string.Format(
                "City Park bake data compiled: instances={0}, variants={1}, exclusions={2}, fallbackChunks={3}.",
                records.Length,
                variants.Length,
                exclusions.Sites.Length,
                fallbackRoot != null ? fallbackRoot.transform.childCount : 0);
            return true;
        }

        private static Material[] CreateIndirectMaterials(
            Material[] source,
            string folder,
            int variant)
        {
            Shader shader = Shader.Find(VegetationShaderName);
            if (shader == null || source == null)
                return Array.Empty<Material>();
            int count = Mathf.Min(
                source.Length,
                CityParkVegetationProfile.MaxSubMeshesPerLod);
            var result = new Material[count];
            for (int index = 0; index < count; index++)
            {
                string path = string.Format(
                    "{0}/M_CityPark_Tree_{1}_{2}.mat",
                    folder,
                    variant,
                    index);
                Material material = AssetDatabase.LoadAssetAtPath<Material>(path);
                if (material == null)
                {
                    material = new Material(shader);
                    AssetDatabase.CreateAsset(material, path);
                }
                else if (material.shader != shader)
                {
                    material.shader = shader;
                }
                if (source[index] != null)
                {
                    if (source[index].HasProperty("_BaseMap"))
                        material.SetTexture("_BaseMap", source[index].GetTexture("_BaseMap"));
                    material.SetColor(
                        "_BaseTint",
                        source[index].HasProperty("_BaseColor")
                            ? source[index].GetColor("_BaseColor")
                            : source[index].HasProperty("_BaseTint")
                                ? source[index].GetColor("_BaseTint")
                                : Color.white);
                }
                material.enableInstancing = true;
                EditorUtility.SetDirty(material);
                result[index] = material;
            }
            return result;
        }

        private static List<SourceInstance> CollectInstances(Transform treeRoot)
        {
            var result = new List<SourceInstance>();
            if (treeRoot == null)
                return result;
            var variantByMesh = new Dictionary<Mesh, int>();
            foreach (MeshRenderer renderer in treeRoot.GetComponentsInChildren<MeshRenderer>(true))
            {
                MeshFilter filter = renderer.GetComponent<MeshFilter>();
                if (filter == null || filter.sharedMesh == null)
                    continue;
                if (!TryResolveLod1Mesh(renderer, out Mesh lod1Mesh))
                    continue;
                if (!variantByMesh.TryGetValue(filter.sharedMesh, out int variant))
                {
                    variant = variantByMesh.Count;
                    if (variant >= CityParkVegetationProfile.MaxVariants)
                        continue;
                    variantByMesh.Add(filter.sharedMesh, variant);
                }
                result.Add(new SourceInstance
                {
                    Transform = renderer.transform,
                    Mesh = filter.sharedMesh,
                    Lod1Mesh = lod1Mesh,
                    Materials = renderer.sharedMaterials,
                    Variant = variant
                });
            }
            return result;
        }

        private static bool TryResolveLod1Mesh(MeshRenderer lod0Renderer, out Mesh lod1Mesh)
        {
            lod1Mesh = null;
            LODGroup group = lod0Renderer.GetComponentInParent<LODGroup>();
            if (group == null)
                return true;

            LOD[] lods = group.GetLODs();
            if (lods.Length == 0 || !lods[0].renderers.Contains(lod0Renderer))
                return false;
            if (lods.Length < 2)
                return true;

            Renderer renderer = lods[1].renderers.FirstOrDefault(candidate =>
                candidate != null && candidate.GetComponent<MeshFilter>() != null);
            if (renderer != null)
                lod1Mesh = renderer.GetComponent<MeshFilter>().sharedMesh;
            return true;
        }

        private static PCGSiteExclusionData.Site[] CollectExclusions(
            GameObject prefab,
            Transform root)
        {
            if (root == null)
                return Array.Empty<PCGSiteExclusionData.Site>();
            var result = new List<PCGSiteExclusionData.Site>();
            foreach (MeshFilter filter in root.GetComponentsInChildren<MeshFilter>(true))
            {
                Mesh mesh = filter.sharedMesh;
                if (mesh == null || mesh.vertexCount < 3)
                    continue;
                int[] boundaryIndices = ExtractBoundaryLoop(mesh);
                Vector3[] vertices = mesh.vertices;
                Vector3[] boundary = CanonicalizeBoundary(boundaryIndices
                    .Where(index => index >= 0 && index < vertices.Length)
                    .Select(index => prefab.transform.worldToLocalMatrix.MultiplyPoint3x4(
                        filter.transform.TransformPoint(vertices[index])))
                    .ToArray());
                if (boundary.Length < 3)
                    continue;
                int parkId = TryReadHoudiniParkId(filter.transform, root, out int houdiniParkId)
                    ? houdiniParkId
                    : StableParkId(boundary);
                result.Add(new PCGSiteExclusionData.Site
                {
                    ParkId = parkId,
                    SiteType = "park",
                    ExcludeBuilding = true,
                    LocalBoundary = boundary
                });
            }
            return result
                .OrderBy(site => site.ParkId)
                .ToArray();
        }

        private static int[] ExtractBoundaryLoop(Mesh mesh)
        {
            var edgeCounts = new Dictionary<MeshEdge, int>();
            for (int subMesh = 0; subMesh < mesh.subMeshCount; subMesh++)
            {
                int[] indices = mesh.GetIndices(subMesh);
                MeshTopology topology = mesh.GetTopology(subMesh);
                int stride = topology == MeshTopology.Quads ? 4
                    : topology == MeshTopology.Triangles ? 3
                    : 0;
                if (stride == 0)
                    continue;
                for (int offset = 0; offset + stride <= indices.Length; offset += stride)
                {
                    for (int edge = 0; edge < stride; edge++)
                    {
                        var key = new MeshEdge(
                            indices[offset + edge],
                            indices[offset + (edge + 1) % stride]);
                        edgeCounts[key] = edgeCounts.TryGetValue(key, out int count)
                            ? count + 1
                            : 1;
                    }
                }
            }

            var adjacency = new Dictionary<int, List<int>>();
            foreach (KeyValuePair<MeshEdge, int> item in edgeCounts)
            {
                if (item.Value != 1)
                    continue;
                AddNeighbour(adjacency, item.Key.A, item.Key.B);
                AddNeighbour(adjacency, item.Key.B, item.Key.A);
            }
            if (adjacency.Count < 3 || adjacency.Any(item => item.Value.Count != 2))
                return Enumerable.Range(0, mesh.vertexCount).ToArray();

            int start = adjacency.Keys.Min();
            var loop = new List<int>(adjacency.Count);
            int previous = -1;
            int current = start;
            do
            {
                loop.Add(current);
                List<int> neighbours = adjacency[current];
                int next = neighbours[0] != previous ? neighbours[0] : neighbours[1];
                previous = current;
                current = next;
            }
            while (current != start && loop.Count <= adjacency.Count);
            return current == start && loop.Count == adjacency.Count
                ? loop.ToArray()
                : Enumerable.Range(0, mesh.vertexCount).ToArray();
        }

        private static void AddNeighbour(
            Dictionary<int, List<int>> adjacency,
            int vertex,
            int neighbour)
        {
            if (!adjacency.TryGetValue(vertex, out List<int> values))
            {
                values = new List<int>(2);
                adjacency.Add(vertex, values);
            }
            values.Add(neighbour);
        }

        private static Vector3[] CanonicalizeBoundary(Vector3[] source)
        {
            if (source == null || source.Length < 3)
                return Array.Empty<Vector3>();
            var unique = new List<Vector3>(source.Length);
            foreach (Vector3 point in source)
            {
                if (unique.Count == 0
                    || (point - unique[unique.Count - 1]).sqrMagnitude > 0.000001f)
                    unique.Add(point);
            }
            if (unique.Count > 2
                && (unique[0] - unique[unique.Count - 1]).sqrMagnitude <= 0.000001f)
                unique.RemoveAt(unique.Count - 1);
            if (unique.Count < 3)
                return Array.Empty<Vector3>();

            float signedArea = 0f;
            for (int index = 0; index < unique.Count; index++)
            {
                Vector3 a = unique[index];
                Vector3 b = unique[(index + 1) % unique.Count];
                signedArea += a.x * b.z - b.x * a.z;
            }
            if (signedArea < 0f)
                unique.Reverse();

            int first = 0;
            for (int index = 1; index < unique.Count; index++)
            {
                Vector3 candidate = unique[index];
                Vector3 current = unique[first];
                int candidateX = Mathf.RoundToInt(candidate.x * 100f);
                int currentX = Mathf.RoundToInt(current.x * 100f);
                int candidateZ = Mathf.RoundToInt(candidate.z * 100f);
                int currentZ = Mathf.RoundToInt(current.z * 100f);
                if (candidateX < currentX
                    || (candidateX == currentX && candidateZ < currentZ))
                    first = index;
            }
            var result = new Vector3[unique.Count];
            for (int index = 0; index < result.Length; index++)
                result[index] = unique[(first + index) % unique.Count];
            return result;
        }

        private static bool TryReadHoudiniParkId(
            Transform transform,
            Transform exclusionRoot,
            out int parkId)
        {
            const string prefix = "CityPark_";
            for (Transform current = transform;
                 current != null && current != exclusionRoot.parent;
                 current = current.parent)
            {
                string name = current.name;
                int prefixIndex = name.IndexOf(prefix, StringComparison.OrdinalIgnoreCase);
                if (prefixIndex < 0)
                    continue;
                int digitStart = prefixIndex + prefix.Length;
                int digitEnd = digitStart;
                while (digitEnd < name.Length && char.IsDigit(name[digitEnd]))
                    digitEnd++;
                if (digitEnd > digitStart
                    && int.TryParse(name.Substring(digitStart, digitEnd - digitStart), out parkId)
                    && parkId > 0)
                    return true;
            }
            parkId = 0;
            return false;
        }

        private static int StableParkId(Vector3[] vertices)
        {
            // Fallback for older HEU group naming: hash the 1 cm quantized point set.
            // Sorting removes input primitive order and winding from the identity.
            var quantized = vertices
                .Select(vertex => new Vector2Int(
                    Mathf.RoundToInt(vertex.x * 100f),
                    Mathf.RoundToInt(vertex.z * 100f)))
                .Distinct()
                .OrderBy(point => point.x)
                .ThenBy(point => point.y);
            unchecked
            {
                int hash = 17;
                foreach (Vector2Int point in quantized)
                {
                    hash = hash * 31 + point.x;
                    hash = hash * 31 + point.y;
                }
                int positive = hash & int.MaxValue;
                return positive == 0 ? 1 : positive;
            }
        }

        private static GameObject BuildFallback(
            GameObject prefab,
            Transform previousRoot,
            List<SourceInstance> instances,
            string folder)
        {
            Transform existing = prefab.transform.Find("CityPark_VegetationFallback");
            if (existing != null)
                UnityEngine.Object.DestroyImmediate(existing.gameObject);
            var root = new GameObject("CityPark_VegetationFallback");
            root.transform.SetParent(prefab.transform, false);

            var chunks = new Dictionary<ChunkKey, List<CombineInstance>>();
            foreach (SourceInstance instance in instances)
            {
                Mesh fallbackMesh = instance.Lod1Mesh != null
                    ? instance.Lod1Mesh
                    : instance.Mesh;
                Vector3 position = prefab.transform.worldToLocalMatrix.MultiplyPoint3x4(
                    instance.Transform.position);
                int chunkX = Mathf.FloorToInt(position.x / FallbackChunkSize);
                int chunkZ = Mathf.FloorToInt(position.z / FallbackChunkSize);
                int subMeshCount = Mathf.Min(
                    fallbackMesh.subMeshCount,
                    CityParkVegetationProfile.MaxSubMeshesPerLod);
                for (int subMesh = 0; subMesh < subMeshCount; subMesh++)
                {
                    var key = new ChunkKey(chunkX, chunkZ, instance.Variant, subMesh);
                    if (!chunks.TryGetValue(key, out List<CombineInstance> list))
                    {
                        list = new List<CombineInstance>();
                        chunks.Add(key, list);
                    }
                    list.Add(new CombineInstance
                    {
                        mesh = fallbackMesh,
                        subMeshIndex = subMesh,
                        transform = root.transform.worldToLocalMatrix
                            * instance.Transform.localToWorldMatrix
                    });
                }
            }

            int meshIndex = 0;
            foreach (KeyValuePair<ChunkKey, List<CombineInstance>> chunk in chunks)
            {
                string chunkName = string.Format(
                    "CityPark_Fallback_{0}_{1}_{2}_{3}",
                    chunk.Key.X,
                    chunk.Key.Z,
                    chunk.Key.Variant,
                    chunk.Key.SubMesh);
                int assetIndex = meshIndex++;
                string assetName = "CityParkFallback_" + assetIndex;
                var mesh = new Mesh
                {
                    // Unity warns when the main object's name differs from
                    // its .asset filename. Keep spatial identity on the child
                    // GameObject and a stable filename-compatible mesh name.
                    name = assetName,
                    indexFormat = IndexFormat.UInt32
                };
                mesh.CombineMeshes(chunk.Value.ToArray(), true, true, false);
                string path = string.Format(
                    "{0}/{1}.asset",
                    folder,
                    assetName);
                Mesh existingMesh = AssetDatabase.LoadAssetAtPath<Mesh>(path);
                if (existingMesh == null)
                    AssetDatabase.CreateAsset(mesh, path);
                else
                {
                    EditorUtility.CopySerialized(mesh, existingMesh);
                    UnityEngine.Object.DestroyImmediate(mesh);
                    mesh = existingMesh;
                }

                var child = new GameObject(chunkName);
                child.transform.SetParent(root.transform, false);
                child.AddComponent<MeshFilter>().sharedMesh = mesh;
                MeshRenderer renderer = child.AddComponent<MeshRenderer>();
                SourceInstance source = instances.First(instance =>
                    instance.Variant == chunk.Key.Variant);
                renderer.sharedMaterial = source.Materials != null
                    && chunk.Key.SubMesh < source.Materials.Length
                        ? source.Materials[chunk.Key.SubMesh]
                        : null;
                renderer.shadowCastingMode = ShadowCastingMode.Off;
                renderer.receiveShadows = true;
            }
            root.SetActive(false);
            return root;
        }

        internal static bool ValidateCompiledPrefab(GameObject prefab, List<string> issues)
        {
            CityParkVegetationAnchor anchor = prefab.GetComponent<CityParkVegetationAnchor>();
            bool hasParkOutputs = FindOutput(prefab, "OUT_PARK_GROUND") != null
                || FindOutput(prefab, "OUT_PARK_PATHS") != null
                || FindOutput(prefab, "OUT_PARK_WATER") != null;
            if (!hasParkOutputs && anchor == null)
                return true;
            if (anchor == null)
            {
                issues.Add("City Park output exists without CityParkVegetationAnchor.");
                return false;
            }
            if (FindOutput(prefab, "OUT_PARK_TREES") != null)
                issues.Add("Final Bake still contains OUT_PARK_TREES GameObjects.");
            if (FindOutput(prefab, "OUT_PARK_EXCLUSION") != null)
                issues.Add("Final Bake still contains raw OUT_PARK_EXCLUSION geometry.");
            Transform collision = FindOutput(prefab, "OUT_PARK_COLLISION");
            if (collision != null
                && collision.GetComponentsInChildren<Renderer>(true).Length > 0)
                issues.Add("Final Bake OUT_PARK_COLLISION must contain no Renderer component.");
            if (anchor.VegetationData == null || anchor.SiteExclusionData == null)
                issues.Add("City Park Bake data assets are not assigned.");
            return issues.Count == 0;
        }

        private static Transform FindOutput(GameObject root, string name)
        {
            return root.GetComponentsInChildren<Transform>(true)
                .FirstOrDefault(transform => transform.name.IndexOf(
                    name,
                    StringComparison.OrdinalIgnoreCase) >= 0);
        }

        private static T LoadOrCreate<T>(string path) where T : ScriptableObject
        {
            T asset = AssetDatabase.LoadAssetAtPath<T>(path);
            if (asset != null)
                return asset;
            asset = ScriptableObject.CreateInstance<T>();
            AssetDatabase.CreateAsset(asset, path);
            return asset;
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
