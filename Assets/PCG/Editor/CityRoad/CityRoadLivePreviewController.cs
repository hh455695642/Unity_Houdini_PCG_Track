#if UNITY_EDITOR
using System;
using System.Collections.Generic;
using System.Globalization;
using System.Linq;
using HoudiniEngineUnity;
using UnityEditor;
using UnityEditor.Build;
using UnityEditor.Build.Reporting;
using UnityEditor.SceneManagement;
using UnityEngine;
using UnityEngine.Events;
using UnityEngine.SceneManagement;

namespace PCG.CityRoad.Editor
{
    /// <summary>
    /// Keeps manual Houdini Inspector cooks safe and visible. A successful cook
    /// enters Live Preview; a successful project Bake restores the runtime-only
    /// baked state. No Houdini Engine plugin code is modified.
    /// </summary>
    [InitializeOnLoad]
    internal static class CityRoadLivePreviewController
    {
        private const double SubscriptionRefreshSeconds = 1.0;
        // Houdini Engine can deliver Cooked/Reloaded callbacks several editor
        // ticks after a project Bake, especially when AssetDatabase validation
        // runs immediately afterwards. Keep the freshly baked state authoritative
        // long enough for those callbacks to drain.
        private const double BakeCallbackGuardSeconds = 30.0;
        private const string SessionPrefix = "PCG.CityRoad.LivePreview.";

        private sealed class Subscription
        {
            internal HEU_HoudiniAssetRoot Root;
            internal HEU_HoudiniAsset Asset;
            internal UnityAction<HEU_CookedEventData> Cooked;
            internal UnityAction<HEU_ReloadEventData> Reloaded;
        }

        private static readonly Dictionary<int, Subscription> s_Subscriptions =
            new Dictionary<int, Subscription>();
        private static readonly Dictionary<int, int> s_StateEpochs =
            new Dictionary<int, int>();
        private static readonly Dictionary<int, double> s_IgnoreLivePreviewUntil =
            new Dictionary<int, double>();
        private static double s_NextRefresh;
        private static bool s_ApplyingState;

        static CityRoadLivePreviewController()
        {
            EditorApplication.update += OnEditorUpdate;
            EditorApplication.hierarchyChanged += QueueRefresh;
            EditorApplication.playModeStateChanged += OnPlayModeStateChanged;
            AssemblyReloadEvents.beforeAssemblyReload += UnsubscribeAll;
            EditorSceneManager.sceneSaving += OnSceneSaving;
            EditorApplication.delayCall += RefreshSubscriptions;
        }

        internal static void EnterLivePreview(HEU_HoudiniAssetRoot root)
        {
            if (root == null || EditorUtility.IsPersistent(root) || !root.gameObject.scene.IsValid())
                return;
            if (EditorApplication.isPlayingOrWillChangePlaymode)
            {
                MarkBaked(root);
                return;
            }

            s_ApplyingState = true;
            try
            {
                CityRoadSafeRebuild.CleanupKnownHapiOrphanTreeRoots(root);
                bool changed = false;
                root.gameObject.tag = "EditorOnly";
                foreach (Renderer renderer in root.GetComponentsInChildren<Renderer>(true))
                {
                    bool expectedEnabled = ShouldEnableLivePreviewRenderer(renderer);
                    if (renderer.enabled != expectedEnabled)
                    {
                        renderer.enabled = expectedEnabled;
                        changed = true;
                    }
                }

                CityRoadBakeWorkflow.ApplyCollisionOutputContract(root.gameObject);
                CityRoadBakeWorkflow.ApplyShadowContract(root.gameObject);
                Transform bake = FindSibling(root, root.name + "_Bake");
                if (bake != null && bake.gameObject.activeSelf)
                {
                    bake.gameObject.SetActive(false);
                    changed = true;
                }

                SessionState.SetBool(GetSessionKey(root), true);
                if (changed)
                {
                    EditorUtility.SetDirty(root.gameObject);
                    EditorSceneManager.MarkSceneDirty(root.gameObject.scene);
                }
            }
            finally
            {
                s_ApplyingState = false;
            }
        }

        internal static void MarkBaked(HEU_HoudiniAssetRoot root)
        {
            if (root == null)
                return;

            // Invalidate Cooked/Reloaded delay calls that were queued before
            // Bake completed. Otherwise a late HEU callback can immediately
            // switch the freshly baked scene back to Live Preview.
            AdvanceStateEpoch(root);
            SetBakeCallbackGuard(root);
            ApplyBakedVisualState(root);
        }

