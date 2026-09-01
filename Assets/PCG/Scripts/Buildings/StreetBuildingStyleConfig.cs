using System;
using System.Collections.Generic;
using UnityEngine;

namespace PCGBike.Buildings
{
    [Flags]
    public enum StreetBuildingFacadeMask
    {
        None = 0,
        Front = 1 << 0,
        SecondaryFront = 1 << 1,
        Side = 1 << 2,
        Rear = 1 << 3,
        All = Front | SecondaryFront | Side | Rear,
    }

    [Flags]
    public enum StreetBuildingFloorMask
    {
        None = 0,
        Ground = 1 << 0,
        Upper = 1 << 1,
        Roof = 1 << 2,
        All = Ground | Upper | Roof,
    }

    public enum StreetBuildingModuleHeightType
    {
        GroundFloor,
        TypicalFloor,
        Absolute,
        AttachmentBounds,
    }

    public enum StreetBuildingModuleGroup
    {
        GroundFacade,
        UpperFacade,
        SideRear,
        ConvexConcaveCorner,
        ColumnTrimCornice,
        RoofParapet,
        Attachments,
    }

    /// <summary>
    /// 美术唯一可见的建筑风格事实源。每个条目只引用一个 Prefab；复合几何在 Prefab 内完成。
    /// </summary>
    [CreateAssetMenu(fileName = "SBStyle_New", menuName = "PCG/Street Building/Style Config")]
    public sealed class StreetBuildingStyleConfig : ScriptableObject
    {
        public const int CurrentSchemaVersion = 4;

        [SerializeField] private int _schemaVersion = CurrentSchemaVersion;
        [SerializeField] private string _styleId = "new_streetbuilding_style";
        [SerializeField] private string _displayName = "新建筑风格";
        [SerializeField, Min(.01f)] private float _cellWidth = 2f;
        [SerializeField, Min(.01f)] private float _groundFloorHeight = 4f;
        [SerializeField, Min(.01f)] private float _typicalFloorHeight = 3f;
        [SerializeField] private List<string> _allowedAssetRoots = new();

        [SerializeField] private List<StreetBuildingModuleDefinition> _groundFacade = new();
        [SerializeField] private List<StreetBuildingModuleDefinition> _upperFacade = new();
        [SerializeField] private List<StreetBuildingModuleDefinition> _sideRear = new();
        [SerializeField] private List<StreetBuildingModuleDefinition> _convexConcaveCorners = new();
        [SerializeField] private List<StreetBuildingModuleDefinition> _columnTrimCornice = new();
        [SerializeField] private List<StreetBuildingModuleDefinition> _roofParapet = new();
        [SerializeField] private List<StreetBuildingModuleDefinition> _attachments = new();

        public int SchemaVersion => _schemaVersion;
        public string StyleId => _styleId;
        public string DisplayName => _displayName;
        public float CellWidth => _cellWidth;
        public float GroundFloorHeight => _groundFloorHeight;
        public float TypicalFloorHeight => _typicalFloorHeight;
        public IReadOnlyList<string> AllowedAssetRoots => _allowedAssetRoots;
        public IReadOnlyList<StreetBuildingModuleDefinition> GroundFacade => _groundFacade;
        public IReadOnlyList<StreetBuildingModuleDefinition> UpperFacade => _upperFacade;
        public IReadOnlyList<StreetBuildingModuleDefinition> SideRear => _sideRear;
        public IReadOnlyList<StreetBuildingModuleDefinition> ConvexConcaveCorners => _convexConcaveCorners;
        public IReadOnlyList<StreetBuildingModuleDefinition> ColumnTrimCornice => _columnTrimCornice;
        public IReadOnlyList<StreetBuildingModuleDefinition> RoofParapet => _roofParapet;
        public IReadOnlyList<StreetBuildingModuleDefinition> Attachments => _attachments;

        public IEnumerable<(StreetBuildingModuleGroup Group, StreetBuildingModuleDefinition Module)> EnumerateModules()
        {
            foreach (StreetBuildingModuleDefinition item in Enumerate(_groundFacade))
                yield return (StreetBuildingModuleGroup.GroundFacade, item);
            foreach (StreetBuildingModuleDefinition item in Enumerate(_upperFacade))
                yield return (StreetBuildingModuleGroup.UpperFacade, item);
            foreach (StreetBuildingModuleDefinition item in Enumerate(_sideRear))
                yield return (StreetBuildingModuleGroup.SideRear, item);
            foreach (StreetBuildingModuleDefinition item in Enumerate(_convexConcaveCorners))
                yield return (StreetBuildingModuleGroup.ConvexConcaveCorner, item);
            foreach (StreetBuildingModuleDefinition item in Enumerate(_columnTrimCornice))
                yield return (StreetBuildingModuleGroup.ColumnTrimCornice, item);
            foreach (StreetBuildingModuleDefinition item in Enumerate(_roofParapet))
                yield return (StreetBuildingModuleGroup.RoofParapet, item);
            foreach (StreetBuildingModuleDefinition item in Enumerate(_attachments))
                yield return (StreetBuildingModuleGroup.Attachments, item);
        }

