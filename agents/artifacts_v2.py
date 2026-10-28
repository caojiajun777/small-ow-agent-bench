"""Data-only, bounded final artifacts. No task imports, secrets or symlink traversal.

Complete means the allowed files were copied without a detected omission. It is
not an atomic filesystem/process checkpoint or an attestation of a hostile OS.
"""
from __future__ import annotations

import base64
import hashlib
import json
import os
import re
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path, PurePosixPath

from agents.protocol_v2 import HARNESS_VERSION
from scripts.task_sets import HARD_RELEASE_15, MAIN_47

OFFICIAL_TASKS = frozenset(MAIN_47 + HARD_RELEASE_15)
CACHES = frozenset({"__pycache__", ".pytest_cache", ".git", ".mypy_cache", ".ruff_cache"})
SENSITIVE = frozenset({"credentials", "credentials.json", "id_rsa", "id_ed25519", ".netrc", ".npmrc", ".pypirc", ".aws", ".ssh"})


@dataclass(frozen=True)
class CaptureLimits:
    max_files: int = 256
    max_file_bytes: int = 1_048_576
    max_total_bytes: int = 8_388_608

    def __post_init__(self):
        if any(type(value) is not int or value < 1 for value in self.__dict__.values()):
            raise ValueError("capture limits must be positive integers")


def artifact_policy(task_id: str) -> dict:
    if not isinstance(task_id, str) or task_id not in OFFICIAL_TASKS:
        raise ValueError("task_id must identify one of the official 62 tasks")
    skill = task_id.split("-", 1)[0]
    root_file = {"loc": "answer.txt", "repro": "repro.py", "review": "review.json"}.get(skill)
    return {"task_id": task_id, "skill": skill, "required": ["repo"] + ([root_file] if root_file else []),
            "root_file": root_file, "test_submission": skill == "testgen"}


def _safe_path(name: str, policy: dict) -> bool:
    if not isinstance(name, str):
        return False
    path = PurePosixPath(name)
    if not name or path.is_absolute() or ".." in path.parts or str(path) != name or "\\" in name or ":" in name:
        return False
    if any(part.lower().startswith(".env") or part.lower() in SENSITIVE or part in CACHES for part in path.parts):
        return False
    return (len(path.parts) > 1 and path.parts[0] == "repo") or name == policy["root_file"]


def artifact_role(name: str, policy: dict) -> str:
    if name == policy["root_file"] or policy["skill"] == "edit" or (policy["test_submission"] and name.startswith("repo/tests/")):
        return "submission"
    return "context"


