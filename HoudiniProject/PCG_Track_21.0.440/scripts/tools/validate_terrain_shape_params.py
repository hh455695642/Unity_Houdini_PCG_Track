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
    "enable_erosion",
    "erosion_iterations",
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

    boxes = {box.name() for box in source.networkBoxes()}
    require("Directional_Ridge_Frame" in boxes, "Directional Ridge network box is missing")

    seed_conditions = root.type().definition().parmTemplateGroup().find("seed").conditionals()
    expected_seed_condition = (
        "{ enable_macro == 0 enable_mid == 0 enable_detail == 0 "
        "enable_ridge == 0 enable_erosion == 0 }"
    )
    require(
        seed_conditions.get(hou.parmCondType.DisableWhen) == expected_seed_condition,
        "Seed Disable When condition differs",
    )
    ridge_conditions = root.type().definition().parmTemplateGroup().find("ridge_angle").conditionals()
    require(
        ridge_conditions.get(hou.parmCondType.DisableWhen) == "{ enable_ridge == 0 }",
        "ridge_angle Disable When condition changed",
    )
    mountain_conditions = (
        root.type().definition().parmTemplateGroup().find("mountain_height_scale").conditionals()
    )
    require(
        mountain_conditions.get(hou.parmCondType.DisableWhen)
        == "{ enable_macro == 0 enable_ridge == 0 }",
        "mountain_height_scale Disable When condition changed",
    )
    messages.append("Topology, expressions, Sparse basis, and UI conditions")
    return messages


def run_validation(root: hou.Node, source: hou.Node, output: hou.Node) -> Dict[str, Any]:
    passed = check_topology(root, source)
    original = {name: root.parm(name).eval() for name in TOUCHED_PARAMETERS}

    # Stable values shared by sensitivity tests. Individual modules are isolated.
    isolated = {
        "seed": 1,
        "mountain_height_scale": 8.0,
        "enable_macro": 0,
        "enable_mid": 0,
        "enable_detail": 0,
        "enable_ridge": 0,
        "enable_erosion": 0,
    }

    set_values(root, isolated)
    reference = heightfield_snapshot(output)

    try:
        ridge = dict(isolated)
        ridge.update(enable_ridge=1, ridge_strength=0.5)
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
            for value in (4.0, 8.0)
        ]
        require(macro_scale_hashes[0] != macro_scale_hashes[1], "Macro ignores mountain height scale")
        ridge_scale_hashes = [
            hash_for(root, output, ridge, {"mountain_height_scale": value}, reference)
            for value in (4.0, 8.0)
        ]
        require(ridge_scale_hashes[0] != ridge_scale_hashes[1], "Ridge ignores mountain height scale")
        passed.append("mountain_height_scale affects Macro and Ridge; UI disable condition is intact")

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
