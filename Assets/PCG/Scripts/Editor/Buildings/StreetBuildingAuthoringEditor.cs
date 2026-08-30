#if UNITY_EDITOR
using System;
using HoudiniEngineUnity;
using PCGBike.Buildings;
using UnityEditor;
using UnityEditor.SceneManagement;
using UnityEngine;

namespace PCGBike.Editor.Buildings
{
    [CustomEditor(typeof(StreetBuildingAuthoring))]
    public sealed class StreetBuildingAuthoringEditor : UnityEditor.Editor
    {
        public override void OnInspectorGUI()
        {
            serializedObject.Update();
            EditorGUILayout.PropertyField(serializedObject.FindProperty("_catalog"));
            EditorGUILayout.PropertyField(serializedObject.FindProperty("_designPreset"));
            EditorGUILayout.PropertyField(serializedObject.FindProperty("_variationSeed"));
            serializedObject.ApplyModifiedProperties();

            StreetBuildingAuthoring authoring = (StreetBuildingAuthoring)target;
            using (new EditorGUI.DisabledScope(authoring.Catalog == null))
            {
                if (GUILayout.Button("Validate Catalog"))
                    LogValidation(authoring);
                if (GUILayout.Button("Compile Preview"))
                    CompilePreview(authoring);
                if (GUILayout.Button("Apply, Cook & Save Scene"))
                    ApplyAndCook(authoring);
            }
            using (new EditorGUI.DisabledScope(authoring.DesignPreset == null))
            {
                if (GUILayout.Button("Apply Design Preset, Cook & Save Scene"))
                    ApplyDesign(authoring);
            }

            if (!string.IsNullOrEmpty(authoring.LastAppliedPayloadSha256))
                EditorGUILayout.HelpBox(
                    "Last applied payload SHA-256:\n" + authoring.LastAppliedPayloadSha256,
                    MessageType.Info);
            if (!string.IsNullOrEmpty(authoring.LastAppliedDesignSha256))
                EditorGUILayout.HelpBox(
                    "Last applied design SHA-256:\n" + authoring.LastAppliedDesignSha256,
                    MessageType.Info);
        }

        private static void LogValidation(StreetBuildingAuthoring authoring)
        {
            StreetBuildingCatalogValidationReport report =
                StreetBuildingModuleCatalogValidator.Validate(authoring.Catalog);
            if (report.IsValid)
                Debug.Log(report, authoring);
            else
                Debug.LogError(report, authoring);
        }

        private static void CompilePreview(StreetBuildingAuthoring authoring)
        {
            try
            {
                StreetBuildingCompiledCatalog compiled =
                    StreetBuildingModuleCatalogCompiler.Compile(authoring.Catalog);
                Debug.Log(
                    $"StreetBuilding Catalog compile PASS: {compiled.ModuleCount} modules / "
                    + $"{compiled.PartCount} parts / SHA-256 {compiled.Sha256}\n{compiled.Payload}",
                    authoring);
            }
            catch (Exception exception)
            {
                Debug.LogError("StreetBuilding Catalog compile failed.\n" + exception, authoring);
            }
        }

        private static void ApplyAndCook(StreetBuildingAuthoring authoring)
        {
            try
            {
                HEU_HoudiniAssetRoot root = authoring.GetComponent<HEU_HoudiniAssetRoot>();
                StreetBuildingCompiledCatalog compiled =
                    StreetBuildingModuleCatalogApplier.Apply(root, authoring);
                if (!EditorSceneManager.SaveScene(authoring.gameObject.scene))
                    throw new InvalidOperationException("StreetBuilding Scene save failed.");
                Debug.Log(
                    "StreetBuilding Catalog applied, cooked and saved. Payload SHA-256 "
                    + compiled.Sha256,
                    authoring);
            }
            catch (Exception exception)
            {
                Debug.LogError("StreetBuilding Catalog apply failed.\n" + exception, authoring);
            }
        }

        private static void ApplyDesign(StreetBuildingAuthoring authoring)
        {
            try
            {
                HEU_HoudiniAssetRoot root = authoring.GetComponent<HEU_HoudiniAssetRoot>();
                StreetBuildingCompiledCatalog compiled =
                    StreetBuildingDesignPresetApplier.ApplyAndSave(root, authoring);
                Debug.Log("StreetBuilding DesignPreset applied, cooked and saved. Payload SHA-256 "
                          + compiled.Sha256 + " / Design SHA-256 "
                          + authoring.LastAppliedDesignSha256, authoring);
            }
            catch (Exception exception)
            {
                Debug.LogError("StreetBuilding DesignPreset apply failed.\n" + exception, authoring);
            }
        }
    }
}
#endif
