#if UNITY_EDITOR
using System;
using System.Collections.Generic;
using System.Reflection;
using HoudiniEngineUnity;
using UnityEditor;
using UnityEditor.SceneManagement;
using UnityEngine;
using UnityEngine.Splines;

namespace PCG.CityRoad.Editor
{
    /// <summary>
    /// Project-side rebuild flow for CityRoad. The installed Houdini Engine
    /// version does not expose bForceUploadInputs on RequestCook, so this file
    /// contains a narrowly-scoped, version-checked compatibility bridge.
    /// The official plugin and inspector remain untouched.
    /// </summary>
    internal static class CityRoadSafeRebuild
    {
        private const string CityRoadAssetPath =
            "Assets/PCG/HDA/City/CityRoad.hda";
        private const int ExpectedAssetConnectorCount = 0;
        private const int ExpectedParameterInputCount = 1;
        internal const string RoadNetworkParameterName = "unity_road_network";
        private const string RoadNetworkSourceParameterName =
            "road_network_source";
        private const int ExternalRoadNetworkSource = 0;
        private static readonly KeyValuePair<string, string>[] s_MaterialParameters =
        {
            new KeyValuePair<string, string>(
                "road_unity_material",
                "Assets/PCG/Materials/M_PCG_CityRoad_Asphalt.mat"),
            new KeyValuePair<string, string>(
                "sidewalk_unity_material",
                "Assets/PCG/Materials/M_PCG_CityRoad_Sidewalk.mat"),
            new KeyValuePair<string, string>(
                "curb_unity_material",
                "Assets/PCG/Materials/M_PCG_CityRoad_Curb.mat"),
            new KeyValuePair<string, string>(
                "marking_unity_material",
                "Assets/PCG/Materials/M_PCG_CityRoad_Marking.mat")
        };
        private static readonly string[] s_InputReaderNodeNames =
        {
            "IN_ROAD_NETWORK"
        };

        private static bool s_RebuildQueued;
        private static readonly Type[] s_UploadInputNodesParameterTypes =
        {
            typeof(HEU_SessionBase),
            typeof(bool),
            typeof(bool)
        };

        [MenuItem("PCG/CityRoad/Safe Rebuild Selected", priority = 2100)]
        private static void RebuildSelected()
        {
            var roots = new HashSet<HEU_HoudiniAssetRoot>();
            foreach (GameObject selected in Selection.gameObjects)
            {
                if (selected == null)
                    continue;

                HEU_HoudiniAssetRoot root =
                    selected.GetComponentInParent<HEU_HoudiniAssetRoot>();
                if (root == null)
                    root = selected.GetComponentInChildren<HEU_HoudiniAssetRoot>(true);

                if (IsCityRoad(root))
                    roots.Add(root);
            }

            if (roots.Count == 0)
            {
                Debug.LogWarning(
                    "CityRoad Safe Rebuild: select a CityRoad HDA instance first.");
                return;
            }

            int rebuilt = 0;
            foreach (HEU_HoudiniAssetRoot root in roots)
            {
                if (Rebuild(root))
                    rebuilt++;
            }

            Debug.LogFormat(
                "CityRoad Safe Rebuild: rebuilt {0}/{1} selected instance(s).",
                rebuilt,
                roots.Count);
        }

        [MenuItem("PCG/CityRoad/Safe Rebuild Selected", true)]
        private static bool ValidateRebuildSelected()
        {
            foreach (GameObject selected in Selection.gameObjects)
            {
                if (selected == null)
                    continue;

                HEU_HoudiniAssetRoot root =
                    selected.GetComponentInParent<HEU_HoudiniAssetRoot>();
                if (root == null)
                    root = selected.GetComponentInChildren<HEU_HoudiniAssetRoot>(true);

                if (IsCityRoad(root))
                    return true;
            }

            return false;
        }

        internal static void QueueImportedAssetReload()
        {
            if (s_RebuildQueued)
                return;

            s_RebuildQueued = true;
            EditorApplication.delayCall += RebuildLoadedInstancesAfterImport;
        }

