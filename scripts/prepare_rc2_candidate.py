"""Build an additive RC2 candidate bank, never activating or editing RC1.

Only copies and deterministic text/metadata transformations are performed.
No model, container, shell, credential or historical experiment is accessed.
An existing output is never overwritten; a partial build is retained for audit.
"""
from __future__ import annotations

import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import shutil
import tomllib

from task_sets import MAIN_47, HARD_RELEASE_15
from validate_upgraded_tasks import task_digest, IGNORED
from rc2_task_patches import (
    patch_review_state, patch_replay_verifier, clarify_submission_readme,
)

ROOT = Path(__file__).resolve().parents[1]
BANK_62 = (*MAIN_47, *HARD_RELEASE_15)
SOURCE_VERSION = "2.0.0-rc.1"
VERSION = "2.0.0-rc.2"
REVISION = "contract-diagnostics-2026-10-25"
DEFAULT_CANDIDATE = ROOT / "task-banks" / "rc2"


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def document_digest(value: dict) -> str:
    body = {key: item for key, item in value.items() if key != "manifest_sha256"}
    return hashlib.sha256(json.dumps(body, sort_keys=True, ensure_ascii=False).encode()).hexdigest()


def replace_once(text: str, old: str, new: str) -> str:
    if text.count(old) != 1:
        raise ValueError("expected exactly one source anchor: " + old[:80])
    return text.replace(old, new, 1)


def write_text(path: Path, text: str) -> None:
    path.write_text(text, encoding="utf-8", newline="\n")


def reject_links(path: Path) -> None:
    for part in (*reversed(path.absolute().parents), path.absolute()):
        if part.is_symlink() or (hasattr(part, "is_junction") and part.is_junction()):
            raise ValueError("candidate/source link or junction not allowed")


def protected_files(root: Path = ROOT) -> dict:
    """Hash source task bank and the old executor's bound source files."""
    from v2_pipeline import HARNESS_SOURCES, PIPELINE_SOURCES, EXECUTION_SOURCES

    files = set(HARNESS_SOURCES + PIPELINE_SOURCES + EXECUTION_SOURCES)
    files.update(("VERSION", "task-bank-v2.manifest.json"))
    files.update(path.relative_to(root).as_posix()
                 for task in BANK_62 for path in (root / "tasks" / task).rglob("*")
                 if path.is_file() and not IGNORED.intersection(path.parts)
                 and path.suffix not in {".pyc", ".pyo"})
    return {name: sha(root / name) for name in sorted(files)}


def validate_source(root: Path) -> dict:
    path = root / "task-bank-v2.manifest.json"
    reject_links(path)
    bank = json.loads(path.read_text(encoding="utf-8"))
    if bank.get("manifest_sha256") != document_digest(bank):
        raise ValueError("RC1 source manifest self digest mismatch")
    items = bank.get("items", [])
    if (bank.get("task_version") != SOURCE_VERSION or len(items) != 62
            or [item["id"] for item in items] != list(BANK_62)):
        raise ValueError("expected complete frozen RC1 source bank")
    for item in items:
        directory = root / "tasks" / item["id"]
        reject_links(directory)
        for path in directory.rglob("*"):
            if path.is_symlink() or (hasattr(path, "is_junction") and path.is_junction()):
                raise ValueError("source link/junction not allowed")
        if task_digest(directory) != item["task_sha256"]:
            raise ValueError("RC1 task drift: " + item["id"])
    return bank


