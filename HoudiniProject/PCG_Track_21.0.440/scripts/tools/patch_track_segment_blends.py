"""Incrementally migrate Track HDA material segments to asymmetric meter blends.

This script patches the currently-open /obj/Track1 instance.  It deliberately
does not clear the HIP, rebuild the asset, or delete historical backups.
Run it inside the current Houdini GUI session through Houdini MCP.
"""

from __future__ import annotations

import os
from datetime import datetime

try:
    import hou
except ModuleNotFoundError:
    # Houdini MCP injects a remote hou proxy into the execution globals.
    if "hou" not in globals():
        raise


PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "..", ".."))
TRACK_HDA_PATH = os.path.join(PROJECT_ROOT, "Assets", "PCG", "HDA", "Track.hda")
TRACK_BACKUP_DIR = os.path.join(PROJECT_ROOT, "Assets", "PCG", "HDA", "backup")
TRACK_NODE_PATH = "/obj/Track1"
TRACK_TYPE_NAME = "pcgbike::Track::1.0"


LOCAL_SAMPLE_VEX = r'''
// Material Segment 边界局部采样。
// 性能关键点：只在每个边界的 -D / 0 / +D 位置插点，不提高整条赛道采样密度。

function void append_unique(export float values[]; float value; float tolerance)
{
    foreach (float existing; values)
    {
        if (abs(existing - value) <= tolerance)
            return;
    }
    append(values, value);
}

function float wrap_distance(float distance; float total_length)
{
    if (total_length <= 1e-5)
        return 0.0;
    return distance - floor(distance / total_length) * total_length;
}

function vector sample_position(
    vector source_positions[];
    float cumulative_distances[];
    float target_distance;
    float total_length;
    int closed_loop)
{
    int point_count = len(source_positions);
    if (point_count <= 0)
        return {0.0, 0.0, 0.0};
    if (point_count == 1 || target_distance <= 1e-6)
        return source_positions[0];

    for (int index = 1; index < point_count; index++)
    {
        if (target_distance <= cumulative_distances[index] + 1e-6)
        {
            float start_distance = cumulative_distances[index - 1];
            float span = max(cumulative_distances[index] - start_distance, 1e-6);
            float local_t = clamp((target_distance - start_distance) / span, 0.0, 1.0);
            return lerp(source_positions[index - 1], source_positions[index], local_t);
        }
    }

    if (closed_loop)
    {
        float start_distance = cumulative_distances[point_count - 1];
        float span = max(total_length - start_distance, 1e-6);
        float local_t = clamp((target_distance - start_distance) / span, 0.0, 1.0);
        return lerp(source_positions[point_count - 1], source_positions[0], local_t);
    }
    return source_positions[point_count - 1];
}

if (nprimitives(0) <= 0)
    return;

int vertex_count = primvertexcount(0, 0);
if (vertex_count < 2)
    return;

int closed_loop = int(primintrinsic(0, "closed", 0));
vector source_positions[];
float cumulative_distances[];
float distance_along = 0.0;
for (int vertex_index = 0; vertex_index < vertex_count; vertex_index++)
{
    int vertex_id = primvertex(0, 0, vertex_index);
    int point_id = vertexpoint(0, vertex_id);
    vector position = point(0, "P", point_id);
    if (vertex_index > 0)
        distance_along += length(position - source_positions[vertex_index - 1]);
    append(source_positions, position);
    append(cumulative_distances, distance_along);
}

float total_length = distance_along;
if (closed_loop)
    total_length += length(source_positions[0] - source_positions[vertex_count - 1]);
if (total_length <= 1e-5)
    return;

float target_distances[] = cumulative_distances;
float dedupe_tolerance = max(total_length * 1e-7, 1e-5);
float hard_edge_distance = min(0.01, max(total_length * 1e-5, 0.0001));
int segment_count = chi("../../material_segments");

for (int index = 1; index <= segment_count; index++)
{
    float start_t = clamp(ch(sprintf("../../material_segment_start_%d", index)), 0.0, 1.0);
    float end_t = clamp(ch(sprintf("../../material_segment_end_%d", index)), 0.0, 1.0);
    float start_blend_m = max(ch(sprintf("../../material_segment_start_blend_distance_m_%d", index)), 0.0);
    float end_blend_m = max(ch(sprintf("../../material_segment_end_blend_distance_m_%d", index)), 0.0);

    if (end_t < start_t)
    {
        float swap_t = start_t;
        start_t = end_t;
        end_t = swap_t;
        float swap_blend = start_blend_m;
        start_blend_m = end_blend_m;
        end_blend_m = swap_blend;
    }

    float segment_length_t = end_t - start_t;
    if (segment_length_t <= 1e-6)
        continue;

    // 0-1 完整覆盖没有外部边界，不在闭环接缝插入无意义淡入淡出点。
    if (start_t <= 1e-6 && end_t >= 1.0 - 1e-6)
        continue;

    float start_width_t = start_blend_m / total_length;
    float end_width_t = end_blend_m / total_length;
    float width_sum = start_width_t + end_width_t;
    if (width_sum > segment_length_t && width_sum > 1e-6)
    {
        float scale = segment_length_t / width_sum;
        start_width_t *= scale;
        end_width_t *= scale;
    }

    float start_sample_m = start_width_t > 1e-6 ? start_width_t * total_length : hard_edge_distance;
    float end_sample_m = end_width_t > 1e-6 ? end_width_t * total_length : hard_edge_distance;
    float boundaries[] = array(start_t * total_length, end_t * total_length);
    float sample_widths[] = array(start_sample_m, end_sample_m);

    for (int boundary_index = 0; boundary_index < 2; boundary_index++)
    {
        float boundary = boundaries[boundary_index];
        float sample_width = sample_widths[boundary_index];
        for (int offset_index = -1; offset_index <= 1; offset_index++)
        {
            float target = boundary + float(offset_index) * sample_width;
            target = closed_loop ? wrap_distance(target, total_length) : clamp(target, 0.0, total_length);
            append_unique(target_distances, target, dedupe_tolerance);
        }
    }
}

target_distances = sort(target_distances);
float sorted_distances[];
foreach (float target; target_distances)
    append_unique(sorted_distances, target, dedupe_tolerance);

vector rebuilt_positions[];
foreach (float target; sorted_distances)
    append(rebuilt_positions, sample_position(source_positions, cumulative_distances, target, total_length, closed_loop));

for (int primitive_index = nprimitives(0) - 1; primitive_index >= 0; primitive_index--)
    removeprim(0, primitive_index, 0);
for (int point_index = npoints(0) - 1; point_index >= 0; point_index--)
    removepoint(0, point_index);

int rebuilt_points[];
foreach (vector position; rebuilt_positions)
    append(rebuilt_points, addpoint(0, position));

int primitive_id = addprim(0, closed_loop ? "poly" : "polyline");
foreach (int point_id; rebuilt_points)
    addvertex(0, primitive_id, point_id);

setdetailattrib(0, "road_material_boundary_sample_count", max(len(rebuilt_points) - vertex_count, 0), "set");
'''


