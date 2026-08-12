"""Incremental CityRoad V18 Cook-optimization patch.

The unlocked Live network is the only implementation source.  This patch is
hash/marker guarded, idempotent, defaults to ``save=False`` and rolls back its
node/snippet/connection changes when any post-patch Cook check fails.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

import hou


ASSET_PATH = "/obj/CityRoad_DEV"
CORE_NAME = "CityRoadCore"
ASSET_TYPE = "pcgbike::CityRoad::1.0"
MARKER = "CITYROAD_COOK_OPTIMIZATION_V18"
EXPECTED = {
    "GRAPH_CLASSIFY_JUNCTIONS": "767b145b2a76bc0cde75954cbdf23cf34b499d71baccdc3dd295b85c85ff9cc1",
    "CITYROAD_TOPOLOGY_CLASSIFY_ROAD": "47f364aaa0efa51c7d9c28a9428efc6e2d0f1c344d34ddec1f75eab7fbc3c9e4",
    "CITYROAD_BUILD_STATIC_MARKING_MESH": "8093f281471e71e1977a4813878fdbf3add4c183f23945fc853bfaff49299450",
    "CITYROAD_STREET_BUILD_LAMPS_V1": "d0a6c749708f89f8a891028df6c04d78756435b82736b3b395fb3964fe42e36b",
    "CITYROAD_STREET_BUILD_TREES_V1": "9341c33bd078bbf77b91d7e3e4a50f88b7d314f40ec0a5eb44ce9ccc3989fb1d",
}


SEGMENT_INDEX_VEX = r'''// CITYROAD_COOK_OPTIMIZATION_V18
// One compact point per sampled XZ segment.  Point numbers are deterministic:
// source primitive order, then local segment order.
int original_points = npoints(0);
int original_primitives = nprimitives(0);
float max_half_length = 0.0;
float max_width = 0.1;
int segment_uid = 0;
for (int primitive = 0; primitive < original_primitives; ++primitive)
{
    int vertices[] = primpoints(0, primitive);
    int segment_count = max(len(vertices) - 1, 0);
    int road_id = int(prim(0, "road_id", primitive));
    int road_level = int(prim(0, "road_level", primitive));
    float width = max(float(prim(0, "road_width", primitive)), 0.1);
    int allow_junction = hasprimattrib(0, "allow_junction")
        ? int(prim(0, "allow_junction", primitive)) : 1;
    max_width = max(max_width, width);
    for (int local = 0; local < segment_count; ++local)
    {
        vector a = point(0, "P", vertices[local]);
        vector b = point(0, "P", vertices[local + 1]);
        vector flat_a = set(a.x, 0, a.z);
        vector flat_b = set(b.x, 0, b.z);
        float half_length = 0.5 * distance(flat_a, flat_b);
        int index_point = addpoint(0, 0.5 * (a + b));
        setpointattrib(0, "segment_uid", index_point, segment_uid++, "set");
        setpointattrib(0, "source_primitive", index_point, primitive, "set");
        setpointattrib(0, "segment_local", index_point, local, "set");
        setpointattrib(0, "segment_count", index_point, segment_count, "set");
        setpointattrib(0, "road_id", index_point, road_id, "set");
        setpointattrib(0, "road_level", index_point, road_level, "set");
        setpointattrib(0, "road_width", index_point, width, "set");
        setpointattrib(0, "allow_junction", index_point, allow_junction, "set");
        setpointattrib(0, "segment_a", index_point, a, "set");
        setpointattrib(0, "segment_b", index_point, b, "set");
        setpointattrib(0, "half_length", index_point, half_length, "set");
        setpointattrib(0, "pscale", index_point, half_length, "set");
        max_half_length = max(max_half_length, half_length);
    }
}
for (int primitive = original_primitives - 1; primitive >= 0; --primitive)
    removeprim(0, primitive, 0);
for (int point_number = original_points - 1; point_number >= 0; --point_number)
    removepoint(0, point_number);
setdetailattrib(0, "segment_index_count", segment_uid, "set");
setdetailattrib(0, "segment_index_max_half_length", max_half_length, "set");
setdetailattrib(0, "segment_index_max_width", max_width, "set");
setdetailattrib(0, "cityroad_segment_index_version", "V2", "set");
'''


JUNCTION_INDEX_VEX = r'''// CITYROAD_COOK_OPTIMIZATION_V18_APPROACH_TABLE
// Keep all approaches. Stable ids are independent of point/Cook order.
int approaches[] = expandpointgroup(0, "junction_approaches");
string keys[];
foreach (int point_number; approaches)
{
    vector center = point(0, "junction_center", point_number);
    append(keys, sprintf("%+011d_%+015d_%+015d_%+011d_%+011d_%+011d",
        int(point(0, "road_level", point_number)),
        int(rint(center.x * 10000.0)), int(rint(center.z * 10000.0)),
        int(point(0, "junction_id", point_number)),
        int(point(0, "road_id", point_number)),
        int(point(0, "approach_id", point_number))));
}
int order[] = argsort(keys);
string junction_keys[];
foreach (int stable_approach_id; int source_index; order)
{
    int point_number = approaches[source_index];
    vector center = point(0, "junction_center", point_number);
    string junction_key = sprintf("%+011d_%+015d_%+015d_%+011d",
        int(point(0, "road_level", point_number)),
        int(rint(center.x * 10000.0)), int(rint(center.z * 10000.0)),
        int(point(0, "junction_id", point_number)));
    int stable_junction_id = find(junction_keys, junction_key);
    if (stable_junction_id < 0)
    {
        append(junction_keys, junction_key);
        stable_junction_id = len(junction_keys) - 1;
    }
    setpointattrib(0, "stable_approach_id", point_number,
        stable_approach_id, "set");
    setpointattrib(0, "stable_junction_id", point_number,
        stable_junction_id, "set");
}
setdetailattrib(0, "junction_index_count", len(junction_keys), "set");
setdetailattrib(0, "approach_index_count", len(approaches), "set");
setdetailattrib(0, "cityroad_junction_approach_index_version", "V2", "set");
'''


JUNCTION_CENTER_VEX = r'''// CITYROAD_COOK_OPTIMIZATION_V18_JUNCTION_CENTER_INDEX
int original_count = npoints(0);
int approaches[] = expandpointgroup(0, "junction_approaches");
string keys[];
int sources[];
foreach (int point_number; approaches)
{
    vector center = point(0, "junction_center", point_number);
    string key = sprintf("%+011d_%+015d_%+015d_%+011d",
        int(point(0, "road_level", point_number)),
        int(rint(center.x * 10000.0)), int(rint(center.z * 10000.0)),
        int(point(0, "junction_id", point_number)));
    if (find(keys, key) < 0)
    {
        append(keys, key);
        append(sources, point_number);
    }
}
int order[] = argsort(keys);
foreach (int stable_id; int key_index; order)
{
    int source = sources[key_index];
    vector center = point(0, "junction_center", source);
    int output = addpoint(0, center);
    setpointattrib(0, "junction_id", output,
        int(point(0, "junction_id", source)), "set");
    setpointattrib(0, "stable_junction_id", output, stable_id, "set");
    setpointattrib(0, "road_level", output,
        int(point(0, "road_level", source)), "set");
    setpointgroup(0, "junction_points", output, 1, "set");
}
for (int point_number = original_count - 1; point_number >= 0; --point_number)
    removepoint(0, point_number);
setdetailattrib(0, "junction_center_index_count", len(order), "set");
setdetailattrib(0, "cityroad_junction_center_index_version", "V2", "set");
'''


CORRIDOR_INDEX_VEX = r'''// CITYROAD_COOK_OPTIMIZATION_V18_CORRIDOR_INTERVALS
function float cross_xz(vector a; vector b) { return a.x*b.z-a.z*b.x; }
// Associate an interval boundary with the same road's stable Approach once.
function int endpoint_approach(
    int geometry; vector position; int level; int road_id;
    float search_radius; export vector road_tangent)
{
    int candidates[] = pcfind(geometry, "P", position, search_radius, 16);
    float best_distance = 1e18;
    int best_point = -1;
    foreach (int point_number; candidates)
    {
        if (int(point(geometry, "road_level", point_number)) != level) continue;
        if (int(point(geometry, "road_id", point_number)) != road_id) continue;
        float candidate_distance = distance(
            position, point(geometry, "P", point_number));
        if (candidate_distance < best_distance)
        {
            best_distance = candidate_distance;
            best_point = point_number;
        }
    }
    road_tangent = {0.0, 0.0, 0.0};
    if (best_point >= 0)
        road_tangent = normalize(vector(
            point(geometry, "approach_direction", best_point)));
    return best_point;
}
function int inside_polygon(int geometry; vector position; int primitive)
{
    int points[] = primpoints(geometry, primitive);
    int inside = 0;
    for (int i = 0; i < len(points); ++i)
    {
        vector a = point(geometry, "P", points[i]);
        vector b = point(geometry, "P", points[(i + 1) % len(points)]);
        if (((a.z > position.z) != (b.z > position.z))
            && position.x < (b.x - a.x) * (position.z - a.z)
                / (b.z - a.z + 1e-20) + a.x)
            inside = !inside;
    }
    return inside;
}
int original_points = npoints(0);
int original_primitives = nprimitives(0);
int corridor_uid = 0;
int source_segment_count = 0;
for (int primitive = 0; primitive < original_primitives; ++primitive)
{
    int source_points[] = primpoints(0, primitive);
    int closed = int(primintrinsic(0, "closed", primitive));
    int segment_count = closed ? len(source_points) : max(len(source_points) - 1, 0);
    int road_level = int(prim(0, "road_level", primitive));
    int road_id = int(prim(0, "road_id", primitive));
    int segment_id = int(prim(0, "segment_id", primitive));
    float road_width = max(float(prim(0, "road_width", primitive)), 0.1);
    for (int local = 0; local < segment_count; ++local)
    {
        source_segment_count++;
        vector a = point(0, "P", source_points[local]);
        vector b = point(0, "P", source_points[(local + 1) % len(source_points)]);
        vector segment = b - a;
        float segment_length = length(segment);
        if (segment_length < 1e-6) continue;
        float cuts[] = array(0.0, 1.0);
        int boundary_hit = 0;
        for (int junction = 0; junction < nprimitives(1); ++junction)
        {
            if (int(prim(1, "road_level", junction)) != road_level) continue;
            int boundary[] = primpoints(1, junction);
            for (int edge = 0; edge < len(boundary); ++edge)
            {
                vector c = point(1, "P", boundary[edge]);
                vector d = point(1, "P", boundary[(edge + 1) % len(boundary)]);
                vector boundary_edge = d - c;
                float denominator = cross_xz(segment, boundary_edge);
                if (abs(denominator) < 1e-8) continue;
                float t = cross_xz(c - a, boundary_edge) / denominator;
                float u = cross_xz(c - a, segment) / denominator;
                if (t > 1e-5 && t < 0.99999 && u > -1e-5 && u < 1.00001)
                {
                    append(cuts, t);
                    boundary_hit = 1;
                }
            }
        }
        cuts = sort(cuts);
        float unique_cuts[];
        foreach (float cut; cuts)
            if (len(unique_cuts) == 0 || abs(cut - unique_cuts[-1]) > 1e-5)
                append(unique_cuts, cut);
        int emitted_for_segment = 0;
        for (int interval = 0; interval < len(unique_cuts) - 1; ++interval)
        {
            float t0 = unique_cuts[interval];
            float t1 = unique_cuts[interval + 1];
            if (t1 - t0 < 1e-6) continue;
            vector midpoint = a + segment * (0.5 * (t0 + t1));
            int inside = 0;
            for (int junction = 0; junction < nprimitives(1); ++junction)
                if (int(prim(1, "road_level", junction)) == road_level
                    && inside_polygon(1, midpoint, junction))
                {
                    inside = 1;
                    break;
                }
            if (inside) continue;
            vector start_position = a + segment * t0;
            vector end_position = a + segment * t1;
            vector start_tangent = normalize(segment);
            vector end_tangent = start_tangent;
            int start_approach = -1;
            int end_approach = -1;
            int start_boundary = t0 > 1e-5;
            int end_boundary = t1 < 0.99999;
            float search_radius = max(road_width * 2.0, 32.0);
            if (start_boundary)
                start_approach = endpoint_approach(
                    2, start_position, road_level, road_id,
                    search_radius, start_tangent);
            if (end_boundary)
                end_approach = endpoint_approach(
                    2, end_position, road_level, road_id,
                    search_radius, end_tangent);
            int output = addpoint(0, midpoint);
            setpointattrib(0, "corridor_id", output, corridor_uid++, "set");
            setpointattrib(0, "source_primitive", output, primitive, "set");
            setpointattrib(0, "source_segment", output, local, "set");
            setpointattrib(0, "interval_order", output, emitted_for_segment++, "set");
            setpointattrib(0, "interval_start", output, t0, "set");
            setpointattrib(0, "interval_end", output, t1, "set");
            setpointattrib(0, "segment_a", output, a, "set");
            setpointattrib(0, "segment_b", output, b, "set");
            setpointattrib(0, "segment_length", output, segment_length, "set");
            setpointattrib(0, "boundary_hit", output, boundary_hit, "set");
            setpointattrib(0, "interval_start_boundary", output, start_boundary, "set");
            setpointattrib(0, "interval_end_boundary", output, end_boundary, "set");
            setpointattrib(0, "interval_start_approach", output, start_approach, "set");
            setpointattrib(0, "interval_end_approach", output, end_approach, "set");
            setpointattrib(0, "interval_start_tangent", output, start_tangent, "set");
            setpointattrib(0, "interval_end_tangent", output, end_tangent, "set");
            setpointattrib(0, "road_id", output, road_id, "set");
            setpointattrib(0, "segment_id", output, segment_id, "set");
            setpointattrib(0, "road_level", output, road_level, "set");
            setpointattrib(0, "road_width", output, road_width, "set");
        }
    }
}
for (int primitive = original_primitives - 1; primitive >= 0; --primitive)
    removeprim(0, primitive, 0);
for (int point_number = original_points - 1; point_number >= 0; --point_number)
    removepoint(0, point_number);
setdetailattrib(0, "corridor_interval_count", corridor_uid, "set");
setdetailattrib(0, "corridor_source_segment_count", source_segment_count, "set");
setdetailattrib(0, "cityroad_corridor_interval_version", "V2", "set");
'''


GRAPH_V2 = r'''// CITYROAD_COOK_OPTIMIZATION_V18
// V2 broad phase: pcfind over segment midpoints; exact XZ tests are unchanged.
float index_max_half = max(float(detail(1, "segment_index_max_half_length", 0)), 0.0);
float index_max_width = max(float(detail(1, "segment_index_max_width", 0)), 0.1);
int broadphase_candidates = 0;
int exact_tests = 0;
for (int a = 0; a < original_prims; ++a)
{
    if (hasprimattrib(0, "allow_junction") && !int(prim(0, "allow_junction", a))) continue;
    int level_a = int(prim(0, "road_level", a));
    int road_a = int(prim(0, "road_id", a));
    float width_a = max(float(prim(0, "road_width", a)), 0.1);
    int pts_a[] = primpoints(0, a);
    string test_keys[];
    int test_segments_a[];
    int test_candidates[];
    for (int ia = 0; ia < len(pts_a) - 1; ++ia)
    {
        vector A = point(0, "P", pts_a[ia]);
        vector B = point(0, "P", pts_a[ia + 1]);
        vector midpoint = 0.5 * (A + B);
        float half_a = 0.5 * distance(set(A.x, 0, A.z), set(B.x, 0, B.z));
        float broad_radius = half_a + index_max_half
            + max(detect, 0.5 * (width_a + index_max_width) + corner + 0.25);
        int candidates[] = pcfind(1, "P", midpoint, broad_radius, 4096);
        sort(candidates);
        foreach (int candidate; candidates)
        {
            broadphase_candidates++;
            int b = int(point(1, "source_primitive", candidate));
            int ib = int(point(1, "segment_local", candidate));
            if (b <= a || int(point(1, "road_level", candidate)) != level_a ||
                !int(point(1, "allow_junction", candidate))) continue;
            string key = sprintf("%+011d_%+011d_%+011d", b, ia, ib);
            if (find(test_keys, key) >= 0) continue;
            append(test_keys, key);
            append(test_segments_a, ia);
            append(test_candidates, candidate);
        }
    }
    // Preserve the V1 road-pair/segment-pair registration order so legacy
    // junction ids and every downstream deterministic hash remain unchanged.
    int test_order[] = argsort(test_keys);
    foreach (int test_index; test_order)
    {
        int ia = test_segments_a[test_index];
        int candidate = test_candidates[test_index];
        int b = int(point(1, "source_primitive", candidate));
        int ib = int(point(1, "segment_local", candidate));
        vector A = point(0, "P", pts_a[ia]);
        vector B = point(0, "P", pts_a[ia + 1]);
        int road_b = int(point(1, "road_id", candidate));
        float width_b = max(float(point(1, "road_width", candidate)), 0.1);
        vector C = point(1, "segment_a", candidate);
        vector D = point(1, "segment_b", candidate);
        float ta, tb; vector hit;
        exact_tests++;
        if (!segment_intersection_xz(A, B, C, D, ta, tb, hit)) continue;
        float terminal_reach = max(detect, 0.5 * (width_a + width_b) + corner + 0.25);
        int endpoint_a = (ia == 0 && distance(set(hit.x,0,hit.z),set(A.x,0,A.z)) <= terminal_reach)
            || (ia == len(pts_a)-2 && distance(set(hit.x,0,hit.z),set(B.x,0,B.z)) <= terminal_reach);
        int count_b = int(point(1, "segment_count", candidate));
        int endpoint_b = (ib == 0 && distance(set(hit.x,0,hit.z),set(C.x,0,C.z)) <= terminal_reach)
            || (ib == count_b-1 && distance(set(hit.x,0,hit.z),set(D.x,0,D.z)) <= terminal_reach);
        int degree = (!endpoint_a && !endpoint_b) ? 4 : ((endpoint_a != endpoint_b) ? 3 : 2);
        if (degree < 3) continue;
        string jt = degree == 4 ? "cross" : "t";
        int helper = register_junction(0, hit, level_a, degree, jt,
            min(road_a, road_b), cluster);
        int jid = int(point(0, "junction_id", helper));
        setprimattrib(0, "junction_id", a, jid, "set");
        setprimattrib(0, "junction_id", b, jid, "set");
        setprimattrib(0, "junction_type", a, jt, "set");
        setprimattrib(0, "junction_type", b, jt, "set");
    }
}

for (int branch = 0; branch < original_prims; ++branch)
{
    if (hasprimattrib(0, "allow_junction") && !int(prim(0, "allow_junction", branch))) continue;
    int level = int(prim(0, "road_level", branch));
    int branch_id = int(prim(0, "road_id", branch));
    float branch_width = max(float(prim(0, "road_width", branch)), 0.1);
    int branch_pts[] = primpoints(0, branch);
    if (len(branch_pts) < 2) continue;
    for (int end_index = 0; end_index < 2; ++end_index)
    {
        int endpoint = end_index == 0 ? branch_pts[0] : branch_pts[-1];
        int inner = end_index == 0 ? branch_pts[1] : branch_pts[-2];
        vector P = point(0, "P", endpoint);
        vector I = point(0, "P", inner);
        vector incoming = normalize(set(P.x-I.x, 0, P.z-I.z));
        float max_reach = max(detect, 0.5*(branch_width+index_max_width)+corner+0.25);
        vector query = P + incoming * (0.5 * max_reach);
        int candidates[] = pcfind(1, "P", query,
            0.5 * max_reach + index_max_half, 4096);
        sort(candidates);
        foreach (int candidate; candidates)
        {
            broadphase_candidates++;
            int host = int(point(1, "source_primitive", candidate));
            if (host == branch || int(point(1, "road_level", candidate)) != level ||
                !int(point(1, "allow_junction", candidate))) continue;
            float host_width = max(float(point(1, "road_width", candidate)), 0.1);
            float reach = max(detect, 0.5*(branch_width+host_width)+corner+0.25);
            vector C = point(1, "segment_a", candidate);
            vector D = point(1, "segment_b", candidate);
            vector host_dir = normalize(set(D.x-C.x, 0, D.z-C.z));
            if (abs(dot(incoming, host_dir)) > 0.95) continue;
            float ray_t, host_t; vector hit;
            exact_tests++;
            if (!segment_intersection_xz(P, P+incoming*reach, C, D, ray_t, host_t, hit)) continue;
            if (host_t < 1e-4 || host_t > 0.9999) continue;
            int helper = register_junction(0, hit, level, 3, "t",
                min(branch_id, int(point(1, "road_id", candidate))), cluster);
            int jid = int(point(0, "junction_id", helper));
            setprimattrib(0, "junction_id", branch, jid, "set");
            setprimattrib(0, "junction_type", branch, "t", "set");
            setprimattrib(0, "junction_id", host, jid, "set");
            setprimattrib(0, "junction_type", host, "t", "set");
        }
    }
}
setdetailattrib(0, "cityroad_graph_segment_count", npoints(1), "set");
setdetailattrib(0, "cityroad_graph_broadphase_candidates", broadphase_candidates, "set");
setdetailattrib(0, "cityroad_graph_exact_tests", exact_tests, "set");
setdetailattrib(0, "cityroad_graph_broadphase_mode", "pcfind_v2", "set");
'''


NEAR_JUNCTION_OLD = '''int near_junction_v1(int input_index; vector position; float clearance)
{
    // The centerline contract currently carries an empty junction_points group.
    // The validated approach metadata repeats the real junction_center value.
    for (int junction = 0; junction < npoints(input_index); ++junction)
    {
        vector junction_position = haspointattrib(input_index, "junction_center")
            ? point(input_index, "junction_center", junction)
            : point(input_index, "P", junction);
        if (distance(position, junction_position) < clearance)
            return 1;
    }
    return 0;
}
'''
NEAR_JUNCTION_NEW = '''int near_junction_v1(int input_index; vector position; float clearance)
{
    // CITYROAD_COOK_OPTIMIZATION_V18: unique junction-centre point cloud.
    return clearance > 0 && nearpoint(input_index, position, clearance) >= 0;
}
'''


def _sha(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _snippet(node: hou.Node) -> str:
    parm = node.parm("snippet")
    if parm is None:
        raise RuntimeError(f"Missing snippet parm: {node.path()}")
    return parm.unexpandedString()


def _guard(node: hou.Node) -> str:
    source = _snippet(node)
    if MARKER not in source:
        expected = EXPECTED.get(node.name())
        if expected and _sha(source) != expected:
            raise RuntimeError(
                f"{node.name()} prerequisite hash changed: {_sha(source)} != {expected}")
    return source


def _create_wrangle(core: hou.Node, name: str, source: hou.Node,
                    snippet: str, position: tuple[float, float]) -> hou.Node:
    node = core.node(name)
    if node is None:
        node = core.createNode("attribwrangle", name)
    node.setInput(0, source)
    node.parm("class").set(0)
    node.parm("snippet").set(snippet)
    node.setPosition(hou.Vector2(position))
    return node


def _restore_inputs(node: hou.Node, inputs: tuple[hou.Node | None, ...]) -> None:
    for index in range(node.type().maxNumInputs()):
        node.setInput(index, inputs[index] if index < len(inputs) else None)


def _road_v2_snippet(source: str, adaptive: bool) -> str:
    """Replace per-builder junction scans with the shared interval table."""
    first = source.index("        float cuts[] = array(0.0, 1.0);")
    unique = source.index("        cuts = sort(cuts);", first)
    interval_loop = source.index(
        "        for (int interval = 0; interval < len(unique_cuts) - 1; ++interval)",
        unique)
    loop_body = source.index("{", interval_loop) + 1
    inside_end = source.index(
        "            if (inside) continue;", loop_body) + len(
            "            if (inside) continue;")
    prefix = (
        "        // CITYROAD_COOK_OPTIMIZATION_V18_CORRIDOR_CONSUMER\n"
        "        int corridor_records[];\n"
        "        for (int corridor_point = 0; corridor_point < npoints(2); ++corridor_point)\n"
        "            if (int(point(2, \"source_primitive\", corridor_point)) == pr &&\n"
        "                int(point(2, \"source_segment\", corridor_point)) == i)\n"
        "                append(corridor_records, corridor_point);\n"
        "        int boundary_hit = 0;\n"
        "        foreach (int corridor_point; corridor_records)\n"
        "        {\n"
        "            float t0 = float(point(2, \"interval_start\", corridor_point));\n"
        "            float t1 = float(point(2, \"interval_end\", corridor_point));\n"
        "            boundary_hit = max(boundary_hit,\n"
        "                int(point(2, \"boundary_hit\", corridor_point)));")
    result = source[:first] + prefix + source[inside_end:]

    if adaptive:
        old_endpoint = '''            int boundary_0 = on_junction_boundary(1, p0, level);
            int boundary_1 = on_junction_boundary(1, p1, level);
            if (boundary_0)
                tangent_0 = junction_mouth_tangent(
                    1, p0, level, segment_direction);
            if (boundary_1)
                tangent_1 = junction_mouth_tangent(
                    1, p1, level, segment_direction);'''
        new_endpoint = '''            int boundary_0 = int(point(
                2, "interval_start_boundary", corridor_point));
            int boundary_1 = int(point(
                2, "interval_end_boundary", corridor_point));
            if (boundary_0)
                tangent_0 = vector(point(
                    2, "interval_start_tangent", corridor_point));
            if (boundary_1)
                tangent_1 = vector(point(
                    2, "interval_end_tangent", corridor_point));
            // CITYROAD_COOK_OPTIMIZATION_V18_ORIENT_INTERVAL_TANGENT
            if (boundary_0 && dot(tangent_0, segment_direction) < 0.0)
                tangent_0 = -tangent_0;
            if (boundary_1 && dot(tangent_1, segment_direction) < 0.0)
                tangent_1 = -tangent_1;'''
    else:
        old_endpoint = '''                if (on_junction_boundary(1, p0, level))
                    tangent_0 = junction_mouth_tangent(1, p0, level, segment_direction);
                if (on_junction_boundary(1, p1, level))
                    tangent_1 = junction_mouth_tangent(1, p1, level, segment_direction);
                vector side_0 = normalize(cross(set(0.0, 1.0, 0.0), tangent_0));
                vector side_1 = normalize(cross(set(0.0, 1.0, 0.0), tangent_1));
                float fade_0 = on_junction_boundary(1, p0, level) ? 0.0 : 1.0;
                float fade_1 = on_junction_boundary(1, p1, level) ? 0.0 : 1.0;'''
        new_endpoint = '''                int boundary_0 = int(point(
                    2, "interval_start_boundary", corridor_point));
                int boundary_1 = int(point(
                    2, "interval_end_boundary", corridor_point));
                if (boundary_0)
                    tangent_0 = vector(point(
                        2, "interval_start_tangent", corridor_point));
                if (boundary_1)
                    tangent_1 = vector(point(
                        2, "interval_end_tangent", corridor_point));
                // CITYROAD_COOK_OPTIMIZATION_V18_ORIENT_INTERVAL_TANGENT
                if (boundary_0 && dot(tangent_0, segment_direction) < 0.0)
                    tangent_0 = -tangent_0;
                if (boundary_1 && dot(tangent_1, segment_direction) < 0.0)
                    tangent_1 = -tangent_1;
                vector side_0 = normalize(cross(set(0.0, 1.0, 0.0), tangent_0));
                vector side_1 = normalize(cross(set(0.0, 1.0, 0.0), tangent_1));
                float fade_0 = boundary_0 ? 0.0 : 1.0;
                float fade_1 = boundary_1 ? 0.0 : 1.0;'''
    if old_endpoint not in result:
        raise RuntimeError("Road V2 endpoint block changed")
    result = result.replace(old_endpoint, new_endpoint, 1)

    # The interval builder owns this correctness diagnostic. Keeping it here
    # would reintroduce three full junction scans for every source segment.
    diagnostic_start = result.rfind("        vector midpoint = (a + b) * 0.5;")
    diagnostic_end = result.find(
        "        accumulated_distance += segment_length;", diagnostic_start)
    if diagnostic_start < 0 or diagnostic_end < 0:
        raise RuntimeError("Road V2 trim-diagnostic block changed")
    return (result[:diagnostic_start]
            + "        // Shared interval table already validated this trim.\n"
            + result[diagnostic_end:])


def _tree_two_pointer_snippet(source: str) -> str:
    """Merge same-corridor lamps monotonically; retain exact spatial fallback."""
    marker = "CITYROAD_COOK_OPTIMIZATION_V18_LAMP_TREE_TWO_POINTER"
    if marker in source:
        return source
    side_old = '''    for (int side_index = 0; side_index < 2; ++side_index)
    {
        int side = side_index == 0 ? -1 : 1;
        int candidate = 0;'''
    side_new = '''    for (int side_index = 0; side_index < 2; ++side_index)
    {
        int side = side_index == 0 ? -1 : 1;
        // CITYROAD_COOK_OPTIMIZATION_V18_LAMP_TREE_TWO_POINTER
        // Monotonic same-corridor sweep; spatial fallback below preserves
        // exact clearance across neighbouring corridors and curved segments.
        int corridor_lamps[] = findattribval(
            1, "point", "pcg_corridor_id", corridor_id);
        float unsorted_lamp_distances[];
        int unsorted_lamp_points[];
        foreach (int lamp_point; corridor_lamps)
            if (int(point(1, "pcg_side", lamp_point)) == side)
            {
                append(unsorted_lamp_distances,
                    float(point(1, "pcg_distance", lamp_point)));
                append(unsorted_lamp_points, lamp_point);
            }
        int lamp_order[] = argsort(unsorted_lamp_distances);
        float lamp_distances[];
        int lamp_points[];
        foreach (int lamp_index; lamp_order)
        {
            append(lamp_distances, unsorted_lamp_distances[lamp_index]);
            append(lamp_points, unsorted_lamp_points[lamp_index]);
        }
        int lamp_cursor = 0;
        int candidate = 0;'''
    clearance_old = '''            if (!blocked && lamp_clearance > 0 && nearpoint(1, position, lamp_clearance) >= 0)
            {
                blocked = 1;
                ++skipped_lamp;
            }'''
    clearance_new = '''            if (!blocked && lamp_clearance > 0)
            {
                float lower = distance_along - lamp_clearance;
                float upper = distance_along + lamp_clearance;
                while (lamp_cursor < len(lamp_distances)
                    && lamp_distances[lamp_cursor] < lower)
                    ++lamp_cursor;
                int scan = lamp_cursor;
                while (scan < len(lamp_distances)
                    && lamp_distances[scan] <= upper)
                {
                    if (distance(position, point(1, "P", lamp_points[scan]))
                        <= lamp_clearance)
                    {
                        blocked = 1;
                        ++skipped_lamp;
                        break;
                    }
                    ++scan;
                }
                // Adjacent corridors can be spatially close even though their
                // one-dimensional ids differ; keep an indexed exact fallback.
                if (!blocked
                    && nearpoint(1, position, lamp_clearance) >= 0)
                {
                    blocked = 1;
                    ++skipped_lamp;
                }
            }'''
    if side_old not in source or clearance_old not in source:
        raise RuntimeError("Tree two-pointer prerequisite changed")
    return source.replace(side_old, side_new, 1).replace(
        clearance_old, clearance_new, 1)


def _apply_v18_2(core: hou.Node, approach: hou.Node,
                  corridor: hou.Node) -> list[str]:
    """Wire shared tables into production branches; rollback on any failure."""
    touched_names = (
        "CITYROAD_MARKING_HELPERS_MERGE", "CITYROAD_BUILD_STATIC_MARKING_MESH",
        "CITYROAD_BUILD_APPROACH_MARKINGS_V5",
        "CITYROAD_MARKING_TRIANGULATE_FOR_WINDING",
        "CITYROAD_TOPOLOGY_TRANSFER_ROADMARKINGS",
        "ROAD_SELECT_ADAPTIVE_CORNER_SURFACE",
        "CITYROAD_STREET_BUILD_LAMPS_V1", "CITYROAD_STREET_BUILD_TREES_V1",
        "CITYROAD_STREET_BUILD_TREE_PITS_V1", "OUT_STREET_LAMPS",
        "OUT_STREET_TREES", "OUT_STREET_TREE_PITS",
    )
    touched = {name: core.node(name) for name in touched_names}
    if any(node is None for node in touched.values()):
        missing = [name for name, node in touched.items() if node is None]
        raise RuntimeError(f"Missing V18.2 target nodes: {missing}")
    input_backup = {name: tuple(node.inputs()) for name, node in touched.items()}
    snippet_backup = {
        name: _snippet(touched[name])
        for name in ("CITYROAD_BUILD_STATIC_MARKING_MESH",
                     "CITYROAD_BUILD_APPROACH_MARKINGS_V5",
                     "CITYROAD_STREET_BUILD_TREES_V1")
    }
    owned_names = (
        "JUNCTION_CENTER_INDEX_V2", "ROAD_BUILD_SURFACE_V2",
        "ROAD_BUILD_ADAPTIVE_CORNER_SURFACE_V2",
        "CITYROAD_ROAD_SURFACE_V1_V2", "CITYROAD_ADAPTIVE_SURFACE_V1_V2",
        "CITYROAD_CROSSWALK_ENABLE_V2", "CITYROAD_MARKING_ENABLE_V2",
        "CITYROAD_MARKING_EMPTY_V2", "CITYROAD_STREET_LAMP_EMPTY_V2",
        "CITYROAD_STREET_LAMP_ENABLE_V2", "CITYROAD_STREET_TREE_EMPTY_V2",
        "CITYROAD_STREET_TREE_ENABLE_V2",
    )
    existed = {name for name in owned_names if core.node(name) is not None}
    owned_backup = {}
    for name in existed:
        node = core.node(name)
        owned_backup[name] = {
            "inputs": tuple(node.inputs()),
            "snippet": (_snippet(node) if node.parm("snippet") else None),
        }
    try:
        center = _create_wrangle(
            core, "JUNCTION_CENTER_INDEX_V2", approach, JUNCTION_CENTER_VEX,
            (11.5, -36.5))
        corridor.setInput(1, core.node("CITYROAD_BUILD_JUNCTION_SURFACE_BOUNDARY_V5"))
        corridor.setInput(2, approach)
        touched["CITYROAD_MARKING_HELPERS_MERGE"].setInput(1, approach)
        touched["CITYROAD_BUILD_APPROACH_MARKINGS_V5"].setInput(2, approach)
        touched["CITYROAD_STREET_BUILD_LAMPS_V1"].setInput(1, center)
        touched["CITYROAD_STREET_BUILD_TREES_V1"].setInput(2, center)
        tree_node = touched["CITYROAD_STREET_BUILD_TREES_V1"]
        tree_node.parm("snippet").set(
            _tree_two_pointer_snippet(_snippet(tree_node)))

        road_nodes = {}
        for source_name, target_name, adaptive in (
            ("ROAD_BUILD_SURFACE", "ROAD_BUILD_SURFACE_V2", False),
            ("ROAD_BUILD_ADAPTIVE_CORNER_SURFACE",
             "ROAD_BUILD_ADAPTIVE_CORNER_SURFACE_V2", True),
        ):
            source_node = core.node(source_name)
            target = core.node(target_name)
            if target is None:
                target = source_node.copyTo(core)
                target.setName(target_name, unique_name=False)
            _restore_inputs(target, tuple(source_node.inputs()))
            target.setInput(2, corridor)
            target.parm("snippet").set(
                _road_v2_snippet(_snippet(source_node), adaptive))
            road_nodes[target_name] = target

        road_switch = core.node("CITYROAD_ROAD_SURFACE_V1_V2")
        if road_switch is None:
            road_switch = core.createNode("switch", "CITYROAD_ROAD_SURFACE_V1_V2")
        road_switch.setInput(0, core.node("ROAD_BUILD_SURFACE"))
        road_switch.setInput(1, road_nodes["ROAD_BUILD_SURFACE_V2"])
        road_switch.parm("input").set(1)
        adaptive_switch = core.node("CITYROAD_ADAPTIVE_SURFACE_V1_V2")
        if adaptive_switch is None:
            adaptive_switch = core.createNode(
                "switch", "CITYROAD_ADAPTIVE_SURFACE_V1_V2")
        adaptive_switch.setInput(0, core.node("ROAD_BUILD_ADAPTIVE_CORNER_SURFACE"))
        adaptive_switch.setInput(
            1, road_nodes["ROAD_BUILD_ADAPTIVE_CORNER_SURFACE_V2"])
        adaptive_switch.parm("input").set(1)
        touched["ROAD_SELECT_ADAPTIVE_CORNER_SURFACE"].setInput(0, road_switch)
        touched["ROAD_SELECT_ADAPTIVE_CORNER_SURFACE"].setInput(1, adaptive_switch)

        static = touched["CITYROAD_BUILD_STATIC_MARKING_MESH"]
        static_source = _snippet(static)
        if "CITYROAD_COOK_OPTIMIZATION_V18_MARKING_TABLE" not in static_source:
            function_start = static_source.index("function int close_to_junction(")
            function_end = static_source.index(
                "function float junction_boundary_distance(", function_start)
            static_source = static_source[:function_start] + static_source[function_end:]
            array_start = static_source.index("vector junction_positions[];")
            array_end = static_source.index(
                "int emitted_primitive_count = 0;", array_start)
            static_source = (static_source[:array_start]
                + "// CITYROAD_COOK_OPTIMIZATION_V18_MARKING_TABLE\n"
                + static_source[array_end:])
            branch_start = static_source.index(
                "    // Crosswalks/stop lines consume stable mouth metadata directly.")
            branch_end = static_source.index(
                "\n}\n\nfor (int primitive = original_primitive_count - 1;", branch_start)
            static_source = (static_source[:branch_start]
                + "    // CITYROAD_COOK_OPTIMIZATION_V18_APPROACH_BRANCH_ONLY\n"
                + static_source[branch_end:])
            static_source = static_source.replace(
                'chi("../../enable_road_markings") && chi("../../enable_crosswalks")\n'
                '        ? len(expandpointgroup(3, "junction_approaches")) : 0',
                "0")
            static_source = static_source.replace(
                'chi("../../enable_road_markings") && chi("../../enable_crosswalks")\n'
                '        ? len(expandpointgroup(3,"junction_approaches")) : 0',
                "0")
            static.parm("snippet").set(static_source)

        approach_marking = touched["CITYROAD_BUILD_APPROACH_MARKINGS_V5"]
        approach_source = _snippet(approach_marking)
        if "CITYROAD_COOK_OPTIMIZATION_V18_APPROACH_MARKING_OWNER" not in approach_source:
            approach_source = approach_source.replace(
                'if (chi("../../enable_road_markings") && chi("../../enable_crosswalks"))',
                'if (chi("../../enable_crosswalks"))')
            approach_source = approach_source.replace(
                'chi("../../enable_road_markings") && chi("../../enable_crosswalks")',
                'chi("../../enable_crosswalks")')
            approach_source = (
                "// CITYROAD_COOK_OPTIMIZATION_V18_APPROACH_MARKING_OWNER\n"
                + approach_source)
            approach_marking.parm("snippet").set(approach_source)

        cross_switch = core.node("CITYROAD_CROSSWALK_ENABLE_V2")
        if cross_switch is None:
            cross_switch = core.createNode("switch", "CITYROAD_CROSSWALK_ENABLE_V2")
        cross_switch.setInput(0, static)
        cross_switch.setInput(1, approach_marking)
        cross_switch.parm("input").setExpression(
            'ch("../../enable_crosswalks")', language=hou.exprLanguage.Hscript)
        touched["CITYROAD_MARKING_TRIANGULATE_FOR_WINDING"].setInput(
            0, cross_switch)
        marking_empty = core.node("CITYROAD_MARKING_EMPTY_V2")
        if marking_empty is None:
            marking_empty = core.createNode("null", "CITYROAD_MARKING_EMPTY_V2")
        marking_empty.setInput(0, static)
        marking_switch = core.node("CITYROAD_MARKING_ENABLE_V2")
        if marking_switch is None:
            marking_switch = core.createNode("switch", "CITYROAD_MARKING_ENABLE_V2")
        marking_switch.setInput(0, marking_empty)
        marking_switch.setInput(1, core.node("CITYROAD_MARKING_OUTPUT_CONTRACT"))
        marking_switch.parm("input").setExpression(
            'ch("../../enable_road_markings")', language=hou.exprLanguage.Hscript)
        touched["CITYROAD_TOPOLOGY_TRANSFER_ROADMARKINGS"].setInput(
            0, marking_switch)

        for kind, expensive_name, consumer_name, parm_name in (
            ("LAMP", "CITYROAD_STREET_BUILD_LAMPS_V1", "OUT_STREET_LAMPS",
             "enable_street_lamps"),
            ("TREE", "CITYROAD_STREET_BUILD_TREES_V1", "OUT_STREET_TREES",
             "enable_street_trees"),
        ):
            empty_name = f"CITYROAD_STREET_{kind}_EMPTY_V2"
            switch_name = f"CITYROAD_STREET_{kind}_ENABLE_V2"
            empty = core.node(empty_name) or core.createNode("null", empty_name)
            switch = core.node(switch_name) or core.createNode("switch", switch_name)
            switch.setInput(0, empty)
            switch.setInput(1, core.node(expensive_name))
            switch.parm("input").setExpression(
                f'ch("../../{parm_name}")', language=hou.exprLanguage.Hscript)
            core.node(consumer_name).setInput(0, switch)
        touched["CITYROAD_STREET_BUILD_TREE_PITS_V1"].setInput(
            0, core.node("CITYROAD_STREET_TREE_ENABLE_V2"))

        # Keep the transactional scope open until all newly wired branches
        # have cooked without diagnostics.
        _validate_hot_nodes(core)
        return sorted(owned_names)
    except Exception:
        for name, inputs in input_backup.items():
            _restore_inputs(touched[name], inputs)
        for name, source in snippet_backup.items():
            touched[name].parm("snippet").set(source)
        for name in reversed(owned_names):
            node = core.node(name)
            if node is None:
                continue
            if name not in existed:
                node.destroy()
            else:
                backup = owned_backup[name]
                _restore_inputs(node, backup["inputs"])
                if backup["snippet"] is not None:
                    node.parm("snippet").set(backup["snippet"])
        raise


def _validate_hot_nodes(core: hou.Node) -> dict:
    diagnostics = {}
    for name in (
        "GRAPH_CLASSIFY_JUNCTIONS", "JUNCTION_APPROACH_INDEX_V2",
        "JUNCTION_CENTER_INDEX_V2", "CORRIDOR_INTERVAL_INDEX_V2",
        "ROAD_BUILD_SURFACE_V2", "ROAD_BUILD_ADAPTIVE_CORNER_SURFACE_V2",
        "CITYROAD_TOPOLOGY_CLASSIFY_ROAD",
        "CITYROAD_STREET_BUILD_LAMPS_V1", "CITYROAD_STREET_BUILD_TREES_V1",
        "CITYROAD_STREET_BUILD_TREE_PITS_V1", "SIDEWALK_REGION_CONNECTIVITY",
        "OUT_ROAD_MARKINGS", "OUT_STREET_LAMPS", "OUT_STREET_TREES",
        "OUT_STREET_TREE_PITS",
    ):
        node = core.node(name)
        if node is None:
            raise RuntimeError(f"Missing V18 verification node: {name}")
        try:
            node.cook(force=True)
        except Exception as exception:
            raise RuntimeError(
                f"{name} cook failed: {exception}; "
                f"errors={node.errors()} warnings={node.warnings()}") from exception
        diagnostics[name] = {
            "errors": list(node.errors()), "warnings": list(node.warnings()),
            "lastCookTimeMs": float(node.lastCookTime()),
        }
        if node.errors() or node.warnings():
            raise RuntimeError(f"{name} diagnostics: {diagnostics[name]}")
    return diagnostics


def _reconcile_existing_v18(core: hou.Node, targets: dict[str, hou.Node],
                            save: bool) -> dict:
    """Restore/validate an already-patched Live graph without nesting V2 again."""
    normalize = core.node("GRAPH_NORMALIZE_CONNECTIONS")
    graph = targets["GRAPH_CLASSIFY_JUNCTIONS"]
    segment_index = _create_wrangle(
        core, "GRAPH_SEGMENT_INDEX_V2", normalize, SEGMENT_INDEX_VEX, (4.8, -10.6))
    empty = core.node("CITYROAD_GRAPH_INDEX_EMPTY_V1_V2")
    if empty is None:
        empty = core.createNode("null", "CITYROAD_GRAPH_INDEX_EMPTY_V1_V2")
    empty.setPosition(hou.Vector2((3.2, -12.0)))
    switch = core.node("CITYROAD_GRAPH_V1_V2")
    if switch is None:
        switch = core.createNode("switch", "CITYROAD_GRAPH_V1_V2")
    switch.setInput(0, empty)
    switch.setInput(1, segment_index)
    switch.parm("input").set(1)
    switch.setPosition(hou.Vector2((6.5, -10.5)))
    graph.setInput(1, switch)

    graph_source = _snippet(graph).replace(
        "if (npoints(1) > 0 && original_prims >= 32)", "if (npoints(1) > 0)")
    marker_start = graph_source.index("// CITYROAD_COOK_OPTIMIZATION_V18")
    v2_end = graph_source.index("}\nelse\n{", marker_start)
    graph.parm("snippet").set(graph_source[:marker_start] + GRAPH_V2 + graph_source[v2_end:])

    junction_index = _create_wrangle(
        core, "JUNCTION_APPROACH_INDEX_V2",
        core.node("CITYROAD_JUNCTION_APPROACH_METADATA"), JUNCTION_INDEX_VEX,
        (9.5, -35.0))
    corridor = _create_wrangle(
        core, "CORRIDOR_INTERVAL_INDEX_V2", core.node("ROAD_POLYFRAME"),
        CORRIDOR_INDEX_VEX, (13.0, -35.0))
    corridor.setInput(1, core.node("CITYROAD_BUILD_JUNCTION_SURFACE_BOUNDARY_V5"))
    corridor.setInput(2, junction_index)

    audit_switch = core.node("CITYROAD_SIDEWALK_AUDIT_V1_V2")
    if audit_switch is None:
        audit_switch = core.createNode("switch", "CITYROAD_SIDEWALK_AUDIT_V1_V2")
    audit_switch.setInput(0, core.node("SIDEWALK_TOPOLOGY_VALIDATE"))
    audit_switch.setInput(1, core.node("SIDEWALK_PLANAR_MARK_SEAMS"))
    audit_switch.parm("input").set(1)
    audit_switch.setPosition(hou.Vector2((21.8, -106.6)))
    core.node("SIDEWALK_REGION_CONNECTIVITY").setInput(0, audit_switch)

    marking = core.node("CITYROAD_BUILD_APPROACH_MARKINGS_V5")
    family_groups = {
        "CITYROAD_MARKING_CENTER_V2": "road_marking_center",
        "CITYROAD_MARKING_LANE_V2": "road_marking_lane",
        "CITYROAD_MARKING_EDGE_V2": "road_marking_edge",
        "CITYROAD_MARKING_JUNCTION_V2": "road_marking_crosswalk road_marking_stopline",
    }
    for offset, (name, group) in enumerate(family_groups.items()):
        node = core.node(name) or core.createNode("blast", name)
        node.setInput(0, marking)
        node.parm("group").set(group)
        node.parm("negate").set(1)
        node.setPosition(hou.Vector2((10.0 + offset * 2.0, -74.0)))

    v18_2_nodes = _apply_v18_2(core, junction_index, corridor)
    diagnostics = _validate_hot_nodes(core)
    if save:
        hou.hipFile.save()
    return {
        "status": "PASS", "saved": bool(save), "already_applied": True,
        "created_or_updated": sorted([
            "GRAPH_SEGMENT_INDEX_V2", "CITYROAD_GRAPH_INDEX_EMPTY_V1_V2",
            "CITYROAD_GRAPH_V1_V2", "JUNCTION_APPROACH_INDEX_V2",
            "CORRIDOR_INTERVAL_INDEX_V2", "CITYROAD_SIDEWALK_AUDIT_V1_V2",
            *family_groups.keys(), *v18_2_nodes,
        ]),
        "diagnostics": diagnostics,
    }


def apply(save: bool = False) -> dict:
    asset = hou.node(ASSET_PATH)
    if asset is None or asset.type().name() != ASSET_TYPE:
        raise RuntimeError(f"Expected {ASSET_TYPE} at {ASSET_PATH}")
    core = asset.node(CORE_NAME)
    if core is None:
        raise RuntimeError(f"Missing {CORE_NAME}")
    if asset.isLockedHDA():
        raise RuntimeError("Live CityRoad must remain the unlocked implementation source")

    targets = {name: core.node(name) for name in EXPECTED}
    if any(node is None for node in targets.values()):
        raise RuntimeError("A guarded V18 target node is missing")
    if MARKER in _snippet(targets["GRAPH_CLASSIFY_JUNCTIONS"]):
        return _reconcile_existing_v18(core, targets, save)
    original_snippets = {name: _guard(node) for name, node in targets.items()}
    original_inputs = {
        name: tuple(node.inputs()) for name, node in targets.items()
    }
    connectivity = core.node("SIDEWALK_REGION_CONNECTIVITY")
    seams = core.node("SIDEWALK_PLANAR_MARK_SEAMS")
    topology_audit = core.node("SIDEWALK_TOPOLOGY_VALIDATE")
    original_connectivity_inputs = tuple(connectivity.inputs())
    created = []
    try:
        normalize = core.node("GRAPH_NORMALIZE_CONNECTIONS")
        graph = targets["GRAPH_CLASSIFY_JUNCTIONS"]
        segment_index = _create_wrangle(
            core, "GRAPH_SEGMENT_INDEX_V2", normalize, SEGMENT_INDEX_VEX,
            (4.8, -10.6))
        created.append(segment_index.name())
        empty = core.node("CITYROAD_GRAPH_INDEX_EMPTY_V1_V2")
        if empty is None:
            empty = core.createNode("null", "CITYROAD_GRAPH_INDEX_EMPTY_V1_V2")
        empty.setPosition(hou.Vector2((3.2, -12.0)))
        switch = core.node("CITYROAD_GRAPH_V1_V2")
        if switch is None:
            switch = core.createNode("switch", "CITYROAD_GRAPH_V1_V2")
        switch.setInput(0, empty)
        switch.setInput(1, segment_index)
        switch.parm("input").set(1)
        switch.setPosition(hou.Vector2((6.5, -10.5)))
        graph.setInput(1, switch)

        graph_source = original_snippets["GRAPH_CLASSIFY_JUNCTIONS"]
        start = graph_source.index("// Exact crossings and terminal overhangs")
        end = graph_source.index("int helpers[]")
        old_scan = graph_source[start:end]
        graph_source = (
            graph_source[:start]
            + "if (npoints(1) > 0)\n{\n" + GRAPH_V2 + "}\nelse\n{\n"
            + old_scan + "}\n\n" + graph_source[end:])
        graph.parm("snippet").set(graph_source)

        approach = core.node("CITYROAD_JUNCTION_APPROACH_METADATA")
        junction_index = _create_wrangle(
            core, "JUNCTION_APPROACH_INDEX_V2", approach, JUNCTION_INDEX_VEX,
            (9.5, -35.0))
        created.append(junction_index.name())
        corridor = _create_wrangle(
            core, "CORRIDOR_INTERVAL_INDEX_V2", core.node("ROAD_POLYFRAME"),
            CORRIDOR_INDEX_VEX, (13.0, -35.0))
        corridor.setInput(1, core.node("CITYROAD_BUILD_JUNCTION_SURFACE_BOUNDARY_V5"))
        corridor.setInput(2, junction_index)
        created.append(corridor.name())

        for name, input_index in (("CITYROAD_STREET_BUILD_LAMPS_V1", 1),
                                  ("CITYROAD_STREET_BUILD_TREES_V1", 2)):
            node = targets[name]
            source = original_snippets[name]
            if NEAR_JUNCTION_OLD not in source:
                raise RuntimeError(f"{name} near-junction block changed")
            node.parm("snippet").set(source.replace(
                NEAR_JUNCTION_OLD, NEAR_JUNCTION_NEW, 1))
            node.setInput(input_index, junction_index)

        winding = targets["CITYROAD_TOPOLOGY_CLASSIFY_ROAD"]
        source = original_snippets["CITYROAD_TOPOLOGY_CLASSIFY_ROAD"]
        source = source.replace(
            "int winding_houdini_down=0;",
            "int winding_houdini_down=0;\nint winding_checked=0;\n// CITYROAD_COOK_OPTIMIZATION_V18", 1)
        source = source.replace(
            "if(len(p3)==3)\n    {",
            "if(len(p3)==3)\n    {\n        winding_checked++;", 1)
        source = source.replace(
            "winding_houdini_down==nprimitives(0) && winding_houdini_up==0",
            "winding_houdini_down==winding_checked && winding_houdini_up==0", 1)
        source = source.replace(
            "if(winding_houdini_down!=nprimitives(0) || winding_houdini_up!=0)",
            "if(winding_houdini_down!=winding_checked || winding_houdini_up!=0)", 1)
        source = source.replace(
            'setdetailattrib(0,"road_houdini_winding_down_count",winding_houdini_down,"set");',
            'setdetailattrib(0,"road_houdini_winding_down_count",winding_houdini_down,"set");\n'
            'setdetailattrib(0,"road_houdini_winding_checked_count",winding_checked,"set");', 1)
        source = source.replace(
            'if(winding_houdini_down!=winding_checked || winding_houdini_up!=0)\n'
            '    warning("CityRoad road winding contract failed: Houdini output must face -Y for Unity +Y.");',
            '// Intermediate constraint triangles may have mixed winding.  The formal\n'
            '// CITYROAD_UNITY_ROAD_NORMALS output is checked triangle-by-triangle by VerifyFull.',
            1)
        winding.parm("snippet").set(source)

        # Keep the exact audit node and its diagnostics available, but remove
        # it from the formal sidewalk geometry dependency.  VerifyFull cooks
        # SIDEWALK_TOPOLOGY_VALIDATE explicitly through the cumulative contract.
        audit_switch = core.node("CITYROAD_SIDEWALK_AUDIT_V1_V2")
        if audit_switch is None:
            audit_switch = core.createNode("switch", "CITYROAD_SIDEWALK_AUDIT_V1_V2")
        audit_switch.setInput(0, topology_audit)
        audit_switch.setInput(1, seams)
        audit_switch.parm("input").set(1)
        audit_switch.setPosition(hou.Vector2((21.8, -106.6)))
        connectivity.setInput(0, audit_switch)
        created.append(audit_switch.name())

        # Explicit marking families are cheap filtered views used by debug and
        # extension passes; production still performs one final triangulation.
        marking = core.node("CITYROAD_BUILD_APPROACH_MARKINGS_V5")
        family_groups = {
            "CITYROAD_MARKING_CENTER_V2": "road_marking_center",
            "CITYROAD_MARKING_LANE_V2": "road_marking_lane",
            "CITYROAD_MARKING_EDGE_V2": "road_marking_edge",
            "CITYROAD_MARKING_JUNCTION_V2": "road_marking_crosswalk road_marking_stopline",
        }
        family_nodes = []
        for offset, (name, group) in enumerate(family_groups.items()):
            node = core.node(name)
            if node is None:
                node = core.createNode("blast", name)
            node.setInput(0, marking)
            node.parm("group").set(group)
            node.parm("negate").set(1)
            node.setPosition(hou.Vector2((10.0 + offset * 2.0, -74.0)))
            family_nodes.append(node)
            created.append(node.name())

        created.extend(_apply_v18_2(core, junction_index, corridor))
        diagnostics = _validate_hot_nodes(core)
        if save:
            hou.hipFile.save()
        return {"status": "PASS", "saved": bool(save),
                "created_or_updated": sorted(set(created)),
                "diagnostics": diagnostics}
    except Exception:
        for name, source in original_snippets.items():
            targets[name].parm("snippet").set(source)
            for index in range(targets[name].type().maxNumInputs()):
                targets[name].setInput(index, original_inputs[name][index]
                                       if index < len(original_inputs[name]) else None)
        for index in range(connectivity.type().maxNumInputs()):
            connectivity.setInput(index, original_connectivity_inputs[index]
                                  if index < len(original_connectivity_inputs) else None)
        for name in (
            "CITYROAD_GRAPH_V1_V2", "CITYROAD_GRAPH_INDEX_EMPTY_V1_V2",
            "GRAPH_SEGMENT_INDEX_V2", "JUNCTION_APPROACH_INDEX_V2",
            "CORRIDOR_INTERVAL_INDEX_V2", "CITYROAD_SIDEWALK_AUDIT_V1_V2",
            "CITYROAD_MARKING_CENTER_V2", "CITYROAD_MARKING_LANE_V2",
            "CITYROAD_MARKING_EDGE_V2", "CITYROAD_MARKING_JUNCTION_V2",
            "JUNCTION_CENTER_INDEX_V2", "ROAD_BUILD_SURFACE_V2",
            "ROAD_BUILD_ADAPTIVE_CORNER_SURFACE_V2",
            "CITYROAD_ROAD_SURFACE_V1_V2",
            "CITYROAD_ADAPTIVE_SURFACE_V1_V2",
            "CITYROAD_CROSSWALK_ENABLE_V2", "CITYROAD_MARKING_ENABLE_V2",
            "CITYROAD_MARKING_EMPTY_V2", "CITYROAD_STREET_LAMP_EMPTY_V2",
            "CITYROAD_STREET_LAMP_ENABLE_V2",
            "CITYROAD_STREET_TREE_EMPTY_V2",
            "CITYROAD_STREET_TREE_ENABLE_V2",
        ):
            node = core.node(name)
            if node is not None:
                node.destroy()
        raise


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=18811)
    parser.add_argument("--live", action="store_true")
    parser.add_argument("--save", action="store_true")
    args = parser.parse_args()
    if not args.live:
        print(json.dumps(apply(save=args.save), ensure_ascii=False, indent=2))
        return 0
    import hrpyc
    connection, _remote_hou = hrpyc.import_remote_module(args.host, args.port, "hou")
    try:
        script_dir = str(Path(__file__).resolve().parent).replace("\\", "/")
        connection.execute(
            "import sys, importlib, json; "
            f"sys.path.insert(0, {script_dir!r}) if {script_dir!r} not in sys.path else None; "
            "import patch_cityroad_cook_v2_20260812 as _pcg_v18; importlib.reload(_pcg_v18)")
        payload = connection.eval(
            f"_pcg_v18.json.dumps(_pcg_v18.apply(save={args.save!r}), ensure_ascii=False)")
        print(json.dumps(json.loads(str(payload)), ensure_ascii=False, indent=2))
    finally:
        connection.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
