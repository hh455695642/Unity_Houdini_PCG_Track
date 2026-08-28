"""REV4.1 patch: one entrance plus original MegaKit edge-column instances."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

import hou


REL_HDA = Path("Assets/PCG/HDA/City/StreetBuilding.hda")
REL_HIP = Path("HoudiniProject/PCG_Track_21.0.440/PCG_Bike_StreetBuilding.hip")
ASSET_PATH = "/obj/StreetBuilding_DEV"
PREVIOUS_REVISION = "STREETBUILDING_REV4_DIRECT_UNITY_INSTANCES"
REVISION = "STREETBUILDING_REV4_1_SINGLE_ENTRANCE_EDGE_COLUMNS"
CONTRACT_VERSION = "StreetBuilding.DirectInstances.4.1"
MARKER = "STREETBUILDING_REV4_1_SINGLE_ENTRANCE_EDGE_COLUMNS"


DIRECT_SNIPPET = r'''// STREETBUILDING_REV4_1_SINGLE_ENTRANCE_EDGE_COLUMNS
// UE-PCG-style authoring: emit only point transforms and original Unity asset paths.
// No FBX vertices, normals, UVs, materials or tangents pass through Houdini.

string sb_catalog_path(string catalog; string role; string variant; int part;
    export vector offset; export vector rotation)
{
    offset = 0;
    rotation = 0;
    string rows[] = split(catalog, "\n");
    foreach (string row; rows)
    {
        string fields[] = split(strip(row), "|");
        if (len(fields) != 10) continue;
        if (fields[0] != role || fields[1] != variant || atoi(fields[2]) != part) continue;
        offset = set(atof(fields[4]), atof(fields[5]), atof(fields[6]));
        rotation = set(atof(fields[7]), atof(fields[8]), atof(fields[9]));
        return fields[3];
    }
    return "";
}

int sb_add_instance(string catalog; string role; string variant; int part;
    float unity_x; float base_y; int floor_index; int cell_index;
    int building_entrance; int shop_entrance)
{
    vector part_offset, part_rotation;
    string asset_path = sb_catalog_path(catalog, role, variant, part,
        part_offset, part_rotation);
    if (len(asset_path) == 0)
        error("StreetBuilding direct catalog missing %s/%s part %d", role, variant, part);
    if (length2(part_rotation) > 1e-10)
        error("StreetBuilding REV4 currently accepts identity module rotations only");

    // HEU converts Houdini's right-handed X to Unity's left-handed X.
    vector unity_position = set(unity_x, base_y, 0) + part_offset;
    vector houdini_position = set(-unity_position.x, unity_position.y, unity_position.z);
    int point_number = addpoint(0, houdini_position);
    vector4 identity_orient = set(0.0, 0.0, 0.0, 1.0);
    setpointattrib(0, "orient", point_number, identity_orient, "set");
    setpointattrib(0, "unity_instance", point_number, asset_path, "set");
    string prefix = sprintf("SB_B0000_F%02d_C%02d_%s_%s_P%d",
        floor_index, cell_index, role, variant, part);
    setpointattrib(0, "instance_prefix", point_number, prefix, "set");
    setpointattrib(0, "name", point_number, prefix, "set");
    setpointattrib(0, "building_id", point_number, 0, "set");
    setpointattrib(0, "floor_index", point_number, floor_index, "set");
    setpointattrib(0, "cell_index", point_number, cell_index, "set");
    setpointattrib(0, "module_role", point_number, role, "set");
    setpointattrib(0, "module_variant", point_number, variant, "set");
    setpointattrib(0, "surface_role", point_number, "front", "set");
    setpointattrib(0, "facade_band", point_number,
        floor_index == 0 ? "ground" : "middle", "set");
    setpointattrib(0, "is_building_entrance", point_number, building_entrance, "set");
    setpointattrib(0, "is_shop_entrance", point_number, shop_entrance, "set");
    setpointattrib(0, "lod", point_number, 0, "set");
    setpointattrib(0, "chunk_id", point_number, 0, "set");
    setpointattrib(0, "pcg_kind", point_number, "streetbuilding_module_instance", "set");
    setpointattrib(0, "pcg_variant", point_number, variant, "set");
    return point_number;
}

string catalog = chs("../../unity_instance_catalog");
if (len(strip(catalog)) == 0)
    error("StreetBuilding Unity Asset Instances requires a compiled module catalog");

float width = ch("../../internal_width");
float bay_width = 2.0;
int cell_count = int(rint(width / bay_width));
if (cell_count < 2 || abs(width - cell_count * bay_width) > 0.01)
    error("StreetBuilding direct frontage %.3fm must be an exact multiple of 2m", width);
if (abs(ch("../../ground_floor_height") - 4.0) > 0.01 ||
    abs(ch("../../typical_floor_height") - 3.0) > 0.01)
    error("StreetBuilding direct MegaKit style requires 4m ground and 3m typical floors");
int floors = max(2, chi("../../floor_count"));

int entrance_cell = cell_count / 2;
for (int cell = 0; cell < cell_count; cell++)
{
    float unity_x = -width * 0.5 + (cell + 0.5) * bay_width;
    if (cell == entrance_cell)
    {
        sb_add_instance(catalog, "Entrance", "entrance_metal", 0,
            unity_x, 0, 0, cell, 1, 0);
        sb_add_instance(catalog, "Entrance", "entrance_metal", 1,
            unity_x, 0, 0, cell, 1, 0);
    }
    else
    {
        string shop_variant = cell % 2 == 0 ? "shop_trim" : "shop_metal";
        sb_add_instance(catalog, "GroundShop", shop_variant, 0,
            unity_x, 0, 0, cell, 0, 0);
    }

    sb_add_instance(catalog, "Cornice", "brick_center", 0,
        unity_x, 3.0, 0, cell, 0, 0);

    for (int floor = 1; floor < floors; floor++)
    {
        string window_variant = ((cell / 2) % 2 == 0) ? "trim" : "trim_single";
        float floor_y = 4.0 + (floor - 1) * 3.0;
        sb_add_instance(catalog, "MiddleWindow", window_variant, 0,
            unity_x, floor_y, floor, cell, 0, 0);
    }
}

// Narrow original columns sit on the facade boundaries. They do not consume a
// 2m cell and only mask the exposed end seams where a side facade can join later.
for (int edge = 0; edge < 2; edge++)
{
    float edge_x = edge == 0 ? -width * 0.5 : width * 0.5;
    int edge_cell = edge == 0 ? -1 : cell_count;
    sb_add_instance(catalog, "FacadeColumn", "trim_ground", 0,
        edge_x, 0, 0, edge_cell, 0, 0);
    for (int floor = 1; floor < floors; floor++)
    {
        float floor_y = 4.0 + (floor - 1) * 3.0;
        sb_add_instance(catalog, "FacadeColumn", "brick_upper", 0,
            edge_x, floor_y, floor, edge_cell, 0, 0);
    }
}

removeattrib(0, "point", "N");
setdetailattrib(0, "output_role", "building_lod0_instances", "set");
setdetailattrib(0, "streetbuilding_lod", 0, "set");
setdetailattrib(0, "streetbuilding_contract", "StreetBuilding.DirectInstances.4.1", "set");
setdetailattrib(0, "streetbuilding_revision", "STREETBUILDING_REV4_1_SINGLE_ENTRANCE_EDGE_COLUMNS", "set");
setdetailattrib(0, "streetbuilding_bottom_face_count", 0, "set");
setdetailattrib(0, "streetbuilding_front_only", 1, "set");
'''


TEST_CATALOG = "\n".join([
    "Entrance|entrance_metal|0|Assets/Test/DoorFrame_Metal_Single.fbx|0|0|0|0|0|0",
    "Entrance|entrance_metal|1|Assets/Test/Door_2.fbx|-0.5|0|0|0|0|0",
    "GroundShop|shop_metal|0|Assets/Test/Metal_FirstFloor_Window.fbx|0|0|0|0|0|0",
    "GroundShop|shop_trim|0|Assets/Test/Trim_FirstFloor_Window_001.fbx|0|0|0|0|0|0",
    "Cornice|brick_center|0|Assets/Test/Cornice_Brick_Center.fbx|0|0|0|0|0|0",
    "MiddleWindow|trim|0|Assets/Test/Brick_Window_Trim.fbx|0|0|0|0|0|0",
    "MiddleWindow|trim_single|0|Assets/Test/Brick_Window_Trim_Single.fbx|0|0|0|0|0|0",
    "FacadeColumn|trim_ground|0|Assets/Test/Trim_Column_Center.fbx|0|0|0|0|0|0",
    "FacadeColumn|brick_upper|0|Assets/Test/Brick_Column_Small.fbx|0|0|0|0|0|0",
])


def _update_interface_group(group: hou.ParmTemplateGroup) -> bool:
    current = group.find("module_source")
    if current is None or not isinstance(current, hou.IntParmTemplate):
        raise RuntimeError("module_source parameter template is missing")
    desired_items = ("internal_proxy", "unity_asset_instances")
    desired_labels = (
        "Internal Proxy / 内部代理",
        "Unity Asset Instances / Unity 原始资产实例",
    )
    changed = current.menuItems() != desired_items or current.menuLabels() != desired_labels
    if changed:
        replacement = current.clone()
        replacement.setMenuItems(desired_items)
        replacement.setMenuLabels(desired_labels)
        replacement.setLabel("Module Source / 模块来源")
        group.replace("module_source", replacement)

    catalog = group.find("unity_instance_catalog")
    if catalog is None:
        catalog = hou.StringParmTemplate(
            "unity_instance_catalog",
            "Unity Instance Catalog / Unity 实例目录",
            1,
            default_value=("",),
            string_type=hou.stringParmType.Regular,
        )
        group.append(catalog)
        changed = True
    elif not isinstance(catalog, hou.StringParmTemplate):
        raise RuntimeError("unity_instance_catalog exists with an unexpected contract")
    elif catalog.isHidden():
        replacement = catalog.clone()
        replacement.hide(False)
        replacement.setLabel("Unity Instance Catalog / Unity 实例目录")
        group.replace("unity_instance_catalog", replacement)
        changed = True
    return changed


def _set_module_source_template(asset: hou.Node) -> bool:
    group = asset.parmTemplateGroup()
    changed = _update_interface_group(group)
    if changed:
        asset.setParmTemplateGroup(group)
    return changed


def _ensure_node(core: hou.Node, node_type: str, name: str) -> tuple[hou.Node, bool]:
    node = core.node(name)
    if node is None:
        return core.createNode(node_type, name), True
    if node.type().name() != node_type:
        raise RuntimeError(f"{name} has unexpected type {node.type().name()}")
    return node, False


def _set_input(node: hou.Node, index: int, source: hou.Node | None) -> bool:
    if node.input(index) == source:
        return False
    node.setInput(index, source)
    return True


def _validate(asset: hou.Node) -> dict:
    core = asset.node("StreetBuildingCore")
    direct = core.node("DIRECT_UNITY_INSTANCE_FACADE")
    if direct is None:
        raise RuntimeError("DIRECT_UNITY_INSTANCE_FACADE is missing")
    saved = {
        name: asset.parm(name).eval()
        for name in (
            "module_source", "unity_instance_catalog", "internal_width",
            "ground_floor_height", "typical_floor_height", "floor_count",
        )
    }
    try:
        asset.parm("module_source").set(1)
        asset.parm("unity_instance_catalog").set(TEST_CATALOG)
        asset.parm("internal_width").set(12.0)
        asset.parm("ground_floor_height").set(4.0)
        asset.parm("typical_floor_height").set(3.0)
        asset.parm("floor_count").set(4)
        try:
            direct.cook(force=True)
        except hou.OperationFailed as error:
            raise RuntimeError(
                "REV4 direct VEX cook failed:\n" + "\n".join(direct.errors())
            ) from error
        geometry = direct.geometry()
        if geometry.intrinsicValue("primitivecount") != 0:
            raise RuntimeError("REV4 direct output contains primitives")
        if geometry.intrinsicValue("pointcount") != 39:
            raise RuntimeError(
                f"REV4.1 expected 39 points, got {geometry.intrinsicValue('pointcount')}")
        required = {
            "unity_instance", "orient", "instance_prefix", "building_id",
            "floor_index", "cell_index", "module_role", "module_variant",
        }
        actual = {attribute.name() for attribute in geometry.pointAttribs()}
        missing = sorted(required - actual)
        if missing:
            raise RuntimeError(f"REV4 missing point attributes: {missing}")
        if geometry.findPointAttrib("N") is not None:
            raise RuntimeError("REV4 direct output must not author N")
        paths = [point.stringAttribValue("unity_instance") for point in geometry.points()]
        if len(paths) != 39 or any(not path.startswith("Assets/Test/") for path in paths):
            raise RuntimeError("REV4 instance paths are missing or rewritten")
        roles = [point.stringAttribValue("module_role") for point in geometry.points()]
        if (roles.count("Entrance") != 2 or roles.count("GroundShopDoor") != 0
                or roles.count("GroundShop") != 5 or roles.count("FacadeColumn") != 8):
            raise RuntimeError("REV4.1 single-entrance/edge-column cardinality failed")
        for output_name in (
            "OUT_BUILDING_LOD1", "OUT_BUILDING_LOD2", "OUT_DETAIL_INSTANCES",
            "OUT_BUILDING_COLLISION", "OUT_BUILDING_METADATA",
        ):
            output = core.node(output_name)
            output.cook(force=True)
            if output.geometry().intrinsicValue("pointcount") != 0 or output.geometry().intrinsicValue("primitivecount") != 0:
                raise RuntimeError(f"{output_name} must be empty in REV4")
        return {"points": 39, "primitives": 0, "paths": len(set(paths))}
    finally:
        for name, value in saved.items():
            asset.parm(name).set(value)


def apply_loaded(asset: hou.Node, save: bool) -> dict:
    if asset is None or asset.type().name() != "pcgbike::StreetBuilding::1.0":
        raise RuntimeError("Expected StreetBuilding_DEV")
    definition = asset.type().definition()
    comment = definition.comment() or ""
    if PREVIOUS_REVISION not in comment and MARKER not in comment:
        raise RuntimeError("REV4.1 precondition marker mismatch")

    asset.allowEditingOfContents(propagate=True)
    core = asset.node("StreetBuildingCore")
    if core is None:
        raise RuntimeError("StreetBuildingCore is missing")
    changed: list[str] = []

    if _set_module_source_template(asset):
        changed.append("module_source/unity_instance_catalog")

    direct, created = _ensure_node(core, "attribwrangle", "DIRECT_UNITY_INSTANCE_FACADE")
    if created:
        changed.append(direct.name())
    if direct.parm("class").eval() != 0:
        direct.parm("class").set(0)
        changed.append(direct.name() + ":class")
    if direct.parm("snippet").eval() != DIRECT_SNIPPET:
        if MARKER in direct.parm("snippet").eval():
            raise RuntimeError("REV4 direct node marker exists with unexpected VEX")
        direct.parm("snippet").set(DIRECT_SNIPPET)
        changed.append(direct.name() + ":snippet")
    empty = core.node("EMPTY_GEOMETRY")
    normal0 = core.node("NORMAL_LOD0")
    if empty is None or normal0 is None:
        raise RuntimeError("REV4 source nodes are missing")
    if _set_input(direct, 0, empty):
        changed.append(direct.name() + ":input0")

    switch, created = _ensure_node(core, "switch", "LOD0_MODULE_SOURCE_SWITCH")
    if created:
        changed.append(switch.name())
    if _set_input(switch, 0, normal0):
        changed.append(switch.name() + ":input0")
    if _set_input(switch, 1, direct):
        changed.append(switch.name() + ":input1")
    switch_parm = switch.parm("input")
    desired_expression = 'ch("../../module_source")'
    try:
        current_expression = switch_parm.expression()
    except hou.OperationFailed:
        current_expression = None
    if current_expression != desired_expression:
        switch_parm.setExpression(desired_expression, language=hou.exprLanguage.Hscript)
        changed.append(switch.name() + ":input")

    output0 = core.node("OUT_BUILDING_LOD0")
    if _set_input(output0, 0, switch):
        changed.append(output0.name() + ":input0")
    for output_name in (
        "OUT_BUILDING_LOD1", "OUT_BUILDING_LOD2", "OUT_DETAIL_INSTANCES",
        "OUT_BUILDING_COLLISION", "OUT_BUILDING_METADATA",
    ):
        output = core.node(output_name)
        if output is None:
            raise RuntimeError(f"{output_name} is missing")
        if _set_input(output, 0, empty):
            changed.append(output.name() + ":input0")

    for lod in range(3):
        fix = core.node(f"FIX_EXTERNAL_NORMALS_LOD{lod}")
        if fix is not None:
            fix.destroy()
            changed.append(f"FIX_EXTERNAL_NORMALS_LOD{lod}:removed")

    direct.setPosition(normal0.position() + hou.Vector2((0.0, -2.0)))
    switch.setPosition((normal0.position() + output0.position()) * 0.5)
    direct.setComment(
        "REV4.1: one entrance plus original MegaKit edge-column instances.\n"
        "Only point transforms and unity_instance paths enter Houdini."
    )
    direct.setGenericFlag(hou.nodeFlag.DisplayComment, True)
    switch.setComment("Internal Proxy (0) / Unity Asset Instances (1)")
    switch.setGenericFlag(hou.nodeFlag.DisplayComment, True)
    validation = _validate(asset)

    if save and changed:
        definition.updateFromNode(asset)
        # updateFromNode persists the subnet contents but Houdini 21 does not
        # reliably copy spare interface edits from an unlocked instance. Persist
        # the REV4 menu/catalog templates explicitly on the definition.
        definition_group = definition.parmTemplateGroup()
        _update_interface_group(definition_group)
        definition.setParmTemplateGroup(definition_group)
        updated_comment = (definition.comment() or "").replace(PREVIOUS_REVISION, REVISION)
        if MARKER not in updated_comment:
            updated_comment = updated_comment.rstrip() + "\n" + MARKER
        definition.setComment(updated_comment)
        asset.matchCurrentDefinition()
        hou.hipFile.save()
    return {
        "status": "UPDATED" if changed else "UNCHANGED",
        "save": save,
        "revision": REVISION,
        "contract": CONTRACT_VERSION,
        "nodes": changed,
        "validation": validation,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--project-root", required=True, type=Path)
    parser.add_argument("--save", choices=("true", "false"), default="false")
    parser.add_argument("--update-existing", choices=("true", "false"), default="true")
    args = parser.parse_args()
    root = args.project_root.resolve()
    hda = (root / REL_HDA).resolve()
    hip = (root / REL_HIP).resolve()
    before = (
        hashlib.sha256(hda.read_bytes()).hexdigest(),
        hashlib.sha256(hip.read_bytes()).hexdigest(),
    )
    hou.hipFile.load(str(hip), suppress_save_prompt=True, ignore_load_warnings=False)
    hou.hda.installFile(str(hda), change_oplibraries_file=False, force_use_assets=True)
    result = apply_loaded(hou.node(ASSET_PATH), args.save == "true")
    if args.save == "true":
        hou.hipFile.save(str(hip))
    after = (
        hashlib.sha256(hda.read_bytes()).hexdigest(),
        hashlib.sha256(hip.read_bytes()).hexdigest(),
    )
    if args.save == "false" and before != after:
        raise RuntimeError("save=False changed production files")
    result["files"] = {"hda": after[0], "hip": after[1]}
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
