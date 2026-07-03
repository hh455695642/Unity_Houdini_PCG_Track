import os
import math
import shutil

import hou


SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
HOUDINI_DIR = os.path.abspath(os.path.join(SCRIPT_DIR, "..", ".."))
PROJECT_ROOT = os.path.abspath(os.path.join(HOUDINI_DIR, "..", ".."))
UNITY_ROAD_DIR = os.path.join(PROJECT_ROOT, "Assets", "Generated", "Road")

HIP_PATH = os.path.join(HOUDINI_DIR, "PCG_Bike_Unity_road_curve_test.hip")
OBJ_PATH = os.path.join(UNITY_ROAD_DIR, "CurveRoadSurface_Test.obj")
HDA_PATH = os.path.join(UNITY_ROAD_DIR, "CurveRoadSurface_Test.hda")
HDA_BACKUP_DIR = os.path.join(UNITY_ROAD_DIR, "backup")

ROAD_NODE_NAME = "ROAD_CurveSurface_Test"
ROAD_ASSET_TYPE = "pcgbike::curve_road_surface_test::1.1"

DEFAULT_POINTS = [
    (-18.0, 0.0, -14.0),
    (-9.0, 0.0, -4.0),
    (-1.0, 0.4, 2.0),
    (8.0, 0.2, 6.5),
    (15.0, 0.0, 1.5),
    (22.0, 0.0, -8.0),
]


LAYER_MENU_ITEMS = ("0", "1", "2", "3")
LAYER_MENU_LABELS = ("Asphalt / R", "Gravel / G", "Mud / B", "Dirt / A")