MASK_VEX = r'''
function float smooth01(float edge0; float edge1; float value)
{
    if (abs(edge1 - edge0) < 1e-6)
        return value >= edge1 ? 1.0 : 0.0;
    float t = clamp((value - edge0) / (edge1 - edge0), 0.0, 1.0);
    return t * t * (3.0 - 2.0 * t);
}

function float segment_weight_linear(
    float road_t;
    float start_t;
    float end_t;
    float start_width_t;
    float end_width_t)
{
    if (end_t - start_t <= 1e-6)
        return 0.0;
    float start_gate = start_width_t <= 1e-6
        ? float(road_t >= start_t)
        : smooth01(start_t - start_width_t, start_t + start_width_t, road_t);
    float end_gate = end_width_t <= 1e-6
        ? float(road_t <= end_t)
        : 1.0 - smooth01(end_t - end_width_t, end_t + end_width_t, road_t);
    return clamp(start_gate * end_gate, 0.0, 1.0);
}

function float segment_weight(
    float road_t;
    float start_t;
    float end_t;
    float start_width_t;
    float end_width_t;
    int closed_loop)
{
    if (start_t <= 1e-6 && end_t >= 1.0 - 1e-6)
        return 1.0;

    float weight = segment_weight_linear(road_t, start_t, end_t, start_width_t, end_width_t);
    if (closed_loop)
    {
        weight = max(weight, segment_weight_linear(road_t - 1.0, start_t, end_t, start_width_t, end_width_t));
        weight = max(weight, segment_weight_linear(road_t + 1.0, start_t, end_t, start_width_t, end_width_t));
    }
    return clamp(weight, 0.0, 1.0);
}

float road_length = max(detail(0, "road_length"), 1e-5);
int closed_loop = detail(0, "road_closed_loop", 0);
float road_t = clamp(f@road_t, 0.0, 1.0);
vector mask = {0.0, 0.0, 0.0};
int segment_count = chi("../../material_segments");

for (int index = 1; index <= segment_count; index++)
{
    float start_t = clamp(ch(sprintf("../../material_segment_start_%d", index)), 0.0, 1.0);
    float end_t = clamp(ch(sprintf("../../material_segment_end_%d", index)), 0.0, 1.0);
    float start_blend_m = max(ch(sprintf("../../material_segment_start_blend_distance_m_%d", index)), 0.0);
    float end_blend_m = max(ch(sprintf("../../material_segment_end_blend_distance_m_%d", index)), 0.0);
    int channel = clamp(chi(sprintf("../../material_segment_layer_%d", index)), 0, 2);

    if (end_t < start_t)
    {
        float swap_t = start_t;
        start_t = end_t;
        end_t = swap_t;
        float swap_blend = start_blend_m;
        start_blend_m = end_blend_m;
        end_blend_m = swap_blend;
    }

    float segment_length_t = end_t - start_t;
    if (segment_length_t <= 1e-6)
        continue;

    float start_width_t = start_blend_m / road_length;
    float end_width_t = end_blend_m / road_length;
    float width_sum = start_width_t + end_width_t;
    if (width_sum > segment_length_t && width_sum > 1e-6)
    {
        float scale = segment_length_t / width_sum;
        start_width_t *= scale;
        end_width_t *= scale;
    }

    float weight = segment_weight(road_t, start_t, end_t, start_width_t, end_width_t, closed_loop);
    mask *= 1.0 - weight;
    if (channel == 0)
        mask.x += weight;
    else if (channel == 1)
        mask.y += weight;
    else
        mask.z += weight;
}

float total = mask.x + mask.y + mask.z;
if (total > 1.0)
    mask /= total;
vector4 color = set(clamp(mask.x, 0.0, 1.0), clamp(mask.y, 0.0, 1.0), clamp(mask.z, 0.0, 1.0), 1.0);
setpointattrib(0, "Cd", @ptnum, color, "set");
'''


