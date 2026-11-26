#if UNITY_EDITOR
using System;
using System.Collections.Generic;
using System.Globalization;
using System.Linq;
using HoudiniEngineUnity;
using UnityEditor;
using UnityEngine;

namespace PCG.CityRoad.Editor
{
    [CreateAssetMenu(menuName = "PCG/CityRoad/Frontage Catalog", fileName = "CityRoadFrontageCatalog")]
    public sealed class CityRoadFrontageCatalog : ScriptableObject
    {
        internal const string ModeParameter = "building_fit_frontage";
        internal const string PayloadParameter = "building_frontage_catalog";
        private const string MinimumGapParameter = "building_gap_min_m";
        private const string MaximumGapParameter = "building_gap_max_m";
        private const string PrefabCountParameter = "building_prefabs";
        private const string PrefabParameterPrefix = "building_prefab";
        private const float GeometryTolerance = 0.01f;

        [Serializable]
        private sealed class Entry
        {
            public GameObject prefab = null;

            [Tooltip("Prefab 根局部坐标，+Z 朝街。X/Y 分别为首层临街面的最小与最大 X，Z 为墙面位置，单位米。")]
            public Vector3 frontage = default;

            [Tooltip("Prefab 根局部坐标中的占地矩形。X/Y 轴分别表示 X/Z，单位米。")]
            public Rect occupancy = default;
        }

        [SerializeField] private Entry[] entries = Array.Empty<Entry>();

        internal static bool TrySynchronize(HEU_HoudiniAsset asset, out string report) =>
            TrySynchronize(asset, out report, out _);

        internal static bool TrySynchronize(HEU_HoudiniAsset asset, out string report, out bool changed)
        {
            report = string.Empty;
            changed = false;
            var parameters = asset?.Parameters;
            var mode = parameters?.GetParameter(ModeParameter);
            if (mode != null)
            {
                // A cached legacy instance still exposes the fit option until HEU reloads it.
                if (!mode._toggle && (mode._intValues == null ||
                    mode._intValues.Length == 0 || mode._intValues[0] == 0))
                    return true;
            }
            else if (parameters?.GetParameter(MinimumGapParameter) == null ||
                parameters.GetParameter(MaximumGapParameter) == null)
            {
                // HEU omits the hidden legacy fit field on unified instances. Their
                // absolute gap endpoints distinguish them from pre-frontage definitions.
                return true;
            }

            var count = parameters.GetParameter(PrefabCountParameter);
            var session = asset.GetAssetSession(false);
            if (count == null || asset.AssetID < 0 || session == null || !asset.IsAssetValid())
            {
                report = "CityRoad 临街数据无法同步，HAPI 实例或 Prefab 列表尚未就绪。";
                return false;
            }

            var paths = new List<string>();
            for (int index = 0; index < count._parmInfo.instanceCount; ++index)
            {
                string name = PrefabParameterPrefix + (index + count._parmInfo.instanceStartOffset)
                    .ToString(CultureInfo.InvariantCulture);
                // heuassetpath is a string, not an HEU object-merge input.
                var slot = parameters.GetParameter(name);
                if (slot?._stringValues?.Length > 0)
                    paths.Add(slot._stringValues[0]);
            }

            bool complete = TryBuild(paths, out string payload, out report);
            if (CityRoadCornerCatalog.IsEnabled(parameters))
            {
                string[] cornerPaths = CityRoadCornerCatalog.RequestedPaths(parameters);
                bool cornersComplete = CityRoadCornerCatalog.TryBuild(cornerPaths,
                    out string cornerPayload, out string cornerReport);
                if (!string.IsNullOrEmpty(cornerPayload))
                    payload = string.IsNullOrEmpty(payload) ? cornerPayload : payload + "\n" + cornerPayload;
                if (!string.IsNullOrEmpty(cornerReport))
                    report = string.IsNullOrEmpty(report) ? cornerReport : report + Environment.NewLine + cornerReport;
                complete &= cornersComplete;
            }
            // Hidden parameters are omitted from the Inspector cache. Use the live HAPI value.
            // On validation failure, upload the valid rows only so deleted or replaced prefabs
            // cannot inherit stale dimensions from the previous cook.
            if (session.GetParmStringValue(asset.AssetID, PayloadParameter, 0, false, out int handle) &&
                string.Equals(HEU_SessionManager.GetString(handle, session), payload, StringComparison.Ordinal))
                return complete;
            if (!session.SetParamStringValue(asset.AssetID, PayloadParameter, payload, 0))
            {
                report = string.IsNullOrEmpty(report) ? "HAPI 无法写入沿街素材数据。"
                    : report + Environment.NewLine + "HAPI 无法写入沿街素材数据。";
                return false;
            }

            changed = true;
            return complete;
        }

