"""One-level CityRoadCore subnet/layout migration.

The current unlocked Live network is the only implementation source.  The
migration is deliberately structural: it preserves every original leaf node,
parameter, flag and logical connection, adds explicit subnet interfaces, and
defaults to ``save=False``.  A failed migration is undone as one Houdini undo
group; HDA definition and HIP persistence are separate, post-VerifyFull steps.
"""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any

import hou


ASSET_PATH = "/obj/CityRoad_DEV"
ASSET_TYPE = "pcgbike::CityRoad::1.0"
CORE_NAME = "CityRoadCore"
MARKER = "CITYROAD_SUBNET_LAYOUT_V19_20260813"
SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = SCRIPT_DIR.parents[3]
LAYOUT_CONTRACT = SCRIPT_DIR.parent / "contracts/cityroad_subnet_layout_contract.json"
EXPECTED_HIP = PROJECT_ROOT / "HoudiniProject/PCG_Track_21.0.440/PCG_Bike_CityRoad.hip"
EXPECTED_HDA = PROJECT_ROOT / "Assets/PCG/HDA/City/CityRoad.hda"


SUBNET_DESCRIPTIONS = {
    "CR_INPUT_CONTRACT": "输入选择、必填校验与道路数据合约初始化",
    "CR_GRAPH_INDEX": "中心线清理、重采样、线段空间索引与路口分类",
    "CR_JUNCTION_INDEX": "稳定路口、Approach 与路口边界索引",
    "CR_CORRIDOR_SURFACE": "道路走廊区间、基础路面与自适应弯角表面",
    "CR_UNION_BOUNDARY": "道路并集可见边界提取与最终边界圆角",
    "CR_UNION_FINALIZE": "道路并集三角化、墙面、元数据与法线收尾",
    "CR_JUNCTION_STRIP_EXTRACT": "从道路结果提取并统一路口条带朝向",
    "CR_JUNCTION_METADATA": "路口材质、UV、拓扑和属性对齐",
    "CR_ROAD_SHELL_AUDIT": "道路壳体融合、外边界提取与完整性检查",
    "CR_LOCAL_TOPOLOGY": "Corridor/Junction 局部拓扑融合与法线",
    "CR_ROAD_BOUNDARY_PARTITION": "最终道路边界约束的合并、融合与三角化",
    "CR_ROAD_FINALIZE": "Unity 绕序、投影、属性转移与道路最终面",
    "CR_ROAD_OUTPUT_CLASSIFY": "道路拓扑分片、Pack 与碰撞语义分类",
    "CR_SIDEWALK_SITE_OPEN_ENDS": "人行道场地布尔、道路端口与开口连接线",
    "CR_SIDEWALK_CONSTRAINT_BUILD": "人行道二维约束、角部截面与确定性条带",
    "CR_SIDEWALK_CLASSIFY": "人行道内外区域分类与无用点清理",
    "CR_SIDEWALK_SEAMS": "端口包含性校验与人行道接缝标记",
    "CR_SIDEWALK_AUDIT_OUTPUT": "人行道拓扑审计、回滚选择与区域连通",
    "CR_CURB_SIDEWALK_FINAL": "路缘/人行道生成、材质元数据、绕序与法线",
    "CR_MARKING_HELPERS": "标线分支共享的图属性与 Approach 辅助数据",
    "CR_MARKING_APPROACH": "中心线、车道线、边缘线与路口标线候选",
    "CR_MARKING_FINAL": "标线绕序、开关、拓扑传递与 Pack 输出",
    "CR_MARKING_POINTS": "道路标线实例点采样与输出合约",
    "CR_COLLISION_AUDIT": "移动端道路碰撞简化、退化面清理与属性传递",
    "CR_STREET_FURNITURE": "路灯、树木、树池共享采样及分支开关",
    "CR_ROAD_MATERIAL_CONTRACT": "道路顶点着色、材质与输出属性合约",
    "CR_SIDEWALK_OUTPUT": "人行道材质、拓扑属性传递与 Pack 输出"
}

