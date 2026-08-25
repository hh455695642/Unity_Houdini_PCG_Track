"""Normalize topologyless Unity HAPI curves before City Park generation."""

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
ASSET_TYPE = "pcgbike::CityRoad::1.0"
SUBNET_PATH = "CityRoadCore/CR_CITY_PARK"
SWITCH_NAME = "PARK_ENABLE_INPUT_SWITCH"
GENERATOR_NAME = "PARK_LAYOUT_AND_SCATTER_V20"
NORMALIZER_NAME = "PARK_REBUILD_HAPI_TOPOLOGY_V29"
EXPECTED_HDA_SUFFIX = "/Assets/PCG/HDA/City/CityRoad.hda"
EXPECTED_HIP_SUFFIX = "/HoudiniProject/PCG_Track_21.0.440/PCG_Bike_CityRoad.hip"
EXPECTED_GENERATOR_SHA256 = "c9d615f046d7d6541c953574ae723e69f677004ac79ae535eb3954f9c194637a"
PATCH_MARKER = "CITYROAD_V29_CITY_PARK_HAPI_TOPOLOGY_REBUILD"
OLD_SWITCH_EXPRESSION = (
    'if(ch("../../../enable_city_park")!=0 '
    '&& nprims("../IN_UNITY_PARK_AREAS")>0,1,0)')
NEW_SWITCH_EXPRESSION = (
    'if(ch("../../../enable_city_park")!=0 '
    '&& npoints("../IN_UNITY_PARK_AREAS")>0,1,0)')

NORMALIZER_SNIPPET = r'''
// CITYROAD_V29_CITY_PARK_HAPI_TOPOLOGY_REBUILD
// HEU 21 可上传有序点但不提供 vertex table；按重复首尾点拆分并重建闭合 polygon。
if (nvertices(0) == 0 && npoints(0) >= 4)
{
    int input_primitive_count = nprimitives(0);
    int point_count = npoints(0);
    int loop_start = 0;
    for (int point_index = 1; point_index < point_count; point_index++)
    {
        vector first_position = point(0,"P",loop_start);
        vector current_position = point(0,"P",point_index);
        if (point_index-loop_start >= 3
            && distance(first_position,current_position) < 0.1)
        {
            int rebuilt_primitive = addprim(0,"poly");
            for (int loop_point = loop_start;
                loop_point < point_index;
                loop_point++)
            {
                addvertex(0,rebuilt_primitive,loop_point);
            }
            loop_start = point_index+1;
        }
    }
    for (int input_primitive = input_primitive_count-1;
        input_primitive >= 0;
        input_primitive--)
    {
        removeprim(0,input_primitive,0);
    }
}
'''.strip()


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
        raise RuntimeError("V29 patch is save=False only; use the regression gate")
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
    generator = subnet.node(GENERATOR_NAME) if subnet is not None else None
    switch_parm = switch.parm("input") if switch is not None else None
    snippet_parm = generator.parm("snippet") if generator is not None else None
    if subnet is None or switch_parm is None or snippet_parm is None:
        raise RuntimeError("City Park input stages are missing")

    existing = subnet.node(NORMALIZER_NAME)
    if existing is not None:
        valid = (
            existing.type().name() == "attribwrangle"
            and PATCH_MARKER in existing.evalParm("snippet")
            and existing.inputs()[0] == switch
            and generator.inputs()[0] == existing
            and switch_parm.expression() == NEW_SWITCH_EXPRESSION)
        if not valid:
            raise RuntimeError("Existing V29 topology normalizer is inconsistent")
        return {"status": "PASS", "already_applied": True, "saved": False}

    generator_hash = hashlib.sha256(
        snippet_parm.rawValue().encode("utf-8")).hexdigest()
    if generator_hash != EXPECTED_GENERATOR_SHA256:
        raise RuntimeError(
            "City Park V28 generator precondition changed: "
            f"snippet_sha256={generator_hash}")
    if generator.inputs()[0] != switch:
        raise RuntimeError("City Park generator input precondition changed")
    old_switch_expression = switch_parm.expression()
    if old_switch_expression != OLD_SWITCH_EXPRESSION:
        raise RuntimeError(
            "City Park Switch precondition changed: "
            f"expression={old_switch_expression!r}")

    normalizer = None
    try:
        with hou.undos.group("CityRoad V29 HAPI Topology Normalizer"):
            normalizer = subnet.createNode(
                "attribwrangle", NORMALIZER_NAME, exact_type_name=True)
            normalizer.parm("class").set(0)
            normalizer.parm("snippet").set(NORMALIZER_SNIPPET)
            normalizer.setComment(
                "Unity/HAPI 21 闭合 Spline 可能只有有序点而没有 vertex table；"
                "本节点先重建 polygon，再交给公园生成器。")
            normalizer.setGenericFlag(hou.nodeFlag.DisplayComment, True)
            normalizer.setColor(hou.Color((0.30, 0.55, 0.80)))
            normalizer.setPosition(
                (switch.position() + generator.position()) * 0.5)
            normalizer.setInput(0, switch)
            generator.setInput(0, normalizer)
            switch_parm.setExpression(
                NEW_SWITCH_EXPRESSION, language=hou.exprLanguage.Hscript)
            generator.cook(force=True)
            if generator.errors() or generator.warnings():
                raise RuntimeError(
                    f"V29 generator diagnostics: errors={generator.errors()} "
                    f"warnings={generator.warnings()}")
    except Exception:
        generator.setInput(0, switch)
        switch_parm.setExpression(
            old_switch_expression, language=hou.exprLanguage.Hscript)
        if normalizer is not None:
            normalizer.destroy()
        raise
    return {
        "status": "PASS",
        "already_applied": False,
        "saved": False,
        "normalizer_snippet_sha256": hashlib.sha256(
            NORMALIZER_SNIPPET.encode("utf-8")).hexdigest(),
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
            "import patch_cityroad_city_park_v29_hapi_topology as _park_v29; "
            "importlib.reload(_park_v29)")
        payload = connection.eval(
            "_park_v29.apply_live_patch(save=False, capture_verified_dirty="
            f"{args.capture_verified_dirty.lower() == 'true'!r})")
        print(json.dumps(payload, ensure_ascii=False, default=list, indent=2))
    finally:
        connection.close()


if __name__ == "__main__":
    main()
