from __future__ import annotations

import copy
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest


TOOLS_DIR = Path(__file__).resolve().parents[1] / "tools"
SPEC = importlib.util.spec_from_file_location(
    "pcg_regression_gate", TOOLS_DIR / "pcg_regression_gate.py")
gate = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(gate)


def manifest():
    return {
        "schema_version": 1,
        "task": "unit-test",
        "module": "CityRoad",
        "allowed_files": [
            "Assets/PCG/HDA/City/CityRoad.hda",
            "HoudiniProject/PCG_Track_21.0.440/PCG_Bike_CityRoad.hip",
        ],
        "allowed_nodes": ["CityRoadCore/V10_*"],
        "allowed_added_nodes": [],
        "allowed_removed_nodes": [],
        "allowed_connections": ["CityRoadCore/MERGE_V10"],
        "allowed_parameters": ["CityRoadCore/SHARED:group"],
        "allowed_public_parameters": [],
        "allow_output_changes": True,
        "allowed_warning_signatures": [],
        "required_contracts": ["CityRoad.V10.CornerSections"],
    }


def snapshot():
    return {
        "schema_version": 1,
        "module": "CityRoad",
        "houdini": {
            "module": "CityRoad",
            "asset_path": "/obj/CityRoad_DEV",
            "asset_type": "pcgbike::CityRoad::1.0",
            "definition": "E:/Project/Assets/PCG/HDA/City/CityRoad.hda",
            "hip": "E:/Project/HoudiniProject/PCG_Bike_CityRoad.hip",
        },
        "files": {
            "Assets/PCG/HDA/City/CityRoad.hda": {"sha256": "a"},
            "HoudiniProject/PCG_Track_21.0.440/PCG_Bike_CityRoad.hip": {
                "sha256": "b"
            },
        },
        "public_interface": {
            "Main/default_lane_count": {"default": [2], "label": "Lane Count"}
        },
        "nodes": {
            "CityRoadCore/V8_BUILDER": {
                "type": "attribwrangle",
                "inputs": [],
                "parameters": {"snippet": {"raw": "CITYROAD_V8"}},
                "flags": {"bypass": False},
                "comment": "",
            },
            "CityRoadCore/V10_SECTION": {
                "type": "attribwrangle",
                "inputs": [],
                "parameters": {"snippet": {"raw": "CITYROAD_V10"}},
                "flags": {"bypass": False},
                "comment": "",
            },
            "CityRoadCore/MERGE_V10": {
                "type": "merge",
                "inputs": [{"input": 0, "source": "V8_BUILDER", "output": 0}],
                "parameters": {},
                "flags": {"bypass": False},
                "comment": "",
            },
        },
        "outputs": {"OUT_ROAD_SURFACE": {"primitives": 10}},
        "diagnostics": {"errors": [], "warnings": []},
    }


class CompareSnapshotsTests(unittest.TestCase):
    def test_unchanged_snapshot_passes(self):
        before = snapshot()
        self.assertEqual([], gate.compare_snapshots(before, copy.deepcopy(before), manifest()))

    def test_allowed_v10_parameter_change_passes(self):
        before = snapshot()
        after = copy.deepcopy(before)
        after["nodes"]["CityRoadCore/V10_SECTION"]["parameters"]["snippet"]["raw"] += "_NEW"
        self.assertEqual([], gate.compare_snapshots(before, after, manifest()))

    def test_v8_regression_is_blocked(self):
        before = snapshot()
        after = copy.deepcopy(before)
        after["nodes"]["CityRoadCore/V8_BUILDER"]["parameters"]["snippet"]["raw"] = "OLD"
        violations = gate.compare_snapshots(before, after, manifest())
        self.assertTrue(any("V8_BUILDER:snippet" in item for item in violations))

    def test_unlisted_connection_change_is_blocked(self):
        before = snapshot()
        after = copy.deepcopy(before)
        after["nodes"]["CityRoadCore/V8_BUILDER"]["inputs"] = [
            {"input": 0, "source": "STALE_SOURCE", "output": 0}
        ]
        violations = gate.compare_snapshots(before, after, manifest())
        self.assertTrue(any("inputs changed" in item for item in violations))

    def test_public_parameter_change_is_blocked(self):
        before = snapshot()
        after = copy.deepcopy(before)
        after["public_interface"]["Main/default_lane_count"]["default"] = [4]
        violations = gate.compare_snapshots(before, after, manifest())
        self.assertTrue(any("Public interface" in item for item in violations))

    def test_new_warning_is_blocked(self):
        before = snapshot()
        after = copy.deepcopy(before)
        after["diagnostics"]["warnings"] = ["OUT_ROAD_SURFACE: new warning"]
        violations = gate.compare_snapshots(before, after, manifest())
        self.assertTrue(any("New Houdini warning" in item for item in violations))

    def test_output_change_requires_explicit_flag(self):
        before = snapshot()
        after = copy.deepcopy(before)
        after["outputs"]["OUT_ROAD_SURFACE"]["primitives"] = 11
        restricted = manifest()
        restricted["allow_output_changes"] = False
        violations = gate.compare_snapshots(before, after, restricted)
        self.assertTrue(any("Output changed" in item for item in violations))

    def test_authoritative_live_scene_flag_must_be_boolean(self):
        data = manifest()
        data["authoritative_live_scene"] = "yes"
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "manifest.json"
            path.write_text(json.dumps(data), encoding="utf-8")
            with self.assertRaises(gate.GateFailure):
                gate.load_manifest(path, "CityRoad")


if __name__ == "__main__":
    unittest.main()
