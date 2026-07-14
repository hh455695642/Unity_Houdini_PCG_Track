using System;
using System.Collections.Generic;
using System.Linq;
using HoudiniEngineUnity;
using PCGBike.Authoring;
using Unity.Mathematics;
using UnityEditor;
using UnityEditor.Callbacks;
using UnityEngine;
using UnityEngine.Splines;

namespace PCGBike.AuthoringEditor
{
    /// <summary>
    /// Project-owned Houdini input interface for explicitly marked PCG Track splines.
    /// It uploads Knot Contract V1 without modifying Houdini Engine package sources.
    /// </summary>
    [InitializeOnLoad]
    internal sealed class PCGTrackSplineInputInterface : HEU_InputInterface
    {
        private const int CustomPriority = DEFAULT_PRIORITY + 100;
        private const string LogPrefix = "[PCG Track Spline Input]";
        private const int MaxRegistrationAttempts = 8;

        private static int _registrationAttempts;

        static PCGTrackSplineInputInterface()
        {
            RegisterOrRetry();
        }

        [InitializeOnLoadMethod]
        private static void OnEditorLoad()
        {
            RegisterOrRetry();
        }

        private PCGTrackSplineInputInterface()
            : base(CustomPriority)
        {
        }

        [DidReloadScripts(1000)]
        private static void OnScriptsReloaded()
        {
            RegisterOrRetry();
        }

        private static void RegisterOrRetry()
        {
            if (HEU_InputUtility.GetInputInterfaceByType(typeof(HEU_InputInterfaceSpline)) != null)
            {
                RegisterInterfaceAfterReload();
                return;
            }

            ScheduleRegistration();
        }

        private static void ScheduleRegistration()
        {
            // Delay until Houdini Engine's built-in interfaces have completed their callbacks.
            EditorApplication.delayCall -= RegisterInterfaceAfterReload;
            EditorApplication.delayCall += RegisterInterfaceAfterReload;
        }

        private static void RegisterInterfaceAfterReload()
        {
            if (HEU_InputUtility.GetInputInterfaceByType(typeof(HEU_InputInterfaceSpline)) == null)
            {
                _registrationAttempts++;
                if (_registrationAttempts < MaxRegistrationAttempts)
                {
                    ScheduleRegistration();
                    return;
                }

                Debug.LogError(
                    $"{LogPrefix} Official HEU_InputInterfaceSpline is not registered; " +
                    "the PCG override was not installed so unmarked splines keep a safe failure mode.");
                return;
            }

            _registrationAttempts = 0;
            if (HEU_InputUtility.GetInputInterfaceByType(typeof(PCGTrackSplineInputInterface)) == null)
                new PCGTrackSplineInputInterface().RegisterInterface();
        }

        public override bool IsThisInputObjectSupported(GameObject inputObject)
        {
            if (inputObject == null || inputObject.GetComponent<SplineContainer>() == null)
                return false;

            TrackSplineHoudiniInputSettings inputSettings =
                inputObject.GetComponent<TrackSplineHoudiniInputSettings>();
            return inputSettings != null && inputSettings.UsesCustomInterface;
        }

