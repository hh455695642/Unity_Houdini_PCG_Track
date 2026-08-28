using System;
using System.Collections.Generic;
using UnityEngine;

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
        [SerializeField] private string _styleId = "na_brick_mixeduse_01";
        [SerializeField] private string _sourceRoot;
        [SerializeField] private string _sourceSha256;
        [SerializeField] private List<StreetBuildingInstanceModuleRecipe> _modules = new();

        public string StyleId => _styleId;
        public string SourceRoot => _sourceRoot;
        public string SourceSha256 => _sourceSha256;
        public IReadOnlyList<StreetBuildingInstanceModuleRecipe> Modules => _modules;

#if UNITY_EDITOR
        public void SetEditorData(
            string styleId,
            string sourceRoot,
            string sourceSha256,
            IEnumerable<StreetBuildingInstanceModuleRecipe> modules)
        {
            _styleId = styleId;
            _sourceRoot = sourceRoot;
            _sourceSha256 = sourceSha256;
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
        [SerializeField] private GameObject _sourceFbx;
        [SerializeField] private Vector3 _localPosition;
        [SerializeField] private Vector3 _localEulerRotation;

        public GameObject SourceFbx => _sourceFbx;
        public Vector3 LocalPosition => _localPosition;
        public Vector3 LocalEulerRotation => _localEulerRotation;

#if UNITY_EDITOR
        public StreetBuildingInstancePart(
            GameObject sourceFbx,
            Vector3 localPosition,
            Vector3 localEulerRotation)
        {
            _sourceFbx = sourceFbx;
            _localPosition = localPosition;
            _localEulerRotation = localEulerRotation;
        }
#endif
    }
}
