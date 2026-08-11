"""CityRoad V9 final-boundary mobile topology patch.

V8 reduced the adaptive road surface, but the later union-boundary rounding
stage independently rebuilt each corner with up to twelve spans.  Unity uses
that final planar boundary, so this incremental patch caps the actual output
boundary and keeps right-angle corners at four spans / five points per side.
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
import shutil

try:
    import hou  # type: ignore
except ModuleNotFoundError:
    hou = None


ASSET_PATH = "/obj/CityRoad_DEV"
EXPECTED_TYPE = "pcgbike::CityRoad::1.0"
EXPECTED_HDA_SUFFIX = "/Assets/PCG/HDA/City/CityRoad.hda"


COUNTERS_OLD = """    int original_prim_count = nprimitives(0);
"""


COUNTERS_NEW = """    int original_prim_count = nprimitives(0);
    // CITYROAD_V9_FINAL_BOUNDARY_MOBILE_CAP
    int final_boundary_rounded_corner_count = 0;
    int final_boundary_right_angle_corner_count = 0;
    int final_boundary_max_segment_count = 0;
"""


SEGMENTS_OLD = """            int segment_count = clamp(int(ceil(estimated_arc_length / spacing)), 2, 12);
"""


SEGMENTS_NEW = """            // The final planar boundary is the topology Unity actually receives.
            // Keep a hard mobile cap of four spans and make a right-angle bend
            // deterministic: five boundary points on each side.
            int adaptive_segment_count = clamp(
                int(ceil(estimated_arc_length / spacing)), 2, 4);
            float corner_degrees = degrees(angle);
            int is_right_angle = abs(corner_degrees - 90.0) <= 15.0;
            int segment_count = is_right_angle ? 4 : adaptive_segment_count;
            final_boundary_rounded_corner_count++;
            final_boundary_right_angle_corner_count += is_right_angle;
            final_boundary_max_segment_count = max(
                final_boundary_max_segment_count, segment_count);
"""


STATS_ANCHOR = """    // 先创建新轮廓，再倒序删除旧轮廓，避免点号失效。
"""


STATS_NEW = """    setdetailattrib(0, "final_boundary_mobile_max_segment_count",
        final_boundary_max_segment_count, "set");
    setdetailattrib(0, "final_boundary_mobile_points_per_side", 5, "set");
    setdetailattrib(0, "final_boundary_mobile_rounded_corner_count",
        final_boundary_rounded_corner_count, "set");
    setdetailattrib(0, "final_boundary_mobile_right_angle_corner_count",
        final_boundary_right_angle_corner_count, "set");
    setdetailattrib(0, "cityroad_final_boundary_patch", "V9", "set");

    // 先创建新轮廓，再倒序删除旧轮廓，避免点号失效。
