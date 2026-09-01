using System;
using UnityEngine;

namespace PCGBike.Buildings
{
    public enum StreetBuildingGroundUse { Auto, Residential, Retail, Mixed }
    public enum StreetBuildingFacadeRhythm { Auto, Uniform, Alternating, CenterAccent, Paired }
    public enum StreetBuildingRearMode { Off, SimpleCap, FullFacade }
    public enum StreetBuildingSideMode { Auto, Off, Force }
    public enum StreetBuildingMassingShape { Rectangle, LShape }
    public enum StreetBuildingNotchSide { RearLeft, RearRight }

    /// <summary>旧资产兼容壳。现有 GUID 保留，但数据语义已由 GenerationPreset 提供且不再引用风格。</summary>
    [Obsolete("Use StreetBuildingGenerationPreset. Existing assets remain compatible to preserve GUIDs.")]
    public sealed class StreetBuildingDesignPreset : StreetBuildingGenerationPreset { }
}
