"""Deterministically tidy the current CityRoadCore network editor layout.

This is a layout-only migration. It never creates, deletes, renames, rewires,
or edits parameters on SOP nodes. The current V15 Live Scene is the sole
baseline; ``save`` defaults to False and all editor layout state is restored
if any precondition or postcondition fails.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

import hou


ASSET_PATH = "/obj/CityRoad_DEV"
ASSET_TYPE = "pcgbike::CityRoad::1.0"
CORE_NAME = "CityRoadCore"
EXPECTED_NODE_COUNT = 179
EXPECTED_CONTENT_SHA256 = (
    "dea552bb37e9ff62c2d70c73f6824760fced409860927bac349fda39711480b1"
)

BOX_RENAMES = {
    "V7_ADAPTIVE_CORNER_TOPOLOGY": "FEATURE_V07_ADAPTIVE_CORNER",
    "__netbox1": "FEATURE_V07_JUNCTION_EXTENT",
    "CITYROAD_V11_DETERMINISTIC_STRIPS": "FEATURE_V11_DETERMINISTIC_STRIPS",
    "CITYROAD_V12_SHARED_CORNER_BOUNDARY": "FEATURE_V12_SHARED_CORNER_BOUNDARY",
}

BOX_ADDITIONS = {
    "STEP_10_CURB_SIDEWALK": ["CURB_SIDEWALK_REMOVE_DEGENERATE"],
    "SIDEWALK_PARTITION_BOOLEAN_SYSTEM": [
        "SIDEWALK_OPEN_END_SEAM_SHATTER",
        "SIDEWALK_MARK_ROAD_INTRUSIONS",
        "SIDEWALK_DELETE_ROAD_INTRUSIONS",
        "SIDEWALK_FINAL_ROAD_BOUNDARY_GROUP",
        "SIDEWALK_FINAL_ROAD_BOUNDARY_CURVES",
    ],
    "SIDEWALK_CONSTRAINED_2D_PARTITION": [
        "CITYROAD_BUILD_CORNER_SECTION_CONSTRAINTS_V10",
        "CITYROAD_BUILD_SIDEWALK_SECTION_CONSTRAINTS_V10",
        "CITYROAD_FUSE_SIDEWALK_TRIANGULATION_V10",
        "CITYROAD_MARK_SIDEWALK_TERMINAL_FRONT_EXCLUSIONS_V15",
        "CITYROAD_VALIDATE_SIDEWALK_TERMINAL_FRONT_CONTAINMENT_V15",
    ],
}

# Rows encode the intended reading order: input -> road construction ->
# boundary/features -> topology/output branches -> final contracts.
BOX_ROWS = [
    ["STEP_01_INPUT_CONTRACT", "STEP_02_GRAPH_PREP"],
    ["STEP_03A_CORRIDOR_SURFACE", "STEP_03B_JUNCTION_PATCH", "STEP_03C_MERGE_JOIN",
     "FEATURE_V07_ADAPTIVE_CORNER", "FEATURE_V07_JUNCTION_EXTENT",
     "ROAD_CONSTRAINED_2D_FINAL_SURFACE"],
    ["FEATURE_V11_DETERMINISTIC_STRIPS", "FEATURE_V12_SHARED_CORNER_BOUNDARY",
     "STEP_04A_UNION_FUSE", "STEP_04B_VISIBLE_SHELL",
     "STEP_04C_BOUNDARY_EXTRACTION", "STEP_04D_ORIENTATION_WINDING"],
    ["STEP_06_V4_V5_BUILD", "STEP_05_LOCAL_TOPOLOGY", "STEP_07_UNITY_WINDING_FIX"],
    ["SIDEWALK_PARTITION_BOOLEAN_SYSTEM", "SIDEWALK_CONSTRAINED_2D_PARTITION",
     "STEP_10_CURB_SIDEWALK", "STEP_11_MARKING_POINTS", "STEP_12_COLLISION",
     "STEP_13_TUTORIAL_LAB_BRIDGE"],
    ["STEP_08_SHADING_CONTRACT", "STEP_09_TOPOLOGY_PACK", "STEP_14_MARKING_MESH",
     "STEP_15_OUTPUT_CONTRACT"],
]

PALETTE = {
    "input": hou.Color((0.24, 0.48, 0.72)),
    "road": hou.Color((0.32, 0.54, 0.34)),
    "feature": hou.Color((0.55, 0.42, 0.20)),
    "sidewalk": hou.Color((0.52, 0.34, 0.58)),
    "unity": hou.Color((0.30, 0.55, 0.58)),
    "output": hou.Color((0.62, 0.30, 0.28)),
}


def _content_sha256(core: hou.Node) -> str:
    rows = []
    for node in sorted(core.children(), key=lambda item: item.name()):
        rows.append({
            "name": node.name(),
            "type": node.type().nameWithCategory(),
            "inputs": [item.path() if item else None for item in node.inputs()],
            "parms": {parm.name(): parm.rawValue() for parm in node.parms()},
        })
    payload = json.dumps(rows, sort_keys=True, default=str).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def _box_map(core: hou.Node) -> dict[str, hou.NetworkBox]:
    return {box.name(): box for box in core.networkBoxes()}


def _box_color(name: str) -> hou.Color:
    if name.startswith(("STEP_01", "STEP_02")):
        return PALETTE["input"]
    if "SIDEWALK" in name or name == "STEP_10_CURB_SIDEWALK":
        return PALETTE["sidewalk"]
    if name.startswith("FEATURE_"):
        return PALETTE["feature"]
    if name.startswith(("STEP_07", "STEP_08", "STEP_09", "STEP_13", "STEP_14")):
        return PALETTE["unity"]
    if name.startswith("STEP_15"):
        return PALETTE["output"]
    return PALETTE["road"]


def _layout_members(box: hou.NetworkBox) -> None:
    """Top-down DAG layout within one semantic box, preserving branch columns."""
    nodes = sorted(box.nodes(), key=lambda item: item.name())
    members = set(nodes)
    level: dict[hou.Node, int] = {}
    pending = set(nodes)
    while pending:
        progressed = False
        for node in sorted(pending, key=lambda item: item.name()):
            parents = [item for item in node.inputs() if item in members]
            unresolved = [item for item in parents if item not in level]
            if unresolved:
                continue
            level[node] = 0 if not parents else max(level[item] for item in parents) + 1
            pending.remove(node)
            progressed = True
        if not progressed:
            # A layout cycle is not a Cook error; place its nodes in one final row.
            fallback = max(level.values(), default=-1) + 1
            for node in sorted(pending, key=lambda item: item.name()):
                level[node] = fallback
            break
    by_level: dict[int, list[hou.Node]] = {}
    for node, value in level.items():
        by_level.setdefault(value, []).append(node)
    for value, layer in sorted(by_level.items()):
        layer.sort(key=lambda item: item.name())
        width = (len(layer) - 1) * 3.1
        for index, node in enumerate(layer):
            node.setPosition(hou.Vector2((index * 3.1 - width * 0.5, -value * 2.8)))
    box.fitAroundContents()


def _capture_layout(core: hou.Node) -> dict:
    return {
        "nodes": {node: node.position() for node in core.children()},
        "boxes": [{
            "box": box,
            "name": box.name(),
            "comment": box.comment(),
            "color": box.color(),
            "position": box.position(),
            "size": box.size(),
            "items": tuple(box.items()),
        } for box in core.networkBoxes()],
        "stickies": [{
            "item": sticky,
            "position": sticky.position(),
            "size": sticky.size(),
            "color": sticky.color(),
        } for sticky in core.stickyNotes()],
    }


def _restore_layout(snapshot: dict) -> None:
    for node, position in snapshot["nodes"].items():
        node.setPosition(position)
    for state in snapshot["boxes"]:
        box = state["box"]
        for item in tuple(box.items()):
            box.removeItem(item)
        for item in state["items"]:
            box.addItem(item)
        box.setName(state["name"])
        box.setComment(state["comment"])
        box.setColor(state["color"])
        box.setPosition(state["position"])
        box.setSize(state["size"])
    for state in snapshot["stickies"]:
        sticky = state["item"]
        sticky.setPosition(state["position"])
        sticky.setSize(state["size"])
        sticky.setColor(state["color"])


def _place_stickies(core: hou.Node, boxes: dict[str, hou.NetworkBox]) -> None:
    note_targets = {
        "01 ": "STEP_01_INPUT_CONTRACT", "02 ": "STEP_02_GRAPH_PREP",
        "03 ": "STEP_03A_CORRIDOR_SURFACE", "04 ": "STEP_04A_UNION_FUSE",
        "05 ": "STEP_05_LOCAL_TOPOLOGY", "06 ": "STEP_06_V4_V5_BUILD",
        "07 ": "STEP_07_UNITY_WINDING_FIX", "08 ": "STEP_08_SHADING_CONTRACT",
        "09 ": "STEP_09_TOPOLOGY_PACK", "10 ": "STEP_10_CURB_SIDEWALK",
        "11 ": "STEP_11_MARKING_POINTS", "12 ": "STEP_12_COLLISION",
        "13 ": "STEP_13_TUTORIAL_LAB_BRIDGE", "14 ": "STEP_14_MARKING_MESH",
        "15 ": "STEP_15_OUTPUT_CONTRACT",
    }
    for sticky in core.stickyNotes():
        text = sticky.text()
        if text.startswith("【阅读路线"):
            sticky.setPosition(hou.Vector2((0.0, 12.0)))
            continue
        if text.startswith("V7 普通弯道"):
            target = boxes["FEATURE_V07_ADAPTIVE_CORNER"]
        else:
            key = next((prefix for prefix in note_targets if text.startswith(prefix)), None)
            if key is None:
                continue
            target = boxes[note_targets[key]]
        sticky.setPosition(target.position() + hou.Vector2((0.0, target.size()[1] + 0.6)))


def apply(save: bool = False) -> dict:
    asset = hou.node(ASSET_PATH)
    if asset is None or asset.type().name() != ASSET_TYPE:
        raise RuntimeError(f"Expected {ASSET_TYPE} at {ASSET_PATH}")
    core = asset.node(CORE_NAME)
    if core is None or len(core.children()) != EXPECTED_NODE_COUNT:
        raise RuntimeError("CityRoadCore node-count precondition changed")
    before_hash = _content_sha256(core)
    if before_hash != EXPECTED_CONTENT_SHA256:
        raise RuntimeError(f"CityRoadCore structural precondition changed: {before_hash}")
    snapshot = _capture_layout(core)
    try:
        boxes = _box_map(core)
        for old_name, new_name in BOX_RENAMES.items():
            box = boxes.get(old_name) or boxes.get(new_name)
            if box is None:
                raise RuntimeError(f"Missing network box: {old_name}")
            if box.name() != new_name:
                box.setName(new_name)
        boxes = _box_map(core)
        expected_boxes = {name for row in BOX_ROWS for name in row}
        if set(boxes) != expected_boxes:
            raise RuntimeError(
                f"Unexpected network-box set: missing={sorted(expected_boxes-set(boxes))} "
                f"extra={sorted(set(boxes)-expected_boxes)}")
        for box_name, node_names in BOX_ADDITIONS.items():
            box = boxes[box_name]
            for node_name in node_names:
                node = core.node(node_name)
                if node is None:
                    raise RuntimeError(f"Missing layout target node: {node_name}")
                owners = [item for item in boxes.values() if node in item.nodes()]
                if owners and box not in owners:
                    raise RuntimeError(f"Node already belongs to another box: {node_name}")
                if not owners:
                    box.addItem(node)
        boxed = {node for box in boxes.values() for node in box.nodes()}
        unboxed = sorted(node.name() for node in core.children() if node not in boxed)
        if unboxed:
            raise RuntimeError(f"Unboxed CityRoadCore nodes remain: {unboxed}")

        for name, box in boxes.items():
            box.setColor(_box_color(name))
            _layout_members(box)

        # Pack variable-size semantic boxes into deterministic horizontal rows.
        gap_x, gap_y = 3.0, 8.0
        top = 0.0
        for row in BOX_ROWS:
            x = 0.0
            row_height = max(boxes[name].size()[1] for name in row)
            for name in row:
                box = boxes[name]
                box.setPosition(hou.Vector2((x, top - box.size()[1])))
                x += box.size()[0] + gap_x
            top -= row_height + gap_y
        _place_stickies(core, boxes)

        after_hash = _content_sha256(core)
        if after_hash != before_hash:
            raise RuntimeError(f"Layout changed CityRoadCore structure: {after_hash}")
        result = {
            "saved": False,
            "node_count": len(core.children()),
            "network_box_count": len(core.networkBoxes()),
            "sticky_note_count": len(core.stickyNotes()),
            "unboxed_node_count": 0,
            "content_sha256": after_hash,
            # Copy to a plain dict before crossing the hrpyc boundary.
            "renamed_boxes": dict(BOX_RENAMES),
        }
        if save:
            definition = asset.type().definition()
            if definition is None:
                raise RuntimeError("CityRoad instance has no HDA definition")
            definition.updateFromNode(asset)
            hou.hipFile.save()
            result["saved"] = True
        return result
    except Exception:
        _restore_layout(snapshot)
        raise


def apply_remote(host: str, port: int, save: bool) -> dict:
    import hrpyc
    connection, _remote_hou = hrpyc.import_remote_module(host, port, "hou")
    try:
        script_dir = str(Path(__file__).resolve().parent).replace("\\", "/")
        connection.execute(
            "import sys, importlib; "
            f"sys.path.insert(0, {script_dir!r}) if {script_dir!r} "
            "not in sys.path else None; "
            "import layout_cityroad_core_20260812 as _pcg_layout; "
            "importlib.reload(_pcg_layout)")
        payload = connection.eval(
            f"_pcg_layout.json.dumps(_pcg_layout.apply(save={save!r}), "
            "ensure_ascii=False)")
        return json.loads(str(payload))
    finally:
        connection.close()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=18811)
    parser.add_argument("--save", action="store_true")
    args = parser.parse_args()
    print(json.dumps(apply_remote(args.host, args.port, args.save),
                     ensure_ascii=False, indent=2, default=list))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
