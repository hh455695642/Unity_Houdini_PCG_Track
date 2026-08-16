"""Move CityRoad longitudinal-marking validation to committed SOP geometry.

The static builder deletes uploaded source curves and adds marking primitives in
one Detail Wrangle. Reading primitive attributes again in that same Wrangle sees
the pre-commit input, so a source road can be misclassified as marking_type=0.
"""

from __future__ import annotations

import argparse
import hashlib
import json

ASSET_PATH = "/obj/CityRoad_DEV"
CORE_PATH = f"{ASSET_PATH}/CityRoadCore"
BUILDER_NAME = "CITYROAD_BUILD_STATIC_MARKING_MESH"
VALIDATOR_NAME = "CITYROAD_VALIDATE_STATIC_MARKING_JUNCTION_CLIP_V24"
MARKER = "CITYROAD_V24_POST_COMMIT_MARKING_VALIDATION"
EXPECTED_BUILDER_SHA256 = "e4fc331096b5680b09b72b9b9f6a2fa42da75b278f55b25d50c0c7dc6ed8f139"

OLD_SCAN = '''int longitudinal_intrusion_count = 0;
for (int primitive = 0; primitive < nprimitives(0); ++primitive)
{
    int marking_type = int(prim(0, "marking_type", primitive));
    if (marking_type < 0 || marking_type > 2) continue;
    int points[] = primpoints(0, primitive);
    vector center = 0;
    foreach (int point_number; points)
        center += point(0, "P", point_number);
    center /= max(1, len(points));
    int road_level = hasprimattrib(0, "road_level")
        ? int(prim(0, "road_level", primitive)) : 0;
    if (v7_inside_junction_surface(
        center, road_level, junction_surface_extension))
        longitudinal_intrusion_count++;
}
'''

OLD_RESULT = '''setdetailattrib(0, "longitudinal_marking_junction_intrusion_count",
    longitudinal_intrusion_count, "set");
setdetailattrib(0, "marking_boundary_gap_max", 0.0, "set");
setdetailattrib(0, "junction_surface_extension", junction_surface_extension, "set");
if (longitudinal_intrusion_count != 0)
    error(sprintf(
        "CityRoad V7 longitudinal marking intrusion count=%d",
        longitudinal_intrusion_count));
'''

NEW_RESULT = '''setdetailattrib(0, "marking_boundary_gap_max", 0.0, "set");
setdetailattrib(0, "junction_surface_extension", junction_surface_extension, "set");
'''

VALIDATOR_SNIPPET = r'''// CITYROAD_V24_POST_COMMIT_MARKING_VALIDATION
// Input 0 is committed static-marking geometry. Inputs 1/2 are junction
// boundaries and approach metadata used by the original V7 extent contract.
function int v24_inside_polygon(int geometry; vector query; int primitive)
{
    int points[] = primpoints(geometry, primitive);
    int inside = 0;
    for (int i = 0, j = len(points) - 1; i < len(points); j = i++)
    {
        vector a = point(geometry, "P", points[i]);
        vector b = point(geometry, "P", points[j]);
        if ((a.z > query.z) == (b.z > query.z)) continue;
        float x_hit = (b.x - a.x) * (query.z - a.z)
            / (b.z - a.z + 1e-20) + a.x;
        if (query.x < x_hit) inside = !inside;
    }
    return inside;
}

function int v24_inside_junction_surface(
    vector query; int road_level; float extension)
{
    int boundaries[] = expandprimgroup(1, "junction_boundary");
    foreach (int primitive; boundaries)
    {
        if (int(prim(1, "road_level", primitive)) != road_level) continue;
        if (v24_inside_polygon(1, query, primitive)) return 1;
    }

    int approaches[] = expandpointgroup(2, "junction_approaches");
    foreach (int approach_point; approaches)
    {
        if (int(point(2, "road_level", approach_point)) != road_level) continue;
        vector outward = point(2, "approach_direction", approach_point);
        outward = normalize(set(outward.x, 0.0, outward.z));
        vector mouth_left = point(2, "approach_mouth_left", approach_point);
        vector mouth_right = point(2, "approach_mouth_right", approach_point);
        vector lateral = mouth_right - mouth_left;
        float span = length(set(lateral.x, 0.0, lateral.z));
        if (length2(outward) < 1e-8 || span < 1e-5) continue;
        vector side = normalize(set(lateral.x, 0.0, lateral.z));
        float along = dot(query - mouth_left, outward);
        float across = dot(query - mouth_left, side);
        if (along >= -1e-4 && along <= extension + 1e-4
            && across >= -1e-4 && across <= span + 1e-4)
            return 1;
    }
    return 0;
}

if (!hasprimattrib(0, "marking_type"))
    error("CityRoad V24 committed marking geometry has no marking_type attribute");

float extension = float(detail(0, "junction_surface_extension", 0));
int longitudinal_intrusion_count = 0;
int longitudinal_primitive_count = 0;
for (int primitive = 0; primitive < nprimitives(0); ++primitive)
{
    int marking_type = int(prim(0, "marking_type", primitive));
    if (marking_type < 0 || marking_type > 2) continue;
    longitudinal_primitive_count++;
    int points[] = primpoints(0, primitive);
    vector center = 0;
    foreach (int point_number; points)
        center += point(0, "P", point_number);
    center /= max(1, len(points));
    int road_level = hasprimattrib(0, "road_level")
        ? int(prim(0, "road_level", primitive)) : 0;
    if (v24_inside_junction_surface(center, road_level, extension))
        longitudinal_intrusion_count++;
}

setdetailattrib(0, "longitudinal_marking_primitive_count",
    longitudinal_primitive_count, "set");
setdetailattrib(0, "longitudinal_marking_junction_intrusion_count",
    longitudinal_intrusion_count, "set");
setdetailattrib(0, "marking_validation_stage", "post_commit_v24", "set");
if (longitudinal_intrusion_count != 0)
    error(sprintf(
        "CityRoad V24 committed longitudinal marking intrusion count=%d",
        longitudinal_intrusion_count));
'''


