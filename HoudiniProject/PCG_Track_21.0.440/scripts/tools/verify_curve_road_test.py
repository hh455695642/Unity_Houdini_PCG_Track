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
    collision_group = geo.findPrimGroup("rendered_collision_geo")
    if collision_group is None or len(collision_group.prims()) != len(geo.prims()):
        return fail("%s_missing_full_rendered_collision_group" % label)
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
        "road_banking_enabled",
        "road_bank_design_speed_kph",
        "road_bank_transition_length_m",
        "road_max_abs_bank_deg",
        "road_max_abs_grade_deg",
        "road_spline_knot_roll_enabled",
        "road_max_abs_spline_roll_deg",
        "road_start_up",
    )
    for name in required_detail:
        if geo.findGlobalAttrib(name) is None:
            return fail("%s_missing_detail_%s" % (label, name))

    cd = geo.findPointAttrib("Cd")
    road_t = geo.findPointAttrib("road_t")
    normal = geo.findPointAttrib("N")
    bank = geo.findPointAttrib("road_bank_deg")
    grade = geo.findPointAttrib("road_grade_deg")
    spline_roll = geo.findPointAttrib("road_spline_roll_deg")
    has_spline_roll = geo.findPointAttrib("road_has_spline_roll")
    tangent = geo.findPointAttrib("road_frame_tangent")
    lateral = geo.findPointAttrib("road_frame_lateral")
    up = geo.findPointAttrib("road_frame_up")
    if any(attribute is None for attribute in (
        cd, road_t, normal, bank, grade, spline_roll, has_spline_roll, tangent, lateral, up
    )):
        return fail("%s_missing_color_frame_or_normal_contract" % label)
    if cd.size() != 4:
        return fail("%s_invalid_Cd_size" % label)
    for point in geo.points():
        color = point.attribValue(cd)
        parameter = point.attribValue(road_t)
        if min(color) < -1e-4 or max(color) > 1.0001 or abs(color[3] - 1.0) > 1e-4:
            return fail("%s_invalid_Cd_%s" % (label, color))
        if parameter < -1e-4 or parameter > 1.0001:
            return fail("%s_invalid_road_t_%f" % (label, parameter))
        bank_angle = point.attribValue(bank)
        grade_angle = point.attribValue(grade)
        spline_roll_angle = point.attribValue(spline_roll)
        spline_roll_flag = point.attribValue(has_spline_roll)
        frame_tangent = hou.Vector3(point.attribValue(tangent))
        frame_lateral = hou.Vector3(point.attribValue(lateral))
        frame_up = hou.Vector3(point.attribValue(up))
        values = (bank_angle, grade_angle, spline_roll_angle) + tuple(frame_tangent) + tuple(frame_lateral) + tuple(frame_up)
        if any(not math.isfinite(value) for value in values):
            return fail("%s_non_finite_frame" % label)
        if abs(bank_angle) > 20.0001:
            return fail("%s_unbounded_bank_%f" % (label, bank_angle))
        if spline_roll_flag not in (0, 1):
            return fail("%s_invalid_spline_roll_flag_%s" % (label, spline_roll_flag))
        if abs(frame_tangent.length() - 1.0) > 2e-3 or \
           abs(frame_lateral.length() - 1.0) > 2e-3 or \
           abs(frame_up.length() - 1.0) > 2e-3:
            return fail("%s_non_unit_frame" % label)
        if abs(frame_tangent.dot(frame_lateral)) > 2e-3 or \
           abs(frame_tangent.dot(frame_up)) > 2e-3 or \
           abs(frame_lateral.dot(frame_up)) > 2e-3:
            return fail("%s_non_orthogonal_frame" % label)
        if frame_tangent.cross(frame_lateral).dot(frame_up) < 0.995:
            return fail("%s_left_handed_frame" % label)

    recorded_ratio = geo.floatAttribValue("road_uv_stretch_max_ratio")
    if abs(recorded_ratio - maximum_ratio) > 2e-3:
        return fail("%s_recorded_ratio_%f_actual_%f" % (label, recorded_ratio, maximum_ratio))
    print(
        "%s points=%d triangles=%d samples=%d lane_ratio=%.6f shoulder_ratio=%.6f "
        "max_turn=%.6f min_radius=%.6f generated_radius=%.6f tight=%d guard=%d residual=%d "
        "shift=%.6f bank=%.6f grade=%.6f"
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
            geo.floatAttribValue("road_max_abs_bank_deg"),
            geo.floatAttribValue("road_max_abs_grade_deg"),
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


def make_grade_curve(obj: hou.Node) -> hou.Node:
    source = obj.createNode("geo", "VERIFY_grade_curve")
    for child in source.children():
        child.destroy()
    node = source.createNode("python", "MAKE_GRADE_CURVE")
    node.parm("python").set(
        """
import hou
geo = hou.pwd().geometry()
geo.clear()
positions = ((0, 0, 0), (15, 3, 0), (30, 6, 0), (45, 3, 0), (60, 0, 0))
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


def make_spline_roll_curve(obj: hou.Node, roll_degrees: float) -> hou.Node:
    source = obj.createNode("geo", "VERIFY_spline_roll_curve")
    for child in source.children():
        child.destroy()
    node = source.createNode("python", "MAKE_SPLINE_ROLL_CURVE")
    node.parm("python").set(
        """
import math
import hou
geo = hou.pwd().geometry()
geo.clear()
rotation_attrib = geo.addAttrib(hou.attribType.Point, "rot", (0.0, 0.0, 0.0, 1.0))
rotation = hou.Quaternion()
rotation.setToAngleAxis(%.9f, hou.Vector3(1.0, 0.0, 0.0))
primitive = geo.createPolygon()
primitive.setIsClosed(False)
for index in range(7):
    point = geo.createPoint()
    point.setPosition(hou.Vector3(float(index) * 10.0, 0.0, 0.0))
    point.setAttribValue(rotation_attrib, tuple(rotation))
    primitive.addVertex(point)
""" % roll_degrees
    )
    node.setDisplayFlag(True)
    node.setRenderFlag(True)
    return source


def make_arc_curve(obj: hou.Node, radius: float = 30.0) -> hou.Node:
    source = obj.createNode("geo", "VERIFY_constant_radius_arc")
    for child in source.children():
        child.destroy()
    node = source.createNode("python", "MAKE_CONSTANT_RADIUS_ARC")
    node.parm("python").set(
        """
import math
import hou
geo = hou.pwd().geometry()
geo.clear()
radius = %.9f
points = []
for index in range(121):
    angle = -0.5 * math.pi + math.pi * float(index) / 120.0
    point = geo.createPoint()
    point.setPosition(hou.Vector3(radius * math.cos(angle), 0.0, radius * math.sin(angle)))
    points.append(point)
primitive = geo.createPolygon()
primitive.setIsClosed(False)
for point in points:
    primitive.addVertex(point)
""" % radius
    )
    node.setDisplayFlag(True)
    node.setRenderFlag(True)
    return source


def make_closed_circle(obj: hou.Node, radius: float = 35.0) -> hou.Node:
    source = obj.createNode("geo", "VERIFY_closed_circle")
    for child in source.children():
        child.destroy()
    node = source.createNode("python", "MAKE_CLOSED_CIRCLE")
    node.parm("python").set(
        """
import math
import hou
geo = hou.pwd().geometry()
geo.clear()
radius = %.9f
points = []
for index in range(180):
    angle = 2.0 * math.pi * float(index) / 180.0
    point = geo.createPoint()
    point.setPosition(hou.Vector3(radius * math.cos(angle), 0.0, radius * math.sin(angle)))
    points.append(point)
primitive = geo.createPolygon()
primitive.setIsClosed(True)
for point in points:
    primitive.addVertex(point)
""" % radius
    )
    node.setDisplayFlag(True)
    node.setRenderFlag(True)
    return source


def set_zero_manual_ramp(asset: hou.Node) -> None:
    asset.parm("bank_manual_offset_ramp").set(
        hou.Ramp(
            (hou.rampBasis.Linear, hou.rampBasis.Linear),
            (0.0, 1.0),
            (0.0, 0.0),
        )
    )


def ring_points(geo: hou.Geometry, ring: int):
    cross_section_count = geo.intAttribValue("road_cross_section_count")
    points = geo.points()
    start = ring * cross_section_count
    return points[start:start + cross_section_count]


def validate_bank_rate(geo: hou.Geometry, label: str, maximum_angle: float, transition_length: float) -> int:
    if transition_length <= 1e-5:
        return 0
    cross_section_count = geo.intAttribValue("road_cross_section_count")
    ring_count = geo.intAttribValue("road_sample_count")
    points = geo.iterPoints()
    maximum_rate = maximum_angle / transition_length
    closed_loop = bool(geo.intAttribValue("road_closed_loop"))
    total_length = geo.floatAttribValue("road_generated_length")
    for ring in range(ring_count - 1 + int(closed_loop)):
        current = ring % ring_count
        following = (ring + 1) % ring_count
        current_point = points[current * cross_section_count]
        following_point = points[following * cross_section_count]
        current_distance = current_point.attribValue("road_generated_distance")
        following_distance = following_point.attribValue("road_generated_distance")
        segment_length = (
            total_length - current_distance + following_distance
            if following == 0 else following_distance - current_distance
        )
        bank_delta = abs(
            following_point.attribValue("road_bank_deg") -
            current_point.attribValue("road_bank_deg")
        )
        if bank_delta > maximum_rate * max(segment_length, 0.0) + 2e-3:
            return fail("%s_bank_rate_%f_over_%f" % (
                label, bank_delta, maximum_rate * max(segment_length, 0.0)
            ))
    return 0


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
    if fallback.parm("enable_road_banking") is None:
        return fail("fallback_missing_banking_parameters")
    if fallback.parm("enable_road_banking").eval() != 0:
        return fail("fallback_banking_default_not_disabled")
    if fallback.parm("bank_use_spline_knot_roll") is None:
        return fail("fallback_missing_spline_knot_roll_toggle")
    if fallback.parm("bank_use_spline_knot_roll").eval() != 1:
        return fail("fallback_spline_knot_roll_default_not_enabled")
    default_ramp = fallback.parm("bank_manual_offset_ramp").eval()
    if any(abs(value) > 1e-6 for value in default_ramp.values()):
        return fail("fallback_manual_ramp_default_not_zero")
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

    grade_source = make_grade_curve(obj)
    grade = obj.createNode(ASSET_TYPE, "VERIFY_track_grade")
    grade.parm("unity_curve_input").set(grade_source.path())
    grade.parm("road_width").set(6.0)
    grade.parm("sample_spacing").set(2.0)
    grade.parm("enable_road_banking").set(1)
    grade.parm("bank_auto_strength").set(0.0)
    grade.parm("bank_transition_length_m").set(24.0)
    set_zero_manual_ramp(grade)
    grade_geo = road_output(grade).geometry()
    result = validate_geometry(grade_geo, "grade_only")
    if result:
        return result
    if grade_geo.floatAttribValue("road_max_abs_bank_deg") > 1e-4:
        return fail("grade_only_unexpected_bank")
    if grade_geo.floatAttribValue("road_max_abs_grade_deg") < 3.0:
        return fail("grade_only_missing_grade")
    for ring in range(grade_geo.intAttribValue("road_sample_count")):
        points = ring_points(grade_geo, ring)
        if abs(points[2].position()[1] - points[1].position()[1]) > 1e-4:
            return fail("grade_only_lane_not_level_%d" % ring)

    spline_roll_source = make_spline_roll_curve(obj, 10.0)
    spline_roll = obj.createNode(ASSET_TYPE, "VERIFY_track_spline_roll")
    spline_roll.parm("unity_curve_input").set(spline_roll_source.path())
    spline_roll.parm("road_width").set(6.0)
    spline_roll.parm("sample_spacing").set(2.0)
    spline_roll.parm("enable_road_banking").set(1)
    spline_roll.parm("bank_use_spline_knot_roll").set(1)
    spline_roll.parm("bank_auto_strength").set(0.0)
    spline_roll.parm("bank_max_angle_deg").set(8.0)
    spline_roll.parm("bank_transition_length_m").set(0.0)
    set_zero_manual_ramp(spline_roll)
    spline_roll_geo = road_output(spline_roll).geometry()
    result = validate_geometry(spline_roll_geo, "spline_roll_clamped")
    if result:
        return result
    middle_ring = spline_roll_geo.intAttribValue("road_sample_count") // 2
    middle_points = ring_points(spline_roll_geo, middle_ring)
    middle = middle_points[0]
    authored_roll = middle.attribValue("road_spline_roll_deg")
    applied_roll = middle.attribValue("road_bank_deg")
    if abs(authored_roll - 10.0) > 0.05:
        return fail("spline_roll_decode_%f" % authored_roll)
    if abs(applied_roll - 8.0) > 0.05:
        return fail("spline_roll_clamp_%f" % applied_roll)
    if middle.attribValue("road_has_spline_roll") != 1:
        return fail("spline_roll_missing_presence_flag")
    lane_height_delta = middle_points[2].position()[1] - middle_points[1].position()[1]
    if lane_height_delta * applied_roll <= 0.0:
        return fail("spline_roll_wrong_lane_height_direction")

    spline_roll.parm("bank_use_spline_knot_roll").set(0)
    spline_roll_disabled_geo = road_output(spline_roll).geometry()
    if spline_roll_disabled_geo.floatAttribValue("road_max_abs_bank_deg") > 1e-4:
        return fail("disabled_spline_roll_still_applied")

    additive_source = make_spline_roll_curve(obj, 3.0)
    additive = obj.createNode(ASSET_TYPE, "VERIFY_track_additive_spline_roll")
    additive.parm("unity_curve_input").set(additive_source.path())
    additive.parm("road_width").set(6.0)
    additive.parm("sample_spacing").set(2.0)
    additive.parm("enable_road_banking").set(1)
    additive.parm("bank_use_spline_knot_roll").set(1)
    additive.parm("bank_auto_strength").set(0.0)
    additive.parm("bank_max_angle_deg").set(8.0)
    additive.parm("bank_transition_length_m").set(0.0)
    additive.parm("bank_manual_offset_ramp").set(
        hou.Ramp(
            (hou.rampBasis.Linear, hou.rampBasis.Linear),
            (0.0, 1.0),
            (2.0, 2.0),
        )
    )
    additive_geo = road_output(additive).geometry()
    result = validate_geometry(additive_geo, "spline_roll_additive")
    if result:
        return result
    additive_middle = ring_points(
        additive_geo, additive_geo.intAttribValue("road_sample_count") // 2
    )[0]
    if abs(additive_middle.attribValue("road_bank_deg") - 5.0) > 0.05:
        return fail("spline_roll_not_additive_%f" % additive_middle.attribValue("road_bank_deg"))

    arc_source = make_arc_curve(obj)
    arc = obj.createNode(ASSET_TYPE, "VERIFY_track_constant_radius_bank")
    arc.parm("unity_curve_input").set(arc_source.path())
    arc.parm("road_width").set(6.0)
    arc.parm("sample_spacing").set(1.5)
    arc.parm("enable_road_banking").set(1)
    arc.parm("bank_design_speed_kph").set(20.0)
    arc.parm("bank_auto_strength").set(1.0)
    arc.parm("bank_max_angle_deg").set(8.0)
    arc.parm("bank_transition_length_m").set(0.0)
    set_zero_manual_ramp(arc)
    arc_geo = road_output(arc).geometry()
    result = validate_geometry(arc_geo, "constant_radius_bank")
    if result:
        return result
    middle_ring = arc_geo.intAttribValue("road_sample_count") // 2
    middle_points = ring_points(arc_geo, middle_ring)
    middle = middle_points[0]
    curvature = middle.attribValue("road_curvature_inv_m")
    expected_bank = -math.degrees(math.atan(((20.0 / 3.6) ** 2) * curvature / 9.80665))
    actual_bank = middle.attribValue("road_bank_deg")
    if abs(actual_bank - expected_bank) > 0.05:
        return fail("constant_radius_formula_%f_expected_%f" % (actual_bank, expected_bank))
    if abs(actual_bank) < 1.0 or abs(actual_bank) > 8.0001:
        return fail("constant_radius_bank_range_%f" % actual_bank)
    lane_height_delta = middle_points[2].position()[1] - middle_points[1].position()[1]
    if lane_height_delta * actual_bank <= 0.0:
        return fail("constant_radius_outside_not_raised")

    manual = obj.createNode(ASSET_TYPE, "VERIFY_track_manual_bank")
    manual.parm("unity_curve_input").set(grade_source.path())
    manual.parm("road_width").set(6.0)
    manual.parm("sample_spacing").set(2.0)
    manual.parm("enable_road_banking").set(1)
    manual.parm("bank_auto_strength").set(0.0)
    manual.parm("bank_max_angle_deg").set(8.0)
    manual.parm("bank_transition_length_m").set(0.0)
    manual.parm("bank_manual_offset_ramp").set(
        hou.Ramp(
            (hou.rampBasis.Linear, hou.rampBasis.Linear, hou.rampBasis.Linear),
            (0.0, 0.5, 1.0),
            (0.0, 4.0, 0.0),
        )
    )
    manual_geo = road_output(manual).geometry()
    result = validate_geometry(manual_geo, "manual_bank")
    if result:
        return result
    manual_peak = max(point.attribValue("road_bank_deg") for point in manual_geo.points())
    if manual_peak < 3.8 or manual_peak > 4.01:
        return fail("manual_bank_peak_%f" % manual_peak)

    bank_stress = obj.createNode(ASSET_TYPE, "VERIFY_track_bank_s_curve")
    bank_stress.parm("unity_curve_input").set(source.path())
    bank_stress.parm("road_width").set(6.0)
    bank_stress.parm("sample_spacing").set(1.5)
    bank_stress.parm("enable_road_banking").set(1)
    bank_stress.parm("bank_design_speed_kph").set(25.0)
    bank_stress.parm("bank_auto_strength").set(1.0)
    bank_stress.parm("bank_max_angle_deg").set(8.0)
    bank_stress.parm("bank_transition_length_m").set(24.0)
    set_zero_manual_ramp(bank_stress)
    bank_stress_geo = road_output(bank_stress).geometry()
    result = validate_geometry(bank_stress_geo, "bank_s_curve")
    if result:
        return result
    bank_values = [point.attribValue("road_bank_deg") for point in bank_stress_geo.points()]
    if min(bank_values) >= -0.1 or max(bank_values) <= 0.1:
        return fail("bank_s_curve_missing_sign_change")
    result = validate_bank_rate(bank_stress_geo, "bank_s_curve", 8.0, 24.0)
    if result:
        return result

    circle_source = make_closed_circle(obj)
    circle = obj.createNode(ASSET_TYPE, "VERIFY_track_closed_bank")
    circle.parm("unity_curve_input").set(circle_source.path())
    circle.parm("road_width").set(6.0)
    circle.parm("sample_spacing").set(2.0)
    circle.parm("enable_road_banking").set(1)
    circle.parm("bank_design_speed_kph").set(20.0)
    circle.parm("bank_auto_strength").set(1.0)
    circle.parm("bank_max_angle_deg").set(8.0)
    circle.parm("bank_transition_length_m").set(24.0)
    set_zero_manual_ramp(circle)
    circle_geo = road_output(circle).geometry()
    result = validate_geometry(circle_geo, "closed_bank")
    if result:
        return result
    if circle_geo.intAttribValue("road_closed_loop") != 1:
        return fail("closed_bank_not_closed")
    result = validate_bank_rate(circle_geo, "closed_bank", 8.0, 24.0)
    if result:
        return result

    print("VERIFY_OK=1")
    return 0


if __name__ == "__main__":
    sys.exit(main())
