#if UNITY_EDITOR
using System;
using System.Collections.Generic;
using System.Globalization;
using System.Linq;
using System.Text.RegularExpressions;

namespace PCGBike.Editor.Buildings
{
    // 只解释输入差异与可能影响范围；实际配额和优先级仍由 HDA 输出诊断确定。
    internal static class StreetBuildingChangeSummary
    {
        internal sealed class Entry
        {
            public string Area, Label, Before, After, Scope, Source;
            public bool Inactive, Estimated;
            public override string ToString() => $"{Label}：{Before} → {After}；{Scope}；来源：{Source}"
                + (Inactive ? "；当前模式不使用（保留输入）" : "") + (Estimated ? "；范围为预计，上次墙段图不代表当前输入" : "");
        }
        private static readonly Dictionary<string, string> Labels = new()
        {
            ["building_width"]="宽度（格）", ["building_depth"]="进深（格）", ["massing_shape"]="体块形状",
            ["l_notch_width_cells"]="缺口宽度（格）", ["l_notch_depth_cells"]="缺口进深（格）", ["l_notch_side"]="缺口方向",
            ["l_notch_units"]="缺口单位", ["l_notch_width"]="兼容缺口宽度", ["l_notch_depth"]="兼容缺口进深",
            ["floor_count"]="楼层数", ["rear_facade_mode"]="后立面", ["ground_floor_use"]="首层用途",
            ["residential_door_enabled"]="住宅入户门", ["ground_quantity_mode"]="商业门数量模式",
            ["entrance_count_min"]="商业门随机最小值", ["entrance_count_max"]="商业门数量／范围上限",
            ["shopfront_control"]="橱窗控制", ["shopfront_quantity_mode"]="橱窗数量模式", ["shopfront_count"]="橱窗数量",
            ["shopfront_count_min"]="橱窗随机最小值", ["shopfront_count_max"]="橱窗随机最大值", ["shopfront_ratio"]="橱窗占格比例",
            ["ground_rhythm"]="首层排列", ["facade_layout_mode"]="标准层窗数量模式", ["window_count_min"]="窗模块数量／范围下限",
            ["window_count_max"]="窗模块随机最大值", ["facade_rhythm"]="标准层排列", ["roof_enabled"]="屋顶开关",
            ["parapet_enabled"]="女儿墙开关", ["parapet_height"]="女儿墙高度", ["architectural_trim_enabled"]="线脚开关",
            ["corner_building"]="街角建筑", ["corner_street_side"]="首层临街侧面", ["attachments_enabled"]="附件开关",
            ["attachment_global_density"]="附件全局密度", ["ground_attachment_placement"]="雨棚／招牌挂点模式",
            ["variation_seed"]="用途与素材种子", ["layout_seed"]="门位与布局种子", ["site_source_auto"]="地块来源自动判断",
            ["unity_generation_policy"]="区间与候选配置", ["generation_sequence"]="生成序号",
            ["random_algorithm"]="采样算法版本", ["random_seed"]="主随机种子", ["random_feasible"]="采样策略",
            ["random_instance_id"]="实例随机身份", ["random_seq_massing"]="体块方案序号", ["random_seq_ground"]="首层方案序号",
            ["random_seq_upper"]="标准层方案序号", ["random_seq_attachments"]="附件方案序号",
            ["__random_dependencies"]="素材依赖内容", ["__random_generator"]="生成器版本",
            ["site_source"]="地块来源", ["facade_overrides"]="立面覆盖条数", ["attachment_overrides"]="附件覆盖条数",
            ["__material"]="素材规格与候选约束", ["__input0"]="地块输入", ["__input1"]="引导输入"
        };
        private static readonly Dictionary<string, string> Fields = new()
        {
            ["target"]="目标立面", ["floor_start"]="起始楼层", ["floor_end"]="结束楼层", ["layout_mode"]="数量模式",
            ["rhythm"]="排列", ["shopfront_min"]="橱窗数量／范围下限", ["shopfront_max"]="橱窗随机最大值",
            ["window_min"]="窗模块数量／范围下限", ["window_max"]="窗模块随机最大值", ["kind"]="附件类型",
            ["density"]="密度", ["max_count"]="数量上限", ["front"]="正面", ["secondary_front"]="次正面", ["side"]="侧面", ["rear"]="背面"
        };
        private static readonly string[] Targets = { "正面", "次正面", "侧面（左、右）", "背面" };
        private static readonly string[] Kinds = { "雨棚", "招牌", "消防梯", "墙面空调", "屋顶附件" };
        private static readonly string[] KindNames = { "awning", "sign", "fire_escape", "wall_ac", "roof_props" };
        private static int I(Dictionary<string,string> d, string n, int fallback=0) => d.TryGetValue(n, out var v) && int.TryParse(v, out var i) ? i : fallback;
        private static string Pick(string[] values, int i) => i >= 0 && i < values.Length ? values[i] : "未知选项";
        private static string Floors(int start, int end) => start == end ? $"第{start}层" : $"第{start}～{end}层";
        private static string Union(string a, string b) => a == b ? a : $"原范围 {a} → 新范围 {b}（两者均受影响）";
        private static Match Row(string name) => Regex.Match(name, @"^(facade|attachment)_override_(.+?)(\d+)$");

