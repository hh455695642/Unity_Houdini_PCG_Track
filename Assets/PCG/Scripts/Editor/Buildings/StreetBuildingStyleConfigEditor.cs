#if UNITY_EDITOR
using System;
using System.Linq;
using PCGBike.Buildings;
using UnityEditor;
using UnityEngine;

namespace PCGBike.Editor.Buildings
{
    [CustomEditor(typeof(StreetBuildingStyleConfig))]
    public sealed class StreetBuildingStyleConfigEditor : UnityEditor.Editor
    {
        private static readonly (string Property, string Label)[] Groups =
        {
            ("_ground", "首层"),
            ("_upper", "上层"),
            ("_roof", "屋顶"),
        };

        public override void OnInspectorGUI()
        {
            serializedObject.Update();
            if (((StreetBuildingStyleConfig)target).NeedsLayerMigration)
            {
                EditorGUILayout.HelpBox("此风格需要迁移为首层 / 上层 / 屋顶配置。", MessageType.Info);
                if (GUILayout.Button("迁移当前风格（保留 Prefab 引用）"))
                    StreetBuildingLayerMigration.Migrate((StreetBuildingStyleConfig)target);
                return;
            }
            EditorGUILayout.LabelField("风格总配置", EditorStyles.boldLabel);
            EditorGUILayout.PropertyField(serializedObject.FindProperty("_cellWidth"), new GUIContent("单元宽度 (m)"));

            foreach ((string property, string label) in Groups)
            {
                EditorGUILayout.Space(4);
                var layer = serializedObject.FindProperty(property);
                layer.isExpanded = EditorGUILayout.Foldout(layer.isExpanded, label, true);
                if (!layer.isExpanded) continue;
                EditorGUI.indentLevel++;
                if (property != "_roof")
                    EditorGUILayout.PropertyField(layer.FindPropertyRelative("_height"), new GUIContent("楼层高度 (m)"));
                foreach (var field in new[] { ("_facade", "正面墙面 / 门窗"), ("_sideRear", "侧墙 / 背墙"),
                             ("_corners", "阴角 / 阳角"), ("_trim", "柱 / 腰线 / 檐口"),
                             ("_roofSurface", "屋面 / 女儿墙及转角"), ("_attachments", "配件") })
                {
                    var list = layer.FindPropertyRelative(field.Item1);
                    if (property == "_roof" && (field.Item1 is "_facade" or "_sideRear" or "_corners") && list.arraySize == 0) continue;
                    if (property != "_roof" && field.Item1 == "_roofSurface" && list.arraySize == 0) continue;
                    EditorGUILayout.PropertyField(list, new GUIContent(field.Item2), true);
                }
                DrawRules(layer.FindPropertyRelative("_rules"), property);
                EditorGUI.indentLevel--;
            }
            serializedObject.ApplyModifiedProperties();

            StreetBuildingStyleConfig style = (StreetBuildingStyleConfig)target;
            int total = style.EnumerateModules().Count();
            int enabled = style.EnumerateModules().Count(item => item.Module != null && item.Module.Enabled);
            int missing = style.EnumerateModules().Count(item => item.Module == null || item.Module.Prefab == null);
            EditorGUILayout.HelpBox($"模块总数 {total} / 启用 {enabled} / 缺失 Prefab {missing}",
                missing == 0 ? MessageType.Info : MessageType.Error);

            using (new EditorGUILayout.HorizontalScope())
            {
                if (GUILayout.Button("定位首个缺失模块")) PingFirstMissing(style);
            }
            using (new EditorGUILayout.HorizontalScope())
            {
                if (GUILayout.Button("Validate")) LogValidation(style);
                if (GUILayout.Button("Compile Preview")) CompilePreview(style);
            }
        }

