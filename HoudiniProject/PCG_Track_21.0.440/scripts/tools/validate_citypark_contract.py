"""Patch-independent cumulative validation for CityPark v1."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

import hou


SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = SCRIPT_DIR.parents[3]
CONTRACT_PATH = SCRIPT_DIR.parent / "contracts/citypark_contract.json"
DEFAULT_HDA = PROJECT_ROOT / "Assets/PCG/HDA/City/CityPark.hda"
DEFAULT_HIP = PROJECT_ROOT / "HoudiniProject/PCG_Track_21.0.440/PCG_Bike_CityRoad.hip"
ASSET_TYPE = "pcgbike::CityPark::1.0"
LIVE_ASSET_PATH = "/obj/CityPark_DEV"


class ContractFailure(RuntimeError):
    pass


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ContractFailure(message)


def load_contract() -> dict[str, Any]:
    data = json.loads(CONTRACT_PATH.read_text(encoding="utf-8"))
    require(data.get("schema_version") == 1, "Unsupported CityPark contract schema")
    return data


def _parameter_default(template: hou.ParmTemplate) -> Any:
    value = template.defaultValue()
    if isinstance(value, tuple) and len(value) == 1:
        return value[0]
    return value


def validate_interface(asset: hou.Node, contract: dict[str, Any]) -> None:
    group = asset.parmTemplateGroup()
    for name, expected in contract["parameters"].items():
        template = group.find(name)
        require(template is not None, f"Missing CityPark parameter: {name}")
        actual = _parameter_default(template)
        if isinstance(expected, float):
            require(abs(float(actual) - expected) <= 1e-6,
                    f"CityPark default changed: {name}={actual}")
        else:
            require(actual == expected, f"CityPark default changed: {name}={actual!r}")
    folder_labels = []
    def collect_folders(templates) -> None:
        for template in templates:
            if isinstance(template, hou.FolderParmTemplate):
                folder_labels.append(template.label())
                collect_folders(template.parmTemplates())
    collect_folders(group.entries())
    for label in ("Inputs / 输入", "Terrain / 地形", "Park Road / 公园跑道",
                  "Materials / 材质"):
        require(label in folder_labels, f"Missing CityPark parameter folder: {label}")
    for name in ("unity_park_areas", "unity_park_roads"):
        template = group.find(name)
        require(isinstance(template, hou.StringParmTemplate)
                and template.stringType() == hou.stringParmType.NodeReference,
                f"CityPark input is not a NodeReference: {name}")


def validate_network(asset: hou.Node, contract: dict[str, Any]) -> hou.Node:
    core = asset.node("CityParkCore")
    require(core is not None, "Missing CityParkCore")
    for index, name in enumerate(contract["outputs"]):
        output = core.node(name)
        require(output is not None and output.type().name() == "output",
                f"Missing CityPark output: {name}")
        require(int(output.evalParm("outputidx")) == index,
                f"CityPark output index changed: {name}")
    required_nodes = (
        "IN_UNITY_PARK_AREAS", "REBUILD_PARK_AREA_TOPOLOGY",
        "IN_UNITY_PARK_ROADS", "RESAMPLE_PARK_ROADS",
        "TRIANGULATE_PARK_RANGE", "REMESH_PARK_TERRAIN",
        "DEFORM_TERRAIN_AND_SINK_ROAD", "BUILD_MULTI_CURVE_ROAD",
        "KEEP_ROAD_SURFACE", "KEEP_ROAD_SHOULDERS",
    )
    for name in required_nodes:
        require(core.node(name) is not None, f"Missing CityPark node: {name}")
    forbidden = ("tree", "vegetation", "water", "lake", "instance", "marking", "sidewalk")
    bad = [node.path() for node in asset.allSubChildren()
           if any(token in node.name().lower() for token in forbidden)]
    require(not bad, f"CityPark v1 contains deferred nodes: {bad}")
    boxes = {box.name(): box.comment() for box in core.networkBoxes()}
    require(set(boxes) == {"AREA_INPUTS", "AREA_TERRAIN", "AREA_ROAD", "AREA_OUTPUTS"},
            f"CityPark network areas changed: {boxes}")
    return core


def _area_input(parent: hou.Node, name: str) -> hou.Node:
    obj = parent.createNode("geo", name)
    for child in obj.children():
        child.destroy()
    sop = obj.createNode("circle", "BUILD_TEST_INPUT")
    sop.parm("type").set(1)
    sop.parm("orient").set(2)
    sop.parm("radx").set(70.0)
    sop.parm("rady").set(60.0)
    sop.parm("divs").set(8)
    sop.setDisplayFlag(True); sop.setRenderFlag(True)
    return sop


def _road_input(parent: hou.Node, name: str) -> hou.Node:
    obj = parent.createNode("geo", name)
    for child in obj.children():
        child.destroy()
    line_a = obj.createNode("line", "TEST_OPEN_ROAD_A")
    line_a.parmTuple("origin").set((-45.0, 0.0, -25.0))
    line_a.parmTuple("dir").set((1.0, 0.0, 0.35))
    line_a.parm("dist").set(85.0); line_a.parm("points").set(8)
    line_b = obj.createNode("line", "TEST_OPEN_ROAD_B")
    line_b.parmTuple("origin").set((-35.0, 0.0, 32.0))
    line_b.parmTuple("dir").set((0.9, 0.0, -0.25))
    line_b.parm("dist").set(70.0); line_b.parm("points").set(7)
    loop = obj.createNode("circle", "TEST_CLOSED_ROAD")
    loop.parm("type").set(1); loop.parm("orient").set(2)
    loop.parm("radx").set(18.0); loop.parm("rady").set(12.0); loop.parm("divs").set(10)
    merge = obj.createNode("merge", "BUILD_TEST_INPUT")
    merge.setInput(0, line_a); merge.setInput(1, line_b); merge.setInput(2, loop)
    merge.setDisplayFlag(True); merge.setRenderFlag(True)
    return merge


def _detail(geometry: hou.Geometry, name: str, default: Any = None) -> Any:
    attribute = geometry.findGlobalAttrib(name)
    return geometry.attribValue(attribute) if attribute is not None else default


def _attribute_values(geometry: hou.Geometry, owner: hou.attribType, name: str) -> set:
    attribute = (geometry.findPrimAttrib(name)
                 if owner == hou.attribType.Prim
                 else geometry.findPointAttrib(name))
    if attribute is None:
        return set()
    elements = geometry.prims() if owner == hou.attribType.Prim else geometry.points()
    return {element.attribValue(attribute) for element in elements}


def _cook_diagnostic(core: hou.Node) -> dict[str, Any]:
    """Return the first useful SOP-level error instead of a generic output failure."""
    result: dict[str, Any] = {}
    for node in core.allSubChildren(top_down=True):
        if node.childTypeCategory() is not None:
            continue
        try:
            node.cook(force=True)
            geometry = node.geometry()
            result[node.name()] = {
                "points": len(geometry.points()) if geometry is not None else None,
                "primitives": len(geometry.prims()) if geometry is not None else None,
                "errors": list(node.errors()),
                "warnings": list(node.warnings()),
            }
        except Exception as exception:
            result[node.name()] = {
                "exception": str(exception),
                "errors": list(node.errors()),
                "warnings": list(node.warnings()),
            }
            break
    return result


def validate_geometry(asset: hou.Node, core: hou.Node) -> dict[str, Any]:
    obj = hou.node("/obj")
    area_sop = _area_input(obj, "CITYPARK_CONTRACT_AREAS")
    road_sop = _road_input(obj, "CITYPARK_CONTRACT_ROADS")
    area_sop.cook(force=True)
    road_sop.cook(force=True)
    require(not area_sop.errors(), f"CityPark area test input failed: {area_sop.errors()}")
    require(not road_sop.errors(), f"CityPark road test input failed: {road_sop.errors()}")
    tracked = {name: asset.evalParm(name) for name in (
        "unity_park_areas", "unity_park_roads", "enable_ground", "enable_road",
        "enable_shoulders", "terrain_height_amplitude", "road_ground_sink")}
    try:
        asset.parm("unity_park_areas").set(area_sop.path())
        asset.parm("unity_park_roads").set(road_sop.path())
        asset.parm("enable_ground").set(1)
        asset.parm("enable_road").set(1)
        asset.parm("enable_shoulders").set(1)
        asset.parm("terrain_height_amplitude").set(0.6)
        asset.parm("road_ground_sink").set(0.25)
        outputs = {name: core.node(name) for name in load_contract()["outputs"]}
        for output in outputs.values():
            try:
                output.cook(force=True)
            except Exception as exception:
                raise ContractFailure(
                    f"CityPark Cook exception: {output.path()} {exception}; "
                    f"network={_cook_diagnostic(core)}") from exception
            require(not output.errors(), f"CityPark Cook error: {output.path()} {output.errors()}")
            require(not output.warnings(), f"CityPark Cook warning: {output.path()} {output.warnings()}")
        ground = outputs["OUT_PARK_GROUND"].geometry()
        road = outputs["OUT_PARK_ROAD"].geometry()
        shoulders = outputs["OUT_PARK_SHOULDERS"].geometry()
        if len(ground.prims()) < 20:
            diagnostic = {}
            diagnostic["binding"] = {
                "area_parameter": asset.evalParm("unity_park_areas"),
                "area_object_merge": core.node("IN_UNITY_PARK_AREAS").evalParm("objpath1"),
                "area_source_points": len(area_sop.geometry().points()),
                "area_source_primitives": len(area_sop.geometry().prims()),
            }
            for node_name in (
                "IN_UNITY_PARK_AREAS", "SELECT_PARK_AREAS_INPUT",
                "CONVERT_PARK_AREAS", "REBUILD_PARK_AREA_TOPOLOGY",
                "TRIANGULATE_PARK_RANGE", "REMESH_PARK_TERRAIN"):
                node = core.node(node_name)
                node.cook(force=True)
                node_geometry = node.geometry()
                diagnostic[node_name] = {
                    "points": len(node_geometry.points()),
                    "primitives": len(node_geometry.prims()),
                    "errors": list(node.errors()),
                    "warnings": list(node.warnings()),
                }
            raise ContractFailure(f"CityPark ground too coarse/empty: {diagnostic}")
        require(len(road.prims()) >= 12, f"CityPark road output too small: {len(road.prims())}")
        require(len(shoulders.prims()) >= 24,
                f"CityPark shoulder output too small: {len(shoulders.prims())}")
        require(_detail(ground, "citypark_contract")
                == "CITYPARK_V1_RANGE_TERRAIN_MULTI_ROAD",
                "CityPark ground contract marker missing")
        require(_detail(ground, "citypark_has_water") == 0
                and _detail(ground, "citypark_has_vegetation") == 0,
                "Deferred CityPark content is enabled")
        require(_detail(road, "citypark_has_markings") == 0
                and _detail(road, "citypark_has_sidewalk") == 0,
                "CityPark road unexpectedly emits markings/sidewalk")
        require(_attribute_values(ground, hou.attribType.Prim, "park_role") == {"ground"},
                "CityPark ground role changed")
        require(_attribute_values(road, hou.attribType.Prim, "park_role") == {"road"},
                "CityPark road role changed")
        require(_attribute_values(shoulders, hou.attribType.Prim, "park_role") == {"shoulder"},
                "CityPark shoulder role changed")
        path_ids = _attribute_values(road, hou.attribType.Prim, "path_id")
        require(len(path_ids) == 3, f"CityPark multi-curve path IDs changed: {path_ids}")
        require(ground.boundingBox().minvec().y() <= -0.15,
                f"CityPark terrain is not sunk below roads: {ground.boundingBox().minvec().y()}")
        require(shoulders.boundingBox().minvec().y()
                < road.boundingBox().minvec().y() - 0.05,
                "CityPark shoulders no longer drop below the road")
        for geometry, label in ((road, "road"), (shoulders, "shoulders")):
            for primitive in geometry.prims()[:32]:
                normal = primitive.normal()
                require(normal.y() > 0.0,
                        f"CityPark {label} winding is not upward: "
                        f"prim={primitive.number()} normal={tuple(normal)} "
                        f"points={[tuple(point.position()) for point in primitive.points()]}")
        return {
            "ground_points": len(ground.points()), "ground_primitives": len(ground.prims()),
            "road_points": len(road.points()), "road_primitives": len(road.prims()),
            "shoulder_points": len(shoulders.points()),
            "shoulder_primitives": len(shoulders.prims()),
            "path_ids": sorted(path_ids),
            "ground_min_y": ground.boundingBox().minvec().y(),
        }
    finally:
        for name, value in tracked.items():
            parm = asset.parm(name)
            if parm is not None:
                parm.set(value)
        area_sop.parent().destroy()
        road_sop.parent().destroy()


def validate_asset(asset: hou.Node, require_locked: bool) -> dict[str, Any]:
    require(asset is not None, "CityPark asset is missing")
    require(asset.type().name() in ("subnet", "CityPark::1.0", ASSET_TYPE),
            f"Unexpected CityPark type: {asset.type().name()}")
    if require_locked:
        require(asset.isLockedHDA(), "Fresh CityPark instance is not locked")
    contract = load_contract()
    validate_interface(asset, contract)
    core = validate_network(asset, contract)
    geometry = validate_geometry(asset, core)
    return {
        "asset": asset.path(), "type": asset.type().nameWithCategory(),
        "locked": asset.isLockedHDA(), "geometry": geometry,
        "contract_ids": contract["contract_ids"], "saved": False,
    }


def validate_live_json(asset_path: str = LIVE_ASSET_PATH) -> str:
    return json.dumps(validate_asset(hou.node(asset_path), require_locked=False),
                      ensure_ascii=False, default=list)


def validate_remote_live(asset_path: str, host: str, port: int) -> dict[str, Any]:
    import hrpyc
    connection, _remote_hou = hrpyc.import_remote_module(host, port, "hou")
    try:
        path = str(SCRIPT_DIR).replace("\\", "/")
        connection.execute(
            "import sys, importlib, hou; "
            f"sys.path.insert(0, {path!r}) if {path!r} not in sys.path else None; "
            "import validate_citypark_contract as _validator; importlib.reload(_validator)")
        payload = connection.eval(f"_validator.validate_live_json({asset_path!r})")
        return json.loads(str(payload))
    finally:
        connection.close()


def validate_fresh(hda_path: Path, hip_path: Path) -> dict[str, Any]:
    require(hda_path.is_file(), f"CityPark HDA not found: {hda_path}")
    require(hip_path.is_file(), f"CityPark HIP not found: {hip_path}")
    hou.hipFile.load(str(hip_path), suppress_save_prompt=True, ignore_load_warnings=False)
    hou.hda.installFile(str(hda_path))
    fresh = hou.node("/obj").createNode(ASSET_TYPE, "VERIFY_CITYPARK_LOCKED")
    result = validate_asset(fresh, require_locked=True)
    result.update({"source": "fresh_locked_instance", "hda": str(hda_path),
                   "hip": str(hip_path)})
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", choices=("live", "fresh"), default="fresh")
    parser.add_argument("--asset", default=LIVE_ASSET_PATH)
    parser.add_argument("--hda", type=Path, default=DEFAULT_HDA)
    parser.add_argument("--hip", type=Path, default=DEFAULT_HIP)
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=18811)
    args = parser.parse_args()
    result = (validate_remote_live(args.asset, args.host, args.port)
              if args.source == "live"
              else validate_fresh(args.hda.resolve(), args.hip.resolve()))
    print(json.dumps(result, ensure_ascii=False, indent=2, default=list))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except ContractFailure as exception:
        print(f"CONTRACT_FAIL: {exception}")
        raise SystemExit(1)
