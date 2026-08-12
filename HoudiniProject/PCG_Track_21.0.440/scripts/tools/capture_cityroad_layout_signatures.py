"""Capture/compare CityRoad geometry and street-furniture signatures over hrpyc."""

from __future__ import annotations

import argparse
import json
from pathlib import Path


def capture(host: str, port: int) -> dict:
    import hrpyc
    connection, _remote_hou = hrpyc.import_remote_module(host, port, "hou")
    try:
        tools = str(Path(__file__).resolve().parent).replace("\\", "/")
        connection.execute(
            "import sys, importlib, json, hou; "
            f"sys.path.insert(0, {tools!r}) if {tools!r} not in sys.path else None; "
            "import validate_cityroad_contract as _crv; importlib.reload(_crv)")
        payload = connection.eval(
            "_crv.json.dumps(_crv._v18_output_snapshot("
            "hou.node('/obj/CityRoad_DEV/CityRoadCore')), ensure_ascii=False)")
        return json.loads(str(payload))
    finally:
        connection.close()


def compare(baseline: dict, candidate: dict) -> dict:
    failures = []
    geometry = {}
    for key, expected in baseline["geometry"].items():
        actual = candidate["geometry"].get(key)
        if actual is None:
            failures.append(f"missing geometry signature: {key}")
            continue
        for field in ("points", "primitives", "primitive_groups", "point_groups", "materials"):
            if expected.get(field) != actual.get(field):
                failures.append(f"{key}.{field} changed")
        expected_positions = expected.get("positions", [])
        actual_positions = actual.get("positions", [])
        if len(expected_positions) != len(actual_positions):
            point_error = float("inf")
        else:
            point_error = max(
                [max(abs(float(a) - float(b)) for a, b in zip(left, right))
                 for left, right in zip(expected_positions, actual_positions)]
                or [0.0])
        if point_error > 1e-4:
            failures.append(f"{key}.point error {point_error} > 1e-4")
        expected_bounds = expected.get("bounds", [])
        actual_bounds = actual.get("bounds", [])
        max_bound_error = max(
            [abs(float(a) - float(b)) for a, b in zip(expected_bounds, actual_bounds)]
            or [0.0])
        if max_bound_error > 1e-4:
            failures.append(f"{key}.bounds error {max_bound_error} > 1e-4")
        expected_area = float(expected.get("area", 0.0))
        actual_area = float(actual.get("area", 0.0))
        relative_area_error = abs(actual_area - expected_area) / max(abs(expected_area), 1e-12)
        if relative_area_error > 1e-5:
            failures.append(f"{key}.area relative error {relative_area_error} > 1e-5")
        geometry[key] = {
            "max_point_error": point_error,
            "max_bound_error": max_bound_error,
            "relative_area_error": relative_area_error,
        }
    if baseline.get("street") != candidate.get("street"):
        failures.append("street furniture deterministic signature changed")
    return {
        "status": "PASS" if not failures else "FAIL",
        "geometry": geometry,
        "street_equal": baseline.get("street") == candidate.get("street"),
        "failures": failures,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=18811)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--baseline", type=Path)
    args = parser.parse_args()
    result = capture(args.host, args.port)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    if args.baseline:
        gate = compare(json.loads(args.baseline.read_text(encoding="utf-8")), result)
        print(json.dumps(gate, ensure_ascii=False, indent=2))
        return 0 if gate["status"] == "PASS" else 1
    print(json.dumps({
        "status": "CAPTURED",
        "output": str(args.output),
        "geometry": {key: {
            "points": value.get("points"),
            "primitives": value.get("primitives"),
            "area": value.get("area"),
        } for key, value in result["geometry"].items()},
        "street": result["street"],
    }, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
