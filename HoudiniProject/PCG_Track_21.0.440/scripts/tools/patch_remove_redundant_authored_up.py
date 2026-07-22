"""Remove the bypassed authored-up normalizer and rename visible banking terms.

The current editable /obj/Track1 network is the source of truth.  This patch
only reconnects the two consumers of the bypassed node, removes that node,
renames user-facing labels/comments to Track Lateral Tilt / 赛道横倾, verifies
geometry equivalence, and saves the live network back to Track.hda. Internal
bank_* and road_bank_* contracts remain unchanged.
"""

from __future__ import annotations

import hashlib
import json
import os
from datetime import datetime

import hrpyc


PROJECT_ROOT = "E:/HoudiniProject/Unity_Houdini_PCG_Track"
TRACK_NODE_PATH = "/obj/Track1"
TRACK_TYPE_NAME = "pcgbike::Track::1.0"
TRACK_HDA_PATH = PROJECT_ROOT + "/Assets/PCG/HDA/Track.hda"
TRACK_BACKUP_DIR = PROJECT_ROOT + "/Assets/PCG/HDA/backup"
TARGET_NODE_PATH = "Road/FRAME_normalize_authored_up"
UPSTREAM_NODE_PATH = "Road/CENTERLINE_sampling_switch"
EXPECTED_CONSUMERS = {
    "Road/FRAME_compute_grade_bank": (1,),
    "Road/CENTERLINE_polyframe": (0,),
}
VISIBLE_PARAMETER_UPDATES = {
    "enable_track_lateral_tilt": (
        "Enable Track Lateral Tilt / 启用赛道横倾",
        "兼容开关。关闭时不修改现有道路顶点位置，但仍输出坡度与赛道 Frame metadata。",
    ),
    "lateral_tilt_use_spline_knot_tilt": (
        "Use Spline Knot Tilt / 使用样条控制点横倾",
        "读取 Unity Spline Knot 绕曲线切线的横滚，换算为赛道横倾并与自动横倾相加。仅影响编辑器 Cook/Bake。",
    ),
    "lateral_tilt_design_speed_kph": (
        "Design Speed (km/h) / 设计速度",
        "自动横倾的目标设计速度；使用 atan(v² / gR) 计算，不参与移动端运行时。",
    ),
    "lateral_tilt_auto_strength": (
        "Auto Lateral Tilt Strength / 自动横倾强度",
        "自动横倾倍率。0 关闭曲率驱动的自动横倾，仅保留 Spline Knot 横倾。",
    ),
    "lateral_tilt_max_angle_deg": (
        "Maximum Lateral Tilt Angle (deg) / 最大横倾角",
        "自动横倾与 Spline Knot 横倾叠加后的绝对横倾角上限；移动端建议保持在 12 度以内。",
    ),
    "lateral_tilt_transition_length_m": (
        "Transition Length (m) / 过渡长度",
        "按道路真实距离平滑，并限制每米横倾角变化率。",
    ),
    "adaptive_max_lateral_tilt_delta_deg": (
        "Maximum Lateral Tilt Delta (deg) / 最大横倾变化",
        None,
    ),
}
VISIBLE_NODE_COMMENTS = {
    "SURFACE_reproject_layout": "保持美术采样中心线不变；重建道路横截面并写入距离、横倾兼容数据与只读急弯诊断，再交给最终横倾 Frame 计算。",
    "FRAME_compute_grade_bank": "基于最终中心线计算三维切线、纵坡、曲率与赛道横倾。第二输入直接读取采样中心线中的 authored-up 数据。",
    "FRAME_apply_grade_bank": "使用最终 tangent/lateral/up 重建道路横截面；关闭赛道横倾时不修改输入顶点。",
    "CENTERLINE_quality_metrics": "计算中心线质量指标，并输出 Spline Knot 横倾和 Lateral Tilt Target。",
    "CENTERLINE_extract_final": "从最终横倾表面提取中心线与稳定 metadata。",
    "OUT_ROAD_CENTERLINE": "输出道路中心线、坡度、曲率与横倾 metadata。",
}
PARAMETER_CONTRACT_NAMES = tuple(VISIBLE_PARAMETER_UPDATES)


def _json_value(value):
    if isinstance(value, (tuple, list)):
        return [_json_value(item) for item in value]
    if isinstance(value, (int, float, str, bool)) or value is None:
        return value
    return str(value)


