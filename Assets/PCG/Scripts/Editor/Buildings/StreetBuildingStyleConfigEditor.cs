#if UNITY_EDITOR
using System;
using System.Linq;
using PCGBike.Buildings;
using UnityEditor;
using UnityEngine;

namespace PCGBike.Editor.Buildings
{
    [CustomEditor(typeof(StreetBuildingStyleConfig))]
    public sealed class StreetBuildingStyleConfigEditor : UnityEditor.Editor
    {
        private static readonly (string Property, string Label)[] Groups =
        {
            ("_groundFacade", "首层墙面 / 铺面 / 门"),
            ("_upperFacade", "上层墙面 / 窗 / 空白"),
            ("_sideRear", "侧墙 / 背墙"),
            ("_convexConcaveCorners", "阳角 / 阴角"),
            ("_columnTrimCornice", "柱 / 腰线 / Cornice"),
            ("_roofParapet", "屋顶 / 女儿墙"),
            ("_attachments", "配件：雨棚 / 招牌 / 消防梯 / 空调 / 屋顶物件"),
        };

        public override void OnInspectorGUI()
        {
            serializedObject.Update();
            EditorGUILayout.LabelField("风格总配置", EditorStyles.boldLabel);
            EditorGUILayout.PropertyField(serializedObject.FindProperty("_cellWidth"), new GUIContent("单元宽度 (m)"));
            EditorGUILayout.PropertyField(serializedObject.FindProperty("_groundFloorHeight"), new GUIContent("首层高度 (m)"));
            EditorGUILayout.PropertyField(serializedObject.FindProperty("_typicalFloorHeight"), new GUIContent("标准层高度 (m)"));
            EditorGUILayout.PropertyField(serializedObject.FindProperty("_allowedAssetRoots"), new GUIContent("允许的 Prefab 目录"), true);

            foreach ((string property, string label) in Groups)
            {
                EditorGUILayout.Space(4);
                EditorGUILayout.PropertyField(serializedObject.FindProperty(property), new GUIContent(label), true);
            }
            serializedObject.ApplyModifiedProperties();

            StreetBuildingStyleConfig style = (StreetBuildingStyleConfig)target;
            int total = style.EnumerateModules().Count();
            int enabled = style.EnumerateModules().Count(item => item.Module != null && item.Module.Enabled);
            int missing = style.EnumerateModules().Count(item => item.Module == null || item.Module.Prefab == null);
            EditorGUILayout.HelpBox($"模块总数 {total} / 启用 {enabled} / 缺失 Prefab {missing}",
                missing == 0 ? MessageType.Info : MessageType.Error);

            using (new EditorGUILayout.HorizontalScope())
            {
                if (GUILayout.Button("批量生成稳定 VariantId")) AssignVariantIds(style);
                if (GUILayout.Button("定位首个缺失模块")) PingFirstMissing(style);
            }
            using (new EditorGUILayout.HorizontalScope())
            {
                if (GUILayout.Button("Validate")) LogValidation(style);
                if (GUILayout.Button("Compile Preview")) CompilePreview(style);
            }
        }

        private static void AssignVariantIds(StreetBuildingStyleConfig style)
        {
            Undo.RecordObject(style, "Assign StreetBuilding Variant IDs");
            foreach ((_, StreetBuildingModuleDefinition module) in style.EnumerateModules())
                if (module != null && module.Prefab != null && string.IsNullOrWhiteSpace(module.VariantId))
                    module.SetEditorVariantId(StreetBuildingStyleCompiler.BuildStableVariantId(module.ModuleRole, module.Prefab));
            EditorUtility.SetDirty(style);
        }

        private static void PingFirstMissing(StreetBuildingStyleConfig style)
        {
            StreetBuildingModuleDefinition module = style.EnumerateModules()
                .Select(item => item.Module).FirstOrDefault(value => value == null || value.Prefab == null);
            if (module == null) Debug.Log("StyleConfig 没有缺失 Prefab。", style);
            else Debug.LogWarning("StyleConfig 存在缺失 Prefab，请展开对应分组检查。", style);
        }

        private static void LogValidation(StreetBuildingStyleConfig style)
        {
            StreetBuildingStyleValidationReport report = StreetBuildingStyleValidator.Validate(style);
            if (report.IsValid) Debug.Log(report, style); else Debug.LogError(report, style);
        }

        private static void CompilePreview(StreetBuildingStyleConfig style)
        {
            try
            {
                StreetBuildingCompiledStyle result = StreetBuildingStyleCompiler.Compile(style);
                Debug.Log($"Style payload compile PASS: {result.ModuleCount} modules / SHA-256 {result.Sha256}\n{result.Payload}", style);
            }
            catch (Exception exception) { Debug.LogError("Style payload compile failed.\n" + exception, style); }
        }
    }
}
#endif