CONTRACT_VEX = r'''
float road_length = max(detail(0, "road_length"), 1e-5);
int sample_count = int(detail(0, "road_sample_count"));
int segment_count = chi("../../material_segments");
float start_blends_m[];
float end_blends_m[];
float start_widths[];
float end_widths[];
int invalid_count = 0;

for (int index = 1; index <= segment_count; index++)
{
    float start_t = clamp(ch(sprintf("../../material_segment_start_%d", index)), 0.0, 1.0);
    float end_t = clamp(ch(sprintf("../../material_segment_end_%d", index)), 0.0, 1.0);
    float start_blend_m = max(ch(sprintf("../../material_segment_start_blend_distance_m_%d", index)), 0.0);
    float end_blend_m = max(ch(sprintf("../../material_segment_end_blend_distance_m_%d", index)), 0.0);
    if (end_t < start_t)
    {
        float swap_t = start_t;
        start_t = end_t;
        end_t = swap_t;
        float swap_blend = start_blend_m;
        start_blend_m = end_blend_m;
        end_blend_m = swap_blend;
    }

    float segment_length_t = end_t - start_t;
    float start_width_t = start_blend_m / road_length;
    float end_width_t = end_blend_m / road_length;
    if (segment_length_t <= 1e-6)
    {
        start_width_t = 0.0;
        end_width_t = 0.0;
        invalid_count++;
    }
    else
    {
        float width_sum = start_width_t + end_width_t;
        if (width_sum > segment_length_t && width_sum > 1e-6)
        {
            float scale = segment_length_t / width_sum;
            start_width_t *= scale;
            end_width_t *= scale;
        }
    }
    append(start_blends_m, start_width_t * road_length);
    append(end_blends_m, end_width_t * road_length);
    append(start_widths, start_width_t);
    append(end_widths, end_width_t);
}

setdetailattrib(0, "road_base_material_mask_value", "Cd.rgb=(0,0,0)", "set");
setdetailattrib(0, "road_segment_count", segment_count, "set");
setdetailattrib(0, "road_segment_start_blend_distances_m", start_blends_m, "set");
setdetailattrib(0, "road_segment_end_blend_distances_m", end_blends_m, "set");
setdetailattrib(0, "road_segment_start_blend_widths", start_widths, "set");
setdetailattrib(0, "road_segment_end_blend_widths", end_widths, "set");
setdetailattrib(0, "road_segment_invalid_count", invalid_count, "set");
setdetailattrib(0, "road_frame_flip_count", 0, "set");
setdetailattrib(0, "road_seam_position_error", 0.0, "set");
setdetailattrib(0, "road_overlap_guard_adjust_count", 0, "set");
setdetailattrib(0, "road_lane_overlap_count", 0, "set");
setdetailattrib(0, "road_simplified_sample_count", sample_count, "set");
setdetailattrib(0, "road_simplify_removed_count", 0, "set");
setdetailattrib(0, "road_seam_trim_count", 0, "set");
setdetailattrib(0, "road_short_segment_count", 0, "set");
setdetailattrib(0, "road_uv_stretch_warning_count", 0, "set");
setdetailattrib(0, "road_vertex_color_semantic", "length_segment_rgb_masks_base_black_a1", "set");
'''


