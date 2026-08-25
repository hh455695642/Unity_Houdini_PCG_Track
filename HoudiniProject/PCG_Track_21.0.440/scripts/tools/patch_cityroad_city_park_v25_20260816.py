"""Recover the reviewed City Park V20 subnet into the current CityRoad V25 live asset.

The user-saved ``PCG_Bike_CityRoad1.hip`` is an explicitly-authorized source
for the park-only authored network.  The rest of that older CityRoad network
is never copied.  This patch is transactional, idempotent, and never persists;
``Invoke-PcgRegression.ps1`` remains the only save authority.
"""

from __future__ import annotations

import argparse
import hashlib
import importlib
import json
import sys
import tempfile
from pathlib import Path

try:
    import hou  # type: ignore
except ImportError:
    hou = None


ASSET_PATH = "/obj/CityRoad_DEV"
ASSET_TYPE = "pcgbike::CityRoad::1.0"
CORE_NAME = "CityRoadCore"
SUBNET_NAME = "CR_CITY_PARK"
GENERATOR_NAME = "PARK_LAYOUT_AND_SCATTER_V20"
MARKER = "CITYROAD_V20_CITY_PARK"
EXPECTED_PUBLIC_HASH = "476b2cbe5a054b5abade2433826431ab229eb88c77026889d3819b177584a65f"
EXPECTED_HDA_SUFFIX = "/Assets/PCG/HDA/City/CityRoad.hda"
EXPECTED_HIP_SUFFIX = "/HoudiniProject/PCG_Track_21.0.440/PCG_Bike_CityRoad.hip"
CANDIDATE_RELATIVE = "HoudiniProject/PCG_Track_21.0.440/PCG_Bike_CityRoad1.hip"
CANDIDATE_SHA256 = "481fe4bb6e4bd50d326de1d11e08b68a2bce7cd32f60620e953168d28dd218ff"
OUTPUT_NAMES = (
    "OUT_PARK_GROUND",
    "OUT_PARK_PATHS",
    "OUT_PARK_WATER",
    "OUT_PARK_COLLISION",
    "OUT_PARK_TREES",
    "OUT_PARK_EXCLUSION",
)
OUTPUT_INDEX_BASE = 10
REQUIRED_CHILDREN = {
    "EMPTY_PARK_AREAS": "null",
    "IN_UNITY_PARK_AREAS": "object_merge",
    "PARK_ENABLE_INPUT_SWITCH": "switch",
    GENERATOR_NAME: "attribwrangle",
    "PARK_GROUND_OUTPUT_CONTRACT": "attribwrangle",
    "PARK_PATHS_OUTPUT_CONTRACT": "attribwrangle",
    "PARK_WATER_OUTPUT_CONTRACT": "attribwrangle",
    "PARK_COLLISION_OUTPUT_CONTRACT": "attribwrangle",
    "PARK_TREES_OUTPUT_CONTRACT": "attribwrangle",
    "PARK_EXCLUSION_OUTPUT_CONTRACT": "attribwrangle",
}


def _normalize(value: str) -> str:
    return value.replace("\\", "/")


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _require_node(parent, relative_path: str):
    node = parent.node(relative_path)
    if node is None:
        raise RuntimeError(f"Missing required node: {parent.path()}/{relative_path}")
    return node


def _public_hash(asset) -> str:
    script_dir = str(Path(__file__).resolve().parent)
    if script_dir not in sys.path:
        sys.path.insert(0, script_dir)
    import validate_cityroad_contract
    importlib.reload(validate_cityroad_contract)
    return validate_cityroad_contract.public_interface_hash(asset)


def _project_root() -> Path:
    # .../HoudiniProject/PCG_Track_21.0.440/scripts/tools/file.py -> project root
    return Path(__file__).resolve().parents[4]


def _validate_source(source):
    source_core = _require_node(source, CORE_NAME)
    source_subnet = _require_node(source_core, SUBNET_NAME)
    generator = _require_node(source_subnet, GENERATOR_NAME)
    snippet = generator.parm("snippet")
    if snippet is None or MARKER not in snippet.evalAsString():
        raise RuntimeError("Candidate City Park generator marker is missing")
    for name, expected_type in REQUIRED_CHILDREN.items():
        node = _require_node(source_subnet, name)
        if node.type().name() != expected_type:
            raise RuntimeError(
                f"Candidate City Park node type changed: {name}="
                f"{node.type().name()} expected={expected_type}")
    for index, name in enumerate(OUTPUT_NAMES):
        node = _require_node(source_core, name)
        if node.type().name() != "output":
            raise RuntimeError(f"Candidate output type changed: {name}")
        connections = node.inputConnections()
        if len(connections) != 1 or connections[0].inputNode() != source_subnet:
            raise RuntimeError(f"Candidate output is not wired to CR_CITY_PARK: {name}")
        if int(node.evalParm("outputidx")) != OUTPUT_INDEX_BASE + index:
            raise RuntimeError(f"Candidate output index changed: {name}")
    return source_core, source_subnet


