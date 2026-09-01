using System;
using System.Collections.Generic;
using System.Linq;
using UnityEngine;

namespace PCGBike.Buildings
{
    /// <summary>
    /// 轻量风格索引。每个条目只引用一个独立 StyleConfig。
    /// </summary>
    [CreateAssetMenu(fileName = "StreetBuildingStyleLibrary",
        menuName = "PCG/Street Building Style Library")]
    public sealed class StreetBuildingStyleLibrary : ScriptableObject
    {
        [SerializeField] private List<StreetBuildingStyleLibraryEntry> _styles = new();

        public IReadOnlyList<StreetBuildingStyleLibraryEntry> Styles => _styles;

        public StreetBuildingStyleConfig ResolveStyle(
            string buildingId, int variationSeed, string usageTag = null)
        {
            StreetBuildingStyleLibraryEntry[] candidates = _styles
                .Where(item => item != null && item.Enabled && item.StyleConfig != null
                               && item.Weight > 0 && item.Matches(usageTag))
                .OrderBy(item => item.StyleConfig.StyleId, StringComparer.Ordinal)
                .ToArray();
            if (candidates.Length == 0)
                return null;

            double total = candidates.Sum(item => (double)item.Weight);
            double cursor = StableUnit(buildingId, variationSeed, usageTag) * total;
            foreach (StreetBuildingStyleLibraryEntry candidate in candidates)
            {
                cursor -= candidate.Weight;
                if (cursor <= 0)
                    return candidate.StyleConfig;
            }
            return candidates[candidates.Length - 1].StyleConfig;
        }

        public static uint StableHash(string buildingId, int seed, string salt)
        {
            const uint offset = 2166136261;
            const uint prime = 16777619;
            uint hash = offset;
            string value = string.Concat(buildingId ?? string.Empty, "|", seed, "|", salt ?? string.Empty);
            foreach (char character in value)
            {
                hash ^= character;
                hash *= prime;
            }
            return hash;
        }

        private static double StableUnit(string buildingId, int seed, string salt) =>
            StableHash(buildingId, seed, salt) / ((double)uint.MaxValue + 1.0);

#if UNITY_EDITOR
        public void SetEditorData(IEnumerable<StreetBuildingStyleLibraryEntry> styles)
        {
            _styles = styles == null
                ? new List<StreetBuildingStyleLibraryEntry>()
                : new List<StreetBuildingStyleLibraryEntry>(styles);
        }
#endif
    }

    [Serializable]
    public sealed class StreetBuildingStyleLibraryEntry
    {
        [SerializeField] private StreetBuildingStyleConfig _styleConfig;
        [SerializeField, Min(0.001f)] private float _weight = 1;
        [SerializeField] private bool _enabled = true;
        [SerializeField] private List<string> _usageTags = new();

        public StreetBuildingStyleConfig StyleConfig => _styleConfig;
        public float Weight => _weight;
        public bool Enabled => _enabled;
        public IReadOnlyList<string> UsageTags => _usageTags;

        public bool Matches(string usageTag) => string.IsNullOrWhiteSpace(usageTag)
                                                || _usageTags == null || _usageTags.Count == 0
                                                || _usageTags.Any(item => string.Equals(
                                                    item, usageTag, StringComparison.OrdinalIgnoreCase));

#if UNITY_EDITOR
        public StreetBuildingStyleLibraryEntry(
            StreetBuildingStyleConfig styleConfig, float weight = 1,
            bool enabled = true, IEnumerable<string> usageTags = null)
        {
            _styleConfig = styleConfig;
            _weight = weight;
            _enabled = enabled;
            _usageTags = usageTags == null ? new List<string>() : new List<string>(usageTags);
        }
#endif
    }
}
