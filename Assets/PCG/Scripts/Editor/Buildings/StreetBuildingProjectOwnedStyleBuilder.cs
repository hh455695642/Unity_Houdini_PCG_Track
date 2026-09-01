#if UNITY_EDITOR
using System;
using System.IO;
using System.Linq;
using System.Collections.Generic;
using PCGBike.Buildings;
using UnityEditor;
using UnityEngine;

namespace PCGBike.Editor.Buildings
{
    /// <summary>
    /// Create-only StyleConfig Wizard。不会生成/覆盖 Prefab、材质、纹理、Preset 或场景。
    /// </summary>
    public static class StreetBuildingProjectOwnedStyleBuilder
    {
        public const string BrickStyleFolder = "urban_brick_mixeduse_01";
        public const string StuccoStyleFolder = "urban_stucco_residential_01";
        public const string ScenePath = "Assets/PCG/Scenes/PCG_Building.unity";
        public const string ShowcaseRootName = "Phase4_ProjectOwned_Showcase";

        [MenuItem("PCG/Street Building/Create-only StyleConfig Wizard", priority = 2260)]
        public static void CreateStyleConfigWizard()
        {
            string folder = SelectedFolder();
            if (string.IsNullOrEmpty(folder) || !folder.StartsWith("Assets/PCG/", StringComparison.Ordinal))
                throw new InvalidOperationException("请选择 Assets/PCG 下的目标文件夹。");
            string[] existing = AssetDatabase.FindAssets("t:StreetBuildingStyleConfig", new[] { folder });
            if (existing.Length > 0)
                throw new InvalidOperationException("目标目录已存在 StyleConfig；Wizard 拒绝覆盖："
                                                    + AssetDatabase.GUIDToAssetPath(existing[0]));

            string baseName = "SBStyle_" + Path.GetFileName(folder).ToLowerInvariant();
            string path = folder + "/" + baseName + ".asset";
            if (AssetDatabase.LoadMainAssetAtPath(path) != null)
                throw new InvalidOperationException("目标资产已存在，拒绝覆盖：" + path);
            var style = ScriptableObject.CreateInstance<StreetBuildingStyleConfig>();
            AssetDatabase.CreateAsset(style, path);
            AssetDatabase.SaveAssets();
            Selection.activeObject = style;
            EditorGUIUtility.PingObject(style);
            Debug.Log("Create-only StyleConfig created: " + path, style);
        }

        /// <summary>一次性归一化迁移后的六个 Preset；不会改变体块/立面原参数。</summary>
        public static string NormalizeGenerationPresets()
        {
            const string root = "Assets/PCG/Art/StreetBuilding/GenerationPresets";
            string[] paths = AssetDatabase.FindAssets("t:StreetBuildingDesignPreset", new[] { root })
                .Select(AssetDatabase.GUIDToAssetPath).OrderBy(value => value, StringComparer.Ordinal).ToArray();
            if (paths.Length != 6) throw new InvalidOperationException("Expected 6 GenerationPresets, got " + paths.Length);
            foreach (string path in paths)
            {
                StreetBuildingGenerationPreset preset = AssetDatabase.LoadAssetAtPath<StreetBuildingGenerationPreset>(path);
                if (preset == null) throw new InvalidOperationException("Cannot load GenerationPreset: " + path);
                if (preset.AttachmentRules.Count == 0)
                {
                    float density = preset.DetailDensity;
                    preset.SetEditorAttachmentRules(new List<StreetBuildingAttachmentRule>
                    {
                        new(StreetBuildingAttachmentKind.Awning, density, 8,
                            StreetBuildingFacadeMask.Front | StreetBuildingFacadeMask.SecondaryFront, 1, 1),
                        new(StreetBuildingAttachmentKind.Sign, density, 8,
                            StreetBuildingFacadeMask.Front | StreetBuildingFacadeMask.SecondaryFront, 1, 1),
                        new(StreetBuildingAttachmentKind.FireEscape, density * .5f, 4,
                            StreetBuildingFacadeMask.Side | StreetBuildingFacadeMask.Rear, 2, preset.Floors),
                        new(StreetBuildingAttachmentKind.WallAC, density, 16,
                            StreetBuildingFacadeMask.All, 2, preset.Floors),
                        new(StreetBuildingAttachmentKind.RoofProps, density * .5f, 8,
                            StreetBuildingFacadeMask.All, preset.Floors + 1, preset.Floors + 1),
                    });
                }
                EditorUtility.SetDirty(preset);
            }
            AssetDatabase.SaveAssets();
            AssetDatabase.ForceReserializeAssets(paths);
            AssetDatabase.Refresh();
            return "PASS|6|style-free GenerationPresets normalized";
        }

        private static string SelectedFolder()
        {
            string path = AssetDatabase.GetAssetPath(Selection.activeObject);
            if (string.IsNullOrEmpty(path)) return "Assets/PCG/Art/StreetBuilding";
            if (AssetDatabase.IsValidFolder(path)) return path.Replace('\\', '/');
            return Path.GetDirectoryName(path)?.Replace('\\', '/');
        }
    }
}
#endif
