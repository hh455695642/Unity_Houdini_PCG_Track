using UnityEngine;
using UnityEngine.Serialization;
using UnityEngine.Splines;

namespace PCGBike.Authoring
{
    /// <summary>
    /// Marks a Unity SplineContainer for the PCG Track Houdini input interface.
    /// This component stores editor-authoring data only and has no per-frame work.
    /// </summary>
    [DisallowMultipleComponent]
    [AddComponentMenu("PCG Bike/Track Spline Houdini Input Settings")]
    public sealed class TrackSplineHoudiniInputSettings : MonoBehaviour
    {
        [FormerlySerializedAs("_enableRotationUpload")]
        public bool EnableKnotDataUpload = true;

        // Migration-only data. It is intentionally not consumed by Knot Contract V1;
        // sample_spacing on the Track HDA is now the only production sampling control.
        [FormerlySerializedAs("_samplingResolution")]
        [SerializeField, HideInInspector]
        private float _legacySamplingResolution = 25.0f;

#if UNITY_EDITOR
        [SerializeField, HideInInspector] private int _lastUploadedSplineCount;
        [SerializeField, HideInInspector] private int _lastUploadedKnotCount;
        [SerializeField, HideInInspector] private string _lastUploadedClosedState = "Not uploaded";
        [SerializeField, HideInInspector] private string _lastUploadValidation = "Not uploaded in this editor domain.";
#endif

        /// <summary>
        /// When false, Houdini Engine falls back to its official Spline input interface.
        /// </summary>
        /// <summary>True when this object uses PCG Knot Contract V1.</summary>
        public bool UsesCustomInterface =>
            isActiveAndEnabled &&
            EnableKnotDataUpload &&
            GetComponent<SplineContainer>() != null;

        /// <summary>
        /// Lightweight inspector/debug status. Not used by runtime rendering.
        /// </summary>
        public string UploadMode => UsesCustomInterface
            ? "PCG Knot Contract V1"
            : "Official Houdini Engine Fallback";

#if UNITY_EDITOR
        public int LastUploadedSplineCount => _lastUploadedSplineCount;
        public int LastUploadedKnotCount => _lastUploadedKnotCount;
        public string LastUploadedClosedState => _lastUploadedClosedState;
        public string LastUploadValidation => _lastUploadValidation;

        public void SetEditorUploadValidation(
            bool success,
            string message,
            int splineCount,
            int knotCount,
            string closedState)
        {
            _lastUploadedSplineCount = Mathf.Max(0, splineCount);
            _lastUploadedKnotCount = Mathf.Max(0, knotCount);
            _lastUploadedClosedState = string.IsNullOrEmpty(closedState) ? "Unknown" : closedState;
            _lastUploadValidation = (success ? "Valid: " : "Invalid: ") + message;
        }

        private void OnValidate()
        {
            if (!IsFinite(_legacySamplingResolution) || _legacySamplingResolution < 0.0f)
                _legacySamplingResolution = 25.0f;
        }
#endif

        private static bool IsFinite(float value)
        {
            return !float.IsNaN(value) && !float.IsInfinity(value);
        }
    }
}
