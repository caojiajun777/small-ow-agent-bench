"""Additive RC2 component profiles and model-free container evidence.

This module does not activate the candidate or launch containers, shells, models,
or API requests. RC1 modules and their historical evidence remain unchanged.
Only oracle/nop job configurations are supported; paid execution is disabled.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import importlib.metadata
import json
import math
from pathlib import Path
import shutil
import tomllib

from prepare_rc2_candidate import BANK_62, reject_links, validate_candidate
from validate_upgraded_tasks import task_digest
from v2_pipeline import (
    HARNESS_SOURCES, PIPELINE_SOURCES, EXECUTION_SOURCES,
    V2Error, bound_file, digest, file_hash, harbor_task_checksum,
    legacy_tree_digest, normalized_job_config, read_json, staged_task_text,
    staged_tree_digest, IMAGE_RE, DIGEST_RE,
)
from validate_v2_containers import static_network_evidence

ROOT = Path(__file__).resolve().parents[1]
COMPONENT_VERSIONS = {
    "benchmark": "2.0.0-rc.2", "task": "2.0.0-rc.2",
    "grader": "2.0.0-rc.2", "harness": "2.0.0-rc.1",
}
SMOKE_TASKS = (
    "loc-bind-host", "edit-clip", "testgen-timeout-zero",
    "repro-keep-zero", "review-clip-incomplete",
)
NEW_SOURCES = (
    "scripts/rc2_pipeline.py", "scripts/validate_rc2_containers.py",
    "scripts/prepare_rc2_candidate.py", "scripts/rc2_task_patches.py",
)
REPORT_KIND = "smallowbench_rc2_container_evidence"
PROBE_LABEL_KEY = "smallowbench.rc2.smoke"
VERSION_PROBE_CODE = "import json,sys,pytest;print(json.dumps({'python':sys.version,'pytest':pytest.__version__}))"
_IGNORED = {"__pycache__", ".pytest_cache", ".git", ".ruff_cache"}


def _within(path, root, *, file=False):
    path, root = Path(path).absolute(), Path(root).resolve()
    reject_links(path)
    resolved = path.resolve()
    if not resolved.is_relative_to(root) or file and not resolved.is_file():
        raise V2Error("evidence path is outside its explicit root or not a regular file")
    return resolved


def _relative(path, root):
    return _within(path, root).relative_to(Path(root).resolve()).as_posix()


def runtime_evidence(root=ROOT):
    """Read-only Harbor source and dependency identity for this repository."""
    source = Path(root).resolve().parent / "harbor"
    code = source / "src" / "harbor"
    if not code.is_dir():
        raise V2Error("configured adjacent Harbor source tree is unavailable")
    rows = []
    for path in sorted(code.rglob("*")):
        if not path.is_file() or _IGNORED.intersection(path.parts) or path.suffix in {".pyc", ".pyo"}:
            continue
        _within(path, source, file=True)
        if path.name.startswith(".env"):
            raise V2Error("credential-like runtime source entry")
        rows.append([path.relative_to(source).as_posix(), file_hash(path)])
    return {
        "package_version": importlib.metadata.version("harbor"),
        "source_tree_sha256": digest(rows),
        "source_files": len(rows),
        "dependency_versions": sorted(
            [distribution.metadata["Name"], distribution.version]
            for distribution in importlib.metadata.distributions()
            if distribution.metadata["Name"]
        ),
        "dependency_spec_sha256": {
            name: file_hash(_within(source / name, source, file=True))
            for name in ("pyproject.toml", "uv.lock")
        },
    }


def load_profile(root=ROOT):
    root = Path(root).resolve()
    candidate = root / "task-banks" / "rc2"
    bank = validate_candidate(candidate, root=root)
    manifest_path = candidate / "task-bank-v2.manifest.json"
    if read_json(manifest_path) != bank:
        raise V2Error("candidate changed during profile loading")
    task_root = _within(candidate / "tasks", root)
    names = set(HARNESS_SOURCES + PIPELINE_SOURCES + EXECUTION_SOURCES + NEW_SOURCES)
    source_hashes = {
        name: file_hash(_within(root / name, root, file=True)) for name in sorted(names)
    }
    specs = {}
    for item in bank["items"]:
        task = item["id"]
        source = _within(task_root / task, task_root)
        config = tomllib.loads((source / "task.toml").read_text(encoding="utf-8"))
        if (config["task"]["version"] != COMPONENT_VERSIONS["task"]
                or task_digest(source) != item["task_sha256"]):
            raise V2Error("candidate task identity changed: " + task)
        specs[task] = {
            "skill": item["skill"], "task_version": COMPONENT_VERSIONS["task"],
            "normalized_sha256": item["task_sha256"],
            "legacy_tree_sha256": legacy_tree_digest(source),
        }
    if set(specs) != set(BANK_62):
        raise V2Error("RC2 profile requires the explicit complete 62-task candidate")
    profile = {
        "schema_version": 1, "kind": "smallowbench_rc2_model_free_profile",
        "repository_root": str(root), "task_root": str(task_root),
        "bank_manifest": {**bound_file(manifest_path), "document_digest": bank["manifest_sha256"]},
        "component_versions": dict(COMPONENT_VERSIONS), "task_specs": specs,
        "source_hashes": source_hashes, "harbor_runtime": runtime_evidence(root),
        "agent_import_path": "agents.compact_shell_v2:CompactShellV2Agent",
        "supported_agents": ["oracle", "nop"], "model_execution_enabled": False,
        "candidate_activated": False,
    }
    profile["profile_sha256"] = digest(profile)
    return profile


def validate_profile(profile):
    if (not isinstance(profile, dict)
            or profile.get("profile_sha256") != digest({k: v for k, v in profile.items() if k != "profile_sha256"})):
        raise V2Error("RC2 profile digest mismatch")
    if profile != load_profile(Path(profile["repository_root"])):
        raise V2Error("RC2 component profile, candidate, source, or runtime drifted")
    return profile


def _task_source(profile, task):
    if task not in profile["task_specs"]:
        raise V2Error("unplanned RC2 task")
    source = _within(Path(profile["task_root"]) / task, profile["task_root"])
    if task_digest(source) != profile["task_specs"][task]["normalized_sha256"]:
        raise V2Error("RC2 task source drifted")
    return source


def _run_directory(profile, directory):
    root = Path(profile["repository_root"])
    directory = _within(directory, root / "experiments" / "smallowbench-v2")
    if directory.parent != root / "experiments" / "smallowbench-v2":
        raise V2Error("RC2 run must be a direct new experiment child")
    return directory


def stage_task(profile, task, directory, agent_image, grader_image):
    validate_profile(profile)
    directory = _run_directory(profile, directory)
    source = _task_source(profile, task)
    text = staged_task_text(source / "task.toml", agent_image, grader_image)
    target = _within(directory / "staged-tasks" / task, directory)
    if target.exists():
        raise V2Error("never overwrite or reuse a staged RC2 task")
    shutil.copytree(source, target, ignore=shutil.ignore_patterns(*_IGNORED, "*.pyc", "*.pyo"))
    (target / "task.toml").write_text(text, encoding="utf-8", newline="\n")
    from harbor.models.task.config import TaskConfig

    TaskConfig.model_validate_toml(text)
    if legacy_tree_digest(target) != staged_tree_digest(source, text):
        raise V2Error("staged RC2 bytes differ from the explicit candidate source")
    return target


def make_config(profile, task, mode, staged, directory):
    if mode not in {"oracle", "nop"}:
        raise V2Error("RC2 model execution is disabled; only oracle/nop are allowed")
    _task_source(profile, task)
    directory = _run_directory(profile, directory)
    expected = directory / "staged-tasks" / task
    if Path(staged).resolve() != expected:
        raise V2Error("config must use this experiment's explicit staged RC2 task")
    config = {
        "job_name": f"v2-{mode}-{task}", "jobs_dir": str(directory / "jobs"),
        "n_attempts": 1, "n_concurrent_trials": 1, "timeout_multiplier": 1.0,
        "quiet": True, "retry": {"max_retries": 0},
        "environment": {"type": "docker", "force_build": False, "delete": False},
        "agents": [{"name": mode}], "tasks": [{"path": str(expected)}],
    }
    from harbor.models.job.config import JobConfig

    JobConfig.model_validate(config)
    return config


def validate_verdict(profile, verdict, task):
    """Check RC2 task/grader identity without rewriting RC1 or input evidence."""
    versions = profile["component_versions"]
    if (not isinstance(verdict, dict) or verdict.get("schema_version") != 2
            or verdict.get("task_id") != task
            or verdict.get("task_version") != versions["task"]
            or verdict.get("grader_version") != versions["grader"]):
        raise V2Error("RC2 verdict identity/component version mismatch")
    status, correct = verdict.get("status"), verdict.get("artifact_correct")
    if status not in {"pass", "fail", "error"} or (
        status == "error" and correct is not None
        or status != "error" and (type(correct) is not int or correct != int(status == "pass"))
    ):
        raise V2Error("RC2 verdict status/reward mismatch")
    rows = verdict.get("submission_manifest")
    if not isinstance(rows, list):
        raise V2Error("missing RC2 submission manifest")
    paths = []
    for row in rows:
        if not isinstance(row, dict) or set(row) != {"path", "role", "size_bytes", "sha256"}:
            raise V2Error("malformed RC2 submission manifest row")
        name = row["path"]
        if (not isinstance(name, str) or not name or Path(name).is_absolute()
                or "\\" in name or ":" in name or ".." in name.split("/")
                or row["role"] not in {"submission", "observation"}
                or type(row["size_bytes"]) is not int or row["size_bytes"] < 0
                or not isinstance(row["sha256"], str) or not DIGEST_RE.fullmatch(row["sha256"])):
            raise V2Error("unsafe RC2 submission manifest row")
        paths.append(name)
    if paths != sorted(set(paths)) or verdict.get("submission_digest") != digest(rows):
        raise V2Error("RC2 submission digest/path mismatch")
    if status == "pass":
        submitted = {row["path"] for row in rows if row["role"] == "submission"}
        skill = profile["task_specs"][task]["skill"]
        primary = {"loc": "answer.txt", "review": "review.json", "repro": "repro.py"}.get(skill)
        if (not submitted or primary and primary not in submitted
                or skill == "edit" and not any(name.startswith("repo/") for name in submitted)
                or skill == "testgen" and not any(name.startswith("repo/tests/")
                    and Path(name).name.startswith("test_") and name.endswith(".py") for name in submitted)):
            raise V2Error("RC2 passing verdict lacks its required submission")
    elapsed = verdict.get("elapsed_sec")
    if (isinstance(elapsed, bool) or not isinstance(elapsed, (int, float))
            or not math.isfinite(elapsed) or elapsed < 0
            or not isinstance(verdict.get("checks"), dict)
            or not isinstance(verdict.get("evidence"), (list, dict))
            or "failure_category" not in verdict):
        raise V2Error("RC2 verdict lacks valid structured diagnostics")
    return verdict


def inspect_trial(profile, task, mode, directory, agent_image, grader_image, session_state=None):
    """Recompute one model-free observation from original raw files, not booleans."""
    validate_profile(profile)
    directory = _run_directory(profile, directory)
    root = Path(profile["repository_root"])
    source = _task_source(profile, task)
    staged = directory / "staged-tasks" / task
    expected = make_config(profile, task, mode, staged, directory)
    generated_path = _within(directory / "configs" / (expected["job_name"] + ".json"), directory, file=True)
    job = _within(directory / "jobs" / expected["job_name"], directory)
    resolved_path = _within(job / "config.json", directory, file=True)
    if (read_json(generated_path) != expected
            or normalized_job_config(read_json(resolved_path)) != normalized_job_config(expected)):
        raise V2Error("executed RC2 job configuration differs from model-free plan")
    results = sorted(job.glob("*/result.json"))
    if len(results) != 1:
        raise V2Error("RC2 model-free job must have exactly one raw Harbor trial")
    result_path = _within(results[0], directory, file=True)
    trial, raw = result_path.parent, read_json(result_path)
    actual = raw.get("config", {})
    agent, environment = actual.get("agent", {}), actual.get("environment", {})
    expected_agent = normalized_job_config(expected)["agents"][0]
    normalized = normalized_job_config(expected)
    if (raw.get("task_name", "").rsplit("/", 1)[-1] != task
            or raw.get("trial_name", trial.name) != trial.name
            or actual.get("trial_name") != trial.name
            or agent != expected_agent
            or environment != normalized["environment"]
            or actual.get("task") != normalized["tasks"][0]
            or actual.get("timeout_multiplier") != 1.0
            or actual.get("verifier") != normalized["verifier"]
            or actual.get("install_only") is not False
            or actual.get("source_trial") is not None
            or actual.get("trials_dir") != str(job)
            or any(actual.get(name) is not None for name in (
                "agent_timeout_multiplier", "verifier_timeout_multiplier", "agent_setup_timeout_multiplier",
                "environment_build_timeout_multiplier"))
            or actual.get("artifacts", []) or actual.get("extra_instruction_paths", [])
            or raw.get("verifier_environment_mode") != "separate"):
        raise V2Error("raw RC2 trial identity/protocol/environment mismatch")
    text = staged_task_text(source / "task.toml", agent_image, grader_image)
    config_hash = hashlib.sha256(text.encode("utf-8")).hexdigest()
    tree_hash = staged_tree_digest(source, text)
    if (file_hash(_within(staged / "task.toml", directory, file=True)) != config_hash
            or legacy_tree_digest(staged) != tree_hash
            or raw.get("task_checksum") != harbor_task_checksum(staged)):
        raise V2Error("raw RC2 trial did not execute the exact candidate/image-pinned staged task")
    proofs = static_network_evidence(trial, {
        trial.name + "__env": agent_image,
        trial.name + "__verifier__trial": grader_image,
    })
    if len(proofs) != 2:
        raise V2Error("RC2 smoke requires two original Docker network-none proofs")
    state = {} if session_state is None else session_state
    ids = state.setdefault("container_ids", set())
    new_ids = {proof["container_id"] for proof in proofs}
    if ids.intersection(new_ids):
        raise V2Error("container identity reused across separate RC2 observations")
    verdict_path = _within(trial / "verifier" / "verdict.json", directory, file=True)
    verdict = validate_verdict(profile, read_json(verdict_path), task)
    reward_path = _within(trial / "verifier" / "reward.txt", directory, file=True)
    reward = (raw.get("verifier_result") or {}).get("rewards", {}).get("reward")
    if (isinstance(reward, bool) or not isinstance(reward, (int, float))
            or reward != verdict["artifact_correct"]
            or reward_path.read_text(encoding="utf-8").strip() != str(verdict["artifact_correct"])):
        raise V2Error("RC2 raw reward and original verdict disagree")
    tmp = verdict["checks"].get("controller", {})
    if verdict["status"] != "error" and (
        tmp.get("temporary_storage") != "native_private" or tmp.get("temporary_parent") != "/tmp"
    ):
        raise V2Error("RC2 grader did not attest container-native private /tmp")
    received = trial / "artifacts" / "submission"
    transfer = []
    for row in verdict["submission_manifest"]:
        artifact = _within(received / row["path"], received, file=True)
        if file_hash(artifact) != row["sha256"] or artifact.stat().st_size != row["size_bytes"]:
            raise V2Error("RC2 grader and transferred artifact bytes differ")
        transfer.append({"path": row["path"], "sha256": row["sha256"], "size_bytes": row["size_bytes"]})
    received_names = {
        path.relative_to(received).as_posix() for path in received.rglob("*")
        if path.is_file() and not _IGNORED.intersection(path.relative_to(received).parts)
        and path.suffix not in {".pyc", ".pyo"}
    }
    if received_names != {row["path"] for row in verdict["submission_manifest"]}:
        raise V2Error("RC2 received artifact set differs from the grader-observed file set")
    exception = (raw.get("exception_info") or {}).get("exception_type")
    want = int(mode == "oracle")
    ok = (exception is None and verdict["status"] == ("pass" if want else "fail")
          and verdict["artifact_correct"] == want)
    paths = [generated_path, resolved_path, result_path, verdict_path, reward_path, staged / "task.toml"]
    paths += [path for path in (trial / "artifacts").rglob("*") if path.is_file()]
    paths += list((trial / "environment").glob("static-network-*.json"))
    paths += [path for path in (trial / "verifier").glob("worker*") if path.is_file()]
    hashes = {_relative(path, root): file_hash(_within(path, directory, file=True)) for path in paths}
    ids.update(new_ids)
    return {
        "task": task, "agent": mode, "directory": str(directory),
        "component_versions": dict(profile["component_versions"]),
        "profile_sha256": profile["profile_sha256"], "task_root": profile["task_root"],
        "task_sha256": profile["task_specs"][task]["normalized_sha256"],
        "image_digest": agent_image, "grader_image_digest": grader_image,
        "verdict": verdict, "returncode": 0,
        "returncode_scope": "validated completed raw Harbor trial, not grader pass/fail exit code",
        "infrastructure_ok": exception is None and verdict["status"] != "error",
        "expected_result_matched": ok, "exception": exception,
        "static_network_isolation_evidence": proofs,
        "native_temporary_parent": tmp.get("temporary_parent"),
        "native_temporary_storage_validated": tmp.get("temporary_storage") == "native_private"
        and tmp.get("temporary_parent") == "/tmp",
        "transfer_files": transfer, "transfer_file_count": len(transfer),
        "transfer_consistency": "complete_bidirectional_file_set_bytes_match",
        "staged_task_path": _relative(staged, root),
        "staged_task_config_sha256": config_hash, "staged_tree_sha256": tree_hash,
        "harbor_task_checksum": raw["task_checksum"],
        "config_path": _relative(generated_path, root), "config_sha256": file_hash(generated_path),
        "resolved_job_config_path": _relative(resolved_path, root),
        "resolved_job_config_sha256": file_hash(resolved_path),
        "raw_trial": _relative(trial, root), "artifacts_sha256": hashes,
    }


def _environment_matches(profile, tasks, environment):
    if (environment.get("backend") != "docker"
            or environment.get("network_mode") != "no-network"
            or environment.get("verifier_environment_mode") != "separate"
            or environment.get("harbor_runtime") != profile["harbor_runtime"]):
        return False
    for name in ("image_digests", "grader_image_digests"):
        images = environment.get(name, {})
        if set(images) != set(tasks) or any(not isinstance(v, str) or not IMAGE_RE.fullmatch(v) for v in images.values()):
            return False
    versions = environment.get("runtime_versions", {})
    return set(versions) == set(tasks) and all(
        isinstance(row, dict) and all(
            isinstance(row.get(phase), dict) and all(
                isinstance(row[phase].get(key), str) and row[phase][key] for key in ("python", "pytest")
            ) for phase in ("agent", "grader")
        ) for row in versions.values()
    )


def _safety_evidence(profile, directory, rows, environment):
    """Bind the runner's safety closeout to original local receipt files."""
    directory = _run_directory(profile, directory)
    root = Path(profile["repository_root"])
    label_value = hashlib.sha256(str(directory.resolve()).encode("utf-8")).hexdigest()
    if environment.get("version_probe_label") != {"key": PROBE_LABEL_KEY, "value": label_value}:
        raise V2Error("version-probe containers lack this run's exact scoped label")
    if environment.get("execution_errors") != []:
        raise V2Error("RC2 smoke execution did not close without errors")
    bindings = {}
    for name in ("profile.json", "old-stops.json", "containers-before.json", "containers-after.json"):
        path = _within(directory / name, directory, file=True)
        bindings[_relative(path, root)] = file_hash(path)
    for task in SMOKE_TASKS:
        for phase in ("agent", "grader"):
            path = _within(directory / "images" / task / (phase + "-runtime.json"), directory, file=True)
            if read_json(path) != environment["runtime_versions"][task][phase]:
                raise V2Error("pinned image runtime differs from its original version receipt")
            bindings[_relative(path, root)] = file_hash(path)
            launch_path = path.with_name(phase + "-runtime-launch.json")
            launch = read_json(_within(launch_path, directory, file=True))
            image = environment["image_digests" if phase == "agent" else "grader_image_digests"][task]
            name = "r2p-" + label_value[:10] + "-" + task[:25] + "-" + phase
            expected_command = [
                "docker", "run", "--rm", "--name", name, "--label", PROBE_LABEL_KEY + "=" + label_value,
                "--network", "none", "--read-only", "--cap-drop", "ALL", "--security-opt", "no-new-privileges",
                "--pids-limit", "64", "--cpus", "1", "--memory", "2g", image, "python3", "-c", VERSION_PROBE_CODE,
            ]
            if (launch.get("image") != image or launch.get("container_name") != name
                    or launch.get("label_key") != PROBE_LABEL_KEY or launch.get("label_value") != label_value
                    or launch.get("network_mode") != "none" or launch.get("command") != expected_command):
                raise V2Error("runtime inspection did not use the frozen model-free labelled version probe")
            bindings[_relative(launch_path, root)] = file_hash(launch_path)
        for name in ("agent.iid", "grader.iid", "agent-reuse.json"):
            path = directory / "images" / task / name
            if path.exists():
                bindings[_relative(path, root)] = file_hash(_within(path, directory, file=True))
                if name.endswith(".iid"):
                    images = environment["image_digests" if name == "agent.iid" else "grader_image_digests"]
                    if path.read_text(encoding="utf-8").strip() != images[task]:
                        raise V2Error("Docker build IID differs from the run's pinned image")
    if read_json(directory / "profile.json") != profile:
        raise V2Error("on-disk RC2 profile does not match its frozen runtime identity")
    receipts = read_json(directory / "old-stops.json")
    if not isinstance(receipts, dict):
        raise V2Error("historical STOP receipts are not an object")
    for relative, expected in receipts.items():
        if (not isinstance(relative, str) or Path(relative).is_absolute()
                or "\\" in relative or ":" in relative or ".." in relative.split("/")
                or Path(relative).name != "STOP" or not relative.startswith("experiments/smallowbench-v2/")
                or not isinstance(expected, str) or not DIGEST_RE.fullmatch(expected)
                or file_hash(_within(root / relative, root, file=True)) != expected):
            raise V2Error("historical STOP evidence is unsafe or changed")
    inventories = {}
    for phase in ("before", "after"):
        records = read_json(directory / ("containers-" + phase + ".json")).get("containers")
        if (not isinstance(records, list) or records != environment.get("container_inventory_" + phase)
                or any(not isinstance(row, dict) or not isinstance(row.get("ID"), str)
                       or not DIGEST_RE.fullmatch(row["ID"]) for row in records)
                or len({row["ID"] for row in records}) != len(records)):
            raise V2Error("container inventory differs from its original scoped receipt")
        inventories[phase] = records
    proofs = [proof for row in rows for proof in row.get("static_network_isolation_evidence", [])]
    ids = {proof["container_id"] for proof in proofs}
    sessions = {proof["session_id"].lower() for proof in proofs}
    remaining = []
    for item in inventories["after"]:
        text = item.get("Labels", "")
        if not isinstance(text, str):
            raise V2Error("container inventory labels are not strings")
        labels = dict(part.split("=", 1) for part in text.split(",") if "=" in part)
        if (item["ID"] in ids or labels.get("com.docker.compose.project") in sessions
                or labels.get(PROBE_LABEL_KEY) == label_value):
            remaining.append(item["ID"])
    cleanup = environment.get("cleanup_check", {})
    if (remaining or cleanup.get("zero_residual") is not True
            or cleanup.get("remaining_containers") != []
            or set(cleanup.get("checked_sessions", [])) != sessions):
        raise V2Error("this RC2 run's exact containers/sessions did not close cleanly")
    planned_jobs = {f"v2-{mode}-{task}" for task in SMOKE_TASKS for mode in ("oracle", "nop")}
    if ({path.name for path in (directory / "jobs").iterdir() if path.is_dir()} != planned_jobs
            or {path.stem for path in (directory / "configs").glob("*.json")} != planned_jobs):
        raise V2Error("RC2 smoke directory contains missing or unplanned executed jobs/configurations")
    return bindings


