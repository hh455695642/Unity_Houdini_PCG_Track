"""Capture and compare the current Houdini Live Scene for PCG change gates.

This script is invoked by ``.agents/scripts/Invoke-PcgRegression.ps1``.
It connects to the already-running Houdini GUI through hrpyc and performs
read-only inspection.  Capture also creates byte-for-byte backups of the
scoped HDA/HIP in ``.codex_tmp``; it never updates an HDA definition or HIP.

The comparison code deliberately has no dependency on ``hou`` so it can be
covered by ordinary Python unit tests.
"""

from __future__ import annotations

import argparse
import copy
import datetime as _datetime
import fnmatch
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
from typing import Any, Iterable


SCHEMA_VERSION = 1

MODULES: dict[str, dict[str, Any]] = {
    "CityRoad": {
        "asset_path": "/obj/CityRoad_DEV",
        "asset_type": "pcgbike::CityRoad::1.0",
        "definition": "Assets/PCG/HDA/City/CityRoad.hda",
        "hip": "HoudiniProject/PCG_Track_21.0.440/PCG_Bike_CityRoad.hip",
        "network_roots": ["CityRoadCore"],
        "outputs": [
            "CityRoadCore/OUT_ROAD_SURFACE",
            "CityRoadCore/OUT_SIDEWALK_CURB",
            "CityRoadCore/OUT_ROAD_COLLISION",
            "CityRoadCore/OUT_ROAD_MARKINGS",
        ],
    },
    "Track": {
        "asset_path": "/obj/Track1",
        "asset_type": "pcgbike::Track::1.0",
        "definition": "Assets/PCG/HDA/Track.hda",
        "hip": "HoudiniProject/PCG_Track_21.0.440/PCG_Bike_Track.hip",
        "network_roots": ["Road"],
        "outputs": ["Road/OUT_ROAD_MESH", "Road/OUT_ROAD_COLLISION"],
    },
    "Terrain": {
        "asset_path": "/obj/Terrain1",
        "asset_type": "pcgbike::Terrain::1.0",
        "definition": "Assets/PCG/HDA/Terrain.hda",
        "hip": "HoudiniProject/PCG_Track_21.0.440/PCG_Bike_Terrain.hip",
        "network_roots": ["TerrainCore", "TerrainCore/10_TERRAIN_SOURCE"],
        "outputs": ["TerrainCore/10_TERRAIN_SOURCE/OUT_BASE_HEIGHTFIELD"],
    },
    "StreetBuilding": {
        # This module is authored and validated in disposable hython processes.
        # The dirty CityRoad GUI session is an observed dependency, never a
        # persistence target for StreetBuilding.
        "isolated": True,
        "asset_path": "/obj/StreetBuilding_DEV",
        "asset_type": "pcgbike::StreetBuilding::1.0",
        "definition": "Assets/PCG/HDA/City/StreetBuilding.hda",
        "hip": "HoudiniProject/PCG_Track_21.0.440/PCG_Bike_StreetBuilding.hip",
        "builder": "HoudiniProject/PCG_Track_21.0.440/scripts/tools/patch_streetbuilding_direct_unity_instances_rev4.py",
        "restore_files": ["Assets/PCG/HDA/City/StreetBuilding.hda.meta"],
        "network_roots": ["StreetBuildingCore"],
        "outputs": [
            "StreetBuildingCore/OUT_BUILDING_LOD0",
            "StreetBuildingCore/OUT_BUILDING_LOD1",
            "StreetBuildingCore/OUT_BUILDING_LOD2",
            "StreetBuildingCore/OUT_DETAIL_INSTANCES",
            "StreetBuildingCore/OUT_BUILDING_COLLISION",
            "StreetBuildingCore/OUT_BUILDING_METADATA",
        ],
    },
}


class GateFailure(RuntimeError):
    """Raised when a regression gate invariant is violated."""


def canonical_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def normalize_path(path: str | Path) -> str:
    return str(path).replace("\\", "/")


def resolve_scoped_path(project_root: Path, relative_path: str) -> Path:
    candidate = (project_root / relative_path).resolve()
    try:
        candidate.relative_to(project_root.resolve())
    except ValueError as exc:
        raise GateFailure(f"Path escapes project root: {relative_path}") from exc
    return candidate


def load_manifest(path: Path, module: str) -> dict[str, Any]:
    if not path.is_file():
        raise GateFailure(f"Change manifest not found: {path}")
    data = json.loads(path.read_text(encoding="utf-8"))
    if data.get("schema_version") != SCHEMA_VERSION:
        raise GateFailure(f"Unsupported manifest schema_version: {data.get('schema_version')}")
    if data.get("module") != module:
        raise GateFailure(
            f"Manifest module {data.get('module')!r} does not match requested {module!r}")
    required = (
        "task",
        "allowed_files",
        "allowed_nodes",
        "allowed_added_nodes",
        "allowed_removed_nodes",
        "allowed_connections",
        "allowed_parameters",
        "allowed_public_parameters",
        "allow_output_changes",
        "required_contracts",
    )
    missing = [name for name in required if name not in data]
    if missing:
        raise GateFailure("Manifest missing required fields: " + ", ".join(missing))
    if not str(data["task"]).strip():
        raise GateFailure("Manifest task must be non-empty")
    if not data["required_contracts"]:
        raise GateFailure("Manifest required_contracts must be non-empty")
    for field in required[1:-2]:
        if not isinstance(data[field], list):
            raise GateFailure(f"Manifest field {field} must be an array")
    if not isinstance(data["allow_output_changes"], bool):
        raise GateFailure("Manifest allow_output_changes must be boolean")
    if not isinstance(data.get("allowed_warning_signatures", []), list):
        raise GateFailure("Manifest allowed_warning_signatures must be an array")
    if not isinstance(data.get("authoritative_live_scene", False), bool):
        raise GateFailure("Manifest authoritative_live_scene must be boolean")
    if not isinstance(data.get("path_rewrites", []), list):
        raise GateFailure("Manifest path_rewrites must be an array")
    for rewrite in data.get("path_rewrites", []):
        if (not isinstance(rewrite, dict) or
                not isinstance(rewrite.get("from"), str) or
                not isinstance(rewrite.get("to"), str)):
            raise GateFailure("Each path_rewrites entry needs string from/to fields")
    if not isinstance(data.get("moved_parameter_exceptions", []), list):
        raise GateFailure("Manifest moved_parameter_exceptions must be an array")
    return data


