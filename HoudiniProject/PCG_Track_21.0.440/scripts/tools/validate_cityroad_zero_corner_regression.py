"""Regression validator for the CityRoad zero-corner-tolerance fix (V22).

Reproduces the reported bug independently of the patch script:

    When a road curve is shortened below the corner-arc threshold, the road
    surface and its markings used to disappear because the corner-section
    pipeline hard-errored on "zero corner sections".

This validator feeds a single short L-shaped road (each leg ``--leg`` metres)
into the CityRoad live node, force-cooks the three public outputs, and asserts
that markings are produced and no node errors.  It also asserts the three
patched nodes carry the ``CITYROAD_V22_ZERO_CORNER_TOLERANCE`` marker.

Usage:
    hython validate_cityroad_zero_corner_regression.py --hip <path> [--leg 5]
"""

from __future__ import annotations

import argparse
import json

try:
    hou
except NameError:
    import hou


ASSET_PATH = "/obj/CityRoad_DEV"
CORE_PATH = f"{ASSET_PATH}/CityRoadCore"
MARKER = "CITYROAD_V22_ZERO_CORNER_TOLERANCE"

MARKED_NODES = (
    "CITYROAD_REPLACE_CORNER_WITH_QUAD_STRIPS_V11",
    "CR_UNION_BOUNDARY/CITYROAD_SNAP_FINAL_BOUNDARY_TO_CORNER_SECTIONS_V12",
    "CR_SIDEWALK_CONSTRAINT_BUILD/CITYROAD_REPLACE_SIDEWALK_CORNER_WITH_QUAD_STRIPS_V11",
)

ROAD_ATTRS = (
    "i@road_id=0;i@segment_id=0;i@road_level=0;i@lane_count=2;"
    "f@road_width=7.0;i@allow_junction=1;i@road_class=0;"
    "f@lane_width=3.5;i@is_bridge=0;i@is_race_route=0;"
)


def _make_short_road(core: hou.Node, leg: float) -> None:
    obj = hou.node("/obj")
    test = obj.node("_ZERO_CORNER_REGRESSION")
    if test is None:
        test = obj.createNode("geo", "_ZERO_CORNER_REGRESSION")
    for child in test.children():
        child.destroy()

    gen = test.createNode("python", "gen")
    gen.parm("python").set(
        "import hou\n"
        "geo = hou.pwd().geometry(); geo.clear()\n"
        "L = hou.ch('L')\n"
        "p0 = geo.createPoint(); p0.setPosition(hou.Vector3(0,0,0))\n"
        "p1 = geo.createPoint(); p1.setPosition(hou.Vector3(L,0,0))\n"
        "p2 = geo.createPoint(); p2.setPosition(hou.Vector3(L,L,0))\n"
        "pr = geo.createPolygon(False)\n"
        "pr.addVertex(p0); pr.addVertex(p1); pr.addVertex(p2)\n")
    tg = gen.parmTemplateGroup()
    tg.append(hou.FloatParmTemplate("L", "L", 1, default_value=(float(leg),)))
    gen.setParmTemplateGroup(tg)

    att = test.createNode("attribwrangle", "att")
    att.setInput(0, gen)
    att.parm("snippet").set(ROAD_ATTRS)
    out = test.createNode("null", "OUT")
    out.setInput(0, att)

    core.node("CR_INPUT_CONTRACT/IN_ROAD_NETWORK").parm("objpath1").set(
        "/obj/_ZERO_CORNER_REGRESSION/OUT")
    core.node("CR_INPUT_CONTRACT/SELECT_ROAD_NETWORK_SOURCE").parm("input").set(0)


def validate(leg: float = 5.0) -> dict:
    asset = hou.node(ASSET_PATH)
    if asset is None or asset.type().name() != "pcgbike::CityRoad::1.0":
        raise RuntimeError(f"Expected pcgbike::CityRoad::1.0 at {ASSET_PATH}")
    core = hou.node(CORE_PATH)
    if core is None:
        raise RuntimeError(f"Missing {CORE_PATH}")

    markers_ok = {}
    for rel in MARKED_NODES:
        node = core.node(rel)
        if node is None:
            raise RuntimeError(f"Missing marked node: {CORE_PATH}/{rel}")
        markers_ok[rel] = MARKER in node.parm("snippet").unexpandedString()

    _make_short_road(core, leg)

    outputs = {}
    for name in ("OUT_ROAD_SURFACE", "OUT_ROAD_MARKINGS", "OUT_SIDEWALK_CURB"):
        node = core.node(name)
        if node is None:
            raise RuntimeError(f"Missing output node: {name}")
        node.cook(force=True)
        outputs[name] = {
            "errors": list(node.errors()),
            "warnings": list(node.warnings()),
        }

    mark = core.node("CITYROAD_BUILD_STATIC_MARKING_MESH")
    mark.cook(force=True)
    geo = mark.geometry()
    marking_count = int(geo.attribValue("marking_primitive_count"))

    failures = []
    if not all(markers_ok.values()):
        failures.append(f"missing marker on: "
                        f"{[k for k, v in markers_ok.items() if not v]}")
    for name, diag in outputs.items():
        if diag["errors"]:
            failures.append(f"{name} errors: {diag['errors']}")
    if marking_count <= 0:
        failures.append(f"marking_primitive_count={marking_count} (expected > 0)")

    return {
        "status": "PASS" if not failures else "FAIL",
        "leg": leg,
        "markers_ok": markers_ok,
        "marking_primitive_count": marking_count,
        "outputs": outputs,
        "failures": failures,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--hip", default="", help="HIP file to load first")
    parser.add_argument("--leg", type=float, default=5.0)
    args = parser.parse_args()
    if args.hip:
        hou.hipFile.load(args.hip, ignore_load_warnings=True)
    result = validate(leg=args.leg)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