        private static void RebuildLoadedInstancesAfterImport()
        {
            s_RebuildQueued = false;

            int rebuilt = 0;
            HEU_HoudiniAssetRoot[] roots =
                Resources.FindObjectsOfTypeAll<HEU_HoudiniAssetRoot>();
            foreach (HEU_HoudiniAssetRoot root in roots)
            {
                if (!IsLoadedSceneObject(root) || !IsCityRoad(root))
                    continue;

                if (Rebuild(root))
                    rebuilt++;
            }

            if (rebuilt > 0)
            {
                Debug.LogFormat(
                    "CityRoad Safe Rebuild: HDA import reloaded {0} loaded instance(s).",
                    rebuilt);
            }
        }

        internal static bool Rebuild(HEU_HoudiniAssetRoot root)
        {
            if (!IsCityRoad(root))
                return false;

            HEU_HoudiniAsset asset = root.HoudiniAsset;
            List<GameObject[]> inputBindings = CaptureInputBindings(asset);
            if (!ValidateInputContract(root, asset, inputBindings))
                return false;

            bool roadMarkingsEnabled;
            bool crosswalksEnabled;
            if (!CaptureGenerationToggles(
                    root,
                    asset,
                    out roadMarkingsEnabled,
                    out crosswalksEnabled))
                return false;

            if (!asset.RequestReload(bAsync: false))
            {
                Debug.LogErrorFormat(
                    root,
                    "CityRoad Safe Rebuild: RequestReload failed for {0}.",
                    root.name);
                return false;
            }

            // RequestReload can refresh the component reference, so fetch it
            // again before forcing a cook/input upload.
            asset = root.HoudiniAsset;
            if (asset == null || !RestoreInputBindings(root, asset, inputBindings))
                return false;

            if (!RestoreGenerationToggles(
                    root,
                    asset,
                    roadMarkingsEnabled,
                    crosswalksEnabled))
                return false;

            if (!ApplyRoadNetworkSourceContract(root, asset))
                return false;

            if (!ApplyMaterialParameterContract(root, asset))
                return false;

            if (!UploadAndCookInputNetworks(root, asset))
                return false;

            // Input upload creates two cached merge levels in this Houdini
            // Engine version. They have been cooked above, so use the public
            // cook path without forcing another upload/recreation.
            bool cookRequested = asset.RequestCook(
                bCheckParametersChanged: true,
                bAsync: false,
                bSkipCookCheck: false,
                bUploadParameters: true);
            bool cookSucceeded = cookRequested
                && asset.LastCookResult == HEU_AssetCookResultWrapper.SUCCESS;
            if (!cookSucceeded)
            {
                Debug.LogErrorFormat(
                    root,
                    "CityRoad Safe Rebuild: forced input cook failed for {0}. "
                    + "CookStatus={1}, LastCookResult={2}.",
                    root.name,
                    asset.CookStatus,
                    asset.LastCookResult);
                return false;
            }

            EditorUtility.SetDirty(root);
            EditorUtility.SetDirty(asset);
            if (root.gameObject.scene.IsValid())
                EditorSceneManager.MarkSceneDirty(root.gameObject.scene);

            string inputZeroName = inputBindings[0][0] != null
                ? inputBindings[0][0].name
                : "<missing>";
            Debug.LogFormat(
                root,
                "CityRoad Safe Rebuild: {0} reloaded and cooked successfully; "
                + "the {1} Spline parameter was force-uploaded ({2}).",
                root.name,
                RoadNetworkParameterName,
                inputZeroName);
            return true;
        }

        private static bool ApplyRoadNetworkSourceContract(
            HEU_HoudiniAssetRoot root,
            HEU_HoudiniAsset asset)
        {
            if (asset == null || asset.Parameters == null
                || !asset.Parameters.SetIntParameterValue(
                    RoadNetworkSourceParameterName,
                    ExternalRoadNetworkSource,
                    bRecookAsset: false))
            {
                Debug.LogErrorFormat(
                    root,
                    "CityRoad Safe Rebuild: required source selector {0} is missing.",
                    RoadNetworkSourceParameterName);
                return false;
            }

            EditorUtility.SetDirty(asset.Parameters);
            return true;
        }

