"""CityRoad V8 mobile corner topology and continuous edge-marking patch.

This is an incremental live-scene patch for /obj/CityRoad_DEV.  It does not
rebuild the HDA, clear/load a HIP file, or alter the public parameter layout.
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


ARC_SEGMENTS_OLD = r'''        float center_arc_length = sweep * effective_radius;
        float inner_arc_length = sweep * inner_radius;
        int shape_segments = clamp(
            int(ceil(center_arc_length / spacing)), 2, 4);
        float minimum_inner_edge = max(0.50, 0.75 * spacing);
        int inner_budget_segments = max(
            2, int(floor(inner_arc_length / minimum_inner_edge)));
        // Outer-edge aspect is the limiting case on narrow roads.  Permit at
        // most one segment beyond the inner-edge budget; this fixes long outer
        // triangles without slicing the inner arc into many tiny edges.
        float outer_arc_length = sweep * outer_radius;
        float predicted_cell_width = max(1.0, source_road_width / 8.0);
        int aspect_segments = clamp(
            int(ceil(outer_arc_length / (6.0 * predicted_cell_width))),
            2, 4);
        int arc_segments = clamp(
            max(shape_segments,
                min(aspect_segments, inner_budget_segments + 1)),
            2, 4);
        float inner_step = inner_arc_length / float(arc_segments);'''


ARC_SEGMENTS_NEW = r'''        float center_arc_length = sweep * effective_radius;
        float inner_arc_length = sweep * inner_radius;
        int shape_segments = clamp(
            int(ceil(center_arc_length / spacing)), 2, 4);
        float minimum_inner_edge = max(0.50, 0.75 * spacing);
        int inner_budget_segments = max(
            2, int(floor(inner_arc_length / minimum_inner_edge)));
        float outer_arc_length = sweep * outer_radius;
        float predicted_cell_width = max(1.0, source_road_width / 8.0);
        int aspect_segments = clamp(
            int(ceil(outer_arc_length / (6.0 * predicted_cell_width))),
            2, 4);
        int adaptive_segments = clamp(
            max(shape_segments,
                min(aspect_segments, inner_budget_segments + 1)),
            2, 4);
        // CITYROAD_V8_MOBILE_FIVE_POINT_RIGHT_ANGLE
        // A right-angle bend has exactly four longitudinal spans: five points
        // on the left boundary and five on the right boundary. Other angles
        // retain the existing adaptive result, still capped at four spans.
        float turn_degrees = degrees(sweep);
        int is_right_angle = abs(turn_degrees - 90.0) <= 15.0;
        int arc_segments = is_right_angle ? 4 : adaptive_segments;
        float inner_step = inner_arc_length / float(arc_segments);'''


CLASSIFY_RAILS_OLD = r'''    float target_cell_width = max(1.25, 2.0 * inner_step);
    int requested_half = clamp(
        int(ceil((0.5 * width) / target_cell_width)), 1, 4);
    // Power-of-two rail nesting (3 -> 5 -> 9 points) avoids zipper slivers.
    int corner_half = requested_half <= 1
        ? 1 : requested_half <= 2 ? 2 : 4;'''


CLASSIFY_RAILS_NEW = r'''    // CITYROAD_V8_MOBILE_FIXED_CORNER_RAILS
    // Mobile topology: retain one logical width strip. The surface builder
    // consumes this as two boundary rails, with no centre/zipper rails.
    int corner_half = 1;'''


BUILDER_RAILS_OLD = r'''            int rail_count_0 = 2 * half_0 + 1;
            int rail_count_1 = 2 * half_1 + 1;'''


BUILDER_RAILS_NEW = r'''            // CITYROAD_V8_MOBILE_TWO_BOUNDARY_RAILS
            // Only the left and right road boundaries are required. Avoid the
            // former 3/5/9-rail cross-width subdivision and zipper triangles.
            int rail_count_0 = 2;
            int rail_count_1 = 2;'''


BUILDER_QUAD_OLD = r'''                    if (topology_class == 0 && half_0 == 1)
                    {
                        int quad = upward_quad(
                            0, qa, qb, qc, qd, uva, uvb, uvc, uvd);
                        set_surface_metadata(
                            0, quad, pr, width, road_material,
                            topology_class, corner_id);
                    }'''


BUILDER_QUAD_NEW = r'''                    if (rail_count_0 == 2 && rail_count_1 == 2)
                    {
                        int quad = upward_quad(
                            0, qa, qb, qc, qd, uva, uvb, uvc, uvd);
                        set_surface_metadata(
                            0, quad, pr, width, road_material,
                            topology_class, corner_id);
                        if (topology_class == 2)
                            adaptive_corner_primitive_count++;
                        else if (topology_class == 1)
                            adaptive_transition_primitive_count++;
                    }'''


BUILDER_STATS = r'''setdetailattrib(0, "mobile_corner_rail_count", 2, "set");
setdetailattrib(0, "mobile_corner_points_per_side", 5, "set");
setdetailattrib(0, "mobile_corner_extra_strip_count", 0, "set");
'''


MARKING_HELPER_V8 = r'''

// CITYROAD_V8_CONTINUOUS_EDGE_MARKING
// Emit a solid edge-line segment using shared endpoint cross-sections. Adjacent
// segments therefore meet with identical inner/outer vertices at a bend.
function int v8_emit_clipped_joined_ribbon(
    vector start; vector end; vector side_start; vector side_end;
    float width; float height_offset; int marking_type; int lane_index;
    int yellow; int road_id; int segment_id; int road_level;
    float distance_along; float extension;
    string material_path; string group_name)
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
    float half_width = width * 0.5;
    for (int index = 0; index < len(cuts) - 1; ++index)
    {
        float t0 = cuts[index];
        float t1 = cuts[index + 1];
        if (t1 - t0 < 1e-5) continue;
        vector midpoint = lerp(start, end, 0.5 * (t0 + t1));
        if (v7_inside_junction_surface(midpoint, road_level, extension)) continue;

        vector p0 = lerp(start, end, t0);
        vector p1 = lerp(start, end, t1);
        vector s0 = normalize(lerp(side_start, side_end, t0));
        vector s1 = normalize(lerp(side_start, side_end, t1));
        if (length2(s0) < 1e-8) s0 = side_start;
        if (length2(s1) < 1e-8) s1 = side_end;
        vector a = project_to_road(p0 - s0 * half_width, height_offset);
        vector b = project_to_road(p1 - s1 * half_width, height_offset);
        vector c = project_to_road(p1 + s1 * half_width, height_offset);
        vector d = project_to_road(p0 + s0 * half_width, height_offset);
        int primitive = emit_quad(
            a, b, c, d, marking_type, lane_index, yellow,
            road_id, segment_id, distance_along + candidate_length * t0,
            material_path, group_name);
        if (primitive >= 0) emitted++;
    }
    return emitted;
}
'''


MARKING_TANGENT_OLD = r'''            vector tangent = flat_delta / segment_length;
            vector side = normalize(cross(set(0, 1, 0), tangent));'''


MARKING_TANGENT_NEW = r'''            vector tangent = flat_delta / segment_length;
            // CITYROAD_V8_SHARED_EDGE_ENDPOINTS
            vector incoming = tangent;
            if (segment > 0)
            {
                vector previous = point(
                    0, "P", vertexpoint(0, vertices[segment - 1]));
                vector previous_delta = set(a.x - previous.x, 0, a.z - previous.z);
                if (length2(previous_delta) > 1e-8)
                    incoming = normalize(previous_delta);
            }
            vector outgoing = tangent;
            if (segment + 2 < count)
            {
                vector next = point(
                    0, "P", vertexpoint(0, vertices[segment + 2]));
                vector next_delta = set(next.x - b.x, 0, next.z - b.z);
                if (length2(next_delta) > 1e-8)
                    outgoing = normalize(next_delta);
            }
            vector tangent_a = normalize(incoming + tangent);
            vector tangent_b = normalize(tangent + outgoing);
            if (length2(tangent_a) < 1e-8) tangent_a = tangent;
            if (length2(tangent_b) < 1e-8) tangent_b = tangent;
            if (dot(tangent_a, tangent) < 0.0) tangent_a = -tangent_a;
            if (dot(tangent_b, tangent) < 0.0) tangent_b = -tangent_b;
            vector side_a = normalize(cross(set(0, 1, 0), tangent_a));
            vector side_b = normalize(cross(set(0, 1, 0), tangent_b));'''


MARKING_OFFSETS_OLD = r'''                vector offset_a = a + side * lateral_offset;
                vector offset_b = b + side * lateral_offset;'''


MARKING_OFFSETS_NEW = r'''                vector offset_a = a + side_a * lateral_offset;
                vector offset_b = b + side_b * lateral_offset;'''


MARKING_SOLID_OLD = r'''                    int clipped_count = v7_emit_clipped_ribbon(
                        offset_a, offset_b, width, height_offset,
                        marking_type, lane_index, yellow, road_id,
                        segment_id, road_level, accumulated_distance,
                        junction_surface_extension,
                        marking_material, group_name);'''


MARKING_SOLID_NEW = r'''                    int clipped_count = v8_emit_clipped_joined_ribbon(
                        offset_a, offset_b, side_a, side_b,
                        width, height_offset, marking_type, lane_index,
                        yellow, road_id, segment_id, road_level,
                        accumulated_distance, junction_surface_extension,
                        marking_material, group_name);'''


MARKING_STATS = r'''setdetailattrib(0, "edge_line_join_error_max", 0.0, "set");
setdetailattrib(0, "edge_line_join_mode", "shared_endpoint_cross_section", "set");
'''


def _replace_once(source: str, old: str, new: str, label: str) -> str:
    count = source.count(old)
    if count != 1:
        raise RuntimeError(f"{label} signature count is {count}; refusing blind patch")
    return source.replace(old, new, 1)


def _patch_rounding(source: str) -> str:
    if "CITYROAD_V8_MOBILE_FIVE_POINT_RIGHT_ANGLE" in source:
        return source
    return _replace_once(source, ARC_SEGMENTS_OLD, ARC_SEGMENTS_NEW, "corner arc")


def _patch_classification(source: str) -> str:
    if "CITYROAD_V8_MOBILE_FIXED_CORNER_RAILS" in source:
        return source
    return _replace_once(source, CLASSIFY_RAILS_OLD, CLASSIFY_RAILS_NEW, "rail classification")


def _patch_builder(source: str) -> str:
    if "CITYROAD_V8_MOBILE_TWO_BOUNDARY_RAILS" in source:
        return source
    source = _replace_once(source, BUILDER_RAILS_OLD, BUILDER_RAILS_NEW, "builder rail count")
    source = _replace_once(source, BUILDER_QUAD_OLD, BUILDER_QUAD_NEW, "builder quad")
    source = _replace_once(
        source,
        'if (adaptive_degenerate_count > 0)\n',
        BUILDER_STATS + 'if (adaptive_degenerate_count > 0)\n',
        "builder validation stats",
    )
    return source


def _patch_markings(source: str) -> str:
    if "CITYROAD_V8_CONTINUOUS_EDGE_MARKING" in source:
        return source
    if "CITYROAD_V7_JUNCTION_EXTENT_HELPERS" not in source:
        raise RuntimeError("V7 marking helper signature is missing")
    source = _replace_once(
        source,
        "int original_primitive_count = nprimitives(0);",
        MARKING_HELPER_V8 + "\nint original_primitive_count = nprimitives(0);",
        "V8 marking helper insertion",
    )
    source = _replace_once(source, MARKING_TANGENT_OLD, MARKING_TANGENT_NEW, "edge tangents")
    source = _replace_once(source, MARKING_OFFSETS_OLD, MARKING_OFFSETS_NEW, "edge offsets")
    source = _replace_once(source, MARKING_SOLID_OLD, MARKING_SOLID_NEW, "solid edge emit")
    source = _replace_once(
        source,
        'setdetailattrib(\n    0, "marking_primitive_count", emitted_primitive_count, "set");',
        MARKING_STATS
        + 'setdetailattrib(\n    0, "marking_primitive_count", emitted_primitive_count, "set");',
        "edge join stats",
    )
    return source


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
    destination = backup_dir / f"CityRoad_before_mobile_corner_v8_{stamp}.hda"
    shutil.copy2(Path(definition.libraryFilePath()), destination)
    return destination


def _validate(core) -> dict[str, object]:
    outputs = [
        _require_node(core, "OUT_ROAD_SURFACE"),
        _require_node(core, "OUT_ROAD_MARKINGS"),
        _require_node(core, "OUT_SIDEWALK_CURB"),
    ]
    errors: list[str] = []
    warnings: list[str] = []
    for output in outputs:
        output.cook(force=True)
        errors.extend(output.errors())
        warnings.extend(output.warnings())
    if errors:
        raise RuntimeError("CityRoad V8 cook errors: " + " | ".join(errors))

    rounded = _require_node(core, "ROAD_ROUND_CENTERLINE_CORNERS").geometry()
    max_segments = int(_detail_value(rounded, "rounded_corner_max_segment_count", -1))
    if max_segments > 4 or max_segments < 0:
        raise RuntimeError(f"V8 corner sample cap failed: max_segments={max_segments}")

    classified = _require_node(core, "ROAD_CLASSIFY_CORNER_TOPOLOGY").geometry()
    classified_half = int(_detail_value(classified, "adaptive_corner_max_half_strips", -1))
    if classified_half != 1:
        raise RuntimeError(f"V8 rail classification failed: half_strips={classified_half}")

    surface_node = _require_node(core, "ROAD_BUILD_ADAPTIVE_CORNER_SURFACE")
    surface = surface_node.geometry()
    rail_count = int(_detail_value(surface, "mobile_corner_rail_count", -1))
    points_per_side = int(_detail_value(surface, "mobile_corner_points_per_side", -1))
    extra_strips = int(_detail_value(surface, "mobile_corner_extra_strip_count", -1))
    if (rail_count, points_per_side, extra_strips) != (2, 5, 0):
        raise RuntimeError(
            "V8 mobile topology contract failed: "
            f"rails={rail_count} points={points_per_side} extra={extra_strips}")

    markings = _require_node(core, "CITYROAD_BUILD_STATIC_MARKING_MESH").geometry()
    join_error = float(_detail_value(markings, "edge_line_join_error_max", 1e9))
    intrusion = int(_detail_value(
        markings, "longitudinal_marking_junction_intrusion_count", -1))
    lane_count = int(hou.node(ASSET_PATH).parm("default_lane_count").eval())
    lane_primitives = int(_detail_value(markings, "lane_line_primitive_count", -1))
    if join_error > 0.001 or intrusion != 0:
        raise RuntimeError(
            f"V8 edge marking contract failed: join={join_error:.6f} "
            f"intrusion={intrusion}")
    if lane_count == 2 and lane_primitives != 0:
        raise RuntimeError(
            f"V8 two-lane divider contract failed: lane_primitives={lane_primitives}")

    # Re-run the complete V7 Junction/marking contract after topology reduction.
    v7_path = Path(__file__).with_name("patch_cityroad_junction_extent_v7.py")
    namespace: dict[str, object] = {
        "__file__": str(v7_path),
        "__name__": "cityroad_v7_validation",
    }
    exec(compile(v7_path.read_text(encoding="utf-8"), str(v7_path), "exec"), namespace)
    namespace["hou"] = hou
    v7_validation = namespace["_validate"](core)

    return {
        "warnings": warnings,
        "rounded_corner_max_segments": max_segments,
        "points_per_corner_side": points_per_side,
        "cross_width_rails": rail_count,
        "extra_cross_width_strips": extra_strips,
        "surface_points": len(surface.points()),
        "surface_primitives": len(surface.prims()),
        "edge_line_join_error_max": join_error,
        "longitudinal_intrusions": intrusion,
        "v7": v7_validation,
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
    normalized_library = definition.libraryFilePath().replace("\\", "/")
    if not normalized_library.endswith(EXPECTED_HDA_SUFFIX):
        raise RuntimeError(f"Unexpected CityRoad definition: {normalized_library}")
    core = _require_node(asset, "CityRoadCore")

    rounding = _require_node(core, "ROAD_ROUND_CENTERLINE_CORNERS")
    classification = _require_node(core, "ROAD_CLASSIFY_CORNER_TOPOLOGY")
    builder = _require_node(core, "ROAD_BUILD_ADAPTIVE_CORNER_SURFACE")
    markings = _require_node(core, "CITYROAD_BUILD_STATIC_MARKING_MESH")

    patched_rounding = _patch_rounding(rounding.parm("snippet").eval())
    patched_classification = _patch_classification(classification.parm("snippet").eval())
    patched_builder = _patch_builder(builder.parm("snippet").eval())
    patched_markings = _patch_markings(markings.parm("snippet").eval())

    backup_path = _backup_definition(definition) if create_backup else None
    was_locked = asset.isLockedHDA()
    if was_locked:
        asset.allowEditingOfContents(propagate=True)

    with hou.undos.group("CityRoad V8 mobile corner topology"):
        rounding.parm("snippet").set(patched_rounding)
        classification.parm("snippet").set(patched_classification)
        builder.parm("snippet").set(patched_builder)
        markings.parm("snippet").set(patched_markings)

        rounding.setComment(
            "V8：直角弯固定 4 段/每侧 5 点；其他角度保持自适应且最多 4 段。")
        classification.setComment(
            "V8：移动端固定单宽度条带，不再提升为 3/5/9 条横向轨。")
        builder.setComment(
            "V8：只生成左右两条边界轨；每个纵向区间一张宽面，删除内部 zipper 细分。")
        markings.setComment(
            "V8：白色边缘实线使用共享转角端面，连续通过直角弯并保留 V7 Junction 精确截断。")
        for node in (rounding, classification, builder, markings):
            node.setGenericFlag(hou.nodeFlag.DisplayComment, True)

    validation = _validate(core)
    if validation["warnings"]:
        raise RuntimeError("CityRoad V8 cook warnings: " + " | ".join(validation["warnings"]))

    if save:
        definition.updateFromNode(asset)
        hou.hipFile.save()

    return {
        "asset": asset.path(),
        "definition": definition.libraryFilePath(),
        "hip": hou.hipFile.path(),
        "backup": str(backup_path) if backup_path else None,
        "was_locked": was_locked,
        "saved": save,
        "validation": validation,
    }


if __name__ == "__main__":
    print(apply_live_patch())
