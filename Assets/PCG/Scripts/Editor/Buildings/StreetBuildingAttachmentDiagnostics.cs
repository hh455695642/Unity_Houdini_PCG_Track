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
                ["maximum_truncated"]="数量上限截断",["none"]="无阻止原因" };
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