        private static bool ApplyMaterialParameterContract(
            HEU_HoudiniAssetRoot root,
            HEU_HoudiniAsset asset)
        {
            if (asset == null || asset.Parameters == null)
            {
                Debug.LogError(
                    "CityRoad Safe Rebuild: HDA parameters are unavailable after reload.",
                    root);
                return false;
            }

            foreach (KeyValuePair<string, string> binding in s_MaterialParameters)
            {
                string currentValue;
                if (!asset.Parameters.GetStringParameterValue(
                        binding.Key,
                        out currentValue))
                {
                    Debug.LogErrorFormat(
                        root,
                        "CityRoad Safe Rebuild: required material parameter {0} is missing.",
                        binding.Key);
                    return false;
                }

                if (!string.Equals(
                        currentValue,
                        binding.Value,
                        StringComparison.Ordinal))
                {
                    // The CityRoad material fields are HAPI path-file parms.
                    // HEU's single-value setter only accepts plain strings,
                    // while the tuple setter supports both string and path
                    // parameter types.
                    if (!asset.Parameters.SetStringParameterValues(
                            binding.Key,
                            new[] { binding.Value },
                            bRecookAsset: false))
                    {
                        Debug.LogErrorFormat(
                            root,
                            "CityRoad Safe Rebuild: failed to assign {0} to {1}.",
                            binding.Value,
                            binding.Key);
                        return false;
                    }
                }
            }

            // HEU_Parameters is its own ScriptableObject. Mark it dirty as
            // well as the parent asset so the material contract survives a
            // Unity domain reload instead of reverting to the old empty
            // serialized strings.
            EditorUtility.SetDirty(asset.Parameters);
            EditorUtility.SetDirty(asset);
            return true;
        }

        private static bool CaptureGenerationToggles(
            HEU_HoudiniAssetRoot root,
            HEU_HoudiniAsset asset,
            out bool roadMarkingsEnabled,
            out bool crosswalksEnabled)
        {
            roadMarkingsEnabled = false;
            crosswalksEnabled = false;
            if (asset == null || asset.Parameters == null
                || !asset.Parameters.GetBoolParameterValue(
                    "enable_road_markings", out roadMarkingsEnabled)
                || !asset.Parameters.GetBoolParameterValue(
                    "enable_crosswalks", out crosswalksEnabled))
            {
                Debug.LogError(
                    "CityRoad Safe Rebuild: marking feature toggles are unavailable.",
                    root);
                return false;
            }

            return true;
        }

        private static bool RestoreGenerationToggles(
            HEU_HoudiniAssetRoot root,
            HEU_HoudiniAsset asset,
            bool roadMarkingsEnabled,
            bool crosswalksEnabled)
        {
            if (asset == null || asset.Parameters == null
                || !asset.Parameters.SetBoolParameterValue(
                    "enable_road_markings",
                    roadMarkingsEnabled,
                    bRecookAsset: false)
                || !asset.Parameters.SetBoolParameterValue(
                    "enable_crosswalks",
                    crosswalksEnabled,
                    bRecookAsset: false))
            {
                Debug.LogError(
                    "CityRoad Safe Rebuild: failed to restore marking feature toggles.",
                    root);
                return false;
            }

            EditorUtility.SetDirty(asset.Parameters);
            return true;
        }

        private static List<GameObject[]> CaptureInputBindings(HEU_HoudiniAsset asset)
        {
            var result = new List<GameObject[]>();
            if (asset == null || asset.InputNodes == null)
                return result;

            foreach (HEU_InputNode inputNode in asset.InputNodes)
            {
                result.Add(
                    inputNode != null
                        ? inputNode.GetInputEntryGameObjects()
                        : Array.Empty<GameObject>());
            }

            return result;
        }

