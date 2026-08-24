"""CityRoad V45: organize the V41 City Park graph without changing geometry.

The patch is intentionally save=False. Persistence is owned by the PCG
regression gate after VerifyFast and VerifyFull pass.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from pathlib import Path
from typing import Any

try:
    import hou  # type: ignore
except ImportError:  # pragma: no cover - injected by Houdini/RPyC
    hou = None  # type: ignore


ASSET_PATH = "/obj/CityRoad_DEV"
ASSET_TYPE = "pcgbike::CityRoad::1.0"
CORE_PATH = "CityRoadCore"
PARK_PATH = "CityRoadCore/CR_CITY_PARK"
EXPECTED_HDA = "E:/HoudiniProject/Unity_Houdini_PCG_Track/Assets/PCG/HDA/City/CityRoad.hda"
EXPECTED_HIP = (
    "E:/HoudiniProject/Unity_Houdini_PCG_Track/"
    "HoudiniProject/PCG_Track_21.0.440/PCG_Bike_CityRoad.hip"
)
MARKER = "CITYROAD_V45_PARK_READABILITY_20260824"
BASELINE_SHA256 = "bbc0bf1ab2114508c57b6768095b8752c478d7c7c2fbf35def919bbb1dddbd9b"


GROUPS = {
    "CR_PARK_INPUT": [
        "EMPTY_PARK_AREAS", "IN_UNITY_PARK_AREAS", "PARK_ENABLE_INPUT_SWITCH",
        "PARK_CONVERT_HAPI_CURVE_V32", "PARK_REBUILD_HAPI_TOPOLOGY_V29",
    ],
    "CR_PARK_MASTERPLAN": [
        "PARK_BOUNDARY_ANALYZE_V41", "PARK_SURFACE_ZONES_V41",
        "PARK_CONNECTED_PATHS_V41", "PARK_WOODLAND_LAYERS_V41",
        "PARK_EXCLUSION_V41", "PARK_ASSEMBLE_V41", "PARK_CONTRACT_V41",
    ],
    "CR_PARK_OUTPUTS": [
        "PARK_KEEP_GROUND", "PARK_GROUND_OUTPUT_CONTRACT", "PARK_GROUND_NORMALS",
        "PARK_KEEP_PATHS", "PARK_PATHS_OUTPUT_CONTRACT", "PARK_PATHS_NORMALS",
        "PARK_KEEP_WATER", "PARK_WATER_OUTPUT_CONTRACT", "PARK_WATER_NORMALS",
        "PARK_KEEP_COLLISION", "PARK_COLLISION_OUTPUT_CONTRACT",
        "PARK_KEEP_TREES", "PARK_TREES_OUTPUT_CONTRACT",
        "PARK_KEEP_EXCLUSION", "PARK_EXCLUSION_OUTPUT_CONTRACT",
    ],
}

FORMAL_OUTPUTS = [
    ("GROUND", "PARK_GROUND_NORMALS", "SUBNET_OUT_PARK_GROUND_0"),
    ("PATHS", "PARK_PATHS_NORMALS", "SUBNET_OUT_PARK_PATHS_1"),
    ("WATER", "PARK_WATER_NORMALS", "SUBNET_OUT_PARK_WATER_2"),
    ("COLLISION", "PARK_COLLISION_OUTPUT_CONTRACT", "SUBNET_OUT_PARK_COLLISION_3"),
    ("TREES", "PARK_TREES_OUTPUT_CONTRACT", "SUBNET_OUT_PARK_TREES_4"),
    ("EXCLUSION", "PARK_EXCLUSION_OUTPUT_CONTRACT", "SUBNET_OUT_PARK_EXCLUSION_5"),
]

SUBNET_COMMENTS = {
    "CR_PARK_INPUT": (
        "01 公园输入与边界规范化 / PARK INPUT\n"
        "Unity 闭合 Spline → 开关回退 → HAPI Curve 转换 → 闭合拓扑重建。\n"
        "输出：供总图模块使用的合法闭合公园边界；无绑定时输出空几何。"),
    "CR_PARK_MASTERPLAN": (
        "02 公园总图生成 / PARK MASTERPLAN\n"
        "边界分析后并行生成地表分区、连通路网、林地层和建筑排除区。\n"
        "输出：带 V41 累计 metadata 的完整公园语义几何。"),
    "CR_PARK_OUTPUTS": (
        "03 六路 Bake 输出 / PARK OUTPUTS\n"
        "按 role 拆分 Ground/Paths/Water/Collision/Trees/Exclusion，补齐稳定 metadata 与法线。\n"
        "运行时只消费 Bake 结果，本模块不进入移动端运行时。"),
}

MASTERPLAN_CHANNEL_NODES = (
    "PARK_BOUNDARY_ANALYZE_V41", "PARK_SURFACE_ZONES_V41",
    "PARK_CONNECTED_PATHS_V41", "PARK_WOODLAND_LAYERS_V41",
    "PARK_EXCLUSION_V41",
)


def _norm(value: str) -> str:
    return str(value).replace("\\", "/").lower()


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
    park = asset.node(PARK_PATH)
    if core is None or park is None:
        raise RuntimeError("CityRoadCore/CR_CITY_PARK is missing")
    return asset, core, park


def _baseline_payload(park) -> list[list[Any]]:
    payload = []
    for node in sorted(park.children(), key=lambda item: item.name()):
        inputs = []
        for connection in node.inputConnections():
            source = connection.inputNode()
            inputs.append([
                connection.inputIndex(), source.name() if source is not None else None,
                connection.outputIndex(),
            ])
        payload.append([node.name(), node.type().name(), sorted(inputs)])
    return payload


def _sha256(value: Any) -> str:
    data = json.dumps(value, ensure_ascii=False, sort_keys=True,
                      separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(data).hexdigest()


def _parm_digest(node) -> str:
    values = []
    for parm in node.parms():
        if ((node.name() == "IN_UNITY_PARK_AREAS" and parm.name() == "objpath1") or
                (node.name() == "PARK_ENABLE_INPUT_SWITCH" and parm.name() == "input") or
                (node.name() in MASTERPLAN_CHANNEL_NODES and parm.name() == "snippet")):
            # These HScript/VEX channel references must gain one ../ after
            # nesting. Their exact semantic form is asserted independently.
            continue
        try:
            value = parm.unexpandedString()
        except Exception:
            try:
                value = str(parm.eval())
            except Exception:
                value = "<UNREADABLE>"
        values.append([parm.name(), value])
    return _sha256(values)


def _set_input_label(subnet, index: int, label: str) -> None:
    parm = subnet.parm(f"label{index + 1}")
    if parm is not None:
        parm.set(label)


def _create_output(subnet, name: str, source, output_index: int, comment: str):
    output = subnet.node(name) or subnet.createNode("output", name)
    output.setInput(0, source, 0)
    parm = output.parm("outputidx")
    if parm is not None:
        parm.set(output_index)
    output.setComment(comment)
    output.setGenericFlag(hou.nodeFlag.DisplayComment, True)
    return output


def _wire_modules(park) -> None:
    input_module = park.node("CR_PARK_INPUT")
    masterplan = park.node("CR_PARK_MASTERPLAN")
    outputs = park.node("CR_PARK_OUTPUTS")
    if any(node is None for node in (input_module, masterplan, outputs)):
        raise RuntimeError("V45 Park modules are incomplete")

    # 01 input module: two sources converge on a guarded conversion chain.
    empty = input_module.node("EMPTY_PARK_AREAS")
    unity = input_module.node("IN_UNITY_PARK_AREAS")
    switch = input_module.node("PARK_ENABLE_INPUT_SWITCH")
    convert = input_module.node("PARK_CONVERT_HAPI_CURVE_V32")
    rebuild = input_module.node("PARK_REBUILD_HAPI_TOPOLOGY_V29")
    switch.setInput(0, empty, 0); switch.setInput(1, unity, 0)
    unity.parm("objpath1").setExpression(
        'ifs(strlen(chs("../../../../unity_park_areas"))>0'
        ' && opexist(chsop("../../../../unity_park_areas")),'
        ' chsop("../../../../unity_park_areas"),"../EMPTY_PARK_AREAS")',
        language=hou.exprLanguage.Hscript)
    switch.parm("input").setExpression(
        'if(ch("../../../../enable_city_park")!=0'
        ' && strlen(chs("../../../../unity_park_areas"))>0,1,0)',
        language=hou.exprLanguage.Hscript)
    convert.setInput(0, switch, 0); rebuild.setInput(0, convert, 0)
    _create_output(
        input_module, "SUBNET_OUT_PARK_BOUNDARY", rebuild, 0,
        "公园边界输出：已完成 Unity/HAPI 曲线转换与闭合拓扑重建。")

    # 02 masterplan: one analyzed boundary fans out into four authored layers.
    masterplan.setInput(0, input_module, 0)
    _set_input_label(masterplan, 0, "PARK_REBUILT_BOUNDARY")
    boundary_input = masterplan.indirectInputs()[0]
    analyze = masterplan.node("PARK_BOUNDARY_ANALYZE_V41")
    surface = masterplan.node("PARK_SURFACE_ZONES_V41")
    paths = masterplan.node("PARK_CONNECTED_PATHS_V41")
    woodland = masterplan.node("PARK_WOODLAND_LAYERS_V41")
    exclusion = masterplan.node("PARK_EXCLUSION_V41")
    assemble = masterplan.node("PARK_ASSEMBLE_V41")
    contract = masterplan.node("PARK_CONTRACT_V41")
    analyze.setInput(0, boundary_input, 0)
    for node in (surface, paths, woodland, exclusion):
        node.setInput(0, analyze, 0)
    assemble.setInput(0, surface, 0); assemble.setInput(1, paths, 0)
    assemble.setInput(2, woodland, 0); assemble.setInput(3, exclusion, 0)
    contract.setInput(0, assemble, 0)
    for channel_node_name in MASTERPLAN_CHANNEL_NODES:
        channel_node = masterplan.node(channel_node_name)
        snippet_parm = channel_node.parm("snippet")
        snippet = snippet_parm.evalAsString()
        # Normalize any prior retry (3, 4 or more ../ segments) to the exact
        # four levels required from CR_PARK_MASTERPLAN back to the HDA node.
        snippet = re.sub(
            r"(?:\.\./)+(enable_|park_|tree_)", r"../../../../\1", snippet)
        snippet_parm.set(snippet)
    _create_output(
        masterplan, "SUBNET_OUT_PARK_MASTERPLAN", contract, 0,
        "公园总图输出：地表、路网、植被与排除区已合并并写入 V41 合约。")

    # 03 outputs: one contracted stream fans out into six stable Bake roles.
    outputs.setInput(0, masterplan, 0)
    _set_input_label(outputs, 0, "PARK_MASTERPLAN_CONTRACT")
    contracted_input = outputs.indirectInputs()[0]
    for role, source_name, outer_name in FORMAL_OUTPUTS:
        keep = outputs.node(f"PARK_KEEP_{role}")
        keep.setInput(0, contracted_input, 0)
        contract_node = outputs.node(f"PARK_{role}_OUTPUT_CONTRACT")
        contract_node.setInput(0, keep, 0)
        source = outputs.node(source_name)
        # RPyC netrefs do not guarantee Python object identity for the same
        # remote hou.Node. Compare paths so contract-only roles never self-wire.
        if source.path() != contract_node.path():
            source.setInput(0, contract_node, 0)
        index = FORMAL_OUTPUTS.index((role, source_name, outer_name))
        _create_output(
            outputs, f"SUBNET_OUT_{role}", source, index,
            f"{role} 子网接口：发布到 CR_CITY_PARK 第 {index} 路稳定输出。")
        outer = park.node(outer_name)
        outer.setInput(0, outputs, index)


def _document_and_layout(park) -> None:
    colors = {
        "CR_PARK_INPUT": (0.22, 0.48, 0.70),
        "CR_PARK_MASTERPLAN": (0.30, 0.62, 0.45),
        "CR_PARK_OUTPUTS": (0.72, 0.52, 0.18),
    }
    top_positions = {
        "CR_PARK_INPUT": (-18, 4), "CR_PARK_MASTERPLAN": (-4, 4),
        "CR_PARK_OUTPUTS": (12, 4),
        "SUBNET_OUT_PARK_GROUND_0": (-3, -8),
        "SUBNET_OUT_PARK_PATHS_1": (3, -8),
        "SUBNET_OUT_PARK_WATER_2": (9, -8),
        "SUBNET_OUT_PARK_COLLISION_3": (15, -8),
        "SUBNET_OUT_PARK_TREES_4": (21, -8),
        "SUBNET_OUT_PARK_EXCLUSION_5": (27, -8),
    }
    for name, position in top_positions.items():
        park.node(name).setPosition(hou.Vector2(position))
    for name, text in SUBNET_COMMENTS.items():
        subnet = park.node(name)
        subnet.setComment(text)
        subnet.setColor(hou.Color(colors[name]))
        subnet.setGenericFlag(hou.nodeFlag.DisplayComment, True)

    input_module = park.node("CR_PARK_INPUT")
    input_positions = {
        "EMPTY_PARK_AREAS": (-14, 7), "IN_UNITY_PARK_AREAS": (-14, 1),
        "PARK_ENABLE_INPUT_SWITCH": (-8, 4), "PARK_CONVERT_HAPI_CURVE_V32": (-2, 4),
        "PARK_REBUILD_HAPI_TOPOLOGY_V29": (4, 4), "SUBNET_OUT_PARK_BOUNDARY": (10, 4),
    }
    for name, position in input_positions.items():
        input_module.node(name).setPosition(hou.Vector2(position))

    masterplan = park.node("CR_PARK_MASTERPLAN")
    master_positions = {
        "PARK_BOUNDARY_ANALYZE_V41": (-6, 4), "PARK_SURFACE_ZONES_V41": (1, 11),
        "PARK_CONNECTED_PATHS_V41": (1, 5), "PARK_WOODLAND_LAYERS_V41": (1, -1),
        "PARK_EXCLUSION_V41": (1, -7), "PARK_ASSEMBLE_V41": (9, 4),
        "PARK_CONTRACT_V41": (15, 4), "SUBNET_OUT_PARK_MASTERPLAN": (21, 4),
    }
    for name, position in master_positions.items():
        masterplan.node(name).setPosition(hou.Vector2(position))

    outputs = park.node("CR_PARK_OUTPUTS")
    for index, (role, source_name, _outer_name) in enumerate(FORMAL_OUTPUTS):
        x = -12 + index * 7
        outputs.node(f"PARK_KEEP_{role}").setPosition(hou.Vector2((x, 8)))
        outputs.node(f"PARK_{role}_OUTPUT_CONTRACT").setPosition(hou.Vector2((x, 3)))
        if source_name != f"PARK_{role}_OUTPUT_CONTRACT":
            outputs.node(source_name).setPosition(hou.Vector2((x, -2)))
        outputs.node(f"SUBNET_OUT_{role}").setPosition(hou.Vector2((x, -7)))

    leaf_comments = {
        "PARK_KEEP_GROUND": "仅保留 park_ground：草坪、林缘与入口地表。",
        "PARK_KEEP_PATHS": "仅保留 park_paths：入口支路、环路与中心节点连通路网。",
        "PARK_KEEP_WATER": "仅保留 park_water：湖区水面。",
        "PARK_KEEP_COLLISION": "仅保留 park_collision：移动端 Bake 碰撞代理。",
        "PARK_KEEP_TREES": "仅保留 park_trees：供 Unity GPU Instancing 的树木点。",
        "PARK_KEEP_EXCLUSION": "仅保留 park_exclusion：建筑和人工覆盖排除区。",
        "PARK_GROUND_NORMALS": "重建 Ground 法线，供 Unity 静态 Mesh Bake。",
        "PARK_PATHS_NORMALS": "重建 Paths 法线，供 Unity 静态 Mesh Bake。",
        "PARK_WATER_NORMALS": "重建 Water 法线，供 Unity 静态 Mesh Bake。",
    }
    for name, comment in leaf_comments.items():
        node = outputs.node(name)
        node.setComment(comment)
        node.setGenericFlag(hou.nodeFlag.DisplayComment, True)
    for role, _source_name, outer_name in FORMAL_OUTPUTS:
        outer = park.node(outer_name)
        outer.setComment(f"CR_CITY_PARK {role} 正式输出；输出序号与 Unity Bake 合约保持不变。")
        outer.setGenericFlag(hou.nodeFlag.DisplayComment, True)

    for box in list(park.networkBoxes()):
        box.destroy()
    box_specs = {
        "PARK_AREA_INPUT": ("01 输入与边界 / INPUT + BOUNDARY", ["CR_PARK_INPUT"], (0.22, 0.48, 0.70)),
        "PARK_AREA_MASTERPLAN": ("02 总图功能层 / MASTERPLAN LAYERS", ["CR_PARK_MASTERPLAN"], (0.30, 0.62, 0.45)),
        "PARK_AREA_OUTPUT": ("03 六路 Bake 输出 / OUTPUT CONTRACT", ["CR_PARK_OUTPUTS", *[item[2] for item in FORMAL_OUTPUTS]], (0.72, 0.52, 0.18)),
    }
    for name, (label, members, color) in box_specs.items():
        box = park.createNetworkBox(name)
        box.setComment(label); box.setColor(hou.Color(color))
        for member in members:
            box.addItem(park.item(member))
        box.fitAroundContents()
    for note in list(park.stickyNotes()):
        note.destroy()
    note = park.createStickyNote()
    note.setName("NOTE_PARK_V45_README", unique_name=False)
    note.setPosition(hou.Vector2((-20, 16))); note.setSize((50, 7))
    note.setText(
        "City Park 阅读顺序 / HOW TO READ\n"
        "① CR_PARK_INPUT：Unity Spline 与闭合边界修复\n"
        "② CR_PARK_MASTERPLAN：地表分区 / 连通路网 / 林地层 / 排除区\n"
        "③ CR_PARK_OUTPUTS：六路稳定 Bake 输出\n"
        "所有 V41 Wrangle 算法与公共参数保持不变；CityRoadTutorialLab 未参与本模块。")
    note.setTextSize(0.55); note.setColor(hou.Color((0.16, 0.18, 0.22)))


def _validate(park, expected_parm_digests: dict[str, str] | None = None) -> dict[str, Any]:
    expected_top = {"CR_PARK_INPUT", "CR_PARK_MASTERPLAN", "CR_PARK_OUTPUTS"} | {
        item[2] for item in FORMAL_OUTPUTS}
    actual_top = {node.name() for node in park.children()}
    if actual_top != expected_top or len(actual_top) != 9:
        raise RuntimeError(f"V45 Park top-level membership mismatch: {sorted(actual_top)}")
    for group, expected_members in GROUPS.items():
        subnet = park.node(group)
        actual = {node.name() for node in subnet.children() if node.type().name() != "output"}
        if actual != set(expected_members):
            raise RuntimeError(f"V45 Park membership mismatch: {group}")
        outputs = [node for node in subnet.children() if node.type().name() == "output"]
        expected_output_count = 6 if group == "CR_PARK_OUTPUTS" else 1
        if len(outputs) != expected_output_count:
            raise RuntimeError(f"V45 Park output count mismatch: {group}")
        if not subnet.comment().strip():
            raise RuntimeError(f"V45 Park module comment missing: {group}")
    input_module = park.node("CR_PARK_INPUT")
    object_expression = input_module.node("IN_UNITY_PARK_AREAS").parm("objpath1").expression()
    switch_expression = input_module.node("PARK_ENABLE_INPUT_SWITCH").parm("input").expression()
    if "../../../../unity_park_areas" not in object_expression:
        raise RuntimeError("V45 Park Object Merge does not resolve the asset parameter")
    if "../../../../enable_city_park" not in switch_expression:
        raise RuntimeError("V45 Park input switch does not resolve the asset parameter")
    for channel_node_name in MASTERPLAN_CHANNEL_NODES:
        snippet = park.node("CR_PARK_MASTERPLAN").node(channel_node_name).parm("snippet").evalAsString()
        references = re.findall(
            r"(?:\"|')((?:\.\./)+(?:enable_|park_|tree_)[^\"']*)", snippet)
        if not references or any(
                not reference.startswith("../../../../") or
                reference.startswith("../../../../../")
                for reference in references):
            raise RuntimeError(f"V45 Park VEX asset path is missing: {channel_node_name}")
    for index, (_role, _source, outer_name) in enumerate(FORMAL_OUTPUTS):
        outer = park.node(outer_name)
        connection = outer.inputConnections()
        if len(connection) != 1 or connection[0].inputNode() != park.node("CR_PARK_OUTPUTS") or connection[0].outputIndex() != index:
            raise RuntimeError(f"V45 Park formal output wiring mismatch: {outer_name}")
    if expected_parm_digests is not None:
        for group, names in GROUPS.items():
            subnet = park.node(group)
            for name in names:
                actual = _parm_digest(subnet.node(name))
                if actual != expected_parm_digests[name]:
                    raise RuntimeError(f"V45 changed an authored parameter: {name}")
    boxes = {box.name(): {item.name() for item in box.items()} for box in park.networkBoxes()}
    expected_boxes = {
        "PARK_AREA_INPUT": {"CR_PARK_INPUT"},
        "PARK_AREA_MASTERPLAN": {"CR_PARK_MASTERPLAN"},
        "PARK_AREA_OUTPUT": {"CR_PARK_OUTPUTS", *[item[2] for item in FORMAL_OUTPUTS]},
    }
    if boxes != expected_boxes:
        raise RuntimeError(f"V45 Park Network Box mismatch: {boxes}")
    return {
        "park_top_level_nodes": 9, "nested_modules": 3,
        "preserved_algorithm_nodes": sum(len(items) for items in GROUPS.values()),
        "formal_outputs": 6, "network_boxes": 3,
    }


def apply_live_patch(save: bool = False, capture_verified_dirty: bool = False,
                     hou_module=None) -> dict[str, Any]:
    global hou
    if hou_module is not None:
        hou = hou_module
    if hou is None:
        raise RuntimeError("The hou module is unavailable")
    if save:
        raise RuntimeError("V45 patch is save=False only; use the regression gate")
    _asset, _core, park = _require_identity()
    if park.userData("cityroad_park_readability_marker") == MARKER:
        _wire_modules(park); _document_and_layout(park)
        result = _validate(park)
        result.update({"status": "PASS", "already_applied": True, "saved": False})
        return result
    if not capture_verified_dirty:
        raise RuntimeError("V45 requires an explicit Capture-verified Live Scene")
    baseline = _sha256(_baseline_payload(park))
    if baseline != BASELINE_SHA256:
        raise RuntimeError(f"V45 Live baseline changed: {baseline} != {BASELINE_SHA256}")
    original_nodes = {node.name(): node for node in park.children()}
    expected_digests = {
        name: _parm_digest(original_nodes[name])
        for names in GROUPS.values() for name in names
    }
    try:
        with hou.undos.group("CityRoad Park Readability V45"):
            for box in list(park.networkBoxes()):
                box.destroy()
            for note in list(park.stickyNotes()):
                note.destroy()
            modules = {}
            for group in GROUPS:
                module = park.createNode("subnet", group)
                modules[group] = module
            for group, names in GROUPS.items():
                hou.moveNodesTo([original_nodes[name] for name in names], modules[group])
            _wire_modules(park)
            _document_and_layout(park)
            park.setComment(
                "城市公园 V45 可读性封装：输入边界 → V41 总图功能层 → 六路稳定 Bake 输出。\n"
                "算法、公共参数和输出顺序保持不变；运行时只消费 Unity Bake 数据。")
            park.setGenericFlag(hou.nodeFlag.DisplayComment, True)
            park.setUserData("cityroad_park_readability_marker", MARKER)
            result = _validate(park, expected_digests)
    except Exception:
        try:
            hou.undos.performUndo()
        finally:
            raise
    result.update({"status": "PASS", "already_applied": False,
                   "saved": False, "marker": MARKER})
    return result


def main() -> None:
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
        tools_path = str(Path(__file__).resolve().parent).replace("\\", "/")
        connection.execute(
            "import sys, importlib; "
            f"sys.path.insert(0, {tools_path!r}) if {tools_path!r} not in sys.path else None; "
            "import patch_cityroad_park_readability_v45_20260824 as _cityroad_v45; "
            "importlib.reload(_cityroad_v45)")
        payload = connection.eval(
            "_cityroad_v45.apply_live_patch(save=False, capture_verified_dirty="
            f"{args.capture_verified_dirty.lower() == 'true'!r})")
        print(json.dumps(payload, ensure_ascii=False, default=list, indent=2))
    finally:
        connection.close()


if __name__ == "__main__":
    main()
