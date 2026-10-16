#if UNITY_EDITOR
using System;
using System.Collections.Generic;
using System.Globalization;
using System.Linq;
using UnityEditor;
using UnityEngine;

namespace PCGBike.Editor.Buildings
{
    internal static class StreetBuildingFacadeDiagram
    {
        internal readonly struct Segment
        {
            public readonly int Face, Target, Cells;
            public readonly string Role;
            public readonly Vector2 A, B;
            public Segment(int face, int target, string role, Vector2 a, Vector2 b, int cells)
            { Face = face; Target = target; Role = role; A = a; B = b; Cells = cells; }
        }
        internal static readonly string[] Targets = { "正面", "次正面", "侧面（左、右）", "背面" };
        internal static List<Segment> Parse(string report)
        {
            var result = new List<Segment>();
            if (string.IsNullOrEmpty(report) || !report.StartsWith("v1\n", StringComparison.Ordinal)) return result;
            foreach (var line in report.Split('\n').Skip(1))
            {
                var f = line.Split('|');
                if (f.Length != 8 || !int.TryParse(f[0], out int face) || !int.TryParse(f[1], out int target)
                    || !int.TryParse(f[7], out int cells) || face < 0 || face > 3 || target < 0 || target > 3 || cells < 1) continue;
                var numbers = new float[4]; bool valid = true;
                for (int i = 0; i < 4; i++) valid &= float.TryParse(f[3 + i], NumberStyles.Float, CultureInfo.InvariantCulture, out numbers[i])
                    && !float.IsNaN(numbers[i]) && !float.IsInfinity(numbers[i]);
                if (!valid) continue;
                var a = new Vector2(numbers[0], numbers[1]); var b = new Vector2(numbers[2], numbers[3]);
                if ((b - a).sqrMagnitude > .0001f) result.Add(new Segment(face, target, f[2], a, b, cells));
            }
            return result;
        }

        // 只用于无成功输出时的明确标注示意；不会作为数量、挂点或生成判断的依据。
        internal static List<Segment> Preview(float width, float depth, int shape, float nw, float nd, int side)
        {
            width = Mathf.Max(.1f, width); depth = Mathf.Max(.1f, depth);
            nw = Mathf.Clamp(nw, .01f, width - .01f); nd = Mathf.Clamp(nd, .01f, depth - .01f);
            float left = -width * .5f, right = width * .5f;
            var segments = new List<Segment>();
            void Add(int face, int target, string role, float ax, float az, float bx, float bz) =>
                segments.Add(new Segment(face, target, role, new Vector2(ax, az), new Vector2(bx, bz), 1));
            Add(0, 0, "front", left + (shape == 1 && side == 2 ? nw : 0), 0, right - (shape == 1 && side == 3 ? nw : 0), 0);
            if (shape == 0)
            {
                Add(1, 2, "left", left, -depth, left, 0); Add(2, 2, "right", right, 0, right, -depth);
                Add(3, 3, "rear", right, -depth, left, -depth); return segments;
            }
            Add(1, 2, "left", left, -depth + (side == 0 ? nd : 0), left, side == 2 ? -nd : 0);
            Add(2, 2, "right", right, side == 3 ? -nd : 0, right, -depth + (side == 1 ? nd : 0));
            if (side < 2)
            {
                Add(3, 3, "rear", right - (side == 1 ? nw : 0), -depth, left + (side == 0 ? nw : 0), -depth);
                Add(side == 0 ? 1 : 2, 2, "notch_inner", side == 0 ? left + nw : right - nw, -depth,
                    side == 0 ? left + nw : right - nw, -depth + nd);
                Add(3, 3, "notch_rear", side == 0 ? left : right - nw, -depth + nd, side == 0 ? left + nw : right, -depth + nd);
            }
            else
            {
                Add(3, 3, "rear", right, -depth, left, -depth);
                Add(0, 1, "secondary_front", side == 2 ? left : right - nw, -nd, side == 2 ? left + nw : right, -nd);
                Add(side == 2 ? 1 : 2, 2, "notch_inner", side == 2 ? left + nw : right - nw, -nd,
                    side == 2 ? left + nw : right - nw, 0);
            }
            return segments;
        }

