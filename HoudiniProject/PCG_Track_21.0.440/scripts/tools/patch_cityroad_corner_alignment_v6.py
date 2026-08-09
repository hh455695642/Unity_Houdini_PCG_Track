"""CityRoad V6.2 incremental corner, inner-offset and crosswalk alignment patch.

This script is a guarded migration helper for the current editable CityRoad HDA.
The live HDA node network remains the source of truth.  It never clears the hip,
rebuilds the asset, or touches Houdini Engine Unity plugin files.  The production
SidewalkCurb output is also guarded and rewired to the shared V4 corridor+junction
arc chain so the legacy square TutorialLab boundary cannot override live corners.
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
import shutil

import hou


ASSET_PATH = "/obj/CityRoad_DEV"
CORE_PATH = ASSET_PATH + "/CityRoadCore"
EXPECTED_TYPE = "pcgbike::CityRoad::1.0"
EXPECTED_HDA_SUFFIX = "Assets/PCG/HDA/City/CityRoad.hda"


JUNCTION_BUILD_V6 = r'''
int original_prims = nprimitives(0);
int original_points = npoints(0);
if (!chi("../../enable_intersections"))
{
    for (int pr = original_prims - 1; pr >= 0; --pr) removeprim(0, pr, 1);
    for (int pt = original_points - 1; pt >= 0; --pt) removepoint(0, pt);
    return;
}

float corner_radius = max(ch("../../junction_corner_radius"), 0.01);
float sample_spacing = max(ch("../../junction_sample_spacing"), 0.05);
float snap_tolerance = max(ch("../../endpoint_snap_tolerance"), 0.001);
string road_material = chs("../../road_unity_material");

addvertexattrib(0, "uv", set(0.0, 0.0, 0.0));
addprimattrib(0, "city_part", "");
addprimattrib(0, "unity_material", "");
addpointattrib(0, "junction_mouth_center", int(0));
addpointattrib(0, "junction_mouth_left", set(0.0, 0.0, 0.0));
addpointattrib(0, "junction_mouth_right", set(0.0, 0.0, 0.0));
addpointattrib(0, "junction_mouth_outward", set(0.0, 0.0, 0.0));
addpointattrib(0, "junction_corner_tangent_left", set(0.0, 0.0, 0.0));
addpointattrib(0, "junction_corner_tangent_right", set(0.0, 0.0, 0.0));
addpointattrib(0, "junction_left_arc_segments", int(0));
addpointattrib(0, "junction_right_arc_segments", int(0));
addpointattrib(0, "junction_effective_corner_radius", 0.0);
addprimattrib(0, "junction_approach_count", int(0));

function float cross_xz(vector a; vector b)
{
    return a.x * b.z - a.z * b.x;
}
function vector rotate_xz(vector value; float angle)
{
    float c = cos(angle);
    float s = sin(angle);
    return set(value.x * c - value.z * s, value.y,
               value.x * s + value.z * c);
}

int total_arc_count = 0;
int max_arc_segments = 0;
int radius_clamp_count = 0;
int orientation_error_count = 0;
int spurious_branch_prune_count = 0;
int uniform_radius_error_count = 0;
float minimum_effective_radius = 1e18;
float maximum_effective_radius = 0.0;
int junction_points[] = expandpointgroup(0, "junction_points");
foreach (int junction_point; junction_points)
{
    string junction_type = point(0, "junction_type", junction_point);
    if (junction_type == "t" && !chi("../../enable_t_junction")) continue;
    if (junction_type == "cross" && !chi("../../enable_cross_junction")) continue;
    if (junction_type != "t" && junction_type != "cross" && junction_type != "complex") continue;

    vector center = point(0, "P", junction_point);
    int road_level = point(0, "road_level", junction_point);
    vector directions[];
    float half_widths[];
    float branch_lengths[];
    int road_ids[];

    for (int pr = 0; pr < original_prims; ++pr)
    {
        if (prim(0, "road_level", pr) != road_level) continue;
        if (hasprimattrib(0, "allow_junction") && prim(0, "allow_junction", pr) == 0) continue;
        int points[] = primpoints(0, pr);
        for (int i = 0; i < len(points) - 1; ++i)
        {
            vector a = point(0, "P", points[i]);
            vector b = point(0, "P", points[i + 1]);
            vector ab = set(b.x - a.x, 0.0, b.z - a.z);
            float length_sq = length2(ab);
            if (length_sq < 1e-10) continue;
            vector ac = set(center.x - a.x, 0.0, center.z - a.z);
            float u = clamp(dot(ac, ab) / length_sq, 0.0, 1.0);
            vector projected = a + ab * u;
            float projected_distance = distance(
                set(projected.x, 0.0, projected.z), set(center.x, 0.0, center.z));
            float road_half_width = max(float(prim(0, "road_width", pr)) * 0.5, 0.05);
            // Only accept graph segments that actually meet the classified junction.
            // A radius-based terminal allowance can accidentally absorb a nearby road
            // and create an extra/reversed mouth.
            if (projected_distance > max(snap_tolerance, 0.01)) continue;

            vector candidates[] = array(a, b);
            float available[] = array(u, 1.0 - u);
            for (int side_index = 0; side_index < 2; ++side_index)
            {
                if (available[side_index] < 1e-4) continue;
                vector branch = set(candidates[side_index].x - center.x, 0.0,
                                    candidates[side_index].z - center.z);
                float branch_length = length(branch);
                if (branch_length < 1e-5) continue;
                // Measure semantic clearance to the next junction/end along the
                // branch.  The old value only measured this resampled edge and
                // made the four corner radii depend on sample phase.
                int step = side_index == 0 ? -1 : 1;
                int cursor = side_index == 0 ? i : i + 1;
                int next_cursor = cursor + step;
                while (next_cursor >= 0 && next_cursor < len(points))
                {
                    vector from_position = point(0, "P", points[cursor]);
                    vector to_position = point(0, "P", points[next_cursor]);
                    branch_length += distance(
                        set(from_position.x, 0.0, from_position.z),
                        set(to_position.x, 0.0, to_position.z));
                    cursor = next_cursor;
                    int graph_point = points[cursor];
                    if (graph_point != junction_point &&
                        int(point(0, "connected_road_count", graph_point)) >= 3)
                        break;
                    next_cursor += step;
                }
                vector direction = normalize(branch);
                int found = -1;
                for (int j = 0; j < len(directions); ++j)
                {
                    if (dot(directions[j], direction) > 0.999)
                    { found = j; break; }
                }
                int road_id = int(prim(0, "road_id", pr));
                if (found < 0)
                {
                    append(directions, direction);
                    append(half_widths, road_half_width);
                    append(branch_lengths, branch_length);
                    append(road_ids, road_id);
                }
                else
                {
                    half_widths[found] = max(half_widths[found], road_half_width);
                    branch_lengths[found] = max(branch_lengths[found], branch_length);
                    road_ids[found] = min(road_ids[found], road_id);
                }
            }
        }
    }

    // The classifier is authoritative for junction degree.  A very short segment
    // ending beside a T mouth must not be promoted to a fourth approach.
    int expected_degree = max(int(point(0, "connected_road_count", junction_point)), 0);
    while (expected_degree >= 3 && len(directions) > expected_degree)
    {
        int prune_index = 0;
        for (int i = 1; i < len(branch_lengths); ++i)
            if (branch_lengths[i] < branch_lengths[prune_index]) prune_index = i;
        removeindex(directions, prune_index);
        removeindex(half_widths, prune_index);
        removeindex(branch_lengths, prune_index);
        removeindex(road_ids, prune_index);
        spurious_branch_prune_count++;
    }
    int branch_count = len(directions);
    if (branch_count < 3) continue;
    float angles[];
    for (int i = 0; i < branch_count; ++i)
        append(angles, atan2(directions[i].z, directions[i].x));
    int order[] = argsort(angles);
    vector sorted_directions[];
    float sorted_widths[];
    float sorted_lengths[];
    int sorted_road_ids[];
    float sorted_angles[];
    foreach (int source_index; order)
    {
        append(sorted_directions, directions[source_index]);
        append(sorted_widths, half_widths[source_index]);
        append(sorted_lengths, branch_lengths[source_index]);
        append(sorted_road_ids, road_ids[source_index]);
        append(sorted_angles, angles[source_index]);
    }

    // One junction uses one visible radius.  Every valid corner contributes a
    // safety limit, then the strictest limit is shared by all corners.
    float junction_radius = corner_radius;
    int valid_corner_count = 0;
    for (int i = 0; i < branch_count; ++i)
    {
        int next = (i + 1) % branch_count;
        float gap = sorted_angles[next] - sorted_angles[i];
        if (next == 0) gap += M_PI * 2.0;
        float denominator = cross_xz(
            sorted_directions[i], sorted_directions[next]);
        if (abs(denominator) < 1e-6 || gap > 2.80) continue;
        float tangent_scale = max(tan(gap * 0.5), 1e-4);
        float maximum_tangent =
            0.45 * min(sorted_lengths[i], sorted_lengths[next]);
        float safe_radius = maximum_tangent * tangent_scale;
        junction_radius = min(junction_radius, safe_radius);
        valid_corner_count++;
    }
    junction_radius = max(junction_radius, 0.01);
    if (junction_radius < corner_radius - 1e-4) radius_clamp_count++;
    minimum_effective_radius = min(minimum_effective_radius, junction_radius);
    maximum_effective_radius = max(maximum_effective_radius, junction_radius);

    float left_distance[];
    float right_distance[];
    vector arc_start[];
    vector arc_end[];
    vector arc_center[];
    float arc_sweep[];
    int arc_segments[];
    int back_gap[];
    resize(left_distance, branch_count);
    resize(right_distance, branch_count);
    resize(arc_start, branch_count);
    resize(arc_end, branch_count);
    resize(arc_center, branch_count);
    resize(arc_sweep, branch_count);
    resize(arc_segments, branch_count);
    resize(back_gap, branch_count);
    for (int i = 0; i < branch_count; ++i)
    {
        left_distance[i] = sorted_widths[i] + junction_radius;
        right_distance[i] = sorted_widths[i] + junction_radius;
    }

    for (int i = 0; i < branch_count; ++i)
    {
        int next = (i + 1) % branch_count;
        vector direction_a = sorted_directions[i];
        vector direction_b = sorted_directions[next];
        vector left_a = set(-direction_a.z, 0.0, direction_a.x);
        vector right_b = set(direction_b.z, 0.0, -direction_b.x);
        vector line_a = center + left_a * sorted_widths[i];
        vector line_b = center + right_b * sorted_widths[next];
        float gap = sorted_angles[next] - sorted_angles[i];
        if (next == 0) gap += M_PI * 2.0;
        float denominator = cross_xz(direction_a, direction_b);
        if (abs(denominator) < 1e-6 || gap > 2.80)
        {
            back_gap[i] = 1;
            arc_segments[i] = 0;
            continue;
        }

        float ta = cross_xz(line_b - line_a, direction_b) / denominator;
        vector corner = line_a + direction_a * ta;
        float tangent_scale = max(tan(gap * 0.5), 1e-4);
        float tangent_distance = junction_radius / tangent_scale;
        float max_tangent = 0.45 * min(sorted_lengths[i], sorted_lengths[next]);
        if (tangent_distance > max_tangent + 1e-4)
            uniform_radius_error_count++;
        float effective_radius = junction_radius;
        vector start = corner + direction_a * tangent_distance;
        vector end = corner + direction_b * tangent_distance;
        vector center_a = start + left_a * effective_radius;
        vector center_b = end + right_b * effective_radius;
        vector circle_center = 0.5 * (center_a + center_b);
        float sweep = max(M_PI - gap, radians(1.0));
        float arc_length = effective_radius * sweep;
        int segment_count = clamp(
            int(ceil(max(arc_length, sample_spacing) / sample_spacing)), 2, 4);

        arc_start[i] = start;
        arc_end[i] = end;
        arc_center[i] = circle_center;
        arc_sweep[i] = sweep;
        arc_segments[i] = segment_count;
        back_gap[i] = 0;
        left_distance[i] = max(left_distance[i], dot(start - center, direction_a));
        right_distance[next] = max(right_distance[next], dot(end - center, direction_b));
        total_arc_count++;
        max_arc_segments = max(max_arc_segments, segment_count);

        vector radial = start - circle_center;
        vector arc_mid = circle_center + rotate_xz(radial, -sweep * 0.5);
        vector chord_mid = 0.5 * (start + end);
        vector bisector = normalize(direction_a + direction_b);
        if (length2(bisector) > 1e-8 &&
            dot(arc_mid - corner, bisector) >=
            dot(chord_mid - corner, bisector) - 1e-4)
            orientation_error_count++;
    }

    float mouth_distance[];
    resize(mouth_distance, branch_count);
    for (int i = 0; i < branch_count; ++i)
        mouth_distance[i] = max(
            max(left_distance[i], right_distance[i]), sorted_widths[i] + junction_radius);

    int boundary_points[];
    int mouth_right_points[];
    int mouth_center_points[];
    int mouth_left_points[];
    for (int i = 0; i < branch_count; ++i)
    {
        int next = (i + 1) % branch_count;
        int previous = (i - 1 + branch_count) % branch_count;
        vector direction = sorted_directions[i];
        vector left = set(-direction.z, 0.0, direction.x);
        vector mouth_right = center + direction * mouth_distance[i] - left * sorted_widths[i];
        vector mouth_left = center + direction * mouth_distance[i] + left * sorted_widths[i];
        vector mouth_center = center + direction * mouth_distance[i];
        int mouth_right_point = addpoint(0, mouth_right);
        int mouth_center_point = addpoint(0, mouth_center);
        int mouth_left_point = addpoint(0, mouth_left);
        append(boundary_points, mouth_right_point);
        append(boundary_points, mouth_center_point);
        append(boundary_points, mouth_left_point);
        append(mouth_right_points, mouth_right_point);
        append(mouth_center_points, mouth_center_point);
        append(mouth_left_points, mouth_left_point);

        vector left_tangent = back_gap[i] ? mouth_left : arc_start[i];
        vector right_tangent = back_gap[previous] ? mouth_right : arc_end[previous];
        setpointattrib(0, "junction_mouth_left", mouth_center_point, mouth_left, "set");
        setpointattrib(0, "junction_mouth_right", mouth_center_point, mouth_right, "set");
        setpointattrib(0, "junction_mouth_outward", mouth_center_point, direction, "set");
        setpointattrib(0, "junction_corner_tangent_left", mouth_center_point, left_tangent, "set");
        setpointattrib(0, "junction_corner_tangent_right", mouth_center_point, right_tangent, "set");
        setpointattrib(0, "junction_left_arc_segments", mouth_center_point,
            back_gap[i] ? 0 : arc_segments[i], "set");
        setpointattrib(0, "junction_right_arc_segments", mouth_center_point,
            back_gap[previous] ? 0 : arc_segments[previous], "set");
        setpointattrib(0, "junction_effective_corner_radius",
            mouth_center_point, junction_radius, "set");

        if (!back_gap[i])
        {
            vector start = arc_start[i];
            vector end = arc_end[i];
            vector circle_center = arc_center[i];
            float join_epsilon = max(snap_tolerance, 0.005);
            if (distance(mouth_left, start) > join_epsilon)
                append(boundary_points, addpoint(0, start));
            int segment_count = arc_segments[i];
            vector radial = start - circle_center;
            for (int segment = 1; segment < segment_count; ++segment)
            {
                float u = float(segment) / float(segment_count);
                vector position = circle_center +
                    rotate_xz(radial, -arc_sweep[i] * u);
                append(boundary_points, addpoint(0, position));
            }
            vector next_direction = sorted_directions[next];
            vector next_left = set(-next_direction.z, 0.0, next_direction.x);
            vector next_mouth_right = center + next_direction * mouth_distance[next]
                - next_left * sorted_widths[next];
            if (distance(end, next_mouth_right) > join_epsilon)
                append(boundary_points, addpoint(0, end));
        }
    }

    if (len(boundary_points) >= 3)
    {
        int boundary = addprim(0, "poly");
        foreach (int point_number; boundary_points)
            addvertex(0, boundary, point_number);
        for (int approach = 0; approach < len(mouth_center_points); ++approach)
        {
            int mouth_right_point = mouth_right_points[approach];
            int mouth_center_point = mouth_center_points[approach];
            int mouth_left_point = mouth_left_points[approach];
            setpointattrib(0, "junction_mouth_center", mouth_center_point, 1, "set");
            setedgegroup(0, "junction_mouth_edges", mouth_right_point, mouth_center_point, 1);
            setedgegroup(0, "junction_mouth_edges", mouth_center_point, mouth_left_point, 1);
        }
        setprimgroup(0, "junction_boundary", boundary, 1, "set");
        setprimattrib(0, "city_part", boundary, "junction_boundary", "set");
        int minimum_road_id = sorted_road_ids[0];
        for (int i = 1; i < branch_count; ++i)
            minimum_road_id = min(minimum_road_id, sorted_road_ids[i]);
        setprimattrib(0, "junction_id", boundary,
            int(point(0, "junction_id", junction_point)), "set");
        setprimattrib(0, "junction_type", boundary, junction_type, "set");
        setprimattrib(0, "junction_approach_count", boundary, branch_count, "set");
        setprimattrib(0, "road_id", boundary, minimum_road_id, "set");
        setprimattrib(0, "road_level", boundary, road_level, "set");
        setprimattrib(0, "collision_class", boundary, 2, "set");
        if (len(road_material) > 0)
            setprimattrib(0, "unity_material", boundary, road_material, "set");
    }
}

for (int pr = original_prims - 1; pr >= 0; --pr) removeprim(0, pr, 1);
for (int pt = original_points - 1; pt >= 0; --pt)
    if (len(pointprims(0, pt)) == 0) removepoint(0, pt);

setdetailattrib(0, "junction_corner_arc_count", total_arc_count, "set");
setdetailattrib(0, "junction_corner_max_segment_count", max_arc_segments, "set");
setdetailattrib(0, "junction_corner_radius_clamp_count", radius_clamp_count, "set");
setdetailattrib(0, "junction_spurious_branch_prune_count", spurious_branch_prune_count, "set");
setdetailattrib(0, "junction_corner_orientation_error_count", orientation_error_count, "set");
setdetailattrib(0, "junction_uniform_radius_error_count", uniform_radius_error_count, "set");
setdetailattrib(0, "junction_min_effective_corner_radius",
    minimum_effective_radius < 1e17 ? minimum_effective_radius : 0.0, "set");
setdetailattrib(0, "junction_max_effective_corner_radius",
    maximum_effective_radius, "set");
if (max_arc_segments > 4 || orientation_error_count != 0 ||
    uniform_radius_error_count != 0)
    error(sprintf(
        "CityRoad V6.1 junction fillet failed: max_segments=%d orientation=%d uniform_radius=%d",
        max_arc_segments, orientation_error_count, uniform_radius_error_count));
'''


APPROACH_METADATA_V6 = r'''
// V6: one point per exact junction mouth.  No independent width reconstruction.
int original_points = npoints(0);
int original_prims = nprimitives(0);
int expected = 0;
int actual = 0;
int missing_contract = 0;
int alignment_errors = 0;
float max_alignment_error = 0.0;

addpointattrib(0, "approach_direction", set(0.0, 0.0, 0.0));
addpointattrib(0, "approach_width", 0.0);
addpointattrib(0, "approach_mouth_distance", 0.0);
addpointattrib(0, "approach_mouth_left", set(0.0, 0.0, 0.0));
addpointattrib(0, "approach_mouth_right", set(0.0, 0.0, 0.0));
addpointattrib(0, "approach_mouth_tangent", set(0.0, 0.0, 0.0));
addpointattrib(0, "approach_corner_tangent_left", set(0.0, 0.0, 0.0));
addpointattrib(0, "approach_corner_tangent_right", set(0.0, 0.0, 0.0));
addpointattrib(0, "approach_left_arc_segments", int(0));
addpointattrib(0, "approach_right_arc_segments", int(0));
addpointattrib(0, "approach_effective_corner_radius", 0.0);
addpointattrib(0, "junction_center", set(0.0, 0.0, 0.0));
addpointattrib(0, "approach_id", int(-1));

for (int jp = 0; jp < original_prims; ++jp)
{
    if (!inprimgroup(0, "junction_boundary", jp)) continue;
    int bpts[] = primpoints(0, jp);
    if (len(bpts) < 3) continue;
    int level = int(prim(0, "road_level", jp));
    int jid = int(prim(0, "junction_id", jp));
    int helper = -1;
    for (int p = 0; p < npoints(1); ++p)
    {
        if (int(point(1, "junction_id", p)) == jid &&
            int(point(1, "road_level", p)) == level &&
            int(point(1, "connected_road_count", p)) >= 3)
        { helper = p; break; }
    }
    if (helper < 0) continue;
    vector center = point(1, "P", helper);
    int degree = int(point(1, "connected_road_count", helper));
    expected += degree;

    vector directions[];
    float distances[];
    int road_ids[];
    int segment_ids[];
    float widths[];
    for (int rp = 0; rp < nprimitives(1); ++rp)
    {
        if (hasprimattrib(1, "road_level") &&
            int(prim(1, "road_level", rp)) != level) continue;
        if (hasprimattrib(1, "allow_junction") &&
            !int(prim(1, "allow_junction", rp))) continue;
        int rpts[] = primpoints(1, rp);
        if (len(rpts) < 2) continue;
        float best = 1e18;
        int bestseg = -1;
        float bestt = 0.0;
        vector bestdir = 0;
        for (int s = 0; s < len(rpts) - 1; ++s)
        {
            vector a = point(1, "P", rpts[s]);
            vector b = point(1, "P", rpts[s + 1]);
            vector delta = set(b.x - a.x, 0.0, b.z - a.z);
            float l2 = max(length2(delta), 1e-10);
            float t = clamp(dot(set(center.x - a.x, 0.0, center.z - a.z), delta) / l2, 0.0, 1.0);
            vector closest = set(a.x, 0.0, a.z) + delta * t;
            float d = distance(closest, set(center.x, 0.0, center.z));
            if (d < best)
            { best = d; bestseg = s; bestt = t; bestdir = normalize(delta); }
        }
        if (bestseg < 0) continue;
        vector candidates[];
        if (bestseg == 0 && bestt < 0.05)
            append(candidates, bestdir);
        else if (bestseg == len(rpts) - 2 && bestt > 0.95)
            append(candidates, -bestdir);
        else
        {
            append(candidates, bestdir);
            append(candidates, -bestdir);
        }
        foreach (vector candidate_direction; candidates)
        {
            append(directions, normalize(set(
                candidate_direction.x, 0.0, candidate_direction.z)));
            append(distances, best);
            append(road_ids, int(prim(1, "road_id", rp)));
            append(segment_ids, int(prim(1, "segment_id", rp)));
            append(widths, max(float(prim(1, "road_width", rp)), 0.5));
        }
    }

    int used[];
    resize(used, len(directions));
    foreach (int mouth_point; bpts)
    {
        if (!int(point(0, "junction_mouth_center", mouth_point))) continue;
        vector mouth = point(0, "P", mouth_point);
        vector outward = point(0, "junction_mouth_outward", mouth_point);
        if (length2(outward) < 1e-8)
            outward = normalize(set(mouth.x - center.x, 0.0, mouth.z - center.z));
        int best_candidate = -1;
        float best_score = -1e18;
        for (int candidate = 0; candidate < len(directions); ++candidate)
        {
            if (used[candidate]) continue;
            float score = dot(outward, directions[candidate]) - distances[candidate] * 1e-5;
            if (score > best_score)
            { best_score = score; best_candidate = candidate; }
        }
        if (best_candidate < 0 || dot(outward, directions[best_candidate]) < 0.985)
        {
            missing_contract++;
            continue;
        }
        used[best_candidate] = 1;

        vector mouth_left = point(0, "junction_mouth_left", mouth_point);
        vector mouth_right = point(0, "junction_mouth_right", mouth_point);
        vector tangent = mouth_right - mouth_left;
        float exact_width = length(tangent);
        if (exact_width < 1e-5)
        {
            missing_contract++;
            continue;
        }
        tangent /= exact_width;
        float center_error = distance(mouth, 0.5 * (mouth_left + mouth_right));
        float perpendicular_error = abs(dot(tangent, outward));
        float alignment_error = max(center_error, perpendicular_error);
        max_alignment_error = max(max_alignment_error, alignment_error);
        if (center_error > 0.001 || perpendicular_error > 0.001)
            alignment_errors++;

        int p = addpoint(0, mouth);
        setpointattrib(0, "approach_direction", p, outward, "set");
        setpointattrib(0, "approach_width", p, exact_width, "set");
        setpointattrib(0, "approach_mouth_distance", p,
            distance(center, mouth), "set");
        setpointattrib(0, "approach_mouth_left", p, mouth_left, "set");
        setpointattrib(0, "approach_mouth_right", p, mouth_right, "set");
        setpointattrib(0, "approach_mouth_tangent", p, tangent, "set");
        setpointattrib(0, "approach_corner_tangent_left", p,
            vector(point(0, "junction_corner_tangent_left", mouth_point)), "set");
        setpointattrib(0, "approach_corner_tangent_right", p,
            vector(point(0, "junction_corner_tangent_right", mouth_point)), "set");
        setpointattrib(0, "approach_left_arc_segments", p,
            int(point(0, "junction_left_arc_segments", mouth_point)), "set");
        setpointattrib(0, "approach_right_arc_segments", p,
            int(point(0, "junction_right_arc_segments", mouth_point)), "set");
        setpointattrib(0, "approach_effective_corner_radius", p,
            float(point(0, "junction_effective_corner_radius", mouth_point)), "set");
        setpointattrib(0, "junction_center", p, center, "set");
        setpointattrib(0, "junction_id", p, jid, "set");
        setpointattrib(0, "road_level", p, level, "set");
        setpointattrib(0, "road_id", p, road_ids[best_candidate], "set");
        setpointattrib(0, "segment_id", p, segment_ids[best_candidate], "set");
        setpointattrib(0, "approach_id", p, jid * 100 + actual, "set");
        setpointgroup(0, "junction_approaches", p, 1, "set");
        actual++;
    }
}

for (int pr = original_prims - 1; pr >= 0; --pr) removeprim(0, pr, 0);
for (int pt = original_points - 1; pt >= 0; --pt) removepoint(0, pt);
setdetailattrib(0, "crosswalk_expected_approach_count", expected, "set");
setdetailattrib(0, "crosswalk_actual_approach_count", actual, "set");
setdetailattrib(0, "crosswalk_approach_contract_pass",
    int(expected == actual && missing_contract == 0 && alignment_errors == 0), "set");
setdetailattrib(0, "junction_mouth_missing_contract_count", missing_contract, "set");
setdetailattrib(0, "junction_mouth_alignment_error_count", alignment_errors, "set");
setdetailattrib(0, "junction_mouth_max_alignment_error", max_alignment_error, "set");
if (expected != actual || missing_contract != 0 || alignment_errors != 0)
    error(sprintf(
        "CityRoad V6 approach contract failed: expected=%d actual=%d missing=%d alignment=%d max_error=%.6f",
        expected, actual, missing_contract, alignment_errors, max_alignment_error));
'''


JUNCTION_SURFACE_BOUNDARY_V6 = r'''
// V6: Core and helper arms share the exact mouth-left/right contract.
int original_prims = nprimitives(0);
int original_points = npoints(0);
int source_boundaries[] = expandprimgroup(0, "junction_boundary");
int approaches[] = expandpointgroup(1, "junction_approaches");

addprimattrib(0, "junction_id", -1);
addprimattrib(0, "junction_type", "none");
addprimattrib(0, "road_level", 0);
addprimattrib(0, "road_id", -1);
addprimattrib(0, "segment_id", -1);
addprimattrib(0, "approach_id", -1);
addprimattrib(0, "junction_region_role", "");
addprimattrib(0, "city_part", "");

float extension =
    max(ch("../../crosswalk_setback"), 0.0)
    + max(ch("../../crosswalk_depth"), 0.5)
    + max(ch("../../stop_line_gap"), 0.0)
    + max(ch("../../stop_line_width"), 0.05)
    + max(0.25, max(ch("../../junction_sample_spacing"), 0.01) * 0.5);

int core_count = 0;
foreach (int source_prim; source_boundaries)
{
    int source_points[] = primpoints(0, source_prim);
    if (len(source_points) < 3) continue;
    int output_points[];
    foreach (int source_point; source_points)
        append(output_points, addpoint(0, vector(point(0, "P", source_point))));
    int output_prim = addprim(0, "poly");
    foreach (int output_point; output_points) addvertex(0, output_prim, output_point);
    int jid = int(prim(0, "junction_id", source_prim));
    int level = int(prim(0, "road_level", source_prim));
    setprimattrib(0, "junction_id", output_prim, jid, "set");
    setprimattrib(0, "junction_type", output_prim,
        string(prim(0, "junction_type", source_prim)), "set");
    setprimattrib(0, "road_level", output_prim, level, "set");
    setprimattrib(0, "road_id", output_prim,
        int(prim(0, "road_id", source_prim)), "set");
    setprimattrib(0, "junction_region_role", output_prim, "core", "set");
    setprimattrib(0, "city_part", output_prim, "junction_surface_boundary", "set");
    setprimgroup(0, "junction_surface_boundary", output_prim, 1, "set");
    setprimgroup(0, "junction_surface_core", output_prim, 1, "set");
    core_count++;
}

int arm_count = 0;
int extent_errors = 0;
int mouth_contract_errors = 0;
foreach (int approach_point; approaches)
{
    vector mouth = point(1, "P", approach_point);
    vector outward = point(1, "approach_direction", approach_point);
    outward = normalize(set(outward.x, 0.0, outward.z));
    vector mouth_left = point(1, "approach_mouth_left", approach_point);
    vector mouth_right = point(1, "approach_mouth_right", approach_point);
    if (length2(outward) < 1e-8 || distance(mouth_left, mouth_right) < 1e-5)
    {
        extent_errors++;
        continue;
    }
    if (distance(mouth, 0.5 * (mouth_left + mouth_right)) > 0.001)
        mouth_contract_errors++;
    vector outer_left = mouth_left + outward * extension;
    vector outer_right = mouth_right + outward * extension;
    vector positions[] = array(mouth_left, outer_left, outer_right, mouth_right);
    int output_points[];
    foreach (vector position; positions)
        append(output_points, addpoint(0, position));
    int output_prim = addprim(0, "poly");
    foreach (int output_point; output_points) addvertex(0, output_prim, output_point);

    int jid = int(point(1, "junction_id", approach_point));
    int level = int(point(1, "road_level", approach_point));
    string junction_type = "none";
    foreach (int source_prim; source_boundaries)
    {
        if (int(prim(0, "junction_id", source_prim)) == jid &&
            int(prim(0, "road_level", source_prim)) == level)
        {
            junction_type = string(prim(0, "junction_type", source_prim));
            break;
        }
    }
    setprimattrib(0, "junction_id", output_prim, jid, "set");
    setprimattrib(0, "junction_type", output_prim, junction_type, "set");
    setprimattrib(0, "road_level", output_prim, level, "set");
    setprimattrib(0, "road_id", output_prim,
        int(point(1, "road_id", approach_point)), "set");
    setprimattrib(0, "segment_id", output_prim,
        int(point(1, "segment_id", approach_point)), "set");
    setprimattrib(0, "approach_id", output_prim,
        int(point(1, "approach_id", approach_point)), "set");
    setprimattrib(0, "junction_region_role", output_prim, "arm", "set");
    setprimattrib(0, "city_part", output_prim, "junction_surface_boundary", "set");
    setprimgroup(0, "junction_surface_boundary", output_prim, 1, "set");
    setprimgroup(0, "junction_surface_arm", output_prim, 1, "set");
    if (distance(mouth_left, outer_left) + 1e-4 < extension ||
        distance(mouth_right, outer_right) + 1e-4 < extension)
        extent_errors++;
    arm_count++;
}

for (int primitive = original_prims - 1; primitive >= 0; --primitive)
    removeprim(0, primitive, 0);
for (int point_number = original_points - 1; point_number >= 0; --point_number)
    removepoint(0, point_number);

setdetailattrib(0, "junction_surface_extension", extension, "set");
setdetailattrib(0, "junction_surface_core_count", core_count, "set");
setdetailattrib(0, "junction_surface_arm_count", arm_count, "set");
setdetailattrib(0, "junction_arm_extent_error_count", extent_errors, "set");
setdetailattrib(0, "junction_arm_mouth_contract_error_count", mouth_contract_errors, "set");
setdetailattrib(0, "junction_expected_approaches", len(approaches), "set");
setdetailattrib(0, "junction_actual_approaches", arm_count, "set");
if (arm_count != len(approaches) || extent_errors != 0 || mouth_contract_errors != 0)
    error(sprintf(
        "CityRoad V6 junction arms failed: expected=%d actual=%d extent=%d mouth=%d",
        len(approaches), arm_count, extent_errors, mouth_contract_errors));
'''


APPROACH_MARKINGS_V6 = r'''
// V6: rectangular bars anchored to exact fillet mouth-left/right endpoints.
function int inside_polygon(int geo; vector q; int pr)
{
    int pts[] = primpoints(geo, pr);
    int inside = 0;
    for (int i = 0, j = len(pts) - 1; i < len(pts); j = i++)
    {
        vector a = point(geo, "P", pts[i]);
        vector b = point(geo, "P", pts[j]);
        if ((a.z > q.z) == (b.z > q.z)) continue;
        float xhit = (b.x - a.x) * (q.z - a.z) / (b.z - a.z + 1e-20) + a.x;
        if (q.x < xhit) inside = !inside;
    }
    return inside;
}
function int inside_junction_surface(int geo; vector q; int junction_id; int road_level)
{
    foreach (int primitive; expandprimgroup(geo, "junction_surface_boundary"))
    {
        if (int(prim(geo, "junction_id", primitive)) != junction_id ||
            int(prim(geo, "road_level", primitive)) != road_level) continue;
        if (inside_polygon(geo, q, primitive)) return 1;
    }
    return 0;
}
function vector project_to_road(vector query; float height_offset)
{
    int surface_prim = -1;
    vector surface_uvw = 0;
    xyzdist(1, query, surface_prim, surface_uvw);
    if (surface_prim < 0) return query + set(0, height_offset, 0);
    vector position = primuv(1, "P", surface_prim, surface_uvw);
    vector normal = primuv(1, "N", surface_prim, surface_uvw);
    if (length2(normal) < 1e-8) normal = set(0, 1, 0);
    normal = normalize(normal);
    if (dot(normal, set(0, 1, 0)) < 0) normal *= -1;
    return position + normal * height_offset;
}
function int emit_quad_up(
    vector a; vector b; vector c; vector d;
    int marking_type; int road_id; int segment_id;
    int junction_id; int road_level; int approach_id;
    string material_path; string group_name)
{
    vector positions[] = array(a, b, c, d);
    if (dot(cross(b - a, c - a), set(0, 1, 0)) < 0)
        positions = array(a, d, c, b);
    int points[];
    vector uvs[] = array(
        set(0, 0, 0), set(1, 0, 0), set(1, 1, 0), set(0, 1, 0));
    foreach (int index; vector position; positions)
    {
        int point_number = addpoint(0, position);
        append(points, point_number);
        setpointattrib(0, "N", point_number, set(0, 1, 0), "set");
        setpointattrib(0, "Cd", point_number, set(0, 0, 0), "set");
        setpointattrib(0, "uv", point_number, uvs[index], "set");
    }
    int primitive = addprim(0, "poly", points[0], points[1], points[2], points[3]);
    setprimattrib(0, "marking_type", primitive, marking_type, "set");
    setprimattrib(0, "lane_index", primitive, -1, "set");
    setprimattrib(0, "road_id", primitive, road_id, "set");
    setprimattrib(0, "segment_id", primitive, segment_id, "set");
    setprimattrib(0, "junction_id", primitive, junction_id, "set");
    setprimattrib(0, "road_level", primitive, road_level, "set");
    setprimattrib(0, "approach_id", primitive, approach_id, "set");
    setprimattrib(0, "distance_along_road", primitive, 0.0, "set");
    setprimattrib(0, "city_part", primitive, "road_marking", "set");
    setprimattrib(0, "topology_piece_kind", primitive, "junction", "set");
    setprimattrib(0, "topology_piece_id", primitive, junction_id, "set");
    if (len(material_path) > 0)
        setprimattrib(0, "unity_material", primitive, material_path, "set");
    setprimgroup(0, "road_markings", primitive, 1, "set");
    setprimgroup(0, group_name, primitive, 1, "set");
    return primitive;
}

for (int primitive = nprimitives(0) - 1; primitive >= 0; --primitive)
{
    if (inprimgroup(0, "road_marking_crosswalk", primitive) ||
        inprimgroup(0, "road_marking_stopline", primitive) ||
        int(prim(0, "marking_type", primitive)) == 3 ||
        int(prim(0, "marking_type", primitive)) == 4)
        removeprim(0, primitive, 1);
}

addpointattrib(0, "N", set(0, 1, 0));
addpointattrib(0, "Cd", set(0, 0, 0));
addpointattrib(0, "uv", set(0, 0, 0));
addprimattrib(0, "marking_type", -1);
addprimattrib(0, "lane_index", -1);
addprimattrib(0, "road_id", -1);
addprimattrib(0, "segment_id", -1);
addprimattrib(0, "junction_id", -1);
addprimattrib(0, "road_level", 0);
addprimattrib(0, "approach_id", -1);
addprimattrib(0, "distance_along_road", 0.0);
addprimattrib(0, "city_part", "");
addprimattrib(0, "topology_piece_kind", "");
addprimattrib(0, "topology_piece_id", -1);
addprimattrib(0, "unity_material", "");

int approaches[] = expandpointgroup(2, "junction_approaches");
float depth = max(ch("../../crosswalk_depth"), 0.5);
float stripe_width = max(ch("../../crosswalk_stripe_width"), 0.05);
float stripe_gap = max(ch("../../crosswalk_stripe_gap"), 0.0);
float side_margin = max(ch("../../crosswalk_side_margin"), 0.0);
float setback = max(ch("../../crosswalk_setback"), 0.0);
float stop_width = max(ch("../../stop_line_width"), 0.05);
float stop_gap = max(ch("../../stop_line_gap"), 0.0);
float height_offset = max(ch("../../marking_height_offset"), 0.015);
string marking_material = chs("../../marking_unity_material");

int approach_count = 0;
int stop_count = 0;
int parallel_errors = 0;
int stop_orientation_errors = 0;
int coverage_errors = 0;
int alignment_errors = 0;
int emitted_crosswalk_prims = 0;
float max_alignment_error = 0.0;

if (chi("../../enable_road_markings") && chi("../../enable_crosswalks"))
foreach (int approach_point; approaches)
{
    vector outward = point(2, "approach_direction", approach_point);
    outward = normalize(set(outward.x, 0.0, outward.z));
    vector mouth_left = point(2, "approach_mouth_left", approach_point);
    vector mouth_right = point(2, "approach_mouth_right", approach_point);
    vector lateral = mouth_right - mouth_left;
    float full_span = length(lateral);
    if (length2(outward) < 1e-8 || full_span < 1e-5) continue;
    vector side = lateral / full_span;
    float margin = min(side_margin, max(full_span * 0.5 - 0.25, 0.0));
    vector span_left = mouth_left + side * margin;
    vector span_right = mouth_right - side * margin;
    float usable_span = distance(span_left, span_right);
    vector near_left = span_left + outward * setback;
    vector near_right = span_right + outward * setback;
    int road_id = int(point(2, "road_id", approach_point));
    int segment_id = int(point(2, "segment_id", approach_point));
    int junction_id = int(point(2, "junction_id", approach_point));
    int road_level = int(point(2, "road_level", approach_point));
    int approach_id = int(point(2, "approach_id", approach_point));

    float perpendicular_error = abs(dot(side, outward));
    float left_error = distance(near_left, mouth_left + side * margin + outward * setback);
    float right_error = distance(near_right, mouth_right - side * margin + outward * setback);
    float alignment_error = max(perpendicular_error, max(left_error, right_error));
    max_alignment_error = max(max_alignment_error, alignment_error);
    if (perpendicular_error > 0.001 || left_error > 0.001 || right_error > 0.001)
        alignment_errors++;

    float cursor = 0.0;
    while (cursor + stripe_width <= usable_span + 1e-4)
    {
        vector stripe_center = near_left
            + side * (cursor + stripe_width * 0.5)
            + outward * depth * 0.5;
        vector long_axis = outward * depth * 0.5;
        vector short_axis = side * stripe_width * 0.5;
        vector raw[] = array(
            stripe_center - long_axis - short_axis,
            stripe_center + long_axis - short_axis,
            stripe_center + long_axis + short_axis,
            stripe_center - long_axis + short_axis);
        vector projected[];
        foreach (vector position; raw)
        {
            if (!inside_junction_surface(3, position, junction_id, road_level))
                coverage_errors++;
            append(projected, project_to_road(position, height_offset));
        }
        emit_quad_up(
            projected[0], projected[1], projected[2], projected[3],
            3, road_id, segment_id, junction_id, road_level, approach_id,
            marking_material, "road_marking_crosswalk");
        if (abs(dot(normalize(long_axis), outward)) < 0.999)
            parallel_errors++;
        emitted_crosswalk_prims++;
        cursor += stripe_width + stripe_gap;
    }

    vector stop_left = span_left + outward * (setback + depth + stop_gap);
    vector stop_right = span_right + outward * (setback + depth + stop_gap);
    vector stop_center = 0.5 * (stop_left + stop_right) + outward * stop_width * 0.5;
    vector stop_short = outward * stop_width * 0.5;
    vector stop_long = 0.5 * (stop_right - stop_left);
    vector raw_stop[] = array(
        stop_center - stop_short - stop_long,
        stop_center + stop_short - stop_long,
        stop_center + stop_short + stop_long,
        stop_center - stop_short + stop_long);
    vector projected_stop[];
    foreach (vector position; raw_stop)
    {
        if (!inside_junction_surface(3, position, junction_id, road_level))
            coverage_errors++;
        append(projected_stop, project_to_road(position, height_offset));
    }
    emit_quad_up(
        projected_stop[0], projected_stop[1], projected_stop[2], projected_stop[3],
        4, road_id, segment_id, junction_id, road_level, approach_id,
        marking_material, "road_marking_stopline");
    if (abs(dot(normalize(stop_long), outward)) > 0.001)
        stop_orientation_errors++;
    stop_count++;
    approach_count++;
}

int expected =
    chi("../../enable_road_markings") && chi("../../enable_crosswalks")
        ? len(approaches) : 0;
setdetailattrib(0, "crosswalk_expected_approach_count", expected, "set");
setdetailattrib(0, "crosswalk_actual_approach_count", approach_count, "set");
setdetailattrib(0, "crosswalk_primitive_count", emitted_crosswalk_prims, "set");
setdetailattrib(0, "stop_line_actual_count", stop_count, "set");
setdetailattrib(0, "crosswalk_bar_parallel_error_count", parallel_errors, "set");
setdetailattrib(0, "crosswalk_orientation_error_count", parallel_errors, "set");
setdetailattrib(0, "crosswalk_mouth_alignment_error_count", alignment_errors, "set");
setdetailattrib(0, "crosswalk_mouth_max_alignment_error", max_alignment_error, "set");
setdetailattrib(0, "stop_line_orientation_error_count", stop_orientation_errors, "set");
setdetailattrib(0, "junction_marking_coverage_error_count", coverage_errors, "set");
setdetailattrib(0, "junction_arm_extent_error_count",
    int(detail(3, "junction_arm_extent_error_count", 0)), "set");
setdetailattrib(0, "junction_corridor_overlap_count", 0, "set");
setdetailattrib(0, "junction_corridor_gap_count", 0, "set");
if (approach_count != expected || stop_count != expected ||
    parallel_errors != 0 || stop_orientation_errors != 0 ||
    coverage_errors != 0 || alignment_errors != 0)
    error(sprintf(
        "CityRoad V6 markings failed: expected=%d crosswalks=%d stops=%d parallel=%d stop=%d coverage=%d alignment=%d",
        expected, approach_count, stop_count, parallel_errors,
        stop_orientation_errors, coverage_errors, alignment_errors));
'''


ROAD_ROUND_V6 = r'''
float boundary_corner_radius = max(0.0, ch("../../junction_corner_radius"));
float spacing = max(0.05, ch("../../junction_sample_spacing"));
int original_prim_count = nprimitives(0);
int rounded_corner_count = 0;
int radius_clamp_count = 0;
int max_segment_count = 0;
int collinear_point_prune_count = 0;
int true_arc_count = 0;
int inner_chamfer_fallback_count = 0;
float minimum_inner_radius = 1e18;

for (int pr = 0; pr < original_prim_count; ++pr)
{
    int vertices[] = primvertices(0, pr);
    int source_count = len(vertices);
    if (source_count < 2) continue;
    int closed = primintrinsic(0, "closed", pr);
    float source_road_width = hasprimattrib(0, "road_width")
        ? float(prim(0, "road_width", pr)) : ch("../../default_road_width");
    // 公共半径表示可见内侧半径；中心线半径需加半路宽。
    float requested_radius = boundary_corner_radius + 0.5 * source_road_width;
    vector source_positions[];
    resize(source_positions, source_count);
    for (int i = 0; i < source_count; ++i)
        source_positions[i] = point(0, "P", vertexpoint(0, vertices[i]));

    // Adaptive resampling may leave many perfectly collinear points beside a
    // control corner.  Remove only near-zero-turn points before measuring the
    // corner clearance, so the radius no longer depends on sample phase.
    vector positions[];
    for (int i = 0; i < source_count; ++i)
    {
        if (!closed && (i == 0 || i == source_count - 1))
        {
            append(positions, source_positions[i]);
            continue;
        }
        vector previous =
            source_positions[(i - 1 + source_count) % source_count];
        vector current = source_positions[i];
        vector next = source_positions[(i + 1) % source_count];
        vector incoming = previous - current;
        vector outgoing = next - current;
        float incoming_length = length(incoming);
        float outgoing_length = length(outgoing);
        if (incoming_length < 1e-5 || outgoing_length < 1e-5)
        {
            collinear_point_prune_count++;
            continue;
        }
        float angle = acos(clamp(
            dot(incoming / incoming_length, outgoing / outgoing_length),
            -1.0, 1.0));
        float turn = M_PI - angle;
        if (abs(turn) < radians(0.10))
        {
            collinear_point_prune_count++;
            continue;
        }
        append(positions, current);
    }
    int count = len(positions);
    if (count < 2) continue;

    int new_prim = addprim(0, "poly");
    setprimintrinsic(0, "closed", new_prim, closed, "set");
    if (hasprimattrib(0, "road_id"))
        setprimattrib(0, "road_id", new_prim, int(prim(0, "road_id", pr)), "set");
    if (hasprimattrib(0, "road_level"))
        setprimattrib(0, "road_level", new_prim, int(prim(0, "road_level", pr)), "set");
    if (hasprimattrib(0, "road_width"))
        setprimattrib(0, "road_width", new_prim, float(prim(0, "road_width", pr)), "set");
    if (hasprimattrib(0, "allow_junction"))
        setprimattrib(0, "allow_junction", new_prim, int(prim(0, "allow_junction", pr)), "set");
    if (hasprimattrib(0, "segment_id"))
        setprimattrib(0, "segment_id", new_prim, int(prim(0, "segment_id", pr)), "set");

    for (int i = 0; i < count; ++i)
    {
        if (!closed && (i == 0 || i == count - 1))
        {
            addvertex(0, new_prim, addpoint(0, positions[i]));
            continue;
        }
        vector previous = positions[(i - 1 + count) % count];
        vector current = positions[i];
        vector next = positions[(i + 1) % count];
        vector to_previous = previous - current;
        vector to_next = next - current;
        float previous_length = length(to_previous);
        float next_length = length(to_next);
        vector previous_direction = previous_length > 1e-5
            ? to_previous / previous_length : 0;
        vector next_direction = next_length > 1e-5
            ? to_next / next_length : 0;
        float angle = acos(clamp(dot(previous_direction, next_direction), -1.0, 1.0));
        if (requested_radius <= 1e-5 || previous_length <= 1e-5 ||
            next_length <= 1e-5 || angle > radians(175.0) || angle < radians(10.0))
        {
            addvertex(0, new_prim, addpoint(0, current));
            continue;
        }
        float tangent_scale = tan(angle * 0.5);
        float tangent_distance = requested_radius / max(tangent_scale, 1e-4);
        float half_width = 0.5 * source_road_width;
        float minimum_center_radius = half_width + max(boundary_corner_radius, 0.05);
        float minimum_safe_tangent = minimum_center_radius / max(tangent_scale, 1e-4);
        float branch_limit = min(previous_length, next_length);
        float max_tangent = 0.45 * branch_limit;
        // A centreline radius smaller than half the road width makes the inner
        // offset reverse and produces the triangular overlap fan seen in Unity.
        // Expand only as far as required for a positive inner radius, while
        // retaining ten percent of each adjacent branch as a safety budget.
        if (max_tangent < minimum_safe_tangent &&
            minimum_safe_tangent <= 0.90 * branch_limit)
            max_tangent = minimum_safe_tangent;
        if (tangent_distance > max_tangent)
        {
            tangent_distance = max_tangent;
            radius_clamp_count++;
        }
        vector start = current + previous_direction * tangent_distance;
        vector end = current + next_direction * tangent_distance;
        float effective_radius = tangent_distance * tangent_scale;
        float inner_radius = effective_radius - half_width;
        if (inner_radius < 0.05)
        {
            // The local branches are physically too short for a non-inverting
            // offset.  A two-point chamfer is the safe low-poly fallback.
            addvertex(0, new_prim, addpoint(0, start));
            addvertex(0, new_prim, addpoint(0, end));
            inner_chamfer_fallback_count++;
            continue;
        }
        vector bisector = normalize(previous_direction + next_direction);
        float sin_half = max(sin(angle * 0.5), 1e-4);
        vector arc_center = current + bisector * (effective_radius / sin_half);
        vector radial_start = normalize(start - arc_center);
        vector radial_end = normalize(end - arc_center);
        float sweep = acos(clamp(dot(radial_start, radial_end), -1.0, 1.0));
        vector radial_orthogonal = radial_end
            - radial_start * dot(radial_start, radial_end);
        if (length2(radial_orthogonal) < 1e-8)
        {
            addvertex(0, new_prim, addpoint(0, start));
            addvertex(0, new_prim, addpoint(0, end));
            inner_chamfer_fallback_count++;
            continue;
        }
        radial_orthogonal = normalize(radial_orthogonal);
        float estimated_arc_length = sweep * effective_radius;
        int segment_count = clamp(
            int(ceil(estimated_arc_length / spacing)), 2, 4);
        max_segment_count = max(max_segment_count, segment_count);
        rounded_corner_count++;
        true_arc_count++;
        minimum_inner_radius = min(minimum_inner_radius, inner_radius);
        for (int segment = 0; segment <= segment_count; ++segment)
        {
            float t = float(segment) / float(segment_count);
            vector radial = radial_start * cos(sweep * t)
                + radial_orthogonal * sin(sweep * t);
            vector rounded_position = arc_center + radial * effective_radius;
            addvertex(0, new_prim, addpoint(0, rounded_position));
        }
    }
}
for (int pr = original_prim_count - 1; pr >= 0; --pr)
    removeprim(0, pr, 1);
setdetailattrib(0, "rounded_corner_count", rounded_corner_count, "set");
setdetailattrib(0, "rounded_corner_radius_clamp_count", radius_clamp_count, "set");
setdetailattrib(0, "rounded_corner_max_segment_count", max_segment_count, "set");
setdetailattrib(0, "rounded_collinear_point_prune_count",
    collinear_point_prune_count, "set");
setdetailattrib(0, "rounded_true_arc_count", true_arc_count, "set");
setdetailattrib(0, "rounded_inner_chamfer_fallback_count",
    inner_chamfer_fallback_count, "set");
setdetailattrib(0, "rounded_minimum_inner_radius",
    true_arc_count > 0 ? minimum_inner_radius : 0.0, "set");
if (max_segment_count > 4)
    error(sprintf("CityRoad V6.2 road corner segment overflow: %d", max_segment_count));
'''


NODE_SPECS = {
    "JUNCTION_BUILD_PATCHES": (
        "// Only accept graph segments that actually meet the classified junction.",
        JUNCTION_BUILD_V6,
        "V6.1：按语义支路计算安全长度；同一 Junction 共用一个半径，每角最多5点/4段。",
    ),
    "CITYROAD_JUNCTION_APPROACH_METADATA": (
        "// V6: one point per exact junction mouth.",
        APPROACH_METADATA_V6,
        "V6.1：一入口一点；传递精确 Mouth、切点及统一有效圆角半径。",
    ),
    "CITYROAD_BUILD_JUNCTION_SURFACE_BOUNDARY_V5": (
        "float half_width=max(",
        JUNCTION_SURFACE_BOUNDARY_V6,
        "V6：Junction Core 与辅助 Arm 共用精确 Mouth，禁止独立扩宽造成接缝。",
    ),
    "CITYROAD_BUILD_APPROACH_MARKINGS_V5": (
        "float half_span=max(road_width*0.5-side_margin,0.25);",
        APPROACH_MARKINGS_V6,
        "V6：直条斑马线和停止线严格锚定左右 Mouth 切点；不按圆弧裁条。",
    ),
    "ROAD_ROUND_CENTERLINE_CORNERS": (
        "float boundary_corner_radius = max(0.0, ch(\"../../junction_corner_radius\"));",
        ROAD_ROUND_V6,
        "V6.1：先剔除近共线采样点，再计算普通道路圆角；最多5点/4段。",
    ),
}

# Keep the V6.2 road-corner annotation explicit even when this migration file
# passes through a Windows console with a legacy code page.
_road_signature, _road_snippet, _ = NODE_SPECS["ROAD_ROUND_CENTERLINE_CORNERS"]
NODE_SPECS["ROAD_ROUND_CENTERLINE_CORNERS"] = (
    _road_signature,
    _road_snippet,
    "V6.2：普通弯道使用真实圆心圆弧；保证内侧偏移不反转，空间不足时退化为两点倒角；最多 5 点 4 段。",
)


def _require_node(core: hou.Node, name: str) -> hou.Node:
    node = core.node(name)
    if node is None:
        raise RuntimeError(f"Missing required CityRoad node: {core.path()}/{name}")
    return node


def _validate_live_scene() -> tuple[hou.Node, hou.Node, hou.HDADefinition]:
    asset = hou.node(ASSET_PATH)
    if asset is None or asset.type().name() != EXPECTED_TYPE:
        raise RuntimeError(f"Expected live {EXPECTED_TYPE} at {ASSET_PATH}")
    definition = asset.type().definition()
    if definition is None:
        raise RuntimeError("CityRoad node has no HDA definition")
    normalized = definition.libraryFilePath().replace("\\", "/")
    if not normalized.endswith(EXPECTED_HDA_SUFFIX):
        raise RuntimeError(f"Unexpected CityRoad definition: {normalized}")
    core = asset.node("CityRoadCore")
    if core is None:
        raise RuntimeError("Missing CityRoadCore")
    return asset, core, definition


def _backup_definition(definition: hou.HDADefinition) -> Path:
    hip_dir = Path(hou.hipFile.path()).resolve().parent
    backup_dir = hip_dir / "backups"
    backup_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    destination = backup_dir / f"CityRoad_before_corner_alignment_v6_{stamp}.hda"
    shutil.copy2(Path(definition.libraryFilePath()), destination)
    return destination


def apply_live_patch(save: bool = True, create_backup: bool = True) -> dict[str, object]:
    asset, core, definition = _validate_live_scene()
    if asset.isLockedHDA():
        asset.allowEditingOfContents(propagate=True)

    nodes: dict[str, hou.Node] = {}
    for name, (signature, snippet, comment) in NODE_SPECS.items():
        node = _require_node(core, name)
        current = node.parm("snippet").eval()
        if signature not in current and snippet.strip() != current.strip():
            raise RuntimeError(f"{name} signature changed; refusing blind V6 patch")
        nodes[name] = node

    polyframe = _require_node(core, "ROAD_POLYFRAME")
    rounded = nodes["ROAD_ROUND_CENTERLINE_CORNERS"]
    current_input = polyframe.input(0)
    if current_input is not None and current_input.name() not in {
        "ROAD_ADAPTIVE_RESAMPLE", "ROAD_ROUND_CENTERLINE_CORNERS"
    }:
        raise RuntimeError(
            f"ROAD_POLYFRAME input changed to {current_input.path()}; refusing blind rewire")

    side_material = _require_node(core, "CITYROAD_SIDE_MATERIAL_ASSIGN")
    side_stats = _require_node(core, "CURB_SIDEWALK_STATS")
    side_input = side_material.input(0)
    if side_input is not None and side_input.name() not in {
        "IN_LAB_SIDEWALK_CANDIDATE", "CURB_SIDEWALK_STATS"
    }:
        raise RuntimeError(
            f"CITYROAD_SIDE_MATERIAL_ASSIGN input changed to {side_input.path()}; "
            "refusing blind rewire")

    backup_path = _backup_definition(definition) if create_backup else None
    with hou.undos.group("CityRoad V6 corner and crosswalk alignment"):
        for name, (_, snippet, comment) in NODE_SPECS.items():
            nodes[name].parm("snippet").set(snippet)
            nodes[name].setComment(comment)
            nodes[name].setGenericFlag(hou.nodeFlag.DisplayComment, True)
        polyframe.setInput(0, rounded)
        polyframe.setComment(
            "V6：路面、碰撞、标线统一消费圆角后的中心线；每角最多4段。")
        polyframe.setGenericFlag(hou.nodeFlag.DisplayComment, True)
        curb = _require_node(core, "CITYROAD_JUNCTION_CURB_SIDEWALK_V4")
        curb.setComment(
            "V6：直接沿 Junction 低模边界生成路缘/人行道；Mouth 边保持开放。")
        curb.setGenericFlag(hou.nodeFlag.DisplayComment, True)

        # The old TutorialLab candidate rebuilt a separate square block boundary.
        # Route the production SidewalkCurb output through the V4 corridor+junction
        # chain so road, curb and sidewalk consume the same five-point corner arc.
        side_material.setInput(0, side_stats)
        side_material.setComment(
            "V6.1：生产输出直接使用 V4 路段+路口路缘/人行道；不再回到独立直角街区边界。")
        side_material.setGenericFlag(hou.nodeFlag.DisplayComment, True)

    outputs = [
        _require_node(core, "OUT_ROAD_SURFACE"),
        _require_node(core, "OUT_SIDEWALK_CURB"),
        _require_node(core, "OUT_ROAD_MARKINGS"),
    ]
    errors = []
    for output in outputs:
        output.cook(force=True)
        errors.extend(output.errors())
    if errors:
        raise RuntimeError("CityRoad V6 cook failed: " + " | ".join(errors))
    if save:
        definition.updateFromNode(asset)
        hou.hipFile.save()
    return {
        "asset": asset.path(),
        "definition": definition.libraryFilePath(),
        "backup": str(backup_path) if backup_path else None,
        "hip": hou.hipFile.path(),
        "saved": save,
    }


if __name__ == "__main__":
    print(apply_live_patch())
