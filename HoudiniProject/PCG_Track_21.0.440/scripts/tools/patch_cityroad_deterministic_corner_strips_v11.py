"""CityRoad V11 deterministic right-angle road/sidewalk topology.

V10 preserved five cross-road constraints but still delegated the final
connectivity to global Triangulate2D nodes.  A spline edit could therefore
recreate Delaunay fans.  V11 keeps the global triangulation for the broad
planar solve, removes only the four right-angle cells (per side for the
sidewalk), and replaces those cells with explicit two-triangle quad strips.

This is an incremental live-scene patch.  It does not rebuild the HDA and it
does not change the public parameter interface.
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
import shutil

try:
    import hou  # type: ignore
except ModuleNotFoundError:
    hou = None


ASSET_PATH = "/obj/CityRoad_DEV"
CORE_NAME = "CityRoadCore"
EXPECTED_TYPE = "pcgbike::CityRoad::1.0"
EXPECTED_HDA_SUFFIX = "/Assets/PCG/HDA/City/CityRoad.hda"
ROAD_NODE_NAME = "CITYROAD_REPLACE_CORNER_WITH_QUAD_STRIPS_V11"
SIDEWALK_NODE_NAME = "CITYROAD_REPLACE_SIDEWALK_CORNER_WITH_QUAD_STRIPS_V11"
MARKER = "CITYROAD_V11_DETERMINISTIC_CORNER_STRIPS"


ROAD_VEX = r'''
// CITYROAD_V11_DETERMINISTIC_CORNER_STRIPS
// Input 0: global road Triangulate2D result.
// Input 1: adaptive corridor quads (the authored five-section topology).
// Input 2: V10 cross-road lines snapped to the final road boundary.
//
// The broad planar solve remains unchanged.  Only topology-class 2 corner
// cells are removed and rebuilt as four deterministic quads / eight tris.
function float cross_xz(vector a; vector b)
{
    return a.x * b.z - a.z * b.x;
}

function int inside_convex_quad_xz(
    vector p; vector q0; vector q1; vector q2; vector q3)
{
    vector edges[] = array(q1-q0, q2-q1, q3-q2, q0-q3);
    vector origins[] = array(q0, q1, q2, q3);
    int positive = 1;
    int negative = 1;
    for (int i = 0; i < 4; ++i)
    {
        float value = cross_xz(edges[i], p-origins[i]);
        positive &= value >= -1e-5;
        negative &= value <= 1e-5;
    }
    return positive || negative;
}

function int snap_section_edge(
    vector a; vector b; export vector out_a; export vector out_b)
{
    float best = 1e18;
    int found = 0;
    for (int primitive = 0; primitive < nprimitives(2); ++primitive)
    {
        int points[] = primpoints(2, primitive);
        if (len(points) != 2)
            continue;
        vector p0 = point(2, "P", points[0]);
        vector p1 = point(2, "P", points[1]);
        float direct = distance(a, p0) + distance(b, p1);
        float reverse = distance(a, p1) + distance(b, p0);
        float score = min(direct, reverse);
        if (score < best)
        {
            best = score;
            if (direct <= reverse)
            {
                out_a = p0;
                out_b = p1;
            }
            else
            {
                out_a = p1;
                out_b = p0;
            }
            found = 1;
        }
    }
    return found;
}

function int ensure_point(vector position)
{
    int point_number = nearpoint(0, position);
    if (point_number >= 0
        && distance(point(0, "P", point_number), position) <= 0.001)
        return point_number;
    return addpoint(0, position);
}

function int add_downward_triangle(int a; int b; int c)
{
    vector pa = point(0, "P", a);
    vector pb = point(0, "P", b);
    vector pc = point(0, "P", c);
    int primitive;
    if (cross(pb-pa, pc-pa).y <= 0.0)
        primitive = addprim(0, "poly", a, b, c);
    else
        primitive = addprim(0, "poly", a, c, b);
    setprimattrib(0, "city_part", primitive,
        "corner_quad_strip_v11", "set");
    setprimgroup(0, "corner_quad_strip_v11", primitive, 1, "set");
    return primitive;
}

int source_primitive_count = nprimitives(0);
int adaptive_quad_count = 0;
int removed_triangle_count = 0;
int added_triangle_count = 0;
int invalid_quad_count = 0;
string debug_quads = "";
int remove_primitives[];

addprimattrib(0, "city_part", "");

// Mark every Delaunay triangle whose centroid lies in an authored corner cell.
for (int primitive = 0; primitive < source_primitive_count; ++primitive)
{
    int triangle_points[] = primpoints(0, primitive);
    vector centroid = 0;
    foreach (int triangle_point; triangle_points)
        centroid += point(0, "P", triangle_point);
    centroid /= max(1, len(triangle_points));
    for (int corner_quad = 0; corner_quad < nprimitives(1); ++corner_quad)
    {
        if (int(prim(1, "road_corner_topology_class", corner_quad)) != 2)
            continue;
        int points[] = primpoints(1, corner_quad);
        if (len(points) != 4)
            continue;
        vector q0, q1, q2, q3;
        if (!snap_section_edge(
                point(1, "P", points[0]), point(1, "P", points[3]),
                q0, q3)
            || !snap_section_edge(
                point(1, "P", points[1]), point(1, "P", points[2]),
                q1, q2))
            continue;
        if (inside_convex_quad_xz(centroid, q0, q1, q2, q3))
        {
            append(remove_primitives, primitive);
            break;
        }
    }
}

for (int remove_index = len(remove_primitives) - 1;
        remove_index >= 0; --remove_index)
{
    removeprim(0, remove_primitives[remove_index], 0);
    removed_triangle_count++;
}

// Rebuild each authored corner cell with one fixed diagonal.
for (int corner_quad = 0; corner_quad < nprimitives(1); ++corner_quad)
{
    if (int(prim(1, "road_corner_topology_class", corner_quad)) != 2)
        continue;
    int points[] = primpoints(1, corner_quad);
    if (len(points) != 4)
    {
        invalid_quad_count++;
        continue;
    }
    vector q0, q1, q2, q3;
    if (!snap_section_edge(
            point(1, "P", points[0]), point(1, "P", points[3]), q0, q3)
        || !snap_section_edge(
            point(1, "P", points[1]), point(1, "P", points[2]), q1, q2))
    {
        invalid_quad_count++;
        continue;
    }
    float area = abs(cross_xz(q1-q0, q3-q0))
        + abs(cross_xz(q2-q1, q0-q1));
    if (area <= 1e-6)
    {
        invalid_quad_count++;
        continue;
    }
    vector quad_center = (q0 + q1 + q2 + q3) * 0.25;
    float nearest_source_centroid = 1e18;
    int source_centroids_inside = 0;
    for (int source_primitive = 0;
            source_primitive < source_primitive_count; ++source_primitive)
    {
        int source_points[] = primpoints(0, source_primitive);
        vector source_centroid = 0;
        foreach (int source_point; source_points)
            source_centroid += point(0, "P", source_point);
        source_centroid /= max(1, len(source_points));
        nearest_source_centroid = min(
            nearest_source_centroid, distance(source_centroid, quad_center));
        source_centroids_inside += inside_convex_quad_xz(
            source_centroid, q0, q1, q2, q3);
    }
    debug_quads += sprintf(
        "q%d center=(%.3f,%.3f) area=%.3f inside=%d nearest=%.3f;",
        corner_quad, quad_center.x, quad_center.z, area,
        source_centroids_inside, nearest_source_centroid);
    int p0 = ensure_point(q0);
    int p1 = ensure_point(q1);
    int p2 = ensure_point(q2);
    int p3 = ensure_point(q3);
    add_downward_triangle(p0, p1, p2);
    add_downward_triangle(p0, p2, p3);
    adaptive_quad_count++;
    added_triangle_count += 2;
}

for (int point_number = npoints(0)-1; point_number >= 0; --point_number)
    if (len(pointprims(0, point_number)) == 0)
        removepoint(0, point_number);

setdetailattrib(0, "corner_strip_quad_count", adaptive_quad_count, "set");
setdetailattrib(0, "corner_strip_removed_delaunay_triangle_count",
    removed_triangle_count, "set");
setdetailattrib(0, "corner_strip_triangle_count", added_triangle_count, "set");
setdetailattrib(0, "corner_strip_invalid_quad_count", invalid_quad_count, "set");
setdetailattrib(0, "corner_strip_debug", debug_quads, "set");
setdetailattrib(0, "corner_strip_lines_per_section", 1, "set");
setdetailattrib(0, "cityroad_corner_strip_patch", "V11", "set");

if (adaptive_quad_count <= 0 || invalid_quad_count > 0)
    error(sprintf(
        "CityRoad V11 road strip contract failed: quads=%d invalid=%d",
        adaptive_quad_count, invalid_quad_count));
'''


SIDEWALK_VEX = r'''
// CITYROAD_V11_DETERMINISTIC_SIDEWALK_CORNER_STRIPS
// Input 0: fused global sidewalk Triangulate2D result.
// Input 1: adaptive road corner quads.
// Input 2: V10 one-per-endpoint outward sidewalk connectors.
// Input 3: V10 road cross sections snapped to the final road boundary.
//
// Every road corner quad creates exactly one sidewalk quad on each side.
function float cross_xz(vector a; vector b)
{
    return a.x * b.z - a.z * b.x;
}

function int inside_convex_quad_xz(
    vector p; vector q0; vector q1; vector q2; vector q3)
{
    vector edges[] = array(q1-q0, q2-q1, q3-q2, q0-q3);
    vector origins[] = array(q0, q1, q2, q3);
    int positive = 1;
    int negative = 1;
    for (int i = 0; i < 4; ++i)
    {
        float value = cross_xz(edges[i], p-origins[i]);
        positive &= value >= -1e-5;
        negative &= value <= 1e-5;
    }
    return positive || negative;
}

function int snap_road_section_edge(
    vector a; vector b; export vector out_a; export vector out_b)
{
    float best = 1e18;
    int found = 0;
    for (int primitive = 0; primitive < nprimitives(3); ++primitive)
    {
        int points[] = primpoints(3, primitive);
        if (len(points) != 2)
            continue;
        vector p0 = point(3, "P", points[0]);
        vector p1 = point(3, "P", points[1]);
        float direct = distance(a, p0) + distance(b, p1);
        float reverse = distance(a, p1) + distance(b, p0);
        float score = min(direct, reverse);
        if (score < best)
        {
            best = score;
            if (direct <= reverse)
            {
                out_a = p0;
                out_b = p1;
            }
            else
            {
                out_a = p1;
                out_b = p0;
            }
            found = 1;
        }
    }
    return found;
}

function int connector_end(vector start; export vector result)
{
    float best = 1e18;
    int found = 0;
    for (int primitive = 0; primitive < nprimitives(2); ++primitive)
    {
        int points[] = primpoints(2, primitive);
        if (len(points) != 2)
            continue;
        vector candidate_start = point(2, "P", points[0]);
        float candidate_distance = distance(start, candidate_start);
        if (candidate_distance < best)
        {
            best = candidate_distance;
            result = point(2, "P", points[1]);
            found = 1;
        }
    }
    return found && best <= 0.05;
}

function int ensure_point(vector position)
{
    int point_number = nearpoint(0, position);
    if (point_number >= 0
        && distance(point(0, "P", point_number), position) <= 0.001)
        return point_number;
    return addpoint(0, position);
}

function int add_downward_triangle(int a; int b; int c)
{
    vector pa = point(0, "P", a);
    vector pb = point(0, "P", b);
    vector pc = point(0, "P", c);
    int primitive;
    if (cross(pb-pa, pc-pa).y <= 0.0)
        primitive = addprim(0, "poly", a, b, c);
    else
        primitive = addprim(0, "poly", a, c, b);
    setprimattrib(0, "city_part", primitive,
        "sidewalk_corner_quad_strip_v11", "set");
    setprimgroup(0, "sidewalk_corner_quad_strip_v11", primitive, 1, "set");
    return primitive;
}

vector plane_position = npoints(0) > 0
    ? vector(point(0, "P", 0))
    : set(0.0, 0.15, 0.0);
float plane_y = plane_position.y;
vector quad_positions[];
int quad_corner_ids[];
int invalid_quad_count = 0;
int missing_connector_count = 0;

// Materialize two sidewalk quads per road corner cell.
for (int road_quad = 0; road_quad < nprimitives(1); ++road_quad)
{
    if (int(prim(1, "road_corner_topology_class", road_quad)) != 2)
        continue;
    int points[] = primpoints(1, road_quad);
    if (len(points) != 4)
    {
        invalid_quad_count++;
        continue;
    }
    vector q0, q1, q2, q3;
    if (!snap_road_section_edge(
            point(1, "P", points[0]), point(1, "P", points[3]), q0, q3)
        || !snap_road_section_edge(
            point(1, "P", points[1]), point(1, "P", points[2]), q1, q2))
    {
        invalid_quad_count++;
        continue;
    }
    vector road[] = array(q0, q1, q2, q3);
    int side_a[] = array(0, 3);
    int side_b[] = array(1, 2);
    for (int side = 0; side < 2; ++side)
    {
        vector start_a = road[side_a[side]];
        vector start_b = road[side_b[side]];
        vector end_a, end_b;
        if (!connector_end(start_a, end_a)
            || !connector_end(start_b, end_b))
        {
            missing_connector_count++;
            continue;
        }
        start_a.y = plane_y;
        start_b.y = plane_y;
        end_a.y = plane_y;
        end_b.y = plane_y;
        float area = abs(cross_xz(start_b-start_a, end_a-start_a))
            + abs(cross_xz(end_b-start_b, start_a-start_b));
        if (area <= 1e-6)
        {
            invalid_quad_count++;
            continue;
        }
        append(quad_positions, start_a);
        append(quad_positions, start_b);
        append(quad_positions, end_b);
        append(quad_positions, end_a);
        append(quad_corner_ids, int(prim(1, "corner_id", road_quad)));
    }
}

int source_primitive_count = nprimitives(0);
int sidewalk_quad_count = len(quad_corner_ids);
int removed_triangle_count = 0;
int added_triangle_count = 0;
int remove_primitives[];
addprimattrib(0, "city_part", "");

for (int primitive = 0; primitive < source_primitive_count; ++primitive)
{
    int triangle_points[] = primpoints(0, primitive);
    vector centroid = 0;
    foreach (int triangle_point; triangle_points)
        centroid += point(0, "P", triangle_point);
    centroid /= max(1, len(triangle_points));
    for (int quad_index = 0; quad_index < sidewalk_quad_count; ++quad_index)
    {
        int base = quad_index * 4;
        if (inside_convex_quad_xz(
                centroid,
                quad_positions[base], quad_positions[base+1],
                quad_positions[base+2], quad_positions[base+3]))
        {
            append(remove_primitives, primitive);
            break;
        }
    }
}

for (int remove_index = len(remove_primitives) - 1;
        remove_index >= 0; --remove_index)
{
    removeprim(0, remove_primitives[remove_index], 0);
    removed_triangle_count++;
}

for (int quad_index = 0; quad_index < sidewalk_quad_count; ++quad_index)
{
    int base = quad_index * 4;
    int p0 = ensure_point(quad_positions[base]);
    int p1 = ensure_point(quad_positions[base+1]);
    int p2 = ensure_point(quad_positions[base+2]);
    int p3 = ensure_point(quad_positions[base+3]);
    int a = add_downward_triangle(p0, p1, p2);
    int b = add_downward_triangle(p0, p2, p3);
    setprimattrib(0, "corner_id", a, quad_corner_ids[quad_index], "set");
    setprimattrib(0, "corner_id", b, quad_corner_ids[quad_index], "set");
    added_triangle_count += 2;
}

for (int point_number = npoints(0)-1; point_number >= 0; --point_number)
    if (len(pointprims(0, point_number)) == 0)
        removepoint(0, point_number);

setdetailattrib(0, "sidewalk_corner_strip_quad_count", sidewalk_quad_count, "set");
setdetailattrib(0, "sidewalk_corner_strip_removed_delaunay_triangle_count",
    removed_triangle_count, "set");
setdetailattrib(0, "sidewalk_corner_strip_triangle_count",
    added_triangle_count, "set");
setdetailattrib(0, "sidewalk_corner_strip_invalid_quad_count",
    invalid_quad_count, "set");
setdetailattrib(0, "sidewalk_corner_strip_missing_connector_count",
    missing_connector_count, "set");
setdetailattrib(0, "sidewalk_corner_strip_lines_per_section", 1, "set");
setdetailattrib(0, "cityroad_sidewalk_corner_strip_patch", "V11", "set");

if (sidewalk_quad_count <= 0
    || invalid_quad_count > 0
    || missing_connector_count > 0)
    error(sprintf(
        "CityRoad V11 sidewalk strip contract failed: quads=%d invalid=%d missing=%d",
        sidewalk_quad_count, invalid_quad_count, missing_connector_count));
'''


def _require_node(parent, name: str):
    node = parent.node(name)
    if node is None:
        raise RuntimeError(f"Missing required CityRoad node: {parent.path()}/{name}")
    return node


def _detail(geometry, name: str, default=None):
    attribute = geometry.findGlobalAttrib(name)
    return geometry.attribValue(attribute) if attribute is not None else default


def _backup_definition(definition) -> Path:
    hip_dir = Path(hou.hipFile.path()).resolve().parent
    backup_dir = hip_dir / "backups"
    backup_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    destination = backup_dir / f"CityRoad_before_deterministic_strips_v11_{stamp}.hda"
    shutil.copy2(Path(definition.libraryFilePath()), destination)
    return destination


def _cook_checked(nodes) -> tuple[list[str], list[str]]:
    errors: list[str] = []
    warnings: list[str] = []
    for node in nodes:
        try:
            node.cook(force=True)
        except Exception as exception:
            messages = list(node.errors())
            raise RuntimeError(
                f"CityRoad V11 cook failed at {node.path()}: "
                + " | ".join(messages or [str(exception)])) from exception
        errors.extend(node.errors())
        warnings.extend(node.warnings())
    if errors:
        raise RuntimeError("CityRoad V11 cook errors: " + " | ".join(errors))
    return errors, warnings


def _xz_cross(a, b) -> float:
    return float(a[0] * b[2] - a[2] * b[0])


def _inside_quad(position, quad, tolerance: float = 1e-5) -> bool:
    values = []
    for index in range(4):
        origin = quad[index]
        target = quad[(index + 1) % 4]
        edge = target - origin
        delta = position - origin
        values.append(_xz_cross(edge, delta))
    return (all(value >= -tolerance for value in values)
            or all(value <= tolerance for value in values))


def _match_section_edge(a, b, section_primitives):
    best = None
    best_score = float("inf")
    for primitive in section_primitives:
        points = primitive.points()
        if len(points) != 2:
            continue
        p0 = points[0].position()
        p1 = points[1].position()
        direct = a.distanceTo(p0) + b.distanceTo(p1)
        reverse = a.distanceTo(p1) + b.distanceTo(p0)
        if min(direct, reverse) < best_score:
            best_score = min(direct, reverse)
            best = (p0, p1) if direct <= reverse else (p1, p0)
    if best is None:
        raise RuntimeError("V11 could not match an authored section edge")
    return best


def _road_quads(core):
    adaptive = _require_node(core, "ROAD_BUILD_ADAPTIVE_CORNER_SURFACE").geometry()
    sections = _require_node(
        core, "CITYROAD_BUILD_CORNER_SECTION_CONSTRAINTS_V10").geometry()
    section_primitives = sections.prims()
    quads = []
    for primitive in adaptive.prims():
        if int(primitive.attribValue("road_corner_topology_class")) != 2:
            continue
        points = primitive.points()
        if len(points) != 4:
            raise RuntimeError(
                f"V11 adaptive primitive {primitive.number()} is not a quad")
        q0, q3 = _match_section_edge(
            points[0].position(), points[3].position(), section_primitives)
        q1, q2 = _match_section_edge(
            points[1].position(), points[2].position(), section_primitives)
        quads.append((q0, q1, q2, q3))
    return quads


def _sidewalk_quads(core, road_quads, plane_y: float):
    connector_geometry = _require_node(
        core, "CITYROAD_BUILD_SIDEWALK_SECTION_CONSTRAINTS_V10").geometry()
    connectors = []
    for primitive in connector_geometry.prims():
        points = primitive.points()
        if len(points) == 2:
            connectors.append((points[0].position(), points[1].position()))

    def connector_end(start):
        if not connectors:
            raise RuntimeError("V11 sidewalk connector geometry is empty")
        candidate = min(connectors, key=lambda item: start.distanceTo(item[0]))
        if start.distanceTo(candidate[0]) > 0.001:
            raise RuntimeError(
                "V11 sidewalk connector does not start at the road section")
        return candidate[1]

    result = []
    for road in road_quads:
        for index_a, index_b in ((0, 1), (3, 2)):
            start_a = hou.Vector3(road[index_a])
            start_b = hou.Vector3(road[index_b])
            end_a = hou.Vector3(connector_end(start_a))
            end_b = hou.Vector3(connector_end(start_b))
            start_a[1] = plane_y
            start_b[1] = plane_y
            end_a[1] = plane_y
            end_b[1] = plane_y
            result.append((start_a, start_b, end_b, end_a))
    return result


def _validate_strip_group(
        geometry, group_name: str, quad_count: int,
        expected_components: int) -> dict[str, int]:
    target_group = geometry.findPrimGroup(group_name)
    if target_group is None:
        raise RuntimeError(f"V11 missing primitive group {group_name}")
    target_numbers = {primitive.number() for primitive in target_group.prims()}
    target_edges = set()
    target_positions = set()
    adjacency = {}
    target_centroids = set()
    for primitive in target_group.prims():
        points = primitive.points()
        keys = [tuple(round(float(value), 4) for value in point.position())
                for point in points]
        target_positions.update(keys)
        centroid = sum(
            (point.position() for point in points), hou.Vector3()) / len(points)
        target_centroids.add(tuple(round(float(value), 4) for value in centroid))
        for index in range(len(keys)):
            a = keys[index]
            b = keys[(index + 1) % len(keys)]
            target_edges.add(tuple(sorted((a, b))))
            adjacency.setdefault(a, set()).add(b)
            adjacency.setdefault(b, set()).add(a)

    remaining = set(target_positions)
    component_count = 0
    while remaining:
        component_count += 1
        stack = [remaining.pop()]
        while stack:
            current = stack.pop()
            for neighbor in adjacency.get(current, set()):
                if neighbor in remaining:
                    remaining.remove(neighbor)
                    stack.append(neighbor)

    expected_primitives = quad_count * 2
    expected_vertices = (quad_count + expected_components) * 2
    expected_edges = quad_count * 4 + expected_components
    if (len(target_numbers) != expected_primitives
            or len(target_positions) != expected_vertices
            or len(target_edges) != expected_edges
            or component_count != expected_components):
        raise RuntimeError(
            f"V11 {group_name} strip topology failed: "
            f"prims={len(target_numbers)}/{expected_primitives} "
            f"vertices={len(target_positions)}/{expected_vertices} "
            f"edges={len(target_edges)}/{expected_edges} "
            f"components={component_count}/{expected_components}")

    all_centroid_counts = {}
    for primitive in geometry.prims():
        points = primitive.points()
        centroid = sum(
            (point.position() for point in points), hou.Vector3()) / len(points)
        key = tuple(round(float(value), 4) for value in centroid)
        all_centroid_counts[key] = all_centroid_counts.get(key, 0) + 1
    duplicate_centroids = sum(
        1 for key in target_centroids if all_centroid_counts.get(key, 0) != 1)
    if duplicate_centroids:
        raise RuntimeError(
            f"V11 {group_name} has {duplicate_centroids} overlapping centroids")

    return {
        "group_primitives": len(target_numbers),
        "group_vertices": len(target_positions),
        "group_edges": len(target_edges),
        "components": component_count,
        "duplicate_centroids": duplicate_centroids,
        "validated_cells": quad_count,
    }


def _validate(core) -> dict[str, object]:
    road = _require_node(core, ROAD_NODE_NAME)
    sidewalk = _require_node(core, SIDEWALK_NODE_NAME)
    outputs = [
        _require_node(core, "OUT_ROAD_SURFACE"),
        _require_node(core, "OUT_ROAD_MARKINGS"),
        _require_node(core, "OUT_SIDEWALK_CURB"),
        _require_node(core, "OUT_ROAD_COLLISION"),
    ]
    _, warnings = _cook_checked([road, sidewalk] + outputs)

    road_geometry = road.geometry()
    sidewalk_geometry = sidewalk.geometry()
    road_quads = int(_detail(road_geometry, "corner_strip_quad_count", -1))
    road_triangles = int(_detail(road_geometry, "corner_strip_triangle_count", -1))
    road_removed = int(_detail(
        road_geometry, "corner_strip_removed_delaunay_triangle_count", -1))
    road_invalid = int(_detail(road_geometry, "corner_strip_invalid_quad_count", -1))
    road_lines = int(_detail(road_geometry, "corner_strip_lines_per_section", -1))
    road_patch = str(_detail(road_geometry, "cityroad_corner_strip_patch", ""))
    road_debug = str(_detail(road_geometry, "corner_strip_debug", ""))

    sidewalk_quads = int(_detail(
        sidewalk_geometry, "sidewalk_corner_strip_quad_count", -1))
    sidewalk_triangles = int(_detail(
        sidewalk_geometry, "sidewalk_corner_strip_triangle_count", -1))
    sidewalk_removed = int(_detail(
        sidewalk_geometry,
        "sidewalk_corner_strip_removed_delaunay_triangle_count", -1))
    sidewalk_invalid = int(_detail(
        sidewalk_geometry, "sidewalk_corner_strip_invalid_quad_count", -1))
    sidewalk_missing = int(_detail(
        sidewalk_geometry, "sidewalk_corner_strip_missing_connector_count", -1))
    sidewalk_lines = int(_detail(
        sidewalk_geometry, "sidewalk_corner_strip_lines_per_section", -1))
    sidewalk_patch = str(_detail(
        sidewalk_geometry, "cityroad_sidewalk_corner_strip_patch", ""))

    if (road_quads <= 0
            or road_triangles != road_quads * 2
            or road_removed < road_quads * 2
            or road_invalid != 0
            or road_lines != 1
            or road_patch != "V11"):
        raise RuntimeError(
            "V11 road strip validation failed: "
            f"quads={road_quads} triangles={road_triangles} "
            f"removed={road_removed} invalid={road_invalid} "
            f"lines={road_lines} patch={road_patch} debug={road_debug}")

    if (sidewalk_quads != road_quads * 2
            or sidewalk_triangles != sidewalk_quads * 2
            or sidewalk_removed < sidewalk_quads * 2
            or sidewalk_invalid != 0
            or sidewalk_missing != 0
            or sidewalk_lines != 1
            or sidewalk_patch != "V11"):
        raise RuntimeError(
            "V11 sidewalk strip validation failed: "
            f"quads={sidewalk_quads} triangles={sidewalk_triangles} "
            f"removed={sidewalk_removed} invalid={sidewalk_invalid} "
            f"missing={sidewalk_missing} lines={sidewalk_lines} "
            f"patch={sidewalk_patch}")

    road_group = road_geometry.findPrimGroup("corner_quad_strip_v11")
    sidewalk_group = sidewalk_geometry.findPrimGroup(
        "sidewalk_corner_quad_strip_v11")
    road_group_count = len(road_group.prims()) if road_group else 0
    sidewalk_group_count = len(sidewalk_group.prims()) if sidewalk_group else 0
    if road_group_count != road_triangles:
        raise RuntimeError(
            f"V11 road group expected {road_triangles}, got {road_group_count}")
    if sidewalk_group_count != sidewalk_triangles:
        raise RuntimeError(
            "V11 sidewalk group expected "
            f"{sidewalk_triangles}, got {sidewalk_group_count}")

    if road_quads % 4 != 0:
        raise RuntimeError(
            f"V11 expected four road quads per corner, got {road_quads}")
    corner_count = road_quads // 4
    road_exact = _validate_strip_group(
        road_geometry, "corner_quad_strip_v11",
        road_quads, corner_count)
    sidewalk_exact = _validate_strip_group(
        sidewalk_geometry, "sidewalk_corner_quad_strip_v11",
        sidewalk_quads, corner_count * 2)

    return {
        "warnings": warnings,
        "road_quads": road_quads,
        "road_triangles": road_triangles,
        "road_removed_delaunay_triangles": road_removed,
        "road_lines_per_section": road_lines,
        "sidewalk_quads": sidewalk_quads,
        "sidewalk_triangles": sidewalk_triangles,
        "sidewalk_removed_delaunay_triangles": sidewalk_removed,
        "sidewalk_lines_per_section": sidewalk_lines,
        "road_exact_topology": road_exact,
        "sidewalk_exact_topology": sidewalk_exact,
        "output_stats": {
            node.name(): {
                "points": len(node.geometry().points()),
                "primitives": len(node.geometry().prims()),
            }
            for node in outputs
        },
    }


def apply_live_patch(save: bool = True, create_backup: bool = True, hou_module=None):
    global hou
    if hou_module is not None:
        hou = hou_module
    if hou is None:
        raise RuntimeError("The hou module is unavailable")

    asset = hou.node(ASSET_PATH)
    if asset is None:
        raise RuntimeError(f"Missing target HDA instance: {ASSET_PATH}")
    if asset.type().name() != EXPECTED_TYPE:
        raise RuntimeError(f"Unexpected target type: {asset.type().name()}")
    definition = asset.type().definition()
    if definition is None:
        raise RuntimeError("CityRoad HDA definition is unavailable")
    library_path = definition.libraryFilePath().replace("\\", "/")
    if not library_path.endswith(EXPECTED_HDA_SUFFIX):
        raise RuntimeError(f"Unexpected CityRoad definition: {library_path}")

    interface_before = asset.parmTemplateGroup().asDialogScript()
    was_locked = asset.isLockedHDA()
    if was_locked:
        asset.allowEditingOfContents()
    core = _require_node(asset, CORE_NAME)

    triangulate = _require_node(core, "ROAD_PLANAR_TRIANGULATE_FINAL_BOUNDARY")
    road_classify = _require_node(core, "ROAD_PLANAR_CLASSIFY_FROM_FINAL_BOUNDARY")
    adaptive = _require_node(core, "ROAD_BUILD_ADAPTIVE_CORNER_SURFACE")
    road_sections = _require_node(
        core, "CITYROAD_BUILD_CORNER_SECTION_CONSTRAINTS_V10")
    sidewalk_fuse = _require_node(
        core, "CITYROAD_FUSE_SIDEWALK_TRIANGULATION_V10")
    sidewalk_sections = _require_node(
        core, "CITYROAD_BUILD_SIDEWALK_SECTION_CONSTRAINTS_V10")
    sidewalk_classify = _require_node(core, "SIDEWALK_PLANAR_CLASSIFY")
    legacy_sidewalk_transfer = _require_node(
        core, "CITYROAD_TOPOLOGY_TRANSFER_SIDEWALKCURB")

    existing_road = core.node(ROAD_NODE_NAME)
    existing_sidewalk = core.node(SIDEWALK_NODE_NAME)
    if road_classify.input(0) not in (triangulate, existing_road):
        raise RuntimeError(
            "V11 signature mismatch: ROAD_PLANAR_CLASSIFY_FROM_FINAL_BOUNDARY "
            f"input 0 is {road_classify.input(0)}")
    if sidewalk_classify.input(0) not in (sidewalk_fuse, existing_sidewalk):
        raise RuntimeError(
            "V11 signature mismatch: SIDEWALK_PLANAR_CLASSIFY input 0 is "
            f"{sidewalk_classify.input(0)}")

    backup_path = _backup_definition(definition) if create_backup else None
    created_road = existing_road is None
    created_sidewalk = existing_sidewalk is None
    road_node = existing_road
    sidewalk_node = existing_sidewalk
    old_road_input = road_classify.input(0)
    old_sidewalk_input = sidewalk_classify.input(0)
    old_legacy_sidewalk_display = legacy_sidewalk_transfer.isDisplayFlagSet()
    try:
        with hou.undos.group("CityRoad V11 deterministic corner strips"):
            if road_node is None:
                road_node = core.createNode("attribwrangle", ROAD_NODE_NAME)
            road_node.setInput(0, triangulate)
            road_node.setInput(1, adaptive)
            road_node.setInput(2, road_sections)
            road_node.parm("class").set(0)
            road_node.parm("snippet").set(ROAD_VEX)
            road_node.setComment(
                "V11：直角弯固定为 5 条横截面、4 个四边形带；"
                "仅替换角弯内部 Delaunay 三角形，禁止放射状连边。")
            road_node.setColor(hou.Color((0.95, 0.55, 0.12)))
            road_node.setPosition(triangulate.position() + hou.Vector2((0.0, -1.6)))
            road_classify.setInput(0, road_node)

            if sidewalk_node is None:
                sidewalk_node = core.createNode("attribwrangle", SIDEWALK_NODE_NAME)
            sidewalk_node.setInput(0, sidewalk_fuse)
            sidewalk_node.setInput(1, adaptive)
            sidewalk_node.setInput(2, sidewalk_sections)
            sidewalk_node.setInput(3, road_sections)
            sidewalk_node.parm("class").set(0)
            sidewalk_node.parm("snippet").set(SIDEWALK_VEX)
            sidewalk_node.setComment(
                "V11：人行道两侧各使用同一套 5 条截面、4 个四边形带；"
                "每个截面位置只有一条横线。")
            sidewalk_node.setColor(hou.Color((0.95, 0.72, 0.18)))
            sidewalk_node.setPosition(
                sidewalk_fuse.position() + hou.Vector2((0.0, -1.6)))
            sidewalk_classify.setInput(0, sidewalk_node)

            # This legacy transfer node is an internal packing stage, not an
            # HDA output.  Leaving its SOP display flag enabled makes Houdini
            # Engine expose an extra transient Geo during rebuild; while its
            # upstream branch is empty HAPI reports "No geometry generated".
            # The real sidewalk/curb result remains OUT_SIDEWALK_CURB.
            legacy_sidewalk_transfer.setDisplayFlag(False)

            network_box = core.findNetworkBox("CITYROAD_V11_DETERMINISTIC_STRIPS")
            if network_box is None:
                network_box = core.createNetworkBox(
                    "CITYROAD_V11_DETERMINISTIC_STRIPS")
            network_box.setComment(
                "V11 移动端确定性角弯拓扑：道路/路牙/人行道共享 5 截面。")
            network_box.setColor(hou.Color((0.33, 0.19, 0.06)))
            for node in (road_node, sidewalk_node):
                network_box.addItem(node)
            network_box.fitAroundContents()

        if asset.parmTemplateGroup().asDialogScript() != interface_before:
            raise RuntimeError("V11 unexpectedly changed the public HDA interface")

        validation = _validate(core)
        if save:
            definition.updateFromNode(asset)
            hou.hipFile.save()
    except Exception:
        road_classify.setInput(0, old_road_input)
        sidewalk_classify.setInput(0, old_sidewalk_input)
        legacy_sidewalk_transfer.setDisplayFlag(old_legacy_sidewalk_display)
        if created_road and road_node is not None:
            road_node.destroy()
        if created_sidewalk and sidewalk_node is not None:
            sidewalk_node.destroy()
        triangulate.cook(force=True)
        sidewalk_fuse.cook(force=True)
        raise

    return {
        "asset": asset.path(),
        "definition": library_path,
        "hip": hou.hipFile.path(),
        "backup": str(backup_path) if backup_path else None,
        "was_locked": was_locked,
        "saved": save,
        "road_node": road_node.path(),
        "sidewalk_node": sidewalk_node.path(),
        "marker": MARKER,
        "validation": validation,
    }


def apply_patch_via_rpc():
    """Execute this exact file inside the already-running Houdini GUI."""
    import json
    import os
    import hrpyc

    connection, _remote_hou = hrpyc.import_remote_module(
        "127.0.0.1", 18811, "hou")
    script_path = os.path.abspath(__file__).replace("\\", "/")
    remote_code = (
        "import hou\n"
        "_cityroad_v11_namespace = {'__name__': 'cityroad_v11_remote'}\n"
        "exec(compile(open(%r, encoding='utf-8').read(), %r, 'exec'), "
        "_cityroad_v11_namespace)\n"
        "CITYROAD_V11_RESULT = "
        "_cityroad_v11_namespace['apply_live_patch'](hou_module=hou)\n"
    ) % (script_path, script_path)
    connection.execute(remote_code)
    return json.loads(connection.eval(
        "__import__('json').dumps(CITYROAD_V11_RESULT, ensure_ascii=False)"))


if __name__ == "__main__":
    in_target_session = hou is not None and hou.node(ASSET_PATH) is not None
    print(apply_live_patch() if in_target_session else apply_patch_via_rpc())