        internal static bool TryBuild(IEnumerable<string> prefabPaths, out string payload, out string report)
        {
            string[] paths = prefabPaths.Where(path => !string.IsNullOrWhiteSpace(path))
                .Select(path => path.Trim()).Distinct(StringComparer.Ordinal)
                .OrderBy(path => path, StringComparer.Ordinal).ToArray();
            var requested = new HashSet<string>(paths.Select(AssetDatabase.AssetPathToGUID)
                .Where(guid => !string.IsNullOrEmpty(guid)), StringComparer.Ordinal);
            var errors = new List<string>();
            var overrides = ReadOverrides(requested, errors);
            var rows = new List<string>(paths.Length);
            foreach (string path in paths)
            {
                if (path.IndexOfAny(new[] { '|', '\r', '\n' }) >= 0)
                {
                    errors.Add("Prefab 路径含沿街素材协议分隔符 " + path);
                    continue;
                }

                var prefab = AssetDatabase.LoadAssetAtPath<GameObject>(path);
                if (prefab == null || !PrefabUtility.IsPartOfPrefabAsset(prefab))
                {
                    errors.Add("Prefab 无法加载 " + path);
                    continue;
                }

                string guid = AssetDatabase.AssetPathToGUID(path);
                overrides.TryGetValue(guid, out Entry authored);
                if (!TryMeasure(prefab, authored, out Vector3 frontage, out Rect occupancy, out string reason))
                {
                    errors.Add(path + " — " + reason);
                    continue;
                }

                // Protocol deliberately uses Unity local X. BUILD_FRONTAGE reflects X
                // when converting to Houdini space, including asymmetric prefabs.
                rows.Add(string.Join("|", path, Number(frontage.x), Number(frontage.y), Number(frontage.z),
                    Number(occupancy.xMin), Number(occupancy.xMax),
                    Number(occupancy.yMin), Number(occupancy.yMax)));
            }

            payload = string.Join("\n", rows);
            report = errors.Count == 0 ? string.Empty : string.Join(Environment.NewLine, errors);
            return errors.Count == 0;
        }

        private static Dictionary<string, Entry> ReadOverrides(HashSet<string> requested, List<string> errors)
        {
            var overrides = new Dictionary<string, Entry>(StringComparer.Ordinal);
            var duplicates = new HashSet<string>(StringComparer.Ordinal);
            foreach (string assetGuid in AssetDatabase.FindAssets("t:CityRoadFrontageCatalog")
                         .OrderBy(guid => guid, StringComparer.Ordinal))
            {
                var catalog = AssetDatabase.LoadAssetAtPath<CityRoadFrontageCatalog>(
                    AssetDatabase.GUIDToAssetPath(assetGuid));
                if (catalog == null || catalog.entries == null)
                    continue;
                foreach (Entry entry in catalog.entries)
                {
                    if (entry == null || entry.prefab == null)
                        continue;
                    string path = AssetDatabase.GetAssetPath(entry.prefab);
                    string guid = AssetDatabase.AssetPathToGUID(path);
                    if (!requested.Contains(guid) || duplicates.Contains(guid))
                        continue;
                    if (overrides.ContainsKey(guid))
                    {
                        errors.Add("Prefab 存在多条沿街覆盖 " + path);
                        overrides.Remove(guid);
                        duplicates.Add(guid);
                    }
                    else
                        overrides.Add(guid, entry);
                }
            }
            return overrides;
        }

