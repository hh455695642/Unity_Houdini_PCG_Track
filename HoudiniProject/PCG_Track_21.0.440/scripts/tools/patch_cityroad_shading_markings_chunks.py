"""
Incremental live-scene patch for CityRoad shading, static road markings and
mobile-friendly chunk outputs.

This script intentionally does not create a new HIP, rebuild CityRoad, delete
existing nodes, or touch Track.hda.  The current editable CityRoad HDA is the
source of truth.  Re-running the script updates only CITYROAD_* nodes created
by this patch.
"""

from __future__ import annotations

import json
import os
import textwrap

try:
    hou
except NameError:
    import hou


HDA_NODE_PATH = "/obj/CityRoad_DEV"
CORE_NODE_PATH = f"{HDA_NODE_PATH}/CityRoadCore"
EXPECTED_LIBRARY_SUFFIX = "Assets/PCG/HDA/City/CityRoad.hda"


ROAD_VERTEX_VEX = r"""
// CITYROAD_SHADING_CONTRACT
// uv  : road-aligned metres, preserved from the accepted V3 road.
// uv3 : city-local XZ metres, stable across road/junction direction changes.
// Cd.r: deterministic wear mask close to the final external road boundary.
v@uv3 = set(@P.x, @P.z, 0.0);

int boundary_prim = -1;
vector boundary_uvw = 0;
float boundary_distance = xyzdist(1, @P, boundary_prim, boundary_uvw);
float edge_mask = 1.0 - smooth(0.15, 1.0, boundary_distance);
if (string(prim(0, "city_part", @primnum)) != "road_surface")
    edge_mask = 0.0;
v@Cd = set(clamp(edge_mask, 0.0, 1.0), 0.0, 0.0);
"""


ROAD_MATERIAL_VEX = r"""
string material_path = chs("../../road_unity_material");
if (len(material_path) > 0)
    s@unity_material = material_path;
"""


SIDEWALK_MATERIAL_VEX = r"""
string material_path = "";
if (s@city_part == "curb")
    material_path = chs("../../curb_unity_material");
else if (s@city_part == "sidewalk")
    material_path = chs("../../sidewalk_unity_material");
if (len(material_path) > 0)
    s@unity_material = material_path;
"""


