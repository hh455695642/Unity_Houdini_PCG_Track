"""Visually organize the live /obj/Track1/Road network without changing SOP behavior."""

from __future__ import annotations

import json
import os
from datetime import datetime

import hrpyc


PROJECT_ROOT = "E:/HoudiniProject/Unity_Houdini_PCG_Track"
TRACK_PATH = "/obj/Track1"
HDA_PATH = PROJECT_ROOT + "/Assets/PCG/HDA/Track.hda"
BACKUP_DIR = PROJECT_ROOT + "/Assets/PCG/HDA/backup"
RECOVERY_DIR = PROJECT_ROOT + "/HoudiniProject/PCG_Track_21.0.440/recovery"


POSITIONS = {
    # 01 Centerline
    "IN_Unity_Curve_Parameter_Input": (0.0, 14.0),
    "CENTERLINE_validate_or_fallback": (0.0, 12.0),
    "CENTERLINE_reverse_curve": (4.0, 10.0),
    "CENTERLINE_reverse_switch": (0.0, 8.0),
    "FRAME_decode_unity_rotation": (0.0, 6.0),
    "CENTERLINE_resample": (0.0, 4.0),
    "CENTERLINE_polyframe": (0.0, 0.0),
    # 02 Profile / Sweep
    "PROFILE_compute_dimensions": (4.0, 1.0),
    "PROFILE_clear_centerline": (4.0, 0.0),
    "PROFILE_build_polyline": (4.0, -1.0),
    "PROFILE_assign_attributes": (4.0, -2.0),
    "PROFILE_cross_section": (4.0, -3.0),
    "SWEEP_road_surface": (0.0, -5.0),
    "SURFACE_reverse_normals": (4.0, -7.0),
    "SURFACE_flip_switch": (0.0, -9.0),
    # 03 Layout / Banking
    "LAYOUT_prepare_dimensions": (0.0, -12.0),
    "SURFACE_reproject_layout": (0.0, -14.0),
    "FRAME_compute_grade_bank": (0.0, -16.0),
    "FRAME_apply_grade_bank": (0.0, -18.0),
    "DEBUG_bank_frames": (5.5, -18.0),
    # 04 Topology / Unity contract
    "TOPO_rebuild_road_quads": (0.0, -21.0),
    "UV_write_road_layout": (0.0, -23.0),
    "GROUP_road_bands": (0.0, -25.0),
    "TOPO_triangulate_for_unity": (0.0, -27.0),
    "COLLISION_mark_rendered": (0.0, -29.0),
    "NORMAL_generate_surface": (0.0, -31.0),
    "MASK_material_segments": (0.0, -33.0),
    "ATTR_road_contract": (0.0, -35.0),
    "OUT_ROAD_MESH": (0.0, -37.0),
    # 05 Start prefab branch
    "START_clear_surface": (5.5, -35.0),
    "START_prefab_instance": (5.5, -37.0),
    "OUT_START_PREFAB_INSTANCE": (5.5, -39.0),
}


GROUPS = (
    (
        "BOX_01_CENTERLINE",
        "01  输入与中心线｜校验、反向、Rotation 解码、重采样",
        (0.28, 0.43, 0.62),
        (
            "IN_Unity_Curve_Parameter_Input",
            "CENTERLINE_validate_or_fallback",
            "CENTERLINE_reverse_curve",
            "CENTERLINE_reverse_switch",
            "FRAME_decode_unity_rotation",
            "CENTERLINE_resample",
            "CENTERLINE_polyframe",
        ),
    ),
    (
        "BOX_02_SWEEP",
        "02  横截面与 Sweep｜生成基础道路网格",
        (0.20, 0.55, 0.52),
        (
            "PROFILE_compute_dimensions",
            "PROFILE_clear_centerline",
            "PROFILE_build_polyline",
            "PROFILE_assign_attributes",
            "PROFILE_cross_section",
            "SWEEP_road_surface",
            "SURFACE_reverse_normals",
            "SURFACE_flip_switch",
        ),
    ),
    (
        "BOX_03_LAYOUT_BANKING",
        "03  Layout 与 Banking｜保持美术中心线，再计算道路 Frame",
        (0.22, 0.48, 0.72),
        (
            "LAYOUT_prepare_dimensions",
            "SURFACE_reproject_layout",
            "FRAME_compute_grade_bank",
            "FRAME_apply_grade_bank",
            "DEBUG_bank_frames",
        ),
    ),
    (
        "BOX_04_UNITY_OUTPUT",
        "04  拓扑、UV、碰撞与 Unity 输出合约",
        (0.63, 0.43, 0.20),
        (
            "TOPO_rebuild_road_quads",
            "UV_write_road_layout",
            "GROUP_road_bands",
            "TOPO_triangulate_for_unity",
            "COLLISION_mark_rendered",
            "NORMAL_generate_surface",
            "MASK_material_segments",
            "ATTR_road_contract",
            "OUT_ROAD_MESH",
        ),
    ),
    (
        "BOX_05_START_PREFAB",
        "05  起点 Prefab 实例输出",
        (0.48, 0.32, 0.62),
        (
            "START_clear_surface",
            "START_prefab_instance",
            "OUT_START_PREFAB_INSTANCE",
        ),
    ),
)


