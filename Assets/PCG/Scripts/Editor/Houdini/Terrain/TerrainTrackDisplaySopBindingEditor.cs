using PCGBike.Terrain.Authoring;
using UnityEditor;
using UnityEngine;

namespace PCGBike.Editor.Houdini.Terrain
{
    [CustomEditor(typeof(TerrainTrackDisplaySopBinding))]
    [CanEditMultipleObjects]
    public sealed class TerrainTrackDisplaySopBindingEditor : UnityEditor.Editor
    {
        private SerializedProperty _trackAssetRoot;
        private SerializedProperty _terrainAssetRoot;
        private SerializedProperty _autoCookTerrain;
        private bool _showDebug;

        private void OnEnable()
        {
            _trackAssetRoot = serializedObject.FindProperty("_trackAssetRoot");
            _terrainAssetRoot = serializedObject.FindProperty("_terrainAssetRoot");
            _autoCookTerrain = serializedObject.FindProperty("_autoCookTerrain");
        }

        public override void OnInspectorGUI()
        {
            serializedObject.Update();

            EditorGUILayout.HelpBox(
                "取消勾选本组件会停止 Track 影响，并自动恢复 Working Terrain 的基础地形。",
                MessageType.Info);

            EditorGUILayout.PropertyField(_trackAssetRoot, new GUIContent("Track Source"));
            EditorGUILayout.PropertyField(_terrainAssetRoot, new GUIContent("Working Terrain"));
            EditorGUILayout.PropertyField(_autoCookTerrain, new GUIContent("Auto Cook Terrain"));

            serializedObject.ApplyModifiedProperties();
            EditorGUILayout.Space(6f);

            if (targets.Length == 1)
                DrawStatus((TerrainTrackDisplaySopBinding)target);
            else
                EditorGUILayout.HelpBox("多选模式下不显示单个 Binding 状态。", MessageType.None);

            EditorGUILayout.Space(4f);
            using (new EditorGUI.DisabledScope(EditorApplication.isPlayingOrWillChangePlaymode))
            {
                if (GUILayout.Button("绑定并重建地形", GUILayout.Height(26f)))
                {
                    foreach (Object item in targets)
                    {
                        var binding = (TerrainTrackDisplaySopBinding)item;
                        Undo.RecordObject(binding, "Bind Terrain Track");
                        binding.RebindNow();
                    }
                }

                if (GUILayout.Button("解绑并恢复基础地形", GUILayout.Height(26f)))
                {
                    foreach (Object item in targets)
                    {
                        var binding = (TerrainTrackDisplaySopBinding)item;
                        Undo.RecordObject(binding, "Detach Terrain Track");
                        binding.DetachAndRestoreBaseNow();
                    }
                }
            }

            _showDebug = EditorGUILayout.Foldout(
                _showDebug,
                "Debug（技术路径）",
                toggleOnLabelClick: true);
            if (_showDebug && targets.Length == 1)
            {
                var binding = (TerrainTrackDisplaySopBinding)target;
                using (new EditorGUI.DisabledScope(true))
                {
                    EditorGUILayout.TextField("Display SOP Path", binding.LastBoundPath);
                    EditorGUILayout.Toggle("Pending Cook", binding.HasPendingCook);
                    EditorGUILayout.TextField("Last Cook", binding.LastCookSummary);
                }
            }
        }

        private static void DrawStatus(TerrainTrackDisplaySopBinding binding)
        {
            MessageType messageType;
            switch (binding.BindingState)
            {
                case TerrainTrackBindingState.Bound:
                case TerrainTrackBindingState.Detached:
                    messageType = MessageType.Info;
                    break;
                case TerrainTrackBindingState.WaitingForSession:
                case TerrainTrackBindingState.CookPending:
                    messageType = MessageType.Warning;
                    break;
                default:
                    messageType = MessageType.Error;
                    break;
            }

            EditorGUILayout.LabelField("Current State", binding.BindingState.ToString());
            EditorGUILayout.HelpBox(binding.LastBindingStatus, messageType);
        }
    }
}
