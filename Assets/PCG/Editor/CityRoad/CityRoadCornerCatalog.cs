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
    [CreateAssetMenu(menuName = "PCG/CityRoad/Corner Catalog", fileName = "CityRoadCornerCatalog")]
    public sealed class CityRoadCornerCatalog : ScriptableObject
    {
        internal const string ModeParameter = "building_corners_enabled";
        internal const string PrefabCountParameter = "building_corner_prefabs";
        private const string PrefabParameterPrefix = "building_corner_prefab";
        private const float Tolerance = 0.01f;

        private enum Side { Left = -1, Right = 1 }

        [Serializable]
        private sealed class Corner
        {
            public GameObject prefab = null;

            [Tooltip("站在建筑内部面向 +Z，左侧为 -X，右侧为 +X。仅为真实临街立面标注。")]
            public Side side = Side.Right;

            [Tooltip("首层主临街墙面的最小 X、最大 X、墙面 Z。使用 Prefab 根局部米制坐标。")]
            public Vector3 frontage = default;

            [Tooltip("首层次临街墙面的最小 Z、最大 Z、墙面 X。使用 Prefab 根局部米制坐标。")]
            public Vector3 secondFrontage = default;
        }

        [SerializeField] private Corner[] corners = Array.Empty<Corner>();

        internal static bool IsEnabled(HEU_Parameters parameters)
        {
            var mode = parameters?.GetParameter(ModeParameter);
            return mode != null && (mode._toggle ||
                mode._intValues?.Length > 0 && mode._intValues[0] != 0);
        }

        internal static string[] RequestedPaths(HEU_Parameters parameters)
        {
            var count = parameters?.GetParameter(PrefabCountParameter);
            if (count == null)
                return Array.Empty<string>();

            var paths = new List<string>();
            for (int index = 0; index < count._parmInfo.instanceCount; index++)
            {
                string name = PrefabParameterPrefix + (index + count._parmInfo.instanceStartOffset)
                    .ToString(CultureInfo.InvariantCulture);
                var slot = parameters.GetParameter(name);
                if (slot?._stringValues?.Length > 0 && !string.IsNullOrWhiteSpace(slot._stringValues[0]))
                    paths.Add(slot._stringValues[0].Trim());
            }
            return paths.ToArray();
        }

        internal static bool TryBuild(IEnumerable<string> cornerPaths, out string payload, out string report)
        {
            string[] paths = cornerPaths.Distinct(StringComparer.Ordinal)
                .OrderBy(path => path, StringComparer.Ordinal).ToArray();
            payload = string.Empty;
            report = string.Empty;
            if (paths.Length == 0)
                return true;

            var errors = new List<string>();
            if (!CityRoadFrontageCatalog.TryBuild(paths, out string occupancyPayload, out string measureReport))
                errors.Add(measureReport);

            var measured = occupancyPayload.Split(new[] { '\n' }, StringSplitOptions.RemoveEmptyEntries)
                .Select(row => row.Split('|')).ToDictionary(row => row[0], StringComparer.Ordinal);
            var annotations = ReadAnnotations(paths, errors);
            var rows = new List<string>(paths.Length);
            foreach (string path in paths)
            {
                if (!measured.TryGetValue(path, out string[] occupancy))
                    continue;
                if (!annotations.TryGetValue(path, out Corner corner))
                {
                    errors.Add("角楼未标注真实双临街立面 " + path);
                    continue;
                }

                Vector3 scale = corner.prefab.transform.localScale;
                Vector3 front = new Vector3(corner.frontage.x * scale.x, corner.frontage.y * scale.x,
                    corner.frontage.z * scale.z);
                Vector3 side = new Vector3(corner.secondFrontage.x * scale.z, corner.secondFrontage.y * scale.z,
                    corner.secondFrontage.z * scale.x);
                if (!Valid(front, side, corner.side, occupancy))
                {
                    errors.Add("角楼双立面端点无效、方向错误或超出占地 " + path);
                    continue;
                }

                // Only the corner multiparm emits extended rows. Preserve Unity local X here.
                rows.Add(string.Join("|", path, Number(front.x), Number(front.y), Number(front.z),
                    occupancy[4], occupancy[5], occupancy[6], occupancy[7],
                    ((int)corner.side).ToString(CultureInfo.InvariantCulture),
                    Number(side.x), Number(side.y), Number(side.z)));
            }
            payload = string.Join("\n", rows);
            report = string.Join(Environment.NewLine, errors);
            return errors.Count == 0;
        }

        private static Dictionary<string, Corner> ReadAnnotations(IEnumerable<string> paths, List<string> errors)
        {
            var requested = new HashSet<string>(paths, StringComparer.Ordinal);
            var duplicatePaths = new HashSet<string>(StringComparer.Ordinal);
            var annotations = new Dictionary<string, Corner>(StringComparer.Ordinal);
            foreach (string guid in AssetDatabase.FindAssets("t:CityRoadCornerCatalog")
                         .OrderBy(id => id, StringComparer.Ordinal))
            {
                var catalog = AssetDatabase.LoadAssetAtPath<CityRoadCornerCatalog>(AssetDatabase.GUIDToAssetPath(guid));
                if (catalog == null || catalog.corners == null)
                    continue;
                foreach (Corner corner in catalog.corners)
                {
                    if (corner == null || corner.prefab == null)
                        continue;
                    string path = AssetDatabase.GetAssetPath(corner.prefab);
                    if (!requested.Contains(path) || duplicatePaths.Contains(path))
                        continue;
                    if (annotations.ContainsKey(path))
                    {
                        errors.Add("同一角楼 Prefab 存在多条双立面标注 " + path);
                        annotations.Remove(path);
                        duplicatePaths.Add(path);
                    }
                    else
                        annotations.Add(path, corner);
                }
            }
            return annotations;
        }

        private static bool Valid(Vector3 front, Vector3 side, Side sideName, string[] occupancy)
        {
            float minX = Parse(occupancy[4]), maxX = Parse(occupancy[5]);
            float minZ = Parse(occupancy[6]), maxZ = Parse(occupancy[7]);
            if (!Finite(front) || !Finite(side) || front.y - front.x < Tolerance || side.y - side.x < Tolerance ||
                front.x < minX - Tolerance || front.y > maxX + Tolerance ||
                front.z < minZ - Tolerance || front.z > maxZ + Tolerance ||
                side.x < minZ - Tolerance || side.y > front.z + Tolerance ||
                side.z < minX - Tolerance || side.z > maxX + Tolerance)
                return false;
            // A chamfer may shorten each wall before the shared street corner.
            return sideName == Side.Left && side.z <= front.x + Tolerance ||
                   sideName == Side.Right && side.z >= front.y - Tolerance;
        }

        private static bool Finite(Vector3 point) => Finite(point.x) && Finite(point.y) && Finite(point.z);
        private static bool Finite(float number) => !float.IsNaN(number) && !float.IsInfinity(number);
        private static float Parse(string number) => float.Parse(number, CultureInfo.InvariantCulture);
        private static string Number(float number) => number.ToString("R", CultureInfo.InvariantCulture);
    }
}
#endif