PYTHON_SOP_CODE = r'''
import math
import hou


def vadd(a, b):
    return (a[0] + b[0], a[1] + b[1], a[2] + b[2])


def vsub(a, b):
    return (a[0] - b[0], a[1] - b[1], a[2] - b[2])


def vmul(a, s):
    return (a[0] * s, a[1] * s, a[2] * s)


def vlen(a):
    return math.sqrt(a[0] * a[0] + a[1] * a[1] + a[2] * a[2])


def vnorm(a, fallback=(0.0, 0.0, 1.0)):
    length = vlen(a)
    if length < 1e-5:
        return fallback
    return (a[0] / length, a[1] / length, a[2] / length)


def clamp(value, min_value, max_value):
    return max(min_value, min(max_value, value))


def smoothstep(edge0, edge1, value):
    if abs(edge1 - edge0) < 1e-6:
        return 1.0 if value >= edge1 else 0.0
    t = clamp((value - edge0) / (edge1 - edge0), 0.0, 1.0)
    return t * t * (3.0 - 2.0 * t)


def catmull_rom(p0, p1, p2, p3, t):
    t2 = t * t
    t3 = t2 * t
    return (
        0.5 * ((2.0 * p1[0]) + (-p0[0] + p2[0]) * t + (2.0 * p0[0] - 5.0 * p1[0] + 4.0 * p2[0] - p3[0]) * t2 + (-p0[0] + 3.0 * p1[0] - 3.0 * p2[0] + p3[0]) * t3),
        0.5 * ((2.0 * p1[1]) + (-p0[1] + p2[1]) * t + (2.0 * p0[1] - 5.0 * p1[1] + 4.0 * p2[1] - p3[1]) * t2 + (-p0[1] + 3.0 * p1[1] - 3.0 * p2[1] + p3[1]) * t3),
        0.5 * ((2.0 * p1[2]) + (-p0[2] + p2[2]) * t + (2.0 * p0[2] - 5.0 * p1[2] + 4.0 * p2[2] - p3[2]) * t2 + (-p0[2] + 3.0 * p1[2] - 3.0 * p2[2] + p3[2]) * t3),
    )


def sample_centerline(points, spacing):
    # Performance key: cook-time only; runtime must use baked Unity mesh data.
    samples = []
    for i in range(len(points) - 1):
        p0 = points[max(i - 1, 0)]
        p1 = points[i]
        p2 = points[i + 1]
        p3 = points[min(i + 2, len(points) - 1)]
        segment_len = vlen(vsub(p2, p1))
        steps = max(2, int(math.ceil(segment_len / max(spacing, 0.1))))
        for step in range(steps):
            if i > 0 and step == 0:
                continue
            samples.append(catmull_rom(p0, p1, p2, p3, float(step) / float(steps)))
    samples.append(points[-1])
    return samples


def dedupe_points(points):
    deduped = []
    for point in points:
        if not deduped or vlen(vsub(point, deduped[-1])) > 1e-4:
            deduped.append(point)
    return deduped


def build_distance_along(points):
    distances = [0.0]
    for i in range(1, len(points)):
        distances.append(distances[-1] + vlen(vsub(points[i], points[i - 1])))
    return distances


def interpolate_at_distance(points, distances, target_distance):
    if not points:
        return (0.0, 0.0, 0.0)
    if target_distance <= 0.0:
        return points[0]
    if target_distance >= distances[-1]:
        return points[-1]

    for i in range(1, len(points)):
        if distances[i] >= target_distance:
            span = max(distances[i] - distances[i - 1], 1e-6)
            t = (target_distance - distances[i - 1]) / span
            return vadd(points[i - 1], vmul(vsub(points[i], points[i - 1]), t))

    return points[-1]


def read_material_segments(asset):
    segments = []
    count_parm = asset.parm("material_segments")
    count = int(count_parm.eval()) if count_parm is not None else 0

    for index in range(1, count + 1):
        start_parm = asset.parm("material_segment_start_%d" % index)
        end_parm = asset.parm("material_segment_end_%d" % index)
        layer_parm = asset.parm("material_segment_layer_%d" % index)
        if start_parm is None or end_parm is None or layer_parm is None:
            continue

        start = clamp(float(start_parm.eval()), 0.0, 1.0)
        end = clamp(float(end_parm.eval()), 0.0, 1.0)
        if end < start:
            start, end = end, start
        if end - start < 1e-5:
            continue

        layer = int(clamp(int(layer_parm.eval()), 0, 3))
        segments.append((start, end, layer))

    return segments


def collect_segment_sample_ts(segments, blend_width):
    sample_ts = set([0.0, 1.0])
    for start, end, _layer in segments:
        sample_ts.add(clamp(start, 0.0, 1.0))
        sample_ts.add(clamp(end, 0.0, 1.0))
        sample_ts.add(clamp((start + end) * 0.5, 0.0, 1.0))
        if blend_width > 1e-5:
            sample_ts.add(clamp(start - blend_width, 0.0, 1.0))
            sample_ts.add(clamp(start + blend_width, 0.0, 1.0))
            sample_ts.add(clamp(end - blend_width, 0.0, 1.0))
            sample_ts.add(clamp(end + blend_width, 0.0, 1.0))
    return sorted(sample_ts)


def insert_centerline_samples(centerline, sample_ts):
    if len(centerline) < 2:
        return centerline

    distances = build_distance_along(centerline)
    total_length = distances[-1]
    if total_length < 1e-5:
        return centerline

    keyed = [(distances[i], centerline[i]) for i in range(len(centerline))]
    for road_t in sample_ts:
        target_distance = clamp(road_t, 0.0, 1.0) * total_length
        if any(abs(existing_distance - target_distance) < 1e-4 for existing_distance, _point in keyed):
            continue
        keyed.append((target_distance, interpolate_at_distance(centerline, distances, target_distance)))

    keyed.sort(key=lambda item: item[0])
    result = []
    last_distance = None
    for distance, point in keyed:
        if last_distance is None or abs(distance - last_distance) > 1e-4:
            result.append(point)
            last_distance = distance

    return result


def segment_weight_at(road_t, start, end, blend_width):
    if blend_width <= 1e-5:
        return 1.0 if start <= road_t <= end else 0.0
    return smoothstep(start - blend_width, start + blend_width, road_t) * (1.0 - smoothstep(end - blend_width, end + blend_width, road_t))


def one_hot_layer(layer_index):
    weights = [0.0, 0.0, 0.0, 0.0]
    weights[int(clamp(layer_index, 0, 3))] = 1.0
    return weights


def normalize_weights(weights):
    total = sum(weights)
    if total < 1e-5:
        return (1.0, 0.0, 0.0, 0.0)
    return tuple(clamp(weight / total, 0.0, 1.0) for weight in weights)


def material_weights_at(road_t, default_layer, segments, blend_width):
    weights = one_hot_layer(default_layer)
    for start, end, layer in segments:
        blend = segment_weight_at(road_t, start, end, blend_width)
        if blend <= 0.0:
            continue
        keep = 1.0 - blend
        for channel in range(4):
            weights[channel] *= keep
        weights[layer] += blend
    return normalize_weights(weights)


def read_input_curve_points(node):
    if len(node.inputs()) < 1 or node.inputs()[0] is None:
        return []

    input_geo = node.inputs()[0].geometry()
    if input_geo is None or len(input_geo.points()) < 2:
        return []

    # Prefer primitive vertex order so the road follows the authored curve direction.
    for prim in input_geo.prims():
        vertices = prim.vertices()
        if len(vertices) >= 2:
            return dedupe_points([tuple(vertex.point().position()) for vertex in vertices])

    return dedupe_points([tuple(point.position()) for point in input_geo.points()])


node = hou.pwd()
geo = node.geometry()
geo.clear()

asset = node.parent()
width = max(asset.evalParm("road_width"), 0.1)
spacing = max(asset.evalParm("sample_spacing"), 0.25)
uv_tile_length_param = asset.evalParm("uv_tile_length")
uv_tile_length = uv_tile_length_param if uv_tile_length_param > 1e-4 else width
reverse_curve = bool(asset.evalParm("reverse_curve"))
flip_surface = bool(asset.evalParm("flip_surface"))
default_layer = int(clamp(asset.evalParm("default_layer") if asset.parm("default_layer") else 0, 0, 3))
segment_blend_width = clamp(asset.evalParm("segment_blend_width") if asset.parm("segment_blend_width") else 0.015, 0.0, 0.5)
material_segments = read_material_segments(asset)

input_points = read_input_curve_points(node)
using_input_curve = len(input_points) >= 2
points = input_points if using_input_curve else [tuple(asset.evalParmTuple("curve_point_%d" % i)) for i in range(6)]
if reverse_curve:
    points = list(reversed(points))

centerline = sample_centerline(points, spacing)
centerline = insert_centerline_samples(centerline, collect_segment_sample_ts(material_segments, segment_blend_width))
half_width = width * 0.5
mesh_points = []
distance_along = build_distance_along(centerline)
road_length = max(distance_along[-1], 1e-5)
road_t_values = [distance / road_length for distance in distance_along]

uv_v = [distance / uv_tile_length for distance in distance_along]
uv_attr = geo.addAttrib(hou.attribType.Vertex, "uv", (0.0, 0.0, 0.0))
cd_attr = geo.addAttrib(hou.attribType.Point, "Cd", (1.0, 0.0, 0.0, 0.0))
road_t_attr = geo.addAttrib(hou.attribType.Point, "road_t", 0.0)

for i, center in enumerate(centerline):
    prev_p = centerline[max(i - 1, 0)]
    next_p = centerline[min(i + 1, len(centerline) - 1)]
    tangent = vnorm(vsub(next_p, prev_p))
    # Flat road lateral in XZ plane: stable and mobile-friendly for early testing.
    lateral = vnorm((tangent[2], 0.0, -tangent[0]), (1.0, 0.0, 0.0))

    left = vsub(center, vmul(lateral, half_width))
    right = vadd(center, vmul(lateral, half_width))

    p_left = geo.createPoint()
    p_left.setPosition(hou.Vector3(left))
    p_left.setAttribValue(cd_attr, material_weights_at(road_t_values[i], default_layer, material_segments, segment_blend_width))
    p_left.setAttribValue(road_t_attr, road_t_values[i])

    p_right = geo.createPoint()
    p_right.setPosition(hou.Vector3(right))
    p_right.setAttribValue(cd_attr, material_weights_at(road_t_values[i], default_layer, material_segments, segment_blend_width))
    p_right.setAttribValue(road_t_attr, road_t_values[i])

    mesh_points.append((p_left, p_right))

for i in range(len(mesh_points) - 1):
    # Unity/Houdini conversion mirrors X, which flips triangle handedness once.
    # Default flip_surface keeps the final Unity mesh front-facing from above.
    poly = geo.createPolygon()
    if flip_surface:
        vertices = [
            (poly.addVertex(mesh_points[i][0]), (0.0, uv_v[i], 0.0)),
            (poly.addVertex(mesh_points[i][1]), (1.0, uv_v[i], 0.0)),
            (poly.addVertex(mesh_points[i + 1][1]), (1.0, uv_v[i + 1], 0.0)),
            (poly.addVertex(mesh_points[i + 1][0]), (0.0, uv_v[i + 1], 0.0)),
        ]
    else:
        vertices = [
            (poly.addVertex(mesh_points[i][0]), (0.0, uv_v[i], 0.0)),
            (poly.addVertex(mesh_points[i + 1][0]), (0.0, uv_v[i + 1], 0.0)),
            (poly.addVertex(mesh_points[i + 1][1]), (1.0, uv_v[i + 1], 0.0)),
            (poly.addVertex(mesh_points[i][1]), (1.0, uv_v[i], 0.0)),
        ]

    for vertex, uv in vertices:
        vertex.setAttribValue(uv_attr, uv)

geo.addAttrib(hou.attribType.Global, "road_width", 0.0)
geo.setGlobalAttribValue("road_width", width)
geo.addAttrib(hou.attribType.Global, "road_sample_count", 0)
geo.setGlobalAttribValue("road_sample_count", len(centerline))
geo.addAttrib(hou.attribType.Global, "road_length", 0.0)
geo.setGlobalAttribValue("road_length", road_length)
geo.addAttrib(hou.attribType.Global, "road_uv_tile_length", 0.0)
geo.setGlobalAttribValue("road_uv_tile_length", uv_tile_length)
geo.addAttrib(hou.attribType.Global, "road_default_layer", 0)
geo.setGlobalAttribValue("road_default_layer", default_layer)
geo.addAttrib(hou.attribType.Global, "road_segment_count", 0)
geo.setGlobalAttribValue("road_segment_count", len(material_segments))
geo.addAttrib(hou.attribType.Global, "road_segment_blend_width", 0.0)
geo.setGlobalAttribValue("road_segment_blend_width", segment_blend_width)
geo.addAttrib(hou.attribType.Global, "road_source", "")
geo.setGlobalAttribValue("road_source", "unity_input_curve" if using_input_curve else "fallback_points")
'''


