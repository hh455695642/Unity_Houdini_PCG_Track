#if UNITY_EDITOR
using System;
using System.Collections.Generic;
using System.Linq;
using HoudiniEngineUnity;
using UnityEngine;

namespace PCGBike.Editor.Buildings
{
    // Stored in the HDA instance, never in StyleConfig or a second Authoring component.
    // The resolved values are written to the existing public HDA parameters before an explicit Generate.
    internal static class StreetBuildingGenerationPolicy
    {
        internal const string Parameter = "unity_generation_policy";
        internal const string SequenceParameter = "generation_sequence";
        internal const string FacesKey = "@shopfront_faces";

        [Serializable]
        internal sealed class Rule
        {
            public string name;
            public string kind; // number, choice, quantity, faces
            public float min, max;
            public int mask;
        }

        [Serializable]
        internal sealed class Data
        {
            public int version = 1;
            public List<Rule> rules = new();
        }

        internal static Data Load(HEU_HoudiniAsset asset)
        {
            string json = StreetBuildingInstanceParameters.String(asset, Parameter);
            if (string.IsNullOrWhiteSpace(json)) return new Data();
            try
            {
                var data = JsonUtility.FromJson<Data>(json);
                if (data?.version != 1 || data.rules == null) throw new FormatException("Unsupported policy schema.");
                return data;
            }
            catch (Exception e) { throw new InvalidOperationException("StreetBuilding 实例随机配置不可读；已保留原始内容。", e); }
        }

        internal static Rule Find(Data data, string name) => data.rules.FirstOrDefault(r => r.name == name);

        internal static Rule Number(Data data, string name, float fallbackMin, float fallbackMax)
            => Find(data, name) ?? new Rule { name = name, kind = "number", min = fallbackMin, max = fallbackMax };

        internal static Rule Choice(Data data, string name, int fallbackMask)
            => Find(data, name) ?? new Rule { name = name, kind = "choice", mask = fallbackMask };

        internal static void Set(HEU_HoudiniAsset asset, Rule rule)
        {
            if (string.IsNullOrEmpty(rule.name)) throw new ArgumentException("Empty generation rule name.");
            StreetBuildingParameterTransaction.Run(asset, "修改 StreetBuilding 生成范围", () =>
            {
                var data = Load(asset);
                data.rules.RemoveAll(r => r.name == rule.name);
                data.rules.Add(rule);
                data.rules.Sort((a, b) => StringComparer.Ordinal.Compare(a.name, b.name));
                StreetBuildingInstanceParameters.SetString(asset, Parameter, JsonUtility.ToJson(data));
            });
        }

        internal static void ShiftAfterRowRemoval(HEU_HoudiniAsset asset, string multi, int removedRow)
        {
            var data = Load(asset);
            string prefix = multi == "facade_overrides" ? "facade_override_" : "attachment_override_";
            foreach (var rule in data.rules.ToArray())
            {
                if (!rule.name.StartsWith(prefix, StringComparison.Ordinal)) continue;
                int start = rule.name.Length;
                while (start > prefix.Length && char.IsDigit(rule.name[start - 1])) start--;
                if (start == rule.name.Length || !int.TryParse(rule.name.Substring(start), out int row)) continue;
                if (row == removedRow) data.rules.Remove(rule);
                else if (row > removedRow) rule.name = rule.name.Substring(0, start) + (row - 1);
            }
            StreetBuildingInstanceParameters.SetString(asset, Parameter, JsonUtility.ToJson(data));
        }

        // A stable field-specific stream keeps unrelated random choices unchanged.
        private static System.Random RandomFor(int sequence, string name)
        {
            unchecked
            {
                uint hash = 2166136261;
                foreach (char c in name) { hash ^= c; hash *= 16777619; }
                hash ^= (uint)sequence; hash *= 16777619;
                return new System.Random((int)(hash & 0x7fffffff));
            }
        }

        internal static int DrawInteger(int low, int high, int sequence, string name)
        {
            if (low > high) throw new ArgumentOutOfRangeException(nameof(high));
            return low == high ? low : RandomFor(sequence, name).Next(low, high + 1);
        }

