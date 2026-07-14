using HoudiniEngineUnity;
using UnityEngine;
using UnityEngine.Splines;

namespace PCGBike.Authoring
{
    /// <summary>
    /// Editor-only authoring bridge that re-uploads a bound Unity Spline after knot edits.
    /// It has no Update loop and performs no Houdini work in player builds.
    /// </summary>
    [ExecuteAlways]
    [DisallowMultipleComponent]
    public sealed class TrackSplineHoudiniSync : MonoBehaviour
    {
        private const string CurveInputParameter = "unity_curve_input";
        private const double ReloadTimeoutSeconds = 15.0;

        [SerializeField] private SplineContainer _splineContainer;
        [SerializeField] private HEU_HoudiniAssetRoot _trackAssetRoot;
        [SerializeField] private bool _autoCookOnSplineChanged = true;
        [SerializeField, Min(0.05f)] private float _cookDebounceSeconds = 0.35f;

#if UNITY_EDITOR
        private double _scheduledCookTime = -1.0;
        private double _reloadDeadline = -1.0;
        private bool _reloadRequested;
        private bool _warnedOfficialFallback;

        private void Reset()
        {
            BindReferences();
        }

        private void OnValidate()
        {
            _cookDebounceSeconds = Mathf.Max(0.05f, _cookDebounceSeconds);
            BindReferences();
        }

        private void OnEnable()
        {
            BindReferences();
            Spline.Changed -= OnSplineChanged;
            Spline.Changed += OnSplineChanged;
        }

        private void OnDisable()
        {
            Spline.Changed -= OnSplineChanged;
            UnityEditor.EditorApplication.update -= PumpScheduledCook;
            _scheduledCookTime = -1.0;
            _reloadRequested = false;
            _warnedOfficialFallback = false;
        }

        private void BindReferences()
        {
            if (_trackAssetRoot == null)
                _trackAssetRoot = GetComponent<HEU_HoudiniAssetRoot>();

            if (_splineContainer != null || _trackAssetRoot == null || _trackAssetRoot.HoudiniAsset == null)
                return;

            if (_trackAssetRoot.HoudiniAsset.Parameters.GetAssetRefParameterValue(
                    CurveInputParameter, out GameObject inputObject) && inputObject != null)
            {
                _splineContainer = inputObject.GetComponent<SplineContainer>();
            }
        }

        private void OnSplineChanged(Spline changedSpline, int knotIndex, SplineModification modification)
        {
            if (!_autoCookOnSplineChanged || !isActiveAndEnabled || !ContainsSpline(changedSpline))
                return;

            ScheduleCook(_cookDebounceSeconds);
        }

        private bool ContainsSpline(Spline candidate)
        {
            if (_splineContainer == null || candidate == null)
                return false;

            foreach (Spline spline in _splineContainer.Splines)
            {
                if (ReferenceEquals(spline, candidate))
                    return true;
            }
            return false;
        }

        private void ScheduleCook(double delaySeconds)
        {
            _scheduledCookTime = UnityEditor.EditorApplication.timeSinceStartup + delaySeconds;
            UnityEditor.EditorApplication.update -= PumpScheduledCook;
            UnityEditor.EditorApplication.update += PumpScheduledCook;
        }

        private void PumpScheduledCook()
        {
            if (this == null || !_autoCookOnSplineChanged || !isActiveAndEnabled)
            {
                UnityEditor.EditorApplication.update -= PumpScheduledCook;
                return;
            }

            if (UnityEditor.EditorApplication.isCompiling || UnityEditor.EditorApplication.isPlayingOrWillChangePlaymode)
                return;

            double now = UnityEditor.EditorApplication.timeSinceStartup;
            if (now < _scheduledCookTime)
                return;

            BindReferences();
            HEU_HoudiniAsset asset = _trackAssetRoot != null ? _trackAssetRoot.HoudiniAsset : null;
            if (asset == null || _splineContainer == null)
            {
                CancelScheduledCook();
                Debug.LogWarning("Track spline auto-cook skipped because the HDA or Spline binding is missing.", this);
                return;
            }

            ValidateSplineInputMode();

            HEU_SessionBase session = HEU_SessionManager.GetDefaultSession();
            bool assetReady =
                session != null &&
                session.IsSessionValid() &&
                asset.AssetID != HEU_Defines.HEU_INVALID_NODE_ID;
            if (!assetReady)
            {
                if (!_reloadRequested)
                {
                    _reloadRequested = asset.RequestReload(bAsync: true);
                    _reloadDeadline = now + ReloadTimeoutSeconds;
                }

                if (!_reloadRequested || now >= _reloadDeadline)
                {
                    CancelScheduledCook();
                    Debug.LogWarning("Track spline auto-cook could not reload the Houdini asset within 15 seconds.", this);
                    return;
                }

                _scheduledCookTime = now + 0.25;
                return;
            }

            _reloadRequested = false;
            bool inputUpdated = asset.Parameters.SetAssetRefParameterValue(
                CurveInputParameter, _splineContainer.gameObject, 0, bRecookAsset: false);
            bool cookRequested = inputUpdated && asset.RequestCook(
                bCheckParametersChanged: false,
                bAsync: true,
                bSkipCookCheck: false,
                bUploadParameters: true);

            CancelScheduledCook();
            if (!cookRequested)
                Debug.LogWarning("Track spline changed, but Houdini rejected the re-upload/cook request.", this);
        }

        private void ValidateSplineInputMode()
        {
            TrackSplineHoudiniInputSettings inputSettings =
                _splineContainer.GetComponent<TrackSplineHoudiniInputSettings>();
            bool usesCustomInterface =
                inputSettings != null && inputSettings.UsesCustomInterface;
            if (usesCustomInterface)
            {
                _warnedOfficialFallback = false;
                return;
            }

            if (_warnedOfficialFallback)
                return;

            _warnedOfficialFallback = true;
            Debug.LogWarning(
                "The bound Track Spline does not have an enabled " +
                "TrackSplineHoudiniInputSettings marker. Houdini Engine will use " +
                "its official fallback interface and authored Knot Rotation will not " +
                "be uploaded by the PCG Track interface.",
                _splineContainer);
        }

        private void CancelScheduledCook()
        {
            UnityEditor.EditorApplication.update -= PumpScheduledCook;
            _scheduledCookTime = -1.0;
            _reloadRequested = false;
            _reloadDeadline = -1.0;
        }

        [ContextMenu("Cook Bound Spline Now")]
        private void CookBoundSplineNow()
        {
            if (!Application.isPlaying)
                ScheduleCook(0.0);
        }
#endif
    }
}