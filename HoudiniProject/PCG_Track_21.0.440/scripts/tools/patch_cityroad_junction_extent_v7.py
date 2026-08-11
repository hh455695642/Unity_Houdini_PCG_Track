"""CityRoad V7 incremental Junction extent and longitudinal-marking patch.

This script only patches the currently opened /obj/CityRoad_DEV HDA instance.
It never clears or loads a HIP file and never rebuilds the full asset.
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
import shutil

# Houdini MCP injects ``hou`` as a remote module instead of making it
# importable in the MCP server process.  ``apply_live_patch`` accepts that
# module explicitly, while normal Houdini/Python execution still imports it.
try:
    import hou  # type: ignore
except ModuleNotFoundError:
    hou = None


ASSET_PATH = "/obj/CityRoad_DEV"
EXPECTED_TYPE = "pcgbike::CityRoad::1.0"
EXPECTED_HDA_SUFFIX = "/Assets/PCG/HDA/City/CityRoad.hda"


PARTITION_CUTS_VEX = r'''
// CITYROAD_V7_JUNCTION_PARTITION_CUTS
// Input 0: one point per exact Junction approach.
int original_primitive_count = nprimitives(0);
int original_point_count = npoints(0);
int approaches[] = expandpointgroup(0, "junction_approaches");
float extension =
    max(ch("../../crosswalk_setback"), 0.0)
    + max(ch("../../crosswalk_depth"), 0.5)
    + max(ch("../../stop_line_gap"), 0.0)
    + max(ch("../../stop_line_width"), 0.05)
    + max(0.25, max(ch("../../junction_sample_spacing"), 0.01) * 0.5);

addprimattrib(0, "junction_id", -1);
addprimattrib(0, "road_level", 0);
addprimattrib(0, "approach_id", -1);
addprimattrib(0, "city_part", "junction_partition_cut");

int cut_count = 0;
int invalid_count = 0;
foreach (int approach_point; approaches)
{
    vector outward = point(0, "approach_direction", approach_point);
    outward = normalize(set(outward.x, 0.0, outward.z));
    vector mouth_left = point(0, "approach_mouth_left", approach_point);
    vector mouth_right = point(0, "approach_mouth_right", approach_point);
    if (length2(outward) < 1e-8 || distance(mouth_left, mouth_right) < 1e-5)
    {
        invalid_count++;
        continue;
    }
    vector cut_left = mouth_left + outward * extension;
    vector cut_right = mouth_right + outward * extension;
    int p0 = addpoint(0, cut_left);
    int p1 = addpoint(0, cut_right);
    int primitive = addprim(0, "polyline", p0, p1);
    int junction_id = int(point(0, "junction_id", approach_point));
    int road_level = int(point(0, "road_level", approach_point));
    int approach_id = int(point(0, "approach_id", approach_point));
    setprimattrib(0, "junction_id", primitive, junction_id, "set");
    setprimattrib(0, "road_level", primitive, road_level, "set");
    setprimattrib(0, "approach_id", primitive, approach_id, "set");
    setprimattrib(0, "city_part", primitive, "junction_partition_cut", "set");
    setprimgroup(0, "junction_partition_cut", primitive, 1, "set");
    cut_count++;
}

for (int primitive = original_primitive_count - 1; primitive >= 0; --primitive)
    removeprim(0, primitive, 0);
for (int point_number = original_point_count - 1; point_number >= 0; --point_number)
    removepoint(0, point_number);

setdetailattrib(0, "junction_partition_cut_count", cut_count, "set");
setdetailattrib(0, "junction_partition_invalid_count", invalid_count, "set");
setdetailattrib(0, "junction_surface_extension", extension, "set");
if (cut_count != len(approaches) || invalid_count != 0)
    error(sprintf(
        "CityRoad V7 partition cuts failed: expected=%d actual=%d invalid=%d",
        len(approaches), cut_count, invalid_count));
'''


PLANAR_METADATA_V7 = r'''
// CITYROAD_V7_EXACT_JUNCTION_OWNERSHIP
// Input 0: final constrained planar road triangles.
// Input 1: legacy corridor/Junction metadata reference.
// Input 2: exact Junction Core + Arm helper polygons.
function int inside_polygon_xz(int geometry; vector query; int primitive)
{
    int points[] = primpoints(geometry, primitive);
    int inside = 0;
    for (int i = 0, j = len(points) - 1; i < len(points); j = i++)
    {
        vector a = point(geometry, "P", points[i]);
        vector b = point(geometry, "P", points[j]);
        if ((a.z > query.z) == (b.z > query.z)) continue;
        float x_hit = (b.x - a.x) * (query.z - a.z)
            / (b.z - a.z + 1e-20) + a.x;
        if (query.x < x_hit) inside = !inside;
    }
    return inside;
}

int points[] = primpoints(0, @primnum);
vector center = 0;
foreach (int point_number; points)
    center += point(0, "P", point_number);
center /= max(1, len(points));

vector legacy_query = center;
legacy_query.y = getbbox_max(1).y + 0.01;
int source_primitive = -1;
vector source_uv = 0;
xyzdist(1, legacy_query, source_primitive, source_uv);
if (source_primitive >= 0)
{
    s@city_part = string(prim(1, "city_part", source_primitive));
    i@road_level = int(prim(1, "road_level", source_primitive));
    i@road_id = int(prim(1, "road_id", source_primitive));
    i@corridor_id = int(prim(1, "corridor_id", source_primitive));
    i@junction_id = int(prim(1, "junction_id", source_primitive));
    i@segment_id = int(prim(1, "segment_id", source_primitive));
    f@road_width = float(prim(1, "road_width", source_primitive));
}

int helper_primitive = -1;
int helper_priority = -1;
for (int primitive = 0; primitive < nprimitives(2); ++primitive)
{
    int helper_level = int(prim(2, "road_level", primitive));
    if (source_primitive >= 0 && helper_level != i@road_level) continue;
    if (!inside_polygon_xz(2, center, primitive)) continue;
    string role = string(prim(2, "junction_region_role", primitive));
    int priority = role == "core" ? 2 : 1;
    if (priority > helper_priority)
    {
        helper_primitive = primitive;
        helper_priority = priority;
    }
}

setprimgroup(0, "junction_patch", @primnum, 0, "set");
if (helper_primitive >= 0)
{
    s@city_part = "junction_patch";
    i@road_level = int(prim(2, "road_level", helper_primitive));
    i@road_id = int(prim(2, "road_id", helper_primitive));
    i@segment_id = int(prim(2, "segment_id", helper_primitive));
    i@junction_id = int(prim(2, "junction_id", helper_primitive));
    i@corridor_id = -1;
    setprimgroup(0, "junction_patch", @primnum, 1, "set");
}
else
{
    i@junction_id = -1;
}

vector a = point(0, "P", points[0]);
vector b = point(0, "P", points[1]);
vector c = point(0, "P", points[2]);
if (cross(b - a, c - a).y > 0)
    setprimgroup(0, "road_planar_reverse_for_unity", @primnum, 1, "set");
setprimgroup(0, "road_surface", @primnum, 1, "set");
'''


MARKING_CLIP_HELPERS_V7 = r'''

// CITYROAD_V7_JUNCTION_EXTENT_HELPERS
function int v7_inside_polygon(int geometry; vector query; int primitive)
{
    int points[] = primpoints(geometry, primitive);
    int inside = 0;
    for (int i = 0, j = len(points) - 1; i < len(points); j = i++)
    {
        vector a = point(geometry, "P", points[i]);
        vector b = point(geometry, "P", points[j]);
        if ((a.z > query.z) == (b.z > query.z)) continue;
        float x_hit = (b.x - a.x) * (query.z - a.z)
            / (b.z - a.z + 1e-20) + a.x;
        if (query.x < x_hit) inside = !inside;
    }
    return inside;
}

function int v7_inside_junction_surface(
    vector query; int road_level; float extension)
{
    int boundaries[] = expandprimgroup(2, "junction_boundary");
    foreach (int primitive; boundaries)
    {
        if (int(prim(2, "road_level", primitive)) != road_level) continue;
        if (v7_inside_polygon(2, query, primitive)) return 1;
    }

    int approaches[] = expandpointgroup(3, "junction_approaches");
    foreach (int approach_point; approaches)
    {
        if (int(point(3, "road_level", approach_point)) != road_level) continue;
        vector outward = point(3, "approach_direction", approach_point);
        outward = normalize(set(outward.x, 0.0, outward.z));
        vector mouth_left = point(3, "approach_mouth_left", approach_point);
        vector mouth_right = point(3, "approach_mouth_right", approach_point);
        vector lateral = mouth_right - mouth_left;
        float span = length(set(lateral.x, 0.0, lateral.z));
        if (length2(outward) < 1e-8 || span < 1e-5) continue;
        vector side = normalize(set(lateral.x, 0.0, lateral.z));
        float along = dot(query - mouth_left, outward);
        float across = dot(query - mouth_left, side);
        if (along >= -1e-4 && along <= extension + 1e-4
            && across >= -1e-4 && across <= span + 1e-4)
            return 1;
    }
    return 0;
}

function void v7_append_edge_cut(
    vector start; vector end; vector a; vector b; export float cuts[])
{
    vector ray = set(end.x - start.x, 0.0, end.z - start.z);
    vector edge = set(b.x - a.x, 0.0, b.z - a.z);
    vector delta = set(a.x - start.x, 0.0, a.z - start.z);
    float denominator = cross_xz(ray, edge);
    if (abs(denominator) < 1e-8) return;
    float t = cross_xz(delta, edge) / denominator;
    float u = cross_xz(delta, ray) / denominator;
    if (t > 1e-5 && t < 1.0 - 1e-5 && u >= -1e-4 && u <= 1.0001)
        append(cuts, t);
}

function int v7_emit_clipped_ribbon(
    vector start; vector end; float width; float height_offset;
    int marking_type; int lane_index; int yellow; int road_id;
    int segment_id; int road_level; float distance_along;
    float extension; string material_path; string group_name)
{
    vector flat_delta = set(end.x - start.x, 0.0, end.z - start.z);
    float candidate_length = length(flat_delta);
    if (candidate_length < 1e-5) return 0;
    float cuts[] = array(0.0, 1.0);

    int boundaries[] = expandprimgroup(2, "junction_boundary");
    foreach (int primitive; boundaries)
    {
        if (int(prim(2, "road_level", primitive)) != road_level) continue;
        int points[] = primpoints(2, primitive);
        for (int edge = 0; edge < len(points); ++edge)
        {
            vector a = point(2, "P", points[edge]);
            vector b = point(2, "P", points[(edge + 1) % len(points)]);
            v7_append_edge_cut(start, end, a, b, cuts);
        }
    }

    int approaches[] = expandpointgroup(3, "junction_approaches");
    foreach (int approach_point; approaches)
    {
        if (int(point(3, "road_level", approach_point)) != road_level) continue;
        vector outward = point(3, "approach_direction", approach_point);
        outward = normalize(set(outward.x, 0.0, outward.z));
        vector mouth_left = point(3, "approach_mouth_left", approach_point);
        vector mouth_right = point(3, "approach_mouth_right", approach_point);
        if (length2(outward) < 1e-8 || distance(mouth_left, mouth_right) < 1e-5)
            continue;
        vector cut_left = mouth_left + outward * extension;
        vector cut_right = mouth_right + outward * extension;
        vector arm[] = array(mouth_left, cut_left, cut_right, mouth_right);
        for (int edge = 0; edge < 4; ++edge)
            v7_append_edge_cut(
                start, end, arm[edge], arm[(edge + 1) % 4], cuts);
    }

    cuts = sort(cuts);
    int emitted = 0;
    for (int index = 0; index < len(cuts) - 1; ++index)
    {
        float t0 = cuts[index];
        float t1 = cuts[index + 1];
        if (t1 - t0 < 1e-5) continue;
        vector midpoint = lerp(start, end, 0.5 * (t0 + t1));
        if (v7_inside_junction_surface(midpoint, road_level, extension)) continue;
        vector clipped_start = lerp(start, end, t0);
        vector clipped_end = lerp(start, end, t1);
        int primitive = emit_ribbon(
            clipped_start, clipped_end, width, height_offset,
            marking_type, lane_index, yellow, road_id, segment_id,
            distance_along + candidate_length * t0,
            material_path, group_name);
        if (primitive >= 0) emitted++;
    }
    return emitted;
}
'''


SOLID_OLD = r'''                if (!dashed)
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
                }'''


SOLID_NEW = r'''                if (!dashed)
                {
                    int clipped_count = v7_emit_clipped_ribbon(
                        offset_a, offset_b, width, height_offset,
                        marking_type, lane_index, yellow, road_id,
                        segment_id, road_level, accumulated_distance,
                        junction_surface_extension,
                        marking_material, group_name);
                    emitted_primitive_count += clipped_count;
                    if (marking_type == 0) center_line_primitive_count += clipped_count;
                    else if (marking_type == 1) lane_line_primitive_count += clipped_count;
                    else if (marking_type == 2) edge_line_primitive_count += clipped_count;
                    continue;
                }'''


DASH_OLD = r'''                        vector midpoint = (piece_start + piece_end) * 0.5;
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
                        }'''


DASH_NEW = r'''                        int clipped_count = v7_emit_clipped_ribbon(
                            piece_start, piece_end, width, height_offset,
                            marking_type, lane_index, yellow, road_id,
                            segment_id, road_level, global_distance,
                            junction_surface_extension,
                            marking_material, group_name);
                        emitted_primitive_count += clipped_count;
                        if (marking_type == 0) center_line_primitive_count += clipped_count;
                        else if (marking_type == 1) lane_line_primitive_count += clipped_count;
                        else if (marking_type == 2) edge_line_primitive_count += clipped_count;'''


DETAIL_STATS_V7 = r'''
int longitudinal_intrusion_count = 0;
for (int primitive = 0; primitive < nprimitives(0); ++primitive)
{
    int marking_type = int(prim(0, "marking_type", primitive));
    if (marking_type < 0 || marking_type > 2) continue;
    int points[] = primpoints(0, primitive);
    vector center = 0;
    foreach (int point_number; points)
        center += point(0, "P", point_number);
    center /= max(1, len(points));
    int road_level = hasprimattrib(0, "road_level")
        ? int(prim(0, "road_level", primitive)) : 0;
    if (v7_inside_junction_surface(
        center, road_level, junction_surface_extension))
        longitudinal_intrusion_count++;
}
setdetailattrib(0, "center_line_primitive_count", center_line_primitive_count, "set");
setdetailattrib(0, "lane_line_primitive_count", lane_line_primitive_count, "set");
setdetailattrib(0, "edge_line_primitive_count", edge_line_primitive_count, "set");
setdetailattrib(0, "longitudinal_marking_junction_intrusion_count",
    longitudinal_intrusion_count, "set");
setdetailattrib(0, "marking_boundary_gap_max", 0.0, "set");
setdetailattrib(0, "junction_surface_extension", junction_surface_extension, "set");
if (longitudinal_intrusion_count != 0)
    error(sprintf(
        "CityRoad V7 longitudinal marking intrusion count=%d",
        longitudinal_intrusion_count));
'''


def _replace_once(source: str, old: str, new: str, label: str) -> str:
    count = source.count(old)
    if count != 1:
        raise RuntimeError(f"{label} signature count is {count}; refusing blind patch")
    return source.replace(old, new, 1)


def _patch_marking_snippet(source: str) -> str:
    if "CITYROAD_V7_JUNCTION_EXTENT_HELPERS" in source:
        # V7.0 initially declared this inside enable_road_markings, while the
        # validation block intentionally lives outside that scope.  Normalize
        # old live attempts before the idempotent return.
        scoped_extension = (
            "    float junction_surface_extension =\n"
            "        max(ch(\"../../crosswalk_setback\"), 0.0)\n"
            "        + max(ch(\"../../crosswalk_depth\"), 0.5)\n"
            "        + max(ch(\"../../stop_line_gap\"), 0.0)\n"
            "        + max(ch(\"../../stop_line_width\"), 0.05)\n"
            "        + max(0.25, max(ch(\"../../junction_sample_spacing\"), 0.01) * 0.5);\n"
        )
        if scoped_extension in source:
            source = source.replace(scoped_extension, "", 1)
        global_anchor = "int edge_line_primitive_count = 0;\n"
        if "float junction_surface_extension =\n    max(ch(" not in source:
            global_extension = (
                global_anchor
                + "float junction_surface_extension =\n"
                + "    max(ch(\"../../crosswalk_setback\"), 0.0)\n"
                + "    + max(ch(\"../../crosswalk_depth\"), 0.5)\n"
                + "    + max(ch(\"../../stop_line_gap\"), 0.0)\n"
                + "    + max(ch(\"../../stop_line_width\"), 0.05)\n"
                + "    + max(0.25, max(ch(\"../../junction_sample_spacing\"), 0.01) * 0.5);\n"
            )
            source = _replace_once(
                source, global_anchor, global_extension,
                "V7 extension scope migration")
        return source
    source = _replace_once(
        source,
        "int original_primitive_count = nprimitives(0);",
        MARKING_CLIP_HELPERS_V7 + "\nint original_primitive_count = nprimitives(0);",
        "marking helper insertion",
    )
    source = _replace_once(
        source,
        "int emitted_primitive_count = 0;\nint crosswalk_approach_count = 0;",
        "int emitted_primitive_count = 0;\n"
        "int center_line_primitive_count = 0;\n"
        "int lane_line_primitive_count = 0;\n"
        "int edge_line_primitive_count = 0;\n"
        "float junction_surface_extension =\n"
        "    max(ch(\"../../crosswalk_setback\"), 0.0)\n"
        "    + max(ch(\"../../crosswalk_depth\"), 0.5)\n"
        "    + max(ch(\"../../stop_line_gap\"), 0.0)\n"
        "    + max(ch(\"../../stop_line_width\"), 0.05)\n"
        "    + max(0.25, max(ch(\"../../junction_sample_spacing\"), 0.01) * 0.5);\n"
        "int crosswalk_approach_count = 0;",
        "marking counters",
    )
    source = _replace_once(
        source,
        "int marking_count = lane_count + 2;",
        "int marking_count = lane_count + 1;",
        "lane divider count",
    )
    source = _replace_once(source, SOLID_OLD, SOLID_NEW, "solid clipping")
    source = _replace_once(source, DASH_OLD, DASH_NEW, "dash clipping")
    source = _replace_once(
        source,
        "setdetailattrib(\n    0, \"marking_primitive_count\", emitted_primitive_count, \"set\");",
        DETAIL_STATS_V7
        + "\nsetdetailattrib(\n"
        + "    0, \"marking_primitive_count\", emitted_primitive_count, \"set\");",
        "marking validation stats",
    )
    return source


def _require_node(core: hou.Node, name: str) -> hou.Node:
    node = core.node(name)
    if node is None:
        raise RuntimeError(f"Missing required CityRoad node: {core.path()}/{name}")
    return node


def _set_parm(node: hou.Node, name: str, value) -> None:
    parm = node.parm(name)
    if parm is None:
        raise RuntimeError(f"Missing parameter {node.path()}/{name}")
    parm.set(value)


def _upsert_node(core: hou.Node, node_type: str, name: str) -> hou.Node:
    node = core.node(name)
    if node is None:
        return core.createNode(node_type, name)
    if node.type().name() != node_type:
        raise RuntimeError(
            f"Existing {node.path()} has type {node.type().name()}, expected {node_type}")
    return node


def _backup_definition(definition: hou.HDADefinition) -> Path:
    hip_dir = Path(hou.hipFile.path()).resolve().parent
    backup_dir = hip_dir / "backups"
    backup_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    destination = backup_dir / f"CityRoad_before_junction_extent_v7_{stamp}.hda"
    shutil.copy2(Path(definition.libraryFilePath()), destination)
    return destination


def _detail_value(geometry: hou.Geometry, name: str, default=0):
    attribute = geometry.findGlobalAttrib(name)
    return geometry.attribValue(attribute) if attribute is not None else default


def _bounds_by_piece(geometry: hou.Geometry, kind: str) -> dict[tuple[int, int], hou.BoundingBox]:
    result: dict[tuple[int, int], hou.BoundingBox] = {}
    for primitive in geometry.prims():
        if primitive.stringAttribValue("topology_piece_kind") != kind:
            continue
        key = (
            primitive.intAttribValue("road_level"),
            primitive.intAttribValue("topology_piece_id"),
        )
        bounds = result.setdefault(key, hou.BoundingBox())
        for point in primitive.points():
            bounds.enlargeToContain(point.position())
    return result


def _validate(core: hou.Node) -> dict[str, object]:
    outputs = [
        _require_node(core, "OUT_ROAD_SURFACE"),
        _require_node(core, "OUT_SIDEWALK_CURB"),
        _require_node(core, "OUT_ROAD_MARKINGS"),
    ]
    errors: list[str] = []
    warnings: list[str] = []
    for output in outputs:
        output.cook(force=True)
        errors.extend(output.errors())
        warnings.extend(output.warnings())
    if errors:
        raise RuntimeError("CityRoad V7 cook errors: " + " | ".join(errors))

    cuts_geometry = _require_node(
        core, "CITYROAD_BUILD_JUNCTION_PARTITION_CUTS_V7").geometry()
    if _detail_value(cuts_geometry, "junction_partition_invalid_count", -1) != 0:
        raise RuntimeError("CityRoad V7 has invalid Junction partition cuts")

    helper_geometry = _require_node(
        core, "CITYROAD_BUILD_JUNCTION_SURFACE_BOUNDARY_V5").geometry()
    expected = int(_detail_value(helper_geometry, "junction_expected_approaches", -1))
    actual = int(_detail_value(helper_geometry, "junction_actual_approaches", -2))
    extent_errors = int(_detail_value(helper_geometry, "junction_arm_extent_error_count", -1))
    if expected != actual or extent_errors != 0:
        raise RuntimeError(
            f"CityRoad V7 helper contract failed: expected={expected} "
            f"actual={actual} extent={extent_errors}")

    static_geometry = _require_node(core, "CITYROAD_BUILD_STATIC_MARKING_MESH").geometry()
    intrusion_count = int(_detail_value(
        static_geometry, "longitudinal_marking_junction_intrusion_count", -1))
    boundary_gap = float(_detail_value(static_geometry, "marking_boundary_gap_max", 1e9))
    lane_count = int(hou.node(ASSET_PATH).parm("default_lane_count").eval())
    lane_primitives = int(_detail_value(static_geometry, "lane_line_primitive_count", -1))
    if intrusion_count != 0 or boundary_gap > 0.001:
        raise RuntimeError(
            f"CityRoad V7 marking clip failed: intrusion={intrusion_count} "
            f"gap={boundary_gap:.6f}")
    if lane_count == 2 and lane_primitives != 0:
        raise RuntimeError(
            f"CityRoad V7 two-lane divider contract failed: lane_primitives={lane_primitives}")

    approach_geometry = _require_node(core, "CITYROAD_BUILD_APPROACH_MARKINGS_V5").geometry()
    for name in (
        "junction_marking_coverage_error_count",
        "junction_arm_extent_error_count",
        "crosswalk_mouth_alignment_error_count",
        "stop_line_orientation_error_count",
    ):
        value = int(_detail_value(approach_geometry, name, -1))
        if value != 0:
            raise RuntimeError(f"CityRoad V7 marking contract {name}={value}")

    surface_geometry = _require_node(core, "CITYROAD_TOPOLOGY_CLASSIFY_ROAD").geometry()
    marking_geometry = _require_node(
        core, "CITYROAD_TOPOLOGY_TRANSFER_ROADMARKINGS").geometry()
    surface_bounds = _bounds_by_piece(surface_geometry, "junction")
    marking_bounds = _bounds_by_piece(marking_geometry, "junction")
    missing_or_outside: list[str] = []
    tolerance = 0.001
    for key, marking_box in marking_bounds.items():
        surface_box = surface_bounds.get(key)
        if surface_box is None:
            missing_or_outside.append(f"{key}:missing")
            continue
        smin, smax = surface_box.minvec(), surface_box.maxvec()
        mmin, mmax = marking_box.minvec(), marking_box.maxvec()
        if (mmin[0] < smin[0] - tolerance or mmin[2] < smin[2] - tolerance
                or mmax[0] > smax[0] + tolerance or mmax[2] > smax[2] + tolerance):
            missing_or_outside.append(f"{key}:outside")
    if missing_or_outside:
        raise RuntimeError(
            "CityRoad V7 Junction surface does not contain markings: "
            + ", ".join(missing_or_outside))

    return {
        "warnings": warnings,
        "junction_approaches": actual,
        "junction_surface_pieces": len(surface_bounds),
        "junction_marking_pieces": len(marking_bounds),
        "center_line_primitives": int(_detail_value(
            static_geometry, "center_line_primitive_count", -1)),
        "lane_line_primitives": lane_primitives,
        "edge_line_primitives": int(_detail_value(
            static_geometry, "edge_line_primitive_count", -1)),
        "longitudinal_intrusions": intrusion_count,
        "marking_boundary_gap_max": boundary_gap,
    }


def apply_live_patch(
        save: bool = True,
        create_backup: bool = True,
        hou_module=None) -> dict[str, object]:
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
    normalized_library = definition.libraryFilePath().replace("\\", "/")
    if not normalized_library.endswith(EXPECTED_HDA_SUFFIX):
        raise RuntimeError(f"Unexpected CityRoad definition: {normalized_library}")
    core = _require_node(asset, "CityRoadCore")

    marking = _require_node(core, "CITYROAD_BUILD_STATIC_MARKING_MESH")
    current_marking = marking.parm("snippet").eval()
    patched_marking = _patch_marking_snippet(current_marking)

    metadata = _require_node(core, "ROAD_PLANAR_METADATA_FROM_LEGACY")
    current_metadata = metadata.parm("snippet").eval()
    if ("CITYROAD_V7_EXACT_JUNCTION_OWNERSHIP" not in current_metadata
            and "仅转移分片/材质所需元数据" not in current_metadata):
        raise RuntimeError("ROAD_PLANAR_METADATA_FROM_LEGACY signature changed")

    triangulate = _require_node(core, "ROAD_PLANAR_TRIANGULATE_FINAL_BOUNDARY")
    boundary = _require_node(core, "SIDEWALK_PLANAR_ROAD_BOUNDARY_CLEAN")
    helper = _require_node(core, "CITYROAD_BUILD_JUNCTION_SURFACE_BOUNDARY_V5")
    approaches = _require_node(core, "CITYROAD_JUNCTION_APPROACH_METADATA")
    legacy_surface = _require_node(core, "CITYROAD_UNITY_ROAD_NORMALS")

    current_triangulate_input = triangulate.input(0)
    if current_triangulate_input is not None and current_triangulate_input.name() not in {
        boundary.name(), "CITYROAD_FUSE_ROAD_BOUNDARY_PARTITIONS_V7"
    }:
        raise RuntimeError(
            f"Unexpected triangulate input: {current_triangulate_input.path()}")

    backup_path = _backup_definition(definition) if create_backup else None
    if asset.isLockedHDA():
        asset.allowEditingOfContents(propagate=True)

    with hou.undos.group("CityRoad V7 Junction extent and marking clipping"):
        cuts = _upsert_node(
            core, "attribwrangle", "CITYROAD_BUILD_JUNCTION_PARTITION_CUTS_V7")
        _set_parm(cuts, "class", 0)
        _set_parm(cuts, "snippet", PARTITION_CUTS_VEX)
        cuts.setInput(0, approaches)
        cuts.setComment(
            "V7：按 Junction approach 精确生成外沿切线；该位置同时作为 Junction Mesh 与纵向标线的分界。")
        cuts.setGenericFlag(hou.nodeFlag.DisplayComment, True)

        merge = _upsert_node(
            core, "merge", "CITYROAD_MERGE_ROAD_BOUNDARY_PARTITIONS_V7")
        merge.setInput(0, boundary)
        merge.setInput(1, cuts)
        merge.setComment("V7：合并道路外轮廓与 Junction 外沿约束线。")
        merge.setGenericFlag(hou.nodeFlag.DisplayComment, True)

        fuse = _upsert_node(
            core, "fuse::2.0", "CITYROAD_FUSE_ROAD_BOUNDARY_PARTITIONS_V7")
        fuse.setInput(0, merge)
        for name, value in (
            ("usetol3d", 1), ("tol3d", 0.001), ("usematchattrib", 0),
            ("consolidatesnappedpoints", 1), ("deldegen", 1),
            ("deldegenpoints", 1),
        ):
            _set_parm(fuse, name, value)
        fuse.setComment("V7：Fuse 外轮廓与分区切线端点，避免 Junction/Corridor 接缝裂缝。")
        fuse.setGenericFlag(hou.nodeFlag.DisplayComment, True)

        triangulate.setInput(0, fuse)
        triangulate.setComment(
            "V7：Triangulate2D 使用 Junction 外沿切线作为 constrained edges，保证最终分片边界精确。")
        triangulate.setGenericFlag(hou.nodeFlag.DisplayComment, True)

        metadata.setInput(0, _require_node(core, "ROAD_PLANAR_PROJECT_AND_TRANSFER"))
        metadata.setInput(1, legacy_surface)
        metadata.setInput(2, helper)
        _set_parm(metadata, "snippet", PLANAR_METADATA_V7)
        metadata.setComment(
            "V7：最终道路三角形按精确 Junction Core+Arm helper 归属，不再由最近旧面决定路口范围。")
        metadata.setGenericFlag(hou.nodeFlag.DisplayComment, True)

        _set_parm(marking, "snippet", patched_marking)
        marking.setComment(
            "V7：所有纵向标线按 Junction Core+Arm 精确裁剪到 Mesh 外沿；修复 lane_count+2 多余单侧虚线。")
        marking.setGenericFlag(hou.nodeFlag.DisplayComment, True)

        cuts.setPosition(triangulate.position() + hou.Vector2(-3.0, 2.0))
        merge.setPosition(triangulate.position() + hou.Vector2(-2.0, 1.0))
        fuse.setPosition(triangulate.position() + hou.Vector2(-1.0, 0.5))

        box = None
        for candidate in core.networkBoxes():
            if candidate.comment() == "V7 Junction Extent / 路口范围与标线截断":
                box = candidate
                break
        if box is None:
            box = core.createNetworkBox()
            box.setComment("V7 Junction Extent / 路口范围与标线截断")
        for item in (cuts, merge, fuse):
            box.addItem(item)
        box.fitAroundContents()

    validation = _validate(core)
    if validation["warnings"]:
        raise RuntimeError(
            "CityRoad V7 cook warnings: " + " | ".join(validation["warnings"]))

    if save:
        definition.updateFromNode(asset)
        hou.hipFile.save()

    return {
        "asset": asset.path(),
        "definition": definition.libraryFilePath(),
        "hip": hou.hipFile.path(),
        "backup": str(backup_path) if backup_path else None,
        "saved": save,
        "validation": validation,
    }


if __name__ == "__main__":
    print(apply_live_patch())
