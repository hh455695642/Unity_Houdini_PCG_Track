"""Standalone contract verification for pcgbike::Track::1.0.

The test runs in a disposable hython process.  It never opens or saves the
production hip and it does not modify the HDA definition.
"""

from __future__ import annotations

import math
import os
import re
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


def validate_geometry(geo: hou.Geometry, label: str) -> int:
    if geo.findGlobalAttrib("road_material_boundary_sample_count") is not None:
        return fail("%s_retired_material_boundary_sample_contract_present" % label)

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
    lane_limit = 10.0 if world_planar else 1.50
    shoulder_limit = 10.0 if world_planar else 1.50
    if lane_ratio > lane_limit + 1e-4:
        return fail("%s_lane_uv3_ratio_%f" % (label, lane_ratio))
    if shoulder_ratio > shoulder_limit + 1e-4:
        return fail("%s_shoulder_uv3_ratio_%f" % (label, shoulder_ratio))

    required_detail = (
        "road_input_max_segment_length",
        "road_max_ring_turn_angle_deg",
        "road_min_turn_radius",
        "road_generated_min_turn_radius",
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
        "road_adaptive_reference_count",
        "road_adaptive_output_count",
        "road_adaptive_detail_density",
        "road_adaptive_effective_chord_error_m",
        "road_adaptive_effective_heading_delta_deg",
        "road_adaptive_effective_grade_delta_deg",
        "road_adaptive_effective_bank_delta_deg",
        "road_adaptive_refinement_ratio",
        "road_adaptive_constraint_floor_hit_count",
        "road_max_chord_error_m",
        "road_max_heading_delta_deg",
        "road_max_grade_delta_deg",
        "road_max_bank_delta_deg",
        "road_loop_residual_twist_deg",
        "road_material_undersampled_transition_count",
        "road_material_mask_semantic",
        "road_material_blend_space",
        "road_material_segment_order",
        "road_width_min",
        "road_width_max",
        "road_total_width_min",
        "road_total_width_max",
    )
    for name in required_detail:
        if geo.findGlobalAttrib(name) is None:
            return fail("%s_missing_detail_%s" % (label, name))

    if geo.stringAttribValue("road_surface_uv_mode") != "arc_length_lateral_metric":
        return fail("%s_wrong_uv_mode_%s" % (
            label, geo.stringAttribValue("road_surface_uv_mode")
        ))
    if geo.stringAttribValue("road_material_blend_space") != "arc_length_meters":
        return fail("%s_wrong_material_blend_space" % label)
    if geo.stringAttribValue("road_material_segment_order") != "later_overrides_earlier":
        return fail("%s_wrong_material_segment_order" % label)
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
    width_multiplier = geo.findPointAttrib("road_width_multiplier")
    width_m = geo.findPointAttrib("road_width_m")
    if any(attribute is None for attribute in (
        cd, road_t, normal, bank, grade, spline_roll, has_spline_roll, tangent, lateral, up,
        width_multiplier, width_m,
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
        multiplier = point.attribValue(width_multiplier)
        local_width = point.attribValue(width_m)
        if not math.isfinite(multiplier) or multiplier < -1e-6:
            return fail("%s_invalid_road_width_multiplier_%f" % (label, multiplier))
        if not math.isfinite(local_width) or local_width < 0.0999:
            return fail("%s_invalid_road_width_m_%f" % (label, local_width))
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
        "max_turn=%.6f min_radius=%.6f generated_radius=%.6f bank=%.6f grade=%.6f"
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


def make_bank_transition_curve(obj: hou.Node) -> hou.Node:
    source = obj.createNode("geo", "VERIFY_bank_transition_curve")
    for child in source.children():
        child.destroy()
    node = source.createNode("python", "MAKE_BANK_TRANSITION_CURVE")
    node.parm("python").set(
        """
import math
import hou
geo = hou.pwd().geometry()
geo.clear()
rotation_attrib = geo.addAttrib(hou.attribType.Point, "rot", (0.0, 0.0, 0.0, 1.0))
primitive = geo.createPolygon()
primitive.setIsClosed(False)
for index in range(201):
    x = float(index) * 0.5
    angle = 6.0 * math.sin(x * math.pi * 2.0 / 100.0)
    rotation = hou.Quaternion()
    rotation.setToAngleAxis(angle, hou.Vector3(1.0, 0.0, 0.0))
    point = geo.createPoint()
    point.setPosition(hou.Vector3(x, 0.0, 0.0))
    point.setAttribValue(rotation_attrib, tuple(rotation))
    primitive.addVertex(point)
"""
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


def make_straight_curve(obj: hou.Node, length: float = 500.0) -> hou.Node:
    source = obj.createNode("geo", "VERIFY_straight_curve")
    for child in source.children():
        child.destroy()
    node = source.createNode("python", "MAKE_STRAIGHT_CURVE")
    node.parm("python").set(
        """
import hou
geo = hou.pwd().geometry()
geo.clear()
primitive = geo.createPolygon()
primitive.setIsClosed(False)
for index in range(%d):
    point = geo.createPoint()
    point.setPosition(hou.Vector3(float(index), 0.0, 0.0))
    primitive.addVertex(point)
""" % (int(length) + 1)
    )
    node.setDisplayFlag(True)
    node.setRenderFlag(True)
    return source


def make_smooth_grade_curve(obj: hou.Node) -> hou.Node:
    source = obj.createNode("geo", "VERIFY_smooth_grade_curve")
    for child in source.children():
        child.destroy()
    node = source.createNode("python", "MAKE_SMOOTH_GRADE_CURVE")
    node.parm("python").set(
        """
import math
import hou
geo = hou.pwd().geometry()
geo.clear()
primitive = geo.createPolygon()
primitive.setIsClosed(False)
for index in range(401):
    x = float(index) * 0.5
    y = 8.0 * math.sin(x * math.pi * 2.0 / 200.0)
    point = geo.createPoint()
    point.setPosition(hou.Vector3(x, y, 0.0))
    primitive.addVertex(point)
"""
    )
    node.setDisplayFlag(True)
    node.setRenderFlag(True)
    return source


def make_unwrapped_roll_curve(obj: hou.Node) -> hou.Node:
    source = obj.createNode("geo", "VERIFY_unwrapped_roll_curve")
    for child in source.children():
        child.destroy()
    node = source.createNode("python", "MAKE_UNWRAPPED_ROLL_CURVE")
    node.parm("python").set(
        """
import hou
geo = hou.pwd().geometry()
geo.clear()
rotation_attrib = geo.addAttrib(hou.attribType.Point, "rot", (0.0, 0.0, 0.0, 1.0))
primitive = geo.createPolygon()
primitive.setIsClosed(False)
for index, angle in enumerate((179.0, -179.0)):
    rotation = hou.Quaternion()
    rotation.setToAngleAxis(angle, hou.Vector3(1.0, 0.0, 0.0))
    point = geo.createPoint()
    point.setPosition(hou.Vector3(float(index) * 60.0, 0.0, 0.0))
    point.setAttribValue(rotation_attrib, tuple(rotation))
    primitive.addVertex(point)
"""
    )
    node.setDisplayFlag(True)
    node.setRenderFlag(True)
    return source


def make_closed_quality_curve(obj: hou.Node) -> hou.Node:
    source = obj.createNode("geo", "VERIFY_closed_quality_curve")
    for child in source.children():
        child.destroy()
    node = source.createNode("python", "MAKE_CLOSED_QUALITY_CURVE")
    node.parm("python").set(
        """
import math
import hou
geo = hou.pwd().geometry()
geo.clear()
primitive = geo.createPolygon()
primitive.setIsClosed(True)
for index in range(360):
    angle = 2.0 * math.pi * float(index) / 360.0
    point = geo.createPoint()
    point.setPosition(hou.Vector3(
        50.0 * math.cos(angle),
        4.0 * math.sin(angle * 3.0),
        35.0 * math.sin(angle) + 5.0 * math.sin(angle * 2.0),
    ))
    primitive.addVertex(point)
"""
    )
    node.setDisplayFlag(True)
    node.setRenderFlag(True)
    return source


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
    # The legacy combined output remains the most useful surface for the
    # geometry-level regression suite. Split Quality is validated separately.
    output_mode = asset.parm("road_output_mode")
    if output_mode is not None:
        output_mode.set(0)
    output = asset.node("Road/OUT_ROAD_MESH")
    if output is None:
        raise RuntimeError("Missing Road/OUT_ROAD_MESH")
    output.cook(force=True)
    return output


def centerline_output(asset: hou.Node) -> hou.Node:
    output = asset.node("Road/OUT_ROAD_CENTERLINE")
    if output is None:
        raise RuntimeError("Missing Road/OUT_ROAD_CENTERLINE")
    output.cook(force=True)
    return output


def validate_hq_interface_and_network(asset: hou.Node) -> int:
    expected_parameters = {
        "enable_adaptive_sampling": 1,
        "adaptive_min_spacing_m": 3.0,
        "adaptive_detail_density": 2.0,
        "adaptive_max_chord_error_m": 0.10,
        "adaptive_max_heading_delta_deg": 8.0,
        "adaptive_max_grade_delta_deg": 4.0,
        "adaptive_max_lateral_tilt_delta_deg": 2.0,
        "road_output_mode": 1,
    }
    group = asset.type().definition().parmTemplateGroup()
    for name, expected in expected_parameters.items():
        parameter = asset.parm(name)
        template = group.find(name)
        if parameter is None or template is None:
            return fail("hq_missing_parameter_%s" % name)
        default = template.defaultValue()
        if isinstance(default, tuple):
            default = default[0]
        if abs(float(default) - float(expected)) > 1e-6:
            return fail("hq_default_%s_%s" % (name, default))

    expected_material_parameters = {
        "road_unity_material": "Assets/PCG/Materials/M_PCG_Road.mat",
        "shoulder_unity_material": "Assets/PCG/Materials/M_PCG_Road.mat",
    }
    for name, expected in expected_material_parameters.items():
        parameter = asset.parm(name)
        template = group.find(name)
        if parameter is None or template is None:
            return fail("hq_missing_parameter_%s" % name)
        default = template.defaultValue()[0]
        if default != expected:
            return fail("hq_default_%s_%s" % (name, default))

    for removed_name in (
        "adaptive_max_point_count",
        "adaptive_refine_material_blends",
        "closed_loop_mode",
        "enable_closed_loop_twist_correction",
        "frame_transport_mode",
        "min_shoulder_scale",
        "skirt_unity_material",
    ):
        if asset.parm(removed_name) is not None or group.find(removed_name) is not None:
            return fail("hq_removed_parameter_present_%s" % removed_name)

    top_entries = group.entries()
    top_labels = tuple(entry.label() for entry in top_entries)
    if top_labels != (
        "Transform",
        "Render",
        "Misc",
        "Curve",
        "Track Shape",
        "Track Lateral Tilt / 赛道横倾",
        "Material",
        "Fallback Curve",
    ):
        return fail("hq_top_folder_layout_%s" % (top_labels,))

    curve = group.findFolder("Curve")
    if curve is None:
        return fail("hq_curve_folder_missing")
    curve_names = tuple(template.name() for template in curve.parmTemplates())
    if curve_names != (
        "curve_input_header",
        "unity_curve_input",
        "reverse_curve",
        "curve_sampling_header",
        "sample_spacing",
        "enable_adaptive_sampling",
        "adaptive_detail_density",
        "adaptive_min_spacing_m",
        "curve_quality_header",
        "adaptive_max_chord_error_m",
        "adaptive_max_heading_delta_deg",
        "adaptive_max_grade_delta_deg",
        "adaptive_max_lateral_tilt_delta_deg",
    ):
        return fail("hq_curve_parameter_layout_%s" % (curve_names,))

    curve_labels = {
        template.name(): template.label()
        for template in curve.parmTemplates()
        if isinstance(template, hou.LabelParmTemplate)
    }
    if curve_labels != {
        "curve_input_header": "Curve Input / 曲线输入",
        "curve_sampling_header": "Sampling / 采样",
        "curve_quality_header": "Quality Limits / 质量阈值",
    }:
        return fail("hq_curve_header_labels_%s" % (curve_labels,))

    track_shape = group.findFolder("Track Shape")
    if track_shape is None:
        return fail("hq_track_shape_folder_missing")
    track_shape_names = tuple(template.name() for template in track_shape.parmTemplates())
    if track_shape_names != (
        "track_geometry_header",
        "road_width",
        "road_width_ramp",
        "track_shoulders_header",
        "enable_shoulders",
        "shoulder_width",
        "shoulder_drop",
        "track_start_finish_header",
        "start_prefab",
        "start_prefab_yaw_offset",
        "track_uv_header",
        "uv_tile_length",
        "flip_surface",
    ):
        return fail("hq_track_shape_parameter_layout_%s" % (track_shape_names,))
    track_shape_labels = {
        template.name(): template.label()
        for template in track_shape.parmTemplates()
        if isinstance(template, hou.LabelParmTemplate)
    }
    if track_shape_labels != {
        "track_geometry_header": "Track Geometry / 赛道形状",
        "track_shoulders_header": "Shoulders / 路肩",
        "track_start_finish_header": "Start / Finish / 起终点",
        "track_uv_header": "UV / Unity",
    }:
        return fail("hq_track_shape_header_labels_%s" % (track_shape_labels,))

    road_width_template = group.find("road_width")
    road_width_default = road_width_template.defaultValue()[0]
    if road_width_template.label() != "Road Width" or \
       abs(road_width_default - 20.0) > 1e-6 or \
       abs(road_width_template.minValue() - 1.0) > 1e-6 or \
       abs(road_width_template.maxValue() - 30.0) > 1e-6:
        return fail("hq_road_width_contract_changed")
    ramp_template = group.find("road_width_ramp")
    if not isinstance(ramp_template, hou.RampParmTemplate) or \
       ramp_template.parmType() != hou.rampParmType.Float or \
       ramp_template.label() != "Road Width Multiplier / 道路宽度曲线":
        return fail("hq_road_width_ramp_template")
    ramp = asset.parm("road_width_ramp").evalAsRamp()
    if ramp.keys() != (0.0, 1.0) or ramp.values() != (1.0, 1.0) or \
       ramp.basis() != (hou.rampBasis.Linear, hou.rampBasis.Linear):
        return fail("hq_road_width_ramp_default_%s_%s_%s" % (
            ramp.keys(), ramp.values(), ramp.basis()
        ))
    if "首尾值一致" not in ramp_template.help() or "0.1m" not in ramp_template.help():
        return fail("hq_road_width_ramp_help")

    road_banking = group.findFolder("Track Lateral Tilt / 赛道横倾")
    if road_banking is None:
        return fail("hq_road_banking_folder_missing")
    road_banking_names = tuple(template.name() for template in road_banking.parmTemplates())
    if road_banking_names != (
        "enable_track_lateral_tilt",
        "lateral_tilt_use_spline_knot_tilt",
        "lateral_tilt_design_speed_kph",
        "lateral_tilt_auto_strength",
        "lateral_tilt_max_angle_deg",
        "lateral_tilt_transition_length_m",
    ):
        return fail("hq_road_banking_parameter_layout_%s" % (road_banking_names,))
    lateral_tilt_labels = {
        template.name(): template.label() for template in road_banking.parmTemplates()
    }
    expected_lateral_tilt_labels = {
        "enable_track_lateral_tilt": "Enable Track Lateral Tilt / 启用赛道横倾",
        "lateral_tilt_use_spline_knot_tilt": "Use Spline Knot Tilt / 使用样条控制点横倾",
        "lateral_tilt_design_speed_kph": "Design Speed (km/h) / 设计速度",
        "lateral_tilt_auto_strength": "Auto Lateral Tilt Strength / 自动横倾强度",
        "lateral_tilt_max_angle_deg": "Maximum Lateral Tilt Angle (deg) / 最大横倾角",
        "lateral_tilt_transition_length_m": "Transition Length (m) / 过渡长度",
    }
    if lateral_tilt_labels != expected_lateral_tilt_labels:
        return fail("hq_lateral_tilt_labels_%s" % (lateral_tilt_labels,))
    adaptive_tilt = group.find("adaptive_max_lateral_tilt_delta_deg")
    if adaptive_tilt.label() != "Maximum Lateral Tilt Delta (deg) / 最大横倾变化":
        return fail("hq_adaptive_lateral_tilt_label_%s" % adaptive_tilt.label())

    fallback_curve = group.findFolder("Fallback Curve")
    if fallback_curve is None:
        return fail("hq_fallback_curve_folder_missing")
    fallback_curve_names = tuple(template.name() for template in fallback_curve.parmTemplates())
    if fallback_curve_names != tuple("curve_point_%d" % index for index in range(6)):
        return fail("hq_fallback_curve_parameter_layout_%s" % (fallback_curve_names,))

    for removed_folder in (
        "Source",
        "Sampling",
        "Advanced / Compatibility",
        "Shoulder",
        "UV / Unity Output",
        "Frame Quality / Frame 质量",
        "Material Masks",
        "Adaptive Sampling / 自适应采样",
        "Unity Output / Unity 输出",
    ):
        if group.findFolder(removed_folder) is not None:
            return fail("hq_removed_folder_present_%s" % removed_folder)
    material = group.findFolder("Material")
    if material is None:
        return fail("hq_material_folder_missing")
    material_names = tuple(template.name() for template in material.parmTemplates())
    if material_names != (
        "road_output_mode",
        "road_unity_material",
        "shoulder_unity_material",
        "material_segments",
    ):
        return fail("hq_material_parameter_layout_%s" % (material_names,))

    road = asset.node("Road")
    required_nodes = (
        "CENTERLINE_quality_reference_resample",
        "CENTERLINE_quality_metrics",
        "CENTERLINE_collect_forced_samples",
        "CENTERLINE_adaptive_select",
        "CENTERLINE_sampling_switch",
        "CENTERLINE_polyframe",
        "OUTPUT_extract_road_surface",
        "OUTPUT_extract_shoulders",
        "OUTPUT_extract_skirts",
        "OUTPUT_extract_collision",
        "OUTPUT_road_mode_switch",
        "CENTERLINE_extract_final",
    )
    for name in required_nodes:
        if road.node(name) is None:
            return fail("hq_missing_node_%s" % name)

    # Final surface Frame/lateral tilt and Sweep backbone are intentionally single
    # Legacy paths. Parallel Transport remains only inside adaptive metrics.
    for removed_name in (
        "FRAME_normalize_authored_up",
        "FRAME_compute_grade_bank_parallel",
        "FRAME_quality_switch",
        "FRAME_parallel_transport_centerline",
        "CENTERLINE_quality_switch",
    ):
        if road.node(removed_name) is not None:
            return fail("hq_removed_node_present_%s" % removed_name)
    legacy_frame = road.node("FRAME_compute_grade_bank")
    frame_apply = road.node("FRAME_apply_grade_bank")
    centerline_extract = road.node("CENTERLINE_extract_final")
    if legacy_frame is None or frame_apply is None or centerline_extract is None:
        return fail("hq_legacy_frame_chain_missing")
    if frame_apply.inputs()[0] != legacy_frame:
        return fail("hq_legacy_frame_apply_connection")
    if centerline_extract.inputs()[0] != legacy_frame or \
       centerline_extract.inputs()[1] != legacy_frame:
        return fail("hq_legacy_centerline_extract_connection")
    polyframe = road.node("CENTERLINE_polyframe")
    sampling_switch = road.node("CENTERLINE_sampling_switch")
    profile_dimensions = road.node("PROFILE_compute_dimensions")
    sweep = road.node("SWEEP_road_surface")
    if legacy_frame.inputs()[1] != sampling_switch or polyframe.inputs()[0] != sampling_switch:
        return fail("hq_sampling_frame_connections")
    if profile_dimensions.inputs()[0] != polyframe or sweep.inputs()[0] != polyframe:
        return fail("hq_legacy_polyframe_connections")

    anchor_source = road.node("CENTERLINE_collect_forced_samples").parm("snippet").eval()
    selector_source = road.node("CENTERLINE_adaptive_select").parm("snippet").eval()
    skirt_source = road.node("OUTPUT_extract_skirts").parm("snippet").eval()
    metrics_source = road.node("CENTERLINE_quality_metrics").parm("snippet").eval()
    validation_source = road.node("CENTERLINE_validate_or_fallback").parm("snippet").eval()
    layout_source = road.node("LAYOUT_prepare_dimensions").parm("snippet").eval()
    reproject_source = road.node("SURFACE_reproject_layout").parm("snippet").eval()
    profile_source = road.node("PROFILE_compute_dimensions").parm("snippet").eval()
    if "adaptive_refine_material_blends" in anchor_source:
        return fail("hq_material_refine_toggle_reference_present")
    if "adaptive_max_point_count" in selector_source or \
       "road_adaptive_limit_hit" in selector_source:
        return fail("hq_point_limit_reference_present")
    if "skirt_unity_material" in skirt_source or \
       "../../road_unity_material" not in skirt_source:
        return fail("hq_skirt_material_inheritance_missing")
    if "enable_closed_loop_twist_correction" in metrics_source:
        return fail("hq_twist_correction_reference_present")
    if "min_shoulder_scale" in layout_source or "min_shoulder_scale" in profile_source:
        return fail("hq_min_shoulder_scale_reference_present")
    if "closed_loop_mode" in validation_source:
        return fail("hq_closed_loop_mode_reference_present")
    for required_source in (
        'chramp("../../road_width_ramp", road_t)',
        'setpointattrib(0, "road_width_multiplier"',
        'setpointattrib(0, "road_width_m"',
        'setdetailattrib(0, "road_width_min"',
        'setdetailattrib(0, "road_total_width_max"',
    ):
        if required_source not in reproject_source:
            return fail("hq_width_ramp_source_missing_%s" % required_source)

    source_switch = road.node("CENTERLINE_source_switch1")
    for name in ("CENTERLINE_resample", "CENTERLINE_quality_reference_resample"):
        node = road.node(name)
        if node.inputs()[0] != source_switch:
            return fail("hq_source_connection_%s" % name)

    expected_box_members = {
        "BOX_01_CURVE_SOURCE": {
            "IN_Unity_Curve_Parameter_Input",
            "CENTERLINE_validate_or_fallback",
            "CENTERLINE_reverse_curve",
            "CENTERLINE_reverse_switch",
            "FRAME_decode_unity_rotation",
            "CONTRACT_validate_unity_knots",
            "CONTRACT_prepare_direction",
            "CONTRACT_decode_knot_frames",
            "CENTERLINE_rebuild_unity_bezier",
            "CENTERLINE_source_switch1",
        },
        "BOX_02_SAMPLING": {
            "CENTERLINE_resample",
            "CENTERLINE_quality_reference_resample",
            "CENTERLINE_quality_metrics",
            "CENTERLINE_collect_forced_samples",
            "CENTERLINE_adaptive_select",
            "CENTERLINE_sampling_switch",
            "CENTERLINE_polyframe",
        },
        "BOX_03_PROFILE_SWEEP": {
            "PROFILE_compute_dimensions",
            "PROFILE_clear_centerline",
            "PROFILE_build_polyline",
            "PROFILE_assign_attributes",
            "PROFILE_cross_section",
            "SWEEP_road_surface",
            "SURFACE_reverse_normals",
            "SURFACE_flip_switch",
        },
        "BOX_04_LAYOUT_BANKING": {
            "LAYOUT_prepare_dimensions",
            "SURFACE_reproject_layout",
            "FRAME_compute_grade_bank",
            "FRAME_apply_grade_bank",
        },
        "BOX_05_TOPO_MATERIAL": {
            "TOPO_rebuild_road_quads",
            "UV_write_road_layout",
            "GROUP_road_bands",
            "TOPO_triangulate_for_unity",
            "COLLISION_mark_rendered",
            "NORMAL_generate_surface",
            "MASK_material_segments",
            "ATTR_road_contract",
        },
        "BOX_06_OUTPUTS": {
            "OUTPUT_extract_road_surface",
            "OUTPUT_extract_shoulders",
            "OUTPUT_extract_skirts",
            "OUTPUT_extract_collision",
            "OUTPUT_road_mode_switch",
            "OUT_ROAD_MESH",
            "OUT_ROAD_SHOULDERS",
            "OUT_ROAD_SKIRTS",
            "OUT_ROAD_COLLISION",
            "CENTERLINE_extract_final",
            "OUT_ROAD_CENTERLINE",
        },
        "BOX_07_START_PREFAB": {
            "START_clear_surface",
            "START_prefab_instance",
            "OUT_START_PREFAB_INSTANCE",
        },
    }
    children = tuple(road.children())
    if len(children) != 51:
        return fail("hq_road_node_count_%d" % len(children))
    boxes = {box.name(): box for box in road.networkBoxes()}
    if set(boxes) != set(expected_box_members):
        return fail("hq_network_boxes_%s" % sorted(boxes))
    assigned_nodes = []
    for box_name, expected_members in expected_box_members.items():
        box = boxes[box_name]
        if not box.comment() or "?" in box.comment() or "\ufffd" in box.comment():
            return fail("hq_network_box_comment_%s" % box_name)
        actual_members = {
            item.name() for item in box.items() if isinstance(item, hou.Node)
        }
        if actual_members != expected_members:
            return fail("hq_network_box_members_%s_%s" % (
                box_name, sorted(actual_members)
            ))
        assigned_nodes.extend(actual_members)
    if sorted(assigned_nodes) != sorted(node.name() for node in children):
        return fail("hq_network_box_assignment")

    notes = {note.name(): note for note in road.stickyNotes()}
    if set(notes) != {"ROAD_PIPELINE_GUIDE"}:
        return fail("hq_sticky_notes_%s" % sorted(notes))
    guide_text = notes["ROAD_PIPELINE_GUIDE"].text()
    if "Legacy" not in guide_text or "Output 0" not in guide_text:
        return fail("hq_sticky_note_contract")

    removed_code_terms = (
        "adaptive_max_point_count",
        "adaptive_refine_material_blends",
        "skirt_unity_material",
        "frame_transport_mode",
        "enable_closed_loop_twist_correction",
        "min_shoulder_scale",
        "closed_loop_mode",
        "road_frame_valid",
        "road_loop_transport_twist_deg",
    )
    declaration_pattern = re.compile(
        r"^\s*(?:const\s+)?(?:int|float|string|vector|vector2|vector4|"
        r"matrix2|matrix3|matrix|dict|int\[\]|float\[\]|string\[\]|"
        r"vector\[\])\s+([A-Za-z_]\w*)\s*(?:=|;)"
    )
    for node in children:
        comment = node.comment()
        if not comment or "?" in comment or "\ufffd" in comment:
            return fail("hq_node_comment_%s" % node.name())
        if "world xz" in comment.lower() or "world-xz" in comment.lower():
            return fail("hq_outdated_node_comment_%s" % node.name())
        if node.spareParms():
            return fail("hq_spare_parms_%s" % node.name())
        node_text = []
        for parm in node.parms():
            try:
                node_text.append(parm.rawValue())
            except hou.OperationFailed:
                pass
        node_text = "\n".join(node_text)
        for term in removed_code_terms:
            if term in node_text:
                return fail("hq_removed_code_term_%s_%s" % (node.name(), term))
        snippet_parm = node.parm("snippet")
        if snippet_parm is None:
            continue
        snippet = snippet_parm.eval()
        for line_number, line in enumerate(snippet.splitlines(), 1):
            match = declaration_pattern.match(line)
            if match is None:
                continue
            local_name = match.group(1)
            if len(re.findall(r"\b%s\b" % re.escape(local_name), snippet)) == 1:
                return fail("hq_unused_vex_local_%s_%d_%s" % (
                    node.name(), line_number, local_name
                ))

    expected_outputs = (
        (0, "OUT_ROAD_MESH"),
        (1, "OUT_START_PREFAB_INSTANCE"),
        (2, "OUT_ROAD_SHOULDERS"),
        (3, "OUT_ROAD_SKIRTS"),
        (4, "OUT_ROAD_COLLISION"),
        (5, "OUT_ROAD_CENTERLINE"),
    )
    for index, name in expected_outputs:
        node = road.node(name)
        if node is None:
            return fail("hq_missing_output_%d_%s" % (index, name))
        index_parm = node.parm("outputidx")
        if index_parm is not None and index_parm.eval() != index:
            return fail("hq_output_index_%s_%d" % (name, index_parm.eval()))
    return 0


def validate_adaptive_limits(asset: hou.Node, label: str) -> int:
    geo = centerline_output(asset).geometry()
    density = asset.parm("adaptive_detail_density").eval()
    checks = (
        (
            "road_max_chord_error_m",
            "road_adaptive_effective_chord_error_m",
            asset.parm("adaptive_max_chord_error_m").eval() / (density * density),
        ),
        (
            "road_max_heading_delta_deg",
            "road_adaptive_effective_heading_delta_deg",
            asset.parm("adaptive_max_heading_delta_deg").eval() / density,
        ),
        (
            "road_max_grade_delta_deg",
            "road_adaptive_effective_grade_delta_deg",
            asset.parm("adaptive_max_grade_delta_deg").eval() / density,
        ),
        (
            "road_max_bank_delta_deg",
            "road_adaptive_effective_bank_delta_deg",
            asset.parm("adaptive_max_lateral_tilt_delta_deg").eval() / density,
        ),
    )
    for detail_name, effective_name, expected in checks:
        actual = geo.floatAttribValue(detail_name)
        maximum = geo.floatAttribValue(effective_name)
        if abs(maximum - expected) > 1e-5:
            return fail("%s_%s_%f_expected_%f" % (label, effective_name, maximum, expected))
        if actual > maximum + 2e-3:
            return fail("%s_%s_%f_over_%f" % (label, detail_name, actual, maximum))
    if abs(geo.floatAttribValue("road_adaptive_detail_density") - density) > 1e-6:
        return fail("%s_adaptive_density_mismatch" % label)
    base_count = max(geo.intAttribValue("road_adaptive_base_count_estimate"), 1)
    expected_ratio = len(geo.points()) / float(base_count)
    if abs(geo.floatAttribValue("road_adaptive_refinement_ratio") - expected_ratio) > 1e-5:
        return fail("%s_adaptive_refinement_ratio_mismatch" % label)
    if geo.intAttribValue("road_adaptive_constraint_floor_hit_count") != 0:
        return fail("%s_adaptive_constraint_floor_hit" % label)
    if geo.intAttribValue("road_adaptive_output_count") != len(geo.points()):
        return fail("%s_adaptive_output_count_mismatch" % label)
    return 0


def source_quad_ids(geo: hou.Geometry):
    attribute = geo.findPrimAttrib("road_source_quad")
    if attribute is None:
        return set()
    return {primitive.attribValue(attribute) for primitive in geo.prims()}


def validate_split_outputs(asset: hou.Node, label: str) -> int:
    asset.parm("road_output_mode").set(0)
    combined_node = asset.node("Road/OUT_ROAD_MESH")
    combined_node.cook(force=True)
    combined_geo = combined_node.geometry()
    combined_ids = source_quad_ids(combined_geo)
    combined_primitive_count = len(combined_geo.prims())

    asset.parm("road_output_mode").set(1)
    output_names = {
        "road": ("OUT_ROAD_MESH", "Road_Surface"),
        "shoulder": ("OUT_ROAD_SHOULDERS", "Road_Shoulders"),
        "skirt": ("OUT_ROAD_SKIRTS", "Road_Skirts"),
        "collision": ("OUT_ROAD_COLLISION", "Road_Collision"),
        "centerline": ("OUT_ROAD_CENTERLINE", "Road_Centerline_Data"),
    }
    geometries = {}
    for key, (node_name, unity_name) in output_names.items():
        node = asset.node("Road/%s" % node_name)
        node.cook(force=True)
        geometry = node.geometry()
        geometries[key] = geometry
        if geometry.findGlobalAttrib("unity_output_name") is None or \
           geometry.stringAttribValue("unity_output_name") != unity_name:
            return fail("%s_output_name_%s" % (label, key))

    road_ids = source_quad_ids(geometries["road"])
    shoulder_ids = source_quad_ids(geometries["shoulder"])
    skirt_ids = source_quad_ids(geometries["skirt"])
    collision_ids = source_quad_ids(geometries["collision"])
    for key in ("road", "shoulder", "skirt"):
        rendered_collision = geometries[key].findPrimGroup("rendered_collision_geo")
        if rendered_collision is not None and len(rendered_collision.prims()) != 0:
            return fail("%s_duplicate_render_collider_%s" % (label, key))
    collision_group = geometries["collision"].findPrimGroup("collision_geo")
    if collision_group is None or len(collision_group.prims()) != len(geometries["collision"].prims()):
        return fail("%s_missing_collision_group" % label)
    if road_ids & shoulder_ids or road_ids & skirt_ids or shoulder_ids & skirt_ids:
        return fail("%s_split_duplicate_source_quad" % label)
    if road_ids | shoulder_ids | skirt_ids != combined_ids:
        return fail("%s_split_union_mismatch" % label)
    if collision_ids != road_ids | shoulder_ids:
        return fail("%s_collision_contract_mismatch" % label)
    if len(geometries["road"].prims()) + len(geometries["shoulder"].prims()) + \
       len(geometries["skirt"].prims()) != combined_primitive_count:
        return fail("%s_split_primitive_count_mismatch" % label)
    centerline = geometries["centerline"]
    if len(centerline.points()) != centerline.intAttribValue("road_adaptive_output_count"):
        return fail("%s_centerline_ring_count_mismatch" % label)
    if len(centerline.prims()) != 0:
        return fail("%s_centerline_generated_render_geometry" % label)
    if centerline.findGlobalAttrib("road_centerline_data_only") is None or \
       centerline.intAttribValue("road_centerline_data_only") != 1:
        return fail("%s_centerline_not_data_only" % label)
    if centerline.findGlobalAttrib("unity_tag") is None or \
       centerline.stringAttribValue("unity_tag") != "EditorOnly":
        return fail("%s_centerline_not_editor_data" % label)
    for key, parameter_name in (
        ("road", "road_unity_material"),
        ("shoulder", "shoulder_unity_material"),
        ("skirt", "road_unity_material"),
    ):
        geometry = geometries[key]
        if geometry.findGlobalAttrib("unity_material") is None or \
           geometry.stringAttribValue("unity_material") != asset.parm(parameter_name).eval():
            return fail("%s_unity_material_%s" % (label, key))
    return 0


def validate_profile_contract(asset: hou.Node, label: str) -> int:
    road = asset.node("Road")
    expected_nodes = {
        "PROFILE_compute_dimensions": "attribwrangle",
        "PROFILE_clear_centerline": "blast",
        "PROFILE_build_polyline": "add",
        "PROFILE_assign_attributes": "attribwrangle",
        "PROFILE_cross_section": "null",
    }
    for node_name, node_type in expected_nodes.items():
        node = road.node(node_name)
        if node is None or node.type().name() != node_type:
            return fail("%s_profile_node_%s_not_%s" % (label, node_name, node_type))
    if road.node("CENTERLINE_material_segment_samples") is not None:
        return fail("%s_retired_material_sample_node_present" % label)

    resample = road.node("CENTERLINE_sampling_switch")
    polyframe = road.node("CENTERLINE_polyframe")
    profile = road.node("PROFILE_cross_section")
    profile.cook(force=True)
    resample_geo = resample.geometry()
    polyframe_geo = polyframe.geometry()
    profile_geo = profile.geometry()
    if len(resample_geo.points()) != len(polyframe_geo.points()):
        return fail("%s_centerline_sample_count_changed" % label)
    if profile_geo.findGlobalAttrib("road_material_boundary_sample_count") is not None:
        return fail("%s_profile_retired_sample_contract_present" % label)
    if len(profile_geo.points()) != 4 or len(profile_geo.prims()) != 1:
        return fail("%s_profile_topology_%d_%d" % (
            label, len(profile_geo.points()), len(profile_geo.prims())
        ))
    if profile_geo.prims()[0].isClosed():
        return fail("%s_profile_must_be_open" % label)

    road_width = max(asset.parm("road_width").eval(), 0.1)
    shoulder_width_param = (
        max(asset.parm("shoulder_width").eval(), 0.0)
        if asset.parm("enable_shoulders").eval() else 0.0
    )
    shoulder_width = shoulder_width_param
    shoulder_drop = max(asset.parm("shoulder_drop").eval(), 0.0) if shoulder_width > 1e-5 else 0.0
    total_width = max(road_width + shoulder_width * 2.0, 0.1)
    expected_positions = (
        (-total_width * 0.5, -shoulder_drop, 0.0),
        (-road_width * 0.5, 0.0, 0.0),
        (road_width * 0.5, 0.0, 0.0),
        (total_width * 0.5, -shoulder_drop, 0.0),
    )
    expected_bands = (1, 0, 0, 1)
    expected_lateral_t = (
        0.0,
        shoulder_width / total_width,
        (shoulder_width + road_width) / total_width,
        1.0,
    )
    for index, point in enumerate(profile_geo.points()):
        if (point.position() - hou.Vector3(expected_positions[index])).length() > 1e-5:
            return fail("%s_profile_position_%d_%s" % (label, index, tuple(point.position())))
        if point.attribValue("profile_section") != index:
            return fail("%s_profile_section_%d" % (label, index))
        if point.attribValue("road_band") != expected_bands[index]:
            return fail("%s_profile_band_%d" % (label, index))
        if abs(point.attribValue("road_lateral_t") - expected_lateral_t[index]) > 1e-5:
            return fail("%s_profile_lateral_t_%d" % (label, index))

    expected_detail = {
        "road_total_width": total_width,
        "road_cross_section_count": 4,
        "road_band_count": 3,
        "road_has_shoulders": int(shoulder_width > 1e-5),
        "road_min_visible_shoulder_width": shoulder_width,
        "road_min_lateral_scale": (
            max(min(shoulder_width / shoulder_width_param, 1.0), 0.0)
            if shoulder_width_param > 1e-5 else 1.0
        ),
    }
    for name, expected in expected_detail.items():
        actual = profile_geo.attribValue(name)
        if abs(float(actual) - float(expected)) > 1e-5:
            return fail("%s_profile_detail_%s_%s" % (label, name, actual))
    return 0


def validate_width_ramp_contract(asset: hou.Node, label: str) -> int:
    """Validate per-ring widths before banking/topology changes point ordering."""
    layout = asset.node("Road/SURFACE_reproject_layout")
    layout.cook(force=True)
    if layout.errors():
        return fail("%s_layout_cook_%s" % (label, layout.errors()))
    geo = layout.geometry()
    cross_section_count = geo.intAttribValue("road_cross_section_count")
    ring_count = geo.intAttribValue("road_sample_count")
    if cross_section_count != 4 or len(geo.points()) != ring_count * cross_section_count:
        return fail("%s_layout_topology_%d_%d_%d" % (
            label, ring_count, cross_section_count, len(geo.points())
        ))

    multiplier_attrib = geo.findPointAttrib("road_width_multiplier")
    width_attrib = geo.findPointAttrib("road_width_m")
    lateral_offset_attrib = geo.findPointAttrib("road_lateral_offset_m")
    lateral_t_attrib = geo.findPointAttrib("road_lateral_t")
    original_center_attrib = geo.findPointAttrib("road_original_center")
    road_t_attrib = geo.findPointAttrib("road_t")
    if any(attrib is None for attrib in (
        multiplier_attrib, width_attrib, lateral_offset_attrib,
        lateral_t_attrib, original_center_attrib, road_t_attrib,
    )):
        return fail("%s_missing_layout_width_attributes" % label)

    base_width = asset.parm("road_width").eval()
    shoulder_width = (
        asset.parm("shoulder_width").eval()
        if asset.parm("enable_shoulders").eval() else 0.0
    )
    ramp = asset.parm("road_width_ramp").evalAsRamp()
    sampled_widths = []
    sampled_total_widths = []
    for ring in range(ring_count):
        points = geo.points()[ring * cross_section_count:(ring + 1) * cross_section_count]
        road_t = points[0].attribValue(road_t_attrib)
        expected_multiplier = max(ramp.lookup(road_t), 0.0)
        expected_width = max(base_width * expected_multiplier, 0.1)
        offsets = [point.attribValue(lateral_offset_attrib) for point in points]
        lateral_ts = [point.attribValue(lateral_t_attrib) for point in points]
        main_width = offsets[2] - offsets[1]
        left_shoulder = offsets[1] - offsets[0]
        right_shoulder = offsets[3] - offsets[2]
        lane_center = (points[1].position() + points[2].position()) * 0.5
        authored_center = hou.Vector3(points[0].attribValue(original_center_attrib))
        if (lane_center - authored_center).length() > 1e-4:
            return fail("%s_ring_%d_center_moved" % (label, ring))
        if abs(points[0].attribValue(multiplier_attrib) - expected_multiplier) > 1e-5:
            return fail("%s_ring_%d_multiplier" % (label, ring))
        if abs(points[0].attribValue(width_attrib) - expected_width) > 1e-5 or \
           abs(main_width - expected_width) > 1e-5:
            return fail("%s_ring_%d_width" % (label, ring))
        if abs(left_shoulder - shoulder_width) > 1e-5 or \
           abs(right_shoulder - shoulder_width) > 1e-5:
            return fail("%s_ring_%d_shoulder" % (label, ring))
        total_width = expected_width + shoulder_width * 2.0
        expected_lateral_t = tuple(
            max(min((offset + total_width * 0.5) / total_width, 1.0), 0.0)
            for offset in offsets
        )
        if any(abs(actual - expected) > 1e-5 for actual, expected in zip(
            lateral_ts, expected_lateral_t
        )):
            return fail("%s_ring_%d_lateral_t" % (label, ring))
        sampled_widths.append(expected_width)
        sampled_total_widths.append(total_width)

    expected_details = {
        "road_width_min": min(sampled_widths),
        "road_width_max": max(sampled_widths),
        "road_total_width_min": min(sampled_total_widths),
        "road_total_width_max": max(sampled_total_widths),
    }
    for name, expected in expected_details.items():
        if geo.findGlobalAttrib(name) is None:
            return fail("%s_missing_detail_%s" % (label, name))
        if abs(geo.floatAttribValue(name) - expected) > 1e-5:
            return fail("%s_detail_%s_%f_expected_%f" % (
                label, name, geo.floatAttribValue(name), expected
            ))
    return 0


def main() -> int:
    if not os.path.isfile(HDA_PATH):
        return fail("missing_hda_%s" % HDA_PATH)
    hou.hda.installFile(HDA_PATH)
    obj = hou.node("/obj")

    fallback = obj.createNode(ASSET_TYPE, "VERIFY_track_fallback")
    result = validate_hq_interface_and_network(fallback)
    if result:
        return result
    # Reproduce the production Live Scene fallback configuration for the
    # strict identity baseline; the public HDA default keeps adaptive sampling enabled.
    fallback.parm("enable_adaptive_sampling").set(0)
    default_output = fallback.node("Road/OUT_ROAD_MESH")
    default_output.cook(force=True)
    default_geo = default_output.geometry()
    default_vertex_count = sum(len(primitive.vertices()) for primitive in default_geo.prims())
    if (len(default_geo.points()), len(default_geo.prims()), default_vertex_count) != (32, 30, 90):
        return fail("fallback_default_identity_counts_%d_%d_%d" % (
            len(default_geo.points()), len(default_geo.prims()), default_vertex_count
        ))
    if default_geo.findVertexAttrib("uv") is None or \
       default_geo.findVertexAttrib("uv3") is None or \
       default_geo.findPrimGroup("lane") is None:
        return fail("fallback_default_identity_contract")
    default_collision = fallback.node("Road/OUT_ROAD_COLLISION")
    default_collision.cook(force=True)
    default_collision_geo = default_collision.geometry()
    default_collision_vertex_count = sum(
        len(primitive.vertices()) for primitive in default_collision_geo.prims()
    )
    if (len(default_collision_geo.points()), len(default_collision_geo.prims()),
            default_collision_vertex_count) != (64, 90, 270):
        return fail("fallback_default_collision_counts_%d_%d_%d" % (
            len(default_collision_geo.points()), len(default_collision_geo.prims()),
            default_collision_vertex_count,
        ))
    collision_group = default_collision_geo.findPrimGroup("collision_geo")
    if collision_group is None or len(collision_group.prims()) != len(default_collision_geo.prims()):
        return fail("fallback_default_collision_group")
    fallback.parm("enable_adaptive_sampling").set(1)
    removed_guard_parameters = (
        "tight_turn_guard_enable",
        "tight_turn_min_inner_radius",
        "tight_turn_transition_length",
        "tight_turn_max_offset",
    )
    for parameter_name in removed_guard_parameters:
        if fallback.parm(parameter_name) is not None:
            return fail("fallback_deprecated_guard_parameter_%s" % parameter_name)
    if fallback.parm("enable_track_lateral_tilt") is None:
        return fail("fallback_missing_banking_parameters")
    if fallback.parm("enable_track_lateral_tilt").eval() != 0:
        return fail("fallback_banking_default_not_disabled")
    if fallback.parm("lateral_tilt_use_spline_knot_tilt") is None:
        return fail("fallback_missing_spline_knot_roll_toggle")
    if fallback.parm("lateral_tilt_use_spline_knot_tilt").eval() != 1:
        return fail("fallback_spline_knot_roll_default_not_enabled")
    if fallback.parm("bank_manual_offset_ramp") is not None:
        return fail("fallback_manual_ramp_parameter_still_present")
    fallback.parm("road_width").set(6.0)
    fallback.parm("sample_spacing").set(1.5)
    open_profile_cases = (
        ("open_shoulders", 6.0, 1, 1.0, 0.08),
        ("open_shoulders_disabled", 6.0, 0, 2.0, 0.20),
        ("open_zero_shoulder", 6.0, 1, 0.0, 0.15),
        ("open_wide_drop", 10.0, 1, 1.5, 0.30),
    )
    for label, width, enabled, shoulder_width, shoulder_drop in open_profile_cases:
        fallback.parm("road_width").set(width)
        fallback.parm("enable_shoulders").set(enabled)
        fallback.parm("shoulder_width").set(shoulder_width)
        fallback.parm("shoulder_drop").set(shoulder_drop)
        result = validate_profile_contract(fallback, label)
        if result:
            return result
    fallback.parm("road_width").set(6.0)
    fallback.parm("enable_shoulders").set(1)
    fallback.parm("shoulder_width").set(1.0)
    fallback.parm("shoulder_drop").set(0.08)
    fallback_geo = road_output(fallback).geometry()
    result = validate_geometry(fallback_geo, "fallback")
    if result:
        return result
    if fallback_geo.stringAttribValue("road_source") != "fallback_points":
        return fail("fallback_wrong_source")

    straight_source = make_straight_curve(obj)
    width_ramp = obj.createNode(ASSET_TYPE, "VERIFY_track_width_ramp")
    width_ramp.parm("unity_curve_input").set(straight_source.path())
    width_ramp.parm("enable_adaptive_sampling").set(0)
    width_ramp.parm("sample_spacing").set(50.0)
    width_ramp.parm("road_width").set(6.0)
    width_ramp.parm("enable_shoulders").set(1)
    width_ramp.parm("shoulder_width").set(2.0)
    width_ramp.parm("shoulder_drop").set(0.08)
    width_ramp.parm("road_width_ramp").set(hou.Ramp(
        (hou.rampBasis.Linear, hou.rampBasis.Linear, hou.rampBasis.Linear),
        (0.0, 0.5, 1.0),
        (1.0, 0.5, 1.0),
    ))
    result = validate_width_ramp_contract(width_ramp, "width_ramp_variable")
    if result:
        return result
    width_layout_geo = width_ramp.node("Road/SURFACE_reproject_layout").geometry()
    if abs(width_layout_geo.floatAttribValue("road_width_min") - 3.0) > 1e-5 or \
       abs(width_layout_geo.floatAttribValue("road_width_max") - 6.0) > 1e-5 or \
       abs(width_layout_geo.floatAttribValue("road_total_width_min") - 7.0) > 1e-5 or \
       abs(width_layout_geo.floatAttribValue("road_total_width_max") - 10.0) > 1e-5:
        return fail("width_ramp_variable_ranges")
    width_ramp.parm("enable_adaptive_sampling").set(1)
    result = validate_split_outputs(width_ramp, "width_ramp_variable")
    if result:
        return result

    width_ramp.parm("road_width_ramp").set(hou.Ramp(
        (hou.rampBasis.Linear, hou.rampBasis.Linear), (0.0, 1.0), (2.0, 2.0)
    ))
    result = validate_width_ramp_contract(width_ramp, "width_ramp_expand")
    if result:
        return result
    if abs(width_ramp.node("Road/SURFACE_reproject_layout").geometry().floatAttribValue(
        "road_width_min"
    ) - 12.0) > 1e-5:
        return fail("width_ramp_expand_not_12m")

    width_ramp.parm("road_width_ramp").set(hou.Ramp(
        (hou.rampBasis.Linear, hou.rampBasis.Linear), (0.0, 1.0), (-1.0, -1.0)
    ))
    result = validate_width_ramp_contract(width_ramp, "width_ramp_clamp")
    if result:
        return result
    clamped_geo = road_output(width_ramp).geometry()
    if abs(clamped_geo.floatAttribValue("road_width_min") - 0.1) > 1e-5:
        return fail("width_ramp_negative_not_clamped")
    result = validate_geometry(clamped_geo, "width_ramp_clamp")
    if result:
        return result

    straight = obj.createNode(ASSET_TYPE, "VERIFY_track_adaptive_straight")
    straight.parm("unity_curve_input").set(straight_source.path())
    straight.parm("sample_spacing").set(8.0)
    straight_centerline = centerline_output(straight).geometry()
    straight_count = len(straight_centerline.points())
    if straight_count < 84 or straight_count > 86:
        return fail("adaptive_straight_count_%d" % straight_count)
    straight_reference_count = straight_centerline.intAttribValue("road_adaptive_reference_count")
    if straight_reference_count < 160:
        return fail("adaptive_straight_reference_not_dense_%d" % straight_reference_count)
    straight_points = straight_centerline.points()
    for index in range(1, len(straight_points)):
        spacing = (straight_points[index].position() - straight_points[index - 1].position()).length()
        if spacing > 8.001:
            return fail("adaptive_straight_spacing_%f" % spacing)
    result = validate_adaptive_limits(straight, "adaptive_straight")
    if result:
        return result

    # Detail Density only controls adaptive refinement. A perfectly straight
    # section must remain governed exclusively by sample_spacing.
    straight_density_counts = {}
    for density in (0.25, 0.5, 1.0, 2.0):
        straight.parm("adaptive_detail_density").set(density)
        density_geo = centerline_output(straight).geometry()
        straight_density_counts[density] = len(density_geo.points())
        result = validate_adaptive_limits(straight, "adaptive_straight_density_%s" % density)
        if result:
            return result
    if len(set(straight_density_counts.values())) != 1:
        return fail("adaptive_density_changed_straight_%s" % straight_density_counts)
    straight.parm("adaptive_detail_density").set(1.0)

    # The legacy branch must ignore the new density parameter completely.
    legacy_density = obj.createNode(ASSET_TYPE, "VERIFY_track_legacy_density")
    legacy_density.parm("unity_curve_input").set(straight_source.path())
    legacy_density.parm("sample_spacing").set(8.0)
    legacy_density.parm("enable_adaptive_sampling").set(0)
    legacy_positions = {}
    for density in (0.25, 2.0):
        legacy_density.parm("adaptive_detail_density").set(density)
        legacy_geo = centerline_output(legacy_density).geometry()
        legacy_positions[density] = [tuple(point.position()) for point in legacy_geo.points()]
    if legacy_positions[0.25] != legacy_positions[2.0]:
        return fail("adaptive_density_changed_legacy_branch")

    # sample_spacing remains the primary density control on ordinary sections.
    straight_coarse = obj.createNode(ASSET_TYPE, "VERIFY_track_adaptive_straight_coarse")
    straight_coarse.parm("unity_curve_input").set(straight_source.path())
    straight_coarse.parm("sample_spacing").set(16.0)
    straight_coarse_centerline = centerline_output(straight_coarse).geometry()
    coarse_count = len(straight_coarse_centerline.points())
    if coarse_count < 34 or coarse_count > 36:
        return fail("adaptive_straight_coarse_count_%d" % coarse_count)
    if coarse_count >= straight_count:
        return fail("adaptive_sample_spacing_not_controlling_density")
    coarse_refine_count = straight_coarse_centerline.intAttribValue("road_adaptive_refine_count")
    if coarse_refine_count > 2:
        return fail("adaptive_straight_unnecessary_refinement_%d" % coarse_refine_count)

    adaptive_hairpin_source = make_hairpin_curve(obj)
    adaptive_hairpin = obj.createNode(ASSET_TYPE, "VERIFY_track_adaptive_hairpin")
    adaptive_hairpin.parm("unity_curve_input").set(adaptive_hairpin_source.path())
    adaptive_hairpin.parm("road_width").set(6.0)
    adaptive_hairpin.parm("sample_spacing").set(8.0)
    # A 12-14 m hairpin needs sub-metre samples to satisfy a strict 3 degree
    # tangent threshold; this case explicitly exercises that allowed setting.
    adaptive_hairpin.parm("adaptive_min_spacing_m").set(0.5)
    result = validate_adaptive_limits(adaptive_hairpin, "adaptive_hairpin")
    if result:
        return result
    adaptive_hairpin_geo = road_output(adaptive_hairpin).geometry()
    if adaptive_hairpin_geo.intAttribValue("road_lane_overlap_count") != 0:
        return fail("adaptive_hairpin_lane_overlap")

    # A large sample spacing keeps ordinary sections sparse, while Detail
    # Density predictably scales only the hairpin refinement.
    density_hairpin = obj.createNode(ASSET_TYPE, "VERIFY_track_density_hairpin")
    density_hairpin.parm("unity_curve_input").set(adaptive_hairpin_source.path())
    density_hairpin.parm("road_width").set(6.0)
    density_hairpin.parm("sample_spacing").set(32.0)
    density_hairpin.parm("adaptive_min_spacing_m").set(0.25)
    hairpin_density_counts = {}
    for density in (0.25, 0.5, 1.0, 2.0):
        density_hairpin.parm("adaptive_detail_density").set(density)
        density_geo = centerline_output(density_hairpin).geometry()
        hairpin_density_counts[density] = len(density_geo.points())
        result = validate_adaptive_limits(
            density_hairpin, "adaptive_density_hairpin_%s" % density
        )
        if result:
            return result
    if not (
        hairpin_density_counts[0.25] <= hairpin_density_counts[0.5] <
        hairpin_density_counts[1.0] < hairpin_density_counts[2.0]
    ):
        return fail("adaptive_density_hairpin_not_monotonic_%s" % hairpin_density_counts)
    if hairpin_density_counts[0.5] > hairpin_density_counts[1.0] * 0.75:
        return fail("adaptive_density_hairpin_half_not_effective_%s" % hairpin_density_counts)

    # Deliberately coarse analysis spacing must report that an adjacent
    # reference interval cannot satisfy the effective high-density limits.
    density_floor = obj.createNode(ASSET_TYPE, "VERIFY_track_density_floor")
    density_floor.parm("unity_curve_input").set(adaptive_hairpin_source.path())
    density_floor.parm("sample_spacing").set(32.0)
    density_floor.parm("adaptive_min_spacing_m").set(8.0)
    density_floor.parm("adaptive_detail_density").set(2.0)
    density_floor_geo = centerline_output(density_floor).geometry()
    if density_floor_geo.intAttribValue("road_adaptive_constraint_floor_hit_count") <= 0:
        return fail("adaptive_density_floor_not_reported")
    if density_floor_geo.findGlobalAttrib("road_adaptive_limit_hit") is not None:
        return fail("adaptive_density_obsolete_point_limit_diagnostic")

    smooth_grade_source = make_smooth_grade_curve(obj)
    smooth_grade = obj.createNode(ASSET_TYPE, "VERIFY_track_adaptive_grade")
    smooth_grade.parm("unity_curve_input").set(smooth_grade_source.path())
    smooth_grade.parm("sample_spacing").set(8.0)
    smooth_grade.parm("adaptive_min_spacing_m").set(0.5)
    result = validate_adaptive_limits(smooth_grade, "adaptive_grade")
    if result:
        return result
    smooth_grade_geo = centerline_output(smooth_grade).geometry()
    if smooth_grade_geo.floatAttribValue("road_max_abs_grade_deg") < 5.0:
        return fail("adaptive_grade_missing_slope")

    density_grade = obj.createNode(ASSET_TYPE, "VERIFY_track_density_grade")
    density_grade.parm("unity_curve_input").set(smooth_grade_source.path())
    density_grade.parm("sample_spacing").set(32.0)
    density_grade.parm("adaptive_min_spacing_m").set(0.25)
    density_grade.parm("adaptive_max_chord_error_m").set(0.5)
    density_grade.parm("adaptive_max_heading_delta_deg").set(15.0)
    density_grade.parm("adaptive_max_grade_delta_deg").set(2.0)
    density_grade.parm("adaptive_max_lateral_tilt_delta_deg").set(5.0)
    grade_density_counts = {}
    for density in (0.5, 1.0, 2.0):
        density_grade.parm("adaptive_detail_density").set(density)
        density_geo = centerline_output(density_grade).geometry()
        grade_density_counts[density] = len(density_geo.points())
        result = validate_adaptive_limits(
            density_grade, "adaptive_density_grade_%s" % density
        )
        if result:
            return result
    if not (
        grade_density_counts[0.5] < grade_density_counts[1.0] <
        grade_density_counts[2.0]
    ):
        return fail("adaptive_density_grade_not_monotonic_%s" % grade_density_counts)

    unwrapped_roll_source = make_unwrapped_roll_curve(obj)
    unwrapped_roll = obj.createNode(ASSET_TYPE, "VERIFY_track_unwrapped_roll")
    unwrapped_roll.parm("unity_curve_input").set(unwrapped_roll_source.path())
    unwrapped_roll.parm("sample_spacing").set(2.0)
    unwrapped_roll.parm("enable_track_lateral_tilt").set(1)
    unwrapped_roll.parm("lateral_tilt_use_spline_knot_tilt").set(1)
    unwrapped_roll.parm("lateral_tilt_auto_strength").set(0.0)
    unwrapped_roll.parm("lateral_tilt_max_angle_deg").set(8.0)
    unwrapped_roll.parm("lateral_tilt_transition_length_m").set(0.0)
    unwrapped_roll_geo = road_output(unwrapped_roll).geometry()
    cross_section_count = unwrapped_roll_geo.intAttribValue("road_cross_section_count")
    roll_points = unwrapped_roll_geo.points()[::cross_section_count]
    authored_rolls = [point.attribValue("road_spline_roll_deg") for point in roll_points]
    applied_rolls = [point.attribValue("road_bank_deg") for point in roll_points]
    if min(authored_rolls) < 178.5 or max(authored_rolls) > 181.5:
        return fail("unwrapped_roll_long_path_%f_%f" % (min(authored_rolls), max(authored_rolls)))
    if min(applied_rolls) < 7.95 or max(applied_rolls) > 8.001:
        return fail("unwrapped_roll_not_clamped_%f_%f" % (min(applied_rolls), max(applied_rolls)))

    closed_quality_source = make_closed_quality_curve(obj)
    closed_quality = obj.createNode(ASSET_TYPE, "VERIFY_track_closed_quality")
    closed_quality.parm("unity_curve_input").set(closed_quality_source.path())
    closed_quality.parm("sample_spacing").set(8.0)
    closed_quality.parm("adaptive_min_spacing_m").set(0.25)
    result = validate_adaptive_limits(closed_quality, "closed_quality")
    if result:
        return result
    closed_centerline = centerline_output(closed_quality).geometry()
    if closed_centerline.intAttribValue("road_closed_loop") != 1 or \
       closed_centerline.intAttribValue("road_centerline_closed_loop") != 1 or \
       closed_centerline.intAttribValue("road_centerline_data_only") != 1 or \
       len(closed_centerline.prims()) != 0:
        return fail("closed_quality_not_closed")
    if closed_centerline.floatAttribValue("road_seam_position_error") > 0.001:
        return fail("closed_quality_seam_position")
    if abs(closed_centerline.floatAttribValue("road_loop_residual_twist_deg")) > 0.1:
        return fail("closed_quality_residual_twist_%f" % (
            closed_centerline.floatAttribValue("road_loop_residual_twist_deg")
        ))
    if closed_centerline.intAttribValue("road_frame_flip_count") != 0:
        return fail("closed_quality_frame_flip")
    first = closed_centerline.points()[0]
    last = closed_centerline.points()[-1]
    # The data-only centerline deliberately has no duplicated seam point. The
    # last point is one adaptive sample before Knot 0, so its frame may differ
    # by one legal heading/bank step rather than being numerically identical.
    seam_min_dot = math.cos(math.radians(
        closed_quality.parm("adaptive_max_heading_delta_deg").eval() +
        closed_quality.parm("adaptive_max_lateral_tilt_delta_deg").eval() + 0.1
    ))
    for attribute_name in ("road_frame_tangent", "road_frame_lateral", "road_frame_up"):
        first_value = hou.Vector3(first.attribValue(attribute_name))
        last_value = hou.Vector3(last.attribValue(attribute_name))
        if first_value.dot(last_value) <= seam_min_dot:
            return fail("closed_quality_seam_%s_%f" % (
                attribute_name, first_value.dot(last_value)
            ))
    if any(point.attribValue("road_distance") >= closed_centerline.floatAttribValue("road_length")
           for point in closed_centerline.points()):
        return fail("closed_quality_centerline_distance_seam")
    closed_combined = road_output(closed_quality).geometry()
    uv_attribute = closed_combined.findVertexAttrib("uv")
    longitudinal = [
        vertex.attribValue(uv_attribute)[1]
        for primitive in closed_combined.prims()
        for vertex in primitive.vertices()
    ]
    expected_uv_span = (
        closed_combined.floatAttribValue("road_length") /
        closed_combined.floatAttribValue("road_uv_tile_length")
    )
    actual_uv_span = max(longitudinal) - min(longitudinal)
    if abs(actual_uv_span - expected_uv_span) > 2e-3:
        return fail("closed_quality_uv_seam_span_%f_expected_%f" % (
            actual_uv_span, expected_uv_span
        ))

    for density in (0.5, 2.0):
        closed_quality.parm("adaptive_detail_density").set(density)
        result = validate_adaptive_limits(
            closed_quality, "closed_quality_density_%s" % density
        )
        if result:
            return result
        closed_density_geo = road_output(closed_quality).geometry()
        result = validate_geometry(
            closed_density_geo, "closed_quality_density_%s" % density
        )
        if result:
            return result
        if closed_density_geo.intAttribValue("road_frame_flip_count") != 0:
            return fail("closed_quality_density_frame_flip_%s" % density)
        if abs(closed_density_geo.floatAttribValue("road_seam_position_error")) > 1e-3:
            return fail("closed_quality_density_seam_error_%s" % density)
    closed_quality.parm("adaptive_detail_density").set(1.0)

    material_open = obj.createNode(ASSET_TYPE, "VERIFY_track_material_open")
    material_open.parm("unity_curve_input").set(straight_source.path())
    material_open.parm("material_segments").set(2)
    material_open.parm("material_segment_start_1").set(0.2)
    material_open.parm("material_segment_end_1").set(0.8)
    material_open.parm("material_segment_layer_1").set(0)
    material_open.parm("material_segment_start_blend_distance_m_1").set(3.0)
    material_open.parm("material_segment_end_blend_distance_m_1").set(3.0)
    material_open.parm("material_segment_start_2").set(0.4)
    material_open.parm("material_segment_end_2").set(0.6)
    material_open.parm("material_segment_layer_2").set(1)
    material_open.parm("material_segment_start_blend_distance_m_2").set(3.0)
    material_open.parm("material_segment_end_blend_distance_m_2").set(3.0)
    material_open_geo = road_output(material_open).geometry()
    middle = min(material_open_geo.points(), key=lambda point: abs(point.attribValue("road_t") - 0.5))
    middle_color = middle.attribValue("Cd")
    if middle_color[0] > 1e-3 or middle_color[1] < 0.999:
        return fail("material_later_segment_not_overriding_%s" % (middle_color,))
    if max(sum(point.attribValue("Cd")[:3]) for point in material_open_geo.points()) > 1.0001:
        return fail("material_mask_not_normalized")
    if material_open_geo.intAttribValue("road_material_anchor_count") < 10:
        return fail("material_transition_anchors_missing")

    material_anchor_sets = {}
    for density in (0.25, 1.0, 2.0):
        material_open.parm("adaptive_detail_density").set(density)
        material_centerline = centerline_output(material_open).geometry()
        material_anchor_sets[density] = {
            round(point.attribValue("road_distance"), 4)
            for point in material_centerline.points()
            if point.attribValue("road_force_priority") > 0
        }
        result = validate_adaptive_limits(
            material_open, "adaptive_density_material_%s" % density
        )
        if result:
            return result
    if not (
        material_anchor_sets[0.25] == material_anchor_sets[1.0] ==
        material_anchor_sets[2.0]
    ):
        return fail("adaptive_density_changed_material_anchors_%s" % material_anchor_sets)
    material_open.parm("adaptive_detail_density").set(1.0)

    material_invalid = obj.createNode(ASSET_TYPE, "VERIFY_track_material_invalid")
    material_invalid.parm("unity_curve_input").set(straight_source.path())
    material_invalid.parm("material_segments").set(1)
    material_invalid.parm("material_segment_start_1").set(0.8)
    material_invalid.parm("material_segment_end_1").set(0.2)
    invalid_geo = road_output(material_invalid).geometry()
    if invalid_geo.intAttribValue("road_segment_invalid_count") != 1:
        return fail("material_open_invalid_not_reported")
    if max(sum(point.attribValue("Cd")[:3]) for point in invalid_geo.points()) > 1e-4:
        return fail("material_open_invalid_applied")

    material_closed = obj.createNode(ASSET_TYPE, "VERIFY_track_material_closed")
    material_closed.parm("unity_curve_input").set(closed_quality_source.path())
    material_closed.parm("material_segments").set(1)
    material_closed.parm("material_segment_start_1").set(0.8)
    material_closed.parm("material_segment_end_1").set(0.2)
    material_closed.parm("material_segment_layer_1").set(0)
    material_closed.parm("material_segment_start_blend_distance_m_1").set(3.0)
    material_closed.parm("material_segment_end_blend_distance_m_1").set(3.0)
    material_closed_geo = road_output(material_closed).geometry()
    seam_point = min(material_closed_geo.points(), key=lambda point: point.attribValue("road_t"))
    middle_point = min(material_closed_geo.points(), key=lambda point: abs(point.attribValue("road_t") - 0.5))
    if seam_point.attribValue("Cd")[0] < 0.99 or middle_point.attribValue("Cd")[0] > 1e-3:
        return fail("material_closed_wrap_semantics")

    split_asset = obj.createNode(ASSET_TYPE, "VERIFY_track_split_outputs")
    split_asset.parm("unity_curve_input").set(closed_quality_source.path())
    result = validate_split_outputs(split_asset, "split_outputs")
    if result:
        return result

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
    if stress_geo.floatAttribValue("road_max_ring_turn_angle_deg") > 15.0 + 1e-3:
        return fail("stress_turn_angle_%f" % stress_geo.floatAttribValue("road_max_ring_turn_angle_deg"))
    hairpin_source = make_hairpin_curve(obj)
    hairpin = obj.createNode(ASSET_TYPE, "VERIFY_track_wide_hairpin")
    hairpin.parm("unity_curve_input").set(hairpin_source.path())
    # Keep the wide-hairpin case as a centerline/UV/banking regression test.
    hairpin.parm("road_width").set(28.0)
    hairpin.parm("sample_spacing").set(1.5)
    hairpin_geo = road_output(hairpin).geometry()
    result = validate_geometry(hairpin_geo, "wide_hairpin")
    if result:
        return result
    if abs(hairpin_geo.floatAttribValue("road_generated_length") - hairpin_geo.floatAttribValue("road_length")) > 1e-5:
        return fail("wide_hairpin_generated_length_changed")
    if abs(hairpin_geo.floatAttribValue("road_generated_min_turn_radius") - hairpin_geo.floatAttribValue("road_min_turn_radius")) > 1e-5:
        return fail("wide_hairpin_generated_radius_changed")
    original_center = hairpin_geo.findPointAttrib("road_original_center")
    generated_center = hairpin_geo.findPointAttrib("road_generated_center")
    if original_center is None or generated_center is None:
        return fail("wide_hairpin_missing_centerline_contract")
    for point in hairpin_geo.points():
        delta = hou.Vector3(point.attribValue(generated_center)) - hou.Vector3(point.attribValue(original_center))
        if delta.length() > 1e-5:
            return fail("wide_hairpin_centerline_shift_%d_%f" % (point.number(), delta.length()))
    if hairpin_geo.stringAttribValue("road_surface_uv_mode") != "arc_length_lateral_metric":
        return fail("wide_hairpin_wrong_uv_mode")

    grade_source = make_grade_curve(obj)
    grade = obj.createNode(ASSET_TYPE, "VERIFY_track_grade")
    grade.parm("unity_curve_input").set(grade_source.path())
    grade.parm("road_width").set(6.0)
    grade.parm("sample_spacing").set(2.0)
    grade.parm("enable_track_lateral_tilt").set(1)
    grade.parm("lateral_tilt_auto_strength").set(0.0)
    grade.parm("lateral_tilt_transition_length_m").set(24.0)
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
    spline_roll.parm("enable_track_lateral_tilt").set(1)
    spline_roll.parm("lateral_tilt_use_spline_knot_tilt").set(1)
    spline_roll.parm("lateral_tilt_auto_strength").set(0.0)
    spline_roll.parm("lateral_tilt_max_angle_deg").set(8.0)
    spline_roll.parm("lateral_tilt_transition_length_m").set(0.0)
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

    spline_roll.parm("lateral_tilt_use_spline_knot_tilt").set(0)
    spline_roll_disabled_geo = road_output(spline_roll).geometry()
    if spline_roll_disabled_geo.floatAttribValue("road_max_abs_bank_deg") > 1e-4:
        return fail("disabled_spline_roll_still_applied")

    arc_source = make_arc_curve(obj)
    arc = obj.createNode(ASSET_TYPE, "VERIFY_track_constant_radius_bank")
    arc.parm("unity_curve_input").set(arc_source.path())
    arc.parm("road_width").set(6.0)
    arc.parm("sample_spacing").set(1.5)
    arc.parm("enable_track_lateral_tilt").set(1)
    arc.parm("lateral_tilt_design_speed_kph").set(20.0)
    arc.parm("lateral_tilt_auto_strength").set(1.0)
    arc.parm("lateral_tilt_max_angle_deg").set(8.0)
    arc.parm("lateral_tilt_transition_length_m").set(0.0)
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

    bank_stress = obj.createNode(ASSET_TYPE, "VERIFY_track_bank_s_curve")
    bank_stress.parm("unity_curve_input").set(source.path())
    bank_stress.parm("road_width").set(6.0)
    bank_stress.parm("sample_spacing").set(1.5)
    bank_stress.parm("enable_track_lateral_tilt").set(1)
    bank_stress.parm("lateral_tilt_design_speed_kph").set(25.0)
    bank_stress.parm("lateral_tilt_auto_strength").set(1.0)
    bank_stress.parm("lateral_tilt_max_angle_deg").set(8.0)
    bank_stress.parm("lateral_tilt_transition_length_m").set(24.0)
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

    density_bank_source = make_bank_transition_curve(obj)
    density_bank = obj.createNode(ASSET_TYPE, "VERIFY_track_density_bank")
    density_bank.parm("unity_curve_input").set(density_bank_source.path())
    density_bank.parm("road_width").set(6.0)
    density_bank.parm("sample_spacing").set(32.0)
    density_bank.parm("adaptive_min_spacing_m").set(0.25)
    density_bank.parm("adaptive_max_chord_error_m").set(0.5)
    density_bank.parm("adaptive_max_heading_delta_deg").set(15.0)
    density_bank.parm("adaptive_max_grade_delta_deg").set(10.0)
    density_bank.parm("adaptive_max_lateral_tilt_delta_deg").set(1.0)
    density_bank.parm("enable_track_lateral_tilt").set(1)
    density_bank.parm("lateral_tilt_use_spline_knot_tilt").set(1)
    density_bank.parm("lateral_tilt_auto_strength").set(0.0)
    density_bank.parm("lateral_tilt_max_angle_deg").set(8.0)
    density_bank.parm("lateral_tilt_transition_length_m").set(0.0)
    bank_density_counts = {}
    for density in (0.5, 1.0, 2.0):
        density_bank.parm("adaptive_detail_density").set(density)
        density_geo = centerline_output(density_bank).geometry()
        bank_density_counts[density] = len(density_geo.points())
        result = validate_adaptive_limits(
            density_bank, "adaptive_density_bank_%s" % density
        )
        if result:
            return result
    if not (
        bank_density_counts[0.5] < bank_density_counts[1.0] <
        bank_density_counts[2.0]
    ):
        return fail("adaptive_density_bank_not_monotonic_%s" % bank_density_counts)

    circle_source = make_closed_circle(obj)
    circle = obj.createNode(ASSET_TYPE, "VERIFY_track_closed_bank")
    circle.parm("unity_curve_input").set(circle_source.path())
    circle.parm("road_width").set(6.0)
    circle.parm("sample_spacing").set(2.0)
    circle.parm("enable_track_lateral_tilt").set(1)
    circle.parm("lateral_tilt_design_speed_kph").set(20.0)
    circle.parm("lateral_tilt_auto_strength").set(1.0)
    circle.parm("lateral_tilt_max_angle_deg").set(8.0)
    circle.parm("lateral_tilt_transition_length_m").set(24.0)
    circle_geo = road_output(circle).geometry()
    result = validate_geometry(circle_geo, "closed_bank")
    if result:
        return result
    if circle_geo.intAttribValue("road_closed_loop") != 1:
        return fail("closed_bank_not_closed")
    result = validate_bank_rate(circle_geo, "closed_bank", 8.0, 24.0)
    if result:
        return result

    circle.parm("road_width").set(20.0)
    circle.parm("enable_shoulders").set(1)
    circle.parm("shoulder_width").set(2.0)
    circle.parm("shoulder_drop").set(0.12)
    result = validate_profile_contract(circle, "closed_wide_profile")
    if result:
        return result
    circle.parm("road_width_ramp").set(hou.Ramp(
        (hou.rampBasis.Linear, hou.rampBasis.Linear, hou.rampBasis.Linear),
        (0.0, 0.5, 1.0),
        (1.0, 0.5, 1.0),
    ))
    result = validate_width_ramp_contract(circle, "closed_width_ramp")
    if result:
        return result
    closed_layout = circle.node("Road/SURFACE_reproject_layout").geometry()
    cross_section_count = closed_layout.intAttribValue("road_cross_section_count")
    widths = [
        closed_layout.points()[ring * cross_section_count].attribValue("road_width_m")
        for ring in range(closed_layout.intAttribValue("road_sample_count"))
    ]
    seam_delta = abs(widths[-1] - widths[0])
    interior_delta = max(
        abs(widths[index] - widths[index - 1]) for index in range(1, len(widths))
    )
    if seam_delta > interior_delta + 1e-4:
        return fail("closed_width_ramp_seam_%f_over_%f" % (seam_delta, interior_delta))

    print("VERIFY_OK=1")
    return 0


if __name__ == "__main__":
    sys.exit(main())
