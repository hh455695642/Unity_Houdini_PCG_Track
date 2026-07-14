using PCGBike.Authoring;
using UnityEditor;

namespace PCGBike.AuthoringEditor
{
    [CustomEditor(typeof(TrackSplineHoudiniInputSettings))]
    [CanEditMultipleObjects]
    internal sealed class TrackSplineHoudiniInputSettingsEditor : UnityEditor.Editor
    {
        private SerializedProperty _enableKnotDataUpload;

        private void OnEnable()
        {
            _enableKnotDataUpload = serializedObject.FindProperty("EnableKnotDataUpload");
        }

        public override void OnInspectorGUI()
        {
            serializedObject.Update();
            EditorGUILayout.PropertyField(_enableKnotDataUpload);
            serializedObject.ApplyModifiedProperties();

            if (targets.Length != 1)
            {
                EditorGUILayout.HelpBox("Select one Track Spline to inspect Knot Contract diagnostics.", MessageType.Info);
                return;
            }

            TrackSplineHoudiniInputSettings settings = (TrackSplineHoudiniInputSettings)target;
            EditorGUILayout.Space();
            EditorGUILayout.LabelField("Upload Mode", settings.UploadMode);

            MessageType validationType = settings.LastUploadValidation.StartsWith("Valid:")
                ? MessageType.Info
                : MessageType.Warning;
            EditorGUILayout.HelpBox(settings.LastUploadValidation, validationType);
            EditorGUILayout.HelpBox(
                "Sampling is controlled only by Track.hda / sample_spacing. Unity uploads authored Knots and handles without pre-sampling.",
                MessageType.None);
        }
    }
}
