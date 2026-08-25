"""Fix City Park V20 for real Houdini Engine Unity spline inputs.

Unity's parameter-input binding is a HAPI node reference and intentionally
leaves the serialized string parm empty.  HEU also tessellates a 200 m square
to roughly 800 curve points.  This transactional, save=False patch gates on
actual input geometry and deterministically reduces each boundary to at most
512 samples before validation.
"""

from __future__ import annotations

import argparse
import hashlib
import importlib
import json
import sys
from pathlib import Path

try:
    import hou  # type: ignore
except ImportError:
    hou = None


ASSET_PATH = "/obj/CityRoad_DEV"
ASSET_TYPE = "pcgbike::CityRoad::1.0"
CORE_NAME = "CityRoadCore"
SUBNET_NAME = "CR_CITY_PARK"
SWITCH_NAME = "PARK_ENABLE_INPUT_SWITCH"
GENERATOR_NAME = "PARK_LAYOUT_AND_SCATTER_V20"
EXPECTED_HDA_SUFFIX = "/Assets/PCG/HDA/City/CityRoad.hda"
EXPECTED_HIP_SUFFIX = "/HoudiniProject/PCG_Track_21.0.440/PCG_Bike_CityRoad.hip"
EXPECTED_SNIPPET_SHA256 = "6f66a7b4cda848e58940fecf333afa5c88a97f62a0ed3df8e1f6f68fcf9a6fcd"
OLD_SWITCH = (
    'if(ch("../../../enable_city_park")!=0 && '
    'strlen(chs("../../../unity_park_areas"))>0,1,0)')
NEW_SWITCH = (
    'if(ch("../../../enable_city_park")!=0 && '
    'nprims("../IN_UNITY_PARK_AREAS")>0,1,0)')
OLD_SAMPLE_BLOCK = '''int vertices[] = primvertices(0,source_prim);
        vector poly[];
        float heights[];
        float min_y = 1e18, max_y = -1e18;
        foreach (int vtx; vertices)
        {
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
        '''
NEW_SAMPLE_BLOCK = '''int vertices[] = primvertices(0,source_prim);
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
        '''
OLD_COUNTER = "int tree_count = 0;"
NEW_COUNTER = "int tree_count = 0;\nint max_boundary_samples = 0;"
OLD_VALIDATION = "closed && len(poly)>=3 && len(poly)<=512 && !self_intersection"
NEW_VALIDATION = "closed && len(poly)>=3 && !self_intersection"
OLD_DETAIL = 'setdetailattrib(0,"park_tree_count",tree_count,"set");'
NEW_DETAIL = (
    'setdetailattrib(0,"park_tree_count",tree_count,"set");\n'
    'setdetailattrib(0,"park_boundary_sample_count_max",max_boundary_samples,"set");')
PATCH_MARKER = "CITYROAD_V21_CITY_PARK_HEU_INPUT"


def _normalize(value: str) -> str:
    return value.replace("\\", "/")


def _replace_once(text: str, old: str, new: str, label: str) -> str:
    count = text.count(old)
    if count != 1:
        raise RuntimeError(f"{label} precondition count changed: {count}")
    return text.replace(old, new, 1)


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
        raise RuntimeError("V26 patch is save=False only; use the regression gate")

    asset = hou.node(ASSET_PATH)
    if asset is None or asset.type().name() != ASSET_TYPE:
        raise RuntimeError(f"Expected {ASSET_TYPE} at {ASSET_PATH}")
    definition = asset.type().definition()
    if definition is None:
        raise RuntimeError("CityRoad asset has no HDA definition")
    library = _normalize(definition.libraryFilePath())
    hip = _normalize(hou.hipFile.path())
    if not library.endswith(EXPECTED_HDA_SUFFIX):
        raise RuntimeError(f"Unexpected CityRoad definition: {library}")
    if not hip.endswith(EXPECTED_HIP_SUFFIX):
        raise RuntimeError(f"Unexpected CityRoad HIP: {hip}")
    if hou.hipFile.hasUnsavedChanges() and not capture_verified_dirty:
        raise RuntimeError("CityRoad Live Scene changed after Capture; patch refused")

    core = asset.node(CORE_NAME)
    subnet = core.node(SUBNET_NAME) if core is not None else None
    switch = subnet.node(SWITCH_NAME) if subnet is not None else None
    generator = subnet.node(GENERATOR_NAME) if subnet is not None else None
    if switch is None or generator is None:
        raise RuntimeError("City Park V20 patch precondition is missing")
    switch_parm = switch.parm("input")
    snippet_parm = generator.parm("snippet")
    if switch_parm is None or snippet_parm is None:
        raise RuntimeError("City Park V20 required parms are missing")
    current_switch = switch_parm.rawValue()
    current_snippet = snippet_parm.rawValue()
    if PATCH_MARKER in current_snippet:
        if current_switch != NEW_SWITCH:
            raise RuntimeError("V26 marker exists but Switch contract differs")
        return {"status": "PASS", "already_applied": True, "saved": False}
    actual_hash = hashlib.sha256(current_snippet.encode("utf-8")).hexdigest()
    if current_switch != OLD_SWITCH or actual_hash != EXPECTED_SNIPPET_SHA256:
        raise RuntimeError(
            "City Park V20 precondition changed: "
            f"switch={current_switch!r} snippet_sha256={actual_hash}")

    updated = current_snippet
    updated = updated.replace("// CITYROAD_V20_CITY_PARK", (
        "// CITYROAD_V20_CITY_PARK\n// " + PATCH_MARKER), 1)
    updated = _replace_once(updated, OLD_COUNTER, NEW_COUNTER, "counter")
    updated = _replace_once(updated, OLD_SAMPLE_BLOCK, NEW_SAMPLE_BLOCK, "sample block")
    updated = _replace_once(updated, OLD_VALIDATION, NEW_VALIDATION, "validation")
    updated = _replace_once(updated, OLD_DETAIL, NEW_DETAIL, "detail metadata")

    try:
        with hou.undos.group("CityRoad V26 HEU Park Input"):
            switch_parm.setExpression(
                NEW_SWITCH, language=hou.exprLanguage.Hscript)
            snippet_parm.set(updated)
            generator.cook(force=True)
            if generator.errors() or generator.warnings():
                raise RuntimeError(
                    f"V26 generator diagnostics: errors={generator.errors()} "
                    f"warnings={generator.warnings()}")
    except Exception:
        switch_parm.setExpression(
            current_switch, language=hou.exprLanguage.Hscript)
        snippet_parm.set(current_snippet)
        raise

    return {
        "status": "PASS",
        "already_applied": False,
        "saved": False,
        "asset": asset.path(),
        "switch": NEW_SWITCH,
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
            "import patch_cityroad_city_park_v26_heu_input as _park_v26; "
            "importlib.reload(_park_v26)")
        payload = connection.eval(
            "_park_v26.apply_live_patch(save=False, capture_verified_dirty="
            f"{args.capture_verified_dirty.lower() == 'true'!r})")
        print(json.dumps(payload, ensure_ascii=False, default=list, indent=2))
    finally:
        connection.close()


if __name__ == "__main__":
    main()
