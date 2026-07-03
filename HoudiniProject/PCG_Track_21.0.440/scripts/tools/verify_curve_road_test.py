import os
import sys

import hou


SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
HOUDINI_DIR = os.path.abspath(os.path.join(SCRIPT_DIR, "..", ".."))
PROJECT_ROOT = os.path.abspath(os.path.join(HOUDINI_DIR, "..", ".."))
HDA_PATH = os.path.join(PROJECT_ROOT, "Assets", "Generated", "Road", "CurveRoadSurface_Test.hda")
ASSET_TYPE = "pcgbike::curve_road_surface_test::1.1"


def fail(message):
    print("VERIFY_FAIL=%s" % message)
    return 1


def validate_road_uv(geo, label):
    uv_attrib = geo.findVertexAttrib("uv")
    if uv_attrib is None:
        return fail("%s_missing_vertex_uv" % label)

    all_v = []
    previous_min_v = None
    for prim_index, prim in enumerate(geo.prims()):
        vertices = prim.vertices()
        if len(vertices) != 4:
            return fail("%s_prim_%d_expected_quad" % (label, prim_index))

        values = [vertex.attribValue(uv_attrib) for vertex in vertices]
        u_values = [value[0] for value in values]
        v_values = [value[1] for value in values]
        all_v.extend(v_values)

        min_u = min(u_values)
        max_u = max(u_values)
        if abs(min_u) > 1e-4 or abs(max_u - 1.0) > 1e-4:
            return fail("%s_prim_%d_u_not_width_0_1_%s" % (label, prim_index, u_values))

        min_v = min(v_values)
        if previous_min_v is not None and min_v + 1e-4 < previous_min_v:
            return fail("%s_prim_%d_v_not_monotonic" % (label, prim_index))
        previous_min_v = min_v

    if not all_v:
        return fail("%s_no_uv_values" % label)
    if abs(min(all_v)) > 1e-4:
        return fail("%s_v_does_not_start_at_zero_%f" % (label, min(all_v)))
    if max(all_v) <= 1.0:
        return fail("%s_v_does_not_tile_above_one_%f" % (label, max(all_v)))

    print("%s_uv_min_v=%.6f %s_uv_max_v=%.6f" % (label, min(all_v), label, max(all_v)))
    return 0


def get_layer_samples(geo, label):
    cd_attrib = geo.findPointAttrib("Cd")
    road_t_attrib = geo.findPointAttrib("road_t")
    if cd_attrib is None:
        return fail("%s_missing_point_Cd" % label), []
    if cd_attrib.size() != 4:
        return fail("%s_point_Cd_not_rgba_size_%d" % (label, cd_attrib.size())), []
    if road_t_attrib is None:
        return fail("%s_missing_point_road_t" % label), []

    samples = []
    for point in geo.points():
        color = point.attribValue(cd_attrib)
        road_t = point.attribValue(road_t_attrib)
        if len(color) != 4:
            return fail("%s_point_Cd_value_not_rgba" % label), []
        if road_t < -1e-4 or road_t > 1.0001:
            return fail("%s_road_t_out_of_range_%f" % (label, road_t)), []
        if min(color) < -1e-4 or max(color) > 1.0001:
            return fail("%s_Cd_channel_out_of_range_%s" % (label, color)), []
        color_sum = sum(color)
        if abs(color_sum - 1.0) > 1e-3:
            return fail("%s_Cd_not_normalized_%s_sum_%f" % (label, color, color_sum)), []
        samples.append((road_t, color))

    if not samples:
        return fail("%s_no_layer_samples" % label), []

    print("%s_layer_sample_count=%d" % (label, len(samples)))
    return 0, samples


def validate_default_road_layer(geo, label):
    result, samples = get_layer_samples(geo, label)
    if result:
        return result

    for road_t, color in samples:
        if abs(color[0] - 1.0) > 1e-4 or abs(color[1]) > 1e-4 or abs(color[2]) > 1e-4 or abs(color[3]) > 1e-4:
            return fail("%s_default_layer_not_asphalt_at_%.4f_%s" % (label, road_t, color))

    return 0


def strongest_channel_near(samples, target_t, channel, radius):
    best = None
    for road_t, color in samples:
        if abs(road_t - target_t) <= radius:
            if best is None or color[channel] > best[1][channel]:
                best = (road_t, color)
    return best


