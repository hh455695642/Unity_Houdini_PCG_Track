"""Reframe CityRoadCore as a three-level learning network.

This patch is structural and save=False only.  It collapses the authored road
pipeline under one navigation subnet, keeps the existing CR_* function subnets
as the implementation layer, lays them out in four topological learning stages,
and leaves CityRoadTutorialLab plus every leaf SOP/VEX body untouched.

Houdini SOP subnets expose only four wired inputs.  The four stages therefore
use explicit Network Boxes rather than hidden Object Merge dependencies or a
merged geometry bus.  This preserves the current geometry semantics while the
top-level network becomes a concise overview.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from pathlib import Path

try:
    import hou  # type: ignore
except ImportError:
    hou = None


ASSET_PATH = "/obj/CityRoad_DEV"
ASSET_TYPE = "pcgbike::CityRoad::1.0"
CORE_PATH = "CityRoadCore"
MAIN_NAME = "CR_MAIN_PIPELINE"
MARKER = "CITYROAD_THREE_LEVEL_READABILITY_V46_20260824"
BASELINE_SHA256 = "15b751b387a0058a23c0336f555a55426328251d52d4c699aef96c67b7092e56"
SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = SCRIPT_DIR.parents[3]
EXPECTED_HIP = PROJECT_ROOT / "HoudiniProject/PCG_Track_21.0.440/PCG_Bike_CityRoad.hip"
EXPECTED_HDA = PROJECT_ROOT / "Assets/PCG/HDA/City/CityRoad.hda"

STAGES = {
    "AREA_STAGE_01_CONTEXT": [
        "IN_LAB_ROAD_TOP_UNITY_READY", "IN_LAB_SIDEWALK_CANDIDATE",
        "IN_LAB_TRUE_OUTER_BOUNDARY", "CR_ROAD_MATERIAL_CONTRACT",
        "CR_INPUT_CONTRACT", "CR_GRAPH_INDEX", "CR_JUNCTION_INDEX",
        "CR_CORRIDOR_SURFACE", "CR_MARKING_HELPERS",
    ],
    "AREA_STAGE_02_SURFACE_CONSTRAINTS": [
        "CR_MARKING_POINTS", "CR_UNION_BOUNDARY", "CR_SIDEWALK_SITE_OPEN_ENDS",
        "CR_UNION_FINALIZE", "CR_JUNCTION_STRIP_EXTRACT",
        "CR_SIDEWALK_CONSTRAINT_BUILD", "CR_JUNCTION_METADATA",
        "CR_ROAD_CORNER_REBUILD", "CR_LOCAL_TOPOLOGY", "CR_ROAD_SHELL_AUDIT",
    ],
    "AREA_STAGE_03_FINALIZE": [
        "CR_ROAD_FINALIZE", "CR_ROAD_OUTPUT_CLASSIFY", "CR_SIDEWALK_CLASSIFY",
        "CR_COLLISION_AUDIT", "CR_SIDEWALK_SEAMS", "CR_STATIC_MARKING_MESH",
        "CR_STREET_FURNITURE",
    ],
    "AREA_STAGE_04_CONTENT_OUTPUTS": [
        "CR_MARKING_APPROACH", "CR_SIDEWALK_AUDIT_OUTPUT",
        "CR_CURB_SIDEWALK_FINAL", "CR_MARKING_FINAL", "CR_SIDEWALK_OUTPUT",
    ],
}

STAGE_LABELS = {
    "AREA_STAGE_01_CONTEXT": "01 输入、Graph、Junction 与 Corridor / CONTEXT",
    "AREA_STAGE_02_SURFACE_CONSTRAINTS": "02 路面、边界与约束 / SURFACE + CONSTRAINTS",
    "AREA_STAGE_03_FINALIZE": "03 道路最终化与内容构建 / FINALIZE",
    "AREA_STAGE_04_CONTENT_OUTPUTS": "04 标线、人行道与正式内容输出 / CONTENT OUTPUTS",
    "AREA_MAIN_PUBLISH": "05 CityRoadCore 发布接口 / PUBLISH",
}

STAGE_COLORS = {
    "AREA_STAGE_01_CONTEXT": (0.20, 0.48, 0.82),
    "AREA_STAGE_02_SURFACE_CONSTRAINTS": (0.90, 0.44, 0.16),
    "AREA_STAGE_03_FINALIZE": (0.25, 0.66, 0.32),
    "AREA_STAGE_04_CONTENT_OUTPUTS": (0.88, 0.70, 0.18),
    "AREA_MAIN_PUBLISH": (0.46, 0.48, 0.54),
}

MAIN_POSITIONS = {
    "IN_LAB_ROAD_TOP_UNITY_READY": (18, 56),
    "IN_LAB_SIDEWALK_CANDIDATE": (30, 56),
    "IN_LAB_TRUE_OUTER_BOUNDARY": (42, 56),
    "CR_ROAD_MATERIAL_CONTRACT": (30, 46),
    "CR_INPUT_CONTRACT": (-28, 58),
    "CR_GRAPH_INDEX": (-28, 48),
    "CR_JUNCTION_INDEX": (-28, 38),
    "CR_CORRIDOR_SURFACE": (-28, 28),
    "CR_MARKING_HELPERS": (0, 28),
    "CR_MARKING_POINTS": (-46, 14),
    "CR_UNION_BOUNDARY": (-28, 14),
    "CR_SIDEWALK_SITE_OPEN_ENDS": (12, 14),
    "CR_UNION_FINALIZE": (-28, 4),
    "CR_JUNCTION_STRIP_EXTRACT": (-10, -6),
    "CR_SIDEWALK_CONSTRAINT_BUILD": (12, 4),
    "CR_JUNCTION_METADATA": (-10, -16),
    "CR_ROAD_CORNER_REBUILD": (12, -6),
    "CR_LOCAL_TOPOLOGY": (-10, -26),
    "CR_ROAD_SHELL_AUDIT": (-32, -26),
    "CR_ROAD_FINALIZE": (-10, -40),
    "CR_ROAD_OUTPUT_CLASSIFY": (-10, -50),
    "CR_SIDEWALK_CLASSIFY": (18, -40),
    "CR_COLLISION_AUDIT": (-36, -60),
    "CR_SIDEWALK_SEAMS": (18, -50),
    "CR_STATIC_MARKING_MESH": (-10, -60),
    "CR_STREET_FURNITURE": (12, -60),
    "CR_MARKING_APPROACH": (-22, -76),
    "CR_SIDEWALK_AUDIT_OUTPUT": (20, -66),
    "CR_CURB_SIDEWALK_FINAL": (20, -76),
    "CR_MARKING_FINAL": (-22, -88),
    "CR_SIDEWALK_OUTPUT": (20, -88),
}

OUTPUT_SOURCES = [
    ("OUT_ROAD_CENTERLINE_GRAPH", "CR_CORRIDOR_SURFACE", 0),
    ("OUT_ROAD_COLLISION", "CR_ROAD_OUTPUT_CLASSIFY", 1),
    ("OUT_ROAD_MARKINGS", "CR_MARKING_FINAL", 0),
    ("OUT_ROAD_MARKING_POINTS", "CR_MARKING_POINTS", 0),
    ("OUT_ROAD_SURFACE", "CR_ROAD_OUTPUT_CLASSIFY", 2),
    ("OUT_SIDEWALK_CURB", "CR_SIDEWALK_OUTPUT", 0),
    ("OUT_STREET_LAMPS", "CR_STREET_FURNITURE", 1),
    ("OUT_STREET_TREES", "CR_STREET_FURNITURE", 2),
    ("OUT_STREET_TREE_PITS", "CR_STREET_FURNITURE", 0),
]

# Exact pre-v46 top-level wiring captured from the authoritative Live Scene.
# collapseIntoSubnet keeps the source nodes but Houdini can flatten Network Dot
# connections to output 0.  Reasserting this table makes every rerun restore
# the original multi-output semantics before rebuilding visual buses.
MEMBER_CONNECTIONS = {
    "IN_LAB_ROAD_TOP_UNITY_READY": [],
    "IN_LAB_SIDEWALK_CANDIDATE": [],
    "IN_LAB_TRUE_OUTER_BOUNDARY": [],
    "CR_ROAD_MATERIAL_CONTRACT": [(0, "IN_LAB_ROAD_TOP_UNITY_READY", 0), (1, "IN_LAB_TRUE_OUTER_BOUNDARY", 0)],
    "CR_INPUT_CONTRACT": [],
    "CR_GRAPH_INDEX": [(0, "CR_INPUT_CONTRACT", 0)],
    "CR_JUNCTION_INDEX": [(0, "CR_GRAPH_INDEX", 1)],
    "CR_CORRIDOR_SURFACE": [(0, "CR_JUNCTION_INDEX", 1), (1, "CR_JUNCTION_INDEX", 3), (2, "CR_GRAPH_INDEX", 1), (3, "CR_JUNCTION_INDEX", 4)],
    "CR_MARKING_HELPERS": [(0, "CR_GRAPH_INDEX", 1), (1, "CR_JUNCTION_INDEX", 4)],
    "CR_MARKING_POINTS": [(0, "CR_CORRIDOR_SURFACE", 3)],
    "CR_UNION_BOUNDARY": [(0, "CR_GRAPH_INDEX", 1), (1, "CR_CORRIDOR_SURFACE", 1), (2, "CR_CORRIDOR_SURFACE", 2), (3, "CR_CORRIDOR_SURFACE", 4)],
    "CR_SIDEWALK_SITE_OPEN_ENDS": [(0, "CR_UNION_BOUNDARY", 0), (1, "CR_ROAD_MATERIAL_CONTRACT", 0), (2, "CR_CORRIDOR_SURFACE", 1)],
    "CR_UNION_FINALIZE": [(0, "CR_UNION_BOUNDARY", 0), (1, "CR_JUNCTION_INDEX", 6), (2, "CR_CORRIDOR_SURFACE", 1), (3, "CR_UNION_BOUNDARY", 1)],
    "CR_JUNCTION_STRIP_EXTRACT": [(0, "CR_JUNCTION_INDEX", 1), (1, "CR_UNION_BOUNDARY", 1), (2, "CR_UNION_FINALIZE", 0)],
    "CR_SIDEWALK_CONSTRAINT_BUILD": [(0, "CR_UNION_BOUNDARY", 0), (1, "CR_CORRIDOR_SURFACE", 2), (2, "CR_SIDEWALK_SITE_OPEN_ENDS", 0), (3, "CR_SIDEWALK_SITE_OPEN_ENDS", 1)],
    "CR_JUNCTION_METADATA": [(0, "CR_JUNCTION_INDEX", 2), (1, "CR_JUNCTION_STRIP_EXTRACT", 0), (2, "CR_JUNCTION_INDEX", 3)],
    "CR_ROAD_CORNER_REBUILD": [(0, "CR_SIDEWALK_CONSTRAINT_BUILD", 0), (1, "CR_JUNCTION_INDEX", 0), (2, "CR_SIDEWALK_CONSTRAINT_BUILD", 2), (3, "CR_CORRIDOR_SURFACE", 0)],
    "CR_LOCAL_TOPOLOGY": [(0, "CR_JUNCTION_METADATA", 0), (1, "CR_CORRIDOR_SURFACE", 5)],
    "CR_ROAD_SHELL_AUDIT": [(0, "CR_JUNCTION_METADATA", 1), (1, "CR_CORRIDOR_SURFACE", 5)],
    "CR_ROAD_FINALIZE": [(0, "CR_JUNCTION_INDEX", 1), (1, "CR_UNION_BOUNDARY", 0), (2, "CR_LOCAL_TOPOLOGY", 0), (3, "CR_ROAD_CORNER_REBUILD", 0)],
    "CR_ROAD_OUTPUT_CLASSIFY": [(0, "CR_JUNCTION_INDEX", 2), (1, "CR_ROAD_FINALIZE", 0)],
    "CR_SIDEWALK_CLASSIFY": [(0, "CR_UNION_BOUNDARY", 0), (1, "CR_SIDEWALK_CONSTRAINT_BUILD", 1), (2, "CR_ROAD_FINALIZE", 0), (3, "CR_SIDEWALK_SITE_OPEN_ENDS", 1)],
    "CR_COLLISION_AUDIT": [(0, "CR_GRAPH_INDEX", 0), (1, "CR_ROAD_OUTPUT_CLASSIFY", 0), (2, "CR_CORRIDOR_SURFACE", 3), (3, "CR_UNION_FINALIZE", 0)],
    "CR_SIDEWALK_SEAMS": [(0, "CR_SIDEWALK_SITE_OPEN_ENDS", 0), (1, "CR_SIDEWALK_CLASSIFY", 0), (2, "CR_SIDEWALK_CONSTRAINT_BUILD", 3)],
    "CR_STATIC_MARKING_MESH": [(0, "CR_CORRIDOR_SURFACE", 3), (1, "CR_ROAD_OUTPUT_CLASSIFY", 0), (2, "CR_JUNCTION_INDEX", 3), (3, "CR_MARKING_HELPERS", 0)],
    "CR_STREET_FURNITURE": [(0, "CR_ROAD_OUTPUT_CLASSIFY", 0), (1, "CR_JUNCTION_INDEX", 5), (2, "CR_CORRIDOR_SURFACE", 0)],
    "CR_MARKING_APPROACH": [(0, "CR_JUNCTION_INDEX", 1), (1, "CR_STATIC_MARKING_MESH", 0), (2, "CR_ROAD_OUTPUT_CLASSIFY", 0), (3, "CR_JUNCTION_INDEX", 4)],
    "CR_SIDEWALK_AUDIT_OUTPUT": [(0, "CR_UNION_BOUNDARY", 0), (1, "CR_ROAD_FINALIZE", 0), (2, "CR_SIDEWALK_SITE_OPEN_ENDS", 0), (3, "CR_SIDEWALK_SEAMS", 0)],
    "CR_CURB_SIDEWALK_FINAL": [(0, "CR_UNION_BOUNDARY", 0), (1, "CR_CORRIDOR_SURFACE", 1), (2, "CR_UNION_FINALIZE", 0), (3, "CR_SIDEWALK_AUDIT_OUTPUT", 0)],
    "CR_MARKING_FINAL": [(0, "CR_STATIC_MARKING_MESH", 0), (1, "CR_MARKING_APPROACH", 0), (2, "CR_ROAD_OUTPUT_CLASSIFY", 0), (3, "CR_STATIC_MARKING_MESH", 0)],
    "CR_SIDEWALK_OUTPUT": [(0, "CR_ROAD_OUTPUT_CLASSIFY", 0), (1, "CR_CURB_SIDEWALK_FINAL", 0)],
}

PORTAL_OUTPUTS = [
    ("OUT_LAB_GRAPH", "../CR_MAIN_PIPELINE/CR_GRAPH_INDEX/"
     "SUBNET_OUT_GRAPH_CLASSIFY_JUNCTIONS_0"),
    ("OUT_LAB_ROAD_CENTERLINES", "../CR_MAIN_PIPELINE/CR_CORRIDOR_SURFACE/"
     "SUBNET_OUT_ROAD_ADAPTIVE_RESAMPLE_0"),
    ("OUT_LAB_ROAD_OUTLINES", "../CR_MAIN_PIPELINE/CR_UNION_BOUNDARY/"
     "SUBNET_OUT_ROAD_UNION_BUILD_CONSTANT_WIDTH_OUTLINES_0"),
]

TOP_POSITIONS = {
    MAIN_NAME: (-10, 22), "CR_CITY_PARK": (54, 22),
    "OUT_ROAD_CENTERLINE_GRAPH": (-48, -2), "OUT_ROAD_COLLISION": (-38, -2),
    "OUT_ROAD_MARKINGS": (-28, -2), "OUT_ROAD_MARKING_POINTS": (-18, -2),
    "OUT_ROAD_SURFACE": (-8, -2), "OUT_SIDEWALK_CURB": (2, -2),
    "OUT_STREET_LAMPS": (12, -2), "OUT_STREET_TREES": (22, -2),
    "OUT_STREET_TREE_PITS": (32, -2),
    "OUT_LAB_GRAPH": (-28, -16), "OUT_LAB_ROAD_CENTERLINES": (-12, -16),
    "OUT_LAB_ROAD_OUTLINES": (4, -16),
    "OUT_PARK_GROUND": (36, -16), "OUT_PARK_PATHS": (46, -16),
    "OUT_PARK_WATER": (56, -16), "OUT_PARK_COLLISION": (66, -16),
    "OUT_PARK_TREES": (76, -16), "OUT_PARK_EXCLUSION": (86, -16),
}

NOTES = {
    "NOTE_STAGE_01_CONTEXT": ((-54, 63), (19, 7),
        "01 CONTEXT\n输入合约 → Graph 索引 → Junction 索引 → Corridor 表面。\n"
        "右侧 IN_LAB_* 仅为 TutorialLab 调试桥；未消费的 SIDEWALK_CANDIDATE 保留并标注。"),
    "NOTE_STAGE_02_SURFACE_CONSTRAINTS": ((-54, 20), (19, 8),
        "02 SURFACE + CONSTRAINTS\n道路并集、路口条带、人行道约束、角部重建按 Cook 顺序向下。\n"
        "先看 UNION_BOUNDARY，再看 SIDEWALK_CONSTRAINT_BUILD 与 ROAD_CORNER_REBUILD。"),
    "NOTE_STAGE_03_FINALIZE": ((-54, -34), (19, 7),
        "03 FINALIZE\nROAD_FINALIZE 发布稳定道路面；随后分类、人行道、碰撞、静态标线和街具分支。\n"
        "黄色 Network Dot 是命名信号分发点，不改变几何。"),
    "NOTE_STAGE_04_CONTENT_OUTPUTS": ((-54, -72), (19, 7),
        "04 CONTENT OUTPUTS\nApproach 标线与人行道审计完成后生成最终 Marking/Sidewalk。\n"
        "正式输出继续向下进入 PUBLISH，不从输出节点反向借线。"),
    "NOTE_MAIN_PUBLISH": ((-54, -101), (19, 6),
        "05 PUBLISH\n9 个正式接口按 Road → Street 排列；3 个 Lab 门户在顶层只读发布。\n"
        "顶层 OUT_* 名称与 HDA 公共输出保持不变。"),
}


def _norm(value) -> str:
    return str(value).replace("\\", "/").lower()


def _sha256(value) -> str:
    raw = json.dumps(value, ensure_ascii=False, sort_keys=True,
                     separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def _inputs(core, node):
    result = []
    for connection in node.inputConnections():
        source = connection.inputNode()
        source_path = source.path().replace(core.path() + "/", "") if source else "<indirect>"
        result.append([connection.inputIndex(), source_path, connection.outputIndex()])
    return sorted(result)


def _baseline_payload(core):
    return {
        "top": sorted([
            [node.name(), node.type().name(), _inputs(core, node)]
            for node in core.children()
        ]),
        "subnets": {
            node.name(): sorted([[child.name(), child.type().name()]
                                 for child in node.children()])
            for node in core.children()
            if node.type().name() == "subnet" and node.name().startswith("CR_")
        },
    }


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


def _collect_core_parameter_proxies(core, members):
    """Find ../../asset-channel reads before adding the navigation level."""
    names = set()
    pattern = re.compile(r"\.\./\.\./([A-Za-z_][A-Za-z0-9_]*)")
    for member in members:
        for node in [member] + list(member.allSubChildren()):
            for parm in node.parms():
                try:
                    raw = parm.rawValue()
                except Exception:
                    continue
                if not isinstance(raw, str) or "../../" not in raw:
                    continue
                for name in pattern.findall(raw):
                    target = node.parm("../../" + name)
                    if target is not None and target.node() == core:
                        names.add(name)
    return sorted(names)


def _install_parameter_proxies(core, main, names):
    group = main.parmTemplateGroup()
    for name in names:
        source = core.parm(name)
        if source is None:
            raise RuntimeError(f"Missing CityRoadCore proxy source: {name}")
        template = source.parmTemplate()
        template.hide(True)
        group.append(template)
    main.setParmTemplateGroup(group)
    return _bind_parameter_proxies(core, main, names)


def _bind_parameter_proxies(core, main, names):
    resolved_names = list(names)
    # Cloning the tree_variants multiparm controller creates its concrete
    # instances, but their authored values are not expressions by default.
    # Bind every instance explicitly so VEX sprintf("tree_prefab%d") reads the
    # same three prefab/weight values as before the hierarchy move.
    for base in ("tree_prefab", "tree_weight"):
        index = 1
        while main.parm(f"{base}{index}") is not None:
            name = f"{base}{index}"
            if core.parm(name) is None:
                raise RuntimeError(f"Missing CityRoadCore multiparm proxy source: {name}")
            if name not in resolved_names:
                resolved_names.append(name)
            index += 1
    for name in resolved_names:
        target = main.parm(name)
        source = core.parm(name)
        if target is None or source is None:
            raise RuntimeError(f"Failed to create CityRoadCore proxy: {name}")
        template_type = target.parmTemplate().type()
        expression = (f'chs("../{name}")'
                      if template_type == hou.parmTemplateType.String
                      else f'ch("../{name}")')
        target.setExpression(expression, language=hou.exprLanguage.Hscript)
    resolved_names = sorted(resolved_names)
    main.setUserData("cityroad_v46_proxy_parameters", json.dumps(resolved_names))
    return resolved_names


def _resolve_signal_name(source, output_index):
    visited = set()
    while source is not None and source.type().name() == "subnet":
        if source.path() in visited:
            return source.name()
        visited.add(source.path())
        match = None
        for child in source.children():
            if child.type().name() != "output":
                continue
            parm = child.parm("outputidx")
            index = int(parm.eval()) if parm is not None else 0
            if index == output_index:
                match = child
                break
        if match is None or not match.inputConnections():
            return source.name()
        connection = match.inputConnections()[0]
        source = connection.inputNode()
        output_index = connection.outputIndex()
    return source.name() if source is not None else "UNCONNECTED"


def _refresh_semantic_labels(main):
    for subnet in [main] + [node for node in main.allSubChildren()
                            if node.type().name() == "subnet" and
                            node.name().startswith("CR_")]:
        for connection in subnet.inputConnections():
            label = subnet.parm(f"label{connection.inputIndex() + 1}")
            if label is not None:
                label.set(_resolve_signal_name(
                    connection.inputNode(), connection.outputIndex()))


def _configure_main_outputs(core, main):
    output_nodes = [node for node in main.children()
                    if node.type().name() == "output"]
    # All Lab outputs are explicit read-only portals.  Recreate the main
    # connector set deterministically so TutorialLab can read internal leaves
    # without cooking the CR_MAIN_PIPELINE container back through IN_LAB_*.
    if (len(output_nodes) != len(OUTPUT_SOURCES) or
            {node.name() for node in output_nodes} != {
                f"SUBNET_{name}_{index}"
                for index, (name, _, _) in enumerate(OUTPUT_SOURCES)}):
        for output in output_nodes:
            output.destroy()
        output_nodes = [main.createNode("output", f"V46_TMP_OUTPUT_{index}")
                        for index in range(len(OUTPUT_SOURCES))]
    output_nodes = sorted(
        output_nodes, key=lambda node: int(node.parm("outputidx").eval()))
    for index, output in enumerate(output_nodes):
        output.setName(f"V46_TMP_OUTPUT_{index}", unique_name=False)
    for index, (top_name, source_name, source_output) in enumerate(OUTPUT_SOURCES):
        output = output_nodes[index]
        source = main.node(source_name)
        if source is None or core.node(top_name) is None:
            raise RuntimeError(f"Missing v46 output endpoint: {top_name}/{source_name}")
        output.parm("outputidx").set(index)
        output.setInput(0, source, source_output)
        output.setName(f"SUBNET_{top_name}_{index}", unique_name=False)
        output.setComment(
            f"{top_name} | CR_MAIN_PIPELINE 显式发布接口 {index}；"
            f"来源 {source_name}[{source_output}]。")
        output.setGenericFlag(hou.nodeFlag.DisplayComment, True)
        output.setPosition(hou.Vector2((-44 + index * 8, -108)))
    # Houdini refreshes a subnet's dynamic output connector table only after
    # all Output SOPs are configured.  Reconnect the public OUT_* nodes in a
    # second pass so the previously-empty centerline connector is valid.
    main.cook(force=True)
    for index, (top_name, _source_name, _source_output) in enumerate(OUTPUT_SOURCES):
        top = core.node(top_name)
        try:
            top.setInput(0, main, index)
        except hou.InvalidInput as exc:
            raise RuntimeError(
                f"CR_MAIN_PIPELINE output {index} is unavailable for {top_name}; "
                f"available={main.outputNames()}") from exc


def _configure_debug_portals(core):
    for name, object_path in PORTAL_OUTPUTS:
        node = core.node(name)
        if node is not None and node.type().name() != "object_merge":
            position = node.position()
            node.destroy()
            node = core.createNode("object_merge", name)
            node.setPosition(position)
        elif node is None:
            node = core.createNode("object_merge", name)
        node.parm("xformtype").set("none")
        node.parm("objpath1").set(object_path)
        node.setComment(
            "TutorialLab 只读调试门户：直接读取 CR_MAIN_PIPELINE 内的叶输出。\n"
            "门户不参与生产阶段依赖，避免 Debug 回读触发主 Subnet 的循环 Cook。")
        node.setGenericFlag(hou.nodeFlag.DisplayComment, True)


def _restore_member_connections(main):
    """Restore the exact captured source and output index for every module."""
    for destination_name, expected in MEMBER_CONNECTIONS.items():
        destination = main.node(destination_name)
        if destination is None:
            raise RuntimeError(f"Missing v46 connection destination: {destination_name}")
        # Disconnect first even when the source node name is unchanged.
        # Houdini otherwise keeps the old cooked indirect-input cache when
        # only a subnet output index changes from 0 to a non-zero connector.
        for connection in list(destination.inputConnections()):
            destination.setInput(connection.inputIndex(), None)
        for input_index, source_name, output_index in expected:
            source = main.node(source_name)
            if source is None:
                raise RuntimeError(
                    f"Missing v46 connection source: {destination_name}/{source_name}")
            destination.setInput(input_index, source, output_index)


def _directify_and_rebuild_buses(main):
    connections = []
    for destination in main.children():
        for connection in destination.inputConnections():
            source = connection.inputNode()
            if source is not None and source.parent() == main:
                connections.append((destination, connection.inputIndex(),
                                    source, connection.outputIndex()))
    for dot in list(main.networkDots()):
        if not dot.name().startswith("CR_BUS_"):
            raise RuntimeError(f"Unexpected user Network Dot in v46 scope: {dot.name()}")
        dot.destroy()
    for destination, input_index, source, output_index in connections:
        destination.setInput(input_index, source, output_index)

    fanout = {}
    for destination in main.children():
        for connection in destination.inputConnections():
            source = connection.inputNode()
            if source is None or source.parent() != main or source.type().name() == "output":
                continue
            fanout.setdefault((source, connection.outputIndex()), []).append(
                (destination, connection.inputIndex()))
    created = 0
    for (source, output_index), destinations in sorted(
            fanout.items(), key=lambda item: (item[0][0].name(), item[0][1])):
        # Houdini 21 Network Dot routing flattens a SOP subnet's non-zero
        # output connector to output 0.  Keep those dependencies direct;
        # output-0 fanouts can be safely routed through semantic buses.
        if len(destinations) < 2 or output_index != 0:
            continue
        dot = main.createNetworkDot()
        safe_name = re.sub(r"[^A-Za-z0-9_]", "_", source.name())
        dot.setName(f"CR_BUS_{safe_name}_O{output_index}", unique_name=False)
        dot.setInput(source, output_index)
        position = source.position()
        dot.setPosition(hou.Vector2((float(position.x()) + 2.5 + output_index * 1.2,
                                     float(position.y()) - 4.0 - output_index * 0.5)))
        for destination, input_index in destinations:
            destination.setInput(input_index, dot, 0)
        created += 1
    return created


def _rebuild_visuals(core, main):
    for name, position in MAIN_POSITIONS.items():
        node = main.node(name)
        if node is None:
            raise RuntimeError(f"Missing v46 main layout node: {name}")
        node.setPosition(hou.Vector2(position))

    for box in list(main.networkBoxes()):
        if box.name().startswith("AREA_"):
            box.destroy()
    for name, members in STAGES.items():
        box = main.createNetworkBox(name)
        box.setComment(STAGE_LABELS[name])
        box.setColor(hou.Color(STAGE_COLORS[name]))
        for member in members:
            node = main.node(member)
            if node is None:
                raise RuntimeError(f"Missing stage member: {name}/{member}")
            node.setColor(hou.Color(STAGE_COLORS[name]))
            box.addItem(node)
        box.fitAroundContents()
    publish = main.createNetworkBox("AREA_MAIN_PUBLISH")
    publish.setComment(STAGE_LABELS["AREA_MAIN_PUBLISH"])
    publish.setColor(hou.Color(STAGE_COLORS["AREA_MAIN_PUBLISH"]))
    for output in [node for node in main.children() if node.type().name() == "output"]:
        publish.addItem(output)
    publish.fitAroundContents()

    for note in list(main.stickyNotes()):
        if note.name().startswith("NOTE_STAGE_") or note.name() == "NOTE_MAIN_PUBLISH":
            note.destroy()
    for name, (position, size, text) in NOTES.items():
        note = main.createStickyNote()
        note.setName(name, unique_name=False)
        note.setPosition(hou.Vector2(position))
        note.setSize(size)
        note.setText(text)
        note.setTextSize(0.55)
        note.setColor(hou.Color((0.16, 0.18, 0.22)))

    for name, position in TOP_POSITIONS.items():
        node = core.node(name)
        if node is None:
            raise RuntimeError(f"Missing v46 top layout node: {name}")
        node.setPosition(hou.Vector2(position))
    for box in list(core.networkBoxes()):
        if box.name().startswith("AREA_") or box.name().startswith("OVERVIEW_"):
            box.destroy()
    top_boxes = {
        "OVERVIEW_MAIN": [MAIN_NAME],
        "OVERVIEW_ROAD_OUTPUTS": ([name for name, _, _ in OUTPUT_SOURCES] +
                                  [name for name, _ in PORTAL_OUTPUTS]),
        "OVERVIEW_PARK": ["CR_CITY_PARK", "OUT_PARK_GROUND", "OUT_PARK_PATHS",
                          "OUT_PARK_WATER", "OUT_PARK_COLLISION",
                          "OUT_PARK_TREES", "OUT_PARK_EXCLUSION"],
    }
    for name, members in top_boxes.items():
        box = core.createNetworkBox(name)
        box.setComment(name.replace("OVERVIEW_", ""))
        for member in members:
            box.addItem(core.node(member))
        box.fitAroundContents()
    for note in list(core.stickyNotes()):
        if note.name().startswith("NOTE_CITYROAD_") or note.name() == "NOTE_V46_OVERVIEW":
            note.destroy()
    note = core.createStickyNote()
    note.setName("NOTE_V46_OVERVIEW", unique_name=False)
    note.setPosition(hou.Vector2((-48, 33)))
    note.setSize((34, 9))
    note.setText(
        "CityRoadCore 总览 / V46\n"
        "① CR_MAIN_PIPELINE：道路、路口、人行道、标线、碰撞与街具。\n"
        "② CR_CITY_PARK：独立公园分支。\n"
        "③ OUT_*：公共输出顺序不变。双击 MAIN 后按 01→05 纵向阅读。")
    note.setTextSize(0.6)
    note.setColor(hou.Color((0.15, 0.18, 0.24)))


def _repair_lab_paths(main):
    for name in ("IN_LAB_ROAD_TOP_UNITY_READY", "IN_LAB_SIDEWALK_CANDIDATE",
                 "IN_LAB_TRUE_OUTER_BOUNDARY"):
        node = main.node(name)
        parm = node.parm("objpath1") if node is not None else None
        if parm is None:
            raise RuntimeError(f"Missing TutorialLab bridge: {name}")
        value = parm.evalAsString()
        if value.startswith("../../CityRoadTutorialLab/"):
            parm.set("../" + value)
        if not parm.evalAsString().startswith("../../../CityRoadTutorialLab/"):
            raise RuntimeError(f"Unexpected TutorialLab bridge path: {name}")
    candidate = main.node("IN_LAB_SIDEWALK_CANDIDATE")
    candidate.setComment(
        "TutorialLab 调试桥：当前生产网络未消费该输入；为教学和兼容性保留，不删除。")
    candidate.setGenericFlag(hou.nodeFlag.DisplayComment, True)


def _restore_structural_reference_state(main):
    """Undo two collapseIntoSubnet UI side effects that are not semantic moves."""
    resample = main.node("CR_CORRIDOR_SURFACE/ROAD_ADAPTIVE_RESAMPLE")
    resample.parm("length").setExpression(
        'detail("../ROAD_RESAMPLE_BUDGET","effective_sample_spacing",0)',
        language=hou.exprLanguage.Hscript)
    street = main.node("CR_STREET_FURNITURE")
    street.setDisplayFlag(False)
    street.setRenderFlag(False)
    corridor = main.node("CR_CORRIDOR_SURFACE")
    corridor.setDisplayFlag(False)
    corridor.setRenderFlag(False)


def _validate(core, main, proxy_names, bus_count):
    expected_top = {MAIN_NAME, "CR_CITY_PARK"} | {
        name for name in TOP_POSITIONS if name.startswith("OUT_")}
    actual_top = {node.name() for node in core.children()}
    if len(actual_top) != 20 or actual_top != expected_top:
        raise RuntimeError(f"V46 top-level membership mismatch: {sorted(actual_top)}")
    if len(main.inputConnections()) != 0:
        raise RuntimeError("CR_MAIN_PIPELINE must have no hidden/external inputs")
    if len([node for node in main.children() if node.type().name() == "output"]) != 9:
        raise RuntimeError("CR_MAIN_PIPELINE output count changed")
    for index, (top_name, source_name, source_output) in enumerate(OUTPUT_SOURCES):
        top = core.node(top_name)
        connections = top.inputConnections()
        if (len(connections) != 1 or connections[0].inputNode() != main or
                connections[0].outputIndex() != index):
            raise RuntimeError(f"V46 top output mapping changed: {top_name}")
        output = next(node for node in main.children()
                      if node.type().name() == "output" and
                      int(node.parm("outputidx").eval()) == index)
        source_connections = output.inputConnections()
        if (len(source_connections) != 1 or
                source_connections[0].inputNode().name() != source_name or
                source_connections[0].outputIndex() != source_output):
            raise RuntimeError(f"V46 main output source changed: {top_name}")
    for portal_name, portal_path in PORTAL_OUTPUTS:
        portal = core.node(portal_name)
        if (portal is None or portal.type().name() != "object_merge" or
                portal.parm("objpath1").evalAsString() != portal_path):
            raise RuntimeError(f"V46 Lab debug portal changed: {portal_name}")
    if len(core.node("CR_CITY_PARK").inputConnections()) != 0:
        raise RuntimeError("City Park branch changed during core hierarchy migration")
    for destination_name, expected in MEMBER_CONNECTIONS.items():
        destination = main.node(destination_name)
        actual = sorted([
            (connection.inputIndex(), connection.inputNode().name(),
             connection.outputIndex())
            for connection in destination.inputConnections()
        ])
        if actual != expected:
            raise RuntimeError(
                f"V46 member connection changed: {destination_name}; actual={actual}")
    for name in proxy_names:
        target = main.parm(name)
        source = core.parm(name)
        if target is None or source is None or target.eval() != source.eval():
            raise RuntimeError(f"V46 proxy parameter mismatch: {name}")
    for stage_name, members in STAGES.items():
        box = next((box for box in main.networkBoxes() if box.name() == stage_name), None)
        if box is None or {item.name() for item in box.items()} != set(members):
            raise RuntimeError(f"V46 stage membership changed: {stage_name}")
    if len(core.children()) != 20 or sum(len(n.inputConnections()) for n in core.children()) != 15:
        raise RuntimeError("V46 overview node/connection budget exceeded")
    if bus_count < 7:
        raise RuntimeError(f"V46 semantic bus coverage is too small: {bus_count}")
    if core.node("CityRoadTutorialLa") is not None:
        raise RuntimeError("CityRoadTutorialLa unexpectedly appeared inside CityRoadCore")
    return {
        "top_level_nodes": len(core.children()),
        "top_level_connections": sum(len(n.inputConnections()) for n in core.children()),
        "main_function_subnets": len([
            node for node in main.children()
            if node.type().name() == "subnet" and node.name().startswith("CR_")]),
        "main_output_ports": 9,
        "logical_top_dependencies": 18,
        "semantic_buses": bus_count,
        "proxy_parameters": len(proxy_names),
        "tutorial_lab_node_untouched": True,
    }


def _clear_old_core_visuals(core):
    for box in list(core.networkBoxes()):
        if box.name().startswith("AREA_") or box.name().startswith("OVERVIEW_"):
            box.destroy()
    for note in list(core.stickyNotes()):
        if note.name().startswith("NOTE_CITYROAD_") or note.name() == "NOTE_V46_OVERVIEW":
            note.destroy()


def _apply_live_patch_impl(save=False, capture_verified_dirty=False,
                           hou_module=None):
    global hou
    if hou_module is not None:
        hou = hou_module
    if hou is None:
        raise RuntimeError("The hou module is unavailable")
    if save:
        raise RuntimeError("V46 patch is save=False only; use the regression gate")
    _asset, core = _require_identity()
    main = core.node(MAIN_NAME)
    marker = core.userData("cityroad_three_level_readability_marker")
    if marker == MARKER:
        if main is None:
            raise RuntimeError("V46 marker exists without CR_MAIN_PIPELINE")
        proxy_names = json.loads(main.userData("cityroad_v46_proxy_parameters") or "[]")
        proxy_names = _bind_parameter_proxies(core, main, proxy_names)
        _configure_main_outputs(core, main)
        _configure_debug_portals(core)
        _repair_lab_paths(main)
        _restore_structural_reference_state(main)
        _rebuild_visuals(core, main)
        _restore_member_connections(main)
        bus_count = _directify_and_rebuild_buses(main)
        _refresh_semantic_labels(main)
        result = _validate(core, main, proxy_names, bus_count)
        result.update({"status": "PASS", "already_applied": True, "saved": False})
        return result
    if main is not None:
        raise RuntimeError("CR_MAIN_PIPELINE exists without the v46 marker")
    if not capture_verified_dirty:
        raise RuntimeError("V46 requires an explicit Capture-verified Live Scene")
    actual_sha = _sha256(_baseline_payload(core))
    if actual_sha != BASELINE_SHA256:
        raise RuntimeError(f"V46 Live baseline changed: {actual_sha} != {BASELINE_SHA256}")

    members = [node for node in core.children()
               if node.name() != "CR_CITY_PARK" and not node.name().startswith("OUT_")]
    if len(members) != 31:
        raise RuntimeError(f"V46 expected 31 main members, found {len(members)}")
    proxy_names = _collect_core_parameter_proxies(core, members)
    if len(proxy_names) < 20:
        raise RuntimeError("V46 failed to capture the CityRoadCore channel proxy set")

    try:
        with hou.undos.group("CityRoadCore Three-Level Readability V46"):
            _clear_old_core_visuals(core)
            dots = list(core.networkDots())
            if any(not dot.name().startswith("CR_BUS_") for dot in dots):
                raise RuntimeError("Unexpected user Network Dot in v46 collapse scope")
            main = core.collapseIntoSubnet(members + dots, MAIN_NAME)
            main.setComment(
                "CR_MAIN_PIPELINE | CityRoad 道路生产总管线\n"
                "内部按 01 Context → 02 Surface/Constraints → 03 Finalize → "
                "04 Content Outputs → 05 Publish 阅读。\n"
                "阶段使用 Network Box，避免标准 SOP Subnet 四输入限制引入隐藏依赖。")
            main.setGenericFlag(hou.nodeFlag.DisplayComment, True)
            main.setColor(hou.Color((0.18, 0.52, 0.78)))
            proxy_names = _install_parameter_proxies(core, main, proxy_names)
            _configure_main_outputs(core, main)
            _configure_debug_portals(core)
            _repair_lab_paths(main)
            _restore_structural_reference_state(main)
            _rebuild_visuals(core, main)
            _restore_member_connections(main)
            bus_count = _directify_and_rebuild_buses(main)
            _refresh_semantic_labels(main)
            core.setUserData("cityroad_three_level_readability_marker", MARKER)
            result = _validate(core, main, proxy_names, bus_count)
    except Exception:
        try:
            hou.undos.performUndo()
        finally:
            raise
    result.update({"status": "PASS", "already_applied": False,
                   "saved": False, "marker": MARKER})
    return result


def apply_live_patch(save=False, capture_verified_dirty=False, hou_module=None):
    """Apply atomically while suppressing GUI auto-cooks of half-moved graphs."""
    global hou
    if hou_module is not None:
        hou = hou_module
    if hou is None:
        raise RuntimeError("The hou module is unavailable")
    previous_mode = hou.updateModeSetting()
    hou.setUpdateMode(hou.updateMode.Manual)
    try:
        return _apply_live_patch_impl(
            save=save,
            capture_verified_dirty=capture_verified_dirty,
            hou_module=hou)
    finally:
        hou.setUpdateMode(previous_mode)


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
            "import patch_cityroad_three_level_readability_v46_20260824 as _cityroad_v46; "
            "importlib.reload(_cityroad_v46)")
        payload = connection.eval(
            "_cityroad_v46.apply_live_patch(save=False, capture_verified_dirty="
            f"{args.capture_verified_dirty.lower() == 'true'!r})")
        print(json.dumps(payload, ensure_ascii=False, default=list, indent=2))
    finally:
        connection.close()


if __name__ == "__main__":
    main()
