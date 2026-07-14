"""Incrementally patch the live pcgbike::Track::1.0 Road network.

This script is intentionally not a builder.  It preserves the current HDA,
public parameter interface and unrelated nodes, and only patches the curve
validation, road layout, UV and final topology modules.
"""

from __future__ import annotations

import json
import os
from datetime import datetime

import hou


PROJECT_ROOT = "E:/HoudiniProject/Unity_Houdini_PCG_Track"
TRACK_NODE_PATH = "/obj/Track1"
TRACK_TYPE_NAME = "pcgbike::Track::1.0"
TRACK_HDA_PATH = PROJECT_ROOT + "/Assets/PCG/HDA/Track.hda"
TRACK_BACKUP_DIR = PROJECT_ROOT + "/Assets/PCG/HDA/backup"
RECOVERY_DIR = PROJECT_ROOT + "/HoudiniProject/PCG_Track_21.0.440/recovery"


VALIDATE_VEX = r'''
function float safe_distance(vector a; vector b)
{
    return length(a - b);
}

int input_valid = npoints(0) >= 2 && nprimitives(0) == 1;
int input_closed = 0;
string road_source = "fallback_points";
string road_input_error = "missing_centerline_input";
float input_max_segment_length = 0.0;

// Valid Unity/HAPI curves pass through unchanged.  In particular, do not
// rebuild Bezier/NURBS input as a polygon before Resample evaluates it.
if (input_valid)
{
    int vertex_count = primvertexcount(0, 0);
    input_valid = vertex_count >= 2;
    if (input_valid)
    {
        input_closed = primintrinsic(0, "closed", 0);
        for (int vertex_index = 1; vertex_index < vertex_count; vertex_index++)
        {
            int previous_point = vertexpoint(0, primvertex(0, 0, vertex_index - 1));
            int current_point = vertexpoint(0, primvertex(0, 0, vertex_index));
            input_max_segment_length = max(
                input_max_segment_length,
                safe_distance(point(0, "P", previous_point), point(0, "P", current_point)));
        }
        if (input_closed)
        {
            int first_point = vertexpoint(0, primvertex(0, 0, 0));
            int last_point = vertexpoint(0, primvertex(0, 0, vertex_count - 1));
            input_max_segment_length = max(
                input_max_segment_length,
                safe_distance(point(0, "P", first_point), point(0, "P", last_point)));
        }
        road_source = "unity_input_curve";
        road_input_error = "";
    }
}
else if (npoints(0) > 0 || nprimitives(0) > 1)
{
    road_source = "invalid_input";
    road_input_error = "centerline_input_must_be_one_curve";
}

if (!input_valid)
{
    vector source_points[] = array(
        chv("../../curve_point_0"),
        chv("../../curve_point_1"),
        chv("../../curve_point_2"),
        chv("../../curve_point_3"),
        chv("../../curve_point_4"),
        chv("../../curve_point_5"));

    float spacing = max(ch("../../sample_spacing"), 0.25);
    int closed_loop_mode = clamp(chi("../../closed_loop_mode"), 0, 2);
    int closed_loop = closed_loop_mode == 2;
    if (closed_loop_mode == 0)
        closed_loop = safe_distance(source_points[0], source_points[len(source_points) - 1]) <= spacing * 1.25;
    if (len(source_points) > 2 && safe_distance(source_points[0], source_points[len(source_points) - 1]) <= 1e-4)
        resize(source_points, len(source_points) - 1);

    for (int prim_index = nprimitives(0) - 1; prim_index >= 0; prim_index--)
        removeprim(0, prim_index, 0);
    for (int point_index = npoints(0) - 1; point_index >= 0; point_index--)
        removepoint(0, point_index);

    int new_points[];
    foreach (vector position; source_points)
        append(new_points, addpoint(0, position));
    int primitive_id = closed_loop ? addprim(0, "poly") : addprim(0, "polyline");
    foreach (int point_id; new_points)
        addvertex(0, primitive_id, point_id);

    for (int index = 1; index < len(source_points); index++)
        input_max_segment_length = max(input_max_segment_length, safe_distance(source_points[index - 1], source_points[index]));
    if (closed_loop)
        input_max_segment_length = max(input_max_segment_length, safe_distance(source_points[len(source_points) - 1], source_points[0]));

    input_closed = closed_loop;
    road_source = "fallback_points";
}

// Explicit Closed Loop Mode remains authoritative without changing the source curve.
int closed_loop_mode = clamp(chi("../../closed_loop_mode"), 0, 2);
int road_closed_loop = closed_loop_mode == 1 ? 0 : (closed_loop_mode == 2 ? 1 : input_closed);
setdetailattrib(0, "road_source", road_source, "set");
setdetailattrib(0, "road_input_valid", input_valid, "set");
setdetailattrib(0, "road_input_error", road_input_error, "set");
setdetailattrib(0, "road_closed_loop", road_closed_loop, "set");
setdetailattrib(0, "road_raw_point_count", npoints(0), "set");
setdetailattrib(0, "road_input_max_segment_length", input_max_segment_length, "set");
'''