        internal static bool Covered(Segment s, int selectedTarget) => s.Target == selectedTarget;
        internal static bool SharedQuota(Segment s, int selectedFace) => selectedFace >= 0 && s.Face == selectedFace;
        internal static string RoleLabel(string role) => role == "secondary_front" ? "次正面" : role == "notch_inner" ? "凹口内壁"
            : role == "notch_rear" ? "凹口后墙" : role == "front" ? "正面" : role == "rear" ? "背面" : role == "left" ? "左侧" : "右侧";

        internal static void Draw(Rect rect, List<Segment> segments, ref int selectedTarget, ref int selectedFace)
        {
            EditorGUI.DrawRect(rect, new Color(.12f, .14f, .16f));
            if (segments.Count == 0) { GUI.Label(rect, "尚无可显示的墙段"); return; }
            float minX = segments.Min(s => Mathf.Min(s.A.x, s.B.x)), maxX = segments.Max(s => Mathf.Max(s.A.x, s.B.x));
            float minZ = segments.Min(s => Mathf.Min(s.A.y, s.B.y)), maxZ = segments.Max(s => Mathf.Max(s.A.y, s.B.y));
            float scale = Mathf.Min((rect.width - 100) / Mathf.Max(.01f, maxX - minX), (rect.height - 80) / Mathf.Max(.01f, maxZ - minZ));
            Vector2 center = rect.center, worldCenter = new((minX + maxX) * .5f, (minZ + maxZ) * .5f);
            // 显示和命中判定共用映射：仅上下翻转，立面 ID 与左右方向保持不变。
            Vector2 Screen(Vector2 p) => center + new Vector2(p.x - worldCenter.x, p.y - worldCenter.y) * scale;
            GUI.Label(new Rect(rect.x + 12, rect.y + 8, rect.width - 24, 20), "正面朝下 ↓    左 / 右为建筑自身方向");
            Handles.BeginGUI(); var old = Handles.color;
            foreach (var s in segments)
            {
                var a = Screen(s.A); var b = Screen(s.B);
                Handles.color = Covered(s, selectedTarget) ? new Color(.3f, .85f, .65f) : new Color(.55f, .6f, .65f);
                Handles.DrawAAPolyLine(Covered(s, selectedTarget) ? 5 : 2, a, b);
                if (SharedQuota(s, selectedFace))
                {
                    var offset = Vector2.Perpendicular((b - a).normalized) * 7;
                    Handles.color = new Color(1, .65f, .2f); Handles.DrawAAPolyLine(2, a + offset, b + offset);
                }
                var midpoint = (a + b) * .5f;
                if (s.Role.Contains("notch") || s.Role == "secondary_front")
                    GUI.Label(new Rect(midpoint.x + 7, midpoint.y + 3, 100, 20), RoleLabel(s.Role), EditorStyles.miniLabel);
                if (Event.current.type == EventType.MouseDown && Event.current.button == 0 && rect.Contains(Event.current.mousePosition)
                    && Distance(Event.current.mousePosition, a, b) < 10)
                { selectedTarget = s.Target; selectedFace = s.Face; Event.current.Use(); GUI.changed = true; }
            }
            Handles.color = old; Handles.EndGUI();
            GUI.Label(new Rect(rect.x + 5, center.y - 10, 42, 20), "左侧");
            GUI.Label(new Rect(rect.xMax - 43, center.y - 10, 42, 20), "右侧");
            GUI.Label(new Rect(center.x - 22, rect.y + 28, 50, 20), "背面");
            GUI.Label(new Rect(center.x - 22, rect.yMax - 27, 50, 20), "正面");
        }
        private static float Distance(Vector2 p, Vector2 a, Vector2 b) => Vector2.Distance(p, a + (b - a) * Mathf.Clamp01(Vector2.Dot(p - a, b - a) / (b - a).sqrMagnitude));
    }
}
#endif
