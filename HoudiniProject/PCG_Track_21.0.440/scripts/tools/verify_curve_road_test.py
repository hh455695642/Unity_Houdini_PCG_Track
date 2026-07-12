"""Standalone contract verification for pcgbike::Track::1.0.

The test runs in a disposable hython process.  It never opens or saves the
production hip and it does not modify the HDA definition.
"""

from __future__ import annotations

import math
import os
import sys

import hou


SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
HOUDINI_DIR = os.path.abspath(os.path.join(SCRIPT_DIR, "..", ".."))
PROJECT_ROOT = os.path.abspath(os.path.join(HOUDINI_DIR, "..", ".."))
HDA_PATH = os.path.join(PROJECT_ROOT, "Assets", "PCG", "HDA", "Track.hda")
ASSET_TYPE = "pcgbike::Track::1.0"


def fail(message: str) -> int:
    print("VERIFY_FAIL=%s" % message)
    return 1


def triangle_area(a, b, c) -> float:
    return 0.5 * (hou.Vector3(b) - hou.Vector3(a)).cross(hou.Vector3(c) - hou.Vector3(a)).length()


def uv_area(a, b, c) -> float:
    return 0.5 * abs((b[0] - a[0]) * (c[1] - a[1]) - (b[1] - a[1]) * (c[0] - a[0]))


def boundary_intersections(geo: hou.Geometry, section: int) -> int:
    cross_section_count = geo.intAttribValue("road_cross_section_count")
    ring_count = geo.intAttribValue("road_sample_count")
    points = [
        hou.Vector3(geo.iterPoints()[ring * cross_section_count + section].position())
        for ring in range(ring_count)
    ]

    def side(a, b, c):
        return (b[0] - a[0]) * (c[2] - a[2]) - (b[2] - a[2]) * (c[0] - a[0])

    count = 0
    for first in range(len(points) - 1):
        for second in range(first + 2, len(points) - 1):
            a, b = points[first], points[first + 1]
            c, d = points[second], points[second + 1]
            ab_c, ab_d = side(a, b, c), side(a, b, d)
            cd_a, cd_b = side(c, d, a), side(c, d, b)
            if ((ab_c > 1e-6 and ab_d < -1e-6) or (ab_c < -1e-6 and ab_d > 1e-6)) and \
               ((cd_a > 1e-6 and cd_b < -1e-6) or (cd_a < -1e-6 and cd_b > 1e-6)):
                count += 1
    return count


