"""Offline host-path admission checks for the current single-step v2 layout.

The guard covers predictable Harbor evidence, staged task files and existing
repository artifacts. It does not promise that arbitrary future model-created
filenames fit: the returned artifact-relative budget makes that boundary
explicit. No Docker probe, directory creation or model call is performed.
"""

from __future__ import annotations

import ntpath
import os
from pathlib import Path, PureWindowsPath
import re


ROOT = Path(__file__).resolve().parents[1]
# MAX_PATH includes the terminating NUL. Do not assume all Docker/CLI tools
# honor either the registry long-path switch or an extended-length prefix.
WINDOWS_PATH_LIMIT = 259
WINDOWS_COMPONENT_LIMIT = 255
ATOMIC_TEMP_OVERHEAD = 14  # .{filename}-{8 random chars}.tmp
MODEL_JOB_NAME = "visit-" + "0" * 32  # ClaimStore's UUID-hex job identity.
_COMPONENT = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.-]*\Z")
_IGNORED = {"__pycache__", ".pytest_cache", ".git"}


class PathPreflightError(ValueError):
    """A predictable host output cannot fit the supported Windows path budget."""


def _units(value: str) -> int:
    """Windows limits count UTF-16 code units, not Python Unicode scalars."""
    return len(value.encode("utf-16-le")) // 2


def _root_path(directory, windows: bool):
    raw = str(directory)
    if windows and os.name != "nt" and PureWindowsPath(raw).is_absolute():
        # Portable offline tests may describe a Windows host from POSIX. Actual
        # native runs take Path.resolve(), including existing junctions.
        return PureWindowsPath(ntpath.normpath(raw))
    resolved = Path(directory).resolve()
    return PureWindowsPath(str(resolved)) if windows else resolved


def prospective_paths(directory, tasks, *, mode="model", task_root=None, platform=None):
    """Return deterministic prospective paths; random suffix lengths are exact.

    Only the current one-trial-per-job, single-step pipeline is supported.
    ``mode='oracle_nop'`` expands both model-free jobs for each selected task.
    """
    if mode not in {"model", "oracle_nop"}:
        raise ValueError("path preflight mode must be model or oracle_nop")
    selected = list(dict.fromkeys(tasks))
    if not selected or any(
        not isinstance(task, str)
        or not _COMPONENT.fullmatch(task)
        or task.endswith((".", " "))
        for task in selected
    ):
        raise ValueError("path preflight needs nonempty safe task identities")
    windows = (os.name if platform is None else platform) == "nt"
    directory = _root_path(directory, windows)
    source = Path(task_root) if task_root is not None else ROOT / "tasks"
    rows = []
    artifact_roots = []

    def add(path, kind, task, overhead=0):
        rows.append(
            {
                "path": str(path),
                "kind": kind,
                "task": task,
                "utf16_units": _units(str(path)) + overhead,
                "temporary_suffix_reserve": overhead,
            }
        )

    for task in selected:
        existing = []
        if (source / task).is_dir():
            existing = [
                path.relative_to(source / task)
                for path in sorted((source / task).rglob("*"))
                if path.is_file()
                and not path.is_symlink()
                and not _IGNORED.intersection(path.relative_to(source / task).parts)
                and path.suffix != ".pyc"
            ]
        for relative in existing:
            add(
                directory / "staged-tasks" / task / relative.as_posix(),
                "staged-task",
                task,
            )
        add(directory / "images" / task / "grader-runtime.json", "image-log", task)
        jobs = (
            [MODEL_JOB_NAME]
            if mode == "model"
            else [f"v2-{agent}-{task}" for agent in ("oracle", "nop")]
        )
        # Harbor TrialConfig.generate_trial_name: basename[:32], trim, __, 7.
        trial_name = task[:32].rstrip("_-") + "__" + "X" * 7
        for job_name in jobs:
            job = directory / "jobs" / job_name
            trial = job / trial_name
            add(directory / "configs" / (job_name + ".json"), "job-config", task)
            add(directory / "runner-logs" / (job_name + ".log"), "runner-log", task)
            add(
                directory / "visits" / (job_name + ".json"),
                "visit-ledger",
                task,
                ATOMIC_TEMP_OVERHEAD,
            )
            add(job / "config.json", "resolved-job", task)
            for name in ("config.json", "lock.json", "result.json", "exception.txt"):
                add(trial / name, "trial-evidence", task)
            for session in (trial_name + "__env", trial_name + "__verifier__trial"):
                # The published bank has one verifier, whose session stays below
                # Harbor's 63-character shortening threshold.
                safe = re.sub(r"[^a-z0-9_-]", "-", session.lower())
                if not re.match(r"^[a-z0-9]", safe):
                    safe = "0" + safe
                add(
                    trial / "environment" / ("static-network-" + safe + ".json"),
                    "static-network-evidence",
                    task,
                )
            for name in (
                "verdict.json",
                "worker-result.json",
                "worker.stdout.txt",
                "worker.stderr.txt",
                "test-stdout.txt",
                "test-stderr.txt",
            ):
                add(trial / "verifier" / name, "verifier-evidence", task)
            add(
                trial / "agent" / "compact-shell-v2.json",
                "agent-trace",
                task,
                ATOMIC_TEMP_OVERHEAD,
            )
            capture = trial / "agent" / "artifacts"
            artifact_roots.append(capture)
            add(
                capture / "manifest.json",
                "artifact-manifest",
                task,
                ATOMIC_TEMP_OVERHEAD,
            )
            for name in ("answer.txt", "repro.py", "review.json"):
                add(capture / name, "root-submission", task, ATOMIC_TEMP_OVERHEAD)
                add(
                    trial / "artifacts" / "submission" / name,
                    "collected-root-submission",
                    task,
                )
            for relative in existing:
                if relative.parts[:2] != ("environment", "repo"):
                    continue
                tail = relative.parts[2:]
                add(
                    capture.joinpath("repo", *tail),
                    "captured-existing-file",
                    task,
                    ATOMIC_TEMP_OVERHEAD,
                )
                add(
                    trial.joinpath("artifacts", "submission", "repo", *tail),
                    "collected-existing-file",
                    task,
                )
    return directory, windows, rows, artifact_roots


