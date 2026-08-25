"""Restore the disconnected CityRoad graph output and empty-pack schema.

The patch targets only the current V50 live asset, defaults to ``save=False``,
is idempotent, and never imports or replays historical migration patches.
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
MARKER = "CITYROAD_V51_RESTORE_GENERATION"
SCHEMA_LINE = 'addprimattrib(0, "name", "");'
CLASSIFIER_ANCHOR = "string pieces[];"
GRAPH_SUBNET = "CityRoadCore/CR_MAIN_PIPELINE/CR_GRAPH_INDEX"
GRAPH_SOURCE = "GRAPH_CLASSIFY_JUNCTIONS"
GRAPH_OUTPUT = "SUBNET_OUT_GRAPH_CLASSIFY_JUNCTIONS_0"
TOPOLOGY_CLASSIFIER = (
    "CityRoadCore/CR_MAIN_PIPELINE/CR_ROAD_OUTPUT_CLASSIFY/"
    "CITYROAD_TOPOLOGY_CLASSIFY_ROAD")
TOPOLOGY_PACK = (
    "CityRoadCore/CR_MAIN_PIPELINE/CR_ROAD_OUTPUT_CLASSIFY/"
    "CITYROAD_TOPOLOGY_PACK_ROAD")


def _definition_path(node: hou.Node) -> Path | None:
    definition = node.type().definition()
    return Path(definition.libraryFilePath()).resolve() if definition else None


def _require_asset() -> hou.Node:
    asset = hou.node(ASSET_PATH)
    if asset is None or asset.type().name() != ASSET_TYPE:
        raise RuntimeError(f"Expected {ASSET_TYPE} at {ASSET_PATH}")
    if _definition_path(asset) != HDA_PATH.resolve():
        raise RuntimeError("CityRoad live definition path changed")
    if asset.userData("pcg_cityroad_v50") != "CITYROAD_V50_CITYPARK_DECOUPLED":
        raise RuntimeError("CityRoad V50 baseline marker is missing")
    return asset


def _nodes(asset: hou.Node) -> tuple[hou.Node, hou.Node, hou.Node, hou.Node]:
    graph = asset.node(GRAPH_SUBNET)
    source = graph.node(GRAPH_SOURCE) if graph else None
    output = graph.node(GRAPH_OUTPUT) if graph else None
    classifier = asset.node(TOPOLOGY_CLASSIFIER)
    pack = asset.node(TOPOLOGY_PACK)
    if any(node is None for node in (graph, source, output, classifier, pack)):
        raise RuntimeError("CityRoad V51 target nodes are missing")
    return source, output, classifier, pack


def validate_precondition(asset: hou.Node) -> None:
    source, output, classifier, _pack = _nodes(asset)
    if asset.userData("pcg_cityroad_v51") == MARKER:
        validate_postcondition(asset)
        return
    connections = output.inputConnections()
    if connections:
        if (len(connections) != 1 or
                connections[0].inputNode() != source or
                connections[0].outputIndex() != 0):
            raise RuntimeError("V51 graph output precondition changed")
        raise RuntimeError("V51 graph output is already connected without marker")
    snippet = classifier.parm("snippet").evalAsString()
    if SCHEMA_LINE in snippet:
        raise RuntimeError("V51 name schema already exists without marker")
    if CLASSIFIER_ANCHOR not in snippet:
        raise RuntimeError("V51 topology classifier precondition marker changed")


def validate_postcondition(asset: hou.Node) -> dict:
    source, output, classifier, pack = _nodes(asset)
    connections = output.inputConnections()
    if (len(connections) != 1 or
            connections[0].inputNode() != source or
            connections[0].outputIndex() != 0):
        raise RuntimeError("CityRoad graph classification output is disconnected")
    snippet = classifier.parm("snippet").evalAsString()
    if snippet.count(SCHEMA_LINE) != 1:
        raise RuntimeError("CityRoad topology name schema is missing or duplicated")
    if asset.userData("pcg_cityroad_v51") != MARKER:
        raise RuntimeError("CityRoad V51 marker is missing")
    pack.cook(force=True)
    if pack.errors():
        raise RuntimeError(f"CityRoad empty-input topology pack failed: {pack.errors()}")
    return {
        "asset": asset.path(),
        "graph_output": output.path(),
        "graph_source": source.path(),
        "empty_pack_errors": list(pack.errors()),
        "marker": MARKER,
    }


def apply(save: bool = False) -> dict:
    asset = _require_asset()
    validate_precondition(asset)
    already_applied = asset.userData("pcg_cityroad_v51") == MARKER
    if already_applied and not save:
        result = validate_postcondition(asset)
        result.update({"changed": False, "saved": False})
        return result

    if asset.isLockedHDA():
        asset.allowEditingOfContents()
    with hou.undos.group("CityRoad V51 restore generation"):
        source, output, classifier, _pack = _nodes(asset)
        output.setInput(0, source, 0)
        snippet = classifier.parm("snippet").evalAsString()
        if SCHEMA_LINE not in snippet:
            snippet = snippet.replace(
                CLASSIFIER_ANCHOR,
                SCHEMA_LINE + "\n" + CLASSIFIER_ANCHOR,
                1)
            classifier.parm("snippet").set(snippet)
        asset.setUserData("pcg_cityroad_v51", MARKER)
        result = validate_postcondition(asset)

    if save:
        definition = asset.type().definition()
        parameter_values = {}
        for parm in asset.parms():
            try:
                parameter_values[parm.name()] = parm.eval()
            except Exception:
                pass
        position = asset.position()
        definition.updateFromNode(asset)
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
        asset.setUserData("pcg_cityroad_v50", "CITYROAD_V50_CITYPARK_DECOUPLED")
        asset.setUserData("pcg_cityroad_v51", MARKER)
        result = validate_postcondition(asset)
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
            "import patch_cityroad_restore_generation_v51_20260825 as _patch; "
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
