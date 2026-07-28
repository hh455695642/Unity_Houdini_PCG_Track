"""Incrementally make Terrain HDA track binding fail closed.

This migration intentionally edits only the existing pcgbike::Terrain::1.0
definition. It never clears or saves the current HIP and never rebuilds the
Terrain network from a builder script.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import struct
import tempfile
from datetime import datetime

import hou


PROJECT_ROOT = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..", "..", "..", "..")
)
TERRAIN_HDA_PATH = os.path.join(PROJECT_ROOT, "Assets", "PCG", "HDA", "Terrain.hda")
BACKUP_DIR = os.path.join(PROJECT_ROOT, "Assets", "PCG", "HDA", "backup")
TYPE_NAME = "pcgbike::Terrain::1.0"

TRACK_PATH_PARM = "track_display_sop_path"
TRACK_ENABLED_PARM = "track_binding_enabled"

TRACK_OBJECT_MERGE = "TerrainCore/00_TRACK_INPUT/IN_track_geometry"
TRACK_VALIDATE = "TerrainCore/00_TRACK_INPUT/TRACK_validate_contract"
BASE_OUTPUT = "TerrainCore/10_TERRAIN_SOURCE/OUT_BASE_HEIGHTFIELD"
FINAL_OUTPUT = "TerrainCore/OUT_TERRAIN_HEIGHTFIELD"
EARTHWORK = "TerrainCore/40_CONFORM_EARTHWORK"
TRACK_CONTEXT = EARTHWORK + "/TRACK_CONTEXT_blend"
TRACK_CONTEXT_SWITCH = EARTHWORK + "/TRACK_CONTEXT_enable_switch"
PREP_MASKS = EARTHWORK + "/PREP_contract_mask_layers"
ADAPTIVE_SWITCH = EARTHWORK + "/ADAPTIVE_enable_switch"
METADATA = "TerrainCore/70_OUTPUT/METADATA_write_contract"

TRACK_OBJECT_EXPRESSION = (
    'ifs(ch("../../../track_binding_enabled")!=0'
    ' && strlen(chs("../../../track_display_sop_path"))>0'
    ' && opexist(chs("../../../track_display_sop_path")),'
    ' chs("../../../track_display_sop_path"),'
    ' ifs(strlen(chs("../../../track_geometry"))>0'
    ' && opexist(chs("../../../track_geometry")),'
    ' chs("../../../track_geometry"),'
    ' ifs(strlen(opinputpath("../../..",0))>0'
    ' && opexist(opinputpath("../../..",0)),'
    ' opinputpath("../../..",0),"../EMPTY_TRACK_FALLBACK")))'
)

VALID_WARNING_OLD = (
    '"Input 0 invalid: Manual Domain active and conform disabled."'
)
VALID_WARNING_NEW = (
    '"Track input unavailable; generated base terrain without track deformation."'
)

BINDING_HELP = (
    "自动 Track Binding 由 Unity 组件管理：删除、禁用或解绑 Track 时会恢复基础地形。"
    "下方 Conform、Track Context、Adaptive Earthwork 仅用于形变调参，不是解绑入口。"
)


def _definition() -> hou.HDADefinition:
    path = os.path.abspath(TERRAIN_HDA_PATH).replace("\\", "/")
    definitions = hou.hda.definitionsInFile(path)
    match = next((item for item in definitions if item.nodeTypeName() == TYPE_NAME), None)
    if match is None:
        raise RuntimeError("Missing %s in %s" % (TYPE_NAME, path))
    return match


def _backup(persistent: bool) -> str:
    source = os.path.abspath(TERRAIN_HDA_PATH)
    if not persistent:
        file_descriptor, target = tempfile.mkstemp(
            prefix="Terrain_binding_dry_run_",
            suffix=".hda",
        )
        os.close(file_descriptor)
        shutil.copy2(source, target)
        return target

    os.makedirs(BACKUP_DIR, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    target = os.path.join(BACKUP_DIR, "Terrain_bak_%s.hda" % stamp)
    shutil.copy2(source, target)
    return target


def _add_parameter_contract(terrain: hou.Node) -> None:
    group = terrain.parmTemplateGroup()

    if group.find(TRACK_ENABLED_PARM) is None:
        enabled = hou.ToggleParmTemplate(
            TRACK_ENABLED_PARM,
            "Track Binding Enabled (Internal)",
            default_value=False,
            help=(
                "Internal Unity binding gate. When disabled, the hidden Display SOP "
                "path is ignored and public Track inputs remain available."
            ),
        )
        enabled.hide(True)
        group.append(enabled)

    if group.find("track_binding_workflow_note") is None:
        note = hou.LabelParmTemplate(
            "track_binding_workflow_note",
            BINDING_HELP,
            column_labels=(),
        )
        folder_indices = group.containingFolderIndices("track_geometry")
        if not folder_indices:
            raise RuntimeError("Track Geometry parameter is not in a folder")
        folder = group.entries()[folder_indices[0]]
        children = list(folder.parmTemplates())
        insert_at = next(
            (index + 1 for index, item in enumerate(children)
             if item.name() == "track_geometry"),
            len(children),
        )
        children.insert(insert_at, note)
        replacement = hou.FolderParmTemplate(
            folder.name(),
            folder.label(),
            folder_type=folder.folderType(),
            ends_tab_group=folder.endsTabGroup(),
            tags=folder.tags(),
        )
        replacement.setParmTemplates(children)
        group.replace(folder.name(), replacement)

    definition = terrain.type().definition()
    if definition is None:
        raise RuntimeError("Terrain instance has no definition")
    definition.setParmTemplateGroup(group)


def _require_node(terrain: hou.Node, relative_path: str) -> hou.Node:
    node = terrain.node(relative_path)
    if node is None:
        raise RuntimeError("Missing node: %s" % relative_path)
    return node


def _patch_nodes(terrain: hou.Node) -> None:
    object_merge = _require_node(terrain, TRACK_OBJECT_MERGE)
    object_merge.parm("objpath1").setExpression(
        TRACK_OBJECT_EXPRESSION,
        language=hou.exprLanguage.Hscript,
    )

    validate = _require_node(terrain, TRACK_VALIDATE)
    snippet = validate.parm("snippet").eval()
    if VALID_WARNING_OLD in snippet:
        snippet = snippet.replace(VALID_WARNING_OLD, VALID_WARNING_NEW)
    elif VALID_WARNING_NEW not in snippet:
        raise RuntimeError("Unexpected Track validation warning implementation")
    validate.parm("snippet").set(snippet)

    adaptive = _require_node(terrain, ADAPTIVE_SWITCH)
    adaptive.parm("input").setExpression(
        'ch("../../../enable_adaptive_earthwork")'
        ' && detail("../../00_TRACK_INPUT/TRACK_validate_contract",'
        '"terrain_input_valid",0)',
        language=hou.exprLanguage.Hscript,
    )

    earthwork = _require_node(terrain, EARTHWORK)
    context = _require_node(terrain, TRACK_CONTEXT)
    prep = _require_node(terrain, PREP_MASKS)
    context_switch = terrain.node(TRACK_CONTEXT_SWITCH)
    if context_switch is None:
        context_switch = earthwork.createNode("switch", "TRACK_CONTEXT_enable_switch")
        context_switch.setColor(hou.Color((0.32, 0.55, 0.32)))
        context_switch.setComment(
            "No valid Track: bypass Track Context completely and preserve base terrain."
        )
        context_switch.setGenericFlag(hou.nodeFlag.DisplayComment, True)
        context_switch.setPosition(context.position() + hou.Vector2((2.2, -0.2)))

    context_connections = context.inputConnections()
    if not context_connections:
        raise RuntimeError("Track Context has no base terrain input")
    # inputConnections() resolves subnet inputs to their external nodes, which
    # cannot be wired directly inside the subnet. This input is deliberately
    # the fourth 40_CONFORM_EARTHWORK connector (lake-constrained base terrain).
    earthwork_inputs = earthwork.indirectInputs()
    if len(earthwork_inputs) < 4:
        raise RuntimeError("Earthwork subnet is missing its base terrain input")
    context_switch.setInput(0, earthwork_inputs[3])
    context_switch.setInput(1, context)
    context_switch.parm("input").setExpression(
        'ch("../../../enable_track_context")'
        ' && detail("../../00_TRACK_INPUT/TRACK_validate_contract",'
        '"terrain_input_valid",0)',
        language=hou.exprLanguage.Hscript,
    )
    prep.setInput(0, context_switch)

    metadata = _require_node(terrain, METADATA)
    snippet = metadata.parm("snippet").eval()
    snippet = snippet.replace(
        '// Terrain Metadata v1.10',
        '// Terrain Metadata v1.11',
    ).replace(
        's@terrain_contract_version = "1.10";',
        's@terrain_contract_version = "1.11";',
    )
    binding_line = (
        'i@terrain_track_binding_enabled = chi("../../../track_binding_enabled");'
    )
    if binding_line not in snippet:
        anchor = 'i@terrain_input_valid = detail(2, "terrain_input_valid", 0);'
        if anchor not in snippet:
            raise RuntimeError("Unexpected Terrain metadata contract")
        snippet = snippet.replace(anchor, anchor + "\n" + binding_line)
    metadata.parm("snippet").set(snippet)


def _height_hash(node: hou.Node) -> str:
    try:
        node.cook(force=True)
    except hou.OperationFailed as exception:
        parent_hda = node
        while parent_hda is not None and parent_hda.type().name() != TYPE_NAME:
            parent_hda = parent_hda.parent()
        errors = _cook_errors(parent_hda) if parent_hda is not None else list(node.errors())
        raise RuntimeError(
            "Cook failed at %s: %s; %s" % (node.path(), exception, errors)
        ) from exception
    geometry = node.geometry()
    height = next(
        (
            prim
            for prim in geometry.prims()
            if prim.type() in (hou.primType.Volume, hou.primType.VDB)
            and prim.attribValue("name") == "height"
        ),
        None,
    )
    if height is None:
        raise RuntimeError("No height volume at %s" % node.path())

    digest = hashlib.sha256()
    for value in height.allVoxels():
        digest.update(struct.pack("<f", float(value)))
    return digest.hexdigest()


def _cook_errors(terrain: hou.Node) -> list[str]:
    errors = list(terrain.errors())
    for node in terrain.allSubChildren():
        errors.extend("%s: %s" % (node.path(), item) for item in node.errors())
    return errors


def _create_validation_track() -> hou.Node:
    container = hou.node("/obj").createNode("geo", "TerrainBindingValidationTrack")
    for child in container.children():
        child.destroy()
    curve = container.createNode("add", "OUT_TRACK")
    curve.parm("points").set(4)
    positions = (
        (-120.0, 42.0, -35.0),
        (-40.0, 42.0, 0.0),
        (40.0, 42.0, 0.0),
        (120.0, 42.0, 35.0),
    )
    for index, position in enumerate(positions):
        curve.parm("pt%dx" % index).set(position[0])
        curve.parm("pt%dy" % index).set(position[1])
        curve.parm("pt%dz" % index).set(position[2])
    curve.parm("prim0").set("0-3")
    curve.setDisplayFlag(True)
    curve.setRenderFlag(True)
    return curve


def _validate(terrain: hou.Node) -> dict:
    base = _require_node(terrain, BASE_OUTPUT)
    final = _require_node(terrain, FINAL_OUTPUT)
    adaptive = _require_node(terrain, ADAPTIVE_SWITCH)
    context_switch = _require_node(terrain, TRACK_CONTEXT_SWITCH)

    terrain.parm(TRACK_ENABLED_PARM).set(0)
    terrain.parm(TRACK_PATH_PARM).set("/obj/DeletedTrack/Road")
    terrain.parm("track_geometry").set("")
    final_hash = _height_hash(final)
    base_hash = _height_hash(base)
    if final_hash != base_hash:
        raise RuntimeError("Detached output does not exactly match base heightfield")
    if adaptive.parm("input").evalAsInt() != 0:
        raise RuntimeError("Adaptive Earthwork did not bypass without a Track")
    if context_switch.parm("input").evalAsInt() != 0:
        raise RuntimeError("Track Context did not bypass without a Track")

    terrain.parm(TRACK_ENABLED_PARM).set(1)
    stale_hash = _height_hash(final)
    if stale_hash != base_hash:
        raise RuntimeError("Invalid auto-binding path did not fall back to base")

    errors = _cook_errors(terrain)
    if errors:
        raise RuntimeError("Terrain cook errors: %s" % errors)

    object_merge = _require_node(terrain, TRACK_OBJECT_MERGE)
    resolved_path = object_merge.parm("objpath1").eval()
    if not resolved_path.endswith("EMPTY_TRACK_FALLBACK"):
        raise RuntimeError("Invalid path resolved to %s" % resolved_path)

    validation_track = _create_validation_track()
    try:
        terrain.parm(TRACK_PATH_PARM).set(validation_track.path())
        terrain.parm(TRACK_ENABLED_PARM).set(1)
        valid_base_hash = _height_hash(base)
        valid_track_hash = _height_hash(final)
        validate = _require_node(terrain, TRACK_VALIDATE)
        validate.cook(force=True)
        input_valid = int(
            validate.geometry().attribValue("terrain_input_valid")
        )
        if input_valid != 1:
            raise RuntimeError("Validation Track was not accepted by the Terrain contract")
        if valid_track_hash == valid_base_hash:
            raise RuntimeError("Enabled valid Track did not deform the Terrain")

        terrain.parm(TRACK_ENABLED_PARM).set(0)
        detached_valid_base_hash = _height_hash(base)
        detached_valid_hash = _height_hash(final)
        if detached_valid_hash != detached_valid_base_hash:
            raise RuntimeError("Disabling a valid binding did not restore base Terrain")
    finally:
        validation_track.parent().destroy()

    return {
        "base_height_sha256": base_hash,
        "detached_height_sha256": final_hash,
        "invalid_path_height_sha256": stale_hash,
        "valid_track_base_sha256": valid_base_hash,
        "valid_track_deformed_sha256": valid_track_hash,
        "valid_track_detached_base_sha256": detached_valid_base_hash,
        "valid_track_detached_sha256": detached_valid_hash,
        "valid_track_input_valid": input_valid,
        "adaptive_branch": adaptive.parm("input").evalAsInt(),
        "track_context_branch": context_switch.parm("input").evalAsInt(),
        "resolved_invalid_path": resolved_path,
        "errors": errors,
        "warnings": list(terrain.warnings()),
    }


def apply_patch(dry_run: bool) -> dict:
    source_path = os.path.abspath(TERRAIN_HDA_PATH)
    backup_path = _backup(persistent=not dry_run)
    hou.hda.installFile(source_path)

    # Existing adaptive feedback expressions are instance-path based and expect
    # the production object name. Keep the validation instance identical.
    terrain = hou.node("/obj").createNode(TYPE_NAME, "Terrain1")
    used_allow_editing = False
    try:
        if not terrain.isEditable():
            terrain.allowEditingOfContents()
            used_allow_editing = True

        _add_parameter_contract(terrain)
        _patch_nodes(terrain)
        validation = _validate(terrain)

        if dry_run:
            shutil.copy2(backup_path, source_path)
            saved = False
        else:
            definition = terrain.type().definition()
            definition.save(
                source_path.replace("\\", "/"),
                template_node=terrain,
                create_backup=False,
            )
            saved = True

        result = {
            "dry_run": dry_run,
            "saved": saved,
            "target_hda": source_path,
            "backup_hda": None if dry_run else backup_path,
            "used_allow_editing": used_allow_editing,
            "hip_saved": False,
            "validation": validation,
        }
        return result
    except Exception:
        shutil.copy2(backup_path, source_path)
        raise
    finally:
        terrain.destroy()
        if dry_run and os.path.exists(backup_path):
            os.remove(backup_path)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true")
    arguments = parser.parse_args()
    print(json.dumps(apply_patch(arguments.dry_run), ensure_ascii=False, indent=2))
