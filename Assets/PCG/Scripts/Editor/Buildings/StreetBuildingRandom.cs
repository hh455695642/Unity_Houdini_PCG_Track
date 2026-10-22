#if UNITY_EDITOR
using System;
using System.Globalization;
using System.Linq;
using HoudiniEngineUnity;
using PCGBike.Buildings;
using UnityEditor;
using UnityEngine;

namespace PCGBike.Editor.Buildings
{
    // 编辑期随机上下文；请求与身份只保存在 HDA 实例，场景组件没有第二份配置。
    internal static class StreetBuildingRandom
    {
        internal enum Group { All = -1, Replay = -2, Massing = 0, Ground = 1, Upper = 2, Attachments = 3 }
        internal static readonly string[] Groups = { "massing", "ground", "upper", "attachments" };
        internal static bool Enabled(HEU_HoudiniAsset a) => StreetBuildingInstanceParameters.Int(a, "random_algorithm", 1) == 2;

        // 与 VEX sb_rng_hash/sb_rng_next 共用测试向量。所有中间值在 int32 范围内。
        internal static int Hash(string text)
        {
            int h = 17;
            foreach (char c in text)
            {
                if (c > 127) throw new ArgumentException("随机键仅允许稳定 ASCII token。");
                // 模 2^31 的多项式散列拆成 17+14 位计算；两端均无 int32 溢出，也不压缩成 20 位。
                int low = (h % 16384) * 131 + c;
                int high = ((h / 16384) * 131 + low / 16384) % 131072;
                h = high * 16384 + low % 16384;
            }
            return h >= 2147483646 ? h - 2147483645 : h + 1;
        }

        internal static int Next(ref int state)
        {
            if (state <= 0 || state >= int.MaxValue) throw new ArgumentOutOfRangeException(nameof(state));
            int value = 16807 * (state % 127773) - 2836 * (state / 127773);
            state = value > 0 ? value : value + int.MaxValue;
            return state;
        }

        // 无偏有界整数，不使用浮点取整或直接取模。宽范围使用两次采样，避免 high+1 溢出。
        internal static int Integer(int low, int high, int key)
        {
            if (low > high) throw new ArgumentOutOfRangeException(nameof(high));
            if (low == high) return low;
            int state = key;
            const ulong radix = 2147483646UL;
            ulong width = (ulong)((long)high - low + 1), domain = radix * radix;
            ulong cutoff = domain - domain % width, value;
            do { value = ((ulong)Next(ref state) - 1) * radix + (ulong)Next(ref state) - 1; } while (value >= cutoff);
            return (int)((long)low + (long)(value % width));
        }

        internal static float Fraction(float low, float high, int key)
        {
            if (!float.IsFinite(low) || !float.IsFinite(high) || low > high) throw new ArgumentOutOfRangeException(nameof(high));
            if (low == high) return low;
            int state = key;
            return (float)(low + ((Next(ref state) - 1) / 2147483646.0) * ((double)high - low));
        }

        internal static int Integral(float value, string field)
        {
            if (!float.IsFinite(value) || value != Math.Truncate(value) || value < int.MinValue || (double)value > int.MaxValue)
                throw new InvalidOperationException(field + " 必须使用合法整数端点；请求已保留。");
            return (int)value;
        }

        internal static Group ForField(string name)
        {
            if (name == "attachments_enabled" || name == "ground_attachment_placement" || name.StartsWith("attachment_override_", StringComparison.Ordinal) || name.Contains("density") || name.EndsWith("max_count", StringComparison.Ordinal)) return Group.Attachments;
            if (name.StartsWith("facade_override_", StringComparison.Ordinal)) return name.Contains("shopfront") ? Group.Ground : Group.Upper;
            if (name == "window_count" || name == "facade_rhythm") return Group.Upper;
            if (name.StartsWith("shopfront", StringComparison.Ordinal) || name == "@shopfront_faces" || name == "entrance_count" || name.StartsWith("ground_", StringComparison.Ordinal) || name == "residential_door_enabled") return Group.Ground;
            return Group.Massing;
        }

        internal sealed class Context
        {
            internal readonly string Identity;
            internal readonly int Master, Variation;
            private readonly int[] sequences;
            internal Context(HEU_HoudiniAsset a)
            {
                Identity = StreetBuildingInstanceParameters.String(a, "random_instance_id");
                if (string.IsNullOrWhiteSpace(Identity)) throw new InvalidOperationException("V2 随机身份未初始化，请先显式生成或初始化身份。");
                Master = StreetBuildingInstanceParameters.Int(a, "random_seed");
                Variation = StreetBuildingInstanceParameters.Int(a, "variation_seed");
                sequences = Groups.Select(g => StreetBuildingInstanceParameters.Int(a, "random_seq_" + g)).ToArray();
            }
            internal int Key(Group group, string field)
            {
                string extra = field == "ground_floor_use" ? "|variation=" + Variation.ToString(CultureInfo.InvariantCulture) : "";
                return Hash(FormattableString.Invariant($"2|{Identity}|{Master}|{Groups[(int)group]}|{sequences[(int)group]}|{field}{extra}"));
            }
        }
        // 每次抽样只读取一次隐藏上下文，避免对每个字段重复扫描全部 HAPI 参数。
        internal static Context Capture(HEU_HoudiniAsset a) => new(a);
        internal static int Key(HEU_HoudiniAsset a, Group group, string field) => Capture(a).Key(group, field);

