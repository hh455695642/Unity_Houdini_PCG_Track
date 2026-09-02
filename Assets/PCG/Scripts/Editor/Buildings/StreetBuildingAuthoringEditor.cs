#if UNITY_EDITOR
using System;
using HoudiniEngineUnity;
using PCGBike.Buildings;
using UnityEditor;
using UnityEngine;

namespace PCGBike.Editor.Buildings
{
    [CustomEditor(typeof(StreetBuildingAuthoring))]
    public sealed class StreetBuildingAuthoringEditor : UnityEditor.Editor
    {
        public override void OnInspectorGUI()
        {
            serializedObject.Update();
            EditorGUILayout.LabelField("风格 / Style", EditorStyles.boldLabel);
            EditorGUILayout.PropertyField(serializedObject.FindProperty("_fixedStyleConfig"),
                new GUIContent("固定风格配置 / Fixed StyleConfig"));
            serializedObject.ApplyModifiedProperties();

            StreetBuildingAuthoring authoring = (StreetBuildingAuthoring)target;
            StreetBuildingStyleConfig style = authoring.ResolveStyle();
            EditorGUILayout.HelpBox(style == null
                    ? "必须为当前 HDA 显式指定 StyleConfig。"
                    : $"当前风格：{style.name}\n体块、立面、附件与 Variation Seed 请直接在 HDA 参数面板调整。",
                style == null ? MessageType.Error : MessageType.Info);

            using (new EditorGUI.DisabledScope(style == null))
            using (new EditorGUILayout.HorizontalScope())
            {
                if (GUILayout.Button("验证 / Validate")) Validate(authoring, style);
                if (GUILayout.Button("编译预览 / Compile Preview")) CompilePreview(authoring, style);
                if (GUILayout.Button("定位 StyleConfig")) EditorGUIUtility.PingObject(style);
            }
            using (new EditorGUI.DisabledScope(style == null))
                if (GUILayout.Button("应用风格、Cook 并保存场景 / Apply Style, Cook & Save")) Apply(authoring);

            if (!string.IsNullOrEmpty(authoring.LastAppliedPayloadSha256))
                EditorGUILayout.HelpBox("最后 Style Payload SHA-256:\n" + authoring.LastAppliedPayloadSha256,
                    MessageType.None);
            if (!string.IsNullOrEmpty(authoring.LastCookDiagnostic))
                EditorGUILayout.HelpBox("Cook 诊断：\n" + authoring.LastCookDiagnostic,
                    authoring.LastCookDiagnostic.Contains("PASS") ? MessageType.Info : MessageType.Warning);
        }

        private static void Validate(StreetBuildingAuthoring authoring, StreetBuildingStyleConfig style)
        {
            string result = StreetBuildingStyleApplier.Validate(style);
            if (string.IsNullOrEmpty(result)) Debug.Log("StreetBuilding StyleConfig validation PASS.", authoring);
            else Debug.LogError(result, authoring);
        }

        private static void CompilePreview(StreetBuildingAuthoring authoring, StreetBuildingStyleConfig style)
        {
            try
            {
                StreetBuildingCompiledStyle compiled = StreetBuildingStyleCompiler.Compile(style);
                Debug.Log($"StreetBuilding style compile PASS\n{compiled.ModuleCount} modules / {compiled.Sha256}\n"
                          + compiled.Payload, authoring);
            }
            catch (Exception exception) { Debug.LogError("StreetBuilding style compile failed.\n" + exception, authoring); }
        }

        private static void Apply(StreetBuildingAuthoring authoring)
        {
            try
            {
                HEU_HoudiniAssetRoot root = authoring.GetComponent<HEU_HoudiniAssetRoot>();
                StreetBuildingCompiledStyle compiled = StreetBuildingStyleApplier.ApplyAndSave(root, authoring);
                Debug.Log("StreetBuilding style applied, cooked and saved. SHA-256 " + compiled.Sha256, authoring);
            }
            catch (Exception exception) { Debug.LogError("StreetBuilding style apply failed.\n" + exception, authoring); }
        }
    }
}
#endif