def matches(value: str, patterns: Iterable[str]) -> bool:
    normalized = normalize_path(value)
    return any(fnmatch.fnmatchcase(normalized, normalize_path(pattern)) for pattern in patterns)


def _changed_keys(before: dict[str, Any], after: dict[str, Any]) -> set[str]:
    return {key for key in before.keys() | after.keys() if before.get(key) != after.get(key)}


def _rewrite_path(value: str, rewrites: list[dict[str, str]], reverse: bool = False) -> str:
    """Rewrite an exact authored node root and all descendants."""
    normalized = normalize_path(value)
    ordered = sorted(rewrites, key=lambda item: len(item["from"]), reverse=True)
    for item in ordered:
        source = normalize_path(item["to"] if reverse else item["from"])
        target = normalize_path(item["from"] if reverse else item["to"])
        if normalized == source:
            return target
        if normalized.startswith(source.rstrip("/") + "/"):
            return target.rstrip("/") + normalized[len(source):]
    return normalized


def _normalize_moved_state(
    state: dict[str, Any], rewrites: list[dict[str, str]]
) -> dict[str, Any]:
    result = copy.deepcopy(state)
    for connection in result.get("inputs", []):
        source = connection.get("source")
        if isinstance(source, str):
            connection["source"] = _rewrite_path(source, rewrites, reverse=True)
    return result


def _is_one_level_relative_rewrite(before: Any, after: Any) -> bool:
    """Accept Houdini's deterministic path-depth update after subnet collapse."""
    if not isinstance(before, dict) or not isinstance(after, dict):
        return False
    if set(before) != set(after):
        return False
    def deepen(value: Any) -> Any:
        if not isinstance(value, str):
            return value
        return re.sub(r"([\"'])(?=(?:\.\./)+)", r"\1../", value)
    expected = {key: deepen(value) for key, value in before.items()}
    return expected == after


def compare_snapshots(
    baseline: dict[str, Any], current: dict[str, Any], manifest: dict[str, Any]
) -> list[str]:
    """Return human-readable violations; an empty list means the fast gate passed."""

    violations: list[str] = []
    if baseline.get("schema_version") != current.get("schema_version"):
        violations.append("Snapshot schema changed")
    for field in ("module", "asset_path", "asset_type", "definition", "hip"):
        if baseline.get("houdini", {}).get(field) != current.get("houdini", {}).get(field):
            violations.append(f"Houdini identity changed: {field}")

    allowed_files = manifest["allowed_files"]
    for path in _changed_keys(baseline.get("files", {}), current.get("files", {})):
        if not matches(path, allowed_files):
            violations.append(f"File changed outside allowlist: {path}")

    before_interface = baseline.get("public_interface", {})
    after_interface = current.get("public_interface", {})
    for key in sorted(_changed_keys(before_interface, after_interface)):
        if not matches(key, manifest["allowed_public_parameters"]):
            violations.append(f"Public interface changed outside allowlist: {key}")

    before_nodes = baseline.get("nodes", {})
    after_nodes = current.get("nodes", {})
    before_names = set(before_nodes)
    after_names = set(after_nodes)
    rewrites = manifest.get("path_rewrites", [])
    moved_pairs = {
        before_name: _rewrite_path(before_name, rewrites)
        for before_name in before_names
        if _rewrite_path(before_name, rewrites) != before_name and
        _rewrite_path(before_name, rewrites) in after_nodes
    }
    moved_before = set(moved_pairs)
    moved_after = set(moved_pairs.values())
    for before_name, after_name in sorted(moved_pairs.items()):
        before = before_nodes[before_name]
        after = _normalize_moved_state(after_nodes[after_name], rewrites)
        if before.get("type") != after.get("type"):
            violations.append(f"Moved node type changed: {before_name} -> {after_name}")
        if before.get("inputs") != after.get("inputs"):
            violations.append(f"Moved node inputs changed: {before_name} -> {after_name}")
        if before.get("flags") != after.get("flags"):
            violations.append(f"Moved node flags changed: {before_name} -> {after_name}")
        # Comments are an intentional readability surface.  Parameters are
        # behavior and remain byte-for-byte stable except for named interface
        # labels and the three TutorialLab bridge paths declared by manifest.
        before_parms = before.get("parameters", {})
        after_parms = after.get("parameters", {})
        for parm in sorted(_changed_keys(before_parms, after_parms)):
            scoped_name = f"{after_name}:{parm}"
            if (not _is_one_level_relative_rewrite(
                    before_parms.get(parm), after_parms.get(parm)) and
                    not matches(scoped_name,
                                manifest.get("moved_parameter_exceptions", []))):
                violations.append(
                    f"Moved node parameter changed: {before_name}:{parm} -> {after_name}")
    before_names -= moved_before
    after_names -= moved_after
    for node in sorted(after_names - before_names):
        if not (
            matches(node, manifest["allowed_added_nodes"])
            or matches(node, manifest["allowed_nodes"])
        ):
            violations.append(f"Node added outside allowlist: {node}")
    for node in sorted(before_names - after_names):
        if not (
            matches(node, manifest["allowed_removed_nodes"])
            or matches(node, manifest["allowed_nodes"])
        ):
            violations.append(f"Node removed outside allowlist: {node}")

    for node in sorted(before_names & after_names):
        before = before_nodes[node]
        after = after_nodes[node]
        node_allowed = matches(node, manifest["allowed_nodes"])
        if before.get("type") != after.get("type") and not node_allowed:
            violations.append(f"Node type changed outside allowlist: {node}")
        if before.get("inputs") != after.get("inputs") and not (
            node_allowed or matches(node, manifest["allowed_connections"])
        ):
            violations.append(f"Node inputs changed outside allowlist: {node}")
        if before.get("flags") != after.get("flags") and not node_allowed:
            violations.append(f"Node flags changed outside allowlist: {node}")
        if before.get("comment") != after.get("comment") and not node_allowed:
            violations.append(f"Node comment changed outside allowlist: {node}")
        before_parms = before.get("parameters", {})
        after_parms = after.get("parameters", {})
        for parm in sorted(_changed_keys(before_parms, after_parms)):
            scoped_name = f"{node}:{parm}"
            if not (node_allowed or matches(scoped_name, manifest["allowed_parameters"])):
                violations.append(f"Node parameter changed outside allowlist: {scoped_name}")

    if not manifest["allow_output_changes"]:
        # needs_cook is transient cache state, not output semantics. A validator
        # or benchmark may cook one formal output without changing its graph,
        # geometry, attributes, or diagnostics.
        baseline_outputs = {
            path: {key: value for key, value in state.items()
                   if key != "needs_cook"}
            for path, state in baseline.get("outputs", {}).items()
        }
        current_outputs = {
            path: {key: value for key, value in state.items()
                   if key != "needs_cook"}
            for path, state in current.get("outputs", {}).items()
        }
        changed_outputs = _changed_keys(
            baseline_outputs, current_outputs)
        for output in sorted(changed_outputs):
            violations.append(f"Output changed without allow_output_changes: {output}")

    baseline_warnings = set(baseline.get("diagnostics", {}).get("warnings", []))
    current_warnings = set(current.get("diagnostics", {}).get("warnings", []))
    allowed_warning_patterns = manifest.get("allowed_warning_signatures", [])
    for warning in sorted(current_warnings - baseline_warnings):
        if not matches(warning, allowed_warning_patterns):
            violations.append(f"New Houdini warning: {warning}")
    for error in current.get("diagnostics", {}).get("errors", []):
        violations.append(f"Houdini error: {error}")
    return violations