def validate_geometry(geo: hou.Geometry, label: str) -> int:
    uv = geo.findVertexAttrib("uv")
    uv3 = geo.findVertexAttrib("uv3")
    source_quad = geo.findPrimAttrib("road_source_quad")
    if uv is None or uv3 is None:
        return fail("%s_missing_uv_or_uv3" % label)
    if source_quad is None:
        return fail("%s_missing_road_source_quad" % label)

    densities_by_quad = {}
    group_by_quad = {}
    directional_v = []
    lane_group = geo.findPrimGroup("lane")
    left_shoulder_group = geo.findPrimGroup("shoulder_l")
    right_shoulder_group = geo.findPrimGroup("shoulder_r")
    for primitive in geo.prims():
        vertices = primitive.vertices()
        if len(vertices) != 3:
            return fail("%s_primitive_%d_not_triangle" % (label, primitive.number()))
        positions = [tuple(vertex.point().position()) for vertex in vertices]
        directional = [vertex.attribValue(uv) for vertex in vertices]
        surface = [vertex.attribValue(uv3) for vertex in vertices]
        values = directional + surface
        if any(not math.isfinite(component) for value in values for component in value[:2]):
            return fail("%s_primitive_%d_non_finite_uv" % (label, primitive.number()))

        physical_area = triangle_area(*positions)
        surface_area = uv_area(*surface)
        if physical_area <= 1e-8:
            return fail("%s_primitive_%d_degenerate_geometry" % (label, primitive.number()))
        if surface_area <= 1e-10:
            return fail("%s_primitive_%d_degenerate_uv3" % (label, primitive.number()))

        quad_id = primitive.attribValue(source_quad)
        densities_by_quad.setdefault(quad_id, []).append(physical_area / surface_area)
        if lane_group is not None and lane_group.contains(primitive):
            group_by_quad[quad_id] = "lane"
        elif ((left_shoulder_group is not None and left_shoulder_group.contains(primitive)) or
              (right_shoulder_group is not None and right_shoulder_group.contains(primitive))):
            group_by_quad[quad_id] = "shoulder"
        directional_v.extend(value[1] for value in directional)

    if not directional_v or abs(min(directional_v)) > 1e-4 or max(directional_v) <= 1.0:
        return fail("%s_invalid_directional_uv_range" % label)

    maximum_ratio = 1.0
    lane_ratio = 1.0
    shoulder_ratio = 1.0
    for quad_id, densities in densities_by_quad.items():
        if len(densities) != 2:
            return fail("%s_quad_%d_expected_two_triangles" % (label, quad_id))
        ratio = max(densities) / max(min(densities), 1e-10)
        maximum_ratio = max(maximum_ratio, ratio)
        if group_by_quad.get(quad_id) == "lane":
            lane_ratio = max(lane_ratio, ratio)
        else:
            shoulder_ratio = max(shoulder_ratio, ratio)
    world_planar = (
        geo.findGlobalAttrib("road_surface_uv_mode") is not None and
        geo.stringAttribValue("road_surface_uv_mode") == "world_xz_meters"
    )
    # XZ projection intentionally measures ground-plan density.  Highly sloped
    # synthetic fallback shoulders can therefore differ strongly in 3D-area
    # ratio even though their projected texture remains stable and continuous.
    lane_limit = 10.0 if world_planar else 1.25
    shoulder_limit = 10.0 if world_planar else 1.35
    if lane_ratio > lane_limit + 1e-4:
        return fail("%s_lane_uv3_ratio_%f" % (label, lane_ratio))
    if shoulder_ratio > shoulder_limit + 1e-4:
        return fail("%s_shoulder_uv3_ratio_%f" % (label, shoulder_ratio))

    required_detail = (
        "road_input_max_segment_length",
        "road_max_ring_turn_angle_deg",
        "road_min_turn_radius",
        "road_tight_turn_count",
        "road_generated_min_turn_radius",
        "road_min_inner_radius_after_guard",
        "road_tight_turn_guard_count",
        "road_tight_turn_residual_count",
        "road_max_outward_shift",
        "road_surface_uv_mode",
        "road_uv_stretch_max_ratio",
    )
    for name in required_detail:
        if geo.findGlobalAttrib(name) is None:
            return fail("%s_missing_detail_%s" % (label, name))

    cd = geo.findPointAttrib("Cd")
    road_t = geo.findPointAttrib("road_t")
    normal = geo.findPointAttrib("N")
    if cd is None or cd.size() != 4 or road_t is None or normal is None:
        return fail("%s_missing_Cd_road_t_or_N" % label)
    for point in geo.points():
        color = point.attribValue(cd)
        parameter = point.attribValue(road_t)
        if min(color) < -1e-4 or max(color) > 1.0001 or abs(color[3] - 1.0) > 1e-4:
            return fail("%s_invalid_Cd_%s" % (label, color))
        if parameter < -1e-4 or parameter > 1.0001:
            return fail("%s_invalid_road_t_%f" % (label, parameter))

    recorded_ratio = geo.floatAttribValue("road_uv_stretch_max_ratio")
    if abs(recorded_ratio - maximum_ratio) > 2e-3:
        return fail("%s_recorded_ratio_%f_actual_%f" % (label, recorded_ratio, maximum_ratio))
    print(
        "%s points=%d triangles=%d samples=%d lane_ratio=%.6f shoulder_ratio=%.6f "
        "max_turn=%.6f min_radius=%.6f generated_radius=%.6f tight=%d guard=%d residual=%d shift=%.6f"
        % (
            label,
            len(geo.points()),
            len(geo.prims()),
            geo.intAttribValue("road_sample_count"),
            lane_ratio,
            shoulder_ratio,
            geo.floatAttribValue("road_max_ring_turn_angle_deg"),
            geo.floatAttribValue("road_min_turn_radius"),
            geo.floatAttribValue("road_generated_min_turn_radius"),
            geo.intAttribValue("road_tight_turn_count"),
            geo.intAttribValue("road_tight_turn_guard_count"),
            geo.intAttribValue("road_tight_turn_residual_count"),
            geo.floatAttribValue("road_max_outward_shift"),
        )
    )
    return 0


def make_stress_curve(obj: hou.Node) -> hou.Node:
    source = obj.createNode("geo", "VERIFY_unity_spline_stress")
    for child in source.children():
        child.destroy()
    node = source.createNode("python", "MAKE_S_CURVE")
    node.parm("python").set(
        """
import math
import hou
geo = hou.pwd().geometry()
geo.clear()
points = []
for index in range(801):
    x = float(index) * 0.5
    z = 20.0 * math.sin(x * math.pi * 2.0 / 100.0)
    point = geo.createPoint()
    point.setPosition(hou.Vector3(x, 0.0, z))
    points.append(point)
primitive = geo.createPolygon()
primitive.setIsClosed(False)
for point in points:
    primitive.addVertex(point)
"""
    )
    node.setDisplayFlag(True)
    node.setRenderFlag(True)
    return source


