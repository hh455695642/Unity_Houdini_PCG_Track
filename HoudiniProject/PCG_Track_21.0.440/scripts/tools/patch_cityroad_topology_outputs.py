"""Incrementally replace CityRoad spatial chunks with topology pieces.

This patch is intentionally scoped to the currently opened CityRoad HDA.  It
does not clear the HIP, recreate the asset, or touch the Houdini Engine Unity
plugin.  Run it only through the live Houdini MCP session after preflight.
"""

from __future__ import annotations

import datetime as _datetime
import json
import os
import shutil
import textwrap

try:
    import hou
except ModuleNotFoundError:
    # Houdini MCP injects the remote hou proxy into the execution globals.
    # The caller exposes that proxy through builtins for imported modules.
    import builtins as _builtins
    hou = _builtins._houdini_mcp_hou

from patch_cityroad_crossroad_v3 import (
    BOUNDARY_METADATA_VEX,
    BOUNDARY_ROADSIDE_CLASSIFY_VEX,
    OUTER_EDGE_EXTRACT_VEX,
)


EXPECTED_LIBRARY_SUFFIX = "Assets/PCG/HDA/City/CityRoad.hda"
EXPECTED_HIP_SUFFIX = "HoudiniProject/PCG_Track_21.0.440/PCG_Bike_CityRoad.hip"
EXPECTED_TYPE = "pcgbike::CityRoad::1.0"


ROAD_TOPOLOGY_VEX = r"""
// One mesh per logical road corridor (stable road_id after graph junction
// splitting); one mesh per junction_id. Input 1 is the classified road graph.
// Boolean output intentionally keeps non-shared points, so triangle
// connectivity is not a valid piece boundary.
int primitive_count = nprimitives(0);
string corridor_keys[];
string junction_keys[];
function int csv_has_id(const string csv; const int value)
{
    string padded = "," + csv + ",";
    return find(padded, "," + itoa(value) + ",") >= 0;
}
function float cross2(const vector a; const vector b; const vector c)
{
    return (b.x-a.x)*(c.z-a.z) - (b.z-a.z)*(c.x-a.x);
}
function int inside_triangle_xz(const vector q; const vector a;
                               const vector b; const vector c)
{
    float e0 = cross2(a,b,q);
    float e1 = cross2(b,c,q);
    float e2 = cross2(c,a,q);
    int has_neg = e0 < -1e-5 || e1 < -1e-5 || e2 < -1e-5;
    int has_pos = e0 >  1e-5 || e1 >  1e-5 || e2 >  1e-5;
    return !(has_neg && has_pos);
}
function float segment_distance_xz(const vector q; const vector a;
                                   const vector b)
{
    vector aq = set(q.x-a.x, 0, q.z-a.z);
    vector ab = set(b.x-a.x, 0, b.z-a.z);
    float denominator = max(dot(ab, ab), 1e-12);
    float t = clamp(dot(aq, ab) / denominator, 0.0, 1.0);
    return distance(set(q.x, 0, q.z),
                    set(a.x, 0, a.z) + t*ab);
}

for (int pr = 0; pr < primitive_count; ++pr)
{
    vector q = primuv(0, "P", pr, set(0.333333, 0.333333, 0));
    int primitive_points[] = primpoints(0, pr);
    int level = int(prim(0, "road_level", pr));
    string junction_memberships = prim(0, "junction_ids_csv", pr);
    int nearest_junction_point = -1;
    float nearest_distance = 1e18;
    for (int point_number = 0; point_number < npoints(1); ++point_number)
    {
        int candidate_junction_id = int(point(1, "junction_id", point_number));
        int same_level = int(point(1, "road_level", point_number)) == level;
        int membership_match = csv_has_id(
            junction_memberships, candidate_junction_id);
        if (int(point(1, "connected_road_count", point_number)) < 3 ||
            !(same_level || membership_match))
            continue;
        vector center = point(1, "P", point_number);
        float distance_xz = 1e18;
        if (len(primitive_points) == 3)
        {
            vector a = point(0, "P", primitive_points[0]);
            vector b = point(0, "P", primitive_points[1]);
            vector c = point(0, "P", primitive_points[2]);
            if (inside_triangle_xz(center, a, b, c))
                distance_xz = 0.0;
        }
        if (distance_xz > 0.0)
        {
            for (int edge = 0; edge < len(primitive_points); ++edge)
            {
                vector a = point(0, "P", primitive_points[edge]);
                vector b = point(0, "P",
                    primitive_points[(edge+1) % len(primitive_points)]);
                distance_xz = min(distance_xz,
                    segment_distance_xz(center, a, b));
            }
        }
        if (distance_xz < nearest_distance)
        {
            nearest_distance = distance_xz;
            nearest_junction_point = point_number;
        }
    }
    float ownership_radius = float(prim(0, "road_width", pr))
        + ch("../junction_corner_radius")
        + ch("../junction_sample_spacing");
    int is_junction = nearest_junction_point >= 0 &&
        nearest_distance <= ownership_radius;
    int road = int(prim(0, "road_id", pr));
    int junction = is_junction
        ? int(point(1, "junction_id", nearest_junction_point)) : -1;
    if (is_junction && junction < 0)
        is_junction = 0;
    string kind_name = is_junction ? "Junction" : "Corridor";
    int stable_id = is_junction ? junction : road;
    string stable_key = sprintf("%s:L%d:%d", kind_name, level, stable_id);
    if (is_junction)
    {
        if (find(junction_keys, stable_key) < 0)
            append(junction_keys, stable_key);
    }
    else if (find(corridor_keys, stable_key) < 0)
        append(corridor_keys, stable_key);
    string piece_name = sprintf("CityRoad_%s_L%d_%04d_RoadSurface",
        kind_name, level, stable_id);
    setprimattrib(0, "name", pr, piece_name, "set");
    // Houdini Engine Unity reads instance_prefix for generated packed-instance
    // GameObject names; name alone only controls the Houdini pack partition.
    setprimattrib(0, "instance_prefix", pr, piece_name, "set");
    setprimattrib(0, "topology_piece_kind", pr,
        tolower(kind_name), "set");
    setprimattrib(0, "topology_piece_id", pr, stable_id, "set");
    setprimattrib(0, "junction_id", pr, junction, "set");
    setprimgroup(0, is_junction
        ? "cityroad_junction_piece" : "cityroad_corridor_piece", pr, 1, "set");
}

setdetailattrib(0, "cityroad_topology_piece_count",
    len(corridor_keys) + len(junction_keys), "set");
setdetailattrib(0, "cityroad_corridor_count", len(corridor_keys), "set");
setdetailattrib(0, "cityroad_junction_piece_count", len(junction_keys), "set");
"""


