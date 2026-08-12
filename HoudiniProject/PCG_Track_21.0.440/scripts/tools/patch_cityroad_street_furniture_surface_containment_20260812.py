"""Reject CityRoad street-furniture candidates that overlap the final road top.

The Live ``/obj/CityRoad_DEV`` network is the implementation source.  The
patch is incremental, idempotent, defaults to ``save=False`` and only changes
the two existing street-furniture wrangles plus their road-surface inputs.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

import hou


ASSET_PATH = "/obj/CityRoad_DEV"
CORE_NAME = "CityRoadCore"
ASSET_TYPE = "pcgbike::CityRoad::1.0"
LAMP_NODE = "CITYROAD_STREET_BUILD_LAMPS_V1"
TREE_NODE = "CITYROAD_STREET_BUILD_TREES_V1"
SURFACE_NODE = "CITYROAD_TOPOLOGY_CLASSIFY_ROAD"
MARKER = "CITYROAD_STREET_FURNITURE_SURFACE_CONTAINMENT_V3"
OLD_SHA256 = {
    LAMP_NODE: "d2e1af8b91fd246acac26af69b7b3bb677cabf731fcf9e9ae81885f63bbdd2a8",
    TREE_NODE: "5a8d5c4089fc10c842accf381e184408f306fd36d98a5b5cb31810ace888cd59",
}


def _sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _add_helper(name: str, snippet: str) -> str:
    if MARKER in snippet:
        return snippet
    expected = OLD_SHA256[name]
    actual = _sha256(snippet)
    if actual != expected:
        raise RuntimeError(f"{name} prerequisite snippet hash changed: {actual} != {expected}")
    anchor = "\nstring group_key_v1(string kind; string prefab)\n"
    helper = """

