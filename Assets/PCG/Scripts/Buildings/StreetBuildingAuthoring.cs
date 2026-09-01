using UnityEngine;
using UnityEngine.Serialization;

namespace PCGBike.Buildings
{
    /// <summary>
    /// Scene-persistent editor authoring link. It has no Update loop and never
    /// cooks or saves automatically; explicit editor commands own persistence.
    /// </summary>
    [DisallowMultipleComponent]
    [AddComponentMenu("PCG Bike/Street Building/Authoring")]
    public sealed class StreetBuildingAuthoring : MonoBehaviour
    {
        [SerializeField] private StreetBuildingStyleConfig _fixedStyleConfig;
        [SerializeField] private StreetBuildingStyleLibrary _styleLibrary;
        [SerializeField] private string _buildingId;
        [SerializeField] private string _usageTag;
        [FormerlySerializedAs("_designPreset")]
        [SerializeField] private StreetBuildingGenerationPreset _generationPreset;
        [SerializeField] private int _variationSeed;
        [SerializeField, HideInInspector] private string _lastAppliedPayloadSha256;
        [SerializeField, HideInInspector] private string _lastAppliedDesignSha256;
        [SerializeField, HideInInspector] private string _lastCookDiagnostic;

        public StreetBuildingStyleConfig FixedStyleConfig => _fixedStyleConfig;
        public StreetBuildingStyleLibrary StyleLibrary => _styleLibrary;
        public string BuildingId => string.IsNullOrWhiteSpace(_buildingId) ? gameObject.name : _buildingId;
        public string UsageTag => _usageTag;
        public StreetBuildingGenerationPreset GenerationPreset => _generationPreset;
        [System.Obsolete("Use GenerationPreset.")]
        public StreetBuildingDesignPreset DesignPreset => _generationPreset as StreetBuildingDesignPreset;
        public int VariationSeed => _variationSeed;
        public string LastAppliedPayloadSha256 => _lastAppliedPayloadSha256;
        public string LastAppliedDesignSha256 => _lastAppliedDesignSha256;
        public string LastCookDiagnostic => _lastCookDiagnostic;

        public StreetBuildingStyleConfig ResolveStyle()
        {
            if (_fixedStyleConfig != null)
                return _fixedStyleConfig;
            return _styleLibrary == null
                ? null
                : _styleLibrary.ResolveStyle(BuildingId, _variationSeed, _usageTag);
        }

#if UNITY_EDITOR
        public void SetEditorFixedStyle(StreetBuildingStyleConfig styleConfig)
        {
            _fixedStyleConfig = styleConfig;
        }

        public void SetEditorStyleLibrary(
            StreetBuildingStyleLibrary styleLibrary, string buildingId, string usageTag = null)
        {
            _styleLibrary = styleLibrary;
            _buildingId = buildingId ?? string.Empty;
            _usageTag = usageTag ?? string.Empty;
        }

        public void SetEditorDesign(StreetBuildingGenerationPreset preset, int variationSeed)
        {
            _generationPreset = preset;
            _variationSeed = variationSeed;
        }

        public void SetEditorAppliedPayloadSha256(string sha256)
        {
            _lastAppliedPayloadSha256 = sha256 ?? string.Empty;
        }

        public void SetEditorAppliedDesignSha256(string sha256)
        {
            _lastAppliedDesignSha256 = sha256 ?? string.Empty;
        }


        public void SetEditorCookDiagnostic(string diagnostic)
        {
            _lastCookDiagnostic = diagnostic ?? string.Empty;
        }
#endif
    }
}
