"""Fix StreetBuilding roof-corner topology and wall-AC attachment.

This patch is intentionally incremental over the exact persisted V7 network.
It defaults to ``save=False`` and refuses any unrecognized snippet state.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
from pathlib import Path

import hou


ASSET_PATH = "/obj/StreetBuilding_DEV"
ASSET_TYPE = "pcgbike::StreetBuilding::1.0"
PREVIOUS_MARKER = "STREETBUILDING_V7_LSHAPE_STYLE_FAMILIES"
MARKER = "STREETBUILDING_V8_CORNER_AC_ATTACHMENT"
PREVIOUS_CONTRACT = "StreetBuilding.DirectInstances.7.0"
CONTRACT_VERSION = "StreetBuilding.DirectInstances.8.0"
REL_HDA = Path("Assets/PCG/HDA/City/StreetBuilding.hda")
REL_HIP = Path("HoudiniProject/PCG_Track_21.0.440/PCG_Bike_StreetBuilding.hip")

EXPECTED_SNIPPETS = {
    "BUILD_DIRECT_ROOF_EDGE_INSTANCES": "b2a51577b93753868b7fa8e760844fd519080cf1bc45d890282600c8d1dd18fd",
    "DETAIL_INSTANCE_POINTS": "ac702d0ec04cde20e23b9578e336a2b953c4077c6405256b13b15542adf23aa7",
    "VALIDATE_DIRECT_BUILDING_INSTANCES": "c645da4135a6120eab58400d2617143ec63170e7344eb47de919ef85f025aafb",
    "VALIDATE_DIRECT_DETAIL_INSTANCES": "ab602b0a5b48bfa6bd329e29bd8d3e6d1a82a072bfd0ce96d7e7263f2271a98e",
}

TEST_V3 = """SBV3|na_brick_mixeduse_01|2|4|3|family_a
M|Entrance|entrance|0|Assets/Test/entrance.prefab|0|0|0|0|0|0|2|3|1
M|Entrance|entrance|1|Assets/Test/EntranceDoor.prefab|0|0|0|0|0|0|2|3|1
M|GroundShop|shop|0|Assets/Test/shop.prefab|0|0|0|0|0|0|2|4|1
M|GroundWall|ground|0|Assets/Test/ground.prefab|0|0|0|0|0|0|2|4|1
M|Cornice|cornice|0|Assets/Test/cornice.prefab|0|0|0|0|0|0|2|1|1
M|MiddleWindow|window|0|Assets/Test/window.prefab|0|0|0|0|0|0|2|3|1
M|MiddleWindow|curved_double|0|Assets/Test/curved_double.prefab|0|0|0|0|0|0|4|3|1
M|MiddleBlank|blank|0|Assets/Test/blank.prefab|0|0|0|0|0|0|2|3|1
M|SideWall|side_ground|0|Assets/Test/side_ground.prefab|0|0|0|0|0|0|2|4|1
M|SideWall|side_upper|0|Assets/Test/side_upper.prefab|0|0|0|0|0|0|2|3|1
M|RearWall|rear_ground|0|Assets/Test/rear_ground.prefab|0|0|0|0|0|0|2|4|1
M|RearWall|rear_upper|0|Assets/Test/rear_upper.prefab|0|0|0|0|0|0|2|3|1
M|FacadeColumn|trim_ground|0|Assets/Test/trim_ground.prefab|0|0|0|0|0|0|2|3|1
M|FacadeColumn|brick_upper|0|Assets/Test/brick_upper.prefab|0|0|0|0|0|0|2|3|1
M|RoofSurface|roof|0|Assets/Test/roof.prefab|0|0|0|0|0|0|2|2|1
M|Parapet|straight|0|Assets/Test/straight.prefab|0|0|0|0|0|0|2|0.6|1
M|ParapetCorner|convex|0|Assets/Test/convex.prefab|0|0|0|0|0|0|2|0.6|1
M|ParapetConcaveCorner|concave|0|Assets/Test/concave.prefab|0|0|0|0|0|0|2|0.6|1
M|Awning|awning|0|Assets/Test/awning.prefab|0|0|0|0|0|0|2|1|1
M|Sign|sign|0|Assets/Test/sign.prefab|0|0|0|0|0|0|2|1|1
M|FireEscape|escape|0|Assets/Test/escape.prefab|0|0|0|0|0|0|4|6|1
M|ACUnit|ac|0|Assets/Test/ac.prefab|0|0|0|0|0|0|2|1|1
M|RoofProp|tank|0|Assets/Test/tank.prefab|0|0|0|0|0|0|2|2|1"""


def _sha(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _replace_once(text: str, old: str, new: str, label: str) -> str:
    if text.count(old) != 1:
        raise RuntimeError(f"V8 precondition failed for {label}: expected one exact match")
    return text.replace(old, new, 1)


def _upgrade_revision(text: str) -> str:
    return text.replace(PREVIOUS_CONTRACT, CONTRACT_VERSION).replace(PREVIOUS_MARKER, MARKER)


def _patch_roof_edge(text: str) -> str:
    text = _replace_once(text, "// STREETBUILDING_V7_ROOF_EDGE_L_FOOTPRINT",
        "// STREETBUILDING_V8_ROOF_EDGE_TOPOLOGY", "roof marker")
    text = _replace_once(text, "vector corners[]; float corner_yaws[]; int concave=3;",
        "vector corners[]; float corner_yaws[]; int concave=ns==0?4:3;",
        "notch-side concave index")
    text = _replace_once(text,
        "corner_yaws=array(0.0,-90.0,-180.0,90.0,0.0,90.0);",
        "corner_yaws=array(0.0,-90.0,-180.0,90.0,-180.0,90.0);",
        "rear-left corner orientation")
    text = _replace_once(text,
        "corner_yaws=array(0.0,-90.0,-180.0,-90.0,0.0,90.0);",
        "corner_yaws=array(0.0,-90.0,-180.0,-90.0,-180.0,90.0);",
        "rear-right corner orientation")
    return _upgrade_revision(text)


def _patch_details(text: str) -> str:
    text = _replace_once(text, "// STREETBUILDING_V7_DETAIL_INSTANCES",
        "// STREETBUILDING_V8_DETAIL_WALL_ATTACHMENT", "detail marker")
    dimensions = '''int wcells = int(rint(width / 2.0));
int dcells = int(rint(depth / 2.0));'''
    topology = dimensions + '''
int shape = chi("../../massing_shape");
int nwc = int(rint(ch("../../notch_width") / 2.0));
int ndc = int(rint(ch("../../notch_depth") / 2.0));
int ns = chi("../../notch_side");'''
    text = _replace_once(text, dimensions, topology, "detail footprint parameters")
    old_rear = '''if (emitted < 64 && rear_mode != 0 && floors >= 2 && sbv6_has_role(catalog, "ACUnit"))
    emitted += sbv6_emit(catalog, "ACUnit", seed * 1009 + 3407,
        set(width * .5, 0, -depth - .20), set(-1, 0, 0), set(0, 0, -1),
        (max(0, wcells - 2) + .5) * 2, 4.7, -180, 3, "rear", 1, max(0, wcells - 2));'''
    new_rear = '''if (emitted < 64 && rear_mode != 0 && floors >= 2 && sbv6_has_role(catalog, "ACUnit"))
{
    int rear_cell = max(0, wcells - 2);
    if (shape == 1)
        rear_cell = ns == 0
            ? min(rear_cell, max(0, wcells - nwc - 1))
            : max(rear_cell, nwc);
    emitted += sbv6_emit(catalog, "ACUnit", seed * 1009 + 3407,
        set(width * .5, 0, -depth), set(-1, 0, 0), set(0, 0, -1),
        (rear_cell + .5) * 2, 4.7, -180, 3, "rear", 1, rear_cell);
}'''
    text = _replace_once(text, old_rear, new_rear, "rear AC support cell")
    text = _replace_once(text,
        '''vector origin = face == 1 ? set(-width * .5 - .20, 0, -depth) : set(width * .5 + .20, 0, 0);''',
        '''vector origin = face == 1 ? set(-width * .5, 0, -depth) : set(width * .5, 0, 0);''',
        "side AC support plane")
    key_line = '''                int key = seed * 1009 + face * 503 + floor * 101 + cell * 37;'''
    guarded_key = '''                int removed_side_cell = shape == 1
                    && ((ns == 0 && face == 1 && cell < ndc)
                        || (ns == 1 && face == 2 && cell >= dcells - ndc));
                if (removed_side_cell) continue;
                int key = seed * 1009 + face * 503 + floor * 101 + cell * 37;'''
    text = _replace_once(text, key_line, guarded_key, "L-shape side AC containment")
    # The roof block now consumes the topology values declared above.
    for declaration in (
        '''    int shape = chi("../../massing_shape");\n''',
        '''    int nwc = int(rint(ch("../../notch_width") / 2.0));\n''',
        '''    int ndc = int(rint(ch("../../notch_depth") / 2.0));\n''',
        '''    int ns = chi("../../notch_side");\n'''):
        text = _replace_once(text, declaration, "", "roof topology reuse")
    return _upgrade_revision(text)


def _patch_building_validator(text: str) -> str:
    needle = '''if (schema == 2 && entrance_count != 1)
    error("StreetBuilding V6.1 requires exactly one logical entrance, got %d", entrance_count);'''
    addition = needle + '''
if (schema >= 2 && chi("../../massing_shape") == 1)
{
    int convex_count = 0; int concave_count = 0;
    for (int point = 0; point < points; point++)
    {
        string role = point(0, "module_role", point);
        if (role == "ParapetCorner")
            convex_count++;
        if (role == "ParapetConcaveCorner")
            concave_count++;
    }
    if (convex_count != 5 || concave_count != 1)
        error("StreetBuilding V8 L parapet corner topology is incomplete");
}'''
    return _upgrade_revision(_replace_once(text, needle, addition, "corner asset validator"))


def _patch_detail_validator(text: str) -> str:
    needle = '''    if (role == "ACUnit" && (face < 1 || face > 3 || floor < 1))
        error("StreetBuilding V6.1 ACUnit must be on an upper side/rear face");'''
    addition = needle + '''
    if (role == "ACUnit")
    {
        vector p = point(0, "P", point);
        float width = ch("../../internal_width"); float depth = ch("../../internal_depth");
        float plane_error = face == 1 ? abs(p.x - width * .5)
            : face == 2 ? abs(p.x + width * .5) : abs(p.z + depth);
        if (plane_error > .001)
            error("StreetBuilding V8 ACUnit pivot escaped its wall support plane");
    }'''
    return _upgrade_revision(_replace_once(text, needle, addition, "AC support-plane validator"))


def _cook(node: hou.Node, label: str) -> None:
    try:
        node.cook(force=True)
    except hou.OperationFailed as exc:
        core = node.parent()
        diagnostics = []
        for child in core.allSubChildren():
            diagnostics.extend(f"{child.path()}: {message}" for message in child.errors())
            diagnostics.extend(f"{child.path()}: {message}" for message in child.warnings())
        raise RuntimeError(label + " cook failed:\n" + "\n".join(diagnostics)) from exc


def _quaternion_matches(actual, yaw_degrees: float) -> bool:
    half = math.radians(yaw_degrees) * .5
    expected = (0.0, math.sin(half), 0.0, math.cos(half))
    dot = sum(float(a) * b for a, b in zip(actual, expected))
    return abs(abs(dot) - 1.0) <= 1e-4


def _validate_corner_points(geometry: hou.Geometry, side: int) -> None:
    points = [point for point in geometry.points()
        if point.stringAttribValue("module_role") in ("ParapetCorner", "ParapetConcaveCorner")]
    by_cell = {point.intAttribValue("cell_index"): point for point in points}
    expected_roles = ["ParapetCorner"] * 6
    expected_roles[4 if side == 0 else 3] = "ParapetConcaveCorner"
    expected_yaws = ([0, -90, -180, 90, -180, 90]
        if side == 0 else [0, -90, -180, -90, -180, 90])
    if set(by_cell) != set(range(6)):
        raise RuntimeError(f"V8 L side {side} corner serials changed: {sorted(by_cell)}")
    for cell in range(6):
        point = by_cell[cell]
        role = point.stringAttribValue("module_role")
        if role != expected_roles[cell]:
            raise RuntimeError(f"V8 L side {side} corner {cell} role is {role}")
        if not _quaternion_matches(point.attribValue("orient"), expected_yaws[cell]):
            raise RuntimeError(f"V8 L side {side} corner {cell} orientation is invalid")
    convex_paths = {point.stringAttribValue("unity_instance") for point in points
        if point.stringAttribValue("module_role") == "ParapetCorner"}
    concave_paths = {point.stringAttribValue("unity_instance") for point in points
        if point.stringAttribValue("module_role") == "ParapetConcaveCorner"}
    if convex_paths & concave_paths:
        raise RuntimeError("V8 convex and concave corners share an asset path")


def _validate_ac_points(geometry: hou.Geometry, side: int, width: float, depth: float,
        notch_width: float, notch_depth: float) -> int:
    count = 0
    dcells = int(round(depth / 2.0)); ndc = int(round(notch_depth / 2.0))
    for point in geometry.points():
        if point.stringAttribValue("module_role") != "ACUnit":
            continue
        count += 1
        face = point.intAttribValue("face_index"); cell = point.intAttribValue("cell_index")
        x, _, z = (float(value) for value in point.position())
        plane_error = abs(x - width * .5) if face == 1 else (
            abs(x + width * .5) if face == 2 else abs(z + depth))
        if plane_error > .001:
            raise RuntimeError(f"V8 AC face {face} is {plane_error:.4f}m off support plane")
        if side == 0 and face == 1 and cell < ndc:
            raise RuntimeError("V8 AC entered the rear-left removed side cells")
        if side == 1 and face == 2 and cell >= dcells - ndc:
            raise RuntimeError("V8 AC entered the rear-right removed side cells")
        if face == 3:
            unity_x = -x
            removed = unity_x < -width * .5 + notch_width if side == 0 \
                else unity_x > width * .5 - notch_width
            if removed:
                raise RuntimeError("V8 rear AC entered the removed L-notch cells")
    return count


def _validate(asset: hou.Node) -> dict:
    core = asset.node("StreetBuildingCore")
    lod0 = core.node("OUT_BUILDING_LOD0")
    details = core.node("OUT_DETAIL_INSTANCES")
    names = ("module_source", "unity_instance_catalog", "style_id", "internal_width",
        "internal_depth", "floor_count", "ground_floor_height", "typical_floor_height",
        "parapet_height", "rear_mode", "side_mode", "generate_roof", "generate_lods",
        "seed", "facade_rhythm", "detail_density", "generate_attachments",
        "massing_shape", "notch_width", "notch_depth", "notch_side")
    saved = {name: asset.parm(name).eval() for name in names}
    try:
        values = {"module_source": 1, "unity_instance_catalog": TEST_V3,
            "style_id": "na_brick_mixeduse_01", "internal_width": 12,
            "internal_depth": 10, "floor_count": 4, "ground_floor_height": 4,
            "typical_floor_height": 3, "parapet_height": .6, "rear_mode": 2,
            "side_mode": 2, "generate_roof": 1, "generate_lods": 0, "seed": 29,
            "facade_rhythm": 3, "detail_density": 1, "generate_attachments": 1,
            "massing_shape": 1, "notch_width": 4, "notch_depth": 4,
            "notch_side": 0}
        for name, value in values.items():
            asset.parm(name).set(value)
        result = {}
        for side in (0, 1):
            asset.parm("notch_side").set(side)
            _cook(lod0, f"V8 L side {side}")
            _cook(details, f"V8 details side {side}")
            _validate_corner_points(lod0.geometry(), side)
            ac_count = _validate_ac_points(details.geometry(), side, 12, 10, 4, 4)
            if ac_count < 1:
                raise RuntimeError(f"V8 L side {side} did not exercise AC placement")
            result[f"l_{'left' if side == 0 else 'right'}_ac"] = ac_count
        diagnostics = []
        for node in (lod0, details, core.node("VALIDATE_DIRECT_BUILDING_INSTANCES"),
                core.node("VALIDATE_DIRECT_DETAIL_INSTANCES")):
            _cook(node, "V8 diagnostics")
            diagnostics.extend(node.errors()); diagnostics.extend(node.warnings())
        if diagnostics:
            raise RuntimeError("V8 cook diagnostics: " + "\n".join(diagnostics))
        result.update({"convex_corners": 5, "concave_corners": 1,
            "corner_assets_distinct": True, "ac_support_plane_error_max": .001})
        return result
    finally:
        for name, value in saved.items():
            asset.parm(name).set(value)


def apply_loaded(asset: hou.Node, save: bool) -> dict:
    if asset is None or asset.type().name() != ASSET_TYPE:
        raise RuntimeError(f"Expected {ASSET_PATH} {ASSET_TYPE}")
    definition = asset.type().definition()
    if definition is None:
        raise RuntimeError("StreetBuilding has no definition")
    comment = definition.comment() or ""
    if MARKER in comment:
        return {"status": "UNCHANGED", "save": save, "revision": MARKER,
            "contract": CONTRACT_VERSION, "validation": _validate(asset)}
    if PREVIOUS_MARKER not in comment:
        raise RuntimeError("V8 requires the exact persisted V7 marker")
    asset.allowEditingOfContents()
    core = asset.node("StreetBuildingCore")
    originals = {}
    for name, expected in EXPECTED_SNIPPETS.items():
        node = core.node(name)
        if node is None:
            raise RuntimeError(f"V8 node is missing: {name}")
        text = node.parm("snippet").eval()
        if _sha(text) != expected:
            raise RuntimeError(f"V8 precondition hash failed: {name}")
        originals[name] = text
    patched = {
        "BUILD_DIRECT_ROOF_EDGE_INSTANCES": _patch_roof_edge(originals["BUILD_DIRECT_ROOF_EDGE_INSTANCES"]),
        "DETAIL_INSTANCE_POINTS": _patch_details(originals["DETAIL_INSTANCE_POINTS"]),
        "VALIDATE_DIRECT_BUILDING_INSTANCES": _patch_building_validator(originals["VALIDATE_DIRECT_BUILDING_INSTANCES"]),
        "VALIDATE_DIRECT_DETAIL_INSTANCES": _patch_detail_validator(originals["VALIDATE_DIRECT_DETAIL_INSTANCES"]),
    }
    try:
        for name, text in patched.items():
            core.node(name).parm("snippet").set(text)
        validation = _validate(asset)
        if save:
            definition.updateFromNode(asset)
            definition.setParmTemplateGroup(asset.parmTemplateGroup())
            definition.setComment(comment.replace(PREVIOUS_MARKER, MARKER))
            asset.matchCurrentDefinition()
            hou.hipFile.save()
        return {"status": "UPDATED", "save": save, "revision": MARKER,
            "contract": CONTRACT_VERSION, "nodes": sorted(patched), "validation": validation}
    except Exception:
        if not save:
            for name, text in originals.items():
                core.node(name).parm("snippet").set(text)
        raise


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--project-root", required=True, type=Path)
    parser.add_argument("--save", choices=("true", "false"), default="false")
    args = parser.parse_args()
    root = args.project_root.resolve()
    hda = (root / REL_HDA).resolve(); hip = (root / REL_HIP).resolve()
    before_hda = hda.read_bytes(); before_hip = hip.read_bytes()
    try:
        hou.hipFile.load(str(hip), suppress_save_prompt=True, ignore_load_warnings=False)
        hou.hda.installFile(str(hda), change_oplibraries_file=False, force_use_assets=True)
        result = apply_loaded(hou.node(ASSET_PATH), args.save == "true")
    except Exception:
        if args.save == "true":
            hda.write_bytes(before_hda); hip.write_bytes(before_hip)
        raise
    after = {"hda": hashlib.sha256(hda.read_bytes()).hexdigest(),
        "hip": hashlib.sha256(hip.read_bytes()).hexdigest()}
    if args.save == "false" and (hda.read_bytes() != before_hda or hip.read_bytes() != before_hip):
        raise RuntimeError("V8 save=False modified persisted HDA/HIP bytes")
    result["files"] = after
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