def capture_script(task_id: str, limits: CaptureLimits | None = None) -> str:
    policy = artifact_policy(task_id)
    limits = limits or CaptureLimits()
    config = {"policy": policy, "limits": limits.__dict__, "caches": sorted(CACHES), "sensitive": sorted(SENSITIVE), "harness_version": HARNESS_VERSION}
    # Fixed /app scope in the sandbox. The host never executes captured task code.
    return "CONFIG = " + repr(config) + "\n" + r'''
import base64, hashlib, json, os, stat
from pathlib import Path
root = Path('/app'); policy = CONFIG['policy']; limits = CONFIG['limits']
files = []; missing = []; issues = []; total = 0
def issue(path, reason):
    issues.append({'path': path, 'reason': reason})
def sensitive(name):
    return name.lower().startswith('.env') or name.lower() in CONFIG['sensitive']
def collect(path, name):
    global total
    try:
        info = path.lstat()
        if not stat.S_ISREG(info.st_mode):
            issue(name, 'not_regular_or_symlink'); return
        if sensitive(path.name):
            issue(name, 'sensitive_filename_excluded'); return
        if len(files) >= limits['max_files'] or info.st_size > limits['max_file_bytes'] or total + info.st_size > limits['max_total_bytes']:
            issue(name, 'size_limit'); return
        descriptor = os.open(path, os.O_RDONLY | getattr(os, 'O_NOFOLLOW', 0))
        with os.fdopen(descriptor, 'rb') as stream:
            opened = os.fstat(stream.fileno())
            if not stat.S_ISREG(opened.st_mode) or (opened.st_ino, opened.st_dev) != (info.st_ino, info.st_dev):
                issue(name, 'changed_during_capture'); return
            data = stream.read(limits['max_file_bytes'] + 1)
            final = os.fstat(stream.fileno())
        if len(data) > limits['max_file_bytes'] or total + len(data) > limits['max_total_bytes']:
            issue(name, 'size_limit'); return
        if (opened.st_size, opened.st_mtime_ns) != (final.st_size, final.st_mtime_ns) or len(data) != final.st_size:
            issue(name, 'changed_during_capture'); return
        mode = stat.S_IMODE(info.st_mode)
        if mode > 0o777:
            issue(name, 'unsupported_mode'); return
        role = 'submission' if name == policy['root_file'] or policy['skill'] == 'edit' or (policy['test_submission'] and name.startswith('repo/tests/')) else 'context'
        files.append({'path': name, 'sha256': hashlib.sha256(data).hexdigest(), 'size': len(data), 'mode': mode,
                      'role': role, 'data_b64': base64.b64encode(data).decode('ascii')})
        total += len(data)
    except OSError:
        issue(name, 'read_error')
root_safe = root.is_dir() and not root.is_symlink()
repo = root / 'repo'
if not root_safe or not repo.is_dir() or repo.is_symlink():
    missing.append('repo'); issue('repo', 'missing_or_symlink_directory')
else:
    def walk_error(error):
        issue('repo', 'walk_error')
    for directory, dirs, names in os.walk(repo, followlinks=False, onerror=walk_error):
        for name in list(dirs):
            path = Path(directory) / name
            relative = path.relative_to(root).as_posix()
            if name in CONFIG['caches']:
                dirs.remove(name)
            elif sensitive(name):
                dirs.remove(name); issue(relative, 'sensitive_filename_excluded')
            elif path.is_symlink():
                dirs.remove(name); issue(relative, 'symlink_directory')
        dirs.sort()
        for name in sorted(names):
            if name.endswith(('.pyc', '.pyo')):
                continue
            path = Path(directory) / name
            collect(path, path.relative_to(root).as_posix())
    if not any(row['path'].startswith('repo/') for row in files):
        missing.append('repo/*')
if policy['root_file']:
    path = root / policy['root_file']
    if not root_safe or (not path.exists() and not path.is_symlink()):
        missing.append(policy['root_file'])
    else:
        collect(path, policy['root_file'])
if policy['test_submission'] and not any(row['path'].startswith('repo/tests/') and row['path'].endswith('.py') for row in files):
    missing.append('repo/tests/*.py')
print(json.dumps({'schema_version': 2, 'harness_version': CONFIG['harness_version'], 'task_id': policy['task_id'],
                  'status': 'incomplete' if missing or issues else 'complete', 'files': sorted(files, key=lambda row: row['path']),
                  'missing': sorted(set(missing)), 'issues': issues, 'atomic': False, 'final_state_verified': False,
                  'limits': limits, 'total_bytes': total}, sort_keys=True))
'''