        private static bool ValidateInputContract(
            HEU_HoudiniAssetRoot root,
            HEU_HoudiniAsset asset,
            List<GameObject[]> inputBindings)
        {
            int assetConnectorCount = asset != null
                ? asset.NodeInfo.inputCount
                : -1;
            if (assetConnectorCount != ExpectedAssetConnectorCount)
            {
                Debug.LogErrorFormat(
                    root,
                    "CityRoad Safe Rebuild: {0} must expose {1} HDA object "
                    + "connector(s); found {2}. The Road Network must be a "
                    + "parameter input, not an HDA connector.",
                    root.name,
                    ExpectedAssetConnectorCount,
                    assetConnectorCount);
                return false;
            }

            if (asset == null
                || asset.InputNodes == null
                || asset.InputNodes.Count != ExpectedParameterInputCount
                || inputBindings.Count != ExpectedParameterInputCount)
            {
                Debug.LogErrorFormat(
                    root,
                    "CityRoad Safe Rebuild: {0} must expose exactly {1} "
                    + "parameter input(s); found {2}. Rebuild was cancelled "
                    + "without changing bindings.",
                    root.name,
                    ExpectedParameterInputCount,
                    asset != null && asset.InputNodes != null
                        ? asset.InputNodes.Count
                        : 0);
                return false;
            }

            HEU_InputNode roadNetworkInput = asset.InputNodes[0];
            if (roadNetworkInput == null
                || roadNetworkInput.NodeType
                    != HEU_InputNodeTypeWrapper.PARAMETER
                || roadNetworkInput.ObjectType
                    != HEU_InputObjectTypeWrapper.SPLINE
                || !string.Equals(
                    roadNetworkInput.ParamName,
                    RoadNetworkParameterName,
                    StringComparison.Ordinal))
            {
                Debug.LogErrorFormat(
                    root,
                    "CityRoad Safe Rebuild: input 0 must be the PARAMETER/SPLINE "
                    + "input {0}; found NodeType={1}, ObjectType={2}, ParamName={3}.",
                    RoadNetworkParameterName,
                    roadNetworkInput != null
                        ? roadNetworkInput.NodeType.ToString()
                        : "<null>",
                    roadNetworkInput != null
                        ? roadNetworkInput.ObjectType.ToString()
                        : "<null>",
                    roadNetworkInput != null
                        ? roadNetworkInput.ParamName
                        : "<null>");
                return false;
            }

            if (inputBindings[0] == null
                || inputBindings[0].Length == 0
                || inputBindings[0][0] == null)
            {
                Debug.LogErrorFormat(
                    root,
                    "CityRoad Safe Rebuild: required Spline parameter {0} on "
                    + "{1} is empty.",
                    RoadNetworkParameterName,
                    root.name);
                return false;
            }

            return true;
        }

        private static bool RestoreInputBindings(
            HEU_HoudiniAssetRoot root,
            HEU_HoudiniAsset asset,
            List<GameObject[]> bindings)
        {
            if (asset.InputNodes == null
                || asset.InputNodes.Count != ExpectedParameterInputCount
                || bindings.Count != ExpectedParameterInputCount)
            {
                Debug.LogErrorFormat(
                    root,
                    "CityRoad Safe Rebuild: input contract changed after reload on {0}; "
                    + "expected {1}, found {2}.",
                    root.name,
                    ExpectedParameterInputCount,
                    asset.InputNodes != null ? asset.InputNodes.Count : 0);
                return false;
            }

            HEU_InputNode roadNetworkInput = asset.InputNodes[0];
            if (roadNetworkInput == null
                || roadNetworkInput.NodeType
                    != HEU_InputNodeTypeWrapper.PARAMETER
                || roadNetworkInput.ObjectType
                    != HEU_InputObjectTypeWrapper.SPLINE
                || !string.Equals(
                    roadNetworkInput.ParamName,
                    RoadNetworkParameterName,
                    StringComparison.Ordinal))
            {
                Debug.LogErrorFormat(
                    root,
                    "CityRoad Safe Rebuild: {0} parameter input contract "
                    + "changed after reload.",
                    RoadNetworkParameterName);
                return false;
            }

            for (int inputIndex = 0; inputIndex < bindings.Count; inputIndex++)
            {
                HEU_InputNode inputNode = asset.InputNodes[inputIndex];
                if (inputNode == null)
                {
                    Debug.LogErrorFormat(
                        root,
                        "CityRoad Safe Rebuild: input {0} is null after reload on {1}.",
                        inputIndex,
                        root.name);
                    return false;
                }

                GameObject[] expectedEntries =
                    bindings[inputIndex] ?? Array.Empty<GameObject>();
                for (int entryIndex = 0;
                    entryIndex < expectedEntries.Length;
                    entryIndex++)
                {
                    GameObject expected = expectedEntries[entryIndex];
                    if (entryIndex < inputNode.NumInputEntries())
                    {
                        if (inputNode.GetInputEntryGameObject(entryIndex) != expected)
                        {
                            inputNode.SetInputEntry(
                                entryIndex,
                                expected,
                                bRecookAsset: false);
                        }
                    }
                    else
                    {
                        inputNode.AddInputEntryAtEnd(
                            expected,
                            bRecookAsset: false);
                    }
                }
            }

            GameObject restoredRoadInput =
                asset.InputNodes[0].GetInputEntryGameObject(0);
            if (restoredRoadInput == null
                || restoredRoadInput != bindings[0][0])
            {
                Debug.LogErrorFormat(
                    root,
                    "CityRoad Safe Rebuild: failed to restore input 0 on {0}.",
                    root.name);
                return false;
            }

            return true;
        }

