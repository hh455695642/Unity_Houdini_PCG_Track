"""Remove the one proven-unreferenced CityRoadCore node (save=False only)."""

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
CANDIDATE_NAME = "IN_LAB_SIDEWALK_CANDIDATE"
V46_MARKER = "CITYROAD_THREE_LEVEL_READABILITY_V46_20260824"
V47_MARKER = "CITYROAD_ANNOTATION_CLARITY_V47_20260824"
MARKER = "CITYROAD_DEAD_NODE_CLEANUP_V48_20260824"
SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = SCRIPT_DIR.parents[3]
EXPECTED_HIP = PROJECT_ROOT / "HoudiniProject/PCG_Track_21.0.440/PCG_Bike_CityRoad.hip"
EXPECTED_HDA = PROJECT_ROOT / "Assets/PCG/HDA/City/CityRoad.hda"


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
        raise RuntimeError("CityRoadCore V46 hierarchy is missing")
    if core.userData("cityroad_three_level_readability_marker") != V46_MARKER:
        raise RuntimeError("V46 readability marker is missing")
    if core.userData("cityroad_annotation_clarity_marker") != V47_MARKER:
        raise RuntimeError("V47 annotation marker is missing")
    return asset, core, main


def _snapshot(node):
    values = {}
    for parm in node.parms():
        try:
            if not parm.isAtDefault():
                values[parm.name()] = parm.rawValue()
        except Exception:
            pass
    return {
        "type": node.type().name(),
        "position": tuple(node.position()),
        "color": tuple(node.color().rgb()),
        "comment": node.comment(),
        "display_comment": node.isGenericFlagSet(hou.nodeFlag.DisplayComment),
        "display": node.isDisplayFlagSet(),
        "render": node.isRenderFlagSet(),
        "parms": values,
    }


def _restore(main, payload):
    node = main.createNode(payload["type"], CANDIDATE_NAME)
    node.setPosition(hou.Vector2(payload["position"]))
    node.setColor(hou.Color(payload["color"]))
    node.setComment(payload["comment"])
    node.setGenericFlag(hou.nodeFlag.DisplayComment, payload["display_comment"])
    node.setDisplayFlag(payload["display"])
    node.setRenderFlag(payload["render"])
    for name, value in payload["parms"].items():
        parm = node.parm(name)
        if parm is not None:
            parm.set(value)
    boxes = {box.name(): box for box in main.networkBoxes()}
    box = boxes.get("AREA_STAGE_01_CONTEXT")
    if box is not None:
        box.addItem(node)
    return node


def _validate(core, main):
    if main.node(CANDIDATE_NAME) is not None:
        raise RuntimeError(f"{CANDIDATE_NAME} still exists")
    protected = {
        "OUT_LAB_GRAPH": "/obj/CityRoad_DEV/CityRoadTutorialLab/IN_CORE_GRAPH",
        "OUT_LAB_ROAD_CENTERLINES": (
            "/obj/CityRoad_DEV/CityRoadTutorialLab/IN_CORE_ROAD_CENTERLINES"),
        "OUT_LAB_ROAD_OUTLINES": (
            "/obj/CityRoad_DEV/CityRoadTutorialLab/IN_CORE_ROAD_OUTLINES"),
    }
    for name, dependent_path in protected.items():
        node = core.node(name)
        if node is None or node.type().name() != "object_merge":
            raise RuntimeError(f"Protected Lab portal is missing: {name}")
        dependents = {dependent.path() for dependent in node.dependents(include_children=True)}
        if dependent_path not in dependents:
            raise RuntimeError(f"Protected Lab portal lost its reader: {name}")
    return {
        "removed": CANDIDATE_NAME,
        "protected_path_portals": len(protected),
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
        raise RuntimeError("V48 is save=False only; persistence belongs to VerifyFull")
    _asset, core, main = _require_identity()
    existing = core.userData("cityroad_dead_node_cleanup_marker")
    if existing == MARKER:
        return _validate(core, main)
    if existing:
        raise RuntimeError(f"Unexpected dead-node cleanup marker: {existing}")
    candidate = main.node(CANDIDATE_NAME)
    if candidate is None:
        raise RuntimeError(f"Missing pre-V48 node: {CANDIDATE_NAME}")
    if candidate.inputConnections() or candidate.outputConnections():
        raise RuntimeError(f"{CANDIDATE_NAME} is no longer disconnected")
    if [node for node in candidate.dependents(include_children=True) if node != candidate]:
        raise RuntimeError(f"{CANDIDATE_NAME} acquired a dependent")

    payload = _snapshot(candidate)
    previous_update_mode = hou.updateModeSetting()
    try:
        hou.setUpdateMode(hou.updateMode.Manual)
        candidate.destroy()
        core.setUserData("cityroad_dead_node_cleanup_marker", MARKER)
        return _validate(core, main)
    except Exception:
        if main.node(CANDIDATE_NAME) is None:
            _restore(main, payload)
        core.destroyUserData("cityroad_dead_node_cleanup_marker")
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
