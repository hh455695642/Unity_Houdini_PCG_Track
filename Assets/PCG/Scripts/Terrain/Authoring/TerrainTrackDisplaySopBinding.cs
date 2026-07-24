using HoudiniEngineUnity;
using UnityEngine;
using UnityEngine.Scripting.APIUpdating;

namespace PCGBike.Terrain.Authoring
{
    public enum TerrainTrackBindingState
    {
        Detached,
        WaitingForSession,
        Bound,
        CookPending,
        Error
    }

    /// <summary>
    /// Editor-only bridge from the current Track HDA Display SOP to Working Terrain.
    /// Disabling/removing this component is an explicit detach-and-restore operation.
    /// Player builds have no polling, Houdini cook, or runtime cost.
    /// </summary>
    [MovedFrom(true, "PCGBike.Authoring", "Assembly-CSharp", "TerrainTrackDisplayBinding")]
    [ExecuteAlways]
    [DisallowMultipleComponent]
    [AddComponentMenu("PCG Bike/Terrain/Track Display SOP Binding")]
    public sealed class TerrainTrackDisplaySopBinding : MonoBehaviour
    {
#if UNITY_EDITOR
        internal const string PathParameter = "track_display_sop_path";
        internal const string EnabledParameter = "track_binding_enabled";

        private const double RetryInterval = 0.25;
        private const double CookRequestRecoveryDelay = 0.75;
        private static readonly System.Reflection.FieldInfo RequestBuildActionField =
            typeof(HEU_HoudiniAsset).GetField(
                "_requestBuildAction",
                System.Reflection.BindingFlags.Instance |
                System.Reflection.BindingFlags.NonPublic);

        [Header("Houdini Assets")]
        [SerializeField] private HEU_HoudiniAssetRoot _trackAssetRoot;
        [SerializeField] private HEU_HoudiniAssetRoot _terrainAssetRoot;
        [Header("Editor Cook")]
        [SerializeField] private bool _autoCookTerrain = true;

        [SerializeField, HideInInspector] private string _lastBoundPath = string.Empty;
        [SerializeField, HideInInspector] private TerrainTrackBindingState _bindingState;
        [SerializeField, HideInInspector] private string _lastBindingStatus = "Detached.";
        [SerializeField, HideInInspector] private string _lastCookSummary = "No Terrain cook requested.";
        [SerializeField, HideInInspector] private bool _pendingDetach;
        [SerializeField, HideInInspector] private bool _manualDetach;

        private HEU_HoudiniAsset _subscribedTrack;
        private HEU_HoudiniAsset _subscribedTerrain;
        private double _nextAttempt = -1.0;
        private bool _terrainReloadRequested;
        private bool _pendingCook;
        private bool _cookRequestIssued;
        private bool _cookAfterCurrent;
        private double _cookRequestIssuedAt = -1.0;
        private bool _forceRebind;
        private bool _forceRestoreCook;
        private bool _processing;
        private bool _destroying;

        public HEU_HoudiniAssetRoot TrackAssetRoot => _trackAssetRoot;
        public HEU_HoudiniAssetRoot TerrainAssetRoot => _terrainAssetRoot;
        public string LastBoundPath => _lastBoundPath;
        public TerrainTrackBindingState BindingState => _bindingState;
        public bool HasPendingCook => _pendingCook || _cookRequestIssued || _cookAfterCurrent;
        public string LastBindingStatus => _lastBindingStatus;
        public string LastCookSummary => _lastCookSummary;
#else
        public TerrainTrackBindingState BindingState => TerrainTrackBindingState.Detached;
        public bool HasPendingCook => false;
        public string LastBindingStatus => "Houdini binding is editor-only.";
#endif

#if UNITY_EDITOR
        private void Reset()
        {
            _terrainAssetRoot = GetComponent<HEU_HoudiniAssetRoot>();
            SetState(TerrainTrackBindingState.Detached, "Detached; base terrain is authoritative.");
        }