        private static bool UploadAndCookInputNetworks(
            HEU_HoudiniAssetRoot root,
            HEU_HoudiniAsset asset)
        {
            HEU_SessionBase session = asset.GetAssetSession(true);
            if (session == null)
            {
                Debug.LogError(
                    "CityRoad Safe Rebuild: no valid Houdini session.",
                    root);
                return false;
            }

            MethodInfo uploadInputNodes = typeof(HEU_HoudiniAsset).GetMethod(
                "UploadInputNodes",
                BindingFlags.Instance | BindingFlags.NonPublic,
                binder: null,
                types: s_UploadInputNodesParameterTypes,
                modifiers: null);
            if (uploadInputNodes == null
                || uploadInputNodes.ReturnType != typeof(void))
            {
                Debug.LogError(
                    "CityRoad Safe Rebuild: the installed Houdini Engine "
                    + "UploadInputNodes signature is unsupported. Update the "
                    + "project compatibility bridge before rebuilding.",
                    root);
                return false;
            }

            try
            {
                uploadInputNodes.Invoke(
                    asset,
                    new object[]
                    {
                        session,
                        true, // bForceUpdate
                        true  // bUpdateAll
                    });

                Dictionary<string, int> readerNodeIds =
                    FindInputReaderNodeIds(session, asset.AssetID);
                for (int inputIndex = 0;
                    inputIndex < asset.InputNodes.Count;
                    inputIndex++)
                {
                    HEU_InputNode inputNode = asset.InputNodes[inputIndex];
                    int connectedMergeId = -1;
                    bool hasConnection = inputNode != null
                        && session.GetParamNodeValue(
                            asset.AssetID,
                            inputNode.ParamName,
                            out connectedMergeId)
                        && connectedMergeId >= 0;
                    if (!hasConnection)
                    {
                        Debug.LogErrorFormat(
                            root,
                            "CityRoad Safe Rebuild: parameter input {0} is not "
                            + "connected to an uploaded Houdini input node.",
                            inputNode != null
                                ? inputNode.ParamName
                                : "<null>");
                        return false;
                    }

                    if (!CookImmediateInputs(session, connectedMergeId)
                        || !session.CookNode(connectedMergeId, false))
                    {
                        Debug.LogErrorFormat(
                            root,
                            "CityRoad Safe Rebuild: failed to cook uploaded "
                            + "input merge {0} for input {1}.",
                            connectedMergeId,
                            inputIndex);
                        return false;
                    }

                    if (inputIndex >= s_InputReaderNodeNames.Length)
                    {
                        Debug.LogErrorFormat(
                            root,
                            "CityRoad Safe Rebuild: no input reader mapping for "
                            + "input {0}; the HDA must expose exactly {1} input(s).",
                            inputIndex,
                            ExpectedParameterInputCount);
                        return false;
                    }

                    string readerName = s_InputReaderNodeNames[inputIndex];
                    int readerNodeId;
                    if (!readerNodeIds.TryGetValue(
                            readerName,
                            out readerNodeId)
                        || !session.CookNode(readerNodeId, false))
                    {
                        Debug.LogErrorFormat(
                            root,
                            "CityRoad Safe Rebuild: failed to refresh HDA "
                            + "input reader {0}.",
                            readerName);
                        return false;
                    }

                    if (inputIndex == 0
                        && !HasGeometry(session, readerNodeId))
                    {
                        Debug.LogError(
                            "CityRoad Safe Rebuild: input 0 was uploaded but "
                            + "IN_ROAD_NETWORK still contains no geometry.",
                            root);
                        return false;
                    }
                }

                return true;
            }
            catch (TargetInvocationException exception)
            {
                Exception cause = exception.InnerException ?? exception;
                Debug.LogException(cause, root);
                return false;
            }
            catch (Exception exception)
            {
                Debug.LogException(exception, root);
                return false;
            }
        }