        public override bool CreateInputNodeWithDataUpload(
            HEU_SessionBase session,
            int connectNodeID,
            GameObject inputObject,
            out int inputNodeID)
        {
            inputNodeID = HEU_Defines.HEU_INVALID_NODE_ID;

            if (session == null ||
                !HEU_HAPIUtility.IsNodeValidInHoudini(session, connectNodeID))
            {
                HEU_Logger.LogErrorFormat(
                    "{0} Connection node {1} is invalid for {2}.",
                    LogPrefix,
                    connectNodeID,
                    inputObject != null ? inputObject.name : "<null>");
                return false;
            }

            if (!TryBuildInputData(inputObject, out SplineContainerData inputData))
                return false;

            int rootNodeID = HEU_Defines.HEU_INVALID_NODE_ID;
            session.CreateInputNode(out rootNodeID, inputObject.name + "_KnotContract_0");
            if (!IsValidNode(session, rootNodeID))
            {
                HEU_Logger.LogErrorFormat(
                    "{0} Failed to create input curve for {1}, spline 0.",
                    LogPrefix,
                    inputObject.name);
                return false;
            }

            inputNodeID = rootNodeID;
            if (!UploadSpline(
                    session,
                    rootNodeID,
                    inputData.Splines[0],
                    Matrix4x4.identity,
                    inputObject.name,
                    0))
            {
                ReportValidation(inputData, false, "Spline 0 HAPI upload failed.");
                return false;
            }

            if (inputData.Splines.Count == 1)
            {
                ReportValidation(inputData, true, "Knot Contract V1 committed.");
                return true;
            }

            int mergeNodeID = HEU_Defines.HEU_INVALID_NODE_ID;
            int parentNodeID = HEU_HAPIUtility.GetParentNodeID(session, rootNodeID);
            if (!session.CreateNode(parentNodeID, "merge", null, false, out mergeNodeID))
            {
                HEU_Logger.LogErrorFormat(
                    "{0} Failed to create the branch merge node for {1}.",
                    LogPrefix,
                    inputObject.name);
                return false;
            }

            if (!session.ConnectNodeInput(mergeNodeID, 0, rootNodeID))
            {
                HEU_Logger.LogErrorFormat(
                    "{0} Failed to connect root spline for {1}.",
                    LogPrefix,
                    inputObject.name);
                return false;
            }

            if (!session.SetNodeDisplay(mergeNodeID, 1))
            {
                HEU_Logger.LogWarningFormat(
                    "{0} Could not set the branch merge display flag for {1}.",
                    LogPrefix,
                    inputObject.name);
            }

            inputNodeID = mergeNodeID;
            Matrix4x4 localToWorld = inputData.Transform.localToWorldMatrix;
            for (int splineIndex = 1; splineIndex < inputData.Splines.Count; splineIndex++)
            {
                int branchNodeID = HEU_Defines.HEU_INVALID_NODE_ID;
                session.CreateInputNode(
                    out branchNodeID,
                    inputObject.name + "_KnotContract_" + splineIndex);

                if (!IsValidNode(session, branchNodeID))
                {
                    HEU_Logger.LogErrorFormat(
                        "{0} Failed to create input curve for {1}, spline {2}.",
                        LogPrefix,
                        inputObject.name,
                        splineIndex);
                    return false;
                }

                if (!UploadSpline(
                        session,
                        branchNodeID,
                        inputData.Splines[splineIndex],
                        localToWorld,
                        inputObject.name,
                        splineIndex))
                {
                    ReportValidation(inputData, false, $"Spline {splineIndex} HAPI upload failed.");
                    return false;
                }

                if (!session.ConnectNodeInput(mergeNodeID, splineIndex, branchNodeID))
                {
                    HEU_Logger.LogErrorFormat(
                        "{0} Failed to connect {1}, spline {2}, to the branch merge.",
                        LogPrefix,
                        inputObject.name,
                        splineIndex);
                    return false;
                }
            }

            if (!session.CookNode(mergeNodeID, false))
            {
                HEU_Logger.LogErrorFormat(
                    "{0} Branch merge cook failed for {1}.",
                    LogPrefix,
                    inputObject.name);
                return false;
            }

            ReportValidation(inputData, true, "Knot Contract V1 committed through multi-spline merge.");
            return true;
        }

        private static bool TryBuildInputData(
            GameObject inputObject,
            out SplineContainerData inputData)
        {
            inputData = null;
            if (inputObject == null)
                return false;

            SplineContainer container = inputObject.GetComponent<SplineContainer>();
            TrackSplineHoudiniInputSettings inputSettings =
                inputObject.GetComponent<TrackSplineHoudiniInputSettings>();
            if (container == null || inputSettings == null || !inputSettings.UsesCustomInterface)
            {
                HEU_Logger.LogErrorFormat(
                    "{0} {1} is missing an enabled SplineContainer or PCG input marker.",
                    LogPrefix,
                    inputObject.name);
                return false;
            }

            List<SplineData> splines = new List<SplineData>(container.Splines.Count);
            int splineIndex = 0;
            foreach (Spline spline in container.Splines)
            {
                if (spline == null)
                {
                    inputSettings.SetEditorUploadValidation(
                        false, $"Spline {splineIndex} is null.", container.Splines.Count, 0, "Unknown");
                    return false;
                }

                int minimumKnotCount = spline.Closed ? 3 : 2;
                if (spline.Count < minimumKnotCount)
                {
                    inputSettings.SetEditorUploadValidation(
                        false,
                        $"Spline {splineIndex} requires at least {minimumKnotCount} Knots.",
                        container.Splines.Count,
                        spline.Count,
                        spline.Closed ? "Closed" : "Open");
                    return false;
                }

                splines.Add(new SplineData(
                    spline.Closed,
                    spline.Knots.ToArray()));
                splineIndex++;
            }

            if (splines.Count == 0)
            {
                HEU_Logger.LogErrorFormat(
                    "{0} No authored spline knots were found on {1}.",
                    LogPrefix,
                    inputObject.name);
                return false;
            }

            inputData = new SplineContainerData(
                splines,
                inputObject.transform,
                inputSettings);
            return true;
        }