def summarize(profile, tasks, rows, environment):
    """Fixed five-task smoke acceptance; full-bank activation is not implemented."""
    validate_profile(profile)
    tasks = list(tasks)
    if tasks != list(SMOKE_TASKS):
        raise V2Error("this RC2 model-free integration supports only the fixed five-task smoke scope")
    expected = {(task, mode) for task in tasks for mode in ("oracle", "nop")}
    identities = [(row.get("task"), row.get("agent")) for row in rows]
    complete = len(rows) == len(expected) and set(identities) == expected
    issues, state, directories = [], {}, set()
    if not _environment_matches(profile, tasks, environment):
        issues.append({"kind": "environment_identity_or_scope_mismatch"})
    for row in rows:
        task, mode = row.get("task"), row.get("agent")
        try:
            if (task, mode) not in expected or identities.count((task, mode)) != 1:
                raise V2Error("duplicate or unplanned RC2 observation")
            directories.add(row["directory"])
            actual = inspect_trial(profile, task, mode, row["directory"],
                environment["image_digests"][task], environment["grader_image_digests"][task], state)
            if any(row.get(key) != value for key, value in actual.items()):
                raise V2Error("RC2 cached row disagrees with recomputed original evidence")
            if not actual["expected_result_matched"] or not actual["infrastructure_ok"]:
                raise V2Error("RC2 oracle/nop outcome did not match the predeclared expectation")
            if actual["verdict"].get("runtime") != environment["runtime_versions"][task]["grader"]:
                raise V2Error("grader-observed runtime differs from its pinned image runtime evidence")
        except (OSError, ValueError, KeyError, TypeError) as exc:
            issues.append({"kind": "invalid_original_evidence", "task": task, "agent": mode, "detail": str(exc)})
    if len(directories) != 1:
        issues.append({"kind": "evidence_must_belong_to_one_explicit_run_directory"})
    safety = {}
    if len(directories) == 1:
        try:
            safety = _safety_evidence(profile, next(iter(directories)), rows, environment)
        except (OSError, ValueError, KeyError, TypeError) as exc:
            issues.append({"kind": "invalid_safety_closeout_evidence", "detail": str(exc)})
    diagnostic_success = complete and not issues
    report = {
        "schema_version": 1, "kind": REPORT_KIND,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "repository_root": profile["repository_root"], "task_root": profile["task_root"],
        "profile_sha256": profile["profile_sha256"],
        "candidate_manifest_file_sha256": profile["bank_manifest"]["sha256"],
        "component_versions": dict(profile["component_versions"]),
        "benchmark_version": profile["component_versions"]["benchmark"],
        "source_hashes": profile["source_hashes"], "environment": environment, "rows": rows,
        "run_safety_bindings": safety,
        "diagnostic_requested_tasks": tasks, "diagnostic_expected_slots": len(expected),
        "diagnostic_complete": complete, "diagnostic_success": diagnostic_success,
        "requested_scope_passed": diagnostic_success,
        "full_bank_coverage": False, "container_validated": False,
        "all_passed": False, "release_gate_passed": False,
        "issues": issues, "model_calls": 0, "cloud_sandbox_creates": 0,
        "model_execution_authorized": False, "formal_ranking_eligible": False,
        "candidate_activated": False,
        "scope": "version-bound original oracle/nop Linux Docker evidence; selected scope is not a release gate",
    }
    report["report_sha256"] = digest(report)
    return report


