"""Incrementally add a wide-road tight-turn guard to the live Track HDA.

The authored input spline remains untouched.  Only the generated road layout is
shifted toward the outside of turns when its inner offset would collapse.
"""

from __future__ import annotations

import json
import os
from datetime import datetime

import hrpyc


PROJECT_ROOT = "E:/HoudiniProject/Unity_Houdini_PCG_Track"
TRACK_NODE_PATH = "/obj/Track1"
TRACK_TYPE_NAME = "pcgbike::Track::1.0"
TRACK_HDA_PATH = PROJECT_ROOT + "/Assets/PCG/HDA/Track.hda"
TRACK_BACKUP_DIR = PROJECT_ROOT + "/Assets/PCG/HDA/backup"
RECOVERY_DIR = PROJECT_ROOT + "/HoudiniProject/PCG_Track_21.0.440/recovery"


REPROJECT_VEX = r'''
function float turn_radius(vector previous; vector current; vector next)
{
    vector incoming = current - previous;
    vector outgoing = next - current;
    incoming.y = 0.0;
    outgoing.y = 0.0;
    float incoming_length = length(incoming);
    float outgoing_length = length(outgoing);
    float chord_length = length(set(next.x - previous.x, 0.0, next.z - previous.z));
    float twice_area = abs(cross(incoming, set(next.x - previous.x, 0.0, next.z - previous.z)).y);
    if (incoming_length <= 1e-5 || outgoing_length <= 1e-5 || twice_area <= 1e-8)
        return 1e18;
    return incoming_length * outgoing_length * chord_length / (2.0 * twice_area);
}

function vector turn_outward(vector previous; vector current; vector next)
{
    // Use the actual XZ circumcenter instead of relying on handedness.  The
    // radial vector from that center to the current point is always outward.
    float ax = previous.x;
    float az = previous.z;
    float bx = current.x;
    float bz = current.z;
    float cx = next.x;
    float cz = next.z;
    float determinant = 2.0 * (ax * (bz - cz) + bx * (cz - az) + cx * (az - bz));
    if (abs(determinant) <= 1e-8)
        return {0.0, 0.0, 0.0};
    float a2 = ax * ax + az * az;
    float b2 = bx * bx + bz * bz;
    float c2 = cx * cx + cz * cz;
    float center_x = (a2 * (bz - cz) + b2 * (cz - az) + c2 * (az - bz)) / determinant;
    float center_z = (a2 * (cx - bx) + b2 * (ax - cx) + c2 * (bx - ax)) / determinant;
    vector outward = current - set(center_x, current.y, center_z);
    outward.y = 0.0;
    return length(outward) > 1e-5 ? normalize(outward) : set(0.0, 0.0, 0.0);
}

function int wrapped_index(int index; int count)
{
    return (index % count + count) % count;
}

int cross_section_count = max(int(detail(0, "road_cross_section_count")), 4);
int point_count = npoints(0);
int ring_count = point_count / cross_section_count;
if (ring_count <= 0)
    return;

int closed_loop = detail(0, "road_closed_loop", 0);
float road_width = max(detail(0, "road_width"), 0.1);
float shoulder_width = max(detail(0, "road_visible_shoulder_width"), 0.0);
float shoulder_drop = max(detail(0, "road_edge_drop"), 0.0);
float half_width = road_width * 0.5;
float total_half_width = max(half_width + shoulder_width, 0.05);
float offsets[] = array(-total_half_width, -half_width, half_width, total_half_width);
float drops[] = array(-shoulder_drop, 0.0, 0.0, -shoulder_drop);

int guard_enabled = chi("../../tight_turn_guard_enable");
float minimum_inner_radius = max(ch("../../tight_turn_min_inner_radius"), 0.05);
float transition_length = max(ch("../../tight_turn_transition_length"), 0.0);
float maximum_offset = max(ch("../../tight_turn_max_offset"), 0.0);
float sample_spacing = max(ch("../../sample_spacing"), 0.25);
// A wider curvature stencil ignores tiny material-boundary insertion segments
// and keeps the outward normal stable through nearly straight approaches.
int curvature_probe_steps = max(1, int(ceil(min(max(transition_length * 0.25, sample_spacing), 6.0) / sample_spacing)));

vector original_centers[];
vector generated_centers[];
vector cumulative_shifts[];
for (int ring = 0; ring < ring_count; ring++)
{
    vector lane_left = point(0, "P", ring * cross_section_count + 1);
    vector lane_right = point(0, "P", ring * cross_section_count + 2);
    vector center = (lane_left + lane_right) * 0.5;
    append(original_centers, center);
    append(generated_centers, center);
    append(cumulative_shifts, {0.0, 0.0, 0.0});
}

float original_distances[];
for (int ring = 0; ring < ring_count; ring++)
{
    float distance = ring == 0 ? 0.0 : original_distances[ring - 1] + length(original_centers[ring] - original_centers[ring - 1]);
    append(original_distances, distance);
}
float input_length = max(original_distances[ring_count - 1], 1e-5);
if (closed_loop && ring_count > 1)
    input_length += length(original_centers[0] - original_centers[ring_count - 1]);

int original_tight[];
float input_minimum_radius = 1e18;
int trigger_ring_count = 0;
for (int ring = 0; ring < ring_count; ring++)
{
    int has_neighbours = closed_loop || (ring >= curvature_probe_steps && ring < ring_count - curvature_probe_steps);
    float radius = 1e18;
    if (has_neighbours)
    {
        int previous_ring = wrapped_index(ring - curvature_probe_steps, ring_count);
        int next_ring = wrapped_index(ring + curvature_probe_steps, ring_count);
        radius = turn_radius(original_centers[previous_ring], original_centers[ring], original_centers[next_ring]);
        input_minimum_radius = min(input_minimum_radius, radius);
    }
    int tight = radius < total_half_width + minimum_inner_radius;
    append(original_tight, tight);
    trigger_ring_count += tight;
}

// Build one parallel-offset field from the authored curve.  Repeatedly
// recomputing curvature after partial displacement can amplify transition
// kinks, so the guard deliberately applies this field once.  The inner half
// of Transition Length is a plateau; falloff only
// starts outside it, preventing a single tight sample from creating a new kink.
int transition_steps = int(ceil(transition_length / sample_spacing)) + 2;
for (int iteration = 0; iteration < 1 && guard_enabled && maximum_offset > 0.0; iteration++)
{
    float required_shifts[];
    vector outward_directions[];
    for (int ring = 0; ring < ring_count; ring++)
    {
        int has_neighbours = closed_loop || (ring >= curvature_probe_steps && ring < ring_count - curvature_probe_steps);
        float required = 0.0;
        vector outward = {0.0, 0.0, 0.0};
        if (has_neighbours)
        {
            int previous_ring = wrapped_index(ring - curvature_probe_steps, ring_count);
            int next_ring = wrapped_index(ring + curvature_probe_steps, ring_count);
            float radius = turn_radius(generated_centers[previous_ring], generated_centers[ring], generated_centers[next_ring]);
            float clearance_deficit = total_half_width + minimum_inner_radius - radius;
            required = clearance_deficit > 0.0
                ? clamp(clearance_deficit + 0.15, 0.0, maximum_offset)
                : 0.0;
            // Very large-radius samples are effectively straight; their
            // circumcenter side is numerically unstable.  Let neighbouring
            // guarded samples provide the transition direction instead.
            if (radius < (total_half_width + minimum_inner_radius) * 4.0)
                outward = turn_outward(generated_centers[previous_ring], generated_centers[ring], generated_centers[next_ring]);
        }
        append(required_shifts, required);
        append(outward_directions, outward);
    }

    vector iteration_deltas[];
    for (int ring = 0; ring < ring_count; ring++)
    {
        float strongest_influence = 0.0;
        vector contributor_direction = {0.0, 0.0, 0.0};
        for (int step = -transition_steps; step <= transition_steps; step++)
        {
            int candidate = ring + step;
            if (!closed_loop && (candidate < 0 || candidate >= ring_count))
                continue;
            candidate = wrapped_index(candidate, ring_count);
            if (required_shifts[candidate] <= 1e-5)
                continue;
            float arc_distance = abs(original_distances[ring] - original_distances[candidate]);
            if (closed_loop)
                arc_distance = min(arc_distance, input_length - arc_distance);
            if (transition_length <= 1e-5 && candidate != ring)
                continue;
            float plateau_length = transition_length * 0.5;
            float falloff_length = max(transition_length - plateau_length, 1e-5);
            float x = transition_length <= 1e-5
                ? 1.0
                : clamp(1.0 - max(arc_distance - plateau_length, 0.0) / falloff_length, 0.0, 1.0);
            float falloff = x * x * (3.0 - 2.0 * x);
            float influence = required_shifts[candidate] * falloff;
            strongest_influence = max(strongest_influence, influence);
            contributor_direction += outward_directions[candidate] * influence;
        }
        vector delta = {0.0, 0.0, 0.0};
        // Every affected ring follows its own curvature normal.  Using the
        // trigger ring's direction would translate the whole patch almost
        // rigidly and would not actually increase its radius.
        if (strongest_influence > 1e-5 && length(contributor_direction) > 1e-5)
            // Weighted guarded normals form a continuous direction field both
            // across the arc and into straight approach/departure transitions.
            delta = normalize(contributor_direction) * strongest_influence;

        // Never let transition blending reduce the mandatory local clearance.
        if (required_shifts[ring] > 1e-5)
        {
            float outward_projection = dot(delta, outward_directions[ring]);
            if (outward_projection < required_shifts[ring])
                delta += outward_directions[ring] * (required_shifts[ring] - outward_projection);
        }
        append(iteration_deltas, delta);
    }

    for (int ring = 0; ring < ring_count; ring++)
    {
        vector accumulated = cumulative_shifts[ring] + iteration_deltas[ring];
        if (length(accumulated) > maximum_offset)
            accumulated = normalize(accumulated) * maximum_offset;
        cumulative_shifts[ring] = accumulated;
        generated_centers[ring] = original_centers[ring] + accumulated;
    }
}

// Low-pass the displacement field itself, not the authored centerline.  This
// removes derivative spikes where the parallel offset blends into straight
// track while keeping the original spline available as untouched metadata.
for (int smooth_pass = 0; smooth_pass < 8 && guard_enabled; smooth_pass++)
{
    vector smoothed_shifts[];
    for (int ring = 0; ring < ring_count; ring++)
    {
        if (!closed_loop && (ring == 0 || ring == ring_count - 1))
        {
            append(smoothed_shifts, cumulative_shifts[ring]);
            continue;
        }
        int previous_ring = wrapped_index(ring - 1, ring_count);
        int next_ring = wrapped_index(ring + 1, ring_count);
        vector smoothed = (
            cumulative_shifts[previous_ring] +
            cumulative_shifts[ring] * 2.0 +
            cumulative_shifts[next_ring]) * 0.25;
        append(smoothed_shifts, smoothed);
    }
    cumulative_shifts = smoothed_shifts;
}
for (int ring = 0; ring < ring_count; ring++)
    generated_centers[ring] = original_centers[ring] + cumulative_shifts[ring];

float generated_distances[];
for (int ring = 0; ring < ring_count; ring++)
{
    float distance = ring == 0 ? 0.0 : generated_distances[ring - 1] + length(generated_centers[ring] - generated_centers[ring - 1]);
    append(generated_distances, distance);
}
float generated_length = max(generated_distances[ring_count - 1], 1e-5);
if (closed_loop && ring_count > 1)
    generated_length += length(generated_centers[0] - generated_centers[ring_count - 1]);

float maximum_applied_shift = 0.0;
int guard_ring_count = 0;
for (int ring = 0; ring < ring_count; ring++)
{
    int previous_ring = closed_loop
        ? wrapped_index(ring - curvature_probe_steps, ring_count)
        : max(ring - curvature_probe_steps, 0);
    int next_ring = closed_loop
        ? wrapped_index(ring + curvature_probe_steps, ring_count)
        : min(ring + curvature_probe_steps, ring_count - 1);
    vector tangent = generated_centers[next_ring] - generated_centers[previous_ring];
    tangent.y = 0.0;
    if (length(tangent) <= 1e-5)
        tangent = {1.0, 0.0, 0.0};
    tangent = normalize(tangent);
    vector lateral = normalize(set(tangent.z, 0.0, -tangent.x));
    float shift_magnitude = length(cumulative_shifts[ring]);
    int guarded = shift_magnitude > 1e-4;
    maximum_applied_shift = max(maximum_applied_shift, shift_magnitude);
    guard_ring_count += guarded;

    float road_t = clamp(original_distances[ring] / input_length, 0.0, 1.0);
    for (int section = 0; section < cross_section_count; section++)
    {
        int point_id = ring * cross_section_count + section;
        vector position = generated_centers[ring] + lateral * offsets[section];
        position.y = generated_centers[ring].y + drops[section];
        setpointattrib(0, "P", point_id, position, "set");
        setpointattrib(0, "road_t", point_id, road_t, "set");
        setpointattrib(0, "road_distance", point_id, original_distances[ring], "set");
        setpointattrib(0, "road_generated_distance", point_id, generated_distances[ring], "set");
        setpointattrib(0, "road_lateral_offset_m", point_id, offsets[section], "set");
        setpointattrib(0, "road_original_center", point_id, original_centers[ring], "set");
        setpointattrib(0, "road_generated_center", point_id, generated_centers[ring], "set");
        setpointattrib(0, "road_center_shift", point_id, cumulative_shifts[ring], "set");
        setpointattrib(0, "road_center_shift_m", point_id, shift_magnitude, "set");
        setpointattrib(0, "road_tight_turn", point_id, original_tight[ring] || guarded, "set");
    }
}

// Physical distance remains available for diagnostics and possible future flow
// maps.  Surface albedo UV itself is world-planar to avoid accumulated U-turn shear.
float column_lengths[];
for (int section = 0; section < cross_section_count; section++)
{
    float column_distance = 0.0;
    for (int ring = 0; ring < ring_count; ring++)
    {
        int point_id = ring * cross_section_count + section;
        if (ring > 0)
        {
            int previous_id = (ring - 1) * cross_section_count + section;
            vector current_position = point(0, "P", point_id);
            vector previous_position = point(0, "P", previous_id);
            column_distance += length(current_position - previous_position);
        }
        setpointattrib(0, "road_surface_distance", point_id, column_distance, "set");
    }
    float column_length = column_distance;
    if (closed_loop && ring_count > 1)
    {
        vector first_position = point(0, "P", section);
        vector last_position = point(0, "P", (ring_count - 1) * cross_section_count + section);
        column_length += length(first_position - last_position);
    }
    append(column_lengths, column_length);
}
setdetailattrib(0, "road_surface_column_lengths", column_lengths, "set");

float maximum_turn_angle = 0.0;
float generated_minimum_radius = 1e18;
float minimum_inner_radius_after_guard = 1e18;
int residual_tight_ring_count = 0;
for (int ring = 0; ring < ring_count; ring++)
{
    int has_neighbours = closed_loop || (ring >= curvature_probe_steps && ring < ring_count - curvature_probe_steps);
    if (!has_neighbours)
        continue;
    int previous_ring = wrapped_index(ring - curvature_probe_steps, ring_count);
    int next_ring = wrapped_index(ring + curvature_probe_steps, ring_count);
    int immediate_previous = wrapped_index(ring - 1, ring_count);
    int immediate_next = wrapped_index(ring + 1, ring_count);
    vector incoming = generated_centers[ring] - generated_centers[immediate_previous];
    vector outgoing = generated_centers[immediate_next] - generated_centers[ring];
    incoming.y = 0.0;
    outgoing.y = 0.0;
    if (length(incoming) > sample_spacing * 0.25 && length(outgoing) > sample_spacing * 0.25)
        maximum_turn_angle = max(maximum_turn_angle, degrees(acos(clamp(dot(normalize(incoming), normalize(outgoing)), -1.0, 1.0))));
    float radius = turn_radius(generated_centers[previous_ring], generated_centers[ring], generated_centers[next_ring]);
    generated_minimum_radius = min(generated_minimum_radius, radius);
    float inner_radius = radius - total_half_width;
    minimum_inner_radius_after_guard = min(minimum_inner_radius_after_guard, inner_radius);
    residual_tight_ring_count += inner_radius < minimum_inner_radius - 0.05;
}

if (input_minimum_radius > 1e17)
    input_minimum_radius = 0.0;
if (generated_minimum_radius > 1e17)
    generated_minimum_radius = 0.0;
if (minimum_inner_radius_after_guard > 1e17)
    minimum_inner_radius_after_guard = 0.0;

setdetailattrib(0, "road_sample_count", ring_count, "set");
setdetailattrib(0, "road_length", input_length, "set");
setdetailattrib(0, "road_generated_length", generated_length, "set");
setdetailattrib(0, "road_start_position", generated_centers[0], "set");
vector start_forward = ring_count > 1 ? generated_centers[1] - generated_centers[0] : set(1.0, 0.0, 0.0);
setdetailattrib(0, "road_start_forward", normalize(start_forward), "set");
setdetailattrib(0, "road_max_ring_turn_angle_deg", maximum_turn_angle, "set");
setdetailattrib(0, "road_min_turn_radius", input_minimum_radius, "set");
setdetailattrib(0, "road_generated_min_turn_radius", generated_minimum_radius, "set");
setdetailattrib(0, "road_min_inner_radius_after_guard", minimum_inner_radius_after_guard, "set");
setdetailattrib(0, "road_tight_turn_count", trigger_ring_count, "set");
setdetailattrib(0, "road_tight_turn_guard_count", guard_ring_count, "set");
setdetailattrib(0, "road_tight_turn_residual_count", residual_tight_ring_count, "set");
setdetailattrib(0, "road_max_outward_shift", maximum_applied_shift, "set");
setdetailattrib(0, "road_surface_uv_mode", "world_xz_meters", "set");

if (residual_tight_ring_count > 0)
    warning("Tight-turn guard reached its configured limit with %d residual ring(s). Increase Max Outward Offset or Transition Length.", residual_tight_ring_count);
'''