def validate_segmented_road_layers(node, label):
    required_parms = [
        "default_layer",
        "segment_blend_width",
        "material_segments",
    ]
    for parm_name in required_parms:
        if node.parm(parm_name) is None:
            return fail("%s_missing_segment_param_%s" % (label, parm_name))

    node.parm("default_layer").set(0)
    node.parm("segment_blend_width").set(0.015)
    node.parm("material_segments").set(2)

    child_parms = [
        "material_segment_start_1",
        "material_segment_end_1",
        "material_segment_layer_1",
        "material_segment_start_2",
        "material_segment_end_2",
        "material_segment_layer_2",
    ]
    for parm_name in child_parms:
        if node.parm(parm_name) is None:
            return fail("%s_missing_segment_param_%s" % (label, parm_name))

    node.parm("material_segment_start_1").set(0.25)
    node.parm("material_segment_end_1").set(0.29)
    node.parm("material_segment_layer_1").set(1)
    node.parm("material_segment_start_2").set(0.42)
    node.parm("material_segment_end_2").set(0.50)
    node.parm("material_segment_layer_2").set(2)

    sop = node.displayNode()
    sop.cook(force=True)
    geo = sop.geometry()
    result, samples = get_layer_samples(geo, label)
    if result:
        return result

    asphalt = strongest_channel_near(samples, 0.10, 0, 0.035)
    gravel = strongest_channel_near(samples, 0.27, 1, 0.02)
    mud = strongest_channel_near(samples, 0.46, 2, 0.03)
    transition = strongest_channel_near(samples, 0.25, 1, 0.006)

    if asphalt is None or asphalt[1][0] < 0.95:
        return fail("%s_expected_asphalt_near_0_10_%s" % (label, asphalt))
    if gravel is None or gravel[1][1] < 0.95:
        return fail("%s_expected_gravel_near_0_27_%s" % (label, gravel))
    if mud is None or mud[1][2] < 0.95:
        return fail("%s_expected_mud_near_0_46_%s" % (label, mud))
    if transition is None or transition[1][0] <= 0.05 or transition[1][1] <= 0.05:
        return fail("%s_expected_mixed_transition_near_0_25_%s" % (label, transition))

    print("%s_asphalt_sample=(%.4f,%s)" % (label, asphalt[0], asphalt[1]))
    print("%s_gravel_sample=(%.4f,%s)" % (label, gravel[0], gravel[1]))
    print("%s_mud_sample=(%.4f,%s)" % (label, mud[0], mud[1]))
    print("%s_transition_sample=(%.4f,%s)" % (label, transition[0], transition[1]))
    return 0


def validate_start_prefab_instance(node, label):
    start_prefab = node.parm("start_prefab")
    if start_prefab is None:
        return fail("%s_missing_start_prefab_param" % label)

    start_output = node.node("OUT_START_PREFAB_INSTANCE")
    if start_output is None:
        return fail("%s_missing_start_instance_output" % label)

    start_output.cook(force=True)
    empty_geo = start_output.geometry()
    if len(empty_geo.points()) != 0 or len(empty_geo.prims()) != 0:
        return fail("%s_empty_prefab_should_not_emit_instance" % label)

    expected_path = "Assets/Generated/Road/TestStart.prefab"
    start_prefab.set(expected_path)
    start_output.cook(force=True)
    geo = start_output.geometry()
    print("%s_start_instance_points=%d %s_start_instance_prims=%d" % (label, len(geo.points()), label, len(geo.prims())))

    if len(geo.points()) != 1:
        return fail("%s_expected_one_start_instance_point" % label)
    if len(geo.prims()) != 0:
        return fail("%s_start_instance_should_not_emit_prims" % label)

    point = geo.points()[0]
    instance_attr = geo.findPointAttrib("unity_instance")
    if instance_attr is None:
        return fail("%s_missing_unity_instance_attr" % label)
    if point.attribValue(instance_attr) != expected_path:
        return fail("%s_unity_instance_path_mismatch_%s" % (label, point.attribValue(instance_attr)))

    prefix_attr = geo.findPointAttrib("instance_prefix")
    if prefix_attr is None or point.attribValue(prefix_attr) != "RaceStart":
        return fail("%s_missing_instance_prefix" % label)

    n_attr = geo.findPointAttrib("N")
    up_attr = geo.findPointAttrib("up")
    orient_attr = geo.findPointAttrib("orient")
    if n_attr is None or up_attr is None or orient_attr is None:
        return fail("%s_missing_orientation_attrs" % label)

    pos = tuple(point.position())
    n_value = point.attribValue(n_attr)
    up_value = point.attribValue(up_attr)
    orient_value = point.attribValue(orient_attr)
    print("%s_start_pos=(%.4f,%.4f,%.4f)" % (label, pos[0], pos[1], pos[2]))
    print("%s_start_N=(%.4f,%.4f,%.4f)" % (label, n_value[0], n_value[1], n_value[2]))
    print("%s_start_orient=(%.4f,%.4f,%.4f,%.4f)" % (label, orient_value[0], orient_value[1], orient_value[2], orient_value[3]))

    if abs(pos[0]) > 1e-3 or abs(pos[1]) > 1e-3 or abs(pos[2]) > 1e-3:
        return fail("%s_start_position_not_curve_start_%s" % (label, pos))
    if n_value[0] < 0.9 or abs(n_value[1]) > 1e-3:
        return fail("%s_start_direction_not_curve_forward_%s" % (label, n_value))
    if abs(up_value[0]) > 1e-4 or abs(up_value[1] - 1.0) > 1e-4 or abs(up_value[2]) > 1e-4:
        return fail("%s_start_up_not_world_y_%s" % (label, up_value))

    return 0


