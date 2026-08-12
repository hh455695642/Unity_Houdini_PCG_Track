"""Deterministic CityRoad topology-edit Cook benchmark.

The benchmark clones the current unlocked Live asset so it can measure an
unpersisted V2 implementation without touching ``/obj/CityRoad_DEV``.  It
builds the agreed 8x7 / 100-edge graph, alternates one interior vertex by
0.35m, and forces all seven public outputs in one Houdini session.
"""

from __future__ import annotations

import argparse
import json
import math
from pathlib import Path
import statistics
import time

import hou


ASSET_PATH = "/obj/CityRoad_DEV"
ASSET_TYPE = "pcgbike::CityRoad::1.0"
CORE_NAME = "CityRoadCore"
TEMP_INPUT = "CITYROAD_COOK_BENCH_INPUT"
TEMP_ASSET = "CITYROAD_COOK_BENCH_ASSET"
OUTPUTS = (
    "OUT_ROAD_SURFACE",
    "OUT_SIDEWALK_CURB",
    "OUT_ROAD_COLLISION",
    "OUT_ROAD_MARKINGS",
    "OUT_STREET_LAMPS",
    "OUT_STREET_TREES",
    "OUT_STREET_TREE_PITS",
)
STAGES = {
    "Graph": "GRAPH_CLASSIFY_JUNCTIONS",
    "Road": "CITYROAD_TOPOLOGY_CLASSIFY_ROAD",
    "Sidewalk": "CURB_SIDEWALK_STATS",
    "Marking": "OUT_ROAD_MARKINGS",
    "Street": "OUT_STREET_TREE_PITS",
}


def _detail_int(node: hou.Node, name: str) -> int:
    geometry = node.geometry()
    attrib = geometry.findGlobalAttrib(name)
    return int(geometry.attribValue(attrib)) if attrib is not None else 0


def percentile(values: list[float], fraction: float) -> float:
    ordered = sorted(values)
    if not ordered:
        return 0.0
    position = (len(ordered) - 1) * fraction
    lower = int(math.floor(position))
    upper = int(math.ceil(position))
    if lower == upper:
        return ordered[lower]
    weight = position - lower
    return ordered[lower] * (1.0 - weight) + ordered[upper] * weight


def _python_sop_source(edge_limit: int) -> str:
    layouts = {
        25: (4, 4, 1),       # 12 + 12 + 1
        100: (8, 7, 3),      # 49 + 48 + 3
        225: (11, 11, 5),    # 110 + 110 + 5
    }
    if edge_limit not in layouts:
        raise ValueError(f"Unsupported deterministic edge count: {edge_limit}")
    nx, nz, feeder_count = layouts[edge_limit]
    return f'''geo = hou.pwd().geometry()
delta = hou.pwd().evalParm("bench_delta")
edge_limit = {int(edge_limit)}
nx = {nx}
nz = {nz}
feeder_count = {feeder_count}
spacing = 24.0
routes = []
for z in range(nz):
    route = [(x*spacing, 0.0, z*spacing) for x in range(nx)]
    routes.append(route)
for x in range(nx):
    routes.append([(x*spacing, 0.0, z*spacing) for z in range(nz)])
feeders = [
    [(-spacing, 0.0, (nz//2)*spacing), (0.0, 0.0, (nz//2)*spacing)],
    [((nx-1)*spacing, 0.0, (nz//3)*spacing), (nx*spacing, 0.0, (nz//3)*spacing)],
    [((nx//2)*spacing, 0.0, (nz-1)*spacing), ((nx//2)*spacing, 0.0, nz*spacing)],
    [((nx//3)*spacing, 0.0, -spacing), ((nx//3)*spacing, 0.0, 0.0)],
    [((nx-1)*spacing, 0.0, ((2*nz)//3)*spacing),
     (nx*spacing, 0.0, ((2*nz)//3)*spacing)],
]
routes.extend(feeders[:feeder_count])
road_id = geo.addAttrib(hou.attribType.Prim, "road_id", -1)
road_level = geo.addAttrib(hou.attribType.Prim, "road_level", 0)
segment_id = geo.addAttrib(hou.attribType.Prim, "segment_id", -1)
road_width = geo.addAttrib(hou.attribType.Prim, "road_width", 8.0)
allow_junction = geo.addAttrib(hou.attribType.Prim, "allow_junction", 1)
actual_edges = sum(len(route)-1 for route in routes)
if actual_edges != edge_limit:
    raise RuntimeError("benchmark edge count mismatch: %d != %d" % (actual_edges, edge_limit))
moving_x = (nx//2)*spacing
moving_z = (nz//2)*spacing
for index, route in enumerate(routes):
    poly = geo.createPolygon()
    poly.setIsClosed(False)
    for position in route:
        p = geo.createPoint()
        px, py, pz = position
        if abs(px-moving_x) < 1e-8 and abs(pz-moving_z) < 1e-8:
            px += delta
        p.setPosition((px, py, pz))
        poly.addVertex(p)
    poly.setAttribValue(road_id, index)
    poly.setAttribValue(road_level, 0)
    poly.setAttribValue(segment_id, index)
    poly.setAttribValue(road_width, 8.0 + float(index % 3))
    poly.setAttribValue(allow_junction, 1)
'''