COLORS = {
    "input": hou.Color((0.24, 0.48, 0.82)),
    "index": hou.Color((0.16, 0.68, 0.72)),
    "road": hou.Color((0.92, 0.48, 0.18)),
    "junction": hou.Color((0.94, 0.30, 0.16)),
    "sidewalk": hou.Color((0.28, 0.68, 0.32)),
    "marking": hou.Color((0.90, 0.74, 0.20)),
    "street": hou.Color((0.57, 0.34, 0.76)),
    "contract": hou.Color((0.48, 0.50, 0.54)),
}

PROXY_NAMES = [
    "center_line_width", "crosswalk_depth", "crosswalk_setback",
    "crosswalk_side_margin", "crosswalk_stripe_gap", "crosswalk_stripe_width",
    "curb_height", "curb_unity_material", "curb_width",
    "debug_show_corner_topology", "default_lane_count", "default_road_level",
    "default_road_width", "edge_line_width", "enable_adaptive_corner_topology",
    "enable_cross_junction", "enable_crosswalks", "enable_curb",
    "enable_intersections", "enable_road_markings", "enable_sidewalk",
    "enable_street_lamps", "enable_street_trees", "enable_t_junction",
    "endpoint_snap_tolerance", "facility_edge_inset", "intersection_detect_radius",
    "junction_corner_radius", "junction_endpoint_clearance",
    "junction_sample_spacing", "lamp_prefab", "lamp_spacing",
    "lamp_tree_clearance", "lamp_yaw_offset", "lane_line_width",
    "marking_dash_gap", "marking_dash_length", "marking_height_offset",
    "marking_unity_material", "minimum_segment_length", "minimum_sidewalk_width",
    "remove_short_segments", "road_corner_inner_radius_ratio",
    "road_crossfall_percent", "road_network_source", "road_thickness",
    "road_unity_material", "sample_spacing", "sidewalk_height",
    "sidewalk_unity_material", "sidewalk_width", "stop_line_gap",
    "stop_line_width", "tree_pit_prefab", "tree_pit_probability",
    "tree_scale_max", "tree_scale_min", "tree_seed", "tree_spacing_max",
    "tree_spacing_min", "tree_variants", "unity_road_network"
]

