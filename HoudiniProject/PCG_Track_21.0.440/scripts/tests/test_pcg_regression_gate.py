from __future__ import annotations

import copy
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from unittest import mock


TOOLS_DIR = Path(__file__).resolve().parents[1] / "tools"
PROJECT_ROOT = Path(__file__).resolve().parents[4]
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
    def test_streetbuilding_hda_panel_contract_ids_are_cumulative(self):
        contract_path = (PROJECT_ROOT / "HoudiniProject" / "PCG_Track_21.0.440"
                         / "scripts" / "contracts" / "streetbuilding_contract.json")
        contract_ids = set(json.loads(contract_path.read_text(encoding="utf-8"))["contract_ids"])
        required = {
            "StreetBuilding.ArtAuthoring.ProjectOwnedStyleCoverage",
            "StreetBuilding.ArtAuthoring.NoExternalAssetDependency",
            "StreetBuilding.ArtAuthoring.DirectSaveRollback",
            "StreetBuilding.V12.HdaPanelSingleSource",
            "StreetBuilding.V12.ExternalParcelOnlyOverride",
            "StreetBuilding.V12.StyleBridgeHapiVisible",
        }
        self.assertTrue(required.issubset(contract_ids))

    def test_streetbuilding_verifyfull_runs_unity_contract_tests(self):
        entrypoint = (PROJECT_ROOT / ".agents" / "scripts"
                      / "Invoke-PcgRegression.ps1").read_text(encoding="utf-8")
        self.assertIn("Invoke-StreetBuildingPipelineTests -CandidateHda $candidate.hda", entrypoint)
        self.assertIn("        Invoke-StreetBuildingPipelineTests\n", entrypoint)
        self.assertIn("$assembly = 'PCGBike.StreetBuilding.Tests.Editor'", entrypoint)
        self.assertIn("--filter_type assembly --filter $assembly", entrypoint)
        self.assertIn("$summary.passed -ne $tests.Count", entrypoint)
        self.assertNotIn("StreetBuildingPhase4ContractBridge", entrypoint)

    def test_streetbuilding_persistence_requires_current_live(self):
        config = gate.MODULES['StreetBuilding']
        self.assertFalse(config.get('isolated'))
        self.assertNotIn('builder', config)
        self.assertEqual('/obj/StreetBuilding_DEV', config['asset_path'])

    def test_unity_only_persistence_keeps_houdini_bytes_without_rpc(self):
        with tempfile.TemporaryDirectory() as directory:
            root, config, change, baseline_path, original = self.persistence_fixture(directory)
            with mock.patch.object(gate, "connect_live", side_effect=AssertionError("RPC must not run")):
                result = gate.persist_live(root, "StreetBuilding", config, change, baseline_path, "localhost", 18811)
            self.assertEqual("not-required", result["persistence"])
            self.assertEqual(original, {relative: (root / relative).read_bytes() for relative in original})

    def test_unity_only_persistence_rejects_changed_or_missing_houdini_files(self):
        for relative_key in ("definition", "hip", "meta"):
            for operation in ("change", "remove"):
                with self.subTest(file=relative_key, operation=operation), tempfile.TemporaryDirectory() as directory:
                    root, config, change, baseline_path, original = self.persistence_fixture(directory)
                    relative = config["restore_files"][0] if relative_key == "meta" else config[relative_key]
                    target = root / relative
                    if operation == "remove":
                        target.unlink()
                    else:
                        target.write_bytes(b"unauthorized-change")
                    with mock.patch.object(gate, "connect_live", side_effect=AssertionError("RPC must not run")):
                        with self.assertRaisesRegex(gate.GateFailure, "unauthorized Houdini file changes"):
                            gate.persist_live(root, "StreetBuilding", config, change, baseline_path, "localhost", 18811)

    def test_unity_only_persistence_requires_capture_hash_and_protected_file_baselines(self):
        for invalid in ("manifest", "missing-meta-hash"):
            with self.subTest(invalid=invalid), tempfile.TemporaryDirectory() as directory:
                root, config, change, baseline_path, original = self.persistence_fixture(directory)
                if invalid == "manifest":
                    change["task"] = "different-task"
                else:
                    baseline = json.loads(baseline_path.read_text(encoding="utf-8"))
                    baseline["backup_sha256"].pop(config["restore_files"][0])
                    baseline_path.write_text(json.dumps(baseline), encoding="utf-8")
                with mock.patch.object(gate, "connect_live", side_effect=AssertionError("RPC must not run")):
                    with self.assertRaises(gate.GateFailure):
                        gate.persist_live(root, "StreetBuilding", config, change, baseline_path, "localhost", 18811)

    def test_partial_houdini_write_permission_remains_blocked(self):
        for allowed_key in ("definition", "hip"):
            with self.subTest(file=allowed_key), tempfile.TemporaryDirectory() as directory:
                root, config, change, baseline_path, original = self.persistence_fixture(directory)
                change["allowed_files"].append(config[allowed_key])
                baseline = json.loads(baseline_path.read_text(encoding="utf-8"))
                baseline["manifest_sha256"] = gate.captured_manifest_hash(change)
                baseline_path.write_text(json.dumps(baseline), encoding="utf-8")
                with mock.patch.object(gate, "connect_live", side_effect=AssertionError("RPC must not run")):
                    with self.assertRaisesRegex(gate.GateFailure, "persistence requires allowed_files"):
                        gate.persist_live(root, "StreetBuilding", config, change, baseline_path, "localhost", 18811)

    def test_authorized_houdini_persistence_still_requires_rpc(self):
        with tempfile.TemporaryDirectory() as directory:
            root, config, change, baseline_path, original = self.persistence_fixture(directory)
            change["allowed_files"].extend(original)
            baseline = json.loads(baseline_path.read_text(encoding="utf-8"))
            baseline["manifest_sha256"] = gate.captured_manifest_hash(change)
            baseline_path.write_text(json.dumps(baseline), encoding="utf-8")
            with mock.patch.object(gate, "connect_live", side_effect=RuntimeError("authorized RPC reached")):
                with self.assertRaisesRegex(RuntimeError, "authorized RPC reached"):
                    gate.persist_live(root, "StreetBuilding", config, change, baseline_path, "localhost", 18811)

    def test_unity_only_failure_does_not_restore_or_reload_unowned_houdini_changes(self):
        with tempfile.TemporaryDirectory() as directory:
            root, config, change, baseline_path, original = self.persistence_fixture(directory)
            target = root / config["definition"]
            target.write_bytes(b"external-change")
            args = mock.Mock(module="StreetBuilding", project_root=root, manifest=root / "manifest.json",
                             snapshot=baseline_path, stage="persist", host="localhost", port=18811)
            with mock.patch.object(gate, "parse_args", return_value=args), \
                    mock.patch.object(gate, "load_manifest", return_value=change), \
                    mock.patch.object(gate, "restore_baseline") as restore, \
                    mock.patch.object(gate, "connect_live", side_effect=AssertionError("RPC must not run")):
                with self.assertRaisesRegex(gate.GateFailure, "unauthorized Houdini file changes"):
                    gate.main()
                restore.assert_not_called()
            self.assertEqual(b"external-change", target.read_bytes())

    @staticmethod
    def persistence_fixture(directory):
        root = Path(directory)
        config = copy.deepcopy(gate.MODULES["StreetBuilding"])
        change = manifest()
        change["module"] = "StreetBuilding"
        change["allowed_files"] = ["Assets/PCG/Art/Building_Test/Style1/SBStyle_Test.asset"]
        protected = [config["definition"], config["hip"], *config["restore_files"]]
        original = {}
        for relative in protected:
            target = root / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            original[relative] = ("original:" + relative).encode("utf-8")
            target.write_bytes(original[relative])
        baseline = {
            "manifest_sha256": gate.captured_manifest_hash(change),
            "files": gate.file_state(root, [config["definition"], config["hip"]]),
            "backup_sha256": {relative: gate.sha256_file(root / relative) for relative in protected},
        }
        baseline_path = root / "baseline.json"
        baseline_path.write_text(json.dumps(baseline), encoding="utf-8")
        return root, config, change, baseline_path, original

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

    def test_moved_leaf_keeps_parameter_and_connection_contract(self):
        before = snapshot()
        before["nodes"]["CityRoadCore/CR_CONTEXT/LEAF"] = {
            "type": "attribwrangle",
            "inputs": [{"input": 0, "source": "CityRoadCore/CR_CONTEXT/SOURCE", "output": 0}],
            "parameters": {"snippet": {"raw": "UNCHANGED_VEX", "expression": None}},
            "flags": {"bypass": False},
            "comment": "old comment",
        }
        after = copy.deepcopy(before)
        moved = after["nodes"].pop("CityRoadCore/CR_CONTEXT/LEAF")
        moved["inputs"][0]["source"] = (
            "CityRoadCore/CR_MAIN_PIPELINE/CR_CONTEXT/SOURCE")
        moved["comment"] = "learning comment"
        after["nodes"]["CityRoadCore/CR_MAIN_PIPELINE/CR_CONTEXT/LEAF"] = moved
        change = manifest()
        change["path_rewrites"] = [{
            "from": "CityRoadCore/CR_CONTEXT",
            "to": "CityRoadCore/CR_MAIN_PIPELINE/CR_CONTEXT",
        }]
        self.assertEqual([], gate.compare_snapshots(before, after, change))

    def test_moved_leaf_vex_change_is_blocked(self):
        before = snapshot()
        before["nodes"]["CityRoadCore/CR_CONTEXT/LEAF"] = {
            "type": "attribwrangle", "inputs": [],
            "parameters": {"snippet": {"raw": "ORIGINAL_VEX", "expression": None}},
            "flags": {"bypass": False}, "comment": "",
        }
        after = copy.deepcopy(before)
        moved = after["nodes"].pop("CityRoadCore/CR_CONTEXT/LEAF")
        moved["parameters"]["snippet"]["raw"] = "CHANGED_VEX"
        after["nodes"]["CityRoadCore/CR_MAIN_PIPELINE/CR_CONTEXT/LEAF"] = moved
        change = manifest()
        change["path_rewrites"] = [{
            "from": "CityRoadCore/CR_CONTEXT",
            "to": "CityRoadCore/CR_MAIN_PIPELINE/CR_CONTEXT",
        }]
        violations = gate.compare_snapshots(before, after, change)
        self.assertTrue(any("Moved node parameter changed" in item for item in violations))

    def test_moved_hscript_reference_may_gain_one_parent_level(self):
        before = snapshot()
        before["nodes"]["CityRoadCore/CR_CONTEXT/SWITCH"] = {
            "type": "switch", "inputs": [],
            "parameters": {"input": {
                "raw": 'ch("../../../toggle")',
                "expression": 'ch("../../../toggle")'}},
            "flags": {"bypass": False}, "comment": "",
        }
        after = copy.deepcopy(before)
        moved = after["nodes"].pop("CityRoadCore/CR_CONTEXT/SWITCH")
        moved["parameters"]["input"] = {
            "raw": 'ch("../../../../toggle")',
            "expression": 'ch("../../../../toggle")'}
        after["nodes"]["CityRoadCore/CR_MAIN_PIPELINE/CR_CONTEXT/SWITCH"] = moved
        change = manifest()
        change["path_rewrites"] = [{
            "from": "CityRoadCore/CR_CONTEXT",
            "to": "CityRoadCore/CR_MAIN_PIPELINE/CR_CONTEXT",
        }]
        self.assertEqual([], gate.compare_snapshots(before, after, change))


if __name__ == "__main__":
    unittest.main()