        private static IEnumerable<StreetBuildingModuleDefinition> Enumerate(
            IEnumerable<StreetBuildingModuleDefinition> source) =>
            source ?? Array.Empty<StreetBuildingModuleDefinition>();

#if UNITY_EDITOR
        public void SetEditorData(int schemaVersion, string styleId, string displayName,
            float cellWidth, float groundFloorHeight, float typicalFloorHeight,
            IEnumerable<string> allowedAssetRoots,
            IDictionary<StreetBuildingModuleGroup, List<StreetBuildingModuleDefinition>> groups)
        {
            _schemaVersion = schemaVersion;
            _styleId = styleId ?? string.Empty;
            _displayName = displayName ?? string.Empty;
            _cellWidth = cellWidth;
            _groundFloorHeight = groundFloorHeight;
            _typicalFloorHeight = typicalFloorHeight;
            _allowedAssetRoots = allowedAssetRoots == null ? new List<string>() : new List<string>(allowedAssetRoots);
            _groundFacade = Get(groups, StreetBuildingModuleGroup.GroundFacade);
            _upperFacade = Get(groups, StreetBuildingModuleGroup.UpperFacade);
            _sideRear = Get(groups, StreetBuildingModuleGroup.SideRear);
            _convexConcaveCorners = Get(groups, StreetBuildingModuleGroup.ConvexConcaveCorner);
            _columnTrimCornice = Get(groups, StreetBuildingModuleGroup.ColumnTrimCornice);
            _roofParapet = Get(groups, StreetBuildingModuleGroup.RoofParapet);
            _attachments = Get(groups, StreetBuildingModuleGroup.Attachments);
        }

        private static List<StreetBuildingModuleDefinition> Get(
            IDictionary<StreetBuildingModuleGroup, List<StreetBuildingModuleDefinition>> groups,
            StreetBuildingModuleGroup key) =>
            groups != null && groups.TryGetValue(key, out List<StreetBuildingModuleDefinition> value)
                ? new List<StreetBuildingModuleDefinition>(value)
                : new List<StreetBuildingModuleDefinition>();
#endif
    }

    [Serializable]
    public sealed class StreetBuildingModuleDefinition
    {
        [SerializeField] private GameObject _prefab;
        [SerializeField] private string _variantId;
        [SerializeField] private StreetBuildingModuleRole _moduleRole;
        [SerializeField, Min(1)] private int _widthSpan = 1;
        [SerializeField, Min(1)] private int _depthSpan = 1;
        [SerializeField] private StreetBuildingModuleHeightType _heightType = StreetBuildingModuleHeightType.TypicalFloor;
        [SerializeField, Min(0f)] private float _absoluteHeight;
        [SerializeField, Min(.001f)] private float _weight = 1f;
        [SerializeField] private bool _enabled = true;
        [SerializeField] private StreetBuildingFacadeMask _allowedFacades = StreetBuildingFacadeMask.All;
        [SerializeField] private StreetBuildingFloorMask _allowedFloors = StreetBuildingFloorMask.All;

        public GameObject Prefab => _prefab;
        public string VariantId => _variantId;
        public StreetBuildingModuleRole ModuleRole => _moduleRole;
        public int WidthSpan => Mathf.Max(1, _widthSpan);
        public int DepthSpan => Mathf.Max(1, _depthSpan);
        public StreetBuildingModuleHeightType HeightType => _heightType;
        public float AbsoluteHeight => _absoluteHeight;
        public float Weight => _weight;
        public bool Enabled => _enabled;
        public StreetBuildingFacadeMask AllowedFacades => _allowedFacades;
        public StreetBuildingFloorMask AllowedFloors => _allowedFloors;

        public float ResolveHeight(StreetBuildingStyleConfig style) => _heightType switch
        {
            StreetBuildingModuleHeightType.GroundFloor => style.GroundFloorHeight,
            StreetBuildingModuleHeightType.TypicalFloor => style.TypicalFloorHeight,
            StreetBuildingModuleHeightType.Absolute => _absoluteHeight,
            _ => 0f,
        };

#if UNITY_EDITOR
        public StreetBuildingModuleDefinition(GameObject prefab, string variantId,
            StreetBuildingModuleRole moduleRole, int widthSpan, int depthSpan,
            StreetBuildingModuleHeightType heightType, float absoluteHeight, float weight,
            bool enabled, StreetBuildingFacadeMask allowedFacades,
            StreetBuildingFloorMask allowedFloors)
        {
            _prefab = prefab;
            _variantId = variantId ?? string.Empty;
            _moduleRole = moduleRole;
            _widthSpan = Mathf.Max(1, widthSpan);
            _depthSpan = Mathf.Max(1, depthSpan);
            _heightType = heightType;
            _absoluteHeight = Mathf.Max(0f, absoluteHeight);
            _weight = weight;
            _enabled = enabled;
            _allowedFacades = allowedFacades;
            _allowedFloors = allowedFloors;
        }

        public void SetEditorVariantId(string variantId) => _variantId = variantId ?? string.Empty;
#endif
    }
}
