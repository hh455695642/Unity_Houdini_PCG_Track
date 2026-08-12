"""Keep CityRoad street furniture outside junction road surfaces.

Live ``/obj/CityRoad_DEV`` is the implementation source.  This patch only
updates the two existing street-furniture wrangles, defaults to ``save=False``,
and does not update the HDA definition or HIP file.
"""

from __future__ import annotations

import argparse
import hashlib

import hou


ASSET_PATH = "/obj/CityRoad_DEV"
CORE_NAME = "CityRoadCore"
ASSET_TYPE = "pcgbike::CityRoad::1.0"
LAMP_NODE = "CITYROAD_STREET_BUILD_LAMPS_V1"
TREE_NODE = "CITYROAD_STREET_BUILD_TREES_V1"
OLD_SHA256 = {
    LAMP_NODE: "fc3edd30bde1b7c47bb708d1fec41679bd61fe9ad01b04737c1478f438396222",
    TREE_NODE: "662357f753f9f5435bd0059bfe66f31702e362af5729a47e99676b5727fe8b58",
}
MARKER = "CITYROAD_STREET_FURNITURE_ROAD_CONTAINMENT_V2"


def _sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _patched_snippet(name: str, snippet: str) -> str:
    already_marked = MARKER in snippet
    expected = OLD_SHA256[name]
    if not already_marked and _sha256(snippet) != expected:
        raise RuntimeError(
            f"{name} prerequisite snippet hash changed: {_sha256(snippet)} != {expected}")

    old_helper = """int near_junction_v1(int input_index; vector position; float clearance)
{
    int junctions[] = expandpointgroup(input_index, "junction_points");
    foreach (int junction; junctions)
    {
        vector junction_position = point(input_index, "P", junction);
        if (distance(position, junction_position) < clearance)
            return 1;
    }
    return 0;
}"""
    new_helper = """int near_junction_v1(int input_index; vector position; float clearance)
{
    // The centerline contract currently carries an empty junction_points group.
    // The validated approach metadata repeats the real junction_center value.
    for (int junction = 0; junction < npoints(input_index); ++junction)
    {
        vector junction_position = haspointattrib(input_index, "junction_center")
            ? point(input_index, "junction_center", junction)
            : point(input_index, "P", junction);
        if (distance(position, junction_position) < clearance)
            return 1;
    }
    return 0;
}"""
    if old_helper in snippet:
        snippet = snippet.replace(old_helper, new_helper)
    elif new_helper not in snippet:
        raise RuntimeError(f"{name} junction helper prerequisite changed")

    if name == LAMP_NODE:
        old = """        if (near_junction_v1(0, center, clearance))
            continue;
        vector lateral = normalize(cross(set(0, 1, 0), tangent));"""
        new = """        // CITYROAD_STREET_FURNITURE_ROAD_CONTAINMENT_V2
        // A junction point sits at the road centre.  Its exclusion radius must
        // include the road footprint before applying the authored extra gap.
        float junction_clearance = 0.5 * road_width + clearance;
        if (near_junction_v1(1, center, junction_clearance))
            continue;
        vector lateral = normalize(cross(set(0, 1, 0), tangent));"""
    else:
        old = """            int blocked = near_junction_v1(0, center, endpoint_clearance);
            if (blocked)
                ++skipped_junction;"""
        new = """            // CITYROAD_STREET_FURNITURE_ROAD_CONTAINMENT_V2
            // Keep the candidate outside the junction road footprint, then add
            // junction_endpoint_clearance beyond that footprint.
            float junction_clearance = 0.5 * road_width + endpoint_clearance;
            int blocked = near_junction_v1(2, center, junction_clearance);
            if (blocked)
                ++skipped_junction;"""
    if old in snippet:
        return snippet.replace(old, new)
    if new in snippet:
        return snippet
    # V2 may already exist with the old empty-group input index.  Upgrade it
    # in place without reapplying the whole block.
    old_index = "near_junction_v1(0, center, junction_clearance)"
    new_index = ("near_junction_v1(1, center, junction_clearance)" if name == LAMP_NODE
                 else "near_junction_v1(2, center, junction_clearance)")
    if old_index in snippet:
        return snippet.replace(old_index, new_index)
    raise RuntimeError(f"{name} prerequisite block changed")


def apply(save: bool = False) -> dict:
    asset = hou.node(ASSET_PATH)
    if asset is None or asset.type().name() != ASSET_TYPE:
        raise RuntimeError(f"Expected {ASSET_TYPE} at {ASSET_PATH}")
    core = asset.node(CORE_NAME)
    if core is None:
        raise RuntimeError(f"Missing {CORE_NAME}")

    previous = {}
    changed = []
    try:
        for name in (LAMP_NODE, TREE_NODE):
            node = core.node(name)
            if node is None:
                raise RuntimeError(f"Missing street furniture node: {name}")
            parm = node.parm("snippet")
            previous[name] = parm.unexpandedString()
            patched = _patched_snippet(name, previous[name])
            if patched != previous[name]:
                parm.set(patched)
                changed.append(name)

        junctions = core.node("CITYROAD_JUNCTION_APPROACH_METADATA")
        core.node(LAMP_NODE).setInput(1, junctions)
        core.node(TREE_NODE).setInput(2, junctions)

        for name in (LAMP_NODE, TREE_NODE, "CITYROAD_STREET_BUILD_TREE_PITS_V1"):
            node = core.node(name)
            node.cook(force=True)
            if node.errors() or node.warnings():
                raise RuntimeError(
                    f"{name} cook diagnostics: errors={node.errors()} warnings={node.warnings()}")
        if save:
            hou.hipFile.save()
        return {"status": "PASS", "changed": changed, "saved": bool(save)}
    except Exception:
        for name, snippet in previous.items():
            node = core.node(name)
            if node is not None:
                node.parm("snippet").set(snippet)
        raise


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--save", action="store_true")
    args = parser.parse_args()
    print(apply(save=args.save))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