REPROJECT_VEX = r'''
int cross_section_count = max(int(detail(0, "road_cross_section_count")), 4);
int point_count = npoints(0);
int ring_count = point_count / cross_section_count;
if (ring_count <= 0)
    return;

int closed_loop = detail(0, "road_closed_loop", 0);
float road_width = max(detail(0, "road_width"), 0.1);
float shoulder_width = max(detail(0, "road_visible_shoulder_width"), 0.0);
float shoulder_drop = max(detail(0, "road_edge_drop"), 0.0);
float half_width = road_width * 0.5;
float total_half_width = max(half_width + shoulder_width, 0.05);
float offsets[] = array(-total_half_width, -half_width, half_width, total_half_width);
float drops[] = array(-shoulder_drop, 0.0, 0.0, -shoulder_drop);

vector centers[];
for (int ring = 0; ring < ring_count; ring++)
{
    vector lane_left = point(0, "P", ring * cross_section_count + 1);
    vector lane_right = point(0, "P", ring * cross_section_count + 2);
    append(centers, (lane_left + lane_right) * 0.5);
}

// Preserve the sampled centerline exactly.  The former width-dependent closed-loop
// smoothing silently changed the artist-authored path and invalidated its metadata.
float distance_along[];
for (int ring = 0; ring < ring_count; ring++)
{
    float distance = ring == 0 ? 0.0 : distance_along[ring - 1] + length(centers[ring] - centers[ring - 1]);
    append(distance_along, distance);
}
float road_length = max(distance_along[ring_count - 1], 1e-5);
if (closed_loop && ring_count > 1)
    road_length = max(road_length + length(centers[0] - centers[ring_count - 1]), 1e-5);

for (int ring = 0; ring < ring_count; ring++)
{
    vector left = point(0, "P", ring * cross_section_count);
    vector right = point(0, "P", ring * cross_section_count + cross_section_count - 1);
    vector lateral = set(right.x - left.x, 0.0, right.z - left.z);
    if (length(lateral) <= 1e-5)
        lateral = {1.0, 0.0, 0.0};
    lateral = normalize(lateral);

    float road_t = clamp(distance_along[ring] / road_length, 0.0, 1.0);
    for (int section = 0; section < cross_section_count; section++)
    {
        int point_id = ring * cross_section_count + section;
        vector position = centers[ring] + lateral * offsets[section];
        position.y = centers[ring].y + drops[section];
        setpointattrib(0, "P", point_id, position, "set");
        setpointattrib(0, "road_t", point_id, road_t, "set");
        setpointattrib(0, "road_distance", point_id, distance_along[ring], "set");
        setpointattrib(0, "road_lateral_offset_m", point_id, offsets[section], "set");
    }
}

// Per-column distance is the low-distortion longitudinal coordinate.  Inner and
// outer turn edges no longer share the centerline's physical distance.
float column_lengths[];
for (int section = 0; section < cross_section_count; section++)
{
    float column_distance = 0.0;
    for (int ring = 0; ring < ring_count; ring++)
    {
        int point_id = ring * cross_section_count + section;
        if (ring > 0)
        {
            int previous_id = (ring - 1) * cross_section_count + section;
            vector current_position = point(0, "P", point_id);
            vector previous_position = point(0, "P", previous_id);
            column_distance += length(current_position - previous_position);
        }
        setpointattrib(0, "road_surface_distance", point_id, column_distance, "set");
    }
    float column_length = column_distance;
    if (closed_loop && ring_count > 1)
    {
        vector first_position = point(0, "P", section);
        vector last_position = point(0, "P", (ring_count - 1) * cross_section_count + section);
        column_length += length(first_position - last_position);
    }
    append(column_lengths, column_length);
}
setdetailattrib(0, "road_surface_column_lengths", column_lengths, "set");

float max_turn_angle = 0.0;
float min_turn_radius = 1e18;
for (int ring = 0; ring < ring_count; ring++)
{
    int has_neighbours = closed_loop || (ring > 0 && ring < ring_count - 1);
    if (has_neighbours)
    {
        int previous_ring = (ring - 1 + ring_count) % ring_count;
        int next_ring = (ring + 1) % ring_count;
        vector previous = centers[previous_ring];
        vector current = centers[ring];
        vector next = centers[next_ring];
        vector incoming = current - previous;
        vector outgoing = next - current;
        float incoming_length = length(incoming);
        float outgoing_length = length(outgoing);
        if (incoming_length > 1e-5 && outgoing_length > 1e-5)
        {
            float cosine = clamp(dot(normalize(incoming), normalize(outgoing)), -1.0, 1.0);
            float turn_angle = degrees(acos(cosine));
            max_turn_angle = max(max_turn_angle, turn_angle);
            float chord_length = length(next - previous);
            float twice_area = length(cross(incoming, next - previous));
            if (twice_area > 1e-8)
            {
                float radius = incoming_length * outgoing_length * chord_length / (2.0 * twice_area);
                min_turn_radius = min(min_turn_radius, radius);
            }
        }
    }
}
if (min_turn_radius > 1e17)
    min_turn_radius = 0.0;
setdetailattrib(0, "road_max_ring_turn_angle_deg", max_turn_angle, "set");
setdetailattrib(0, "road_min_turn_radius", min_turn_radius, "set");

vector start_forward = ring_count > 1 ? centers[1] - centers[0] : {1.0, 0.0, 0.0};
if (length(start_forward) <= 1e-5)
    start_forward = {1.0, 0.0, 0.0};
setdetailattrib(0, "road_sample_count", ring_count, "set");
setdetailattrib(0, "road_length", road_length, "set");
setdetailattrib(0, "road_start_position", centers[0], "set");
setdetailattrib(0, "road_start_forward", normalize(start_forward), "set");
'''