TRANSFER_TOPOLOGY_VEX = r"""
// Transfer the nearest accepted road topology piece to this output role.
string role = "__ROLE__";
int points[] = primpoints(0, @primnum);
vector q = 0;
foreach (int point_number; points)
    q += point(0, "P", point_number);
q /= max(len(points), 1);
int source = -1;
vector uv = 0;
xyzdist(1, q, source, uv);
if (source < 0)
    error(sprintf("CityRoad %s primitive %d has no road topology owner.",
        role, @primnum));
string road_name = prim(1, "name", source);
if (len(road_name) == 0)
    error(sprintf("CityRoad %s primitive %d resolved an unnamed road owner.",
        role, @primnum));
s@name = replace(road_name, "RoadSurface", role);
s@instance_prefix = s@name;
s@topology_piece_kind = prim(1, "topology_piece_kind", source);
i@topology_piece_id = int(prim(1, "topology_piece_id", source));
i@junction_id = int(prim(1, "junction_id", source));
"""


COLLISION_GROUP_VEX = r"""
// Houdini Engine Unity contract: collision_geo creates collider-only output.
for (int pr = 0; pr < nprimitives(0); ++pr)
    setprimgroup(0, "collision_geo", pr, 1, "set");
removeprimattrib(0, "unity_material");
setdetailattrib(0, "cityroad_collision_renderer_count", 0, "set");
setdetailattrib(0, "cityroad_collision_contract", "collision_geo", "set");
"""


CORNER_COUNT_VEX = r"""
// Accepted CityRoad convention: T-junction keeps the straight side continuous
// and rounds two curb returns; a cross rounds all four. Higher-degree
// junctions round one return per approach.
int expected = 0;
for (int point_number = 0; point_number < npoints(1); ++point_number)
{
    int degree = int(point(1, "connected_road_count", point_number));
    if (degree == 3) expected += 2;
    else if (degree >= 4) expected += degree;
}
int selected[] = expandpointgroup(0, "tutorial_roundable");
int actual = len(selected);
setdetailattrib(0, "junction_expected_curb_return_count", expected, "set");
setdetailattrib(0, "junction_actual_curb_return_count", actual, "set");
setdetailattrib(0, "junction_curb_return_validation_pass",
    int(expected == actual), "set");
if (expected != actual)
    error(sprintf(
        "CityRoad curb-return validation failed: expected %d, selected %d. "
        "Bake is blocked instead of emitting a square junction.",
        expected, actual));
"""