        private static Dictionary<string, int> FindInputReaderNodeIds(
            HEU_SessionBase session,
            int assetId)
        {
            var result = new Dictionary<string, int>(
                StringComparer.Ordinal);
            int[] childNodeIds;
            bool composed = HEU_SessionManager.GetComposedChildNodeList(
                session,
                assetId,
                (int)HAPI_NodeType.HAPI_NODETYPE_ANY,
                (int)HAPI_NodeFlags.HAPI_NODEFLAGS_ANY,
                true,
                out childNodeIds,
                false);
            if (!composed || childNodeIds == null)
                return result;

            var wanted = new HashSet<string>(
                s_InputReaderNodeNames,
                StringComparer.Ordinal);
            foreach (int nodeId in childNodeIds)
            {
                string nodeName =
                    HEU_SessionManager.GetNodeName(nodeId, session);
                if (wanted.Contains(nodeName))
                    result[nodeName] = nodeId;
            }

            return result;
        }

        private static bool CookImmediateInputs(
            HEU_SessionBase session,
            int nodeId)
        {
            const int MaxConsecutiveEmptyInputs = 8;
            int consecutiveEmptyInputs = 0;
            for (int inputIndex = 0; inputIndex < 64; inputIndex++)
            {
                int connectedNodeId;
                if (!session.QueryNodeInput(
                        nodeId,
                        inputIndex,
                        out connectedNodeId,
                        false))
                {
                    return false;
                }

                if (connectedNodeId < 0)
                {
                    consecutiveEmptyInputs++;
                    if (consecutiveEmptyInputs >= MaxConsecutiveEmptyInputs)
                        break;
                    continue;
                }

                consecutiveEmptyInputs = 0;
                if (!session.CookNode(connectedNodeId, false))
                    return false;
            }

            return true;
        }

        private static bool HasGeometry(
            HEU_SessionBase session,
            int nodeId)
        {
            var geoInfo = new HAPI_GeoInfo();
            if (!session.GetGeoInfo(nodeId, ref geoInfo, false))
                return false;

            for (int partIndex = 0;
                partIndex < geoInfo.partCount;
                partIndex++)
            {
                var partInfo = new HAPI_PartInfo();
                if (session.GetPartInfo(
                        geoInfo.nodeId,
                        partIndex,
                        ref partInfo)
                    && partInfo.pointCount > 0)
                {
                    return true;
                }
            }

            return false;
        }

        private static bool IsLoadedSceneObject(HEU_HoudiniAssetRoot root)
        {
            return root != null
                && !EditorUtility.IsPersistent(root)
                && root.gameObject.scene.IsValid()
                && root.gameObject.scene.isLoaded;
        }

        internal static bool IsCityRoad(HEU_HoudiniAssetRoot root)
        {
            if (root == null || root.HoudiniAsset == null)
                return false;

            string assetPath = root.HoudiniAsset.AssetPath;
            if (string.IsNullOrEmpty(assetPath))
                return false;

            assetPath = assetPath.Replace('\\', '/');
            return assetPath.EndsWith(
                CityRoadAssetPath,
                StringComparison.OrdinalIgnoreCase);
        }
    }

