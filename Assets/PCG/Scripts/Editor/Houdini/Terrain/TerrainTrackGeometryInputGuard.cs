using System;
using System.Collections.Generic;
using HoudiniEngineUnity;
using PCGBike.Terrain.Authoring;
using UnityEditor;
using UnityEditor.SceneManagement;
using UnityEngine;

namespace PCGBike.Terrain.Editor
{
    /// <summary>
    /// Project-only safety boundary for Terrain.track_geometry.
    /// The official Houdini Engine inspector remains untouched: this guard reacts
    /// after a user selects an unsupported generic input type.
    /// </summary>
    [InitializeOnLoad]
    public static class TerrainTrackGeometryInputGuard
    {
        private const string TerrainOperatorName = "pcgbike::Object/Terrain::1.0";
        private const string TerrainAssetSuffix = "Assets/PCG/HDA/Terrain.hda";
        private const string TrackGeometryParameter = "track_geometry";
        private const string TrackBindingEnabledParameter = "track_binding_enabled";
        private const string TrackDisplayPathParameter = "track_display_sop_path";
        private const double ScanIntervalSeconds = 0.25;

        private static readonly Dictionary<int, string> LastRejectedTypeByInput =
            new Dictionary<int, string>();

        private static double _nextScanTime;
        private static bool _scanRequested = true;
        private static bool _isScanning;

        static TerrainTrackGeometryInputGuard()
        {
            EditorApplication.update -= OnEditorUpdate;
            EditorApplication.update += OnEditorUpdate;
            EditorApplication.hierarchyChanged -= RequestScan;
            EditorApplication.hierarchyChanged += RequestScan;
            Undo.undoRedoPerformed -= RequestScan;
            Undo.undoRedoPerformed += RequestScan;
        }

        private static void RequestScan()
        {
            _scanRequested = true;
            _nextScanTime = 0.0;
        }

        private static void OnEditorUpdate()
        {
            if (_isScanning ||
                EditorApplication.isCompiling ||
                EditorApplication.isUpdating ||
                EditorApplication.isPlayingOrWillChangePlaymode)
            {
                return;
            }

            double now = EditorApplication.timeSinceStartup;
            if (!_scanRequested && now < _nextScanTime)
                return;

            _scanRequested = false;
            _nextScanTime = now + ScanIntervalSeconds;
            EnforceAllLoadedTerrainAssets();
        }

        /// <summary>Runs the same guard used by the editor update loop.</summary>
        public static int EnforceAllLoadedTerrainAssets()
        {
            if (_isScanning)
                return 0;

            _isScanning = true;
            int rejectedCount = 0;
            try
            {
                HEU_HoudiniAssetRoot[] roots = Resources.FindObjectsOfTypeAll<HEU_HoudiniAssetRoot>();
                foreach (HEU_HoudiniAssetRoot root in roots)
                {
                    if (!IsTargetTerrain(root))
                        continue;

                    HEU_HoudiniAsset asset = root.HoudiniAsset;
                    List<HEU_InputNode> inputs = asset.InputNodes;
                    if (inputs == null)
                        continue;

                    foreach (HEU_InputNode input in inputs)
                    {
                        if (input == null ||
                            !string.Equals(input.ParamName, TrackGeometryParameter, StringComparison.Ordinal))
                        {
                            continue;
                        }

                        if (EnforceInput(root, asset, input))
                            ++rejectedCount;
                    }
                }
            }
            finally
            {
                _isScanning = false;
            }

            return rejectedCount;
        }