        internal static float DrawFraction(float low, float high, int sequence, string name)
        {
            if (float.IsNaN(low) || float.IsNaN(high) || float.IsInfinity(low) || float.IsInfinity(high) || low > high)
                throw new ArgumentOutOfRangeException(nameof(high));
            return low == high ? low : (float)(low + RandomFor(sequence, name).NextDouble() * (high - low));
        }

        private static int Pick(int mask, int sequence, string name)
        {
            var options = Enumerable.Range(0, 30).Where(i => (mask & (1 << i)) != 0).ToArray();
            if (options.Length == 0) throw new InvalidOperationException("候选项不能为空：" + name);
            return options[RandomFor(sequence, name).Next(options.Length)];
        }

        internal static int PickSubset(int mask, int sequence, string name)
        {
            var subsets = new List<int>();
            for (int subset = mask; subset != 0; subset = (subset - 1) & mask) subsets.Add(subset);
            if (subsets.Count == 0) throw new InvalidOperationException("立面候选不能为空：" + name);
            return subsets[RandomFor(sequence, name).Next(subsets.Count)];
        }

        private static int Int(HEU_HoudiniAsset asset, string name, int fallback = 0)
            => StreetBuildingInstanceParameters.Int(asset, name, fallback);
        private static float Float(HEU_HoudiniAsset asset, string name, float fallback = 0)
            => StreetBuildingInstanceParameters.Float(asset, name, fallback);

        private static void Add(Data data, Rule rule)
        {
            if (Find(data, rule.name) == null) data.rules.Add(rule);
        }

        private static void AddNumber(Data data, HEU_HoudiniAsset asset, string name, bool floating)
        {
            if (!StreetBuildingInstanceParameters.Exists(asset, name)) return;
            float current = floating ? Float(asset, name) : Int(asset, name);
            if (name == "layout_seed" && current < 0)
            {
                int remembered = asset.GetComponentInParent<PCGBike.Buildings.StreetBuildingAuthoring>()?.LayoutSeed ?? -1;
                current = remembered >= 0 ? remembered : 0;
            }
            if (name == "building_width" || name == "building_depth")
            {
                float cellWidth = asset.GetComponentInParent<PCGBike.Buildings.StreetBuildingAuthoring>()?.ResolveStyle()?.CellWidth ?? 0;
                if (cellWidth > 0) current = Mathf.Max(2, Mathf.RoundToInt(current / cellWidth));
            }
            Add(data, new Rule { name = name, kind = "number", min = current, max = current });
        }

        private static void AddChoice(Data data, HEU_HoudiniAsset asset, string name, int[] values)
        {
            if (!StreetBuildingInstanceParameters.Exists(asset, name)) return;
            int value = Int(asset, name), index = Array.IndexOf(values, value);
            int mask = index < 0 ? 1 : 1 << index;
            if (name == "ground_floor_use" && value == 0) mask = 3;
            Add(data, new Rule { name = name, kind = "choice", mask = mask });
        }

        private static void AddQuantity(Data data, HEU_HoudiniAsset asset, string key, string minName, string maxName, int mode)
        {
            if (!StreetBuildingInstanceParameters.Exists(asset, minName) || !StreetBuildingInstanceParameters.Exists(asset, maxName)) return;
            float min = Int(asset, minName), max = mode == 1 ? Int(asset, maxName) : min;
            if (key == "entrance_count" && mode == 0) min = max = Int(asset, maxName);
            if (key == "shopfront_count" && mode == 0) min = max = Int(asset, key);
            Add(data, new Rule { name = key, kind = "quantity", min = min, max = max });
        }