        private static void ApplyBakedVisualState(HEU_HoudiniAssetRoot root)
        {
            if (root == null)
                return;
            s_ApplyingState = true;
            try
            {
                CityRoadSafeRebuild.CleanupKnownHapiOrphanTreeRoots(root);
                bool changed = false;
                foreach (Renderer renderer in root.GetComponentsInChildren<Renderer>(true))
                {
                    if (!renderer.enabled)
                        continue;
                    renderer.enabled = false;
                    changed = true;
                }

                Transform bake = FindSibling(root, root.name + "_Bake");
                if (bake != null && !bake.gameObject.activeSelf)
                {
                    bake.gameObject.SetActive(true);
                    changed = true;
                }

                SessionState.SetBool(GetSessionKey(root), false);
                if (changed && root.gameObject.scene.IsValid())
                    EditorSceneManager.MarkSceneDirty(root.gameObject.scene);
            }
            finally
            {
                s_ApplyingState = false;
            }
        }

        internal static bool IsLivePreview(HEU_HoudiniAssetRoot root)
        {
            if (root == null)
                return false;
            if (SessionState.GetBool(GetSessionKey(root), false))
                return true;

            Transform bake = FindSibling(root, root.name + "_Bake");
            bool hasActiveBake = bake != null && bake.gameObject.activeInHierarchy;
            bool sourceVisible = root.GetComponentsInChildren<Renderer>(true).Any(renderer =>
                renderer.enabled
                && renderer.gameObject.activeInHierarchy
                && (CityRoadBakeWorkflow.IsUnderNamedOutput(renderer.transform, "OUT_ROAD_SURFACE")
                     || CityRoadBakeWorkflow.IsUnderNamedOutput(renderer.transform, "OUT_SIDEWALK_CURB")
                     || CityRoadBakeWorkflow.IsUnderNamedOutput(renderer.transform, "OUT_ROAD_MARKINGS")
                     || CityRoadBakeWorkflow.IsStreetFurnitureOutput(renderer.transform)));
            return sourceVisible || !hasActiveBake;
        }

        internal static bool ValidateBakedScene(Scene scene, out string report)
        {
            var issues = new List<string>();
            foreach (GameObject sceneRoot in scene.GetRootGameObjects())
            {
                foreach (HEU_HoudiniAssetRoot root in sceneRoot.GetComponentsInChildren<HEU_HoudiniAssetRoot>(true))
                {
                    if (!CityRoadSafeRebuild.IsCityRoad(root))
                        continue;
                    if (IsLivePreview(root))
                        issues.Add(root.name + " is still in Live Preview or has no active Bake instance.");
                }
            }

            report = string.Join("\n", issues);
            return issues.Count == 0;
        }

        private static void OnEditorUpdate()
        {
            if (EditorApplication.timeSinceStartup < s_NextRefresh)
                return;
            s_NextRefresh = EditorApplication.timeSinceStartup + SubscriptionRefreshSeconds;
            RefreshSubscriptions();
        }

        private static void QueueRefresh()
        {
            if (!s_ApplyingState)
                EditorApplication.delayCall += RefreshSubscriptions;
        }