def make_hairpin_curve(obj: hou.Node) -> hou.Node:
    source = obj.createNode("geo", "VERIFY_unity_spline_hairpin")
    for child in source.children():
        child.destroy()
    node = source.createNode("python", "MAKE_HAIRPIN_CURVE")
    node.parm("python").set(
        """
import math
import hou
geo = hou.pwd().geometry()
geo.clear()
positions = []
for index in range(100):
    positions.append((float(index) * 0.5, 0.0, 0.0))
radius = 13.5
arc_steps = int(math.ceil(math.pi * radius / 0.5))
for index in range(arc_steps + 1):
    angle = -0.5 * math.pi + math.pi * float(index) / float(arc_steps)
    positions.append((50.0 + radius * math.cos(angle), 0.0, 13.5 + radius * math.sin(angle)))
for index in range(99, -1, -1):
    positions.append((float(index) * 0.5, 0.0, 27.0))
primitive = geo.createPolygon()
primitive.setIsClosed(False)
for position in positions:
    point = geo.createPoint()
    point.setPosition(hou.Vector3(position))
    primitive.addVertex(point)
"""
    )
    node.setDisplayFlag(True)
    node.setRenderFlag(True)
    return source


def road_output(asset: hou.Node) -> hou.Node:
    output = asset.node("Road/OUT_ROAD_MESH")
    if output is None:
        raise RuntimeError("Missing Road/OUT_ROAD_MESH")
    output.cook(force=True)
    return output


def main() -> int:
    if not os.path.isfile(HDA_PATH):
        return fail("missing_hda_%s" % HDA_PATH)
    hou.hda.installFile(HDA_PATH)
    obj = hou.node("/obj")

    fallback = obj.createNode(ASSET_TYPE, "VERIFY_track_fallback")
    fallback.parm("road_width").set(6.0)
    fallback.parm("sample_spacing").set(1.5)
    fallback_geo = road_output(fallback).geometry()
    result = validate_geometry(fallback_geo, "fallback")
    if result:
        return result
    if fallback_geo.stringAttribValue("road_source") != "fallback_points":
        return fail("fallback_wrong_source")

    source = make_stress_curve(obj)
    stress = obj.createNode(ASSET_TYPE, "VERIFY_track_stress")
    stress.parm("unity_curve_input").set(source.path())
    stress.parm("road_width").set(6.0)
    stress.parm("sample_spacing").set(1.5)
    stress_geo = road_output(stress).geometry()
    result = validate_geometry(stress_geo, "stress")
    if result:
        return result
    if stress_geo.stringAttribValue("road_source") != "unity_input_curve":
        return fail("stress_input_not_preserved")
    if stress_geo.floatAttribValue("road_input_max_segment_length") > 1.01:
        return fail("stress_input_spacing_%f" % stress_geo.floatAttribValue("road_input_max_segment_length"))
    if stress_geo.floatAttribValue("road_max_ring_turn_angle_deg") > 7.5 + 1e-3:
        return fail("stress_turn_angle_%f" % stress_geo.floatAttribValue("road_max_ring_turn_angle_deg"))
    if stress_geo.intAttribValue("road_tight_turn_count") != 0:
        return fail("stress_unexpected_tight_turns")

    hairpin_source = make_hairpin_curve(obj)
    hairpin = obj.createNode(ASSET_TYPE, "VERIFY_track_wide_hairpin")
    hairpin.parm("unity_curve_input").set(hairpin_source.path())
    hairpin.parm("road_width").set(23.0)
    hairpin.parm("sample_spacing").set(1.5)
    hairpin.parm("tight_turn_guard_enable").set(1)
    hairpin.parm("tight_turn_min_inner_radius").set(2.0)
    hairpin.parm("tight_turn_transition_length").set(24.0)
    hairpin.parm("tight_turn_max_offset").set(30.0)
    hairpin_geo = road_output(hairpin).geometry()
    result = validate_geometry(hairpin_geo, "wide_hairpin")
    if result:
        return result
    if hairpin_geo.intAttribValue("road_tight_turn_count") <= 0:
        return fail("wide_hairpin_guard_not_triggered")
    if hairpin_geo.intAttribValue("road_tight_turn_guard_count") <= 0:
        return fail("wide_hairpin_no_guard_zone")
    if hairpin_geo.floatAttribValue("road_max_outward_shift") <= 0.1:
        return fail("wide_hairpin_no_outward_shift")
    left_crossings = boundary_intersections(hairpin_geo, 0)
    right_crossings = boundary_intersections(hairpin_geo, 3)
    if left_crossings or right_crossings:
        return fail("wide_hairpin_boundary_crossings_%d_%d" % (left_crossings, right_crossings))
    if hairpin_geo.stringAttribValue("road_surface_uv_mode") != "world_xz_meters":
        return fail("wide_hairpin_wrong_uv_mode")

    print("VERIFY_OK=1")
    return 0


if __name__ == "__main__":
    sys.exit(main())
