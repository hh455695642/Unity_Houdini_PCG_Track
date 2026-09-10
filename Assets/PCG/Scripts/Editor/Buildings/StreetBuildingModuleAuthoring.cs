#if UNITY_EDITOR
using System;
using System.Collections.Generic;
using System.Linq;
using UnityEditor;
using UnityEngine;

namespace PCGBike.Editor.Buildings
{
    // Editor-only 扩展点：集中定义分组菜单；不改枚举数值、载荷或运行时逻辑。
    public static class StreetBuildingModuleAuthoring
    {
        public static readonly string[] Lists = { "_facade", "_sideRear", "_corners", "_trim", "_roofSurface", "_attachments" };
        public static readonly string[] Names = { "商铺立面", "店铺门", "首层实墙", "建筑主入口", "标准层窗", "标准层实墙",
            "建筑阳角", "建筑阴角", "檐口", "女儿墙", "侧墙", "背墙", "立面柱", "层间腰线",
            "雨棚", "招牌", "消防梯", "外墙空调", "屋顶设备", "屋面板", "女儿墙阳角", "女儿墙阴角" };
        public static string RoleName(int role) => role >= 0 && role < Names.Length ? Names[role] : $"未知用途 ({role})";
        public static int[] Roles(string layer, string list) => list switch {
            "_facade" => layer == "_ground" ? new[] { 3, 0, 1, 2 } : layer == "_upper" ? new[] { 4, 5 } : Array.Empty<int>(),
            "_sideRear" => layer == "_roof" ? Array.Empty<int>() : new[] { 10, 11 },
            "_corners" => layer == "_roof" ? Array.Empty<int>() : new[] { 6, 7 },
            "_trim" => layer == "_roof" ? new[] { 8 } : new[] { 12, 13, 8 },
            "_roofSurface" => layer == "_roof" ? new[] { 19, 9, 20, 21 } : Array.Empty<int>(),
            "_attachments" => layer == "_roof" ? new[] { 18 } : layer == "_ground" ? new[] { 14, 15 } : new[] { 14, 15, 16, 17 },
            _ => Array.Empty<int>() };
        public static int Facades(int role) => role switch {
            0 or 1 or 3 or 14 or 15 => 3, 10 => 4, 11 or 16 => 8, 17 => 12, _ => 15 };
        public static int DefaultHeight(string layer, int role) =>
            role >= 14 && role <= 18 ? 3 : role is 8 or 9 or 13 or 19 or 20 or 21 ? 2 : layer == "_ground" ? 0 : 1;
        public static int[] Heights(string layer, int role) => role >= 14 && role <= 18 ? new[] { 3 } :
            layer == "_roof" ? new[] { 2, 3 } : new[] { layer == "_ground" ? 0 : 1, 2, 3 };
        public static void Initialize(SerializedProperty entry, string layer, int role)
        {
            entry.FindPropertyRelative("_prefab").objectReferenceValue = null;
            entry.FindPropertyRelative("_moduleRole").intValue = role;
            entry.FindPropertyRelative("_widthSpan").intValue = 1;
            entry.FindPropertyRelative("_depthSpan").intValue = 1;
            entry.FindPropertyRelative("_heightType").intValue = DefaultHeight(layer, role);
            entry.FindPropertyRelative("_absoluteHeight").floatValue = 1;
            entry.FindPropertyRelative("_weight").floatValue = 1;
            entry.FindPropertyRelative("_enabled").boolValue = true;
            entry.FindPropertyRelative("_allowedFacades").intValue = Facades(role);
            entry.FindPropertyRelative("_allowedFloors").intValue = layer == "_ground" ? 1 : layer == "_upper" ? 2 : 4;
        }
        public sealed class Issue
        {
            public string Path, Message;
            public Action<SerializedObject> Fix;
        }
        // 审计无写入。无法确定用户意图的角色、Prefab 或高度问题只报告，不猜测替换。
        public static List<Issue> Audit(SerializedObject data)
        {
            var issues = new List<Issue>();
            foreach (string layer in new[] { "_ground", "_upper", "_roof" })
            foreach (string listName in Lists)
            {
                var list = data.FindProperty(layer + "." + listName);
                for (int i = 0; i < list.arraySize; i++)
                {
                    var e = list.GetArrayElementAtIndex(i);
                    string path = e.propertyPath;
                    void Report(string message) => issues.Add(new Issue { Path = path, Message = message });
                    void IntFix(string field, int value, string message) => issues.Add(new Issue {
                        Path = path, Message = message, Fix = so => so.FindProperty(path + "." + field).intValue = value });
                    int role = e.FindPropertyRelative("_moduleRole").intValue;
                    bool enabled = e.FindPropertyRelative("_enabled").boolValue;
                    if (!Roles(layer, listName).Contains(role)) Report("用途不属于此层/分组，请手动选择或移动。");
                    if (enabled && e.FindPropertyRelative("_prefab").objectReferenceValue == null) Report("参与生成但缺少 Prefab。");
                    foreach (string field in new[] { "_widthSpan", "_depthSpan" })
                        if (e.FindPropertyRelative(field).intValue < 1) IntFix(field, 1, field == "_widthSpan" ? "横向占格不足 1 → 1。" : "进深占格不足 1 → 1（与现有编译钳制一致）。");
                    float weight = e.FindPropertyRelative("_weight").floatValue;
                    if (weight <= 0 || float.IsNaN(weight) || float.IsInfinity(weight)) Report("权重必须是有限正数，请明确填写。");
                    int height = e.FindPropertyRelative("_heightType").intValue;
                    if (!Heights(layer, role).Contains(height)) Report("高度模式跨层或不适用于此用途，请手动选择。");
                    float absolute = e.FindPropertyRelative("_absoluteHeight").floatValue;
                    if (height == 2 && (!(absolute > 0) || float.IsInfinity(absolute))) Report("固定高度必须是有限正数。");
                    int mask = e.FindPropertyRelative("_allowedFacades").intValue;
                    int intersection = mask & Facades(role);
                    if (intersection == 0) Report("可用立面与用途无交集，请手动选择。");
                    else if (intersection != mask) IntFix("_allowedFacades", intersection, $"立面包含此用途不使用的方向：{mask} → {intersection}。");
                    int floor = layer == "_ground" ? 1 : layer == "_upper" ? 2 : 4;
                    if (e.FindPropertyRelative("_allowedFloors").intValue != floor)
                        IntFix("_allowedFloors", floor, "隐藏楼层标记与所属层不一致 → 按所属层同步。");
                }
            }
            return issues;
        }
        public static int Repair(SerializedObject data)
        {
            data.Update();
            var fixes = Audit(data).Where(x => x.Fix != null).ToArray();
            if (fixes.Length == 0) return 0;
            Undo.RecordObject(data.targetObject, "修复建筑模块配置");
            foreach (var issue in fixes) issue.Fix(data);
            data.ApplyModifiedProperties();
            return fixes.Length;
        }
    }
}
#endif
