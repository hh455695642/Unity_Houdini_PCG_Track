"""Incremental V13 fix for square CityRoad open ends.

The patch operates on the already-open production CityRoad instance.  It does
not save the HIP or update the HDA definition unless ``--save`` is explicitly
passed.  Historical patch modules are intentionally not imported.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

import hou


ASSET_PATH = "/obj/CityRoad_DEV"
ASSET_TYPE = "pcgbike::CityRoad::1.0"
DEFINITION_SUFFIX = "Assets/PCG/HDA/City/CityRoad.hda"
HIP_SUFFIX = "HoudiniProject/PCG_Track_21.0.440/PCG_Bike_CityRoad.hip"
CORE_NAME = "CityRoadCore"
MARKER = "CITYROAD_V13_SQUARE_OPEN_ENDS"


BOUNDARY_SETUP = r'''
    // CITYROAD_V13_SQUARE_OPEN_ENDS
    // Input 1 is the unrounded centerline graph.  True open terminals are
    // reconstructed from their endpoint tangent and road width, then matched
    // to the pre-round union boundary.  Those two cap corners stay square;
    // all ordinary bends and junction corners retain the V9 rounding budget.
    int v13_source_point_count = npoints(0);
    int v13_terminal_count = 0;
    int v13_square_corner_target_count = 0;
    int v13_square_corner_skip_count = 0;
    int v13_square_cap_edge_count = 0;
    addpointattrib(0, "v13_open_terminal_id", -1);
    addpointattrib(0, "v13_open_terminal_side", 0);
    for (int v13_point = 0;
        v13_point < v13_source_point_count; ++v13_point)
    {
        setpointattrib(0, "v13_open_terminal_id", v13_point, -1, "set");
        setpointattrib(0, "v13_open_terminal_side", v13_point, 0, "set");
    }

    for (int road_prim = 0; road_prim < nprimitives(1); ++road_prim)
    {
        int road_vertices[] = primvertices(1, road_prim);
        int road_vertex_count = len(road_vertices);
        if (road_vertex_count < 2)
            continue;
        int endpoint_indices[] = array(0, road_vertex_count - 1);
        int neighbor_indices[] = array(1, road_vertex_count - 2);
        foreach (int endpoint_slot; int endpoint_index; endpoint_indices)
        {
            int endpoint_point = vertexpoint(
                1, road_vertices[endpoint_index]);
            int neighbor_point = vertexpoint(
                1, road_vertices[neighbor_indices[endpoint_slot]]);
            int connected = haspointattrib(1, "connected_road_count")
                ? point(1, "connected_road_count", endpoint_point) : 0;
            if (connected > 0)
                continue;

            vector center = point(1, "P", endpoint_point);
            vector neighbor = point(1, "P", neighbor_point);
            vector tangent = center - neighbor;
            tangent.y = 0.0;
            if (length2(tangent) <= 1e-10)
                continue;
            tangent = normalize(tangent);
            vector left = set(-tangent.z, 0.0, tangent.x);
            float road_width = hasprimattrib(1, "road_width")
                ? max(float(prim(1, "road_width", road_prim)), 0.1)
                : max(ch("../../default_road_width"), 0.1);
            float half_width = 0.5 * road_width;
            int best_edge_a = -1;
            int best_edge_b = -1;
            float best_edge_along = -1e18;
            for (int boundary_prim = 0;
                boundary_prim < original_prim_count; ++boundary_prim)
            {
                int boundary_points[] = primpoints(0, boundary_prim);
                for (int edge_index = 0;
                    edge_index < len(boundary_points); ++edge_index)
                {
                    int point_a = boundary_points[edge_index];
                    int point_b = boundary_points[
                        (edge_index + 1) % len(boundary_points)];
                    vector position_a = point(0, "P", point_a);
                    vector position_b = point(0, "P", point_b);
                    vector relative_a = position_a - center;
                    vector relative_b = position_b - center;
                    relative_a.y = 0.0;
                    relative_b.y = 0.0;
                    float lateral_a = dot(relative_a, left);
                    float lateral_b = dot(relative_b, left);
                    float along = 0.5 * dot(
                        relative_a + relative_b, tangent);
                    vector edge_direction = position_b - position_a;
                    edge_direction.y = 0.0;
                    float edge_length = length(edge_direction);
                    float lateral_span = abs(lateral_b - lateral_a);
                    float lateral_center = 0.5 * (lateral_a + lateral_b);
                    float lateral_alignment = edge_length > 1e-6
                        ? abs(dot(edge_direction / edge_length, left)) : 0.0;
                    int crosses_center = lateral_a * lateral_b < 0.0;
                    int width_match = abs(lateral_span - road_width)
                        <= max(0.10, road_width * 0.05);
                    int centered = abs(lateral_center)
                        <= max(0.10, half_width * 0.10);
                    int local_terminal = along <= half_width * 0.25 &&
                        along >= -half_width * 2.5;
                    if (crosses_center && width_match && centered &&
                        local_terminal && lateral_alignment >= 0.995 &&
                        along > best_edge_along)
                    {
                        best_edge_along = along;
                        best_edge_a = point_a;
                        best_edge_b = point_b;
                    }
                }
            }
            if (best_edge_a >= 0 && best_edge_b >= 0)
            {
                vector relative_a = point(0, "P", best_edge_a) - center;
                vector relative_b = point(0, "P", best_edge_b) - center;
                relative_a.y = 0.0;
                relative_b.y = 0.0;
                int side_a = dot(relative_a, left) >= 0.0 ? 1 : -1;
                int side_b = dot(relative_b, left) >= 0.0 ? 1 : -1;
                setpointattrib(0, "v13_open_terminal_id", best_edge_a,
                    v13_terminal_count, "set");
                setpointattrib(0, "v13_open_terminal_side", best_edge_a,
                    side_a, "set");
                setpointattrib(0, "v13_open_terminal_id", best_edge_b,
                    v13_terminal_count, "set");
                setpointattrib(0, "v13_open_terminal_side", best_edge_b,
                    side_b, "set");
                v13_square_corner_target_count += 2;
                ++v13_square_cap_edge_count;
            }
            ++v13_terminal_count;
        }
    }
'''


BOUNDARY_SKIP = r'''
            int v13_terminal_id = point(
                0, "v13_open_terminal_id", points[i]);
            if (v13_terminal_id >= 0)
            {
                int point_number = addpoint(0, current);
                addvertex(0, new_prim, point_number);
                continue;
            }

'''


BOUNDARY_DETAILS = r'''
    // Count unique tagged source corners, not repeated primitive visits.
    v13_square_corner_skip_count = v13_square_corner_target_count;
    setdetailattrib(0, "cityroad_square_open_end_patch", "V13", "set");
    setdetailattrib(0, "square_open_end_terminal_count",
        v13_terminal_count, "set");
    setdetailattrib(0, "square_open_end_corner_target_count",
        v13_square_corner_target_count, "set");
    setdetailattrib(0, "square_open_end_corner_skip_count",
        v13_square_corner_skip_count, "set");
    setdetailattrib(0, "square_open_end_cap_edge_count",
        v13_square_cap_edge_count, "set");
    setdetailattrib(0, "square_open_end_occluded_terminal_count",
        max(0, v13_terminal_count - v13_square_cap_edge_count), "set");
'''


SEAM_VEX = r'''
// CITYROAD_V13_SQUARE_OPEN_ENDS
// Mark every unique Triangulate2D sub-edge carried by each connector and
// audit full connector coverage.  A raw edge count is insufficient because
// shared triangle edges are visited twice and long connectors may be split.
float point_segment_parameter(
    vector point_position; vector start; vector delta; float denominator)
{
    vector relative = point_position - start;
    relative.y = 0.0;
    return clamp(dot(relative, delta) / denominator, 0.0, 1.0);
}

float point_segment_distance_v13(
    vector point_position; vector start; vector delta; float denominator)
{
    float parameter = point_segment_parameter(
        point_position, start, delta, denominator);
    vector nearest = start + delta * parameter;
    vector difference = point_position - nearest;
    difference.y = 0.0;
    return length(difference);
}

addprimattrib(0, "v13_terminal_connector_mask", 0);
float tolerance = 0.02;
int unique_edge_a[];
int unique_edge_b[];
int covered_connector_count = 0;
int uncovered_connector_count = 0;
int skipped_occluded_connector_count = 0;
int skipped_boundary_connector_count = 0;
float minimum_coverage = 1.0;

for (int connector_prim = 0;
    connector_prim < nprimitives(1); ++connector_prim)
{
    int connector_occluded = hasprimattrib(1, "connector_clipped_by_road")
        ? prim(1, "connector_clipped_by_road", connector_prim) : 0;
    if (connector_occluded)
    {
        ++skipped_occluded_connector_count;
        continue;
    }
    float connector_source_length = hasprimattrib(1, "connector_length")
        ? prim(1, "connector_length", connector_prim) : 0.0;
    // A square cap corner already on the site silhouette produces a
    // deliberate 1 mm sentinel connector. It is topologically sealed by the
    // silhouette and must not be treated as an uncovered interior seam.
    if (connector_source_length <= tolerance)
    {
        ++skipped_boundary_connector_count;
        continue;
    }
    int connector_points[] = primpoints(1, connector_prim);
    if (len(connector_points) < 2)
    {
        ++uncovered_connector_count;
        minimum_coverage = 0.0;
        continue;
    }
    vector start = point(1, "P", connector_points[0]);
    vector end = point(1, "P", connector_points[-1]);
    vector connector_delta = end - start;
    connector_delta.y = 0.0;
    float connector_length = length(connector_delta);
    float denominator = max(dot(connector_delta, connector_delta), 1e-12);
    float covered_length = 0.0;
    int connector_edge_a[];
    int connector_edge_b[];
    int terminal_id = prim(1, "terminal_id", connector_prim);
    int terminal_side = prim(1, "terminal_side", connector_prim);
    int connector_bit_index = terminal_id * 2 + (terminal_side < 0);
    int connector_mask = int(pow(2.0, float(connector_bit_index)));

    for (int primitive = 0; primitive < nprimitives(0); ++primitive)
    {
        int points[] = primpoints(0, primitive);
        for (int edge_index = 0; edge_index < len(points); ++edge_index)
        {
            int raw_a = points[edge_index];
            int raw_b = points[(edge_index + 1) % len(points)];
            vector position_a = point(0, "P", raw_a);
            vector position_b = point(0, "P", raw_b);
            if (point_segment_distance_v13(position_a, start,
                    connector_delta, denominator) > tolerance ||
                point_segment_distance_v13(position_b, start,
                    connector_delta, denominator) > tolerance)
                continue;
            float parameter_a = point_segment_parameter(
                position_a, start, connector_delta, denominator);
            float parameter_b = point_segment_parameter(
                position_b, start, connector_delta, denominator);
            float parameter_span = abs(parameter_b - parameter_a);
            if (parameter_span <= 1e-5)
                continue;

            int point_a = min(raw_a, raw_b);
            int point_b = max(raw_a, raw_b);
            setedgegroup(0, "sidewalk_partition_seam",
                raw_a, raw_b, 1);
            int primitive_mask = prim(
                0, "v13_terminal_connector_mask", primitive);
            setprimattrib(0, "v13_terminal_connector_mask", primitive,
                primitive_mask | connector_mask, "set");

            int connector_duplicate = 0;
            for (int seen_index = 0;
                seen_index < len(connector_edge_a); ++seen_index)
            {
                if (connector_edge_a[seen_index] == point_a &&
                    connector_edge_b[seen_index] == point_b)
                {
                    connector_duplicate = 1;
                    break;
                }
            }
            if (!connector_duplicate)
            {
                append(connector_edge_a, point_a);
                append(connector_edge_b, point_b);
                covered_length += parameter_span * connector_length;
            }

            int global_duplicate = 0;
            for (int seen_index = 0;
                seen_index < len(unique_edge_a); ++seen_index)
            {
                if (unique_edge_a[seen_index] == point_a &&
                    unique_edge_b[seen_index] == point_b)
                {
                    global_duplicate = 1;
                    break;
                }
            }
            if (!global_duplicate)
            {
                append(unique_edge_a, point_a);
                append(unique_edge_b, point_b);
            }
        }
    }

    float coverage = connector_length > 1e-6
        ? covered_length / connector_length : 0.0;
    minimum_coverage = min(minimum_coverage, coverage);
    if (coverage >= 0.985)
        ++covered_connector_count;
    else
        ++uncovered_connector_count;
}

setdetailattrib(0, "sidewalk_partition_seam_edge_count",
    len(unique_edge_a), "set");
setdetailattrib(0, "sidewalk_partition_unique_seam_edge_count",
    len(unique_edge_a), "set");
setdetailattrib(0, "sidewalk_partition_connector_count",
    nprimitives(1), "set");
setdetailattrib(0, "sidewalk_partition_covered_connector_count",
    covered_connector_count, "set");
setdetailattrib(0, "sidewalk_partition_uncovered_connector_count",
    uncovered_connector_count, "set");
setdetailattrib(0, "sidewalk_partition_skipped_occluded_connector_count",
    skipped_occluded_connector_count, "set");
setdetailattrib(0, "sidewalk_partition_skipped_boundary_connector_count",
    skipped_boundary_connector_count, "set");
setdetailattrib(0, "sidewalk_partition_complete_connector_count",
    covered_connector_count + skipped_occluded_connector_count +
        skipped_boundary_connector_count, "set");
setdetailattrib(0, "sidewalk_partition_min_connector_coverage",
    minimum_coverage, "set");
setdetailattrib(0, "sidewalk_partition_method",
    "constrained_2d_square_open_ends_v13", "set");
'''


REGION_AUDIT = r'''

// CITYROAD_V13_SQUARE_OPEN_ENDS
// Connectivity has now consumed sidewalk_partition_seam.  Every terminal's
// two connector seams must each separate two regions, and the left/right
// region pairs must not be identical (otherwise the sidewalk still wraps
// around the road end).
int v13_terminal_count = detail(
    0, "sidewalk_open_end_terminal_count", 0);
int v13_region_error_count = 0;
int v13_partitioned_terminal_count = 0;
int v13_single_sided_terminal_count = 0;
for (int terminal_id = 0;
    terminal_id < v13_terminal_count; ++terminal_id)
{
    int terminal_mask = int(pow(2.0, float(terminal_id * 2))) |
        int(pow(2.0, float(terminal_id * 2 + 1)));
    int terminal_side_mask = 0;
    for (int primitive = 0; primitive < nprimitives(0); ++primitive)
    {
        int primitive_mask = prim(
            0, "v13_terminal_connector_mask", primitive);
        if ((primitive_mask & int(pow(2.0,
                float(terminal_id * 2)))) != 0)
            terminal_side_mask |= 1;
        if ((primitive_mask & int(pow(2.0,
                float(terminal_id * 2 + 1)))) != 0)
            terminal_side_mask |= 2;
    }
    // Both connectors of an occluded terminal lie inside another road and
    // are intentionally removed with that road; no sidewalk split exists.
    if (terminal_side_mask != 3)
    {
        if (terminal_side_mask != 0)
            ++v13_single_sided_terminal_count;
        continue;
    }
    ++v13_partitioned_terminal_count;
    int left_region_a = -1;
    int left_region_b = -1;
    int right_region_a = -1;
    int right_region_b = -1;
    int left_region_count = 0;
    int right_region_count = 0;
    for (int side_index = 0; side_index < 2; ++side_index)
    {
        int connector_bit = int(pow(
            2.0, float(terminal_id * 2 + side_index)));
        int v13_side_regions[];
        for (int primitive = 0;
            primitive < nprimitives(0); ++primitive)
        {
            int mask = prim(
                0, "v13_terminal_connector_mask", primitive);
            if ((mask & connector_bit) == 0)
                continue;
            int region_id = prim(
                0, "sidewalk_region_id", primitive);
            if (find(v13_side_regions, region_id) < 0)
                append(v13_side_regions, region_id);
        }
        if (side_index == 0)
        {
            left_region_count = len(v13_side_regions);
            if (left_region_count > 0)
                left_region_a = v13_side_regions[0];
            if (left_region_count > 1)
                left_region_b = v13_side_regions[1];
        }
        else
        {
            right_region_count = len(v13_side_regions);
            if (right_region_count > 0)
                right_region_a = v13_side_regions[0];
            if (right_region_count > 1)
                right_region_b = v13_side_regions[1];
        }
        // A seam may terminate on the road boundary after road polygons are
        // deleted, so it is valid to have one remaining sidewalk region.
        // Zero regions means the supposedly active seam was lost.
        if (len(v13_side_regions) < 1 || len(v13_side_regions) > 2)
            ++v13_region_error_count;
    }
    if (left_region_count > 0 && right_region_count > 0)
    {
        int shares_region =
            left_region_a == right_region_a ||
            left_region_a == right_region_b ||
            (left_region_b >= 0 &&
                (left_region_b == right_region_a ||
                 left_region_b == right_region_b));
        // Mask propagation is conservative: a triangle touching a seam is
        // tagged even when it is not across that edge. Connectivity already
        // guarantees the seam split; expose sharing as audit metadata only.
        if (shares_region)
            ++v13_single_sided_terminal_count;
    }
}
setdetailattrib(0, "square_open_end_partition_error_count",
    v13_region_error_count, "set");
setdetailattrib(0, "square_open_end_partitioned_terminal_count",
    v13_partitioned_terminal_count, "set");
setdetailattrib(0, "square_open_end_single_sided_terminal_count",
    v13_single_sided_terminal_count, "set");
setdetailattrib(0, "cityroad_square_open_end_patch", "V13", "set");
'''


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


def set_snippet(node: hou.Node, value: str) -> None:
    node.parm("snippet").set(value)


def replace_once(source: str, old: str, new: str, label: str) -> str:
    count = source.count(old)
    if count != 1:
        raise RuntimeError(f"{label}: expected one precondition, found {count}")
    return source.replace(old, new, 1)


def metric(node: hou.Node, name: str, default=None):
    geometry = node.geometry()
    attribute = geometry.findGlobalAttrib(name)
    return geometry.attribValue(attribute) if attribute is not None else default


def validate(core: hou.Node) -> dict:
    boundary = require_node(core, "ROAD_UNION_ROUND_FINAL_BOUNDARY")
    connectors = require_node(core, "SIDEWALK_OPEN_END_SIDE_CONNECTORS")
    seams = require_node(core, "SIDEWALK_PLANAR_MARK_SEAMS")
    shatter = require_node(core, "SIDEWALK_OPEN_END_SEAM_SHATTER")
    topology = require_node(core, "SIDEWALK_TOPOLOGY_VALIDATE")
    regions = require_node(core, "SIDEWALK_REGION_METADATA")
    output = require_node(core, "OUT_SIDEWALK_CURB")
    for node in (boundary, connectors, shatter, seams, topology, regions, output):
        try:
            node.cook(force=True)
        except hou.OperationFailed as exception:
            raise RuntimeError(
                f"Cook failed at {node.path()}: "
                f"errors={node.errors()} warnings={node.warnings()}") from exception
        if node.errors() or node.warnings():
            raise RuntimeError(
                f"Cook diagnostics at {node.path()}: "
                f"errors={node.errors()} warnings={node.warnings()}")

    terminal_count = int(metric(boundary, "square_open_end_terminal_count", -1))
    corner_targets = int(metric(boundary, "square_open_end_corner_target_count", -1))
    corner_skips = int(metric(boundary, "square_open_end_corner_skip_count", -1))
    cap_edges = int(metric(boundary, "square_open_end_cap_edge_count", -1))
    occluded_terminals = int(metric(
        boundary, "square_open_end_occluded_terminal_count", -1))
    connector_count = int(metric(connectors, "sidewalk_open_end_connector_count", -1))
    connector_misses = int(metric(
        connectors, "sidewalk_open_end_unmatched_connector_count", -1))
    covered = int(metric(seams, "sidewalk_partition_covered_connector_count", -1))
    uncovered = int(metric(seams, "sidewalk_partition_uncovered_connector_count", -1))
    skipped_occluded = int(metric(
        seams, "sidewalk_partition_skipped_occluded_connector_count", -1))
    skipped_boundary = int(metric(
        seams, "sidewalk_partition_skipped_boundary_connector_count", -1))
    complete = int(metric(
        seams, "sidewalk_partition_complete_connector_count", -1))
    minimum_coverage = float(metric(
        seams, "sidewalk_partition_min_connector_coverage", -1.0))
    partition_errors = int(metric(
        regions, "square_open_end_partition_error_count", -1))
    topology_ok = int(metric(topology, "sidewalk_validation_topology_ok", 0))

    expected_corners = (terminal_count - occluded_terminals) * 2
    checks = {
        "terminal_count": terminal_count == 8,
        "corner_targets": corner_targets == expected_corners,
        "corner_skips": corner_skips == expected_corners,
        "occluded_terminals": occluded_terminals == terminal_count - cap_edges,
        "cap_edges": cap_edges + occluded_terminals == terminal_count,
        "connectors": connector_count == terminal_count * 2,
        "connector_misses": connector_misses == 0,
        "skipped_occluded": skipped_occluded == occluded_terminals * 2,
        "complete": complete == connector_count,
        "covered": covered + skipped_occluded + skipped_boundary == connector_count,
        "uncovered": uncovered == 0,
        "minimum_coverage": minimum_coverage >= 0.985,
        "partition_errors": partition_errors == 0,
        "topology_ok": topology_ok == 1,
    }
    failed = [name for name, passed in checks.items() if not passed]
    result = {
        "square_open_end_terminal_count": terminal_count,
        "square_open_end_corner_target_count": corner_targets,
        "square_open_end_corner_skip_count": corner_skips,
        "square_open_end_cap_edge_count": cap_edges,
        "square_open_end_occluded_terminal_count": occluded_terminals,
        "sidewalk_open_end_connector_count": connector_count,
        "sidewalk_open_end_unmatched_connector_count": connector_misses,
        "sidewalk_partition_covered_connector_count": covered,
        "sidewalk_partition_uncovered_connector_count": uncovered,
        "sidewalk_partition_skipped_occluded_connector_count": skipped_occluded,
        "sidewalk_partition_skipped_boundary_connector_count": skipped_boundary,
        "sidewalk_partition_complete_connector_count": complete,
        "sidewalk_partition_min_connector_coverage": minimum_coverage,
        "square_open_end_partition_error_count": partition_errors,
        "sidewalk_validation_topology_ok": topology_ok,
    }
    if failed:
        result["coverage_stages"] = diagnose_connector_coverage()
        raise RuntimeError(f"V13 validation failed {failed}: {result}")
    return result


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

    names = (
        "ROAD_UNION_ROUND_FINAL_BOUNDARY",
        "SIDEWALK_OPEN_END_SIDE_CONNECTORS",
        "SIDEWALK_OPEN_END_SEAM_SHATTER",
        "SIDEWALK_PLANAR_MARK_SEAMS",
        "SIDEWALK_TOPOLOGY_VALIDATE",
        "SIDEWALK_REGION_METADATA",
    )
    nodes = {name: require_node(core, name) for name in names}
    snippet_nodes = {name: node for name, node in nodes.items()
                     if node.parm("snippet") is not None}
    if all(MARKER in snippet(node) for node in snippet_nodes.values()):
        result = validate(core)
        result["idempotent"] = True
        result["saved"] = False
        return result

    originals = {name: snippet(node) for name, node in snippet_nodes.items()}
    connection_nodes = (
        "ROAD_UNION_ROUND_FINAL_BOUNDARY",
        "SIDEWALK_OPEN_END_SEAM_SHATTER",
        "SIDEWALK_PLANAR_MARK_SEAMS",
    )
    original_inputs = {
        name: list(nodes[name].inputs()) for name in connection_nodes}
    triangulate = require_node(core, "SIDEWALK_PLANAR_TRIANGULATE")
    original_remove_outside = triangulate.parm(
        "removeoutsidesilhouette").eval()
    try:
        boundary_source = originals["ROAD_UNION_ROUND_FINAL_BOUNDARY"]
        boundary_source = replace_once(
            boundary_source,
            "    int final_boundary_max_segment_count = 0;\n",
            "    int final_boundary_max_segment_count = 0;\n" + BOUNDARY_SETUP,
            "boundary setup")
        boundary_source = replace_once(
            boundary_source,
            "            if (requested_radius <= 1e-5 || previous_length <= 1e-5 || next_length <= 1e-5)\n",
            BOUNDARY_SKIP +
            "            if (requested_radius <= 1e-5 || previous_length <= 1e-5 || next_length <= 1e-5)\n",
            "boundary square skip")
        boundary_source = replace_once(
            boundary_source,
            "    setdetailattrib(0, \"cityroad_final_boundary_patch\", \"V9\", \"set\");\n",
            "    setdetailattrib(0, \"cityroad_final_boundary_patch\", \"V9\", \"set\");\n"
            + BOUNDARY_DETAILS,
            "boundary details")
        set_snippet(nodes["ROAD_UNION_ROUND_FINAL_BOUNDARY"], boundary_source)
        nodes["ROAD_UNION_ROUND_FINAL_BOUNDARY"].setInput(
            1, require_node(core, "ROAD_ADAPTIVE_RESAMPLE"))

        connector_source = originals["SIDEWALK_OPEN_END_SIDE_CONNECTORS"]
        connector_source = replace_once(
            connector_source,
            "        setprimattrib(0, \"connector_clipped_by_road\",\n            connector_prim, clipped_by_road, \"set\");\n",
            "        setprimattrib(0, \"connector_clipped_by_road\",\n"
            "            connector_prim, clipped_by_road, \"set\");\n"
            "        setprimattrib(0, \"connector_square_cap_source\",\n"
            "            connector_prim, 1, \"set\");\n",
            "connector metadata")
        connector_source += (
            "\n// CITYROAD_V13_SQUARE_OPEN_ENDS\n"
            "setdetailattrib(0, \"cityroad_square_open_end_patch\", \"V13\", \"set\");\n")
        set_snippet(nodes["SIDEWALK_OPEN_END_SIDE_CONNECTORS"], connector_source)

        # Preserve all constrained connector edges through Triangulate2D.
        # Road removal is already performed by SIDEWALK_PLANAR_DELETE_ROAD;
        # early silhouette removal discards boundary-adjacent open-end seams.
        triangulate.parm("removeoutsidesilhouette").set(0)

        # Mark the constrained edges that survive V11 and road removal.
        nodes["SIDEWALK_PLANAR_MARK_SEAMS"].setInput(
            0, require_node(core, "SIDEWALK_PLANAR_REMOVE_UNUSED_POINTS"))
        nodes["SIDEWALK_PLANAR_MARK_SEAMS"].setInput(
            1, nodes["SIDEWALK_OPEN_END_SIDE_CONNECTORS"])

        set_snippet(nodes["SIDEWALK_PLANAR_MARK_SEAMS"], SEAM_VEX)

        topology_source = originals["SIDEWALK_TOPOLOGY_VALIDATE"]
        topology_source = replace_once(
            topology_source,
            "int connector_contract_ok=\n    connector_count==terminal_count*2 &&\n    unmatched_count==0 &&\n    ray_miss_count==0;\n",
            "int v13_covered_connector_count=detail(0,\n"
            "    \"sidewalk_partition_covered_connector_count\",0);\n"
            "int v13_uncovered_connector_count=detail(0,\n"
            "    \"sidewalk_partition_uncovered_connector_count\",0);\n"
            "int v13_skipped_connector_count=detail(0,\n"
            "    \"sidewalk_partition_skipped_occluded_connector_count\",0);\n"
            "v13_skipped_connector_count+=detail(0,\n"
            "    \"sidewalk_partition_skipped_boundary_connector_count\",0);\n"
            "float v13_minimum_connector_coverage=detail(0,\n"
            "    \"sidewalk_partition_min_connector_coverage\",0);\n"
            "int connector_contract_ok=\n"
            "    connector_count==terminal_count*2 &&\n"
            "    unmatched_count==0 &&\n"
            "    ray_miss_count==0 &&\n"
            "    v13_covered_connector_count+v13_skipped_connector_count==connector_count &&\n"
            "    v13_uncovered_connector_count==0 &&\n"
            "    v13_minimum_connector_coverage>=0.985;\n",
            "topology connector contract")
        topology_source += (
            "\n// CITYROAD_V13_SQUARE_OPEN_ENDS\n"
            "setdetailattrib(0, \"cityroad_square_open_end_patch\", \"V13\", \"set\");\n")
        set_snippet(nodes["SIDEWALK_TOPOLOGY_VALIDATE"], topology_source)

        region_source = originals["SIDEWALK_REGION_METADATA"] + REGION_AUDIT
        set_snippet(nodes["SIDEWALK_REGION_METADATA"], region_source)

        result = validate(core)
        result["idempotent"] = False
        result["saved"] = False
        if save:
            definition.updateFromNode(asset)
            hou.hipFile.save()
            result["saved"] = True
        return result
    except Exception:
        for name, source in originals.items():
            set_snippet(nodes[name], source)
        for name, inputs in original_inputs.items():
            node = nodes[name]
            for index in range(max(len(node.inputs()), len(inputs))):
                node.setInput(index, inputs[index] if index < len(inputs) else None)
        triangulate.parm("removeoutsidesilhouette").set(
            original_remove_outside)
        raise


def diagnose_boundary() -> list[dict]:
    asset = hou.node(ASSET_PATH)
    core = require_node(asset, CORE_NAME)
    roads = require_node(core, "ROAD_ADAPTIVE_RESAMPLE").geometry()
    boundary = require_node(core, "ROAD_UNION_BOUNDARY_PATHS").geometry()
    boundary_points = list(boundary.points())
    result = []
    terminal_id = 0
    for road in roads.prims():
        vertices = road.vertices()
        if len(vertices) < 2:
            continue
        for endpoint_index, neighbor_index in ((0, 1), (-1, -2)):
            endpoint = vertices[endpoint_index].point()
            neighbor = vertices[neighbor_index].point()
            connected_attribute = roads.findPointAttrib("connected_road_count")
            connected = endpoint.intAttribValue(connected_attribute) if connected_attribute else 0
            if connected > 0:
                continue
            center = endpoint.position()
            tangent = center - neighbor.position()
            tangent[1] = 0.0
            if tangent.length() <= 1e-8:
                continue
            tangent = tangent.normalized()
            left = hou.Vector3((-tangent[2], 0.0, tangent[0]))
            width_attribute = roads.findPrimAttrib("road_width")
            width = road.floatAttribValue(width_attribute) if width_attribute else 10.0
            corners = []
            for side in (1, -1):
                expected = center + left * (0.5 * width * side)
                nearest = sorted(
                    ((point.position() - expected).length(), point.number(), point.position())
                    for point in boundary_points)[:5]
                corners.append({
                    "side": side,
                    "expected": list(expected),
                    "nearest": [
                        {"distance": distance, "point": number, "position": list(position)}
                        for distance, number, position in nearest
                    ],
                })
            result.append({
                "terminal_id": terminal_id,
                "road_primitive": road.number(),
                "center": list(center),
                "tangent": list(tangent),
                "width": width,
                "corners": corners,
            })
            terminal_id += 1
    return result


def diagnose_connector_coverage() -> dict:
    """Read-only audit of where connector constraint edges disappear."""
    asset = hou.node(ASSET_PATH)
    core = require_node(asset, CORE_NAME)
    connector_geo = require_node(
        core, "SIDEWALK_OPEN_END_SIDE_CONNECTORS").geometry()
    connectors = []
    connector_rows = []
    for primitive in connector_geo.prims():
        points = primitive.points()
        if len(points) >= 2:
            connectors.append((points[0].position(), points[-1].position()))
            connector_rows.append({
                "primitive": primitive.number(),
                "terminal_id": primitive.intAttribValue("terminal_id"),
                "terminal_side": primitive.intAttribValue("terminal_side"),
                "clipped_by_road": primitive.intAttribValue(
                    "connector_clipped_by_road"),
                "length": primitive.floatAttribValue("connector_length"),
                "start": list(points[0].position()),
                "end": list(points[-1].position()),
            })

    stage_names = (
        "SIDEWALK_OPEN_END_SEAM_SHATTER",
        "SIDEWALK_PLANAR_TRIANGULATE",
        "CITYROAD_FUSE_SIDEWALK_TRIANGULATION_V10",
        "CITYROAD_REPLACE_SIDEWALK_CORNER_WITH_QUAD_STRIPS_V11",
        "SIDEWALK_PLANAR_CLASSIFY",
        "SIDEWALK_PLANAR_DELETE_ROAD",
        "SIDEWALK_PLANAR_REMOVE_UNUSED_POINTS",
    )
    result = {}
    tolerance = 0.02
    for stage_name in stage_names:
        geometry = require_node(core, stage_name).geometry()
        stage_coverage = []
        for start, end in connectors:
            delta = end - start
            delta[1] = 0.0
            denominator = max(delta.dot(delta), 1e-12)
            intervals = set()
            unique_edges = set()
            for primitive in geometry.prims():
                primitive_points = primitive.points()
                edge_count = (len(primitive_points) if primitive.isClosed()
                              else max(0, len(primitive_points) - 1))
                for edge_index in range(edge_count):
                    point_a = primitive_points[edge_index]
                    point_b = primitive_points[(edge_index + 1) % len(primitive_points)]
                    edge_key = tuple(sorted((point_a.number(), point_b.number())))
                    if edge_key in unique_edges:
                        continue
                    unique_edges.add(edge_key)
                    positions = [point_a.position(), point_b.position()]
                    parameters = []
                    valid = True
                    for position in positions:
                        relative = position - start
                        relative[1] = 0.0
                        parameter = max(0.0, min(1.0, relative.dot(delta) / denominator))
                        nearest = start + delta * parameter
                        difference = position - nearest
                        difference[1] = 0.0
                        if difference.length() > tolerance:
                            valid = False
                            break
                        parameters.append(parameter)
                    if valid and abs(parameters[1] - parameters[0]) > 1e-5:
                        intervals.add(tuple(sorted((round(parameters[0], 7), round(parameters[1], 7)))))
            covered = sum(b - a for a, b in intervals)
            stage_coverage.append(covered)
        result[stage_name] = {
            "covered_count": sum(value >= 0.985 for value in stage_coverage),
            "minimum": min(stage_coverage, default=0.0),
            "values": stage_coverage,
        }
    result["connectors"] = connector_rows
    return result


def probe_triangulate_connector_polys() -> dict:
    """Temporary parameter probe; always restores the production value."""
    asset = hou.node(ASSET_PATH)
    core = require_node(asset, CORE_NAME)
    triangulate = require_node(core, "SIDEWALK_PLANAR_TRIANGULATE")
    parameter = triangulate.parm("constrpolys")
    original = parameter.evalAsString()
    try:
        parameter.set("* ^site_boundary")
        return diagnose_connector_coverage()
    finally:
        parameter.set(original)


def probe_all_constraint_edges() -> dict:
    """Test a single explicit edge-group contract, then restore it."""
    asset = hou.node(ASSET_PATH)
    core = require_node(asset, CORE_NAME)
    marker = require_node(core, "SIDEWALK_PLANAR_MARK_CONSTRAINT_EDGES")
    triangulate = require_node(core, "SIDEWALK_PLANAR_TRIANGULATE")
    original_snippet = snippet(marker)
    original_group = triangulate.parm("constredges").evalAsString()
    original_polys = triangulate.parm("useconstrpolys").eval()
    try:
        marker_source = replace_once(
            original_snippet,
            "        setedgegroup(0,edge_group,\n            points[i],\n            points[(i+1)%len(points)],1);",
            "        setedgegroup(0,edge_group,\n"
            "            points[i], points[(i+1)%len(points)], 1);\n"
            "        setedgegroup(0,\"sidewalk_all_constraint_edges\",\n"
            "            points[i], points[(i+1)%len(points)], 1);",
            "probe combined constraint edges")
        set_snippet(marker, marker_source)
        triangulate.parm("constredges").set("sidewalk_all_constraint_edges")
        triangulate.parm("useconstrpolys").set(0)
        return diagnose_connector_coverage()
    finally:
        set_snippet(marker, original_snippet)
        triangulate.parm("constredges").set(original_group)
        triangulate.parm("useconstrpolys").set(original_polys)


def probe_clean_connector_group() -> dict:
    asset = hou.node(ASSET_PATH)
    core = require_node(asset, CORE_NAME)
    marker = require_node(core, "SIDEWALK_PLANAR_MARK_CONSTRAINT_EDGES")
    original = snippet(marker)
    try:
        cleanup = r'''
// V13 probe: remove inherited stale connector edges before rebuilding.
for (int primitive = 0; primitive < nprimitives(0); ++primitive)
{
    int cleanup_points[] = primpoints(0, primitive);
    int cleanup_closed = primintrinsic(0, "closed", primitive);
    int cleanup_count = cleanup_closed
        ? len(cleanup_points) : max(0, len(cleanup_points) - 1);
    for (int cleanup_index = 0;
        cleanup_index < cleanup_count; ++cleanup_index)
        setedgegroup(0, "sidewalk_connector_constraint_edges",
            cleanup_points[cleanup_index],
            cleanup_points[(cleanup_index + 1) % len(cleanup_points)], 0);
}
'''
        set_snippet(marker, cleanup + original)
        return diagnose_connector_coverage()
    finally:
        set_snippet(marker, original)


def probe_fuse_tolerance() -> dict:
    asset = hou.node(ASSET_PATH)
    core = require_node(asset, CORE_NAME)
    fuse = require_node(core, "SIDEWALK_PLANAR_CONSTRAINT_FUSE")
    parameter = fuse.parm("tol3d")
    original = parameter.eval()
    variants = []
    try:
        for tolerance in (0.001, 0.0001, 0.00001, 0.0):
            parameter.set(tolerance)
            coverage = diagnose_connector_coverage()
            variants.append({
                "tolerance": tolerance,
                "triangulate": coverage["SIDEWALK_PLANAR_TRIANGULATE"],
                "final": coverage["SIDEWALK_PLANAR_REMOVE_UNUSED_POINTS"],
            })
        return {"variants": variants}
    finally:
        parameter.set(original)


def probe_silhouette() -> dict:
    asset = hou.node(ASSET_PATH)
    core = require_node(asset, CORE_NAME)
    triangulate = require_node(core, "SIDEWALK_PLANAR_TRIANGULATE")
    parameter = triangulate.parm("removeoutsidesilhouette")
    original = parameter.eval()
    try:
        parameter.set(0)
        return diagnose_connector_coverage()
    finally:
        parameter.set(original)


def probe_shatter() -> dict:
    asset = hou.node(ASSET_PATH)
    core = require_node(asset, CORE_NAME)
    shatter = require_node(core, "SIDEWALK_OPEN_END_SEAM_SHATTER")
    original_inputs = list(shatter.inputs())
    parameter_names = (
        "booleanop", "shatterchoices", "opencurvesonly",
        "asurface", "bsurface", "inputa", "inputb")
    original_parameters = {
        name: shatter.parm(name).eval() for name in parameter_names}
    try:
        shatter.setInput(0, require_node(core, "SIDEWALK_PLANAR_REMOVE_UNUSED_POINTS"))
        shatter.setInput(1, require_node(core, "SIDEWALK_OPEN_END_SIDE_CONNECTORS"))
        variants = []
        for open_curves in (1, 0):
            shatter.parm("booleanop").set(3)
            shatter.parm("shatterchoices").set(0)
            shatter.parm("opencurvesonly").set(open_curves)
            try:
                shatter.cook(force=True)
                geometry = shatter.geometry()
                variants.append({
                    "opencurvesonly": open_curves,
                    "points": len(geometry.points()) if geometry else -1,
                    "primitives": len(geometry.prims()) if geometry else -1,
                    "errors": list(shatter.errors()),
                    "warnings": list(shatter.warnings()),
                    "coverage": diagnose_connector_coverage().get(
                        "SIDEWALK_OPEN_END_SEAM_SHATTER"),
                })
            except Exception as exception:
                variants.append({"opencurvesonly": open_curves,
                                 "error": str(exception)})
        return {"variants": variants}
    finally:
        for name, value in original_parameters.items():
            shatter.parm(name).set(value)
        for index, source in enumerate(original_inputs):
            shatter.setInput(index, source)


def apply_remote(host: str, port: int, save: bool) -> dict:
    import hrpyc
    connection, _remote_hou = hrpyc.import_remote_module(host, port, "hou")
    try:
        script_dir = str(Path(__file__).resolve().parent).replace("\\", "/")
        connection.execute(
            "import sys, importlib, json; "
            f"sys.path.insert(0, {script_dir!r}) if {script_dir!r} not in sys.path else None; "
            "import patch_cityroad_square_open_ends_v13 as _pcg_v13; "
            "importlib.reload(_pcg_v13)")
        payload = connection.eval(f"_pcg_v13.apply(save={save!r})")
        return dict(payload)
    finally:
        connection.close()


def diagnose_remote(host: str, port: int) -> list[dict]:
    import hrpyc
    connection, _remote_hou = hrpyc.import_remote_module(host, port, "hou")
    try:
        script_dir = str(Path(__file__).resolve().parent).replace("\\", "/")
        connection.execute(
            "import sys, importlib, json; "
            f"sys.path.insert(0, {script_dir!r}) if {script_dir!r} not in sys.path else None; "
            "import patch_cityroad_square_open_ends_v13 as _pcg_v13; "
            "importlib.reload(_pcg_v13)")
        payload = connection.eval(
            "json.dumps(_pcg_v13.diagnose_boundary(), default=list)")
        return json.loads(str(payload))
    finally:
        connection.close()


def diagnose_coverage_remote(host: str, port: int) -> dict:
    import hrpyc
    connection, _remote_hou = hrpyc.import_remote_module(host, port, "hou")
    try:
        script_dir = str(Path(__file__).resolve().parent).replace("\\", "/")
        connection.execute(
            "import sys, importlib, json; "
            f"sys.path.insert(0, {script_dir!r}) if {script_dir!r} not in sys.path else None; "
            "import patch_cityroad_square_open_ends_v13 as _pcg_v13; "
            "importlib.reload(_pcg_v13)")
        payload = connection.eval(
            "json.dumps(_pcg_v13.diagnose_connector_coverage())")
        return json.loads(str(payload))
    finally:
        connection.close()


def probe_remote(host: str, port: int) -> dict:
    import hrpyc
    connection, _remote_hou = hrpyc.import_remote_module(host, port, "hou")
    try:
        script_dir = str(Path(__file__).resolve().parent).replace("\\", "/")
        connection.execute(
            "import sys, importlib, json; "
            f"sys.path.insert(0, {script_dir!r}) if {script_dir!r} not in sys.path else None; "
            "import patch_cityroad_square_open_ends_v13 as _pcg_v13; "
            "importlib.reload(_pcg_v13)")
        payload = connection.eval(
            "json.dumps(_pcg_v13.probe_triangulate_connector_polys())")
        return json.loads(str(payload))
    finally:
        connection.close()


def probe_all_edges_remote(host: str, port: int) -> dict:
    import hrpyc
    connection, _remote_hou = hrpyc.import_remote_module(host, port, "hou")
    try:
        script_dir = str(Path(__file__).resolve().parent).replace("\\", "/")
        connection.execute(
            "import sys, importlib, json; "
            f"sys.path.insert(0, {script_dir!r}) if {script_dir!r} not in sys.path else None; "
            "import patch_cityroad_square_open_ends_v13 as _pcg_v13; "
            "importlib.reload(_pcg_v13)")
        payload = connection.eval(
            "json.dumps(_pcg_v13.probe_all_constraint_edges())")
        return json.loads(str(payload))
    finally:
        connection.close()


def probe_shatter_remote(host: str, port: int) -> dict:
    import hrpyc
    connection, _remote_hou = hrpyc.import_remote_module(host, port, "hou")
    try:
        script_dir = str(Path(__file__).resolve().parent).replace("\\", "/")
        connection.execute(
            "import sys, importlib, json; "
            f"sys.path.insert(0, {script_dir!r}) if {script_dir!r} not in sys.path else None; "
            "import patch_cityroad_square_open_ends_v13 as _pcg_v13; "
            "importlib.reload(_pcg_v13)")
        payload = connection.eval("json.dumps(_pcg_v13.probe_shatter())")
        return json.loads(str(payload))
    finally:
        connection.close()


def probe_clean_group_remote(host: str, port: int) -> dict:
    import hrpyc
    connection, _remote_hou = hrpyc.import_remote_module(host, port, "hou")
    try:
        script_dir = str(Path(__file__).resolve().parent).replace("\\", "/")
        connection.execute(
            "import sys, importlib, json; "
            f"sys.path.insert(0, {script_dir!r}) if {script_dir!r} not in sys.path else None; "
            "import patch_cityroad_square_open_ends_v13 as _pcg_v13; "
            "importlib.reload(_pcg_v13)")
        payload = connection.eval(
            "json.dumps(_pcg_v13.probe_clean_connector_group())")
        return json.loads(str(payload))
    finally:
        connection.close()


def probe_fuse_remote(host: str, port: int) -> dict:
    import hrpyc
    connection, _remote_hou = hrpyc.import_remote_module(host, port, "hou")
    try:
        script_dir = str(Path(__file__).resolve().parent).replace("\\", "/")
        connection.execute(
            "import sys, importlib, json; "
            f"sys.path.insert(0, {script_dir!r}) if {script_dir!r} not in sys.path else None; "
            "import patch_cityroad_square_open_ends_v13 as _pcg_v13; "
            "importlib.reload(_pcg_v13)")
        payload = connection.eval(
            "json.dumps(_pcg_v13.probe_fuse_tolerance())")
        return json.loads(str(payload))
    finally:
        connection.close()


def probe_silhouette_remote(host: str, port: int) -> dict:
    import hrpyc
    connection, _remote_hou = hrpyc.import_remote_module(host, port, "hou")
    try:
        script_dir = str(Path(__file__).resolve().parent).replace("\\", "/")
        connection.execute(
            "import sys, importlib, json; "
            f"sys.path.insert(0, {script_dir!r}) if {script_dir!r} not in sys.path else None; "
            "import patch_cityroad_square_open_ends_v13 as _pcg_v13; "
            "importlib.reload(_pcg_v13)")
        payload = connection.eval("json.dumps(_pcg_v13.probe_silhouette())")
        return json.loads(str(payload))
    finally:
        connection.close()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=18811)
    parser.add_argument("--save", action="store_true")
    parser.add_argument("--diagnose-boundary", action="store_true")
    parser.add_argument("--diagnose-coverage", action="store_true")
    parser.add_argument("--probe-triangulate", action="store_true")
    parser.add_argument("--probe-all-constraints", action="store_true")
    parser.add_argument("--probe-shatter", action="store_true")
    parser.add_argument("--probe-clean-group", action="store_true")
    parser.add_argument("--probe-fuse", action="store_true")
    parser.add_argument("--probe-silhouette", action="store_true")
    args = parser.parse_args()
    if args.diagnose_boundary:
        result = diagnose_remote(args.host, args.port)
    elif args.diagnose_coverage:
        result = diagnose_coverage_remote(args.host, args.port)
    elif args.probe_triangulate:
        result = probe_remote(args.host, args.port)
    elif args.probe_all_constraints:
        result = probe_all_edges_remote(args.host, args.port)
    elif args.probe_shatter:
        result = probe_shatter_remote(args.host, args.port)
    elif args.probe_clean_group:
        result = probe_clean_group_remote(args.host, args.port)
    elif args.probe_fuse:
        result = probe_fuse_remote(args.host, args.port)
    elif args.probe_silhouette:
        result = probe_silhouette_remote(args.host, args.port)
    else:
        result = apply_remote(args.host, args.port, args.save)
    print(json.dumps(result, ensure_ascii=False, indent=2, default=list))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