        private void OnEnable()
        {
            if (UnityEditor.EditorApplication.isPlayingOrWillChangePlaymode)
                return;

            BindTerrainReference();
            RefreshSubscriptions();
            SubscribeEditorEvents();
            // A detach interrupted by a session/reload always wins over rebind.
            Schedule(0.0);
        }

        private void OnDisable()
        {
            if (_destroying || UnityEditor.EditorApplication.isPlayingOrWillChangePlaymode)
                return;

            _pendingDetach = true;
            _forceRestoreCook = true;
            SetState(
                TerrainTrackBindingState.WaitingForSession,
                "Component disabled: detaching Track and restoring base terrain.");
            RefreshSubscriptions();
            SubscribeEditorEvents();
            Schedule(0.0, allowDisabled: true);
        }

        private void OnDestroy()
        {
            if (UnityEditor.EditorApplication.isPlayingOrWillChangePlaymode)
                return;

            _destroying = true;
            BindTerrainReference();
            TryDetachAndQueueCook(forceCook: true);
            // The component cannot receive the eventual cook event after it is
            // destroyed, so a short-lived editor queue owns the final base cook.
            if (_terrainAssetRoot != null)
                TerrainTrackDetachRecovery.Enqueue(_terrainAssetRoot);
            Cleanup();
        }

        private void OnValidate()
        {
            if (UnityEditor.EditorApplication.isPlayingOrWillChangePlaymode)
                return;

            BindTerrainReference();
            RefreshSubscriptions();
            SubscribeEditorEvents();
            if (isActiveAndEnabled)
                Schedule(0.0);
        }

        private void BindTerrainReference()
        {
            if (_terrainAssetRoot == null)
                _terrainAssetRoot = GetComponent<HEU_HoudiniAssetRoot>();
        }

        private void SubscribeEditorEvents()
        {
            UnityEditor.EditorApplication.hierarchyChanged -= OnHierarchyChanged;
            UnityEditor.EditorApplication.hierarchyChanged += OnHierarchyChanged;
            UnityEditor.Undo.undoRedoPerformed -= OnUndoRedo;
            UnityEditor.Undo.undoRedoPerformed += OnUndoRedo;
        }

        private void RefreshSubscriptions()
        {
            HEU_HoudiniAsset track = GetAsset(_trackAssetRoot);
            HEU_HoudiniAsset terrain = GetAsset(_terrainAssetRoot);
            if (ReferenceEquals(track, _subscribedTrack) &&
                ReferenceEquals(terrain, _subscribedTerrain))
            {
                return;
            }

            UnsubscribeAssetEvents();
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
                _subscribedTerrain.CookedDataEvent.RemoveListener(OnTerrainCooked);
                _subscribedTerrain.CookedDataEvent.AddListener(OnTerrainCooked);
                _subscribedTerrain.ReloadDataEvent.RemoveListener(OnTerrainReloaded);
                _subscribedTerrain.ReloadDataEvent.AddListener(OnTerrainReloaded);
            }
        }

        private void UnsubscribeAssetEvents()
        {
            if (_subscribedTrack != null)
            {
                _subscribedTrack.CookedDataEvent.RemoveListener(OnTrackCooked);
                _subscribedTrack.ReloadDataEvent.RemoveListener(OnTrackReloaded);
            }

            if (_subscribedTerrain != null)
            {
                _subscribedTerrain.CookedDataEvent.RemoveListener(OnTerrainCooked);
                _subscribedTerrain.ReloadDataEvent.RemoveListener(OnTerrainReloaded);
            }

            _subscribedTrack = null;
            _subscribedTerrain = null;
        }

        private void OnTrackCooked(HEU_CookedEventData data)
        {
            if (data != null && data.CookSuccess)
            {
                _forceRebind = true;
                Schedule(0.0);
            }
            else
            {
                _pendingDetach = true;
                SetState(TerrainTrackBindingState.Error, "Track cook failed; Track influence is being detached.");
                Schedule(0.0);
            }
        }

        private void OnTrackReloaded(HEU_ReloadEventData data)
        {
            _forceRebind = true;
            Schedule(0.0);
        }

