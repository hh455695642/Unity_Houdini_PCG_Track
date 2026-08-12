"""Incremental V14 fix for CityRoad non-terminal boundary rounding.

V13 correctly identifies square open-end cap corners, but attempted to read a
point attribute written earlier in the same detail-wrangle execution.  VEX
reads the input geometry snapshot, so untagged corners were observed as zero
and every boundary corner skipped the V9 rounding path.  V14 keeps the exact
matched point numbers in local arrays and uses those arrays for control flow.

The current live CityRoad instance is the only implementation source.  This
patch defaults to ``save=False``, is idempotent, and restores the snippet if
validation fails.  Historical patch modules are not imported.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

import hou


ASSET_PATH = "/obj/CityRoad_DEV"
ASSET_TYPE = "pcgbike::CityRoad::1.0"
DEFINITION_SUFFIX = "Assets/PCG/HDA/City/CityRoad.hda"
HIP_SUFFIX = "HoudiniProject/PCG_Track_21.0.440/PCG_Bike_CityRoad.hip"
CORE_NAME = "CityRoadCore"
NODE_NAME = "ROAD_UNION_ROUND_FINAL_BOUNDARY"
V13_MARKER = "CITYROAD_V13_SQUARE_OPEN_ENDS"
V14_MARKER = "CITYROAD_V14_NONTERMINAL_ROUNDING"


ARRAY_DECLARATION_ANCHOR = "    int v13_square_cap_edge_count = 0;\n"
ARRAY_DECLARATION = (
    ARRAY_DECLARATION_ANCHOR
    + "    // CITYROAD_V14_NONTERMINAL_ROUNDING\n"
    + "    // Use local arrays for same-cook control flow.  Point attributes\n"
    + "    // remain output metadata only; point() cannot read values written\n"
    + "    // earlier by this detail wrangle.\n"
    + "    int v14_square_corner_points[];\n"
    + "    int v14_square_corner_terminals[];\n"
)

MATCH_ANCHOR = (
    "                v13_square_corner_target_count += 2;\n"
    "                ++v13_square_cap_edge_count;\n"
)
MATCH_REPLACEMENT = (
    "                append(v14_square_corner_points, best_edge_a);\n"
    "                append(v14_square_corner_terminals, v13_terminal_count);\n"
    "                append(v14_square_corner_points, best_edge_b);\n"
    "                append(v14_square_corner_terminals, v13_terminal_count);\n"
    + MATCH_ANCHOR
)

READBACK_ANCHOR = (
    "            int v13_terminal_id = point(\n"
    "                0, \"v13_open_terminal_id\", points[i]);\n"
    "            if (v13_terminal_id >= 0)\n"
)
READBACK_REPLACEMENT = (
    "            int v14_terminal_index = find(\n"
    "                v14_square_corner_points, points[i]);\n"
    "            int v13_terminal_id = v14_terminal_index >= 0\n"
    "                ? v14_square_corner_terminals[v14_terminal_index] : -1;\n"
    "            if (v13_terminal_id >= 0)\n"
)

DETAIL_ANCHOR = (
    "    setdetailattrib(0, \"square_open_end_occluded_terminal_count\",\n"
    "        max(0, v13_terminal_count - v13_square_cap_edge_count), \"set\");\n"
)
DETAIL_REPLACEMENT = (
    DETAIL_ANCHOR
    + "    setdetailattrib(0, \"cityroad_nonterminal_rounding_patch\",\n"
    + "        \"V14\", \"set\");\n"
    + "    setdetailattrib(0, \"nonterminal_rounding_candidate_count\",\n"
    + "        final_boundary_rounded_corner_count\n"
    + "        + v13_square_corner_skip_count, \"set\");\n"
)


def require_node(core: hou.Node, name: str) -> hou.Node:
    node = core.node(name)
    if node is None:
        raise RuntimeError(f"Missing CityRoad node: {name}")
    return node


def snippet(node: hou.Node) -> str:
    parameter = node.parm("snippet")
    if parameter is None:
        raise RuntimeError(f"Node has no snippet parameter: {node.path()}")
    return parameter.evalAsString()


def replace_once(source: str, old: str, new: str, label: str) -> str:
    count = source.count(old)
    if count != 1:
        raise RuntimeError(f"{label}: expected one precondition, found {count}")
    return source.replace(old, new, 1)


def metric(node: hou.Node, name: str, default=None):
    geometry = node.geometry()
    attribute = geometry.findGlobalAttrib(name)
    return geometry.attribValue(attribute) if attribute is not None else default


def validate(core: hou.Node) -> dict:
    boundary = require_node(core, NODE_NAME)
    output = require_node(core, "OUT_SIDEWALK_CURB")
    for node in (boundary, output):
        try:
            node.cook(force=True)
        except hou.OperationFailed as exception:
            raise RuntimeError(
                f"Cook failed at {node.path()}: "
                f"errors={node.errors()} warnings={node.warnings()}") from exception
        if node.errors() or node.warnings():
            raise RuntimeError(
                f"Cook diagnostics at {node.path()}: "
                f"errors={node.errors()} warnings={node.warnings()}")

    values = {
        "terminal_count": int(metric(
            boundary, "square_open_end_terminal_count", -1)),
        "cap_count": int(metric(
            boundary, "square_open_end_cap_edge_count", -1)),
        "occluded_count": int(metric(
            boundary, "square_open_end_occluded_terminal_count", -1)),
        "skip_count": int(metric(
            boundary, "square_open_end_corner_skip_count", -1)),
        "rounded_count": int(metric(
            boundary, "final_boundary_mobile_rounded_corner_count", -1)),
        "right_angle_count": int(metric(
            boundary, "final_boundary_mobile_right_angle_corner_count", -1)),
        "candidate_count": int(metric(
            boundary, "nonterminal_rounding_candidate_count", -1)),
        "max_segments": int(metric(
            boundary, "final_boundary_mobile_max_segment_count", -1)),
        "patch": str(metric(
            boundary, "cityroad_nonterminal_rounding_patch", "")),
    }
    checks = {
        "terminal_accounting": (
            values["terminal_count"], values["cap_count"],
            values["occluded_count"]) == (8, 7, 1),
        "square_skips": values["skip_count"] == 14,
        "rounded_count": values["rounded_count"] == 32,
        "right_angle_count": values["right_angle_count"] == 10,
        "candidate_accounting": values["candidate_count"] == (
            values["rounded_count"] + values["skip_count"]) == 46,
        "mobile_cap": values["max_segments"] == 4,
        "patch": values["patch"] == "V14",
    }
    failed = [name for name, passed in checks.items() if not passed]
    if failed:
        raise RuntimeError(f"V14 validation failed {failed}: {values}")
    return values


def apply(save: bool = False) -> dict:
    asset = hou.node(ASSET_PATH)
    if asset is None or asset.type().name() != ASSET_TYPE:
        raise RuntimeError(f"Expected {ASSET_TYPE} at {ASSET_PATH}")
    definition = asset.type().definition()
    if definition is None:
        raise RuntimeError("CityRoad instance has no HDA definition")
    if not definition.libraryFilePath().replace("\\", "/").endswith(
            DEFINITION_SUFFIX):
        raise RuntimeError("Unexpected CityRoad definition path")
    if not hou.hipFile.path().replace("\\", "/").endswith(HIP_SUFFIX):
        raise RuntimeError("Unexpected CityRoad HIP path")

    core = require_node(asset, CORE_NAME)
    node = require_node(core, NODE_NAME)
    original = snippet(node)
    if V13_MARKER not in original:
        raise RuntimeError("V14 requires the current V13 boundary implementation")
    if V14_MARKER in original:
        result = validate(core)
        result.update({"idempotent": True, "saved": False})
        return result

    try:
        source = replace_once(
            original, ARRAY_DECLARATION_ANCHOR, ARRAY_DECLARATION,
            "V14 array declaration")
        source = replace_once(
            source, MATCH_ANCHOR, MATCH_REPLACEMENT,
            "V14 matched corner recording")
        source = replace_once(
            source, READBACK_ANCHOR, READBACK_REPLACEMENT,
            "V14 local-array lookup")
        source = replace_once(
            source, DETAIL_ANCHOR, DETAIL_REPLACEMENT,
            "V14 detail metadata")
        node.parm("snippet").set(source)
        result = validate(core)
        result.update({"idempotent": False, "saved": False})
        if save:
            definition.updateFromNode(asset)
            hou.hipFile.save()
            result["saved"] = True
        return result
    except Exception:
        node.parm("snippet").set(original)
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
            "import patch_cityroad_nonterminal_rounding_v14 as _pcg_v14; "
            "importlib.reload(_pcg_v14)")
        return dict(connection.eval(f"_pcg_v14.apply(save={save!r})"))
    finally:
        connection.close()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=18811)
    parser.add_argument("--save", action="store_true")
    args = parser.parse_args()
    result = apply_remote(args.host, args.port, args.save)
    print(json.dumps(result, ensure_ascii=False, indent=2, default=list))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
