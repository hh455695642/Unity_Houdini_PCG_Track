"""Rename Track lateral-tilt HDA parameters without changing output metadata.

The editable /obj/Track1 instance is the source of truth. This incremental
patch preserves every live parameter value, updates channel references, checks
full geometry equivalence, and saves the result back to the existing Track.hda.
"""

from __future__ import annotations

import hashlib
import json
import os
from datetime import datetime

import hrpyc


PROJECT_ROOT = "E:/HoudiniProject/Unity_Houdini_PCG_Track"
HIP_PATH = PROJECT_ROOT + "/HoudiniProject/PCG_Track_21.0.440/PCG_Bike_Track.hip"
TRACK_NODE_PATH = "/obj/Track1"
TRACK_TYPE_NAME = "pcgbike::Track::1.0"
TRACK_HDA_PATH = PROJECT_ROOT + "/Assets/PCG/HDA/Track.hda"
TRACK_BACKUP_DIR = PROJECT_ROOT + "/Assets/PCG/HDA/backup"

RENAME_MAP = {
    "enable_road_banking": "enable_track_lateral_tilt",
    "bank_use_spline_knot_roll": "lateral_tilt_use_spline_knot_tilt",
    "bank_design_speed_kph": "lateral_tilt_design_speed_kph",
    "bank_auto_strength": "lateral_tilt_auto_strength",
    "bank_max_angle_deg": "lateral_tilt_max_angle_deg",
    "bank_transition_length_m": "lateral_tilt_transition_length_m",
    "adaptive_max_bank_delta_deg": "adaptive_max_lateral_tilt_delta_deg",
    "debug_bank_frames": "debug_lateral_tilt_frames",
}
DISABLED_WITH_FEATURE = {
    "lateral_tilt_use_spline_knot_tilt",
    "lateral_tilt_design_speed_kph",
    "lateral_tilt_auto_strength",
    "lateral_tilt_max_angle_deg",
    "lateral_tilt_transition_length_m",
}


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
        payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    return {
        "sha256": hashlib.sha256(serialized).hexdigest(),
        "points": payload["point_count"],
        "primitives": payload["primitive_count"],
    }


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


def _parameter_state_signature(state, rename=None):
    rename = rename or {}
    return tuple(
        (
            rename.get(item["name"], item["name"]),
            item["raw_value"],
            repr(item["value"]),
            tuple(repr(keyframe) for keyframe in item["keyframes"]),
        )
        for item in state
    )


def _restore_full_parameter_state(track, state):
    for item in state:
        if item["keyframes"]:
            continue
        name = RENAME_MAP.get(item["name"], item["name"])
        parm = track.parm(name)
        if parm is None:
            raise RuntimeError("Parameter disappeared while restoring: %s" % name)
        try:
            parm.set(item["raw_value"])
        except Exception:
            parm.set(item["value"])
    for item in state:
        if not item["keyframes"]:
            continue
        name = RENAME_MAP.get(item["name"], item["name"])
        parm = track.parm(name)
        if parm is None:
            raise RuntimeError("Animated parameter disappeared: %s" % name)
        parm.deleteAllKeyframes()
        parm.setKeyframes(item["keyframes"])