        private void OnTerrainCooked(HEU_CookedEventData data)
        {
            _cookRequestIssued = false;
            _cookRequestIssuedAt = -1.0;
            if (_cookAfterCurrent)
            {
                _cookAfterCurrent = false;
                _pendingCook = true;
            }
            else
            {
                _pendingCook = false;
            }

            bool success = data != null && data.CookSuccess;
            _lastCookSummary = success
                ? "Terrain cook completed successfully."
                : "Terrain cook failed; inspect Houdini Engine and Unity Console.";

            if (!success)
                SetState(TerrainTrackBindingState.Error, _lastCookSummary);
            else if (!_pendingCook)
                SetStableState();

            Schedule(0.0, allowDisabled: _pendingDetach || !isActiveAndEnabled);
        }

        private void OnTerrainReloaded(HEU_ReloadEventData data)
        {
            _terrainReloadRequested = false;
            // A cook request made while reload owned the asset may have been rejected.
            _cookRequestIssued = false;
            _cookRequestIssuedAt = -1.0;
            RefreshSubscriptions();
            Schedule(0.0, allowDisabled: _pendingDetach || !isActiveAndEnabled);
        }

        private void OnHierarchyChanged()
        {
            if (isActiveAndEnabled)
                Schedule(0.0);
        }

        private void OnUndoRedo()
        {
            if (isActiveAndEnabled)
                Schedule(0.0);
        }

        private void Schedule(double delay, bool allowDisabled = false)
        {
            if (_destroying ||
                UnityEditor.EditorApplication.isPlayingOrWillChangePlaymode ||
                (!allowDisabled && !isActiveAndEnabled))
            {
                return;
            }

            double now = UnityEditor.EditorApplication.timeSinceStartup;
            double requested = now + delay;
            _nextAttempt = _nextAttempt < 0.0
                ? requested
                : System.Math.Min(_nextAttempt, requested);
            UnityEditor.EditorApplication.update -= Pump;
            UnityEditor.EditorApplication.update += Pump;
        }

        private void Pump()
        {
            if (this == null || _destroying)
            {
                Cleanup();
                return;
            }

            if (UnityEditor.EditorApplication.isCompiling ||
                UnityEditor.EditorApplication.isUpdating ||
                UnityEditor.EditorApplication.isPlayingOrWillChangePlaymode)
            {
                return;
            }

            double now = UnityEditor.EditorApplication.timeSinceStartup;
            if (_nextAttempt >= 0.0 && now < _nextAttempt)
                return;
            _nextAttempt = -1.0;

            BindTerrainReference();
            RefreshSubscriptions();

            bool stateReady;
            if (_pendingDetach || _manualDetach || !isActiveAndEnabled)
            {
                stateReady = TryDetachAndQueueCook(_forceRestoreCook);
                _forceRestoreCook = false;
            }
            else
            {
                stateReady = TryBindCurrentTrack();
            }

            bool cookReady = TrySubmitPendingCook();
            if (!stateReady || !cookReady || HasPendingCook)
            {
                Schedule(RetryInterval, allowDisabled: _pendingDetach || !isActiveAndEnabled);
                return;
            }

            UnityEditor.EditorApplication.update -= Pump;
            if (!isActiveAndEnabled)
            {
                UnsubscribeAssetEvents();
                UnityEditor.EditorApplication.hierarchyChanged -= OnHierarchyChanged;
                UnityEditor.Undo.undoRedoPerformed -= OnUndoRedo;
            }
        }

