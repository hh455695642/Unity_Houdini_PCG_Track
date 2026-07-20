using HoudiniEngineUnity;
using Unity.Mathematics;
using UnityEngine;
using UnityEngine.Splines;

namespace PCGBike.Editor.Houdini.TrackSplineInput
{
    internal sealed class TrackSplineHapiPayload
    {
        public TrackSplineHapiPayload(
            bool closed,
            int splineIndex,
            float[] positions,
            float[] rotations,
            float[] tangentIn,
            float[] tangentOut,
            int[] knotIndices,
            int[] splineIndices)
        {
            Closed = closed;
            SplineIndex = splineIndex;
            Positions = positions;
            Rotations = rotations;
            TangentIn = tangentIn;
            TangentOut = tangentOut;
            KnotIndices = knotIndices;
            SplineIndices = splineIndices;
        }

        public bool Closed { get; }
        public int SplineIndex { get; }
        public int PointCount => KnotIndices.Length;
        public float[] Positions { get; }
        public float[] Rotations { get; }
        public float[] TangentIn { get; }
        public float[] TangentOut { get; }
        public int[] KnotIndices { get; }
        public int[] SplineIndices { get; }
    }

    internal static class TrackSplineHapiPayloadBuilder
    {
        private const string LogPrefix = "[PCG Track Spline Input]";

        public static bool TryCreate(
            TrackSplineSnapshot spline,
            Matrix4x4 localToWorld,
            string objectName,
            int splineIndex,
            out TrackSplineHapiPayload payload)
        {
            payload = null;
            int pointCount = spline.Knots.Length;
            float[] positions = new float[pointCount * 3];
            float[] rotations = new float[pointCount * 4];
            float[] tangentIn = new float[pointCount * 3];
            float[] tangentOut = new float[pointCount * 3];
            int[] knotIndices = new int[pointCount];
            int[] splineIndices = new int[pointCount];

            for (int pointIndex = 0; pointIndex < pointCount; pointIndex++)
            {
                BezierKnot knot = spline.Knots[pointIndex];
                knotIndices[pointIndex] = pointIndex;
                splineIndices[pointIndex] = splineIndex;

                Vector3 position = localToWorld.MultiplyPoint((Vector3)knot.Position);
                Quaternion knotRotation = TrackSplineCoordinateUtility.ToNormalizedUnityRotation(knot.Rotation);
                Vector3 inHandle = localToWorld.MultiplyVector(
                    knotRotation * (Vector3)knot.TangentIn);
                Vector3 outHandle = localToWorld.MultiplyVector(
                    knotRotation * (Vector3)knot.TangentOut);
                Quaternion rotation = TrackSplineCoordinateUtility.BuildUploadedRotation(
                    knot.Rotation,
                    localToWorld);

                if (!WriteKnot(
                        positions,
                        rotations,
                        tangentIn,
                        tangentOut,
                        pointIndex,
                        position,
                        rotation,
                        inHandle,
                        outHandle,
                        objectName,
                        splineIndex))
                {
                    return false;
                }
            }

            payload = new TrackSplineHapiPayload(
                spline.Closed,
                splineIndex,
                positions,
                rotations,
                tangentIn,
                tangentOut,
                knotIndices,
                splineIndices);
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
            if (!TrackSplineCoordinateUtility.IsFinite(position) ||
                !TrackSplineCoordinateUtility.IsFinite(rotation) ||
                !TrackSplineCoordinateUtility.IsFinite(inHandle) ||
                !TrackSplineCoordinateUtility.IsFinite(outHandle))
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
                if (!TrackSplineCoordinateUtility.IsFinite(positions[pointIndex * 3 + component]) ||
                    !TrackSplineCoordinateUtility.IsFinite(tangentIn[pointIndex * 3 + component]) ||
                    !TrackSplineCoordinateUtility.IsFinite(tangentOut[pointIndex * 3 + component]))
                {
                    return false;
                }
            }

            for (int component = 0; component < 4; component++)
            {
                if (!TrackSplineCoordinateUtility.IsFinite(rotations[pointIndex * 4 + component]))
                    return false;
            }

            return true;
        }
    }

    internal static class TrackSplineCoordinateUtility
    {
        public static Quaternion BuildUploadedRotation(
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

            if (!IsFinite(uploadedTangent) || uploadedTangent.sqrMagnitude <= 1e-10f)
                uploadedTangent = Vector3.forward;
            uploadedTangent.Normalize();

            uploadedUp = Vector3.ProjectOnPlane(uploadedUp, uploadedTangent);
            if (!IsFinite(uploadedUp) || uploadedUp.sqrMagnitude <= 1e-10f)
            {
                Vector3 fallbackAxis =
                    Mathf.Abs(Vector3.Dot(uploadedTangent, Vector3.up)) < 0.999f
                        ? Vector3.up
                        : Vector3.right;
                uploadedUp = Vector3.ProjectOnPlane(fallbackAxis, uploadedTangent);
            }
            uploadedUp.Normalize();

            return Quaternion.LookRotation(uploadedTangent, uploadedUp);
        }

        public static Quaternion ToNormalizedUnityRotation(quaternion rotation)
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

        public static bool IsFinite(Vector3 value)
        {
            return IsFinite(value.x) && IsFinite(value.y) && IsFinite(value.z);
        }

        public static bool IsFinite(Quaternion value)
        {
            return IsFinite(value.x) && IsFinite(value.y) &&
                   IsFinite(value.z) && IsFinite(value.w);
        }

        public static bool IsFinite(float value)
        {
            return !float.IsNaN(value) && !float.IsInfinity(value);
        }
    }
}