SPECIAL_COMMENTS = {
    "GRAPH_CLASSIFY_JUNCTIONS": (
        "GRAPH_CLASSIFY_JUNCTIONS | 路口候选分类\n"
        "pcfind 对线段中点做宽相位查询，再执行精确 XZ 线段相交与端点投影；"
        "保持稳定的道路对/线段对注册顺序。"),
    "ROAD_MARKING_POINTS_BUILD": (
        "ROAD_MARKING_POINTS_BUILD | 道路标线实例点\n"
        "只输出道路标线采样点；路灯、树木与树池由 CR_STREET_FURNITURE 独立生成。"),
    "CITYROAD_GRAPH_V1_V2": (
        "CITYROAD_GRAPH_V1_V2 | 图索引生产/回滚切换\n"
        "默认输入 1 为 V2 生产路径；输入 0 仅供内部回滚，不提升为公共参数。"),
    "CITYROAD_ROAD_SURFACE_V1_V2": (
        "CITYROAD_ROAD_SURFACE_V1_V2 | 道路表面生产/回滚切换\n"
        "默认输入 1 为 Corridor Interval 生产路径；输入 0 为内部旧实现。"),
    "CITYROAD_ADAPTIVE_SURFACE_V1_V2": (
        "CITYROAD_ADAPTIVE_SURFACE_V1_V2 | 弯角表面生产/回滚切换\n"
        "默认输入 1 为索引化生产路径；输入 0 为内部旧实现。"),
    "CITYROAD_SIDEWALK_AUDIT_V1_V2": (
        "CITYROAD_SIDEWALK_AUDIT_V1_V2 | 人行道审计生产/回滚切换\n"
        "默认输入 1 为已验证生产结果；输入 0 为内部审计回滚路径。"),
    "CITYROAD_CROSSWALK_ENABLE_V2": "CITYROAD_CROSSWALK_ENABLE_V2 | 斑马线分支提前开关",
    "CITYROAD_MARKING_ENABLE_V2": "CITYROAD_MARKING_ENABLE_V2 | 道路标线分支提前开关",
    "CITYROAD_STREET_LAMP_ENABLE_V2": "CITYROAD_STREET_LAMP_ENABLE_V2 | 路灯分支提前开关",
    "CITYROAD_STREET_TREE_ENABLE_V2": "CITYROAD_STREET_TREE_ENABLE_V2 | 树木分支提前开关",
    "CITYROAD_BUILD_JUNCTION_SURFACE_BOUNDARY_V5": "CITYROAD_BUILD_JUNCTION_SURFACE_BOUNDARY_V5 | 路口表面边界与 Approach 裁切基准",
    "CITYROAD_BUILD_JUNCTION_PARTITION_CUTS_V7": "CITYROAD_BUILD_JUNCTION_PARTITION_CUTS_V7 | 路口分区裁切线构建",
    "CITYROAD_REPLACE_SIDEWALK_CORNER_WITH_QUAD_STRIPS_V11": "CITYROAD_REPLACE_SIDEWALK_CORNER_WITH_QUAD_STRIPS_V11 | 确定性人行道角部四边形条带",
    "CITYROAD_REPLACE_CORNER_WITH_QUAD_STRIPS_V11": "CITYROAD_REPLACE_CORNER_WITH_QUAD_STRIPS_V11 | 道路角部四边形条带关键汇合",
    "CITYROAD_SNAP_FINAL_BOUNDARY_TO_CORNER_SECTIONS_V12": "CITYROAD_SNAP_FINAL_BOUNDARY_TO_CORNER_SECTIONS_V12 | 最终边界对齐共享角部截面",
    "CITYROAD_FUSE_FINAL_BOUNDARY_CORNER_SECTIONS_V12": "CITYROAD_FUSE_FINAL_BOUNDARY_CORNER_SECTIONS_V12 | 共享角部边界融合",
}

OUTPUT_COMMENTS = {
    "OUT_ROAD_CENTERLINE_GRAPH": "OUT_ROAD_CENTERLINE_GRAPH | 正式输出：稳定道路中心线图与路口索引元数据。",
    "OUT_ROAD_SURFACE": "OUT_ROAD_SURFACE | 正式输出：Unity 道路表面拓扑分片与材质合约。",
    "OUT_SIDEWALK_CURB": "OUT_SIDEWALK_CURB | 正式输出：路缘和人行道拓扑分片。",
    "OUT_ROAD_COLLISION": "OUT_ROAD_COLLISION | 正式输出：移动端简化道路碰撞几何。",
    "OUT_ROAD_MARKINGS": "OUT_ROAD_MARKINGS | 正式输出：道路标线网格与材质元数据。",
    "OUT_ROAD_MARKING_POINTS": "OUT_ROAD_MARKING_POINTS | 正式输出：道路标线实例点，不包含街具。",
    "OUT_STREET_LAMPS": "OUT_STREET_LAMPS | 正式输出：路灯实例点。",
    "OUT_STREET_TREES": "OUT_STREET_TREES | 正式输出：行道树实例点。",
    "OUT_STREET_TREE_PITS": "OUT_STREET_TREE_PITS | 正式输出：树池实例点。",
    "OUT_LAB_GRAPH": "OUT_LAB_GRAPH | TutorialLab 桥接输出：中心线图调试数据。",
    "OUT_LAB_ROAD_CENTERLINES": "OUT_LAB_ROAD_CENTERLINES | TutorialLab 桥接输出：道路中心线。",
    "OUT_LAB_ROAD_OUTLINES": "OUT_LAB_ROAD_OUTLINES | TutorialLab 桥接输出：道路轮廓。",
}