UV_VEX = r'''
int point_id = vertexpoint(0, @vtxnum);
int primitive_id = vertexprim(0, @vtxnum);
int cross_section_count = max(int(detail(0, "road_cross_section_count")), 4);
int band_count = max(int(detail(0, "road_band_count")), 3);
int ring_count = max(int(detail(0, "road_sample_count")), 1);
int closed_loop = detail(0, "road_closed_loop", 0);
float uv_tile_length = max(detail(0, "road_uv_tile_length"), 1e-4);
int segment = primitive_id / band_count;
int ring = point_id / cross_section_count;
int section = point_id % cross_section_count;

float center_distance = point(0, "road_distance", point_id);
float surface_distance = point(0, "road_surface_distance", point_id);
if (closed_loop && segment == ring_count - 1 && ring == 0)
{
    center_distance = detail(0, "road_length");
    float column_lengths[] = detail(0, "road_surface_column_lengths");
    if (section < len(column_lengths))
        surface_distance = column_lengths[section];
}

float lateral_t = point(0, "road_lateral_t", point_id);
float lateral_offset_m = point(0, "road_lateral_offset_m", point_id);
v@uv = set(lateral_t, center_distance / uv_tile_length, 0.0);
v@uv3 = set(lateral_offset_m / uv_tile_length, surface_distance / uv_tile_length, 0.0);
'''


GROUP_VEX = r'''
int band = @primnum % 3;
setprimgroup(0, "shoulder_l", @primnum, band == 0, "set");
setprimgroup(0, "lane", @primnum, band == 1, "set");
setprimgroup(0, "shoulder_r", @primnum, band == 2, "set");
setprimgroup(0, "skirt_l", @primnum, 0, "set");
setprimgroup(0, "skirt_r", @primnum, 0, "set");
'''