MARKING_BUILD_VEX = r"""
// CITYROAD_MARKING_MESH
// Input 0: sampled road centreline graph
// Input 1: accepted final road surface
// Input 2: junction patch boundary polygons
// Input 3: classified graph containing junction helper points
//
// All dashes, crosswalk stripes and stop lines are physical opaque geometry.

function float cross_xz(vector a; vector b)
{
    return a.x * b.z - a.z * b.x;
}

function vector project_to_road(vector query; float height_offset)
{
    int surface_prim = -1;
    vector surface_uvw = 0;
    xyzdist(1, query, surface_prim, surface_uvw);
    if (surface_prim < 0)
        return query + set(0, height_offset, 0);

    vector position = primuv(1, "P", surface_prim, surface_uvw);
    vector normal = primuv(1, "N", surface_prim, surface_uvw);
    if (length2(normal) < 1e-8)
        normal = set(0, 1, 0);
    normal = normalize(normal);
    if (dot(normal, set(0, 1, 0)) < 0)
        normal *= -1;
    return position + normal * height_offset;
}

function int close_to_junction(
    vector position;
    int road_level;
    float clearance;
    vector junction_positions[];
    int junction_levels[])
{
    vector flat_position = set(position.x, 0, position.z);
    for (int i = 0; i < len(junction_positions); ++i)
    {
        if (junction_levels[i] != road_level)
            continue;
        vector flat_junction = set(
            junction_positions[i].x, 0, junction_positions[i].z);
        if (distance(flat_position, flat_junction) < clearance)
            return 1;
    }
    return 0;
}

function float junction_boundary_distance(
    vector center;
    vector direction;
    int road_level;
    float fallback_distance)
{
    float best_distance = 1e18;
    vector ray = normalize(set(direction.x, 0, direction.z));
    for (int primitive = 0; primitive < nprimitives(2); ++primitive)
    {
        if (hasprimattrib(2, "road_level")
            && int(prim(2, "road_level", primitive)) != road_level)
            continue;

        int vertices[] = primvertices(2, primitive);
        int count = len(vertices);
        if (count < 2)
            continue;
        int closed = int(primintrinsic(2, "closed", primitive));
        int edge_count = closed ? count : count - 1;
        for (int edge = 0; edge < edge_count; ++edge)
        {
            vector a = point(
                2, "P", vertexpoint(2, vertices[edge]));
            vector b = point(
                2, "P", vertexpoint(2, vertices[(edge + 1) % count]));
            vector segment = set(b.x - a.x, 0, b.z - a.z);
            vector delta = set(a.x - center.x, 0, a.z - center.z);
            float denominator = cross_xz(ray, segment);
            if (abs(denominator) < 1e-6)
                continue;
            float ray_t = cross_xz(delta, segment) / denominator;
            float segment_t = cross_xz(delta, ray) / denominator;
            if (ray_t > 0.01 && segment_t >= -1e-4 && segment_t <= 1.0001)
                best_distance = min(best_distance, ray_t);
        }
    }
    return best_distance < 1e17 ? best_distance : fallback_distance;
}

function int emit_quad(
    vector a;
    vector b;
    vector c;
    vector d;
    int marking_type;
    int lane_index;
    int yellow;
    int road_id;
    int segment_id;
    float distance_along;
    string material_path;
    string group_name)
{
    int points[] = array(
        addpoint(0, a),
        addpoint(0, b),
        addpoint(0, c),
        addpoint(0, d));
    vector uvs[] = array(
        set(0, 0, 0), set(1, 0, 0), set(1, 1, 0), set(0, 1, 0));
    foreach (int index; int point_number; points)
    {
        setpointattrib(0, "N", point_number, set(0, 1, 0), "set");
        setpointattrib(
            0, "Cd", point_number, set(float(yellow), 0, 0), "set");
        setpointattrib(0, "uv", point_number, uvs[index], "set");
    }

    int primitive = addprim(
        0, "poly", points[0], points[1], points[2], points[3]);
    setprimattrib(0, "marking_type", primitive, marking_type, "set");
    setprimattrib(0, "lane_index", primitive, lane_index, "set");
    setprimattrib(0, "road_id", primitive, road_id, "set");
    setprimattrib(0, "segment_id", primitive, segment_id, "set");
    setprimattrib(
        0, "distance_along_road", primitive, distance_along, "set");
    setprimattrib(0, "city_part", primitive, "road_marking", "set");
    if (len(material_path) > 0)
        setprimattrib(
            0, "unity_material", primitive, material_path, "set");
    setprimgroup(0, "road_markings", primitive, 1, "set");
    setprimgroup(0, group_name, primitive, 1, "set");
    return primitive;
}

function int emit_ribbon(
    vector start;
    vector end;
    float width;
    float height_offset;
    int marking_type;
    int lane_index;
    int yellow;
    int road_id;
    int segment_id;
    float distance_along;
    string material_path;
    string group_name)
{
    vector tangent = normalize(set(end.x - start.x, 0, end.z - start.z));
    if (length2(tangent) < 1e-8)
        return -1;
    vector side = normalize(cross(set(0, 1, 0), tangent));
    float half_width = width * 0.5;
    vector a = project_to_road(start - side * half_width, height_offset);
    vector b = project_to_road(end - side * half_width, height_offset);
    vector c = project_to_road(end + side * half_width, height_offset);
    vector d = project_to_road(start + side * half_width, height_offset);
    return emit_quad(
        a, b, c, d, marking_type, lane_index, yellow,
        road_id, segment_id, distance_along, material_path, group_name);
}

int original_primitive_count = nprimitives(0);
int original_point_count = npoints(0);

addpointattrib(0, "N", set(0.0, 1.0, 0.0));
addpointattrib(0, "Cd", set(0.0, 0.0, 0.0));
addpointattrib(0, "uv", set(0.0, 0.0, 0.0));
addprimattrib(0, "marking_type", int(-1));
addprimattrib(0, "lane_index", int(-1));
addprimattrib(0, "road_id", int(-1));
addprimattrib(0, "segment_id", int(-1));
addprimattrib(0, "distance_along_road", 0.0);
addprimattrib(0, "city_part", "");

string marking_material = chs("../../marking_unity_material");
if (len(marking_material) > 0)
    addprimattrib(0, "unity_material", "");

vector junction_positions[];
int junction_levels[];
string junction_types[];
float snap_tolerance = max(ch("../../endpoint_snap_tolerance"), 0.001);
int junction_points[] = expandpointgroup(3, "junction_points");
foreach (int junction_point; junction_points)
{
    string junction_type = point(3, "junction_type", junction_point);
    if (junction_type != "t"
        && junction_type != "cross"
        && junction_type != "complex")
        continue;

    vector position = point(3, "P", junction_point);
    int road_level = int(point(3, "road_level", junction_point));
    int duplicate = 0;
    for (int index = 0; index < len(junction_positions); ++index)
    {
        if (junction_levels[index] == road_level
            && distance(
                set(position.x, 0, position.z),
                set(junction_positions[index].x, 0, junction_positions[index].z))
                <= snap_tolerance)
        {
            duplicate = 1;
            break;
        }
    }
    if (!duplicate)
    {
        append(junction_positions, position);
        append(junction_levels, road_level);
        append(junction_types, junction_type);
    }
}

int emitted_primitive_count = 0;
int crosswalk_approach_count = 0;
int unsupported_lane_direction_count = 0;
float height_offset = max(ch("../../marking_height_offset"), 0.001);

if (chi("../../enable_road_markings"))
{
    float center_width = max(ch("../../center_line_width"), 0.01);
    float lane_width_marking = max(ch("../../lane_line_width"), 0.01);
    float edge_width = max(ch("../../edge_line_width"), 0.01);
    float dash_length = max(ch("../../marking_dash_length"), 0.05);
    float dash_gap = max(ch("../../marking_dash_gap"), 0.0);
    float dash_period = max(dash_length + dash_gap, dash_length);
    float junction_clearance_extra =
        ch("../../junction_corner_radius")
        + ch("../../crosswalk_setback")
        + ch("../../crosswalk_depth")
        + ch("../../stop_line_gap")
        + ch("../../stop_line_width");

    // Base centre/lane/edge lines.
    for (int primitive = 0; primitive < original_primitive_count; ++primitive)
    {
        if (hasprimattrib(0, "city_valid")
            && !int(prim(0, "city_valid", primitive)))
            continue;
        int vertices[] = primvertices(0, primitive);
        int count = len(vertices);
        if (count < 2)
            continue;

        int road_id = hasprimattrib(0, "road_id")
            ? int(prim(0, "road_id", primitive)) : primitive;
        int segment_id = hasprimattrib(0, "segment_id")
            ? int(prim(0, "segment_id", primitive)) : road_id;
        int road_level = hasprimattrib(0, "road_level")
            ? int(prim(0, "road_level", primitive)) : 0;
        int lane_count = max(
            hasprimattrib(0, "lane_count")
                ? int(prim(0, "lane_count", primitive)) : 2,
            1);
        float road_width = max(
            hasprimattrib(0, "road_width")
                ? float(prim(0, "road_width", primitive)) : 7.0,
            0.5);
        float clearance =
            road_width * 0.5 + junction_clearance_extra;

        float accumulated_distance = 0.0;
        for (int segment = 0; segment < count - 1; ++segment)
        {
            vector a = point(
                0, "P", vertexpoint(0, vertices[segment]));
            vector b = point(
                0, "P", vertexpoint(0, vertices[segment + 1]));
            vector flat_delta = set(b.x - a.x, 0, b.z - a.z);
            float segment_length = length(flat_delta);
            if (segment_length < 1e-5)
                continue;
            vector tangent = flat_delta / segment_length;
            vector side = normalize(cross(set(0, 1, 0), tangent));

            int marking_count = lane_count + 2;
            for (int marking = 0; marking < marking_count; ++marking)
            {
                float lateral_offset = 0;
                float width = lane_width_marking;
                int marking_type = 1;
                int lane_index = marking;
                int yellow = 0;
                int dashed = 1;
                string group_name = "road_marking_lane";

                if (marking == 0 || marking == marking_count - 1)
                {
                    int side_sign = marking == 0 ? -1 : 1;
                    lateral_offset = road_width * 0.48 * side_sign;
                    width = edge_width;
                    marking_type = 2;
                    lane_index = side_sign;
                    dashed = 0;
                    group_name = "road_marking_edge";
                }
                else
                {
                    int divider = marking - 1;
                    lateral_offset =
                        -road_width * 0.5
                        + road_width * float(divider + 1) / float(lane_count);
                    int is_center = (divider + 1) * 2 == lane_count;
                    if (is_center && lane_count % 2 == 0)
                    {
                        width = center_width;
                        marking_type = 0;
                        yellow = 1;
                        group_name = "road_marking_center";
                    }
                    else if (lane_count % 2 != 0)
                    {
                        unsupported_lane_direction_count = 1;
                    }
                }

                vector offset_a = a + side * lateral_offset;
                vector offset_b = b + side * lateral_offset;
                if (!dashed)
                {
                    vector midpoint = (offset_a + offset_b) * 0.5;
                    if (!close_to_junction(
                        midpoint, road_level, clearance,
                        junction_positions, junction_levels))
                    {
                        if (emit_ribbon(
                            offset_a, offset_b, width, height_offset,
                            marking_type, lane_index, yellow, road_id,
                            segment_id, accumulated_distance,
                            marking_material, group_name) >= 0)
                            emitted_primitive_count++;
                    }
                    continue;
                }

                float local_distance = 0.0;
                while (local_distance < segment_length - 1e-5)
                {
                    float global_distance =
                        accumulated_distance + local_distance;
                    float phase = global_distance
                        - floor(global_distance / dash_period) * dash_period;
                    if (phase < dash_length)
                    {
                        float visible_length = min(
                            dash_length - phase,
                            segment_length - local_distance);
                        vector piece_start =
                            offset_a + tangent * local_distance;
                        vector piece_end =
                            piece_start + tangent * visible_length;
                        vector midpoint = (piece_start + piece_end) * 0.5;
                        if (!close_to_junction(
                            midpoint, road_level, clearance,
                            junction_positions, junction_levels))
                        {
                            if (emit_ribbon(
                                piece_start, piece_end, width, height_offset,
                                marking_type, lane_index, yellow, road_id,
                                segment_id, global_distance,
                                marking_material, group_name) >= 0)
                                emitted_primitive_count++;
                        }
                        local_distance += max(visible_length, 1e-4);
                    }
                    else
                    {
                        local_distance += max(
                            dash_period - phase, 1e-4);
                    }
                }
            }
            accumulated_distance += segment_length;
        }
    }

    // Crosswalks and stop lines: one set for every unique physical approach.
    if (chi("../../enable_crosswalks"))
    {
        float crosswalk_depth = max(ch("../../crosswalk_depth"), 0.5);
        float stripe_width = max(ch("../../crosswalk_stripe_width"), 0.05);
        float stripe_gap = max(ch("../../crosswalk_stripe_gap"), 0.0);
        float side_margin = max(ch("../../crosswalk_side_margin"), 0.0);
        float setback = max(ch("../../crosswalk_setback"), 0.0);
        float stop_width = max(ch("../../stop_line_width"), 0.05);
        float stop_gap = max(ch("../../stop_line_gap"), 0.0);
        float detect_radius = max(
            ch("../../intersection_detect_radius"),
            ch("../../junction_corner_radius") + 0.5);

        for (int junction_index = 0;
            junction_index < len(junction_positions);
            ++junction_index)
        {
            vector center = junction_positions[junction_index];
            int junction_level = junction_levels[junction_index];
            vector emitted_directions[];

            for (int primitive = 0;
                primitive < original_primitive_count;
                ++primitive)
            {
                if (hasprimattrib(0, "road_level")
                    && int(prim(0, "road_level", primitive)) != junction_level)
                    continue;
                if (hasprimattrib(0, "allow_junction")
                    && !int(prim(0, "allow_junction", primitive)))
                    continue;

                int vertices[] = primvertices(0, primitive);
                int count = len(vertices);
                if (count < 2)
                    continue;

                float best_distance = 1e18;
                int best_segment = -1;
                float best_t = 0;
                vector best_direction = 0;
                for (int segment = 0; segment < count - 1; ++segment)
                {
                    vector a = point(
                        0, "P", vertexpoint(0, vertices[segment]));
                    vector b = point(
                        0, "P", vertexpoint(0, vertices[segment + 1]));
                    vector delta = set(b.x - a.x, 0, b.z - a.z);
                    float length_squared = max(length2(delta), 1e-8);
                    vector center_delta =
                        set(center.x - a.x, 0, center.z - a.z);
                    float t = clamp(
                        dot(center_delta, delta) / length_squared, 0.0, 1.0);
                    vector closest =
                        set(a.x, 0, a.z) + delta * t;
                    float candidate_distance = distance(
                        closest, set(center.x, 0, center.z));
                    if (candidate_distance < best_distance)
                    {
                        best_distance = candidate_distance;
                        best_segment = segment;
                        best_t = t;
                        best_direction = normalize(delta);
                    }
                }

                float road_width = max(
                    hasprimattrib(0, "road_width")
                        ? float(prim(0, "road_width", primitive)) : 7.0,
                    0.5);
                if (best_segment < 0
                    || best_distance > max(detect_radius, road_width * 0.6))
                    continue;

                int road_id = hasprimattrib(0, "road_id")
                    ? int(prim(0, "road_id", primitive)) : primitive;
                int segment_id = hasprimattrib(0, "segment_id")
                    ? int(prim(0, "segment_id", primitive)) : road_id;
                vector candidate_directions[];
                if (best_segment == 0 && best_t < 0.05)
                {
                    append(candidate_directions, best_direction);
                }
                else if (best_segment == count - 2 && best_t > 0.95)
                {
                    append(candidate_directions, -best_direction);
                }
                else
                {
                    append(candidate_directions, best_direction);
                    append(candidate_directions, -best_direction);
                }

                foreach (vector outward_direction; candidate_directions)
                {
                    outward_direction = normalize(set(
                        outward_direction.x, 0, outward_direction.z));
                    int duplicate_direction = 0;
                    foreach (vector existing_direction; emitted_directions)
                    {
                        if (dot(outward_direction, existing_direction) > 0.985)
                        {
                            duplicate_direction = 1;
                            break;
                        }
                    }
                    if (duplicate_direction)
                        continue;
                    append(emitted_directions, outward_direction);

                    float patch_distance = junction_boundary_distance(
                        center, outward_direction, junction_level,
                        road_width * 0.5
                            + ch("../../junction_corner_radius"));
                    vector side = normalize(cross(
                        set(0, 1, 0), outward_direction));
                    float half_span = max(
                        road_width * 0.5 - side_margin, 0.25);

                    float stripe_start = 0.0;
                    while (stripe_start + stripe_width
                        <= crosswalk_depth + 1e-4)
                    {
                        float center_distance =
                            patch_distance + setback
                            + stripe_start + stripe_width * 0.5;
                        vector stripe_center =
                            center + outward_direction * center_distance;
                        vector along =
                            outward_direction * stripe_width * 0.5;
                        vector across = side * half_span;
                        vector a = project_to_road(
                            stripe_center - along - across, height_offset);
                        vector b = project_to_road(
                            stripe_center + along - across, height_offset);
                        vector c = project_to_road(
                            stripe_center + along + across, height_offset);
                        vector d = project_to_road(
                            stripe_center - along + across, height_offset);
                        emit_quad(
                            a, b, c, d, 3, -1, 0, road_id, segment_id,
                            center_distance, marking_material,
                            "road_marking_crosswalk");
                        emitted_primitive_count++;
                        stripe_start += stripe_width + stripe_gap;
                    }

                    float stop_center_distance =
                        patch_distance + setback + crosswalk_depth
                        + stop_gap + stop_width * 0.5;
                    vector stop_center =
                        center + outward_direction * stop_center_distance;
                    vector stop_along =
                        outward_direction * stop_width * 0.5;
                    vector stop_across = side * half_span;
                    vector sa = project_to_road(
                        stop_center - stop_along - stop_across, height_offset);
                    vector sb = project_to_road(
                        stop_center + stop_along - stop_across, height_offset);
                    vector sc = project_to_road(
                        stop_center + stop_along + stop_across, height_offset);
                    vector sd = project_to_road(
                        stop_center - stop_along + stop_across, height_offset);
                    emit_quad(
                        sa, sb, sc, sd, 4, -1, 0, road_id, segment_id,
                        stop_center_distance, marking_material,
                        "road_marking_stopline");
                    emitted_primitive_count++;
                    crosswalk_approach_count++;
                }
            }
        }
    }
}

for (int primitive = original_primitive_count - 1;
    primitive >= 0;
    --primitive)
    removeprim(0, primitive, 0);
for (int point_number = original_point_count - 1;
    point_number >= 0;
    --point_number)
    removepoint(0, point_number);

setdetailattrib(
    0, "marking_primitive_count", emitted_primitive_count, "set");
setdetailattrib(
    0, "crosswalk_approach_count", crosswalk_approach_count, "set");
setdetailattrib(0, "marking_junction_overlap_count", 0, "set");
setdetailattrib(
    0, "unsupported_lane_direction_count",
    unsupported_lane_direction_count, "set");
setdetailattrib(0, "city_road_contract_version", "1.1.0", "set");
setdetailattrib(0, "output_role", "OUT_ROAD_MARKINGS", "set");
"""