def dump_messages(node):
    errors = node.errors()
    warnings = node.warnings()
    if errors:
        print("%s ERRORS:" % node.path())
        for error in errors:
            print("  %s" % error)
    if warnings:
        print("%s WARNINGS:" % node.path())
        for warning in warnings:
            print("  %s" % warning)


def main():
    hou.hda.installFile(HDA_PATH)

    obj = hou.node("/obj")
    node = obj.createNode(ASSET_TYPE, "VERIFY_curve_road_surface_test")

    print("asset_type=%s" % node.type().name())
    print("asset_parms=%s" % ",".join(parm.name() for parm in node.parms()))
    dump_messages(node)

    for child in node.children():
        print("child=%s type=%s" % (child.path(), child.type().name()))
        try:
            child.cook(force=True)
        except Exception as exc:
            print("cook_exception=%s" % exc)
        dump_messages(child)

    sop = node.displayNode()
    if sop is None:
        print("display_sop=<none>")
        return 1

    print("display_sop=%s" % sop.path())
    try:
        sop.cook(force=True)
    except Exception as exc:
        print("display_cook_exception=%s" % exc)
        dump_messages(sop)
        return 1

    geo = sop.geometry()
    print("fallback_points=%d fallback_prims=%d" % (len(geo.points()), len(geo.prims())))
    print("fallback_source=%s" % geo.stringAttribValue("road_source"))
    print("has_point_uv=%s" % bool(geo.findPointAttrib("uv")))
    print("has_vertex_uv=%s" % bool(geo.findVertexAttrib("uv")))
    print("has_material_path=%s" % bool(geo.findPrimAttrib("shop_materialpath")))
    uv_result = validate_road_uv(geo, "fallback")
    if uv_result:
        return uv_result
    layer_result = validate_default_road_layer(geo, "fallback")
    if layer_result:
        return layer_result
    parm = node.parm("unity_curve_input")
    template = parm.parmTemplate() if parm else None
    print("unity_curve_input_exists=%s" % bool(parm))
    print("unity_curve_input_string_type=%s" % (template.stringType() if template else "<none>"))

    source = obj.createNode("geo", "VERIFY_unity_curve_input")
    for child in source.children():
        child.destroy()

    make_curve = source.createNode("python", "MAKE_INPUT_CURVE")
    make_curve.parm("python").set(
        """
geo = hou.pwd().geometry()
geo.clear()
pts = []
for pos in [(0, 0, 0), (5, 0, 0), (10, 0, 4), (15, 0, 4)]:
    p = geo.createPoint()
    p.setPosition(hou.Vector3(pos))
    pts.append(p)
poly = geo.createPolygon()
poly.setIsClosed(False)
for p in pts:
    poly.addVertex(p)
"""
    )
    make_curve.setDisplayFlag(True)
    make_curve.setRenderFlag(True)

    param_input_node = obj.createNode(ASSET_TYPE, "VERIFY_curve_road_surface_with_param_input")
    param_input_node.parm("unity_curve_input").set(source.path())
    param_input_node.parm("sample_spacing").set(2.0)
    param_input_node.parm("road_width").set(4.0)

    param_input_sop = param_input_node.displayNode()
    param_input_sop.cook(force=True)
    param_input_geo = param_input_sop.geometry()
    print("param_input_points=%d param_input_prims=%d" % (len(param_input_geo.points()), len(param_input_geo.prims())))
    print("param_input_source=%s" % param_input_geo.stringAttribValue("road_source"))
    print("param_input_bounds=%s" % param_input_geo.boundingBox())
    uv_result = validate_road_uv(param_input_geo, "param_input")
    if uv_result:
        return uv_result
    layer_result = validate_default_road_layer(param_input_geo, "param_input_default")
    if layer_result:
        return layer_result
    segment_result = validate_segmented_road_layers(param_input_node, "param_input_segments")
    if segment_result:
        return segment_result
    start_result = validate_start_prefab_instance(param_input_node, "param_input")
    if start_result:
        return start_result

    object_input_node = obj.createNode(ASSET_TYPE, "VERIFY_curve_road_surface_with_object_input")
    object_input_node.setInput(0, source)
    object_input_node.parm("sample_spacing").set(2.0)
    object_input_node.parm("road_width").set(4.0)

    object_input_sop = object_input_node.displayNode()
    object_input_sop.cook(force=True)
    object_input_geo = object_input_sop.geometry()
    print("object_input_points=%d object_input_prims=%d" % (len(object_input_geo.points()), len(object_input_geo.prims())))
    print("object_input_source=%s" % object_input_geo.stringAttribValue("road_source"))
    print("object_input_bounds=%s" % object_input_geo.boundingBox())
    uv_result = validate_road_uv(object_input_geo, "object_input")
    if uv_result:
        return uv_result
    return 0


if __name__ == "__main__":
    sys.exit(main())