UV_VEX = r'''
int point_id = vertexpoint(0, @vtxnum);
int primitive_id = vertexprim(0, @vtxnum);
int band_count = max(int(detail(0, "road_band_count")), 3);
int ring_count = max(int(detail(0, "road_sample_count")), 1);
int closed_loop = detail(0, "road_closed_loop", 0);
float uv_tile_length = max(detail(0, "road_uv_tile_length"), 1e-4);
int segment = primitive_id / band_count;
int ring = point_id / max(int(detail(0, "road_cross_section_count")), 4);

float center_distance = point(0, "road_distance", point_id);
if (closed_loop && segment == ring_count - 1 && ring == 0)
    center_distance = detail(0, "road_length");

float lateral_t = point(0, "road_lateral_t", point_id);
vector position = point(0, "P", point_id);
v@uv = set(lateral_t, center_distance / uv_tile_length, 0.0);
// Stable, seam-free and constant-density surface UV for non-directional road layers.
// UV0 remains available for lane markings and other direction-dependent graphics.
v@uv3 = set(position.x / uv_tile_length, position.z / uv_tile_length, 0.0);
'''


GROUP_VEX = r'''
int band = @primnum % 3;
setprimgroup(0, "shoulder_l", @primnum, band == 0, "set");
setprimgroup(0, "lane", @primnum, band == 1, "set");
setprimgroup(0, "shoulder_r", @primnum, band == 2, "set");
setprimgroup(0, "skirt_l", @primnum, 0, "set");
setprimgroup(0, "skirt_r", @primnum, 0, "set");
int guarded = 0;
foreach (int point_id; primpoints(0, @primnum))
    guarded = max(guarded, point(0, "road_tight_turn", point_id));
setprimgroup(0, "road_tight_turn", @primnum, guarded, "set");
setprimgroup(0, "road_tight_turn_guard", @primnum, guarded, "set");
'''