def _backup_definition(track):
    os.makedirs(TRACK_BACKUP_DIR, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    path = TRACK_BACKUP_DIR + "/Track_bak_rename_lateral_tilt_params_" + timestamp + ".hda"
    track.type().definition().copyToHDAFile(path)
    return path


def _rename_channel_references(track):
    changed = []
    for node in track.allSubChildren():
        for parm in node.parms():
            try:
                raw = parm.rawValue()
            except Exception:
                continue
            updated = raw
            for old_name, new_name in RENAME_MAP.items():
                # Restrict replacement to HDA channel paths so road_bank_* output
                # metadata remains intentionally unchanged.
                updated = updated.replace("../../" + old_name, "../../" + new_name)
            if updated != raw:
                parm.set(updated)
                changed.append(parm.path())
    return changed


def _rename_parameter_templates(hou, definition):
    group = definition.parmTemplateGroup()
    renamed = []
    disable_when = "{ enable_track_lateral_tilt == 0 }"
    for old_name, new_name in RENAME_MAP.items():
        template = group.find(old_name)
        if template is None:
            if old_name == "debug_bank_frames":
                continue
            raise RuntimeError("Missing source parameter template: %s" % old_name)
        if group.find(new_name) is not None:
            raise RuntimeError("Destination parameter already exists: %s" % new_name)
        template.setName(new_name)
        if new_name in DISABLED_WITH_FEATURE:
            template.setConditional(hou.parmCondType.DisableWhen, disable_when)
        group.replace(old_name, template)
        renamed.append((old_name, new_name))
    definition.setParmTemplateGroup(group)
    return renamed


def apply_patch_in_session(hou):
    if os.path.normcase(hou.hipFile.path()) != os.path.normcase(HIP_PATH):
        raise RuntimeError("Unexpected HIP: %s" % hou.hipFile.path())
    candidates = [
        node for node in hou.node("/obj").children()
        if node.type().name() == TRACK_TYPE_NAME
    ]
    if len(candidates) != 1 or candidates[0].path() != TRACK_NODE_PATH:
        raise RuntimeError("Expected exactly one editable Track at %s" % TRACK_NODE_PATH)
    track = candidates[0]
    definition = track.type().definition()
    if definition is None or os.path.normcase(definition.libraryFilePath()) != os.path.normcase(TRACK_HDA_PATH):
        raise RuntimeError("Track definition is not bound to %s" % TRACK_HDA_PATH)
    output = track.node("Road/OUT_ROAD_MESH")
    if output is None:
        raise RuntimeError("Missing OUT_ROAD_MESH")

    hip_backup = hou.hipFile.saveAsBackup()
    hda_backup = _backup_definition(track)
    before_geometry = _geometry_signature(hou, output)
    before_state = _snapshot_full_parameter_state(hou, track)
    expected_state_signature = _parameter_state_signature(before_state, RENAME_MAP)

    used_allow_editing = False
    if not track.isEditable():
        track.allowEditingOfContents()
        used_allow_editing = True

    changed_references = _rename_channel_references(track)
    renamed_parameters = _rename_parameter_templates(hou, definition)
    _restore_full_parameter_state(track, before_state)

    after_state_signature = _parameter_state_signature(
        _snapshot_full_parameter_state(hou, track)
    )
    if expected_state_signature != after_state_signature:
        raise RuntimeError("Live parameter values changed during parameter rename")
    after_live_geometry = _geometry_signature(hou, output)
    if before_geometry != after_live_geometry:
        raise RuntimeError(
            "Geometry changed during parameter rename: before=%r after=%r"
            % (before_geometry, after_live_geometry)
        )
    if track.errors() or output.errors() or track.warnings() or output.warnings():
        raise RuntimeError(
            "Cook messages: errors=%r warnings=%r"
            % (track.errors() + output.errors(), track.warnings() + output.warnings())
        )

    definition.save(TRACK_HDA_PATH, template_node=track, create_backup=True)
    hou.hda.installFile(TRACK_HDA_PATH)
    installed_definition = next(
        item for item in hou.hda.definitionsInFile(TRACK_HDA_PATH)
        if item.nodeTypeName() == TRACK_TYPE_NAME
    )
    installed_definition.setIsPreferred(True)
    track.matchCurrentDefinition()
    track.allowEditingOfContents()
    hou.hipFile.save()

    output = track.node("Road/OUT_ROAD_MESH")
    after_saved_geometry = _geometry_signature(hou, output)
    if before_geometry != after_saved_geometry:
        raise RuntimeError("Saved HDA geometry differs from the pre-rename result")
    group = track.type().definition().parmTemplateGroup()
    for old_name, new_name in renamed_parameters:
        if group.find(old_name) is not None or track.parm(old_name) is not None:
            raise RuntimeError("Old parameter still exists: %s" % old_name)
        if group.find(new_name) is None or track.parm(new_name) is None:
            raise RuntimeError("Renamed parameter is missing: %s" % new_name)
    if track.errors() or output.errors() or track.warnings() or output.warnings():
        raise RuntimeError("Saved Track has cook errors or warnings")

    track.setCurrent(True, clear_all_selected=True)
    hou.hipFile.save()
    return {
        "hip": hou.hipFile.path(),
        "hip_backup": hip_backup,
        "hda": track.type().definition().libraryFilePath(),
        "hda_backup": hda_backup,
        "renamed_parameters": renamed_parameters,
        "changed_reference_parms": changed_references,
        "used_allow_editing": used_allow_editing,
        "left_editable": track.isEditable(),
        "selected": [node.path() for node in hou.selectedNodes()],
        "geometry": after_saved_geometry,
        "errors": list(track.errors()) + list(output.errors()),
        "warnings": list(track.warnings()) + list(output.warnings()),
        "hip_unsaved": hou.hipFile.hasUnsavedChanges(),
    }


def apply_patch():
    connection, _remote_hou = hrpyc.import_remote_module("127.0.0.1", 18811, "hou")
    script_path = os.path.abspath(__file__).replace("\\", "/")
    remote_code = (
        "import hou\n"
        "_rename_lateral_tilt_namespace = {'__name__': 'rename_lateral_tilt_remote'}\n"
        "exec(compile(open(%r, encoding='utf-8').read(), %r, 'exec'), "
        "_rename_lateral_tilt_namespace)\n"
        "RENAME_LATERAL_TILT_RESULT = "
        "_rename_lateral_tilt_namespace['apply_patch_in_session'](hou)\n"
    ) % (script_path, script_path)
    connection.execute(remote_code)
    return connection.eval(
        "__import__('json').dumps(RENAME_LATERAL_TILT_RESULT, ensure_ascii=False)"
    )


if __name__ == "__main__":
    print("RENAME_LATERAL_TILT_RESULT=" + apply_patch())