"""


def _replace_once(source: str, old: str, new: str, label: str) -> str:
    count = source.count(old)
    if count != 1:
        raise RuntimeError(f"{label} signature count is {count}; refusing blind patch")
    return source.replace(old, new, 1)


def _patch_snippet(source: str) -> str:
    if "CITYROAD_V9_FINAL_BOUNDARY_MOBILE_CAP" in source:
        return source
    source = _replace_once(source, COUNTERS_OLD, COUNTERS_NEW, "V9 counters")
    source = _replace_once(source, SEGMENTS_OLD, SEGMENTS_NEW, "V9 segment cap")
    source = _replace_once(source, STATS_ANCHOR, STATS_NEW, "V9 validation stats")
    return source


def _require_node(parent, name: str):
    node = parent.node(name)
    if node is None:
        raise RuntimeError(f"Missing required CityRoad node: {parent.path()}/{name}")
    return node


def _detail_value(geometry, name: str, default=0):
    attribute = geometry.findGlobalAttrib(name)
    return geometry.attribValue(attribute) if attribute is not None else default


def _backup_definition(definition) -> Path:
    hip_dir = Path(hou.hipFile.path()).resolve().parent
    backup_dir = hip_dir / "backups"
    backup_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    destination = backup_dir / f"CityRoad_before_final_boundary_mobile_v9_{stamp}.hda"
    shutil.copy2(Path(definition.libraryFilePath()), destination)
    return destination


def _validate(core) -> dict[str, object]:
    boundary_node = _require_node(core, "ROAD_UNION_ROUND_FINAL_BOUNDARY")
    outputs = [
        _require_node(core, "OUT_ROAD_SURFACE"),
        _require_node(core, "OUT_ROAD_MARKINGS"),
        _require_node(core, "OUT_SIDEWALK_CURB"),
    ]
    errors: list[str] = []
    warnings: list[str] = []
    for node in [boundary_node] + outputs:
        node.cook(force=True)
        errors.extend(node.errors())
        warnings.extend(node.warnings())
    if errors:
        raise RuntimeError("CityRoad V9 cook errors: " + " | ".join(errors))

    boundary = boundary_node.geometry()
    max_segments = int(_detail_value(
        boundary, "final_boundary_mobile_max_segment_count", -1))
    points_per_side = int(_detail_value(
        boundary, "final_boundary_mobile_points_per_side", -1))
    right_angles = int(_detail_value(
        boundary, "final_boundary_mobile_right_angle_corner_count", -1))
    patch = str(_detail_value(boundary, "cityroad_final_boundary_patch", ""))
    if max_segments < 0 or max_segments > 4:
        raise RuntimeError(
            f"V9 final boundary segment cap failed: max={max_segments}")
    if points_per_side != 5 or patch != "V9":
        raise RuntimeError(
            f"V9 final boundary contract failed: points={points_per_side} patch={patch}")

    v8_path = Path(__file__).with_name("patch_cityroad_mobile_corner_v8.py")
    namespace: dict[str, object] = {
        "__file__": str(v8_path),
        "__name__": "cityroad_v8_validation",
    }
    exec(compile(v8_path.read_text(encoding="utf-8"), str(v8_path), "exec"), namespace)
    namespace["hou"] = hou
    v8_validation = namespace["_validate"](core)

    return {
        "warnings": warnings,
        "final_boundary_points": len(boundary.points()),
        "final_boundary_primitives": len(boundary.prims()),
        "final_boundary_max_segments": max_segments,
        "final_boundary_points_per_side": points_per_side,
        "final_boundary_right_angle_corners": right_angles,
        "v8": v8_validation,
    }


def apply_live_patch(save: bool = True, create_backup: bool = True, hou_module=None):
    global hou
    if hou_module is not None:
        hou = hou_module
    if hou is None:
        raise RuntimeError("A Houdini hou module is required")

    asset = hou.node(ASSET_PATH)
    if asset is None or asset.type().name() != EXPECTED_TYPE:
        raise RuntimeError(f"Expected live {EXPECTED_TYPE} at {ASSET_PATH}")
    definition = asset.type().definition()
    if definition is None:
        raise RuntimeError("CityRoad node has no HDA definition")
    library = definition.libraryFilePath().replace("\\", "/")
    if not library.endswith(EXPECTED_HDA_SUFFIX):
        raise RuntimeError(f"Unexpected CityRoad definition: {library}")

    core = _require_node(asset, "CityRoadCore")
    boundary = _require_node(core, "ROAD_UNION_ROUND_FINAL_BOUNDARY")
    current = boundary.parm("snippet").eval()
    patched = _patch_snippet(current)
    before_points = len(boundary.geometry().points())
    interface_before = asset.parmTemplateGroup().asDialogScript()

    backup_path = _backup_definition(definition) if create_backup else None
    was_locked = asset.isLockedHDA()
    if was_locked:
        asset.allowEditingOfContents(propagate=True)

    with hou.undos.group("CityRoad V9 final boundary mobile cap"):
        boundary.parm("snippet").set(patched)
        boundary.setComment(
            "V9：最终 Unity RoadSurface 边界最多 4 段；直角弯每侧固定 5 点，禁止后级重新加密。")
        boundary.setGenericFlag(hou.nodeFlag.DisplayComment, True)

    if asset.parmTemplateGroup().asDialogScript() != interface_before:
        raise RuntimeError("V9 unexpectedly changed the public HDA parameter interface")

    validation = _validate(core)
    if validation["warnings"]:
        raise RuntimeError("CityRoad V9 cook warnings: " + " | ".join(validation["warnings"]))

    if save:
        definition.updateFromNode(asset)
        hou.hipFile.save()

    return {
        "asset": asset.path(),
        "definition": definition.libraryFilePath(),
        "hip": hou.hipFile.path(),
        "backup": str(backup_path) if backup_path else None,
        "was_locked": was_locked,
        "saved": save,
        "before_final_boundary_points": before_points,
        "validation": validation,
    }


if __name__ == "__main__":
    print(apply_live_patch())
