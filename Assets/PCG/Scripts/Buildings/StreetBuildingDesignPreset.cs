using UnityEngine;

namespace PCGBike.Buildings
{
    public enum StreetBuildingGroundUse { Auto, Residential, Retail, Mixed }
    public enum StreetBuildingFacadeRhythm { Auto, Uniform, Alternating, CenterAccent, Paired }
    public enum StreetBuildingRearMode { Off, SimpleCap, FullFacade }
    public enum StreetBuildingSideMode { Auto, Off, Force }

    /// <summary>
    /// Artist-owned, reusable design intent. It maps only to the existing HDA
    /// interface; runtime builds consume the saved/baked Unity result.
    /// </summary>
    [CreateAssetMenu(fileName = "StreetBuildingDesignPreset",
        menuName = "PCG/Street Building Design Preset")]
    public sealed class StreetBuildingDesignPreset : ScriptableObject
    {
        [SerializeField] private StreetBuildingInstanceModuleCatalog _catalog;
        [SerializeField] private float _width = 12;
        [SerializeField] private float _depth = 10;
        [SerializeField, Range(2, 12)] private int _floors = 4;
        [SerializeField] private bool _cornerBuilding;
        [SerializeField] private StreetBuildingGroundUse _groundUse = StreetBuildingGroundUse.Mixed;
        [SerializeField] private StreetBuildingFacadeRhythm _facadeRhythm = StreetBuildingFacadeRhythm.CenterAccent;
        [SerializeField, Range(0, 1)] private float _shopfrontRatio = .65f;
        [SerializeField] private StreetBuildingSideMode _sideMode = StreetBuildingSideMode.Force;
        [SerializeField] private StreetBuildingRearMode _rearMode = StreetBuildingRearMode.FullFacade;
        [SerializeField] private bool _generateRoof = true;
        [SerializeField] private float _parapetHeight = .6f;
        [SerializeField] private bool _generateArchitecturalTrim = true;
        [SerializeField] private bool _generateAttachments = true;
        [SerializeField, Range(0, 1)] private float _detailDensity = .6f;
        [SerializeField] private int _baseSeed = 1;

        public StreetBuildingInstanceModuleCatalog Catalog => _catalog;
        public float Width => _width;
        public float Depth => _depth;
        public int Floors => _floors;
        public bool CornerBuilding => _cornerBuilding;
        public StreetBuildingGroundUse GroundUse => _groundUse;
        public StreetBuildingFacadeRhythm FacadeRhythm => _facadeRhythm;
        public float ShopfrontRatio => _shopfrontRatio;
        public StreetBuildingSideMode SideMode => _sideMode;
        public StreetBuildingRearMode RearMode => _rearMode;
        public bool GenerateRoof => _generateRoof;
        public float ParapetHeight => _parapetHeight;
        public bool GenerateArchitecturalTrim => _generateArchitecturalTrim;
        public bool GenerateAttachments => _generateAttachments;
        public float DetailDensity => _detailDensity;
        public int BaseSeed => _baseSeed;

#if UNITY_EDITOR
        public void SetEditorData(StreetBuildingInstanceModuleCatalog catalog, float width, float depth,
            int floors, bool cornerBuilding, StreetBuildingGroundUse groundUse,
            StreetBuildingFacadeRhythm facadeRhythm, float shopfrontRatio,
            StreetBuildingSideMode sideMode, StreetBuildingRearMode rearMode, bool generateRoof,
            float parapetHeight, bool generateArchitecturalTrim, bool generateAttachments,
            float detailDensity, int baseSeed)
        {
            _catalog = catalog;
            _width = width;
            _depth = depth;
            _floors = floors;
            _cornerBuilding = cornerBuilding;
            _groundUse = groundUse;
            _facadeRhythm = facadeRhythm;
            _shopfrontRatio = shopfrontRatio;
            _sideMode = sideMode;
            _rearMode = rearMode;
            _generateRoof = generateRoof;
            _parapetHeight = parapetHeight;
            _generateArchitecturalTrim = generateArchitecturalTrim;
            _generateAttachments = generateAttachments;
            _detailDensity = detailDensity;
            _baseSeed = baseSeed;
        }
#endif
    }
}