        internal static List<Entry> Build(StreetBuildingPanelResult previous, List<StreetBuildingPanelInput> current, float cellWidth)
        {
            if (previous == null || current == null || current.Count == 0) return new();
            var old = previous.inputs.ToDictionary(r=>r.name,r=>r.value);
            var now = current.ToDictionary(r=>r.name,r=>r.value);
            bool topology = new[] { "building_width", "building_depth", "massing_shape", "l_notch_width_cells", "l_notch_depth_cells", "l_notch_side", "rear_facade_mode", "floor_count", "__input0", "__material" }
                .Any(n=>old.GetValueOrDefault(n)!=now.GetValueOrDefault(n));
            var result = new List<Entry>();
            foreach (var name in old.Keys.Union(now.Keys).OrderBy(n=>n,StringComparer.Ordinal))
            {
                if (old.GetValueOrDefault(name) == now.GetValueOrDefault(name)) continue;
                var row = Row(name);
                if (row.Success && !Fields.ContainsKey(row.Groups[2].Value)) continue; // 退休兼容字段没有生成语义。
                string area = Area(name), label = Labels.GetValueOrDefault(name), scope, source;
                if (row.Success)
                {
                    string kind=row.Groups[1].Value, field=row.Groups[2].Value, index=row.Groups[3].Value;
                    label = (kind=="facade" ? "立面覆盖 " : "附件覆盖 ")+index+" · "+Fields.GetValueOrDefault(field,"覆盖选项");
                    scope=Union(RowScope(old,kind,index),RowScope(now,kind,index));
                    source=(kind=="facade" ? "局部覆盖第" : "附件覆盖第")+index+"条";
                }
                else
                {
                    if (name.StartsWith("shopfront_face_")) label="橱窗适用 · "+Pick(new[]{"正面","左侧","右侧","背面"},int.Parse(name.Substring(name.Length-1)));
                    if (label==null)
                    {
                        int kind=Array.FindIndex(KindNames,k=>name.StartsWith(k+"_",StringComparison.Ordinal));
                        label=kind>=0 ? Kinds[kind]+(name.EndsWith("density") ? "密度" : "数量上限") : "实例选项";
                    }
                    scope=Union(BaseScope(old,name,area),BaseScope(now,name,area));
                    source=name.StartsWith("__") ? "素材／地块输入" : "基础参数";
                    if (area is "首层门窗" or "标准层门窗") source+="（显式局部／地块覆盖可调整；以生成诊断为准）";
                }
                // 数量标签只承担当前模式中的一个名称。
                if (name=="window_count_min") label=I(now,"facade_layout_mode")==0 ? "窗模块数量" : "窗模块随机最小值";
                if (name=="entrance_count_max") label=I(now,"ground_quantity_mode")==0 ? "商业门数量" : "商业门随机最大值";
                if (row.Success && row.Groups[2].Value.EndsWith("_min")) label=label.Replace("数量／范围下限",I(now,"facade_override_layout_mode"+row.Groups[3].Value)==1 ? "随机最小值" : "数量");
                result.Add(new Entry {Area=area,Label=label,Before=Value(old,name,cellWidth),After=Value(now,name,cellWidth),Scope=scope,Source=source,
                    Inactive=now.ContainsKey(name)&&!Active(now,name),Estimated=topology});
                if (name.StartsWith("__")) { result[result.Count-1].Before="上次输入"; result[result.Count-1].After="当前输入"; }
            }
            return result;
        }