        private bool TryBindCurrentTrack()
        {
            if (_processing)
                return false;

            HEU_HoudiniAsset terrain = GetAsset(_terrainAssetRoot);
            HEU_SessionBase session = HEU_SessionManager.GetDefaultSession();
            if (!TryGetValidTerrain(session, terrain))
            {
                SetState(
                    TerrainTrackBindingState.WaitingForSession,
                    "Waiting for a valid Houdini session and Terrain asset.");
                TryRequestTerrainReload();
                return false;
            }

            HEU_HoudiniAsset track = GetAsset(_trackAssetRoot);
            if (!IsTrackSourceUsable(track))
            {
                _pendingDetach = true;
                _forceRestoreCook = false;
                return TryDetachAndQueueCook(forceCook: false);
            }

            if (!HasBindingParameters(session, terrain))
            {
                SetState(
                    TerrainTrackBindingState.WaitingForSession,
                    "Terrain HDA is reloading the internal Track binding contract.");
                TryRequestTerrainReload();
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
                // Fail closed while Track reload/cook has no valid Display SOP.
                _pendingDetach = true;
                SetState(
                    TerrainTrackBindingState.WaitingForSession,
                    "Track Display SOP is unavailable; restoring base terrain while waiting.");
                return TryDetachAndQueueCook(forceCook: false);
            }

            if (!TryGetTerrainPath(session, terrain, out string currentPath) ||
                !session.GetParamIntValue(terrain.AssetID, EnabledParameter, 0, out int enabled))
            {
                SetState(TerrainTrackBindingState.Error, "Unable to read Terrain Track binding parameters.");
                return false;
            }

            bool changed = enabled == 0 ||
                !string.Equals(currentPath, displayPath, System.StringComparison.Ordinal);
            _processing = true;
            try
            {
                if (changed &&
                    (!session.SetParamStringValue(terrain.AssetID, PathParameter, displayPath, 0) ||
                     !session.SetParamIntValue(terrain.AssetID, EnabledParameter, 0, 1)))
                {
                    SetState(TerrainTrackBindingState.Error, "Failed to write Terrain Track binding parameters.");
                    return false;
                }
            }
            finally
            {
                _processing = false;
            }

            _pendingDetach = false;
            _lastBoundPath = displayPath;
            if (changed || _forceRebind)
                QueueCook(changed ? "Track binding changed." : "Track recooked; rebuilding Terrain once.");
            _forceRebind = false;

            if (!HasPendingCook)
            {
                SetState(
                    TerrainTrackBindingState.Bound,
                    "Bound to the current Track Display SOP.");
            }
            UnityEditor.EditorUtility.SetDirty(this);
            return true;
        }

        private bool TryDetachAndQueueCook(bool forceCook)
        {
            if (_processing)
                return false;

            HEU_HoudiniAsset terrain = GetAsset(_terrainAssetRoot);
            HEU_SessionBase session = HEU_SessionManager.GetDefaultSession();
            if (!TryGetValidTerrain(session, terrain))
            {
                _pendingDetach = true;
                SetState(
                    TerrainTrackBindingState.WaitingForSession,
                    "Detach pending: waiting for a valid Houdini session and Terrain asset.");
                return false;
            }

            if (!HasBindingParameters(session, terrain))
            {
                _pendingDetach = true;
                SetState(
                    TerrainTrackBindingState.WaitingForSession,
                    "Detach pending: Terrain HDA is reloading the binding contract.");
                TryRequestTerrainReload();
                return false;
            }

            if (!session.GetParamIntValue(
                    terrain.AssetID, EnabledParameter, 0, out int enabled) ||
                !TryGetTerrainPath(session, terrain, out string currentPath))
            {
                _pendingDetach = true;
                SetState(TerrainTrackBindingState.Error, "Failed to read Terrain binding before detach.");
                return false;
            }

            bool changed = enabled != 0 || !string.IsNullOrEmpty(currentPath);
            _processing = true;
            try
            {
                // Order is intentional: old Display SOP becomes inert before its path is cleared.
                if (enabled != 0 &&
                    !session.SetParamIntValue(terrain.AssetID, EnabledParameter, 0, 0))
                {
                    _pendingDetach = true;
                    SetState(TerrainTrackBindingState.Error, "Failed to disable Terrain Track binding.");
                    return false;
                }

                if (!string.IsNullOrEmpty(currentPath) &&
                    !session.SetParamStringValue(terrain.AssetID, PathParameter, string.Empty, 0))
                {
                    _pendingDetach = true;
                    SetState(TerrainTrackBindingState.Error, "Track influence was disabled, but its debug path could not be cleared.");
                    return false;
                }
            }
            finally
            {
                _processing = false;
            }

            _pendingDetach = false;
            _lastBoundPath = string.Empty;
            if (changed || forceCook)
                QueueCook("Track detached; restoring base terrain.");

            if (!HasPendingCook)
            {
                SetState(
                    TerrainTrackBindingState.Detached,
                    "Detached; Working Terrain uses its base heightfield.");
            }
            UnityEditor.EditorUtility.SetDirty(this);
            return true;
        }