REMOTE_CAPTURE_CODE = r'''
import hashlib
import json
import hou

def _pcg_safe(callable_value, default=None):
    try:
        return callable_value()
    except Exception:
        return default

def _pcg_json_value(value):
    if value is None or isinstance(value, (bool, int, float, str)):
        return value
    if isinstance(value, (tuple, list)):
        return [_pcg_json_value(item) for item in value]
    return str(value)

def _pcg_template_type(template):
    value = _pcg_safe(lambda: template.type(), None)
    return _pcg_safe(lambda: value.name(), str(value)) if value is not None else "unknown"

def _pcg_public_interface(asset):
    result = {}
    def visit(templates, folder):
        for template in templates:
            name = _pcg_safe(lambda: template.name(), "")
            label = _pcg_safe(lambda: template.label(), "")
            kind = _pcg_template_type(template)
            key = ("/".join(folder + [name])) if name else ("/".join(folder + ["@" + label]))
            entry = {
                "name": name,
                "label": label,
                "type": kind,
                "folder": folder,
                "components": _pcg_safe(lambda: template.numComponents(), None),
                "default": _pcg_json_value(_pcg_safe(lambda: template.defaultValue(), None)),
                "min": _pcg_safe(lambda: template.minValue(), None),
                "max": _pcg_safe(lambda: template.maxValue(), None),
                "min_strict": _pcg_safe(lambda: template.minIsStrict(), None),
                "max_strict": _pcg_safe(lambda: template.maxIsStrict(), None),
                "menu_items": _pcg_json_value(_pcg_safe(lambda: template.menuItems(), None)),
                "menu_labels": _pcg_json_value(_pcg_safe(lambda: template.menuLabels(), None)),
                "hidden": _pcg_safe(lambda: template.isHidden(), None),
                "conditionals": str(_pcg_safe(lambda: template.conditionals(), {})),
            }
            result[key] = entry
            children = _pcg_safe(lambda: template.parmTemplates(), None)
            if children:
                visit(children, folder + [name or ("@" + label)])
    visit(asset.parmTemplateGroup().parmTemplates(), [])
    return result

def _pcg_parameter_state(node):
    always = {
        "snippet", "group", "class", "entity", "negate", "grouptype",
        "switcher", "input", "output", "method", "operation", "path"
    }
    result = {}
    for parm in node.parms():
        name = parm.name()
        include = name in always or not _pcg_safe(lambda: parm.isAtDefault(), True)
        expression = _pcg_safe(lambda: parm.expression(), None)
        if expression:
            include = True
        if not include:
            continue
        # rawValue/unexpandedString are structural reads.  eval() can trigger
        # dependency cooks and must not be used during Capture.
        raw = _pcg_safe(lambda: parm.rawValue(), None)
        if raw is None:
            raw = _pcg_safe(lambda: parm.unexpandedString(), None)
        result[name] = {
            "raw": raw,
            "expression": expression,
        }
    return result

def _pcg_relative(asset_path, path):
    if path == asset_path:
        return "."
    prefix = asset_path.rstrip("/") + "/"
    return path[len(prefix):] if path.startswith(prefix) else path

def _pcg_node_state(asset, node):
    asset_path = asset.path()
    inputs = []
    for connection in node.inputConnections():
        source_node = connection.inputNode()
        source_path = source_node.path() if source_node is not None else "<indirect>"
        inputs.append({
            "input": connection.inputIndex(),
            "source": _pcg_relative(asset_path, source_path),
            "output": connection.outputIndex(),
        })
    inputs.sort(key=lambda item: (item["input"], item["source"], item["output"]))
    node_type = node.type()
    return {
        "type": node_type.name(),
        "category": node_type.category().name(),
        "inputs": inputs,
        "parameters": _pcg_parameter_state(node),
        "flags": {
            "bypass": _pcg_safe(lambda: node.isBypassed(), None),
            "display": _pcg_safe(lambda: node.isDisplayFlagSet(), None),
            "render": _pcg_safe(lambda: node.isRenderFlagSet(), None),
        },
        "comment": _pcg_safe(lambda: node.comment(), ""),
    }

def _pcg_detail_values(geometry):
    result = {}
    for attrib in geometry.globalAttribs():
        name = attrib.name()
        value = _pcg_safe(lambda: geometry.attribValue(attrib), None)
        converted = _pcg_json_value(value)
        if isinstance(converted, (bool, int, float, str)) or (
                isinstance(converted, list) and len(converted) <= 16):
            result[name] = converted
    return result

def _pcg_output_state(asset, relative_path):
    node = asset.node(relative_path)
    if node is None:
        return {"missing": True, "errors": [], "warnings": []}
    needs_cook = _pcg_safe(lambda: node.needsToCook(), True)
    state = {
        "missing": False,
        "needs_cook": needs_cook,
        "type": node.type().name(),
        "errors": [],
        "warnings": [],
    }
    # Full validators own geometry and diagnostic checks.  Accessing geometry
    # or errors here may cook and dirty an editable production HDA.
    return state

def _pcg_find_asset(expected_path, expected_type):
    candidate = hou.node(expected_path)
    if candidate is not None and candidate.type().name() == expected_type:
        return candidate
    matches = [
        node for node in hou.node("/obj").children()
        if node.type().name() == expected_type
    ]
    if len(matches) != 1:
        raise RuntimeError(
            "Expected one {} instance, found {}: {}".format(
                expected_type, len(matches), [node.path() for node in matches]))
    return matches[0]

def _pcg_capture_live(module, config_json):
    config = json.loads(config_json)
    asset = _pcg_find_asset(config["asset_path"], config["asset_type"])
    initial_unsaved_changes = hou.hipFile.hasUnsavedChanges()
    definition = asset.type().definition()
    if definition is None:
        raise RuntimeError("Target asset has no HDA definition: " + asset.path())
    nodes = {".": _pcg_node_state(asset, asset)}
    # Capture authored CR_* navigation/function subnets recursively, but never
    # walk Wrangle/VOP internals.  V46 adds CR_MAIN_PIPELINE above the existing
    # function subnets; recursion keeps their leaf parameters/VEX protected.
    for network_path in config["network_roots"]:
        network = asset.node(network_path)
        if network is None:
            raise RuntimeError("Configured network root is missing: " + network_path)
        nodes[_pcg_relative(asset.path(), network.path())] = _pcg_node_state(asset, network)
        queue = [network]
        while queue:
            authored_network = queue.pop(0)
            for node in authored_network.children():
                nodes[_pcg_relative(asset.path(), node.path())] = _pcg_node_state(asset, node)
                if node.name().startswith("CR_") and node.type().name() == "subnet":
                    queue.append(node)
    outputs = {
        path: _pcg_output_state(asset, path) for path in config["outputs"]
    }
    diagnostics = {"errors": [], "warnings": []}
    for path, state in outputs.items():
        diagnostics["errors"].extend(path + ": " + value for value in state.get("errors", []))
        diagnostics["warnings"].extend(path + ": " + value for value in state.get("warnings", []))
    payload = {
        "schema_version": 1,
        "module": module,
        "houdini": {
            "module": module,
            "hip": hou.hipFile.path().replace("\\", "/"),
            "hip_unsaved_changes": initial_unsaved_changes,
            "hip_unsaved_changes_after_capture": hou.hipFile.hasUnsavedChanges(),
            "asset_path": asset.path(),
            "asset_type": asset.type().name(),
            "definition": definition.libraryFilePath().replace("\\", "/"),
            "editable": asset.isEditable(),
            "locked": asset.isLockedHDA(),
        },
        "public_interface": _pcg_public_interface(asset),
        "nodes": nodes,
        "outputs": outputs,
        "diagnostics": diagnostics,
    }
    return json.dumps(payload, ensure_ascii=False, sort_keys=True)

def _pcg_reload_current_clean():
    path = hou.hipFile.path()
    hou.hipFile.load(path, suppress_save_prompt=True, ignore_load_warnings=False)
    return {
        "hip": hou.hipFile.path().replace("\\", "/"),
        "unsaved": hou.hipFile.hasUnsavedChanges(),
    }
'''


