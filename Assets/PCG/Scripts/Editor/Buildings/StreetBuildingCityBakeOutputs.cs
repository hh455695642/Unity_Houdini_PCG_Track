#if UNITY_EDITOR
using System;
using System.Collections.Generic;
using UnityEngine;

namespace PCGBike.Editor.Buildings
{
    /// <summary>编辑期城市 Bake 的输出边界；数据、碰撞和独立 LOD 不参与近景合并。</summary>
    public static class StreetBuildingCityBakeOutputs
    {
        static readonly string[] VisualOutputs = { "OUT_BUILDING_LOD0", "OUT_DETAIL_INSTANCES" };
        static readonly string[] NonVisualOutputs = {
            "OUT_BUILDING_METADATA", "OUT_BUILDING_COLLISION", "OUT_BUILDING_LOD1", "OUT_BUILDING_LOD2",
            "OUT_BUILDING_FOOTPRINT", "OUT_FOOTPRINT", "OUT_BUILDING_DEBUG", "OUT_DEBUG"
        };

        static bool Matches(string name, string output)
        {
            return name == output || name.StartsWith(output + "_", StringComparison.Ordinal)
                || name.IndexOf("_" + output + "_", StringComparison.Ordinal) >= 0;
        }

        // 扩展点：新增正式 HDA 输出时明确登记其视觉职责；未知输出禁止悄悄丢弃。
        static bool IsVisual(Transform item, Transform root)
        {
            bool visual = false;
            for (var current = item; current != null; current = current.parent)
            {
                foreach (string output in NonVisualOutputs)
                    if (Matches(current.name, output)) return false;
                foreach (string output in VisualOutputs)
                    if (Matches(current.name, output)) visual = true;
                if (current == root) break;
            }
            if (!visual)
                throw new InvalidOperationException("Unclassified visible StreetBuilding Bake output: " + item.name);
            return true;
        }

        public static MeshFilter[] GetVisualMeshFilters(GameObject root)
        {
            if (root == null) throw new ArgumentNullException(nameof(root));
            var filters = new List<MeshFilter>();
            foreach (var renderer in root.GetComponentsInChildren<MeshRenderer>(true))
            {
                if (!renderer.enabled || !renderer.gameObject.activeInHierarchy) continue;
                if (!IsVisual(renderer.transform, root.transform)) continue;
                var filter = renderer.GetComponent<MeshFilter>();
                if (filter == null || filter.sharedMesh == null || filter.sharedMesh.vertexCount == 0)
                    throw new InvalidOperationException("Visual Bake output has no usable Mesh: " + renderer.name);
                filters.Add(filter);
            }
            if (filters.Count == 0)
                throw new InvalidOperationException("StreetBuilding Bake contains no visible building geometry.");
            // 性能关键点：只在编辑期 Bake 执行，不增加运行时组件、轮询或材质副本。
            return filters.ToArray();
        }
    }
}
#endif