VALIDATION_PYTHON = '''node = hou.pwd()
geo = node.geometry()
if geo is None or (not geo.prims() and not geo.points()):
    root = node
    while root is not None and root.parm("road_network_source") is None:
        root = root.parent()
    source = "External / IN_ROAD_NETWORK"
    source_parm = root.parm("road_network_source") if root else None
    if source_parm is not None and int(source_parm.eval()) == 1:
        source = "Internal / CR_INPUT_CONTRACT/INTERNAL_ROAD_NETWORK_CURVE"
    raise hou.NodeError(
        "CityRoad: selected Road Network source is empty / 当前选择的道路网络来源为空。 "
        "Source: %s. External mode requires the unity_road_network Spline parameter; "
        "Internal mode requires CityRoadCore/CR_INPUT_CONTRACT/INTERNAL_ROAD_NETWORK_CURVE."
        % source)
'''


def _norm(path: str | Path) -> str:
    return str(path).replace("\\", "/").lower()


def _load_contract() -> dict[str, Any]:
    data = json.loads(LAYOUT_CONTRACT.read_text(encoding="utf-8"))
    if data.get("schema_version") != 1:
        raise RuntimeError("Unsupported CityRoad subnet layout contract")
    return data


def _require_live_baseline(contract: dict[str, Any]) -> tuple[hou.Node, hou.Node]:
    asset = hou.node(ASSET_PATH)
    if asset is None or asset.type().name() != ASSET_TYPE:
        raise RuntimeError(f"Expected {ASSET_TYPE} at {ASSET_PATH}")
    core = asset.node(CORE_NAME)
    if core is None:
        raise RuntimeError("CityRoadCore is missing")
    definition = asset.type().definition()
    if definition is None or _norm(definition.libraryFilePath()) != _norm(EXPECTED_HDA):
        raise RuntimeError("CityRoad definition does not match the production HDA")
    if _norm(hou.hipFile.path()) != _norm(EXPECTED_HIP):
        raise RuntimeError("Current HIP is not the production CityRoad HIP")

    direct = {node.name() for node in core.children()}
    if set(contract["subnets"]).issubset(direct):
        return asset, core
    expected_members = {name for names in contract["subnets"].values() for name in names}
    expected_direct = expected_members | set(contract["preserved_top_level"])
    if len(direct) != 208 or direct != expected_direct:
        missing = sorted(expected_direct - direct)
        extra = sorted(direct - expected_direct)
        raise RuntimeError(
            f"CityRoadCore precondition mismatch: count={len(direct)} "
            f"missing={missing[:8]} extra={extra[:8]}")
    # Houdini can mark editable HDAs dirty while loading them in disposable
    # non-UI hython.  The production GUI must still be byte-clean here.
    if hou.isUIAvailable() and hou.hipFile.hasUnsavedChanges():
        raise RuntimeError("Live HIP must be clean before applying the layout patch")
    return asset, core


def _snapshot_connections(core: hou.Node) -> list[tuple[str, int, str, int]]:
    result = []
    for destination in core.children():
        for connection in destination.inputConnections():
            source = connection.inputNode()
            if source is None or source.parent() != core:
                raise RuntimeError(f"Unexpected non-local input at {destination.path()}")
            result.append((
                destination.name(), connection.inputIndex(),
                source.name(), connection.outputIndex()))
    return sorted(result)