        // Migration reads current instance fields only. No StyleConfig default can enter this path.
        internal static Data WithDefaults(HEU_HoudiniAsset asset)
        {
            var data = Load(asset);
            foreach (string name in new[] { "l_notch_width_cells", "l_notch_depth_cells", "floor_count", "variation_seed", "layout_seed",
                     "awning_max_count", "sign_max_count", "fire_escape_max_count", "wall_ac_max_count", "roof_props_max_count" }) AddNumber(data, asset, name, false);
            foreach (string name in new[] { "building_width", "building_depth", "shopfront_ratio", "parapet_height", "attachment_global_density",
                     "awning_density", "sign_density", "fire_escape_density", "wall_ac_density", "roof_props_density" }) AddNumber(data, asset, name, true);
            AddChoice(data, asset, "massing_shape", new[] { 0, 1 });
            AddChoice(data, asset, "l_notch_side", new[] { 0, 1, 2, 3 });
            AddChoice(data, asset, "rear_facade_mode", new[] { 0, 2 });
            AddChoice(data, asset, "ground_floor_use", new[] { 1, 2 });
            AddChoice(data, asset, "shopfront_control", new[] { 0, 1 });
            AddChoice(data, asset, "ground_rhythm", new[] { 0, 1, 3, 4 });
            AddChoice(data, asset, "facade_rhythm", new[] { 0, 1, 3, 4 });
            AddChoice(data, asset, "corner_street_side", new[] { 0, 1, 2 });
            AddChoice(data, asset, "ground_attachment_placement", new[] { 0, 1 });
            foreach (string name in new[] { "residential_door_enabled", "roof_enabled", "parapet_enabled", "architectural_trim_enabled", "corner_building", "attachments_enabled" })
                AddChoice(data, asset, name, new[] { 0, 1 });
            AddQuantity(data, asset, "entrance_count", "entrance_count_min", "entrance_count_max", Int(asset, "ground_quantity_mode"));
            AddQuantity(data, asset, "shopfront_count", "shopfront_count_min", "shopfront_count_max", Int(asset, "shopfront_quantity_mode"));
            AddQuantity(data, asset, "window_count", "window_count_min", "window_count_max", Int(asset, "facade_layout_mode"));
            int faces = 0;
            for (int i = 0; i < 4; i++) if (Int(asset, "shopfront_face_" + i) != 0) faces |= 1 << i;
            Add(data, new Rule { name = FacesKey, kind = "faces", mask = faces == 0 ? 1 : faces });
            int facadeRows = Int(asset, "facade_overrides"), attachmentRows = Int(asset, "attachment_overrides");
            for (int row = 1; row <= facadeRows; row++)
            {
                AddChoice(data, asset, "facade_override_rhythm" + row, new[] { 0, 1, 3, 4 });
                foreach (string suffix in new[] { "shopfront", "window" })
                {
                    string prefix = "facade_override_" + suffix + "_";
                    AddQuantity(data, asset, prefix + row, prefix + "min" + row, prefix + "max" + row,
                        Int(asset, "facade_override_layout_mode" + row) == 1 ? 1 : 0);
                }
            }
            for (int row = 1; row <= attachmentRows; row++)
            {
                AddNumber(data, asset, "attachment_override_density" + row, true);
                AddNumber(data, asset, "attachment_override_max_count" + row, false);
            }
            return data;
        }

        internal static void SampleInto(HEU_HoudiniAsset asset, Data data, int sequence)
        {
            foreach (var rule in data.rules)
            {
                if (rule.kind == "number")
                {
                    if (!StreetBuildingInstanceParameters.Exists(asset, rule.name)) continue;
                    var parameter = asset.Parameters.GetParameter(rule.name);
                    bool floating = parameter?._parmInfo.type == HAPI_ParmType.HAPI_PARMTYPE_FLOAT;
                    if (floating)
                    {
                        float value = DrawFraction(rule.min, rule.max, sequence, rule.name);
                        if (rule.name == "building_width" || rule.name == "building_depth")
                        {
                            float cellWidth = asset.GetComponentInParent<PCGBike.Buildings.StreetBuildingAuthoring>()?.ResolveStyle()?.CellWidth ?? 0;
                            if (cellWidth <= 0) throw new InvalidOperationException("素材格宽不可用。");
                            value = Mathf.RoundToInt(value) * cellWidth;
                        }
                        StreetBuildingInstanceParameters.SetFloat(asset, rule.name, value);
                    }
                    else
                    {
                        int lo = Mathf.RoundToInt(rule.min), hi = Mathf.RoundToInt(rule.max);
                        if (lo > hi) throw new InvalidOperationException("无效整数范围：" + rule.name);
                        StreetBuildingInstanceParameters.SetInt(asset, rule.name, DrawInteger(lo, hi, sequence, rule.name));
                    }
                }
                else if (rule.kind == "choice")
                {
                    int[] values = Values(rule.name);
                    if (values == null || !StreetBuildingInstanceParameters.Exists(asset, rule.name)) continue;
                    int picked = Pick(rule.mask, sequence, rule.name);
                    if (picked >= values.Length) throw new InvalidOperationException("无效候选索引：" + rule.name);
                    StreetBuildingInstanceParameters.SetInt(asset, rule.name, values[picked]);
                }
                else if (rule.kind == "faces")
                {
                    int selected = PickSubset(rule.mask, sequence, rule.name);
                    for (int i = 0; i < 4; i++) StreetBuildingInstanceParameters.SetInt(asset, "shopfront_face_" + i, (selected >> i) & 1);
                }
                else if (rule.kind == "quantity")
                {
                    WriteQuantity(asset, rule);
                }
            }
            // One legacy HDA mode controls both counts in an override. A fixed count uses
            // equal endpoints while the other count may still use a range.
            int overrideRows = Int(asset, "facade_overrides");
            for (int row = 1; row <= overrideRows; row++)
            {
                string mode = "facade_override_layout_mode" + row;
                if (Int(asset, mode) == 0) continue; // Existing Auto/inherit semantics.
                var shop = Find(data, "facade_override_shopfront_" + row);
                var window = Find(data, "facade_override_window_" + row);
                bool random = shop != null && shop.min != shop.max || window != null && window.min != window.max;
                StreetBuildingInstanceParameters.SetInt(asset, mode, random ? 1 : 2);
            }
            StreetBuildingInstanceParameters.SetInt(asset, SequenceParameter, sequence);
            StreetBuildingInstanceParameters.SetString(asset, Parameter, JsonUtility.ToJson(data));
        }

