using UnityEngine;

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
        [SerializeField] private StreetBuildingInstanceModuleCatalog _catalog;
        [SerializeField] private StreetBuildingDesignPreset _designPreset;
        [SerializeField] private int _variationSeed;
        [SerializeField, HideInInspector] private string _lastAppliedPayloadSha256;
        [SerializeField, HideInInspector] private string _lastAppliedDesignSha256;

        public StreetBuildingInstanceModuleCatalog Catalog => _catalog;
        public StreetBuildingDesignPreset DesignPreset => _designPreset;
        public int VariationSeed => _variationSeed;
        public string LastAppliedPayloadSha256 => _lastAppliedPayloadSha256;
        public string LastAppliedDesignSha256 => _lastAppliedDesignSha256;

#if UNITY_EDITOR
        public void SetEditorCatalog(StreetBuildingInstanceModuleCatalog catalog)
        {
            _catalog = catalog;
        }

        public void SetEditorDesign(StreetBuildingDesignPreset preset, int variationSeed)
        {
            _designPreset = preset;
            _variationSeed = variationSeed;
            if (preset != null)
                _catalog = preset.Catalog;
        }

        public void SetEditorAppliedPayloadSha256(string sha256)
        {
            _lastAppliedPayloadSha256 = sha256 ?? string.Empty;
        }

        public void SetEditorAppliedDesignSha256(string sha256)
        {
            _lastAppliedDesignSha256 = sha256 ?? string.Empty;
        }
#endif
    }
}
