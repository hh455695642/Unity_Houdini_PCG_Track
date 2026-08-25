"""Detect Unity HAPI closed curves by duplicated endpoint runs."""

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
NORMALIZER_PATH = (
    "CityRoadCore/CR_CITY_PARK/PARK_REBUILD_HAPI_TOPOLOGY_V29")
EXPECTED_HDA_SUFFIX = "/Assets/PCG/HDA/City/CityRoad.hda"
EXPECTED_HIP_SUFFIX = "/HoudiniProject/PCG_Track_21.0.440/PCG_Bike_CityRoad.hip"
EXPECTED_SNIPPET_SHA256 = "58d575578f02665cdebbdb1191e9dfc14a8ff62db883f6afc20357b32deb8f47"
PATCH_MARKER = "CITYROAD_V31_CITY_PARK_HAPI_DUPLICATE_ENDPOINT"
OLD_CONDITION = (
    "if (npoints(0) >= 4\n"
    "    && (nprimitives(0) == 0 || len(primpoints(0,0)) == 0))")
NEW_GUARD = r'''
int hapi_duplicate_endpoint = 0;
int hapi_loop_start = 0;
for (int hapi_point_index = 1;
    hapi_point_index < npoints(0);
    hapi_point_index++)
{
    vector hapi_first_position = point(0,"P",hapi_loop_start);
    vector hapi_current_position = point(0,"P",hapi_point_index);
    if (hapi_point_index-hapi_loop_start >= 3
        && distance(hapi_first_position,hapi_current_position) < 0.1)
    {
        hapi_duplicate_endpoint = 1;
        hapi_loop_start = hapi_point_index+1;
    }
}
if (hapi_duplicate_endpoint)
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
        raise RuntimeError("V31 patch is save=False only; use the regression gate")
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
    node = asset.node(NORMALIZER_PATH)
    snippet_parm = node.parm("snippet") if node is not None else None
    if snippet_parm is None:
        raise RuntimeError("V29 topology normalizer is missing")
    current = snippet_parm.rawValue()
    if PATCH_MARKER in current:
        if NEW_GUARD not in current:
            raise RuntimeError("V31 marker exists but endpoint guard changed")
        return {"status": "PASS", "already_applied": True, "saved": False}
    actual_hash = hashlib.sha256(current.encode("utf-8")).hexdigest()
    if actual_hash != EXPECTED_SNIPPET_SHA256:
        raise RuntimeError(
            "City Park V30 normalizer precondition changed: "
            f"snippet_sha256={actual_hash}")
    if current.count(OLD_CONDITION) != 1:
        raise RuntimeError("V31 endpoint guard precondition changed")
    updated = current.replace(
        "// CITYROAD_V30_CITY_PARK_HAPI_PRIMPOINTS_GUARD",
        "// CITYROAD_V30_CITY_PARK_HAPI_PRIMPOINTS_GUARD\n// " + PATCH_MARKER,
        1).replace(OLD_CONDITION, NEW_GUARD, 1)
    try:
        with hou.undos.group("CityRoad V31 HAPI Duplicate Endpoint"):
            snippet_parm.set(updated)
            node.cook(force=True)
            if node.errors() or node.warnings():
                raise RuntimeError(
                    f"V31 normalizer diagnostics: errors={node.errors()} "
                    f"warnings={node.warnings()}")
    except Exception as exception:
        diagnostics = (node.errors(), node.warnings())
        snippet_parm.set(current)
        node.cook(force=True)
        raise RuntimeError(
            f"V31 cook failed: errors={diagnostics[0]} "
            f"warnings={diagnostics[1]}") from exception
    return {
        "status": "PASS",
        "already_applied": False,
        "saved": False,
        "snippet_sha256": hashlib.sha256(updated.encode("utf-8")).hexdigest(),
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
            "import patch_cityroad_city_park_v31_hapi_duplicate_endpoint as _park_v31; "
            "importlib.reload(_park_v31)")
        payload = connection.eval(
            "_park_v31.apply_live_patch(save=False, capture_verified_dirty="
            f"{args.capture_verified_dirty.lower() == 'true'!r})")
        print(json.dumps(payload, ensure_ascii=False, default=list, indent=2))
    finally:
        connection.close()


if __name__ == "__main__":
    main()
