"""Regression fixture for CityRoad short-curve marking generation.

The five input curves mirror the shortened Unity SplineContainer in
Assets/PCG/Scenes/PCG_City.unity. Unity X is negated for Houdini's handedness.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import hou


SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = SCRIPT_DIR.parents[3]
DEFAULT_HDA = PROJECT_ROOT / "Assets/PCG/HDA/City/CityRoad.hda"
ASSET_TYPE = "pcgbike::CityRoad::1.0"
VALIDATOR_NAME = "CITYROAD_VALIDATE_STATIC_MARKING_JUNCTION_CLIP_V24"

CURVES = (
    ((254.0, 0.0, 57.0), (-1015.0, 0.0, 77.0)),
    ((-292.0, 0.0, 443.9), (-310.0, 0.0, -1239.0)),
    ((-660.0, 0.0, 302.0), (-715.0, 0.0, -835.0), (126.0, 0.0, -855.0)),
    ((121.0, 0.0, -172.0), (-1446.0, 0.0, -955.0)),
    ((-831.31, 0.0, 73.95), (-1316.0, 0.0, -1157.0)),
)


def require(condition: bool, message: str) -> None:
    if not condition:
        raise RuntimeError(message)


def build_input() -> hou.Node:
    container = hou.node("/obj").createNode("geo", "CITYROAD_V24_SHORT_CURVE_INPUT")
    for child in container.children():
        child.destroy()
    source = container.createNode("python", "BUILD_UNITY_SHORT_CURVES")
    source.parm("python").set(
        """geo = hou.pwd().geometry()
geo.clear()
curves = %r
specs = (
    (\"road_id\", hou.attribType.Prim, 0),
    (\"road_width\", hou.attribType.Prim, 16.0),
    (\"lane_count\", hou.attribType.Prim, 2),
    (\"lane_width\", hou.attribType.Prim, 3.5),
    (\"road_class\", hou.attribType.Prim, 0),
    (\"road_level\", hou.attribType.Prim, 0),
    (\"allow_junction\", hou.attribType.Prim, 1),
    (\"is_bridge\", hou.attribType.Prim, 0),
    (\"is_race_route\", hou.attribType.Prim, 0),
)
attribs = {name: geo.addAttrib(kind, name, default) for name, kind, default in specs}
for road_id, positions in enumerate(curves):
    primitive = geo.createPolygon()
    primitive.setIsClosed(False)
    for position in positions:
        point = geo.createPoint()
        point.setPosition(position)
        primitive.addVertex(point)
    primitive.setAttribValue(attribs[\"road_id\"], road_id)
""" % (CURVES,))
    source.setDisplayFlag(True)
    source.setRenderFlag(True)
    source.cook(force=True)
    require(not source.errors(), f"Short-curve source cook failed: {source.errors()}")
    return source


def run(hda_path: Path, expect: str) -> dict:
    hou.hipFile.clear(suppress_save_prompt=True)
    hou.hda.installFile(str(hda_path))
    source = build_input()
    asset = hou.node("/obj").createNode(ASSET_TYPE, "CityRoad_V24_REGRESSION")
    asset.parm("unity_road_network").set(source.path())
    parameters = {
        "default_road_width": 16.0,
        "default_lane_count": 2,
        "enable_road_markings": 1,
        "enable_crosswalks": 1,
        "marking_dash_length": 3.0,
        "marking_dash_gap": 6.0,
        "junction_endpoint_clearance": 6.0,
        "road_corner_inner_radius_ratio": 0.2,
    }
    for name, value in parameters.items():
        parm = asset.parm(name)
        require(parm is not None, f"Missing CityRoad parameter: {name}")
        parm.set(value)

    core = asset.node("CityRoadCore")
    builder = core.node("CITYROAD_BUILD_STATIC_MARKING_MESH")
    validator = core.node(VALIDATOR_NAME)
    output = core.node("OUT_ROAD_MARKINGS")
    try:
        output.cook(force=True)
    except hou.OperationFailed:
        pass

    output_geometry = output.geometry()
    output_primitives = len(output_geometry.prims()) if output_geometry is not None else 0
    builder_errors = list(builder.errors())
    validator_errors = list(validator.errors()) if validator is not None else []
    intrusion = -1
    validator_geometry = validator.geometry() if validator is not None else None
    if validator_geometry is not None and validator_geometry.findGlobalAttrib(
            "longitudinal_marking_junction_intrusion_count") is not None:
        intrusion = int(validator_geometry.attribValue(
            "longitudinal_marking_junction_intrusion_count"))

    if expect == "broken":
        require(validator is None, "Broken fixture unexpectedly contains V24 validator")
        require(output_primitives == 0, "Broken fixture unexpectedly emitted markings")
        require(any("longitudinal marking intrusion count=1" in item
                    for item in builder_errors),
                f"Broken fixture did not reproduce false intrusion: {builder_errors}")
    else:
        require(validator is not None, "V24 validator node is missing")
        require(not builder_errors, f"Static marking builder errors: {builder_errors}")
        require(not validator_errors, f"Post-commit validator errors: {validator_errors}")
        require(output_primitives > 0, "Short curves produced no road markings")
        require(intrusion == 0, f"True post-commit intrusion count is {intrusion}")

    return {
        "status": "PASS",
        "expect": expect,
        "asset_locked": asset.isLockedHDA(),
        "input_curve_count": len(CURVES),
        "output_primitive_count": output_primitives,
        "builder_errors": builder_errors,
        "validator_errors": validator_errors,
        "longitudinal_intrusion_count": intrusion,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--hda", type=Path, default=DEFAULT_HDA)
    parser.add_argument("--expect", choices=("broken", "fixed"), required=True)
    args = parser.parse_args()
    print(json.dumps(run(args.hda.resolve(), args.expect), indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
