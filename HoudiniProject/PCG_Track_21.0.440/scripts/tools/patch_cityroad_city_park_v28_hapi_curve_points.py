"""Read HEU HAPI curve points without relying on polygon vertex storage."""

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
GENERATOR_PATH = "CityRoadCore/CR_CITY_PARK/PARK_LAYOUT_AND_SCATTER_V20"
EXPECTED_HDA_SUFFIX = "/Assets/PCG/HDA/City/CityRoad.hda"
EXPECTED_HIP_SUFFIX = "/HoudiniProject/PCG_Track_21.0.440/PCG_Bike_CityRoad.hip"
EXPECTED_SNIPPET_SHA256 = "6c7b6da0a22aa02b86d3d00f26717b834096f39a5a4650bf86b49de165b9cbdc"
PATCH_MARKER = "CITYROAD_V23_CITY_PARK_HAPI_CURVE_POINTS"
REPLACEMENTS = (
    ("int vertices[] = primvertices(0,source_prim);",
     "int source_points[] = primpoints(0,source_prim);"),
    ("int source_vertex_count = len(vertices);",
     "int source_vertex_count = len(source_points);"),
    ('point(0,"P",vertexpoint(0,vertices[0]))',
     'point(0,"P",source_points[0])'),
    ('point(0,"P",vertexpoint(0,vertices[source_vertex_count-1]))',
     'point(0,"P",source_points[source_vertex_count-1])'),
    ("int vtx = vertices[vertex_index];\n            "
     'vector p = point(0,"P",vertexpoint(0,vtx));',
     "int source_point = source_points[vertex_index];\n            "
     'vector p = point(0,"P",source_point);'),
)


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
        raise RuntimeError("V28 patch is save=False only; use the regression gate")
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
    generator = asset.node(GENERATOR_PATH)
    snippet_parm = generator.parm("snippet") if generator is not None else None
    if snippet_parm is None:
        raise RuntimeError("City Park generator snippet is missing")
    current = snippet_parm.rawValue()
    if PATCH_MARKER in current:
        return {"status": "PASS", "already_applied": True, "saved": False}
    actual_hash = hashlib.sha256(current.encode("utf-8")).hexdigest()
    if actual_hash != EXPECTED_SNIPPET_SHA256:
        raise RuntimeError(
            "City Park V22 precondition changed: "
            f"snippet_sha256={actual_hash}")
    updated = current.replace(
        "// CITYROAD_V22_CITY_PARK_HEU_CLOSED_CURVE",
        "// CITYROAD_V22_CITY_PARK_HEU_CLOSED_CURVE\n// " + PATCH_MARKER,
        1)
    for old, new in REPLACEMENTS:
        if updated.count(old) != 1:
            raise RuntimeError(
                f"V28 replacement precondition changed: {old!r} "
                f"count={updated.count(old)}")
        updated = updated.replace(old, new, 1)
    try:
        with hou.undos.group("CityRoad V28 HAPI Curve Points"):
            snippet_parm.set(updated)
            generator.cook(force=True)
            if generator.errors() or generator.warnings():
                raise RuntimeError(
                    f"V28 generator diagnostics: errors={generator.errors()} "
                    f"warnings={generator.warnings()}")
    except Exception:
        snippet_parm.set(current)
        raise
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
            "import patch_cityroad_city_park_v28_hapi_curve_points as _park_v28; "
            "importlib.reload(_park_v28)")
        payload = connection.eval(
            "_park_v28.apply_live_patch(save=False, capture_verified_dirty="
            f"{args.capture_verified_dirty.lower() == 'true'!r})")
        print(json.dumps(payload, ensure_ascii=False, default=list, indent=2))
    finally:
        connection.close()


if __name__ == "__main__":
    main()
