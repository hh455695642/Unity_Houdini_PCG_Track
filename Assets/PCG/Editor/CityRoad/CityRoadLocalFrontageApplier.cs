#if UNITY_EDITOR
using System;
using System.Collections.Generic;
using System.Linq;
using HoudiniEngineUnity;
using UnityEditor;
using UnityEngine;

namespace PCG.CityRoad.Editor
{
    internal static class CityRoadLocalFrontageApplier
    {
        private const float PositionTolerance = .01f;
        private const float ScaleTolerance = .001f;
        private const float RotationTolerance = .1f;

        internal static bool TryApply(HEU_HoudiniAssetRoot source, GameObject output, out bool changed, out string report)
        {
            changed = false;
            report = string.Empty;
            var parent = source.transform.parent;
            var siblings = parent != null ? parent.Cast<Transform>().Select(t => t.gameObject)
                : source.gameObject.scene.GetRootGameObjects();
            var frontages = siblings.Where(obj => obj.name == "CityRoad_Overrides")
                .SelectMany(obj => obj.GetComponentsInChildren<CityRoadLocalFrontage>(true))
                .Where(frontage => frontage.Source == source.transform).ToArray();
            if (frontages.Length == 0)
                return true;

            var groups = output.GetComponentsInChildren<Transform>(true)
                .Where(t => t.name.Contains("OUT_STREET_BUILDINGS", StringComparison.Ordinal)
                    && !t.name.Contains("_Instance", StringComparison.Ordinal)).ToArray();
            if (groups.Length != 1)
            {
                foreach (var frontage in frontages)
                    SetActive(frontage.Replacement, false, ref changed);
                report = "CityRoad 局部街面需要唯一的 OUT_STREET_BUILDINGS 输出。";
                return false;
            }

            // Compare the generated building's original source Prefab and local transform.
            // HEU instance names are ordinal-based and can change across cooks.
            var outputSpace = output.transform;
            var candidates = new Dictionary<GameObject, List<Transform>>();
            foreach (Transform item in groups[0])
            {
                var prefab = PrefabUtility.GetCorrespondingObjectFromOriginalSource(item.gameObject);
                if (prefab == null)
                    continue;
                if (!candidates.TryGetValue(prefab, out var entries))
                    candidates.Add(prefab, entries = new List<Transform>());
                entries.Add(item);
            }

            var taken = new HashSet<Transform>();
            var valid = new List<CityRoadLocalFrontage>();
            var inactive = new List<(CityRoadLocalFrontage frontage, List<Transform> matches)>();
            var issues = new List<string>();
            foreach (var frontage in frontages)
            {
                var matches = new List<Transform>();
                // Keep this descriptor on an EditorOnly child next to the native replacement group.
                bool complete = frontage.Replacement != null && frontage.Replacement.transform.parent == frontage.transform.parent
                    && frontage.ReplacedBuildings.Length > 0;
                foreach (var binding in frontage.ReplacedBuildings)
                {
                    if (binding.prefab == null || !candidates.TryGetValue(binding.prefab, out var entries))
                    {
                        complete = false;
                        continue;
                    }
                    var matching = entries.Where(item => Fits(outputSpace, item, binding)).Take(2).ToArray();
                    if (matching.Length != 1 || matches.Contains(matching[0]))
                    {
                        complete = false;
                        continue;
                    }
                    matches.Add(matching[0]);
                }

                if (!complete || matches.Any(taken.Contains))
                {
                    if (frontage.isActiveAndEnabled)
                        issues.Add($"{frontage.name} 的原楼定位不完整或与其他覆盖重叠（匹配 {matches.Count}/{frontage.ReplacedBuildings.Length}）。");
                    inactive.Add((frontage, matches));
                    continue;
                }

                if (!frontage.isActiveAndEnabled)
                {
                    inactive.Add((frontage, matches));
                    continue;
                }

                valid.Add(frontage);
                taken.UnionWith(matches);
            }

            // Validate all source references before hiding any original building.
            // An invalid lock restores the original buildings it can still identify.
            foreach (var item in inactive)
            {
                SetActive(item.frontage.Replacement, false, ref changed);
                foreach (var original in item.matches)
                    if (!taken.Contains(original))
                        SetActive(original.gameObject, true, ref changed);
            }
            foreach (Transform original in taken)
                SetActive(original.gameObject, false, ref changed);
            foreach (var frontage in valid)
                SetActive(frontage.Replacement, true, ref changed);

            report = string.Join(Environment.NewLine, issues);
            return issues.Count == 0;
        }

        private static bool Fits(Transform root, Transform item, CityRoadLocalFrontage.Building binding)
        {
            Vector3 position = root.InverseTransformPoint(item.position);
            Quaternion rotation = Quaternion.Inverse(root.rotation) * item.rotation;
            return (position - binding.position).sqrMagnitude <= PositionTolerance * PositionTolerance
                && (item.localScale - binding.scale).sqrMagnitude <= ScaleTolerance * ScaleTolerance
                && Quaternion.Angle(rotation, binding.rotation) <= RotationTolerance;
        }

        private static void SetActive(GameObject item, bool active, ref bool changed)
        {
            if (item == null || item.activeSelf == active)
                return;

            item.SetActive(active);
            // Persist nested Prefab overrides on the scene instance, never on a shared asset.
            PrefabUtility.RecordPrefabInstancePropertyModifications(item);
            changed = true;
        }
    }
}
#endif
