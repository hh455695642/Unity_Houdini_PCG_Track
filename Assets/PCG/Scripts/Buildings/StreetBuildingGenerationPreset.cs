using System;
using System.Collections.Generic;
using UnityEngine;

namespace PCGBike.Buildings
{
    public enum StreetBuildingFacadeControlMode { Auto, RandomRange, Manual }
    public enum StreetBuildingFacadeTarget { Front, SecondaryFront, Side, Rear }
    public enum StreetBuildingAttachmentKind { Awning, Sign, FireEscape, WallAC, RoofProps }

    [Serializable]
    public struct StreetBuildingCountRange
    {
        [Min(0)] public int Min;
        [Min(0)] public int Max;

        public int NormalizedMin => Mathf.Max(0, Mathf.Min(Min, Max));
        public int NormalizedMax => Mathf.Max(0, Mathf.Max(Min, Max));
    }

    [Serializable]
    public sealed class StreetBuildingFacadeOverride
    {
        [SerializeField] private StreetBuildingFacadeTarget _facade;
        [SerializeField, Min(1)] private int _floorFrom = 1;
        [SerializeField, Min(1)] private int _floorTo = 1;
        [SerializeField] private StreetBuildingFacadeControlMode _mode;
        [SerializeField] private StreetBuildingFacadeRhythm _rhythm;
        [SerializeField] private StreetBuildingCountRange _entrance;
        [SerializeField] private StreetBuildingCountRange _shopDoor;
        [SerializeField] private StreetBuildingCountRange _shopfront;
        [SerializeField] private StreetBuildingCountRange _window;
        [SerializeField] private StreetBuildingCountRange _blank;

        public StreetBuildingFacadeTarget Facade => _facade;
        public int FloorFrom => Mathf.Max(1, _floorFrom);
        public int FloorTo => Mathf.Max(FloorFrom, _floorTo);
        public StreetBuildingFacadeControlMode Mode => _mode;
        public StreetBuildingFacadeRhythm Rhythm => _rhythm;
        public StreetBuildingCountRange Entrance => _entrance;
        public StreetBuildingCountRange ShopDoor => _shopDoor;
        public StreetBuildingCountRange Shopfront => _shopfront;
        public StreetBuildingCountRange Window => _window;
        public StreetBuildingCountRange Blank => _blank;
    }

    [Serializable]
    public sealed class StreetBuildingAttachmentRule
    {
        [SerializeField] private StreetBuildingAttachmentKind _kind;
        [SerializeField, Range(0, 1)] private float _density;
        [SerializeField, Range(0, 64)] private int _maximumCount = 8;
        [SerializeField] private StreetBuildingFacadeMask _facades = StreetBuildingFacadeMask.All;
        [SerializeField, Min(1)] private int _floorFrom = 1;
        [SerializeField, Min(1)] private int _floorTo = 99;

        public StreetBuildingAttachmentKind Kind => _kind;
        public float Density => _density;
        public int MaximumCount => _maximumCount;
        public StreetBuildingFacadeMask Facades => _facades;
        public int FloorFrom => Mathf.Max(1, _floorFrom);
        public int FloorTo => Mathf.Max(FloorFrom, _floorTo);

#if UNITY_EDITOR
        public StreetBuildingAttachmentRule(StreetBuildingAttachmentKind kind, float density,
            int maximumCount, StreetBuildingFacadeMask facades, int floorFrom, int floorTo)
        {
            _kind = kind; _density = Mathf.Clamp01(density); _maximumCount = Mathf.Clamp(maximumCount, 0, 64);
            _facades = facades; _floorFrom = Mathf.Max(1, floorFrom); _floorTo = Mathf.Max(_floorFrom, floorTo);
        }
#endif
    }