def validate_capture(value: dict, task_id: str, limits: CaptureLimits | None = None) -> tuple[dict, dict[str, bytes]]:
    policy = artifact_policy(task_id)
    limits = limits or CaptureLimits()
    if not isinstance(value, dict) or value.get("schema_version") != 2 or value.get("harness_version") != HARNESS_VERSION or value.get("task_id") != task_id:
        raise ValueError("capture identity mismatch")
    if value.get("atomic") is not False or value.get("final_state_verified") is not False or value.get("limits") != limits.__dict__:
        raise ValueError("unsupported capture assurances or limits")
    if value.get("status") not in {"complete", "incomplete"}:
        raise ValueError("invalid capture status")
    rows = value.get("files")
    if not isinstance(rows, list) or len(rows) > limits.max_files:
        raise ValueError("invalid capture file count")
    missing, issues = value.get("missing"), value.get("issues")
    if not isinstance(missing, list) or not all(isinstance(item, str) for item in missing) or not isinstance(issues, list):
        raise ValueError("invalid capture omissions")
    allowed_missing = {"repo", "repo/*", "repo/tests/*.py", policy["root_file"]}
    if any(item not in allowed_missing for item in missing):
        raise ValueError("unexpected missing artifact name")
    reasons = {"not_regular_or_symlink", "sensitive_filename_excluded", "size_limit", "changed_during_capture",
               "unsupported_mode", "read_error", "missing_or_symlink_directory", "walk_error", "symlink_directory"}
    for issue in issues:
        if not isinstance(issue, dict) or set(issue) != {"path", "reason"} or issue["reason"] not in reasons:
            raise ValueError("invalid capture issue")
        name = issue["path"]
        if not isinstance(name, str) or not (name == "repo" or name.startswith("repo/") or name == policy["root_file"]):
            raise ValueError("unsafe capture issue path")
        path = PurePosixPath(name)
        if path.is_absolute() or ".." in path.parts or "\\" in name or ":" in name or str(path) != name:
            raise ValueError("unsafe capture issue path")
    decoded, metadata, total = {}, [], 0
    for row in rows:
        if not isinstance(row, dict):
            raise ValueError("invalid artifact row")
        name = row.get("path")
        if not _safe_path(name, policy) or name in decoded:
            raise ValueError("unsafe or duplicate artifact path")
        encoded = row.get("data_b64")
        if not isinstance(encoded, str) or len(encoded) > 4 * ((limits.max_file_bytes + 2) // 3):
            raise ValueError("encoded artifact exceeds limit")
        data = base64.b64decode(encoded, validate=True)
        total += len(data)
        if type(row.get("size")) is not int or row["size"] != len(data) or len(data) > limits.max_file_bytes or total > limits.max_total_bytes:
            raise ValueError("artifact size mismatch or limit")
        if not isinstance(row.get("sha256"), str) or not re.fullmatch(r"[0-9a-f]{64}", row["sha256"]) or hashlib.sha256(data).hexdigest() != row["sha256"]:
            raise ValueError("artifact hash mismatch")
        if type(row.get("mode")) is not int or not 0 <= row["mode"] <= 0o777 or row.get("role") != artifact_role(name, policy):
            raise ValueError("invalid artifact mode or role")
        decoded[name] = data
        metadata.append({key: row[key] for key in ("path", "sha256", "size", "mode", "role")})
    if type(value.get("total_bytes")) is not int or value["total_bytes"] != total:
        raise ValueError("artifact total mismatch")
    if not any(name.startswith("repo/") for name in decoded):
        missing = [*missing, "repo/*"]
    if policy["root_file"] and policy["root_file"] not in decoded:
        missing = [*missing, policy["root_file"]]
    if policy["test_submission"] and not any(name.startswith("repo/tests/") and name.endswith(".py") for name in decoded):
        missing = [*missing, "repo/tests/*.py"]
    missing = sorted(set(missing))
    status = "incomplete" if missing or issues else "complete"
    if value["status"] != status:
        raise ValueError("capture completeness claim contradicts its evidence")
    return {"schema_version": 2, "harness_version": HARNESS_VERSION, "task_id": task_id, "status": status,
            "files": sorted(metadata, key=lambda row: row["path"]), "missing": missing, "issues": issues,
            "atomic": False, "final_state_verified": False, "limits": limits.__dict__, "total_bytes": total}, decoded


def write_atomic(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary = tempfile.mkstemp(prefix="." + path.name + "-", suffix=".tmp", dir=path.parent)
    try:
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        # Windows readers/AV may briefly open the destination without delete
        # sharing. Keep ownership and the same complete temp file throughout
        # bounded retries; do not fall back to truncating the destination.
        deadline = time.monotonic() + 5.0
        while True:
            try:
                os.replace(temporary, path)
                break
            except PermissionError as exc:
                if os.name != "nt" or getattr(exc, "winerror", None) not in {5, 32, 33}:
                    raise
                if time.monotonic() >= deadline:
                    raise
                time.sleep(0.025)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def write_json_atomic(path: Path, value: dict) -> str:
    data = (json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2, allow_nan=False) + "\n").encode("utf-8")
    write_atomic(path, data)
    return hashlib.sha256(data).hexdigest()


def save_capture(directory: Path, manifest: dict, decoded: dict[str, bytes]) -> str:
    directory.mkdir(parents=True, exist_ok=True)
    root = directory.resolve()
    for row in manifest["files"]:
        name = row["path"]
        destination = directory.joinpath(*PurePosixPath(name).parts)
        if not destination.resolve().is_relative_to(root):
            raise ValueError("artifact destination escapes archive")
        write_atomic(destination, decoded[name])
        destination.chmod(row["mode"])
    return write_json_atomic(directory / "manifest.json", manifest)