        private static void RefreshSubscriptions()
        {
            if (EditorApplication.isCompiling || EditorApplication.isUpdating)
                return;

            HEU_HoudiniAssetRoot[] roots = Resources.FindObjectsOfTypeAll<HEU_HoudiniAssetRoot>()
                .Where(root =>
                    root != null
                    && !EditorUtility.IsPersistent(root)
                    && root.gameObject.scene.IsValid()
                    && root.gameObject.scene.isLoaded
                    && CityRoadSafeRebuild.IsCityRoad(root))
                .ToArray();
            var liveIds = new HashSet<int>();
            foreach (HEU_HoudiniAssetRoot root in roots)
            {
                HEU_HoudiniAsset asset = root.HoudiniAsset;
                if (asset == null)
                    continue;
                CityRoadSafeRebuild.CleanupKnownHapiOrphanTreeRoots(root);
                int id = root.GetInstanceID();
                liveIds.Add(id);
                if (s_Subscriptions.TryGetValue(id, out Subscription existing)
                    && existing.Asset == asset)
                {
                    // HEU can emit ReloadDataEvent before all output GameObjects
                    // have been materialized. Normalize an existing Live Preview
                    // on the regular editor tick as well, so late-created backing,
                    // collision and metadata renderers cannot remain visible.
                    if (IsBakeCallbackGuardActive(root))
                        ApplyBakedVisualState(root);
                    else if (IsLivePreview(root))
                        EnterLivePreview(root);
                    continue;
                }

                RemoveSubscription(id);
                var subscription = new Subscription
                {
                    Root = root,
                    Asset = asset
                };
                subscription.Cooked = data =>
                {
                    if (data != null && data.CookSuccess)
                        QueueLivePreview(subscription.Root);
                };
                subscription.Reloaded = data => QueueLivePreview(subscription.Root);
                asset.CookedDataEvent.RemoveListener(subscription.Cooked);
                asset.CookedDataEvent.AddListener(subscription.Cooked);
                asset.ReloadDataEvent.RemoveListener(subscription.Reloaded);
                asset.ReloadDataEvent.AddListener(subscription.Reloaded);
                s_Subscriptions.Add(id, subscription);

                // A scene can reopen with valid serialized HDA outputs without
                // emitting CookedDataEvent/ReloadDataEvent. Normalize that
                // restored Live Preview immediately so helper/debug outputs stay
                // hidden and the mobile shadow contract is not silently reset.
                HEU_HoudiniAssetRoot restoredRoot = root;
                EditorApplication.delayCall += () =>
                {
                    if (restoredRoot == null)
                        return;
                    if (IsBakeCallbackGuardActive(restoredRoot))
                        ApplyBakedVisualState(restoredRoot);
                    else if (IsLivePreview(restoredRoot))
                        EnterLivePreview(restoredRoot);
                };
            }

            foreach (int staleId in s_Subscriptions.Keys.Where(id => !liveIds.Contains(id)).ToArray())
                RemoveSubscription(staleId);
        }

        private static void RemoveSubscription(int id)
        {
            if (!s_Subscriptions.TryGetValue(id, out Subscription subscription))
                return;
            if (subscription.Asset != null)
            {
                subscription.Asset.CookedDataEvent.RemoveListener(subscription.Cooked);
                subscription.Asset.ReloadDataEvent.RemoveListener(subscription.Reloaded);
            }
            s_Subscriptions.Remove(id);
            s_IgnoreLivePreviewUntil.Remove(id);
        }

        private static void QueueLivePreview(HEU_HoudiniAssetRoot root)
        {
            if (root == null || EditorApplication.isPlayingOrWillChangePlaymode)
                return;

            int id = root.GetInstanceID();
            if (IsBakeCallbackGuardActive(root))
                return;
            int queuedEpoch = GetStateEpoch(id);
            EditorApplication.delayCall += () =>
            {
                if (root != null
                    && GetStateEpoch(id) == queuedEpoch
                    && !IsBakeCallbackGuardActive(root))
                    EnterLivePreview(root);
            };
        }

        private static void OnPlayModeStateChanged(PlayModeStateChange state)
        {
            if (state != PlayModeStateChange.ExitingEditMode
                && state != PlayModeStateChange.EnteredPlayMode)
                return;

            foreach (HEU_HoudiniAssetRoot root in
                Resources.FindObjectsOfTypeAll<HEU_HoudiniAssetRoot>())
            {
                if (root == null
                    || EditorUtility.IsPersistent(root)
                    || !root.gameObject.scene.IsValid()
                    || !root.gameObject.scene.isLoaded
                    || !CityRoadSafeRebuild.IsCityRoad(root)
                    || FindSibling(root, root.name + "_Bake") == null)
                    continue;
                MarkBaked(root);
            }
        }

        private static void SetBakeCallbackGuard(HEU_HoudiniAssetRoot root)
        {
            double until = EditorApplication.timeSinceStartup
                + BakeCallbackGuardSeconds;
            s_IgnoreLivePreviewUntil[root.GetInstanceID()] = until;
            SessionState.SetString(
                GetBakeGuardKey(root),
                until.ToString("R", CultureInfo.InvariantCulture));
        }

