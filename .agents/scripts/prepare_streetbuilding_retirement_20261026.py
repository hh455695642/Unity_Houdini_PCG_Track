"""Create an exact rollback inventory from the live AssetDatabase retirement audit.

Only reads Assets and writes into this task's .codex_tmp/regression directory.
Actual removal remains a separate, typed Unity Pipeline asset-delete operation.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil


RETIRED_ROOT = "Assets/PCG/Generated/Buildings/ReferenceAttachments"
RETIRED_SCENES = (
    "Assets/PCG/Scenes/StreetBuilding_AttachmentValidation.unity",
    "Assets/PCG/Scenes/StreetBuilding_ReferenceValidation.unity",
)


def native_path(path: Path) -> Path:
    # Task evidence adds several directories to already deep Unity asset paths.
    return Path("\\\\?\\" + str(path.resolve())) if os.name == "nt" else path


def sha(path: Path) -> str:
    return hashlib.sha256(native_path(path).read_bytes()).hexdigest()


def allowed(path: str) -> bool:
    return path in RETIRED_SCENES or path == RETIRED_ROOT or path.startswith(RETIRED_ROOT + "/")


def prepare(audit_path: Path, task_root: Path) -> dict:
    project = Path(__file__).resolve().parents[2]
    permitted = (project / ".codex_tmp/regression").resolve()
    task_root = task_root.resolve()
    if not task_root.is_relative_to(permitted) or task_root == permitted:
        raise ValueError("A unique task root under .codex_tmp/regression is required")
    audit = json.loads(audit_path.read_text(encoding="utf-8-sig"))
    if audit.get("status") != "NO_EXTERNAL_REFERENCES_FOUND":
        raise ValueError("The fresh AssetDatabase/Live audit requires review")
    if any(audit.get(key) for key in ("externalReferences", "liveReferences", "buildSettingsReferences", "unknownCases")):
        raise ValueError("The audit has external ownership or unknown cases")
    if any(scene.get("isLoaded") and scene.get("path") in RETIRED_SCENES
           for scene in audit.get("scenes", [])):
        raise ValueError("Close and preserve retired Live scenes before deletion")
    backup = task_root / "backup/retired-unity-assets"
    manifest_path = task_root / "cleanup-manifest.json"
    if manifest_path.exists():
        raise FileExistsError("Do not overwrite an existing cleanup inventory")
    rows = []
    for candidate in audit["candidates"]:
        relative = candidate["path"]
        source = (project / relative).resolve()
        if not allowed(relative) or not source.is_relative_to(project / "Assets"):
            raise ValueError(f"Out-of-scope candidate: {relative}")
        files = []
        for name, expected_key in ((relative, "sha256"), (relative + ".meta", "metaSha256")):
            item = project / name
            if item.is_dir():
                continue
            if not item.is_file():
                raise FileNotFoundError(f"Audit became stale: {name}")
            digest = sha(item)
            if digest != candidate[expected_key]:
                raise ValueError(f"Audit hash changed: {name}")
            destination = backup / name
            if native_path(destination).exists():
                if sha(destination) != digest:
                    raise ValueError(f"Existing rollback copy disagrees: {name}")
            else:
                native_path(destination.parent).mkdir(parents=True, exist_ok=True)
                shutil.copy2(native_path(item), native_path(destination))
            files.append({"path": name, "sha256": digest, "backup": destination.relative_to(project).as_posix()})
        rows.append({"path": relative, "guid": candidate["guid"], "type": candidate["type"],
                     "folder": candidate["folder"], "reason": candidate["reason"],
                     "dependencies": candidate["dependencies"], "files": files})
    report = {
        "schema_version": 1,
        "task": "streetbuilding-placement-20261026-retirement",
        "status": "BACKED_UP_NOT_DELETED",
        "source_audit": str(audit_path.resolve()),
        "source_audit_sha256": sha(audit_path),
        "candidate_count": len(rows),
        "backup_file_count": sum(len(row["files"]) for row in rows),
        "typed_delete_roots": [*RETIRED_SCENES, RETIRED_ROOT],
        "candidates": rows,
        "preserve": [
            "Assets/PCG/Art/Building_Test/Style1/**",
            "Assets/PCG/Materials/**", "Assets/PCG/Texture/**",
            "Assets/PCG/Generated/Buildings/MyTestCityFrontage/**",
            "Assets/PCG/Generated/Buildings/MyTestCityVaried/**",
            "Assets/PCG/Scenes/PCG_Building.unity",
            ".codex_tmp/regression/**",
        ],
        "next_step": "Use the reviewed manifest with a separate cleanup Capture; typed Pipeline asset delete only. Re-audit before deletion if live or disk changes.",
    }
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    return {"manifest": str(manifest_path), "candidateCount": len(rows), "backupFileCount": report["backup_file_count"]}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--audit", type=Path, required=True)
    parser.add_argument("--task-root", type=Path, required=True)
    options = parser.parse_args()
    print(json.dumps(prepare(options.audit, options.task_root), ensure_ascii=False))
