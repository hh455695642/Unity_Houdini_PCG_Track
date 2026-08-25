"""Clean CityRoadCore overview annotations without changing geometry semantics.

The V46 hierarchy already stores detailed learning documentation in node
comments.  V47 stops displaying every comment at once, removes obsolete
top-level Sticky Notes left by earlier flat layouts, and keeps one compact
reading card per navigation level.  This patch is idempotent and save=False.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

try:
    import hou  # type: ignore
except ImportError:
    hou = None


ASSET_PATH = "/obj/CityRoad_DEV"
ASSET_TYPE = "pcgbike::CityRoad::1.0"
CORE_PATH = "CityRoadCore"
MAIN_NAME = "CR_MAIN_PIPELINE"
V46_MARKER = "CITYROAD_THREE_LEVEL_READABILITY_V46_20260824"
MARKER = "CITYROAD_ANNOTATION_CLARITY_V47_20260824"
SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = SCRIPT_DIR.parents[3]
EXPECTED_HIP = PROJECT_ROOT / "HoudiniProject/PCG_Track_21.0.440/PCG_Bike_CityRoad.hip"
EXPECTED_HDA = PROJECT_ROOT / "Assets/PCG/HDA/City/CityRoad.hda"

TOP_NOTE = {
    "name": "NOTE_V47_OVERVIEW",
    "position": (-20.0, 30.0),
    "size": (34.0, 5.0),
    "text": (
        "CityRoadCore｜总览\n"
        "CR_MAIN_PIPELINE：道路主链　CR_CITY_PARK：独立公园分支\n"
        "OUT_*：正式输出；双击 MAIN 后按 01→05 向下阅读。"
    ),
    "color": (0.16, 0.23, 0.32),
}

MAIN_NOTE = {
    "name": "NOTE_V47_READING_GUIDE",
    "position": (-26.0, 65.0),
    "size": (39.0, 5.0),
    "text": (
        "阅读：01→02→03→04→05；双击 CR_* 查看实现。\n"
        "详细说明保留在节点 Comment 中，默认不常驻显示。\n"
        "黄色 Network Dot 只做线路路由；IN_LAB_* 仅用于 Debug。"
    ),
    "color": (0.16, 0.23, 0.32),
}

TOP_BOX_LABELS = {
    "OVERVIEW_MAIN": "MAIN PIPELINE",
    "OVERVIEW_ROAD_OUTPUTS": "ROAD + DEBUG OUTPUTS",
    "OVERVIEW_PARK": "CITY PARK",
}

MAIN_BOX_LABELS = {
    "AREA_STAGE_01_CONTEXT": "01 CONTEXT｜输入与索引",
    "AREA_STAGE_02_SURFACE_CONSTRAINTS": "02 SURFACE｜路面与约束",
    "AREA_STAGE_03_FINALIZE": "03 FINALIZE｜最终化与并行内容",
    "AREA_STAGE_04_CONTENT_OUTPUTS": "04 OUTPUTS｜标线与人行道",
    "AREA_MAIN_PUBLISH": "05 PUBLISH｜9 路正式接口",
}


def _norm(value) -> str:
    return str(value).replace("\\", "/").lower()


def _require_identity():
    asset = hou.node(ASSET_PATH)
    if asset is None or asset.type().name() != ASSET_TYPE:
        raise RuntimeError(f"Expected {ASSET_TYPE} at {ASSET_PATH}")
    definition = asset.type().definition()
    if definition is None or _norm(definition.libraryFilePath()) != _norm(EXPECTED_HDA):
        raise RuntimeError("Unexpected CityRoad HDA definition")
    if _norm(hou.hipFile.path()) != _norm(EXPECTED_HIP):
        raise RuntimeError("Unexpected CityRoad HIP")
    core = asset.node(CORE_PATH)
    main = core.node(MAIN_NAME) if core is not None else None
    if core is None or main is None:
        raise RuntimeError("V46 CityRoadCore hierarchy is missing")
    if core.userData("cityroad_three_level_readability_marker") != V46_MARKER:
        raise RuntimeError("V46 readability marker is missing")
    return asset, core, main


def _note_payload(note):
    return {
        "name": note.name(),
        "text": note.text(),
        "position": tuple(note.position()),
        "size": tuple(note.size()),
        "color": tuple(note.color().rgb()),
        "text_size": float(note.textSize()),
    }


def _snapshot(core, main):
    return {
        "core_notes": [_note_payload(note) for note in core.stickyNotes()],
        "main_notes": [_note_payload(note) for note in main.stickyNotes()],
        "core_flags": {node.name(): node.isGenericFlagSet(hou.nodeFlag.DisplayComment)
                       for node in core.children()},
        "main_flags": {node.name(): node.isGenericFlagSet(hou.nodeFlag.DisplayComment)
                       for node in main.children()},
        "core_boxes": {box.name(): box.comment() for box in core.networkBoxes()},
        "main_boxes": {box.name(): box.comment() for box in main.networkBoxes()},
        "marker": core.userData("cityroad_annotation_clarity_marker"),
    }


def _replace_notes(parent, spec):
    for note in list(parent.stickyNotes()):
        note.destroy()
    note = parent.createStickyNote()
    note.setName(spec["name"], unique_name=False)
    note.setPosition(hou.Vector2(spec["position"]))
    note.setSize(hou.Vector2(spec["size"]))
    note.setText(spec["text"])
    note.setTextSize(0.55)
    note.setColor(hou.Color(spec["color"]))


def _restore_notes(parent, payloads):
    for note in list(parent.stickyNotes()):
        note.destroy()
    for payload in payloads:
        note = parent.createStickyNote()
        note.setName(payload["name"], unique_name=False)
        note.setPosition(hou.Vector2(payload["position"]))
        note.setSize(hou.Vector2(payload["size"]))
        note.setText(payload["text"])
        note.setTextSize(payload["text_size"])
        note.setColor(hou.Color(payload["color"]))


def _set_box_labels(parent, labels):
    boxes = {box.name(): box for box in parent.networkBoxes()}
    if set(boxes) != set(labels):
        raise RuntimeError(f"Unexpected Network Box set at {parent.path()}: {sorted(boxes)}")
    for name, label in labels.items():
        boxes[name].setComment(label)


def _validate(core, main):
    core_notes = list(core.stickyNotes())
    main_notes = list(main.stickyNotes())
    if len(core_notes) != 1 or core_notes[0].name() != TOP_NOTE["name"]:
        raise RuntimeError("CityRoadCore must contain exactly one V47 overview note")
    if len(main_notes) != 1 or main_notes[0].name() != MAIN_NOTE["name"]:
        raise RuntimeError("CR_MAIN_PIPELINE must contain exactly one V47 reading note")
    if any(node.isGenericFlagSet(hou.nodeFlag.DisplayComment) for node in core.children()):
        raise RuntimeError("CityRoadCore still has always-visible node comments")
    if any(node.isGenericFlagSet(hou.nodeFlag.DisplayComment) for node in main.children()):
        raise RuntimeError("CR_MAIN_PIPELINE still has always-visible node comments")
    if {box.name(): box.comment() for box in core.networkBoxes()} != TOP_BOX_LABELS:
        raise RuntimeError("CityRoadCore Network Box labels differ from V47")
    if {box.name(): box.comment() for box in main.networkBoxes()} != MAIN_BOX_LABELS:
        raise RuntimeError("CR_MAIN_PIPELINE Network Box labels differ from V47")
    return {
        "top_notes": len(core_notes),
        "main_notes": len(main_notes),
        "hidden_top_comments": len(core.children()),
        "hidden_main_comments": len(main.children()),
        "saved": False,
        "marker": MARKER,
    }


def apply_live_patch(save=False, capture_verified_dirty=False, hou_module=None):
    global hou
    if hou_module is not None:
        hou = hou_module
    if hou is None:
        raise RuntimeError("hou is unavailable")
    if save:
        raise RuntimeError("V47 is save=False only; persistence belongs to VerifyFull")
    _asset, core, main = _require_identity()
    existing = core.userData("cityroad_annotation_clarity_marker")
    if existing == MARKER:
        return _validate(core, main)
    if existing:
        raise RuntimeError(f"Unexpected annotation marker: {existing}")

    before = _snapshot(core, main)
    previous_update_mode = hou.updateModeSetting()
    try:
        hou.setUpdateMode(hou.updateMode.Manual)
        with hou.undos.group("CityRoad V47 annotation clarity"):
            _replace_notes(core, TOP_NOTE)
            _replace_notes(main, MAIN_NOTE)
            for node in core.children():
                node.setGenericFlag(hou.nodeFlag.DisplayComment, False)
            for node in main.children():
                node.setGenericFlag(hou.nodeFlag.DisplayComment, False)
            _set_box_labels(core, TOP_BOX_LABELS)
            _set_box_labels(main, MAIN_BOX_LABELS)
            core.setUserData("cityroad_annotation_clarity_marker", MARKER)
            result = _validate(core, main)
        return result
    except Exception:
        _restore_notes(core, before["core_notes"])
        _restore_notes(main, before["main_notes"])
        for name, flag in before["core_flags"].items():
            node = core.node(name)
            if node is not None:
                node.setGenericFlag(hou.nodeFlag.DisplayComment, flag)
        for name, flag in before["main_flags"].items():
            node = main.node(name)
            if node is not None:
                node.setGenericFlag(hou.nodeFlag.DisplayComment, flag)
        for box in core.networkBoxes():
            box.setComment(before["core_boxes"][box.name()])
        for box in main.networkBoxes():
            box.setComment(before["main_boxes"][box.name()])
        if before["marker"] is None:
            core.destroyUserData("cityroad_annotation_clarity_marker")
        else:
            core.setUserData("cityroad_annotation_clarity_marker", before["marker"])
        raise
    finally:
        hou.setUpdateMode(previous_update_mode)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--save", default="false", choices=("false",))
    parser.add_argument("--capture-verified-dirty", default="false",
                        choices=("true", "false"))
    args = parser.parse_args()
    result = apply_live_patch(
        save=False,
        capture_verified_dirty=args.capture_verified_dirty == "true")
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