def connect_live(host: str, port: int):
    try:
        import hrpyc
    except ImportError as exc:
        raise GateFailure("hrpyc is unavailable; run this script with Houdini hython") from exc
    connection, _remote_hou = hrpyc.import_remote_module(host, port, "hou")
    return connection


def capture_live(module: str, config: dict[str, Any], host: str, port: int) -> dict[str, Any]:
    connection = connect_live(host, port)
    try:
        connection.execute(REMOTE_CAPTURE_CODE)
        payload = connection.eval(
            "_pcg_capture_live({!r}, {!r})".format(module, canonical_json(config)))
        result = json.loads(str(payload))
        houdini_state = result.get("houdini", {})
        if (not houdini_state.get("hip_unsaved_changes")
                and houdini_state.get("hip_unsaved_changes_after_capture")):
            reload_result = dict(connection.eval("_pcg_reload_current_clean()"))
            if reload_result.get("unsaved"):
                raise GateFailure("Capture dirtied the Live Scene and automatic reload stayed dirty")
            houdini_state["capture_reloaded_clean"] = True
        return result
    finally:
        connection.close()


def capture_disk(module: str, config: dict[str, Any], project_root: Path) -> dict[str, Any]:
    """Capture the saved HIP in this disposable hython process, never the GUI."""

    try:
        import hou
    except ImportError as exc:
        raise GateFailure("Disk comparison requires Houdini hython") from exc
    hip_path = resolve_scoped_path(project_root, config["hip"])
    hou.hipFile.load(str(hip_path), suppress_save_prompt=True, ignore_load_warnings=False)
    namespace: dict[str, Any] = {}
    exec(REMOTE_CAPTURE_CODE, namespace)
    return json.loads(namespace["_pcg_capture_live"](module, canonical_json(config)))