        private static string Value(Dictionary<string,string> d,string name,float cellWidth)
        {
            if(!d.TryGetValue(name,out var v))return "未设置／已移除";
            if(name=="unity_generation_policy")return "配置已记录";
            if(name.StartsWith("__"))return "输入已记录";
            if(name is "building_width" or "building_depth")
            {
                var m=Regex.Match(d.GetValueOrDefault("__material", ""),@"(?:^|\n)_cellWidth=([^\n]+)");
                if(m.Success&&float.TryParse(m.Groups[1].Value,NumberStyles.Float,CultureInfo.InvariantCulture,out float w)&&w>0)cellWidth=w;
                return cellWidth>0&&float.TryParse(v,NumberStyles.Float,CultureInfo.InvariantCulture,out float size) ? (size/cellWidth).ToString("0.###",CultureInfo.InvariantCulture)+" 格" : "规格未知";
            }
            int.TryParse(v,out int i);
            if(name=="ground_floor_use")return Pick(new[]{"随机","住宅","商业"},i);
            if(name=="massing_shape")return Pick(new[]{"矩形","L 形"},i);
            if(name=="l_notch_side")return Pick(new[]{"后左","后右","前左","前右"},i);
            if(name.EndsWith("enabled")||name.Contains("shopfront_face_"))return i==0?"关闭":"开启";
            var row=Row(name);
            if(row.Success&&row.Groups[2].Value=="target")return Pick(Targets,i);
            if(row.Success&&row.Groups[2].Value=="kind")return Pick(Kinds,i);
            if(name.EndsWith("quantity_mode")||name=="facade_layout_mode")return Pick(new[]{"固定数量","随机范围"},i);
            if(row.Success&&row.Groups[2].Value=="layout_mode")return Pick(new[]{"自动","随机范围","固定数量"},i);
            return v;
        }
        private static string RowScope(Dictionary<string,string>d,string kind,string index)
        {
            string prefix=kind+"_override_";
            if(!d.ContainsKey(prefix+"floor_start"+index))return "无此条覆盖";
            int start=I(d,prefix+"floor_start"+index),end=I(d,prefix+"floor_end"+index);
            string face=kind=="facade"?Pick(Targets,I(d,prefix+"target"+index)):
                string.Join("、",new[]{"front","secondary_front","side","rear"}.Select((n,i)=>(n,i)).Where(p=>I(d,prefix+p.n+index)!=0).Select(p=>Targets[p.i]));
            string invalid=start<1||end<start||start>I(d,"floor_count",12)+ (kind=="attachment"?1:0) ? "；范围无效" : "";
            return Floors(start,end)+"；"+(string.IsNullOrEmpty(face)?"未选立面":face)+invalid;
        }
        private static string BaseScope(Dictionary<string,string>d,string name,string area)
        {
            if(name.StartsWith("entrance_")||name=="ground_quantity_mode")return "整栋首层（商业门总数）";
            if(name.StartsWith("shopfront_"))return "首层；"+string.Join("、",Enumerable.Range(0,4).Where(i=>I(d,"shopfront_face_"+i)!=0).Select(i=>new[]{"正面","左侧","右侧","背面"}[i]))+"；每个选中启用立面";
            if(area=="标准层门窗")return I(d,"floor_count",1)<2 ? "无标准层" : Floors(2,I(d,"floor_count"))+"；各启用物理立面（同方向分段共享额度）";
            if(area=="首层门窗")return "首层；各启用立面";
            if(area=="局部覆盖")return "覆盖条目列表；具体范围见条目差异";
            if(name.StartsWith("roof_props"))return "屋顶合格挂点";
            if(area=="附件")return "所选楼层与立面的合格挂点；实际受素材适用范围限制";
            if(area=="屋顶与线脚")return "屋顶／女儿墙／线脚对应部位";
            return "整栋建筑";
        }
        private static bool Active(Dictionary<string,string>d,string n)
        {
            if(n=="window_count_max")return I(d,"facade_layout_mode")==1;
            if(n=="entrance_count_min")return I(d,"ground_quantity_mode")==1&&I(d,"ground_floor_use")!=1;
            if(n.StartsWith("entrance_")||n=="ground_quantity_mode")return I(d,"ground_floor_use")!=1;
            if(n.StartsWith("shopfront_"))
            {
                if(I(d,"ground_floor_use")==1)return false;
                if(n=="shopfront_ratio")return I(d,"shopfront_control")==1;
                if(n=="shopfront_count")return I(d,"shopfront_control")==0&&I(d,"shopfront_quantity_mode")==0;
                if(n is "shopfront_count_min" or "shopfront_count_max")return I(d,"shopfront_control")==0&&I(d,"shopfront_quantity_mode")==1;
            }
            if(n=="parapet_height")return I(d,"parapet_enabled")!=0;
            if(n=="residential_door_enabled")return I(d,"ground_floor_use")!=2;
            if(n=="l_notch_width"||n=="l_notch_depth")return false;
            if(n.StartsWith("l_notch_"))return I(d,"massing_shape")==1;
            var r=Row(n);
            if(r.Success&&r.Groups[1].Value=="facade")
            {
                string field=r.Groups[2].Value,i=r.Groups[3].Value;
                if(field.EndsWith("_max")&&I(d,"facade_override_layout_mode"+i)!=1)return false;
                if(field.StartsWith("shopfront_")&&(I(d,"facade_override_floor_start"+i)>1||I(d,"facade_override_floor_end"+i)<1||I(d,"ground_floor_use")==1))return false;
                if(field.StartsWith("window_")&&Math.Max(2,I(d,"facade_override_floor_start"+i))>Math.Min(I(d,"floor_count",12),I(d,"facade_override_floor_end"+i)))return false;
            }
            if(n!="attachments_enabled"&&(Area(n)=="附件"||n.StartsWith("attachment_override_")))return I(d,"attachments_enabled")!=0;
            return true;
        }
        internal static string Area(string name) => name.StartsWith("__material") ? "素材规格" : name.StartsWith("__input") ? "输入地块与引导"
            : name.StartsWith("facade_override") || name.StartsWith("attachment_override") ? "局部覆盖"
            : name.StartsWith("building_") || name.StartsWith("l_notch") || name is "massing_shape" or "floor_count" or "rear_facade_mode" ? "建筑体块"
            : name.StartsWith("window_") || name.StartsWith("facade_") ? "标准层门窗"
            : name.StartsWith("roof_props") || name.Contains("density") || name.Contains("max_count") || name.StartsWith("attachment") ? "附件"
            : name.StartsWith("roof") || name.StartsWith("parapet") || name.Contains("trim") ? "屋顶与线脚"
            : name.Contains("seed") || name.StartsWith("random_") || name.StartsWith("__random_") ? "随机与复现" : "首层门窗";
    }
}
#endif
