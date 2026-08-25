"""V44 incremental patch: raise City Park above Unity's baked sidewalk surface.

Unity Bake measurement found every grass sample covered by sidewalk geometry at
Y=0.5705 while V43 grass was Y=0.12.  V44 uses a 0.65 m park datum, leaving
the lowest visible layer (water, 0.61 m) about 3.95 cm above the cover plane.
The patch is hash-gated, idempotent, rollback-safe, and deliberately save=False.
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
BASELINE_TREE_SHA256 = "12c38240e46c73d269b89eea08f0366b0c97404588588d186386c1d3d1720e2e"
MARKER = "CITYROAD_V44_PARK_VISIBLE_ABOVE_SIDEWALK"
OLD_LIFT = 0.12
PARK_LIFT = 0.65
SCRIPT_DIR = Path(__file__).resolve().parent

EXPECTED_SNIPPET_SHA256 = {
    "PARK_SURFACE_ZONES_V41": "4f3aecf503e23d858fef183d3024142475d0b3b874893a0d24504f2e067273fe",
    "PARK_CONNECTED_PATHS_V41": "4aaa4e30f67e04c7e714a6d0775ee8b955e56fcc334d269572fc4ab191a2b1a0",
    "PARK_WOODLAND_LAYERS_V41": "42e165e2b8f11c37a0f89c7521205152e2e50512d8f74278bb34dfd72580ef75",
    "PARK_EXCLUSION_V41": "8ed2f448cd6d98ccbd96b4a493233226442bf58b1d971d7a92e3948f23d7d3cf",
    "PARK_CONTRACT_V41": "638b9a6e2168ba46bc04e54b43e7762d8358fc5a7a285314ffb7bc64807475e1",
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
    if Path(hou.hipFile.path().replace("\\", "/")).name != EXPECTED_HIP:
        raise RuntimeError(f"Unexpected HIP: {hou.hipFile.path()}")
    asset = hou.node(ASSET_PATH)
    if asset is None or asset.type().nameWithCategory() != "pcgbike::Object/CityRoad::1.0":
        raise RuntimeError(f"Missing expected CityRoad instance: {ASSET_PATH}")
    definition = asset.type().definition()
    library = definition.libraryFilePath().replace("\\", "/") if definition else ""
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
            raise RuntimeError(f"{name}: missing V44 marker")
        node.cook(force=True)
        if node.errors() or node.warnings():
            raise RuntimeError(
                f"{name}: cook diagnostics errors={node.errors()} warnings={node.warnings()}")
    for name in (
            "PARK_SURFACE_ZONES_V41", "PARK_CONNECTED_PATHS_V41",
            "PARK_WOODLAND_LAYERS_V41", "PARK_EXCLUSION_V41"):
        snippet = nodes[name].parm("snippet").unexpandedString()
        if "float park_surface_lift=0.65;" not in snippet:
            raise RuntimeError(f"{name}: V44 lift is not 0.65")
    contract = nodes["PARK_CONTRACT_V41"].parm("snippet").unexpandedString()
    if 'setdetailattrib(0,"park_surface_lift",0.65,"set");' not in contract:
        raise RuntimeError("PARK_CONTRACT_V41: V44 lift metadata is not 0.65")
    return {
        "status": "PASS", "marker": MARKER,
        "park_surface_lift": PARK_LIFT, "save": False,
        "snippet_sha256": {
            name: _sha256(node.parm("snippet").unexpandedString())
            for name, node in nodes.items()},
    }


def patch(*, save: bool = False) -> dict[str, object]:
    if save:
        raise RuntimeError("V44 patch is intentionally save=False; persist only after VerifyFull")
    park, nodes = _validate_identity()
    snippets = {name: node.parm("snippet").unexpandedString() for name, node in nodes.items()}
    states = {name: MARKER in snippet for name, snippet in snippets.items()}
    if all(states.values()):
        result = _validate_result(nodes)
        result["idempotent"] = True
        return result
    if any(states.values()):
        raise RuntimeError(f"Partial V44 state detected: {states}")
    if _tree_sha256(park) != BASELINE_TREE_SHA256:
        raise RuntimeError("V43 Live park tree changed after Capture")
    for name, expected in EXPECTED_SNIPPET_SHA256.items():
        actual = _sha256(snippets[name])
        if actual != expected:
            raise RuntimeError(f"{name}: snippet precondition changed: {actual} != {expected}")

    updated = dict(snippets)
    for name in (
            "PARK_SURFACE_ZONES_V41", "PARK_CONNECTED_PATHS_V41",
            "PARK_WOODLAND_LAYERS_V41", "PARK_EXCLUSION_V41"):
        updated[name] = _replace_once(
            updated[name], "// CITYROAD_V43_PARK_SURFACE_LIFT\n",
            "// CITYROAD_V43_PARK_SURFACE_LIFT\n"
            f"// {MARKER}\n", name)
        updated[name] = _replace_once(
            updated[name], "float park_surface_lift=0.12;",
            "float park_surface_lift=0.65;", name)
    updated["PARK_CONTRACT_V41"] = _replace_once(
        updated["PARK_CONTRACT_V41"], "// CITYROAD_V43_PARK_SURFACE_LIFT\n",
        "// CITYROAD_V43_PARK_SURFACE_LIFT\n"
        f"// {MARKER}\n", "PARK_CONTRACT_V41")
    updated["PARK_CONTRACT_V41"] = _replace_once(
        updated["PARK_CONTRACT_V41"],
        'setdetailattrib(0,"park_surface_lift",0.12,"set");',
        'setdetailattrib(0,"park_surface_lift",0.65,"set");',
        "PARK_CONTRACT_V41")

    try:
        with hou.undos.group("CityRoad V44 Park Visible Above Sidewalk"):
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
            "import patch_cityroad_park_visible_above_sidewalk_v44_20260824 as _cityroad_v44; "
            "importlib.reload(_cityroad_v44)")
        payload = connection.eval("_cityroad_v44.patch(save=False)")
        print(json.dumps(payload, ensure_ascii=False, default=list, indent=2))
    finally:
        connection.close()


if __name__ == "__main__":
    main()