        internal static int Pick(Context context, string field, int mask, int size)
        {
            if (mask <= 0 || size <= 0 || size > 30 || (mask & ~((1 << size) - 1)) != 0)
                throw new InvalidOperationException("无效随机候选：" + field);
            var options = Enumerable.Range(0, size).Where(i => (mask & (1 << i)) != 0).ToArray();
            return options[Integer(0, options.Length - 1, context.Key(ForField(field), field))];
        }

        internal static void Upgrade(HEU_HoudiniAsset a)
        {
            if (!StreetBuildingInstanceParameters.Exists(a, "random_algorithm")) throw new InvalidOperationException("请先更新 HDA definition 并 Rebuild。");
            if (Enabled(a)) return;
            StreetBuildingParameterTransaction.Run(a, "启用 StreetBuilding 随机算法 V2", () =>
            {
                StreetBuildingInstanceParameters.SetInt(a, "random_algorithm", 2);
                StreetBuildingInstanceParameters.SetString(a, "random_instance_id", Guid.NewGuid().ToString("N"));
                foreach (string group in Groups) StreetBuildingInstanceParameters.SetInt(a, "random_seq_" + group, 0);
            });
        }

        internal static void Advance(HEU_HoudiniAsset a, Group selected)
        {
            string id = StreetBuildingInstanceParameters.String(a, "random_instance_id");
            // 复制来的身份在下一次显式生成中去重，保留复制当下的已有外观，不隐式 Cook。
            bool duplicate = Resources.FindObjectsOfTypeAll<StreetBuildingAuthoring>().Any(owner =>
            {
                var other = owner.GetComponent<HEU_HoudiniAssetRoot>()?.HoudiniAsset;
                if (!owner.gameObject.scene.IsValid() || other == null || other == a) return false;
                string otherId = other.IsAssetValid() ? StreetBuildingInstanceParameters.String(other, "random_instance_id")
                    : other.Parameters?.GetParameter("random_instance_id")?._stringValues?.FirstOrDefault();
                return otherId == id;
            });
            if (selected == Group.Replay && (string.IsNullOrEmpty(id) || duplicate))
                throw new InvalidOperationException("随机身份缺失或与副本重复；请先显式生成建立独立方案。");
            if (string.IsNullOrEmpty(id) || duplicate) StreetBuildingInstanceParameters.SetString(a, "random_instance_id", Guid.NewGuid().ToString("N"));
            if (selected == Group.Replay) return;
            foreach (string group in Groups)
            {
                if (selected != Group.All && Groups[(int)selected] != group) continue;
                string name = "random_seq_" + group;
                int value = StreetBuildingInstanceParameters.Int(a, name);
                if (value == int.MaxValue) throw new InvalidOperationException("随机组序号已达上限：" + group);
                StreetBuildingInstanceParameters.SetInt(a, name, value + 1);
            }
        }

        internal static GameObject Duplicate(StreetBuildingAuthoring owner)
        {
            var a = owner.GetComponent<HEU_HoudiniAssetRoot>()?.HoudiniAsset;
            if (!Enabled(a)) throw new InvalidOperationException("独立方案复制需要随机算法 V2。");
            StreetBuildingPanelState.Observe(owner);
            var state = StreetBuildingPanelState.Get(owner);
            if (state.Cooking || state.Requested || state.NeedsResultValidation || state.Result == null || state.Result.inputHash != state.CurrentHash)
                throw new InvalidOperationException("请先成功生成当前参数，再复制为独立建筑。");
            GameObject copy = null;
            try
            {
                // HEU 的公开复制 API 负责 HAPI/输入/生成资产；项目只保留自己的绑定与随机身份。
                using (StreetBuildingRecook.Suppress()) copy = a.DuplicateAsset();
                if (copy == null || copy == owner.gameObject) throw new InvalidOperationException("HDA 副本创建失败。");
                Undo.RegisterCreatedObjectUndo(copy, "复制独立 StreetBuilding");
                var copyOwner = copy.GetComponent<StreetBuildingAuthoring>() ?? copy.AddComponent<StreetBuildingAuthoring>();
                EditorUtility.CopySerialized(owner, copyOwner);
                var copyAsset = copy.GetComponent<HEU_HoudiniAssetRoot>().HoudiniAsset;
                StreetBuildingParameterTransaction.Run(copyAsset, "初始化副本随机身份", () =>
                    StreetBuildingInstanceParameters.SetString(copyAsset, "random_instance_id", Guid.NewGuid().ToString("N")));
                // 当前外观沿用原方案；新身份将在下一次主动生成时生效，绝不伪装成已经验证的新结果。
                StreetBuildingPanelState.MarkNeedsValidation(copyOwner);
                StreetBuildingRecook.Attach();
                return copy;
            }
            catch
            {
                if (copy != null && copy != owner.gameObject) UnityEngine.Object.DestroyImmediate(copy);
                throw;
            }
        }
    }
}
#endif