def detail_value(geometry, name, kind="float"):
    if geometry.findGlobalAttrib(name) is None:
        return None
    if kind == "int":
        return geometry.intAttribValue(name)
    if kind == "string":
        return geometry.stringAttribValue(name)
    return geometry.floatAttribValue(name)


def ensure_parameters(hou, track, definition):
    group = definition.parmTemplateGroup()
    if group.find("tight_turn_guard_enable") is not None:
        return False

    enable = hou.ToggleParmTemplate(
        "tight_turn_guard_enable",
        "Enable Tight Turn Guard",
        default_value=True,
    )
    minimum_inner = hou.FloatParmTemplate(
        "tight_turn_min_inner_radius",
        "Minimum Inner Radius (m)",
        1,
        default_value=(2.0,),
        min=0.1,
        max=20.0,
        min_is_strict=True,
    )
    transition = hou.FloatParmTemplate(
        "tight_turn_transition_length",
        "Transition Length (m)",
        1,
        default_value=(24.0,),
        min=0.0,
        max=100.0,
        min_is_strict=True,
    )
    maximum_offset = hou.FloatParmTemplate(
        "tight_turn_max_offset",
        "Maximum Outward Offset (m)",
        1,
        default_value=(30.0,),
        min=0.0,
        max=100.0,
        min_is_strict=True,
    )
    folder = hou.FolderParmTemplate(
        "tight_turn_guard_folder",
        "Tight Turn Guard",
        parm_templates=(enable, minimum_inner, transition, maximum_offset),
    )
    folder.setHelp(
        "急弯处仅外移生成道路中心和整条横截面，避免内侧偏移线反转；不会修改输入 Spline。"
    )
    if group.find("stdswitcher6_6") is not None:
        group.insertBefore("stdswitcher6_6", folder)
    else:
        group.append(folder)
    definition.setParmTemplateGroup(group)
    track.matchCurrentDefinition()
    return True


