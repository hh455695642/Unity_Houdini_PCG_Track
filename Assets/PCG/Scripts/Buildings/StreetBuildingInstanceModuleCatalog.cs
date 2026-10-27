namespace PCGBike.Buildings
{
    /// <summary>稳定模块语义。数值只追加，不重排；Unity→Houdini 模块载荷依赖该顺序。</summary>
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
        RoofSurface,
        ParapetCorner,
        ParapetConcaveCorner,
        FloorBandCorner, // 首层凸角腰线收口；追加编号 22，保持已有载荷兼容。
        DrainPipe, // 追加 23；连续管线零件，数量仍由实例控制。
    }

    /// <summary>附件素材规格。X|1 元数据使用稳定整数；禁止从文件名推断语义。</summary>
    public enum StreetBuildingAttachmentSubtype
    {
        Generic = 0,
        WaterTower = 1,
        Chimney = 2,
        FireEscapeStoreyLeft = 3,
        FireEscapeStoreyRight = 4,
        FireEscapeTop = 5,
        FireEscapeBottom = 6,
        RoofAccess = 7,
        DrainStraight = 8,
        DrainTop = 9,
        DrainBottom = 10,
        DrainElbow = 11,
        DrainOffset = 12,
        FireEscapePlatform = 13,
        FireEscapeFlightLeft = 14,
        FireEscapeFlightRight = 15,
    }
}