def _replace_parameter_interface(track_node: hou.Node) -> None:
    group = track_node.parmTemplateGroup()
    old_multiparm = group.find("material_segments")
    if old_multiparm is None:
        raise RuntimeError("Missing material_segments multiparm")

    children = {template.name(): template for template in old_multiparm.parmTemplates()}
    required = (
        "material_segment_start_#",
        "material_segment_end_#",
        "material_segment_layer_#",
    )
    missing = [name for name in required if name not in children]
    if missing:
        raise RuntimeError("Missing existing multiparm children: %s" % ", ".join(missing))

    new_multiparm = hou.FolderParmTemplate(
        "material_segments",
        old_multiparm.label(),
        folder_type=hou.folderType.MultiparmBlock,
    )
    new_multiparm.setHelp(
        "按顺序覆盖道路材质遮罩；后面的 Segment 在重叠区域确定性覆盖前面的 Segment。"
    )
    new_multiparm.addParmTemplate(children["material_segment_start_#"])
    new_multiparm.addParmTemplate(
        hou.FloatParmTemplate(
            "material_segment_start_blend_distance_m_#",
            "Start Blend Distance (m)",
            1,
            default_value=(3.0,),
            min=0.0,
            max=20.0,
            min_is_strict=True,
            max_is_strict=False,
            help=(
                "以 Start 边界为中心，边界前后各混合 D 米；完整过渡宽度约为 2D。"
                "0 表示近似硬边界。"
            ),
        )
    )
    new_multiparm.addParmTemplate(children["material_segment_end_#"])
    new_multiparm.addParmTemplate(
        hou.FloatParmTemplate(
            "material_segment_end_blend_distance_m_#",
            "End Blend Distance (m)",
            1,
            default_value=(3.0,),
            min=0.0,
            max=20.0,
            min_is_strict=True,
            max_is_strict=False,
            help=(
                "以 End 边界为中心，边界前后各混合 D 米；完整过渡宽度约为 2D。"
                "0 表示近似硬边界。"
            ),
        )
    )
    new_multiparm.addParmTemplate(children["material_segment_layer_#"])
    group.replace("material_segments", new_multiparm)

    for obsolete_name in ("segment_blend_distance_m", "segment_blend_width"):
        if group.find(obsolete_name) is not None:
            group.remove(obsolete_name)

    # Public HDA parameters belong to the definition, not to instance spare parms.
    # Updating the definition keeps Houdini Engine/Unity parameter discovery stable.
    definition = track_node.type().definition()
    if definition is None:
        raise RuntimeError("Track has no HDA definition")
    definition.setParmTemplateGroup(group)


def _patch_nodes(track_node: hou.Node) -> None:
    road = track_node.node("Road")
    if road is None:
        raise RuntimeError("Missing Road subnet")

    resample = road.node("CENTERLINE_resample")
    polyframe = road.node("CENTERLINE_polyframe")
    if resample is None or polyframe is None:
        raise RuntimeError("Missing centerline resample/polyframe nodes")

    local_samples = road.node("CENTERLINE_material_segment_samples")
    if local_samples is None:
        local_samples = road.createNode("attribwrangle", "CENTERLINE_material_segment_samples")
    local_samples.setInput(0, resample)
    local_samples.parm("class").set(0)  # Detail (only once)
    local_samples.parm("snippet").set(LOCAL_SAMPLE_VEX)
    local_samples.setComment(
        "材质段边界局部采样：只增加 Start/End ± Blend Distance 所需 Ring，避免全局加密。"
    )
    local_samples.setGenericFlag(hou.nodeFlag.DisplayComment, True)
    local_samples.setColor(hou.Color((0.32, 0.62, 0.92)))
    local_samples.setPosition((resample.position() + polyframe.position()) * 0.5)
    polyframe.setInput(0, local_samples)

    reproject = road.node("SURFACE_reproject_layout")
    mask = road.node("MASK_material_segments")
    contract = road.node("ATTR_road_contract")
    if reproject is None or mask is None or contract is None:
        raise RuntimeError("Missing road projection/mask/contract nodes")

    reproject_code = reproject.parm("snippet").eval()
    old_line = (
        "float road_t = closed_loop ? float(ring) / float(ring_count) : "
        "float(ring) / float(max(ring_count - 1, 1));"
    )
    new_line = "float road_t = clamp(distance_along[ring] / road_length, 0.0, 1.0);"
    if old_line in reproject_code:
        reproject_code = reproject_code.replace(old_line, new_line)
    elif new_line not in reproject_code:
        raise RuntimeError("Unexpected SURFACE_reproject_layout road_t implementation")
    reproject.parm("snippet").set(reproject_code)

    mask.parm("snippet").set(MASK_VEX)
    contract.parm("snippet").set(CONTRACT_VEX)


