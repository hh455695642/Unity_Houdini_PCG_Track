"""Remove the unused stock Subnet tab from the CityRoad public interface.

This is an incremental, Live-Scene-first V21 patch.  It never saves unless
``save=True`` is explicitly requested by the regression persistence stage.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

import hou


ASSET_PATH = "/obj/CityRoad_DEV"
ASSET_TYPE = "pcgbike::CityRoad::1.0"
EXPECTED_HIP_SUFFIX = "/HoudiniProject/PCG_Track_21.0.440/PCG_Bike_CityRoad.hip"
EXPECTED_HDA_SUFFIX = "/Assets/PCG/HDA/City/CityRoad.hda"
EXPECTED_PUBLIC_HASH = "408bd642613842797ff4cb417242ebc838edcacd371b396ecc8126fe33a8c5c8"
LEGACY_FOLDER_NAME = "stdswitcher9_1"
LEGACY_FOLDER_LABEL = "Subnet"
MARKER = "CITYROAD_V21_PUBLIC_PARAMETER_CLEANUP"


def _normalize(path: str) -> str:
    return path.replace("\\", "/")


def _safe(callable_value, default=None):
    try:
        return callable_value()
    except Exception:
        return default


def _json_value(value):
    if value is None or isinstance(value, (bool, int, float, str)):
        return value
    if isinstance(value, (tuple, list)):
        return [_json_value(item) for item in value]
    return str(value)


def _public_interface_hash(asset: hou.Node) -> str:
    result = {}

    def visit(templates, folder):
        for template in templates:
            name = _safe(template.name, "")
            label = _safe(template.label, "")
            template_type = _safe(template.type)
            kind = (_safe(template_type.name, str(template_type))
                    if template_type is not None else "unknown")
            key = "/".join(folder + [name or ("@" + label)])
            result[key] = {
                "name": name,
                "label": label,
                "type": kind,
                "folder": folder,
                "components": _safe(lambda: template.numComponents()),
                "default": _json_value(_safe(lambda: template.defaultValue())),
                "min": _safe(lambda: template.minValue()),
                "max": _safe(lambda: template.maxValue()),
                "min_strict": _safe(lambda: template.minIsStrict()),
                "max_strict": _safe(lambda: template.maxIsStrict()),
                "menu_items": _json_value(_safe(lambda: template.menuItems())),
                "menu_labels": _json_value(_safe(lambda: template.menuLabels())),
                "hidden": _safe(lambda: template.isHidden()),
                "conditionals": str(_safe(lambda: template.conditionals(), {})),
            }
            children = _safe(lambda: template.parmTemplates())
            if children:
                visit(children, folder + [name or ("@" + label)])

    visit(asset.parmTemplateGroup().parmTemplates(), [])
    payload = json.dumps(result, ensure_ascii=False, sort_keys=True,
                         separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _find_legacy_folder(group: hou.ParmTemplateGroup):
    exact = group.find(LEGACY_FOLDER_NAME)
    if exact is not None and exact.label() == LEGACY_FOLDER_LABEL:
        return exact
    for template in group.parmTemplates():
        if (isinstance(template, hou.FolderParmTemplate)
                and template.label() == LEGACY_FOLDER_LABEL):
            return template
    return None


def _preflight() -> hou.Node:
    asset = hou.node(ASSET_PATH)
    if asset is None or asset.type().name() != ASSET_TYPE:
        raise RuntimeError(f"CityRoad V21 target mismatch: {ASSET_PATH}")
    definition = asset.type().definition()
    if definition is None:
        raise RuntimeError("CityRoad V21 target has no HDA definition")
    if not _normalize(hou.hipFile.path()).endswith(EXPECTED_HIP_SUFFIX):
        raise RuntimeError(f"Unexpected HIP: {hou.hipFile.path()}")
    if not _normalize(definition.libraryFilePath()).endswith(EXPECTED_HDA_SUFFIX):
        raise RuntimeError(f"Unexpected HDA: {definition.libraryFilePath()}")
    if asset.isLockedHDA():
        raise RuntimeError("CityRoad V21 target must be the unlocked production instance")
    if asset.parm("enable_city_park") is None:
        raise RuntimeError("CityRoad V20 public park contract is missing")
    if asset.node("CityRoadCore/CR_CITY_PARK") is None:
        raise RuntimeError("CityRoad V20 park subnet is missing")
    return asset


def validate(asset: hou.Node) -> dict:
    group = asset.parmTemplateGroup()
    legacy = _find_legacy_folder(group)
    if legacy is not None:
        raise RuntimeError(
            f"Unused CityRoad public folder still exists: {legacy.name()} / {legacy.label()}")
    if asset.parm("enable_city_park") is None or asset.parm("unity_park_areas") is None:
        raise RuntimeError("CityRoad park parameters were damaged by public cleanup")
    return {
        "status": "PASS",
        "marker": asset.userData("cityroad_public_cleanup_marker"),
        "public_hash": _public_interface_hash(asset),
        "subnet_tab_removed": True,
        "park_contract_preserved": True,
    }


def apply(save: bool = False) -> dict:
    asset = _preflight()
    existing = _find_legacy_folder(asset.parmTemplateGroup())
    if existing is None:
        return {"idempotent": True, **validate(asset)}

    before_hash = _public_interface_hash(asset)
    if before_hash != EXPECTED_PUBLIC_HASH:
        raise RuntimeError(
            f"CityRoad V21 public pre-hash mismatch: {before_hash} != {EXPECTED_PUBLIC_HASH}")

    original_group = asset.parmTemplateGroup()
    original_marker = asset.userData("cityroad_public_cleanup_marker")
    try:
        with hou.undos.group("CityRoad V21 Remove Unused Subnet Parameters"):
            updated = asset.parmTemplateGroup()
            updated.remove(existing.name())
            if updated.find(existing.name()) is not None:
                raise RuntimeError(f"Failed to remove public folder {existing.name()}")
            asset.setParmTemplateGroup(updated)
            asset.setUserData("cityroad_public_cleanup_marker", MARKER)
            result = validate(asset)
            if save:
                definition = asset.type().definition()
                definition.updateFromNode(asset)
                definition.setParmTemplateGroup(asset.parmTemplateGroup())
                hou.hipFile.save()
            return {"idempotent": False, "before_hash": before_hash,
                    "saved": bool(save), **result}
    except Exception:
        asset.setParmTemplateGroup(original_group)
        if original_marker is None:
            if asset.userData("cityroad_public_cleanup_marker") is not None:
                asset.destroyUserData("cityroad_public_cleanup_marker")
        else:
            asset.setUserData("cityroad_public_cleanup_marker", original_marker)
        raise


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=18811)
    parser.add_argument("--save", default="false")
    args = parser.parse_args()

    import hrpyc
    connection, _remote_hou = hrpyc.import_remote_module(args.host, args.port, "hou")
    try:
        tools_path = str(Path(__file__).resolve().parent).replace("\\", "/")
        connection.execute(
            "import sys, importlib; "
            f"sys.path.insert(0, {tools_path!r}) if {tools_path!r} not in sys.path else None; "
            "import patch_cityroad_public_cleanup_v21_20260813 as _cleanup_patch; "
            "importlib.reload(_cleanup_patch)")
        payload = connection.eval(
            "_cleanup_patch.apply(save="
            + ("True" if args.save.lower() == "true" else "False")
            + ")")
        print(json.dumps(payload, ensure_ascii=False, default=list, indent=2))
    finally:
        connection.close()


if __name__ == "__main__":
    main()