def validate_run_paths(
    directory, tasks, *, mode="model", task_root=None, platform=None
):
    """Reject unsafe prospective Windows paths before runtime admission.

    Return the longest predicted path and the worst-case relative filename
    budget below agent/artifacts (including atomic temporary-file overhead).
    This is a fixed-layout preflight, not validation of not-yet-created model
    output paths, host TEMP configuration, or future multi-step Harbor layouts.
    """
    directory, windows, rows, artifact_roots = prospective_paths(
        directory, tasks, mode=mode, task_root=task_root, platform=platform
    )
    longest = max(rows, key=lambda row: row["utf16_units"])
    bad_components = (
        [
            row
            for row in rows
            if any(
                _units(part) > WINDOWS_COMPONENT_LIMIT
                for part in PureWindowsPath(row["path"]).parts
            )
        ]
        if windows
        else []
    )
    if windows and (longest["utf16_units"] > WINDOWS_PATH_LIMIT or bad_components):
        excess = max(0, longest["utf16_units"] - WINDOWS_PATH_LIMIT)
        suffix = (
            f"shorten the resolved run-directory path by at least {excess} "
            "UTF-16 characters"
            if excess
            else "shorten the overlong path component (maximum 255 UTF-16 characters)"
        )
        raise PathPreflightError(
            "Windows path preflight rejected this run before any container/model launch: "
            f"{longest['utf16_units']} > {WINDOWS_PATH_LIMIT} supported path units; "
            f"{longest['kind']} for {longest['task']}: {longest['path']}. "
            f"Use a shorter new run directory or a supported shorter checkout; {suffix}. "
            "A short directory name alone is not sufficient. Existing evidence is unchanged."
        )
    return {
        "checked": True,
        "windows_limit_enforced": windows,
        "directory": str(directory),
        "predicted_paths": len(rows),
        "longest_path": longest,
        "windows_path_limit": WINDOWS_PATH_LIMIT,
        "artifact_relative_path_budget": min(
            WINDOWS_PATH_LIMIT - _units(str(path)) - 1 - ATOMIC_TEMP_OVERHEAD
            for path in artifact_roots
        )
        if windows
        else None,
        "scope": "fixed single-step evidence and existing task/artifact paths; "
        "future model-created paths and host TEMP are not guaranteed",
    }