        private static void WriteQuantity(HEU_HoudiniAsset asset, Rule rule)
        {
            int lo = Mathf.RoundToInt(rule.min), hi = Mathf.RoundToInt(rule.max);
            if (lo > hi) throw new InvalidOperationException("无效数量范围：" + rule.name);
            string minName, maxName, modeName;
            if (rule.name == "entrance_count") { minName = "entrance_count_min"; maxName = "entrance_count_max"; modeName = "ground_quantity_mode"; }
            else if (rule.name == "shopfront_count") { minName = "shopfront_count_min"; maxName = "shopfront_count_max"; modeName = "shopfront_quantity_mode"; }
            else if (rule.name == "window_count") { minName = "window_count_min"; maxName = "window_count_max"; modeName = "facade_layout_mode"; }
            else if (rule.name.StartsWith("facade_override_shopfront_", StringComparison.Ordinal))
            { string row = rule.name.Substring("facade_override_shopfront_".Length); minName = "facade_override_shopfront_min" + row; maxName = "facade_override_shopfront_max" + row; modeName = "facade_override_layout_mode" + row; }
            else if (rule.name.StartsWith("facade_override_window_", StringComparison.Ordinal))
            { string row = rule.name.Substring("facade_override_window_".Length); minName = "facade_override_window_min" + row; maxName = "facade_override_window_max" + row; modeName = "facade_override_layout_mode" + row; }
            else return;
            if (!StreetBuildingInstanceParameters.Exists(asset, minName)) return;
            StreetBuildingInstanceParameters.SetInt(asset, minName, lo);
            StreetBuildingInstanceParameters.SetInt(asset, maxName, hi);
            if (rule.name == "shopfront_count") StreetBuildingInstanceParameters.SetInt(asset, "shopfront_count", lo);
            if (!modeName.StartsWith("facade_override_", StringComparison.Ordinal))
                StreetBuildingInstanceParameters.SetInt(asset, modeName, lo == hi ? 0 : 1);
        }

        internal static int[] Values(string name)
        {
            if (name == "massing_shape" || name == "shopfront_control" || name == "ground_attachment_placement"
                || name == "residential_door_enabled" || name == "roof_enabled" || name == "parapet_enabled"
                || name == "architectural_trim_enabled" || name == "corner_building" || name == "attachments_enabled") return new[] { 0, 1 };
            if (name == "ground_floor_use") return new[] { 1, 2 };
            if (name == "rear_facade_mode") return new[] { 0, 2 };
            if (name == "ground_rhythm" || name == "facade_rhythm") return new[] { 0, 1, 3, 4 };
            if (name.StartsWith("facade_override_rhythm", StringComparison.Ordinal)) return new[] { 0, 1, 3, 4 };
            if (name == "l_notch_side") return new[] { 0, 1, 2, 3 };
            if (name == "corner_street_side") return new[] { 0, 1, 2 };
            return null;
        }
    }
}
#endif