    /// <summary>仅保存体块与生成规则，不包含任何建筑风格或模块资产引用。</summary>
    [CreateAssetMenu(fileName = "SBGeneration_New", menuName = "PCG/Street Building/Generation Preset")]
    public class StreetBuildingGenerationPreset : ScriptableObject
    {
        [SerializeField] private float _width = 12;
        [SerializeField] private float _depth = 10;
        [SerializeField] private StreetBuildingMassingShape _massingShape;
        [SerializeField] private float _notchWidth = 4;
        [SerializeField] private float _notchDepth = 4;
        [SerializeField] private StreetBuildingNotchSide _notchSide;
        [SerializeField, Range(1, 12)] private int _floors = 4;
        [SerializeField] private bool _cornerBuilding;
        [SerializeField] private StreetBuildingGroundUse _groundUse = StreetBuildingGroundUse.Mixed;
        [SerializeField] private StreetBuildingFacadeControlMode _facadeMode;
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
        [SerializeField] private List<StreetBuildingFacadeOverride> _facadeOverrides = new();
        [SerializeField] private List<StreetBuildingAttachmentRule> _attachmentRules = new();

        public float Width => _width;
        public float Depth => _depth;
        public StreetBuildingMassingShape MassingShape => _massingShape;
        public float NotchWidth => _notchWidth;
        public float NotchDepth => _notchDepth;
        public StreetBuildingNotchSide NotchSide => _notchSide;
        public int Floors => _floors;
        public bool CornerBuilding => _cornerBuilding;
        public StreetBuildingGroundUse GroundUse => _groundUse;
        public StreetBuildingFacadeControlMode FacadeMode => _facadeMode;
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
        public IReadOnlyList<StreetBuildingFacadeOverride> FacadeOverrides => _facadeOverrides;
        public IReadOnlyList<StreetBuildingAttachmentRule> AttachmentRules => _attachmentRules;

#if UNITY_EDITOR
        public void SetEditorData(float width, float depth, int floors, bool cornerBuilding,
            StreetBuildingGroundUse groundUse, StreetBuildingFacadeRhythm facadeRhythm,
            float shopfrontRatio, StreetBuildingSideMode sideMode, StreetBuildingRearMode rearMode,
            bool generateRoof, float parapetHeight, bool generateArchitecturalTrim,
            bool generateAttachments, float detailDensity, int baseSeed,
            StreetBuildingMassingShape massingShape = StreetBuildingMassingShape.Rectangle,
            float notchWidth = 4, float notchDepth = 4,
            StreetBuildingNotchSide notchSide = StreetBuildingNotchSide.RearLeft,
            StreetBuildingFacadeControlMode facadeMode = StreetBuildingFacadeControlMode.Auto,
            IEnumerable<StreetBuildingFacadeOverride> overrides = null,
            IEnumerable<StreetBuildingAttachmentRule> attachmentRules = null)
        {
            _width = width; _depth = depth; _floors = floors; _cornerBuilding = cornerBuilding;
            _groundUse = groundUse; _facadeMode = facadeMode; _facadeRhythm = facadeRhythm;
            _shopfrontRatio = shopfrontRatio; _sideMode = sideMode; _rearMode = rearMode;
            _generateRoof = generateRoof; _parapetHeight = parapetHeight;
            _generateArchitecturalTrim = generateArchitecturalTrim;
            _generateAttachments = generateAttachments; _detailDensity = detailDensity;
            _baseSeed = baseSeed; _massingShape = massingShape; _notchWidth = notchWidth;
            _notchDepth = notchDepth; _notchSide = notchSide;
            _facadeOverrides = overrides == null ? new List<StreetBuildingFacadeOverride>() : new List<StreetBuildingFacadeOverride>(overrides);
            _attachmentRules = attachmentRules == null ? new List<StreetBuildingAttachmentRule>() : new List<StreetBuildingAttachmentRule>(attachmentRules);
        }

        public void SetEditorAttachmentRules(IEnumerable<StreetBuildingAttachmentRule> rules) =>
            _attachmentRules = rules == null ? new List<StreetBuildingAttachmentRule>() : new List<StreetBuildingAttachmentRule>(rules);
#endif
    }
}