def validate_smoke_report(report, profile=None, *, tasks=None):
    """Read-only revalidation of exact raw evidence; RC1 reports are not accepted."""
    report = read_json(report) if isinstance(report, (str, Path)) else report
    if (not isinstance(report, dict) or report.get("kind") != REPORT_KIND
            or report.get("schema_version") != 1
            or report.get("report_sha256") != digest({k: v for k, v in report.items() if k != "report_sha256"})):
        raise V2Error("not a valid additive RC2 container evidence report")
    profile = load_profile(report["repository_root"]) if profile is None else validate_profile(profile)
    requested = report["diagnostic_requested_tasks"]
    if tasks is not None and list(tasks) != requested:
        raise V2Error("RC2 evidence does not cover the explicitly requested task scope")
    actual = summarize(profile, requested, report["rows"], report["environment"])
    for key, value in actual.items():
        if key not in {"generated_at", "report_sha256"} and report.get(key) != value:
            raise V2Error("RC2 report disagrees with recomputed scope/component/raw evidence: " + key)
    if not actual["diagnostic_success"]:
        raise V2Error("RC2 requested-scope container evidence has not passed")
    directories = {row["directory"] for row in report["rows"]}
    state_path = _within(Path(next(iter(directories))) / "run-state.json", next(iter(directories)), file=True)
    state = read_json(state_path)
    if state != {"status": "completed", "execution_errors": []}:
        raise V2Error("RC2 run completion state is missing, failed, or not safely closed")
    if report.get("execution_errors", []) != [] or report.get("historical_stops_preserved", True) is not True:
        raise V2Error("RC2 report contains runner or STOP safety errors")
    if report.get("automatic_retries", 0) != 0:
        raise V2Error("RC2 smoke evidence cannot claim automatic retries")
    return report


def execute_models(*args, **kwargs):
    raise V2Error("model execution is disabled in this model-free RC2 integration")


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check-profile", action="store_true")
    parser.add_argument("--analyze-smoke", type=Path)
    args = parser.parse_args(argv)
    profile = load_profile()
    if args.analyze_smoke:
        report = validate_smoke_report(args.analyze_smoke, profile)
        value = {key: report[key] for key in ("diagnostic_success", "container_validated", "release_gate_passed", "report_sha256")}
    else:
        value = {key: profile[key] for key in ("kind", "task_root", "component_versions", "profile_sha256", "model_execution_enabled")}
        value["task_count"] = len(profile["task_specs"])
    print(json.dumps(value, ensure_ascii=False, allow_nan=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
