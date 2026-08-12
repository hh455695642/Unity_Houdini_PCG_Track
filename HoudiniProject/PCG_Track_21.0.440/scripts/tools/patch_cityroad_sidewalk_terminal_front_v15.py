"""Incremental V15 sidewalk terminal-front containment fix for CityRoad.

The current live V14 CityRoad instance is the only implementation source.
This patch adds one marker wrangle before sidewalk road classification and one
containment validator after deletion.  It defaults to ``save=False``, checks
exact preconditions, is idempotent, and restores all touched state on failure.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

import hou


ASSET_PATH = "/obj/CityRoad_DEV"
ASSET_TYPE = "pcgbike::CityRoad::1.0"
DEFINITION_SUFFIX = "Assets/PCG/HDA/City/CityRoad.hda"
HIP_SUFFIX = "HoudiniProject/PCG_Track_21.0.440/PCG_Bike_CityRoad.hip"
CORE_NAME = "CityRoadCore"
MARK_NODE = "CITYROAD_MARK_SIDEWALK_TERMINAL_FRONT_EXCLUSIONS_V15"
VALIDATE_NODE = "CITYROAD_VALIDATE_SIDEWALK_TERMINAL_FRONT_CONTAINMENT_V15"
V15_MARKER = "CITYROAD_V15_SIDEWALK_TERMINAL_FRONT_CONTAINMENT"
CLASSIFY_SHA256 = "02064ebe9c45fb3251267112e866a22595c5e4fd2b9eb8d8169649ee7044ef9e"


MARK_SNIPPET = r'''
// CITYROAD_V15_SIDEWALK_TERMINAL_FRONT_CONTAINMENT
// Input 0: V11 constrained sidewalk triangles.
// Input 1: exact closed site silhouette.
// Input 2: V13 square-open-end side connectors.
// Build one exclusion polygon per terminal from the square cap, its two
// connector endpoints, and their shared site edge.  Only whole constrained
// triangles may be marked; any crossing means the upstream constraints broke.
float cross2d_v15(vector a; vector b)
{
    return a.x * b.z - a.z * b.x;
}

vector project_to_segment_v15(vector p; vector a; vector b)
{
    vector delta = b - a;
    delta.y = 0.0;
    float denominator = max(dot(delta, delta), 1e-20);
    float u = clamp(dot(p - a, delta) / denominator, 0.0, 1.0);
    return a + delta * u;
}

int point_in_quad_v15(vector p; vector quad[]; float tolerance)
{
    int inside = 0;
    for (int edge = 0; edge < len(quad); ++edge)
    {
        vector a = quad[edge];
        vector b = quad[(edge + 1) % len(quad)];
        vector delta = b - a;
        delta.y = 0.0;
        vector relative = p - a;
        relative.y = 0.0;
        float denominator = max(dot(delta, delta), 1e-20);
        float u = clamp(dot(relative, delta) / denominator, 0.0, 1.0);
        vector nearest = a + delta * u;
        nearest.y = p.y;
        if (distance(nearest, p) <= tolerance)
            return 1;
        if (((a.z > p.z) != (b.z > p.z)) &&
            p.x < (b.x - a.x) * (p.z - a.z) /
                (b.z - a.z + 1e-20) + a.x)
            inside = !inside;
    }
    return inside;
}

int proper_segment_crossing_v15(
    vector a; vector b; vector c; vector d; float tolerance)
{
    vector ab = b - a;
    vector cd = d - c;
    vector ac = c - a;
    vector ad = d - a;
    vector ca = a - c;
    vector cb = b - c;
    ab.y = 0.0;
    cd.y = 0.0;
    ac.y = 0.0;
    ad.y = 0.0;
    ca.y = 0.0;
    cb.y = 0.0;
    float o1 = cross2d_v15(ab, ac);
    float o2 = cross2d_v15(ab, ad);
    float o3 = cross2d_v15(cd, ca);
    float o4 = cross2d_v15(cd, cb);
    return ((o1 > tolerance && o2 < -tolerance) ||
            (o1 < -tolerance && o2 > tolerance)) &&
           ((o3 > tolerance && o4 < -tolerance) ||
            (o3 < -tolerance && o4 > tolerance));
}

addprimattrib(0, "v15_terminal_front_id", -1);
int terminal_count = detail(2, "sidewalk_open_end_terminal_count", 0);
int active_count = 0;
int sealed_count = 0;
int occluded_count = 0;
int invalid_count = 0;
int marked_count = 0;
int nonconforming_count = 0;
float active_area = 0.0;
float tolerance = 0.02;
float sealed_area_epsilon = 0.01;

for (int terminal_id = 0; terminal_id < terminal_count; ++terminal_id)
{
    int left_connector = -1;
    int right_connector = -1;
    int duplicate_side = 0;
    int clipped_by_road = 0;
    for (int connector = 0; connector < nprimitives(2); ++connector)
    {
        if (prim(2, "terminal_id", connector) != terminal_id)
            continue;
        clipped_by_road |= prim(2, "connector_clipped_by_road", connector);
        int side = prim(2, "terminal_side", connector);
        if (side > 0)
        {
            duplicate_side |= left_connector >= 0;
            left_connector = connector;
        }
        else if (side < 0)
        {
            duplicate_side |= right_connector >= 0;
            right_connector = connector;
        }
        else
            duplicate_side = 1;
    }
    if (clipped_by_road)
    {
        ++occluded_count;
        continue;
    }
    if (duplicate_side || left_connector < 0 || right_connector < 0)
    {
        ++invalid_count;
        continue;
    }
    int left_site_prim = prim(2, "connector_site_primitive", left_connector);
    int right_site_prim = prim(2, "connector_site_primitive", right_connector);
    int left_site_edge = prim(2, "connector_site_edge", left_connector);
    int right_site_edge = prim(2, "connector_site_edge", right_connector);
    if (left_site_prim != right_site_prim ||
        left_site_edge != right_site_edge || left_site_prim < 0)
    {
        ++invalid_count;
        continue;
    }
    int site_points[] = primpoints(1, left_site_prim);
    if (len(site_points) < 3 || left_site_edge < 0 ||
        left_site_edge >= len(site_points))
    {
        ++invalid_count;
        continue;
    }
    vector site_a = point(1, "P", site_points[left_site_edge]);
    vector site_b = point(1, "P",
        site_points[(left_site_edge + 1) % len(site_points)]);
    int left_points[] = primpoints(2, left_connector);
    int right_points[] = primpoints(2, right_connector);
    if (len(left_points) < 2 || len(right_points) < 2)
    {
        ++invalid_count;
        continue;
    }
    vector left_cap = point(2, "P", left_points[0]);
    vector right_cap = point(2, "P", right_points[0]);
    vector left_target = project_to_segment_v15(
        point(2, "P", left_points[-1]), site_a, site_b);
    vector right_target = project_to_segment_v15(
        point(2, "P", right_points[-1]), site_a, site_b);
    vector quad[] = array(left_cap, left_target, right_target, right_cap);
    float double_area = 0.0;
    for (int edge = 0; edge < 4; ++edge)
        double_area += cross2d_v15(
            quad[edge], quad[(edge + 1) % 4]);
    float exclusion_area = abs(double_area) * 0.5;
    if (exclusion_area <= sealed_area_epsilon)
    {
        ++sealed_count;
        continue;
    }
    ++active_count;
    active_area += exclusion_area;

    for (int primitive = 0; primitive < nprimitives(0); ++primitive)
    {
        int points[] = primpoints(0, primitive);
        if (len(points) < 3)
            continue;
        vector center = 0;
        foreach (int point_number; points)
        {
            vector position = point(0, "P", point_number);
            center += position;
        }
        center /= float(len(points));
        int center_inside = point_in_quad_v15(center, quad, tolerance);
        int crosses_boundary = 0;
        for (int triangle_edge = 0;
            triangle_edge < len(points) && !crosses_boundary;
            ++triangle_edge)
        {
            vector triangle_a = point(0, "P", points[triangle_edge]);
            vector triangle_b = point(0, "P",
                points[(triangle_edge + 1) % len(points)]);
            for (int quad_edge = 0; quad_edge < 4; ++quad_edge)
                if (proper_segment_crossing_v15(
                    triangle_a, triangle_b, quad[quad_edge],
                    quad[(quad_edge + 1) % 4], tolerance))
                {
                    crosses_boundary = 1;
                    break;
                }
        }
        if (crosses_boundary)
        {
            ++nonconforming_count;
            continue;
        }
        if (center_inside &&
            !inprimgroup(0, "sidewalk_terminal_front_exclusion_v15", primitive))
        {
            setprimgroup(0, "sidewalk_terminal_front_exclusion_v15",
                primitive, 1, "set");
            setprimattrib(0, "v15_terminal_front_id",
                primitive, terminal_id, "set");
            ++marked_count;
        }
    }
}

setdetailattrib(0, "sidewalk_terminal_front_active_count",
    active_count, "set");
setdetailattrib(0, "sidewalk_terminal_front_sealed_count",
    sealed_count, "set");
setdetailattrib(0, "sidewalk_terminal_front_occluded_count",
    occluded_count, "set");
setdetailattrib(0, "sidewalk_terminal_front_invalid_count",
    invalid_count, "set");
setdetailattrib(0, "sidewalk_terminal_front_marked_triangle_count",
    marked_count, "set");
setdetailattrib(0, "sidewalk_terminal_front_nonconforming_triangle_count",
    nonconforming_count, "set");
setdetailattrib(0, "sidewalk_terminal_front_active_area",
    active_area, "set");
setdetailattrib(0, "cityroad_sidewalk_terminal_front_patch",
    "V15", "set");
if (invalid_count > 0 || nonconforming_count > 0)
    error(sprintf(
        "V15 terminal-front constraints invalid=%d nonconforming=%d",
        invalid_count, nonconforming_count));
'''


VALIDATE_SNIPPET = r'''
// CITYROAD_V15_SIDEWALK_TERMINAL_FRONT_CONTAINMENT
// Input 0: final planar sidewalk after road and terminal-front deletion.
// Input 1: exact closed site silhouette.
// Input 2: V13 open-end connectors used to reconstruct exclusion polygons.
float cross2d_v15(vector a; vector b)
{
    return a.x * b.z - a.z * b.x;
}

float point_segment_distance_v15(vector p; vector a; vector b)
{
    vector delta = b - a;
    delta.y = 0.0;
    vector relative = p - a;
    relative.y = 0.0;
    float denominator = max(dot(delta, delta), 1e-20);
    float u = clamp(dot(relative, delta) / denominator, 0.0, 1.0);
    vector nearest = a + delta * u;
    nearest.y = p.y;
    return distance(nearest, p);
}

vector project_to_segment_v15(vector p; vector a; vector b)
{
    vector delta = b - a;
    delta.y = 0.0;
    float denominator = max(dot(delta, delta), 1e-20);
    float u = clamp(dot(p - a, delta) / denominator, 0.0, 1.0);
    return a + delta * u;
}

int point_in_polygon_v15(vector p; int input_index; int primitive;
    float tolerance)
{
    int points[] = primpoints(input_index, primitive);
    int inside = 0;
    for (int edge = 0; edge < len(points); ++edge)
    {
        vector a = point(input_index, "P", points[edge]);
        vector b = point(input_index, "P",
            points[(edge + 1) % len(points)]);
        if (point_segment_distance_v15(p, a, b) <= tolerance)
            return 1;
        if (((a.z > p.z) != (b.z > p.z)) &&
            p.x < (b.x - a.x) * (p.z - a.z) /
                (b.z - a.z + 1e-20) + a.x)
            inside = !inside;
    }
    return inside;
}

int point_in_quad_v15(vector p; vector quad[]; float tolerance)
{
    int inside = 0;
    for (int edge = 0; edge < len(quad); ++edge)
    {
        vector a = quad[edge];
        vector b = quad[(edge + 1) % len(quad)];
        if (point_segment_distance_v15(p, a, b) <= tolerance)
            return 1;
        if (((a.z > p.z) != (b.z > p.z)) &&
            p.x < (b.x - a.x) * (p.z - a.z) /
                (b.z - a.z + 1e-20) + a.x)
            inside = !inside;
    }
    return inside;
}

int proper_segment_crossing_v15(
    vector a; vector b; vector c; vector d; float tolerance)
{
    vector ab = b - a;
    vector cd = d - c;
    vector ac = c - a;
    vector ad = d - a;
    vector ca = a - c;
    vector cb = b - c;
    ab.y = 0.0;
    cd.y = 0.0;
    ac.y = 0.0;
    ad.y = 0.0;
    ca.y = 0.0;
    cb.y = 0.0;
    float o1 = cross2d_v15(ab, ac);
    float o2 = cross2d_v15(ab, ad);
    float o3 = cross2d_v15(cd, ca);
    float o4 = cross2d_v15(cd, cb);
    return ((o1 > tolerance && o2 < -tolerance) ||
            (o1 < -tolerance && o2 > tolerance)) &&
           ((o3 > tolerance && o4 < -tolerance) ||
            (o3 < -tolerance && o4 > tolerance));
}

float tolerance = 0.005;
int outside_vertex_count = 0;
int boundary_crossing_edge_count = 0;
int outside_positive_area_triangle_count = 0;
int outside_points[];
int crossing_edge_a[];
int crossing_edge_b[];

for (int primitive = 0; primitive < nprimitives(0); ++primitive)
{
    int points[] = primpoints(0, primitive);
    if (len(points) < 3)
        continue;
    vector center = 0;
    foreach (int point_number; points)
    {
        vector position = point(0, "P", point_number);
        center += position;
        int inside_site = 0;
        for (int site_primitive = 0;
            site_primitive < nprimitives(1); ++site_primitive)
            if (point_in_polygon_v15(
                position, 1, site_primitive, tolerance))
                inside_site = !inside_site;
        if (!inside_site && find(outside_points, point_number) < 0)
        {
            append(outside_points, point_number);
            ++outside_vertex_count;
        }
    }
    center /= float(len(points));
    int center_inside_site = 0;
    for (int site_primitive = 0;
        site_primitive < nprimitives(1); ++site_primitive)
        if (point_in_polygon_v15(center, 1, site_primitive, tolerance))
            center_inside_site = !center_inside_site;
    if (!center_inside_site)
        ++outside_positive_area_triangle_count;

    for (int edge = 0; edge < len(points); ++edge)
    {
        int raw_a = points[edge];
        int raw_b = points[(edge + 1) % len(points)];
        vector a = point(0, "P", raw_a);
        vector b = point(0, "P", raw_b);
        // A valid edge may be collinear with the site silhouette and differ
        // by sub-millimetre Fuse noise.  Audit actual edge occupancy instead
        // of treating an orientation-sign flip at the shared boundary as a
        // crossing: every interior sample must remain in/on the site.
        int crosses = 0;
        for (int sample_index = 1;
            sample_index < 8 && !crosses; ++sample_index)
        {
            float sample_u = float(sample_index) / 8.0;
            vector sample_position = lerp(a, b, sample_u);
            int sample_inside = 0;
            for (int site_primitive = 0;
                site_primitive < nprimitives(1); ++site_primitive)
                if (point_in_polygon_v15(
                    sample_position, 1, site_primitive, tolerance))
                    sample_inside = !sample_inside;
            if (!sample_inside)
                crosses = 1;
        }
        int key_a = min(raw_a, raw_b);
        int key_b = max(raw_a, raw_b);
        int duplicate = 0;
        for (int seen = 0; seen < len(crossing_edge_a); ++seen)
            if (crossing_edge_a[seen] == key_a &&
                crossing_edge_b[seen] == key_b)
            {
                duplicate = 1;
                break;
            }
        if (crosses && !duplicate)
        {
            append(crossing_edge_a, key_a);
            append(crossing_edge_b, key_b);
            ++boundary_crossing_edge_count;
        }
    }
}

int residual_count = 0;
int terminal_count = detail(2, "sidewalk_open_end_terminal_count", 0);
for (int terminal_id = 0; terminal_id < terminal_count; ++terminal_id)
{
    int left_connector = -1;
    int right_connector = -1;
    int clipped_by_road = 0;
    for (int connector = 0; connector < nprimitives(2); ++connector)
    {
        if (prim(2, "terminal_id", connector) != terminal_id)
            continue;
        clipped_by_road |= prim(2, "connector_clipped_by_road", connector);
        int side = prim(2, "terminal_side", connector);
        if (side > 0)
            left_connector = connector;
        else if (side < 0)
            right_connector = connector;
    }
    if (clipped_by_road || left_connector < 0 || right_connector < 0)
        continue;
    int site_prim = prim(2, "connector_site_primitive", left_connector);
    int site_edge = prim(2, "connector_site_edge", left_connector);
    if (site_prim != prim(2, "connector_site_primitive", right_connector) ||
        site_edge != prim(2, "connector_site_edge", right_connector))
        continue;
    int site_points[] = primpoints(1, site_prim);
    int left_points[] = primpoints(2, left_connector);
    int right_points[] = primpoints(2, right_connector);
    if (len(site_points) < 3 || len(left_points) < 2 ||
        len(right_points) < 2)
        continue;
    vector site_a = point(1, "P", site_points[site_edge]);
    vector site_b = point(1, "P",
        site_points[(site_edge + 1) % len(site_points)]);
    vector left_cap = point(2, "P", left_points[0]);
    vector right_cap = point(2, "P", right_points[0]);
    vector left_raw_target = point(2, "P", left_points[-1]);
    vector right_raw_target = point(2, "P", right_points[-1]);
    vector left_target = project_to_segment_v15(
        left_raw_target, site_a, site_b);
    vector right_target = project_to_segment_v15(
        right_raw_target, site_a, site_b);
    vector quad[] = array(
        left_cap, left_target, right_target, right_cap);
    float double_area = 0.0;
    for (int edge = 0; edge < 4; ++edge)
        double_area += cross2d_v15(quad[edge], quad[(edge + 1) % 4]);
    if (abs(double_area) * 0.5 <= 0.01)
        continue;
    for (int primitive = 0; primitive < nprimitives(0); ++primitive)
    {
        int points[] = primpoints(0, primitive);
        if (len(points) < 3)
            continue;
        vector center = 0;
        foreach (int point_number; points)
        {
            vector position = point(0, "P", point_number);
            center += position;
        }
        center /= float(len(points));
        if (point_in_quad_v15(center, quad, tolerance))
            ++residual_count;
    }
}

int marked_count = detail(
    0, "sidewalk_terminal_front_marked_triangle_count", 0);
int deleted_count = max(0, marked_count - residual_count);
int containment_ok = outside_vertex_count == 0 &&
    boundary_crossing_edge_count == 0 &&
    outside_positive_area_triangle_count == 0 && residual_count == 0 &&
    detail(0, "sidewalk_terminal_front_invalid_count", 0) == 0 &&
    detail(0, "sidewalk_terminal_front_nonconforming_triangle_count", 0) == 0;
setdetailattrib(0, "sidewalk_terminal_front_deleted_triangle_count",
    deleted_count, "set");
setdetailattrib(0, "sidewalk_terminal_front_residual_triangle_count",
    residual_count, "set");
setdetailattrib(0, "sidewalk_site_outside_vertex_count",
    outside_vertex_count, "set");
setdetailattrib(0, "sidewalk_site_boundary_crossing_edge_count",
    boundary_crossing_edge_count, "set");
setdetailattrib(0, "sidewalk_site_outside_positive_area_triangle_count",
    outside_positive_area_triangle_count, "set");
setdetailattrib(0, "sidewalk_terminal_front_containment_ok",
    containment_ok, "set");
setdetailattrib(0, "cityroad_sidewalk_terminal_front_patch",
    "V15", "set");
if (!containment_ok)
    error(sprintf(
        "V15 containment failed outside_points=%d crossings=%d outside_triangles=%d residual=%d",
        outside_vertex_count, boundary_crossing_edge_count,
        outside_positive_area_triangle_count, residual_count));
'''


CLASSIFY_ANCHOR = "    if(inside_road)\n"
CLASSIFY_REPLACEMENT = (
    "    // CITYROAD_V15_SIDEWALK_TERMINAL_FRONT_CONTAINMENT\n"
    "    int inside_terminal_front = inprimgroup(\n"
    "        0, \"sidewalk_terminal_front_exclusion_v15\", pr);\n"
    "    if(inside_road || inside_terminal_front)\n"
)


def require_node(core: hou.Node, name: str) -> hou.Node:
    node = core.node(name)
    if node is None:
        raise RuntimeError(f"Missing CityRoad node: {name}")
    return node


def snippet(node: hou.Node) -> str:
    parm = node.parm("snippet")
    if parm is None:
        raise RuntimeError(f"Node has no snippet parameter: {node.path()}")
    return parm.evalAsString()


def sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def metric(node: hou.Node, name: str, default=None):
    geometry = node.geometry()
    attrib = geometry.findGlobalAttrib(name)
    return geometry.attribValue(attrib) if attrib is not None else default


def validate(core: hou.Node) -> dict:
    nodes = [
        require_node(core, MARK_NODE),
        require_node(core, VALIDATE_NODE),
        require_node(core, "SIDEWALK_PLANAR_MARK_SEAMS"),
        require_node(core, "SIDEWALK_TOPOLOGY_VALIDATE"),
        require_node(core, "SIDEWALK_REGION_METADATA"),
        require_node(core, "ROAD_UNION_ROUND_FINAL_BOUNDARY"),
        require_node(core, "CURB_SIDEWALK_STATS"),
        require_node(core, "OUT_SIDEWALK_CURB"),
    ]
    for node in nodes:
        try:
            node.cook(force=True)
        except hou.OperationFailed as exc:
            raise RuntimeError(
                f"Cook failed at {node.path()}: "
                f"errors={node.errors()} warnings={node.warnings()}") from exc
        if node.errors() or node.warnings():
            raise RuntimeError(
                f"Cook diagnostics at {node.path()}: "
                f"errors={node.errors()} warnings={node.warnings()}")

    mark, containment, seams, topology, regions, boundary, stats, output = nodes
    values = {
        "active": int(metric(containment, "sidewalk_terminal_front_active_count", -1)),
        "sealed": int(metric(containment, "sidewalk_terminal_front_sealed_count", -1)),
        "occluded": int(metric(containment, "sidewalk_terminal_front_occluded_count", -1)),
        "invalid": int(metric(containment, "sidewalk_terminal_front_invalid_count", -1)),
        "marked": int(metric(containment, "sidewalk_terminal_front_marked_triangle_count", -1)),
        "deleted": int(metric(containment, "sidewalk_terminal_front_deleted_triangle_count", -1)),
        "residual": int(metric(containment, "sidewalk_terminal_front_residual_triangle_count", -1)),
        "nonconforming": int(metric(containment, "sidewalk_terminal_front_nonconforming_triangle_count", -1)),
        "outside_vertices": int(metric(containment, "sidewalk_site_outside_vertex_count", -1)),
        "site_crossings": int(metric(containment, "sidewalk_site_boundary_crossing_edge_count", -1)),
        "outside_triangles": int(metric(containment, "sidewalk_site_outside_positive_area_triangle_count", -1)),
        "containment_ok": int(metric(containment, "sidewalk_terminal_front_containment_ok", 0)),
        "patch": str(metric(containment, "cityroad_sidewalk_terminal_front_patch", "")),
        "sidewalk_primitives": len(regions.geometry().prims()),
        "region_count": int(metric(regions, "sidewalk_region_partition_count", -1)),
        "connector_complete": int(metric(seams, "sidewalk_partition_complete_connector_count", -1)),
        "connector_uncovered": int(metric(seams, "sidewalk_partition_uncovered_connector_count", -1)),
        "partition_errors": int(metric(regions, "square_open_end_partition_error_count", -1)),
        "topology_ok": int(metric(topology, "sidewalk_validation_topology_ok", 0)),
        "rounded": int(metric(boundary, "final_boundary_mobile_rounded_corner_count", -1)),
        "right_angles": int(metric(boundary, "final_boundary_mobile_right_angle_corner_count", -1)),
        "square_skips": int(metric(boundary, "square_open_end_corner_skip_count", -1)),
        "degenerate": int(metric(stats, "degenerate_primitive_count", -1)),
        "output_primitives": len(output.geometry().prims()),
    }
    expected = {
        "active": 3, "sealed": 4, "occluded": 1, "invalid": 0,
        "marked": 4, "deleted": 4, "residual": 0, "nonconforming": 0,
        "outside_vertices": 0, "site_crossings": 0, "outside_triangles": 0,
        "containment_ok": 1, "patch": "V15", "sidewalk_primitives": 167,
        "region_count": 9, "connector_complete": 16,
        "connector_uncovered": 0, "partition_errors": 0, "topology_ok": 1,
        "rounded": 32, "right_angles": 10, "square_skips": 14,
        "degenerate": 0,
    }
    failed = [key for key, expected_value in expected.items()
              if values[key] != expected_value]
    if failed:
        raise RuntimeError(f"V15 validation failed {failed}: {values}")
    return values


def apply(save: bool = False) -> dict:
    asset = hou.node(ASSET_PATH)
    if asset is None or asset.type().name() != ASSET_TYPE:
        raise RuntimeError(f"Expected {ASSET_TYPE} at {ASSET_PATH}")
    definition = asset.type().definition()
    if definition is None:
        raise RuntimeError("CityRoad instance has no HDA definition")
    if not definition.libraryFilePath().replace("\\", "/").endswith(DEFINITION_SUFFIX):
        raise RuntimeError("Unexpected CityRoad definition path")
    if not hou.hipFile.path().replace("\\", "/").endswith(HIP_SUFFIX):
        raise RuntimeError("Unexpected CityRoad HIP path")
    core = require_node(asset, CORE_NAME)
    triangulate = require_node(core, "SIDEWALK_PLANAR_TRIANGULATE")
    classify = require_node(core, "SIDEWALK_PLANAR_CLASSIFY")
    mark_seams = require_node(core, "SIDEWALK_PLANAR_MARK_SEAMS")
    existing_mark = core.node(MARK_NODE)
    existing_validate = core.node(VALIDATE_NODE)
    if existing_mark is not None or existing_validate is not None:
        if existing_mark is None or existing_validate is None:
            raise RuntimeError("Partial V15 node set exists")
        if V15_MARKER not in snippet(existing_mark) or V15_MARKER not in snippet(existing_validate):
            raise RuntimeError("Existing V15 nodes have unexpected implementation")
        result = validate(core)
        result.update({"idempotent": True, "saved": False})
        return result

    original_classify = snippet(classify)
    original_remove_outside = triangulate.parm("removeoutsidesilhouette").eval()
    original_classify_inputs = list(classify.inputs())
    original_mark_seams_inputs = list(mark_seams.inputs())
    if sha256_text(original_classify) != CLASSIFY_SHA256:
        raise RuntimeError("V15 classify precondition hash changed")
    if original_remove_outside != 0:
        raise RuntimeError("V15 expected removeoutsidesilhouette=0 baseline")
    if original_classify_inputs[0].name() != "CITYROAD_REPLACE_SIDEWALK_CORNER_WITH_QUAD_STRIPS_V11":
        raise RuntimeError("V15 classify input 0 precondition changed")
    if original_mark_seams_inputs[0].name() != "SIDEWALK_PLANAR_REMOVE_UNUSED_POINTS":
        raise RuntimeError("V15 seam input 0 precondition changed")

    created = []
    try:
        mark = core.createNode("attribwrangle", MARK_NODE)
        created.append(mark)
        mark.setInput(0, original_classify_inputs[0])
        mark.setInput(1, require_node(core, "SIDEWALK_PLANAR_SITE_CLEAN"))
        mark.setInput(2, require_node(core, "SIDEWALK_OPEN_END_SIDE_CONNECTORS"))
        mark.parm("class").set(0)
        mark.parm("snippet").set(MARK_SNIPPET)
        mark.setComment(
            "V15：按开放端左右 connector 与同一场地边构造端头前方排除区；"
            "只标记完整约束三角面，零面积贴边端和道路遮蔽端不删除。")
        mark.setGenericFlag(hou.nodeFlag.DisplayComment, True)
        mark.setColor(hou.Color((0.95, 0.55, 0.15)))
        mark.setPosition(classify.position() + hou.Vector2((-1.4, 0.0)))
        classify.setInput(0, mark)

        count = original_classify.count(CLASSIFY_ANCHOR)
        if count != 1:
            raise RuntimeError(f"V15 classify anchor count changed: {count}")
        classify.parm("snippet").set(original_classify.replace(
            CLASSIFY_ANCHOR, CLASSIFY_REPLACEMENT, 1))

        containment = core.createNode("attribwrangle", VALIDATE_NODE)
        created.append(containment)
        containment.setInput(0, original_mark_seams_inputs[0])
        containment.setInput(1, require_node(core, "SIDEWALK_PLANAR_SITE_CLEAN"))
        containment.setInput(2, require_node(core, "SIDEWALK_OPEN_END_SIDE_CONNECTORS"))
        containment.parm("class").set(0)
        containment.parm("snippet").set(VALIDATE_SNIPPET)
        containment.setComment(
            "V15：删除后累计审计场地 containment 与 terminal-front 残留；"
            "必须为零场地外顶点、零边界穿越、零残留面。")
        containment.setGenericFlag(hou.nodeFlag.DisplayComment, True)
        containment.setColor(hou.Color((0.95, 0.35, 0.15)))
        containment.setPosition(mark_seams.position() + hou.Vector2((-1.4, 0.0)))
        mark_seams.setInput(0, containment)
        triangulate.parm("removeoutsidesilhouette").set(1)

        result = validate(core)
        result.update({"idempotent": False, "saved": False})
        if save:
            definition.updateFromNode(asset)
            hou.hipFile.save()
            result["saved"] = True
        return result
    except Exception:
        triangulate.parm("removeoutsidesilhouette").set(original_remove_outside)
        classify.parm("snippet").set(original_classify)
        for index, input_node in enumerate(original_classify_inputs):
            classify.setInput(index, input_node)
        for index, input_node in enumerate(original_mark_seams_inputs):
            mark_seams.setInput(index, input_node)
        for node in reversed(created):
            if node is not None:
                node.destroy()
        raise


def apply_remote(host: str, port: int, save: bool) -> dict:
    import hrpyc
    connection, _remote_hou = hrpyc.import_remote_module(host, port, "hou")
    try:
        script_dir = str(Path(__file__).resolve().parent).replace("\\", "/")
        connection.execute(
            "import sys, importlib; "
            f"sys.path.insert(0, {script_dir!r}) if {script_dir!r} "
            "not in sys.path else None; "
            "import patch_cityroad_sidewalk_terminal_front_v15 as _pcg_v15; "
            "importlib.reload(_pcg_v15)")
        return dict(connection.eval(f"_pcg_v15.apply(save={save!r})"))
    finally:
        connection.close()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=18811)
    parser.add_argument("--save", action="store_true")
    args = parser.parse_args()
    result = apply_remote(args.host, args.port, args.save)
    print(json.dumps(result, ensure_ascii=False, indent=2, default=list))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
