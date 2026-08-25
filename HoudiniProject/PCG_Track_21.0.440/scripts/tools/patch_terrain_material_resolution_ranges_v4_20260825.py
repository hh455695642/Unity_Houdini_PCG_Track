"""Repair Terrain material recooks and widen Terrain Shape control ranges.

The patch is incremental, idempotent, verification-first, and never saves.
It preserves all instance values, snaps legacy/invalid Unity resolution values
to the nearest supported 2^n+1 HeightField resolution, and only changes the
declared public parameter metadata.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from typing import Any

try:
    import hou
except ModuleNotFoundError:
    hou = None


ROOT_PATH = "/obj/Terrain1"
EXPECTED_TYPE = "pcgbike::Terrain::1.0"
EXPECTED_LIBRARY_SUFFIX = "/Assets/PCG/HDA/Terrain.hda"
MARKER = "terrain_material_resolution_ranges_v4_20260825"

DOMAIN_NODE = "TerrainCore/10_TERRAIN_SOURCE/HF_DOMAIN"
OLD_GRID_SAMPLES = 'ch("../../../tile_resolution")'
NEW_GRID_SAMPLES = (
    'if(ch("../../../tile_resolution")<=193,129,'
    'if(ch("../../../tile_resolution")<=385,257,'
    'if(ch("../../../tile_resolution")<=769,513,'
    'if(ch("../../../tile_resolution")<=1537,1025,2049))))'
)
OLD_SIZE_X = (
    'if(ch("../../../auto_domain")&&detail("../../00_TRACK_INPUT/TRACK_validate_contract",'
    '"terrain_input_valid",0),bbox("../../00_TRACK_INPUT/TRACK_validate_contract",D_XSIZE)'
    '+2*(ch("../../../padding")+if(ch("../../../enable_adaptive_earthwork"),'
    'ch("../../../maximum_adaptive_radius")+2*(max(bbox("../../00_TRACK_INPUT/'
    'TRACK_validate_contract",D_XSIZE),bbox("../../00_TRACK_INPUT/TRACK_validate_contract",'
    'D_ZSIZE))+2*(ch("../../../padding")+ch("../../../maximum_adaptive_radius")))'
    '/max(1,ch("../../../tile_resolution")-1),0)),ch("../../../manual_sizex"))'
)
OLD_SIZE_Y = (
    'if(ch("../../../auto_domain")&&detail("../../00_TRACK_INPUT/TRACK_validate_contract",'
    '"terrain_input_valid",0),bbox("../../00_TRACK_INPUT/TRACK_validate_contract",D_ZSIZE)'
    '+2*(ch("../../../padding")+if(ch("../../../enable_adaptive_earthwork"),'
    'ch("../../../maximum_adaptive_radius")+2*(max(bbox("../../00_TRACK_INPUT/'
    'TRACK_validate_contract",D_XSIZE),bbox("../../00_TRACK_INPUT/TRACK_validate_contract",'
    'D_ZSIZE))+2*(ch("../../../padding")+ch("../../../maximum_adaptive_radius")))'
    '/max(1,ch("../../../tile_resolution")-1),0)),ch("../../../manual_sizey"))'
)
NEW_SQUARE_SIZE = (
    'if(ch("../../../auto_domain")&&detail("../../00_TRACK_INPUT/TRACK_validate_contract",'
    '"terrain_input_valid",0),max(bbox("../../00_TRACK_INPUT/TRACK_validate_contract",'
    'D_XSIZE),bbox("../../00_TRACK_INPUT/TRACK_validate_contract",D_ZSIZE))'
    '+2*(ch("../../../padding")+if(ch("../../../enable_adaptive_earthwork"),'
    'ch("../../../maximum_adaptive_radius")+2*(max(bbox("../../00_TRACK_INPUT/'
    'TRACK_validate_contract",D_XSIZE),bbox("../../00_TRACK_INPUT/TRACK_validate_contract",'
    'D_ZSIZE))+2*(ch("../../../padding")+ch("../../../maximum_adaptive_radius")))'
    '/max(1,' + NEW_GRID_SAMPLES + '-1),0)),max(ch("../../../manual_sizex"),'
    'ch("../../../manual_sizey")))'
)

EXPECTED_RANGES = {
    "padding": (0.0, 1.0e9, False),
    "seed": (0, 100000, False),
    "mountain_height_scale": (0.0, 12.0, False),
    "macro_amp": (0.0, 500.0, False),
    "macro_size": (10.0, 2000.0, False),
    "mid_amp": (0.0, 200.0, False),
    "mid_size": (5.0, 500.0, False),
    "detail_amp": (0.0, 50.0, False),
    "detail_size": (1.0, 100.0, False),
    "ridge_strength": (0.0, 2.0, False),
    "ridge_amp": (0.0, 2000.0, False),
    "ridge_size": (1.0, 10000.0, False),
}

TARGET_RANGES = {
    "padding": (0.0, 4096.0, True),
    "seed": (0, 200000, False),
    "mountain_height_scale": (0.0, 24.0, False),
    "macro_amp": (0.0, 1000.0, False),
    "macro_size": (10.0, 4000.0, False),
    "mid_amp": (0.0, 400.0, False),
    "mid_size": (5.0, 1000.0, False),
    "detail_amp": (0.0, 100.0, False),
    "detail_size": (1.0, 200.0, False),
    "ridge_strength": (0.0, 4.0, False),
    "ridge_amp": (0.0, 4000.0, False),
    "ridge_size": (1.0, 20000.0, False),
}


class PatchFailure(RuntimeError):
    pass


def require(condition: bool, message: str) -> None:
    if not condition:
        raise PatchFailure(message)


def digest(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def range_state(template: hou.ParmTemplate) -> tuple[float, float, bool]:
    return (template.minValue(), template.maxValue(), template.maxIsStrict())


def same_range(actual: tuple[float, float, bool], expected: tuple[float, float, bool]) -> bool:
    return (
        abs(float(actual[0]) - float(expected[0])) <= 1e-6
        and abs(float(actual[1]) - float(expected[1])) <= 1e-6
        and bool(actual[2]) == bool(expected[2])
    )


def capture_values(root: hou.Node) -> dict[str, tuple[str, Any, Any | None]]:
    values: dict[str, tuple[str, Any, Any | None]] = {}
    for parm in root.parms():
        if parm.parmTemplate().type() == hou.parmTemplateType.Folder:
            continue
        try:
            values[parm.name()] = ("expr", parm.expression(), parm.expressionLanguage())
        except Exception:
            try:
                values[parm.name()] = ("value", parm.eval(), None)
            except Exception:
                pass
    return values


def restore_values(root: hou.Node, values: dict[str, tuple[str, Any, Any | None]]) -> None:
    for name, (kind, value, language) in values.items():
        parm = root.parm(name)
        if parm is None:
            continue
        try:
            if kind == "expr":
                parm.setExpression(value, language=language)
            else:
                parm.set(value)
        except Exception:
            pass


def refresh_instance(root: hou.Node, values: dict[str, tuple[str, Any, Any | None]]) -> hou.Node:
    root.matchCurrentDefinition()
    root.allowEditingOfContents()
    restore_values(root, values)
    require(not root.spareParms(), "Template refresh created instance-only spare parameters")
    return root


def update_public_interface(definition: hou.HDADefinition) -> tuple[list[str], bool]:
    group = definition.parmTemplateGroup()
    original_dialog = group.asDialogScript()
    changed: list[str] = []
    for name, target in TARGET_RANGES.items():
        template = group.find(name)
        require(template is not None, f"Missing public parameter template: {name}")
        current = range_state(template)
        require(
            same_range(current, EXPECTED_RANGES[name]) or same_range(current, target),
            f"Unexpected range pre-state for {name}: {current}",
        )
        if not same_range(current, target):
            template.setMinValue(target[0])
            template.setMaxValue(target[1])
            template.setMaxIsStrict(target[2])
            group.replace(name, template)
            changed.append(name)

    padding = group.find("padding")
    padding.setHelp(
        "Auto Domain 开启时作为 Track 包围盒四周的额外外扩距离；范围 0–4096 m。"
        "自适应土方安全边距会在此数值之外另行叠加。"
    )
    group.replace("padding", padding)

    resolution = group.find("tile_resolution")
    require(resolution is not None, "Missing tile_resolution template")
    require(
        tuple(resolution.menuItems()) == ("129", "257", "513", "1025", "2049"),
        f"Unexpected Terrain Resolution menu: {resolution.menuItems()}",
    )
    resolution.setHelp(
        "Unity Heightmap 仅使用 2^n+1 分辨率。HDA 会把旧场景或 Unity 序列化的非法整数"
        "安全吸附到最近的 129/257/513/1025/2049，避免 alphamap 写入失败。"
    )
    group.replace("tile_resolution", resolution)

    group_changed = original_dialog != group.asDialogScript()
    if group_changed:
        definition.setParmTemplateGroup(group)
    return changed, group_changed


def apply_patch(root_path: str = ROOT_PATH, save: bool = False) -> dict[str, Any]:
    require(not save, "Patch must run with save=False")
    root = hou.node(root_path)
    require(root is not None, f"Missing Terrain asset: {root_path}")
    require(root.type().name() == EXPECTED_TYPE, f"Unexpected Terrain type: {root.type().name()}")
    definition = root.type().definition()
    require(definition is not None, "Terrain asset has no definition")
    library = definition.libraryFilePath().replace("\\", "/")
    require(library.endswith(EXPECTED_LIBRARY_SUFFIX), f"Unexpected HDA library: {library}")

    domain = root.node(DOMAIN_NODE)
    require(domain is not None, f"Missing node: {DOMAIN_NODE}")
    grid_parm = domain.parm("gridsamples")
    require(grid_parm is not None, "HF_DOMAIN has no gridsamples parameter")
    current_grid = str(grid_parm.rawValue())
    require(
        current_grid in (OLD_GRID_SAMPLES, NEW_GRID_SAMPLES),
        f"Unexpected gridsamples pre-state: {digest(current_grid)}",
    )
    size_parms = {name: domain.parm(name) for name in ("sizex", "sizey")}
    require(all(size_parms.values()), "HF_DOMAIN size parameters are incomplete")
    current_sizes = {name: str(parm.rawValue()) for name, parm in size_parms.items()}
    require(current_sizes["sizex"] in (OLD_SIZE_X, NEW_SQUARE_SIZE),
            f"Unexpected sizex pre-state: {digest(current_sizes['sizex'])}")
    require(current_sizes["sizey"] in (OLD_SIZE_Y, NEW_SQUARE_SIZE),
            f"Unexpected sizey pre-state: {digest(current_sizes['sizey'])}")

    original_group = definition.parmTemplateGroup()
    original_values = capture_values(root)
    original_grid = current_grid
    original_grid_language = None
    original_size_languages: dict[str, Any | None] = {}
    try:
        original_grid_language = grid_parm.expressionLanguage()
    except Exception:
        pass
    for name, parm in size_parms.items():
        try:
            original_size_languages[name] = parm.expressionLanguage()
        except Exception:
            original_size_languages[name] = None
    original_marker = root.userData("pcgbike_patch_marker")
    old_mode = hou.updateModeSetting()
    changed: list[str] = []
    try:
        hou.setUpdateMode(hou.updateMode.Manual)
        with hou.undos.group(MARKER):
            interface_changes, interface_changed = update_public_interface(definition)
            if interface_changes:
                changed.extend(f"range:{name}" for name in interface_changes)
            if interface_changed:
                root = refresh_instance(root, original_values)
            domain = root.node(DOMAIN_NODE)
            grid_parm = domain.parm("gridsamples")
            if str(grid_parm.rawValue()) != NEW_GRID_SAMPLES:
                grid_parm.setExpression(NEW_GRID_SAMPLES, language=hou.exprLanguage.Hscript)
                changed.append("unity_resolution_guard")
            size_changed = False
            for name in ("sizex", "sizey"):
                parm = domain.parm(name)
                if str(parm.rawValue()) != NEW_SQUARE_SIZE:
                    parm.setExpression(NEW_SQUARE_SIZE, language=hou.exprLanguage.Hscript)
                    size_changed = True
            if size_changed:
                changed.append("unity_square_heightfield_domain")
            root.setUserData("pcgbike_patch_marker", MARKER)
    except Exception:
        definition.setParmTemplateGroup(original_group)
        root = refresh_instance(root, original_values)
        grid_parm = root.node(DOMAIN_NODE).parm("gridsamples")
        if original_grid_language is not None:
            grid_parm.setExpression(original_grid, language=original_grid_language)
        else:
            grid_parm.set(original_grid)
        domain = root.node(DOMAIN_NODE)
        for name, original in current_sizes.items():
            parm = domain.parm(name)
            language = original_size_languages[name]
            if language is not None:
                parm.setExpression(original, language=language)
            else:
                parm.set(original)
        if original_marker is None:
            root.destroyUserData("pcgbike_patch_marker")
        else:
            root.setUserData("pcgbike_patch_marker", original_marker)
        raise
    finally:
        hou.setUpdateMode(old_mode)

    return {
        "status": "PASS",
        "root": root.path(),
        "definition": library,
        "changed": changed,
        "save": False,
        "hip_unsaved_changes": hou.hipFile.hasUnsavedChanges(),
        "spare_parameters": [parm.name() for parm in root.spareParms()],
        "grid_expression": root.node(DOMAIN_NODE).parm("gridsamples").rawValue(),
        "square_domain": {
            name: root.node(DOMAIN_NODE).parm(name).rawValue()
            for name in ("sizex", "sizey")
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", default=ROOT_PATH)
    parser.add_argument("--save", default="false")
    args = parser.parse_args()
    save = str(args.save).lower() in {"1", "true", "yes"}
    print(json.dumps(apply_patch(args.root, save=save), ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