        private static bool TryMeasure(GameObject prefab, Entry authored, out Vector3 frontage,
            out Rect occupancy, out string reason)
        {
            frontage = default;
            occupancy = default;
            reason = string.Empty;
            Transform root = prefab.transform;
            Vector3 scale = root.localScale;
            if (Quaternion.Angle(root.localRotation, Quaternion.identity) > 0.01f ||
                !Finite(scale.x) || !Finite(scale.z) || scale.x <= 0f || scale.z <= 0f)
            {
                reason = "Prefab 根节点须采用 +Z 朝街、零旋转及正数 X/Z 缩放。";
                return false;
            }

            var boxes = new List<Rect>();
            foreach (BoxCollider box in prefab.GetComponentsInChildren<BoxCollider>(true))
            {
                if (!box.enabled || box.isTrigger || !IsActiveBelowRoot(box.transform, root))
                    continue;
                Rect bounds = TransformBounds(new Bounds(box.center, box.size), ToRoot(box.transform, root));
                if (Valid(bounds))
                    boxes.Add(bounds);
            }

            if (authored != null)
            {
                frontage = authored.frontage;
                occupancy = authored.occupancy;
                if (!Valid(occupancy) || !Finite(frontage.x) || !Finite(frontage.y) ||
                    !Finite(frontage.z) || frontage.y - frontage.x < GeometryTolerance ||
                    frontage.x < occupancy.xMin - GeometryTolerance ||
                    frontage.y > occupancy.xMax + GeometryTolerance ||
                    frontage.z < occupancy.yMin - GeometryTolerance ||
                    frontage.z > occupancy.yMax + GeometryTolerance)
                {
                    reason = "人工临街面无效或超出声明的占地范围。";
                    return false;
                }
            }
            else
            {
                if (boxes.Count == 0)
                {
                    reason = "缺少有效 BoxCollider 和人工标注。";
                    return false;
                }

                float wallZ = boxes.Max(box => box.yMax);
                // Recessed sections reserve space without extending the wall used for coverage.
                Rect[] leading = boxes.Where(box => wallZ - box.yMax < GeometryTolerance)
                    .OrderBy(box => box.xMin).ToArray();
                var run = new Vector2(leading[0].xMin, leading[0].xMax);
                var longest = run;
                foreach (Rect box in leading.Skip(1))
                {
                    if (box.xMin <= run.y + GeometryTolerance)
                        run.y = Mathf.Max(run.y, box.xMax);
                    else
                        run = new Vector2(box.xMin, box.xMax);
                    if (run.y - run.x > longest.y - longest.x)
                        longest = run;
                }
                frontage = new Vector3(longest.x, longest.y, wallZ);
                occupancy = boxes[0];
            }

            foreach (Rect box in boxes)
                occupancy = Union(occupancy, box);

            // Include enabled rendered overhangs in occupancy. The wall reference
            // remains the leading ground-floor collision face or the artist override.
            foreach (Renderer renderer in prefab.GetComponentsInChildren<Renderer>(true))
            {
                if (!renderer.enabled || !IsActiveBelowRoot(renderer.transform, root))
                    continue;
                Bounds local;
                if (renderer is MeshRenderer)
                {
                    Mesh mesh = renderer.GetComponent<MeshFilter>()?.sharedMesh;
                    if (mesh == null)
                        continue;
                    local = mesh.bounds;
                }
                else if (renderer is SkinnedMeshRenderer skinned && skinned.sharedMesh != null)
                    local = skinned.localBounds;
                else
                    continue;
                Rect bounds = TransformBounds(local, ToRoot(renderer.transform, root));
                if (Valid(bounds))
                    occupancy = Union(occupancy, bounds);
            }

            frontage = new Vector3(frontage.x * scale.x, frontage.y * scale.x, frontage.z * scale.z);
            occupancy = Rect.MinMaxRect(occupancy.xMin * scale.x, occupancy.yMin * scale.z,
                occupancy.xMax * scale.x, occupancy.yMax * scale.z);
            return true;
        }

        private static bool IsActiveBelowRoot(Transform child, Transform root)
        {
            for (Transform node = child; node != root; node = node.parent)
                if (!node.gameObject.activeSelf)
                    return false;
            return true;
        }

        private static Matrix4x4 ToRoot(Transform child, Transform root)
        {
            Matrix4x4 matrix = Matrix4x4.identity;
            for (Transform node = child; node != root; node = node.parent)
                matrix = Matrix4x4.TRS(node.localPosition, node.localRotation, node.localScale) * matrix;
            return matrix;
        }

        private static Rect TransformBounds(Bounds bounds, Matrix4x4 transform)
        {
            Vector3 center = transform.MultiplyPoint3x4(bounds.center);
            Vector3 extents = bounds.extents;
            float x = Mathf.Abs(transform.m00) * extents.x + Mathf.Abs(transform.m01) * extents.y +
                      Mathf.Abs(transform.m02) * extents.z;
            float z = Mathf.Abs(transform.m20) * extents.x + Mathf.Abs(transform.m21) * extents.y +
                      Mathf.Abs(transform.m22) * extents.z;
            return Rect.MinMaxRect(center.x - x, center.z - z, center.x + x, center.z + z);
        }

        private static Rect Union(Rect a, Rect b) => Rect.MinMaxRect(
            Mathf.Min(a.xMin, b.xMin), Mathf.Min(a.yMin, b.yMin),
            Mathf.Max(a.xMax, b.xMax), Mathf.Max(a.yMax, b.yMax));

        private static bool Valid(Rect bounds) =>
            Finite(bounds.xMin) && Finite(bounds.xMax) && Finite(bounds.yMin) && Finite(bounds.yMax) &&
            bounds.width >= GeometryTolerance && bounds.height >= GeometryTolerance;

        private static bool Finite(float value) => !float.IsNaN(value) && !float.IsInfinity(value);
        private static string Number(float value) => value.ToString("R", CultureInfo.InvariantCulture);
    }
}
#endif