CHUNK_CLIP_VEX_TEMPLATE = r"""
// CITYROAD_CHUNK_OUTPUT
// Physically clips polygons against the XZ chunk grid, interpolating the
// attributes required by the CityRoad render contract.  Primitive groups and
// material assignments are preserved.  Packing happens in the following SOP.

function void clip_plane(
    vector input_p[];
    vector input_uv[];
    vector input_uv3[];
    vector input_n[];
    vector input_cd[];
    int axis;
    float boundary;
    int keep_greater;
    export vector output_p[];
    export vector output_uv[];
    export vector output_uv3[];
    export vector output_n[];
    export vector output_cd[])
{
    resize(output_p, 0);
    resize(output_uv, 0);
    resize(output_uv3, 0);
    resize(output_n, 0);
    resize(output_cd, 0);
    int count = len(input_p);
    if (count == 0)
        return;

    for (int current = 0; current < count; ++current)
    {
        int previous = (current + count - 1) % count;
        vector a = input_p[previous];
        vector b = input_p[current];
        float av = axis == 0 ? a.x : a.z;
        float bv = axis == 0 ? b.x : b.z;
        int a_inside = keep_greater
            ? av >= boundary - 1e-5 : av <= boundary + 1e-5;
        int b_inside = keep_greater
            ? bv >= boundary - 1e-5 : bv <= boundary + 1e-5;

        if (a_inside != b_inside)
        {
            float t = clamp(
                (boundary - av) / (bv - av + 1e-20), 0.0, 1.0);
            append(output_p, lerp(a, b, t));
            append(
                output_uv,
                lerp(input_uv[previous], input_uv[current], t));
            append(
                output_uv3,
                lerp(input_uv3[previous], input_uv3[current], t));
            append(
                output_n,
                normalize(lerp(input_n[previous], input_n[current], t)));
            append(
                output_cd,
                lerp(input_cd[previous], input_cd[current], t));
        }
        if (b_inside)
        {
            append(output_p, b);
            append(output_uv, input_uv[current]);
            append(output_uv3, input_uv3[current]);
            append(output_n, input_n[current]);
            append(output_cd, input_cd[current]);
        }
    }
}

int original_primitive_count = nprimitives(0);
int original_point_count = npoints(0);
int enable_chunking = chi("../../enable_chunking");
float chunk_size = max(ch("../../chunk_size"), 1.0);
vector chunk_origin = chv("../../chunk_origin");
string role = "__ROLE__";

addvertexattrib(0, "uv", set(0.0, 0.0, 0.0));
addvertexattrib(0, "uv3", set(0.0, 0.0, 0.0));
addvertexattrib(0, "N", set(0.0, 1.0, 0.0));
addvertexattrib(0, "Cd", set(0.0, 0.0, 0.0));
addprimattrib(0, "chunk_x", int(0));
addprimattrib(0, "chunk_z", int(0));
addprimattrib(0, "chunk_key", "");
addprimattrib(0, "chunk_id", int(0));
addprimattrib(0, "name", "");

string primitive_groups[] = detailintrinsic(0, "primitivegroups");
string chunk_keys[];
int chunk_vertex_counts[];

string integer_attributes[] = array(
    "road_id", "segment_id", "road_class", "lane_count", "road_level",
    "is_bridge", "is_race_route", "material_style", "allow_junction",
    "junction_id", "collision_class", "junction_membership_count",
    "process_order", "city_valid", "fuse_key", "trimmed_inside_count",
    "cutter_prim_count", "candidate_prim_count", "marking_type",
    "lane_index", "patch_piece_index");
string float_attributes[] = array(
    "road_width", "lane_width", "speed_limit", "distance_along_road");
string string_attributes[] = array(
    "road_name", "junction_type", "junction_ids_csv", "city_part",
    "unity_material");

for (int source_primitive = 0;
    source_primitive < original_primitive_count;
    ++source_primitive)
{
    int source_vertices[] = primvertices(0, source_primitive);
    int source_count = len(source_vertices);
    if (source_count < 3)
        continue;

    vector source_p[];
    vector source_uv[];
    vector source_uv3[];
    vector source_n[];
    vector source_cd[];
    vector min_position = set(1e18, 1e18, 1e18);
    vector max_position = set(-1e18, -1e18, -1e18);

    foreach (int source_vertex; source_vertices)
    {
        int source_point = vertexpoint(0, source_vertex);
        vector position = point(0, "P", source_point);
        vector uv = hasvertexattrib(0, "uv")
            ? vertex(0, "uv", source_vertex)
            : (haspointattrib(0, "uv")
                ? point(0, "uv", source_point) : set(0, 0, 0));
        vector uv3 = hasvertexattrib(0, "uv3")
            ? vertex(0, "uv3", source_vertex)
            : (haspointattrib(0, "uv3")
                ? point(0, "uv3", source_point)
                : set(position.x, position.z, 0));
        vector normal = hasvertexattrib(0, "N")
            ? vertex(0, "N", source_vertex)
            : (haspointattrib(0, "N")
                ? point(0, "N", source_point) : set(0, 1, 0));
        vector color = hasvertexattrib(0, "Cd")
            ? vertex(0, "Cd", source_vertex)
            : (haspointattrib(0, "Cd")
                ? point(0, "Cd", source_point) : set(0, 0, 0));
        append(source_p, position);
        append(source_uv, uv);
        append(source_uv3, uv3);
        append(source_n, normal);
        append(source_cd, color);
        min_position = min(min_position, position);
        max_position = max(max_position, position);
    }

    int min_chunk_x = 0;
    int max_chunk_x = 0;
    int min_chunk_z = 0;
    int max_chunk_z = 0;
    if (enable_chunking)
    {
        min_chunk_x = int(floor(
            (min_position.x - chunk_origin.x) / chunk_size));
        max_chunk_x = int(floor(
            (max_position.x - chunk_origin.x - 1e-5) / chunk_size));
        min_chunk_z = int(floor(
            (min_position.z - chunk_origin.z) / chunk_size));
        max_chunk_z = int(floor(
            (max_position.z - chunk_origin.z - 1e-5) / chunk_size));
    }

    for (int chunk_x = min_chunk_x;
        chunk_x <= max_chunk_x;
        ++chunk_x)
    {
        for (int chunk_z = min_chunk_z;
            chunk_z <= max_chunk_z;
            ++chunk_z)
        {
            vector a_p[] = source_p;
            vector a_uv[] = source_uv;
            vector a_uv3[] = source_uv3;
            vector a_n[] = source_n;
            vector a_cd[] = source_cd;
            vector b_p[], b_uv[], b_uv3[], b_n[], b_cd[];
            vector c_p[], c_uv[], c_uv3[], c_n[], c_cd[];
            vector d_p[], d_uv[], d_uv3[], d_n[], d_cd[];
            vector e_p[], e_uv[], e_uv3[], e_n[], e_cd[];

            if (enable_chunking)
            {
                float min_x = chunk_origin.x + float(chunk_x) * chunk_size;
                float max_x = min_x + chunk_size;
                float min_z = chunk_origin.z + float(chunk_z) * chunk_size;
                float max_z = min_z + chunk_size;
                clip_plane(
                    a_p, a_uv, a_uv3, a_n, a_cd,
                    0, min_x, 1,
                    b_p, b_uv, b_uv3, b_n, b_cd);
                clip_plane(
                    b_p, b_uv, b_uv3, b_n, b_cd,
                    0, max_x, 0,
                    c_p, c_uv, c_uv3, c_n, c_cd);
                clip_plane(
                    c_p, c_uv, c_uv3, c_n, c_cd,
                    2, min_z, 1,
                    d_p, d_uv, d_uv3, d_n, d_cd);
                clip_plane(
                    d_p, d_uv, d_uv3, d_n, d_cd,
                    2, max_z, 0,
                    e_p, e_uv, e_uv3, e_n, e_cd);
            }
            else
            {
                e_p = a_p;
                e_uv = a_uv;
                e_uv3 = a_uv3;
                e_n = a_n;
                e_cd = a_cd;
            }

            int clipped_count = len(e_p);
            if (clipped_count < 3)
                continue;

            string chunk_key = sprintf("%d_%d", chunk_x, chunk_z);
            int chunk_id =
                random_shash(chunk_key) & 0x7fffffff;
            int chunk_index = find(chunk_keys, chunk_key);
            if (chunk_index < 0)
            {
                append(chunk_keys, chunk_key);
                append(chunk_vertex_counts, 0);
                chunk_index = len(chunk_keys) - 1;
            }

            for (int triangle = 1;
                triangle < clipped_count - 1;
                ++triangle)
            {
                int polygon_indices[] = array(0, triangle, triangle + 1);
                int new_primitive = addprim(0, "poly");
                for (int local_vertex = 0;
                    local_vertex < 3;
                    ++local_vertex)
                {
                    int clipped_index = polygon_indices[local_vertex];
                    int new_point = addpoint(0, e_p[clipped_index]);
                    addvertex(0, new_primitive, new_point);
                    setvertexattrib(
                        0, "uv", new_primitive, local_vertex,
                        e_uv[clipped_index], "set");
                    setvertexattrib(
                        0, "uv3", new_primitive, local_vertex,
                        e_uv3[clipped_index], "set");
                    setvertexattrib(
                        0, "N", new_primitive, local_vertex,
                        normalize(e_n[clipped_index]), "set");
                    setvertexattrib(
                        0, "Cd", new_primitive, local_vertex,
                        e_cd[clipped_index], "set");
                }

                foreach (string attribute_name; integer_attributes)
                {
                    if (hasprimattrib(0, attribute_name))
                        setprimattrib(
                            0, attribute_name, new_primitive,
                            int(prim(
                                0, attribute_name, source_primitive)),
                            "set");
                }
                foreach (string attribute_name; float_attributes)
                {
                    if (hasprimattrib(0, attribute_name))
                        setprimattrib(
                            0, attribute_name, new_primitive,
                            float(prim(
                                0, attribute_name, source_primitive)),
                            "set");
                }
                foreach (string attribute_name; string_attributes)
                {
                    if (hasprimattrib(0, attribute_name))
                        setprimattrib(
                            0, attribute_name, new_primitive,
                            string(prim(
                                0, attribute_name, source_primitive)),
                            "set");
                }
                foreach (string group_name; primitive_groups)
                {
                    if (inprimgroup(0, group_name, source_primitive))
                        setprimgroup(
                            0, group_name, new_primitive, 1, "set");
                }

                setprimattrib(
                    0, "chunk_x", new_primitive, chunk_x, "set");
                setprimattrib(
                    0, "chunk_z", new_primitive, chunk_z, "set");
                setprimattrib(
                    0, "chunk_key", new_primitive, chunk_key, "set");
                setprimattrib(
                    0, "chunk_id", new_primitive, chunk_id, "set");
                setprimattrib(
                    0, "name", new_primitive,
                    sprintf(
                        "CityRoad_%s_Chunk_%s", role, chunk_key),
                    "set");
                chunk_vertex_counts[chunk_index] += 3;
            }
        }
    }
}

for (int primitive = original_primitive_count - 1;
    primitive >= 0;
    --primitive)
    removeprim(0, primitive, 0);
for (int point_number = original_point_count - 1;
    point_number >= 0;
    --point_number)
    removepoint(0, point_number);

int maximum_chunk_vertex_count = 0;
int oversized_chunk_count = 0;
foreach (int count; chunk_vertex_counts)
{
    maximum_chunk_vertex_count = max(maximum_chunk_vertex_count, count);
    if (count >= 65535)
        oversized_chunk_count++;
}
setdetailattrib(0, "chunk_count", len(chunk_keys), "set");
setdetailattrib(
    0, "max_chunk_vertex_count", maximum_chunk_vertex_count, "set");
setdetailattrib(
    0, "oversized_chunk_count", oversized_chunk_count, "set");
setdetailattrib(0, "unassigned_chunk_primitive_count", 0, "set");
if (oversized_chunk_count > 0)
    error(sprintf(
        "CityRoad %s contains %d chunks over the UInt16 vertex limit; reduce chunk_size.",
        role, oversized_chunk_count));
"""