def serialize_live_scene_backup(
    config: dict[str, Any], backup_root: Path, host: str, port: int
) -> Path:
    """Serialize a dirty GUI scene without changing its current HIP path.

    This is only used when a change manifest explicitly declares the Live
    Scene authoritative.  ``saveAsBackup`` preserves the current scene name,
    allowing Capture to protect approved unsaved work before any mutation.
    """

    backup_root.mkdir(parents=True, exist_ok=True)
    connection = connect_live(host, port)
    try:
        connection.execute(
            """
import hou
def _pcg_serialize_live_backup(backup_dir):
    original_hip = hou.hipFile.path().replace('\\\\', '/')
    old_backup_dir = hou.getenv('HOUDINI_BACKUP_DIR')
    try:
        hou.putenv('HOUDINI_BACKUP_DIR', backup_dir)
        backup_path = hou.hipFile.saveAsBackup()
    finally:
        if old_backup_dir is None:
            hou.unsetenv('HOUDINI_BACKUP_DIR')
        else:
            hou.putenv('HOUDINI_BACKUP_DIR', old_backup_dir)
    current_hip = hou.hipFile.path().replace('\\\\', '/')
    if current_hip.lower() != original_hip.lower():
        raise RuntimeError('saveAsBackup changed current HIP path: {} -> {}'.format(
            original_hip, current_hip))
    return backup_path
"""
        )
        backup_path = Path(str(connection.eval(
            "_pcg_serialize_live_backup({!r})".format(normalize_path(backup_root)))))
    finally:
        connection.close()
    if not backup_path.is_file():
        raise GateFailure(f"Live Scene backup was not created: {backup_path}")
    return backup_path.resolve()


def assert_live_matches_disk(live: dict[str, Any], disk: dict[str, Any]) -> None:
    """Fail closed when a dirty Live Scene contains any structural edit."""

    differences = []
    for field in ("asset_type", "definition"):
        if os.path.normcase(live["houdini"].get(field, "")) != os.path.normcase(
                disk["houdini"].get(field, "")):
            differences.append(f"identity:{field}")
    if live.get("public_interface") != disk.get("public_interface"):
        differences.append("public_interface")
    live_nodes = live.get("nodes", {})
    disk_nodes = disk.get("nodes", {})
    for node in sorted(set(live_nodes) | set(disk_nodes)):
        if live_nodes.get(node) != disk_nodes.get(node):
            differences.append("node:" + node)
            if len(differences) >= 21:
                break
    if differences:
        raise GateFailure(
            "Dirty Live Scene differs from the saved HIP; reconcile before Capture:\n- "
            + "\n- ".join(differences))


def git_status(project_root: Path) -> list[str]:
    result = subprocess.run(
        ["git", "status", "--short"],
        cwd=project_root,
        text=True,
        encoding="utf-8",
        errors="replace",
        capture_output=True,
        check=False,
    )
    if result.returncode != 0:
        raise GateFailure("git status failed: " + result.stderr.strip())
    return [line for line in result.stdout.splitlines() if line]