        private static bool UploadSpline(
            HEU_SessionBase session,
            int inputNodeID,
            SplineData splineData,
            Matrix4x4 localToWorld,
            string objectName,
            int splineIndex)
        {
            int pointCount = splineData.Knots.Length;
            HAPI_GeoInfo displayGeoInfo = new HAPI_GeoInfo();
            if (!session.GetDisplayGeoInfo(inputNodeID, ref displayGeoInfo))
                return LogUploadFailure(objectName, splineIndex, "GetDisplayGeoInfo");
            int geoNodeID = displayGeoInfo.nodeId;

            HAPI_PartInfo partInfo = new HAPI_PartInfo();
            partInfo.init();
            partInfo.id = 0;
            partInfo.type = HAPI_PartType.HAPI_PARTTYPE_CURVE;
            partInfo.faceCount = 1;
            partInfo.vertexCount = pointCount;
            partInfo.pointCount = pointCount;
            partInfo.pointAttributeCount = 6;
            partInfo.primitiveAttributeCount = 3;
            partInfo.detailAttributeCount = 3;
            if (!session.SetPartInfo(geoNodeID, 0, ref partInfo))
                return LogUploadFailure(objectName, splineIndex, "SetPartInfo");

            // This is a data-carrier curve. Houdini reconstructs the actual cubic Bezier
            // from P + relative handles before the single production Resample.
            HAPI_CurveInfo curveInfo = new HAPI_CurveInfo
            {
                curveType = HAPI_CurveType.HAPI_CURVETYPE_LINEAR,
                curveCount = 1,
                vertexCount = pointCount,
                knotCount = 0,
                // A linear carrier uses polygon closure only. HAPI's periodic mode
                // appends a separate periodic point and must not be combined with
                // isClosed; that invalid combination can crash a native HAPI cook.
                isPeriodic = false,
                isRational = false,
                order = 2,
                hasKnots = false,
                isClosed = splineData.Closed
            };
            if (!session.SetCurveInfo(geoNodeID, 0, ref curveInfo))
                return LogUploadFailure(objectName, splineIndex, "SetCurveInfo");

            int[] curveCounts = { pointCount };
            if (!session.SetCurveCounts(geoNodeID, 0, curveCounts, 0, 1))
                return LogUploadFailure(objectName, splineIndex, "SetCurveCounts");

            float[] positions = new float[pointCount * 3];
            float[] rotations = new float[pointCount * 4];
            float[] tangentIn = new float[pointCount * 3];
            float[] tangentOut = new float[pointCount * 3];
            int[] knotIndices = new int[pointCount];
            int[] splineIndices = new int[pointCount];

            for (int pointIndex = 0; pointIndex < pointCount; pointIndex++)
            {
                BezierKnot knot = splineData.Knots[pointIndex];
                knotIndices[pointIndex] = pointIndex;
                splineIndices[pointIndex] = splineIndex;

                Vector3 position = localToWorld.MultiplyPoint((Vector3)knot.Position);
                Quaternion knotRotation = ToNormalizedUnityRotation(knot.Rotation);
                // BezierKnot TangentIn/Out are Knot-local vectors. Unity's exact
                // Bezier definition rotates each handle by Knot.Rotation before
                // adding it to Position (BezierCurve.cs in com.unity.splines).
                Vector3 inHandle = localToWorld.MultiplyVector(
                    knotRotation * (Vector3)knot.TangentIn);
                Vector3 outHandle = localToWorld.MultiplyVector(
                    knotRotation * (Vector3)knot.TangentOut);
                Quaternion rotation = BuildUploadedRotation(knot.Rotation, localToWorld);
                if (!WriteKnot(
                        positions, rotations, tangentIn, tangentOut, pointIndex,
                        position, rotation, inHandle, outHandle, objectName, splineIndex))
                {
                    return false;
                }
            }

            if (!AddFloatAttribute(session, geoNodeID, "P", HAPI_AttributeOwner.HAPI_ATTROWNER_POINT,
                    pointCount, 3, HAPI_AttributeTypeInfo.HAPI_ATTRIBUTE_TYPE_POINT, positions) ||
                !AddFloatAttribute(session, geoNodeID, "rot", HAPI_AttributeOwner.HAPI_ATTROWNER_POINT,
                    pointCount, 4, HAPI_AttributeTypeInfo.HAPI_ATTRIBUTE_TYPE_QUATERNION, rotations) ||
                !AddFloatAttribute(session, geoNodeID, "unity_tangent_in", HAPI_AttributeOwner.HAPI_ATTROWNER_POINT,
                    pointCount, 3, HAPI_AttributeTypeInfo.HAPI_ATTRIBUTE_TYPE_VECTOR, tangentIn) ||
                !AddFloatAttribute(session, geoNodeID, "unity_tangent_out", HAPI_AttributeOwner.HAPI_ATTROWNER_POINT,
                    pointCount, 3, HAPI_AttributeTypeInfo.HAPI_ATTRIBUTE_TYPE_VECTOR, tangentOut) ||
                !AddIntAttribute(session, geoNodeID, "unity_knot_index", HAPI_AttributeOwner.HAPI_ATTROWNER_POINT,
                    pointCount, knotIndices) ||
                !AddIntAttribute(session, geoNodeID, "unity_spline_index", HAPI_AttributeOwner.HAPI_ATTROWNER_POINT,
                    pointCount, splineIndices) ||
                !AddIntAttribute(session, geoNodeID, "unity_spline_index", HAPI_AttributeOwner.HAPI_ATTROWNER_PRIM,
                    1, new[] { splineIndex }) ||
                !AddIntAttribute(session, geoNodeID, "unity_spline_closed", HAPI_AttributeOwner.HAPI_ATTROWNER_PRIM,
                    1, new[] { splineData.Closed ? 1 : 0 }) ||
                !AddIntAttribute(session, geoNodeID, "unity_spline_knot_count", HAPI_AttributeOwner.HAPI_ATTROWNER_PRIM,
                    1, new[] { pointCount }) ||
                !AddIntAttribute(session, geoNodeID, "unity_spline_contract_version", HAPI_AttributeOwner.HAPI_ATTROWNER_DETAIL,
                    1, new[] { 1 }) ||
                !AddIntAttribute(session, geoNodeID, "unity_spline_contract_valid", HAPI_AttributeOwner.HAPI_ATTROWNER_DETAIL,
                    1, new[] { 1 }) ||
                !AddStringAttribute(session, geoNodeID, "unity_spline_contract_source", "UnitySplineContainer"))
            {
                return LogUploadFailure(objectName, splineIndex, "Set contract attributes");
            }

            if (!session.CommitGeo(geoNodeID))
            {
                HEU_Logger.LogErrorFormat(
                    "{0} CommitGeo failed for {1}, spline {2}.",
                    LogPrefix,
                    objectName,
                    splineIndex);
                return false;
            }

            // Curve marshalling uses CurveCounts + point P as the CV topology. It has
            // no polygon VertexList, and the parent HDA cook consumes the committed
            // geometry. Independently cooking this editable input SOP is unsupported.
            return true;
        }

