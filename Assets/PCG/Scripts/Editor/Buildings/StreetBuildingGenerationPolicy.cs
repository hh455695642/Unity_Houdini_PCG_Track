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
        internal const string LegacyBalconyDoorCount = "balcony_door_count";

        // 附件输入与诊断分类。生成范围仍只保存在 HDA 实例 policy；不能用此集合禁止抽样。
        internal static readonly HashSet<string> ReferenceFields = new(StringComparer.Ordinal)
        {
            "roof_props_layout_mode", "water_tower_count", "chimney_count",
            "fire_escape_layout_mode", "fire_escape_group_count", "fire_escape_face_mask",
            "fire_escape_floor_start", "fire_escape_floor_end", "fire_escape_roof_access",
            "drainpipe_enabled", "drainpipe_count", "drainpipe_face_mask",
            "water_tower_count_mode", "water_tower_count_min", "water_tower_count_max",
            "chimney_count_mode", "chimney_count_min", "chimney_count_max", "roof_prop_position_mode"
        };

        internal static bool ReferenceFieldActive(string name, Func<string, int> read)
        {
            if (name == "attachments_enabled") return true;
            if (read("attachments_enabled") == 0) return false;
            if (name == "roof_props_layout_mode") return read("roof_enabled") != 0;
            bool typedRoof = read("roof_enabled") != 0 && read("roof_props_layout_mode") == 1;
            if (name == "roof_prop_position_mode" || name == "water_tower_count_mode" || name == "chimney_count_mode")
                return typedRoof;
            if (name == "water_tower_count" || name == "chimney_count")
                return typedRoof && read(name + "_mode") == 0;
            if (name == "water_tower_count_min" || name == "water_tower_count_max")
                return typedRoof && read("water_tower_count_mode") == 1;
            if (name == "chimney_count_min" || name == "chimney_count_max")
                return typedRoof && read("chimney_count_mode") == 1;
            if (name == "roof_props_density" || name == "roof_props_max_count")
                return read("roof_enabled") != 0 && read("roof_props_layout_mode") == 0;
            if (name == "fire_escape_density" || name == "fire_escape_max_count") return read("fire_escape_layout_mode") == 0;
            if (name.StartsWith("fire_escape_", StringComparison.Ordinal) && name != "fire_escape_layout_mode")
                return read("fire_escape_layout_mode") == 1;
            if (name.StartsWith("drainpipe_", StringComparison.Ordinal) && name != "drainpipe_enabled") return read("drainpipe_enabled") != 0;
            return true;
        }

        // 扩展点：生成字段与技术／作用域字段显式分开，不能按“数字类型”一律随机。
        internal static bool IsDirectField(string name)
        {
            if (name is "balcony_floor_start" or "balcony_floor_end") return true;
            if (name is "variation_seed" or "layout_seed" or "debug_metadata_enabled"
                or "fire_escape_floor_start" or "fire_escape_floor_end") return true;
            if (name == SequenceParameter || name.StartsWith("random_", StringComparison.Ordinal)) return true;
            if (name.StartsWith("facade_override_target", StringComparison.Ordinal)
                || name.StartsWith("facade_override_floor_start", StringComparison.Ordinal)
                || name.StartsWith("facade_override_floor_end", StringComparison.Ordinal)) return true;
            return name.StartsWith("attachment_override_floor_start", StringComparison.Ordinal)
                || name.StartsWith("attachment_override_floor_end", StringComparison.Ordinal)
                || name.StartsWith("attachment_override_front", StringComparison.Ordinal)
                || name.StartsWith("attachment_override_secondary_front", StringComparison.Ordinal)
                || name.StartsWith("attachment_override_side", StringComparison.Ordinal)
                || name.StartsWith("attachment_override_rear", StringComparison.Ordinal);
        }

        private static bool IsRoofQuantityTransport(string name)
            => name is "water_tower_count_mode" or "water_tower_count_min" or "water_tower_count_max"
                or "chimney_count_mode" or "chimney_count_min" or "chimney_count_max";

        internal static bool CanSampleField(string name, Func<string, int> read)
        {
            if (name == LegacyBalconyDoorCount || IsDirectField(name) || IsRoofQuantityTransport(name)) return false;
            if (name is "wall_lamp_enabled" or "balcony_enabled") return read("attachments_enabled") != 0;
            if (name.StartsWith("wall_lamp_", StringComparison.Ordinal))
                return read("attachments_enabled") != 0 && read("wall_lamp_enabled") != 0;
            if (name.StartsWith("balcony_", StringComparison.Ordinal))
                return read("attachments_enabled") != 0 && read("balcony_enabled") != 0 && read("floor_count") > 1;
            if (name is "water_tower_count" or "chimney_count")
                return read("attachments_enabled") != 0 && read("roof_enabled") != 0 && read("roof_props_layout_mode") == 1;
            if (ReferenceFields.Contains(name) || name is "roof_props_density" or "roof_props_max_count"
                or "fire_escape_density" or "fire_escape_max_count") return ReferenceFieldActive(name, read);
            return StreetBuildingRandom.ForField(name) != StreetBuildingRandom.Group.Attachments
                || name == "attachments_enabled" || read("attachments_enabled") != 0;
        }

        private static int ChoicePriority(Rule rule) => rule.name is "attachments_enabled" or "roof_enabled" ? 0
            : rule.name is "roof_props_layout_mode" or "fire_escape_layout_mode" or "drainpipe_enabled"
                or "wall_lamp_enabled" or "balcony_enabled" ? 1 : 2;

        [Serializable]
        internal sealed class Rule
        {
            public string name;
            public string kind; // number, choice, quantity, faces, attachment_faces
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
                if (data == null || (data.version != 1 && data.version != 2) || data.rules == null) throw new FormatException("Unsupported policy schema.");
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
                if (StreetBuildingRandom.Enabled(asset) && (rule.name == "l_notch_width_cells" || rule.name == "l_notch_depth_cells"))
                    StreetBuildingInstanceParameters.SetInt(asset, "l_notch_units", 1);
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

        internal static int AttachmentFaceCandidates(string name, int mask)
        {
            // 消防梯和落水管只允许侧／背面；原始请求保留，禁止把正面静默替换成其它立面。
            int supported = mask & 12;
            if (supported == 0)
                throw new InvalidOperationException(name + " 的立面候选与允许的侧面／背面没有交集；请修正候选。原请求已保留。");
            return supported;
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

        private static void AddRoofQuantity(Data data, HEU_HoudiniAsset asset, string prefix)
        {
            string key = prefix + "_count";
            if (!StreetBuildingInstanceParameters.Exists(asset, key)) return;
            var existing = Find(data, key);
            if (existing?.kind == "quantity") return;
            // 旧附件 policy 从未生效。首次迁移以当前生效的原生固定值／范围为准，不复活隐藏旧请求。
            data.rules.RemoveAll(r => r.name == key);
            int mode = Int(asset, key + "_mode");
            int low = mode == 1 ? Int(asset, key + "_min") : Int(asset, key);
            int high = mode == 1 ? Int(asset, key + "_max") : low;
            Add(data, new Rule { name = key, kind = "quantity", min = low, max = high });
        }

        private static void AddAttachmentFaces(Data data, HEU_HoudiniAsset asset, string name)
        {
            if (!StreetBuildingInstanceParameters.Exists(asset, name)) return;
            if (Find(data, name)?.kind == "attachment_faces") return;
            // 旧数字型 policy 未参与过生成，按当前原生立面集合迁移；不可把 mask 当整数范围抽样。
            data.rules.RemoveAll(r => r.name == name);
            Add(data, new Rule { name = name, kind = "attachment_faces", mask = Int(asset, name) });
        }

        // Migration reads current instance fields only. No StyleConfig default can enter this path.
        internal static Data WithDefaults(HEU_HoudiniAsset asset)
        {
            var data = Load(asset);
            RemoveTechnicalRules(data);
            foreach (string name in new[] { "l_notch_width_cells", "l_notch_depth_cells", "floor_count",
                     "awning_max_count", "sign_max_count", "fire_escape_max_count", "wall_ac_max_count", "roof_props_max_count",
                     "fire_escape_group_count", "drainpipe_count", "wall_lamp_count", "balcony_count" }) AddNumber(data, asset, name, false);
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
            foreach (string name in new[] { "roof_props_layout_mode", "roof_prop_position_mode", "fire_escape_layout_mode",
                     "fire_escape_roof_access", "drainpipe_enabled", "wall_lamp_enabled", "wall_lamp_layout", "balcony_enabled" }) AddChoice(data, asset, name, new[] { 0, 1 });
            foreach (string name in new[] { "residential_door_enabled", "roof_enabled", "parapet_enabled", "architectural_trim_enabled", "corner_building", "attachments_enabled" })
                AddChoice(data, asset, name, new[] { 0, 1 });
            AddQuantity(data, asset, "entrance_count", "entrance_count_min", "entrance_count_max", Int(asset, "ground_quantity_mode"));
            AddQuantity(data, asset, "shopfront_count", "shopfront_count_min", "shopfront_count_max", Int(asset, "shopfront_quantity_mode"));
            AddQuantity(data, asset, "window_count", "window_count_min", "window_count_max", Int(asset, "facade_layout_mode"));
            AddRoofQuantity(data, asset, "water_tower");
            AddRoofQuantity(data, asset, "chimney");
            AddAttachmentFaces(data, asset, "fire_escape_face_mask");
            AddAttachmentFaces(data, asset, "drainpipe_face_mask");
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
                AddChoice(data, asset, "attachment_override_kind" + row, new[] { 0, 1, 2, 3, 4 });
                AddNumber(data, asset, "attachment_override_density" + row, true);
                AddNumber(data, asset, "attachment_override_max_count" + row, false);
            }
            return data;
        }

        private static void RemoveTechnicalRules(Data data)
        {
            // 重绘只清理内存视图；仅显式编辑／生成才保存，作用域和传输字段不能被遗留规则覆盖。
            data.rules.RemoveAll(r => IsDirectField(r.name) || IsRoofQuantityTransport(r.name));
        }

        internal static void SampleInto(HEU_HoudiniAsset asset, Data data, int sequence)
        {
            RemoveTechnicalRules(data);
            if (StreetBuildingRandom.Enabled(asset))
            {
                SampleV2Into(asset, data, sequence);
                return;
            }
            // 开关／模式先选定，再逐项检查本次活性，避免模式切换当次沿用旧分支。
            foreach (var rule in data.rules.OrderBy(r => r.kind == "choice" ? 0 : 1)
                         .ThenBy(r => r.kind == "choice" ? ChoicePriority(r) : 0).ThenBy(r => r.name, StringComparer.Ordinal))
            {
                if (!CanSampleField(rule.name, name => Int(asset, name))) continue;
                if (rule.kind == "number")
                {
                    if (!StreetBuildingInstanceParameters.Exists(asset, rule.name)) continue;
                    bool floating = StreetBuildingInstanceParameters.Info(asset, rule.name).type == HAPI_ParmType.HAPI_PARMTYPE_FLOAT;
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
                else if (rule.kind == "attachment_faces")
                {
                    int selected = PickSubset(AttachmentFaceCandidates(rule.name, rule.mask), sequence, rule.name);
                    StreetBuildingInstanceParameters.SetInt(asset, rule.name, selected);
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

        // 扩展点：语义类型决定抽样，HAPI FLOAT 只是米制传输类型，不代表宽深允许小数格。
        private static void SampleV2Into(HEU_HoudiniAsset asset, Data data, int sequence)
        {
            var context = StreetBuildingRandom.Capture(asset);
            // Keep legacy rows in the stored policy, without including them in validation or sampling.
            var ordered = data.rules.Where(r => r.name != LegacyBalconyDoorCount)
                .OrderBy(r => r.name, StringComparer.Ordinal).ToArray();
            if (ordered.Select(r => r.name).Distinct(StringComparer.Ordinal).Count() != ordered.Length)
                throw new InvalidOperationException("随机配置存在重复字段，请先修复请求。");
            foreach (var r in ordered.Where(r => r.kind == "choice").OrderBy(ChoicePriority).ThenBy(r => r.name, StringComparer.Ordinal))
            {
                if (!CanSampleField(r.name, name => Int(asset, name))) continue;
                var values = Values(r.name);
                if (values == null || !StreetBuildingInstanceParameters.Exists(asset, r.name)) continue;
                StreetBuildingInstanceParameters.SetInt(asset, r.name, values[StreetBuildingRandom.Pick(context, r.name, r.mask, values.Length)]);
            }
            float cellWidth = asset.GetComponentInParent<PCGBike.Buildings.StreetBuildingAuthoring>()?.ResolveStyle()?.CellWidth ?? 0;
            if (!float.IsFinite(cellWidth) || cellWidth <= 0) throw new InvalidOperationException("素材格宽不可用。");
            bool external = Int(asset, "site_source_auto", 1) != 0
                ? asset.GetInputNodeByIndex(0)?.GetConnectedInputCount() > 0 : Int(asset, "site_source") == 1;
            if (!external)
            {
                DimensionV2(asset, data, "building_width", "l_notch_width_cells", cellWidth, context);
                DimensionV2(asset, data, "building_depth", "l_notch_depth_cells", cellWidth, context);
            }
            foreach (var r in ordered.Where(r => r.kind == "number"))
            {
                if (!CanSampleField(r.name, name => Int(asset, name))) continue;
                if (r.name == "building_width" || r.name == "building_depth" || !StreetBuildingInstanceParameters.Exists(asset, r.name)) continue;
                bool notch = r.name == "l_notch_width_cells" || r.name == "l_notch_depth_cells";
                if (notch && (Int(asset, "massing_shape") == 0 || Int(asset, "l_notch_units") != 1)) continue;
                if ((r.name.StartsWith("roof_props_", StringComparison.Ordinal) && Int(asset, "roof_enabled") == 0)
                    || (StreetBuildingRandom.ForField(r.name) == StreetBuildingRandom.Group.Attachments && Int(asset, "attachments_enabled") == 0)) continue;
                int key = context.Key( StreetBuildingRandom.ForField(r.name), r.name);
                bool floating = StreetBuildingInstanceParameters.Info(asset, r.name).type == HAPI_ParmType.HAPI_PARMTYPE_FLOAT;
                if (floating) StreetBuildingInstanceParameters.SetFloat(asset, r.name, StreetBuildingRandom.Fraction(r.min, r.max, key));
                else
                {
                    int lo = StreetBuildingRandom.Integral(r.min, r.name), hi = StreetBuildingRandom.Integral(r.max, r.name);
                    if (notch && !external)
                    {
                        string dimension = r.name == "l_notch_width_cells" ? "building_width" : "building_depth";
                        int bound = Mathf.RoundToInt(Float(asset, dimension) / cellWidth) - 1;
                        // 请求端点保留在 policy，只有本次采用值受几何约束。
                        if (lo < 1 || lo > bound || lo == hi && hi > bound)
                            throw new InvalidOperationException($"{r.name} 请求 {lo}～{hi} 格与当前尺寸冲突（最大 {bound} 格）。");
                        hi = Math.Min(hi, bound);
                    }
                    StreetBuildingInstanceParameters.SetInt(asset, r.name, StreetBuildingRandom.Integer(lo, hi, key));
                }
            }
            foreach (var r in ordered.Where(r => r.kind == "quantity"))
            {
                if (!CanSampleField(r.name, name => Int(asset, name))) continue;
                if (r.name == "entrance_count" && Int(asset, "ground_floor_use") != 2
                    || r.name == "shopfront_count" && (Int(asset, "ground_floor_use") != 2 || Int(asset, "shopfront_control") != 0)
                    || r.name == "window_count" && Int(asset, "floor_count") < 2) continue;
                int low = StreetBuildingRandom.Integral(r.min, r.name), high = StreetBuildingRandom.Integral(r.max, r.name);
                int minimum = r.name == "entrance_count" ? 1 : 0, maximum = r.name == "entrance_count" ? 4 : 64;
                if (low < minimum || high > maximum || low > high) throw new InvalidOperationException("数量请求范围无效：" + r.name);
                WriteQuantity(asset, r); // 各楼层／物理立面的实际抽样继续由 HDA 执行。
            }
            foreach (var r in ordered.Where(r => r.kind == "attachment_faces"))
            {
                if (!CanSampleField(r.name, name => Int(asset, name))) continue;
                int mask = AttachmentFaceCandidates(r.name, r.mask);
                var subsets = new List<int>();
                for (int s = mask; s != 0; s = (s - 1) & mask) subsets.Add(s);
                int selected = subsets[StreetBuildingRandom.Integer(0, subsets.Count - 1,
                    context.Key(StreetBuildingRandom.Group.Attachments, r.name))];
                StreetBuildingInstanceParameters.SetInt(asset, r.name, selected);
            }
            var faces = Find(data, FacesKey);
            if (faces != null && Int(asset, "ground_floor_use") == 2)
            {
                int mask = faces.mask;
                if (Int(asset, "rear_facade_mode") == 0) mask &= 7;
                if (mask == 0) throw new InvalidOperationException("橱窗候选与当前启用立面的交集为空；请调整候选或启用对应立面。");
                if ((mask & ~15) != 0) throw new InvalidOperationException("橱窗候选包含无效立面。");
                var subsets = new List<int>();
                for (int s = mask; s != 0; s = (s - 1) & mask) subsets.Add(s);
                int selected = subsets[StreetBuildingRandom.Integer(0, subsets.Count - 1, context.Key( StreetBuildingRandom.Group.Ground, FacesKey))];
                for (int i = 0; i < 4; i++) StreetBuildingInstanceParameters.SetInt(asset, "shopfront_face_" + i, (selected >> i) & 1);
            }
            ReconcileOverrides(asset, data);
            data.version = 2;
            StreetBuildingInstanceParameters.SetInt(asset, SequenceParameter, sequence);
            StreetBuildingInstanceParameters.SetString(asset, Parameter, JsonUtility.ToJson(data));
        }

        private static void DimensionV2(HEU_HoudiniAsset asset, Data data, string name, string notchName, float cellWidth, StreetBuildingRandom.Context context)
        {
            var r = Find(data, name);
            if (r == null) return;
            int lo = StreetBuildingRandom.Integral(r.min, name), hi = StreetBuildingRandom.Integral(r.max, name);
            if (lo < 2 || hi < lo || hi > 100000) throw new InvalidOperationException("无效建筑格数范围：" + name);
            if (Int(asset, "massing_shape") == 1 && Int(asset, "random_feasible") != 0)
            {
                var notch = Find(data, notchName);
                int needed;
                if (Int(asset, "l_notch_units") == 1)
                    needed = notch == null ? Int(asset, notchName) : StreetBuildingRandom.Integral(notch.min, notchName);
                else
                {
                    // 保留旧米制缺口；只筛选能容纳它的尺寸，不把米制值强制取整回写。
                    float notchMetres = Float(asset, notchName.Replace("_cells", ""));
                    if (!float.IsFinite(notchMetres) || notchMetres <= 0) throw new InvalidOperationException("无效米制缺口：" + notchName);
                    needed = Mathf.CeilToInt(notchMetres / cellWidth - .00001f);
                }
                lo = Math.Max(lo, needed + 1); // 可行前缀筛选，避免第一次尺寸抽小即误报全范围无解。
                if (lo > hi) throw new InvalidOperationException($"{name} 与 {notchName} 在请求范围内不存在合法组合。");
            }
            int cells = StreetBuildingRandom.Integer(lo, hi, context.Key( StreetBuildingRandom.Group.Massing, name));
            float metres = cells * cellWidth;
            if (!float.IsFinite(metres)) throw new InvalidOperationException("建筑尺寸换算溢出：" + name);
            StreetBuildingInstanceParameters.SetFloat(asset, name, metres);
        }

        private static void ReconcileOverrides(HEU_HoudiniAsset asset, Data data)
        {
            for (int row = 1; row <= Int(asset, "facade_overrides"); row++)
            {
                string mode = "facade_override_layout_mode" + row;
                if (Int(asset, mode) == 0) continue;
                var shop = Find(data, "facade_override_shopfront_" + row); var window = Find(data, "facade_override_window_" + row);
                bool random = shop != null && shop.min != shop.max || window != null && window.min != window.max;
                StreetBuildingInstanceParameters.SetInt(asset, mode, random ? 1 : 2);
            }
        }

        private static void WriteQuantity(HEU_HoudiniAsset asset, Rule rule)
        {
            int lo = Mathf.RoundToInt(rule.min), hi = Mathf.RoundToInt(rule.max);
            if (lo > hi) throw new InvalidOperationException("无效数量范围：" + rule.name);
            string minName, maxName, modeName;
            if (rule.name == "entrance_count") { minName = "entrance_count_min"; maxName = "entrance_count_max"; modeName = "ground_quantity_mode"; }
            else if (rule.name == "shopfront_count") { minName = "shopfront_count_min"; maxName = "shopfront_count_max"; modeName = "shopfront_quantity_mode"; }
            else if (rule.name == "window_count") { minName = "window_count_min"; maxName = "window_count_max"; modeName = "facade_layout_mode"; }
            else if (rule.name is "water_tower_count" or "chimney_count")
            { minName = rule.name + "_min"; maxName = rule.name + "_max"; modeName = rule.name + "_mode"; }
            else if (rule.name.StartsWith("facade_override_shopfront_", StringComparison.Ordinal))
            { string row = rule.name.Substring("facade_override_shopfront_".Length); minName = "facade_override_shopfront_min" + row; maxName = "facade_override_shopfront_max" + row; modeName = "facade_override_layout_mode" + row; }
            else if (rule.name.StartsWith("facade_override_window_", StringComparison.Ordinal))
            { string row = rule.name.Substring("facade_override_window_".Length); minName = "facade_override_window_min" + row; maxName = "facade_override_window_max" + row; modeName = "facade_override_layout_mode" + row; }
            else return;
            if (!StreetBuildingInstanceParameters.Exists(asset, minName)) return;
            StreetBuildingInstanceParameters.SetInt(asset, minName, lo);
            StreetBuildingInstanceParameters.SetInt(asset, maxName, hi);
            if (rule.name == "shopfront_count") StreetBuildingInstanceParameters.SetInt(asset, "shopfront_count", lo);
            if (rule.name is "water_tower_count" or "chimney_count")
                StreetBuildingInstanceParameters.SetInt(asset, rule.name, lo);
            if (!modeName.StartsWith("facade_override_", StringComparison.Ordinal))
                StreetBuildingInstanceParameters.SetInt(asset, modeName, lo == hi ? 0 : 1);
        }

        internal static int[] Values(string name)
        {
            if (name == "massing_shape" || name == "shopfront_control" || name == "ground_attachment_placement"
                || name == "residential_door_enabled" || name == "roof_enabled" || name == "parapet_enabled"
                || name == "architectural_trim_enabled" || name == "corner_building" || name == "attachments_enabled"
                || name == "roof_props_layout_mode" || name == "roof_prop_position_mode" || name == "fire_escape_layout_mode"
                || name == "fire_escape_roof_access" || name == "drainpipe_enabled"
                || name == "wall_lamp_enabled" || name == "wall_lamp_layout" || name == "balcony_enabled") return new[] { 0, 1 };
            if (name.StartsWith("attachment_override_kind", StringComparison.Ordinal)) return new[] { 0, 1, 2, 3, 4 };
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
