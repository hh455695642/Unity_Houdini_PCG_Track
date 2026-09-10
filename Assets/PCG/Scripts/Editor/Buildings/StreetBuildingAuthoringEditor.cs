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
        public override void OnInspectorGUI()
        {
            serializedObject.Update();
            EditorGUILayout.LabelField("风格 / Style", EditorStyles.boldLabel);
            EditorGUILayout.PropertyField(serializedObject.FindProperty("_fixedStyleConfig"),
                new GUIContent("固定风格配置 / Fixed StyleConfig"));
            EditorGUILayout.PropertyField(serializedObject.FindProperty("_randomizeOnRecook"),
                new GUIContent("Recook 随机布局", "关闭后锁定当前布局；保存和 Bake 不改变随机结果。"));
            serializedObject.ApplyModifiedProperties();

            StreetBuildingAuthoring authoring = (StreetBuildingAuthoring)target;
            if (!string.IsNullOrEmpty(authoring.MissingModuleSummary))
                EditorGUILayout.HelpBox("自动缺项占位（上次成功应用）：\n" + authoring.MissingModuleSummary, MessageType.Info);
            StreetBuildingStyleConfig style = authoring.ResolveStyle();
            var root = authoring.GetComponent<HEU_HoudiniAssetRoot>();
            var parameters = root != null && root.HoudiniAsset != null ? root.HoudiniAsset.Parameters : null;
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
                var complete = StreetBuildingStyleValidator.Validate(style, true);
                var preview = StreetBuildingStyleValidator.Validate(style);
                if (!preview.IsValid)
                    EditorGUILayout.HelpBox("配置数据无效：\n" + string.Join("\n", preview.Errors), MessageType.Error);
                else if (!complete.IsValid)
                    EditorGUILayout.HelpBox("部分模块预览可用；正式 Bake 需要补齐：\n" + string.Join("\n", complete.Errors), MessageType.Info);
                if (GUILayout.Button("完整建筑检查"))
                    EditorUtility.DisplayDialog("完整建筑检查", complete.ToString(), "确定");
            }
            EditorGUILayout.HelpBox(style == null
                    ? "必须为当前 HDA 显式指定 StyleConfig。"
                    : $"当前风格：{style.name}\nRecook 自动同步配置。随机仅影响墙面模块，体块尺寸保留。",
                style == null ? MessageType.Error : MessageType.Info);

            using (new EditorGUI.DisabledScope(style == null))
            using (new EditorGUILayout.HorizontalScope())
            {
                if (GUILayout.Button("验证 / Validate")) Validate(authoring, style);
                if (GUILayout.Button("编译预览 / Compile Preview")) CompilePreview(authoring, style);
                if (GUILayout.Button("定位 StyleConfig")) EditorGUIUtility.PingObject(style);
            }
            using (new EditorGUI.DisabledScope(style == null))
                if (GUILayout.Button("应用风格、Cook 并保存场景 / Apply Style, Cook & Save")) Apply(authoring);

            if (!string.IsNullOrEmpty(authoring.LastAppliedPayloadSha256))
                EditorGUILayout.HelpBox("最后 Style Payload SHA-256:\n" + authoring.LastAppliedPayloadSha256,
                    MessageType.None);
            if (!string.IsNullOrEmpty(authoring.LastCookDiagnostic))
                EditorGUILayout.HelpBox("Cook 诊断：\n" + authoring.LastCookDiagnostic,
                    authoring.LastCookDiagnostic.Contains("PASS") ? MessageType.Info : MessageType.Warning);
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

        private static void Apply(StreetBuildingAuthoring authoring)
        {
            try
            {
                HEU_HoudiniAssetRoot root = authoring.GetComponent<HEU_HoudiniAssetRoot>();
                StreetBuildingCompiledStyle compiled = StreetBuildingStyleApplier.ApplyAndSave(root, authoring);
                Debug.Log("StreetBuilding style applied, cooked and saved. SHA-256 " + compiled.Sha256, authoring);
            }
            catch (Exception exception) { Debug.LogError("StreetBuilding style apply failed.\n" + exception, authoring); }
        }
    }
}
#endif