def _attrib_values(hou, geometry, owner, attrib):
    name = attrib.name()
    data_type = attrib.dataType()
    if owner == "point":
        if data_type == hou.attribData.Float:
            return list(geometry.pointFloatAttribValues(name))
        if data_type == hou.attribData.Int:
            return list(geometry.pointIntAttribValues(name))
        if data_type == hou.attribData.String:
            return list(geometry.pointStringAttribValues(name))
    if owner == "primitive":
        if data_type == hou.attribData.Float:
            return list(geometry.primFloatAttribValues(name))
        if data_type == hou.attribData.Int:
            return list(geometry.primIntAttribValues(name))
        if data_type == hou.attribData.String:
            return list(geometry.primStringAttribValues(name))
    raise RuntimeError("Unsupported %s attribute type for %s" % (owner, name))


def _geometry_signature(hou, output):
    output.cook(force=True)
    geometry = output.geometry()
    if geometry is None:
        raise RuntimeError("OUT_ROAD_MESH produced no geometry")

    payload = {
        "point_count": len(geometry.points()),
        "primitive_count": len(geometry.prims()),
        "topology": [
            [vertex.point().number() for vertex in primitive.vertices()]
            for primitive in geometry.prims()
        ],
        "point_attributes": {
            attrib.name(): _attrib_values(hou, geometry, "point", attrib)
            for attrib in geometry.pointAttribs()
        },
        "primitive_attributes": {
            attrib.name(): _attrib_values(hou, geometry, "primitive", attrib)
            for attrib in geometry.primAttribs()
        },
        "detail_attributes": {
            attrib.name(): _json_value(geometry.attribValue(attrib))
            for attrib in geometry.globalAttribs()
        },
        "point_groups": {
            group.name(): [point.number() for point in group.points()]
            for group in geometry.pointGroups()
        },
        "primitive_groups": {
            group.name(): [primitive.number() for primitive in group.prims()]
            for group in geometry.primGroups()
        },
    }
    serialized = json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return {
        "sha256": hashlib.sha256(serialized).hexdigest(),
        "points": payload["point_count"],
        "primitives": payload["primitive_count"],
    }