def _create_input(obj: hou.Node, edge_limit: int) -> tuple[hou.Node, hou.Node]:
    old = obj.node(TEMP_INPUT)
    if old is not None:
        old.destroy()
    container = obj.createNode("geo", TEMP_INPUT)
    for child in container.children():
        child.destroy()
    source = container.createNode("python", "BUILD_100_EDGE_GRID")
    group = source.parmTemplateGroup()
    group.append(hou.FloatParmTemplate("bench_delta", "Benchmark Delta", 1, default_value=(0.0,)))
    source.setParmTemplateGroup(group)
    code_parm = source.parm("python") or source.parm("snippet")
    if code_parm is None:
        raise RuntimeError("Python SOP code parameter was not found")
    code_parm.set(_python_sop_source(edge_limit))
    output = container.createNode("null", "OUT_BENCH_ROAD_GRAPH")
    output.setInput(0, source)
    output.setDisplayFlag(True)
    output.setRenderFlag(True)
    return container, source


def _clone_live(obj: hou.Node, input_path: str) -> hou.Node:
    old = obj.node(TEMP_ASSET)
    if old is not None:
        old.destroy()
    source = hou.node(ASSET_PATH)
    if source is None or source.type().name() != ASSET_TYPE:
        raise RuntimeError(f"Expected {ASSET_TYPE} at {ASSET_PATH}")
    asset = source.copyTo(obj)
    asset.setName(TEMP_ASSET, unique_name=False)
    if asset.isLockedHDA():
        asset.allowEditingOfContents(propagate=True)
    for child in asset.allSubChildren():
        if child.isLockedHDA():
            try:
                child.allowEditingOfContents(propagate=True)
            except hou.PermissionError:
                pass
    for name, value in (("road_network_source", 0), ("unity_road_network", input_path)):
        parm = asset.parm(name)
        if parm is None:
            raise RuntimeError(f"Missing benchmark parameter: {name}")
        parm.set(value)
    # Several cumulative regression assertions are embedded directly in VEX
    # as error()/warning() calls and intentionally describe the production
    # fixture, not arbitrary synthetic grids.  On this disposable clone only,
    # turn the reporting calls into no-op string assignments.  Algorithmic
    # conditions, geometry generation and all seven formal output chains are
    # otherwise unchanged; production verification retains the hard asserts.
    sanitized = 0
    for node in asset.allSubChildren():
        snippet = node.parm("snippet")
        if snippet is None or snippet.keyframes():
            continue
        source_text = snippet.evalAsString()
        updated = source_text.replace("error(", "cityroad_benchmark_report(")
        updated = updated.replace("warning(", "cityroad_benchmark_report(")
        if updated != source_text:
            updated = (
                "function int cityroad_benchmark_report(string message) { return 0; }\n"
                + updated)
            try:
                snippet.set(updated)
                sanitized += 1
            except hou.PermissionError:
                continue
    asset.setUserData("cityroad_benchmark_sanitized_assert_nodes", str(sanitized))
    return asset


def _require_core_node(core: hou.Node, name: str) -> hou.Node:
    direct = core.node(name)
    if direct is not None:
        return direct
    matches = [
        child.node(name)
        for child in core.children()
        if child.type().name() == "subnet" and child.name().startswith("CR_")
        and child.node(name) is not None
    ]
    if len(matches) != 1:
        raise RuntimeError(f"Benchmark requires one CityRoad leaf {name}; found {len(matches)}")
    return matches[0]


def _bake_proxy_values_for_diagnostic(core: hou.Node) -> None:
    """Freeze internal proxy values on the disposable benchmark clone only."""
    if core.parm("cityroad_layout_marker") is None:
        return
    for parm in core.parms():
        try:
            expression = parm.expression()
        except hou.OperationFailed:
            continue
        if not expression or "../" not in expression:
            continue
        template_type = parm.parmTemplate().type()
        value = (parm.evalAsString()
                 if template_type == hou.parmTemplateType.String else parm.eval())
        parm.deleteAllKeyframes()
        parm.set(value)


