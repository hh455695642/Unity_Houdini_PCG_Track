"""Read-only Terrain Shape sensitivity validation.

The script loads a HIP, cooks HeightFields, compares deterministic hashes, and
restores all touched in-memory parameters. It never saves the HIP or HDA.

Run with Houdini's Python:
    hython validate_terrain_shape_params.py
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import statistics
import sys
import time
from pathlib import Path
from typing import Any, Dict, Iterable, List, Tuple

import hou


SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_DIR = SCRIPT_DIR.parents[1]
DEFAULT_HIP = PROJECT_DIR / "PCG_Bike_Terrain.hip"
DEFAULT_NODE = "/obj/Terrain1"
SOURCE_RELATIVE_PATH = "TerrainCore/10_TERRAIN_SOURCE"
OUTPUT_NODE = "OUT_BASE_HEIGHTFIELD"
RIDGE_NOISE_NODE = "BASE_directional_ridge"
RIDGE_PRE_NODE = "BASE_ridge_pre_rotate"
RIDGE_POST_NODE = "BASE_ridge_post_rotate"
RIDGE_SWITCH_NODE = "BASE_ridge_switch"

TOUCHED_PARAMETERS = (
    "track_geometry",
    "auto_domain",
    "manual_sizex",
    "manual_sizey",
    "padding",
    "tile_resolution",
    "enable_adaptive_earthwork",
    "seed",
    "mountain_height_scale",
    "enable_macro",
    "macro_amp",
    "macro_size",
    "enable_mid",
    "mid_amp",
    "mid_size",
    "enable_detail",
    "detail_amp",
    "detail_size",
    "enable_ridge",
    "ridge_angle",
    "ridge_strength",
    "ridge_amp",
    "ridge_size",
    "enable_erosion",
    "erosion_iterations",
    "material_layers_enabled",
    "cliff_start",
    "cliff_full",
)


class ValidationFailure(RuntimeError):
    pass


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ValidationFailure(message)


def set_values(root: hou.Node, values: Dict[str, float | int]) -> None:
    for name, value in values.items():
        parm = root.parm(name)
        require(parm is not None, f"Missing public parameter: {name}")
        parm.set(value)


def volume_bytes(prim: hou.Volume) -> bytes:
    try:
        return prim.allVoxelsAsString()
    except AttributeError:
        # Compatibility fallback for older Houdini builds.
        return b"".join(float(v).hex().encode("ascii") + b";" for v in prim.allVoxels())


def heightfield_snapshot(output: hou.Node) -> Dict[str, Any]:
    output.cook(force=True)
    require(not output.errors(), f"{output.path()} errors: {'; '.join(output.errors())}")

    geometry = output.geometry()
    volumes = [prim for prim in geometry.prims() if isinstance(prim, hou.Volume)]
    names = tuple(prim.attribValue("name") for prim in volumes)
    height = next((prim for prim in volumes if prim.attribValue("name") == "height"), None)
    require(height is not None, f"{output.path()} has no height volume")

    values = height.allVoxels()
    require(all(math.isfinite(value) for value in values), "HeightField contains NaN/Inf")
    bounds = geometry.boundingBox()
    return {
        "hash": hashlib.sha256(volume_bytes(height)).hexdigest(),
        "resolution": tuple(height.resolution()),
        "layer_names": names,
        "point_count": len(geometry.points()),
        "prim_count": len(geometry.prims()),
        "vertex_count": sum(prim.numVertices() for prim in geometry.prims()),
        "bbox_min": tuple(bounds.minvec()),
        "bbox_max": tuple(bounds.maxvec()),
        "warnings": tuple(output.warnings()),
    }


def hash_for(
    root: hou.Node,
    output: hou.Node,
    base: Dict[str, float | int],
    overrides: Dict[str, float | int],
    reference_structure: Dict[str, Any],
    enforce_structure: bool = True,
) -> str:
    values = dict(base)
    values.update(overrides)
    set_values(root, values)
    snapshot = heightfield_snapshot(output)

    if enforce_structure:
        for key in ("resolution", "layer_names", "point_count", "prim_count", "vertex_count"):
            require(
                snapshot[key] == reference_structure[key],
                f"Geometry structure changed for {overrides}: {key} "
                f"{snapshot[key]!r} != {reference_structure[key]!r}",
            )
    return snapshot["hash"]


def all_distinct(values: Iterable[str]) -> bool:
    values = tuple(values)
    return len(set(values)) == len(values)


def material_layer_snapshot(output: hou.Node) -> Dict[str, Any]:
    """Hash Unity TerrainLayer weights and report their numeric ranges."""

    output.cook(force=True)
    require(not output.errors(), f"{output.path()} errors: {'; '.join(output.errors())}")
    volumes = {
        prim.attribValue("name"): prim
        for prim in output.geometry().prims()
        if isinstance(prim, hou.Volume)
    }
    expected = ("terrain_grass", "terrain_stone", "terrain_gravel", "terrain_dirt")
    require(all(name in volumes for name in expected), "Unity material layer topology is incomplete")
    digest = hashlib.sha256()
    ranges = {}
    for name in expected:
        values = volumes[name].allVoxels()
        require(all(math.isfinite(value) for value in values), f"{name} contains NaN/Inf")
        digest.update(volume_bytes(volumes[name]))
        ranges[name] = (min(values), max(values))
    return {"hash": digest.hexdigest(), "ranges": ranges, "layer_names": tuple(volumes)}


def check_topology(root: hou.Node, source: hou.Node) -> List[str]:
    messages: List[str] = []
    detail = source.node("BASE_detail_switch")
    pre = source.node(RIDGE_PRE_NODE)
    noise = source.node(RIDGE_NOISE_NODE)
    post = source.node(RIDGE_POST_NODE)
    switch = source.node(RIDGE_SWITCH_NODE)
    require(all((detail, pre, noise, post, switch)), "Directional Ridge nodes are incomplete")

    require(pre.type().name() == "heightfield_xform", "Pre-rotate is not HeightField Transform")
    require(post.type().name() == "heightfield_xform", "Post-rotate is not HeightField Transform")
    require(pre.input(0) == detail, "detail -> pre connection is incorrect")
    require(noise.input(0) == pre, "pre -> sparse ridge connection is incorrect")
    require(post.input(0) == noise, "sparse ridge -> post connection is incorrect")
    require(switch.input(0) == detail, "ridge disabled branch changed")
    require(switch.input(1) == post, "post -> ridge enabled branch is incorrect")

    require(noise.parm("basis").evalAsString() == "sparse", "Ridge basis is not Sparse Convolution")
    require(noise.parm("flowrot").eval() == 0, "Flow Rotation must remain zero")
    require(pre.parm("ry").expression() == 'ch("../../../ridge_angle")', "Pre rotation expression differs")
    require(
        post.parm("ry").expression() == '-ch("../../../ridge_angle")',
        "Post rotation expression differs",
    )
    require(
        noise.parm("offsetx").expression() == '(ch("../../../seed") - 1) * 101.03',
        "Ridge offsetx expression differs",
    )
    require(
        noise.parm("offsetz").expression() == '(ch("../../../seed") - 1) * 53.17',
        "Ridge offsetz expression differs",
    )
    require(abs(noise.parm("elementscalex").eval() - 0.35) < 1e-7, "Ridge X scale changed")
    require(
        noise.parm("amp").expression()
        == 'ch("../../../ridge_amp")*ch("../../../ridge_strength")',
        "Ridge amplitude is coupled to Macro controls",
    )
    require(
        noise.parm("elementsize").expression() == 'ch("../../../ridge_size")',
        "Ridge size is coupled to Macro controls",
    )

    boxes = {box.name() for box in source.networkBoxes()}
    require("Directional_Ridge_Frame" in boxes, "Directional Ridge network box is missing")

    group = root.type().definition().parmTemplateGroup()
    conditional_names: List[str] = []

    def collect_conditionals(templates: Iterable[hou.ParmTemplate]) -> None:
        for template in templates:
            if hou.parmCondType.DisableWhen in template.conditionals():
                conditional_names.append(template.name())
            if template.type() == hou.parmTemplateType.Folder:
                collect_conditionals(template.parmTemplates())

    collect_conditionals(group.entries())
    require(
        not conditional_names,
        f"Public DisableWhen rules remain and can desync in HEU: {conditional_names}",
    )
    guide_switch = root.node("TerrainCore/20_GUIDE_MESH/GUIDE_MESH_SWITCH")
    lake_switch = root.node("TerrainCore/30_LAKE_CONSTRAINT/LAKE_SWITCH")
    require(all((guide_switch, lake_switch)), "Guide/Lake switches are incomplete")
    require(root.parm("enable_guide_mesh") is not None, "Enable Guide Mesh is missing")
    require(root.parm("enable_lake") is not None, "Enable Lake is missing")
    require(
        "enable_guide_mesh" in guide_switch.parm("input").expression(),
        "Guide Mesh switch ignores its explicit toggle",
    )
    require(
        "enable_lake" in lake_switch.parm("input").expression(),
        "Lake switch ignores its explicit toggle",
    )
    messages.append("Topology, no HEU-hostile DisableWhen rules, and explicit module toggles")
    return messages


def check_panel_bindings(root: hou.Node) -> List[str]:
    """Every editable business parameter on all four tabs must reach the node network."""

    raw_values: List[str] = []
    for node in root.allSubChildren():
        for parm in node.parms():
            try:
                value = parm.rawValue()
            except Exception:
                continue
            if isinstance(value, str):
                raw_values.append(value)
    joined = "\n".join(raw_values)
    group = root.type().definition().parmTemplateGroup()
    missing: List[str] = []

    def walk(templates: Iterable[hou.ParmTemplate], in_public_tab: bool = False) -> None:
        for template in templates:
            public = in_public_tab or template.name().startswith("terrain_overview_tab")
            if template.type() == hou.parmTemplateType.Folder:
                walk(template.parmTemplates(), public)
            elif public and template.type() != hou.parmTemplateType.Label:
                if template.name() not in joined:
                    missing.append(template.name())

    walk(group.entries())
    require(not missing, f"Public Terrain parameters have no downstream binding: {missing}")
    return ["All editable parameters across the four public tabs have downstream bindings"]


def check_failsoft_and_material_contract(root: hou.Node) -> List[str]:
    earthwork = root.node("TerrainCore/40_CONFORM_EARTHWORK")
    material = root.node("TerrainCore/60_MATERIAL_LAYERS")
    require(all((earthwork, material)), "Earthwork/Material networks are incomplete")
    adaptive_switch = earthwork.node("ADAPTIVE_enable_switch")
    adaptive_error = earthwork.node("ADAPT_validate_error")
    weights = material.node("MATERIAL_generate_raw_weights")
    material_switch = material.node("MATERIAL_enable_switch")
    require(all((adaptive_switch, adaptive_error, weights, material_switch)),
            "Fail-soft/material repair nodes are incomplete")
    adaptive_expression = adaptive_switch.parm("input").expression()
    for token in (
        "terrain_constraint_conflict_count",
        "terrain_max_generated_slope_deg",
        "terrain_max_road_clearance_error",
    ):
        require(token in adaptive_expression, f"Adaptive fail-soft switch ignores {token}")
    require(adaptive_error.parm("enable1").eval() == 0,
            "Adaptive validation can still abort the entire HDA cook")
    snippet = weights.parm("snippet").evalAsString()
    require("material_layers_enabled" in snippet and "f@terrain_grass = 1.0" in snippet,
            "Material-off state does not explicitly overwrite Unity weights")
    require(material_switch.parm("input").eval() == 1,
            "Unity TerrainLayer topology is still omitted when materials are disabled")
    return ["Adaptive Earthwork fails soft; material-off uploads explicit all-grass weights"]


def check_output_routing(root: hou.Node) -> List[str]:
    """Protect the current compact Terrain pipeline routing."""

    core = root.node("TerrainCore")
    require(core is not None, "TerrainCore is missing")
    source = core.node("10_TERRAIN_SOURCE")
    guide = core.node("20_GUIDE_MESH")
    lake = core.node("30_LAKE_CONSTRAINT")
    earthwork = core.node("40_CONFORM_EARTHWORK")
    layers = core.node("60_MATERIAL_LAYERS")
    terrain_heightfield = core.node("OUT_TERRAIN_HEIGHTFIELD")
    require(
        all((source, guide, lake, earthwork, layers, terrain_heightfield)),
        "Terrain compact output pipeline is incomplete",
    )
    require(guide.input(0) == source, "Terrain Source no longer feeds Guide Mesh")
    require(lake.input(0) == guide, "Guide Mesh no longer feeds Lake Constraint")
    require(earthwork.input(0) == lake, "Lake Constraint no longer feeds Earthwork")
    require(layers.input(0) == earthwork, "Earthwork no longer feeds Material Layers")
    require(
        terrain_heightfield.input(0) == layers,
        "60_MATERIAL_LAYERS no longer feeds OUT_TERRAIN_HEIGHTFIELD",
    )
    require(core.node("70_OUTPUT") is None, "Removed 70_OUTPUT subnet returned")
    require(core.node("80_VALIDATION") is None, "Removed 80_VALIDATION subnet returned")
    return ["Compact Source -> Guide -> Lake -> Earthwork -> Material output routing"]


def check_mask_cleanup(root: hou.Node) -> List[str]:
    """Protect the material-only cliff controls and removed dead mask branches."""

    core = root.node("TerrainCore")
    earthwork = core.node("40_CONFORM_EARTHWORK") if core else None
    output_stage = core.node("70_OUTPUT") if core else None
    require(all((core, earthwork, output_stage)), "Terrain mask cleanup networks are incomplete")

    removed_paths = (
        "40_CONFORM_EARTHWORK/MASK_no_scatter",
        "40_CONFORM_EARTHWORK/MASK_water_candidate",
        "40_CONFORM_EARTHWORK/MASK_apply_water_exclusions",
        "40_CONFORM_EARTHWORK/PREP_isolate_mask_no_scatter",
        "40_CONFORM_EARTHWORK/PREP_keep_mask_no_scatter",
        "40_CONFORM_EARTHWORK/PREP_name_no_scatter",
        "40_CONFORM_EARTHWORK/PREP_isolate_mask_water_candidate",
        "40_CONFORM_EARTHWORK/PREP_keep_mask_water_candidate",
        "40_CONFORM_EARTHWORK/PREP_name_water_candidate",
        "70_OUTPUT/OUTPUT_contract_layers",
        "70_OUTPUT/OUTPUT_keep_road",
        "70_OUTPUT/OUTPUT_keep_shoulder",
        "70_OUTPUT/OUTPUT_keep_cut",
        "70_OUTPUT/OUTPUT_keep_fill",
        "70_OUTPUT/OUTPUT_keep_slope",
        "70_OUTPUT/OUTPUT_keep_no_scatter",
        "70_OUTPUT/OUTPUT_keep_cliff",
        "70_OUTPUT/OUTPUT_keep_water_candidate",
        "70_OUTPUT/OUTPUT_keep_artist_lock",
    )
    for path in removed_paths:
        require(core.node(path) is None, f"Removed dead mask node returned: {path}")

    prep = earthwork.node("PREP_contract_mask_layers")
    mask_fill = earthwork.node("MASK_fill")
    mask_cliff = earthwork.node("MASK_cliff")
    resolve_overlap = earthwork.node("MASK_resolve_cut_fill_overlap")
    final_guard = earthwork.node("FINAL_road_clearance_guard")
    require(
        all((prep, mask_fill, mask_cliff, resolve_overlap, final_guard)),
        "Terrain retained mask nodes are incomplete",
    )
    expected_prep_inputs = [
        "TRACK_CONTEXT_enable_switch",
        "PREP_name_road",
        "PREP_name_shoulder",
        "PREP_name_cut",
        "PREP_name_fill",
        "PREP_name_slope",
        "PREP_name_cliff",
        "PREP_name_artist_lock",
    ]
    actual_prep_inputs = [
        connection.inputNode().name()
        for connection in sorted(prep.inputConnections(), key=lambda item: item.inputIndex())
    ]
    require(actual_prep_inputs == expected_prep_inputs, "Terrain contract mask merge inputs changed")

    for node_name in (
        "ADAPT_measure_grid",
        "CONFORM_BASE_LOW",
        "CONFORM_core_exact_height",
        "CONFORM_enable_switch",
    ):
        require(
            earthwork.node(node_name).input(0) == mask_fill,
            f"MASK_fill bypass route changed: {node_name}",
        )
    require(resolve_overlap.input(0) == mask_cliff, "Cliff -> overlap mask route changed")
    require(final_guard.input(0) == resolve_overlap, "Overlap mask -> clearance guard route changed")
    require(
        mask_cliff.parm("min_slopeangle").expression() == 'ch("../../../cliff_start")',
        "Stone slope start binding changed",
    )
    require(
        mask_cliff.parm("max_slopeangle").expression() == 'ch("../../../cliff_full")',
        "Stone slope full binding changed",
    )

    metadata = output_stage.node("METADATA_write_contract")
    require(metadata is not None, "Terrain metadata writer is missing")
    snippet = metadata.parm("snippet").evalAsString()
    require('s@terrain_contract_version = "1.14";' in snippet, "Terrain metadata version changed")
    require("no_scatter" not in snippet, "Removed no_scatter metadata returned")
    require("water_candidate" not in snippet, "Removed water_candidate metadata returned")
    return ["Dead no-scatter/water masks removed; cliff remains material-only"]


def check_interface_contract(root: hou.Node, source: hou.Node) -> List[str]:
    """Protect the authored Terrain panel hierarchy from spare-folder drift."""

    group = root.type().definition().parmTemplateGroup()
    top_tabs = [
        entry
        for entry in group.entries()
        if entry.type() == hou.parmTemplateType.Folder
        and entry.folderType() == hou.folderType.Tabs
        and not entry.isHidden()
    ]
    expected_top_labels = [
        "Overview / 总览",
        "Terrain Shape / 地形形态",
        "Advanced / 高级",
        "Terrain Material / 地形材质",
    ]
    require(
        [entry.label() for entry in top_tabs] == expected_top_labels,
        "Terrain top-level parameter tabs changed",
    )

    overview, terrain_shape, advanced, terrain_material = top_tabs
    require(
        [entry.name() for entry in overview.parmTemplates()]
        == [
            "input_contract_label",
            "output_contract_label",
            "auto_domain",
            "manual_size",
            "padding",
            "tile_resolution",
        ],
        "Overview must contain contract, domain, and resolution parameters directly",
    )
    padding_template = group.find("padding")
    manual_template = group.find("manual_size")
    mountain_template = group.find("mountain_height_scale")
    require(padding_template.maxValue() == 4096.0, "Auto Padding maximum is not 4096")
    require(padding_template.maxIsStrict(), "Auto Padding maximum is not enforced")
    require(manual_template.maxValue() >= 1.0e9, "Manual Domain still has the old UI cap")
    require(tuple(mountain_template.defaultValue()) == (1.0,),
            "Macro height multiplier default is not the meter-safe value 1")
    resolution_template = group.find("tile_resolution")
    require(
        tuple(resolution_template.menuItems()) == ("129", "257", "513", "1025", "2049"),
        "Terrain Resolution no longer exposes only Unity-safe 2^n+1 values",
    )

    expected_noise_maxima = {
        "seed": 200000.0,
        "mountain_height_scale": 24.0,
        "macro_amp": 1000.0,
        "macro_size": 4000.0,
        "mid_amp": 400.0,
        "mid_size": 1000.0,
        "detail_amp": 100.0,
        "detail_size": 200.0,
        "ridge_strength": 4.0,
        "ridge_amp": 4000.0,
        "ridge_size": 20000.0,
    }
    for name, expected_maximum in expected_noise_maxima.items():
        template = group.find(name)
        require(template is not None, f"Missing Terrain Shape control: {name}")
        require(abs(float(template.maxValue()) - expected_maximum) <= 1e-6,
                f"Terrain Shape range changed for {name}")

    shape_folders = {
        entry.label(): entry
        for entry in terrain_shape.parmTemplates()
        if entry.type() == hou.parmTemplateType.Folder
    }
    ridge_folder = shape_folders.get("Directional Ridge / 方向山脊")
    require(ridge_folder is not None, "Directional Ridge folder is missing")
    require(
        [entry.name() for entry in ridge_folder.parmTemplates()]
        == ["enable_ridge", "ridge_angle", "ridge_strength", "ridge_amp", "ridge_size"],
        "Directional Ridge public controls changed",
    )

    advanced_tabs = [
        entry
        for entry in advanced.parmTemplates()
        if entry.type() == hou.parmTemplateType.Folder
    ]
    require(
        [entry.label() for entry in advanced_tabs]
        == [
            "Track & Earthwork / 赛道与土方",
            "Guide Mesh / 地形引导",
            "Island Coast / 海岛海岸",
            "Lake / 湖泊",
        ],
        "Advanced child tabs changed",
    )
    island = advanced_tabs[2]
    guide = advanced_tabs[1]
    lake = advanced_tabs[3]
    require(
        [entry.name() for entry in guide.parmTemplates()]
        == [
            "terrain_guide_meshes",
            "enable_guide_mesh",
            "guide_mesh_strength",
            "guide_mesh_blend_width",
            "guide_mesh_detail_preserve",
            "guide_mesh_detail_scale",
            "guide_mesh_transition_slope",
        ],
        "Guide Mesh controls changed",
    )
    require(
        [entry.name() for entry in lake.parmTemplates()]
        == [
            "lake_curves",
            "enable_lake",
            "lake_depth",
            "lake_bank_width",
            "lake_shore_flatness",
            "lake_strength",
        ],
        "Lake controls changed",
    )
    require(
        [
            entry.label()
            for entry in island.parmTemplates()
            if entry.type() == hou.parmTemplateType.Folder
        ]
        == ["Profile / 横截面", "Beach Surface / 海滩表面"],
        "Island Coast inner groups changed",
    )
    require(
        [entry.name() for entry in terrain_material.parmTemplates()]
        == [
            "material_layers_enabled",
            "cliff_start",
            "cliff_full",
        ],
        "Terrain Material parameters changed",
    )
    require(
        terrain_material.parmTemplates()[1].label()
        == "Stone Slope Start (deg) / 岩石材质起始坡度",
        "Stone Slope Start label changed",
    )
    require(
        terrain_material.parmTemplates()[2].label()
        == "Stone Slope Full (deg) / 岩石材质完全坡度",
        "Stone Slope Full label changed",
    )

    for name in (
        "height_range",
        "min_domain_size",
        "tile_count",
        "no_scatter_extra",
        "water_max_slope",
        "water_max_height",
        "terrain_material_output_folder",
    ):
        require(group.find(name) is None, f"Removed parameter returned: {name}")
        require(root.parm(name) is None, f"Instance still contains removed parameter: {name}")
    require(not root.spareParms(), "Terrain instance contains spare parameter-folder overrides")

    domain = source.node("HF_DOMAIN")
    require(domain is not None, "HF_DOMAIN is missing")
    for name in ("sizex", "sizey"):
        expression = domain.parm(name).expression()
        require("use_bake_resolution" not in expression, f"{name} uses removed preview switch")
        require("bake_resolution" not in expression, f"{name} uses removed bake resolution")
        require("tile_resolution" in expression, f"{name} no longer uses Terrain Resolution")
        require('max(ch("../../../padding")' not in expression,
                f"{name} restored the dead Auto Padding max() range")
    size_expressions = (domain.parm("sizex").expression(), domain.parm("sizey").expression())
    require(size_expressions[0] == size_expressions[1],
            "Terrain HeightField domain is no longer square")
    for expression in size_expressions:
        require("manual_sizex" in expression and "manual_sizey" in expression,
                "Manual X/Z controls no longer contribute to the square domain")
        require("D_XSIZE" in expression and "D_ZSIZE" in expression,
                "Auto Track X/Z extents no longer contribute to the square domain")
    require("auto_domain" not in domain.parm("tx").expression(),
            "Manual Domain X center no longer follows Track")
    require("auto_domain" not in domain.parm("tz").expression(),
            "Manual Domain Z center no longer follows Track")
    grid_expression = domain.parm("gridsamples").expression()
    for token in ("129", "257", "513", "1025", "2049"):
        require(token in grid_expression,
                f"Terrain Resolution guard is missing supported value {token}")

    return [
        "Four-tab interface, square Unity domain, Padding max 4096, widened noise ranges"
    ]


def run_validation(root: hou.Node, source: hou.Node, output: hou.Node) -> Dict[str, Any]:
    passed = check_topology(root, source)
    passed.extend(check_output_routing(root))
    passed.extend(check_interface_contract(root, source))
    passed.extend(check_panel_bindings(root))
    passed.extend(check_failsoft_and_material_contract(root))
    original = {name: root.parm(name).eval() for name in TOUCHED_PARAMETERS}

    # Stable values shared by sensitivity tests. Individual modules are isolated.
    isolated = {
        "auto_domain": 0,
        "manual_sizex": 512.0,
        "manual_sizey": 512.0,
        "padding": 128.0,
        "tile_resolution": 513,
        "enable_adaptive_earthwork": 0,
        "seed": 1,
        "mountain_height_scale": 1.0,
        "enable_macro": 0,
        "enable_mid": 0,
        "enable_detail": 0,
        "enable_ridge": 0,
        "enable_erosion": 0,
    }

    set_values(root, isolated)
    reference = heightfield_snapshot(output)

    probe_geo = None
    try:
        probe_geo = hou.node("/obj").createNode(
            "geo", "__terrain_domain_validation_probe__", run_init_scripts=False
        )
        box = probe_geo.createNode("box", "TRACK_SURFACE_PROBE")
        box.parmTuple("size").set((1000.0, 10.0, 700.0))
        box.parmTuple("t").set((125.0, 0.0, -75.0))
        tag = probe_geo.createNode("attribwrangle", "TAG_UNITY_MESH")
        tag.setInput(0, box)
        tag.parm("class").set(1)
        tag.parm("snippet").set('s@unity_input_mesh_name = "terrain-domain-probe";')
        root.parm("track_geometry").set(tag.path())
        track_validate = root.node("TerrainCore/00_TRACK_INPUT/TRACK_validate_contract")
        track_validate.cook(force=True)
        require(
            track_validate.geometry().intAttribValue("terrain_input_valid") == 1,
            "Synthetic Track probe was rejected by Terrain input contract",
        )

        domain = source.node("HF_DOMAIN")
        set_values(root, {"tile_resolution": 512})
        require(domain.parm("gridsamples").evalAsInt() == 513,
                "Legacy Terrain Resolution 512 does not snap to 513")
        set_values(root, {"tile_resolution": 2048})
        require(domain.parm("gridsamples").evalAsInt() == 2049,
                "Legacy Terrain Resolution 2048 does not snap to 2049")
        set_values(root, {"tile_resolution": 513})
        passed.append("Resolution: legacy 512/2048 snap to Unity-safe 513/2049")

        set_values(root, {"auto_domain": 0, "manual_sizex": 640.0, "manual_sizey": 960.0})
        require(abs(domain.parm("sizex").eval() - 960.0) < 1e-5,
                "Manual Domain does not use the larger X/Z extent")
        require(abs(domain.parm("sizey").eval() - 960.0) < 1e-5,
                "Manual HeightField domain is not square")
        manual_center = (domain.parm("tx").eval(), domain.parm("tz").eval())
        set_values(root, {"auto_domain": 1, "enable_adaptive_earthwork": 0, "padding": 128.0})
        size_128 = (domain.parm("sizex").eval(), domain.parm("sizey").eval())
        require(abs(size_128[0] - size_128[1]) < 1e-5,
                "Auto HeightField domain is not square")
        auto_center = (domain.parm("tx").eval(), domain.parm("tz").eval())
        set_values(root, {"padding": 2048.0})
        size_2048 = (domain.parm("sizex").eval(), domain.parm("sizey").eval())
        expected_delta = 2.0 * (2048.0 - 128.0)
        require(all(abs((b - a) - expected_delta) < 1e-4
                    for a, b in zip(size_128, size_2048)),
                "Auto Padding above 1024 does not expand both axes numerically")
        require(all(abs(a - b) < 1e-5 for a, b in zip(manual_center, auto_center)),
                "Manual and Auto Domain centers differ with a valid Track")
        set_values(root, {"padding": 4096.0})
        size_4096 = (domain.parm("sizex").eval(), domain.parm("sizey").eval())
        require(all(b > a for a, b in zip(size_2048, size_4096)),
                "Auto Padding 4096 does not expand both axes")
        passed.append("Domain: square X/Z, Track-centered manual mode, Padding 4096 sensitivity")

        ridge = dict(isolated)
        ridge.update(enable_ridge=1, ridge_strength=0.5, ridge_amp=80.0, ridge_size=300.0)
        angle_hashes = [
            hash_for(root, output, ridge, {"ridge_angle": angle}, reference)
            for angle in (0.0, 45.0, 90.0, 360.0)
        ]
        require(all_distinct(angle_hashes[:3]), "Ridge angle 0/45/90 is not sensitive")
        require(angle_hashes[0] == angle_hashes[3], "Ridge angle 0 and 360 differ")
        passed.append("Ridge angle: 0 != 45 != 90 and 0 == 360")

        ridge_disabled_hash = hash_for(root, output, isolated, {}, reference)
        strength_zero_hash = hash_for(
            root, output, ridge, {"ridge_angle": 0.0, "ridge_strength": 0.0}, reference
        )
        require(strength_zero_hash == ridge_disabled_hash, "Ridge strength 0 changes upstream output")
        strength_hashes = [
            hash_for(root, output, ridge, {"ridge_strength": strength}, reference)
            for strength in (0.5, 1.0)
        ]
        require(strength_hashes[0] != strength_hashes[1], "Ridge strength 0.5/1.0 is not sensitive")
        passed.append("Ridge strength: 0 is bypass-equivalent; 0.5 != 1.0")

        ridge_amp_hashes = [
            hash_for(root, output, ridge, {"ridge_amp": value}, reference)
            for value in (40.0, 80.0)
        ]
        require(ridge_amp_hashes[0] != ridge_amp_hashes[1],
                "Ridge Amplitude is not sensitive")
        ridge_size_hashes = [
            hash_for(root, output, ridge, {"ridge_size": value}, reference)
            for value in (180.0, 360.0)
        ]
        require(ridge_size_hashes[0] != ridge_size_hashes[1],
                "Ridge Element Size is not sensitive")
        passed.append("Ridge: independent Amplitude and Element Size change output")

        seed_hashes = [
            hash_for(root, output, ridge, {"seed": seed, "ridge_angle": 0.0}, reference)
            for seed in (0, 1, 2)
        ]
        require(all_distinct(seed_hashes), "Ridge seed 0/1/2 is not sensitive")
        repeat_a = hash_for(root, output, ridge, {"seed": 100000, "ridge_angle": 23.0}, reference)
        repeat_b = hash_for(root, output, ridge, {"seed": 100000, "ridge_angle": 23.0}, reference)
        require(repeat_a == repeat_b, "Repeated Ridge seed is not deterministic")
        passed.append("Ridge seed: 0/1/2 differ; repeated 100000 is deterministic")

        ridge_off_variants = [
            hash_for(
                root,
                output,
                isolated,
                {"ridge_angle": angle, "ridge_strength": strength, "seed": seed},
                reference,
            )
            for angle, strength, seed in ((0.0, 0.0, 0), (90.0, 1.0, 2), (360.0, 0.5, 100000))
        ]
        require(len(set(ridge_off_variants)) == 1, "Disabled Ridge still consumes angle/strength/seed")
        passed.append("Ridge disabled: angle/strength/seed do not change output")

        module_cases: List[Tuple[str, str, float, float, str, float, float]] = [
            ("Macro", "enable_macro", 35.0, 80.0, "macro", 180.0, 300.0),
            ("Mid", "enable_mid", 10.0, 22.0, "mid", 50.0, 90.0),
            ("Detail", "enable_detail", 1.5, 4.0, "detail", 10.0, 20.0),
        ]
        for label, enable_name, amp_a, amp_b, prefix, size_a, size_b in module_cases:
            module = dict(isolated)
            module[enable_name] = 1
            amp_hashes = [
                hash_for(root, output, module, {f"{prefix}_amp": value}, reference)
                for value in (amp_a, amp_b)
            ]
            size_hashes = [
                hash_for(root, output, module, {f"{prefix}_size": value}, reference)
                for value in (size_a, size_b)
            ]
            require(amp_hashes[0] != amp_hashes[1], f"{label} Amp is not sensitive")
            require(size_hashes[0] != size_hashes[1], f"{label} Size is not sensitive")
            passed.append(f"{label}: Amp and Size change output")

        erosion_base = dict(isolated)
        erosion_base.update(enable_macro=1, macro_amp=80.0, macro_size=300.0)
        erosion_on = dict(erosion_base)
        erosion_on["enable_erosion"] = 1
        erosion_snapshots = []
        for value in (1, 2):
            values = dict(erosion_on)
            values["erosion_iterations"] = value
            set_values(root, values)
            erosion_snapshots.append(heightfield_snapshot(output))
        require(
            erosion_snapshots[0]["hash"] != erosion_snapshots[1]["hash"],
            "Enabled Erosion ignores Iterations",
        )
        for key in ("resolution", "layer_names", "point_count", "prim_count", "vertex_count"):
            require(
                erosion_snapshots[0][key] == erosion_snapshots[1][key],
                f"Erosion geometry structure changes with Iterations: {key}",
            )
        erosion_off_hashes = [
            hash_for(root, output, erosion_base, {"erosion_iterations": value}, reference)
            for value in (1, 2)
        ]
        require(erosion_off_hashes[0] == erosion_off_hashes[1], "Disabled Erosion consumes Iterations")
        passed.append("Erosion: enabled Iterations differ; disabled Iterations are ignored")

        macro_scale = dict(isolated)
        macro_scale.update(enable_macro=1, macro_amp=80.0)
        macro_scale_hashes = [
            hash_for(root, output, macro_scale, {"mountain_height_scale": value}, reference)
            for value in (0.5, 1.5)
        ]
        require(macro_scale_hashes[0] != macro_scale_hashes[1], "Macro ignores mountain height scale")
        ridge_scale_hashes = [
            hash_for(root, output, ridge, {"mountain_height_scale": value}, reference)
            for value in (0.5, 1.5)
        ]
        require(ridge_scale_hashes[0] == ridge_scale_hashes[1],
                "Ridge still consumes Macro mountain height scale")
        ridge_macro_hashes = [
            hash_for(
                root,
                output,
                ridge,
                {"macro_amp": amp, "macro_size": size},
                reference,
            )
            for amp, size in ((20.0, 120.0), (400.0, 900.0))
        ]
        require(ridge_macro_hashes[0] == ridge_macro_hashes[1],
                "Ridge still consumes disabled Macro amplitude/size")
        passed.append("Macro scale affects Macro only; Ridge is fully decoupled")

        material_output = root.node(
            "TerrainCore/60_MATERIAL_LAYERS/OUT_UNITY_TERRAIN_LAYERS"
        )
        require(material_output is not None, "Unity material output is missing")
        material_probe = dict(isolated)
        material_probe.update(
            enable_macro=1,
            macro_amp=40.0,
            macro_size=300.0,
            mountain_height_scale=1.0,
            enable_ridge=0,
            ridge_amp=80.0,
            ridge_size=300.0,
            ridge_strength=0.5,
            cliff_start=1.0,
            cliff_full=4.0,
        )
        set_values(root, dict(material_probe, material_layers_enabled=0))
        material_off = material_layer_snapshot(material_output)
        grass_min, grass_max = material_off["ranges"]["terrain_grass"]
        require(grass_min >= 0.99999 and grass_max <= 1.00001,
                "Material disabled state is not all grass")
        for name in ("terrain_stone", "terrain_gravel", "terrain_dirt"):
            minimum, maximum = material_off["ranges"][name]
            require(abs(minimum) <= 1e-6 and abs(maximum) <= 1e-6,
                    f"Material disabled state retains stale {name} weights")

        set_values(root, dict(material_probe, material_layers_enabled=1))
        material_on = material_layer_snapshot(material_output)
        require(material_on["layer_names"] == material_off["layer_names"],
                "Material toggle changes Unity TerrainLayer topology")
        require(material_on["hash"] != material_off["hash"],
                "Material toggle does not change Unity alphamap weights")
        require(
            max(material_on["ranges"][name][1]
                for name in ("terrain_stone", "terrain_gravel", "terrain_dirt")) > 0.01,
            "Enabled material output remains visually all grass",
        )
        passed.append(
            "Material: toggle restores visible non-grass weights with stable 4-layer topology"
        )

        # Alternating values dirty the dependency chain, producing meaningful Cook timings.
        timings: List[float] = []
        set_values(root, ridge)
        for index in range(5):
            root.parm("ridge_angle").set(35.0 + (index % 2))
            started = time.perf_counter()
            heightfield_snapshot(output)
            timings.append((time.perf_counter() - started) * 1000.0)

        return {
            "status": "PASS",
            "checks": passed,
            "cook_times_ms": timings,
            "cook_median_ms": statistics.median(timings),
            "reference_structure": reference,
        }
    finally:
        set_values(root, original)
        if probe_geo is not None:
            probe_geo.destroy()
        output.cook(force=True)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--hip", type=Path, default=DEFAULT_HIP)
    parser.add_argument("--node", default=DEFAULT_NODE)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    hip_path = args.hip.resolve()
    if not hip_path.is_file():
        print(f"ERROR: HIP not found: {hip_path}", file=sys.stderr)
        return 2

    hou.hipFile.load(str(hip_path), suppress_save_prompt=True, ignore_load_warnings=False)
    root = hou.node(args.node)
    require(root is not None, f"Terrain node not found: {args.node}")
    source = root.node(SOURCE_RELATIVE_PATH)
    require(source is not None, f"Terrain source network not found: {SOURCE_RELATIVE_PATH}")
    output = source.node(OUTPUT_NODE)
    require(output is not None, f"Output node not found: {OUTPUT_NODE}")

    result = run_validation(root, source, output)
    result["hip"] = str(hip_path)
    result["node"] = root.path()
    result["definition"] = root.type().definition().libraryFilePath()
    result["saved"] = False
    print(json.dumps(result, ensure_ascii=False, indent=2, default=list))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except ValidationFailure as exc:
        print(f"FAIL: {exc}", file=sys.stderr)
        raise SystemExit(1)
