"""StreetBuilding V12: HDA-panel generation single source.

The patch is based on the current V10 definition. ``preview`` mutates only the
loaded Live node and leaves the definition/HIP untouched. ``commit`` is called
only after the regression gates pass.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import hou


ASSET_PATH = "/obj/StreetBuilding_DEV"
ASSET_TYPE = "pcgbike::StreetBuilding::1.0"
CORE_NAME = "StreetBuildingCore"
PREVIOUS_MARKER = "STREETBUILDING_V10_VERSIONLESS_STYLE_PAYLOAD"
MARKER = "STREETBUILDING_V12_HDA_PANEL_GENERATION"


VALUE_MAP = {
    "site_source": "site_source",
    "module_source": "module_source",
    "internal_width": "building_width",
    "internal_depth": "building_depth",
    "massing_shape": "massing_shape",
    "notch_width": "l_notch_width",
    "notch_depth": "l_notch_depth",
    "notch_side": "l_notch_side",
    "corner_building": "corner_building",
    "floor_count": "floor_count",
    "ground_floor_height": "floor_height_ground",
    "typical_floor_height": "floor_height_typical",
    "parapet_height": "parapet_height",
    "rear_mode": "rear_facade_mode",
    "side_mode": "side_facade_mode",
    "generate_roof": "roof_enabled",
    "facade_control_mode": "facade_layout_mode",
    "target_bay_width": "proxy_bay_width_target",
    "minimum_bay_width": "proxy_bay_width_min",
    "maximum_bay_width": "proxy_bay_width_max",
    "ground_use": "ground_floor_use",
    "facade_rhythm": "facade_rhythm",
    "shopfront_ratio": "shopfront_ratio",
    "entrance_count_min": "entrance_count_min",
    "entrance_count_max": "entrance_count_max",
    "shopdoor_count_min": "shop_door_count_min",
    "shopdoor_count_max": "shop_door_count_max",
    "shopfront_count_min": "shopfront_count_min",
    "shopfront_count_max": "shopfront_count_max",
    "window_count_min": "window_count_min",
    "window_count_max": "window_count_max",
    "blank_count_min": "blank_count_min",
    "blank_count_max": "blank_count_max",
    "detail_density": "attachment_global_density",
    "generate_architectural_trim": "architectural_trim_enabled",
    "generate_attachments": "attachments_enabled",
    "attachment_0_density": "awning_density",
    "attachment_0_max": "awning_max_count",
    "attachment_1_density": "sign_density",
    "attachment_1_max": "sign_max_count",
    "attachment_2_density": "fire_escape_density",
    "attachment_2_max": "fire_escape_max_count",
    "attachment_3_density": "wall_ac_density",
    "attachment_3_max": "wall_ac_max_count",
    "attachment_4_density": "roof_props_density",
    "attachment_4_max": "roof_props_max_count",
    "seed": "variation_seed",
    "generate_lods": "lod_outputs_enabled",
    "debug_metadata": "debug_metadata_enabled",
    "wall_unity_material": "proxy_wall_material",
    "trim_unity_material": "proxy_trim_material",
    "window_unity_material": "proxy_window_material",
    "unity_instance_catalog": "unity_style_catalog",
    "unity_bridge_end_marker": "unity_bridge_end_marker",
}


def _help(template: hou.ParmTemplate, text: str) -> hou.ParmTemplate:
    template.setHelp(text)
    return template


def _hide(template: hou.ParmTemplate, expression: str) -> hou.ParmTemplate:
    template.setConditional(hou.parmCondType.HideWhen, expression)
    return template


def _disable(template: hou.ParmTemplate, expression: str) -> hou.ParmTemplate:
    template.setConditional(hou.parmCondType.DisableWhen, expression)
    return template


def _menu(name: str, label: str, items: tuple[str, ...], labels: tuple[str, ...],
          default: int = 0) -> hou.MenuParmTemplate:
    return hou.MenuParmTemplate(name, label, items, labels, default_value=default)


def _float(name: str, label: str, default: float, minimum: float, maximum: float,
           strict_min: bool = False, strict_max: bool = False) -> hou.FloatParmTemplate:
    return hou.FloatParmTemplate(name, label, 1, (default,), min=minimum, max=maximum,
                                 min_is_strict=strict_min, max_is_strict=strict_max)


def _int(name: str, label: str, default: int, minimum: int, maximum: int,
         strict_min: bool = False, strict_max: bool = False) -> hou.IntParmTemplate:
    return hou.IntParmTemplate(name, label, 1, (default,), min=minimum, max=maximum,
                               min_is_strict=strict_min, max_is_strict=strict_max)


def _toggle(name: str, label: str, default: bool) -> hou.ToggleParmTemplate:
    return hou.ToggleParmTemplate(name, label, default_value=default)


def _string(name: str, label: str, default: str) -> hou.StringParmTemplate:
    return hou.StringParmTemplate(name, label, 1, (default,),
                                  string_type=hou.stringParmType.Regular)


def _parameter_group(asset: hou.Node) -> hou.ParmTemplateGroup:
    old = asset.parmTemplateGroup()
    standard = next((item for item in old.parmTemplates()
                     if item.label() == "Standard"), None)
    entries: list[hou.ParmTemplate] = [standard] if standard is not None else []

    source = hou.FolderParmTemplate("sb_source", "来源 / Source", folder_type=hou.folderType.Simple)
    source.addParmTemplate(_help(_menu(
        "site_source", "地块来源 / Site Source", ("internal", "external"),
        ("内部测试地块 / Internal Test Parcel", "外部输入 1 / External Input 1")),
        "Internal 使用本 HDA 的建筑宽深；External 使用输入 1，并允许地块规则覆盖面板。"))
    source.addParmTemplate(_help(_menu(
        "module_source", "模块来源 / Module Source", ("internal_proxy", "unity_asset_instances"),
        ("内部代理 / Internal Proxy", "Unity StyleConfig 实例 / Unity StyleConfig Instances")),
        "Unity 模式的模块目录与风格尺寸由 StreetBuildingAuthoring 写入。"))
    source.addParmTemplate(_help(_hide(_float(
        "proxy_bay_width_target", "代理目标开间宽 / Proxy Target Bay Width (m)", 3.0, .1, 12.0),
        "{ module_source == unity_asset_instances }"), "仅内部代理网格使用；Unity StyleConfig 模式使用 Cell Width。"))
    source.addParmTemplate(_hide(_float(
        "proxy_bay_width_min", "代理最小开间宽 / Proxy Minimum Bay Width (m)", 2.4, .1, 12.0),
        "{ module_source == unity_asset_instances }"))
    source.addParmTemplate(_hide(_float(
        "proxy_bay_width_max", "代理最大开间宽 / Proxy Maximum Bay Width (m)", 3.6, .1, 20.0),
        "{ module_source == unity_asset_instances }"))

    massing = hou.FolderParmTemplate("sb_massing", "体块 / Massing", folder_type=hou.folderType.Simple)
    massing.addParmTemplate(_help(_hide(_float(
        "building_width", "建筑宽度 / Building Width (m)", 12.0, .1, 100.0),
        "{ site_source == external }"), "Unity StyleConfig 模式必须是 Cell Width 的整数倍，并至少保留两个 Cell。"))
    massing.addParmTemplate(_help(_hide(_float(
        "building_depth", "建筑深度 / Building Depth (m)", 10.0, .1, 100.0),
        "{ site_source == external }"), "Unity StyleConfig 模式必须是 Cell Width 的整数倍，并至少保留两个 Cell。"))
    massing.addParmTemplate(_menu(
        "massing_shape", "体块形状 / Massing Shape", ("rectangle", "l_shape"),
        ("矩形 / Rectangle", "L 形 / L Shape")))
    massing.addParmTemplate(_help(_hide(_float(
        "l_notch_width", "L 缺口宽度 / L Notch Width (m)", 4.0, 2.0, 100.0),
        "{ massing_shape == rectangle }"), "缺口必须对齐 StyleConfig Cell 网格，并保留两 Cell 宽的两条翼。"))
    massing.addParmTemplate(_hide(_float(
        "l_notch_depth", "L 缺口深度 / L Notch Depth (m)", 4.0, 2.0, 100.0),
        "{ massing_shape == rectangle }"))
    massing.addParmTemplate(_hide(_menu(
        "l_notch_side", "L 缺口方向 / L Notch Side", ("rear_left", "rear_right"),
        ("后左 / Rear Left", "后右 / Rear Right")), "{ massing_shape == rectangle }"))
    massing.addParmTemplate(_toggle("corner_building", "街角建筑 / Corner Building", False))
    massing.addParmTemplate(_help(_int(
        "floor_count", "楼层数 / Floor Count", 4, 1, 12, True, True),
        "正式支持 1–12 层；超出范围会阻断 Cook。"))
    massing.addParmTemplate(_help(_disable(_float(
        "floor_height_ground", "首层高度 / Ground Floor Height (m)", 4.2, .1, 12.0, True),
        "{ module_source == unity_asset_instances }"), "Unity StyleConfig 模式由 StyleConfig 同步，禁止在 HDA 单独修改。"))
    massing.addParmTemplate(_help(_disable(_float(
        "floor_height_typical", "标准层高 / Typical Floor Height (m)", 3.2, .1, 8.0, True),
        "{ module_source == unity_asset_instances }"), "Unity StyleConfig 模式由 StyleConfig 同步，禁止在 HDA 单独修改。"))
    massing.addParmTemplate(_menu(
        "side_facade_mode", "侧立面模式 / Side Facade Mode", ("auto", "off", "force"),
        ("自动 / Auto", "关闭 / Off", "强制 / Force")))
    massing.addParmTemplate(_menu(
        "rear_facade_mode", "后立面模式 / Rear Facade Mode", ("off", "simple_cap", "full_facade"),
        ("关闭 / Off", "简单封面 / Simple Cap", "完整立面 / Full Facade")))

    facade = hou.FolderParmTemplate("sb_facade", "立面 / Facade", folder_type=hou.folderType.Simple)
    facade.addParmTemplate(_help(_menu(
        "facade_layout_mode", "布局模式 / Layout Mode", ("auto", "random_range", "manual"),
        ("自动 / Auto", "范围随机 / Random Range", "精确数量 / Manual")),
        "Auto 根据用途自动分配；Random Range 在 Min/Max 间确定性采样；Manual 使用 Min 字段作为精确数量。"))
    facade.addParmTemplate(_menu(
        "ground_floor_use", "首层用途 / Ground Floor Use",
        ("auto", "residential", "retail", "mixed"),
        ("自动 / Auto", "住宅 / Residential", "商业 / Retail", "混合 / Mixed")))
    facade.addParmTemplate(_menu(
        "facade_rhythm", "立面节奏 / Facade Rhythm",
        ("auto", "uniform", "alternating", "center_accent", "paired"),
        ("自动 / Auto", "均匀 / AAAAA", "交替 / ABABA", "中心强调 / AABAA", "成对 / AABBAA")))
    facade.addParmTemplate(_float(
        "shopfront_ratio", "橱窗比例 / Shopfront Ratio", .65, 0, 1, True, True))
    count_specs = (
        ("entrance", "主入口 / Entrance", 1, 1),
        ("shop_door", "店门 / Shop Door", 0, 1),
        ("shopfront", "铺面 / Shopfront", 1, 4),
        ("window", "窗 / Window", 2, 8),
        ("blank", "空白 / Blank", 0, 4),
    )
    for token, label, default_min, default_max in count_specs:
        facade.addParmTemplate(_hide(_int(
            f"{token}_count_min", f"{label} 数量 / Count", default_min, 0, 64, True, True),
            "{ facade_layout_mode == auto }"))
        facade.addParmTemplate(_hide(_int(
            f"{token}_count_max", f"{label} 最大值 / Maximum", default_max, 0, 64, True, True),
            "{ facade_layout_mode != random_range }"))

    facade_advanced = hou.FolderParmTemplate(
        "sb_facade_advanced", "高级楼层覆盖 / Advanced Floor Overrides",
        folder_type=hou.folderType.Collapsible)
    overrides = hou.FolderParmTemplate(
        "facade_overrides", "立面覆盖 / Facade Overrides",
        folder_type=hou.folderType.MultiparmBlock, default_value=0)
    overrides.addParmTemplate(_menu(
        "facade_override_target#", "目标立面 / Target Facade",
        ("front", "secondary_front", "side", "rear"),
        ("正面 / Front", "次正面 / Secondary Front", "侧面 / Side", "背面 / Rear")))
    overrides.addParmTemplate(_int("facade_override_floor_start#", "起始楼层 / Floor Start", 1, 1, 12, True, True))
    overrides.addParmTemplate(_int("facade_override_floor_end#", "结束楼层 / Floor End", 1, 1, 12, True, True))
    overrides.addParmTemplate(_menu(
        "facade_override_layout_mode#", "布局模式 / Layout Mode",
        ("auto", "random_range", "manual"),
        ("自动 / Auto", "范围随机 / Random Range", "精确数量 / Manual")))
    overrides.addParmTemplate(_menu(
        "facade_override_rhythm#", "立面节奏 / Rhythm",
        ("auto", "uniform", "alternating", "center_accent", "paired"),
        ("自动 / Auto", "均匀 / Uniform", "交替 / Alternating", "中心强调 / Center Accent", "成对 / Paired")))
    for token, label, _, _ in count_specs:
        overrides.addParmTemplate(_int(f"facade_override_{token}_min#", f"{label} 数量 / Count", 0, 0, 64, True, True))
        overrides.addParmTemplate(_int(f"facade_override_{token}_max#", f"{label} 最大值 / Maximum", 0, 0, 64, True, True))
    facade_advanced.addParmTemplate(overrides)
    facade.addParmTemplate(facade_advanced)

    roof = hou.FolderParmTemplate("sb_roof_trim", "屋顶与线脚 / Roof & Trim", folder_type=hou.folderType.Simple)
    roof.addParmTemplate(_toggle("roof_enabled", "生成屋顶 / Generate Roof", True))
    roof.addParmTemplate(_help(_hide(_float(
        "parapet_height", "女儿墙高度 / Parapet Height (m)", .6, 0, 3, True, True),
        "{ roof_enabled == 0 }"), "大于 0 时必须与 StyleConfig 的女儿墙模块高度一致。"))
    roof.addParmTemplate(_toggle(
        "architectural_trim_enabled", "生成建筑线脚 / Generate Architectural Trim", True))

    attachments = hou.FolderParmTemplate("sb_attachments", "附件 / Attachments", folder_type=hou.folderType.Simple)
    attachments.addParmTemplate(_toggle("attachments_enabled", "生成附件 / Generate Attachments", True))
    attachments.addParmTemplate(_help(_hide(_float(
        "attachment_global_density", "全局附件密度 / Global Attachment Density", .6, 0, 1, True, True),
        "{ attachments_enabled == 0 }"), "只影响附件实例，不改变 LOD0 外壳。"))
    attachment_specs = (
        ("awning", "雨棚 / Awning", 1.0, 8),
        ("sign", "招牌 / Sign", .72, 8),
        ("fire_escape", "消防梯 / Fire Escape", .5, 4),
        ("wall_ac", "墙面空调 / Wall AC", .28, 16),
        ("roof_props", "屋顶附件 / Roof Props", .55, 8),
    )
    for token, label, density, maximum in attachment_specs:
        attachments.addParmTemplate(_hide(_float(
            f"{token}_density", f"{label} 密度 / Density", density, 0, 1, True, True),
            "{ attachments_enabled == 0 }"))
        attachments.addParmTemplate(_hide(_int(
            f"{token}_max_count", f"{label} 最大数量 / Maximum", maximum, 0, 64, True, True),
            "{ attachments_enabled == 0 }"))

    attachment_advanced = hou.FolderParmTemplate(
        "sb_attachment_advanced", "高级附件覆盖 / Advanced Attachment Overrides",
        folder_type=hou.folderType.Collapsible)
    attachment_overrides = hou.FolderParmTemplate(
        "attachment_overrides", "附件覆盖 / Attachment Overrides",
        folder_type=hou.folderType.MultiparmBlock, default_value=0)
    attachment_overrides.addParmTemplate(_menu(
        "attachment_override_kind#", "附件类型 / Kind",
        ("awning", "sign", "fire_escape", "wall_ac", "roof_props"),
        ("雨棚 / Awning", "招牌 / Sign", "消防梯 / Fire Escape", "墙面空调 / Wall AC", "屋顶附件 / Roof Props")))
    attachment_overrides.addParmTemplate(_float(
        "attachment_override_density#", "密度 / Density", .5, 0, 1, True, True))
    attachment_overrides.addParmTemplate(_int(
        "attachment_override_max_count#", "最大数量 / Maximum", 8, 0, 64, True, True))
    attachment_overrides.addParmTemplate(_toggle("attachment_override_front#", "正面 / Front", True))
    attachment_overrides.addParmTemplate(_toggle("attachment_override_secondary_front#", "次正面 / Secondary Front", True))
    attachment_overrides.addParmTemplate(_toggle("attachment_override_side#", "侧面 / Side", True))
    attachment_overrides.addParmTemplate(_toggle("attachment_override_rear#", "背面 / Rear", True))
    attachment_overrides.addParmTemplate(_int(
        "attachment_override_floor_start#", "起始楼层 / Floor Start", 1, 1, 13, True, True))
    attachment_overrides.addParmTemplate(_int(
        "attachment_override_floor_end#", "结束楼层 / Floor End", 12, 1, 13, True, True))
    attachment_advanced.addParmTemplate(attachment_overrides)
    attachments.addParmTemplate(attachment_advanced)

    variation = hou.FolderParmTemplate("sb_variation", "随机 / Variation", folder_type=hou.folderType.Simple)
    variation.addParmTemplate(_help(_int(
        "variation_seed", "随机种子 / Variation Seed", 1, 0, 999999, True, False),
        "每个 HDA 的唯一随机入口；相同输入与 Seed 必须得到相同结果。"))

    output = hou.FolderParmTemplate("sb_output", "输出与调试 / Output & Debug", folder_type=hou.folderType.Simple)
    output.addParmTemplate(_toggle("lod_outputs_enabled", "生成 LOD1/LOD2 / Generate LOD1/LOD2", True))
    output.addParmTemplate(_toggle("debug_metadata_enabled", "调试元数据 / Debug Metadata", False))
    output.addParmTemplate(_hide(_string(
        "proxy_wall_material", "代理墙体材质 / Proxy Wall Material",
        "Assets/PCG/Materials/Buildings/M_StreetBuilding_Graybox_Wall.mat"), "{ module_source == unity_asset_instances }"))
    output.addParmTemplate(_hide(_string(
        "proxy_trim_material", "代理线脚材质 / Proxy Trim Material",
        "Assets/PCG/Materials/Buildings/M_StreetBuilding_Graybox_Trim.mat"), "{ module_source == unity_asset_instances }"))
    output.addParmTemplate(_hide(_string(
        "proxy_window_material", "代理窗户材质 / Proxy Window Material",
        "Assets/PCG/Materials/Buildings/M_StreetBuilding_Graybox_Window.mat"), "{ module_source == unity_asset_instances }"))

    bridge = hou.FolderParmTemplate(
        "sb_bridge", "Unity 自动桥接 / Unity Bridge",
        folder_type=hou.folderType.Collapsible)
    catalog = _string("unity_style_catalog", "Unity Style Catalog", "")
    marker = _string("unity_bridge_end_marker", "Unity Bridge End Marker", "END")
    bridge.addParmTemplate(catalog)
    bridge.addParmTemplate(marker)

    entries.extend((source, massing, facade, roof, attachments, variation, output, bridge))
    return hou.ParmTemplateGroup(entries)


CHANNEL_RENAMES = {
    old: new for old, new in VALUE_MAP.items() if old != new
}


PARSE_RULES = r'''// STREETBUILDING_V12_HDA_PANEL_RULES
void sbv12_apply_global(string payload; export float width; export float depth;
    export int shape; export float notch_w; export float notch_d; export int notch_side;
    export int floors; export int corner; export int ground_use; export int mode;
    export int rhythm; export float shop_ratio; export int side_mode; export int rear_mode;
    export int roof; export float parapet; export int trim; export int attachments;
    export float detail_density; export int seed)
{
    foreach (string row; split(payload, "\n"))
    {
        string f[] = split(strip(row), "|");
        if (len(f) != 21 || f[0] != "G") continue;
        if (atof(f[1]) > 0) width = atof(f[1]);
        if (atof(f[2]) > 0) depth = atof(f[2]);
        shape=atoi(f[3]); notch_w=atof(f[4]); notch_d=atof(f[5]); notch_side=atoi(f[6]);
        if (atoi(f[7]) > 0) floors=atoi(f[7]);
        corner=atoi(f[8]); ground_use=atoi(f[9]); mode=atoi(f[10]); rhythm=atoi(f[11]);
        shop_ratio=atof(f[12]); side_mode=atoi(f[13]); rear_mode=atoi(f[14]);
        roof=atoi(f[15]); parapet=atof(f[16]); trim=atoi(f[17]); attachments=atoi(f[18]);
        detail_density=atof(f[19]); seed=atoi(f[20]);
    }
}

float width=ch("../../building_width"); float depth=ch("../../building_depth");
int shape=chi("../../massing_shape"); float notch_w=ch("../../l_notch_width");
float notch_d=ch("../../l_notch_depth"); int notch_side=chi("../../l_notch_side");
int floors=clamp(chi("../../floor_count"),1,12); int corner=chi("../../corner_building");
int ground_use=chi("../../ground_floor_use"); int mode=chi("../../facade_layout_mode");
int rhythm=chi("../../facade_rhythm"); float shop_ratio=ch("../../shopfront_ratio");
int side_mode=chi("../../side_facade_mode"); int rear_mode=chi("../../rear_facade_mode");
int roof=chi("../../roof_enabled"); float parapet=ch("../../parapet_height");
int trim=chi("../../architectural_trim_enabled"); int attachments=chi("../../attachments_enabled");
float detail_density=ch("../../attachment_global_density"); int seed=chi("../../variation_seed");

string hda_payload="SBR1";
int count=chi("../../facade_overrides");
for (int i=1;i<=count;i++)
    hda_payload+=sprintf("\nO|%d|%d|%d|%d|%d|%d|%d|%d|%d|%d|%d|%d|%d|%d|%d",
        chi(sprintf("../../facade_override_target%d",i)),chi(sprintf("../../facade_override_floor_start%d",i)),
        chi(sprintf("../../facade_override_floor_end%d",i)),chi(sprintf("../../facade_override_layout_mode%d",i)),
        chi(sprintf("../../facade_override_rhythm%d",i)),chi(sprintf("../../facade_override_entrance_min%d",i)),
        chi(sprintf("../../facade_override_entrance_max%d",i)),chi(sprintf("../../facade_override_shop_door_min%d",i)),
        chi(sprintf("../../facade_override_shop_door_max%d",i)),chi(sprintf("../../facade_override_shopfront_min%d",i)),
        chi(sprintf("../../facade_override_shopfront_max%d",i)),chi(sprintf("../../facade_override_window_min%d",i)),
        chi(sprintf("../../facade_override_window_max%d",i)),chi(sprintf("../../facade_override_blank_min%d",i)),
        chi(sprintf("../../facade_override_blank_max%d",i)));
int acount=chi("../../attachment_overrides");
for (int i=1;i<=acount;i++)
{
    int mask=chi(sprintf("../../attachment_override_front%d",i))
        +2*chi(sprintf("../../attachment_override_secondary_front%d",i))
        +4*chi(sprintf("../../attachment_override_side%d",i))
        +8*chi(sprintf("../../attachment_override_rear%d",i));
    hda_payload+=sprintf("\nA|%d|%g|%d|%d|%d|%d",
        chi(sprintf("../../attachment_override_kind%d",i)),chf(sprintf("../../attachment_override_density%d",i)),
        chi(sprintf("../../attachment_override_max_count%d",i)),mask,
        chi(sprintf("../../attachment_override_floor_start%d",i)),chi(sprintf("../../attachment_override_floor_end%d",i)));
}

string parcel_payload="";
if (chi("../../site_source")==1 && nprimitives(0)>0 && hasprimattrib(0,"streetbuilding_rule_payload"))
    parcel_payload=string(prim(0,"streetbuilding_rule_payload",0));
if (len(strip(parcel_payload)))
    sbv12_apply_global(parcel_payload,width,depth,shape,notch_w,notch_d,notch_side,floors,
        corner,ground_use,mode,rhythm,shop_ratio,side_mode,rear_mode,roof,parapet,trim,
        attachments,detail_density,seed);

for (int p=0;p<nprimitives(0);p++)
{
    setprimattrib(0,"floor_count",p,floors,"set"); setprimattrib(0,"seed",p,seed,"set");
    setprimattrib(0,"rear_mode",p,rear_mode,"set"); setprimattrib(0,"side_mode",p,side_mode,"set");
}
setdetailattrib(0,"rule_payload_hda",hda_payload,"set");
setdetailattrib(0,"rule_payload_parcel",parcel_payload,"set");
setdetailattrib(0,"rule_source",len(strip(parcel_payload))?"parcel":"hda","set");
setdetailattrib(0,"effective_width",width,"set"); setdetailattrib(0,"effective_depth",depth,"set");
setdetailattrib(0,"effective_shape",shape,"set"); setdetailattrib(0,"effective_notch_width",notch_w,"set");
setdetailattrib(0,"effective_notch_depth",notch_d,"set"); setdetailattrib(0,"effective_notch_side",notch_side,"set");
setdetailattrib(0,"effective_floor_count",floors,"set"); setdetailattrib(0,"effective_corner",corner,"set");
setdetailattrib(0,"effective_ground_use",ground_use,"set"); setdetailattrib(0,"effective_facade_mode",mode,"set");
setdetailattrib(0,"effective_rhythm",rhythm,"set"); setdetailattrib(0,"effective_shopfront_ratio",clamp(shop_ratio,0,1),"set");
setdetailattrib(0,"effective_side_mode",side_mode,"set"); setdetailattrib(0,"effective_rear_mode",rear_mode,"set");
setdetailattrib(0,"effective_generate_roof",roof,"set"); setdetailattrib(0,"effective_parapet",max(0,parapet),"set");
setdetailattrib(0,"effective_trim",trim,"set"); setdetailattrib(0,"effective_attachments",attachments,"set");
setdetailattrib(0,"effective_detail_density",clamp(detail_density,0,1),"set"); setdetailattrib(0,"effective_seed",seed,"set");
'''


def _transform_snippet(node_name: str, source: str) -> str:
    if node_name == "PARSE_GENERATION_RULES":
        return PARSE_RULES
    result = source
    for old, new in CHANNEL_RENAMES.items():
        result = result.replace(f"../../{old}", f"../../{new}")
    result = result.replace('rule_payload_unity', 'rule_payload_hda')
    if node_name == "SELECT_ATTACHMENT_MODULES":
        marker = "// STREETBUILDING_V9_SELECT_ATTACHMENT_MODULES\n"
        if marker not in result:
            raise RuntimeError("SELECT_ATTACHMENT_MODULES marker is missing")
        result = result.replace(marker, marker +
            'string sbv12_attachment_tokens[]=array("awning","sign","fire_escape","wall_ac","roof_props");\n', 1)
        result = result.replace(
            'chf(sprintf("../../attachment_%d_density",kind))',
            'chf(sprintf("../../%s_density",sbv12_attachment_tokens[kind]))')
        result = result.replace(
            'chi(sprintf("../../attachment_%d_max",kind))',
            'chi(sprintf("../../%s_max_count",sbv12_attachment_tokens[kind]))')
    return result


def _capture_values(asset: hou.Node) -> dict[str, object]:
    result: dict[str, object] = {}
    for old, new in VALUE_MAP.items():
        parm_tuple = asset.parmTuple(old)
        if parm_tuple is None:
            continue
        value = parm_tuple.eval()
        result[new] = value[0] if len(value) == 1 else tuple(value)
    return result


def _set_value(asset: hou.Node, name: str, value: object) -> None:
    parm_tuple = asset.parmTuple(name)
    if parm_tuple is None:
        raise RuntimeError(f"V12 parameter missing after rebuild: {name}")
    if isinstance(value, tuple):
        parm_tuple.set(value)
    else:
        parm_tuple.set((value,))


def _validate(asset: hou.Node, require_removed: bool = False) -> dict[str, object]:
    group = asset.parmTemplateGroup()
    required = (
        "building_width", "building_depth", "floor_count", "facade_layout_mode",
        "attachment_overrides", "variation_seed", "unity_style_catalog",
        "unity_bridge_end_marker",
    )
    missing = [name for name in required if group.find(name) is None]
    if missing:
        raise RuntimeError("V12 interface missing: " + ", ".join(missing))
    removed = ("unity_generation_rules", "internal_width", "detail_density", "seed")
    stale = [name for name in removed if group.find(name) is not None]
    if require_removed and stale:
        raise RuntimeError("V12 stale interface remains: " + ", ".join(stale))
    if (require_removed and
            (group.find("floor_count").maxValue() != 12 or
             not group.find("floor_count").maxIsStrict())):
        raise RuntimeError("V12 floor_count must be strictly limited to 12")

    asset.cook(force=True)
    errors = list(asset.errors())
    warnings = list(asset.warnings())
    if errors or warnings:
        raise RuntimeError(f"V12 cook diagnostics errors={errors} warnings={warnings}")
    core = asset.node(CORE_NAME)
    parsed = core.node("PARSE_GENERATION_RULES")
    parsed.cook(force=True)
    geometry = parsed.geometry()
    source = geometry.attribValue("rule_source")
    if source != "hda":
        raise RuntimeError(f"V12 internal default rule source must be hda, got {source!r}")
    return {
        "rule_source": source,
        "floor_count": int(geometry.attribValue("effective_floor_count")),
        "seed": int(geometry.attribValue("effective_seed")),
        "errors": errors,
        "warnings": warnings,
    }


def preview(asset: hou.Node) -> dict[str, object]:
    if asset is None or asset.type().name() != ASSET_TYPE:
        raise RuntimeError(f"Expected {ASSET_PATH} {ASSET_TYPE}")
    definition = asset.type().definition()
    if definition is None or PREVIOUS_MARKER not in (definition.comment() or ""):
        raise RuntimeError("V12 requires the exact V10 definition marker")
    if not asset.matchesCurrentDefinition():
        raise RuntimeError("V12 preview requires a clean locked definition instance")

    old_values = _capture_values(asset)
    asset.allowEditingOfContents()
    core = asset.node(CORE_NAME)
    changed_nodes: list[str] = []
    try:
        for node in [core] + list(core.allSubChildren()):
            snippet = node.parm("snippet")
            if snippet is None:
                continue
            source = snippet.rawValue()
            transformed = _transform_snippet(node.name(), source)
            if transformed != source:
                snippet.set(transformed)
                changed_nodes.append(node.name())
        asset.setParmTemplateGroup(_parameter_group(asset))
        for name, value in old_values.items():
            _set_value(asset, name, value)
        validation = _validate(asset)
        return {
            "status": "PREVIEW",
            "revision": MARKER,
            "changed_nodes": sorted(changed_nodes),
            "validation": validation,
        }
    except Exception:
        asset.matchCurrentDefinition()
        raise


def commit(asset: hou.Node) -> dict[str, object]:
    if asset.matchesCurrentDefinition():
        raise RuntimeError("V12 commit requires an active preview")
    validation = _validate(asset)
    definition = asset.type().definition()
    comment = definition.comment() or ""
    candidate_group = _parameter_group(asset)
    definition.updateFromNode(asset)
    definition.setParmTemplateGroup(candidate_group)
    definition.setComment(comment.replace(PREVIOUS_MARKER, MARKER))
    asset.matchCurrentDefinition()
    fresh = _validate(asset, require_removed=True)
    hou.hipFile.save()
    return {"status": "COMMITTED", "revision": MARKER,
            "validation": validation, "fresh_validation": fresh}


def rollback(asset: hou.Node) -> dict[str, str]:
    asset.matchCurrentDefinition()
    return {"status": "ROLLED_BACK", "revision": PREVIOUS_MARKER}


def repair_bridge(asset: hou.Node) -> dict[str, object]:
    definition = asset.type().definition()
    if definition is None or MARKER not in (definition.comment() or ""):
        raise RuntimeError("Bridge repair requires the committed V12 definition")
    definition.setParmTemplateGroup(_parameter_group(asset))
    asset.matchCurrentDefinition()
    validation = _validate(asset, require_removed=True)
    hou.hipFile.save()
    return {"status": "BRIDGE_EXPOSED", "revision": MARKER, "validation": validation}


def apply_loaded(asset: hou.Node, save: bool) -> dict[str, object]:
    """Regression-gate entry point; committed V12 definitions are idempotent."""
    definition = asset.type().definition()
    comment = definition.comment() if definition is not None else ""
    if MARKER in (comment or ""):
        validation = _validate(asset, require_removed=True)
        if save:
            hou.hipFile.save()
        return {"status": "UNCHANGED", "save": save, "revision": MARKER,
                "contract": "StreetBuilding.HdaPanelGeneration.12.0",
                "validation": validation}
    result = preview(asset)
    return commit(asset) if save else rollback(asset)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--project-root", required=True, type=Path)
    parser.add_argument("--save", choices=("true", "false"), default="false")
    parser.add_argument("--remote-action", choices=("preview", "commit", "rollback", "repair_bridge"))
    parser.add_argument("--port", type=int, default=18811)
    args = parser.parse_args()
    root = args.project_root.resolve()
    if args.remote_action:
        import hrpyc
        connection, _ = hrpyc.import_remote_module("127.0.0.1", args.port, "hou")
        script_path = str(Path(__file__).resolve()).replace("\\", "/")
        connection.execute(
            "import hou, importlib.util, json\n"
            f"_sbv12_spec=importlib.util.spec_from_file_location('sbv12_live', {script_path!r})\n"
            "_sbv12=importlib.util.module_from_spec(_sbv12_spec)\n"
            "_sbv12_spec.loader.exec_module(_sbv12)\n"
            f"_sbv12_result=_sbv12.{args.remote_action}(hou.node({ASSET_PATH!r}))\n"
            "_sbv12_json=json.dumps(_sbv12_result, ensure_ascii=False, indent=2)\n")
        print(connection.eval("_sbv12_json"))
        return
    hip = root / "HoudiniProject/PCG_Track_21.0.440/PCG_Bike_StreetBuilding.hip"
    hda = root / "Assets/PCG/HDA/City/StreetBuilding.hda"
    before_hip = hip.read_bytes()
    before_hda = hda.read_bytes()
    try:
        hou.hipFile.load(str(hip), suppress_save_prompt=True, ignore_load_warnings=False)
        hou.hda.installFile(str(hda), change_oplibraries_file=False, force_use_assets=True)
        asset = hou.node(ASSET_PATH)
        result = preview(asset)
        if args.save == "true":
            result = commit(asset)
        else:
            rollback(asset)
        print(json.dumps(result, ensure_ascii=False, indent=2))
    except Exception:
        if args.save == "true":
            hda.write_bytes(before_hda)
            hip.write_bytes(before_hip)
        raise


if __name__ == "__main__":
    main()