def _add_internal_proxies(asset: hou.Node, core: hou.Node) -> None:
    existing = core.parmTemplateGroup()
    if existing.find("cityroad_layout_marker") is not None:
        return
    source_group = asset.parmTemplateGroup()
    templates = []
    marker = hou.StringParmTemplate("cityroad_layout_marker", "CityRoad Layout Marker", 1,
                                    default_value=(MARKER,))
    marker.hide(True)
    templates.append(marker)
    for name in PROXY_NAMES:
        source = source_group.find(name)
        if source is None:
            raise RuntimeError(f"Cannot create CityRoadCore proxy; public parm missing: {name}")
        clone = source.clone()
        clone.hide(True)
        templates.append(clone)
    folder = hou.FolderParmTemplate(
        "cityroad_subnet_proxies", "CityRoad Subnet Proxies", tuple(templates),
        folder_type=hou.folderType.Simple)
    folder.hide(True)
    existing.append(folder)
    core.setParmTemplateGroup(existing)
    for name in PROXY_NAMES:
        target = core.parm(name)
        source = asset.parm(name)
        if target is None or source is None:
            raise RuntimeError(f"Failed to instantiate CityRoadCore proxy: {name}")
        expression = f'chs("../{name}")' if target.parmTemplate().type() == hou.parmTemplateType.String else f'ch("../{name}")'
        target.setExpression(expression, language=hou.exprLanguage.Hscript)
        target.eval()
    # The public tree-variant multiparm owns generated tree_prefabN/tree_weightN
    # children.  Mirror each instantiated child without promoting a new API.
    for source in asset.parms():
        if re.fullmatch(r"tree_(?:prefab|weight)\d+", source.name()):
            target = core.parm(source.name())
            if target is None:
                raise RuntimeError(f"Failed to instantiate tree variant proxy: {source.name()}")
            expression = (f'chs("../{source.name()}")'
                          if target.parmTemplate().type() == hou.parmTemplateType.String
                          else f'ch("../{source.name()}")')
            target.setExpression(expression, language=hou.exprLanguage.Hscript)


def _module_color(name: str) -> hou.Color:
    if name == "CR_INPUT_CONTRACT": return COLORS["input"]
    if name in ("CR_GRAPH_INDEX", "CR_JUNCTION_INDEX", "CR_CORRIDOR_SURFACE"): return COLORS["index"]
    if "SIDEWALK" in name or "CURB" in name: return COLORS["sidewalk"]
    if "MARKING" in name: return COLORS["marking"]
    if "STREET" in name: return COLORS["street"]
    if "JUNCTION" in name: return COLORS["junction"]
    if "CONTRACT" in name or "AUDIT" in name or "COLLISION" in name: return COLORS["contract"]
    return COLORS["road"]


def _safe_output_name(source_name: str, output_index: int) -> str:
    base = re.sub(r"[^A-Za-z0-9_]", "_", source_name)
    return f"SUBNET_OUT_{base}_{output_index}"


def _set_leaf_comments(subnet: hou.Node, description: str) -> None:
    for node in subnet.children():
        if node.type().name() == "output":
            continue
        special = SPECIAL_COMMENTS.get(node.name())
        if special:
            node.setComment(special)
            node.setGenericFlag(hou.nodeFlag.DisplayComment, True)
        elif node.type().name() in ("attribwrangle", "switch", "output", "python") and not node.comment().strip():
            node.setComment(f"{node.name()} | {description}")
            node.setGenericFlag(hou.nodeFlag.DisplayComment, False)


def _layout_subnet(subnet: hou.Node) -> None:
    subnet.layoutChildren(horizontal_spacing=2.4, vertical_spacing=1.25)
    children = list(subnet.children())
    if any(abs(n.position().x()) < 1e-6 and abs(n.position().y()) < 1e-6 for n in children):
        for node in children:
            node.setPosition(node.position() + hou.Vector2((13.25, 7.75)))
    seen = set()
    for index, node in enumerate(children):
        key = (round(node.position().x(), 3), round(node.position().y(), 3))
        if key in seen:
            node.setPosition(node.position() + hou.Vector2((0.75 * (index + 1), 0.35)))
        seen.add((round(node.position().x(), 3), round(node.position().y(), 3)))


def _top_positions(contract: dict[str, Any]) -> dict[str, hou.Vector2]:
    result = {}
    area_y = {
        "AREA_INPUT_GRAPH": 18.0,
        "AREA_ROAD": 4.0,
        "AREA_JUNCTION_SIDEWALK": -10.0,
        "AREA_MARKING_STREET": -24.0,
        "AREA_OUTPUT_DEBUG": -38.0,
    }
    for area_name, items in contract["areas"].items():
        y = area_y[area_name]
        for index, name in enumerate(items):
            result[name] = hou.Vector2((4.0 + index * 5.5, y - (index % 2) * 3.0))
    return result


