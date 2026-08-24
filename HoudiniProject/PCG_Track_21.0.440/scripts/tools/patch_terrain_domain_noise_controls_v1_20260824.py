"""Incremental Terrain domain/noise control repair for the current Live Scene.

The patch is idempotent and never saves the HIP.  Public HDA templates are
updated first so the unlocked implementation instance can be refreshed without
creating instance-only spare folder IDs.  The regression Capture backup is the
rollback source for the HDA library if a later gate fails.
"""

from __future__ import annotations

import argparse
import json
from typing import Any

import hou


ROOT_PATH = "/obj/Terrain1"
EXPECTED_TYPE = "pcgbike::Terrain::1.0"
EXPECTED_LIBRARY_SUFFIX = "/Assets/PCG/HDA/Terrain.hda"
MARKER = "terrain_domain_noise_controls_v1_20260824"

SOURCE = "TerrainCore/10_TERRAIN_SOURCE"
DOMAIN = SOURCE + "/HF_DOMAIN"
RIDGE = SOURCE + "/BASE_directional_ridge"
GUIDE_SWITCH = "TerrainCore/20_GUIDE_MESH/GUIDE_MESH_SWITCH"
LAKE_SWITCH = "TerrainCore/30_LAKE_CONSTRAINT/LAKE_SWITCH"

OLD_DOMAIN_SIZE = (
    'if(ch("../../../auto_domain")&&detail("../../00_TRACK_INPUT/'
    'TRACK_validate_contract","terrain_input_valid",0),(max(bbox('
    '"../../00_TRACK_INPUT/TRACK_validate_contract",D_XSIZE),bbox('
    '"../../00_TRACK_INPUT/TRACK_validate_contract",D_ZSIZE))+2*(max('
    'ch("../../../padding"),if(ch("../../../enable_adaptive_earthwork"),'
    'ch("../../../maximum_adaptive_radius")+2*(max(bbox('
    '"../../00_TRACK_INPUT/TRACK_validate_contract",D_XSIZE),bbox('
    '"../../00_TRACK_INPUT/TRACK_validate_contract",D_ZSIZE))+2*ch('
    '"../../../padding"))/(max(1,(ch("../../../tile_resolution")-1))),'
    'ch("../../../padding"))))),max(ch("../../../manual_sizex"),'
    'ch("../../../manual_sizey")))'
)

TRACK = "../../00_TRACK_INPUT/TRACK_validate_contract"
TRACK_VALID = f'detail("{TRACK}","terrain_input_valid",0)'
RESOLUTION_DENOM = 'max(1,ch("../../../tile_resolution")-1)'
ADAPTIVE_MARGIN = (
    'if(ch("../../../enable_adaptive_earthwork"),'
    'ch("../../../maximum_adaptive_radius")+'
    f'2*(max(bbox("{TRACK}",D_XSIZE),bbox("{TRACK}",D_ZSIZE))+'
    '2*(ch("../../../padding")+ch("../../../maximum_adaptive_radius")))/'
    f'{RESOLUTION_DENOM},0)'
)
NEW_SIZE_X = (
    f'if(ch("../../../auto_domain")&&{TRACK_VALID},'
    f'bbox("{TRACK}",D_XSIZE)+2*(ch("../../../padding")+'
    f'{ADAPTIVE_MARGIN}),ch("../../../manual_sizex"))'
)
NEW_SIZE_Z = (
    f'if(ch("../../../auto_domain")&&{TRACK_VALID},'
    f'bbox("{TRACK}",D_ZSIZE)+2*(ch("../../../padding")+'
    f'{ADAPTIVE_MARGIN}),ch("../../../manual_sizey"))'
)
NEW_CENTER_X = (
    f'if({TRACK_VALID},(bbox("{TRACK}",D_XMIN)+'
    f'bbox("{TRACK}",D_XMAX))/2,0)'
)
NEW_CENTER_Z = (
    f'if({TRACK_VALID},(bbox("{TRACK}",D_ZMIN)+'
    f'bbox("{TRACK}",D_ZMAX))/2,0)'
)