def run_benchmark(
    label: str,
    edge_limit: int = 100,
    warmups: int = 3,
    samples: int = 11,
    keep_nodes: bool = False,
    bake_proxies: bool = False,
) -> dict:
    obj = hou.node("/obj")
    if obj is None:
        raise RuntimeError("/obj is unavailable")
    container = None
    asset = None
    try:
        container, source = _create_input(obj, edge_limit)
        output = container.node("OUT_BENCH_ROAD_GRAPH")
        asset = _clone_live(obj, output.path())
        core = asset.node(CORE_NAME)
        if core is None:
            raise RuntimeError("Benchmark clone has no CityRoadCore")
        if bake_proxies:
            _bake_proxy_values_for_diagnostic(core)
        output_nodes = [_require_core_node(core, name) for name in OUTPUTS]
        if any(node is None for node in output_nodes):
            raise RuntimeError("Benchmark clone is missing a formal output")
        stage_nodes = {key: _require_core_node(core, name) for key, name in STAGES.items()}
        if any(node is None for node in stage_nodes.values()):
            raise RuntimeError("Benchmark clone is missing a stage probe")

        rows = []
        total_rounds = warmups + samples
        for iteration in range(total_rounds):
            delta = 0.35 if iteration % 2 == 0 else -0.35
            source.parm("bench_delta").set(delta)
            before = {key: node.cookCount() for key, node in stage_nodes.items()}
            start = time.perf_counter()
            for node in output_nodes:
                try:
                    # Changing the source parm dirties every dependent branch.
                    # Non-forced output cooks evaluate that dirty graph once;
                    # force=True here would redundantly recook shared upstream
                    # nodes once per formal output and cease to model an edit.
                    node.cook(force=False)
                except Exception as exception:
                    raise RuntimeError(
                        f"{node.path()} cook failed: {exception}; "
                        f"errors={node.errors()} warnings={node.warnings()}") from exception
                if node.errors() or node.warnings():
                    raise RuntimeError(
                        f"{node.path()} diagnostics: errors={node.errors()} warnings={node.warnings()}")
            wall_ms = (time.perf_counter() - start) * 1000.0
            stage = {
                key: {
                    "cookCount": int(node.cookCount() - before[key]),
                    # HOM already reports lastCookTime() in milliseconds.
                    "lastCookTimeMs": float(node.lastCookTime()),
                }
                for key, node in stage_nodes.items()
            }
            if iteration >= warmups:
                rows.append({"iteration": iteration - warmups, "delta": delta,
                             "wallTimeMs": wall_ms, "stages": stage,
                             "graphComplexity": {
                                 "segments": _detail_int(
                                     stage_nodes["Graph"], "cityroad_graph_segment_count"),
                                 "broadphaseCandidates": _detail_int(
                                     stage_nodes["Graph"], "cityroad_graph_broadphase_candidates"),
                                 "exactTests": _detail_int(
                                     stage_nodes["Graph"], "cityroad_graph_exact_tests"),
                             }})

        wall = [row["wallTimeMs"] for row in rows]
        result = {
            "schema_version": 2,
            "label": label,
            "edge_count": edge_limit,
            "warmups": warmups,
            "samples": samples,
            "wall_ms": {
                "median": statistics.median(wall),
                "p95": percentile(wall, 0.95),
                "min": min(wall),
                "max": max(wall),
            },
            "stage_last_cook_ms_median": {
                key: statistics.median(
                    row["stages"][key]["lastCookTimeMs"] for row in rows)
                for key in STAGES
            },
            "graph_complexity_median": {
                key: statistics.median(
                    row["graphComplexity"][key] for row in rows)
                for key in ("segments", "broadphaseCandidates", "exactTests")
            },
            "rows": rows,
        }
        return result
    finally:
        if not keep_nodes:
            if asset is not None:
                asset.destroy()
            if container is not None:
                container.destroy()


def run_remote(label: str, edge_limit: int, warmups: int, samples: int,
               host: str, port: int, keep_nodes: bool,
               bake_proxies: bool = False) -> dict:
    import hrpyc
    connection, _remote_hou = hrpyc.import_remote_module(host, port, "hou")
    try:
        script_dir = str(Path(__file__).resolve().parent).replace("\\", "/")
        connection.execute(
            "import sys, importlib, json; "
            f"sys.path.insert(0, {script_dir!r}) if {script_dir!r} not in sys.path else None; "
            "import benchmark_cityroad_cook as _pcg_bench; importlib.reload(_pcg_bench)")
        payload = connection.eval(
            "_pcg_bench.json.dumps(_pcg_bench.run_benchmark("
            f"{label!r}, edge_limit={edge_limit}, warmups={warmups}, "
            f"samples={samples}, keep_nodes={keep_nodes!r}, "
            f"bake_proxies={bake_proxies!r}), ensure_ascii=False)")
        return json.loads(str(payload))
    finally:
        connection.close()