START_INSTANCE_SOP_CODE = r'''
import math
import hou


def vadd(a, b):
    return (a[0] + b[0], a[1] + b[1], a[2] + b[2])


def vsub(a, b):
    return (a[0] - b[0], a[1] - b[1], a[2] - b[2])


def vmul(a, s):
    return (a[0] * s, a[1] * s, a[2] * s)


def vlen(a):
    return math.sqrt(a[0] * a[0] + a[1] * a[1] + a[2] * a[2])


def vnorm(a, fallback=(0.0, 0.0, 1.0)):
    length = vlen(a)
    if length < 1e-5:
        return fallback
    return (a[0] / length, a[1] / length, a[2] / length)


def point_pos(point):
    pos = point.position()
    return (pos[0], pos[1], pos[2])


def midpoint(a, b):
    return vmul(vadd(a, b), 0.5)


def orient_from_forward(forward):
    # Houdini instancing convention: orient local +Z to the road forward.
    yaw = math.atan2(forward[0], forward[2])
    half_yaw = yaw * 0.5
    return (0.0, math.sin(half_yaw), 0.0, math.cos(half_yaw))


node = hou.pwd()
geo = node.geometry()
input_geo = node.inputs()[0].geometry() if len(node.inputs()) > 0 and node.inputs()[0] is not None else None

geo.clear()

asset = node.parent()
start_prefab = (asset.evalParm("start_prefab") or "").strip()

geo.addAttrib(hou.attribType.Global, "road_start_prefab", "")
geo.setGlobalAttribValue("road_start_prefab", start_prefab)

if start_prefab and input_geo is not None:
    input_points = input_geo.points()
    if len(input_points) >= 4:
        start = midpoint(point_pos(input_points[0]), point_pos(input_points[1]))
        next_pos = midpoint(point_pos(input_points[2]), point_pos(input_points[3]))
    elif len(input_points) >= 2:
        start = point_pos(input_points[0])
        next_pos = point_pos(input_points[1])
    else:
        start = None
        next_pos = None

    if start is not None and next_pos is not None:
        forward = vnorm(vsub(next_pos, start))

        point = geo.createPoint()
        point.setPosition(hou.Vector3(start))

        instance_attr = geo.addAttrib(hou.attribType.Point, "unity_instance", "")
        prefix_attr = geo.addAttrib(hou.attribType.Point, "instance_prefix", "")
        n_attr = geo.addAttrib(hou.attribType.Point, "N", (0.0, 0.0, 1.0))
        up_attr = geo.addAttrib(hou.attribType.Point, "up", (0.0, 1.0, 0.0))
        orient_attr = geo.addAttrib(hou.attribType.Point, "orient", (0.0, 0.0, 0.0, 1.0))
        pscale_attr = geo.addAttrib(hou.attribType.Point, "pscale", 1.0)

        point.setAttribValue(instance_attr, start_prefab)
        point.setAttribValue(prefix_attr, "RaceStart")
        point.setAttribValue(n_attr, forward)
        point.setAttribValue(up_attr, (0.0, 1.0, 0.0))
        point.setAttribValue(orient_attr, orient_from_forward(forward))
        point.setAttribValue(pscale_attr, 1.0)

        geo.addAttrib(hou.attribType.Global, "road_start_forward", (0.0, 0.0, 1.0))
        geo.setGlobalAttribValue("road_start_forward", forward)
'''