def _rebuild_boxes(core: hou.Node, contract: dict[str, Any]) -> None:
    for box in list(core.networkBoxes()):
        box.destroy()
    labels = {
        "AREA_INPUT_GRAPH": "输入与图索引 / INPUT + GRAPH INDEX",
        "AREA_ROAD": "道路核心 / ROAD CORE",
        "AREA_JUNCTION_SIDEWALK": "路口与人行道 / JUNCTION + SIDEWALK",
        "AREA_MARKING_STREET": "标线与街具 / MARKING + STREET FURNITURE",
        "AREA_OUTPUT_DEBUG": "输出与调试 / OUTPUT + DEBUG",
    }
    colors = [COLORS["input"], COLORS["road"], COLORS["sidewalk"], COLORS["marking"], COLORS["contract"]]
    for color, (area_name, members) in zip(colors, contract["areas"].items()):
        box = core.createNetworkBox(area_name)
        box.setComment(labels[area_name])
        box.setColor(color)
        for name in members:
            item = core.item(name)
            if item is None:
                raise RuntimeError(f"Top-level area member missing: {name}")
            box.addItem(item)
        box.fitAroundContents()


def _refresh_documentation(core: hou.Node, contract: dict[str, Any]) -> None:
    for subnet_name in contract["subnets"]:
        subnet = core.node(subnet_name)
        if subnet is None:
            continue
        for connection in subnet.inputConnections():
            source = connection.inputNode()
            label = source.name() if source is not None else f"INPUT_{connection.inputIndex() + 1}"
            parm = subnet.parm(f"label{connection.inputIndex() + 1}")
            if parm is not None:
                parm.set(label)
    for name, comment in OUTPUT_COMMENTS.items():
        node = core.node(name)
        if node is not None:
            node.setComment(comment)
            node.setGenericFlag(hou.nodeFlag.DisplayComment, True)
    for name, comment in SPECIAL_COMMENTS.items():
        node = core.node(name)
        if node is not None:
            node.setComment(comment)