    /// <summary>
    /// Marks the CityRoad parameter input dirty when its bound Unity Spline changes.
    /// The bridge performs no automatic cook and has no Update loop: Houdini Engine's
    /// standard Recook command remains in control of the actual upload/cook timing.
    /// </summary>
    [InitializeOnLoad]
    internal static class CityRoadSplineInputUploadTracker
    {
        static CityRoadSplineInputUploadTracker()
        {
            Install();
        }

        [InitializeOnLoadMethod]
        private static void Install()
        {
            Spline.Changed -= OnSplineChanged;
            Spline.Changed += OnSplineChanged;
        }

        private static void OnSplineChanged(
            Spline changedSpline,
            int knotIndex,
            SplineModification modification)
        {
            if (changedSpline == null)
                return;

            HEU_HoudiniAssetRoot[] roots =
                Resources.FindObjectsOfTypeAll<HEU_HoudiniAssetRoot>();
            foreach (HEU_HoudiniAssetRoot root in roots)
            {
                if (!CityRoadSafeRebuild.IsCityRoad(root)
                    || root.HoudiniAsset == null
                    || root.HoudiniAsset.Parameters == null
                    || !root.gameObject.scene.IsValid()
                    || !root.gameObject.scene.isLoaded)
                {
                    continue;
                }

                HEU_InputNode roadNetworkInput =
                    FindRoadNetworkParameterInput(root.HoudiniAsset);
                GameObject inputObject = roadNetworkInput != null
                    && roadNetworkInput.NumInputEntries() > 0
                        ? roadNetworkInput.GetInputEntryGameObject(0)
                        : null;
                SplineContainer container = inputObject != null
                    ? inputObject.GetComponent<SplineContainer>()
                    : null;
                if (!ContainsSpline(container, changedSpline))
                    continue;

                if (root.HoudiniAsset.Parameters.SetAssetRefParameterValue(
                        CityRoadSafeRebuild.RoadNetworkParameterName,
                        inputObject,
                        0,
                        bRecookAsset: false))
                {
                    EditorUtility.SetDirty(root.HoudiniAsset.Parameters);
                    EditorUtility.SetDirty(root.HoudiniAsset);
                }
            }
        }

        private static HEU_InputNode FindRoadNetworkParameterInput(
            HEU_HoudiniAsset asset)
        {
            if (asset == null || asset.InputNodes == null)
                return null;

            foreach (HEU_InputNode input in asset.InputNodes)
            {
                if (input != null
                    && input.NodeType == HEU_InputNodeTypeWrapper.PARAMETER
                    && input.ObjectType == HEU_InputObjectTypeWrapper.SPLINE
                    && string.Equals(
                        input.ParamName,
                        CityRoadSafeRebuild.RoadNetworkParameterName,
                        StringComparison.Ordinal))
                {
                    return input;
                }
            }

            return null;
        }

        private static bool ContainsSpline(
            SplineContainer container,
            Spline candidate)
        {
            if (container == null || candidate == null)
                return false;

            foreach (Spline spline in container.Splines)
            {
                if (ReferenceEquals(spline, candidate))
                    return true;
            }

            return false;
        }
    }

    internal sealed class CityRoadHdaImportPostprocessor : AssetPostprocessor
    {
        private static void OnPostprocessAllAssets(
            string[] importedAssets,
            string[] deletedAssets,
            string[] movedAssets,
            string[] movedFromAssetPaths)
        {
            foreach (string importedAsset in importedAssets)
            {
                if (string.Equals(
                    importedAsset,
                    "Assets/PCG/HDA/City/CityRoad.hda",
                    StringComparison.OrdinalIgnoreCase))
                {
                    // Importing an HDA must not synchronously reload every
                    // loaded CityRoad instance. A CityRoad cook can be costly,
                    // and an automatic reload here also makes saving the HDA
                    // recursively trigger another cook while the definition is
                    // still being imported. Rebuild remains an explicit user or
                    // project-workflow action.
                    Debug.Log(
                        "CityRoad HDA definition imported. Run PCG/CityRoad/"
                        + "Safe Rebuild Selected when you are ready to cook.");
                    break;
                }
            }
        }
    }
}
#endif
