"""V43 incremental patch: lift all CityRoad park layers above the sidewalk plane.

The current Live Scene is the only implementation source.  This patch validates
the captured V41 snippet hashes before editing, performs no save, is idempotent,
and restores every touched snippet if validation fails.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

try:
    import hou  # type: ignore
except ImportError:
    hou = None


ASSET_PATH = "/obj/CityRoad_DEV"
PARK_PATH = ASSET_PATH + "/CityRoadCore/CR_CITY_PARK"
EXPECTED_HIP = "PCG_Bike_CityRoad.hip"
EXPECTED_HDA = "Assets/PCG/HDA/City/CityRoad.hda"
BASELINE_TREE_SHA256 = "03bd24cbed12f49820400baeb3d40c4e494559d33c55bb423648bfe79d7062fd"
MARKER = "CITYROAD_V43_PARK_SURFACE_LIFT"
PARK_LIFT = 0.12
SCRIPT_DIR = Path(__file__).resolve().parent

EXPECTED_SNIPPET_SHA256 = {
    "PARK_SURFACE_ZONES_V41": "6cfe1d046db08f046e67c08d6e2da5a60d8dd737052127aed9804deb4831bb5a",
    "PARK_CONNECTED_PATHS_V41": "5d48a76595196b45a9b99880aed8172c6907d564ddea8b5dbc12b97fa71ce01e",
    "PARK_WOODLAND_LAYERS_V41": "c2d11ad4d4b8efe27f0258af36bf71576319b6bab7ecbe44c28cb9220f6b84b6",
    "PARK_EXCLUSION_V41": "f3fd236f5a1fdb095d58c7bb885148291b3dc873a55a651f9986a38d542d8ca5",
    "PARK_CONTRACT_V41": "6068c97521df808b6596e9abda47f6b3477d03fe8b6020f3deb9f6a0f349e0c6",
}


def _sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _tree_sha256(park: hou.Node) -> str:
    children = []
    for node in sorted(park.children(), key=lambda item: item.name()):
        snippet = node.parm("snippet")
        children.append({
            "name": node.name(),
            "type": node.type().name(),
            "inputs": [item.name() if item else None for item in node.inputs()],
            "snippet": snippet.unexpandedString() if snippet else None,
        })
    payload = json.dumps(children, sort_keys=True, separators=(",", ":"))
    return _sha256(payload)


def _replace_once(source: str, old: str, new: str, node_name: str) -> str:
    count = source.count(old)
    if count != 1:
        raise RuntimeError(
            f"{node_name}: expected exactly one replacement target, got {count}: {old!r}")
    return source.replace(old, new, 1)


def _validate_identity() -> tuple[hou.Node, dict[str, hou.Node]]:
    hip_path = Path(hou.hipFile.path().replace("\\", "/"))
    if hip_path.name != EXPECTED_HIP:
        raise RuntimeError(f"Unexpected HIP: {hou.hipFile.path()}")

    asset = hou.node(ASSET_PATH)
    if asset is None or asset.type().nameWithCategory() != "pcgbike::Object/CityRoad::1.0":
        raise RuntimeError(f"Missing expected CityRoad instance: {ASSET_PATH}")
    definition = asset.type().definition()
    if definition is None:
        raise RuntimeError("CityRoad instance has no HDA definition")
    library = definition.libraryFilePath().replace("\\", "/")
    if not library.endswith(EXPECTED_HDA):
        raise RuntimeError(f"Unexpected CityRoad definition: {library}")

    park = hou.node(PARK_PATH)
    if park is None:
        raise RuntimeError(f"Missing park subnet: {PARK_PATH}")
    nodes = {}
    for name in EXPECTED_SNIPPET_SHA256:
        node = park.node(name)
        if node is None or node.type().name() != "attribwrangle" or node.parm("snippet") is None:
            raise RuntimeError(f"Missing expected V41 wrangle: {name}")
        nodes[name] = node
    return park, nodes


def _validate_result(nodes: dict[str, hou.Node]) -> dict[str, object]:
    for name, node in nodes.items():
        snippet = node.parm("snippet").unexpandedString()
        if MARKER not in snippet:
            raise RuntimeError(f"{name}: missing V43 marker")
        node.cook(force=True)
        if node.errors():
            raise RuntimeError(f"{name}: cook errors: {node.errors()}")
        if node.warnings():
            raise RuntimeError(f"{name}: cook warnings: {node.warnings()}")

    required_fragments = {
        "PARK_SURFACE_ZONES_V41": (
            "center.y+park_surface_lift-0.04",
            "center.y+park_surface_lift,\"ground\""),
        "PARK_CONNECTED_PATHS_V41": (
            "center.y+park_surface_lift+0.02",
            "center.y+park_surface_lift,\"collision\""),
        "PARK_WOODLAND_LAYERS_V41": (
            "center.y+park_surface_lift,bbmin.z"),
        "PARK_EXCLUSION_V41": ("p.y=center.y+park_surface_lift;",),
        "PARK_CONTRACT_V41": (
            'setdetailattrib(0,"park_surface_lift",0.12,"set");',),
    }
    for name, fragments in required_fragments.items():
        snippet = nodes[name].parm("snippet").unexpandedString()
        for fragment in fragments:
            if fragment not in snippet:
                raise RuntimeError(f"{name}: missing result fragment: {fragment}")

    return {
        "status": "PASS",
        "marker": MARKER,
        "park_surface_lift": PARK_LIFT,
        "save": False,
        "snippet_sha256": {
            name: _sha256(node.parm("snippet").unexpandedString())
            for name, node in nodes.items()
        },
    }


def patch(*, save: bool = False) -> dict[str, object]:
    if save:
        raise RuntimeError("V43 patch is intentionally save=False; persist only after VerifyFull")

    park, nodes = _validate_identity()
    snippets = {name: node.parm("snippet").unexpandedString() for name, node in nodes.items()}
    marker_states = {name: MARKER in snippet for name, snippet in snippets.items()}
    if all(marker_states.values()):
        result = _validate_result(nodes)
        result["idempotent"] = True
        return result
    if any(marker_states.values()):
        raise RuntimeError(f"Partial V43 state detected: {marker_states}")

    tree_sha = _tree_sha256(park)
    if tree_sha != BASELINE_TREE_SHA256:
        raise RuntimeError(
            f"V41 Live park tree changed after Capture: {tree_sha} != {BASELINE_TREE_SHA256}")
    for name, expected in EXPECTED_SNIPPET_SHA256.items():
        actual = _sha256(snippets[name])
        if actual != expected:
            raise RuntimeError(f"{name}: snippet precondition changed: {actual} != {expected}")

    updated = dict(snippets)
    updated["PARK_SURFACE_ZONES_V41"] = _replace_once(
        updated["PARK_SURFACE_ZONES_V41"],
        "// CITYROAD_V41_PARK_SURFACE_ZONES\n",
        f"// CITYROAD_V41_PARK_SURFACE_ZONES\n// {MARKER}\nfloat park_surface_lift={PARK_LIFT:.2f};\n",
        "PARK_SURFACE_ZONES_V41")
    updated["PARK_SURFACE_ZONES_V41"] = _replace_once(
        updated["PARK_SURFACE_ZONES_V41"], "center.y-0.04,\"water\"",
        "center.y+park_surface_lift-0.04,\"water\"", "PARK_SURFACE_ZONES_V41")
    updated["PARK_SURFACE_ZONES_V41"] = _replace_once(
        updated["PARK_SURFACE_ZONES_V41"], "center.y,\"ground\"",
        "center.y+park_surface_lift,\"ground\"", "PARK_SURFACE_ZONES_V41")

    updated["PARK_CONNECTED_PATHS_V41"] = _replace_once(
        updated["PARK_CONNECTED_PATHS_V41"],
        "// CITYROAD_V41_PARK_CONNECTED_PATHS\n",
        f"// CITYROAD_V41_PARK_CONNECTED_PATHS\n// {MARKER}\nfloat park_surface_lift={PARK_LIFT:.2f};\n",
        "PARK_CONNECTED_PATHS_V41")
    updated["PARK_CONNECTED_PATHS_V41"] = _replace_once(
        updated["PARK_CONNECTED_PATHS_V41"], "center.y+0.02,\"paths\"",
        "center.y+park_surface_lift+0.02,\"paths\"", "PARK_CONNECTED_PATHS_V41")
    updated["PARK_CONNECTED_PATHS_V41"] = _replace_once(
        updated["PARK_CONNECTED_PATHS_V41"], "center.y,\"collision\"",
        "center.y+park_surface_lift,\"collision\"", "PARK_CONNECTED_PATHS_V41")

    updated["PARK_WOODLAND_LAYERS_V41"] = _replace_once(
        updated["PARK_WOODLAND_LAYERS_V41"],
        "// CITYROAD_V41_PARK_WOODLAND_LAYERS\n",
        f"// CITYROAD_V41_PARK_WOODLAND_LAYERS\n// {MARKER}\nfloat park_surface_lift={PARK_LIFT:.2f};\n",
        "PARK_WOODLAND_LAYERS_V41")
    updated["PARK_WOODLAND_LAYERS_V41"] = _replace_once(
        updated["PARK_WOODLAND_LAYERS_V41"], "center.y,bbmin.z",
        "center.y+park_surface_lift,bbmin.z", "PARK_WOODLAND_LAYERS_V41")

    updated["PARK_EXCLUSION_V41"] = _replace_once(
        updated["PARK_EXCLUSION_V41"],
        "// CITYROAD_V41_PARK_EXCLUSION\n",
        f"// CITYROAD_V41_PARK_EXCLUSION\n// {MARKER}\nfloat park_surface_lift={PARK_LIFT:.2f};\n",
        "PARK_EXCLUSION_V41")
    updated["PARK_EXCLUSION_V41"] = _replace_once(
        updated["PARK_EXCLUSION_V41"], "p.y=center.y;",
        "p.y=center.y+park_surface_lift;", "PARK_EXCLUSION_V41")

    updated["PARK_CONTRACT_V41"] = _replace_once(
        updated["PARK_CONTRACT_V41"],
        "// CITYROAD_V41_PARK_MASTERPLAN_CONTRACT\n",
        f"// CITYROAD_V41_PARK_MASTERPLAN_CONTRACT\n// {MARKER}\n",
        "PARK_CONTRACT_V41")
    updated["PARK_CONTRACT_V41"] = _replace_once(
        updated["PARK_CONTRACT_V41"],
        'setdetailattrib(0,"park_masterplan_version",41,"set");',
        'setdetailattrib(0,"park_masterplan_version",41,"set");\n'
        'setdetailattrib(0,"park_surface_lift",0.12,"set");',
        "PARK_CONTRACT_V41")

    try:
        with hou.undos.group("CityRoad V43 Park Surface Lift"):
            for name, snippet in updated.items():
                nodes[name].parm("snippet").set(snippet)
        result = _validate_result(nodes)
        result["idempotent"] = False
        return result
    except Exception:
        for name, snippet in snippets.items():
            nodes[name].parm("snippet").set(snippet)
        raise


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=18811)
    parser.add_argument("--save", default="false")
    args = parser.parse_args()
    if args.save.lower() != "false":
        raise RuntimeError("Only --save false is supported")

    import hrpyc
    connection, _remote_hou = hrpyc.import_remote_module(args.host, args.port, "hou")
    try:
        tools_path = str(SCRIPT_DIR).replace("\\", "/")
        connection.execute(
            "import sys, importlib; "
            f"sys.path.insert(0, {tools_path!r}) if {tools_path!r} not in sys.path else None; "
            "import patch_cityroad_park_surface_lift_v43_20260824 as _cityroad_v43; "
            "importlib.reload(_cityroad_v43)")
        payload = connection.eval("_cityroad_v43.patch(save=False)")
        print(json.dumps(payload, ensure_ascii=False, default=list, indent=2))
    finally:
        connection.close()


if __name__ == "__main__":
    main()