TRIANGULATE_VEX = r'''
function float triangle_area(vector a; vector b; vector c)
{
    return 0.5 * length(cross(b - a, c - a));
}

function float triangle_uv_area(vector a; vector b; vector c)
{
    return 0.5 * abs((b.x - a.x) * (c.y - a.y) - (b.y - a.y) * (c.x - a.x));
}

function float split_ratio(
    vector p0; vector p1; vector p2;
    vector q0; vector q1; vector q2;
    vector uv0; vector uv1; vector uv2;
    vector uv3; vector uv4; vector uv5)
{
    float area_a = triangle_area(p0, p1, p2);
    float area_b = triangle_area(q0, q1, q2);
    float uv_area_a = triangle_uv_area(uv0, uv1, uv2);
    float uv_area_b = triangle_uv_area(uv3, uv4, uv5);
    if (area_a <= 1e-8 || area_b <= 1e-8 || uv_area_a <= 1e-10 || uv_area_b <= 1e-10)
        return 1e12;
    float density_a = area_a / uv_area_a;
    float density_b = area_b / uv_area_b;
    return max(density_a, density_b) / max(min(density_a, density_b), 1e-10);
}

function int add_triangle(
    int p0; int p1; int p2;
    vector uv0; vector uv1; vector uv2;
    vector surface_uv0; vector surface_uv1; vector surface_uv2)
{
    int primitive_id = addprim(0, "poly");
    addvertex(0, primitive_id, p0);
    addvertex(0, primitive_id, p1);
    addvertex(0, primitive_id, p2);
    // setvertexattrib addresses a vertex by primitive id + local vertex index.
    setvertexattrib(0, "uv", primitive_id, 0, uv0, "set");
    setvertexattrib(0, "uv", primitive_id, 1, uv1, "set");
    setvertexattrib(0, "uv", primitive_id, 2, uv2, "set");
    setvertexattrib(0, "uv3", primitive_id, 0, surface_uv0, "set");
    setvertexattrib(0, "uv3", primitive_id, 1, surface_uv1, "set");
    setvertexattrib(0, "uv3", primitive_id, 2, surface_uv2, "set");
    return primitive_id;
}

int original_primitive_count = nprimitives(0);
float maximum_ratio = 1.0;
for (int primitive_index = original_primitive_count - 1; primitive_index >= 0; primitive_index--)
{
    int vertices[] = primvertices(0, primitive_index);
    if (len(vertices) != 4)
        continue;
    int points[];
    vector positions[];
    vector directional_uvs[];
    vector surface_uvs[];
    foreach (int vertex_id; vertices)
    {
        int point_id = vertexpoint(0, vertex_id);
        vector point_position = point(0, "P", point_id);
        vector directional_uv = vertex(0, "uv", vertex_id);
        vector surface_uv = vertex(0, "uv3", vertex_id);
        append(points, point_id);
        append(positions, point_position);
        append(directional_uvs, directional_uv);
        append(surface_uvs, surface_uv);
    }

    float diagonal_02_ratio = split_ratio(
        positions[0], positions[1], positions[2], positions[0], positions[2], positions[3],
        surface_uvs[0], surface_uvs[1], surface_uvs[2], surface_uvs[0], surface_uvs[2], surface_uvs[3]);
    float diagonal_13_ratio = split_ratio(
        positions[0], positions[1], positions[3], positions[1], positions[2], positions[3],
        surface_uvs[0], surface_uvs[1], surface_uvs[3], surface_uvs[1], surface_uvs[2], surface_uvs[3]);
    int use_diagonal_13 = diagonal_13_ratio < diagonal_02_ratio;
    float selected_ratio = use_diagonal_13 ? diagonal_13_ratio : diagonal_02_ratio;
    maximum_ratio = max(maximum_ratio, selected_ratio);

    int in_lane = inprimgroup(0, "lane", primitive_index);
    int in_left_shoulder = inprimgroup(0, "shoulder_l", primitive_index);
    int in_right_shoulder = inprimgroup(0, "shoulder_r", primitive_index);
    int source_quad = primitive_index;
    removeprim(0, primitive_index, 0);

    int triangles[];
    if (use_diagonal_13)
    {
        append(triangles, add_triangle(points[0], points[1], points[3], directional_uvs[0], directional_uvs[1], directional_uvs[3], surface_uvs[0], surface_uvs[1], surface_uvs[3]));
        append(triangles, add_triangle(points[1], points[2], points[3], directional_uvs[1], directional_uvs[2], directional_uvs[3], surface_uvs[1], surface_uvs[2], surface_uvs[3]));
    }
    else
    {
        append(triangles, add_triangle(points[0], points[1], points[2], directional_uvs[0], directional_uvs[1], directional_uvs[2], surface_uvs[0], surface_uvs[1], surface_uvs[2]));
        append(triangles, add_triangle(points[0], points[2], points[3], directional_uvs[0], directional_uvs[2], directional_uvs[3], surface_uvs[0], surface_uvs[2], surface_uvs[3]));
    }
    foreach (int triangle; triangles)
    {
        setprimattrib(0, "road_source_quad", triangle, source_quad, "set");
        setprimgroup(0, "lane", triangle, in_lane, "set");
        setprimgroup(0, "shoulder_l", triangle, in_left_shoulder, "set");
        setprimgroup(0, "shoulder_r", triangle, in_right_shoulder, "set");
    }
}
setdetailattrib(0, "road_uv_stretch_max_ratio", maximum_ratio, "set");
'''