def write_recovery(track):
    os.makedirs(RECOVERY_DIR, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    path = RECOVERY_DIR + "/track_tight_turn_guard_prepatch_" + timestamp + ".json"
    road = track.node("Road")
    payload = {
        "hip": hou.hipFile.path(),
        "definition": track.type().definition().libraryFilePath(),
        "track": track.path(),
        "parameters": {
            name: track.parm(name).eval() if track.parm(name) is not None else None
            for name in ("road_width", "shoulder_width", "sample_spacing", "uv_tile_length")
        },
        "snippets": {
            name: road.node(name).parm("snippet").eval()
            for name in ("SURFACE_reproject_layout", "UV_write_road_layout", "GROUP_road_bands")
        },
    }
    with open(path, "w", encoding="utf-8") as stream:
        json.dump(payload, stream, ensure_ascii=False, indent=2)
    return path


def backup_definition(track):
    os.makedirs(TRACK_BACKUP_DIR, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    path = TRACK_BACKUP_DIR + "/Track_bak_tight_turn_" + timestamp + ".hda"
    track.type().definition().copyToHDAFile(path)
    return path


connection, hou = hrpyc.import_remote_module("127.0.0.1", 18811, "hou")
track = hou.node(TRACK_NODE_PATH)
if track is None or track.type().name() != TRACK_TYPE_NAME:
    raise RuntimeError("Expected %s at %s" % (TRACK_TYPE_NAME, TRACK_NODE_PATH))
definition = track.type().definition()
if definition is None or os.path.normcase(definition.libraryFilePath()) != os.path.normcase(TRACK_HDA_PATH):
    raise RuntimeError("Track definition is not bound to %s" % TRACK_HDA_PATH)

recovery_path = write_recovery(track)
backup_path = backup_definition(track)
parameters_added = ensure_parameters(hou, track, definition)
used_allow_editing = False
if not track.isEditable():
    track.allowEditingOfContents()
    used_allow_editing = True

road = track.node("Road")
reproject = road.node("SURFACE_reproject_layout")
uv = road.node("UV_write_road_layout")
groups = road.node("GROUP_road_bands")
output = road.node("OUT_ROAD_MESH")
if any(node is None for node in (reproject, uv, groups, output)):
    raise RuntimeError("Missing required Road nodes")

reproject.parm("snippet").set(REPROJECT_VEX)
reproject.setComment(
    "急弯保护：当 R < 总半宽 + 最小内侧半径时，将生成道路整体向弯道外侧平移并按长度平滑过渡；输入曲线保持不变。"
)
uv.parm("snippet").set(UV_VEX)
uv.setComment("UV0 保留道路流向；uv3 使用世界 XZ 米制投影，避免发卡弯内外弧长差累积成扇形纹理。")
groups.parm("snippet").set(GROUP_VEX)

output.cook(force=True)
if track.errors() or output.errors():
    raise RuntimeError("Cook failed: %r / %r" % (track.errors(), output.errors()))
geometry = output.geometry()
if geometry.findVertexAttrib("uv") is None or geometry.findVertexAttrib("uv3") is None:
    raise RuntimeError("Output is missing uv or uv3")
if any(len(primitive.vertices()) != 3 for primitive in geometry.prims()):
    raise RuntimeError("Output contains non-triangle primitives")

definition.save(TRACK_HDA_PATH, template_node=track, create_backup=True)
hou.hda.installFile(TRACK_HDA_PATH)
installed_definition = next(
    item for item in hou.hda.definitionsInFile(TRACK_HDA_PATH)
    if item.nodeTypeName() == TRACK_TYPE_NAME
)
installed_definition.setIsPreferred(True)
track.matchCurrentDefinition()
hou.hipFile.save()

output = track.node("Road/OUT_ROAD_MESH")
output.cook(force=True)
geometry = output.geometry()
result = {
    "hip": hou.hipFile.path(),
    "hda": track.type().definition().libraryFilePath(),
    "backup": backup_path,
    "recovery": recovery_path,
    "used_allow_editing": used_allow_editing,
    "parameters_added": parameters_added,
    "points": len(geometry.points()),
    "primitives": len(geometry.prims()),
    "input_min_radius": detail_value(geometry, "road_min_turn_radius"),
    "generated_min_radius": detail_value(geometry, "road_generated_min_turn_radius"),
    "minimum_inner_radius": detail_value(geometry, "road_min_inner_radius_after_guard"),
    "trigger_rings": detail_value(geometry, "road_tight_turn_count", "int"),
    "guard_rings": detail_value(geometry, "road_tight_turn_guard_count", "int"),
    "residual_rings": detail_value(geometry, "road_tight_turn_residual_count", "int"),
    "maximum_shift": detail_value(geometry, "road_max_outward_shift"),
    "uv_mode": detail_value(geometry, "road_surface_uv_mode", "string"),
    "uv_ratio": detail_value(geometry, "road_uv_stretch_max_ratio"),
    "errors": list(output.errors()),
    "warnings": list(output.warnings()),
}
print("TIGHT_TURN_PATCH_RESULT=" + json.dumps(result, ensure_ascii=False))
