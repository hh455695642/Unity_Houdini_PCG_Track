#if UNITY_EDITOR
using System;
using System.Collections.Generic;
using System.Globalization;
using System.Text;

namespace PCGBike.Editor.Buildings
{
    // 只解析成功输出；扩展点是 metadata 版本，不能在此重新分配数量或计算挂点。
    internal sealed class StreetBuildingAttachmentDiagnostics
    {
        internal sealed class Row
        {
            internal int Kind, Band, RequestedLimit, EffectiveLimit, EligibleHosts, Actual;
            internal string Source, Reasons, Probability, EffectiveProbability, FloorStart, FloorEnd, FaceMask, Materials, MatchingMaterials, SampledHits;
            private string text;
            internal int CapacityUpperBound => Math.Max(0, Math.Min(EffectiveLimit, EligibleHosts));
            internal string Text => text ??= $"{Bands[Band]}：基础上限 {RequestedLimit}；覆盖后上限 {EffectiveLimit}；合格挂点 {EligibleHosts}；容量上界 {CapacityUpperBound}；实际 {Actual}\n基础概率 {Probability}；生效概率 {EffectiveProbability}；命中 {SampledHits}\n楼层 {FloorStart}～{FloorEnd}；立面掩码 {FaceMask}；素材 {Materials}／适用 {MatchingMaterials}\n来源：{SourceLabel(Source)}\n原因：{ReasonLabel(Reasons)}";
        }
        internal static readonly string[] Names = { "雨棚", "招牌", "消防梯", "墙面空调", "屋顶附件" };
        internal static readonly string[] Bands = { "首层", "标准层", "屋顶" };
        internal readonly List<Row> Rows = new();
        internal string Error, Global;
        private string formatted;
        internal sealed class ReferenceRow
        {
            internal string Kind, Reasons, Source;
            internal int Requested, Actual;
            internal string Label => Kind switch { "WaterTower" => "水塔", "Chimney" => "烟囱", "FireEscape" => "连续消防梯组", "DrainPipe" => "完整落水管", _ => Kind };
            internal string Text => $"{Label}：请求 {Requested}；实际 {Actual}；单位：{(Kind == "FireEscape" ? "组" : Kind == "DrainPipe" ? "条" : "件")}\n来源：{SourceLabel(Source)}；原因：{ReasonLabel(Reasons)}";
        }
        internal sealed class ReferenceReport
        {
            internal string Error;
            internal readonly List<ReferenceRow> Rows = new();
        }
        internal static ReferenceReport ParseReference(string report)
        {
            var result = new ReferenceReport();
            if (string.IsNullOrEmpty(report) || !report.StartsWith("v1\n", StringComparison.Ordinal))
            { result.Error = "固定附件诊断不可确认：缺少记录或不支持的版本。"; return result; }
            var seen = new HashSet<string>(StringComparer.Ordinal);
            foreach (string line in report.Split('\n'))
            {
                if (line == "v1" || string.IsNullOrWhiteSpace(line)) continue;
                var fields = line.Split('|');
                if (fields.Length != 6 || fields[0] != "R"
                    || !(fields[1] is "WaterTower" or "Chimney" or "FireEscape" or "DrainPipe")
                    || !int.TryParse(fields[2], NumberStyles.Integer, CultureInfo.InvariantCulture, out int requested)
                    || !int.TryParse(fields[3], NumberStyles.Integer, CultureInfo.InvariantCulture, out int actual)
                    || requested < 0 || actual < 0 || actual > requested || string.IsNullOrEmpty(fields[4])
                    || string.IsNullOrEmpty(fields[5]) || !seen.Add(fields[1]))
                { result.Error = "固定附件诊断不可确认：记录格式损坏、重复或实际数量超过请求。"; continue; }
                result.Rows.Add(new ReferenceRow { Kind = fields[1], Requested = requested, Actual = actual, Reasons = fields[4], Source = fields[5] });
            }
            if (seen.Count != 4 && result.Error == null) result.Error = "固定附件诊断不可确认：缺少部分子类型记录。";
            return result;
        }
        internal static string FormatReference(string report)
        {
            var parsed = ParseReference(report);
            var text = new StringBuilder();
            if (parsed.Error != null) text.AppendLine(parsed.Error);
            foreach (var row in parsed.Rows) text.AppendLine(row.Text);
            return text.ToString().TrimEnd();
        }
        internal static StreetBuildingAttachmentDiagnostics Parse(string report)
        {
            var result = new StreetBuildingAttachmentDiagnostics();
            if (string.IsNullOrEmpty(report) || !report.StartsWith("v1\n", StringComparison.Ordinal))
            { result.Error = "诊断不可确认：缺少记录或不支持的版本。"; return result; }
            var seen = new HashSet<int>();
            foreach (string line in report.Split('\n'))
            {
                if (line == "v1" || string.IsNullOrWhiteSpace(line)) continue;
                var f = line.Split('|');
                if (f.Length == 6 && f[0] == "G")
                { result.Global = $"全局附件密度：基础 {f[1]}，生效 {f[2]}；来源 {SourceLabel(f[3])}；附件开关：基础 {f[4]}，生效 {f[5]}"; continue; }
                var values = new int[11]; int[] indices = { 0, 1, 3, 5, 7, 8, 9, 10, 11, 12, 14 };
                bool valid = f.Length == 16;
                if (valid) for (int i = 0; i < indices.Length; i++) valid &= int.TryParse(f[indices[i]], NumberStyles.Integer, CultureInfo.InvariantCulture, out values[i]);
                if (!valid || values[0] < 0 || values[0] > 4 || values[1] < 0 || values[1] > 2
                    || values[2] < 0 || values[3] < 0 || values[9] < 0 || values[10] < 0 || !seen.Add(values[0] * 3 + values[1]))
                { result.Error = "诊断不可确认：记录格式损坏或重复。"; continue; }
                result.Rows.Add(new Row { Kind=values[0],Band=values[1],RequestedLimit=values[2],EffectiveLimit=values[3],
                    EligibleHosts=values[9],Actual=values[10],Source=f[6],Reasons=f[15],Probability=f[2],EffectiveProbability=f[4],
                    FaceMask=f[7],FloorStart=f[8],FloorEnd=f[9],Materials=f[10],MatchingMaterials=f[11],SampledHits=f[13] });
            }
            if (seen.Count != 15) result.Error = "诊断不可确认：缺少部分附件或楼层记录。";
            return result;
        }
        internal static string SourceLabel(string source) => source == "instance" ? "基础参数"
            : source.StartsWith("attachment_override:", StringComparison.Ordinal) ? "附件覆盖第" + source.Substring(20) + "条"
            : source.StartsWith("parcel_global:", StringComparison.Ordinal) ? "地块全局覆盖第" + source.Substring(14) + "行"
            : source.StartsWith("parcel:", StringComparison.Ordinal) ? "地块覆盖第" + source.Substring(7) + "条" : source;
        internal static string ReasonLabel(string reasons)
        {
            var known = new Dictionary<string, string> {
                ["attachments_disabled"]="附件关闭",["probability_zero"]="概率为零",["maximum_zero"]="上限为零",
                ["no_material"]="缺少素材",["material_scope"]="无适用素材",["scope_restricted"]="楼层或立面范围限制",
                ["rear_facade_condition"]="后立面条件未满足",["floor_condition"]="楼层条件未满足",
                ["no_eligible_host"]="无合格挂点",["random_miss"]="随机未命中",["budget_truncated"]="预算截断",
                ["maximum_truncated"]="数量上限截断",["none"]="无阻止原因",
                ["disabled"]="当前模式或开关关闭",["capacity"]="合法支承空间不足",["floor_range"]="有效楼层范围不足",
                ["height_mismatch"]="素材连接点与实际层高不匹配",["unsupported_roof_access"]="缺少合法屋顶检修连接",
                ["roof_access_floor_range"]="检修梯未延伸到屋顶，整组消防梯已拒绝",
                ["roof_disabled"]="屋顶关闭",["no_face"]="无启用立面",["collision"]="与既有构件冲突" };
            var text = new List<string>();
            foreach (var token in (reasons ?? "").Split(',')) if (token.Length > 0) text.Add(known.TryGetValue(token, out var label) ? label : token);
            return text.Count == 0 ? "原因未提供" : string.Join("、", text);
        }
        internal string Format()
        {
            if (formatted != null) return formatted;
            var text = new StringBuilder();
            if (Error != null) text.AppendLine(Error);
            if (Global != null) text.AppendLine(Global);
            foreach (var row in Rows) text.AppendLine(Names[row.Kind] + " · " + row.Text);
            return formatted = text.ToString().TrimEnd();
        }
    }
}
#endif