OLD_RIDGE_AMP = (
    'ch("../../../macro_amp")*ch("../../../ridge_strength")*'
    'ch("../../../mountain_height_scale")'
)
NEW_RIDGE_AMP = 'ch("../../../ridge_amp")*ch("../../../ridge_strength")'
OLD_RIDGE_SIZE = 'ch("../../../macro_size")'
NEW_RIDGE_SIZE = 'ch("../../../ridge_size")'
OLD_GUIDE_SWITCH = (
    'if(detail("../GUIDE_MESH_VALIDATE","terrain_guide_mesh_valid",0)>0,1,0)'
)
NEW_GUIDE_SWITCH = (
    'if(ch("../../../enable_guide_mesh")&&detail('
    '"../GUIDE_MESH_VALIDATE","terrain_guide_mesh_valid",0)>0,1,0)'
)
OLD_LAKE_SWITCH = (
    'if(detail("../LAKE_VALIDATE_CLOSED","terrain_lake_valid_count",0)>0,1,0)'
)
NEW_LAKE_SWITCH = (
    'if(ch("../../../enable_lake")&&detail('
    '"../LAKE_VALIDATE_CLOSED","terrain_lake_valid_count",0)>0,1,0)'
)


class PatchFailure(RuntimeError):
    pass


def require(condition: bool, message: str) -> None:
    if not condition:
        raise PatchFailure(message)


def parm_expression(node: hou.Node, name: str) -> str:
    parm = node.parm(name)
    require(parm is not None, f"Missing parameter: {node.path()}:{name}")
    try:
        return parm.expression()
    except Exception:
        return str(parm.rawValue())


def set_expression_checked(
    node: hou.Node, name: str, old: str, new: str
) -> bool:
    current = parm_expression(node, name)
    if current == new:
        return False
    require(current == old, f"Unexpected pre-state: {node.path()}:{name} = {current!r}")
    node.parm(name).setExpression(new, language=hou.exprLanguage.Hscript)
    return True


def float_template(
    name: str, label: str, default: float, minimum: float, maximum: float, help_text: str
) -> hou.FloatParmTemplate:
    template = hou.FloatParmTemplate(
        name,
        label,
        1,
        default_value=(default,),
        min=minimum,
        max=maximum,
        min_is_strict=True,
        max_is_strict=False,
    )
    template.setHelp(help_text)
    template.setConditional(hou.parmCondType.DisableWhen, "{ enable_ridge == 0 }")
    return template


def update_public_interface(definition: hou.HDADefinition) -> list[str]:
    group = definition.parmTemplateGroup()
    changed: list[str] = []

    manual = group.find("manual_size")
    padding = group.find("padding")
    mountain = group.find("mountain_height_scale")
    require(all((manual, padding, mountain)), "Terrain domain templates are incomplete")

    if manual.maxValue() != 1.0e9 or manual.maxIsStrict():
        manual.setMaxValue(1.0e9)
        manual.setMaxIsStrict(False)
        changed.append("manual_size")
    manual.setHelp(
        "Auto Domain 关闭时分别控制 X/Z 尺寸；有有效 Track 输入时，手动区域自动以 Track 包围盒中心对齐。"
    )
    group.replace("manual_size", manual)

    if padding.maxValue() != 1.0e9 or padding.maxIsStrict():
        padding.setMaxValue(1.0e9)
        padding.setMaxIsStrict(False)
        changed.append("padding")
    padding.setLabel("Auto Domain Padding (m) / 自动区域外扩数值")
    padding.setHelp(
        "Auto Domain 开启时作为 Track 包围盒四周的额外外扩距离；可直接输入任意非负数值，不再受 1024 限制。自适应土方安全边距会在此数值之外另行叠加。"
    )
    group.replace("padding", padding)

    mountain.setConditional(hou.parmCondType.DisableWhen, "{ enable_macro == 0 }")
    mountain.setHelp("仅缩放 Macro Noise；Directional Ridge 使用独立高度参数。")
    group.replace("mountain_height_scale", mountain)

    if group.find("ridge_amp") is None:
        group.insertAfter(
            "ridge_strength",
            float_template(
                "ridge_amp",
                "Ridge Amplitude (m) / 山脊高度",
                80.0,
                0.0,
                2000.0,
                "方向山脊的独立高度，最终振幅为 Ridge Amplitude × Ridge Strength。",
            ),
        )
        changed.append("ridge_amp")
    if group.find("ridge_size") is None:
        group.insertAfter(
            "ridge_amp",
            float_template(
                "ridge_size",
                "Ridge Element Size (m) / 山脊尺度",
                300.0,
                1.0,
                10000.0,
                "方向山脊的独立噪声尺度，不再读取 Macro Element Size。",
            ),
        )
        changed.append("ridge_size")

    if group.find("enable_guide_mesh") is None:
        toggle = hou.ToggleParmTemplate(
            "enable_guide_mesh",
            "Enable Guide Mesh / 启用地形引导",
            default_value=True,
        )
        toggle.setHelp("显式控制 Guide Mesh 阶段；关闭时即使 Input 2 仍有连接也直接旁路。")
        group.insertAfter("terrain_guide_meshes", toggle)
        changed.append("enable_guide_mesh")

    if group.find("enable_lake") is None:
        toggle = hou.ToggleParmTemplate(
            "enable_lake",
            "Enable Lake / 启用湖泊约束",
            default_value=True,
        )
        toggle.setHelp("显式控制 Lake 阶段；关闭时即使 Input 3 仍有闭合曲线也直接旁路。")
        group.insertAfter("lake_curves", toggle)
        changed.append("enable_lake")

    if changed or definition.parmTemplateGroup().asDialogScript() != group.asDialogScript():
        definition.setParmTemplateGroup(group)
    return changed