def snippet(node: hou.Node) -> str:
    parm = node.parm("snippet")
    if parm is None:
        raise RuntimeError(f"Missing snippet parm: {node.path()}")
    return parm.unexpandedString()


def apply(save: bool = False, hou_module=None) -> dict:
    if hou_module is None:
        import hou as hou_module
    h = hou_module
    asset = h.node(ASSET_PATH)
    if asset is None or asset.type().name() != "pcgbike::CityRoad::1.0":
        raise RuntimeError(f"Expected pcgbike::CityRoad::1.0 at {ASSET_PATH}")
    core = h.node(CORE_PATH)
    builder = core.node(BUILDER_NAME)
    approach = core.node("CR_MARKING_APPROACH")
    final = core.node("CR_MARKING_FINAL")
    junction = core.node("CR_JUNCTION_INDEX")
    helpers = core.node("CR_MARKING_HELPERS")
    required = (builder, approach, final, junction, helpers)
    if any(node is None for node in required):
        raise RuntimeError("CityRoad V24 prerequisite node is missing")

    original_source = snippet(builder)
    existing = core.node(VALIDATOR_NAME)
    if existing is None:
        digest = hashlib.sha256(original_source.encode("utf-8")).hexdigest()
        if digest != EXPECTED_BUILDER_SHA256:
            raise RuntimeError(
                f"Static marking prerequisite hash changed: {digest}; aborting")
        if original_source.count(OLD_SCAN) != 1 or original_source.count(OLD_RESULT) != 1:
            raise RuntimeError("Static marking validation block changed or is ambiguous")
    elif MARKER not in snippet(existing):
        raise RuntimeError(f"Existing {VALIDATOR_NAME} does not carry the V24 marker")

    original_inputs = {
        approach: approach.inputConnections(),
        final: final.inputConnections(),
    }
    validator = existing
    created = False
    try:
        if validator is None:
            builder.parm("snippet").set(
                original_source.replace(
                    OLD_SCAN, f"// {MARKER}: validation runs downstream.\n", 1
                ).replace(OLD_RESULT, NEW_RESULT, 1))
            validator = core.createNode("attribwrangle", VALIDATOR_NAME)
            created = True
            validator.parm("class").set(0)
            validator.parm("snippet").set(VALIDATOR_SNIPPET)
            validator.setComment(
                "V24: validate committed marking primitives after Detail Wrangle writes/deletes apply.")
            validator.setPosition(h.Vector2(36.0, -27.0))
            validator.setInput(0, builder, 0)
            validator.setInput(1, junction, 3)
            validator.setInput(2, helpers, 0)
            box = next((item for item in core.networkBoxes()
                        if item.name() == "AREA_MARKING_STREET"), None)
            if box is None:
                raise RuntimeError("Missing AREA_MARKING_STREET network box")
            box.addItem(validator)

        approach.setInput(1, validator, 0)
        final.setInput(0, validator, 0)
        validator.cook(force=True)
        if validator.errors():
            raise RuntimeError(f"V24 validator cook failed: {validator.errors()}")
        output = core.node("OUT_ROAD_MARKINGS")
        output.cook(force=True)
        if output.errors():
            raise RuntimeError(f"Road marking output failed: {output.errors()}")
        if save:
            raise RuntimeError("V24 patch is save=False only; use the regression gate to persist")
    except Exception:
        builder.parm("snippet").set(original_source)
        for target, connections in original_inputs.items():
            target.setInput(0, None)
            target.setInput(1, None)
            target.setInput(2, None)
            target.setInput(3, None)
            for connection in connections:
                target.setInput(
                    connection.inputIndex(), connection.inputNode(), connection.outputIndex())
        if created and validator is not None:
            validator.destroy()
        raise

    return {
        "status": "PASS",
        "saved": False,
        "marker": MARKER,
        "validator": validator.path(),
        "marking_primitives": len(core.node("OUT_ROAD_MARKINGS").geometry().prims()),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--save", action="store_true")
    args = parser.parse_args()
    print(json.dumps(apply(save=args.save), ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