def file_state(project_root: Path, relative_paths: Iterable[str]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for relative in relative_paths:
        path = resolve_scoped_path(project_root, relative)
        result[normalize_path(relative)] = {
            "exists": path.is_file(),
            "size": path.stat().st_size if path.is_file() else None,
            "sha256": sha256_file(path) if path.is_file() else None,
        }
    return result


def assert_identity(snapshot: dict[str, Any], project_root: Path, config: dict[str, Any]) -> None:
    houdini = snapshot["houdini"]
    expected_hip = normalize_path(resolve_scoped_path(project_root, config["hip"]))
    expected_definition = normalize_path(resolve_scoped_path(project_root, config["definition"]))
    if os.path.normcase(houdini["hip"]) != os.path.normcase(expected_hip):
        raise GateFailure(
            f"Live HIP mismatch: expected {expected_hip}, got {houdini['hip']}")
    if os.path.normcase(houdini["definition"]) != os.path.normcase(expected_definition):
        raise GateFailure(
            "Live HDA definition mismatch: "
            f"expected {expected_definition}, got {houdini['definition']}")
    if houdini["asset_type"] != config["asset_type"]:
        raise GateFailure(
            f"Live asset type mismatch: expected {config['asset_type']}, got {houdini['asset_type']}")


def default_snapshot_path(project_root: Path, module: str, task: str) -> Path:
    safe_task = "".join(character if character.isalnum() or character in "-_" else "-" for character in task)
    safe_task = safe_task.strip("-") or "task"
    stamp = _datetime.datetime.now().strftime("%Y%m%d-%H%M%S")
    return project_root / ".codex_tmp" / "regression" / f"{stamp}-{module}-{safe_task}" / "baseline.json"


def isolated_snapshot(
    project_root: Path, module: str, config: dict[str, Any]
) -> dict[str, Any]:
    """Describe an isolated module without reading or mutating the live GUI."""

    return {
        "schema_version": SCHEMA_VERSION,
        "module": module,
        "houdini": {
            "module": module,
            "hip": normalize_path(resolve_scoped_path(project_root, config["hip"])),
            "hip_unsaved_changes": False,
            "asset_path": config["asset_path"],
            "asset_type": config["asset_type"],
            "definition": normalize_path(
                resolve_scoped_path(project_root, config["definition"])),
            "editable": False,
            "locked": True,
            "isolated_process": True,
        },
        "public_interface": {},
        "nodes": {},
        "outputs": {},
        "diagnostics": {"errors": [], "warnings": []},
    }


def write_capture(
    project_root: Path,
    module: str,
    config: dict[str, Any],
    manifest: dict[str, Any],
    snapshot_path: Path,
    host: str,
    port: int,
) -> dict[str, Any]:
    backup_root = snapshot_path.parent / "backup"
    backup_root.mkdir(parents=True, exist_ok=True)
    authoritative_live_backup: Path | None = None
    if config.get("isolated"):
        snapshot = isolated_snapshot(project_root, module, config)
        assert_identity(snapshot, project_root, config)
    else:
        snapshot = capture_live(module, config, host, port)
        assert_identity(snapshot, project_root, config)
        if snapshot["houdini"].get("hip_unsaved_changes"):
            disk_snapshot = capture_disk(module, config, project_root)
            if manifest.get("authoritative_live_scene", False):
                authoritative_live_backup = serialize_live_scene_backup(
                    config, backup_root, host, port)
                snapshot["houdini"]["authoritative_live_scene"] = True
                snapshot["houdini"]["live_backup"] = normalize_path(
                    authoritative_live_backup.relative_to(project_root))
            else:
                assert_live_matches_disk(snapshot, disk_snapshot)
                snapshot["houdini"]["unsaved_changes_verified_against_disk"] = True
        if (snapshot["houdini"].get("hip_unsaved_changes_after_capture")
                and not snapshot["houdini"].get("capture_reloaded_clean")
                and not snapshot["houdini"].get("unsaved_changes_verified_against_disk")
                and not snapshot["houdini"].get("authoritative_live_scene")):
            raise GateFailure(
                "Capture left an unverified dirty Live Scene; no baseline was written. "
                "Reload the HIP and inspect the capture path.")

    scoped_files = sorted(set([config["definition"], config["hip"], *manifest["allowed_files"]]))
    snapshot["captured_at"] = _datetime.datetime.now(_datetime.timezone.utc).isoformat()
    snapshot["git_status"] = git_status(project_root)
    snapshot["files"] = file_state(project_root, scoped_files)
    snapshot["manifest_sha256"] = sha256_bytes(canonical_json(manifest).encode("utf-8"))

    snapshot_path.parent.mkdir(parents=True, exist_ok=True)
    backups: dict[str, str] = {}
    backup_sha256: dict[str, str] = {}
    for relative in (config["definition"], config["hip"], *config.get("restore_files", [])):
        source = resolve_scoped_path(project_root, relative)
        if relative == config["hip"] and authoritative_live_backup is not None:
            source = authoritative_live_backup
        if not source.is_file() and config.get("isolated"):
            # A missing HDA/HIP pair is the valid baseline for a new isolated
            # asset. Restore will remove only these exact files if needed.
            continue
        if not source.is_file():
            raise GateFailure(f"Required baseline file not found: {source}")
        destination = backup_root / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, destination)
        backups[relative] = normalize_path(destination.relative_to(project_root))
        backup_sha256[relative] = sha256_file(destination)
    snapshot["backups"] = backups
    snapshot["backup_sha256"] = backup_sha256
    snapshot_path.write_text(json.dumps(snapshot, ensure_ascii=False, indent=2), encoding="utf-8")
    return snapshot


def load_baseline(path: Path) -> dict[str, Any]:
    if not path.is_file():
        raise GateFailure(f"Baseline snapshot not found: {path}")
    return json.loads(path.read_text(encoding="utf-8"))


def verify_fast(
    project_root: Path,
    module: str,
    config: dict[str, Any],
    manifest: dict[str, Any],
    snapshot_path: Path,
    host: str,
    port: int,
) -> dict[str, Any]:
    baseline = load_baseline(snapshot_path)
    expected_manifest_hash = sha256_bytes(canonical_json(manifest).encode("utf-8"))
    if baseline.get("manifest_sha256") != expected_manifest_hash:
        raise GateFailure("Change manifest differs from the one used by Capture")
    current = (
        isolated_snapshot(project_root, module, config)
        if config.get("isolated")
        else capture_live(module, config, host, port)
    )
    assert_identity(current, project_root, config)
    scoped_files = baseline.get("files", {}).keys()
    current["files"] = file_state(project_root, scoped_files)
    violations = compare_snapshots(baseline, current, manifest)
    if violations:
        raise GateFailure("VerifyFast failed:\n- " + "\n- ".join(violations))
    return {
        "status": "PASS",
        "module": module,
        "stage": "VerifyFast",
        "snapshot": normalize_path(snapshot_path),
        "live_unsaved_changes": current["houdini"].get("hip_unsaved_changes", False),
        "node_count": len(current.get("nodes", {})),
        "required_contracts": manifest["required_contracts"],
    }