int overlaps_road_surface_v3(int input_index; vector position; float sample_y)
{
    // Test in plan view at the road elevation.  xyzdist is zero when the
    // projected point lies inside a final road-top triangle.  The small
    // tolerance also rejects objects grazing a curb/road boundary.
    vector probe = position;
    probe.y = sample_y;
    int primitive = -1;
    vector uvw = 0;
    float surface_distance = xyzdist(input_index, probe, primitive, uvw);
    return primitive >= 0 && surface_distance <= 0.05;
}
"""
    if anchor not in snippet:
        raise RuntimeError(f"{name} helper insertion anchor changed")
    return snippet.replace(anchor, helper + anchor, 1)


def _patch_lamps(snippet: str) -> str:
    snippet = _add_helper(LAMP_NODE, snippet)
    if MARKER in snippet:
        return snippet
    old = """        vector lateral = normalize(cross(set(0, 1, 0), tangent));
        float offset = 0.5 * road_width + sidewalk_width - inset;
        for (int side_index = 0; side_index < 2; ++side_index)
        {
            int side = side_index == 0 ? -1 : 1;
            vector position = center + lateral * float(side) * offset;
            position.y += y_offset;"""
    new = """        vector lateral = normalize(cross(set(0, 1, 0), tangent));
        float offset = 0.5 * road_width + sidewalk_width - inset;
        // CITYROAD_STREET_FURNITURE_SURFACE_CONTAINMENT_V3
        // Lamps are a strict pair: if either final transform overlaps the
        // real road top, reject both instead of leaving a one-sided result.
        vector left_position = center - lateral * offset;
        vector right_position = center + lateral * offset;
        if (overlaps_road_surface_v3(2, left_position, center.y) ||
            overlaps_road_surface_v3(2, right_position, center.y))
        {
            ++skipped_road_surface_pairs;
            continue;
        }
        for (int side_index = 0; side_index < 2; ++side_index)
        {
            int side = side_index == 0 ? -1 : 1;
            vector position = center + lateral * float(side) * offset;
            position.y += y_offset;"""
    if old not in snippet:
        raise RuntimeError(f"{LAMP_NODE} generation block changed")
    snippet = snippet.replace(old, new, 1)
    snippet = snippet.replace(
        "int generated = 0;\nstring prefab = chs(\"../../lamp_prefab\");",
        "int generated = 0;\nint skipped_road_surface_pairs = 0;\nstring prefab = chs(\"../../lamp_prefab\");",
        1,
    )
    snippet = snippet.replace(
        'setdetailattrib(0, "street_lamp_instance_count", generated, "set");',
        'setdetailattrib(0, "street_lamp_instance_count", generated, "set");\n'
        'setdetailattrib(0, "street_lamp_skipped_road_surface_pair_count", '
        'skipped_road_surface_pairs, "set");',
        1,
    )
    return snippet


def _patch_trees(snippet: str) -> str:
    snippet = _add_helper(TREE_NODE, snippet)
    if MARKER in snippet:
        return snippet
    old = """            int blocked = near_junction_v1(2, center, junction_clearance);
            if (blocked)
                ++skipped_junction;
            if (!blocked && lamp_clearance > 0 && nearpoint(1, position, lamp_clearance) >= 0)"""
    new = """            int blocked = near_junction_v1(2, center, junction_clearance);
            if (blocked)
                ++skipped_junction;
            // CITYROAD_STREET_FURNITURE_SURFACE_CONTAINMENT_V3
            // The centre-based exclusion cannot describe irregular corners;
            // validate the actual final instance position against road tris.
            if (!blocked && overlaps_road_surface_v3(3, position, center.y))
            {
                blocked = 1;
                ++skipped_road_surface;
            }
            if (!blocked && lamp_clearance > 0 && nearpoint(1, position, lamp_clearance) >= 0)"""
    if old not in snippet:
        raise RuntimeError(f"{TREE_NODE} generation block changed")
    snippet = snippet.replace(old, new, 1)
    snippet = snippet.replace(
        "int skipped_junction = 0;\nint enabled =",
        "int skipped_junction = 0;\nint skipped_road_surface = 0;\nint enabled =",
        1,
    )
    snippet = snippet.replace(
        'setdetailattrib(0, "street_tree_skipped_junction_count", skipped_junction, "set");',
        'setdetailattrib(0, "street_tree_skipped_junction_count", skipped_junction, "set");\n'
        'setdetailattrib(0, "street_tree_skipped_road_surface_count", '
        'skipped_road_surface, "set");',
        1,
    )
    return snippet


def apply(save: bool = False) -> dict:
    asset = hou.node(ASSET_PATH)
    if asset is None or asset.type().name() != ASSET_TYPE:
        raise RuntimeError(f"Expected {ASSET_TYPE} at {ASSET_PATH}")
    core = asset.node(CORE_NAME)
    if core is None:
        raise RuntimeError(f"Missing {CORE_NAME}")
    lamps = core.node(LAMP_NODE)
    trees = core.node(TREE_NODE)
    surface = core.node(SURFACE_NODE)
    if lamps is None or trees is None or surface is None:
        raise RuntimeError("Missing street-furniture or final road-surface node")

    previous_snippets = {
        LAMP_NODE: lamps.parm("snippet").unexpandedString(),
        TREE_NODE: trees.parm("snippet").unexpandedString(),
    }
    previous_inputs = {
        LAMP_NODE: lamps.inputs(),
        TREE_NODE: trees.inputs(),
    }
    changed = []
    try:
        patched = {
            LAMP_NODE: _patch_lamps(previous_snippets[LAMP_NODE]),
            TREE_NODE: _patch_trees(previous_snippets[TREE_NODE]),
        }
        for name, node in ((LAMP_NODE, lamps), (TREE_NODE, trees)):
            if patched[name] != previous_snippets[name]:
                node.parm("snippet").set(patched[name])
                changed.append(name)
        lamps.setInput(2, surface)
        trees.setInput(3, surface)

        diagnostics = {}
        for name in (LAMP_NODE, TREE_NODE, "CITYROAD_STREET_BUILD_TREE_PITS_V1"):
            node = core.node(name)
            node.cook(force=True)
            diagnostics[name] = {
                "points": len(node.geometry().points()),
                "errors": list(node.errors()),
                "warnings": list(node.warnings()),
            }
            if node.errors() or node.warnings():
                raise RuntimeError(f"{name} cook diagnostics: {diagnostics[name]}")
        if save:
            hou.hipFile.save()
        return {
            "status": "PASS",
            "changed": changed,
            "saved": bool(save),
            "diagnostics": diagnostics,
        }
    except Exception:
        for name, node in ((LAMP_NODE, lamps), (TREE_NODE, trees)):
            node.parm("snippet").set(previous_snippets[name])
            for index, input_node in enumerate(previous_inputs[name]):
                node.setInput(index, input_node)
        raise


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=18811)
    parser.add_argument("--live", action="store_true")
    parser.add_argument("--save", action="store_true")
    args = parser.parse_args()
    if not args.live:
        print(json.dumps(apply(save=args.save), ensure_ascii=False, indent=2))
        return 0

    import hrpyc
    connection, _remote_hou = hrpyc.import_remote_module(args.host, args.port, "hou")
    try:
        script_dir = str(Path(__file__).resolve().parent).replace("\\", "/")
        connection.execute(
            "import sys, importlib, json; "
            f"sys.path.insert(0, {script_dir!r}) if {script_dir!r} not in sys.path else None; "
            "import patch_cityroad_street_furniture_surface_containment_20260812 as _pcg_surface; "
            "importlib.reload(_pcg_surface)")
        payload = connection.eval(
            f"_pcg_surface.json.dumps(_pcg_surface.apply(save={args.save!r}), "
            "ensure_ascii=False)")
        print(json.dumps(json.loads(str(payload)), ensure_ascii=False, indent=2))
    finally:
        connection.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