def _set(node: hou.Node, name: str, value) -> None:
    parm = node.parm(name)
    if parm is not None:
        parm.set(value)


def _require(parent: hou.Node, name: str) -> hou.Node:
    node = parent.node(name)
    if node is None:
        raise hou.Error(f"Required CityRoad node is missing: {parent.path()}/{name}")
    return node


def _upsert(parent: hou.Node, type_name: str, name: str) -> hou.Node:
    node = parent.node(name)
    if node is None:
        return parent.createNode(type_name, name)
    if node.type().name() != type_name:
        raise hou.Error(
            f"{node.path()} is {node.type().name()}, expected {type_name}")
    return node


def _wrangle(
    parent: hou.Node,
    name: str,
    snippet: str,
    run_over: int,
    comment: str,
) -> hou.Node:
    node = _upsert(parent, "attribwrangle", name)
    _set(node, "class", run_over)
    _set(node, "snippet", textwrap.dedent(snippet).strip())
    node.setComment(comment)
    return node


def _pack(parent: hou.Node, name: str, source: hou.Node, comment: str) -> hou.Node:
    node = _upsert(parent, "pack", name)
    node.setInput(0, source)
    _set(node, "packbyname", 1)
    _set(node, "nameattribute", "name")
    _set(node, "packedfragments", 0)
    _set(node, "pivot", "centroid")
    _set(
        node,
        "transfer_attributes",
        "name instance_prefix topology_piece_kind topology_piece_id junction_id road_level unity_material",
    )
    node.setComment(comment)
    return node


def _resolve_asset() -> hou.Node:
    selected = []
    for node in hou.selectedNodes():
        current = node
        while current is not None and current.parent() is not None:
            if current.type().name() == EXPECTED_TYPE:
                selected.append(current)
                break
            current = current.parent()
    selected = list(dict.fromkeys(selected))
    if len(selected) > 1:
        raise hou.Error(
            "Multiple selected CityRoad HDA candidates: "
            + ", ".join(node.path() for node in selected))
    if len(selected) == 1:
        return selected[0]

    candidates = [
        node for node in hou.node("/obj").children()
        if node.type().name() == EXPECTED_TYPE
    ]
    if len(candidates) != 1:
        raise hou.Error(
            "Expected exactly one loaded CityRoad HDA candidate; found: "
            + ", ".join(node.path() for node in candidates))
    return candidates[0]


def _remove_chunk_interface(definition: hou.HDADefinition) -> list[str]:
    group = definition.parmTemplateGroup()
    removed = []
    for name in ("enable_chunking", "chunk_size", "chunk_origin"):
        if group.find(name) is not None:
            group.remove(name)
            removed.append(name)
    if removed:
        definition.setParmTemplateGroup(group)
    return removed


def _set_material_parameter_defaults(
    definition: hou.HDADefinition,
) -> dict[str, str]:
    material_defaults = {
        "road_unity_material":
            "Assets/PCG/Materials/M_PCG_CityRoad_Asphalt.mat",
        "sidewalk_unity_material":
            "Assets/PCG/Materials/M_PCG_CityRoad_Sidewalk.mat",
        "curb_unity_material":
            "Assets/PCG/Materials/M_PCG_CityRoad_Curb.mat",
        "marking_unity_material":
            "Assets/PCG/Materials/M_PCG_CityRoad_Marking.mat",
    }
    group = definition.parmTemplateGroup()
    for name, value in material_defaults.items():
        template = group.find(name)
        if template is None:
            raise hou.Error(f"Required material parameter is missing: {name}")
        template.setDefaultValue((value,))
        group.replace(name, template)
    definition.setParmTemplateGroup(group)
    return material_defaults