def persist_isolated(
    project_root: Path,
    module: str,
    config: dict[str, Any],
    manifest: dict[str, Any],
    snapshot_path: Path,
) -> dict[str, Any]:
    """Create a new asset in a disposable hython process, never in Live GUI."""

    baseline = load_baseline(snapshot_path)
    expected_manifest_hash = sha256_bytes(canonical_json(manifest).encode("utf-8"))
    if baseline.get("manifest_sha256") != expected_manifest_hash:
        raise GateFailure("Change manifest differs from the one used by Capture")
    definition = config["definition"]
    hip = config["hip"]
    definition_allowed = matches(definition, manifest["allowed_files"])
    hip_allowed = matches(hip, manifest["allowed_files"])
    if definition_allowed != hip_allowed:
        raise GateFailure(
            "Isolated persistence must authorize both HDA and HIP, or neither")

    # Unity-only authoring tasks deliberately leave the persisted Houdini files
    # outside the modification whitelist. Verify their exact Capture hashes and
    # run the remaining cumulative validators without needlessly re-saving the
    # binary HIP through the historical builder.
    if not definition_allowed:
        states = file_state(project_root, (definition, hip))
        changed = [
            relative
            for relative, state in states.items()
            if state.get("sha256")
            != baseline.get("files", {}).get(relative, {}).get("sha256")
        ]
        if changed:
            raise GateFailure(
                "Unity-only VerifyFull detected unauthorized Houdini file changes: "
                + ", ".join(changed))
        return {
            "status": "PASS",
            "module": module,
            "stage": "Persist",
            "persistence": "not-required",
            "snapshot": normalize_path(snapshot_path),
            "files": states,
            "houdini": {"isolated_process": True, "live_scene_untouched": True},
        }

    builder = resolve_scoped_path(project_root, config["builder"])
    result = subprocess.run(
        [
            sys.executable,
            str(builder),
            "--project-root",
            str(project_root),
            "--save",
            "true",
            "--update-existing",
            "true",
        ],
        cwd=project_root,
        text=True,
        encoding="utf-8",
        errors="replace",
        capture_output=True,
        check=False,
    )
    if result.stdout:
        print(result.stdout, end="")
    if result.returncode != 0:
        raise GateFailure(
            "Isolated builder failed:\n" + (result.stderr or result.stdout).strip())
    states = file_state(project_root, (config["definition"], config["hip"]))
    missing = [path for path, state in states.items() if not state["exists"]]
    if missing:
        raise GateFailure("Isolated builder did not create: " + ", ".join(missing))
    return {
        "status": "PASS",
        "module": module,
        "stage": "Persist",
        "persistence": "completed",
        "snapshot": normalize_path(snapshot_path),
        "files": states,
        "houdini": {"isolated_process": True, "live_scene_untouched": True},
    }


def persist_live(
    project_root: Path,
    module: str,
    config: dict[str, Any],
    manifest: dict[str, Any],
    snapshot_path: Path,
    host: str,
    port: int,
) -> dict[str, Any]:
    """Persist the already-verified Live Scene to its exact HDA/HIP targets."""

    if config.get("isolated"):
        return persist_isolated(project_root, module, config, manifest, snapshot_path)

    baseline = load_baseline(snapshot_path)
    expected_manifest_hash = sha256_bytes(canonical_json(manifest).encode("utf-8"))
    if baseline.get("manifest_sha256") != expected_manifest_hash:
        raise GateFailure("Change manifest differs from the one used by Capture")
    for relative in (config["definition"], config["hip"], *config.get("restore_files", [])):
        if not matches(relative, manifest["allowed_files"]):
            raise GateFailure(
                f"VerifyFull persistence requires allowed_files to include {relative}")

    expected_hip = normalize_path(resolve_scoped_path(project_root, config["hip"]))
    expected_definition = normalize_path(
        resolve_scoped_path(project_root, config["definition"]))
    connection = connect_live(host, port)
    try:
        preserve_public_interface = not bool(manifest.get("allowed_public_parameters", []))
        connection.execute(
            """
import hou
def _pcg_persist_live(expected_path, expected_type, expected_hip, expected_definition,
                      preserve_public_interface):
    asset = hou.node(expected_path)
    if asset is None or asset.type().name() != expected_type:
        matches = [node for node in hou.node('/obj').children() if node.type().name() == expected_type]
        if len(matches) != 1:
            raise RuntimeError('Unable to resolve one persistence target: {}'.format([node.path() for node in matches]))
        asset = matches[0]
    definition = asset.type().definition()
    if definition is None:
        raise RuntimeError('Persistence target has no HDA definition')
    actual_hip = hou.hipFile.path().replace('\\\\', '/')
    actual_definition = definition.libraryFilePath().replace('\\\\', '/')
    if actual_hip.lower() != expected_hip.lower():
        raise RuntimeError('HIP changed before persistence: {} != {}'.format(actual_hip, expected_hip))
    if actual_definition.lower() != expected_definition.lower():
        raise RuntimeError('Definition changed before persistence: {} != {}'.format(actual_definition, expected_definition))
    original_templates = definition.parmTemplateGroup()
    definition.updateFromNode(asset)
    if preserve_public_interface:
        # Internal network edits can make Houdini synthesize instance-only
        # baseparm/folder ids on the unlocked implementation node.  They are
        # not public API and must never leak into a definition when the
        # manifest allows no public parameter changes.
        definition.setParmTemplateGroup(original_templates)
    else:
        # Only a manifest with an explicit public-parameter allowlist may
        # promote the verified Live template group into the definition.
        definition.setParmTemplateGroup(asset.parmTemplateGroup())
    hou.hipFile.save()
    return {
        'asset_path': asset.path(),
        'hip': hou.hipFile.path().replace('\\\\', '/'),
        'definition': definition.libraryFilePath().replace('\\\\', '/'),
        'hip_unsaved_changes': hou.hipFile.hasUnsavedChanges(),
    }
"""
        )
        payload = connection.eval(
            "_pcg_persist_live({!r}, {!r}, {!r}, {!r}, {!r})".format(
                config["asset_path"], config["asset_type"], expected_hip,
                expected_definition, preserve_public_interface))
        persisted = dict(payload)
    finally:
        connection.close()
    if persisted.get("hip_unsaved_changes"):
        raise GateFailure("Houdini still reports unsaved changes after persistence")
    return {
        "status": "PASS",
        "module": module,
        "stage": "Persist",
        "snapshot": normalize_path(snapshot_path),
        "files": file_state(project_root, (config["definition"], config["hip"])),
        "houdini": persisted,
    }