def _backup_target_hda() -> str:
    target_path = os.path.abspath(TRACK_HDA_PATH).replace("\\", "/")
    backup_dir = os.path.abspath(TRACK_BACKUP_DIR).replace("\\", "/")
    os.makedirs(backup_dir, exist_ok=True)
    definitions = hou.hda.definitionsInFile(target_path)
    source = next((definition for definition in definitions if definition.nodeTypeName() == TRACK_TYPE_NAME), None)
    if source is None:
        raise RuntimeError("Track definition missing from %s" % target_path)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_path = "%s/Track_bak_%s.hda" % (backup_dir, timestamp)
    source.copyToHDAFile(backup_path)
    return backup_path


def apply_patch() -> dict:
    track = hou.node(TRACK_NODE_PATH)
    if track is None or track.type().name() != TRACK_TYPE_NAME:
        raise RuntimeError("Expected %s at %s" % (TRACK_TYPE_NAME, TRACK_NODE_PATH))

    used_allow_editing = False
    if not track.isEditable():
        track.allowEditingOfContents()
        used_allow_editing = True

    backup_path = _backup_target_hda()
    _replace_parameter_interface(track)
    _patch_nodes(track)

    output = track.node("Road/OUT_ROAD_MESH")
    output.cook(force=True)
    if track.errors() or output.errors():
        raise RuntimeError("Cook failed: %r / %r" % (track.errors(), output.errors()))

    target_path = os.path.abspath(TRACK_HDA_PATH).replace("\\", "/")
    source_definition = track.type().definition()
    source_definition.save(target_path, template_node=track, create_backup=True)
    hou.hda.installFile(target_path)
    target_definition = next(
        definition
        for definition in hou.hda.definitionsInFile(target_path)
        if definition.nodeTypeName() == TRACK_TYPE_NAME
    )
    target_definition.setIsPreferred(True)
    track.matchCurrentDefinition()

    # Validate the installed file-backed definition before removing Embedded.
    if os.path.normcase(track.type().definition().libraryFilePath()) != os.path.normcase(target_path):
        raise RuntimeError("Track did not switch to file-backed definition")
    required_parms = (
        "material_segment_start_blend_distance_m_#",
        "material_segment_end_blend_distance_m_#",
    )
    template_group = track.parmTemplateGroup()
    segment_folder = template_group.find("material_segments")
    segment_children = {
        template.name() for template in segment_folder.parmTemplates()
    } if segment_folder is not None else set()
    for parm_name in required_parms:
        if parm_name not in segment_children:
            raise RuntimeError("Saved definition missing %s" % parm_name)
    if template_group.find("segment_blend_distance_m") is not None:
        raise RuntimeError("Obsolete segment_blend_distance_m still present")
    if template_group.find("segment_blend_width") is not None:
        raise RuntimeError("Obsolete segment_blend_width still present")
    if track.node("Road/CENTERLINE_material_segment_samples") is None:
        raise RuntimeError("Saved definition missing local sample node")

    output = track.node("Road/OUT_ROAD_MESH")
    output.cook(force=True)
    if track.errors() or output.errors():
        raise RuntimeError("File-backed definition cook failed: %r / %r" % (track.errors(), output.errors()))

    removed_embedded = False
    for definition in tuple(track.type().allInstalledDefinitions()):
        if definition.libraryFilePath() == "Embedded":
            definition.destroy()
            removed_embedded = True

    track.matchCurrentDefinition()
    hou.hipFile.save()

    return {
        "track": track.path(),
        "target_hda": target_path,
        "backup_hda": backup_path,
        "used_allow_editing": used_allow_editing,
        "removed_embedded": removed_embedded,
        "definition": track.type().definition().libraryFilePath(),
        "hip": hou.hipFile.path(),
        "hip_unsaved": hou.hipFile.hasUnsavedChanges(),
        "warnings": list(track.warnings()) + list(output.warnings()),
        "errors": list(track.errors()) + list(output.errors()),
    }


if __name__ == "__main__":
    print(apply_patch())