def _remove_chunk_network_items(core: hou.Node) -> dict:
    removed_nodes = []
    for node in tuple(core.children()):
        if node.name().startswith("CITYROAD_CHUNK_"):
            removed_nodes.append(node.name())
            node.destroy()

    removed_boxes = []
    for box in tuple(core.networkBoxes()):
        if box.name() == "ORG_14_CITYROAD_CHUNK_OUTPUT":
            removed_boxes.append(box.name())
            box.destroy()

    removed_notes = []
    for note in tuple(core.stickyNotes()):
        if note.name() == "NOTE_CITYROAD_CHUNK_OUTPUT":
            removed_notes.append(note.name())
            note.destroy()
    return {
        "nodes": removed_nodes,
        "network_boxes": removed_boxes,
        "sticky_notes": removed_notes,
    }


def _patch_corner_contract(core: hou.Node) -> dict:
    graph = _require(core, "GRAPH_CLASSIFY_JUNCTIONS")
    final_road = _require(core, "TUTORIAL_V3_VALIDATE_FINAL_ROAD_RESIDUAL_OVERLAP")
    outlines = _require(core, "TUTORIAL_V2_ROAD_SORT_ORDER")

    corner_stats = _require(core, "TUTORIAL_V3_FINALIZE_CORNER_STATS")
    _set(corner_stats, "class", 0)
    _set(corner_stats, "snippet", textwrap.dedent(CORNER_COUNT_VEX).strip())
    corner_stats.setInput(1, graph)
    corner_stats.setComment(
        "倒角硬校验：T 路口 2 个 curb return；十字路口 4 个。数量不一致时阻止 Bake。"
    )

    outer_edges = _wrangle(
        core,
        "TUTORIAL_V3_POSTROAD_EXTRACT_TRUE_OUTER_EDGES",
        OUTER_EDGE_EXTRACT_VEX,
        0,
        "从最终圆角路面提取同层真实外边；内部接缝不进入 curb/sidewalk。",
    )
    outer_edges.setInput(0, final_road)

    fuse = _upsert(core, "fuse::2.0", "TUTORIAL_V3_POSTROAD_OUTER_EDGE_FUSE")
    fuse.setInput(0, outer_edges)
    for name, value in (
        ("usetol3d", 1),
        ("tol3d", 0.0005),
        ("usematchattrib", 1),
        ("matchattrib", "road_level"),
        ("consolidatesnappedpoints", 1),
    ):
        _set(fuse, name, value)
    fuse.setComment("0.5 mm 同层 Fuse，消除 Boolean 非共享外边端点。")

    path = _upsert(core, "polypath", "TUTORIAL_V3_POSTROAD_OUTER_POLYPATH")
    path.setInput(0, fuse)
    for name, value in (
        ("connectends", 1),
        ("maxendptdist", 0.001),
        ("connectonlytoends", 1),
        ("closeloops", 1),
    ):
        _set(path, name, value)
    path.setComment("1 mm 内只连接真实端点，形成可供 PolyExpand2D 使用的闭环。")

    metadata = _wrangle(
        core,
        "TUTORIAL_V3_POSTROAD_BOUNDARY_METADATA",
        BOUNDARY_METADATA_VEX,
        0,
        "按 road_level 与闭环写入稳定 boundary_loop_id/half width。",
    )
    metadata.setInput(0, path)
    metadata.setInput(1, final_road)

    validate = _require(core, "TUTORIAL_V3_BOUNDARY_VALIDATE")
    validate.setInput(0, metadata)
    validate.setInput(1, metadata)
    validate.setInput(2, final_road)

    classify = _require(core, "TUTORIAL_V3_BOUNDARY_CLASSIFY_ROAD_SIDE")
    _set(classify, "snippet", BOUNDARY_ROADSIDE_CLASSIFY_VEX)
    classify.setInput(0, validate)
    classify.setInput(1, final_road)
    classify.setInput(2, outlines)

    away = _require(core, "TUTORIAL_V3_BOUNDARY_ORIENT_AWAY_FROM_ROAD")
    away.setInput(0, classify)
    orient = _require(core, "TUTORIAL_V3_BOUNDARY_ORIENT_SAFE")
    orient.setInput(0, classify)
    orient.setInput(1, away)
    _set(orient, "input", 1)

    boundary = _require(core, "TUTORIAL_V3_TRUE_OUTER_BOUNDARY")
    boundary.setInput(0, orient)
    boundary.setComment(
        "唯一生产边界：直接来自最终圆角 road top；道路始终在有向边右侧。"
    )

    for name, input_index in (
        ("TUTORIAL_V2_CURVE_PIECE_SAFE", 0),
        ("TUTORIAL_V2_CURB_PIECE_SAFE", 0),
        ("TUTORIAL_V2_CURVE_PIECE_END", 1),
        ("TUTORIAL_V2_CURVE_PIECE_BEGIN", 0),
        ("TUTORIAL_V2_CURB_PIECE_END", 1),
        ("TUTORIAL_V2_CURB_PIECE_BEGIN", 0),
        ("TUTORIAL_V2_CURB_SIDEWALK_STATS", 3),
        ("TUTORIAL_V2_ROAD_BOUNDARY_WALLS", 0),
        ("TUTORIAL_V2_CURB_RESTORE_HEIGHT_METADATA", 1),
        ("TUTORIAL_V2_SIDEWALK_RESTORE_HEIGHT_METADATA", 1),
    ):
        _require(core, name).setInput(input_index, boundary)

    return {
        "corner_stats": corner_stats.path(),
        "final_boundary": boundary.path(),
        "postroad_nodes": [
            outer_edges.path(), fuse.path(), path.path(), metadata.path()
        ],
    }