def restore_baseline(
    project_root: Path,
    module: str,
    config: dict[str, Any],
    snapshot_path: Path,
    host: str,
    port: int,
) -> dict[str, Any]:
    """Restore only the two scoped files captured for this gate and reload Live Scene."""

    baseline = load_baseline(snapshot_path)
    restored: dict[str, str] = {}
    restore_targets = [config["definition"], config["hip"], *config.get("restore_files", [])]
    for relative in restore_targets:
        backup_relative = baseline.get("backups", {}).get(relative)
        if not backup_relative:
            expected_state = baseline.get("files", {}).get(relative, {})
            destination = resolve_scoped_path(project_root, relative)
            if config.get("isolated") and not expected_state.get("exists", False):
                if destination.is_file():
                    destination.unlink()
                    restored[relative] = "REMOVED_NEW_FILE"
                continue
            raise GateFailure(f"Baseline has no backup entry for {relative}")
        source = resolve_scoped_path(project_root, backup_relative)
        destination = resolve_scoped_path(project_root, relative)
        if not source.is_file():
            raise GateFailure(f"Baseline backup is missing: {source}")
        expected_hash = baseline.get("backup_sha256", {}).get(relative)
        if expected_hash is None:
            expected_hash = baseline.get("files", {}).get(relative, {}).get("sha256")
        if expected_hash and sha256_file(source) != expected_hash:
            raise GateFailure(f"Baseline backup hash mismatch: {source}")
        shutil.copy2(source, destination)
        restored[relative] = sha256_file(destination)

    if config.get("isolated"):
        return {
            "status": "RESTORED",
            "module": module,
            "stage": "Restore",
            "snapshot": normalize_path(snapshot_path),
            "files": restored,
            "houdini": {"isolated_process": True, "live_scene_untouched": True},
        }

    hip_path = normalize_path(resolve_scoped_path(project_root, config["hip"]))
    hda_path = normalize_path(resolve_scoped_path(project_root, config["definition"]))
    connection = connect_live(host, port)
    try:
        connection.execute(
            """
import hou
def _pcg_reload_restored(hip_path, hda_path):
    hou.hda.installFile(hda_path)
    hou.hipFile.load(hip_path, suppress_save_prompt=True, ignore_load_warnings=False)
    return {
        'hip': hou.hipFile.path().replace('\\\\', '/'),
        'unsaved': hou.hipFile.hasUnsavedChanges(),
    }
"""
        )
        live = dict(connection.eval(
            "_pcg_reload_restored({!r}, {!r})".format(hip_path, hda_path)))
    finally:
        connection.close()
    return {
        "status": "RESTORED",
        "module": module,
        "stage": "Restore",
        "snapshot": normalize_path(snapshot_path),
        "files": restored,
        "houdini": live,
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--module", choices=sorted(MODULES), required=True)
    parser.add_argument(
        "--stage", choices=("capture", "verify-fast", "persist", "restore"), required=True)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--project-root", type=Path, required=True)
    parser.add_argument("--snapshot", type=Path)
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=18811)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    project_root = args.project_root.resolve()
    manifest_path = args.manifest.resolve()
    manifest = load_manifest(manifest_path, args.module)
    config = dict(MODULES[args.module])
    config["asset_path"] = manifest.get("asset_path", config["asset_path"])
    snapshot_path = (
        args.snapshot.resolve()
        if args.snapshot
        else default_snapshot_path(project_root, args.module, manifest["task"])
    )

    if args.stage == "capture":
        snapshot = write_capture(
            project_root, args.module, config, manifest, snapshot_path, args.host, args.port)
        result = {
            "status": "PASS",
            "module": args.module,
            "stage": "Capture",
            "snapshot": normalize_path(snapshot_path),
            "node_count": len(snapshot.get("nodes", {})),
            "backups": snapshot["backups"],
        }
    elif args.stage == "verify-fast":
        if args.snapshot is None:
            raise GateFailure("--snapshot is required for verify-fast")
        result = verify_fast(
            project_root, args.module, config, manifest, snapshot_path, args.host, args.port)
    elif args.stage == "persist":
        if args.snapshot is None:
            raise GateFailure("--snapshot is required for persist")
        try:
            result = persist_live(
                project_root, args.module, config, manifest,
                snapshot_path, args.host, args.port)
        except Exception:
            baseline = load_baseline(snapshot_path)
            current_files = file_state(
                project_root, (config["definition"], config["hip"]))
            baseline_files = baseline.get("files", {})
            changed = any(
                current_files.get(path, {}).get("sha256")
                != baseline_files.get(path, {}).get("sha256")
                for path in (config["definition"], config["hip"])
            )
            if changed:
                restore_baseline(
                    project_root, args.module, config,
                    snapshot_path, args.host, args.port)
            raise
    else:
        if args.snapshot is None:
            raise GateFailure("--snapshot is required for restore")
        result = restore_baseline(
            project_root, args.module, config, snapshot_path, args.host, args.port)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (GateFailure, OSError, ValueError, json.JSONDecodeError) as exception:
        print(f"GATE_FAIL: {exception}", file=sys.stderr)
        raise SystemExit(1)