        private void QueueCook(string reason)
        {
            if (!_autoCookTerrain)
            {
                _pendingCook = _cookRequestIssued = _cookAfterCurrent = false;
                _lastCookSummary = reason + " Auto Cook is disabled.";
                SetStableState();
                return;
            }

            if (_cookRequestIssued)
                _cookAfterCurrent = true;
            _pendingCook = true;
            _lastCookSummary = reason + " Terrain cook pending.";
            SetState(TerrainTrackBindingState.CookPending, _lastCookSummary);
        }

        private bool TrySubmitPendingCook()
        {
            if (!_pendingCook)
                return true;

            HEU_HoudiniAsset terrain = GetAsset(_terrainAssetRoot);
            HEU_SessionBase session = HEU_SessionManager.GetDefaultSession();
            if (!TryGetValidTerrain(session, terrain))
            {
                SetState(TerrainTrackBindingState.WaitingForSession, "Terrain cook pending: session is unavailable.");
                return false;
            }

            string pendingBuildAction = GetPendingBuildActionName(terrain);
            if (_cookRequestIssued)
            {
                if (IsCookBusy(terrain.CookStatus) ||
                    string.Equals(pendingBuildAction, "COOK", System.StringComparison.Ordinal))
                {
                    return true;
                }

                if (!string.Equals(pendingBuildAction, "NONE", System.StringComparison.Ordinal))
                {
                    SetState(
                        TerrainTrackBindingState.CookPending,
                        "Terrain reload is busy; one replacement cook is coalesced.");
                    return false;
                }

                double elapsed = UnityEditor.EditorApplication.timeSinceStartup -
                    _cookRequestIssuedAt;
                if (elapsed < CookRequestRecoveryDelay)
                    return true;

                // RequestCook was submitted only while the private build action
                // was NONE. Returning to NONE means the cook completed even on
                // HEU versions that omit CookedDataEvent for this path.
                CompleteCookFromPolledState(terrain);
                return true;
            }

            if (IsCookBusy(terrain.CookStatus))
            {
                SetState(TerrainTrackBindingState.CookPending, "Terrain is busy; one replacement cook is coalesced.");
                return false;
            }

            if (!string.Equals(pendingBuildAction, "NONE", System.StringComparison.Ordinal))
            {
                SetState(
                    TerrainTrackBindingState.CookPending,
                    "Terrain has a pending HEU build action; replacement cook remains coalesced.");
                return false;
            }

            // RequestCook reports true even when an async reload owns the asset.
            // Keep _pendingCook until CookedDataEvent; ReloadDataEvent clears
            // _cookRequestIssued so the one coalesced request can be resubmitted.
            terrain.RequestCook(
                bCheckParametersChanged: false,
                bAsync: true,
                bSkipCookCheck: false,
                // Binding values were written directly through HAPI. Uploading
                // HEU's stale serialized parameter cache would revive the old path.
                bUploadParameters: false);
            _cookRequestIssued = true;
            _cookRequestIssuedAt = UnityEditor.EditorApplication.timeSinceStartup;
            _lastCookSummary = "Terrain cook submitted.";
            SetState(TerrainTrackBindingState.CookPending, _lastCookSummary);
            return true;
        }