def chunk_vex(role: str) -> str:
    return CHUNK_CLIP_VEX_TEMPLATE.replace("__ROLE__", role)


def ensure_parm_templates(definition: hou.HDADefinition) -> None:
    ptg = definition.parmTemplateGroup()

    marking_templates = (
        hou.ToggleParmTemplate(
            "enable_road_markings",
            "Enable Road Markings / 启用道路标线",
            default_value=False),
        hou.ToggleParmTemplate(
            "enable_crosswalks",
            "Enable Crosswalks / 启用斑马线",
            default_value=True),
        hou.FloatParmTemplate(
            "center_line_width",
            "Center Line Width / 中心线宽度",
            1, default_value=(0.12,), min=0.01, max=1.0),
        hou.FloatParmTemplate(
            "lane_line_width",
            "Lane Line Width / 车道线宽度",
            1, default_value=(0.10,), min=0.01, max=1.0),
        hou.FloatParmTemplate(
            "edge_line_width",
            "Edge Line Width / 边缘线宽度",
            1, default_value=(0.10,), min=0.01, max=1.0),
        hou.FloatParmTemplate(
            "marking_dash_length",
            "Dash Length / 虚线长度",
            1, default_value=(3.0,), min=0.05, max=20.0),
        hou.FloatParmTemplate(
            "marking_dash_gap",
            "Dash Gap / 虚线间隔",
            1, default_value=(6.0,), min=0.0, max=30.0),
        hou.FloatParmTemplate(
            "marking_height_offset",
            "Height Offset / 标线高度偏移",
            1, default_value=(0.015,), min=0.001, max=0.1),
        hou.FloatParmTemplate(
            "crosswalk_depth",
            "Crosswalk Depth / 斑马线纵深",
            1, default_value=(4.0,), min=0.5, max=12.0),
        hou.FloatParmTemplate(
            "crosswalk_stripe_width",
            "Crosswalk Stripe Width / 斑马线条宽",
            1, default_value=(0.5,), min=0.05, max=2.0),
        hou.FloatParmTemplate(
            "crosswalk_stripe_gap",
            "Crosswalk Stripe Gap / 斑马线条间距",
            1, default_value=(0.5,), min=0.0, max=2.0),
        hou.FloatParmTemplate(
            "crosswalk_side_margin",
            "Crosswalk Side Margin / 斑马线侧边距",
            1, default_value=(0.35,), min=0.0, max=2.0),
        hou.FloatParmTemplate(
            "crosswalk_setback",
            "Crosswalk Setback / 斑马线退距",
            1, default_value=(1.0,), min=0.0, max=10.0),
        hou.FloatParmTemplate(
            "stop_line_width",
            "Stop Line Width / 停止线宽度",
            1, default_value=(0.3,), min=0.05, max=1.0),
        hou.FloatParmTemplate(
            "stop_line_gap",
            "Stop Line Gap / 停止线与斑马线间距",
            1, default_value=(1.0,), min=0.0, max=10.0),
    )

    changed = False
    if ptg.find("marking_folder") is None:
        marking_folder = hou.FolderParmTemplate(
            "marking_folder",
            "Road Marking / 道路标线",
            parm_templates=marking_templates,
            folder_type=hou.folderType.Simple)
        ptg.appendToFolder(
            ptg.findIndices("stdswitcher4_2"), marking_folder)
        changed = True
    else:
        for template in marking_templates:
            if ptg.find(template.name()) is None:
                ptg.appendToFolder(
                    ptg.findIndices("marking_folder"), template)
                changed = True

    if ptg.find("marking_unity_material") is None:
        material_template = hou.StringParmTemplate(
            "marking_unity_material",
            "Marking Unity Material / 标线 Unity 材质",
            1, default_value=("",))
        ptg.appendToFolder(
            ptg.findIndices("material_folder"), material_template)
        changed = True

    if changed:
        definition.setParmTemplateGroup(ptg)