NODE_COLORS = {
    "source": (0.34, 0.55, 0.80),
    "switch": (0.55, 0.82, 0.42),
    "sweep": (0.24, 0.66, 0.62),
    "layout": (0.92, 0.62, 0.18),
    "bank": (0.20, 0.58, 0.86),
    "topology": (0.82, 0.48, 0.18),
    "contract": (0.38, 0.70, 0.42),
    "output": (0.72, 0.30, 0.24),
    "start": (0.58, 0.38, 0.72),
}


def _snapshot(hou, road):
    return {
        "nodes": {
            node.name(): {
                "position": list(node.position()),
                "inputs": [
                    {
                        "index": connection.inputIndex(),
                        "item": connection.inputItem().name() if connection.inputItem() else None,
                        "node": connection.inputNode().name() if connection.inputNode() else None,
                    }
                    for connection in node.inputConnections()
                ],
                "comment": node.comment(),
                "display_comment": node.isGenericFlagSet(hou.nodeFlag.DisplayComment),
            }
            for node in road.children()
        },
        "boxes": [
            {
                "name": box.name(),
                "comment": box.comment(),
                "position": list(box.position()),
                "size": list(box.size()),
                "items": [item.name() for item in box.items()],
            }
            for box in road.networkBoxes()
        ],
        "notes": [
            {
                "name": note.name(),
                "text": note.text(),
                "position": list(note.position()),
                "size": list(note.size()),
            }
            for note in road.stickyNotes()
        ],
    }


def _logical_inputs(node):
    """Node.inputs() resolves subnet indirect inputs/network dots to SOP nodes."""
    return tuple(item.name() if item else None for item in node.inputs())


def _normalize_value(value):
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    try:
        return tuple(_normalize_value(item) for item in value)
    except TypeError:
        return str(value)


def _geometry_signature(geometry):
    point_attribs = tuple(sorted(geometry.pointAttribs(), key=lambda attrib: attrib.name()))
    vertex_attribs = tuple(sorted(geometry.vertexAttribs(), key=lambda attrib: attrib.name()))
    prim_attribs = tuple(sorted(geometry.primAttribs(), key=lambda attrib: attrib.name()))
    detail_attribs = tuple(sorted(geometry.globalAttribs(), key=lambda attrib: attrib.name()))
    return {
        "points": tuple(
            (
                _normalize_value(point.position()),
                tuple((attrib.name(), _normalize_value(point.attribValue(attrib))) for attrib in point_attribs),
            )
            for point in geometry.points()
        ),
        "primitives": tuple(
            (
                primitive.type().name(),
                tuple(vertex.point().number() for vertex in primitive.vertices()),
                tuple((attrib.name(), _normalize_value(primitive.attribValue(attrib))) for attrib in prim_attribs),
                tuple(
                    tuple((attrib.name(), _normalize_value(vertex.attribValue(attrib))) for attrib in vertex_attribs)
                    for vertex in primitive.vertices()
                ),
            )
            for primitive in geometry.prims()
        ),
        "detail": tuple(
            (attrib.name(), _normalize_value(geometry.attribValue(attrib)))
            for attrib in detail_attribs
        ),
    }