def _validate_destination(asset, cook: bool = True) -> dict:
    core = _require_node(asset, CORE_NAME)
    subnet = _require_node(core, SUBNET_NAME)
    generator = _require_node(subnet, GENERATOR_NAME)
    snippet = generator.parm("snippet")
    if snippet is None or MARKER not in snippet.evalAsString():
        raise RuntimeError("Destination City Park generator marker is missing")
    for name, expected_type in REQUIRED_CHILDREN.items():
        node = _require_node(subnet, name)
        if node.type().name() != expected_type:
            raise RuntimeError(
                f"Destination City Park node type changed: {name}="
                f"{node.type().name()} expected={expected_type}")
    if asset.parm("enable_city_park") is None or asset.parm("unity_park_areas") is None:
        raise RuntimeError("Destination City Park public interface is incomplete")

    stats = {}
    for index, name in enumerate(OUTPUT_NAMES):
        node = _require_node(core, name)
        connections = node.inputConnections()
        if (node.type().name() != "output" or len(connections) != 1
                or connections[0].inputNode() != subnet
                or int(node.evalParm("outputidx")) != OUTPUT_INDEX_BASE + index):
            raise RuntimeError(f"Destination output contract changed: {name}")
        if cook:
            node.cook(force=True)
            if node.errors() or node.warnings():
                raise RuntimeError(
                    f"Destination output diagnostics at {name}: "
                    f"errors={node.errors()} warnings={node.warnings()}")
            geometry = node.geometry()
            stats[name] = {
                "points": len(geometry.points()),
                "primitives": len(geometry.prims()),
            }
    return stats


def _float_parm(name, label, default, minimum, maximum, help_text):
    return hou.FloatParmTemplate(
        name, label, 1, default_value=(default,), min=minimum, max=maximum,
        min_is_strict=True, max_is_strict=True, help=help_text)


def _int_parm(name, label, default, minimum, maximum, help_text):
    return hou.IntParmTemplate(
        name, label, 1, default_value=(default,), min=minimum, max=maximum,
        min_is_strict=True, max_is_strict=True, help=help_text)


def _toggle(name, label, default, help_text):
    return hou.ToggleParmTemplate(
        name, label, default_value=default, help=help_text)


def _material_parm(name, label, default):
    return hou.StringParmTemplate(
        name, label, 1, default_value=(default,),
        string_type=hou.stringParmType.FileReference,
        file_type=hou.fileType.Any,
        help="Unity Assets/ 路径；Bake 前由项目侧验证。")


def _build_park_folder():
    park_input = hou.StringParmTemplate(
        "unity_park_areas", "Park Areas / 公园边界", 1,
        default_value=("",),
        string_type=hou.stringParmType.NodeReference,
        help="Unity 闭合 SplineContainer 参数输入；一个容器可包含多个公园边界。")
    park_input.setTags({"oprelative": "."})
    parameters = [
        _toggle(
            "enable_city_park", "Enable City Park / 启用城市公园", False,
            "总开关。关闭或没有边界时公园分支直接输出空结果。"),
        park_input,
        _int_parm(
            "park_seed", "Park Seed / 公园随机种子", 1729, 0, 2147483647,
            "控制湖泊、园路和树木的确定性随机布局。"),
        _float_parm(
            "park_boundary_inset", "Boundary Inset (m) / 边界内缩",
            2.0, 0.0, 20.0, "从地块边界向内保留的安全距离。"),
        _toggle(
            "enable_park_water", "Enable Lake / 启用湖泊", True,
            "生成 1-2 个低成本不透明湖面。"),
        _int_parm(
            "park_lake_count", "Lake Count / 湖泊数量", 1, 1, 2,
            "V1 支持 1-2 个湖泊。"),
        _float_parm(
            "park_lake_area_ratio", "Lake Area Ratio / 湖泊面积占比",
            0.25, 0.05, 0.45, "湖泊目标面积相对公园面积的比例。"),
        _toggle(
            "enable_park_paths", "Enable Paths / 启用园路", True,
            "生成湖边环路与最多三条确定性支路。"),
        _float_parm(
            "park_path_width", "Path Width (m) / 园路宽度",
            3.0, 0.5, 10.0, "园路渲染和碰撞宽度。"),
        _int_parm(
            "park_path_branch_count", "Path Branch Count / 园路支路数",
            2, 0, 3, "从边界连接到环路的支路数量。"),
        _float_parm(
            "park_path_jitter", "Path Jitter / 园路扰动",
            0.15, 0.0, 0.35, "控制环路轮廓的低频扰动强度。"),
        _toggle(
            "enable_park_trees", "Enable Park Trees / 启用公园树木", True,
            "树点复用 CityRoad Tree Variants 调色板。"),
        _float_parm(
            "park_tree_density_per_hectare",
            "Tree Density (/ha) / 每公顷树密度", 120.0, 0.0, 1000.0,
            "最终受每公园 2048、每 CityRoad 4096 棵预算限制。"),
        _float_parm(
            "park_tree_min_spacing", "Tree Minimum Spacing (m) / 树最小间距",
            6.0, 1.0, 30.0, "确定性网格散布的最小间距。"),
        _float_parm(
            "park_tree_clearance", "Tree Clearance (m) / 树木净距",
            2.5, 0.0, 20.0, "树木到边界、湖岸和园路的额外净距。"),
        _material_parm(
            "park_ground_unity_material", "Ground Unity Material / 草地 Unity 材质",
            "Assets/PCG/Materials/CityPark/M_PCG_CityPark_Grass.mat"),
        _material_parm(
            "park_path_unity_material", "Path Unity Material / 园路 Unity 材质",
            "Assets/PCG/Materials/CityPark/M_PCG_CityPark_Path.mat"),
        _material_parm(
            "park_water_unity_material", "Water Unity Material / 湖水 Unity 材质",
            "Assets/PCG/Materials/CityPark/M_PCG_CityPark_Water.mat"),
    ]
    folder = hou.FolderParmTemplate(
        "city_park_folder", "City Park / 城市公园",
        parm_templates=parameters,
        folder_type=hou.folderType.Simple)
    folder.setHelp("指定闭合地块并生成移动端友好的灰盒城市公园。")
    return folder


