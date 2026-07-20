using HoudiniEngineUnity;
using UnityEngine;
using UnityEngine.Scripting.APIUpdating;

namespace PCGBike.Terrain.Authoring
{
    /// <summary>
    /// Editor-only bridge from a Track HDA Display SOP to the Terrain HDA.
    /// Player builds have no polling, Houdini cook, or runtime cost.
    /// </summary>
    [MovedFrom(true, "PCGBike.Authoring", "Assembly-CSharp", "TerrainTrackDisplayBinding")]
    [ExecuteAlways]
    [DisallowMultipleComponent]
    [AddComponentMenu("PCG Bike/Terrain/Track Display SOP Binding")]
    public sealed class TerrainTrackDisplaySopBinding : MonoBehaviour
    {
        private const string PathParameter = "track_display_sop_path";
        private const double RetryTimeout = 15.0;
        private const double RetryInterval = 0.25;

#if UNITY_EDITOR
        [Header("Houdini Assets")]
        [SerializeField] private HEU_HoudiniAssetRoot _trackAssetRoot;
        [SerializeField] private HEU_HoudiniAssetRoot _terrainAssetRoot;
        [Header("Editor Cook")]
        [SerializeField] private bool _autoCookTerrain = true;
        [SerializeField, HideInInspector] private string _lastBoundPath = string.Empty;

        private HEU_HoudiniAsset _subscribedTrack;
        private HEU_HoudiniAsset _subscribedTerrain;
        private double _nextAttempt = -1.0;
        private double _deadline = -1.0;
        private bool _terrainReloadRequested;
        private bool _binding;
        private bool _warned;
        private string _status = "Idle";

        public HEU_HoudiniAssetRoot TrackAssetRoot => _trackAssetRoot;
        public HEU_HoudiniAssetRoot TerrainAssetRoot => _terrainAssetRoot;
        public string LastBoundPath => _lastBoundPath;
        public string LastBindingStatus => _status;

        private void Reset()
        {
            _terrainAssetRoot = GetComponent<HEU_HoudiniAssetRoot>();
        }

        private void OnEnable()
        {
            BindTerrainReference();
            RefreshSubscriptions();
            Schedule(0.0, true);
        }

        private void OnDisable()
        {
            Unsubscribe();
            UnityEditor.EditorApplication.update -= Pump;
            _nextAttempt = _deadline = -1.0;
            _terrainReloadRequested = _binding = false;
        }

        private void OnValidate()
        {
            BindTerrainReference();
            RefreshSubscriptions();
            if (isActiveAndEnabled && !UnityEditor.EditorApplication.isPlayingOrWillChangePlaymode)
                Schedule(0.0, true);
        }

        private void BindTerrainReference()
        {
            if (_terrainAssetRoot == null)
                _terrainAssetRoot = GetComponent<HEU_HoudiniAssetRoot>();
        }

        private void RefreshSubscriptions()
        {
            HEU_HoudiniAsset track = _trackAssetRoot != null ? _trackAssetRoot.HoudiniAsset : null;
            HEU_HoudiniAsset terrain = _terrainAssetRoot != null ? _terrainAssetRoot.HoudiniAsset : null;
            if (ReferenceEquals(track, _subscribedTrack) && ReferenceEquals(terrain, _subscribedTerrain))
                return;

            Unsubscribe();
            _subscribedTrack = track;
            _subscribedTerrain = terrain;

            if (_subscribedTrack != null)
            {
                _subscribedTrack.CookedDataEvent.RemoveListener(OnTrackCooked);
                _subscribedTrack.CookedDataEvent.AddListener(OnTrackCooked);
                _subscribedTrack.ReloadDataEvent.RemoveListener(OnTrackReloaded);
                _subscribedTrack.ReloadDataEvent.AddListener(OnTrackReloaded);
            }

            if (_subscribedTerrain != null)
            {
                _subscribedTerrain.ReloadDataEvent.RemoveListener(OnTerrainReloaded);
                _subscribedTerrain.ReloadDataEvent.AddListener(OnTerrainReloaded);
            }
        }

