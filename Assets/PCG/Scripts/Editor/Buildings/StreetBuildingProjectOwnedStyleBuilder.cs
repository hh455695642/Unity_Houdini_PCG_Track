#if UNITY_EDITOR
using System;
using System.IO;
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