def _migrate(asset: hou.Node, core: hou.Node, contract: dict[str, Any]) -> None:
    groups = contract["subnets"]
    owner = {leaf: group for group, leaves in groups.items() for leaf in leaves}
    connections = _snapshot_connections(core)
    _add_internal_proxies(asset, core)
    # Network Boxes move their contents as a unit.  Remove the old decorative
    # boxes before hou.moveNodesTo so the explicit 27-way membership stays exact.
    for box in list(core.networkBoxes()):
        box.destroy()

    subnets = {}
    for group in groups:
        subnet = core.createNode("subnet", node_name=group)
        subnet.setColor(_module_color(group))
        subnets[group] = subnet

    for group, leaves in groups.items():
        nodes = [core.node(name) for name in leaves]
        if any(node is None for node in nodes):
            raise RuntimeError(f"Missing member while moving {group}")
        hou.moveNodesTo(nodes, subnets[group])

    leaves = {}
    for group, member_names in groups.items():
        for name in member_names:
            node = subnets[group].node(name)
            if node is None:
                raise RuntimeError(f"Move failed: {group}/{name}")
            leaves[name] = node

    outgoing = {group: set() for group in groups}
    for destination, _dst_index, source, source_output in connections:
        source_group = owner.get(source)
        destination_group = owner.get(destination)
        if source_group is not None and source_group != destination_group:
            outgoing[source_group].add((source, source_output))

    output_map = {}
    output_names = {group: [] for group in groups}
    for group, keys in outgoing.items():
        subnet = subnets[group]
        for output_index, (source, source_output) in enumerate(sorted(keys)):
            output = subnet.createNode("output", node_name=_safe_output_name(source, source_output))
            output.setInput(0, leaves[source], source_output)
            if output.parm("outputidx") is not None:
                output.parm("outputidx").set(output_index)
            output.setComment(f"{source}[{source_output}] | {SUBNET_DESCRIPTIONS[group]}输出")
            output.setGenericFlag(hou.nodeFlag.DisplayComment, False)
            output_map[(group, source, source_output)] = output_index
            output_names[group].append(source)

    incoming = {group: set() for group in groups}
    for destination, _dst_index, source, source_output in connections:
        source_group = owner.get(source)
        destination_group = owner.get(destination)
        if destination_group is not None and destination_group != source_group:
            incoming[destination_group].add((source, source_output))

    input_map = {}
    input_dots = {}
    input_names = {group: [] for group in groups}
    for group, keys in incoming.items():
        subnet = subnets[group]
        for input_index, (source, source_output) in enumerate(sorted(keys)):
            source_group = owner.get(source)
            if source_group is None:
                source_node = core.node(source)
                parent_output = source_output
            else:
                source_node = subnets[source_group]
                parent_output = output_map[(source_group, source, source_output)]
            subnet.setInput(input_index, source_node, parent_output)
            label_parm = subnet.parm(f"label{input_index + 1}")
            if label_parm is not None:
                label_parm.set(source)
            indirect = subnet.indirectInputs()[input_index]
            dot = subnet.createNetworkDot()
            dot.setName(f"IN_{input_index}_{source}", unique_name=True)
            dot.setInput(indirect, 0)
            dot.setPosition(hou.Vector2((-4.0, 8.0 - input_index * 2.0)))
            input_map[(group, source, source_output)] = input_index
            input_dots[(group, input_index)] = dot
            input_names[group].append(source)

    # Rebuild every original logical edge explicitly.  Internal edges retain
    # direct leaf-to-leaf wiring; boundary edges pass through named interfaces.
    for destination, destination_index, source, source_output in connections:
        destination_group = owner.get(destination)
        source_group = owner.get(source)
        destination_node = leaves.get(destination) or core.node(destination)
        if destination_group is None:
            if source_group is None:
                destination_node.setInput(destination_index, core.node(source), source_output)
            else:
                destination_node.setInput(
                    destination_index, subnets[source_group],
                    output_map[(source_group, source, source_output)])
        elif source_group == destination_group:
            destination_node.setInput(destination_index, leaves[source], source_output)
        else:
            indirect_index = input_map[(destination_group, source, source_output)]
            destination_node.setInput(destination_index,
                                      input_dots[(destination_group, indirect_index)], 0)

    validator = leaves["VALIDATE_ROAD_NETWORK_REQUIRED"]
    python_parm = validator.parm("python")
    if python_parm is None:
        raise RuntimeError("VALIDATE_ROAD_NETWORK_REQUIRED.python is missing")
    python_parm.set(VALIDATION_PYTHON)

    for group, subnet in subnets.items():
        description = SUBNET_DESCRIPTIONS[group]
        _set_leaf_comments(subnet, description)
        inputs_text = ", ".join(input_names[group]) if input_names[group] else "无（内部源）"
        outputs_text = ", ".join(output_names[group]) if output_names[group] else "无（终端模块）"
        subnet.setComment(
            f"{group} | {description}\n"
            f"输入：{inputs_text}\n输出：{outputs_text}\n"
            "默认路径：生产 Cook；调试入口：进入 Subnet 查看命名接口与原叶节点。")
        subnet.setGenericFlag(hou.nodeFlag.DisplayComment, True)
        _layout_subnet(subnet)

    # Key top-level anchors and all formal outputs remain visible and documented.
    for node in core.children():
        if node.name() in SPECIAL_COMMENTS:
            node.setComment(SPECIAL_COMMENTS[node.name()])
        if node.type().name() == "output" and not node.comment().strip():
            node.setComment(f"{node.name()} | CityRoad 正式输出；名称与 Unity 输出语义保持不变。")
        node.setGenericFlag(
            hou.nodeFlag.DisplayComment,
            node.name().startswith("CR_") or node.type().name() == "output" or
            node.name() in ("CITYROAD_BUILD_STATIC_MARKING_MESH",
                            "CITYROAD_REPLACE_CORNER_WITH_QUAD_STRIPS_V11"))

    positions = _top_positions(contract)
    for name, position in positions.items():
        item = core.item(name)
        if item is not None:
            item.setPosition(position)
    _rebuild_boxes(core, contract)
    _refresh_documentation(core, contract)
    core.setUserData("cityroad_subnet_layout_marker", MARKER)