        private static bool WriteKnot(
            float[] positions,
            float[] rotations,
            float[] tangentIn,
            float[] tangentOut,
            int pointIndex,
            Vector3 position,
            Quaternion rotation,
            Vector3 inHandle,
            Vector3 outHandle,
            string objectName,
            int splineIndex)
        {
            if (!IsFinite(position) || !IsFinite(rotation) ||
                !IsFinite(inHandle) || !IsFinite(outHandle))
            {
                HEU_Logger.LogErrorFormat(
                    "{0} Non-finite Knot data on {1}, spline {2}, Knot {3}.",
                    LogPrefix,
                    objectName,
                    splineIndex,
                    pointIndex);
                return false;
            }

            float rotationMagnitudeSq =
                rotation.x * rotation.x +
                rotation.y * rotation.y +
                rotation.z * rotation.z +
                rotation.w * rotation.w;
            if (rotationMagnitudeSq <= 1e-12f ||
                Mathf.Abs(rotationMagnitudeSq - 1.0f) > 1e-4f)
            {
                HEU_Logger.LogErrorFormat(
                    "{0} Non-unit rotation on {1}, spline {2}, point {3} (lengthSq={4}).",
                    LogPrefix,
                    objectName,
                    splineIndex,
                    pointIndex,
                    rotationMagnitudeSq);
                return false;
            }

            // Quaternion.LookRotation already returns a unit quaternion. Avoid a second
            // normalization here: it introduces needless bit-level drift from the
            // Houdini Engine patch this interface is replacing.

            HEU_HAPIUtility.ConvertPositionUnityToHoudini(
                position,
                out positions[pointIndex * 3 + 0],
                out positions[pointIndex * 3 + 1],
                out positions[pointIndex * 3 + 2]);
            HEU_HAPIUtility.ConvertRotationUnityToHoudini(
                rotation,
                out rotations[pointIndex * 4 + 0],
                out rotations[pointIndex * 4 + 1],
                out rotations[pointIndex * 4 + 2],
                out rotations[pointIndex * 4 + 3]);
            HEU_HAPIUtility.ConvertPositionUnityToHoudini(
                inHandle,
                out tangentIn[pointIndex * 3 + 0],
                out tangentIn[pointIndex * 3 + 1],
                out tangentIn[pointIndex * 3 + 2]);
            HEU_HAPIUtility.ConvertPositionUnityToHoudini(
                outHandle,
                out tangentOut[pointIndex * 3 + 0],
                out tangentOut[pointIndex * 3 + 1],
                out tangentOut[pointIndex * 3 + 2]);

            for (int component = 0; component < 3; component++)
            {
                if (!IsFinite(positions[pointIndex * 3 + component]))
                    return false;
            }
            for (int component = 0; component < 4; component++)
            {
                if (!IsFinite(rotations[pointIndex * 4 + component]))
                    return false;
            }
            for (int component = 0; component < 3; component++)
            {
                if (!IsFinite(tangentIn[pointIndex * 3 + component]) ||
                    !IsFinite(tangentOut[pointIndex * 3 + component]))
                {
                    return false;
                }
            }

            return true;
        }