def refresh_instance(root: hou.Node) -> hou.Node:
    """Refresh inherited templates without retaining synthetic spare folders."""
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


def apply_patch(root_path: str = ROOT_PATH, save: bool = False) -> dict[str, Any]:
    require(not save, "This patch is verification-first and must run with save=False")
    root = hou.node(root_path)
    require(root is not None, f"Missing Terrain asset: {root_path}")
    require(root.type().name() == EXPECTED_TYPE, f"Unexpected Terrain type: {root.type().name()}")
    definition = root.type().definition()
    require(definition is not None, "Terrain asset has no HDA definition")
    library = definition.libraryFilePath().replace("\\", "/")
    require(library.endswith(EXPECTED_LIBRARY_SUFFIX), f"Unexpected Terrain library: {library}")

    old_update_mode = hou.updateModeSetting()
    hou.setUpdateMode(hou.updateMode.Manual)
    changed: list[str] = []
    with hou.undos.group(MARKER):
        interface_changes = update_public_interface(definition)
        root = refresh_instance(root)

        domain = root.node(DOMAIN)
        ridge = root.node(RIDGE)
        guide_switch = root.node(GUIDE_SWITCH)
        lake_switch = root.node(LAKE_SWITCH)
        require(all((domain, ridge, guide_switch, lake_switch)), "Terrain repair nodes are incomplete")

        if set_expression_checked(domain, "sizex", OLD_DOMAIN_SIZE, NEW_SIZE_X):
            changed.append("domain_x_independent")
        if set_expression_checked(domain, "sizey", OLD_DOMAIN_SIZE, NEW_SIZE_Z):
            changed.append("domain_z_independent")
        old_center_x = (
            'if(ch("../../../auto_domain")&&detail("../../00_TRACK_INPUT/'
            'TRACK_validate_contract","terrain_input_valid",0),(bbox('
            '"../../00_TRACK_INPUT/TRACK_validate_contract",D_XMIN)+bbox('
            '"../../00_TRACK_INPUT/TRACK_validate_contract",D_XMAX))/2,0)'
        )
        old_center_z = (
            'if(ch("../../../auto_domain")&&detail("../../00_TRACK_INPUT/'
            'TRACK_validate_contract","terrain_input_valid",0),(bbox('
            '"../../00_TRACK_INPUT/TRACK_validate_contract",D_ZMIN)+bbox('
            '"../../00_TRACK_INPUT/TRACK_validate_contract",D_ZMAX))/2,0)'
        )
        if set_expression_checked(domain, "tx", old_center_x, NEW_CENTER_X):
            changed.append("manual_center_x_tracks_input")
        if set_expression_checked(domain, "tz", old_center_z, NEW_CENTER_Z):
            changed.append("manual_center_z_tracks_input")
        if set_expression_checked(ridge, "amp", OLD_RIDGE_AMP, NEW_RIDGE_AMP):
            changed.append("ridge_amplitude_decoupled")
        if set_expression_checked(ridge, "elementsize", OLD_RIDGE_SIZE, NEW_RIDGE_SIZE):
            changed.append("ridge_size_decoupled")
        if set_expression_checked(guide_switch, "input", OLD_GUIDE_SWITCH, NEW_GUIDE_SWITCH):
            changed.append("guide_explicit_toggle")
        if set_expression_checked(lake_switch, "input", OLD_LAKE_SWITCH, NEW_LAKE_SWITCH):
            changed.append("lake_explicit_toggle")

        root.setUserData("pcgbike_patch_marker", MARKER)
        changed.extend(f"interface:{name}" for name in interface_changes)

    hou.setUpdateMode(old_update_mode)
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