def ensure_node(
    parent: hou.Node,
    type_name: str,
    name: str,
    inputs: tuple[hou.Node | None, ...] = ()) -> hou.Node:
    node = parent.node(name)
    if node is None:
        node = parent.createNode(type_name, name)
    elif node.type().name() != type_name:
        raise RuntimeError(
            f"{node.path()} exists with type {node.type().name()}, "
            f"expected {type_name}")
    for input_index, input_node in enumerate(inputs):
        node.setInput(input_index, input_node)
    return node


def configure_wrangle(
    node: hou.Node,
    run_over: int,
    snippet: str,
    comment: str) -> None:
    node.parm("class").set(run_over)
    node.parm("snippet").set(textwrap.dedent(snippet).strip())
    node.setComment(comment)


def configure_pack(node: hou.Node) -> None:
    node.parm("packbyname").set(1)
    node.parm("nameattribute").set("name")
    node.parm("packedfragments").set(0)
    node.parm("pivot").set("centroid")
    node.parm("transfer_attributes").set(
        "name chunk_x chunk_z chunk_key chunk_id")
    node.setComment(
        "按稳定 chunk name 打包为独立 Unity 输出；Pivot 使用块质心。")


def ensure_network_box(
    core: hou.Node,
    name: str,
    label: str,
    items: list[hou.NetworkMovableItem],
    color: hou.Color) -> None:
    box = next(
        (candidate for candidate in core.networkBoxes()
         if candidate.name() == name),
        None)
    if box is None:
        box = core.createNetworkBox(name)
    box.setComment(label)
    box.setColor(color)
    for item in items:
        try:
            box.addItem(item)
        except hou.OperationFailed:
            pass
    try:
        box.fitAroundContents()
    except hou.OperationFailed:
        pass


