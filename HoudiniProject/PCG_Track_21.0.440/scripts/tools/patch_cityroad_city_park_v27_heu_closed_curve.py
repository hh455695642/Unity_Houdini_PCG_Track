"""Preserve HEU's duplicate-endpoint closed-curve convention before sampling.

Transactional, idempotent and save=False.  Persistence is exclusively owned
by Invoke-PcgRegression.ps1.
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
ASSET_TYPE = "pcgbike::CityRoad::1.0"
GENERATOR_PATH = "CityRoadCore/CR_CITY_PARK/PARK_LAYOUT_AND_SCATTER_V20"
EXPECTED_HDA_SUFFIX = "/Assets/PCG/HDA/City/CityRoad.hda"
EXPECTED_HIP_SUFFIX = "/HoudiniProject/PCG_Track_21.0.440/PCG_Bike_CityRoad.hip"
EXPECTED_SNIPPET_SHA256 = "fd21e390b218ac0d85a8a06af1cdc9054fffb51074fb40902193566b5d54ea66"
PATCH_MARKER = "CITYROAD_V22_CITY_PARK_HEU_CLOSED_CURVE"
OLD_BLOCK = '''int vertices[] = primvertices(0,source_prim);
        vector poly[];
        float heights[];
        float min_y = 1e18, max_y = -1e18;
        // HEU tessellates Unity Splines densely.  Keep a deterministic,
        // ordered subset so authoring resolution cannot exceed the V1 budget.
        int source_vertex_count = len(vertices);
        int sample_step = max(1, int(ceil(float(source_vertex_count) / 512.0)));
        for (int vertex_index=0; vertex_index<source_vertex_count; vertex_index+=sample_step)
        {
            int vtx = vertices[vertex_index];
            vector p = point(0,"P",vertexpoint(0,vtx));
            append(poly,p);
            append(heights,p.y);
            min_y = min(min_y,p.y); max_y = max(max_y,p.y);
        }
        if (len(poly)>3 && distance(poly[0],poly[-1])<0.01)
        {
            pop(poly);
            pop(heights);
        }
        max_boundary_samples = max(max_boundary_samples, len(poly));
        int closed = int(primintrinsic(0,"closed",source_prim));
        if (!closed && len(poly)>2 && distance(poly[0],poly[-1])<0.1) closed=1;

        '''
NEW_BLOCK = '''int vertices[] = primvertices(0,source_prim);
        vector poly[];
        float heights[];
        float min_y = 1e18, max_y = -1e18;
        // HEU tessellates Unity Splines densely and represents a closed
        // linear curve with a duplicated endpoint while isClosed stays false.
        int source_vertex_count = len(vertices);
        int closed = int(primintrinsic(0,"closed",source_prim));
        if (source_vertex_count > 2)
        {
            vector source_first = point(0,"P",vertexpoint(0,vertices[0]));
            vector source_last = point(0,"P",vertexpoint(0,vertices[source_vertex_count-1]));
            if (distance(source_first,source_last) < 0.1)
            {
                closed = 1;
                source_vertex_count--;
            }
        }
        // Keep a deterministic ordered subset within the V1 512-point budget.
        int sample_step = max(1, int(ceil(float(source_vertex_count) / 512.0)));
        for (int vertex_index=0; vertex_index<source_vertex_count; vertex_index+=sample_step)
        {
            int vtx = vertices[vertex_index];
            vector p = point(0,"P",vertexpoint(0,vtx));
            append(poly,p);
            append(heights,p.y);
            min_y = min(min_y,p.y); max_y = max(max_y,p.y);
        }
        max_boundary_samples = max(max_boundary_samples, len(poly));

        '''


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
        raise RuntimeError("V27 patch is save=False only; use the regression gate")
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
    if actual_hash != EXPECTED_SNIPPET_SHA256 or current.count(OLD_BLOCK) != 1:
        raise RuntimeError(
            "City Park V21 precondition changed: "
            f"snippet_sha256={actual_hash} block_count={current.count(OLD_BLOCK)}")
    updated = current.replace(
        "// CITYROAD_V21_CITY_PARK_HEU_INPUT",
        "// CITYROAD_V21_CITY_PARK_HEU_INPUT\n// " + PATCH_MARKER,
        1).replace(OLD_BLOCK, NEW_BLOCK, 1)
    try:
        with hou.undos.group("CityRoad V27 HEU Closed Park Curve"):
            snippet_parm.set(updated)
            generator.cook(force=True)
            if generator.errors() or generator.warnings():
                raise RuntimeError(
                    f"V27 generator diagnostics: errors={generator.errors()} "
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
            "import patch_cityroad_city_park_v27_heu_closed_curve as _park_v27; "
            "importlib.reload(_park_v27)")
        payload = connection.eval(
            "_park_v27.apply_live_patch(save=False, capture_verified_dirty="
            f"{args.capture_verified_dirty.lower() == 'true'!r})")
        print(json.dumps(payload, ensure_ascii=False, default=list, indent=2))
    finally:
        connection.close()


if __name__ == "__main__":
    main()