        private static bool IsBakeCallbackGuardActive(HEU_HoudiniAssetRoot root)
        {
            if (root == null)
                return false;
            int id = root.GetInstanceID();
            if (!s_IgnoreLivePreviewUntil.TryGetValue(id, out double until))
            {
                string persisted = SessionState.GetString(
                    GetBakeGuardKey(root),
                    string.Empty);
                if (!double.TryParse(
                        persisted,
                        NumberStyles.Float,
                        CultureInfo.InvariantCulture,
                        out until))
                    return false;
                s_IgnoreLivePreviewUntil[id] = until;
            }
            if (EditorApplication.timeSinceStartup < until)
                return true;
            s_IgnoreLivePreviewUntil.Remove(id);
            SessionState.SetString(GetBakeGuardKey(root), string.Empty);
            return false;
        }

        private static int GetStateEpoch(int id)
        {
            return s_StateEpochs.TryGetValue(id, out int epoch) ? epoch : 0;
        }

        private static void AdvanceStateEpoch(HEU_HoudiniAssetRoot root)
        {
            int id = root.GetInstanceID();
            s_StateEpochs[id] = GetStateEpoch(id) + 1;
        }

        private static void UnsubscribeAll()
        {
            foreach (int id in s_Subscriptions.Keys.ToArray())
                RemoveSubscription(id);
        }

        private static void OnSceneSaving(Scene scene, string path)
        {
            if (!ValidateBakedScene(scene, out string report))
            {
                Debug.LogError(
                    "CityRoad scene save validation: Live Preview is editor-only. "
                    + "Run Cook + Validate + Update Bake before building.\n"
                    + report);
            }
        }

        private static Transform FindSibling(HEU_HoudiniAssetRoot source, string name)
        {
            Transform parent = source.transform.parent;
            IEnumerable<Transform> siblings = parent != null
                ? parent.Cast<Transform>()
                : source.gameObject.scene.GetRootGameObjects().Select(gameObject => gameObject.transform);
            return siblings.FirstOrDefault(transform =>
                string.Equals(transform.name, name, StringComparison.Ordinal));
        }

        private static bool HasTopologyPieceName(Transform transform)
        {
            for (Transform current = transform; current != null; current = current.parent)
            {
                if (current.name.IndexOf("Corridor_", StringComparison.OrdinalIgnoreCase) >= 0
                    || current.name.IndexOf("Junction_", StringComparison.OrdinalIgnoreCase) >= 0
                    // Direct-fill sidewalk/curb output is packed per enclosed
                    // block instead of per road corridor or junction.
                    || current.name.IndexOf("SidewalkRegion_", StringComparison.OrdinalIgnoreCase) >= 0)
                {
                    return true;
                }
            }
            return false;
        }

        private static bool ShouldEnableLivePreviewRenderer(Renderer renderer)
        {
            if (renderer == null)
                return false;

            Transform transform = renderer.transform;
            bool streetFurniture =
                CityRoadBakeWorkflow.IsStreetFurnitureOutput(transform);
            bool visibleRole =
                CityRoadBakeWorkflow.IsUnderNamedOutput(transform, "OUT_ROAD_SURFACE")
                || CityRoadBakeWorkflow.IsUnderNamedOutput(transform, "OUT_SIDEWALK_CURB")
                || CityRoadBakeWorkflow.IsUnderNamedOutput(transform, "OUT_ROAD_MARKINGS")
                || streetFurniture;
            bool collisionRole =
                CityRoadBakeWorkflow.IsUnderNamedOutput(transform, "OUT_ROAD_COLLISION");

            // HEU road outputs include a backing renderer and topology-piece
            // renderers that reference the same Mesh, so roads still require a
            // presentation-piece marker.
            bool roadPresentationPiece = HasTopologyPieceName(transform);
            return visibleRole
                && (roadPresentationPiece || streetFurniture)
                && !collisionRole;
        }

        private static string GetSessionKey(HEU_HoudiniAssetRoot root)
        {
            return SessionPrefix + root.gameObject.scene.path + ":" + root.name;
        }

        private static string GetBakeGuardKey(HEU_HoudiniAssetRoot root)
        {
            return GetSessionKey(root) + ".BakeGuardUntil";
        }
    }

    internal sealed class CityRoadBuildGuard : IProcessSceneWithReport
    {
        public int callbackOrder => 0;

        public void OnProcessScene(Scene scene, BuildReport report)
        {
            if (!CityRoadLivePreviewController.ValidateBakedScene(scene, out string validation))
            {
                throw new BuildFailedException(
                    "CityRoad build blocked: scene contains Live Preview or a missing/inactive Bake.\n"
                    + validation);
            }
        }
    }
}
#endif