def build_candidate(directory: Path = DEFAULT_CANDIDATE, *, root: Path = ROOT) -> dict:
    root = root.resolve()
    directory = directory.absolute()
    reject_links(directory)
    # The output must be one new child of this explicit bank namespace.
    namespace = root / "task-banks"
    if (namespace.is_symlink() or (hasattr(namespace, "is_junction") and namespace.is_junction())
            or directory.parent != namespace or directory.name != "rc2"
            or directory.exists() or directory.is_symlink()
            or directory.resolve().parent != namespace):
        raise ValueError("output must be a new task-banks/rc2 directory; no overwrite")
    bank = validate_source(root)
    before = protected_files(root)
    directory.parent.mkdir(exist_ok=True)
    directory.mkdir()
    source_hash = sha(root / "task-bank-v2.manifest.json")
    changed_files = []
    for task in BANK_62:
        source, target = root / "tasks" / task, directory / "tasks" / task
        shutil.copytree(source, target, ignore=shutil.ignore_patterns(*IGNORED, "*.pyc", "*.pyo"))
        config = target / "task.toml"
        text = replace_once(config.read_text(encoding="utf-8"),
                            f'version = "{SOURCE_VERSION}"', f'version = "{VERSION}"')
        text = replace_once(text, 'benchmark_revision = "workflow-2026-10-19"',
                            f'benchmark_revision = "{REVISION}"')
        write_text(config, text)
        grader_config = target / "tests/grader_config.json"
        data = json.loads(grader_config.read_text(encoding="utf-8"))
        if data["task_version"] != SOURCE_VERSION or data["grader_version"] != SOURCE_VERSION:
            raise ValueError("unexpected controller version")
        data.update(task_version=VERSION, grader_version=VERSION)
        write_text(grader_config, json.dumps(data, ensure_ascii=False, indent=2) + "\n")
        controller = target / "tests/verdict_v2.py"
        write_text(controller, replace_once(controller.read_text(encoding="utf-8"),
                                            f'VERSION = "{SOURCE_VERSION}"', f'VERSION = "{VERSION}"'))
        if task.startswith("review-"):
            path = target / "tests/test_state.py"
            write_text(path, patch_review_state(path.read_text(encoding="utf-8")))
        elif task.startswith(("testgen-", "repro-")):
            path = target / "tests/verifier.py"
            write_text(path, patch_replay_verifier(path.read_text(encoding="utf-8")))
            for relative in ("environment/repo/README.md", "tests/baseline/README.md"):
                path = target / relative
                write_text(path, clarify_submission_readme(path.read_text(encoding="utf-8")))
        for path in sorted(target.rglob("*")):
            if path.is_file():
                relative = path.relative_to(target)
                if path.read_bytes() != (source / relative).read_bytes():
                    changed_files.append({"task": task, "path": relative.as_posix(),
                                          "before_sha256": sha(source / relative), "after_sha256": sha(path)})
    if protected_files(root) != before:
        raise ValueError("protected RC1 source changed during candidate build")
    items = []
    for original in bank["items"]:
        task = original["id"]
        directory_task = directory / "tasks" / task
        config = tomllib.loads((directory_task / "task.toml").read_text(encoding="utf-8"))
        if config["task"]["version"] != VERSION:
            raise ValueError("candidate version mismatch")
        items.append({**original, "task_version": VERSION, "revision": REVISION,
                      "task_sha256": task_digest(directory_task)})
    result = {
        "schema_version": 1, "kind": "smallowbench_candidate_bank",
        "benchmark_name": "SmallOWBench", "benchmark_version": VERSION,
        "task_version": VERSION, "grader_version": VERSION,
        "harness_version": SOURCE_VERSION, "harness_changed": False,
        "revision": REVISION, "release_status": "candidate; not activated",
        "active_pipeline_compatible": False,
        "activation_requires": ["explicit task-root/component-version pipeline support", "new version-bound Linux container evidence", "separate run design and budget authorization"],
        "model_runs_authorized": False, "container_validated": False,
        "validation_status": "not_validated_current_contents",
        "scores_comparable_to_rc1": False,
        "source_rc1_manifest": {"path": "task-bank-v2.manifest.json", "sha256": source_hash},
        "task_count": 62, "skill_counts": dict(Counter(item["skill"] for item in items)),
        "items": items,
        "changes": changed_files,
        "protected_source_hashes": before,
        "builder_sources": {name: sha(root / name) for name in
                            ("scripts/prepare_rc2_candidate.py", "scripts/rc2_task_patches.py")},
    }
    result["manifest_sha256"] = document_digest(result)
    write_text(directory / "task-bank-v2.manifest.json", json.dumps(result, ensure_ascii=False, indent=2) + "\n")
    write_text(directory / "VERSION", VERSION + "\n")
    return result