        private static Quaternion BuildUploadedRotation(
            quaternion knotRotation,
            Matrix4x4 localToWorld)
        {
            Quaternion sourceRotation = ToNormalizedUnityRotation(knotRotation);
            if (!IsFinite(sourceRotation))
                return new Quaternion(float.NaN, 0.0f, 0.0f, 0.0f);

            Vector3 uploadedTangent =
                localToWorld.MultiplyVector(sourceRotation * Vector3.forward);
            Vector3 uploadedUp =
                localToWorld.MultiplyVector(sourceRotation * Vector3.up);

            if (!IsFinite(uploadedTangent) ||
                uploadedTangent.sqrMagnitude <= 1e-10f)
            {
                uploadedTangent = Vector3.forward;
            }
            uploadedTangent.Normalize();

            uploadedUp = Vector3.ProjectOnPlane(uploadedUp, uploadedTangent);
            if (!IsFinite(uploadedUp) || uploadedUp.sqrMagnitude <= 1e-10f)
            {
                Vector3 fallbackAxis =
                    Mathf.Abs(Vector3.Dot(uploadedTangent, Vector3.up)) < 0.999f
                        ? Vector3.up
                        : Vector3.right;
                uploadedUp =
                    Vector3.ProjectOnPlane(fallbackAxis, uploadedTangent);
            }
            uploadedUp.Normalize();

            return Quaternion.LookRotation(uploadedTangent, uploadedUp);
        }

        private static Quaternion ToNormalizedUnityRotation(quaternion rotation)
        {
            Quaternion result = new Quaternion(
                rotation.value.x,
                rotation.value.y,
                rotation.value.z,
                rotation.value.w);
            if (!IsFinite(result))
                return new Quaternion(float.NaN, 0.0f, 0.0f, 0.0f);

            float magnitudeSq =
                result.x * result.x + result.y * result.y +
                result.z * result.z + result.w * result.w;
            return magnitudeSq > 1e-12f
                ? Quaternion.Normalize(result)
                : new Quaternion(float.NaN, 0.0f, 0.0f, 0.0f);
        }

        private static bool AddFloatAttribute(
            HEU_SessionBase session,
            int nodeID,
            string name,
            HAPI_AttributeOwner owner,
            int count,
            int tupleSize,
            HAPI_AttributeTypeInfo typeInfo,
            float[] data)
        {
            HAPI_AttributeInfo info = CreateAttributeInfo(
                owner, HAPI_StorageType.HAPI_STORAGETYPE_FLOAT, count, tupleSize, typeInfo);
            return session.AddAttribute(nodeID, 0, name, ref info) &&
                   session.SetAttributeFloatData(nodeID, 0, name, ref info, data, 0, count);
        }