def _copy_park_only(asset, payload_path: Path):
    core = _require_node(asset, CORE_NAME)
    previous_children = {node.name(): node for node in core.children()}
    created = []
    park_box = None
    interface_before = asset.parmTemplateGroup()
    try:
        core.loadItemsFromFile(str(payload_path), ignore_load_warnings=True)
        created = [
            node for node in core.children()
            if node.name() not in previous_children
        ]
        expected = {SUBNET_NAME, *OUTPUT_NAMES}
        actual = {node.name() for node in created}
        if actual != expected:
            raise RuntimeError(
                "Park payload added an unexpected node set: "
                f"actual={sorted(actual)} expected={sorted(expected)}")
        park_folder = _build_park_folder()
        current_group = asset.parmTemplateGroup()
        if current_group.find("city_park_folder") is not None:
            raise RuntimeError("Destination already has a partial City Park parameter folder")
        current_group.append(park_folder)
        asset.setParmTemplateGroup(current_group)
        core.node(SUBNET_NAME).setPosition(hou.Vector2((44.0, -54.0)))
        for index, name in enumerate(OUTPUT_NAMES):
            output = core.node(name)
            output.setPosition(hou.Vector2((52.0 + index * 2.2, -58.0)))
        park_box = core.createNetworkBox()
        park_box.setName("AREA_CITY_PARK")
        park_box.setComment(
            "城市公园 V1｜独立边界、湖面、园路、树木与建筑排除输出；"
            "不接入 Road/Track 拓扑。")
        for node in created:
            park_box.addItem(node)
        park_box.fitAroundContents()
        return created
    except Exception:
        if park_box is not None:
            try:
                park_box.destroy()
            except Exception:
                pass
        for node in reversed(created):
            try:
                if node is not None:
                    node.destroy()
            except Exception:
                pass
        try:
            asset.setParmTemplateGroup(interface_before)
        except Exception:
            pass
        raise