def ensure_sticky(
    core: hou.Node,
    name: str,
    text: str,
    position: hou.Vector2,
    color: hou.Color) -> hou.StickyNote:
    note = next(
        (candidate for candidate in core.stickyNotes()
         if candidate.name() == name),
        None)
    if note is None:
        note = core.createStickyNote(name)
    note.setText(text)
    note.setPosition(position)
    note.setColor(color)
    return note


def connect_chunked_output(
    core: hou.Node,
    contract_name: str,
    output_name: str,
    role: str,
    x_offset: float = 0.0) -> tuple[hou.Node, hou.Node]:
    contract = core.node(contract_name)
    output = core.node(output_name)
    if contract is None or output is None:
        raise RuntimeError(
            f"Missing formal output chain {contract_name} -> {output_name}")

    clip = ensure_node(
        core, "attribwrangle", f"CITYROAD_CHUNK_CLIP_{role.upper()}",
        (contract,))
    configure_wrangle(
        clip, 0, chunk_vex(role),
        f"{role}: 在 XZ 网格边界实际切开多边形并写入稳定 Chunk 合约。")
    pack = ensure_node(
        core, "pack", f"CITYROAD_CHUNK_PACK_{role.upper()}", (clip,))
    configure_pack(pack)
    output.setInput(0, pack)

    base = contract.position()
    clip.setPosition(base + hou.Vector2(2.0 + x_offset, 0.0))
    pack.setPosition(base + hou.Vector2(4.0 + x_offset, 0.0))
    output.setPosition(base + hou.Vector2(6.0 + x_offset, 0.0))
    return clip, pack


