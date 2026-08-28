using System;
using System.Collections.Generic;
using UnityEngine;
using UnityEngine.Serialization;

namespace PCGBike.Buildings
{
    /// <summary>
    /// Logical roles used by the REV4.1 direct-instance selector. Keep the
    /// numeric order stable because catalog assets serialize this enum.
    /// </summary>
    public enum StreetBuildingModuleRole
    {
        GroundShop,
        GroundShopDoor,
        GroundWall,
        Entrance,
        MiddleWindow,
        MiddleBlank,
        CornerConvex,
        CornerConcave,
        Cornice,
        Parapet,
        SideWall,
        RearWall,
        FacadeColumn,
        FloorBand,
        Awning,
        Sign,
        FireEscape,
        ACUnit,
        RoofProp,
    }

    public enum StreetBuildingAssetSourceKind
    {
        ProjectOwned,
        ExternalReadOnly,
    }

    /// <summary>
    /// Editor-authored selector table for REV4. Entries reference imported FBX
    /// model prefabs directly; no source vertices are copied into project assets.
    /// Runtime builds consume baked/optimized data in a later phase.
    /// </summary>
    [CreateAssetMenu(
        fileName = "StreetBuildingInstanceModuleCatalog",
        menuName = "PCG/Street Building Instance Module Catalog")]
    public sealed class StreetBuildingInstanceModuleCatalog : ScriptableObject
    {
        public const int CurrentSchemaVersion = 1;

        [SerializeField] private int _schemaVersion = CurrentSchemaVersion;
        [SerializeField] private string _displayName = "Street Building Style";
        [SerializeField] private StreetBuildingAssetSourceKind _sourceKind;
        [SerializeField] private string _styleId = "na_brick_mixeduse_01";
        [SerializeField] private string _sourceRoot;
        [SerializeField] private string _sourceSha256;
        [SerializeField] private List<string> _allowedAssetRoots = new();
        [SerializeField] private float _cellWidth = 2.0f;
        [SerializeField] private float _groundFloorHeight = 4.0f;
        [SerializeField] private float _typicalFloorHeight = 3.0f;
        [SerializeField] private List<StreetBuildingInstanceModuleRecipe> _modules = new();

        public int SchemaVersion => _schemaVersion;
        public string DisplayName => _displayName;
        public StreetBuildingAssetSourceKind SourceKind => _sourceKind;
        public string StyleId => _styleId;
        public string SourceRoot => _sourceRoot;
        public string SourceSha256 => _sourceSha256;
        public IReadOnlyList<string> AllowedAssetRoots => _allowedAssetRoots;
        public float CellWidth => _cellWidth;
        public float GroundFloorHeight => _groundFloorHeight;
        public float TypicalFloorHeight => _typicalFloorHeight;
        public IReadOnlyList<StreetBuildingInstanceModuleRecipe> Modules => _modules;

#if UNITY_EDITOR
        public void SetEditorData(
            int schemaVersion,
            string displayName,
            StreetBuildingAssetSourceKind sourceKind,
            string styleId,
            string sourceRoot,
            string sourceSha256,
            IEnumerable<string> allowedAssetRoots,
            float cellWidth,
            float groundFloorHeight,
            float typicalFloorHeight,
            IEnumerable<StreetBuildingInstanceModuleRecipe> modules)
        {
            _schemaVersion = schemaVersion;
            _displayName = displayName;
            _sourceKind = sourceKind;
            _styleId = styleId;
            _sourceRoot = sourceRoot;
            _sourceSha256 = sourceSha256;
            _allowedAssetRoots = allowedAssetRoots == null
                ? new List<string>()
                : new List<string>(allowedAssetRoots);
            _cellWidth = cellWidth;
            _groundFloorHeight = groundFloorHeight;
            _typicalFloorHeight = typicalFloorHeight;
            _modules = modules == null
                ? new List<StreetBuildingInstanceModuleRecipe>()
                : new List<StreetBuildingInstanceModuleRecipe>(modules);
        }
#endif
    }

    [Serializable]
    public sealed class StreetBuildingInstanceModuleRecipe
    {
        [SerializeField] private StreetBuildingModuleRole _moduleRole;
        [SerializeField] private string _variantId;
        [SerializeField] private float _cellWidth = 2.0f;
        [SerializeField] private float _cellHeight = 3.0f;
        [SerializeField] private float _weight = 1.0f;
        [SerializeField] private List<StreetBuildingInstancePart> _parts = new();

        public StreetBuildingModuleRole ModuleRole => _moduleRole;
        public string VariantId => _variantId;
        public float CellWidth => _cellWidth;
        public float CellHeight => _cellHeight;
        public float Weight => _weight;
        public IReadOnlyList<StreetBuildingInstancePart> Parts => _parts;

#if UNITY_EDITOR
        public StreetBuildingInstanceModuleRecipe(
            StreetBuildingModuleRole moduleRole,
            string variantId,
            float cellWidth,
            float cellHeight,
            float weight,
            IEnumerable<StreetBuildingInstancePart> parts)
        {
            _moduleRole = moduleRole;
            _variantId = variantId;
            _cellWidth = cellWidth;
            _cellHeight = cellHeight;
            _weight = weight;
            _parts = parts == null
                ? new List<StreetBuildingInstancePart>()
                : new List<StreetBuildingInstancePart>(parts);
        }
#endif
    }

    [Serializable]
    public sealed class StreetBuildingInstancePart
    {
        [FormerlySerializedAs("_sourceFbx")]
        [SerializeField] private GameObject _sourceAsset;
        [SerializeField] private Vector3 _localPosition;
        [SerializeField] private Vector3 _localEulerRotation;

        public GameObject SourceAsset => _sourceAsset;

        [Obsolete("Use SourceAsset. Catalog parts now support Prefab and Model Prefab assets.")]
        public GameObject SourceFbx => _sourceAsset;
        public Vector3 LocalPosition => _localPosition;
        public Vector3 LocalEulerRotation => _localEulerRotation;

#if UNITY_EDITOR
        public StreetBuildingInstancePart(
            GameObject sourceAsset,
            Vector3 localPosition,
            Vector3 localEulerRotation)
        {
            _sourceAsset = sourceAsset;
            _localPosition = localPosition;
            _localEulerRotation = localEulerRotation;
        }
#endif
    }
}