def _validate_layout(core: hou.Node, contract: dict[str, Any]) -> dict[str, Any]:
    direct = list(core.children())
    if len(direct) != contract["top_level_node_count"]:
        raise RuntimeError(f"Top-level node count is {len(direct)}, expected 44")
    direct_names = {node.name() for node in direct}
    expected = set(contract["subnets"]) | set(contract["preserved_top_level"])
    if direct_names != expected:
        raise RuntimeError("Top-level node membership changed")
    member_count = 0
    max_inputs = 0
    max_outputs = 0
    for group, members in contract["subnets"].items():
        subnet = core.node(group)
        if subnet is None or subnet.type().name() != "subnet":
            raise RuntimeError(f"Missing author subnet: {group}")
        actual = {node.name() for node in subnet.children() if node.type().name() != "output"}
        if actual != set(members):
            raise RuntimeError(
                f"Subnet membership changed: {group}; "
                f"missing={sorted(set(members) - actual)} "
                f"extra={sorted(actual - set(members))}")
        member_count += len(actual)
        max_inputs = max(max_inputs, len(subnet.inputConnections()))
        max_outputs = max(max_outputs, sum(1 for node in subnet.children() if node.type().name() == "output"))
        for node in subnet.children():
            if abs(node.position().x()) < 1e-6 and abs(node.position().y()) < 1e-6:
                raise RuntimeError(f"Node left at origin: {node.path()}")
            if node.type().name() in ("attribwrangle", "switch", "output") and not node.comment().strip():
                raise RuntimeError(f"Required node comment is empty: {node.path()}")
    if member_count != contract["original_member_count"]:
        raise RuntimeError(f"Moved member count is {member_count}, expected 191")
    if max_inputs > contract["max_subnet_inputs"] or max_outputs > contract["max_subnet_outputs"]:
        raise RuntimeError(f"Subnet interface exceeds limit: {max_inputs} inputs/{max_outputs} outputs")
    boxes = list(core.networkBoxes())
    if len(boxes) != 5 or any(not box.items() for box in boxes):
        raise RuntimeError("Top-level network box contract failed")
    return {"top_level": len(direct), "subnets": len(contract["subnets"]),
            "members": member_count, "max_inputs": max_inputs,
            "max_outputs": max_outputs, "network_boxes": len(boxes)}


def apply(*, save: bool = False) -> dict[str, Any]:
    contract = _load_contract()
    asset, core = _require_live_baseline(contract)
    if set(contract["subnets"]).issubset({node.name() for node in core.children()}):
        _refresh_documentation(core, contract)
        result = _validate_layout(core, contract)
        result.update({"status": "already_applied_refreshed", "saved": False})
        return result
    try:
        with hou.undos.group("CityRoadCore Subnet Layout V19"):
            _migrate(asset, core, contract)
            result = _validate_layout(core, contract)
    except Exception:
        try:
            hou.undos.performUndo()
        finally:
            raise
    if save:
        definition = asset.type().definition()
        definition.updateFromNode(asset)
        hou.hipFile.save()
    result.update({"status": "applied", "saved": bool(save), "marker": MARKER})
    return result


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--save", action="store_true",
                        help="Persist definition and HIP (default: Live only)")
    args = parser.parse_args()
    print(json.dumps(apply(save=args.save), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
