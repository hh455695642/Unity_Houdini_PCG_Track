"""Incremental CityRoad V22 short-road / zero-corner tolerance patch.

Fix for: shortening a road curve below the corner-arc threshold makes all
road markings disappear.

Root cause: when the corner-rounding stage collapses a too-short corner, the
corner-section pipeline produces ZERO corner sections, and three downstream
nodes hard-error on ``count <= 0`` instead of passing the (already valid)
straight boundary through unchanged.  Those errors cascade into the final
road surface (CR_ROAD_OUTPUT_CLASSIFY) and then into
``CITYROAD_BUILD_STATIC_MARKING_MESH`` (whose input 1 is the road surface),
so both the road surface and its markings come out empty.

This patch relaxes "zero corner sections" from a hard error to a valid
pass-through, while preserving the checks for *present-but-invalid* corners.

Edits only the three whitelisted snippet nodes under
``/obj/CityRoad_DEV/CityRoadCore``.  It does not create a new HIP, rebuild
the HDA, or change any public parameter interface.
"""

from __future__ import annotations

import argparse
import json

try:
    hou
except NameError:
    import hou


ASSET_PATH = "/obj/CityRoad_DEV"
CORE_PATH = f"{ASSET_PATH}/CityRoadCore"

MARKER = "CITYROAD_V22_ZERO_CORNER_TOLERANCE"

# (node path relative to core, old condition, new condition)
# Each edit is a pure relaxation: zero corner sections become a no-op
# pass-through; real corner corruption still errors.
EDITS = (
    (
        "CR_UNION_BOUNDARY/CITYROAD_SNAP_FINAL_BOUNDARY_TO_CORNER_SECTIONS_V12",
        "if (len(targets) <= 0 || touched_target_count != len(targets))",
        "// CITYROAD_V22_ZERO_CORNER_TOLERANCE\n"
        "if (len(targets) > 0 && touched_target_count != len(targets))",
    ),
    (
        "CITYROAD_REPLACE_CORNER_WITH_QUAD_STRIPS_V11",
        "if (adaptive_quad_count <= 0 || invalid_quad_count > 0)",
        "// CITYROAD_V22_ZERO_CORNER_TOLERANCE\n"
        "if (invalid_quad_count > 0)",
    ),
    (
        "CR_SIDEWALK_CONSTRAINT_BUILD/CITYROAD_REPLACE_SIDEWALK_CORNER_WITH_QUAD_STRIPS_V11",
        "if (sidewalk_quad_count <= 0\n"
        "    || invalid_quad_count > 0\n"
        "    || missing_connector_count > 0)",
        "// CITYROAD_V22_ZERO_CORNER_TOLERANCE\n"
        "if (invalid_quad_count > 0\n"
        "    || missing_connector_count > 0)",
    ),
)

VERIFY_NODES = (
    "OUT_ROAD_SURFACE",
    "OUT_ROAD_MARKINGS",
    "OUT_SIDEWALK_CURB",
)


def _snippet(node: hou.Node) -> str:
    parm = node.parm("snippet")
    if parm is None:
        raise RuntimeError(f"Missing snippet parm: {node.path()}")
    return parm.unexpandedString()


def apply(save: bool = False) -> dict:
    asset = hou.node(ASSET_PATH)
    if asset is None or asset.type().name() != "pcgbike::CityRoad::1.0":
        raise RuntimeError(
            f"Expected pcgbike::CityRoad::1.0 at {ASSET_PATH}")
    core = hou.node(CORE_PATH)
    if core is None:
        raise RuntimeError(f"Missing {CORE_PATH}")

    # Resolve all target nodes up front and snapshot their snippets for a
    # transactional rollback if anything fails.
    targets = []
    for rel, _old, _new in EDITS:
        node = core.node(rel)
        if node is None:
            raise RuntimeError(f"Missing target node: {CORE_PATH}/{rel}")
        targets.append((rel, node))

    snapshots = {rel: _snippet(node) for rel, node in targets}
    applied = []
    try:
        for (rel, old, new), (_, node) in zip(EDITS, targets):
            source = _snippet(node)
            if MARKER in source:
                # Idempotent: already patched.
                continue
            if old not in source:
                raise RuntimeError(
                    f"{node.path()} prerequisite changed; expected to find "
                    f"the zero-corner guard but did not. Aborting without "
                    f"changes.")
            if source.count(old) != 1:
                raise RuntimeError(
                    f"{node.path()} guard is ambiguous "
                    f"({source.count(old)} matches); aborting.")
            node.parm("snippet").set(source.replace(old, new, 1))
            applied.append(node.path())

        # Verify: the target outputs must cook without error.
        diagnostics = {}
        for name in VERIFY_NODES:
            node = core.node(name)
            if node is None:
                raise RuntimeError(f"Missing verify node: {name}")
            try:
                node.cook(force=True)
            except Exception as exc:  # pragma: no cover
                raise RuntimeError(
                    f"{name} cook failed: {exc}; "
                    f"errors={list(node.errors())}") from exc
            errs = list(node.errors())
            diagnostics[name] = {
                "errors": errs,
                "warnings": list(node.warnings()),
            }
            if errs:
                raise RuntimeError(f"{name} has errors: {errs}")

        if save:
            hou.hipFile.save()
    except Exception:
        for rel, node in targets:
            node.parm("snippet").set(snapshots[rel])
        raise

    return {
        "status": "PASS",
        "saved": bool(save),
        "marker": MARKER,
        "edited_nodes": applied,
        "hip": hou.hipFile.path(),
        "diagnostics": diagnostics,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--hip", default="", help="HIP file to load first")
    parser.add_argument("--save", action="store_true")
    args = parser.parse_args()

    if args.hip:
        hou.hipFile.load(args.hip, ignore_load_warnings=True)

    print(json.dumps(apply(save=args.save), ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