def _node_snapshot(node: hou.Node) -> dict:
    return {
        "path": node.path(),
        "type": node.type().name(),
        "inputs": [item.path() if item is not None else None for item in node.inputs()],
        "errors": list(node.errors()),
        "warnings": list(node.warnings()),
    }


def _write_recovery_snapshot(track: hou.Node) -> str:
    os.makedirs(RECOVERY_DIR, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    path = "%s/track_low_distortion_uv_prepatch_%s.json" % (RECOVERY_DIR, timestamp)
    road = track.node("Road")
    snippets = {}
    for name in (
        "CENTERLINE_validate_or_fallback",
        "SURFACE_reproject_layout",
        "UV_write_road_layout",
        "GROUP_road_bands",
        "ATTR_road_contract",
    ):
        node = road.node(name)
        snippets[name] = node.parm("snippet").eval() if node is not None and node.parm("snippet") is not None else None
    payload = {
        "hip": hou.hipFile.path(),
        "track": _node_snapshot(track),
        "definition": track.type().definition().libraryFilePath(),
        "parameters": {
            name: track.parm(name).eval() if track.parm(name) is not None else None
            for name in ("road_width", "sample_spacing", "closed_loop_mode", "uv_tile_length")
        },
        "road_nodes": [_node_snapshot(node) for node in road.children()],
        "snippets": snippets,
    }
    with open(path, "w", encoding="utf-8") as stream:
        json.dump(payload, stream, ensure_ascii=False, indent=2)
    return path


def _backup_hda() -> str:
    os.makedirs(TRACK_BACKUP_DIR, exist_ok=True)
    definitions = hou.hda.definitionsInFile(TRACK_HDA_PATH)
    source = next((item for item in definitions if item.nodeTypeName() == TRACK_TYPE_NAME), None)
    if source is None:
        raise RuntimeError("Missing %s definition in %s" % (TRACK_TYPE_NAME, TRACK_HDA_PATH))
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    path = "%s/Track_bak_uv_%s.hda" % (TRACK_BACKUP_DIR, timestamp)
    source.copyToHDAFile(path)
    return path


def apply_patch() -> dict:
    track = hou.node(TRACK_NODE_PATH)
    if track is None or track.type().name() != TRACK_TYPE_NAME:
        raise RuntimeError("Expected %s at %s" % (TRACK_TYPE_NAME, TRACK_NODE_PATH))
    definition = track.type().definition()
    if definition is None:
        raise RuntimeError("Track has no HDA definition")
    if os.path.normcase(definition.libraryFilePath()) != os.path.normcase(TRACK_HDA_PATH):
        raise RuntimeError("Track definition path mismatch: %s" % definition.libraryFilePath())

    recovery_path = _write_recovery_snapshot(track)
    backup_path = _backup_hda()
    used_allow_editing = False
    if not track.isEditable():
        track.allowEditingOfContents()
        used_allow_editing = True

    road = track.node("Road")
    required = {
        name: road.node(name)
        for name in (
            "CENTERLINE_validate_or_fallback",
            "CENTERLINE_resample",
            "SURFACE_reproject_layout",
            "TOPO_rebuild_road_quads",
            "NORMAL_generate_surface",
            "UV_write_road_layout",
            "GROUP_road_bands",
            "MASK_material_segments",
            "ATTR_road_contract",
            "OUT_ROAD_MESH",
        )
    }
    missing = [name for name, node in required.items() if node is None]
    if missing:
        raise RuntimeError("Missing Road nodes: %s" % ", ".join(missing))

    required["CENTERLINE_validate_or_fallback"].parm("snippet").set(VALIDATE_VEX)
    required["SURFACE_reproject_layout"].parm("snippet").set(REPROJECT_VEX)
    required["UV_write_road_layout"].parm("snippet").set(UV_VEX)
    required["GROUP_road_bands"].parm("snippet").set(GROUP_VEX)

    triangulate = road.node("TOPO_triangulate_for_unity")
    if triangulate is None:
        triangulate = road.createNode("attribwrangle", "TOPO_triangulate_for_unity")
    triangulate.parm("class").set(0)
    triangulate.parm("snippet").set(TRIANGULATE_VEX)
    triangulate.setComment(
        "Unity 输出确定性三角化：比较两条对角线的 UV3 纹理密度，保留较低畸变方案。"
    )
    triangulate.setGenericFlag(hou.nodeFlag.DisplayComment, True)
    triangulate.setColor(hou.Color((0.95, 0.55, 0.18)))

    # Quad topology -> both UV sets -> semantic groups -> deterministic triangles
    # -> triangle normals -> material masks/contract.
    required["UV_write_road_layout"].setInput(0, required["TOPO_rebuild_road_quads"])
    required["GROUP_road_bands"].setInput(0, required["UV_write_road_layout"])
    triangulate.setInput(0, required["GROUP_road_bands"])
    required["NORMAL_generate_surface"].setInput(0, triangulate)
    required["MASK_material_segments"].setInput(0, required["NORMAL_generate_surface"])
    required["ATTR_road_contract"].setInput(0, required["MASK_material_segments"])
    required["OUT_ROAD_MESH"].setInput(0, required["ATTR_road_contract"])

    group_position = required["GROUP_road_bands"].position()
    normal_position = required["NORMAL_generate_surface"].position()
    triangulate.setPosition((group_position + normal_position) * 0.5)

    contract = required["ATTR_road_contract"]
    contract_code = contract.parm("snippet").eval()
    old_line = 'setdetailattrib(0, "road_uv_stretch_warning_count", 0, "set");'
    new_lines = (
        'float uv_stretch_ratio = max(detail(0, "road_uv_stretch_max_ratio"), 1.0);\n'
        'setdetailattrib(0, "road_uv_stretch_warning_count", int(uv_stretch_ratio > 1.35), "set");'
    )
    if old_line in contract_code:
        contract_code = contract_code.replace(old_line, new_lines)
    elif "uv_stretch_ratio" not in contract_code:
        contract_code += "\n" + new_lines + "\n"
    contract.parm("snippet").set(contract_code)

    output = required["OUT_ROAD_MESH"]
    output.cook(force=True)
    if track.errors() or output.errors():
        raise RuntimeError("Cook failed: %r / %r" % (track.errors(), output.errors()))
    geometry = output.geometry()
    if geometry.findVertexAttrib("uv") is None or geometry.findVertexAttrib("uv3") is None:
        raise RuntimeError("Output is missing uv or uv3")
    if any(len(primitive.vertices()) != 3 for primitive in geometry.prims()):
        raise RuntimeError("Output contains non-triangle primitives")

    definition.save(TRACK_HDA_PATH, template_node=track, create_backup=True)
    hou.hda.installFile(TRACK_HDA_PATH)
    installed_definition = next(
        item for item in hou.hda.definitionsInFile(TRACK_HDA_PATH)
        if item.nodeTypeName() == TRACK_TYPE_NAME
    )
    installed_definition.setIsPreferred(True)
    track.matchCurrentDefinition()
    if os.path.normcase(track.type().definition().libraryFilePath()) != os.path.normcase(TRACK_HDA_PATH):
        raise RuntimeError("Track did not remain bound to the file-backed definition")

    hou.hipFile.save()
    output = track.node("Road/OUT_ROAD_MESH")
    output.cook(force=True)
    geometry = output.geometry()
    result = {
        "hip": hou.hipFile.path(),
        "hda": track.type().definition().libraryFilePath(),
        "backup": backup_path,
        "recovery": recovery_path,
        "used_allow_editing": used_allow_editing,
        "points": len(geometry.points()),
        "primitives": len(geometry.prims()),
        "road_sample_count": geometry.intAttribValue("road_sample_count"),
        "road_max_ring_turn_angle_deg": geometry.floatAttribValue("road_max_ring_turn_angle_deg"),
        "road_min_turn_radius": geometry.floatAttribValue("road_min_turn_radius"),
        "road_uv_stretch_max_ratio": geometry.floatAttribValue("road_uv_stretch_max_ratio"),
        "errors": list(output.errors()),
        "warnings": list(output.warnings()),
    }
    print("PATCH_RESULT=" + json.dumps(result, ensure_ascii=False))
    return result


PATCH_RESULT = apply_patch()
