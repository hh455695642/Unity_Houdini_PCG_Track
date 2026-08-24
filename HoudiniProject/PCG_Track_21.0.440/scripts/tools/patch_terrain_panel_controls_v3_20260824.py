"""Repair Terrain panel controls against the current Live Scene.

The patch is incremental, idempotent, verification-first, and never saves.
It removes HEU-hostile DisableWhen rules, makes the material-off state an
explicit four-layer result, and makes invalid adaptive earthwork fall back to
exact conform instead of aborting the whole HDA cook.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from typing import Any

try:
    import hou
except ModuleNotFoundError:
    # Houdini MCP injects its remote hou proxy after importing this audit script.
    hou = None


ROOT_PATH = "/obj/Terrain1"
EXPECTED_TYPE = "pcgbike::Terrain::1.0"
EXPECTED_LIBRARY_SUFFIX = "/Assets/PCG/HDA/Terrain.hda"
MARKER = "terrain_panel_controls_v3_20260824"

ADAPT_SWITCH = "TerrainCore/40_CONFORM_EARTHWORK/ADAPTIVE_enable_switch"
ADAPT_ERROR = "TerrainCore/40_CONFORM_EARTHWORK/ADAPT_validate_error"
MATERIAL_WEIGHTS = "TerrainCore/60_MATERIAL_LAYERS/MATERIAL_generate_raw_weights"
MATERIAL_SWITCH = "TerrainCore/60_MATERIAL_LAYERS/MATERIAL_enable_switch"

EXPECTED_HASHES = {
    "adaptive_switch": "630a1e81512289fde44fa19cc711d89bea78b9391cff00c3adfe2b9da3cc9f98",
    "adaptive_error": "918f74256a62639d918e746e0442c680f7ed5bd1624a547291180812c6180bec",
    "material_snippet": "68879eecf579adf7820bd9333276033972828fcc149406457a223b6626df85b4",
    "material_switch": "ef0a09a4dbfb2eb1c71c55f38f07b636ab3f12989b306238dd3e7040b477bd70",
}

DISABLE_WHEN_NAMES = {
    "manual_size", "padding", "seed", "mountain_height_scale",
    "macro_amp", "macro_size", "mid_amp", "mid_size", "detail_amp", "detail_size",
    "ridge_angle", "ridge_strength", "ridge_amp", "ridge_size", "erosion_iterations",
    "fallback_road_width", "clearance", "core_extra", "shoulder_blend", "cut_slope",
    "fill_slope", "max_cut", "max_fill", "track_context_width",
    "track_context_strength", "track_context_max_delta", "maximum_earthwork_slope",
    "maximum_adaptive_radius", "earthwork_detail_preserve",
    "earthwork_detail_restore_width", "island_boundary", "sea_level",
    "coast_transition_width", "beach_width", "seabed_depth", "coast_beach_profile",
    "coast_blend_sharpness", "enable_beach_noise", "beach_noise_amplitude",
    "coast_noise_scale", "coast_seed", "enable_beach_erosion",
    "beach_erosion_strength", "beach_erosion_feature_size",
    "beach_erosion_iterations", "track_coast_protect",
}

NEW_ADAPT_SWITCH = (
    'ch("../../../enable_adaptive_earthwork") && '
    'detail("../../00_TRACK_INPUT/TRACK_validate_contract","terrain_input_valid",0) && '
    'detail("../ADAPT_reduce_detail_final","terrain_constraint_conflict_count",0)==0 && '
    'detail("../ADAPT_reduce_detail_final","terrain_max_generated_slope_deg",0)'
    '<=ch("../../../maximum_earthwork_slope")+1.0 && '
    'detail("../ADAPT_reduce_detail_final","terrain_max_road_clearance_error",0)<=0.05'
)

NEW_MATERIAL_SNIPPET = '''// Unity TerrainLayer topology is always explicit.
// Disabling material generation writes a deterministic all-grass result so
// Houdini Engine cannot leave stale alphamaps from the previous successful cook.
int enabled = chi("../../../material_layers_enabled");
if (!enabled)
{
    f@terrain_stone = 0.0;
    f@terrain_gravel = 0.0;
    f@terrain_dirt = 0.0;
    f@terrain_grass = 1.0;
}
else
{
    float cliff_mask = clamp(f@cliff, 0.0, 1.0);
    float steep_rock = smooth(0.35, 0.80, cliff_mask);
    float coast_rock = clamp(f@coast_rock, 0.0, 1.0);
    float stone_raw = max(steep_rock, coast_rock);

    float sand_raw = clamp(f@beach, 0.0, 1.0);
    float gravel_raw = clamp(max(f@road, f@shoulder)
        + max(f@cut, f@fill) * 0.10, 0.0, 1.0);

    f@terrain_stone = stone_raw;
    f@terrain_gravel = gravel_raw;
    f@terrain_dirt = sand_raw;
    f@terrain_grass = clamp(1.0 - stone_raw - gravel_raw - sand_raw, 0.0, 1.0);
}'''


class PatchFailure(RuntimeError):
    pass


def require(condition: bool, message: str) -> None:
    if not condition:
        raise PatchFailure(message)


def digest(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def raw(node: hou.Node, parm_name: str) -> str:
    parm = node.parm(parm_name)
    require(parm is not None, f"Missing parameter: {node.path()}:{parm_name}")
    return str(parm.rawValue())


def refresh_instance(root: hou.Node) -> hou.Node:
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
    root.matchCurrentDefinition()
    root.allowEditingOfContents()
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
    require(not root.spareParms(), "Template refresh created instance-only spare parameters")
    return root


def update_public_interface(definition: hou.HDADefinition) -> tuple[list[str], bool]:
    group = definition.parmTemplateGroup()
    current = {
        name for name in DISABLE_WHEN_NAMES
        if group.find(name) is not None
        and hou.parmCondType.DisableWhen in group.find(name).conditionals()
    }
    require(current == DISABLE_WHEN_NAMES or not current,
            f"Unexpected conditional baseline: {sorted(current)}")
    for name in sorted(current):
        template = group.find(name)
        template.setConditional(hou.parmCondType.DisableWhen, "")
        group.replace(name, template)

    mountain = group.find("mountain_height_scale")
    require(mountain is not None, "Missing mountain_height_scale template")
    defaults_changed = tuple(mountain.defaultValue()) != (1.0,)
    require(tuple(mountain.defaultValue()) in ((8.0,), (1.0,)),
            f"Unexpected mountain_height_scale default: {mountain.defaultValue()}")
    mountain.setDefaultValue((1.0,))
    mountain.setLabel("Macro Height Multiplier / 宏观高度倍率")
    mountain.setHelp(
        "最终 Macro 高度 = Macro Amplitude (m) × 此倍率；默认 1 保持米制振幅，"
        "仅在需要整体放大宏观起伏时提高。"
    )
    group.replace("mountain_height_scale", mountain)
    if current or defaults_changed:
        definition.setParmTemplateGroup(group)
    return sorted(current), defaults_changed


def apply_patch(root_path: str = ROOT_PATH, save: bool = False) -> dict[str, Any]:
    require(not save, "Patch must run with save=False")
    root = hou.node(root_path)
    require(root is not None, f"Missing Terrain asset: {root_path}")
    require(root.type().name() == EXPECTED_TYPE, f"Unexpected Terrain type: {root.type().name()}")
    definition = root.type().definition()
    require(definition is not None, "Terrain asset has no definition")
    library = definition.libraryFilePath().replace("\\", "/")
    require(library.endswith(EXPECTED_LIBRARY_SUFFIX), f"Unexpected HDA library: {library}")

    nodes = {
        "adaptive_switch": root.node(ADAPT_SWITCH),
        "adaptive_error": root.node(ADAPT_ERROR),
        "material_snippet": root.node(MATERIAL_WEIGHTS),
        "material_switch": root.node(MATERIAL_SWITCH),
    }
    require(all(nodes.values()), "Terrain control repair nodes are incomplete")
    current = {
        "adaptive_switch": raw(nodes["adaptive_switch"], "input"),
        "adaptive_error": raw(nodes["adaptive_error"], "enable1"),
        "material_snippet": raw(nodes["material_snippet"], "snippet"),
        "material_switch": raw(nodes["material_switch"], "input"),
    }
    target = {
        "adaptive_switch": NEW_ADAPT_SWITCH,
        "adaptive_error": "0",
        "material_snippet": NEW_MATERIAL_SNIPPET,
        "material_switch": "1",
    }
    for name, value in current.items():
        require(
            value == target[name] or digest(value) == EXPECTED_HASHES[name],
            f"Unexpected pre-state for {name}: {digest(value)}",
        )

    old_mode = hou.updateModeSetting()
    changed: list[str] = []
    try:
        hou.setUpdateMode(hou.updateMode.Manual)
        with hou.undos.group(MARKER):
            removed, defaults_changed = update_public_interface(definition)
            if removed or defaults_changed:
                root = refresh_instance(root)
                if removed:
                    changed.append(f"removed_disable_when:{len(removed)}")
                if defaults_changed:
                    changed.append("macro_height_default_1")
                nodes = {
                    "adaptive_switch": root.node(ADAPT_SWITCH),
                    "adaptive_error": root.node(ADAPT_ERROR),
                    "material_snippet": root.node(MATERIAL_WEIGHTS),
                    "material_switch": root.node(MATERIAL_SWITCH),
                }
            if raw(nodes["adaptive_switch"], "input") != NEW_ADAPT_SWITCH:
                nodes["adaptive_switch"].parm("input").setExpression(
                    NEW_ADAPT_SWITCH, language=hou.exprLanguage.Hscript
                )
                changed.append("adaptive_failsoft_switch")
            if raw(nodes["adaptive_error"], "enable1") != "0":
                nodes["adaptive_error"].parm("enable1").deleteAllKeyframes()
                nodes["adaptive_error"].parm("enable1").set(0)
                changed.append("adaptive_error_disabled")
            if raw(nodes["material_snippet"], "snippet") != NEW_MATERIAL_SNIPPET:
                nodes["material_snippet"].parm("snippet").set(NEW_MATERIAL_SNIPPET)
                changed.append("material_off_explicit_weights")
            if raw(nodes["material_switch"], "input") != "1":
                nodes["material_switch"].parm("input").deleteAllKeyframes()
                nodes["material_switch"].parm("input").set(1)
                changed.append("material_topology_always_uploaded")
            root.setUserData("pcgbike_patch_marker", MARKER)
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