        private static bool AddIntAttribute(
            HEU_SessionBase session,
            int nodeID,
            string name,
            HAPI_AttributeOwner owner,
            int count,
            int[] data)
        {
            HAPI_AttributeInfo info = CreateAttributeInfo(
                owner, HAPI_StorageType.HAPI_STORAGETYPE_INT, count, 1,
                HAPI_AttributeTypeInfo.HAPI_ATTRIBUTE_TYPE_NONE);
            return session.AddAttribute(nodeID, 0, name, ref info) &&
                   session.SetAttributeIntData(nodeID, 0, name, ref info, data, 0, count);
        }

        private static bool AddStringAttribute(
            HEU_SessionBase session,
            int nodeID,
            string name,
            string value)
        {
            HAPI_AttributeInfo info = CreateAttributeInfo(
                HAPI_AttributeOwner.HAPI_ATTROWNER_DETAIL,
                HAPI_StorageType.HAPI_STORAGETYPE_STRING,
                1,
                1,
                HAPI_AttributeTypeInfo.HAPI_ATTRIBUTE_TYPE_NONE);
            return session.AddAttribute(nodeID, 0, name, ref info) &&
                   session.SetAttributeStringData(nodeID, 0, name, ref info, new[] { value }, 0, 1);
        }

        private static HAPI_AttributeInfo CreateAttributeInfo(
            HAPI_AttributeOwner owner,
            HAPI_StorageType storage,
            int count,
            int tupleSize,
            HAPI_AttributeTypeInfo typeInfo)
        {
            return new HAPI_AttributeInfo
            {
                exists = true,
                owner = owner,
                originalOwner = HAPI_AttributeOwner.HAPI_ATTROWNER_INVALID,
                storage = storage,
                count = count,
                tupleSize = tupleSize,
                typeInfo = typeInfo
            };
        }

        private static bool LogUploadFailure(string objectName, int splineIndex, string operation)
        {
            HEU_Logger.LogErrorFormat(
                "{0} {1} failed for {2}, spline {3}.",
                LogPrefix, operation, objectName, splineIndex);
            return false;
        }

        private static void ReportValidation(
            SplineContainerData inputData,
            bool success,
            string message)
        {
            int knotCount = inputData.Splines.Sum(spline => spline.Knots.Length);
            bool anyClosed = inputData.Splines.Any(spline => spline.Closed);
            bool anyOpen = inputData.Splines.Any(spline => !spline.Closed);
            string closedState = anyClosed && anyOpen ? "Mixed" : (anyClosed ? "Closed" : "Open");
            inputData.Settings.SetEditorUploadValidation(
                success, message, inputData.Splines.Count, knotCount, closedState);
        }

        private static bool IsValidNode(
            HEU_SessionBase session,
            int nodeID)
        {
            return nodeID != HEU_Defines.HEU_INVALID_NODE_ID &&
                   HEU_HAPIUtility.IsNodeValidInHoudini(session, nodeID);
        }

        private static bool IsFinite(Vector3 value)
        {
            return IsFinite(value.x) &&
                   IsFinite(value.y) &&
                   IsFinite(value.z);
        }

        private static bool IsFinite(Quaternion value)
        {
            return IsFinite(value.x) &&
                   IsFinite(value.y) &&
                   IsFinite(value.z) &&
                   IsFinite(value.w);
        }

        private static bool IsFinite(float value)
        {
            return !float.IsNaN(value) && !float.IsInfinity(value);
        }

        private sealed class SplineData
        {
            public SplineData(
                bool closed,
                BezierKnot[] knots)
            {
                Closed = closed;
                Knots = knots;
            }

            public bool Closed { get; }
            public BezierKnot[] Knots { get; }
        }

        private sealed class SplineContainerData
        {
            public SplineContainerData(
                List<SplineData> splines,
                Transform transform,
                TrackSplineHoudiniInputSettings settings)
            {
                Splines = splines;
                Transform = transform;
                Settings = settings;
            }

            public List<SplineData> Splines { get; }
            public Transform Transform { get; }
            public TrackSplineHoudiniInputSettings Settings { get; }
        }
    }
}