        private void CompleteCookFromPolledState(HEU_HoudiniAsset terrain)
        {
            _cookRequestIssued = false;
            _cookRequestIssuedAt = -1.0;
            if (_cookAfterCurrent)
            {
                _cookAfterCurrent = false;
                _pendingCook = true;
            }
            else
            {
                _pendingCook = false;
            }

            bool success = terrain.LastCookResult != HEU_AssetCookResultWrapper.ERRORED;
            _lastCookSummary = success
                ? "Terrain cook completed successfully."
                : "Terrain cook failed; inspect Houdini Engine and Unity Console.";
            if (!success)
                SetState(TerrainTrackBindingState.Error, _lastCookSummary);
            else if (!_pendingCook)
                SetStableState();
        }

        private void TryRequestTerrainReload()
        {
            HEU_HoudiniAsset terrain = GetAsset(_terrainAssetRoot);
            if (_terrainReloadRequested || terrain == null)
                return;

            _terrainReloadRequested = terrain.RequestReload(bAsync: true);
        }

        private void SetStableState()
        {
            if (_pendingDetach || _manualDetach || !isActiveAndEnabled ||
                string.IsNullOrEmpty(_lastBoundPath))
            {
                SetState(
                    TerrainTrackBindingState.Detached,
                    "Detached; Working Terrain uses its base heightfield.");
            }
            else
            {
                SetState(
                    TerrainTrackBindingState.Bound,
                    "Bound to the current Track Display SOP.");
            }
        }

        private void SetState(TerrainTrackBindingState state, string status)
        {
            if (_bindingState == state &&
                string.Equals(_lastBindingStatus, status, System.StringComparison.Ordinal))
            {
                return;
            }

            _bindingState = state;
            _lastBindingStatus = status;
            if (this != null)
                UnityEditor.EditorUtility.SetDirty(this);
        }

        private void Cleanup()
        {
            UnityEditor.EditorApplication.update -= Pump;
            UnityEditor.EditorApplication.hierarchyChanged -= OnHierarchyChanged;
            UnityEditor.Undo.undoRedoPerformed -= OnUndoRedo;
            UnsubscribeAssetEvents();
            _nextAttempt = -1.0;
        }

        private static HEU_HoudiniAsset GetAsset(HEU_HoudiniAssetRoot root)
        {
            return root != null ? root.HoudiniAsset : null;
        }

        private bool IsTrackSourceUsable(HEU_HoudiniAsset track)
        {
            return _trackAssetRoot != null &&
                _trackAssetRoot.gameObject.activeInHierarchy &&
                track != null &&
                track.gameObject.activeInHierarchy &&
                track.AssetID != HEU_Defines.HEU_INVALID_NODE_ID;
        }

        private static bool TryGetValidTerrain(
            HEU_SessionBase session,
            HEU_HoudiniAsset terrain)
        {
            return session != null &&
                session.IsSessionValid() &&
                terrain != null &&
                terrain.AssetID != HEU_Defines.HEU_INVALID_NODE_ID;
        }

        private static bool HasBindingParameters(
            HEU_SessionBase session,
            HEU_HoudiniAsset terrain)
        {
            return session.GetParmIDFromName(
                    terrain.AssetID, PathParameter, out int pathParmId) &&
                pathParmId != HEU_HAPIConstants.HAPI_INVALID_PARM_ID &&
                session.GetParmIDFromName(
                    terrain.AssetID, EnabledParameter, out int enabledParmId) &&
                enabledParmId != HEU_HAPIConstants.HAPI_INVALID_PARM_ID;
        }

        internal static bool IsCookBusy(HEU_AssetCookStatusWrapper status)
        {
            return status != HEU_AssetCookStatusWrapper.NONE &&
                status != HEU_AssetCookStatusWrapper.POSTLOAD;
        }

        private static string GetPendingBuildActionName(HEU_HoudiniAsset terrain)
        {
            object value = RequestBuildActionField != null
                ? RequestBuildActionField.GetValue(terrain)
                : null;
            // If a future Houdini Engine version removes the field, the public
            // CookStatus path remains functional and treats the asset as idle.
            return value != null ? value.ToString() : "NONE";
        }