        private void Unsubscribe()
        {
            if (_subscribedTrack != null)
            {
                _subscribedTrack.CookedDataEvent.RemoveListener(OnTrackCooked);
                _subscribedTrack.ReloadDataEvent.RemoveListener(OnTrackReloaded);
            }
            if (_subscribedTerrain != null)
                _subscribedTerrain.ReloadDataEvent.RemoveListener(OnTerrainReloaded);
            _subscribedTrack = null;
            _subscribedTerrain = null;
        }

        private void OnTrackCooked(HEU_CookedEventData data)
        {
            if (data != null && data.CookSuccess)
                Schedule(0.0, true);
        }

        private void OnTrackReloaded(HEU_ReloadEventData data)
        {
            Schedule(0.0, true);
        }

        private void OnTerrainReloaded(HEU_ReloadEventData data)
        {
            _terrainReloadRequested = false;
            Schedule(0.0, true);
        }

        private void Schedule(double delay, bool resetDeadline)
        {
            if (!isActiveAndEnabled || UnityEditor.EditorApplication.isPlayingOrWillChangePlaymode)
                return;

            double now = UnityEditor.EditorApplication.timeSinceStartup;
            _nextAttempt = now + delay;
            if (resetDeadline || _deadline < now)
                _deadline = now + RetryTimeout;
            UnityEditor.EditorApplication.update -= Pump;
            UnityEditor.EditorApplication.update += Pump;
        }

        private void Pump()
        {
            if (this == null || !isActiveAndEnabled)
            {
                Cancel();
                return;
            }

            if (UnityEditor.EditorApplication.isCompiling ||
                UnityEditor.EditorApplication.isUpdating ||
                UnityEditor.EditorApplication.isPlayingOrWillChangePlaymode)
                return;

            double now = UnityEditor.EditorApplication.timeSinceStartup;
            if (now < _nextAttempt)
                return;

            BindTerrainReference();
            RefreshSubscriptions();
            if (TryBind())
            {
                Cancel();
                return;
            }

            TryRequestTerrainReload();
            if (now < _deadline)
            {
                _nextAttempt = now + RetryInterval;
                return;
            }

            ClearStalePath();
            Cancel();
            if (!_warned)
            {
                _warned = true;
                Debug.LogWarning(
                    "Terrain Track Display binding could not resolve a valid Track Display SOP " +
                    "within 15 seconds. The hidden Terrain path was cleared to prevent stale geometry.",
                    this);
            }
        }

        private bool TryBind()
        {
            if (_binding)
                return false;

            HEU_HoudiniAsset track = _trackAssetRoot != null ? _trackAssetRoot.HoudiniAsset : null;
            HEU_HoudiniAsset terrain = _terrainAssetRoot != null ? _terrainAssetRoot.HoudiniAsset : null;
            HEU_SessionBase session = HEU_SessionManager.GetDefaultSession();

            if (session == null || !session.IsSessionValid() ||
                track == null || terrain == null ||
                track.AssetID == HEU_Defines.HEU_INVALID_NODE_ID ||
                terrain.AssetID == HEU_Defines.HEU_INVALID_NODE_ID)
            {
                _status = "Waiting for a valid Houdini session, Track asset, and Terrain asset.";
                return false;
            }

            HAPI_GeoInfo geoInfo = new HAPI_GeoInfo();
            if (!session.GetDisplayGeoInfo(track.AssetID, ref geoInfo, false) ||
                geoInfo.nodeId == HEU_Defines.HEU_INVALID_NODE_ID ||
                !session.GetNodePath(
                    geoInfo.nodeId,
                    HEU_Defines.HEU_INVALID_NODE_ID,
                    out string displayPath) ||
                string.IsNullOrWhiteSpace(displayPath))
            {
                _status = "Track Display SOP is not available yet.";
                return false;
            }

            if (!TryGetTerrainPath(session, terrain, out string currentPath))
            {
                _status = "Unable to read the Terrain Track Display SOP path parameter.";
                return false;
            }

            if (string.Equals(currentPath, displayPath, System.StringComparison.Ordinal))
            {
                _lastBoundPath = displayPath;
                _status = "Track Display SOP is already bound; no Terrain cook requested.";
                _warned = _terrainReloadRequested = false;
                return true;
            }

            _binding = true;
            try
            {
                if (!session.SetParamStringValue(
                        terrain.AssetID, PathParameter, displayPath, 0))
                {
                    _status = "Failed to write the Terrain Track Display SOP path.";
                    return false;
                }

                bool accepted = !_autoCookTerrain || terrain.RequestCook(
                    bCheckParametersChanged: false,
                    bAsync: true,
                    bSkipCookCheck: false,
                    bUploadParameters: true);
                if (!accepted)
                {
                    _status = "Terrain rejected the binding cook request.";
                    return false;
                }

                _lastBoundPath = displayPath;
                _status = _autoCookTerrain
                    ? "Track path bound; Terrain cook requested."
                    : "Track path bound; auto-cook disabled.";
                _warned = _terrainReloadRequested = false;
                UnityEditor.EditorUtility.SetDirty(this);
                return true;
            }
            finally
            {
                _binding = false;
            }
        }