def _patch_topology_outputs(core: hou.Node) -> dict:
    classify = _require(core, "GRAPH_CLASSIFY_JUNCTIONS")
    contracts = {
        "RoadSurface": _require(core, "OUTPUT_CONTRACT_ROAD_SURFACE"),
        "SidewalkCurb": _require(core, "OUTPUT_CONTRACT_SIDEWALK"),
        "RoadCollision": _require(core, "OUTPUT_CONTRACT_COLLISION"),
        "RoadMarkings": _require(core, "CITYROAD_MARKING_OUTPUT_CONTRACT"),
    }

    road = _wrangle(
        core,
        "CITYROAD_TOPOLOGY_CLASSIFY_ROAD",
        ROAD_TOPOLOGY_VEX,
        0,
        "按最终连通性拆分：junction/crossroad 区域独立；其余为路口之间的最大 corridor。",
    )
    road.setInput(0, contracts["RoadSurface"])
    road.setInput(1, classify)
    road_pack = _pack(
        core,
        "CITYROAD_TOPOLOGY_PACK_ROAD",
        road,
        "按稳定 Corridor/Junction name 打包；不再按 XZ 网格切割。",
    )
    _require(core, "OUT_ROAD_SURFACE").setInput(0, road_pack)

    result = {"RoadSurface": [road.path(), road_pack.path()]}
    output_names = {
        "SidewalkCurb": "OUT_SIDEWALK_CURB",
        "RoadCollision": "OUT_ROAD_COLLISION",
        "RoadMarkings": "OUT_ROAD_MARKINGS",
    }
    for role in ("SidewalkCurb", "RoadCollision", "RoadMarkings"):
        transfer = _wrangle(
            core,
            f"CITYROAD_TOPOLOGY_TRANSFER_{role.upper()}",
            TRANSFER_TOPOLOGY_VEX.replace("__ROLE__", role),
            1,
            f"{role} 就近继承 RoadSurface 的 Corridor/Junction 拓扑归属。",
        )
        transfer.setInput(0, contracts[role])
        transfer.setInput(1, road)
        packed = _pack(
            core,
            f"CITYROAD_TOPOLOGY_PACK_{role.upper()}",
            transfer,
            f"{role} 与路面使用相同拓扑 piece；禁止空间网格切片。",
        )
        final_node = packed
        if role == "RoadCollision":
            collision_group = _wrangle(
                core,
                "CITYROAD_TOPOLOGY_COLLISION_GEO",
                COLLISION_GROUP_VEX,
                0,
                "写 collision_geo：Unity 仅生成非凸静态 MeshCollider，不生成 Renderer。",
            )
            # collision_geo must be authored on the real polygon part. When
            # placed on packed primitives Houdini Engine Unity treats the
            # output as renderable instancing and creates the duplicate mesh.
            collision_group.setInput(0, transfer)
            final_node = collision_group
            packed.destroy()
        _require(core, output_names[role]).setInput(0, final_node)
        result[role] = (
            [transfer.path(), final_node.path()]
            if role == "RoadCollision"
            else [transfer.path(), packed.path(), final_node.path()]
        )
    return result


def _backup_definition(definition: hou.HDADefinition) -> str:
    library = definition.libraryFilePath()
    directory = os.path.join(os.path.dirname(library), "backup")
    os.makedirs(directory, exist_ok=True)
    stamp = _datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    destination = os.path.join(directory, f"CityRoad_before_topology_{stamp}.hda")
    shutil.copy2(library, destination)
    return destination.replace("\\", "/")