def organize_in_session(hou):
    track = hou.node(TRACK_PATH)
    if track is None or track.type().name() != "pcgbike::Track::1.0":
        raise RuntimeError("Expected pcgbike::Track::1.0 at %s" % TRACK_PATH)
    definition = track.type().definition()
    if definition is None or os.path.normcase(definition.libraryFilePath()) != os.path.normcase(HDA_PATH):
        raise RuntimeError("Track definition is not bound to %s" % HDA_PATH)
    if not track.isEditable():
        track.allowEditingOfContents()

    road = track.node("Road")
    if road is None:
        raise RuntimeError("Missing Road subnet")
    missing = [name for name in POSITIONS if road.node(name) is None]
    if missing:
        raise RuntimeError("Missing Road nodes: %s" % ", ".join(missing))

    output = road.node("OUT_ROAD_MESH")
    output.cook(force=True)
    geometry_before = _geometry_signature(output.geometry())
    inputs_before = {node.name(): _logical_inputs(node) for node in road.children()}
    snapshot = _snapshot(hou, road)

    os.makedirs(BACKUP_DIR, exist_ok=True)
    os.makedirs(RECOVERY_DIR, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    hip_backup = hou.hipFile.saveAsBackup()
    hda_backup = BACKUP_DIR + "/Track_bak_road_layout_" + timestamp + ".hda"
    definition.copyToHDAFile(hda_backup)
    recovery_path = RECOVERY_DIR + "/track_road_layout_prepatch_" + timestamp + ".json"
    with open(recovery_path, "w", encoding="utf-8") as stream:
        json.dump(snapshot, stream, ensure_ascii=False, indent=2)

    # Remove only visual containers/routing items; SOP nodes and their parameters remain untouched.
    for box in list(road.networkBoxes()):
        box.destroy()
    for dot in list(road.networkDots()):
        if dot.name().startswith("ROUTE_AUTHORED_FRAME"):
            dot.destroy()

    for name, position in POSITIONS.items():
        road.node(name).setPosition(hou.Vector2(position))

    # Route the long centerline authored-up input around the right side instead of
    # drawing a diagonal wire across Sweep, Layout and Banking nodes.
    resample = road.node("CENTERLINE_resample")
    compute = road.node("FRAME_compute_grade_bank")
    route_top = road.createNetworkDot()
    route_top.setName("ROUTE_AUTHORED_FRAME_TOP")
    route_top.setColor(hou.Color((0.60, 0.38, 0.88)))
    route_top.setPosition(hou.Vector2((7.0, 2.0)))
    route_top.setInput(resample)
    route_bottom = road.createNetworkDot()
    route_bottom.setName("ROUTE_AUTHORED_FRAME_BANK")
    route_bottom.setColor(hou.Color((0.60, 0.38, 0.88)))
    route_bottom.setPosition(hou.Vector2((7.0, -15.5)))
    route_bottom.setInput(route_top)
    compute.setInput(1, route_bottom)

    # Keep detailed comments available in node info, but hide all inline comments.
    # Box titles and two concise sticky notes carry the learning documentation.
    for node in road.children():
        node.setGenericFlag(hou.nodeFlag.DisplayComment, False)

    road.node("NORMAL_generate_surface").setComment(
        "统一重算法线并保持平滑道路表面；供 Unity URP MeshRenderer 与 MeshCollider 共用。"
    )
    road.node("SURFACE_reproject_layout").setComment(
        "保持美术采样中心线不变；重建道路横截面并写入距离、Banking 兼容数据与只读急弯诊断，不执行自动改线。"
    )
    road.node("FRAME_compute_grade_bank").setComment(
        "计算三维切线、纵坡、曲率，并叠加 Auto Bank、Unity Knot Roll 与 Manual Ramp。第二输入是紫色 authored-up 路由。"
    )
    road.node("FRAME_apply_grade_bank").setComment(
        "使用最终 tangent/lateral/up 重建道路横截面；关闭 Banking 时不修改输入顶点。"
    )

    color_groups = {
        "source": (
            "IN_Unity_Curve_Parameter_Input", "CENTERLINE_validate_or_fallback",
            "FRAME_decode_unity_rotation", "CENTERLINE_resample",
            "CENTERLINE_polyframe",
        ),
        "switch": ("CENTERLINE_reverse_curve", "CENTERLINE_reverse_switch", "SURFACE_reverse_normals", "SURFACE_flip_switch"),
        "sweep": (
            "PROFILE_compute_dimensions", "PROFILE_clear_centerline",
            "PROFILE_build_polyline", "PROFILE_assign_attributes",
            "PROFILE_cross_section", "SWEEP_road_surface",
        ),
        "layout": ("LAYOUT_prepare_dimensions", "SURFACE_reproject_layout"),
        "bank": ("FRAME_compute_grade_bank", "FRAME_apply_grade_bank", "DEBUG_bank_frames"),
        "topology": ("TOPO_rebuild_road_quads", "UV_write_road_layout", "GROUP_road_bands", "TOPO_triangulate_for_unity"),
        "contract": ("COLLISION_mark_rendered", "NORMAL_generate_surface", "MASK_material_segments", "ATTR_road_contract"),
        "output": ("OUT_ROAD_MESH",),
        "start": ("START_clear_surface", "START_prefab_instance", "OUT_START_PREFAB_INSTANCE"),
    }
    for color_name, names in color_groups.items():
        color = hou.Color(NODE_COLORS[color_name])
        for name in names:
            road.node(name).setColor(color)

    for box_name, title, rgb, names in GROUPS:
        box = road.createNetworkBox()
        box.setName(box_name)
        box.setComment(title)
        box.setColor(hou.Color(rgb))
        for name in names:
            box.addItem(road.node(name))
        box.fitAroundContents()

    notes = {note.name(): note for note in road.stickyNotes()}
    learning = notes.get("NOTE_Road_SOP_Learning") or road.createStickyNote("NOTE_Road_SOP_Learning")
    learning.setText(
        "阅读顺序：01 中心线 → 02 Sweep → 03 Layout/Banking → 04 Unity 输出。\n"
        "所有 Houdini 计算只发生在编辑器 Cook/Bake；移动端运行时使用 Bake 网格。"
    )
    learning.setPosition(hou.Vector2((-2.0, 17.5)))
    learning.setSize(hou.Vector2((10.0, 1.8)))
    learning.setColor(hou.Color((1.0, 0.94, 0.42)))
    learning.setTextSize(0.65)

    banking_note = notes.get("NOTE_Road_Banking") or road.createStickyNote("NOTE_Road_Banking")
    banking_note.setText(
        "紫色旁路线：Unity Knot authored up → FRAME_compute_grade_bank 输入 2。\n"
        "主链顺序：Layout 保持美术中心线，Banking 直接按该中心线计算倾角。\n"
        "DEBUG_bank_frames 仅供 Houdini 查看，不进入 Unity Bake。"
    )
    banking_note.setPosition(hou.Vector2((8.5, -12.0)))
    banking_note.setSize(hou.Vector2((10.0, 3.2)))
    banking_note.setColor(hou.Color((0.82, 0.73, 1.0)))
    banking_note.setTextSize(0.62)

    inputs_after = {node.name(): _logical_inputs(node) for node in road.children()}
    if inputs_before != inputs_after:
        changes = {
            name: {"before": inputs_before.get(name), "after": inputs_after.get(name)}
            for name in sorted(set(inputs_before) | set(inputs_after))
            if inputs_before.get(name) != inputs_after.get(name)
        }
        raise RuntimeError("Logical SOP connections changed: %r" % changes)

    output.cook(force=True)
    geometry_after = _geometry_signature(output.geometry())
    if geometry_before != geometry_after:
        raise RuntimeError("Road geometry changed while applying visual-only layout")
    if track.errors() or output.errors():
        raise RuntimeError("Cook errors after layout: %r / %r" % (track.errors(), output.errors()))

    definition.save(HDA_PATH, template_node=track, create_backup=False)
    hou.hipFile.save()
    return {
        "hip": hou.hipFile.path(),
        "hip_backup": hip_backup,
        "hda": definition.libraryFilePath(),
        "hda_backup": hda_backup,
        "recovery": recovery_path,
        "node_count": len(road.children()),
        "box_count": len(road.networkBoxes()),
        "note_count": len(road.stickyNotes()),
        "route_dot_count": len(road.networkDots()),
        "geometry_unchanged": True,
        "errors": list(track.errors()) + list(output.errors()),
        "warnings": list(track.warnings()) + list(output.warnings()),
        "hip_unsaved": hou.hipFile.hasUnsavedChanges(),
    }


def main():
    connection, _ = hrpyc.import_remote_module("127.0.0.1", 18811, "hou")
    script_path = os.path.abspath(__file__).replace("\\", "/")
    code = (
        "import hou\n"
        "_layout_ns={'__name__':'track_road_layout_remote'}\n"
        "exec(compile(open(%r,encoding='utf-8').read(),%r,'exec'),_layout_ns)\n"
        "TRACK_ROAD_LAYOUT_RESULT=_layout_ns['organize_in_session'](hou)\n"
    ) % (script_path, script_path)
    connection.execute(code)
    try:
        return connection.eval("__import__('json').dumps(TRACK_ROAD_LAYOUT_RESULT,ensure_ascii=False)")
    finally:
        connection.close()


if __name__ == "__main__":
    print("TRACK_ROAD_LAYOUT_RESULT=" + main())
