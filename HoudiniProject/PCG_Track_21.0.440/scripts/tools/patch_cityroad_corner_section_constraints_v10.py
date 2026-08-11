"""CityRoad V10 single cross-section topology constraints.

The V8/V9 patches limited right-angle sampling to five points per boundary,
but the final global Triangulate 2D stage still created Delaunay fans from
those points.  This incremental live-scene patch adds exactly one unique
cross-road constraint for every paired corner sample.  It does not rebuild
the HDA or change its public parameter interface.
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
EXPECTED_TYPE = "pcgbike::CityRoad::1.0"
EXPECTED_HDA_SUFFIX = "/Assets/PCG/HDA/City/CityRoad.hda"
NODE_NAME = "CITYROAD_BUILD_CORNER_SECTION_CONSTRAINTS_V10"
SIDEWALK_NODE_NAME = "CITYROAD_BUILD_SIDEWALK_SECTION_CONSTRAINTS_V10"
SIDEWALK_FUSE_NODE_NAME = "CITYROAD_FUSE_SIDEWALK_TRIANGULATION_V10"
MARKER = "CITYROAD_V10_SINGLE_CORNER_SECTION"


SECTION_VEX = r'''
// CITYROAD_V10_SINGLE_CORNER_SECTION
// Input 0: ROAD_BUILD_ADAPTIVE_CORNER_SURFACE.
// Input 1: the exact final road boundary used by Triangulate 2D.
// A four-span right-angle corner has five paired boundary samples.  Emit one
// and only one cross-road polyline for each pair; the final Triangulate 2D
// stage uses these as constraints instead of creating an unconstrained fan.
function vector snap_to_level_boundary(
    int geometry; vector query; int level)
{
    vector flat_query = set(query.x, 0.0, query.z);
    vector best = query;
    float best_distance = 1e18;
    for (int primitive = 0; primitive < nprimitives(geometry); ++primitive)
    {
        if (hasprimattrib(geometry, "road_level")
            && int(prim(geometry, "road_level", primitive)) != level)
            continue;
        int points[] = primpoints(geometry, primitive);
        int closed = int(primintrinsic(geometry, "closed", primitive));
        int edge_count = closed ? len(points) : len(points) - 1;
        for (int edge = 0; edge < edge_count; ++edge)
        {
            vector a = point(geometry, "P", points[edge]);
            vector b = point(geometry, "P", points[(edge + 1) % len(points)]);
            vector flat_a = set(a.x, 0.0, a.z);
            vector flat_b = set(b.x, 0.0, b.z);
            vector ab = flat_b - flat_a;
            float length_sq = length2(ab);
            float u = length_sq > 1e-12
                ? clamp(dot(flat_query - flat_a, ab) / length_sq, 0.0, 1.0)
                : 0.0;
            vector candidate = lerp(a, b, u);
            float candidate_distance = distance(
                flat_query, set(candidate.x, 0.0, candidate.z));
            if (candidate_distance < best_distance)
            {
                best_distance = candidate_distance;
                best = candidate;
            }
        }
    }
    return best;
}

function int same_section(
    vector a; vector b; vector c; vector d; float tolerance)
{
    return (distance(a, c) <= tolerance && distance(b, d) <= tolerance)
        || (distance(a, d) <= tolerance && distance(b, c) <= tolerance);
}

int original_primitive_count = nprimitives(0);
float tolerance = 0.001;
vector emitted_a[];
vector emitted_b[];
int emitted_corner_id[];
int section_count = 0;
int duplicate_count = 0;
int invalid_quad_count = 0;
float max_boundary_snap_distance = 0.0;

addprimattrib(0, "city_part", "corner_section_constraint");
addprimattrib(0, "corner_id", -1);
addprimattrib(0, "road_id", -1);
addprimattrib(0, "segment_id", -1);
addprimattrib(0, "road_level", 0);

for (int primitive = 0; primitive < original_primitive_count; ++primitive)
{
    // Only the actual rounded corner is constrained.  Straight corridors and
    // transition quads retain their existing low-cost topology.
    if (int(prim(0, "road_corner_topology_class", primitive)) != 2)
        continue;

    int vertices[] = primvertices(0, primitive);
    if (len(vertices) != 4)
    {
        invalid_quad_count++;
        continue;
    }

    // upward_quad() always stores its two cross-road edges at local vertex
    // pairs (0,3) and (1,2), even when winding is reversed.
    int local_a[] = array(0, 1);
    int local_b[] = array(3, 2);
    for (int side = 0; side < 2; ++side)
    {
        vector original_a = point(
            0, "P", vertexpoint(0, vertices[local_a[side]]));
        vector original_b = point(
            0, "P", vertexpoint(0, vertices[local_b[side]]));
        int level = int(prim(0, "road_level", primitive));
        vector a = snap_to_level_boundary(1, original_a, level);
        vector b = snap_to_level_boundary(1, original_b, level);
        max_boundary_snap_distance = max(
            max_boundary_snap_distance,
            max(distance(original_a, a), distance(original_b, b)));
        int corner_id = int(prim(0, "corner_id", primitive));
        int duplicate = 0;
        for (int existing = 0; existing < len(emitted_a); ++existing)
        {
            if (emitted_corner_id[existing] == corner_id
                && same_section(
                    a, b, emitted_a[existing], emitted_b[existing], tolerance))
            {
                duplicate = 1;
                break;
            }
        }
        if (duplicate)
        {
            duplicate_count++;
            continue;
        }

        int point_a = addpoint(0, a);
        int point_b = addpoint(0, b);
        int section = addprim(0, "polyline", point_a, point_b);
        setprimattrib(0, "city_part", section,
            "corner_section_constraint", "set");
        setprimattrib(0, "corner_id", section, corner_id, "set");
        setprimattrib(0, "road_id", section,
            int(prim(0, "road_id", primitive)), "set");
        setprimattrib(0, "segment_id", section,
            int(prim(0, "segment_id", primitive)), "set");
        setprimattrib(0, "road_level", section,
            int(prim(0, "road_level", primitive)), "set");
        setprimgroup(0, "corner_section_constraint", section, 1, "set");
        append(emitted_a, a);
        append(emitted_b, b);
        append(emitted_corner_id, corner_id);
        section_count++;
    }
}

for (int primitive = original_primitive_count - 1; primitive >= 0; --primitive)
    removeprim(0, primitive, 1);

setdetailattrib(0, "corner_section_constraint_count", section_count, "set");
setdetailattrib(0, "corner_section_duplicate_removed_count",
    duplicate_count, "set");
setdetailattrib(0, "corner_section_invalid_quad_count",
    invalid_quad_count, "set");
setdetailattrib(0, "corner_section_lines_per_sample", 1, "set");
setdetailattrib(0, "corner_section_max_boundary_snap_distance",
    max_boundary_snap_distance, "set");
setdetailattrib(0, "cityroad_corner_section_patch", "V10", "set");

if (invalid_quad_count > 0)
    error(sprintf(
        "CityRoad V10 expected corner quads, invalid=%d",
        invalid_quad_count));
'''


SIDEWALK_SECTION_VEX = r'''
// CITYROAD_V10_SINGLE_SIDEWALK_SECTION
// Input 0: five exact road corner cross-sections.
// Input 1: site boundary. Input 2: all final road boundaries.
// Each of the ten road-edge samples emits exactly one outward sidewalk
// constraint, replacing the unconstrained Delaunay fan at that location.
function float cross_xz(vector a; vector b)
{
    return a.x * b.z - a.z * b.x;
}

function float nearest_ray_hit(
    int geometry; vector origin; vector direction)
{
    float best_t = 1e18;
    for (int primitive = 0; primitive < nprimitives(geometry); ++primitive)
    {
        int points[] = primpoints(geometry, primitive);
        int closed = int(primintrinsic(geometry, "closed", primitive));
        int edge_count = closed ? len(points) : len(points) - 1;
        for (int edge = 0; edge < edge_count; ++edge)
        {
            vector a = point(geometry, "P", points[edge]);
            vector b = point(
                geometry, "P", points[(edge + 1) % len(points)]);
            vector segment = b - a;
            segment.y = 0.0;
            vector delta = a - origin;
            delta.y = 0.0;
            float denominator = cross_xz(direction, segment);
            if (abs(denominator) < 1e-8)
                continue;
            float t = cross_xz(delta, segment) / denominator;
            float u = cross_xz(delta, direction) / denominator;
            // Ignore the source road-boundary contact at t=0.
            if (t > 0.01 && u >= -1e-5 && u <= 1.00001)
                best_t = min(best_t, t);
        }
    }
    return best_t;
}

int original_primitive_count = nprimitives(0);
vector emitted_starts[];
int connector_count = 0;
int duplicate_start_count = 0;
int missed_boundary_count = 0;
float max_connector_length = 0.0;

addprimattrib(0, "city_part", "sidewalk_corner_section_constraint");
addprimattrib(0, "corner_id", -1);

for (int primitive = 0; primitive < original_primitive_count; ++primitive)
{
    int points[] = primpoints(0, primitive);
    if (len(points) != 2)
        continue;
    vector end_0 = point(0, "P", points[0]);
    vector end_1 = point(0, "P", points[1]);
    vector ends[] = array(end_0, end_1);
    int corner_id = int(prim(0, "corner_id", primitive));
    for (int side = 0; side < 2; ++side)
    {
        vector start = ends[side];
        vector opposite = ends[1 - side];
        vector direction = start - opposite;
        direction.y = 0.0;
        if (length2(direction) < 1e-10)
            continue;
        direction = normalize(direction);

        int duplicate = 0;
        foreach (vector existing; emitted_starts)
            if (distance(existing, start) <= 0.001)
            {
                duplicate = 1;
                break;
            }
        if (duplicate)
        {
            duplicate_start_count++;
            continue;
        }

        float site_t = nearest_ray_hit(1, start, direction);
        float road_t = nearest_ray_hit(2, start, direction);
        float hit_t = min(site_t, road_t);
        if (hit_t >= 1e17)
        {
            missed_boundary_count++;
            continue;
        }

        vector end = start + direction * hit_t;
        int start_point = addpoint(0, start);
        int end_point = addpoint(0, end);
        int connector = addprim(0, "polyline", start_point, end_point);
        setprimattrib(0, "city_part", connector,
            "sidewalk_corner_section_constraint", "set");
        setprimattrib(0, "corner_id", connector, corner_id, "set");
        setprimgroup(0, "sidewalk_corner_section_connector",
            connector, 1, "set");
        // Reuse the existing open-connector constraint path in Triangulate2D.
        setprimgroup(0, "sidewalk_open_end_connector",
            connector, 1, "set");
        append(emitted_starts, start);
        connector_count++;
        max_connector_length = max(max_connector_length, hit_t);
    }
}

for (int primitive = original_primitive_count - 1; primitive >= 0; --primitive)
    removeprim(0, primitive, 1);

setdetailattrib(0, "sidewalk_corner_section_connector_count",
    connector_count, "set");
setdetailattrib(0, "sidewalk_corner_section_duplicate_start_count",
    duplicate_start_count, "set");
setdetailattrib(0, "sidewalk_corner_section_missed_boundary_count",
    missed_boundary_count, "set");
setdetailattrib(0, "sidewalk_corner_section_lines_per_endpoint", 1, "set");
setdetailattrib(0, "sidewalk_corner_section_max_length",
    max_connector_length, "set");
setdetailattrib(0, "cityroad_sidewalk_section_patch", "V10", "set");

if (missed_boundary_count > 0)
    error(sprintf(
        "CityRoad V10 sidewalk connector misses=%d",
        missed_boundary_count));
'''


def _require_node(parent, name: str):
    node = parent.node(name)
    if node is None:
        raise RuntimeError(f"Missing required CityRoad node: {parent.path()}/{name}")
    return node


def _detail_value(geometry, name: str, default=0):
    attribute = geometry.findGlobalAttrib(name)
    return geometry.attribValue(attribute) if attribute is not None else default


def _backup_definition(definition) -> Path:
    hip_dir = Path(hou.hipFile.path()).resolve().parent
    backup_dir = hip_dir / "backups"
    backup_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    destination = backup_dir / f"CityRoad_before_corner_sections_v10_{stamp}.hda"
    shutil.copy2(Path(definition.libraryFilePath()), destination)
    return destination


def _position_key(position, precision: int = 4):
    return tuple(round(float(value), precision) for value in position)


def _geometry_edges(geometry):
    positions = {
        point.number(): _position_key(point.position())
        for point in geometry.points()
    }
    edges = set()
    neighbors: dict[tuple[float, float, float], set[tuple[float, float, float]]] = {}
    for primitive in geometry.prims():
        vertices = primitive.vertices()
        count = len(vertices)
        for index in range(count):
            a = positions[vertices[index].point().number()]
            b = positions[vertices[(index + 1) % count].point().number()]
            if a == b:
                continue
            edge = tuple(sorted((a, b)))
            edges.add(edge)
            neighbors.setdefault(a, set()).add(b)
            neighbors.setdefault(b, set()).add(a)
    return edges, neighbors


def _constraint_edges(geometry):
    result = []
    for primitive in geometry.prims():
        points = primitive.points()
        if len(points) != 2:
            raise RuntimeError(
                f"V10 constraint primitive {primitive.number()} is not one line")
        result.append(tuple(sorted((
            _position_key(points[0].position()),
            _position_key(points[1].position()),
        ))))
    return result


def _validate(core) -> dict[str, object]:
    section_node = _require_node(core, NODE_NAME)
    sidewalk_section_node = _require_node(core, SIDEWALK_NODE_NAME)
    triangulate = _require_node(core, "ROAD_PLANAR_TRIANGULATE_FINAL_BOUNDARY")
    sidewalk_triangulate = _require_node(core, "SIDEWALK_PLANAR_TRIANGULATE")
    sidewalk_fuse = _require_node(core, SIDEWALK_FUSE_NODE_NAME)
    outputs = [
        _require_node(core, "OUT_ROAD_SURFACE"),
        _require_node(core, "OUT_ROAD_MARKINGS"),
        _require_node(core, "OUT_SIDEWALK_CURB"),
    ]

    errors: list[str] = []
    warnings: list[str] = []
    for node in [
            section_node, sidewalk_section_node,
            triangulate, sidewalk_triangulate, sidewalk_fuse] + outputs:
        try:
            node.cook(force=True)
        except Exception as exception:
            messages = list(node.errors())
            raise RuntimeError(
                f"CityRoad V10 cook failed at {node.path()}: "
                + " | ".join(messages or [str(exception)])) from exception
        errors.extend(node.errors())
        warnings.extend(node.warnings())
    if errors:
        raise RuntimeError("CityRoad V10 cook errors: " + " | ".join(errors))

    section_geometry = section_node.geometry()
    section_count = int(_detail_value(
        section_geometry, "corner_section_constraint_count", -1))
    max_snap_distance = float(_detail_value(
        section_geometry, "corner_section_max_boundary_snap_distance", -1.0))
    invalid_count = int(_detail_value(
        section_geometry, "corner_section_invalid_quad_count", -1))
    lines_per_sample = int(_detail_value(
        section_geometry, "corner_section_lines_per_sample", -1))
    patch = str(_detail_value(
        section_geometry, "cityroad_corner_section_patch", ""))
    constraints = _constraint_edges(section_geometry)
    if section_count <= 0 or len(constraints) != section_count:
        raise RuntimeError(
            f"V10 produced invalid section count: detail={section_count} "
            f"primitives={len(constraints)}")
    if len(set(constraints)) != len(constraints):
        raise RuntimeError("V10 emitted duplicate cross-road section lines")
    if invalid_count != 0 or lines_per_sample != 1 or patch != "V10":
        raise RuntimeError(
            "V10 corner section contract failed: "
            f"invalid={invalid_count} lines={lines_per_sample} patch={patch}")

    triangulated_geometry = triangulate.geometry()
    triangulated_edges, neighbors = _geometry_edges(triangulated_geometry)
    final_positions = list(neighbors.keys())

    def nearest_final(position, tolerance: float = 0.002):
        best = None
        best_distance_sq = tolerance * tolerance
        for candidate in final_positions:
            distance_sq = sum(
                (position[index] - candidate[index]) ** 2
                for index in range(3))
            if distance_sq <= best_distance_sq:
                best = candidate
                best_distance_sq = distance_sq
        return best

    mapped_constraints = []
    missing = []
    for edge in constraints:
        endpoint_a = nearest_final(edge[0])
        endpoint_b = nearest_final(edge[1])
        if endpoint_a is None or endpoint_b is None:
            missing.append(edge)
            continue
        mapped = tuple(sorted((endpoint_a, endpoint_b)))
        mapped_constraints.append(mapped)
        if mapped not in triangulated_edges:
            missing.append(edge)
    if missing:
        raise RuntimeError(
            f"V10 final triangulation lost {len(missing)} section constraints")
    endpoint_degrees = [
        len(neighbors.get(endpoint, set()))
        for edge in mapped_constraints
        for endpoint in edge
    ]

    sidewalk_geometry = sidewalk_section_node.geometry()
    sidewalk_count = int(_detail_value(
        sidewalk_geometry, "sidewalk_corner_section_connector_count", -1))
    sidewalk_misses = int(_detail_value(
        sidewalk_geometry, "sidewalk_corner_section_missed_boundary_count", -1))
    sidewalk_lines_per_endpoint = int(_detail_value(
        sidewalk_geometry, "sidewalk_corner_section_lines_per_endpoint", -1))
    sidewalk_patch = str(_detail_value(
        sidewalk_geometry, "cityroad_sidewalk_section_patch", ""))
    expected_sidewalk_count = section_count * 2
    if (sidewalk_count != expected_sidewalk_count
            or sidewalk_misses != 0
            or sidewalk_lines_per_endpoint != 1
            or sidewalk_patch != "V10"):
        raise RuntimeError(
            "V10 sidewalk section contract failed: "
            f"expected={expected_sidewalk_count} actual={sidewalk_count} "
            f"misses={sidewalk_misses} lines={sidewalk_lines_per_endpoint} "
            f"patch={sidewalk_patch}")

    sidewalk_final_edges, sidewalk_neighbors = _geometry_edges(
        sidewalk_fuse.geometry())
    sidewalk_final_positions = list(sidewalk_neighbors.keys())

    def nearest_sidewalk(position, tolerance: float = 0.002):
        best = None
        best_distance_sq = tolerance * tolerance
        for candidate in sidewalk_final_positions:
            # SIDEWALK_PLANAR_CONSTRAINT_HEIGHT intentionally raises all
            # constraints to the sidewalk plane, so topology matching is XZ.
            distance_sq = (
                (position[0] - candidate[0]) ** 2
                + (position[2] - candidate[2]) ** 2)
            if distance_sq <= best_distance_sq:
                best = candidate
                best_distance_sq = distance_sq
        return best

    sidewalk_outgoing_counts = []
    sidewalk_alignment_samples = []
    for primitive in sidewalk_geometry.prims():
        points = primitive.points()
        start = _position_key(points[0].position())
        end = _position_key(points[1].position())
        mapped_start = nearest_sidewalk(start)
        if mapped_start is None:
            sidewalk_outgoing_counts.append(0)
            continue
        direction = (end[0] - start[0], end[2] - start[2])
        direction_length = max(
            (direction[0] ** 2 + direction[1] ** 2) ** 0.5, 1e-12)
        outgoing = 0
        alignments = []
        for neighbor in sidewalk_neighbors.get(mapped_start, set()):
            candidate = (
                neighbor[0] - mapped_start[0],
                neighbor[2] - mapped_start[2])
            candidate_length = max(
                (candidate[0] ** 2 + candidate[1] ** 2) ** 0.5, 1e-12)
            alignment = (
                direction[0] * candidate[0]
                + direction[1] * candidate[1]) / (
                    direction_length * candidate_length)
            alignments.append((alignment, candidate_length))
            if alignment >= 0.999:
                outgoing += 1
        sidewalk_outgoing_counts.append(outgoing)
        sidewalk_alignment_samples.append(sorted(alignments, reverse=True)[:4])
    if any(count != 1 for count in sidewalk_outgoing_counts):
        raise RuntimeError(
            "V10 sidewalk endpoint must have exactly one outward constraint: "
            f"counts={sidewalk_outgoing_counts} "
            f"alignments={sidewalk_alignment_samples}")

    return {
        "warnings": warnings,
        "corner_section_lines": section_count,
        "duplicate_lines": len(constraints) - len(set(constraints)),
        "lines_per_sample": lines_per_sample,
        "constraints_preserved": len(constraints) - len(missing),
        "max_boundary_snap_distance": max_snap_distance,
        "section_endpoint_max_neighbor_count": max(endpoint_degrees or [0]),
        "sidewalk_section_lines": sidewalk_count,
        "sidewalk_lines_per_endpoint": sidewalk_lines_per_endpoint,
        "sidewalk_outgoing_counts": sidewalk_outgoing_counts,
        "sidewalk_final_points": len(sidewalk_fuse.geometry().points()),
        "sidewalk_final_primitives": len(sidewalk_fuse.geometry().prims()),
        "final_points": len(triangulated_geometry.points()),
        "final_primitives": len(triangulated_geometry.prims()),
    }


def apply_live_patch(save: bool = True, create_backup: bool = True, hou_module=None):
    global hou
    if hou_module is not None:
        hou = hou_module
    if hou is None:
        raise RuntimeError("A Houdini hou module is required")

    asset = hou.node(ASSET_PATH)
    if asset is None or asset.type().name() != EXPECTED_TYPE:
        raise RuntimeError(f"Expected live {EXPECTED_TYPE} at {ASSET_PATH}")
    definition = asset.type().definition()
    if definition is None:
        raise RuntimeError("CityRoad node has no HDA definition")
    library = definition.libraryFilePath().replace("\\", "/")
    if not library.endswith(EXPECTED_HDA_SUFFIX):
        raise RuntimeError(f"Unexpected CityRoad definition: {library}")

    core = _require_node(asset, "CityRoadCore")
    builder = _require_node(core, "ROAD_BUILD_ADAPTIVE_CORNER_SURFACE")
    merge = _require_node(core, "CITYROAD_MERGE_ROAD_BOUNDARY_PARTITIONS_V7")
    sidewalk_merge = _require_node(core, "SIDEWALK_PLANAR_CONSTRAINT_MERGE")
    sidewalk_classify = _require_node(core, "SIDEWALK_PLANAR_CLASSIFY")
    triangulate = _require_node(core, "ROAD_PLANAR_TRIANGULATE_FINAL_BOUNDARY")
    if MARKER not in builder.parm("snippet").eval():
        # V10 depends on the V8 paired two-rail corner contract.
        if "CITYROAD_V8_MOBILE_TWO_BOUNDARY_RAILS" not in builder.parm("snippet").eval():
            raise RuntimeError("V10 requires the V8 two-boundary-rail corner builder")
    if "CITYROAD_V9_FINAL_BOUNDARY_MOBILE_CAP" not in _require_node(
            core, "ROAD_UNION_ROUND_FINAL_BOUNDARY").parm("snippet").eval():
        raise RuntimeError("V10 requires the V9 final boundary patch")

    interface_before = asset.parmTemplateGroup().asDialogScript()
    backup_path = _backup_definition(definition) if create_backup else None
    was_locked = asset.isLockedHDA()
    if was_locked:
        asset.allowEditingOfContents(propagate=True)

    section_node = core.node(NODE_NAME)
    created = section_node is None
    sidewalk_section_node = core.node(SIDEWALK_NODE_NAME)
    sidewalk_created = sidewalk_section_node is None
    sidewalk_fuse = core.node(SIDEWALK_FUSE_NODE_NAME)
    sidewalk_fuse_created = sidewalk_fuse is None
    old_input_2 = merge.input(2)
    old_sidewalk_input_3 = sidewalk_merge.input(3)
    old_sidewalk_classify_input_0 = sidewalk_classify.input(0)
    try:
        with hou.undos.group("CityRoad V10 single corner sections"):
            if section_node is None:
                section_node = core.createNode("attribwrangle", NODE_NAME)
            section_node.setInput(0, builder)
            section_node.setInput(
                1, _require_node(core, "SIDEWALK_PLANAR_ROAD_BOUNDARY_CLEAN"))
            section_node.parm("class").set(0)
            section_node.parm("snippet").set(SECTION_VEX)
            section_node.setComment(
                "V10：直角弯每对左右采样点只生成一条横向截面约束；"
                "四段弯道即五条截面线，禁止最终三角化形成线束。")
            merge.setInput(2, section_node)
            merge.setComment(
                "V10：输入 2 为唯一角弯横向截面线；Triangulate2D 必须保留这些约束。")
            if sidewalk_section_node is None:
                sidewalk_section_node = core.createNode(
                    "attribwrangle", SIDEWALK_NODE_NAME)
            sidewalk_section_node.setInput(0, section_node)
            sidewalk_section_node.setInput(
                1, _require_node(core, "SIDEWALK_PLANAR_SITE_CLEAN"))
            sidewalk_section_node.setInput(
                2, _require_node(core, "SIDEWALK_PLANAR_ROAD_BOUNDARY_CLEAN"))
            sidewalk_section_node.parm("class").set(0)
            sidewalk_section_node.parm("snippet").set(SIDEWALK_SECTION_VEX)
            sidewalk_section_node.setComment(
                "V10：道路五条角弯截面的十个端点，各向人行道仅延伸一条约束线；"
                "禁止人行道三角化在端点形成线束。")
            sidewalk_merge.setInput(3, sidewalk_section_node)
            sidewalk_merge.setComment(
                "V10：输入 3 为十条唯一人行道角弯截面约束。")
            if sidewalk_fuse is None:
                sidewalk_fuse = core.createNode(
                    "fuse::2.0", SIDEWALK_FUSE_NODE_NAME)
            sidewalk_fuse.setInput(
                0, _require_node(core, "SIDEWALK_PLANAR_TRIANGULATE"))
            sidewalk_fuse.parm("usetol3d").set(1)
            sidewalk_fuse.parm("tol3d").set(0.0005)
            sidewalk_fuse.parm("deldegen").set(1)
            sidewalk_fuse.parm("deldegenpoints").set(1)
            sidewalk_fuse.parm("delunusedpoints").set(1)
            sidewalk_fuse.setComment(
                "V10：仅合并 Triangulate2D 产生的 0.5 mm 内重复端点/微型边。")
            sidewalk_classify.setInput(0, sidewalk_fuse)

        if asset.parmTemplateGroup().asDialogScript() != interface_before:
            raise RuntimeError("V10 unexpectedly changed the public HDA parameter interface")

        validation = _validate(core)
        if save:
            definition.updateFromNode(asset)
            hou.hipFile.save()
    except Exception:
        merge.setInput(2, old_input_2)
        sidewalk_merge.setInput(3, old_sidewalk_input_3)
        sidewalk_classify.setInput(0, old_sidewalk_classify_input_0)
        if created and section_node is not None:
            section_node.destroy()
        if sidewalk_created and sidewalk_section_node is not None:
            sidewalk_section_node.destroy()
        if sidewalk_fuse_created and sidewalk_fuse is not None:
            sidewalk_fuse.destroy()
        triangulate.cook(force=True)
        raise

    return {
        "asset": asset.path(),
        "definition": definition.libraryFilePath(),
        "hip": hou.hipFile.path(),
        "backup": str(backup_path) if backup_path else None,
        "was_locked": was_locked,
        "saved": save,
        "node": section_node.path(),
        "validation": validation,
    }


if __name__ == "__main__":
    print(apply_live_patch())