        private static void DrawRules(SerializedProperty rules, string layer)
        {
            rules.isExpanded = EditorGUILayout.Foldout(rules.isExpanded, "默认生成规则", true);
            if (!rules.isExpanded) return;
            EditorGUI.indentLevel++;
            void Field(string name, string label) => EditorGUILayout.PropertyField(
                rules.FindPropertyRelative(name), new GUIContent(label), true);
            if (layer == "_ground")
            {
                var use = rules.FindPropertyRelative("groundUse");
                use.intValue = EditorGUILayout.Popup("首层用途", use.intValue, new[] { "自动", "住宅", "商业", "混合" });
                Field("shopfrontRatio", "铺面比例");
            }
            if (layer != "_roof")
            {
                var mode = rules.FindPropertyRelative("layoutMode");
                mode.intValue = EditorGUILayout.Popup("布局模式", mode.intValue, new[] { "自动", "随机范围", "手动数量" });
                var rhythm = rules.FindPropertyRelative("rhythm");
                rhythm.intValue = EditorGUILayout.Popup("立面节奏", rhythm.intValue, new[] { "自动", "均匀", "交替", "中央强调", "成对" });
                foreach (var pair in new[] { ("entrance", "入口"), ("shopDoor", "铺门"),
                             ("shopfront", "铺面"), ("window", "窗"), ("blank", "空白") })
                {
                    if (layer == "_upper" && (pair.Item1 is "entrance" or "shopDoor" or "shopfront")) continue;
                    Field(pair.Item1 + "Min", pair.Item2 + "最少数量");
                    Field(pair.Item1 + "Max", pair.Item2 + "最多数量");
                }
            }
            else { Field("roofEnabled", "生成屋顶"); Field("parapetHeight", "女儿墙高度 (m)"); }
            Field("trimEnabled", "启用柱 / 腰线 / 檐口");
            Field("attachmentsEnabled", "启用本层配件"); Field("density", "本层配件密度");
            foreach (var pair in new[] { ("awning", "雨棚"), ("sign", "招牌"), ("fireEscape", "消防梯"),
                         ("wallAC", "空调"), ("roofProps", "屋顶配件") })
            {
                if (layer == "_roof" ? pair.Item1 != "roofProps" : pair.Item1 == "roofProps") continue;
                var attachment = rules.FindPropertyRelative(pair.Item1);
                attachment.isExpanded = EditorGUILayout.Foldout(attachment.isExpanded, pair.Item2, true);
                if (!attachment.isExpanded) continue;
                EditorGUI.indentLevel++;
                foreach (var option in new[] { ("enabled", "启用"), ("density", "密度"),
                             ("maxCount", "数量上限"), ("facades", "适用立面") })
                    EditorGUILayout.PropertyField(attachment.FindPropertyRelative(option.Item1), new GUIContent(option.Item2));
                EditorGUI.indentLevel--;
            }
            EditorGUI.indentLevel--;
        }

        private static void PingFirstMissing(StreetBuildingStyleConfig style)
        {
            var missing = style.EnumerateLayerModules().Where(item => item.Module == null || item.Module.Prefab == null).ToArray();
            if (missing.Length == 0) Debug.Log("StyleConfig 没有缺失 Prefab。", style);
            else Debug.LogWarning($"StyleConfig 缺失 Prefab：{missing[0].Floor}/{missing[0].Group}，共 {missing.Length} 项。", style);
        }

        private static void LogValidation(StreetBuildingStyleConfig style)
        {
            StreetBuildingStyleValidationReport report = StreetBuildingStyleValidator.Validate(style);
            if (report.IsValid) Debug.Log(report, style); else Debug.LogError(report, style);
        }

        private static void CompilePreview(StreetBuildingStyleConfig style)
        {
            try
            {
                StreetBuildingCompiledStyle result = StreetBuildingStyleCompiler.Compile(style);
                Debug.Log($"Style payload compile PASS: {result.ModuleCount} modules / SHA-256 {result.Sha256}\n{result.Payload}", style);
            }
            catch (Exception exception) { Debug.LogError("Style payload compile failed.\n" + exception, style); }
        }
    }
}
#endif