def validate_candidate(directory: Path = DEFAULT_CANDIDATE, *, root: Path = ROOT) -> dict:
    root = root.resolve()
    if directory.absolute() != root / "task-banks" / "rc2":
        raise ValueError("only the explicit additive RC2 candidate may be validated")
    reject_links(directory)
    directory = directory.resolve()
    if directory != root / "task-banks" / "rc2":
        raise ValueError("candidate namespace resolves outside its explicit location")
    manifest_path = directory / "task-bank-v2.manifest.json"
    reject_links(manifest_path)
    reject_links(directory / "VERSION")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if (manifest.get("manifest_sha256") != document_digest(manifest)
            or manifest.get("kind") != "smallowbench_candidate_bank"
            or manifest.get("task_version") != VERSION
            or manifest.get("model_runs_authorized") is not False
            or manifest.get("container_validated") is not False):
        raise ValueError("candidate manifest is malformed or claims unauthorized activation")
    expected_metadata = {
        "benchmark_version": VERSION, "grader_version": VERSION,
        "harness_version": SOURCE_VERSION, "harness_changed": False,
        "active_pipeline_compatible": False, "release_status": "candidate; not activated",
        "revision": REVISION, "validation_status": "not_validated_current_contents",
        "scores_comparable_to_rc1": False,
    }
    if (any(type(manifest.get(key)) is not type(value) or manifest.get(key) != value
            for key, value in expected_metadata.items())
            or (directory / "VERSION").read_text(encoding="utf-8").strip() != VERSION):
        raise ValueError("candidate component versions or activation metadata mismatch")
    items = manifest.get("items", [])
    if (manifest.get("task_count") != 62 or len(items) != 62
            or [item["id"] for item in items] != list(BANK_62)
            or manifest.get("skill_counts") != dict(Counter(item["skill"] for item in items))):
        raise ValueError("candidate must contain exactly 62 declared tasks")
    for name, expected in manifest.get("builder_sources", {}).items():
        if name not in {"scripts/prepare_rc2_candidate.py", "scripts/rc2_task_patches.py"} or sha(root / name) != expected:
            raise ValueError("candidate builder source changed")
    if set(manifest.get("builder_sources", {})) != {"scripts/prepare_rc2_candidate.py", "scripts/rc2_task_patches.py"}:
        raise ValueError("candidate builder provenance is missing")
    if protected_files(root) != manifest.get("protected_source_hashes"):
        raise ValueError("protected RC1 source no longer matches candidate provenance")
    if manifest.get("source_rc1_manifest") != {"path": "task-bank-v2.manifest.json", "sha256": sha(root / "task-bank-v2.manifest.json")}:
        raise ValueError("candidate source manifest binding mismatch")
    for item in items:
        task = directory / "tasks" / item["id"]
        reject_links(task)
        for path in task.rglob("*"):
            if path.is_symlink() or (hasattr(path, "is_junction") and path.is_junction()):
                raise ValueError("candidate link/junction not allowed")
        if item["task_version"] != VERSION or item["task_sha256"] != task_digest(task):
            raise ValueError("candidate task fingerprint mismatch: " + item["id"])
        config = tomllib.loads((task / "task.toml").read_text(encoding="utf-8"))
        grader = json.loads((task / "tests/grader_config.json").read_text(encoding="utf-8"))
        if (config["task"]["version"] != VERSION
                or config["metadata"]["benchmark_revision"] != REVISION
                or grader.get("task_id") != item["id"]
                or grader.get("task_version") != VERSION or grader.get("grader_version") != VERSION
                or grader.get("skill") != item["skill"]
                or f'VERSION = "{VERSION}"' not in (task / "tests/verdict_v2.py").read_text(encoding="utf-8")):
            raise ValueError("candidate actual task/controller version mismatch: " + item["id"])
    return manifest


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=DEFAULT_CANDIDATE)
    parser.add_argument("--check", action="store_true", help="only verify an existing candidate")
    args = parser.parse_args()
    result = validate_candidate(args.output) if args.check else build_candidate(args.output)
    print(json.dumps({key: result[key] for key in ("task_version", "harness_version", "task_count", "release_status", "model_runs_authorized", "container_validated", "manifest_sha256")}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
