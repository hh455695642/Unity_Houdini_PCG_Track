using HoudiniEngineUnity;
using PCGBike.Track.Authoring;
using UnityEditor;
using UnityEditor.Callbacks;
using UnityEngine;
using UnityEngine.Splines;

namespace PCGBike.Editor.Houdini.TrackSplineInput
{
    /// <summary>
    /// Project-owned Houdini input interface for explicitly marked PCG Track splines.
    /// Registration and orchestration stay here; snapshot, payload, and HAPI upload
    /// responsibilities live in dedicated collaborators.
    /// </summary>
    [InitializeOnLoad]
    internal sealed class TrackSplineHoudiniInputInterface : HEU_InputInterface
    {
        private const int CustomPriority = DEFAULT_PRIORITY + 100;
        private const string LogPrefix = "[PCG Track Spline Input]";
        private const int MaxRegistrationAttempts = 8;

        private static int _registrationAttempts;

        static TrackSplineHoudiniInputInterface()
        {
            RegisterOrRetry();
        }

        private TrackSplineHoudiniInputInterface()
            : base(CustomPriority)
        {
        }

        [InitializeOnLoadMethod]
        private static void OnEditorLoad()
        {
            RegisterOrRetry();
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
            // Houdini Engine registers its built-in interfaces through editor callbacks.
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
            if (HEU_InputUtility.GetInputInterfaceByType(typeof(TrackSplineHoudiniInputInterface)) == null)
                new TrackSplineHoudiniInputInterface().RegisterInterface();
        }

        public override bool IsThisInputObjectSupported(GameObject inputObject)
        {
            if (inputObject == null || inputObject.GetComponent<SplineContainer>() == null)
                return false;

            TrackSplineHoudiniInputAuthoring inputAuthoring =
                inputObject.GetComponent<TrackSplineHoudiniInputAuthoring>();
            return inputAuthoring != null && inputAuthoring.UsesCustomInterface;
        }

        public override bool CreateInputNodeWithDataUpload(
            HEU_SessionBase session,
            int connectNodeID,
            GameObject inputObject,
            out int inputNodeID)
        {
            inputNodeID = HEU_Defines.HEU_INVALID_NODE_ID;
            if (session == null || !HEU_HAPIUtility.IsNodeValidInHoudini(session, connectNodeID))
            {
                HEU_Logger.LogErrorFormat(
                    "{0} Connection node {1} is invalid for {2}.",
                    LogPrefix,
                    connectNodeID,
                    inputObject != null ? inputObject.name : "<null>");
                return false;
            }

            if (!TrackSplineInputSnapshotBuilder.TryCreate(inputObject, out TrackSplineInputSnapshot snapshot))
                return false;

            bool success = TrackSplineHapiUploader.TryUpload(
                session,
                inputObject.name,
                snapshot,
                out inputNodeID,
                out string validationMessage);
            ReportValidation(snapshot, success, validationMessage);
            return success;
        }

        private static void ReportValidation(
            TrackSplineInputSnapshot snapshot,
            bool success,
            string message)
        {
            snapshot.Authoring.SetEditorUploadValidation(
                success,
                message,
                snapshot.Splines.Count,
                snapshot.TotalKnotCount,
                snapshot.ClosedState);
        }
    }
}
