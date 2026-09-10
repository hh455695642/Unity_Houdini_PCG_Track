#if UNITY_EDITOR
using System;
using System.Linq;
using System.Collections.Generic;
using PCGBike.Buildings;
using UnityEditor;
using UnityEngine;

namespace PCGBike.Editor.Buildings
{
    [CustomEditor(typeof(StreetBuildingStyleConfig))]
    public sealed class StreetBuildingStyleConfigEditor : UnityEditor.Editor
    {
        private readonly HashSet<string> _advanced = new();
        private string _auditReport;
        private bool _audited;
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
                int count = StreetBuildingModuleAuthoring.Lists.Sum(n => layer.FindPropertyRelative(n).arraySize);
                layer.isExpanded = EditorGUILayout.Foldout(layer.isExpanded, $"{label} · {count} 个模块", true);
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
                    DrawModules(list, property, field.Item1, field.Item2);
                }
                DrawRules(layer.FindPropertyRelative("_rules"), property);
                EditorGUI.indentLevel--;
            }
            if (serializedObject.ApplyModifiedProperties()) _audited = false;

            StreetBuildingStyleConfig style = (StreetBuildingStyleConfig)target;
            int total = style.EnumerateModules().Count();
            int enabled = style.EnumerateModules().Count(item => item.Module != null && item.Module.Enabled);
            int missing = style.EnumerateModules().Count(item => item.Module == null || (item.Module.Enabled && item.Module.Prefab == null));
            EditorGUILayout.HelpBox($"模块总数 {total} / 启用 {enabled} / 启用但缺失 Prefab {missing}",
                missing == 0 ? MessageType.Info : MessageType.Error);

            using (new EditorGUILayout.HorizontalScope())
            {
                if (GUILayout.Button("定位首个缺失模块")) PingFirstMissing(style);
            }
            using (new EditorGUILayout.HorizontalScope())
            {
                if (GUILayout.Button("校验配置")) LogValidation(style);
                if (GUILayout.Button("查看编译结果")) CompilePreview(style);
            }
            if (GUILayout.Button("配置审计（只读）")) Audit();
            if (!string.IsNullOrEmpty(_auditReport))
                EditorGUILayout.HelpBox(_auditReport, MessageType.Info);
            using (new EditorGUI.DisabledScope(!_audited))
                if (GUILayout.Button("修复可确定的问题（支持撤销）"))
                {
                    int fixedCount = StreetBuildingModuleAuthoring.Repair(serializedObject);
                    Audit();
                    _auditReport = $"已修复 {fixedCount} 项；未自动保存。\n" + _auditReport;
                }
        }

        private void Audit()
        {
            serializedObject.Update();
            var issues = StreetBuildingModuleAuthoring.Audit(serializedObject);
            _auditReport = issues.Count == 0 ? "未发现配置问题。" : string.Join("\n", issues.Select(x =>
                $"{x.Path}: {x.Message}" + (x.Fix != null ? " [可修复]" : " [需手动处理]")));
            _audited = true;
        }

        private void DrawModules(SerializedProperty list, string layer, string group, string label)
        {
            int[] roles = StreetBuildingModuleAuthoring.Roles(layer, group);
            list.isExpanded = EditorGUILayout.Foldout(list.isExpanded, $"{label} ({list.arraySize})", true);
            if (!list.isExpanded) return;
            float cell = serializedObject.FindProperty("_cellWidth").floatValue;
            for (int i = 0; i < list.arraySize; i++)
            {
                var e = list.GetArrayElementAtIndex(i);
                var prefab = e.FindPropertyRelative("_prefab");
                var role = e.FindPropertyRelative("_moduleRole");
                var width = e.FindPropertyRelative("_widthSpan");
                var weight = e.FindPropertyRelative("_weight");
                var enabled = e.FindPropertyRelative("_enabled");
                using (new EditorGUILayout.VerticalScope(EditorStyles.helpBox))
                {
                    using (new EditorGUILayout.HorizontalScope())
                    {
                        // 标题行使用独立矩形，避免父级缩进与 Foldout 左侧箭头挤进勾选框。
                        Rect header = EditorGUILayout.GetControlRect();
                        using (new EditorGUI.IndentLevelScope(-EditorGUI.indentLevel))
                        {
                            EditorGUI.PropertyField(new Rect(header.x, header.y, 18, header.height),
                                enabled, new GUIContent(string.Empty, "参与生成"));
                            Rect foldout = new Rect(header.x + 40, header.y,
                                Mathf.Max(0, header.width - 40), header.height);
                            e.isExpanded = EditorGUI.Foldout(foldout, e.isExpanded,
                                prefab.objectReferenceValue != null ? prefab.objectReferenceValue.name : "未指定 Prefab", true);
                        }
                        using (new EditorGUI.DisabledScope(i == 0))
                            if (GUILayout.Button("↑", GUILayout.Width(24))) { list.MoveArrayElement(i, i - 1); break; }
                        using (new EditorGUI.DisabledScope(i == list.arraySize - 1))
                            if (GUILayout.Button("↓", GUILayout.Width(24))) { list.MoveArrayElement(i, i + 1); break; }
                        if (GUILayout.Button("−", GUILayout.Width(24))) { list.DeleteArrayElementAtIndex(i); break; }
                    }
                    EditorGUILayout.LabelField($"{StreetBuildingModuleAuthoring.RoleName(role.intValue)} · 宽 {width.intValue} 格 ({width.intValue * cell:0.##}m) · 权重 {weight.floatValue:0.##}" +
                        (enabled.boolValue ? "" : " · 已停用"), EditorStyles.miniLabel);
                    if (!roles.Contains(role.intValue))
                        EditorGUILayout.HelpBox("当前用途不属于本分组，已有值已保留。请选择有效用途或手动调整所属分组。", MessageType.Warning);
                    if (!e.isExpanded) continue;
                    EditorGUILayout.PropertyField(prefab, new GUIContent("模块 Prefab", "参与生成的 Prefab 或 FBX Model Prefab。复合几何在 Prefab 内组织。"));
                    Popup(role, "模块用途", roles, StreetBuildingModuleAuthoring.RoleName);
                    EditorGUILayout.PropertyField(width, new GUIContent("横向占用格数", "模块在立面横向占用的网格数量；实际宽度 = 格数 × 单元宽度。"));
                    EditorGUILayout.PropertyField(weight, new GUIContent("随机选中权重", "同层、同用途且满足尺寸与立面条件的候选项之间的相对权重。不是生成数量或百分比。"));
                    string key = e.propertyPath;
                    bool expanded = EditorGUILayout.Foldout(_advanced.Contains(key), "高级约束", true);
                    if (expanded) _advanced.Add(key); else _advanced.Remove(key);
                    if (!expanded) continue;
                    var height = e.FindPropertyRelative("_heightType");
                    string[] heights = { "跟随首层高度", "跟随标准层高度", "固定高度", "使用 Prefab 包围盒" };
                    Popup(height, "高度适配方式", StreetBuildingModuleAuthoring.Heights(layer, role.intValue),
                        v => v >= 0 && v < heights.Length ? heights[v] : $"未知 ({v})");
                    if (height.intValue == 2)
                        EditorGUILayout.PropertyField(e.FindPropertyRelative("_absoluteHeight"), new GUIContent("固定高度 (m)", "声明模块高度，用于尺寸校验与候选匹配；不表示自动缩放模型。"));
                    else
                        EditorGUILayout.LabelField("高度来源", height.intValue == 3 ? "模型自身包围盒" :
                            serializedObject.FindProperty((height.intValue == 0 ? "_ground" : "_upper") + "._height").floatValue.ToString("0.##") + " m");
                    if (role.intValue is not (18 or 19 or 9 or 20 or 21))
                        DrawFacades(e.FindPropertyRelative("_allowedFacades"), StreetBuildingModuleAuthoring.Facades(role.intValue));
                    else EditorGUILayout.LabelField("放置范围", "屋顶（由所在分组决定）");
                    using (new EditorGUI.DisabledScope(true))
                        EditorGUILayout.PropertyField(e.FindPropertyRelative("_depthSpan"),
                            new GUIContent("进深占格（预留）", "保留旧数据兼容；当前面板不提供编辑。此字段不是模型厚度。"));
                }
            }
            using (new EditorGUI.DisabledScope(roles.Length == 0))
                if (GUILayout.Button("添加" + label + "模块"))
                {
                    int index = list.arraySize;
                    list.InsertArrayElementAtIndex(index);
                    var entry = list.GetArrayElementAtIndex(index);
                    StreetBuildingModuleAuthoring.Initialize(entry, layer, roles[0]);
                    entry.isExpanded = true;
                }
        }

        private static void Popup(SerializedProperty property, string label, int[] values, Func<int, string> name)
        {
            // 未知旧值保留为可见项；只在明确交互后写入，避免 Repaint 隐式迁移。
            var options = values.Contains(property.intValue) ? values : new[] { property.intValue }.Concat(values).ToArray();
            var labels = options.Select(v => new GUIContent(name(v) + (values.Contains(v) ? "" : "（旧值，需调整）"),
                property.name == "_moduleRole" ? ((StreetBuildingModuleRole)v).ToString() : name(v))).ToArray();
            EditorGUI.BeginChangeCheck();
            int index = EditorGUILayout.Popup(new GUIContent(label), Array.IndexOf(options, property.intValue), labels);
            if (EditorGUI.EndChangeCheck() && index >= 0) property.intValue = options[index];
        }

        internal static void DrawFacades(SerializedProperty property, int allowed)
        {
            string[] labels = { "主正面", "次正面", "侧面", "背面" };
            EditorGUILayout.LabelField(new GUIContent("可用立面", "限制候选模块可放置的立面；实际生成还受用途与生成规则约束。"));
            for (int bit = 0; bit < 4; bit++)
            {
                int flag = 1 << bit;
                if ((allowed & flag) == 0) continue;
                EditorGUI.BeginChangeCheck();
                bool value = EditorGUILayout.ToggleLeft(labels[bit], (property.intValue & flag) != 0);
                if (EditorGUI.EndChangeCheck()) property.intValue = value ? property.intValue | flag : property.intValue & ~flag;
            }
            if ((property.intValue & allowed) == 0 || (property.intValue & ~allowed) != 0)
                EditorGUILayout.HelpBox("已有立面范围与用途不匹配。配置审计可列出可修复项。", MessageType.Warning);
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
                if (layer == "_ground" && (pair.Item1 is "fireEscape" or "wallAC")) continue;
                var attachment = rules.FindPropertyRelative(pair.Item1);
                attachment.isExpanded = EditorGUILayout.Foldout(attachment.isExpanded, pair.Item2, true);
                if (!attachment.isExpanded) continue;
                EditorGUI.indentLevel++;
                foreach (var option in new[] { ("enabled", "启用"), ("density", "密度"),
                             ("maxCount", "数量上限"), ("facades", "适用立面") })
                {
                    if (option.Item1 == "facades")
                    {
                        if (layer != "_roof") DrawFacades(attachment.FindPropertyRelative(option.Item1),
                            pair.Item1 is "awning" or "sign" ? 3 : pair.Item1 == "fireEscape" ? 8 : 12);
                    }
                    else EditorGUILayout.PropertyField(attachment.FindPropertyRelative(option.Item1), new GUIContent(option.Item2));
                }
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
