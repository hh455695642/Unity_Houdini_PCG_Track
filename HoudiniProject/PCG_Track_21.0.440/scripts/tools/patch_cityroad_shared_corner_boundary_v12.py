"""CityRoad V12 shared five-section corner-boundary patch.

V11 replaced the four interior road cells, but the rounded union boundary
still retained sub-half-metre vertices immediately before/after the first and
fifth authored sections.  Those vertices produced three near-parallel cap
edges and were also consumed independently by curb and sidewalk builders.

This incremental patch snaps only those short endpoint clusters to the ten
authored adaptive-corner rail points, fuses the duplicates, and routes every
final-boundary consumer through the same cleaned curve.  No public HDA
parameter is changed and the existing HDA network is not rebuilt.
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
import json
import os
import shutil

try:
    import hou  # type: ignore
except ModuleNotFoundError:
    hou = None


ASSET_PATH = "/obj/CityRoad_DEV"
CORE_NAME = "CityRoadCore"
EXPECTED_TYPE = "pcgbike::CityRoad::1.0"
EXPECTED_HDA_SUFFIX = "/Assets/PCG/HDA/City/CityRoad.hda"
SNAP_NODE_NAME = "CITYROAD_SNAP_FINAL_BOUNDARY_TO_CORNER_SECTIONS_V12"
FUSE_NODE_NAME = "CITYROAD_FUSE_FINAL_BOUNDARY_CORNER_SECTIONS_V12"
MARKER = "CITYROAD_V12_SHARED_FIVE_SECTION_BOUNDARY"

BOUNDARY_CONSUMERS = (
    "ROAD_PLANAR_CLASSIFY_FROM_FINAL_BOUNDARY",
    "SIDEWALK_TOPOLOGY_VALIDATE",
    "SIDEWALK_PLANAR_ROAD_BOUNDARY_CLEAN",
    "SIDEWALK_PLANAR_CLASSIFY",
    "SIDEWALK_SITE_BOUNDARY_FROM_ROAD",
    "ROAD_UNION_BOUNDARY_WALLS",
    "ROAD_UNION_SHIFT_PIECES_FOR_TRIANGULATION",
    "CURB_SIDEWALK_BUILD_FROM_FINAL_BOUNDARY",
)


SNAP_VEX = r'''
// CITYROAD_V12_SHARED_FIVE_SECTION_BOUNDARY
// Input 0: V9 rounded final road boundary.
// Input 1: V8 adaptive corner quads (four cells / five cross-sections).
//
// V9 correctly limits the arc itself to five points, but short source-boundary
// samples can survive immediately outside its first and fifth points.  Snap
// the full one-sample-spacing cluster to the authored corner rails; the
// following Fuse SOP consolidates them into one endpoint per rail.
vector targets[];
int target_corner_ids[];
for (int primitive = 0; primitive < nprimitives(1); ++primitive)
{
    if (int(prim(1, "road_corner_topology_class", primitive)) != 2)
        continue;
    int corner_id = int(prim(1, "corner_id", primitive));
    int points[] = primpoints(1, primitive);
    foreach (int point_number; points)
    {
        vector target = point(1, "P", point_number);
        int duplicate = 0;
        foreach (vector existing; targets)
        {
            vector delta = target - existing;
            delta.y = 0.0;
            if (length2(delta) <= 1e-8)
            {
                duplicate = 1;
                break;
            }
        }
        if (!duplicate)
        {
            append(targets, target);
            append(target_corner_ids, corner_id);
        }
    }
}

float sample_spacing = max(ch("../../junction_sample_spacing"), 0.05);
float snap_radius = max(1.0, sample_spacing);
int snapped_points = 0;
int touched_targets[];
resize(touched_targets, len(targets));

for (int point_number = 0; point_number < npoints(0); ++point_number)
{
    vector position = point(0, "P", point_number);
    float nearest_distance = 1e18;
    int nearest_target = -1;
    for (int target_index = 0; target_index < len(targets); ++target_index)
    {
        vector delta = position - targets[target_index];
        delta.y = 0.0;
        float candidate = length(delta);
        if (candidate < nearest_distance)
        {
            nearest_distance = candidate;
            nearest_target = target_index;
        }
    }
    if (nearest_target < 0 || nearest_distance > snap_radius)
        continue;

    vector snapped = targets[nearest_target];
    snapped.y = position.y;
    setpointattrib(0, "P", point_number, snapped, "set");
    setpointattrib(0, "corner_section_target", point_number,
        nearest_target, "set");
    snapped_points++;
    touched_targets[nearest_target] = 1;
}

int touched_target_count = 0;
foreach (int touched; touched_targets)
    touched_target_count += touched;

// Fuse SOPs can consolidate point numbers while leaving repeated vertices in
// a closed polygon.  The curb offset code iterates vertices, so those zero-
// length edges would create invalid miters.  Rebuild every boundary primitive
// here and explicitly emit each snapped cluster once, per primitive.
int original_primitive_count = nprimitives(0);
int removed_duplicate_vertices = 0;
int rebuilt_primitive_count = 0;
for (int primitive = 0; primitive < original_primitive_count; ++primitive)
{
    int vertices[] = primvertices(0, primitive);
    vector rebuilt_positions[];
    foreach (int vertex_number; vertices)
    {
        vector position = point(0, "P", vertexpoint(0, vertex_number));
        float rebuild_nearest_distance = 1e18;
        int rebuild_nearest_target = -1;
        for (int target_index = 0; target_index < len(targets); ++target_index)
        {
            vector delta = position - targets[target_index];
            delta.y = 0.0;
            float candidate = length(delta);
            if (candidate < rebuild_nearest_distance)
            {
                rebuild_nearest_distance = candidate;
                rebuild_nearest_target = target_index;
            }
        }
        if (rebuild_nearest_target >= 0
            && rebuild_nearest_distance <= snap_radius)
        {
            float original_y = position.y;
            position = targets[rebuild_nearest_target];
            position.y = original_y;
        }
        if (len(rebuilt_positions) > 0
            && distance(position, rebuilt_positions[-1]) <= 1e-5)
        {
            removed_duplicate_vertices++;
            continue;
        }
        append(rebuilt_positions, position);
    }
    if (len(rebuilt_positions) > 2
        && distance(rebuilt_positions[0], rebuilt_positions[-1]) <= 1e-5)
    {
        resize(rebuilt_positions, len(rebuilt_positions) - 1);
        removed_duplicate_vertices++;
    }
    if (len(rebuilt_positions) < 3)
        continue;

    int rebuilt = addprim(0, "poly");
    setprimintrinsic(0, "closed", rebuilt, 1, "set");
    foreach (vector position; rebuilt_positions)
        addvertex(0, rebuilt, addpoint(0, position));

    if (hasprimattrib(0, "fuse_key"))
        setprimattrib(0, "fuse_key", rebuilt,
            int(prim(0, "fuse_key", primitive)), "set");
    if (hasprimattrib(0, "road_level"))
        setprimattrib(0, "road_level", rebuilt,
            int(prim(0, "road_level", primitive)), "set");
    if (hasprimattrib(0, "allow_junction"))
        setprimattrib(0, "allow_junction", rebuilt,
            int(prim(0, "allow_junction", primitive)), "set");
    if (hasprimattrib(0, "road_id"))
        setprimattrib(0, "road_id", rebuilt,
            int(prim(0, "road_id", primitive)), "set");
    if (hasprimattrib(0, "road_width"))
        setprimattrib(0, "road_width", rebuilt,
            float(prim(0, "road_width", primitive)), "set");
    rebuilt_primitive_count++;
}

for (int primitive = original_primitive_count - 1;
        primitive >= 0; --primitive)
    removeprim(0, primitive, 1);

setdetailattrib(0, "cityroad_shared_corner_boundary_patch", "V12", "set");
setdetailattrib(0, "corner_section_target_count", len(targets), "set");
setdetailattrib(0, "corner_section_touched_target_count",
    touched_target_count, "set");
setdetailattrib(0, "corner_section_snapped_point_count",
    snapped_points, "set");
setdetailattrib(0, "corner_section_snap_radius", snap_radius, "set");
setdetailattrib(0, "corner_section_removed_duplicate_vertices",
    removed_duplicate_vertices, "set");
setdetailattrib(0, "corner_section_rebuilt_primitive_count",
    rebuilt_primitive_count, "set");

if (len(targets) <= 0 || touched_target_count != len(targets))
    error(sprintf(
        "CityRoad V12 boundary contract failed: targets=%d touched=%d",
        len(targets), touched_target_count));
'''


def _require_node(parent, name: str):
    node = parent.node(name)
    if node is None:
        raise RuntimeError(f"Missing CityRoad node: {parent.path()}/{name}")
    return node


def _detail(geometry, name: str, default=None):
    attribute = geometry.findGlobalAttrib(name)
    return geometry.attribValue(attribute) if attribute is not None else default


def _backup_definition(definition) -> Path:
    hip_dir = Path(hou.hipFile.path()).resolve().parent
    backup_dir = hip_dir / "backups"
    backup_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    destination = backup_dir / f"CityRoad_before_shared_boundary_v12_{stamp}.hda"
    shutil.copy2(Path(definition.libraryFilePath()), destination)
    return destination


def _set_if_present(node, name: str, value) -> None:
    parm = node.parm(name)
    if parm is not None:
        parm.set(value)


def _xz_distance(a, b) -> float:
    return ((float(a[0]) - float(b[0])) ** 2
            + (float(a[2]) - float(b[2])) ** 2) ** 0.5


def _adaptive_targets(adaptive) -> list[tuple[float, float, float]]:
    targets: list[tuple[float, float, float]] = []
    geometry = adaptive.geometry()
    for primitive in geometry.prims():
        try:
            topology_class = int(
                primitive.attribValue("road_corner_topology_class"))
        except Exception:
            topology_class = -1
        if topology_class != 2:
            continue
        for point in primitive.points():
            position = point.position()
            candidate = (float(position[0]), float(position[1]), float(position[2]))
            if not any(_xz_distance(candidate, existing) <= 1e-4
                       for existing in targets):
                targets.append(candidate)
    return targets


def _parallel_cap_edge_count(road, section_position_pair) -> int:
    a, b = section_position_pair
    tx = b[0] - a[0]
    tz = b[2] - a[2]
    target_length = (tx * tx + tz * tz) ** 0.5
    if target_length <= 1e-6:
        return 0
    tx /= target_length
    tz /= target_length
    mx = (a[0] + b[0]) * 0.5
    mz = (a[2] + b[2]) * 0.5
    unique_edges: dict[tuple[int, int], tuple[object, object]] = {}
    for primitive in road.geometry().prims():
        points = list(primitive.points())
        for index in range(len(points)):
            point_a = points[index]
            point_b = points[(index + 1) % len(points)]
            key = tuple(sorted((point_a.number(), point_b.number())))
            unique_edges[key] = (point_a, point_b)
    count = 0
    for point_a, point_b in unique_edges.values():
        position_a = point_a.position()
        position_b = point_b.position()
        ex = float(position_b[0] - position_a[0])
        ez = float(position_b[2] - position_a[2])
        edge_length = (ex * ex + ez * ez) ** 0.5
        if edge_length < target_length * 0.75:
            continue
        alignment = abs((ex * tx + ez * tz) / edge_length)
        edge_mx = float(position_a[0] + position_b[0]) * 0.5
        edge_mz = float(position_a[2] + position_b[2]) * 0.5
        midpoint_distance = ((edge_mx - mx) ** 2 + (edge_mz - mz) ** 2) ** 0.5
        if alignment >= 0.98 and midpoint_distance <= 0.75:
            count += 1
    return count


def _validate(core) -> dict[str, object]:
    snap = _require_node(core, SNAP_NODE_NAME)
    fuse = _require_node(core, FUSE_NODE_NAME)
    adaptive = _require_node(core, "ROAD_BUILD_ADAPTIVE_CORNER_SURFACE")
    sections = _require_node(core, "CITYROAD_BUILD_CORNER_SECTION_CONSTRAINTS_V10")
    road = _require_node(core, "CITYROAD_REPLACE_CORNER_WITH_QUAD_STRIPS_V11")
    sidewalk = _require_node(
        core, "CITYROAD_REPLACE_SIDEWALK_CORNER_WITH_QUAD_STRIPS_V11")
    curb = _require_node(core, "CURB_SIDEWALK_BUILD_FROM_FINAL_BOUNDARY")
    outputs = [
        _require_node(core, "OUT_ROAD_SURFACE"),
        _require_node(core, "OUT_ROAD_MARKINGS"),
        _require_node(core, "OUT_SIDEWALK_CURB"),
    ]
    nodes = [snap, fuse, sections, road, sidewalk, curb] + outputs
    errors: list[str] = []
    warnings: list[str] = []
    for node in nodes:
        node.cook(force=True)
        errors.extend(node.errors())
        warnings.extend(node.warnings())
    if errors:
        raise RuntimeError("CityRoad V12 cook errors: " + " | ".join(errors))

    snap_geometry = snap.geometry()
    fused_geometry = fuse.geometry()
    targets = _adaptive_targets(adaptive)
    if len(targets) != 10:
        raise RuntimeError(f"V12 expected 10 rail targets, got {len(targets)}")
    target_occurrences = []
    for target in targets:
        count = sum(
            _xz_distance(point.position(), target) <= 0.001
            for point in fused_geometry.points())
        target_occurrences.append(count)
    if any(count != 1 for count in target_occurrences):
        raise RuntimeError(
            f"V12 fused boundary target occurrences: {target_occurrences}")

    section_pairs = []
    for primitive in sections.geometry().prims():
        points = list(primitive.points())
        if len(points) != 2:
            continue
        section_pairs.append(tuple(tuple(float(v) for v in point.position())
                                   for point in points))
    if len(section_pairs) != 5:
        raise RuntimeError(f"V12 expected 5 sections, got {len(section_pairs)}")
    endpoint_cap_counts = [
        _parallel_cap_edge_count(road, section_pairs[0]),
        _parallel_cap_edge_count(road, section_pairs[-1]),
    ]
    if endpoint_cap_counts != [1, 1]:
        raise RuntimeError(
            f"V12 endpoint cap counts are {endpoint_cap_counts}, expected [1, 1]")

    if _detail(snap_geometry, "cityroad_shared_corner_boundary_patch", "") != "V12":
        raise RuntimeError("V12 boundary marker is missing")

    return {
        "warnings": warnings,
        "targets": len(targets),
        "target_occurrences": target_occurrences,
        "snapped_points": int(_detail(
            snap_geometry, "corner_section_snapped_point_count", -1)),
        "boundary_points_before_fuse": len(snap_geometry.points()),
        "boundary_points_after_fuse": len(fused_geometry.points()),
        "road_sections": len(section_pairs),
        "road_endpoint_parallel_cap_edges": endpoint_cap_counts,
        "road_strip_triangles": int(_detail(
            road.geometry(), "corner_strip_triangle_count", -1)),
        "sidewalk_strip_triangles": int(_detail(
            sidewalk.geometry(), "sidewalk_corner_strip_triangle_count", -1)),
        "curb_primitives": len(curb.geometry().prims()),
        "output_stats": {
            node.name(): {
                "points": len(node.geometry().points()),
                "primitives": len(node.geometry().prims()),
            }
            for node in outputs
        },
    }


def apply_live_patch(save: bool = True, create_backup: bool = True,
                     hou_module=None):
    global hou
    if hou_module is not None:
        hou = hou_module
    if hou is None:
        raise RuntimeError("The hou module is unavailable")

    asset = hou.node(ASSET_PATH)
    if asset is None or asset.type().name() != EXPECTED_TYPE:
        raise RuntimeError(f"Expected live {EXPECTED_TYPE} at {ASSET_PATH}")
    definition = asset.type().definition()
    if definition is None:
        raise RuntimeError("CityRoad HDA definition is unavailable")
    library_path = definition.libraryFilePath().replace("\\", "/")
    if not library_path.endswith(EXPECTED_HDA_SUFFIX):
        raise RuntimeError(f"Unexpected CityRoad definition: {library_path}")

    interface_before = asset.parmTemplateGroup().asDialogScript()
    was_locked = asset.isLockedHDA()
    if was_locked:
        asset.allowEditingOfContents()
    core = _require_node(asset, CORE_NAME)
    boundary = _require_node(core, "ROAD_UNION_ROUND_FINAL_BOUNDARY")
    adaptive = _require_node(core, "ROAD_BUILD_ADAPTIVE_CORNER_SURFACE")

    snap = core.node(SNAP_NODE_NAME)
    fuse = core.node(FUSE_NODE_NAME)
    created_snap = snap is None
    created_fuse = fuse is None
    backup_path = _backup_definition(definition) if create_backup else None
    original_connections: list[tuple[object, int, object]] = []
    try:
        with hou.undos.group("CityRoad V12 shared five-section boundary"):
            if snap is None:
                snap = core.createNode("attribwrangle", SNAP_NODE_NAME)
            snap.setInput(0, boundary)
            snap.setInput(1, adaptive)
            snap.parm("class").set(0)
            snap.parm("snippet").set(SNAP_VEX)
            snap.setComment(
                "V12：把直角弯第1/5截面外侧的短边簇吸附到同一截面；"
                "道路、路牙、人行路面共用此最终边界。")
            snap.setColor(hou.Color((0.92, 0.36, 0.08)))
            snap.setPosition(boundary.position() + hou.Vector2((0.0, -1.5)))

            if fuse is None:
                fuse = core.createNode("fuse::2.0", FUSE_NODE_NAME)
            fuse.setInput(0, snap)
            for name, value in (
                ("usetol3d", 1), ("tol3d", 0.001),
                ("consolidatesnappedpoints", 1),
                ("keepconsolidatedpoints", 0),
                ("deldegen", 1), ("deldegenpoints", 1),
                ("delunusedpoints", 1), ("recomputenml", 0),
            ):
                _set_if_present(fuse, name, value)
            fuse.setComment(
                "V12：合并端部重复点并删除退化边；最终每条轨仅保留5个弯角点。")
            fuse.setColor(hou.Color((0.98, 0.58, 0.10)))
            fuse.setPosition(snap.position() + hou.Vector2((0.0, -1.0)))

            for consumer_name in BOUNDARY_CONSUMERS:
                consumer = _require_node(core, consumer_name)
                matched = False
                for input_index, input_node in enumerate(consumer.inputs()):
                    input_path = input_node.path() if input_node is not None else ""
                    if input_path == boundary.path():
                        original_connections.append(
                            (consumer, input_index, boundary))
                        consumer.setInput(input_index, fuse)
                        matched = True
                    elif input_path == fuse.path():
                        matched = True
                if not matched:
                    raise RuntimeError(
                        f"V12 signature mismatch: {consumer.path()} does not read "
                        "the final boundary")

            network_box = core.findNetworkBox(
                "CITYROAD_V12_SHARED_CORNER_BOUNDARY")
            if network_box is None:
                network_box = core.createNetworkBox(
                    "CITYROAD_V12_SHARED_CORNER_BOUNDARY")
            network_box.setComment(
                "V12 移动端共享角弯边界：道路/路牙/人行路面统一5截面。")
            network_box.setColor(hou.Color((0.32, 0.12, 0.04)))
            for node in (snap, fuse):
                network_box.addItem(node)
            network_box.fitAroundContents()

        if asset.parmTemplateGroup().asDialogScript() != interface_before:
            raise RuntimeError("V12 unexpectedly changed the public HDA interface")

        validation = _validate(core)
        if save:
            definition.updateFromNode(asset)
            hou.hipFile.save()
    except Exception:
        for consumer, input_index, input_node in reversed(original_connections):
            consumer.setInput(input_index, input_node)
        if created_fuse and fuse is not None:
            fuse.destroy()
        if created_snap and snap is not None:
            snap.destroy()
        raise

    return {
        "asset": asset.path(),
        "definition": library_path,
        "hip": hou.hipFile.path(),
        "backup": str(backup_path) if backup_path else None,
        "was_locked": was_locked,
        "saved": save,
        "snap_node": snap.path(),
        "fuse_node": fuse.path(),
        "marker": MARKER,
        "validation": validation,
    }


def apply_patch_via_rpc():
    """Execute this exact file inside the already-running Houdini GUI."""
    import hrpyc

    connection, _remote_hou = hrpyc.import_remote_module(
        "127.0.0.1", 18811, "hou")
    script_path = os.path.abspath(__file__).replace("\\", "/")
    remote_code = (
        "import hou\n"
        "_cityroad_v12_namespace = {'__name__': 'cityroad_v12_remote'}\n"
        "exec(compile(open(%r, encoding='utf-8').read(), %r, 'exec'), "
        "_cityroad_v12_namespace)\n"
        "CITYROAD_V12_RESULT = "
        "_cityroad_v12_namespace['apply_live_patch'](hou_module=hou)\n"
    ) % (script_path, script_path)
    connection.execute(remote_code)
    return json.loads(connection.eval(
        "__import__('json').dumps(CITYROAD_V12_RESULT, ensure_ascii=False)"))


if __name__ == "__main__":
    in_target_session = hou is not None and hou.node(ASSET_PATH) is not None
    print(apply_live_patch() if in_target_session else apply_patch_via_rpc())
