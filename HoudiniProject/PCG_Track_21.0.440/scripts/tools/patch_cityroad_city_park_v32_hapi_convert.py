"""Insert a native Convert SOP before City Park HAPI topology normalization."""

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
SUBNET_PATH = "CityRoadCore/CR_CITY_PARK"
SWITCH_NAME = "PARK_ENABLE_INPUT_SWITCH"
CONVERT_NAME = "PARK_CONVERT_HAPI_CURVE_V32"
NORMALIZER_NAME = "PARK_REBUILD_HAPI_TOPOLOGY_V29"
EXPECTED_HDA_SUFFIX = "/Assets/PCG/HDA/City/CityRoad.hda"
EXPECTED_HIP_SUFFIX = "/HoudiniProject/PCG_Track_21.0.440/PCG_Bike_CityRoad.hip"


def _normalize(value: str) -> str:
    return value.replace("\\", "/")


def apply_live_patch(
        save: bool = False,
        capture_verified_dirty: bool = False,
        hou_module=None) -> dict:
    global hou
    if hou_module is not None:
        hou = hou_module
    if hou is None:
        raise RuntimeError("The hou module is unavailable")
    if save:
        raise RuntimeError("V32 patch is save=False only; use the regression gate")
    asset = hou.node(ASSET_PATH)
    if asset is None or asset.type().name() != ASSET_TYPE:
        raise RuntimeError(f"Expected {ASSET_TYPE} at {ASSET_PATH}")
    definition = asset.type().definition()
    if definition is None:
        raise RuntimeError("CityRoad asset has no HDA definition")
    if not _normalize(definition.libraryFilePath()).endswith(EXPECTED_HDA_SUFFIX):
        raise RuntimeError("Unexpected CityRoad definition")
    if not _normalize(hou.hipFile.path()).endswith(EXPECTED_HIP_SUFFIX):
        raise RuntimeError("Unexpected CityRoad HIP")
    if hou.hipFile.hasUnsavedChanges() and not capture_verified_dirty:
        raise RuntimeError("CityRoad Live Scene changed after Capture; patch refused")

    subnet = asset.node(SUBNET_PATH)
    switch = subnet.node(SWITCH_NAME) if subnet is not None else None
    normalizer = subnet.node(NORMALIZER_NAME) if subnet is not None else None
    if subnet is None or switch is None or normalizer is None:
        raise RuntimeError("City Park HAPI normalization stages are missing")
    existing = subnet.node(CONVERT_NAME)
    if existing is not None:
        valid = (
            existing.type().name() == "convert"
            and existing.inputs()[0] == switch
            and normalizer.inputs()[0] == existing
            and existing.evalParm("fromtype") == 0
            and existing.evalParm("totype") == 0)
        if not valid:
            raise RuntimeError("Existing V32 HAPI Convert is inconsistent")
        return {"status": "PASS", "already_applied": True, "saved": False}
    if normalizer.inputs()[0] != switch:
        raise RuntimeError("V32 normalizer input precondition changed")

    convert = None
    try:
        with hou.undos.group("CityRoad V32 Native HAPI Curve Convert"):
            convert = subnet.createNode("convert", CONVERT_NAME, exact_type_name=True)
            convert.parm("fromtype").set(0)
            convert.parm("totype").set(0)
            convert.setComment(
                "将 Unity/HAPI Curve Part 原生转换为 polygon；"
                "后续 V29 节点再统一重复端点与闭合拓扑。")
            convert.setGenericFlag(hou.nodeFlag.DisplayComment, True)
            convert.setColor(hou.Color((0.25, 0.65, 0.85)))
            convert.setPosition(
                (switch.position() + normalizer.position()) * 0.5)
            convert.setInput(0, switch)
            normalizer.setInput(0, convert)
            normalizer.cook(force=True)
            if normalizer.errors() or normalizer.warnings():
                raise RuntimeError(
                    f"V32 normalizer diagnostics: errors={normalizer.errors()} "
                    f"warnings={normalizer.warnings()}")
    except Exception:
        normalizer.setInput(0, switch)
        if convert is not None:
            convert.destroy()
        raise
    return {
        "status": "PASS",
        "already_applied": False,
        "saved": False,
        "node": convert.path(),
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=18811)
    parser.add_argument("--save", default="false")
    parser.add_argument("--capture-verified-dirty", default="false")
    args = parser.parse_args()
    if args.save.lower() != "false":
        raise RuntimeError("Only --save false is supported")
    import hrpyc
    connection, _remote_hou = hrpyc.import_remote_module(args.host, args.port, "hou")
    try:
        tools_path = str(Path(__file__).resolve().parent).replace("\\", "/")
        connection.execute(
            "import sys, importlib; "
            f"sys.path.insert(0, {tools_path!r}) if {tools_path!r} not in sys.path else None; "
            "import patch_cityroad_city_park_v32_hapi_convert as _park_v32; "
            "importlib.reload(_park_v32)")
        payload = connection.eval(
            "_park_v32.apply_live_patch(save=False, capture_verified_dirty="
            f"{args.capture_verified_dirty.lower() == 'true'!r})")
        print(json.dumps(payload, ensure_ascii=False, default=list, indent=2))
    finally:
        connection.close()


if __name__ == "__main__":
    main()
