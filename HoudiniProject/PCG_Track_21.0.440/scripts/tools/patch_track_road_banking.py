"""Incrementally add grade-aware road banking to the live Track HDA.

This patch intentionally treats the current unlocked /obj/Track1 network as
the source of truth.  It never rebuilds the HDA and it preserves every
unrelated node, parameter, connection and comment.
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


def _hom_construct(hou, name, *args, **kwargs):
    """Construct a HOM value inside the remote Houdini Python process."""
    return getattr(hou, name)(*args, **kwargs)


FRAME_DECODE_VEX = r'''
// Point wrangle before centerline Resample. Unity/HAPI uploads Spline frames in
// the conventional point `rot` quaternion attribute. Decode to a vector before
// resampling so quaternion sign ambiguity cannot create interpolation flips.
i@road_has_spline_roll = 0;
v@road_authored_up = {0.0, 1.0, 0.0};

if (!chi("../../bank_use_spline_knot_roll") || !haspointattrib(0, "rot"))
    return;

vector4 rotation = p@rot;
float magnitude_squared = dot(rotation, rotation);
if (magnitude_squared <= 1e-10)
    return;

rotation /= sqrt(magnitude_squared);
vector authored_up = qrotate(rotation, {0.0, 1.0, 0.0});
if (!isfinite(authored_up.x) || !isfinite(authored_up.y) ||
    !isfinite(authored_up.z) || length2(authored_up) <= 1e-10)
    return;

v@road_authored_up = normalize(authored_up);
i@road_has_spline_roll = 1;
'''


FRAME_COMPUTE_VEX = r'''
// Runs once over Detail. The finalized artist-authored centerline remains
// authoritative; this node only derives a stable 3D frame and banking.

function int wrapped_index(int index; int count)
{
    return (index % count + count) % count;
}

function float arc_distance(float a; float b; float total_length; int closed_loop)
{
    float distance = abs(a - b);
    if (closed_loop && total_length > 1e-5)
        distance = min(distance, max(total_length - distance, 0.0));
    return distance;
}

int cross_section_count = max(int(detail(0, "road_cross_section_count")), 4);
int ring_count = npoints(0) / cross_section_count;
if (ring_count <= 0)
    return;

int closed_loop = detail(0, "road_closed_loop", 0);
int banking_enabled = chi("../../enable_road_banking");
int spline_roll_enabled = banking_enabled && chi("../../bank_use_spline_knot_roll");
float design_speed_kph = max(ch("../../bank_design_speed_kph"), 0.0);
float auto_strength = max(ch("../../bank_auto_strength"), 0.0);
float maximum_angle = max(ch("../../bank_max_angle_deg"), 0.0);
float transition_length = max(ch("../../bank_transition_length_m"), 0.0);
float sample_spacing = max(ch("../../sample_spacing"), 0.25);
float speed_mps = design_speed_kph / 3.6;
float gravity = 9.80665;

vector centers[];
float distances[];
for (int ring = 0; ring < ring_count; ring++)
{
    int point_id = ring * cross_section_count;
    vector center = point(0, "road_generated_center", point_id);
    float generated_distance = point(0, "road_generated_distance", point_id);
    append(centers, center);
    append(distances, generated_distance);
}

float total_length = max(detail(0, "road_generated_length"), 1e-5);
float probe_distance = min(max(sample_spacing, 1.0), max(total_length * 0.25, 1.0));

vector tangents[];
vector base_laterals[];
vector base_ups[];
float grades[];
float curvatures[];
float spline_rolls[];
int spline_roll_flags[];
float target_angles[];

for (int ring = 0; ring < ring_count; ring++)
{
    int previous_ring = ring;
    int next_ring = ring;

    for (int step = 1; step < ring_count; step++)
    {
        int candidate = ring - step;
        if (!closed_loop && candidate < 0)
            break;
        candidate = wrapped_index(candidate, ring_count);
        previous_ring = candidate;
        if (arc_distance(distances[ring], distances[candidate], total_length, closed_loop) >= probe_distance)
            break;
    }
    for (int step = 1; step < ring_count; step++)
    {
        int candidate = ring + step;
        if (!closed_loop && candidate >= ring_count)
            break;
        candidate = wrapped_index(candidate, ring_count);
        next_ring = candidate;
        if (arc_distance(distances[ring], distances[candidate], total_length, closed_loop) >= probe_distance)
            break;
    }

    vector tangent = centers[next_ring] - centers[previous_ring];
    if (previous_ring == ring)
        tangent = centers[next_ring] - centers[ring];
    else if (next_ring == ring)
        tangent = centers[ring] - centers[previous_ring];
    if (length(tangent) <= 1e-5)
        tangent = {1.0, 0.0, 0.0};
    tangent = normalize(tangent);

    vector lateral = cross({0.0, 1.0, 0.0}, tangent);
    if (length(lateral) <= 1e-5)
        lateral = {0.0, 0.0, -1.0};
    lateral = normalize(lateral);
    vector up = normalize(cross(tangent, lateral));

    float grade = degrees(atan2(tangent.y, max(length(set(tangent.x, 0.0, tangent.z)), 1e-5)));
    float signed_curvature = 0.0;
    if (previous_ring != ring && next_ring != ring)
    {
        vector incoming = centers[ring] - centers[previous_ring];
        vector outgoing = centers[next_ring] - centers[ring];
        incoming.y = 0.0;
        outgoing.y = 0.0;
        float incoming_length = length(incoming);
        float outgoing_length = length(outgoing);
        if (incoming_length > 1e-5 && outgoing_length > 1e-5)
        {
            incoming /= incoming_length;
            outgoing /= outgoing_length;
            float turn_angle = atan2(cross(incoming, outgoing).y, clamp(dot(incoming, outgoing), -1.0, 1.0));
            float mean_chord = max((incoming_length + outgoing_length) * 0.5, 1e-5);
            signed_curvature = sign(turn_angle) * 2.0 * sin(abs(turn_angle) * 0.5) / mean_chord;
        }
    }

    // Positive bank raises the positive road_lateral_offset_m side.  Negating
    // signed XZ curvature therefore raises the outside edge in either turn.
    float automatic_angle = banking_enabled
        ? -degrees(atan((speed_mps * speed_mps * signed_curvature) / gravity)) * auto_strength
        : 0.0;
    int authored_frame_input = npoints(1) == ring_count ? 1 : 0;
    int authored_frame_point = authored_frame_input == 1 ? ring : ring * cross_section_count;
    int has_spline_roll = point(authored_frame_input, "road_has_spline_roll", authored_frame_point);
    vector authored_up = point(authored_frame_input, "road_authored_up", authored_frame_point);
    float spline_roll_angle = 0.0;
    if (spline_roll_enabled && has_spline_roll && length2(authored_up) > 1e-10)
    {
        // Ignore authored yaw/pitch: centerline position and the 3D tangent remain
        // authoritative. Only measure the signed roll around that tangent.
        authored_up -= tangent * dot(authored_up, tangent);
        if (length2(authored_up) > 1e-10)
        {
            authored_up = normalize(authored_up);
            spline_roll_angle = degrees(atan2(
                dot(tangent, cross(up, authored_up)),
                clamp(dot(up, authored_up), -1.0, 1.0)));
        }
    }
    float target_angle = clamp(
        automatic_angle + spline_roll_angle,
        -maximum_angle,
        maximum_angle);

    append(tangents, tangent);
    append(base_laterals, lateral);
    append(base_ups, up);
    append(grades, grade);
    append(curvatures, signed_curvature);
    append(spline_rolls, spline_roll_angle);
    append(spline_roll_flags, has_spline_roll);
    append(target_angles, target_angle);
}

// Distance-weighted smoothing.  Candidate count is capped by the configured
// sample spacing plus a small allowance for uneven source spacing.
float smoothed_angles[];
int smoothing_steps = transition_length <= 1e-5
    ? 0
    : min(ring_count - 1, int(ceil(transition_length / sample_spacing)) + 8);
for (int ring = 0; ring < ring_count; ring++)
{
    float weighted_angle = 0.0;
    float total_weight = 0.0;
    int visited[];
    for (int step = -smoothing_steps; step <= smoothing_steps; step++)
    {
        int candidate = ring + step;
        if (!closed_loop && (candidate < 0 || candidate >= ring_count))
            continue;
        candidate = wrapped_index(candidate, ring_count);
        if (find(visited, candidate) >= 0)
            continue;
        append(visited, candidate);
        float distance = arc_distance(distances[ring], distances[candidate], total_length, closed_loop);
        if (transition_length > 1e-5 && distance > transition_length)
            continue;
        float x = transition_length <= 1e-5 ? 1.0 : clamp(1.0 - distance / transition_length, 0.0, 1.0);
        float weight = transition_length <= 1e-5 ? 1.0 : x * x * (3.0 - 2.0 * x);
        weighted_angle += target_angles[candidate] * weight;
        total_weight += weight;
    }
    append(smoothed_angles, total_weight > 1e-5 ? weighted_angle / total_weight : target_angles[ring]);
}

// Limit angle change per metre.  With the default 8 deg / 24 m settings an
// 8 m ring spacing changes by at most about 2.67 degrees.
float final_angles[] = smoothed_angles;
if (banking_enabled && transition_length > 1e-5 && ring_count > 1)
{
    float maximum_rate = maximum_angle / transition_length;
    int passes = closed_loop ? ring_count : 1;
    for (int pass = 0; pass < passes; pass++)
    {
        for (int ring = 1; ring < ring_count + int(closed_loop); ring++)
        {
            int current = wrapped_index(ring, ring_count);
            int previous = wrapped_index(ring - 1, ring_count);
            float segment_length = current == 0
                ? max(total_length - distances[previous] + distances[current], 0.0)
                : max(distances[current] - distances[previous], 0.0);
            float allowance = maximum_rate * segment_length;
            final_angles[current] = clamp(
                final_angles[current],
                final_angles[previous] - allowance,
                final_angles[previous] + allowance);
        }
        for (int ring = ring_count - 2; ring >= -int(closed_loop); ring--)
        {
            int current = wrapped_index(ring, ring_count);
            int next = wrapped_index(ring + 1, ring_count);
            float segment_length = next == 0
                ? max(total_length - distances[current] + distances[next], 0.0)
                : max(distances[next] - distances[current], 0.0);
            float allowance = maximum_rate * segment_length;
            final_angles[current] = clamp(
                final_angles[current],
                final_angles[next] - allowance,
                final_angles[next] + allowance);
        }
    }
}

float maximum_abs_bank = 0.0;
float maximum_abs_grade = 0.0;
float maximum_abs_spline_roll = 0.0;
vector final_laterals[];
vector final_ups[];
float applied_angles[];
for (int ring = 0; ring < ring_count; ring++)
{
    float bank_angle = banking_enabled ? clamp(final_angles[ring], -maximum_angle, maximum_angle) : 0.0;
    vector4 bank_rotation = quaternion(radians(bank_angle), tangents[ring]);
    vector lateral = normalize(qrotate(bank_rotation, base_laterals[ring]));
    vector up = normalize(qrotate(bank_rotation, base_ups[ring]));
    maximum_abs_bank = max(maximum_abs_bank, abs(bank_angle));
    maximum_abs_grade = max(maximum_abs_grade, abs(grades[ring]));
    maximum_abs_spline_roll = max(maximum_abs_spline_roll, abs(spline_rolls[ring]));
    append(final_laterals, lateral);
    append(final_ups, up);
    append(applied_angles, bank_angle);

    for (int section = 0; section < cross_section_count; section++)
    {
        int point_id = ring * cross_section_count + section;
        setpointattrib(0, "road_bank_deg", point_id, bank_angle, "set");
        setpointattrib(0, "road_bank_target_deg", point_id, target_angles[ring], "set");
        setpointattrib(0, "road_grade_deg", point_id, grades[ring], "set");
        setpointattrib(0, "road_curvature_inv_m", point_id, curvatures[ring], "set");
        setpointattrib(0, "road_spline_roll_deg", point_id, spline_rolls[ring], "set");
        setpointattrib(0, "road_has_spline_roll", point_id, spline_roll_flags[ring], "set");
        setpointattrib(0, "road_frame_tangent", point_id, tangents[ring], "set");
        setpointattrib(0, "road_frame_lateral", point_id, lateral, "set");
        setpointattrib(0, "road_frame_up", point_id, up, "set");
    }
}

setdetailattrib(0, "road_banking_enabled", banking_enabled, "set");
setdetailattrib(0, "road_spline_knot_roll_enabled", spline_roll_enabled, "set");
setdetailattrib(0, "road_bank_design_speed_kph", design_speed_kph, "set");
setdetailattrib(0, "road_bank_transition_length_m", transition_length, "set");
setdetailattrib(0, "road_max_abs_bank_deg", maximum_abs_bank, "set");
setdetailattrib(0, "road_max_abs_grade_deg", maximum_abs_grade, "set");
setdetailattrib(0, "road_max_abs_spline_roll_deg", maximum_abs_spline_roll, "set");
setdetailattrib(0, "road_start_position", centers[0], "set");
setdetailattrib(0, "road_start_forward", tangents[0], "set");
setdetailattrib(0, "road_start_up", final_ups[0], "set");
setdetailattrib(0, "road_start_bank_deg", applied_angles[0], "set");
setdetailattrib(0, "road_start_grade_deg", grades[0], "set");
setdetailattrib(0, "road_start_spline_roll_deg", spline_rolls[0], "set");
'''


FRAME_APPLY_VEX = r'''
// Runs once over Detail.  Disabled mode is a strict compatibility path: the
// incoming vertex positions remain untouched while frame metadata is retained.
if (!chi("../../enable_road_banking"))
    return;

int cross_section_count = max(int(detail(0, "road_cross_section_count")), 4);
int ring_count = npoints(0) / cross_section_count;
int closed_loop = detail(0, "road_closed_loop", 0);
float shoulder_drop = max(detail(0, "road_edge_drop"), 0.0);
if (ring_count <= 0)
    return;

for (int ring = 0; ring < ring_count; ring++)
{
    int base_point = ring * cross_section_count;
    vector center = point(0, "road_generated_center", base_point);
    vector lateral = normalize(point(0, "road_frame_lateral", base_point));
    vector up = normalize(point(0, "road_frame_up", base_point));
    for (int section = 0; section < cross_section_count; section++)
    {
        int point_id = base_point + section;
        float lateral_offset = point(0, "road_lateral_offset_m", point_id);
        float drop = (section == 0 || section == cross_section_count - 1) ? -shoulder_drop : 0.0;
        vector position = center + lateral * lateral_offset + up * drop;
        setpointattrib(0, "P", point_id, position, "set");
    }
}

// Banking changes the physical edge length, so refresh diagnostic distances.
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
'''


DEBUG_FRAME_VEX = r'''
// Houdini viewport guide only.  This branch is never connected to an HDA output.
int cross_section_count = max(int(detail(0, "road_cross_section_count")), 4);
int ring_count = npoints(0) / cross_section_count;
vector centers[];
vector tangents[];
vector laterals[];
vector ups[];
for (int ring = 0; ring < ring_count; ring++)
{
    int point_id = ring * cross_section_count;
    vector center = point(0, "road_generated_center", point_id);
    vector tangent = point(0, "road_frame_tangent", point_id);
    vector lateral = point(0, "road_frame_lateral", point_id);
    vector up = point(0, "road_frame_up", point_id);
    append(centers, center);
    append(tangents, tangent);
    append(laterals, lateral);
    append(ups, up);
}

for (int primitive_index = nprimitives(0) - 1; primitive_index >= 0; primitive_index--)
    removeprim(0, primitive_index, 0);
for (int point_index = npoints(0) - 1; point_index >= 0; point_index--)
    removepoint(0, point_index);
if (!chi("../../debug_bank_frames"))
    return;

float scale = 1.5;
vector colors[] = array({1.0, 0.15, 0.1}, {0.1, 1.0, 0.2}, {0.15, 0.4, 1.0});
for (int ring = 0; ring < ring_count; ring++)
{
    vector axes[] = array(tangents[ring], laterals[ring], ups[ring]);
    for (int axis = 0; axis < 3; axis++)
    {
        int start_point = addpoint(0, centers[ring]);
        int end_point = addpoint(0, centers[ring] + normalize(axes[axis]) * scale);
        setpointattrib(0, "Cd", start_point, colors[axis], "set");
        setpointattrib(0, "Cd", end_point, colors[axis], "set");
        int primitive_id = addprim(0, "polyline");
        addvertex(0, primitive_id, start_point);
        addvertex(0, primitive_id, end_point);
    }
}
'''


START_PREFAB_VEX = r'''
string prefab = chs("../../start_prefab");
setdetailattrib(0, "road_start_prefab", prefab, "set");
if (prefab == "")
    return;

vector start_pos = detail(0, "road_start_position");
vector forward = detail(0, "road_start_forward");
vector up = detail(0, "road_start_up");
if (length(forward) <= 1e-5)
    forward = {1.0, 0.0, 0.0};
forward = normalize(forward);
if (length(up) <= 1e-5 || abs(dot(normalize(up), forward)) > 0.999)
    up = {0.0, 1.0, 0.0};
up = normalize(up - forward * dot(up, forward));

float yaw_offset = radians(ch("../../start_prefab_yaw_offset"));
int point_id = addpoint(0, start_pos);
setpointattrib(0, "unity_instance", point_id, prefab, "set");
setpointattrib(0, "instance_prefix", point_id, "RaceStart", "set");
setpointattrib(0, "N", point_id, forward, "set");
setpointattrib(0, "up", point_id, up, "set");
matrix3 frame = maketransform(forward, up);
vector4 align_orient = quaternion(frame);
vector4 yaw_orient = quaternion(yaw_offset - radians(90.0), up);
setpointattrib(0, "orient", point_id, normalize(qmultiply(yaw_orient, align_orient)), "set");
setpointattrib(0, "pscale", point_id, 1.0, "set");
'''


COLLISION_VEX = r'''
// Houdini Engine Unity contract: render this geometry and reuse the same mesh
// as a non-convex MeshCollider.  No duplicate SOP geometry is generated.
setprimgroup(0, "rendered_collision_geo", @primnum, 1, "set");
'''


def _snapshot_live_state(hou, track) -> str:
    def raw_value(parm):
        try:
            return parm.unexpandedString()
        except Exception:
            return None

    os.makedirs(RECOVERY_DIR, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    path = RECOVERY_DIR + "/track_road_banking_prepatch_" + timestamp + ".json"
    road = track.node("Road")
    output = road.node("OUT_ROAD_MESH")
    cook_exception = None
    try:
        output.cook(force=True)
    except Exception as error:
        cook_exception = str(error)
    geometry = output.geometry()
    node_names = (
        "SURFACE_reproject_layout",
        "TOPO_rebuild_road_quads",
        "START_prefab_instance",
    )
    payload = {
        "hip": hou.hipFile.path(),
        "hip_unsaved": hou.hipFile.hasUnsavedChanges(),
        "selection": [node.path() for node in hou.selectedNodes()],
        "track": track.path(),
        "track_type": track.type().name(),
        "definition": track.type().definition().libraryFilePath(),
        "editable": track.isEditable(),
        "matches_definition": track.matchesCurrentDefinition(),
        "errors": list(track.errors()) + list(output.errors()),
        "warnings": list(track.warnings()) + list(output.warnings()),
        "cook_exception": cook_exception,
        "geometry": {
            "points": len(geometry.points()) if geometry is not None else None,
            "primitives": len(geometry.prims()) if geometry is not None else None,
        },
        "nodes": {
            name: {
                "path": road.node(name).path(),
                "type": road.node(name).type().name(),
                "inputs": [item.path() if item is not None else None for item in road.node(name).inputs()],
                "snippet": road.node(name).parm("snippet").unexpandedString()
                if road.node(name).parm("snippet") is not None else None,
            }
            for name in node_names
        },
        "parameters": {
            parm.name(): {
                "label": parm.parmTemplate().label(),
                "value": str(parm.eval()),
                "raw": raw_value(parm),
            }
            for parm in track.parms()
        },
    }
    with open(path, "w", encoding="utf-8") as stream:
        json.dump(payload, stream, ensure_ascii=False, indent=2)
    return path


def _backup_definition(track) -> str:
    os.makedirs(TRACK_BACKUP_DIR, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    path = TRACK_BACKUP_DIR + "/Track_bak_road_banking_" + timestamp + ".hda"
    track.type().definition().copyToHDAFile(path)
    return path


def _ensure_parameters(hou, track, definition) -> bool:
    group = definition.parmTemplateGroup()
    legacy_required = (
        "enable_road_banking",
        "bank_design_speed_kph",
        "bank_auto_strength",
        "bank_max_angle_deg",
        "bank_transition_length_m",
        "debug_bank_frames",
    )
    disable_when = "{ enable_road_banking == 0 }"
    present = [group.find(name) is not None for name in legacy_required]
    if any(present) and not all(present):
        missing = [name for name, exists in zip(legacy_required, present) if not exists]
        raise RuntimeError("Partial Road Banking interface; missing %s" % ", ".join(missing))
    if all(present):
        if group.find("bank_use_spline_knot_roll") is not None:
            return False

        folder = next(
            (
                template for template in group.entries()
                if template.type() == hou.parmTemplateType.Folder
                and any(child.name() == "enable_road_banking" for child in template.parmTemplates())
            ),
            None,
        )
        if folder is None:
            raise RuntimeError("Could not locate the existing Road Banking folder")
        use_spline_roll = _hom_construct(hou, "ToggleParmTemplate",
            "bank_use_spline_knot_roll",
            "Use Spline Knot Roll",
            default_value=True,
            help="读取 Unity Spline Knot 绕曲线切线的横滚，与自动 Banking 相加。仅影响编辑器 Cook/Bake。",
        )
        use_spline_roll.setConditional(hou.parmCondType.DisableWhen, disable_when)
        children = list(folder.parmTemplates())
        enable_index = next(
            (index for index, template in enumerate(children) if template.name() == "enable_road_banking"),
            -1,
        )
        children.insert(enable_index + 1, use_spline_roll)
        folder.setParmTemplates(tuple(children))
        group.replace(folder.name(), folder)
        definition.setParmTemplateGroup(group)
        if track.parm("bank_use_spline_knot_roll") is None:
            raise RuntimeError("Spline knot roll parameter did not reach the live Track instance")
        return True

    enable = _hom_construct(hou, "ToggleParmTemplate",
        "enable_road_banking",
        "Enable Road Banking",
        default_value=False,
        help="兼容开关。关闭时不修改现有道路顶点位置，但仍输出坡度与道路 Frame metadata。",
    )
    use_spline_roll = _hom_construct(hou, "ToggleParmTemplate",
        "bank_use_spline_knot_roll",
        "Use Spline Knot Roll",
        default_value=True,
        help="读取 Unity Spline Knot 绕曲线切线的横滚，与自动 Banking 相加。仅影响编辑器 Cook/Bake。",
    )
    speed = _hom_construct(hou, "FloatParmTemplate",
        "bank_design_speed_kph",
        "Design Speed (km/h)",
        1,
        default_value=(25.0,),
        min=0.0,
        max=80.0,
        min_is_strict=True,
        help="自动倾角的目标设计速度；使用 atan(v² / gR) 计算，不参与移动端运行时。",
    )
    strength = _hom_construct(hou, "FloatParmTemplate",
        "bank_auto_strength",
        "Auto Bank Strength",
        1,
        default_value=(1.0,),
        min=0.0,
        max=2.0,
        min_is_strict=True,
        help="自动倾角倍率。0 关闭曲率驱动的自动倾角，仅保留 Spline Knot Roll。",
    )
    maximum = _hom_construct(hou, "FloatParmTemplate",
        "bank_max_angle_deg",
        "Maximum Bank Angle (deg)",
        1,
        default_value=(8.0,),
        min=0.0,
        max=20.0,
        min_is_strict=True,
        help="自动与手动叠加后的绝对倾角上限；移动端建议保持在 12 度以内。",
    )
    transition = _hom_construct(hou, "FloatParmTemplate",
        "bank_transition_length_m",
        "Transition Length (m)",
        1,
        default_value=(24.0,),
        min=0.0,
        max=100.0,
        min_is_strict=True,
        help="按道路真实距离平滑，并限制每米倾角变化率。",
    )
    debug = _hom_construct(hou, "ToggleParmTemplate",
        "debug_bank_frames",
        "Debug Bank Frames",
        default_value=False,
        help="仅显示 Houdini viewport guide；不会连接到 HDA 输出或进入 Unity Bake。",
    )
    for template in (use_spline_roll, speed, strength, maximum, transition):
        template.setConditional(hou.parmCondType.DisableWhen, disable_when)

    folder = _hom_construct(hou, "FolderParmTemplate",
        "road_banking_folder",
        "Road Banking",
        parm_templates=(enable, use_spline_roll, speed, strength, maximum, transition, debug),
    )
    folder.setHelp(
        "曲线 Y 控制纵坡；XZ 曲率生成自动横坡；Spline Knot Roll 用于人工横坡控制。所有结果在 HDA Cook/Bake 阶段完成。"
    )
    if group.find("stdswitcher5_5") is not None:
        group.insertBefore("stdswitcher5_5", folder)
    else:
        group.append(folder)
    definition.setParmTemplateGroup(group)
    if track.parm("enable_road_banking") is None:
        raise RuntimeError("Definition parameter update did not reach the live Track instance")
    return True


def _ensure_network_annotations(hou, road, nodes) -> None:
    network_box = next(
        (box for box in road.networkBoxes() if box.comment().startswith("03_道路Frame与Banking")),
        None,
    )
    if network_box is None:
        network_box = road.createNetworkBox()
    network_box.setComment(
        "03_道路Frame与Banking：基于生成中心线计算三维切线、纵坡、曲率、自动/手动倾角，再重建横截面。"
    )
    network_box.setColor(_hom_construct(hou, "Color", (0.22, 0.48, 0.72)))
    for node in nodes:
        network_box.addItem(node)
    network_box.fitAroundContents()

    note = next((item for item in road.stickyNotes() if item.name() == "NOTE_Road_Banking"), None)
    if note is None:
        note = road.createStickyNote("NOTE_Road_Banking")
    note.setText(
        "维护提示：SURFACE_reproject_layout 保持美术中心线并写入距离与只读急弯诊断；"
        "FRAME_compute_grade_bank 只算姿态；FRAME_apply_grade_bank 只改顶点。"
        "正 bank 抬高正 road_lateral_offset_m 一侧，Debug guide 默认关闭。"
    )
    note.setTextSize(0.8)
    note.setPosition(nodes[0].position() + _hom_construct(hou, "Vector2", (0.0, 1.4)))


def _patch_nodes(hou, track) -> None:
    road = track.node("Road")
    if road is None:
        raise RuntimeError("Missing Road subnet")
    reproject = road.node("SURFACE_reproject_layout")
    topology = road.node("TOPO_rebuild_road_quads")
    start_prefab = road.node("START_prefab_instance")
    triangulate = road.node("TOPO_triangulate_for_unity")
    normal = road.node("NORMAL_generate_surface")
    reverse_switch = road.node("CENTERLINE_reverse_switch")
    resample = road.node("CENTERLINE_resample")
    if any(node is None for node in (
        reproject, topology, start_prefab, triangulate, normal,
        reverse_switch, resample,
    )):
        raise RuntimeError("Missing required Road projection/topology/start-prefab node")

    decode = road.node("FRAME_decode_unity_rotation")
    if decode is None:
        decode = road.createNode("attribwrangle", "FRAME_decode_unity_rotation")
    decode.setInput(0, reverse_switch)
    decode.parm("class").set(2)  # Point
    decode.parm("snippet").set(FRAME_DECODE_VEX)
    decode.setComment(
        "将 Unity/HAPI rot 解码为可插值的 authored up；只保留后续绕三维切线计算横滚所需的数据。"
    )
    decode.setGenericFlag(hou.nodeFlag.DisplayComment, True)
    decode.setColor(_hom_construct(hou, "Color", (0.46, 0.34, 0.82)))
    decode.setPosition(reverse_switch.position() + _hom_construct(hou, "Vector2", (2.4, -0.15)))
    resample.setInput(0, decode)

    compute = road.node("FRAME_compute_grade_bank")
    if compute is None:
        compute = road.createNode("attribwrangle", "FRAME_compute_grade_bank")
    compute.setInput(0, reproject)
    compute.setInput(1, resample)
    compute.parm("class").set(0)
    compute.parm("snippet").set(FRAME_COMPUTE_VEX)
    compute.setComment(
        "计算三维道路 Frame、纵坡、曲率、自动 Banking 与 Ramp 修正；按道路距离平滑，不增加网格采样。"
    )
    compute.setGenericFlag(hou.nodeFlag.DisplayComment, True)
    compute.setColor(_hom_construct(hou, "Color", (0.18, 0.55, 0.85)))
    compute.setPosition(reproject.position() + _hom_construct(hou, "Vector2", (2.5, -0.2)))

    apply = road.node("FRAME_apply_grade_bank")
    if apply is None:
        apply = road.createNode("attribwrangle", "FRAME_apply_grade_bank")
    apply.setInput(0, compute)
    apply.parm("class").set(0)
    apply.parm("snippet").set(FRAME_APPLY_VEX)
    apply.setComment(
        "用 banked lateral/up 重建横截面；关闭 Banking 时严格保留旧顶点位置。"
    )
    apply.setGenericFlag(hou.nodeFlag.DisplayComment, True)
    apply.setColor(_hom_construct(hou, "Color", (0.16, 0.72, 0.58)))
    apply.setPosition(compute.position() + _hom_construct(hou, "Vector2", (2.5, -0.2)))
    topology.setInput(0, apply)

    debug = road.node("DEBUG_bank_frames")
    if debug is None:
        debug = road.createNode("attribwrangle", "DEBUG_bank_frames")
    debug.setInput(0, apply)
    debug.parm("class").set(0)
    debug.parm("snippet").set(DEBUG_FRAME_VEX)
    debug.setComment("Viewport-only Frame guide：红=Tangent，绿=Lateral，蓝=Up；不进入 Unity 输出。")
    debug.setGenericFlag(hou.nodeFlag.DisplayComment, True)
    debug.setColor(_hom_construct(hou, "Color", (0.95, 0.55, 0.12)))
    debug.setPosition(apply.position() + _hom_construct(hou, "Vector2", (2.5, -0.2)))
    debug.setTemplateFlag(True)
    debug.setSelectableTemplateFlag(False)

    collision = road.node("COLLISION_mark_rendered")
    if collision is None:
        collision = road.createNode("attribwrangle", "COLLISION_mark_rendered")
    collision.setInput(0, triangulate)
    collision.parm("class").set(1)  # Primitive
    collision.parm("snippet").set(COLLISION_VEX)
    collision.setComment(
        "Unity 输出合约：同一份道路网格同时生成 MeshRenderer 与非凸 MeshCollider，不复制 SOP 几何。"
    )
    collision.setGenericFlag(hou.nodeFlag.DisplayComment, True)
    collision.setColor(_hom_construct(hou, "Color", (0.72, 0.38, 0.16)))
    collision.setPosition(triangulate.position() + _hom_construct(hou, "Vector2", (2.5, -0.2)))
    normal.setInput(0, collision)

    start_prefab.parm("snippet").set(START_PREFAB_VEX)
    start_prefab.setComment("起点 Prefab 使用 road_start_forward + road_start_up 对齐纵坡与 Banking。")
    start_prefab.setGenericFlag(hou.nodeFlag.DisplayComment, True)
    _ensure_network_annotations(hou, road, (decode, compute, apply, debug))


def _detail_value(geometry, name, kind="float"):
    if geometry.findGlobalAttrib(name) is None:
        return None
    if kind == "int":
        return geometry.intAttribValue(name)
    if kind == "vector":
        return tuple(geometry.attribValue(name))
    return geometry.floatAttribValue(name)


def apply_patch_in_session(hou) -> dict:
    track = hou.node(TRACK_NODE_PATH)
    if track is None or track.type().name() != TRACK_TYPE_NAME:
        raise RuntimeError("Expected %s at %s" % (TRACK_TYPE_NAME, TRACK_NODE_PATH))
    definition = track.type().definition()
    if definition is None or os.path.normcase(definition.libraryFilePath()) != os.path.normcase(TRACK_HDA_PATH):
        raise RuntimeError("Track definition is not bound to %s" % TRACK_HDA_PATH)

    # Preserve the complete unlocked scene before touching either the parameter
    # interface or the SOP network.  This is stronger than an HDA-only backup.
    hip_backup = hou.hipFile.saveAsBackup()
    recovery_path = _snapshot_live_state(hou, track)
    backup_path = _backup_definition(track)

    parameters_added = _ensure_parameters(hou, track, definition)
    used_allow_editing = False
    if not track.isEditable():
        track.allowEditingOfContents()
        used_allow_editing = True

    track.parm("enable_road_banking").set(1)
    track.parm("bank_use_spline_knot_roll").set(1)
    track.parm("bank_design_speed_kph").set(25.0)
    track.parm("bank_auto_strength").set(1.0)
    track.parm("bank_max_angle_deg").set(8.0)
    track.parm("bank_transition_length_m").set(24.0)
    track.parm("debug_bank_frames").set(0)

    _patch_nodes(hou, track)
    output = track.node("Road/OUT_ROAD_MESH")
    output.cook(force=True)
    if track.errors() or output.errors():
        raise RuntimeError("Cook failed: %r / %r" % (track.errors(), output.errors()))
    geometry = output.geometry()
    required_point_attribs = (
        "road_bank_deg",
        "road_grade_deg",
        "road_spline_roll_deg",
        "road_has_spline_roll",
        "road_frame_tangent",
        "road_frame_lateral",
        "road_frame_up",
    )
    missing = [name for name in required_point_attribs if geometry.findPointAttrib(name) is None]
    if missing:
        raise RuntimeError("Cooked road missing frame attributes: %s" % ", ".join(missing))
    if len(geometry.points()) != 32 or len(geometry.prims()) != 42:
        # The current scene is expected to preserve topology.  Standalone tests
        # below cover arbitrary input curves and are not constrained to 32/42.
        raise RuntimeError(
            "Current Track topology changed unexpectedly: points=%d prims=%d"
            % (len(geometry.points()), len(geometry.prims()))
        )
    collision_group = geometry.findPrimGroup("rendered_collision_geo")
    if collision_group is None or len(collision_group.prims()) != len(geometry.prims()):
        raise RuntimeError("Rendered collision group does not contain the full road surface")

    definition.save(TRACK_HDA_PATH, template_node=track, create_backup=True)
    hou.hda.installFile(TRACK_HDA_PATH)
    installed_definition = next(
        item for item in hou.hda.definitionsInFile(TRACK_HDA_PATH)
        if item.nodeTypeName() == TRACK_TYPE_NAME
    )
    installed_definition.setIsPreferred(True)

    # The live network has just been saved, so matching cannot discard authored
    # work.  Re-open the saved contents afterwards to preserve the user's
    # existing Live Scene editing workflow.
    track.matchCurrentDefinition()
    track.parm("enable_road_banking").set(1)
    track.parm("bank_use_spline_knot_roll").set(1)
    track.allowEditingOfContents()
    hou.hipFile.save()

    output = track.node("Road/OUT_ROAD_MESH")
    output.cook(force=True)
    geometry = output.geometry()
    hou.hipFile.save()
    result = {
        "hip": hou.hipFile.path(),
        "hip_backup": hip_backup,
        "hda": track.type().definition().libraryFilePath(),
        "hda_backup": backup_path,
        "recovery": recovery_path,
        "used_allow_editing": used_allow_editing,
        "left_editable": track.isEditable(),
        "parameters_added": parameters_added,
        "banking_enabled": track.parm("enable_road_banking").eval(),
        "spline_knot_roll_enabled": track.parm("bank_use_spline_knot_roll").eval(),
        "points": len(geometry.points()),
        "primitives": len(geometry.prims()),
        "maximum_bank_deg": _detail_value(geometry, "road_max_abs_bank_deg"),
        "maximum_grade_deg": _detail_value(geometry, "road_max_abs_grade_deg"),
        "maximum_spline_roll_deg": _detail_value(geometry, "road_max_abs_spline_roll_deg"),
        "start_up": _detail_value(geometry, "road_start_up", "vector"),
        "errors": list(track.errors()) + list(output.errors()),
        "warnings": list(track.warnings()) + list(output.warnings()),
        "hip_unsaved": hou.hipFile.hasUnsavedChanges(),
    }
    return result


def apply_patch() -> str:
    """Execute the patch in Houdini's Python process so HOM constructors stay local."""
    connection, _remote_hou = hrpyc.import_remote_module("127.0.0.1", 18811, "hou")
    script_path = os.path.abspath(__file__).replace("\\", "/")
    remote_code = (
        "import hou\n"
        "_road_banking_namespace = {'__name__': 'road_banking_remote'}\n"
        "exec(compile(open(%r, encoding='utf-8').read(), %r, 'exec'), _road_banking_namespace)\n"
        "ROAD_BANKING_REMOTE_RESULT = _road_banking_namespace['apply_patch_in_session'](hou)\n"
    ) % (script_path, script_path)
    connection.execute(remote_code)
    return connection.eval(
        "__import__('json').dumps(ROAD_BANKING_REMOTE_RESULT, ensure_ascii=False)"
    )


if __name__ == "__main__":
    print("ROAD_BANKING_PATCH_RESULT=" + apply_patch())
