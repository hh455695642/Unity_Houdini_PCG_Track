"""Incremental, idempotent CityRoad street-furniture patch.

The synchronized Live ``/obj/CityRoad_DEV`` is the only implementation source.
The patch defaults to ``save=False`` and never updates the HDA definition.  It
adds an isolated point-generation branch driven by the existing centerline
contract, plus a public authoring folder.  On failure all newly-created nodes
and the prior live parameter interface are restored.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os

import hou


ASSET_PATH = "/obj/CityRoad_DEV"
ASSET_TYPE = "pcgbike::CityRoad::1.0"
CORE_NAME = "CityRoadCore"
DEFINITION_SUFFIX = "Assets/PCG/HDA/City/CityRoad.hda"
HIP_SUFFIX = "HoudiniProject/PCG_Track_21.0.440/PCG_Bike_CityRoad.hip"
BASELINE_HDA_SHA256 = "f441eb573f33cd378eb32038db1109a21f031e004dc89c0859131d353ebbc052"
MARKER = "CITYROAD_STREET_FURNITURE_V1"

LAMP_NODE = "CITYROAD_STREET_BUILD_LAMPS_V1"
TREE_NODE = "CITYROAD_STREET_BUILD_TREES_V1"
PIT_NODE = "CITYROAD_STREET_BUILD_TREE_PITS_V1"
NOTE_NODE = "CITYROAD_STREET_FURNITURE_V1"
OUTPUTS = (
    ("OUT_STREET_LAMPS", LAMP_NODE, 7),
    ("OUT_STREET_TREES", TREE_NODE, 8),
    ("OUT_STREET_TREE_PITS", PIT_NODE, 9),
)

PLACEHOLDER_ROOT = "Assets/PCG/Art/StreetFurniture/Placeholders"
DEFAULT_LAMP = PLACEHOLDER_ROOT + "/PF_StreetLamp_Placeholder.prefab"
DEFAULT_TREES = (
    PLACEHOLDER_ROOT + "/PF_Tree_Round_Placeholder.prefab",
    PLACEHOLDER_ROOT + "/PF_Tree_Tall_Placeholder.prefab",
    PLACEHOLDER_ROOT + "/PF_Tree_Wide_Placeholder.prefab",
)
DEFAULT_PIT = PLACEHOLDER_ROOT + "/PF_TreePit_Placeholder.prefab"


COMMON_VEX = r'''
// CITYROAD_STREET_FURNITURE_V1
vector sample_polyline_distance_v1(int input_index; int primitive; float target;
    export vector position; export vector tangent)
{
    int points[] = primpoints(input_index, primitive);
    position = 0;
    tangent = set(0, 0, 1);
    if (len(points) < 2)
        return position;
    float accumulated = 0;
    for (int index = 0; index < len(points) - 1; ++index)
    {
        vector a = point(input_index, "P", points[index]);
        vector b = point(input_index, "P", points[index + 1]);
        float segment_length = distance(a, b);
        if (segment_length <= 1e-6)
            continue;
        if (target <= accumulated + segment_length || index == len(points) - 2)
        {
            float u = clamp((target - accumulated) / segment_length, 0.0, 1.0);
            position = lerp(a, b, u);
            tangent = normalize(b - a);
            tangent.y = 0;
            tangent = normalize(tangent);
            return position;
        }
        accumulated += segment_length;
    }
    return position;
}

float polyline_length_v1(int input_index; int primitive)
{
    int points[] = primpoints(input_index, primitive);
    float result = 0;
    for (int index = 0; index < len(points) - 1; ++index)
    {
        vector a = point(input_index, "P", points[index]);
        vector b = point(input_index, "P", points[index + 1]);
        result += distance(a, b);
    }
    return result;
}

int near_junction_v1(int input_index; vector position; float clearance)
{
    int junctions[] = expandpointgroup(input_index, "junction_points");
    foreach (int junction; junctions)
    {
        vector junction_position = point(input_index, "P", junction);
        if (distance(position, junction_position) < clearance)
            return 1;
    }
    return 0;
}

string group_key_v1(string kind; string prefab)
{
    string key = re_replace("[^A-Za-z0-9_]", "_", prefab);
    return sprintf("StreetFurniture/%s/%s", kind, key);
}

void add_contract_attributes_v1(int point_number; string kind; string prefab;
    int corridor_id; int side; int variant; int owner_id; vector tangent;
    float distance_along; float corridor_length)
{
    string key = group_key_v1(kind, prefab);
    setpointattrib(0, "unity_instance", point_number, prefab, "set");
    setpointattrib(0, "instance_prefix", point_number, key, "set");
    setpointattrib(0, "pcg_kind", point_number, kind, "set");
    setpointattrib(0, "pcg_group_key", point_number, key, "set");
    setpointattrib(0, "pcg_corridor_id", point_number, corridor_id, "set");
    setpointattrib(0, "pcg_side", point_number, side, "set");
    setpointattrib(0, "pcg_variant", point_number, variant, "set");
    setpointattrib(0, "pcg_owner_id", point_number, owner_id, "set");
    setpointattrib(0, "pcg_tangent", point_number, tangent, "set");
    setpointattrib(0, "pcg_distance", point_number, distance_along, "set");
    setpointattrib(0, "pcg_corridor_length", point_number, corridor_length, "set");
}
'''


LAMP_VEX = COMMON_VEX + r'''
// Detail wrangle, input 0: OUT_ROAD_CENTERLINE_GRAPH contract.
addpointattrib(0, "unity_instance", "");
addpointattrib(0, "instance_prefix", "");
addpointattrib(0, "pcg_kind", "");
addpointattrib(0, "pcg_group_key", "");
addpointattrib(0, "pcg_corridor_id", -1);
addpointattrib(0, "pcg_side", 0);
addpointattrib(0, "pcg_variant", 0);
addpointattrib(0, "pcg_owner_id", -1);
addpointattrib(0, "pcg_tangent", set(0, 0, 1));
addpointattrib(0, "pcg_distance", 0.0);
addpointattrib(0, "pcg_corridor_length", 0.0);
setdetailattrib(0, "unity_split_attr", "pcg_group_key", "set");

int original_count = npoints(0);
int original_primitive_count = nprimitives(0);
int generated = 0;
string prefab = chs("../../lamp_prefab");
int enabled = chi("../../enable_street_lamps") && chi("../../enable_sidewalk") &&
    chf("../../sidewalk_width") >= chf("../../minimum_sidewalk_width") && len(prefab) > 0;
float spacing = max(chf("../../lamp_spacing"), 0.1);
float clearance = max(chf("../../junction_endpoint_clearance"), 0.0);
float sidewalk_width = max(chf("../../sidewalk_width"), 0.0);
float inset = clamp(chf("../../facility_edge_inset"), 0.0, sidewalk_width);
float y_offset = max(chf("../../sidewalk_height"), 0.0);
float yaw_offset = radians(chf("../../lamp_yaw_offset"));

if (enabled)
for (int primitive = 0; primitive < nprimitives(0); ++primitive)
{
    if (inprimgroup(0, "invalid_roads", primitive))
        continue;
    float length = polyline_length_v1(0, primitive);
    float usable = length - 2.0 * clearance;
    int pair_count = int(floor(usable / spacing));
    if (pair_count < 1)
        continue;
    float first = clearance + 0.5 * spacing + 0.5 * (usable - pair_count * spacing);
    float road_width = max(prim(0, "road_width", primitive), 0.1);
    int corridor_id = prim(0, "road_id", primitive);
    int segment_id = prim(0, "segment_id", primitive);
    for (int pair_index = 0; pair_index < pair_count; ++pair_index)
    {
        vector center, tangent;
        float distance_along = first + pair_index * spacing;
        sample_polyline_distance_v1(0, primitive, distance_along, center, tangent);
        if (near_junction_v1(0, center, clearance))
            continue;
        vector lateral = normalize(cross(set(0, 1, 0), tangent));
        float offset = 0.5 * road_width + sidewalk_width - inset;
        for (int side_index = 0; side_index < 2; ++side_index)
        {
            int side = side_index == 0 ? -1 : 1;
            vector position = center + lateral * float(side) * offset;
            position.y += y_offset;
            vector toward_road = normalize(center - position);
            toward_road.y = 0;
            toward_road = normalize(toward_road);
            vector4 base_orient = dihedral(set(0, 0, 1), toward_road);
            vector4 yaw = quaternion(yaw_offset, set(0, 1, 0));
            int point_number = addpoint(0, position);
            setpointattrib(0, "orient", point_number,
                qmultiply(base_orient, yaw), "set");
            setpointattrib(0, "pscale", point_number, 1.0, "set");
            add_contract_attributes_v1(point_number, "Lamps", prefab,
                corridor_id, side, 0, segment_id * 100000 + pair_index,
                tangent, distance_along, length);
            ++generated;
        }
    }
}

for (int primitive = original_primitive_count - 1; primitive >= 0; --primitive)
    removeprim(0, primitive, 0);
for (int point_number = original_count - 1; point_number >= 0; --point_number)
    removepoint(0, point_number);
setdetailattrib(0, "street_lamp_instance_count", generated, "set");
setdetailattrib(0, "street_furniture_contract", "V1", "set");
'''


TREE_VEX = COMMON_VEX + r'''
// Detail wrangle, input 0: centerline contract, input 1: generated lamps.
addpointattrib(0, "unity_instance", "");
addpointattrib(0, "instance_prefix", "");
addpointattrib(0, "pcg_kind", "");
addpointattrib(0, "pcg_group_key", "");
addpointattrib(0, "pcg_corridor_id", -1);
addpointattrib(0, "pcg_side", 0);
addpointattrib(0, "pcg_variant", 0);
addpointattrib(0, "pcg_owner_id", -1);
addpointattrib(0, "pcg_tangent", set(0, 0, 1));
addpointattrib(0, "pcg_distance", 0.0);
addpointattrib(0, "pcg_corridor_length", 0.0);
setdetailattrib(0, "unity_split_attr", "pcg_group_key", "set");

int variant_count = chi("../../tree_variants");
string prefabs[];
float weights[];
float total_weight = 0;
for (int variant = 1; variant <= variant_count; ++variant)
{
    string prefab = chs(sprintf("../../tree_prefab%d", variant));
    float weight = max(chf(sprintf("../../tree_weight%d", variant)), 0.0);
    if (len(prefab) > 0 && weight > 0)
    {
        int existing = find(prefabs, prefab);
        if (existing >= 0)
            weights[existing] += weight;
        else
        {
            append(prefabs, prefab);
            append(weights, weight);
        }
        total_weight += weight;
    }
}

int original_count = npoints(0);
int original_primitive_count = nprimitives(0);
int generated = 0;
int skipped_lamp = 0;
int skipped_junction = 0;
int enabled = chi("../../enable_street_trees") && chi("../../enable_sidewalk") &&
    chf("../../sidewalk_width") >= chf("../../minimum_sidewalk_width") && total_weight > 0;
float minimum_spacing = max(chf("../../tree_spacing_min"), 0.1);
float maximum_spacing = max(chf("../../tree_spacing_max"), minimum_spacing);
float minimum_scale = max(chf("../../tree_scale_min"), 0.01);
float maximum_scale = max(chf("../../tree_scale_max"), minimum_scale);
float endpoint_clearance = max(chf("../../junction_endpoint_clearance"), 0.0);
float lamp_clearance = max(chf("../../lamp_tree_clearance"), 0.0);
float sidewalk_width = max(chf("../../sidewalk_width"), 0.0);
float inset = clamp(chf("../../facility_edge_inset"), 0.0, sidewalk_width);
float y_offset = max(chf("../../sidewalk_height"), 0.0);
int seed = chi("../../tree_seed");

if (enabled)
for (int primitive = 0; primitive < nprimitives(0); ++primitive)
{
    if (inprimgroup(0, "invalid_roads", primitive))
        continue;
    float length = polyline_length_v1(0, primitive);
    if (length <= 2.0 * endpoint_clearance + minimum_spacing)
        continue;
    float road_width = max(prim(0, "road_width", primitive), 0.1);
    int corridor_id = prim(0, "road_id", primitive);
    int segment_id = prim(0, "segment_id", primitive);
    for (int side_index = 0; side_index < 2; ++side_index)
    {
        int side = side_index == 0 ? -1 : 1;
        int candidate = 0;
        float distance_along = endpoint_clearance +
            fit01(rand(set(seed, corridor_id, side * 17)), minimum_spacing, maximum_spacing) * 0.5;
        while (distance_along <= length - endpoint_clearance && candidate < 100000)
        {
            vector center, tangent;
            sample_polyline_distance_v1(0, primitive, distance_along, center, tangent);
            vector lateral = normalize(cross(set(0, 1, 0), tangent));
            float offset = 0.5 * road_width + sidewalk_width - inset;
            vector position = center + lateral * float(side) * offset;
            position.y += y_offset;
            int blocked = near_junction_v1(0, center, endpoint_clearance);
            if (blocked)
                ++skipped_junction;
            if (!blocked && lamp_clearance > 0 && nearpoint(1, position, lamp_clearance) >= 0)
            {
                blocked = 1;
                ++skipped_lamp;
            }
            if (!blocked)
            {
                vector random_key = set(seed + candidate * 31,
                    corridor_id * 131 + side * 17, segment_id * 19);
                float pick = rand(random_key + set(3.1, 7.2, 11.3)) * total_weight;
                int chosen = 0;
                float cumulative = 0;
                for (int variant = 0; variant < len(prefabs); ++variant)
                {
                    cumulative += weights[variant];
                    if (pick <= cumulative)
                    {
                        chosen = variant;
                        break;
                    }
                }
                float yaw_angle = rand(random_key + set(13.7, 17.1, 19.9)) *
                    6.283185307179586;
                float scale = fit01(rand(random_key + set(23.3, 29.1, 31.7)),
                    minimum_scale, maximum_scale);
                int point_number = addpoint(0, position);
                setpointattrib(0, "orient", point_number,
                    quaternion(yaw_angle, set(0, 1, 0)), "set");
                setpointattrib(0, "pscale", point_number, scale, "set");
                add_contract_attributes_v1(point_number, "Trees", prefabs[chosen],
                    corridor_id, side, chosen,
                    segment_id * 100000 + side_index * 50000 + candidate,
                    tangent, distance_along, length);
                ++generated;
            }
            float step = fit01(rand(set(seed + candidate * 43 + 1,
                corridor_id * 197 + 3, side * 37 + 5)), minimum_spacing, maximum_spacing);
            distance_along += step;
            ++candidate;
        }
    }
}

for (int primitive = original_primitive_count - 1; primitive >= 0; --primitive)
    removeprim(0, primitive, 0);
for (int point_number = original_count - 1; point_number >= 0; --point_number)
    removepoint(0, point_number);
setdetailattrib(0, "street_tree_instance_count", generated, "set");
setdetailattrib(0, "street_tree_skipped_lamp_count", skipped_lamp, "set");
setdetailattrib(0, "street_tree_skipped_junction_count", skipped_junction, "set");
setdetailattrib(0, "street_tree_variant_count", len(prefabs), "set");
setdetailattrib(0, "street_furniture_contract", "V1", "set");
'''


PIT_VEX = r'''
// CITYROAD_STREET_FURNITURE_V1
// Detail wrangle, input 0: generated trees.  Tree pits deliberately keep
// scale=1 and align +Z to the road tangent instead of inheriting tree yaw.
string prefab = chs("../../tree_pit_prefab");
float probability = clamp(chf("../../tree_pit_probability"), 0.0, 1.0);
int seed = chi("../../tree_seed");
int original_count = npoints(0);
int original_primitive_count = nprimitives(0);
int generated = 0;
for (int source = 0; source < original_count; ++source)
{
    if (point(0, "pcg_kind", source) != "Trees")
        continue;
    int owner_id = point(0, "pcg_owner_id", source);
    int corridor_id = point(0, "pcg_corridor_id", source);
    int side = point(0, "pcg_side", source);
    if (len(prefab) == 0 || rand(set(seed + source * 59,
        corridor_id * 73, side * 97)) > probability)
        continue;
    vector tangent = normalize(point(0, "pcg_tangent", source));
    string key = re_replace("[^A-Za-z0-9_]", "_", prefab);
    key = "StreetFurniture/TreePits/" + key;
    vector source_position = point(0, "P", source);
    int point_number = addpoint(0, source_position);
    setpointattrib(0, "unity_instance", point_number, prefab, "set");
    setpointattrib(0, "instance_prefix", point_number, key, "set");
    setpointattrib(0, "pcg_kind", point_number, "TreePits", "set");
    setpointattrib(0, "pcg_group_key", point_number, key, "set");
    setpointattrib(0, "pcg_corridor_id", point_number, corridor_id, "set");
    setpointattrib(0, "pcg_side", point_number, side, "set");
    setpointattrib(0, "pcg_variant", point_number, 0, "set");
    setpointattrib(0, "pcg_owner_id", point_number, owner_id, "set");
    setpointattrib(0, "pcg_tangent", point_number, tangent, "set");
    float distance_along = point(0, "pcg_distance", source);
    float corridor_length = point(0, "pcg_corridor_length", source);
    setpointattrib(0, "pcg_distance", point_number, distance_along, "set");
    setpointattrib(0, "pcg_corridor_length", point_number, corridor_length, "set");
    vector4 pit_orient = dihedral(set(0, 0, 1), tangent);
    setpointattrib(0, "orient", point_number, pit_orient, "set");
    setpointattrib(0, "pscale", point_number, 1.0, "set");
    ++generated;
}
for (int primitive = original_primitive_count - 1; primitive >= 0; --primitive)
    removeprim(0, primitive, 0);
for (int point_number = original_count - 1; point_number >= 0; --point_number)
    removepoint(0, point_number);
setdetailattrib(0, "unity_split_attr", "pcg_group_key", "set");
setdetailattrib(0, "street_tree_pit_instance_count", generated, "set");
setdetailattrib(0, "street_furniture_contract", "V1", "set");
'''


def _sha256(path: str) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _normalized(path: str) -> str:
    return path.replace("\\", "/")


def _require_live() -> tuple[hou.Node, hou.Node, hou.HDADefinition]:
    asset = hou.node(ASSET_PATH)
    if asset is None:
        raise RuntimeError("Missing " + ASSET_PATH)
    if asset.type().name() != ASSET_TYPE:
        raise RuntimeError("Unexpected asset type: " + asset.type().name())
    definition = asset.type().definition()
    if definition is None or not _normalized(definition.libraryFilePath()).endswith(DEFINITION_SUFFIX):
        raise RuntimeError("Unexpected CityRoad definition library")
    if not _normalized(hou.hipFile.path()).endswith(HIP_SUFFIX):
        raise RuntimeError("Unexpected HIP: " + hou.hipFile.path())
    core = asset.node(CORE_NAME)
    if core is None:
        raise RuntimeError("Missing CityRoadCore")
    return asset, core, definition


def _templates() -> hou.FolderParmTemplate:
    trees = hou.FolderParmTemplate(
        "tree_variants", "Tree Variants / 树木预设",
        folder_type=hou.folderType.MultiparmBlock,
        parm_templates=(
            hou.StringParmTemplate(
                "tree_prefab#", "Tree Prefab # / 树木预设 #", 1,
                default_value=(DEFAULT_TREES[0],),
                string_type=hou.stringParmType.FileReference,
                file_type=hou.fileType.Any),
            hou.FloatParmTemplate(
                "tree_weight#", "Tree Weight # / 树木权重 #", 1,
                default_value=(1.0,), min=0.0, max=100.0,
                min_is_strict=True),
        ))
    trees.setDefaultValue(3)
    return hou.FolderParmTemplate(
        "street_furniture_folder", "Street Furniture / 街道设施",
        folder_type=hou.folderType.Simple,
        parm_templates=(
            hou.ToggleParmTemplate("enable_street_lamps", "Enable Street Lamps / 启用路灯", True),
            hou.StringParmTemplate("lamp_prefab", "Lamp Prefab / 路灯预设", 1,
                default_value=(DEFAULT_LAMP,), string_type=hou.stringParmType.FileReference,
                file_type=hou.fileType.Any),
            hou.FloatParmTemplate("lamp_spacing", "Lamp Spacing (m) / 路灯间距", 1,
                default_value=(25.0,), min=0.1, max=200.0, min_is_strict=True),
            hou.FloatParmTemplate("lamp_yaw_offset", "Lamp Yaw Offset / 路灯朝向修正", 1,
                default_value=(0.0,), min=-180.0, max=180.0),
            hou.ToggleParmTemplate("enable_street_trees", "Enable Street Trees / 启用行道树", True),
            trees,
            hou.FloatParmTemplate("tree_spacing_min", "Tree Minimum Spacing (m) / 树最小间距", 1,
                default_value=(8.0,), min=0.1, max=100.0, min_is_strict=True),
            hou.FloatParmTemplate("tree_spacing_max", "Tree Maximum Spacing (m) / 树最大间距", 1,
                default_value=(14.0,), min=0.1, max=200.0, min_is_strict=True),
            hou.FloatParmTemplate("tree_scale_min", "Tree Minimum Scale / 树最小缩放", 1,
                default_value=(0.85,), min=0.01, max=10.0, min_is_strict=True),
            hou.FloatParmTemplate("tree_scale_max", "Tree Maximum Scale / 树最大缩放", 1,
                default_value=(1.25,), min=0.01, max=10.0, min_is_strict=True),
            hou.IntParmTemplate("tree_seed", "Tree Seed / 树随机种子", 1, default_value=(1729,)),
            hou.StringParmTemplate("tree_pit_prefab", "Tree Pit Prefab / 树池预设", 1,
                default_value=(DEFAULT_PIT,), string_type=hou.stringParmType.FileReference,
                file_type=hou.fileType.Any),
            hou.FloatParmTemplate("tree_pit_probability", "Tree Pit Probability / 树池概率", 1,
                default_value=(1.0,), min=0.0, max=1.0,
                min_is_strict=True, max_is_strict=True),
            hou.FloatParmTemplate("facility_edge_inset", "Facility Edge Inset (m) / 设施带内缩", 1,
                default_value=(0.5,), min=0.0, max=10.0, min_is_strict=True),
            hou.FloatParmTemplate("minimum_sidewalk_width", "Minimum Sidewalk Width (m) / 最小人行道宽度", 1,
                default_value=(1.0,), min=0.0, max=20.0, min_is_strict=True),
            hou.FloatParmTemplate("lamp_tree_clearance", "Lamp-Tree Clearance (m) / 灯树净距", 1,
                default_value=(3.0,), min=0.0, max=20.0, min_is_strict=True),
            hou.FloatParmTemplate("junction_endpoint_clearance", "Junction/Endpoint Clearance (m) / 路口端点净距", 1,
                default_value=(6.0,), min=0.0, max=50.0, min_is_strict=True),
        ))


def _ensure_wrangle(core: hou.Node, name: str, snippet: str, inputs: tuple[hou.Node, ...], created: list[hou.Node]) -> hou.Node:
    node = core.node(name)
    if node is None:
        node = core.createNode("attribwrangle", name)
        created.append(node)
    elif node.type().name() != "attribwrangle":
        raise RuntimeError(f"{node.path()} has unexpected type {node.type().name()}")
    node.parm("class").set(0)
    node.parm("snippet").set(snippet)
    for index, input_node in enumerate(inputs):
        node.setInput(index, input_node)
    node.setComment(MARKER + "\nIndependent point-instancer branch; no road topology mutation.")
    node.setGenericFlag(hou.nodeFlag.DisplayComment, True)
    return node


def _validate_structure(asset: hou.Node, core: hou.Node) -> dict[str, object]:
    lamp = core.node(LAMP_NODE)
    tree = core.node(TREE_NODE)
    pit = core.node(PIT_NODE)
    centerline = core.node("OUT_ROAD_CENTERLINE_GRAPH")
    if not all((lamp, tree, pit, centerline)):
        raise RuntimeError("Street-furniture branch is incomplete")
    expected = {
        LAMP_NODE: [centerline],
        TREE_NODE: [centerline, lamp],
        PIT_NODE: [tree],
    }
    for name, inputs in expected.items():
        node = core.node(name)
        for index, expected_input in enumerate(inputs):
            if node.input(index) != expected_input:
                raise RuntimeError(f"Unexpected input {name}[{index}]")
        if MARKER not in node.parm("snippet").eval():
            raise RuntimeError("Missing marker on " + name)
    for output_name, source_name, output_index in OUTPUTS:
        output = core.node(output_name)
        if output is None or output.type().name() != "output":
            raise RuntimeError("Missing output " + output_name)
        if output.input(0) != core.node(source_name) or output.evalParm("outputidx") != output_index:
            raise RuntimeError("Unexpected output contract " + output_name)
    required_parms = (
        "enable_street_lamps", "lamp_prefab", "lamp_spacing", "lamp_yaw_offset",
        "enable_street_trees", "tree_variants", "tree_spacing_min", "tree_spacing_max",
        "tree_scale_min", "tree_scale_max", "tree_seed", "tree_pit_prefab",
        "tree_pit_probability", "facility_edge_inset", "minimum_sidewalk_width",
        "lamp_tree_clearance", "junction_endpoint_clearance")
    missing = [name for name in required_parms if asset.parm(name) is None]
    if missing:
        raise RuntimeError("Missing street-furniture parameters: " + ", ".join(missing))
    return {"nodes": [name for name in (LAMP_NODE, TREE_NODE, PIT_NODE)],
            "outputs": [entry[0] for entry in OUTPUTS]}


def run(save: bool = False) -> dict[str, object]:
    asset, core, definition = _require_live()
    already_applied = core.node(LAMP_NODE) is not None
    if not already_applied and _sha256(definition.libraryFilePath()) != BASELINE_HDA_SHA256:
        raise RuntimeError("CityRoad HDA baseline hash does not match the synchronized Capture baseline")
    if already_applied:
        centerline = core.node("OUT_ROAD_CENTERLINE_GRAPH")
        lamp = _ensure_wrangle(core, LAMP_NODE, LAMP_VEX, (centerline,), [])
        tree = _ensure_wrangle(core, TREE_NODE, TREE_VEX, (centerline, lamp), [])
        pit = _ensure_wrangle(core, PIT_NODE, PIT_VEX, (tree,), [])
        for node in (lamp, tree, pit):
            node.cook(force=True)
            if node.errors():
                raise RuntimeError(node.path() + " cook errors: " + " | ".join(node.errors()))
        result = _validate_structure(asset, core)
        result.update({
            "status": "already_applied",
            "saved": False,
            "counts": {
                "lamps": lamp.geometry().intrinsicValue("pointcount"),
                "trees": tree.geometry().intrinsicValue("pointcount"),
                "tree_pits": pit.geometry().intrinsicValue("pointcount"),
            },
        })
        return result

    original_group = asset.parmTemplateGroup()
    was_locked = asset.isLockedHDA()
    created: list[hou.Node] = []
    try:
        if was_locked:
            asset.allowEditingOfContents()
        group = asset.parmTemplateGroup()
        if group.find("street_furniture_folder") is not None:
            raise RuntimeError("Unexpected pre-existing street_furniture_folder")
        group.append(_templates())
        asset.setParmTemplateGroup(group)
        # Multiparm defaults cannot express different prefab paths per row.
        # Initialize the three default rows deterministically after creation.
        asset.parm("tree_variants").set(3)
        for index, path in enumerate(DEFAULT_TREES, 1):
            asset.parm(f"tree_prefab{index}").set(path)
            asset.parm(f"tree_weight{index}").set(1.0)

        centerline = core.node("OUT_ROAD_CENTERLINE_GRAPH")
        if centerline is None:
            raise RuntimeError("Missing OUT_ROAD_CENTERLINE_GRAPH")
        lamp = _ensure_wrangle(core, LAMP_NODE, LAMP_VEX, (centerline,), created)
        tree = _ensure_wrangle(core, TREE_NODE, TREE_VEX, (centerline, lamp), created)
        pit = _ensure_wrangle(core, PIT_NODE, PIT_VEX, (tree,), created)
        note = core.createNode("null", NOTE_NODE)
        created.append(note)
        note.setInput(0, pit)
        note.setComment(MARKER + "\nExtension point: consume stable point metadata for future GPU instance baking.")
        note.setGenericFlag(hou.nodeFlag.DisplayComment, True)
        for output_name, source_name, output_index in OUTPUTS:
            output = core.createNode("output", output_name)
            created.append(output)
            output.setInput(0, core.node(source_name))
            output.parm("outputidx").set(output_index)
        for node, position in ((lamp, (38, -28)), (tree, (42, -28)), (pit, (46, -28)), (note, (50, -28))):
            node.setPosition(hou.Vector2(position))
        for offset, (output_name, _, _) in enumerate(OUTPUTS):
            core.node(output_name).setPosition(hou.Vector2((54, -26 - offset * 2)))

        for node in (lamp, tree, pit):
            try:
                node.cook(force=True)
            except hou.OperationFailed as exception:
                diagnostics = " | ".join(node.errors()) or str(exception)
                raise RuntimeError(node.path() + " cook errors: " + diagnostics) from exception
            if node.errors():
                raise RuntimeError(node.path() + " cook errors: " + " | ".join(node.errors()))
        result = _validate_structure(asset, core)
        result.update({
            "status": "applied_live",
            "saved": False,
            "counts": {
                "lamps": lamp.geometry().intrinsicValue("pointcount"),
                "trees": tree.geometry().intrinsicValue("pointcount"),
                "tree_pits": pit.geometry().intrinsicValue("pointcount"),
            },
        })
        if save:
            definition.updateFromNode(asset)
            hou.hipFile.save()
            asset.matchCurrentDefinition()
            hou.hipFile.save()
            result["saved"] = True
        return result
    except Exception:
        for node in reversed(created):
            if node is not None:
                node.destroy()
        try:
            asset.setParmTemplateGroup(original_group)
        finally:
            if was_locked:
                asset.matchCurrentDefinition()
        raise


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--save", action="store_true")
    parser.add_argument("--live", action="store_true",
        help="Execute this exact module inside the connected Houdini GUI session.")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=18811)
    args = parser.parse_args()
    if not args.live:
        print(json.dumps(run(save=args.save), ensure_ascii=False, indent=2))
        return

    import hrpyc
    connection, _remote_hou = hrpyc.import_remote_module(
        args.host, args.port, "hou")
    module_directory = _normalized(os.path.dirname(os.path.abspath(__file__)))
    try:
        connection.execute(
            "import importlib, json, sys\n"
            "_pcg_module_dir = {!r}\n"
            "if _pcg_module_dir not in sys.path: sys.path.insert(0, _pcg_module_dir)\n"
            "import patch_cityroad_street_furniture_20260812 as _pcg_street\n"
            "importlib.reload(_pcg_street)\n"
            "_pcg_street_result = json.dumps(_pcg_street.run(save={!r}), ensure_ascii=False)\n"
            .format(module_directory, args.save))
        print(json.dumps(
            json.loads(str(connection.eval("_pcg_street_result"))),
            ensure_ascii=False,
            indent=2))
    finally:
        connection.close()


if __name__ == "__main__":
    main()
