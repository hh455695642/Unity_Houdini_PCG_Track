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
        [SerializeField, Min(.01f)] private float _cellWidth = 2f;
        [SerializeField, HideInInspector] private float _groundFloorHeight = 4f;
        [SerializeField, HideInInspector] private float _typicalFloorHeight = 3f;
        [SerializeField, HideInInspector] private int _layerSchema;
        [SerializeField] private StreetBuildingLayerConfig _ground = new(4f);
        [SerializeField] private StreetBuildingLayerConfig _upper = new(3f);
        [SerializeField] private StreetBuildingLayerConfig _roof = new(0f);

        [SerializeField, HideInInspector] private List<StreetBuildingModuleDefinition> _groundFacade = new();
        [SerializeField, HideInInspector] private List<StreetBuildingModuleDefinition> _upperFacade = new();
        [SerializeField, HideInInspector] private List<StreetBuildingModuleDefinition> _sideRear = new();
        [SerializeField, HideInInspector] private List<StreetBuildingModuleDefinition> _convexConcaveCorners = new();
        [SerializeField, HideInInspector] private List<StreetBuildingModuleDefinition> _columnTrimCornice = new();
        [SerializeField, HideInInspector] private List<StreetBuildingModuleDefinition> _roofParapet = new();
        [SerializeField, HideInInspector] private List<StreetBuildingModuleDefinition> _attachments = new();

        public float CellWidth => _cellWidth;
        public float GroundFloorHeight => _layerSchema == 0 ? _groundFloorHeight : _ground.Height;
        public float TypicalFloorHeight => _layerSchema == 0 ? _typicalFloorHeight : _upper.Height;
        public StreetBuildingLayerConfig Ground => _ground;
        public StreetBuildingLayerConfig Upper => _upper;
        public StreetBuildingLayerConfig Roof => _roof;
        public bool NeedsLayerMigration => _layerSchema == 0;

        public IEnumerable<(StreetBuildingModuleGroup Group, StreetBuildingModuleDefinition Module)> EnumerateModules()
        {
            if (_layerSchema > 0)
            {
                foreach (var item in EnumerateLayerModules()) yield return (item.Group, item.Module);
                yield break;
            }
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

        public IEnumerable<(StreetBuildingFloorMask Floor, StreetBuildingModuleGroup Group,
            StreetBuildingModuleDefinition Module)> EnumerateLayerModules()
        {
            foreach (var pair in new[] { (StreetBuildingFloorMask.Ground, _ground),
                         (StreetBuildingFloorMask.Upper, _upper), (StreetBuildingFloorMask.Roof, _roof) })
                foreach (var item in pair.Item2.Enumerate(pair.Item1))
                    yield return (pair.Item1, item.Group, item.Module);
        }

#if UNITY_EDITOR
        // Editor-only incremental migration. Build all destination lists before
        // replacing the live data; never duplicate Prefab assets or their GUIDs.
        public bool MigrateLayers()
        {
            if (_layerSchema > 0) return false;
            var ground = new StreetBuildingLayerConfig(_groundFloorHeight);
            var upper = new StreetBuildingLayerConfig(_typicalFloorHeight);
            var roof = new StreetBuildingLayerConfig(0f);
            foreach (var item in EnumerateModules())
            {
                var m = item.Module;
                if (m == null || m.Prefab == null || !Enum.IsDefined(typeof(StreetBuildingModuleRole), m.ModuleRole)
                    || m.AllowedFloors == StreetBuildingFloorMask.None || (m.AllowedFloors & ~StreetBuildingFloorMask.All) != 0)
                    throw new InvalidOperationException($"{name}/{item.Group}: invalid legacy module; migration stopped.");
                foreach (var pair in new[] { (StreetBuildingFloorMask.Ground, ground),
                             (StreetBuildingFloorMask.Upper, upper), (StreetBuildingFloorMask.Roof, roof) })
                    if ((m.AllowedFloors & pair.Item1) != 0)
                        pair.Item2.Add(item.Group, m.CopyForFloor(pair.Item1));
            }
            _ground = ground; _upper = upper; _roof = roof; _layerSchema = 1;
            _groundFacade.Clear(); _upperFacade.Clear(); _sideRear.Clear();
            _convexConcaveCorners.Clear(); _columnTrimCornice.Clear(); _roofParapet.Clear(); _attachments.Clear();
            return true;
        }

        public void SetEditorData(float cellWidth, float groundFloorHeight, float typicalFloorHeight,
            IDictionary<StreetBuildingModuleGroup, List<StreetBuildingModuleDefinition>> groups)
        {
            _cellWidth = cellWidth;
            _groundFloorHeight = groundFloorHeight;
            _typicalFloorHeight = typicalFloorHeight;
            _groundFacade = Get(groups, StreetBuildingModuleGroup.GroundFacade);
            _upperFacade = Get(groups, StreetBuildingModuleGroup.UpperFacade);
            _sideRear = Get(groups, StreetBuildingModuleGroup.SideRear);
            _convexConcaveCorners = Get(groups, StreetBuildingModuleGroup.ConvexConcaveCorner);
            _columnTrimCornice = Get(groups, StreetBuildingModuleGroup.ColumnTrimCornice);
            _roofParapet = Get(groups, StreetBuildingModuleGroup.RoofParapet);
            _attachments = Get(groups, StreetBuildingModuleGroup.Attachments);
            _layerSchema = 0;
            MigrateLayers();
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
    public sealed class StreetBuildingLayerConfig
    {
        [SerializeField, Min(0)] private float _height;
        [SerializeField] private List<StreetBuildingModuleDefinition> _facade = new();
        [SerializeField] private List<StreetBuildingModuleDefinition> _sideRear = new();
        [SerializeField] private List<StreetBuildingModuleDefinition> _corners = new();
        [SerializeField] private List<StreetBuildingModuleDefinition> _trim = new();
        [SerializeField] private List<StreetBuildingModuleDefinition> _roofSurface = new();
        [SerializeField] private List<StreetBuildingModuleDefinition> _attachments = new();
        [SerializeField] private StreetBuildingLayerRules _rules = new();
        public float Height => _height;
        public StreetBuildingLayerRules Rules => _rules;
        public StreetBuildingLayerConfig(float height) { _height = height; }
        public IEnumerable<(StreetBuildingModuleGroup Group, StreetBuildingModuleDefinition Module)> Enumerate(StreetBuildingFloorMask floor)
        {
            // 分类枚举保持旧数值；楼层归属由调用方的层上下文独立派生。
            foreach (var m in _facade) yield return (m != null && (int)m.ModuleRole <= 3
                ? StreetBuildingModuleGroup.GroundFacade : StreetBuildingModuleGroup.UpperFacade, m);
            foreach (var m in _sideRear) yield return (StreetBuildingModuleGroup.SideRear, m);
            foreach (var m in _corners) yield return (StreetBuildingModuleGroup.ConvexConcaveCorner, m);
            foreach (var m in _trim) yield return (StreetBuildingModuleGroup.ColumnTrimCornice, m);
            foreach (var m in _roofSurface) yield return (StreetBuildingModuleGroup.RoofParapet, m);
            foreach (var m in _attachments) yield return (StreetBuildingModuleGroup.Attachments, m);
        }
#if UNITY_EDITOR
        internal void Add(StreetBuildingModuleGroup group, StreetBuildingModuleDefinition module)
        {
            var list = group switch {
                StreetBuildingModuleGroup.GroundFacade or StreetBuildingModuleGroup.UpperFacade => _facade,
                StreetBuildingModuleGroup.SideRear => _sideRear,
                StreetBuildingModuleGroup.ConvexConcaveCorner => _corners,
                StreetBuildingModuleGroup.ColumnTrimCornice => _trim,
                StreetBuildingModuleGroup.RoofParapet => _roofSurface,
                StreetBuildingModuleGroup.Attachments => _attachments,
                _ => throw new ArgumentOutOfRangeException(nameof(group)) };
            list.Add(module);
        }
#endif
    }

    // These defaults mirror the current HDA interface. Extension point: add
    // optional authoring rules here; they are compiled only in the Editor.
    [Serializable]
    public sealed class StreetBuildingLayerRules
    {
        public int groundUse;
        [Range(0, 2)] public int layoutMode;
        [Range(0, 4)] public int rhythm;
        [Range(0, 1)] public float shopfrontRatio = .65f;
        public int entranceMin = 1, entranceMax = 1;
        public int shopDoorMin, shopDoorMax = 1;
        public int shopfrontMin = 1, shopfrontMax = 4;
        public int windowMin = 2, windowMax = 8;
        public int blankMin, blankMax = 4;
        public bool trimEnabled = true, attachmentsEnabled = true, roofEnabled = true;
        [Min(0)] public float parapetHeight = .6f;
        [Range(0, 1)] public float density = .6f;
        public StreetBuildingAttachmentRule awning = new(1f, 8);
        public StreetBuildingAttachmentRule sign = new(.72f, 8);
        public StreetBuildingAttachmentRule fireEscape = new(.5f, 4);
        public StreetBuildingAttachmentRule wallAC = new(.28f, 16);
        public StreetBuildingAttachmentRule roofProps = new(.55f, 8);
    }

    [Serializable]
    public sealed class StreetBuildingAttachmentRule
    {
        public bool enabled = true;
        [Range(0, 1)] public float density;
        [Range(0, 64)] public int maxCount;
        public StreetBuildingFacadeMask facades = StreetBuildingFacadeMask.All;
        public StreetBuildingAttachmentRule(float density, int maxCount)
        { this.density = density; this.maxCount = maxCount; }
    }

    [Serializable]
    public sealed class StreetBuildingModuleDefinition
    {
        [SerializeField] private GameObject _prefab;
        [SerializeField] private StreetBuildingModuleRole _moduleRole;
        [SerializeField, Min(1)] private int _widthSpan = 1;
        [SerializeField, Min(1)] private int _depthSpan = 1;
        [SerializeField] private StreetBuildingModuleHeightType _heightType = StreetBuildingModuleHeightType.TypicalFloor;
        [SerializeField, Min(0f)] private float _absoluteHeight;
        [SerializeField, Min(.001f)] private float _weight = 1f;
        [SerializeField] private bool _enabled = true;
        [SerializeField] private StreetBuildingFacadeMask _allowedFacades = StreetBuildingFacadeMask.All;
        [SerializeField, HideInInspector] private StreetBuildingFloorMask _allowedFloors = StreetBuildingFloorMask.All;

        public GameObject Prefab => _prefab;
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
        internal StreetBuildingModuleDefinition CopyForFloor(StreetBuildingFloorMask floor) =>
            new(_prefab, _moduleRole, _widthSpan, _depthSpan, _heightType, _absoluteHeight,
                _weight, _enabled, _allowedFacades, floor);
        public StreetBuildingModuleDefinition(GameObject prefab, StreetBuildingModuleRole moduleRole,
            int widthSpan, int depthSpan,
            StreetBuildingModuleHeightType heightType, float absoluteHeight, float weight,
            bool enabled, StreetBuildingFacadeMask allowedFacades,
            StreetBuildingFloorMask allowedFloors)
        {
            _prefab = prefab;
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

#endif
    }
}
