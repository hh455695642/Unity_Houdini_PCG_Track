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
            EditorGUILayout.LabelField("风格配置", EditorStyles.boldLabel);
            EditorGUILayout.PropertyField(serializedObject.FindProperty("_fixedStyleConfig"), new GUIContent("固定 StyleConfig"));
            EditorGUILayout.PropertyField(serializedObject.FindProperty("_variationSeed"), new GUIContent("Variation Seed"));
            EditorGUILayout.Space(4);
            EditorGUILayout.LabelField("生成规则", EditorStyles.boldLabel);
            EditorGUILayout.PropertyField(serializedObject.FindProperty("_generationPreset"), new GUIContent("可选 GenerationPreset"));
            serializedObject.ApplyModifiedProperties();

            StreetBuildingAuthoring authoring = (StreetBuildingAuthoring)target;
            StreetBuildingStyleConfig style = authoring.ResolveStyle();
            EditorGUILayout.HelpBox(style == null
                    ? "必须为当前 HDA 显式指定 StyleConfig。"
                    : $"最终风格：{style.name}\n来源：当前 HDA 显式 StyleConfig\n规则："
                      + (authoring.GenerationPreset == null ? "HDA 可见参数" : "GenerationPreset > HDA 参数"),
                style == null ? MessageType.Error : MessageType.Info);

            using (new EditorGUI.DisabledScope(style == null))
            using (new EditorGUILayout.HorizontalScope())
            {
                if (GUILayout.Button("Validate")) Validate(authoring, style);
                if (GUILayout.Button("Compile Preview")) CompilePreview(authoring, style);
                if (GUILayout.Button("定位 StyleConfig")) EditorGUIUtility.PingObject(style);
            }
            using (new EditorGUI.DisabledScope(style == null))
                if (GUILayout.Button("Apply Style + Rules, Cook & Save Scene")) Apply(authoring);

            if (!string.IsNullOrEmpty(authoring.LastAppliedPayloadSha256))
                EditorGUILayout.HelpBox("最后 Style Payload SHA-256:\n" + authoring.LastAppliedPayloadSha256, MessageType.None);
            if (!string.IsNullOrEmpty(authoring.LastAppliedDesignSha256))
                EditorGUILayout.HelpBox("最后完整规则 SHA-256:\n" + authoring.LastAppliedDesignSha256, MessageType.None);
            if (!string.IsNullOrEmpty(authoring.LastCookDiagnostic))
                EditorGUILayout.HelpBox("Cook 诊断：\n" + authoring.LastCookDiagnostic,
                    authoring.LastCookDiagnostic.Contains("PASS") ? MessageType.Info : MessageType.Warning);
        }

        private static void Validate(StreetBuildingAuthoring authoring, StreetBuildingStyleConfig style)
        {
            string result = StreetBuildingDesignPresetApplier.Validate(authoring.GenerationPreset, style);
            if (string.IsNullOrEmpty(result)) Debug.Log("StreetBuilding Style + Generation validation PASS.", authoring);
            else Debug.LogError(result, authoring);
        }

        private static void CompilePreview(StreetBuildingAuthoring authoring, StreetBuildingStyleConfig style)
        {
            try
            {
                StreetBuildingCompiledStyle compiledStyle = StreetBuildingStyleCompiler.Compile(style);
                StreetBuildingCompiledGeneration compiledRules = StreetBuildingGenerationCompiler.Compile(
                    authoring.GenerationPreset, style, authoring.VariationSeed);
                Debug.Log($"StreetBuilding compile PASS\nStyle payload {compiledStyle.ModuleCount} modules / {compiledStyle.Sha256}"
                          + $"\nSBR1 {compiledRules.Sha256}\n{compiledStyle.Payload}\n{compiledRules.Payload}", authoring);
            }
            catch (Exception exception) { Debug.LogError("StreetBuilding compile failed.\n" + exception, authoring); }
        }

        private static void Apply(StreetBuildingAuthoring authoring)
        {
            try
            {
                HEU_HoudiniAssetRoot root = authoring.GetComponent<HEU_HoudiniAssetRoot>();
                StreetBuildingCompiledStyle compiled = StreetBuildingDesignPresetApplier.ApplyAndSave(root, authoring);
                Debug.Log("StreetBuilding applied, cooked and saved. Style payload SHA-256 " + compiled.Sha256, authoring);
            }
            catch (Exception exception) { Debug.LogError("StreetBuilding apply failed.\n" + exception, authoring); }
        }
    }
}
#endif
