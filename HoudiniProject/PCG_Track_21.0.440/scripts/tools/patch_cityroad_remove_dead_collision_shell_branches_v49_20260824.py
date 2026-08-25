"""Remove two proven-dead CityRoad branches (save=False only)."""

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
COLLISION_SUBNET = "CR_COLLISION_AUDIT"
COLLISION_LEAVES = {
    "COLLISION_REMOVE_DEGENERATE",
    "COLLISION_NORMALS",
    "OUTPUT_CONTRACT_COLLISION",
    "CITYROAD_TOPOLOGY_TRANSFER_ROADCOLLISION",
}
SHELL_BRANCH = (
    "ROAD_UNION_BOUNDARY_WALLS",
    "ROAD_WALL_METADATA",
    "ROAD_MERGE_VISIBLE_SHELL",
)
V46_MARKER = "CITYROAD_THREE_LEVEL_READABILITY_V46_20260824"
V47_MARKER = "CITYROAD_ANNOTATION_CLARITY_V47_20260824"
V48_MARKER = "CITYROAD_DEAD_NODE_CLEANUP_V48_20260824"
MARKER = "CITYROAD_REMOVE_DEAD_COLLISION_SHELL_BRANCHES_V49_20260824"
SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = SCRIPT_DIR.parents[3]
EXPECTED_HIP = PROJECT_ROOT / "HoudiniProject/PCG_Track_21.0.440/PCG_Bike_CityRoad.hip"
EXPECTED_HDA = PROJECT_ROOT / "Assets/PCG/HDA/City/CityRoad.hda"


def _norm(value) -> str:
    return str(value).replace("\\", "/").lower()


def _subnet_output_source(subnet, output_index):
    for child in subnet.children():
        if child.type().name() != "output":
            continue
        parm = child.parm("outputidx")
        index = int(parm.eval()) if parm is not None else 0
        if index != output_index:
            continue
        connections = child.inputConnections()
        if not connections:
            return None, 0
        return connections[0].inputNode(), connections[0].outputIndex()
    return None, 0


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
    expected_markers = {
        "cityroad_three_level_readability_marker": V46_MARKER,
        "cityroad_annotation_clarity_marker": V47_MARKER,
        "cityroad_dead_node_cleanup_marker": V48_MARKER,
    }
    for key, value in expected_markers.items():
        if core.userData(key) != value:
            raise RuntimeError(f"Required predecessor marker is missing: {key}")
    return asset, core, main


def _validate_official_collision(main):
    source, output_index = _subnet_output_source(main, 1)
    if source is None or source.name() != "CR_ROAD_OUTPUT_CLASSIFY" or output_index != 1:
        raise RuntimeError("Official collision output is not CR_ROAD_OUTPUT_CLASSIFY output 1")


def _validate_protected(main):
    protected = (
        "CR_ROAD_SHELL_AUDIT",
        "CR_SIDEWALK_SITE_OPEN_ENDS/SIDEWALK_OPEN_END_SEAM_SHATTER",
        "CR_STREET_FURNITURE/CITYROAD_STREET_FURNITURE_V1",
    )
    for relative_path in protected:
        if main.node(relative_path) is None:
            raise RuntimeError(f"Protected branch is missing: {relative_path}")


def _validate_removed(core, main):
    absent = [COLLISION_SUBNET]
    absent.extend(f"CR_UNION_FINALIZE/{name}" for name in SHELL_BRANCH)
    remaining = [path for path in absent if main.node(path) is not None]
    if remaining:
        raise RuntimeError(f"Dead branches still exist: {remaining}")
    _validate_official_collision(main)
    _validate_protected(main)
    if core.userData("cityroad_dead_branch_cleanup_marker") != MARKER:
        raise RuntimeError("V49 cleanup marker is missing")
    return {
        "removed": absent,
        "protected": 3,
        "official_collision_source": "CR_ROAD_OUTPUT_CLASSIFY:1",
        "saved": False,
        "marker": MARKER,
    }


def _validate_preflight(main):
    collision = main.node(COLLISION_SUBNET)
    if collision is None:
        raise RuntimeError(f"Missing pre-V49 subnet: {COLLISION_SUBNET}")
    if collision.outputConnections():
        raise RuntimeError(f"{COLLISION_SUBNET} acquired an output consumer")
    functional = {
        child.name() for child in collision.children()
        if child.type().name() not in {"subnetconnector", "output"}
    }
    if functional != COLLISION_LEAVES:
        raise RuntimeError(
            f"{COLLISION_SUBNET} members changed: {sorted(functional)}")

    union = main.node("CR_UNION_FINALIZE")
    if union is None:
        raise RuntimeError("CR_UNION_FINALIZE is missing")
    walls, metadata, merged = (union.node(name) for name in SHELL_BRANCH)
    if any(node is None for node in (walls, metadata, merged)):
        raise RuntimeError("Pre-V49 visible-shell branch is incomplete")
    if merged.outputConnections():
        raise RuntimeError("ROAD_MERGE_VISIBLE_SHELL acquired an output consumer")
    if {c.outputNode().name() for c in walls.outputConnections()} != {"ROAD_WALL_METADATA"}:
        raise RuntimeError("ROAD_UNION_BOUNDARY_WALLS is no longer branch-local")
    if {c.outputNode().name() for c in metadata.outputConnections()} != {"ROAD_MERGE_VISIBLE_SHELL"}:
        raise RuntimeError("ROAD_WALL_METADATA is no longer branch-local")
    _validate_official_collision(main)
    _validate_protected(main)
    return collision, union, (walls, metadata, merged)


def apply_live_patch(save=False, capture_verified_dirty=False, hou_module=None):
    global hou
    if hou_module is not None:
        hou = hou_module
    if hou is None:
        raise RuntimeError("hou is unavailable")
    if save:
        raise RuntimeError("V49 is save=False only; persistence belongs to VerifyFull")
    _asset, core, main = _require_identity()
    existing = core.userData("cityroad_dead_branch_cleanup_marker")
    if existing == MARKER:
        return _validate_removed(core, main)
    if existing:
        raise RuntimeError(f"Unexpected V49 cleanup marker: {existing}")
    collision, union, branch = _validate_preflight(main)

    previous_update_mode = hou.updateModeSetting()
    mutation_started = False
    try:
        hou.setUpdateMode(hou.updateMode.Manual)
        with hou.undos.group("CityRoad V49 remove dead branches"):
            mutation_started = True
            # Delete downstream-to-upstream so only branch-local wires disappear.
            for node in reversed(branch):
                node.destroy()
            collision.destroy()
            # The deleted wall node held this subnet's display/render flags.
            # Promote the actual published output deterministically.
            union_output = union.node("SUBNET_OUT_ROAD_UNION_CLEAR_ORIENT_HELPER_0")
            if union_output is None:
                raise RuntimeError("CR_UNION_FINALIZE output node is missing")
            union_output.setDisplayFlag(True)
            union_output.setRenderFlag(True)
            core.setUserData("cityroad_dead_branch_cleanup_marker", MARKER)
            result = _validate_removed(core, main)
        return result
    except Exception:
        if mutation_started:
            hou.undos.performUndo()
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