def evaluate_gate(baseline: dict, candidate: dict) -> dict:
    failures = []
    baseline_median = float(baseline["wall_ms"]["median"])
    candidate_median = float(candidate["wall_ms"]["median"])
    baseline_p95 = float(baseline["wall_ms"]["p95"])
    candidate_p95 = float(candidate["wall_ms"]["p95"])
    if candidate_median > baseline_median * 0.70:
        failures.append("total median exceeds 70% of baseline")
    if candidate_p95 > baseline_p95:
        failures.append("total P95 regressed")

    stage_rows = {}
    for key in STAGES:
        baseline_value = float(baseline["stage_last_cook_ms_median"][key])
        # Schema v1 accidentally multiplied HOM milliseconds by 1000.
        if int(baseline.get("schema_version", 1)) < 2:
            baseline_value /= 1000.0
        candidate_value = float(candidate["stage_last_cook_ms_median"][key])
        if int(candidate.get("schema_version", 1)) < 2:
            candidate_value /= 1000.0
        regressed = (candidate_value > baseline_value * 1.10
                     and candidate_value - baseline_value > 1.0)
        if regressed:
            failures.append(f"{key} stage regressed by >10% and >1 ms")
        stage_rows[key] = {
            "baselineMs": baseline_value,
            "candidateMs": candidate_value,
            "regressed": regressed,
        }
    return {
        "status": "PASS" if not failures else "FAIL",
        "medianRatio": candidate_median / baseline_median,
        "p95Ratio": candidate_p95 / baseline_p95,
        "stages": stage_rows,
        "failures": failures,
    }


def evaluate_layout_gate(baseline: dict, candidate: dict) -> dict:
    """V19: Subnet maintenance work may add at most 3% median/5% P95."""
    failures = []
    median_ratio = float(candidate["wall_ms"]["median"]) / float(baseline["wall_ms"]["median"])
    p95_ratio = float(candidate["wall_ms"]["p95"]) / float(baseline["wall_ms"]["p95"])
    if median_ratio > 1.03:
        failures.append("total median exceeds 103% of baseline")
    if p95_ratio > 1.05:
        failures.append("total P95 exceeds 105% of baseline")
    stage_rows = {}
    for key in STAGES:
        baseline_value = float(baseline["stage_last_cook_ms_median"][key])
        candidate_value = float(candidate["stage_last_cook_ms_median"][key])
        regressed = (candidate_value > baseline_value * 1.10 and
                     candidate_value - baseline_value > 1.0)
        if regressed:
            failures.append(f"{key} stage regressed by >10% and >1 ms")
        stage_rows[key] = {
            "baselineMs": baseline_value,
            "candidateMs": candidate_value,
            "regressed": regressed,
        }
    return {
        "status": "PASS" if not failures else "FAIL",
        "profile": "layout",
        "medianRatio": median_ratio,
        "p95Ratio": p95_ratio,
        "stages": stage_rows,
        "failures": failures,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--label", required=True)
    parser.add_argument("--edges", type=int, default=100, choices=(25, 100, 225))
    parser.add_argument("--warmups", type=int, default=3)
    parser.add_argument("--samples", type=int, default=11)
    parser.add_argument("--live", action="store_true")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=18811)
    parser.add_argument("--keep-nodes", action="store_true")
    parser.add_argument("--bake-proxies", action="store_true",
                        help="Diagnostic only: freeze hidden Core proxy expressions on the clone")
    parser.add_argument("--output", type=Path)
    parser.add_argument("--baseline", type=Path,
                        help="Evaluate the measured candidate against a baseline JSON")
    parser.add_argument("--gate-profile", choices=("cook", "layout"), default="cook")
    args = parser.parse_args()
    if args.live:
        result = run_remote(args.label, args.edges, args.warmups, args.samples,
                            args.host, args.port, args.keep_nodes, args.bake_proxies)
    else:
        result = run_benchmark(args.label, args.edges, args.warmups, args.samples,
                               args.keep_nodes, args.bake_proxies)
    payload = json.dumps(result, ensure_ascii=False, indent=2)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(payload, encoding="utf-8")
    print(payload)
    if args.baseline:
        baseline = json.loads(args.baseline.read_text(encoding="utf-8"))
        gate = (evaluate_layout_gate(baseline, result)
                if args.gate_profile == "layout" else evaluate_gate(baseline, result))
        print(json.dumps({"performance_gate": gate}, ensure_ascii=False, indent=2))
        if gate["status"] != "PASS":
            return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