def ensure_dirs():
    os.makedirs(UNITY_ROAD_DIR, exist_ok=True)
    os.makedirs(HOUDINI_DIR, exist_ok=True)


def cleanup_hda_backup_dir():
    road_dir = os.path.abspath(UNITY_ROAD_DIR)
    backup_dir = os.path.abspath(HDA_BACKUP_DIR)
    if os.path.isdir(backup_dir) and os.path.commonpath([road_dir, backup_dir]) == road_dir:
        shutil.rmtree(backup_dir)


def append_road_parms(parm_group):
    road_folder = hou.FolderParmTemplate("road_settings", "Road")
    road_folder.addParmTemplate(
        hou.StringParmTemplate(
            "unity_curve_input",
            "Unity Curve Input",
            1,
            string_type=hou.stringParmType.NodeReference,
        )
    )
    road_folder.addParmTemplate(
        hou.StringParmTemplate(
            "start_prefab",
            "Start Prefab",
            1,
            default_value=("",),
            string_type=hou.stringParmType.FileReference,
        )
    )
    road_folder.addParmTemplate(hou.FloatParmTemplate("road_width", "Road Width", 1, default_value=(6.0,), min=0.5, max=20.0))
    road_folder.addParmTemplate(hou.FloatParmTemplate("sample_spacing", "Sample Spacing", 1, default_value=(1.5,), min=0.25, max=10.0))
    road_folder.addParmTemplate(
        hou.FloatParmTemplate(
            "uv_tile_length",
            "UV Tile Length (0 = Road Width)",
            1,
            default_value=(0.0,),
            min=0.0,
            max=50.0,
        )
    )
    road_folder.addParmTemplate(hou.ToggleParmTemplate("reverse_curve", "Reverse Curve Direction", default_value=False))
    road_folder.addParmTemplate(hou.ToggleParmTemplate("flip_surface", "Flip Surface For Unity", default_value=True))
    road_folder.addParmTemplate(
        hou.IntParmTemplate(
            "default_layer",
            "Default Layer",
            1,
            default_value=(0,),
            menu_items=LAYER_MENU_ITEMS,
            menu_labels=LAYER_MENU_LABELS,
        )
    )
    road_folder.addParmTemplate(
        hou.FloatParmTemplate(
            "segment_blend_width",
            "Segment Blend Width",
            1,
            default_value=(0.015,),
            min=0.0,
            max=0.25,
        )
    )

    segment_folder = hou.FolderParmTemplate(
        "material_segments",
        "Material Segments",
        folder_type=hou.folderType.MultiparmBlock,
    )
    segment_folder.addParmTemplate(
        hou.FloatParmTemplate(
            "material_segment_start_#",
            "Start 0-1",
            1,
            default_value=(0.0,),
            min=0.0,
            max=1.0,
        )
    )
    segment_folder.addParmTemplate(
        hou.FloatParmTemplate(
            "material_segment_end_#",
            "End 0-1",
            1,
            default_value=(1.0,),
            min=0.0,
            max=1.0,
        )
    )
    segment_folder.addParmTemplate(
        hou.IntParmTemplate(
            "material_segment_layer_#",
            "Layer",
            1,
            default_value=(1,),
            menu_items=LAYER_MENU_ITEMS,
            menu_labels=LAYER_MENU_LABELS,
        )
    )
    road_folder.addParmTemplate(segment_folder)

    fallback_folder = hou.FolderParmTemplate("fallback_points", "Fallback Points")

    for index, point in enumerate(DEFAULT_POINTS):
        fallback_folder.addParmTemplate(
            hou.FloatParmTemplate(
                "curve_point_%d" % index,
                "Curve Point %d" % index,
                3,
                default_value=point,
            )
        )

    road_folder.addParmTemplate(fallback_folder)
    parm_group.append(road_folder)


