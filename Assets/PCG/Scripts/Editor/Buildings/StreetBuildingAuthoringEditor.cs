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
            EditorGUILayout.PropertyField(serializedObject.FindProperty("_catalog"));
            serializedObject.ApplyModifiedProperties();

            StreetBuildingAuthoring authoring = (StreetBuildingAuthoring)target;
            using (new EditorGUI.DisabledScope(authoring.Catalog == null))
            {
                if (GUILayout.Button("Validate Catalog"))
                    LogValidation(authoring);
                if (GUILayout.Button("Compile Preview"))
                    CompilePreview(authoring);
                if (GUILayout.Button("Apply & Cook (No Auto Save)"))
                    ApplyAndCook(authoring);
            }

            if (!string.IsNullOrEmpty(authoring.LastAppliedPayloadSha256))
                EditorGUILayout.HelpBox(
                    "Last applied payload SHA-256:\n" + authoring.LastAppliedPayloadSha256,
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
                Debug.Log(
                    "StreetBuilding Catalog applied and cooked without saving the Scene. Payload SHA-256 "
                    + compiled.Sha256,
                    authoring);
            }
            catch (Exception exception)
            {
                Debug.LogError("StreetBuilding Catalog apply failed.\n" + exception, authoring);
            }
        }
    }
}
#endif
