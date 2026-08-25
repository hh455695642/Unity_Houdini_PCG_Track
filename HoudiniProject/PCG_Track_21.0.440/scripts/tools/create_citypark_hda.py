"""Create the dedicated CityPark v1 HDA from the current live Houdini scene.

The generated asset owns only park range terrain and multi-curve running roads.
It intentionally contains no lake, vegetation, scatter, Unity instancing, or
runtime rendering logic.  ``--save false`` creates and validates an editable
live subnet; ``--save true`` persists the definition and current HIP.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

import hou


SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = SCRIPT_DIR.parents[3]
HDA_PATH = PROJECT_ROOT / "Assets/PCG/HDA/City/CityPark.hda"
HIP_PATH = PROJECT_ROOT / "HoudiniProject/PCG_Track_21.0.440/PCG_Bike_CityRoad.hip"
ASSET_TYPE = "pcgbike::CityPark::1.0"
ASSET_PATH = "/obj/CityPark_DEV"
MARKER = "CITYPARK_V1_RANGE_TERRAIN_MULTI_ROAD"


BOUNDARY_REBUILD_VEX = r'''// CITYPARK_V1_HAPI_CLOSED_BOUNDARY_REBUILD
// Unity SplineContainer can arrive as ordered points without a vertex table.
// A repeated first/end point is treated as one closed boundary.
int duplicate_endpoint = 0;
int loop_start = 0;
for (int point_index = 1; point_index < npoints(0); point_index++)
{
    vector first_position = point(0, "P", loop_start);
    vector current_position = point(0, "P", point_index);
    if (point_index - loop_start >= 3
        && distance(first_position, current_position) < 0.1)
    {
        duplicate_endpoint = 1;
        loop_start = point_index + 1;
    }
}
if (duplicate_endpoint)
{
    int input_primitive_count = nprimitives(0);
    int point_count = npoints(0);
    loop_start = 0;
    for (int point_index = 1; point_index < point_count; point_index++)
    {
        vector first_position = point(0, "P", loop_start);
        vector current_position = point(0, "P", point_index);
        if (point_index - loop_start >= 3
            && distance(first_position, current_position) < 0.1)
        {
            int primitive = addprim(0, "poly");
            for (int loop_point = loop_start; loop_point < point_index; loop_point++)
                addvertex(0, primitive, loop_point);
            loop_start = point_index + 1;
        }
    }
    for (int primitive = input_primitive_count - 1; primitive >= 0; primitive--)
        removeprim(0, primitive, 0);
}
'''


GROUND_DEFORM_VEX = r'''// CITYPARK_V1_LIGHT_TERRAIN_AND_ROAD_SINK
float amplitude = max(ch("../../terrain_height_amplitude"), 0.0);
float wavelength = max(ch("../../terrain_noise_wavelength"), 1.0);
float edge_fade = max(ch("../../terrain_edge_fade"), 0.001);
float boundary_distance = xyzdist(1, @P);
float boundary_mask = smooth(0.0, edge_fade, boundary_distance);
float seed = float(chi("../../terrain_seed"));
float noise_value = snoise(set(@P.x / wavelength, seed * 0.173, @P.z / wavelength));
@P.y += noise_value * amplitude * boundary_mask;

// Lower only the terrain below the authored road corridor.  The running-road
// mesh remains independent and therefore cannot be pierced by positive grass
// noise.  The transition band keeps the park surface smooth and editable.
if (chi("../../enable_road") && nprimitives(2) > 0 && nprimitives(3) > 0)
{
    int road_primitive = -1;
    vector road_uv = 0;
    vector projected = set(@P.x, 0.0, @P.z);
    float distance_to_road = xyzdist(2, projected, road_primitive, road_uv);
    if (road_primitive >= 0)
    {
        vector road_position = primuv(3, "P", road_primitive, road_uv);
        float shoulders = chi("../../enable_shoulders")
            ? max(ch("../../shoulder_width"), 0.0) : 0.0;
        float corridor = max(ch("../../road_width"), 0.1) * 0.5 + shoulders;
        float blend_width = max(ch("../../road_ground_blend"), 0.001);
        float mask = 1.0 - smooth(corridor, corridor + blend_width, distance_to_road);
        float target_y = road_position.y - max(ch("../../road_ground_sink"), 0.0);
        @P.y = lerp(@P.y, min(@P.y, target_y), mask);
    }
}
'''


GROUND_ORIENT_VEX = r'''// CITYPARK_V1_UNITY_UPWARD_WINDING
for (int primitive = 0; primitive < nprimitives(0); primitive++)
{
    vector normal = prim_normal(0, primitive, set(0.3333, 0.3333, 0.0));
    if (normal.y < 0.0)
    {
        int points[] = primpoints(0, primitive);
        int count = len(points);
        for (int index = 0; index < count; index++)
            setvertexpoint(0, primitive, index, points[count - 1 - index]);
    }
}
'''


GROUND_CONTRACT_VEX = r'''// CITYPARK_V1_GROUND_OUTPUT_CONTRACT
string material = chs("../../ground_unity_material");
for (int primitive = 0; primitive < nprimitives(0); primitive++)
{
    setprimattrib(0, "park_role", primitive, "ground", "set");
    setprimattrib(0, "name", primitive, "CityPark_Ground", "set");
    setprimattrib(0, "unity_material", primitive, material, "set");
}
setdetailattrib(0, "citypark_contract", "CITYPARK_V1_RANGE_TERRAIN_MULTI_ROAD", "set");
setdetailattrib(0, "citypark_has_water", 0, "set");
setdetailattrib(0, "citypark_has_vegetation", 0, "set");
setdetailattrib(0, "citypark_ground_sink", max(ch("../../road_ground_sink"), 0.0), "set");
'''


ROAD_BUILD_VEX = r'''// CITYPARK_V1_MULTI_CURVE_RUNNING_ROAD
// One detail pass builds a compact strip for every input primitive.  Central
// road and shoulders are tagged separately so Unity/Houdini can split outputs.
int source_primitive_count = nprimitives(0);
int source_point_count = npoints(0);
float road_width = max(ch("../../road_width"), 0.1);
int shoulders_enabled = chi("../../enable_shoulders");
float shoulder_width = shoulders_enabled ? max(ch("../../shoulder_width"), 0.0) : 0.0;
float shoulder_drop = shoulder_width > 1e-5 ? max(ch("../../shoulder_drop"), 0.0) : 0.0;
float surface_offset = ch("../../road_surface_offset");
float tile_length = max(ch("../../uv_tile_length"), 0.1);
string road_material = chs("../../road_unity_material");
string shoulder_material = chs("../../shoulder_unity_material");
addvertexattrib(0, "uv", set(0.0, 0.0, 0.0));

for (int source_primitive = 0; source_primitive < source_primitive_count; source_primitive++)
{
    int source_points[] = primpoints(0, source_primitive);
    int count = len(source_points);
    if (count < 2)
        continue;
    int closed = primintrinsic(0, "closed", source_primitive);
    vector first_position = point(0, "P", source_points[0]);
    vector last_position = point(0, "P", source_points[count - 1]);
    if (!closed && count >= 3
        && distance(first_position, last_position) < 0.1)
    {
        closed = 1;
        resize(source_points, count - 1);
        count--;
    }
    if (count < 2)
        continue;

    float distance_along[];
    resize(distance_along, count);
    distance_along[0] = 0.0;
    for (int index = 1; index < count; index++)
    {
        vector previous_position = point(0, "P", source_points[index - 1]);
        vector current_position = point(0, "P", source_points[index]);
        distance_along[index] = distance_along[index - 1]
            + distance(previous_position, current_position);
    }

    int outer_left[]; int inner_left[]; int inner_right[]; int outer_right[];
    resize(outer_left, count); resize(inner_left, count);
    resize(inner_right, count); resize(outer_right, count);
    for (int index = 0; index < count; index++)
    {
        int previous = index > 0 ? index - 1 : (closed ? count - 1 : 0);
        int next = index + 1 < count ? index + 1 : (closed ? 0 : count - 1);
        vector center = point(0, "P", source_points[index]);
        vector tangent = point(0, "P", source_points[next])
            - point(0, "P", source_points[previous]);
        tangent.y = 0.0;
        if (length2(tangent) < 1e-8)
            tangent = set(0.0, 0.0, 1.0);
        tangent = normalize(tangent);
        vector lateral = normalize(cross(set(0.0, 1.0, 0.0), tangent));
        float half_width = road_width * 0.5;
        vector road_center = center + set(0.0, surface_offset, 0.0);
        inner_left[index] = addpoint(0, road_center + lateral * half_width);
        inner_right[index] = addpoint(0, road_center - lateral * half_width);
        outer_left[index] = addpoint(0,
            road_center + lateral * (half_width + shoulder_width)
            - set(0.0, shoulder_drop, 0.0));
        outer_right[index] = addpoint(0,
            road_center - lateral * (half_width + shoulder_width)
            - set(0.0, shoulder_drop, 0.0));
        setpointattrib(0, "path_id", outer_left[index], source_primitive, "set");
        setpointattrib(0, "path_id", inner_left[index], source_primitive, "set");
        setpointattrib(0, "path_id", inner_right[index], source_primitive, "set");
        setpointattrib(0, "path_id", outer_right[index], source_primitive, "set");
        setpointattrib(0, "sample_index", outer_left[index], index, "set");
        setpointattrib(0, "sample_index", inner_left[index], index, "set");
        setpointattrib(0, "sample_index", inner_right[index], index, "set");
        setpointattrib(0, "sample_index", outer_right[index], index, "set");
    }

    int segment_count = closed ? count : count - 1;
    for (int segment = 0; segment < segment_count; segment++)
    {
        int next = (segment + 1) % count;
        float v0 = distance_along[segment] / tile_length;
        float next_distance = distance_along[next];
        if (next == 0)
        {
            vector closing_start = point(0, "P", source_points[count - 1]);
            vector closing_end = point(0, "P", source_points[0]);
            next_distance = distance_along[count - 1]
                + distance(closing_start, closing_end);
        }
        float v1 = next_distance / tile_length;

        int road = addprim(0, "poly", inner_left[segment], inner_left[next],
                           inner_right[next], inner_right[segment]);
        setvertexattrib(0, "uv", road, 0, set(0.0, v0, 0.0), "set");
        setvertexattrib(0, "uv", road, 1, set(0.0, v1, 0.0), "set");
        setvertexattrib(0, "uv", road, 2, set(1.0, v1, 0.0), "set");
        setvertexattrib(0, "uv", road, 3, set(1.0, v0, 0.0), "set");
        setprimattrib(0, "park_role", road, "road", "set");
        setprimattrib(0, "name", road, "CityPark_Road", "set");
        setprimattrib(0, "unity_material", road, road_material, "set");
        setprimattrib(0, "path_id", road, source_primitive, "set");
        setprimattrib(0, "segment_index", road, segment, "set");
        setprimgroup(0, "park_road", road, 1, "set");

        if (shoulder_width > 1e-5)
        {
            int left = addprim(0, "poly", outer_left[segment], outer_left[next],
                               inner_left[next], inner_left[segment]);
            int right = addprim(0, "poly", inner_right[segment], inner_right[next],
                                outer_right[next], outer_right[segment]);
            setprimattrib(0, "park_role", left, "shoulder", "set");
            setprimattrib(0, "name", left, "CityPark_Shoulders", "set");
            setprimattrib(0, "unity_material", left, shoulder_material, "set");
            setprimattrib(0, "path_id", left, source_primitive, "set");
            setprimattrib(0, "segment_index", left, segment, "set");
            setprimgroup(0, "park_shoulders", left, 1, "set");
            setprimattrib(0, "park_role", right, "shoulder", "set");
            setprimattrib(0, "name", right, "CityPark_Shoulders", "set");
            setprimattrib(0, "unity_material", right, shoulder_material, "set");
            setprimattrib(0, "path_id", right, source_primitive, "set");
            setprimattrib(0, "segment_index", right, segment, "set");
            setprimgroup(0, "park_shoulders", right, 1, "set");
            setvertexattrib(0, "uv", left, 0, set(0.0, v0, 0.0), "set");
            setvertexattrib(0, "uv", left, 1, set(0.0, v1, 0.0), "set");
            setvertexattrib(0, "uv", left, 2, set(1.0, v1, 0.0), "set");
            setvertexattrib(0, "uv", left, 3, set(1.0, v0, 0.0), "set");
            setvertexattrib(0, "uv", right, 0, set(0.0, v0, 0.0), "set");
            setvertexattrib(0, "uv", right, 1, set(0.0, v1, 0.0), "set");
            setvertexattrib(0, "uv", right, 2, set(1.0, v1, 0.0), "set");
            setvertexattrib(0, "uv", right, 3, set(1.0, v0, 0.0), "set");
        }
    }
}

for (int primitive = source_primitive_count - 1; primitive >= 0; primitive--)
    removeprim(0, primitive, 0);
for (int point_index = source_point_count - 1; point_index >= 0; point_index--)
    removepoint(0, point_index);
setdetailattrib(0, "citypark_contract", "CITYPARK_V1_RANGE_TERRAIN_MULTI_ROAD", "set");
setdetailattrib(0, "citypark_path_count", source_primitive_count, "set");
setdetailattrib(0, "citypark_has_markings", 0, "set");
setdetailattrib(0, "citypark_has_sidewalk", 0, "set");
'''


def _node_ref(name: str, label: str, help_text: str) -> hou.StringParmTemplate:
    template = hou.StringParmTemplate(
        name, label, 1, default_value=("",),
        string_type=hou.stringParmType.NodeReference)
    template.setTags({"oprelative": "."})
    template.setHelp(help_text)
    return template


def create_parameter_group() -> hou.ParmTemplateGroup:
    group = hou.ParmTemplateGroup()
    inputs = hou.FolderParmTemplate("citypark_inputs", "Inputs / 输入")
    inputs.addParmTemplate(hou.ToggleParmTemplate(
        "enable_ground", "Enable Ground / 生成公园地形", default_value=True))
    inputs.addParmTemplate(_node_ref(
        "unity_park_areas", "Park Areas / 公园范围曲线",
        "Unity 闭合 SplineContainer；一个容器可包含多个范围。"))
    inputs.addParmTemplate(_node_ref(
        "unity_park_roads", "Park Roads / 公园跑道曲线",
        "Unity SplineContainer；支持多条开放或闭合跑道曲线。"))
    group.append(inputs)

    terrain = hou.FolderParmTemplate("citypark_terrain", "Terrain / 地形")
    terrain.addParmTemplate(hou.FloatParmTemplate(
        "terrain_mesh_size", "Mesh Size (m) / 网格尺寸", 1,
        default_value=(5.0,), min=1.0, max=20.0))
    terrain.addParmTemplate(hou.FloatParmTemplate(
        "terrain_height_amplitude", "Height Amplitude (m) / 起伏高度", 1,
        default_value=(0.6,), min=0.0, max=3.0))
    terrain.addParmTemplate(hou.FloatParmTemplate(
        "terrain_noise_wavelength", "Noise Wavelength (m) / 起伏尺度", 1,
        default_value=(45.0,), min=5.0, max=200.0))
    terrain.addParmTemplate(hou.FloatParmTemplate(
        "terrain_edge_fade", "Boundary Fade (m) / 边界渐变", 1,
        default_value=(8.0,), min=0.1, max=50.0))
    terrain.addParmTemplate(hou.IntParmTemplate(
        "terrain_seed", "Terrain Seed / 地形种子", 1,
        default_value=(1,), min=0, max=999999))
    terrain.addParmTemplate(hou.FloatParmTemplate(
        "road_ground_sink", "Ground Sink Under Road (m) / 跑道下沉", 1,
        default_value=(0.25,), min=0.0, max=2.0))
    terrain.addParmTemplate(hou.FloatParmTemplate(
        "road_ground_blend", "Sink Blend Width (m) / 下沉过渡宽度", 1,
        default_value=(1.5,), min=0.1, max=10.0))
    group.append(terrain)

    road = hou.FolderParmTemplate("citypark_road", "Park Road / 公园跑道")
    road.addParmTemplate(hou.ToggleParmTemplate(
        "enable_road", "Enable Road / 生成跑道", default_value=True))
    road.addParmTemplate(hou.FloatParmTemplate(
        "road_width", "Road Width (m) / 主路宽度", 1,
        default_value=(4.0,), min=1.0, max=15.0))
    road.addParmTemplate(hou.FloatParmTemplate(
        "sample_spacing", "Sample Spacing (m) / 曲线采样间距", 1,
        default_value=(2.0,), min=0.25, max=10.0))
    road.addParmTemplate(hou.ToggleParmTemplate(
        "enable_shoulders", "Enable Shoulders / 生成路肩", default_value=True))
    road.addParmTemplate(hou.FloatParmTemplate(
        "shoulder_width", "Shoulder Width (m) / 路肩宽度", 1,
        default_value=(0.75,), min=0.0, max=5.0))
    road.addParmTemplate(hou.FloatParmTemplate(
        "shoulder_drop", "Shoulder Drop (m) / 路肩下沉", 1,
        default_value=(0.12,), min=0.0, max=1.0))
    road.addParmTemplate(hou.FloatParmTemplate(
        "road_surface_offset", "Surface Offset (m) / 路面抬升", 1,
        default_value=(0.05,), min=-0.5, max=1.0))
    road.addParmTemplate(hou.FloatParmTemplate(
        "uv_tile_length", "UV Tile Length (m) / UV 纵向长度", 1,
        default_value=(4.0,), min=0.1, max=50.0))
    group.append(road)

    materials = hou.FolderParmTemplate("citypark_materials", "Materials / 材质")
    for name, label, default in (
        ("ground_unity_material", "Ground Material / 草地材质",
         "Assets/PCG/Materials/CityPark/M_PCG_CityPark_Grass.mat"),
        ("road_unity_material", "Road Material / 跑道材质",
         "Assets/PCG/Materials/CityPark/M_PCG_CityPark_Path.mat"),
        ("shoulder_unity_material", "Shoulder Material / 路肩材质",
         "Assets/PCG/Materials/CityPark/M_PCG_CityPark_Path.mat"),
    ):
        materials.addParmTemplate(hou.StringParmTemplate(
            name, label, 1, default_value=(default,),
            string_type=hou.stringParmType.FileReference))
    group.append(materials)
    return group


def _set_expression(parm: hou.Parm, expression: str) -> None:
    parm.setExpression(expression, language=hou.exprLanguage.Hscript)


def _wrangle(parent: hou.Node, name: str, run_over: int, code: str) -> hou.Node:
    node = parent.createNode("attribwrangle", name)
    node.parm("class").set(run_over)
    node.parm("snippet").set(code)
    return node


def _tag(node: hou.Node, comment: str, color: tuple[float, float, float]) -> None:
    node.setComment(comment)
    node.setGenericFlag(hou.nodeFlag.DisplayComment, True)
    node.setColor(hou.Color(color))


def build_network(root: hou.Node) -> hou.Node:
    root.setParmTemplateGroup(create_parameter_group())
    root.setUserData("pcg_citypark_marker", MARKER)
    core = root.createNode("geo", "CityParkCore")
    for child in core.children():
        child.destroy()
    _tag(core, "独立公园生成：范围地形 + 多曲线跑道；无湖、树和实例化。", (0.18, 0.48, 0.25))

    empty_areas = core.createNode("null", "EMPTY_PARK_AREAS")
    area_input = core.createNode("object_merge", "IN_UNITY_PARK_AREAS")
    _set_expression(area_input.parm("objpath1"),
        'ifs(strlen(chs("../../unity_park_areas"))>0 && opexist(chsop("../../unity_park_areas")), chsop("../../unity_park_areas"), "../EMPTY_PARK_AREAS")')
    area_input.parm("xformtype").set(1)
    area_switch = core.createNode("switch", "SELECT_PARK_AREAS_INPUT")
    area_switch.setInput(0, empty_areas); area_switch.setInput(1, area_input)
    _set_expression(area_switch.parm("input"),
        'if(ch("../../enable_ground")!=0 && strlen(chs("../../unity_park_areas"))>0,1,0)')
    area_convert = core.createNode("convert", "CONVERT_PARK_AREAS")
    area_convert.setInput(0, area_switch)
    area_rebuild = _wrangle(core, "REBUILD_PARK_AREA_TOPOLOGY", 0, BOUNDARY_REBUILD_VEX)
    area_rebuild.setInput(0, area_convert)

    empty_roads = core.createNode("null", "EMPTY_PARK_ROADS")
    road_input = core.createNode("object_merge", "IN_UNITY_PARK_ROADS")
    _set_expression(road_input.parm("objpath1"),
        'ifs(strlen(chs("../../unity_park_roads"))>0 && opexist(chsop("../../unity_park_roads")), chsop("../../unity_park_roads"), "../EMPTY_PARK_ROADS")')
    road_input.parm("xformtype").set(1)
    road_switch = core.createNode("switch", "SELECT_PARK_ROADS_INPUT")
    road_switch.setInput(0, empty_roads); road_switch.setInput(1, road_input)
    _set_expression(road_switch.parm("input"),
        'if(ch("../../enable_road")!=0 && strlen(chs("../../unity_park_roads"))>0,1,0)')
    road_convert = core.createNode("convert", "CONVERT_PARK_ROADS")
    road_convert.setInput(0, road_switch)
    road_resample = core.createNode("resample", "RESAMPLE_PARK_ROADS")
    road_resample.setInput(0, road_convert)
    if road_resample.parm("length") is not None:
        _set_expression(road_resample.parm("length"), 'ch("../../sample_spacing")')
    if road_resample.parm("dolength") is not None:
        road_resample.parm("dolength").set(1)
    road_project = _wrangle(core, "PROJECT_ROADS_FOR_GROUND_SINK", 2,
        '@P.y = 0.0; // CITYPARK_V1_GROUND_SINK_DISTANCE_ONLY')
    road_project.setInput(0, road_resample)

    ground_fill = core.createNode("triangulate2d::3.0", "TRIANGULATE_PARK_RANGE")
    ground_fill.setInput(0, area_rebuild)
    ground_remesh = core.createNode("remesh::2.0", "REMESH_PARK_TERRAIN")
    ground_remesh.setInput(0, ground_fill)
    if ground_remesh.parm("targetsize") is not None:
        _set_expression(ground_remesh.parm("targetsize"), 'ch("../../terrain_mesh_size")')
    ground_deform = _wrangle(core, "DEFORM_TERRAIN_AND_SINK_ROAD", 2, GROUND_DEFORM_VEX)
    ground_deform.setInput(0, ground_remesh)
    ground_deform.setInput(1, area_rebuild)
    ground_deform.setInput(2, road_project)
    ground_deform.setInput(3, road_resample)
    ground_orient = _wrangle(core, "ORIENT_GROUND_FOR_UNITY", 0, GROUND_ORIENT_VEX)
    ground_orient.setInput(0, ground_deform)
    ground_normals = core.createNode("normal", "GROUND_NORMALS")
    ground_normals.setInput(0, ground_orient)
    ground_contract = _wrangle(core, "GROUND_OUTPUT_CONTRACT", 0, GROUND_CONTRACT_VEX)
    ground_contract.setInput(0, ground_normals)

    road_build = _wrangle(core, "BUILD_MULTI_CURVE_ROAD", 0, ROAD_BUILD_VEX)
    road_build.setInput(0, road_resample)
    road_keep = _wrangle(core, "KEEP_ROAD_SURFACE", 1,
        'if (s@park_role != "road") removeprim(0, @primnum, 1);')
    road_keep.setInput(0, road_build)
    road_normals = core.createNode("normal", "ROAD_NORMALS")
    road_normals.setInput(0, road_keep)
    shoulder_keep = _wrangle(core, "KEEP_ROAD_SHOULDERS", 1,
        'if (s@park_role != "shoulder") removeprim(0, @primnum, 1);')
    shoulder_keep.setInput(0, road_build)
    shoulder_normals = core.createNode("normal", "SHOULDER_NORMALS")
    shoulder_normals.setInput(0, shoulder_keep)

    outputs = []
    for index, (name, source) in enumerate((
        ("OUT_PARK_GROUND", ground_contract),
        ("OUT_PARK_ROAD", road_normals),
        ("OUT_PARK_SHOULDERS", shoulder_normals),
    )):
        output = core.createNode("output", name)
        output.parm("outputidx").set(index)
        output.setInput(0, source)
        outputs.append(output)
    outputs[0].setDisplayFlag(True)
    outputs[0].setRenderFlag(True)

    input_box = core.createNetworkBox("AREA_INPUTS")
    input_box.setComment("01 INPUTS / Unity 曲线输入")
    for node in (empty_areas, area_input, area_switch, area_convert, area_rebuild,
                 empty_roads, road_input, road_switch, road_convert, road_resample, road_project):
        input_box.addItem(node)
    terrain_box = core.createNetworkBox("AREA_TERRAIN")
    terrain_box.setComment("02 TERRAIN / 范围面片、低起伏、跑道下沉")
    for node in (ground_fill, ground_remesh, ground_deform, ground_orient,
                 ground_normals, ground_contract):
        terrain_box.addItem(node)
    road_box = core.createNetworkBox("AREA_ROAD")
    road_box.setComment("03 ROAD / 多曲线主路与 Track 式路肩")
    for node in (road_build, road_keep, road_normals, shoulder_keep, shoulder_normals):
        road_box.addItem(node)
    output_box = core.createNetworkBox("AREA_OUTPUTS")
    output_box.setComment("04 OUTPUTS / 可独立 Bake 的三类网格")
    for node in outputs: output_box.addItem(node)
    note = core.createStickyNote("NOTE_CITYPARK_V1")
    note.setText("CityPark v1｜范围曲线→低起伏地形；多条跑道曲线→主路+路肩。\n地形在跑道下方下沉；湖水、树、散布与实例化留到后续版本。")
    note.setTextSize(0.9)
    core.layoutChildren(items=core.children(), horizontal_spacing=2.0, vertical_spacing=1.5)
    core.setDisplayFlag(True)
    return core


def validate_live_network(root: hou.Node) -> dict[str, Any]:
    if root is None:
        raise RuntimeError("CityPark_DEV is missing")
    core = root.node("CityParkCore")
    if core is None:
        raise RuntimeError("CityParkCore is missing")
    expected = ("OUT_PARK_GROUND", "OUT_PARK_ROAD", "OUT_PARK_SHOULDERS")
    for name in expected:
        node = core.node(name)
        if node is None or node.type().name() != "output":
            raise RuntimeError(f"Missing CityPark output: {name}")
    forbidden = ("tree", "vegetation", "water", "lake", "instance")
    bad = [node.path() for node in root.allSubChildren()
           if any(token in node.name().lower() for token in forbidden)]
    if bad:
        raise RuntimeError(f"CityPark v1 contains deferred nodes: {bad}")
    return {"asset": root.path(), "outputs": list(expected), "forbidden_nodes": bad}


def build(save: bool = False) -> dict[str, Any]:
    obj = hou.node("/obj")
    existing = hou.node(ASSET_PATH)
    created = False
    if existing is not None:
        definition = existing.type().definition()
        existing_marker = existing.userData("pcg_citypark_marker")
        definition_path = (Path(definition.libraryFilePath()).resolve()
                           if definition is not None else None)
        if existing_marker != MARKER and not (
            definition is not None and existing.type().name() == "CityPark::1.0"
            and definition_path == HDA_PATH.resolve()
        ):
            raise RuntimeError("Refusing to replace non-generated /obj/CityPark_DEV")
        validate_live_network(existing)
        root = existing
    else:
        if save and HDA_PATH.is_file():
            hou.hda.installFile(str(HDA_PATH))
            root = obj.createNode(ASSET_TYPE, "CityPark_DEV")
            created = True
            validate_live_network(root)
        else:
            root = obj.createNode("subnet", "CityPark_DEV")
            created = True
            try:
                build_network(root)
                validate_live_network(root)
            except Exception:
                root.destroy()
                raise

    if save:
        HDA_PATH.parent.mkdir(parents=True, exist_ok=True)
        definition = root.type().definition()
        if definition is None:
            parameter_group = root.parmTemplateGroup()
            root = root.createDigitalAsset(
                name=ASSET_TYPE,
                hda_file_name=str(HDA_PATH),
                description="City Park / 城市公园",
                min_num_inputs=0,
                max_num_inputs=0)
            root.setName("CityPark_DEV", unique_name=False)
            definition = root.type().definition()
            definition.setParmTemplateGroup(parameter_group)
            root.setParmTemplateGroup(parameter_group)
            root.setUserData("pcg_citypark_marker", MARKER)
        definition.setComment(
            "CityPark v1: closed range curves generate a lightweight terrain; "
            "multiple road curves generate road and Track-style shoulders. "
            "No water, vegetation, scattering, or runtime instancing.")
        definition.updateFromNode(root)
        hou.hipFile.save(str(HIP_PATH))
    result = validate_live_network(root)
    result.update({
        "created": created,
        "saved": save,
        "hda": str(HDA_PATH),
        "hip": hou.hipFile.path(),
        "marker": MARKER,
    })
    return result


def run_remote(host: str, port: int, save: bool) -> dict[str, Any]:
    import hrpyc
    connection, _remote_hou = hrpyc.import_remote_module(host, port, "hou")
    try:
        path = str(SCRIPT_DIR).replace("\\", "/")
        connection.execute(
            "import sys, importlib, json; "
            f"sys.path.insert(0, {path!r}) if {path!r} not in sys.path else None; "
            "import create_citypark_hda as _citypark_builder; "
            "importlib.reload(_citypark_builder)")
        payload = connection.eval(
            f"json.dumps(_citypark_builder.build({save!r}), ensure_ascii=False)")
        return json.loads(str(payload))
    finally:
        connection.close()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=18811)
    parser.add_argument("--save", choices=("true", "false"), default="false")
    args = parser.parse_args()
    print(json.dumps(run_remote(args.host, args.port, args.save == "true"),
                     ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