def _backup_definition(track):
    os.makedirs(TRACK_BACKUP_DIR, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    path = TRACK_BACKUP_DIR + "/Track_bak_remove_authored_up_" + timestamp + ".hda"
    track.type().definition().copyToHDAFile(path)
    return path


def _parameter_contract(definition, track):
    """Capture values and compatibility-sensitive template fields, not UI text."""
    group = definition.parmTemplateGroup()
    result = {}
    for name in PARAMETER_CONTRACT_NAMES:
        template = group.find(name)
        parm = track.parm(name)
        if template is None or parm is None:
            raise RuntimeError("Missing parameter contract: %s" % name)
        try:
            expression = parm.expression()
        except Exception:
            expression = None
        result[name] = {
            "name": template.name(),
            "default": _json_value(template.defaultValue()),
            "conditionals": {
                str(key): str(value)
                for key, value in template.conditionals().items()
            },
            "value": _json_value(parm.eval()),
            "expression": expression,
        }
    return result


def _update_visible_interface(definition):
    group = definition.parmTemplateGroup()
    folder = group.find("stdswitcher19_5")
    if folder is None or not any(
        child.name() == "enable_track_lateral_tilt" for child in folder.parmTemplates()
    ):
        raise RuntimeError("Could not locate the existing lateral-tilt folder")
    folder.setLabel("Track Lateral Tilt / 赛道横倾")
    folder.setHelp("在编辑器 Cook/Bake 阶段计算曲率驱动与样条控制点驱动的赛道横倾；内部 bank_* 与 road_bank_* 合约保持不变。")
    group.replace(folder.name(), folder)

    for name, (label, help_text) in VISIBLE_PARAMETER_UPDATES.items():
        template = group.find(name)
        if template is None:
            raise RuntimeError("Missing parameter template: %s" % name)
        template.setLabel(label)
        if help_text is not None:
            template.setHelp(help_text)
        elif name == "adaptive_max_lateral_tilt_delta_deg":
            template.setHelp("限制相邻自适应采样点之间允许的最大赛道横倾角变化。")
        group.replace(name, template)

    detail_density = group.find("adaptive_detail_density")
    if detail_density is not None:
        detail_density.setHelp(
            detail_density.help().replace("bank detail", "lateral-tilt detail")
        )
        group.replace("adaptive_detail_density", detail_density)
    definition.setParmTemplateGroup(group)


def _update_visible_annotations(road):
    for name, comment in VISIBLE_NODE_COMMENTS.items():
        node = road.node(name)
        if node is None:
            raise RuntimeError("Missing annotated node: %s" % name)
        node.setComment(comment)

    box = next(
        (item for item in road.networkBoxes() if item.name() == "BOX_04_LAYOUT_BANKING"),
        None,
    )
    if box is None:
        raise RuntimeError("Missing BOX_04_LAYOUT_BANKING")
    box.setComment("04 Layout 与 Lateral Tilt｜中心线修正、最终 Frame 和 Debug")

    note = next(
        (item for item in road.stickyNotes() if item.name() == "ROAD_PIPELINE_GUIDE"),
        None,
    )
    if note is None:
        raise RuntimeError("Missing ROAD_PIPELINE_GUIDE")
    note.setText(
        note.text()
        .replace("Legacy Banking", "Lateral Tilt")
        .replace("Banking", "Lateral Tilt")
    )


def _snapshot_full_parameter_state(hou, track):
    state = []
    for parm in track.parms():
        if parm.parmTemplate().type() == hou.parmTemplateType.Button:
            continue
        try:
            raw_value = parm.rawValue()
        except Exception:
            raw_value = None
        try:
            value = parm.eval()
        except Exception:
            value = None
        state.append(
            {
                "name": parm.name(),
                "raw_value": raw_value,
                "value": value,
                "keyframes": tuple(parm.keyframes()),
            }
        )
    return state


def _parameter_state_signature(state):
    return tuple(
        (
            item["name"],
            item["raw_value"],
            repr(item["value"]),
            tuple(repr(keyframe) for keyframe in item["keyframes"]),
        )
        for item in state
    )


def _restore_full_parameter_state(track, state):
    # Restore scalar/multiparm counts first. Re-fetch by name each time because
    # changing a multiparm count can recreate its instance parameters.
    for item in state:
        if item["keyframes"]:
            continue
        parm = track.parm(item["name"])
        if parm is None:
            raise RuntimeError("Parameter disappeared while restoring: %s" % item["name"])
        try:
            parm.set(item["raw_value"])
        except Exception:
            parm.set(item["value"])
    for item in state:
        if not item["keyframes"]:
            continue
        parm = track.parm(item["name"])
        if parm is None:
            raise RuntimeError("Animated parameter disappeared: %s" % item["name"])
        parm.deleteAllKeyframes()
        parm.setKeyframes(item["keyframes"])


def apply_patch_in_session(hou):
    if os.path.normcase(hou.hipFile.path()) != os.path.normcase(
        PROJECT_ROOT + "/HoudiniProject/PCG_Track_21.0.440/PCG_Bike_Track.hip"
    ):
        raise RuntimeError("Unexpected HIP: %s" % hou.hipFile.path())

    candidates = [
        node
        for node in hou.node("/obj").children()
        if node.type().name() == TRACK_TYPE_NAME
    ]
    if len(candidates) != 1 or candidates[0].path() != TRACK_NODE_PATH:
        raise RuntimeError(
            "Expected exactly %s at %s; found %s"
            % (TRACK_TYPE_NAME, TRACK_NODE_PATH, [node.path() for node in candidates])
        )

    track = candidates[0]
    definition = track.type().definition()
    if definition is None or os.path.normcase(definition.libraryFilePath()) != os.path.normcase(
        TRACK_HDA_PATH
    ):
        raise RuntimeError("Track definition is not bound to %s" % TRACK_HDA_PATH)

    target = track.node(TARGET_NODE_PATH)
    upstream = track.node(UPSTREAM_NODE_PATH)
    output = track.node("Road/OUT_ROAD_MESH")
    if target is None or upstream is None or output is None:
        raise RuntimeError("Required cleanup nodes are missing")
    if target.type().name() != "attribwrangle" or not target.isBypassed():
        raise RuntimeError("Target is no longer the expected bypassed Attribute Wrangle")
    if tuple(target.inputs()) != (upstream,):
        raise RuntimeError("Unexpected target input: %s" % [node.path() for node in target.inputs()])

    expected_outputs = {track.node(path) for path in EXPECTED_CONSUMERS}
    if set(target.outputs()) != expected_outputs or None in expected_outputs:
        raise RuntimeError(
            "Unexpected target outputs: %s" % [node.path() for node in target.outputs()]
        )
    for path, indexes in EXPECTED_CONSUMERS.items():
        consumer = track.node(path)
        for index in indexes:
            if consumer.input(index) != target:
                raise RuntimeError("Unexpected connection at %s input %d" % (path, index))

    hip_backup = hou.hipFile.saveAsBackup()
    hda_backup = _backup_definition(track)
    before = _geometry_signature(hou, output)
    parameter_contract_before = _parameter_contract(definition, track)
    # Updating a definition's ParmTemplateGroup can reset non-default values on
    # live instances (for example enable_adaptive_sampling). Preserve the full
    # live parameter state, not only the lateral-tilt parameters.
    full_parameter_state = _snapshot_full_parameter_state(hou, track)
    full_parameter_signature = _parameter_state_signature(full_parameter_state)

    used_allow_editing = False
    if not track.isEditable():
        track.allowEditingOfContents()
        used_allow_editing = True

    for path, indexes in EXPECTED_CONSUMERS.items():
        consumer = track.node(path)
        for index in indexes:
            consumer.setInput(index, upstream)
    target.destroy()
    _update_visible_interface(definition)
    _restore_full_parameter_state(track, full_parameter_state)
    _update_visible_annotations(track.node("Road"))

    full_parameter_signature_after_ui = _parameter_state_signature(
        _snapshot_full_parameter_state(hou, track)
    )
    if full_parameter_signature != full_parameter_signature_after_ui:
        raise RuntimeError("Live Track parameter state changed while updating UI labels")

    parameter_contract_after_ui = _parameter_contract(definition, track)
    if parameter_contract_before != parameter_contract_after_ui:
        raise RuntimeError(
            "Internal parameter contract changed: before=%r after=%r"
            % (parameter_contract_before, parameter_contract_after_ui)
        )

    after_live = _geometry_signature(hou, output)
    if before != after_live:
        raise RuntimeError(
            "Geometry changed after removing bypassed node: before=%r after=%r"
            % (before, after_live)
        )
    if track.errors() or output.errors():
        raise RuntimeError("Cook failed: %r / %r" % (track.errors(), output.errors()))

    definition.save(TRACK_HDA_PATH, template_node=track, create_backup=True)
    hou.hda.installFile(TRACK_HDA_PATH)
    installed_definition = next(
        item
        for item in hou.hda.definitionsInFile(TRACK_HDA_PATH)
        if item.nodeTypeName() == TRACK_TYPE_NAME
    )
    installed_definition.setIsPreferred(True)

    # Re-open the saved contents so the user's Live Scene editing workflow is
    # preserved after synchronizing the definition.
    track.matchCurrentDefinition()
    track.allowEditingOfContents()
    hou.hipFile.save()

    output = track.node("Road/OUT_ROAD_MESH")
    after_saved = _geometry_signature(hou, output)
    if before != after_saved:
        raise RuntimeError(
            "Saved HDA geometry differs from the pre-patch result: before=%r after=%r"
            % (before, after_saved)
        )
    if track.node(TARGET_NODE_PATH) is not None:
        raise RuntimeError("Target node still exists after saving the definition")
    for path, indexes in EXPECTED_CONSUMERS.items():
        consumer = track.node(path)
        for index in indexes:
            if consumer.input(index) != track.node(UPSTREAM_NODE_PATH):
                raise RuntimeError("Saved connection mismatch at %s input %d" % (path, index))
    if track.errors() or output.errors():
        raise RuntimeError("Post-save cook failed: %r / %r" % (track.errors(), output.errors()))
    parameter_contract_after_saved = _parameter_contract(track.type().definition(), track)
    if parameter_contract_before != parameter_contract_after_saved:
        raise RuntimeError("Saved parameter contract differs from the live baseline")

    hou.hipFile.save()
    return {
        "hip": hou.hipFile.path(),
        "hip_backup": hip_backup,
        "hda": track.type().definition().libraryFilePath(),
        "hda_backup": hda_backup,
        "removed_node": TRACK_NODE_PATH + "/" + TARGET_NODE_PATH,
        "upstream": TRACK_NODE_PATH + "/" + UPSTREAM_NODE_PATH,
        "rewired": {
            TRACK_NODE_PATH + "/" + path: list(indexes)
            for path, indexes in EXPECTED_CONSUMERS.items()
        },
        "used_allow_editing": used_allow_editing,
        "left_editable": track.isEditable(),
        "geometry": after_saved,
        "parameter_contract_preserved": True,
        "folder_label": track.type().definition().parmTemplateGroup().find("stdswitcher19_5").label(),
        "errors": list(track.errors()) + list(output.errors()),
        "warnings": list(track.warnings()) + list(output.warnings()),
        "hip_unsaved": hou.hipFile.hasUnsavedChanges(),
    }


def apply_patch():
    connection, _remote_hou = hrpyc.import_remote_module("127.0.0.1", 18811, "hou")
    script_path = os.path.abspath(__file__).replace("\\", "/")
    remote_code = (
        "import hou\n"
        "_remove_authored_up_namespace = {'__name__': 'remove_authored_up_remote'}\n"
        "exec(compile(open(%r, encoding='utf-8').read(), %r, 'exec'), "
        "_remove_authored_up_namespace)\n"
        "REMOVE_AUTHORED_UP_RESULT = "
        "_remove_authored_up_namespace['apply_patch_in_session'](hou)\n"
    ) % (script_path, script_path)
    connection.execute(remote_code)
    return connection.eval(
        "__import__('json').dumps(REMOVE_AUTHORED_UP_RESULT, ensure_ascii=False)"
    )


if __name__ == "__main__":
    print("REMOVE_AUTHORED_UP_RESULT=" + apply_patch())
