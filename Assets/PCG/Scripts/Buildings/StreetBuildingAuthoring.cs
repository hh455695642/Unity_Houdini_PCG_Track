using UnityEngine;

namespace PCGBike.Buildings
{
    /// <summary>
    /// Scene-persistent editor authoring link. It has no Update loop and never
    /// cooks or saves automatically; the Editor inspector performs explicit work.
    /// </summary>
    [DisallowMultipleComponent]
    [AddComponentMenu("PCG Bike/Street Building/Authoring")]
    public sealed class StreetBuildingAuthoring : MonoBehaviour
    {
        [SerializeField] private StreetBuildingInstanceModuleCatalog _catalog;
        [SerializeField, HideInInspector] private string _lastAppliedPayloadSha256;

        public StreetBuildingInstanceModuleCatalog Catalog => _catalog;
        public string LastAppliedPayloadSha256 => _lastAppliedPayloadSha256;

#if UNITY_EDITOR
        public void SetEditorCatalog(StreetBuildingInstanceModuleCatalog catalog)
        {
            _catalog = catalog;
        }

        public void SetEditorAppliedPayloadSha256(string sha256)
        {
            _lastAppliedPayloadSha256 = sha256 ?? string.Empty;
        }
#endif
    }
}
