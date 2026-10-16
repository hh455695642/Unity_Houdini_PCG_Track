#if UNITY_EDITOR
using System;
using HoudiniEngineUnity;
using PCGBike.Buildings;
using UnityEditor;
using UnityEngine;

namespace PCGBike.Editor.Buildings
{
    [CustomEditor(typeof(StreetBuildingAuthoring))]
    public sealed class StreetBuildingAuthoringEditor : UnityEditor.Editor
    {
        private readonly StreetBuildingParameterPanel panel = new();
        private void OnEnable() { if (target is StreetBuildingAuthoring a) StreetBuildingPanelState.Observe(a); }
        public override bool RequiresConstantRepaint() => true;
        public override void OnInspectorGUI()
        {
            serializedObject.Update();
            EditorGUILayout.LabelField("风格 / Style", EditorStyles.boldLabel);
            EditorGUILayout.PropertyField(serializedObject.FindProperty("_fixedStyleConfig"),
                new GUIContent("固定风格配置 / Fixed StyleConfig"));
            serializedObject.ApplyModifiedProperties();

            StreetBuildingAuthoring authoring = (StreetBuildingAuthoring)target;
            panel.Draw(authoring);
            if (!string.IsNullOrEmpty(authoring.MissingModuleSummary))
                EditorGUILayout.HelpBox("自动缺项占位（上次成功应用）：\n" + authoring.MissingModuleSummary, MessageType.Info);
            StreetBuildingStyleConfig style = authoring.ResolveStyle();
            var root = authoring.GetComponent<HEU_HoudiniAssetRoot>();
            var parameters = root != null && root.HoudiniAsset != null ? root.HoudiniAsset.Parameters : null;
            EditorGUILayout.HelpBox("素材配置只提供模块与尺寸。生成数量、用途、排列和开关使用 HDA 实例面板；局部覆盖的生效范围见 Cook 诊断。", MessageType.Info);
            if (!string.IsNullOrEmpty(authoring.LastCookDiagnostic)
                && authoring.LastCookDiagnostic.Contains("实际首层：住宅")
                && authoring.LastCookDiagnostic.Contains("入户门 0"))
                EditorGUILayout.HelpBox("当前实际用途为住宅，且住宅入户门已关闭；商业门数不会在住宅首层生成门。需要商铺时将本实例首层用途设为“商业”并 Recook。",
                    MessageType.Warning);
            if (parameters != null && parameters.GetIntParameterValue("rear_facade_mode", out int rearMode)
                && rearMode == 0)
                EditorGUILayout.HelpBox("后立面当前关闭：额外商业门只能在可用的左、右立面抽取。开启后立面后才会参与后门抽取。",
                    MessageType.Info);
            var automatic = parameters?.GetParameter("site_source_auto");
            var siteInput = root?.HoudiniAsset?.GetInputNodeByIndex(0);
            string resolvedSite = siteInput != null && siteInput.GetConnectedInputCount() > 0
                ? "输入地块（有效性由 Cook 检查）" : "独栋（宽度、进深和轮廓参数）";
            if (automatic != null && !automatic._toggle)
            {
                EditorGUILayout.HelpBox("旧实例使用手动地块来源。按当前连接迁移后：" + resolvedSite + "。无效输入报错。", MessageType.Info);
                if (GUILayout.Button("迁移为自动地块来源"))
                {
                    Undo.RecordObject(parameters, "自动地块来源迁移");
                    parameters.SetBoolParameterValue("site_source_auto", true);
                    EditorUtility.SetDirty(parameters);
                    UnityEditor.SceneManagement.EditorSceneManager.MarkSceneDirty(authoring.gameObject.scene);
                }
            }
            else if (automatic != null)
                EditorGUILayout.HelpBox("地块来源：自动 → " + resolvedSite, MessageType.Info);
            if (style != null)
            {
                if (GUILayout.Button("完整建筑检查"))
                    EditorUtility.DisplayDialog("完整建筑检查", StreetBuildingStyleValidator.Validate(style, true).ToString(), "确定");
            }
            EditorGUILayout.HelpBox(style == null
                    ? "必须为当前 HDA 显式指定 StyleConfig。"
                    : $"当前风格：{style.name}\nRecook 自动同步配置；固定种子重复生成一致。",
                style == null ? MessageType.Error : MessageType.Info);

            using (new EditorGUI.DisabledScope(style == null))
            using (new EditorGUILayout.HorizontalScope())
            {
                if (GUILayout.Button("验证 / Validate")) Validate(authoring, style);
                if (GUILayout.Button("编译预览 / Compile Preview")) CompilePreview(authoring, style);
                if (GUILayout.Button("定位 StyleConfig")) EditorGUIUtility.PingObject(style);
            }
            if (!string.IsNullOrEmpty(authoring.LastAppliedPayloadSha256))
                EditorGUILayout.HelpBox("最后 Style Payload SHA-256:\n" + authoring.LastAppliedPayloadSha256,
                    MessageType.None);
            if (!string.IsNullOrEmpty(authoring.LastCookDiagnostic))
                EditorGUILayout.HelpBox("Cook 诊断：\n" + StreetBuildingRecook.CurrentCookDiagnostic(root?.HoudiniAsset, authoring.LastCookDiagnostic), MessageType.Info);
        }

        private static void Validate(StreetBuildingAuthoring authoring, StreetBuildingStyleConfig style)
        {
            string result = StreetBuildingStyleApplier.Validate(style);
            if (string.IsNullOrEmpty(result)) Debug.Log("StreetBuilding StyleConfig validation PASS.", authoring);
            else Debug.LogError(result, authoring);
        }

        private static void CompilePreview(StreetBuildingAuthoring authoring, StreetBuildingStyleConfig style)
        {
            try
            {
                StreetBuildingCompiledStyle compiled = StreetBuildingStyleCompiler.Compile(style);
                Debug.Log($"StreetBuilding style compile PASS\n{compiled.ModuleCount} modules / {compiled.Sha256}\n"
                          + compiled.Payload, authoring);
            }
            catch (Exception exception) { Debug.LogError("StreetBuilding style compile failed.\n" + exception, authoring); }
        }

    }
}
#endif