def configure_geo_node():
    hou.hipFile.clear(suppress_save_prompt=True)

    obj = hou.node("/obj")
    geo_node = obj.createNode("geo", ROAD_NODE_NAME)
    for child in geo_node.children():
        child.destroy()

    parm_group = hou.ParmTemplateGroup()
    append_road_parms(parm_group)
    geo_node.setParmTemplateGroup(parm_group)

    param_input_merge = geo_node.createNode("object_merge", "IN_Unity_Curve_Parameter_Input")
    param_input_merge.parm("objpath1").set('`chs("../unity_curve_input")`')
    param_input_merge.parm("xformtype").set(1)

    object_input_merge = geo_node.createNode("object_merge", "IN_Unity_Curve_Object_Input")
    object_input_merge.parm("objpath1").set('`opinputpath("..", 0)`')
    object_input_merge.parm("xformtype").set(1)

    merged_input = geo_node.createNode("merge", "MERGE_Unity_Curve_Inputs")
    merged_input.setInput(0, param_input_merge)
    merged_input.setInput(1, object_input_merge)

    road_sop = geo_node.createNode("python", "BUILD_curve_driven_road_surface")
    road_sop.setInput(0, merged_input)
    road_sop.parm("python").set(PYTHON_SOP_CODE)
    road_sop.setDisplayFlag(True)
    road_sop.setRenderFlag(True)

    road_out = geo_node.createNode("output", "OUT_ROAD_MESH")
    road_out.setInput(0, road_sop)
    road_out.parm("outputidx").set(0)
    road_out.setDisplayFlag(True)
    road_out.setRenderFlag(True)

    start_instance_sop = geo_node.createNode("python", "BUILD_start_prefab_instance")
    start_instance_sop.setInput(0, road_sop)
    start_instance_sop.parm("python").set(START_INSTANCE_SOP_CODE)

    start_out = geo_node.createNode("output", "OUT_START_PREFAB_INSTANCE")
    start_out.setInput(0, start_instance_sop)
    start_out.parm("outputidx").set(1)

    geo_node.layoutChildren()
    geo_node.setDisplayFlag(True)

    return geo_node, road_out