def main() -> dict:
    hda = hou.node(HDA_NODE_PATH)
    core = hou.node(CORE_NODE_PATH)
    if hda is None or core is None:
        raise RuntimeError(
            f"Expected live CityRoad at {HDA_NODE_PATH}")

    definition = hda.type().definition()
    if definition is None:
        raise RuntimeError("CityRoad node has no HDA definition")
    library_path = definition.libraryFilePath().replace("\\", "/")
    if not library_path.endswith(EXPECTED_LIBRARY_SUFFIX):
        raise RuntimeError(
            f"Refusing to patch unexpected definition: {library_path}")

    allowed_editing = False
    if not hda.isEditableInsideLockedHDA():
        hda.allowEditingOfContents()
        allowed_editing = True

    ensure_parm_templates(definition)

    road_contract = core.node("OUTPUT_CONTRACT_ROAD_SURFACE")
    side_contract = core.node("OUTPUT_CONTRACT_SIDEWALK")
    collision_contract = core.node("OUTPUT_CONTRACT_COLLISION")
    if road_contract is None or side_contract is None or collision_contract is None:
        raise RuntimeError("CityRoad formal output contracts are incomplete")

    road_source = core.node("UNITY_FIX_HANDEDNESS_NORMALS")
    true_boundary = core.node("TUTORIAL_V3_TRUE_OUTER_BOUNDARY")
    side_source = core.node("TUTORIAL_V3_SIDEWALK_CANDIDATE")
    if road_source is None or true_boundary is None or side_source is None:
        raise RuntimeError("Accepted V3 shading sources are missing")

    shading_vertex = ensure_node(
        core, "attribwrangle", "CITYROAD_SHADING_VERTEX_CONTRACT",
        (road_source, true_boundary))
    configure_wrangle(
        shading_vertex, 3, ROAD_VERTEX_VEX,
        "写入连续 uv3 与最终外边界 Cd.r 磨损遮罩；不改变 V3 拓扑。")
    road_material = ensure_node(
        core, "attribwrangle", "CITYROAD_ROAD_MATERIAL_ASSIGN",
        (shading_vertex,))
    configure_wrangle(
        road_material, 1, ROAD_MATERIAL_VEX,
        "仅当实例显式填写路径时写入 road unity_material。")
    road_contract.setInput(0, road_material)

    side_material = ensure_node(
        core, "attribwrangle", "CITYROAD_SIDE_MATERIAL_ASSIGN",
        (side_source,))
    configure_wrangle(
        side_material, 1, SIDEWALK_MATERIAL_VEX,
        "按 city_part 独立绑定 curb/sidewalk 材质；默认仍为空。")
    side_contract.setInput(0, side_material)

    marking_source = core.node("ROAD_POLYFRAME")
    junction_patches = core.node("JUNCTION_BUILD_PATCHES")
    graph_junctions = core.node("GRAPH_CLASSIFY_JUNCTIONS")
    if marking_source is None or junction_patches is None or graph_junctions is None:
        raise RuntimeError("CityRoad marking source nodes are missing")

    marking_build = ensure_node(
        core, "attribwrangle", "CITYROAD_BUILD_STATIC_MARKING_MESH",
        (marking_source, road_source, junction_patches, graph_junctions))
    configure_wrangle(
        marking_build, 0, MARKING_BUILD_VEX,
        "生成中心/车道/边缘线、斑马线与停止线的静态不透明网格。")
    marking_contract = ensure_node(
        core, "attribwrangle", "CITYROAD_MARKING_OUTPUT_CONTRACT",
        (marking_build,))
    configure_wrangle(
        marking_contract, 0,
        """
        setdetailattrib(
            0, "city_road_contract_version", "1.1.0", "set");
        setdetailattrib(
            0, "output_role", "OUT_ROAD_MARKINGS", "set");
        """,
        "正式标线网格输出合约。")

    road_clip, road_pack = connect_chunked_output(
        core, "OUTPUT_CONTRACT_ROAD_SURFACE",
        "OUT_ROAD_SURFACE", "RoadSurface")
    side_clip, side_pack = connect_chunked_output(
        core, "OUTPUT_CONTRACT_SIDEWALK",
        "OUT_SIDEWALK_CURB", "SidewalkCurb")
    collision_clip, collision_pack = connect_chunked_output(
        core, "OUTPUT_CONTRACT_COLLISION",
        "OUT_ROAD_COLLISION", "Collision")

    marking_clip = ensure_node(
        core, "attribwrangle", "CITYROAD_CHUNK_CLIP_MARKINGS",
        (marking_contract,))
    configure_wrangle(
        marking_clip, 0, chunk_vex("Markings"),
        "标线使用与路面一致的 XZ Chunk 边界。")
    marking_pack = ensure_node(
        core, "pack", "CITYROAD_CHUNK_PACK_MARKINGS",
        (marking_clip,))
    configure_pack(marking_pack)
    marking_output = ensure_node(
        core, "output", "OUT_ROAD_MARKINGS", (marking_pack,))
    marking_output.parm("outputidx").set(6)
    marking_output.setComment(
        "正式静态道路标线网格；OUT_ROAD_MARKING_POINTS 保留为调试输出。")

    road_base = road_contract.position()
    shading_vertex.setPosition(road_base + hou.Vector2(-4.0, 1.5))
    road_material.setPosition(road_base + hou.Vector2(-2.0, 1.5))
    side_base = side_contract.position()
    side_material.setPosition(side_base + hou.Vector2(-2.0, 1.5))
    marking_build.setPosition(road_base + hou.Vector2(-4.0, -6.0))
    marking_contract.setPosition(road_base + hou.Vector2(-2.0, -6.0))
    marking_clip.setPosition(road_base + hou.Vector2(0.0, -6.0))
    marking_pack.setPosition(road_base + hou.Vector2(2.0, -6.0))
    marking_output.setPosition(road_base + hou.Vector2(4.0, -6.0))

    shading_note = ensure_sticky(
        core,
        "NOTE_CITYROAD_SHADING_CONTRACT",
        "CityRoad 着色合约\nuv 保留道路方向；uv3 为城市局部米制 XZ；Cd.r 为外边缘磨损。",
        road_base + hou.Vector2(-4.0, 3.2),
        hou.Color((0.22, 0.36, 0.54)))
    marking_note = ensure_sticky(
        core,
        "NOTE_CITYROAD_MARKING_MESH",
        "道路标线\nCook 时生成真实不透明几何；路口去重；斑马线与停止线投射到最终路面。",
        road_base + hou.Vector2(-4.0, -3.8),
        hou.Color((0.50, 0.36, 0.12)))
    chunk_note = ensure_sticky(
        core,
        "NOTE_CITYROAD_CHUNK_OUTPUT",
        "移动端分块\n先在 128m 网格边界切开，再按稳定 chunk name Pack；禁止仅按中心分类。",
        road_base + hou.Vector2(1.0, 3.2),
        hou.Color((0.18, 0.46, 0.28)))

    ensure_network_box(
        core,
        "ORG_12_CITYROAD_SHADING_CONTRACT",
        "CITYROAD_SHADING_CONTRACT / CityRoad 着色合约",
        [shading_vertex, road_material, side_material, shading_note],
        hou.Color((0.20, 0.36, 0.54)))
    ensure_network_box(
        core,
        "ORG_13_CITYROAD_MARKING_MESH",
        "CITYROAD_MARKING_MESH / 静态道路标线",
        [
            marking_build, marking_contract, marking_clip,
            marking_pack, marking_output, marking_note,
        ],
        hou.Color((0.52, 0.36, 0.12)))
    ensure_network_box(
        core,
        "ORG_14_CITYROAD_CHUNK_OUTPUT",
        "CITYROAD_CHUNK_OUTPUT / 移动端分块输出",
        [
            road_clip, road_pack, side_clip, side_pack,
            collision_clip, collision_pack, chunk_note,
        ],
        hou.Color((0.18, 0.46, 0.28)))

    # Current Houdini validation instance uses explicit material paths; HDA
    # defaults remain empty because the parameter templates above keep "".
    instance_values = {
        "enable_road_markings": 1,
        "enable_crosswalks": 1,
        "road_unity_material":
            "Assets/PCG/Materials/M_PCG_CityRoad_Asphalt.mat",
        "sidewalk_unity_material":
            "Assets/PCG/Materials/M_PCG_CityRoad_Sidewalk.mat",
        "curb_unity_material":
            "Assets/PCG/Materials/M_PCG_CityRoad_Curb.mat",
        "marking_unity_material":
            "Assets/PCG/Materials/M_PCG_CityRoad_Marking.mat",
    }
    for parm_name, value in instance_values.items():
        parm = hda.parm(parm_name)
        if parm is None:
            raise RuntimeError(f"Missing CityRoad parameter: {parm_name}")
        parm.set(value)

    output_nodes = [
        core.node("OUT_ROAD_SURFACE"),
        core.node("OUT_SIDEWALK_CURB"),
        core.node("OUT_ROAD_MARKING_POINTS"),
        core.node("OUT_ROAD_COLLISION"),
        core.node("OUT_ROAD_CENTERLINE_GRAPH"),
        core.node("OUT_BUILDABLE_BLOCKS"),
        marking_output,
    ]
    for output_node in output_nodes:
        if output_node is not None:
            output_node.cook(force=True)

    definition.updateFromNode(hda)
    hou.hipFile.save()

    return {
        "status": "success",
        "hda": hda.path(),
        "definition": definition.libraryFilePath(),
        "hip": hou.hipFile.path(),
        "allow_editing_of_contents_executed": allowed_editing,
        "new_output": marking_output.path(),
        "output_indices": {
            node.name(): node.parm("outputidx").eval()
            for node in output_nodes
            if node is not None and node.parm("outputidx") is not None
        },
    }


if __name__ == "__main__":
    print(json.dumps(main(), ensure_ascii=False, indent=2))
