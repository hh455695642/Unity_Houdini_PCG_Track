"""Finish the CityRoadCore readability migration from the captured Live Scene.

The patch is structural and save=False only.  It keeps CityRoadTutorialLab
bridges untouched, restores stable leaf names inside the two new subnets,
routes long wires through named network dots, rebuilds semantic Network Boxes,
and adds Chinese learning notes.  HDA/HIP persistence belongs to VerifyFull.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

try:
    import hou  # type: ignore
except ImportError:
    hou = None


ASSET_PATH = "/obj/CityRoad_DEV"
ASSET_TYPE = "pcgbike::CityRoad::1.0"
CORE_PATH = "CityRoadCore"
MARKER = "CITYROAD_CORE_READABILITY_V38_20260822"
BASELINE_SHA256 = "ed0aeb0a4a25b0d90a3a4b01fa76c74f1e96fa324d9cf45122ab3f190ac4df13"
SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = SCRIPT_DIR.parents[3]
LAYOUT_CONTRACT = SCRIPT_DIR.parent / "contracts/cityroad_subnet_layout_contract.json"
EXPECTED_HIP = PROJECT_ROOT / "HoudiniProject/PCG_Track_21.0.440/PCG_Bike_CityRoad.hip"
EXPECTED_HDA = PROJECT_ROOT / "Assets/PCG/HDA/City/CityRoad.hda"

DEAD_PATHS = (
    "CR_CORRIDOR_SURFACE/CITYROAD_CORRIDOR_CURB_SIDEWALK_V4",
    "CR_CORRIDOR_SURFACE/CITYROAD_JUNCTION_CURB_SIDEWALK_V4",
    "CR_UNION_FINALIZE/ROAD_NORMALS",
    "CR_MARKING_APPROACH/CITYROAD_MARKING_CENTER_V2",
    "CR_MARKING_APPROACH/CITYROAD_MARKING_LANE_V2",
    "CR_MARKING_APPROACH/CITYROAD_MARKING_EDGE_V2",
    "CR_MARKING_APPROACH/CITYROAD_MARKING_JUNCTION_V2",
    "CR_COLLISION_AUDIT/COLLISION_BUILD_SIMPLIFIED",
)

LAB_BRIDGES = (
    "IN_LAB_ROAD_TOP_UNITY_READY", "IN_LAB_SIDEWALK_CANDIDATE",
    "IN_LAB_TRUE_OUTER_BOUNDARY", "OUT_LAB_GRAPH",
    "OUT_LAB_ROAD_CENTERLINES", "OUT_LAB_ROAD_OUTLINES",
)

COLORS = {
    "AREA_INPUT_GRAPH": (0.20, 0.48, 0.82),
    "AREA_ROAD": (0.90, 0.44, 0.16),
    "AREA_JUNCTION_SIDEWALK": (0.25, 0.66, 0.32),
    "AREA_MARKING_STREET": (0.88, 0.70, 0.18),
    "AREA_CITY_PARK": (0.30, 0.62, 0.45),
    "AREA_OUTPUT_DEBUG": (0.46, 0.48, 0.54),
}

AREA_LABELS = {
    "AREA_INPUT_GRAPH": "01 输入与图索引 / INPUT + GRAPH",
    "AREA_ROAD": "02 道路核心 / ROAD CORE",
    "AREA_JUNCTION_SIDEWALK": "03 路口、人行道与路缘 / JUNCTION + SIDEWALK",
    "AREA_MARKING_STREET": "04 标线、碰撞与街具 / MARKING + COLLISION + STREET",
    "AREA_CITY_PARK": "05 城市公园 / CITY PARK",
    "AREA_OUTPUT_DEBUG": "06 正式输出与 TutorialLab 桥接 / OUTPUT + DEBUG",
}

TOP_POSITIONS = {
    # 输入与索引：只在最上游展开，主干从左向右。
    "CR_INPUT_CONTRACT": (-30, 34), "CR_GRAPH_INDEX": (-20, 34),
    "CR_JUNCTION_INDEX": (-10, 34), "CR_CORRIDOR_SURFACE": (0, 34),
    "IN_LAB_ROAD_TOP_UNITY_READY": (14, 34),
    "IN_LAB_SIDEWALK_CANDIDATE": (24, 34),
    "IN_LAB_TRUE_OUTER_BOUNDARY": (34, 34),
    # 道路主干。
    "CR_UNION_BOUNDARY": (-30, 20), "CR_UNION_FINALIZE": (-20, 20),
    "CR_JUNCTION_STRIP_EXTRACT": (-10, 20), "CR_JUNCTION_METADATA": (0, 20),
    "CR_ROAD_SHELL_AUDIT": (10, 20), "CR_LOCAL_TOPOLOGY": (20, 20),
    "CR_ROAD_CORNER_REBUILD": (30, 20), "CR_ROAD_FINALIZE": (40, 20),
    "CR_ROAD_OUTPUT_CLASSIFY": (50, 20),
    # 人行道分支。
    "CR_SIDEWALK_SITE_OPEN_ENDS": (-30, 6),
    "CR_SIDEWALK_CONSTRAINT_BUILD": (-18, 6), "CR_SIDEWALK_CLASSIFY": (-6, 6),
    "CR_SIDEWALK_SEAMS": (6, 6), "CR_SIDEWALK_AUDIT_OUTPUT": (18, 6),
    "CR_CURB_SIDEWALK_FINAL": (30, 6), "CR_SIDEWALK_OUTPUT": (42, 6),
    # 标线、碰撞、街具；CR_STATIC_MARKING_MESH 回到主视野，不再漂在 y=-119。
    "CR_MARKING_HELPERS": (-30, -10), "CR_STATIC_MARKING_MESH": (-18, -10),
    "CR_MARKING_APPROACH": (-6, -10), "CR_MARKING_FINAL": (6, -10),
    "CR_MARKING_POINTS": (18, -10), "CR_COLLISION_AUDIT": (30, -10),
    "CR_STREET_FURNITURE": (42, -10), "CR_ROAD_MATERIAL_CONTRACT": (54, -10),
    # 输出分两排，正式输出与 Lab 桥接可一眼区分。
    "OUT_LAB_GRAPH": (-30, -28), "OUT_LAB_ROAD_CENTERLINES": (-20, -28),
    "OUT_LAB_ROAD_OUTLINES": (-10, -28), "OUT_ROAD_CENTERLINE_GRAPH": (2, -28),
    "OUT_ROAD_COLLISION": (12, -28), "OUT_ROAD_MARKINGS": (22, -28),
    "OUT_ROAD_MARKING_POINTS": (32, -28), "OUT_ROAD_SURFACE": (42, -28),
    "OUT_SIDEWALK_CURB": (52, -28), "OUT_STREET_LAMPS": (62, -28),
    "OUT_STREET_TREES": (72, -28), "OUT_STREET_TREE_PITS": (82, -28),
    "CR_CITY_PARK": (18, -46), "OUT_PARK_GROUND": (30, -50),
    "OUT_PARK_PATHS": (38, -50), "OUT_PARK_WATER": (46, -50),
    "OUT_PARK_COLLISION": (54, -50), "OUT_PARK_TREES": (62, -50),
    "OUT_PARK_EXCLUSION": (70, -50),
}

NOTES = {
    "NOTE_CITYROAD_README": ((-47, 41), (15, 8),
        "CityRoadCore 阅读顺序\n"
        "① CR_INPUT_CONTRACT → ② GRAPH/JUNCTION INDEX → ③ CORRIDOR SURFACE\n"
        "④ ROAD / SIDEWALK 分支 → ⑤ MARKING / COLLISION / STREET → ⑥ OUT_*\n"
        "颜色只表达职责，不表达 Cook 状态；正式输出统一放在底部。"),
    "NOTE_ROAD_GUIDE": ((-47, 25), (15, 7),
        "道路核心\n并集边界 → 路口条带/元数据 → 壳体审计 → 局部融合 → 角部重建 → Unity 最终化。\n"
        "CR_ROAD_CORNER_REBUILD 内保留边界分区 subnet，便于单独检查角部四边形条带。"),
    "NOTE_SIDEWALK_GUIDE": ((-47, 11), (15, 7),
        "人行道/路缘\n场地与开口 → 2D 约束 → 内外分类 → 接缝校验 → 审计 → 路缘/人行道输出。\n"
        "调试时从左向右检查；不要从输出节点反向跨模块追线。"),
    "NOTE_MARKING_GUIDE": ((-47, -5), (15, 8),
        "标线/碰撞/街具\nCR_STATIC_MARKING_MESH：静态标线构建 + V24 提交后裁切校验。\n"
        "CR_STREET_FURNITURE：中心线直接来自 CR_CORRIDOR_SURFACE，不再借道 OUT 节点。\n"
        "街具仅生成 Bake 用实例点，不修改道路拓扑。"),
    "NOTE_OUTPUT_GUIDE": ((-47, -24), (15, 7),
        "输出与 Lab 桥接\nOUT_* 是 Unity/HDA 正式输出；OUT_LAB_* 与 IN_LAB_* 仅用于 TutorialLab 桥接。\n"
        "本次未修改 CityRoadTutorialLab；排查生产输出时优先忽略 Lab 桥接线。"),
}


def _norm(value) -> str:
    return str(value).replace("\\", "/").lower()


def _inputs(core, node):
    return sorted([
        [connection.inputIndex(),
         connection.inputNode().path().replace(core.path() + "/", ""),
         connection.outputIndex()]
        for connection in node.inputConnections()
    ])


def _baseline_payload(core):
    targets = (
        "CR_STATIC_MARKING_MESH", "CR_ROAD_CORNER_REBUILD", "CR_STREET_FURNITURE",
        "OUT_ROAD_CENTERLINE_GRAPH", *LAB_BRIDGES)
    payload = {
        "top": sorted([[node.name(), node.type().name()] for node in core.children()]),
        "targets": {},
    }
    for name in targets:
        node = core.node(name)
        if node is None:
            raise RuntimeError(f"V38 baseline target missing: {name}")
        payload["targets"][name] = {
            "type": node.type().name(), "inputs": _inputs(core, node),
            "children": sorted([
                [child.name(), child.type().name(), _inputs(core, child)]
                for child in node.children()
            ]) if node.type().name() == "subnet" else [],
        }
    return payload


def _sha256(value) -> str:
    data = json.dumps(value, ensure_ascii=False, sort_keys=True,
                      separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(data).hexdigest()


def _require_identity():
    asset = hou.node(ASSET_PATH)
    if asset is None or asset.type().name() != ASSET_TYPE:
        raise RuntimeError(f"Expected {ASSET_TYPE} at {ASSET_PATH}")
    definition = asset.type().definition()
    if definition is None or _norm(definition.libraryFilePath()) != _norm(EXPECTED_HDA):
        raise RuntimeError("Unexpected CityRoad HDA definition")
    if _norm(hou.hipFile.path()) != _norm(EXPECTED_HIP):
        raise RuntimeError("Unexpected CityRoad HIP")
    core = asset.node(CORE_PATH)
    if core is None:
        raise RuntimeError("CityRoadCore is missing")
    return asset, core


def _set_connector_labels(subnet):
    for connection in subnet.inputConnections():
        parm = subnet.parm(f"label{connection.inputIndex() + 1}")
        if parm is not None:
            parm.set(connection.inputNode().name())


def _refresh_all_connector_labels(core):
    """Replace every default ``Sub-Network Input`` label with a semantic source."""
    for node in core.children():
        if node.type().name() != "subnet" or not node.name().startswith("CR_"):
            continue
        _set_connector_labels(node)
        for descendant in node.allSubChildren():
            if descendant.type().name() == "subnet" and descendant.name().startswith("CR_"):
                _set_connector_labels(descendant)


def _repair_corner_rebuild_interface(core):
    """Restore the four distinct logical feeds hidden by the partial wrapper."""
    corner = core.node("CR_ROAD_CORNER_REBUILD")
    constraints = core.node("CR_SIDEWALK_CONSTRAINT_BUILD")
    junction = core.node("CR_JUNCTION_INDEX")
    corridor = core.node("CR_CORRIDOR_SURFACE")
    # Preserve the nested boundary subnet's authored interface order:
    # 0=corner section constraints, 1=junction partition cuts,
    # 2=clean road boundary, 3=adaptive road surface.
    corner.setInput(0, constraints, 0)
    corner.setInput(1, junction, 0)
    corner.setInput(2, constraints, 2)
    corner.setInput(3, corridor, 0)
    indirect = corner.indirectInputs()
    boundary = corner.node("CR_ROAD_BOUNDARY_PARTITION")
    boundary.setInput(0, indirect[0], 0)
    boundary.setInput(1, indirect[1], 0)
    boundary.setInput(2, indirect[2], 0)
    rebuild = corner.node("CITYROAD_REPLACE_CORNER_WITH_QUAD_STRIPS_V11")
    rebuild.setInput(0, boundary, 0)
    rebuild.setInput(1, indirect[3], 0)
    rebuild.setInput(2, indirect[0], 0)
    _set_connector_labels(corner)


def _document_new_subnets(core):
    static = core.node("CR_STATIC_MARKING_MESH")
    corner = core.node("CR_ROAD_CORNER_REBUILD")
    static.setComment(
        "CR_STATIC_MARKING_MESH | 静态道路标线构建与提交后裁切审计\n"
        "输入0：圆角中心线；输入1：道路分类；输入2：路口口沿；输入3：标线辅助数据\n"
        "输出：已通过 V24 Junction Clip 校验的标线网格。")
    corner.setComment(
        "CR_ROAD_CORNER_REBUILD | 最终道路边界分区与角部四边形条带重建\n"
        "输入0：角部约束；输入1：路口分区裁切；输入2：道路边界；输入3：自适应道路面\n"
        "输出：送入 CR_ROAD_FINALIZE 的确定性道路角部结果。")
    for subnet in (static, corner):
        subnet.setGenericFlag(hou.nodeFlag.DisplayComment, True)
        _set_connector_labels(subnet)

    build = static.node("CITYROAD_BUILD_STATIC_MARKING_MESH")
    validate = static.node("CITYROAD_VALIDATE_STATIC_MARKING_JUNCTION_CLIP_V24")
    build.setComment(
        "构建中心线/车道线/边缘线/路口标线静态网格；共享道路分类与 Junction 口沿数据。")
    validate.setComment(
        "V24 提交后审计：在 Detail Wrangle 写入/删除完成后，验证 Junction 裁切与标线合法性。")
    output = static.node("SUBNET_OUT_STATIC_MARKING_MESH")
    output.setComment("静态标线网格输出：只发布已通过 V24 裁切审计的结果。")

    boundary = corner.node("CR_ROAD_BOUNDARY_PARTITION")
    boundary.setComment(
        "CR_ROAD_BOUNDARY_PARTITION | 合并道路边界、路口裁切与角部约束，并融合后做 2D 三角化。")
    _set_connector_labels(boundary)
    rebuild = corner.node("CITYROAD_REPLACE_CORNER_WITH_QUAD_STRIPS_V11")
    rebuild.setComment(
        "V11/V22：用确定性四边形条带替换道路角部；输入0为最终边界三角化，输入1为道路面，输入2为角部约束。")
    corner_out = corner.node("SUBNET_OUT_CORNER_REBUILD")
    corner_out.setComment("道路角部重建输出：供 CR_ROAD_FINALIZE 做 Unity 绕序、投影与属性转移。")
    for node in (build, validate, output, boundary, rebuild, corner_out):
        node.setGenericFlag(hou.nodeFlag.DisplayComment, True)

    # 两个新 subnet 内部保持自左向右的数据流，所有 Output 离开原点。
    build.setPosition((-3, 4)); validate.setPosition((4, 4)); output.setPosition((10, 4))
    boundary.setPosition((-3, 4)); rebuild.setPosition((4, 4)); corner_out.setPosition((10, 4))
    boundary.layoutChildren(horizontal_spacing=2.4, vertical_spacing=1.3)


def _rebuild_visual_structure(core, contract):
    for name, position in TOP_POSITIONS.items():
        item = core.item(name)
        if item is None:
            raise RuntimeError(f"V38 top-level layout target missing: {name}")
        item.setPosition(hou.Vector2(position))

    # 只重建本任务命名的总线点和学习注释，不触碰用户的其他 Network Item。
    for dot in list(core.networkDots()):
        if dot.name().startswith("CR_BUS_"):
            dot.destroy()
    corridor = core.node("CR_CORRIDOR_SURFACE")
    road_classify = core.node("CR_ROAD_OUTPUT_CLASSIFY")
    buses = {
        "CR_BUS_CENTERLINE": (corridor, 0, (6, -18), [
            (core.node("OUT_ROAD_CENTERLINE_GRAPH"), 0),
            (core.node("CR_STREET_FURNITURE"), 2)]),
        "CR_BUS_ROAD_CLASSIFIED": (road_classify, 0, (48, -2), [
            (core.node("CR_MARKING_APPROACH"), 2), (core.node("CR_MARKING_FINAL"), 2),
            (core.node("CR_COLLISION_AUDIT"), 1), (core.node("CR_STREET_FURNITURE"), 0),
            (core.node("CR_SIDEWALK_OUTPUT"), 0), (core.node("CR_STATIC_MARKING_MESH"), 1)]),
        "CR_BUS_MARKING_CENTERLINE": (corridor, 3, (-12, -2), [
            (core.node("CR_STATIC_MARKING_MESH"), 0),
            (core.node("CR_MARKING_POINTS"), 0), (core.node("CR_COLLISION_AUDIT"), 2)]),
        "CR_BUS_VALIDATED_STATIC_MARKINGS": (
            core.node("CR_STATIC_MARKING_MESH"), 0, (-10, -15), [
                (core.node("CR_MARKING_APPROACH"), 1),
                (core.node("CR_MARKING_FINAL"), 0)]),
    }
    for name, (source, output_index, position, destinations) in buses.items():
        dot = core.createNetworkDot()
        dot.setName(name, unique_name=False)
        dot.setInput(source, output_index)
        dot.setPosition(hou.Vector2(position))
        for destination, input_index in destinations:
            destination.setInput(input_index, dot, 0)

    # Street Furniture 不再借道 OUT_ROAD_CENTERLINE_GRAPH；Output 只负责发布。
    street = core.node("CR_STREET_FURNITURE")
    street.setComment(
        "CR_STREET_FURNITURE | 路灯、树木、树池共享采样及分支开关\n"
        "输入0：道路分类；输入1：路口中心索引；输入2：CR_CORRIDOR_SURFACE 中心线总线\n"
        "输出：树池、路灯、行道树 Bake 用实例点；不修改道路拓扑。")
    _set_connector_labels(street)

    for box in list(core.networkBoxes()):
        if box.name() in contract["areas"]:
            box.destroy()
    for area_name, members in contract["areas"].items():
        box = core.createNetworkBox(area_name)
        box.setComment(AREA_LABELS[area_name])
        box.setColor(hou.Color(COLORS[area_name]))
        for member in members:
            item = core.item(member)
            if item is None:
                raise RuntimeError(f"V38 area member missing: {area_name}/{member}")
            box.addItem(item)
        box.fitAroundContents()

    for note in list(core.stickyNotes()):
        if note.name().startswith("NOTE_CITYROAD_") or note.name() in NOTES:
            note.destroy()
    for name, (position, size, text) in NOTES.items():
        note = core.createStickyNote()
        note.setName(name, unique_name=False)
        note.setPosition(hou.Vector2(position))
        note.setSize(size)
        note.setText(text)
        note.setTextSize(0.55)
        note.setColor(hou.Color((0.16, 0.18, 0.22)))


def _validate(core, contract):
    expected_top = set(contract["subnets"]) | set(contract["preserved_top_level"])
    actual_top = {node.name() for node in core.children()}
    if actual_top != expected_top or len(actual_top) != 50:
        raise RuntimeError("V38 top-level membership/count mismatch")
    for path in DEAD_PATHS:
        if core.node(path) is not None:
            raise RuntimeError(f"Proven-dead node returned: {path}")
    if core.node("CR_STREET_FURNITURE").inputConnections()[2].inputNode() != core.node("CR_CORRIDOR_SURFACE"):
        raise RuntimeError("Street Furniture centerline still routes through an output SOP")
    for subnet_name in ("CR_STATIC_MARKING_MESH", "CR_ROAD_CORNER_REBUILD"):
        subnet = core.node(subnet_name)
        if not subnet.comment().strip():
            raise RuntimeError(f"Missing subnet documentation: {subnet_name}")
        for output in [node for node in subnet.children() if node.type().name() == "output"]:
            if not output.comment().strip() or output.position() == hou.Vector2((0, 0)):
                raise RuntimeError(f"Incomplete subnet output documentation/layout: {output.path()}")
    if len(core.networkBoxes()) != len(contract["areas"]):
        raise RuntimeError("V38 Network Box count mismatch")
    lab_signature = {
        name: _inputs(core, core.node(name)) for name in LAB_BRIDGES
    }
    expected_lab = {
        "IN_LAB_ROAD_TOP_UNITY_READY": [], "IN_LAB_SIDEWALK_CANDIDATE": [],
        "IN_LAB_TRUE_OUTER_BOUNDARY": [], "OUT_LAB_GRAPH": [[0, "CR_GRAPH_INDEX", 1]],
        "OUT_LAB_ROAD_CENTERLINES": [[0, "CR_CORRIDOR_SURFACE", 1]],
        "OUT_LAB_ROAD_OUTLINES": [[0, "CR_UNION_BOUNDARY", 1]],
    }
    if lab_signature != expected_lab:
        raise RuntimeError("CityRoadTutorialLab bridge signature changed")
    return {
        "top_level": len(actual_top), "network_boxes": len(core.networkBoxes()),
        "network_dots": len([d for d in core.networkDots() if d.name().startswith("CR_BUS_")]),
        "learning_notes": len([n for n in core.stickyNotes() if n.name() in NOTES]),
        "tutorial_lab_untouched": True,
    }


def apply_live_patch(save=False, capture_verified_dirty=False, hou_module=None):
    global hou
    if hou_module is not None:
        hou = hou_module
    if hou is None:
        raise RuntimeError("The hou module is unavailable")
    if save:
        raise RuntimeError("V38 patch is save=False only; use the regression gate")
    _asset, core = _require_identity()
    contract = json.loads(LAYOUT_CONTRACT.read_text(encoding="utf-8"))
    if core.userData("cityroad_core_readability_marker") == MARKER:
        _document_new_subnets(core)
        _repair_corner_rebuild_interface(core)
        _rebuild_visual_structure(core, contract)
        _refresh_all_connector_labels(core)
        result = _validate(core, contract)
        result.update({"status": "PASS", "already_applied": True, "saved": False})
        return result
    if not capture_verified_dirty:
        raise RuntimeError("V38 requires an explicit Capture-verified Live Scene")
    actual_sha = _sha256(_baseline_payload(core))
    if actual_sha != BASELINE_SHA256:
        raise RuntimeError(f"V38 Live baseline changed: {actual_sha} != {BASELINE_SHA256}")
    for path in DEAD_PATHS:
        if core.node(path) is not None:
            raise RuntimeError(f"Dead-node precondition changed: {path}")

    try:
        with hou.undos.group("CityRoadCore Readability V38"):
            renames = {
                "CR_STATIC_MARKING_MESH/BUILD_STATIC_MARKING_MESH":
                    "CITYROAD_BUILD_STATIC_MARKING_MESH",
                "CR_STATIC_MARKING_MESH/VALIDATE_STATIC_MARKING_JUNCTION_CLIP_V24":
                    "CITYROAD_VALIDATE_STATIC_MARKING_JUNCTION_CLIP_V24",
                "CR_ROAD_CORNER_REBUILD/REPLACE_CORNER_WITH_QUAD_STRIPS_V11":
                    "CITYROAD_REPLACE_CORNER_WITH_QUAD_STRIPS_V11",
            }
            for path, new_name in renames.items():
                core.node(path).setName(new_name, unique_name=False)
            _document_new_subnets(core)
            _repair_corner_rebuild_interface(core)
            _rebuild_visual_structure(core, contract)
            _refresh_all_connector_labels(core)
            core.setUserData("cityroad_core_readability_marker", MARKER)
            result = _validate(core, contract)
    except Exception:
        try:
            hou.undos.performUndo()
        finally:
            raise
    result.update({"status": "PASS", "already_applied": False,
                   "saved": False, "marker": MARKER})
    return result


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=18811)
    parser.add_argument("--save", default="false")
    parser.add_argument("--capture-verified-dirty", default="false")
    args = parser.parse_args()
    if args.save.lower() != "false":
        raise RuntimeError("Only --save false is supported")
    import hrpyc
    connection, _remote_hou = hrpyc.import_remote_module(args.host, args.port, "hou")
    try:
        tools_path = str(SCRIPT_DIR).replace("\\", "/")
        connection.execute(
            "import sys, importlib; "
            f"sys.path.insert(0, {tools_path!r}) if {tools_path!r} not in sys.path else None; "
            "import patch_cityroad_core_readability_v38_20260822 as _cityroad_v38; "
            "importlib.reload(_cityroad_v38)")
        payload = connection.eval(
            "_cityroad_v38.apply_live_patch(save=False, capture_verified_dirty="
            f"{args.capture_verified_dirty.lower() == 'true'!r})")
        print(json.dumps(payload, ensure_ascii=False, default=list, indent=2))
    finally:
        connection.close()


if __name__ == "__main__":
    main()
