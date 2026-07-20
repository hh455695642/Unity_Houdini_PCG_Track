using HoudiniEngineUnity;
using UnityEngine;

namespace PCGBike.Editor.Houdini.TrackSplineInput
{
    internal static class TrackSplineHapiUploader
    {
        private const string LogPrefix = "[PCG Track Spline Input]";
        private const int ContractVersion = 1;
        private const string ContractSource = "UnitySplineContainer";

        public static bool TryUpload(
            HEU_SessionBase session,
            string objectName,
            TrackSplineInputSnapshot snapshot,
            out int inputNodeID,
            out string validationMessage)
        {
            inputNodeID = HEU_Defines.HEU_INVALID_NODE_ID;
            validationMessage = "HAPI upload failed.";

            int rootNodeID = HEU_Defines.HEU_INVALID_NODE_ID;
            session.CreateInputNode(out rootNodeID, objectName + "_KnotContract_0");
            if (!IsValidNode(session, rootNodeID))
            {
                HEU_Logger.LogErrorFormat(
                    "{0} Failed to create input curve for {1}, spline 0.",
                    LogPrefix,
                    objectName);
                validationMessage = "Spline 0 input node creation failed.";
                return false;
            }

            inputNodeID = rootNodeID;
            if (!TryBuildAndUploadSpline(
                    session,
                    rootNodeID,
                    snapshot.Splines[0],
                    Matrix4x4.identity,
                    objectName,
                    0))
            {
                validationMessage = "Spline 0 HAPI upload failed.";
                return false;
            }

            if (snapshot.Splines.Count == 1)
            {
                validationMessage = "Knot Contract V1 committed.";
                return true;
            }

            int mergeNodeID = HEU_Defines.HEU_INVALID_NODE_ID;
            int parentNodeID = HEU_HAPIUtility.GetParentNodeID(session, rootNodeID);
            if (!session.CreateNode(parentNodeID, "merge", null, false, out mergeNodeID))
            {
                HEU_Logger.LogErrorFormat(
                    "{0} Failed to create the branch merge node for {1}.",
                    LogPrefix,
                    objectName);
                validationMessage = "Multi-spline merge node creation failed.";
                return false;
            }

            if (!session.ConnectNodeInput(mergeNodeID, 0, rootNodeID))
            {
                HEU_Logger.LogErrorFormat(
                    "{0} Failed to connect root spline for {1}.",
                    LogPrefix,
                    objectName);
                validationMessage = "Root spline merge connection failed.";
                return false;
            }

            if (!session.SetNodeDisplay(mergeNodeID, 1))
            {
                HEU_Logger.LogWarningFormat(
                    "{0} Could not set the branch merge display flag for {1}.",
                    LogPrefix,
                    objectName);
            }

            inputNodeID = mergeNodeID;
            Matrix4x4 localToWorld = snapshot.Transform.localToWorldMatrix;
            for (int splineIndex = 1; splineIndex < snapshot.Splines.Count; splineIndex++)
            {
                int branchNodeID = HEU_Defines.HEU_INVALID_NODE_ID;
                session.CreateInputNode(
                    out branchNodeID,
                    objectName + "_KnotContract_" + splineIndex);
                if (!IsValidNode(session, branchNodeID))
                {
                    HEU_Logger.LogErrorFormat(
                        "{0} Failed to create input curve for {1}, spline {2}.",
                        LogPrefix,
                        objectName,
                        splineIndex);
                    validationMessage = $"Spline {splineIndex} input node creation failed.";
                    return false;
                }

                if (!TryBuildAndUploadSpline(
                        session,
                        branchNodeID,
                        snapshot.Splines[splineIndex],
                        localToWorld,
                        objectName,
                        splineIndex))
                {
                    validationMessage = $"Spline {splineIndex} HAPI upload failed.";
                    return false;
                }

                if (!session.ConnectNodeInput(mergeNodeID, splineIndex, branchNodeID))
                {
                    HEU_Logger.LogErrorFormat(
                        "{0} Failed to connect {1}, spline {2}, to the branch merge.",
                        LogPrefix,
                        objectName,
                        splineIndex);
                    validationMessage = $"Spline {splineIndex} merge connection failed.";
                    return false;
                }
            }

            if (!session.CookNode(mergeNodeID, false))
            {
                HEU_Logger.LogErrorFormat(
                    "{0} Branch merge cook failed for {1}.",
                    LogPrefix,
                    objectName);
                validationMessage = "Multi-spline merge cook failed.";
                return false;
            }

            validationMessage = "Knot Contract V1 committed through multi-spline merge.";
            return true;
        }

        private static bool TryBuildAndUploadSpline(
            HEU_SessionBase session,
            int inputNodeID,
            TrackSplineSnapshot spline,
            Matrix4x4 localToWorld,
            string objectName,
            int splineIndex)
        {
            return TrackSplineHapiPayloadBuilder.TryCreate(
                       spline,
                       localToWorld,
                       objectName,
                       splineIndex,
                       out TrackSplineHapiPayload payload) &&
                   UploadSpline(session, inputNodeID, payload, objectName);
        }

