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
        [FormerlySerializedAs("_designPreset")]
        [SerializeField] private StreetBuildingGenerationPreset _generationPreset;
        [SerializeField] private int _variationSeed;
        [SerializeField, HideInInspector] private string _lastAppliedPayloadSha256;
        [SerializeField, HideInInspector] private string _lastAppliedDesignSha256;
        [SerializeField, HideInInspector] private string _lastCookDiagnostic;

        public StreetBuildingStyleConfig FixedStyleConfig => _fixedStyleConfig;
        public StreetBuildingGenerationPreset GenerationPreset => _generationPreset;
        [System.Obsolete("Use GenerationPreset.")]
        public StreetBuildingDesignPreset DesignPreset => _generationPreset as StreetBuildingDesignPreset;
        public int VariationSeed => _variationSeed;
        public string LastAppliedPayloadSha256 => _lastAppliedPayloadSha256;
        public string LastAppliedDesignSha256 => _lastAppliedDesignSha256;
        public string LastCookDiagnostic => _lastCookDiagnostic;

        /// <summary>每个 HDA 显式绑定唯一 StyleConfig；保留此入口以兼容现有调用方。</summary>
        public StreetBuildingStyleConfig ResolveStyle() => _fixedStyleConfig;

#if UNITY_EDITOR
        public void SetEditorFixedStyle(StreetBuildingStyleConfig styleConfig)
        {
            _fixedStyleConfig = styleConfig;
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
