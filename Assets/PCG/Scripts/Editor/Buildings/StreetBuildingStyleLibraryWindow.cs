#if UNITY_EDITOR
using System;
using System.Linq;
using PCGBike.Buildings;
using UnityEditor;
using UnityEngine;

namespace PCGBike.Editor.Buildings
{
    /// <summary>
    /// Library + StyleConfig 聚合入口；Catalog/Payload 不在美术界面暴露。
    /// </summary>
    public sealed class StreetBuildingStyleLibraryWindow : EditorWindow
    {
        private StreetBuildingStyleLibrary _library;
        private StreetBuildingStyleConfig _style;
        private Vector2 _scroll;

        [MenuItem("PCG/Street Building/Open Style Library & StyleConfig", priority = 2250)]
        public static void OpenMenu() => Open(null, null);

        public static void Open(
            StreetBuildingStyleLibrary library,
            StreetBuildingStyleConfig style)
        {
            StreetBuildingStyleLibraryWindow window = GetWindow<StreetBuildingStyleLibraryWindow>();
            window.titleContent = new GUIContent("Building Styles");
            if (library != null) window._library = library;
            if (style != null) window._style = style;
            window.minSize = new Vector2(560, 420);
            window.Show();
        }

        private void OnGUI()
        {
            EditorGUILayout.LabelField("StreetBuilding Style Configuration", EditorStyles.boldLabel);
            EditorGUILayout.HelpBox(
                "Library 使用 BuildingId + Seed + UsageTag 稳定加权选择 StyleConfig；"
                + "每个 StyleConfig 是一个风格的唯一事实源，模块按用途分组直接拖拽。",
                MessageType.Info);
            _library = (StreetBuildingStyleLibrary)EditorGUILayout.ObjectField(
                "Style Library", _library, typeof(StreetBuildingStyleLibrary), false);
            _style = (StreetBuildingStyleConfig)EditorGUILayout.ObjectField(
                "Selected StyleConfig", _style, typeof(StreetBuildingStyleConfig), false);

            _scroll = EditorGUILayout.BeginScrollView(_scroll);
            DrawSerializedList(_library, "_styles", "StyleConfig 列表");
            foreach (string property in new[] { "_groundFacade", "_upperFacade", "_sideRear",
                         "_convexConcaveCorners", "_columnTrimCornice", "_roofParapet", "_attachments" })
                DrawSerializedList(_style, property, property.TrimStart('_'));
            if (_style != null)
            {
                EditorGUILayout.Space();
                EditorGUILayout.LabelField("Coverage Summary", EditorStyles.boldLabel);
                foreach (var group in _style.EnumerateModules().Where(item => item.Module != null)
                             .GroupBy(item => item.Module.ModuleRole).OrderBy(item => item.Key))
                    EditorGUILayout.LabelField(group.Key.ToString(), string.Join(", ",
                        group.Select(item => item.Module.VariantId)));
                if (GUILayout.Button("Validate Selected StyleConfig"))
                {
                    StreetBuildingStyleValidationReport report = StreetBuildingStyleValidator.Validate(_style);
                    if (report.IsValid) Debug.Log(report, _style);
                    else Debug.LogError(report, _style);
                }
            }
            EditorGUILayout.EndScrollView();
        }

        private static void DrawSerializedList(UnityEngine.Object target, string path, string label)
        {
            if (target == null) return;
            var serialized = new SerializedObject(target);
            serialized.Update();
            SerializedProperty property = serialized.FindProperty(path);
            EditorGUILayout.Space();
            EditorGUILayout.PropertyField(property, new GUIContent(label), true);
            if (serialized.ApplyModifiedProperties())
            {
                EditorUtility.SetDirty(target);
                AssetDatabase.SaveAssetIfDirty(target);
            }
        }
    }
}
#endif