        private static bool UploadSpline(
            HEU_SessionBase session,
            int inputNodeID,
            TrackSplineHapiPayload payload,
            string objectName)
        {
            HAPI_GeoInfo displayGeoInfo = new HAPI_GeoInfo();
            if (!session.GetDisplayGeoInfo(inputNodeID, ref displayGeoInfo))
                return LogUploadFailure(objectName, payload.SplineIndex, "GetDisplayGeoInfo");
            int geoNodeID = displayGeoInfo.nodeId;

            HAPI_PartInfo partInfo = new HAPI_PartInfo();
            partInfo.init();
            partInfo.id = 0;
            partInfo.type = HAPI_PartType.HAPI_PARTTYPE_CURVE;
            partInfo.faceCount = 1;
            partInfo.vertexCount = payload.PointCount;
            partInfo.pointCount = payload.PointCount;
            partInfo.pointAttributeCount = 6;
            partInfo.primitiveAttributeCount = 3;
            partInfo.detailAttributeCount = 3;
            if (!session.SetPartInfo(geoNodeID, 0, ref partInfo))
                return LogUploadFailure(objectName, payload.SplineIndex, "SetPartInfo");

            // The curve is a data carrier. Houdini reconstructs cubic Bezier segments
            // from P and relative handles before the single production Resample.
            HAPI_CurveInfo curveInfo = new HAPI_CurveInfo
            {
                curveType = HAPI_CurveType.HAPI_CURVETYPE_LINEAR,
                curveCount = 1,
                vertexCount = payload.PointCount,
                knotCount = 0,
                isPeriodic = false,
                isRational = false,
                order = 2,
                hasKnots = false,
                isClosed = payload.Closed
            };
            if (!session.SetCurveInfo(geoNodeID, 0, ref curveInfo))
                return LogUploadFailure(objectName, payload.SplineIndex, "SetCurveInfo");

            int[] curveCounts = { payload.PointCount };
            if (!session.SetCurveCounts(geoNodeID, 0, curveCounts, 0, 1))
                return LogUploadFailure(objectName, payload.SplineIndex, "SetCurveCounts");

            if (!AddFloatAttribute(session, geoNodeID, "P", HAPI_AttributeOwner.HAPI_ATTROWNER_POINT,
                    payload.PointCount, 3, HAPI_AttributeTypeInfo.HAPI_ATTRIBUTE_TYPE_POINT, payload.Positions) ||
                !AddFloatAttribute(session, geoNodeID, "rot", HAPI_AttributeOwner.HAPI_ATTROWNER_POINT,
                    payload.PointCount, 4, HAPI_AttributeTypeInfo.HAPI_ATTRIBUTE_TYPE_QUATERNION, payload.Rotations) ||
                !AddFloatAttribute(session, geoNodeID, "unity_tangent_in", HAPI_AttributeOwner.HAPI_ATTROWNER_POINT,
                    payload.PointCount, 3, HAPI_AttributeTypeInfo.HAPI_ATTRIBUTE_TYPE_VECTOR, payload.TangentIn) ||
                !AddFloatAttribute(session, geoNodeID, "unity_tangent_out", HAPI_AttributeOwner.HAPI_ATTROWNER_POINT,
                    payload.PointCount, 3, HAPI_AttributeTypeInfo.HAPI_ATTRIBUTE_TYPE_VECTOR, payload.TangentOut) ||
                !AddIntAttribute(session, geoNodeID, "unity_knot_index", HAPI_AttributeOwner.HAPI_ATTROWNER_POINT,
                    payload.PointCount, payload.KnotIndices) ||
                !AddIntAttribute(session, geoNodeID, "unity_spline_index", HAPI_AttributeOwner.HAPI_ATTROWNER_POINT,
                    payload.PointCount, payload.SplineIndices) ||
                !AddIntAttribute(session, geoNodeID, "unity_spline_index", HAPI_AttributeOwner.HAPI_ATTROWNER_PRIM,
                    1, new[] { payload.SplineIndex }) ||
                !AddIntAttribute(session, geoNodeID, "unity_spline_closed", HAPI_AttributeOwner.HAPI_ATTROWNER_PRIM,
                    1, new[] { payload.Closed ? 1 : 0 }) ||
                !AddIntAttribute(session, geoNodeID, "unity_spline_knot_count", HAPI_AttributeOwner.HAPI_ATTROWNER_PRIM,
                    1, new[] { payload.PointCount }) ||
                !AddIntAttribute(session, geoNodeID, "unity_spline_contract_version", HAPI_AttributeOwner.HAPI_ATTROWNER_DETAIL,
                    1, new[] { ContractVersion }) ||
                !AddIntAttribute(session, geoNodeID, "unity_spline_contract_valid", HAPI_AttributeOwner.HAPI_ATTROWNER_DETAIL,
                    1, new[] { 1 }) ||
                !AddStringAttribute(session, geoNodeID, "unity_spline_contract_source", ContractSource))
            {
                return LogUploadFailure(objectName, payload.SplineIndex, "Set contract attributes");
            }

            if (!session.CommitGeo(geoNodeID))
            {
                HEU_Logger.LogErrorFormat(
                    "{0} CommitGeo failed for {1}, spline {2}.",
                    LogPrefix,
                    objectName,
                    payload.SplineIndex);
                return false;
            }

            return true;
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
                owner,
                HAPI_StorageType.HAPI_STORAGETYPE_FLOAT,
                count,
                tupleSize,
                typeInfo);
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
                owner,
                HAPI_StorageType.HAPI_STORAGETYPE_INT,
                count,
                1,
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

        private static bool IsValidNode(HEU_SessionBase session, int nodeID)
        {
            return nodeID != HEU_Defines.HEU_INVALID_NODE_ID &&
                   HEU_HAPIUtility.IsNodeValidInHoudini(session, nodeID);
        }

        private static bool LogUploadFailure(
            string objectName,
            int splineIndex,
            string operation)
        {
            HEU_Logger.LogErrorFormat(
                "{0} {1} failed for {2}, spline {3}.",
                LogPrefix,
                operation,
                objectName,
                splineIndex);
            return false;
        }
    }
}
