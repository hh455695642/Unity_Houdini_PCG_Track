#if UNITY_EDITOR
using System;
using System.Collections.Generic;
using PCGBike.Buildings;
using UnityEditor;
using UnityEngine;

namespace PCGBike.Editor.Buildings
{
    public static class StreetBuildingLayerMigration
    {
        // Explicit one-time scene migration. Existing instances keep their
        // selected HDA rule source, including instances without a saved hash.
        public static int PreserveOpenedSceneRuleSources()
        {
            int changed = 0;
            foreach (var authoring in Resources.FindObjectsOfTypeAll<StreetBuildingAuthoring>())
            {
                if (!authoring.gameObject.scene.IsValid() || authoring.StyleRuleSourceInitialized) continue;
                Undo.RecordObject(authoring, "保留已有建筑实例规则");
                authoring.SetEditorRuleSourceInitialized(true);
                EditorUtility.SetDirty(authoring);
                UnityEditor.SceneManagement.EditorSceneManager.MarkSceneDirty(authoring.gameObject.scene);
                changed++;
            }
            return changed;
        }
        public static void Migrate(StreetBuildingStyleConfig style)
        {
            Undo.RecordObject(style, "迁移建筑三层配置");
            if (style.MigrateLayers()) EditorUtility.SetDirty(style);
        }

        // Do not save automatically: the regression gate owns persistence.
        [MenuItem("PCG/Street Building/Migrate All Styles To Layers")]
        public static void MigrateAll()
        {
            var originals = new Dictionary<StreetBuildingStyleConfig, string>();
            try
            {
                foreach (string guid in AssetDatabase.FindAssets("t:StreetBuildingStyleConfig"))
                {
                    string path = AssetDatabase.GUIDToAssetPath(guid);
                    if (!path.StartsWith("Assets/PCG/", StringComparison.Ordinal))
                        throw new InvalidOperationException("Style outside authorized PCG scope: " + path);
                    var style = AssetDatabase.LoadAssetAtPath<StreetBuildingStyleConfig>(path);
                    originals[style] = EditorJsonUtility.ToJson(style);
                    Migrate(style);
                }
                Debug.Log($"StreetBuilding layer migration PASS: {originals.Count} styles; assets not saved yet.");
            }
            catch
            {
                foreach (var item in originals) EditorJsonUtility.FromJsonOverwrite(item.Value, item.Key);
                throw;
            }
        }
    }
}
#endif