def apply_live_patch(
        save: bool = False,
        payload_path: str | None = None,
        capture_verified_dirty: bool = False,
        hou_module=None) -> dict:
    global hou
    if hou_module is not None:
        hou = hou_module
    if hou is None:
        raise RuntimeError("The hou module is unavailable")
    if save:
        raise RuntimeError("V25 patch is save=False only; use the regression gate to persist")

    asset = hou.node(ASSET_PATH)
    if asset is None or asset.type().name() != ASSET_TYPE:
        raise RuntimeError(f"Expected {ASSET_TYPE} at {ASSET_PATH}")
    definition = asset.type().definition()
    if definition is None:
        raise RuntimeError("CityRoad asset has no HDA definition")
    library = _normalize(definition.libraryFilePath())
    hip = _normalize(hou.hipFile.path())
    if not library.endswith(EXPECTED_HDA_SUFFIX):
        raise RuntimeError(f"Unexpected CityRoad definition: {library}")
    if not hip.endswith(EXPECTED_HIP_SUFFIX):
        raise RuntimeError(f"Unexpected CityRoad HIP: {hip}")
    if hou.hipFile.hasUnsavedChanges() and not capture_verified_dirty:
        raise RuntimeError("CityRoad Live Scene changed after Capture; patch refused")

    core = _require_node(asset, CORE_NAME)
    if core.node("CITYROAD_VALIDATE_STATIC_MARKING_JUNCTION_CLIP_V24") is None:
        raise RuntimeError("V24 production precondition is missing")

    existing = core.node(SUBNET_NAME)
    if existing is not None:
        stats = _validate_destination(asset, cook=True)
        return {
            "status": "PASS",
            "already_applied": True,
            "saved": False,
            "asset": asset.path(),
            "outputs": stats,
            "public_interface_sha256": _public_hash(asset),
        }
    if any(core.node(name) is not None for name in OUTPUT_NAMES):
        raise RuntimeError("Partial OUT_PARK nodes exist without CR_CITY_PARK")
    actual_hash = _public_hash(asset)
    if actual_hash != EXPECTED_PUBLIC_HASH:
        raise RuntimeError(
            "CityRoad V25 public-interface precondition changed: "
            f"actual={actual_hash} expected={EXPECTED_PUBLIC_HASH}")

    candidate_path = _project_root() / CANDIDATE_RELATIVE
    if not candidate_path.is_file():
        raise RuntimeError(f"Candidate HIP is missing: {candidate_path}")
    actual_candidate_hash = _sha256(candidate_path)
    if actual_candidate_hash != CANDIDATE_SHA256:
        raise RuntimeError(
            "Candidate HIP changed after audit: "
            f"actual={actual_candidate_hash} expected={CANDIDATE_SHA256}")
    if not payload_path:
        raise RuntimeError("The audited City Park CPIO payload is missing")
    payload = Path(payload_path)
    if not payload.is_file():
        raise RuntimeError(f"City Park CPIO payload is missing: {payload}")

    with hou.undos.group("CityRoad V25 City Park Recovery"):
        _copy_park_only(asset, payload)
        stats = _validate_destination(asset, cook=True)
    return {
        "status": "PASS",
        "already_applied": False,
        "saved": False,
        "asset": asset.path(),
        "definition": library,
        "hip": hip,
        "candidate": _normalize(str(candidate_path)),
        "candidate_sha256": actual_candidate_hash,
        "public_interface_sha256": _public_hash(asset),
        "outputs": stats,
    }


def _export_candidate_payload(candidate_path: Path) -> Path:
    actual_hash = _sha256(candidate_path)
    if actual_hash != CANDIDATE_SHA256:
        raise RuntimeError(
            "Candidate HIP changed before payload export: "
            f"actual={actual_hash} expected={CANDIDATE_SHA256}")
    hou.hipFile.load(
        str(candidate_path),
        suppress_save_prompt=True,
        ignore_load_warnings=True)
    candidates = [
        node for node in hou.node("/obj").children()
        if node.type().name() == ASSET_TYPE
    ]
    if len(candidates) != 1:
        raise RuntimeError(
            "Candidate HIP must contain exactly one CityRoad source: "
            + repr([node.path() for node in candidates]))
    source_core, source_subnet = _validate_source(candidates[0])
    source_items = (source_subnet,) + tuple(
        _require_node(source_core, name) for name in OUTPUT_NAMES)
    temporary = tempfile.NamedTemporaryFile(
        prefix="cityroad-v25-park-",
        suffix=".cpio",
        delete=False)
    temporary.close()
    payload_path = Path(temporary.name)
    try:
        source_core.saveItemsToFile(
            source_items,
            str(payload_path),
            save_hda_fallbacks=False)
    except Exception:
        payload_path.unlink(missing_ok=True)
        raise
    return payload_path


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=18811)
    parser.add_argument("--save", default="false")
    parser.add_argument("--capture-verified-dirty", default="false")
    args = parser.parse_args()
    if args.save.lower() != "false":
        raise RuntimeError("Only --save false is supported")

    candidate_path = _project_root() / CANDIDATE_RELATIVE
    payload_path = _export_candidate_payload(candidate_path)
    import hrpyc
    try:
        connection, _remote_hou = hrpyc.import_remote_module(
            args.host, args.port, "hou")
        tools_path = str(Path(__file__).resolve().parent).replace("\\", "/")
        connection.execute(
            "import sys, importlib; "
            f"sys.path.insert(0, {tools_path!r}) if {tools_path!r} not in sys.path else None; "
            "import patch_cityroad_city_park_v25_20260816 as _park_v25; "
            "importlib.reload(_park_v25)")
        payload = connection.eval(
            "_park_v25.apply_live_patch("
            f"save=False, payload_path={str(payload_path)!r}, "
            "capture_verified_dirty="
            f"{args.capture_verified_dirty.lower() == 'true'!r})")
        print(json.dumps(payload, ensure_ascii=False, default=list, indent=2))
    finally:
        if "connection" in locals():
            connection.close()
        payload_path.unlink(missing_ok=True)


if __name__ == "__main__":
    main()