        private static bool EnforceInput(
            HEU_HoudiniAssetRoot root,
            HEU_HoudiniAsset asset,
            HEU_InputNode input)
        {
            string currentType = GetSerializedInputType(input, "_inputObjectType");
            string pendingType = GetSerializedInputType(input, "_pendingInputObjectType");
            string rejectedType = !IsAllowedType(pendingType)
                ? pendingType
                : (!IsAllowedType(currentType) ? currentType : string.Empty);

            int inputId = input.GetInstanceID();
            if (string.IsNullOrEmpty(rejectedType))
            {
                LastRejectedTypeByInput.Remove(inputId);
                return false;
            }

            bool shouldWarn = !LastRejectedTypeByInput.TryGetValue(inputId, out string previousType) ||
                !string.Equals(previousType, rejectedType, StringComparison.Ordinal);
            LastRejectedTypeByInput[inputId] = rejectedType;

            Undo.RecordObject(input, "Reject Unsupported Terrain Track Input");
            input.RemoveAllInputEntries(false);
            input.PendingObjectType = HEU_InputObjectTypeWrapper.HDA;
            if (input.ObjectType != HEU_InputObjectTypeWrapper.HDA)
                input.ChangeInputType(HEU_InputObjectTypeWrapper.HDA, false);

            // The project binding can feed the Track Display SOP independently of
            // the generic input. Disable both paths so rejection is fail-closed.
            DisableTrackDisplayBinding(asset);
            TerrainTrackDisplaySopBinding binding =
                root.GetComponent<TerrainTrackDisplaySopBinding>();
            if (binding != null)
                binding.DetachAndRestoreBaseNow();

            EditorUtility.SetDirty(input);
            EditorUtility.SetDirty(asset);
            EditorUtility.SetDirty(root);
            if (root.gameObject.scene.IsValid())
                EditorSceneManager.MarkSceneDirty(root.gameObject.scene);

            // Parameter values above were written directly through HAPI; do not
            // upload the stale serialized parameter cache during the base cook.
            asset.RequestCook(
                bCheckParametersChanged: false,
                bAsync: true,
                bSkipCookCheck: false,
                bUploadParameters: false);

            if (shouldWarn)
            {
                Debug.LogWarning(
                    $"[PCG Terrain] track_geometry rejected input type '{rejectedType}'. " +
                    "Only HDA and UNITY_MESH are supported. The old connection was cleared, " +
                    "the input was reset to an empty HDA, and a base-terrain cook was requested.",
                    root);
            }

            return true;
        }

        private static void DisableTrackDisplayBinding(HEU_HoudiniAsset asset)
        {
            if (asset == null || asset.AssetID == HEU_Defines.HEU_INVALID_NODE_ID)
                return;

            HEU_SessionBase session = asset.GetAssetSession(false);
            if (session == null || !session.IsSessionValid())
                return;

            if (session.GetParmIDFromName(
                    asset.AssetID,
                    TrackBindingEnabledParameter,
                    out int enabledParmId) &&
                enabledParmId != HEU_HAPIConstants.HAPI_INVALID_PARM_ID)
            {
                session.SetParamIntValue(asset.AssetID, TrackBindingEnabledParameter, 0, 0);
            }

            if (session.GetParmIDFromName(
                    asset.AssetID,
                    TrackDisplayPathParameter,
                    out int pathParmId) &&
                pathParmId != HEU_HAPIConstants.HAPI_INVALID_PARM_ID)
            {
                session.SetParamStringValue(asset.AssetID, TrackDisplayPathParameter, string.Empty, 0);
            }
        }

        private static bool IsTargetTerrain(HEU_HoudiniAssetRoot root)
        {
            if (root == null ||
                EditorUtility.IsPersistent(root) ||
                !root.gameObject.scene.IsValid())
            {
                return false;
            }

            HEU_HoudiniAsset asset = root.HoudiniAsset;
            if (asset == null ||
                !string.Equals(asset.AssetOpName, TerrainOperatorName, StringComparison.Ordinal))
            {
                return false;
            }

            string normalizedPath = (asset.AssetPath ?? string.Empty).Replace('\\', '/');
            return normalizedPath.EndsWith(TerrainAssetSuffix, StringComparison.OrdinalIgnoreCase);
        }

        private static bool IsAllowedType(string typeName)
        {
            return string.Equals(typeName, "HDA", StringComparison.Ordinal) ||
                string.Equals(typeName, "UNITY_MESH", StringComparison.Ordinal);
        }

        private static string GetSerializedInputType(HEU_InputNode input, string propertyName)
        {
            SerializedObject serializedInput = new SerializedObject(input);
            SerializedProperty property = serializedInput.FindProperty(propertyName);
            if (property == null || property.propertyType != SerializedPropertyType.Enum || property.enumValueIndex < 0)
                return string.Empty;

            string[] enumNames = property.enumNames;
            return property.enumValueIndex < enumNames.Length
                ? enumNames[property.enumValueIndex]
                : string.Empty;
        }
    }
}