def create_hda(geo_node):
    if os.path.exists(HDA_PATH):
        os.remove(HDA_PATH)

    # Keep a copy before createDigitalAsset converts the node to an HDA instance.
    # The HDA definition must own these parameters or Houdini Engine cannot cook it.
    road_parm_group = geo_node.parmTemplateGroup()

    definition_node = geo_node.createDigitalAsset(
        name=ROAD_ASSET_TYPE,
        hda_file_name=HDA_PATH,
        description="PCG Bike Curve Road Surface Test",
        min_num_inputs=0,
        max_num_inputs=1,
    )

    definition = definition_node.type().definition()
    definition.setParmTemplateGroup(road_parm_group)
    definition.setComment(
        "Test HDA: Unity Curve Input parameter generates a single road surface mesh. "
        "UV uses width 0..1 and distance-based V tiling. No material output. "
        "Start Prefab emits a separate unity_instance point at the curve start. "
        "Extension points: shoulder mesh, lanes, collider, metadata."
    )
    definition_node.matchCurrentDefinition()
    return definition_node


def export_obj(sop_node):
    sop_node.cook(force=True)
    geometry = sop_node.geometry()
    geometry.saveToFile(OBJ_PATH)


def main():
    ensure_dirs()
    geo_node, out_sop = configure_geo_node()
    export_obj(out_sop)
    create_hda(geo_node)
    cleanup_hda_backup_dir()
    hou.hipFile.save(HIP_PATH)

    print("Generated Houdini test hip: %s" % HIP_PATH)
    print("Generated Unity OBJ: %s" % OBJ_PATH)
    print("Generated Unity HDA: %s" % HDA_PATH)


if __name__ == "__main__":
    main()