        private void TryRequestTerrainReload()
        {
            HEU_HoudiniAsset terrain = _terrainAssetRoot != null ? _terrainAssetRoot.HoudiniAsset : null;
            HEU_SessionBase session = HEU_SessionManager.GetDefaultSession();

            int hiddenParmId;
            bool terrainNeedsReload = terrain != null &&
                (terrain.AssetID == HEU_Defines.HEU_INVALID_NODE_ID ||
                 session == null || !session.IsSessionValid() ||
                 !session.GetParmIDFromName(terrain.AssetID, PathParameter, out hiddenParmId));
            if (!_terrainReloadRequested && terrainNeedsReload)
                _terrainReloadRequested = terrain.RequestReload(bAsync: true);
        }

        private void ClearStalePath()
        {
            HEU_HoudiniAsset terrain = _terrainAssetRoot != null ? _terrainAssetRoot.HoudiniAsset : null;
            HEU_SessionBase session = HEU_SessionManager.GetDefaultSession();
            if (terrain == null || session == null || !session.IsSessionValid() ||
                terrain.AssetID == HEU_Defines.HEU_INVALID_NODE_ID)
            {
                _lastBoundPath = string.Empty;
                _status = "Waiting for a valid Terrain asset and Houdini session.";
                return;
            }

            if (!TryGetTerrainPath(session, terrain, out string current) ||
                string.IsNullOrEmpty(current))
            {
                _lastBoundPath = string.Empty;
                _status = "Terrain Track Display SOP path is already empty.";
                return;
            }

            if (!session.SetParamStringValue(
                    terrain.AssetID, PathParameter, string.Empty, 0))
                return;

            _lastBoundPath = string.Empty;
            _status = "Cleared the stale Terrain Track Display SOP path.";
            UnityEditor.EditorUtility.SetDirty(this);
            if (_autoCookTerrain)
            {
                terrain.RequestCook(
                    bCheckParametersChanged: false,
                    bAsync: true,
                    bSkipCookCheck: false,
                    bUploadParameters: true);
            }
        }

        private void Cancel()
        {
            UnityEditor.EditorApplication.update -= Pump;
            _nextAttempt = _deadline = -1.0;
            _terrainReloadRequested = false;
        }

        private static bool TryGetTerrainPath(
            HEU_SessionBase session,
            HEU_HoudiniAsset terrain,
            out string path)
        {
            path = string.Empty;
            if (!session.GetParmStringValue(
                    terrain.AssetID, PathParameter, 0, true, out int stringHandle))
                return false;

            path = HEU_SessionManager.GetString(stringHandle, session) ?? string.Empty;
            return true;
        }

        [ContextMenu("Rebind Track Display SOP Now")]
        public void RebindNow()
        {
            if (!Application.isPlaying)
                Schedule(0.0, true);
        }
#endif
    }
}
