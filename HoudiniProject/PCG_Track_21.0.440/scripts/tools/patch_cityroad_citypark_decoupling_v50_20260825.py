"""Remove the legacy CityPark branch from the current CityRoad live asset.

The patch is scoped to the captured V49 live instance, never imports historical
patches, defaults to ``save=False``, is idempotent, and restores the affected
nodes/interface in the active Houdini undo group when an exception is raised.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import hou


SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = SCRIPT_DIR.parents[3]
ASSET_PATH = "/obj/CityRoad_DEV"
ASSET_TYPE = "pcgbike::CityRoad::1.0"
HDA_PATH = PROJECT_ROOT / "Assets/PCG/HDA/City/CityRoad.hda"
HIP_PATH = PROJECT_ROOT / "HoudiniProject/PCG_Track_21.0.440/PCG_Bike_CityRoad.hip"
MARKER = "CITYROAD_V50_CITYPARK_DECOUPLED"
PARK_PARAMETERS = (
    "enable_city_park", "unity_park_areas", "park_seed", "park_boundary_inset",
    "enable_park_water", "park_lake_count", "park_lake_area_ratio",
    "enable_park_paths", "park_path_width", "park_path_branch_count",
    "park_path_jitter", "enable_park_trees", "park_tree_density_per_hectare",
    "park_tree_min_spacing", "park_tree_clearance", "park_ground_unity_material",
    "park_path_unity_material", "park_water_unity_material",
)
PARK_OUTPUTS = (
    "OUT_PARK_GROUND", "OUT_PARK_PATHS", "OUT_PARK_WATER",
    "OUT_PARK_COLLISION", "OUT_PARK_TREES", "OUT_PARK_EXCLUSION",
)
PARK_FOLDER = "city_park_folder"


def _definition_path(node: hou.Node) -> Path | None:
    definition = node.type().definition()
    return Path(definition.libraryFilePath()).resolve() if definition is not None else None


def validate_precondition(asset: hou.Node) -> None:
    if asset is None or asset.type().nameWithCategory() != "pcgbike::Object/CityRoad::1.0":
        raise RuntimeError("Expected /obj/CityRoad_DEV pcgbike::CityRoad::1.0")
    if _definition_path(asset) != HDA_PATH.resolve():
        raise RuntimeError("CityRoad live definition path changed")
    core = asset.node("CityRoadCore")
    if core is None:
        raise RuntimeError("CityRoadCore is missing")
    marker = asset.userData("pcg_cityroad_v50")
    if marker == MARKER:
        validate_postcondition(asset, require_interface_removed=False)
        return
    existing_nodes = [name for name in ("CR_CITY_PARK", *PARK_OUTPUTS)
                      if core.node(name) is not None]
    if existing_nodes and len(existing_nodes) != 1 + len(PARK_OUTPUTS):
        raise RuntimeError(f"V50 precondition has a partial park graph: {existing_nodes}")
    group = asset.parmTemplateGroup()
    missing_parameters = [name for name in PARK_PARAMETERS if group.find(name) is None]
    if missing_parameters:
        raise RuntimeError(f"V50 precondition missing park parameters: {missing_parameters}")


def validate_postcondition(asset: hou.Node, require_interface_removed: bool = False) -> dict:
    core = asset.node("CityRoadCore")
    bad_nodes = [name for name in ("CR_CITY_PARK", *PARK_OUTPUTS)
                 if core.node(name) is not None]
    bad_parameters = [name for name in PARK_PARAMETERS
                      if asset.parmTemplateGroup().find(name) is not None]
    bad_boxes = [box.name() for box in core.networkBoxes()
                 if box.name() == "OVERVIEW_PARK"]
    if bad_nodes or bad_boxes or (require_interface_removed and bad_parameters):
        raise RuntimeError({
            "remaining_nodes": bad_nodes,
            "remaining_parameters": bad_parameters,
            "remaining_boxes": bad_boxes,
        })
    if asset.userData("pcg_cityroad_v50") != MARKER:
        raise RuntimeError("CityRoad V50 marker missing")
    return {
        "asset": asset.path(),
        "removed_nodes": ["CR_CITY_PARK", *PARK_OUTPUTS],
        "removed_parameters": list(PARK_PARAMETERS),
        "marker": MARKER,
    }


def _normalize_annotations(asset: hou.Node) -> None:
    core = asset.node("CityRoadCore")
    note = next((item for item in core.stickyNotes()
                 if item.name() == "NOTE_V47_OVERVIEW"), None)
    if note is not None:
        note.setText(
            "CityRoadCore｜总览\n"
            "CR_MAIN_PIPELINE：道路主链；公园已迁移到独立 CityPark HDA。\n"
            "OUT_*：正式输出；双击 MAIN 后按 01→05 向下阅读。")
    debug_names = {"OUT_LAB_GRAPH", "OUT_LAB_ROAD_CENTERLINES", "OUT_LAB_ROAD_OUTLINES"}
    for box in core.networkBoxes():
        if {item.name() for item in box.items()} == debug_names:
            box.setName("OVERVIEW_LAB_PORTALS")
            box.setComment("LAB DEBUG PORTALS｜教程与算法验证")


def apply(save: bool = False) -> dict:
    asset = hou.node(ASSET_PATH)
    validate_precondition(asset)
    already_applied = asset.userData("pcg_cityroad_v50") == MARKER
    _normalize_annotations(asset)
    if already_applied and not save:
        result = validate_postcondition(asset, require_interface_removed=save)
        result.update({"changed": False, "saved": save})
        return result

    with hou.undos.group("CityRoad V50 CityPark decoupling"):
        core = asset.node("CityRoadCore")
        note = next((item for item in core.stickyNotes()
                     if item.name() == "NOTE_V47_OVERVIEW"), None)
        note_before = note.text() if note is not None else None
        try:
            for box in list(core.networkBoxes()):
                if box.name() == "OVERVIEW_PARK":
                    box.destroy()
            for name in PARK_OUTPUTS:
                node = core.node(name)
                if node is not None:
                    node.destroy()
            park = core.node("CR_CITY_PARK")
            if park is not None:
                park.destroy()
            if note is not None:
                note.setText(
                    "CityRoadCore｜总览\n"
                    "CR_MAIN_PIPELINE：道路主链；公园已迁移到独立 CityPark HDA。\n"
                    "OUT_*：正式输出；双击 MAIN 后按 01→05 向下阅读。")
            asset.setUserData("pcg_cityroad_v50", MARKER)
            result = validate_postcondition(asset, require_interface_removed=False)
        except Exception:
            if note is not None and note_before is not None:
                note.setText(note_before)
            raise

    if save:
        definition = asset.type().definition()
        parameter_values = {}
        for parm in asset.parms():
            try:
                parameter_values[parm.name()] = parm.eval()
            except Exception:
                pass
        position = asset.position()
        group = definition.parmTemplateGroup()
        park_folder = group.find(PARK_FOLDER)
        if park_folder is not None:
            group.remove(park_folder)
        else:
            for name in PARK_PARAMETERS:
                template = group.find(name)
                if template is not None:
                    group.remove(template)
        definition.updateFromNode(asset)
        definition.setParmTemplateGroup(group)
        # Recreate a locked production instance from the persisted definition.
        # Houdini otherwise retains removed definition parms as node-level
        # spares on the formerly editable instance, and the regression
        # persister would serialize those spares back into the HDA.
        asset.destroy()
        asset = hou.node("/obj").createNode(ASSET_TYPE, "CityRoad_DEV")
        asset.setPosition(position)
        for name, value in parameter_values.items():
            parm = asset.parm(name)
            if parm is not None:
                try:
                    parm.set(value)
                except Exception:
                    pass
        asset.setUserData("pcg_cityroad_v50", MARKER)
        result = validate_postcondition(asset, require_interface_removed=True)
        hou.hipFile.save(str(HIP_PATH))
    result.update({"changed": not already_applied, "saved": save})
    return result


def run_remote(host: str, port: int, save: bool) -> dict:
    import hrpyc
    connection, _remote_hou = hrpyc.import_remote_module(host, port, "hou")
    try:
        path = str(SCRIPT_DIR).replace("\\", "/")
        connection.execute(
            "import sys, importlib, json; "
            f"sys.path.insert(0, {path!r}) if {path!r} not in sys.path else None; "
            "import patch_cityroad_citypark_decoupling_v50_20260825 as _patch; "
            "importlib.reload(_patch)")
        payload = connection.eval(
            f"json.dumps(_patch.apply({save!r}), ensure_ascii=False)")
        return json.loads(str(payload))
    finally:
        connection.close()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=18811)
    parser.add_argument("--save", choices=("true", "false"), default="false")
    args = parser.parse_args()
    print(json.dumps(run_remote(args.host, args.port, args.save == "true"),
                     ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