        private static bool TryGetTerrainPath(
            HEU_SessionBase session,
            HEU_HoudiniAsset terrain,
            out string path)
        {
            path = string.Empty;
            if (!session.GetParmStringValue(
                    terrain.AssetID, PathParameter, 0, true, out int stringHandle))
            {
                return false;
            }

            path = HEU_SessionManager.GetString(stringHandle, session) ?? string.Empty;
            return true;
        }

        [ContextMenu("Bind And Rebuild Terrain")]
        public void RebindNow()
        {
            if (Application.isPlaying)
                return;

            _pendingDetach = false;
            _manualDetach = false;
            _forceRebind = true;
            Schedule(0.0);
        }

        [ContextMenu("Detach And Restore Base Terrain")]
        public void DetachAndRestoreBaseNow()
        {
            if (Application.isPlaying)
                return;

            _pendingDetach = true;
            _manualDetach = true;
            _forceRestoreCook = true;
            Schedule(0.0, allowDisabled: true);
        }
#else
        public void RebindNow() { }
        public void DetachAndRestoreBaseNow() { }
#endif
    }

#if UNITY_EDITOR
    /// <summary>
    /// Finishes component-removal detach after HARS/Terrain becomes available.
    /// This queue exists only while the Editor is open and never enters Player builds.
    /// </summary>
    internal static class TerrainTrackDetachRecovery
    {
        private static readonly System.Collections.Generic.List<HEU_HoudiniAssetRoot> Pending =
            new System.Collections.Generic.List<HEU_HoudiniAssetRoot>();
        private static double _nextAttempt;

        internal static void Enqueue(HEU_HoudiniAssetRoot terrainRoot)
        {
            if (terrainRoot == null || Pending.Contains(terrainRoot))
                return;

            Pending.Add(terrainRoot);
            UnityEditor.EditorApplication.update -= Pump;
            UnityEditor.EditorApplication.update += Pump;
        }

        private static void Pump()
        {
            double now = UnityEditor.EditorApplication.timeSinceStartup;
            if (now < _nextAttempt)
                return;
            _nextAttempt = now + 0.25;

            if (UnityEditor.EditorApplication.isCompiling ||
                UnityEditor.EditorApplication.isUpdating ||
                UnityEditor.EditorApplication.isPlayingOrWillChangePlaymode)
            {
                return;
            }

            HEU_SessionBase session = HEU_SessionManager.GetDefaultSession();
            if (session == null || !session.IsSessionValid())
                return;

            for (int index = Pending.Count - 1; index >= 0; --index)
            {
                HEU_HoudiniAssetRoot root = Pending[index];
                HEU_HoudiniAsset terrain = root != null ? root.HoudiniAsset : null;
                if (terrain == null ||
                    terrain.AssetID == HEU_Defines.HEU_INVALID_NODE_ID ||
                    !session.GetParmIDFromName(
                        terrain.AssetID,
                        TerrainTrackDisplaySopBinding.EnabledParameter,
                        out int enabledParmId) ||
                    enabledParmId == HEU_HAPIConstants.HAPI_INVALID_PARM_ID ||
                    !session.GetParmIDFromName(
                        terrain.AssetID,
                        TerrainTrackDisplaySopBinding.PathParameter,
                        out int pathParmId) ||
                    pathParmId == HEU_HAPIConstants.HAPI_INVALID_PARM_ID)
                {
                    continue;
                }

                bool disabled = session.SetParamIntValue(
                    terrain.AssetID,
                    TerrainTrackDisplaySopBinding.EnabledParameter,
                    0,
                    0);
                bool cleared = session.SetParamStringValue(
                    terrain.AssetID,
                    TerrainTrackDisplaySopBinding.PathParameter,
                    string.Empty,
                    0);
                if (!disabled || !cleared)
                    continue;

                if (TerrainTrackDisplaySopBinding.IsCookBusy(terrain.CookStatus))
                    continue;

                terrain.RequestCook(
                    bCheckParametersChanged: false,
                    bAsync: true,
                    bSkipCookCheck: false,
                    bUploadParameters: false);
                Pending.RemoveAt(index);
            }

            if (Pending.Count == 0)
                UnityEditor.EditorApplication.update -= Pump;
        }
    }
#endif
}