def patch_live() -> dict:
    asset = _resolve_asset()
    definition = asset.type().definition()
    if definition is None:
        raise hou.Error("CityRoad HDA definition was not found")
    library = definition.libraryFilePath().replace("\\", "/")
    hip = hou.hipFile.path().replace("\\", "/")
    if not library.endswith(EXPECTED_LIBRARY_SUFFIX):
        raise hou.Error(f"Refusing unexpected HDA definition: {library}")
    if not hip.endswith(EXPECTED_HIP_SUFFIX):
        raise hou.Error(f"Refusing unexpected HIP: {hip}")

    core = _require(asset, "CityRoadCore")
    before = {
        "hip": hip,
        "asset": asset.path(),
        "type": asset.type().nameWithCategory(),
        "definition": library,
        "locked": asset.isLockedHDA(),
        "node_count": len(core.children()),
        "output_inputs": {
            name: [node.path() if node else None for node in _require(core, name).inputs()]
            for name in (
                "OUT_ROAD_SURFACE", "OUT_SIDEWALK_CURB",
                "OUT_ROAD_COLLISION", "OUT_ROAD_MARKINGS"
            )
        },
    }

    hou.hipFile.save()
    backup = _backup_definition(definition)
    allowed_editing = False
    if asset.isLockedHDA():
        asset.allowEditingOfContents()
        allowed_editing = True

    # Keep the accepted V3 rounding chain intact.  It already validates ten
    # curb returns in the current 3xT + 1xCross test network; rebuilding its
    # boundary from post-Boolean edges creates fragmented open paths.
    corner = {
        "preserved_node": _require(
            core, "TUTORIAL_V3_FINALIZE_CORNER_STATS").path(),
        "postroad_boundary_rebuild": False,
    }
    topology = _patch_topology_outputs(core)
    removed_network = _remove_chunk_network_items(core)

    outputs = [
        _require(core, "OUT_ROAD_SURFACE"),
        _require(core, "OUT_SIDEWALK_CURB"),
        _require(core, "OUT_ROAD_COLLISION"),
        _require(core, "OUT_ROAD_MARKINGS"),
    ]
    for output in outputs:
        output.cook(force=True)
    output_errors = {
        output.name(): list(output.errors()) for output in outputs
        if output.errors()
    }
    if output_errors:
        raise hou.Error(
            "CityRoad topology patch cook failed; definition was not updated: "
            + json.dumps(output_errors, ensure_ascii=False))

    road_geometry = _require(core, "CITYROAD_TOPOLOGY_CLASSIFY_ROAD").geometry()
    expected = int(_require(core, "TUTORIAL_V3_FINALIZE_CORNER_STATS").geometry()
                   .attribValue("junction_expected_curb_return_count"))
    actual = int(_require(core, "TUTORIAL_V3_FINALIZE_CORNER_STATS").geometry()
                 .attribValue("junction_actual_curb_return_count"))
    corridor_count = int(road_geometry.attribValue("cityroad_corridor_count"))
    junction_count = int(road_geometry.attribValue("cityroad_junction_piece_count"))
    if expected != actual:
        raise hou.Error(
            f"Curb-return validation failed: expected={expected}, actual={actual}")
    if corridor_count <= 0 or junction_count <= 0:
        raise hou.Error(
            "Topology validation failed: "
            f"corridors={corridor_count}, junctions={junction_count}")

    definition.updateFromNode(asset)
    removed_parameters = _remove_chunk_interface(definition)
    material_defaults = _set_material_parameter_defaults(definition)
    asset.matchCurrentDefinition()
    hou.hipFile.save()
    result = {
        "before": before,
        "backup": backup,
        "allowed_editing_of_contents": allowed_editing,
        "removed_parameters": removed_parameters,
        "material_parameter_defaults": material_defaults,
        "removed_chunk_network": removed_network,
        "corner_patch": corner,
        "topology_nodes": topology,
        "corridor_count": corridor_count,
        "junction_piece_count": junction_count,
        "expected_curb_returns": expected,
        "actual_curb_returns": actual,
        "output_errors": output_errors,
        "saved_hda": definition.libraryFilePath().replace("\\", "/"),
        "saved_hip": hou.hipFile.path().replace("\\", "/"),
    }
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return result


if __name__ == "__main__":
    patch_live()
