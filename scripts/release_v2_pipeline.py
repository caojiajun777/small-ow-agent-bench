"""Additive SmallOWBench 2.0 formal release preparation and evidence binding.

No function in this module launches a model, shell, container, or provider.
Legacy execution/scoring modules and historical experiments are not modified.
"""

from __future__ import annotations

from collections import Counter
from datetime import datetime, timezone
import hashlib
import importlib.metadata
import json
import math
from pathlib import Path
import re
import shutil
import sqlite3
import sys
import tomllib
import warnings

from task_sets import MAIN_47, HARD_RELEASE_15
from validate_upgraded_tasks import task_digest

VERSION = "2.0.0-rc.2"
HARNESS_VERSION = "2.0.0-rc.1"
COMPONENT_VERSIONS = {"benchmark": VERSION, "task": VERSION, "grader": VERSION, "harness": HARNESS_VERSION}
AGENT_IMPORT_PATH = "agents.compact_shell_v2:CompactShellV2Agent"
ORIGINAL_ROSTER_SHA256 = "f77f510c4991f5033f3d9587d508554d414acbb3fff92715f8e6d9a23f5e0969"
_SMOKE_VALIDATION_CACHE = {}
SCORER_VERSION = "smallowbench-v2-taskbinary-1"
BANK_62 = (*MAIN_47, *HARD_RELEASE_15)
SKILLS = ("loc", "edit", "testgen", "repro", "review")
ROOT = Path(__file__).resolve().parents[1]
DIGEST_RE = re.compile(r"^[0-9a-f]{64}$")
IMAGE_RE = re.compile(r"^sha256:[0-9a-f]{64}$")
SAFE_NAME = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]*$")
HARNESS_SOURCES = (
    "agents/compact_shell_v2.py",
    "agents/protocol_v2.py",
    "agents/artifacts_v2.py",
)
PIPELINE_SOURCES = (
    "scripts/release_v2_pipeline.py",
    "scripts/run_release_v2.py",
    "scripts/analyze_release_v2.py",
    "scripts/build_release_v2_images.py",
    "scripts/rc2_pipeline.py",
    "scripts/prepare_rc2_candidate.py",
    "scripts/rc2_task_patches.py",
)
EXECUTION_SOURCES = (
    "scripts/release_v2_executor.py",
    "scripts/v2_paths.py",
    "scripts/v2_routes.py",
    "scripts/route_probe_v2.py",
    "scripts/v2_budget_handoff.py",
    "scripts/validate_v2_containers.py",
    "scripts/experiment_execution.py",
    "scripts/ledger_io.py",
    "scripts/classify_timeouts.py",
    "scripts/task_sets.py",
    "scripts/validate_upgraded_tasks.py",
)
SUBMISSION_SCHEMAS = {
    "loc": {"name": "relative-file-set", "version": 2, "path": "/app/answer.txt"},
    "edit": {"name": "repository-patch", "version": 2, "path": "/app/repo"},
    "testgen": {
        "name": "behavioral-pytest-suite",
        "version": 2,
        "path": "/app/repo/tests",
    },
    "repro": {
        "name": "standalone-behavior-reproducer",
        "version": 2,
        "path": "/app/repro.py",
    },
    "review": {
        "name": "behavioral-multi-candidate-review",
        "version": 2,
        "path": "/app/review.json",
    },
}
SCORING_POLICY = {
    "unit": "task",
    "tasks": 62,
    "skill_macro": "equal skills; equal tasks within skill",
    "task_micro": "all 62 tasks; complete frozen repetitions only",
    "infra_or_missing": "missing; never imputed zero",
    "difficulty_weights": None,
}
INFRA_EXCEPTIONS = {
    "BuildException",
    "EnvironmentStartTimeoutError",
    "EnvironmentStartError",
    "CancelledError",
    "RewardFileNotFoundError",
    "RewardFileEmptyError",
    "VerifierOutputParseError",
    "ReadError",
    "RateLimitException",
    "RateLimitError",
    "ConnectError",
    "APIConnectionError",
    "ServiceUnavailableError",
    "ServiceUnavailable",
    "InternalServerError",
    "AuthenticationError",
}


class V2Error(ValueError):
    pass


def canonical(value):
    return json.dumps(
        value,
        sort_keys=True,
        ensure_ascii=False,
        allow_nan=False,
        separators=(",", ":"),
    )


def digest(value):
    return hashlib.sha256(canonical(value).encode("utf-8")).hexdigest()


def file_hash(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def document_digest(value, field="manifest_sha256"):
    return digest({key: item for key, item in value.items() if key != field})


def read_json(path):
    def pairs(items):
        result = {}
        for key, value in items:
            if key in result:
                raise V2Error("duplicate JSON key: " + key)
            result[key] = value
        return result

    return json.loads(
        Path(path).read_text(encoding="utf-8"),
        object_pairs_hook=pairs,
        parse_constant=lambda value: (_ for _ in ()).throw(
            V2Error("nonfinite JSON: " + value)
        ),
    )


def safe_name(name):
    if (
        not isinstance(name, str)
        or not SAFE_NAME.fullmatch(name)
        or name in (".", "..")
    ):
        raise V2Error("unsafe experiment/model/job name")
    return name


def bound_file(path):
    path = Path(path).resolve()
    if not path.is_file() or path.is_symlink():
        raise V2Error("evidence must be a regular file")
    return {"path": str(path), "sha256": file_hash(path)}


def read_binding(binding):
    path = Path(binding["path"]).resolve()
    if bound_file(path)["sha256"] != binding.get("sha256"):
        raise V2Error("bound file changed: " + path.name)
    return read_json(path)


def legacy_tree_digest(path):
    """Historical byte-exact tree digest, deliberately separate from v2 normalized hash."""
    rows = []
    path = Path(path)
    for item in sorted(path.rglob("*")):
        if (
            not item.is_file()
            or {"__pycache__", ".pytest_cache", ".git"}.intersection(item.parts)
            or item.suffix == ".pyc"
        ):
            continue
        if item.is_symlink() or item.name.startswith(".env"):
            raise V2Error("symlink/credential file in task tree")
        rows.append([item.relative_to(path).as_posix(), file_hash(item)])
    if not rows:
        raise V2Error("empty task tree")
    return digest(rows)


def staged_task_text(path, agent_image, grader_image):
    text = Path(path).read_text(encoding="utf-8").replace("\r\n", "\n")
    for table, image in (
        ("environment", agent_image),
        ("verifier.environment", grader_image),
    ):
        if not isinstance(image, str) or not IMAGE_RE.fullmatch(image):
            raise V2Error("staging requires immutable Docker images")
        anchor = "[" + table + "]\n"
        if text.count(anchor) != 1:
            raise V2Error(
                "task must have exactly one agent and separate grader environment"
            )
        config = tomllib.loads(text)
        section = (
            config["environment"]
            if table == "environment"
            else config["verifier"]["environment"]
        )
        if "docker_image" in section:
            raise V2Error("published task already pins a run-specific image")
        text = text.replace(anchor, anchor + 'docker_image = "' + image + '"\n')
    config = tomllib.loads(text)
    if (
        config["verifier"].get("environment_mode") != "separate"
        or config["environment"].get("network_mode") != "no-network"
        or config["verifier"]["environment"].get("network_mode") != "no-network"
    ):
        raise V2Error("v2 tasks must keep separate no-network agent/grader containers")
    return text


def staged_tree_digest(task_root, config_text):
    task_root = Path(task_root)
    rows = []
    for path in sorted(task_root.rglob("*")):
        if (
            not path.is_file()
            or {"__pycache__", ".pytest_cache", ".git", ".ruff_cache"}.intersection(
                path.parts
            )
            or path.suffix in (".pyc", ".pyo")
        ):
            continue
        if path.is_symlink() or path.name.startswith(".env"):
            raise V2Error("unsafe source in staged task")
        relative = path.relative_to(task_root).as_posix()
        value = (
            hashlib.sha256(config_text.encode("utf-8")).hexdigest()
            if relative == "task.toml"
            else file_hash(path)
        )
        rows.append([relative, value])
    return digest(rows)


def harbor_task_checksum(task_root):
    from harbor.models.task.task import Task

    with warnings.catch_warnings():
        warnings.filterwarnings(
            "ignore",
            message="Task.checksum will be deprecated soon.*",
            category=DeprecationWarning,
        )
        return Task(Path(task_root)).checksum


def task_root(root=ROOT):
    return Path(root).resolve() / "task-banks" / "rc2" / "tasks"


def stage_tasks(manifest, directory, *, root=ROOT):
    """Generate run copies only. No task source edits, subprocesses, or containers."""
    directory = Path(directory).resolve()
    if manifest["directory"] != str(directory):
        raise V2Error("staging belongs to another experiment")
    result = {}
    for task, spec in manifest["tasks"].items():
        source = task_root(root) / task
        text = staged_task_text(
            source / "task.toml",
            manifest["runtime_environment_evidence"]["image_digests"][task],
            manifest["runtime_environment_evidence"]["grader_image_digests"][task],
        )
        target = directory / "staged-tasks" / task
        if not target.exists():
            shutil.copytree(
                source,
                target,
                ignore=shutil.ignore_patterns(
                    "__pycache__",
                    ".pytest_cache",
                    ".git",
                    ".ruff_cache",
                    "*.pyc",
                    "*.pyo",
                ),
            )
            (target / "task.toml").write_text(text, encoding="utf-8", newline="\n")
        if (
            file_hash(target / "task.toml") != spec["staged_task_config_sha256"]
            or legacy_tree_digest(target) != spec["staged_tree_sha256"]
        ):
            raise V2Error("staged task has drifted; never overwrite it")
        from harbor.models.task.config import TaskConfig

        TaskConfig.model_validate_toml(text)
        result[task] = str(target)
    return result


def job_config(manifest, slot, job_name, directory):
    safe_name(job_name)
    if (
        slot not in manifest["schedule"]
        or str(Path(directory).resolve()) != manifest["directory"]
    ):
        raise V2Error("job is not part of this frozen experiment")
    model = manifest["models"][slot["model"]]
    config = {
        "job_name": job_name,
        "jobs_dir": str(Path(directory).resolve() / "jobs"),
        "n_attempts": 1,
        "n_concurrent_trials": 1,
        "timeout_multiplier": 1.0,
        "quiet": True,
        "retry": {"max_retries": 0},
        "environment": {"type": "docker", "force_build": False, "delete": False},
        "agents": [
            {
                "import_path": manifest["agent_import_path"],
                "model_name": model["runtime_id"],
                "kwargs": {**model["agent_kwargs"], "task_id": slot["task"]},
            }
        ],
        "tasks": [
            {"path": str(Path(directory).resolve() / "staged-tasks" / slot["task"])}
        ],
    }
    if manifest.get("diagnostic") is not None:
        condition = next(
            row for row in manifest["diagnostic"]["conditions"]
            if row["name"] == slot["condition"]
        )
        config["agents"][0]["override_timeout_sec"] = condition["agent_timeout_sec"]
        config["agents"][0]["kwargs"]["max_turns"] = condition["max_turns"]
    from harbor.models.job.config import JobConfig

    JobConfig.model_validate(config)
    return config


def normalized_job_config(value):
    from harbor.models.job.config import JobConfig

    result = JobConfig.model_validate(value).model_dump(mode="json")
    for name in ("include_exceptions", "exclude_exceptions"):
        items = result.get("retry", {}).get(name)
        if isinstance(items, list):
            result["retry"][name] = sorted(items)
    return result


def load_bank(path, *, root=ROOT):
    path, root = Path(path).resolve(), Path(root).resolve()
    from prepare_rc2_candidate import validate_candidate

    expected_path = task_root(root).parent / "task-bank-v2.manifest.json"
    if path != expected_path:
        raise V2Error("release must use the explicit additive RC2 candidate bank")
    bank = validate_candidate(expected_path.parent, root=root)
    if read_json(path) != bank:
        raise V2Error("RC2 candidate changed during release loading")
    # The bank builder predates this experiment document's compact JSON policy.
    body = {key: value for key, value in bank.items() if key != "manifest_sha256"}
    expected = hashlib.sha256(
        json.dumps(body, sort_keys=True, ensure_ascii=False).encode("utf-8")
    ).hexdigest()
    if bank.get("manifest_sha256") != expected or bank.get("task_version") != VERSION:
        raise V2Error("task-bank self digest/version mismatch")
    items = bank.get("items", [])
    if (
        bank.get("task_count") != 62
        or len(items) != 62
        or {item.get("id") for item in items} != set(BANK_62)
    ):
        raise V2Error("the v2 bank must contain each official task exactly once")
    tasks = {}
    for item in items:
        task = item["id"]
        skill = task.split("-", 1)[0]
        directory = task_root(root) / task
        config = tomllib.loads((directory / "task.toml").read_text(encoding="utf-8"))
        if (
            item.get("task_version") != VERSION
            or config["task"]["version"] != VERSION
            or item.get("skill") != skill
            or skill not in SKILLS
        ):
            raise V2Error("task version/skill mismatch: " + task)
        normalized = task_digest(directory)
        if item.get("task_sha256") != normalized:
            raise V2Error("stale task-bank fingerprint: " + task)
        tasks[task] = {
            "skill": skill,
            "task_version": VERSION,
            "normalized_sha256": normalized,
            "legacy_tree_sha256": legacy_tree_digest(directory),
            "submission_schema": SUBMISSION_SCHEMAS[skill],
        }
    return bank, tasks


def validate_verdict(verdict, task):
    if not isinstance(verdict, dict) or verdict.get("schema_version") != 2:
        raise V2Error("verdict schema 2 is required")
    if (
        verdict.get("task_id") != task
        or verdict.get("task_version") != VERSION
        or verdict.get("grader_version") != VERSION
    ):
        raise V2Error("verdict identity/version mismatch")
    status, correct = verdict.get("status"), verdict.get("artifact_correct")
    if status not in ("pass", "fail", "error"):
        raise V2Error("unknown verdict status")
    if (
        status == "error"
        and correct is not None
        or status != "error"
        and (type(correct) is not int or correct != int(status == "pass"))
    ):
        raise V2Error("verdict status and artifact correctness disagree")
    rows = verdict.get("submission_manifest")
    if not isinstance(rows, list):
        raise V2Error("verdict submission manifest is required")
    paths = []
    for row in rows:
        if not isinstance(row, dict) or set(row) != {
            "path",
            "role",
            "size_bytes",
            "sha256",
        }:
            raise V2Error("invalid submission manifest row")
        name = row["path"]
        if (
            not isinstance(name, str)
            or not name
            or Path(name).is_absolute()
            or "\\" in name
            or ":" in name
            or ".." in name.split("/")
            or row["role"] not in ("submission", "observation")
            or type(row["size_bytes"]) is not int
            or row["size_bytes"] < 0
            or not isinstance(row["sha256"], str)
            or not DIGEST_RE.fullmatch(row["sha256"])
        ):
            raise V2Error("unsafe/invalid submission manifest row")
        paths.append(name)
    if paths != sorted(set(paths)) or verdict.get("submission_digest") != digest(rows):
        raise V2Error("submission digest/path order mismatch")
    if status == "pass":
        submitted = {row["path"] for row in rows if row["role"] == "submission"}
        skill = task.split("-", 1)[0]
        required = {
            "loc": "answer.txt",
            "repro": "repro.py",
            "review": "review.json",
        }.get(skill)
        if (
            required
            and required not in submitted
            or not submitted
            or skill == "testgen"
            and not any(
                name.startswith("repo/tests/")
                and Path(name).name.startswith("test_")
                and name.endswith(".py")
                for name in submitted
            )
            or skill == "edit"
            and not any(name.startswith("repo/") for name in submitted)
        ):
            raise V2Error("passing verdict lacks its required submission evidence")
    elapsed = verdict.get("elapsed_sec")
    if (
        isinstance(elapsed, bool)
        or not isinstance(elapsed, (int, float))
        or not math.isfinite(elapsed)
        or elapsed < 0
    ):
        raise V2Error("invalid verdict duration")
    if (
        "checks" not in verdict
        or "evidence" not in verdict
        or "failure_category" not in verdict
    ):
        raise V2Error("verdict lacks structured diagnostic fields")
    return verdict


def preflight_policy():
    return {
        "kind": "sampled_rc2_model_free_evidence",
        "validated_task_ids": [
            "loc-bind-host", "edit-clip", "testgen-timeout-zero",
            "repro-keep-zero", "review-clip-incomplete",
        ],
        "full_bank_container_validated": False,
        "additional_preflight_required": False,
    }


def _check_relative_artifacts(artifacts, root):
    from prepare_rc2_candidate import reject_links

    root = Path(root).resolve()
    if not isinstance(artifacts, dict) or not artifacts:
        raise V2Error("release evidence needs original fingerprinted artifacts")
    for relative, expected in artifacts.items():
        if (not isinstance(relative, str) or not relative or Path(relative).is_absolute()
                or "\\" in relative or ":" in relative or ".." in relative.split("/")
                or any(part.startswith(".env") for part in relative.split("/"))
                or not isinstance(expected, str) or not DIGEST_RE.fullmatch(expected)):
            raise V2Error("unsafe release evidence binding")
        path = root / relative
        reject_links(path)
        if (not path.resolve().is_relative_to(root) or not path.is_file()
                or file_hash(path) != expected):
            raise V2Error("release evidence missing or drifted: " + relative)


def _strict_smoke_validation(path):
    from rc2_pipeline import validate_smoke_report
    return validate_smoke_report(path)


def _evidence_tree_signature(directory):
    """A cache guard includes new files/directories, not only old file hashes."""
    from prepare_rc2_candidate import reject_links

    rows = []
    for path in sorted(Path(directory).rglob("*")):
        reject_links(path)
        relative = path.relative_to(directory).as_posix()
        if path.is_file():
            rows.append([relative, "file", file_hash(path)])
        elif path.is_dir():
            rows.append([relative, "directory"])
        else:
            raise V2Error("non-regular entry added to original preflight evidence")
    return digest(rows)


def validate_preflight(path, tasks, bank_binding, *, manifest_sha256=None, root=ROOT):
    """Bind existing five-task RC2 evidence, never pretend it is a 124-slot gate.

    Successful semantic revalidation is cached only while *every* original raw
    artifact, frozen source and Harbor runtime remains freshly hash-matched.
    No boolean-only cache or model/container request is used.
    """
    from rc2_pipeline import runtime_evidence

    root = Path(root).resolve()
    report = read_json(path)
    policy = preflight_policy()
    if (report.get("schema_version") != 1
            or report.get("kind") != "smallowbench_rc2_container_evidence"
            or report.get("component_versions") != COMPONENT_VERSIONS
            or report.get("repository_root") != str(root)
            or report.get("task_root") != str(task_root(root))
            or report.get("candidate_manifest_file_sha256") != bank_binding["sha256"]
            or report.get("profile_sha256") is None
            or report.get("diagnostic_requested_tasks") != policy["validated_task_ids"]
            or report.get("diagnostic_expected_slots") != 10
            or report.get("diagnostic_success") is not True
            or report.get("diagnostic_complete") is not True
            or report.get("requested_scope_passed") is not True
            or any(report.get(name) is not False for name in (
                "container_validated", "full_bank_coverage", "release_gate_passed",
                "all_passed", "candidate_activated", "model_execution_authorized",
                "formal_ranking_eligible"))
            or report.get("model_calls") != 0
            or report.get("cloud_sandbox_creates") != 0
            or report.get("report_sha256") != document_digest(report, "report_sha256")):
        raise V2Error("release requires the existing version-bound RC2 sampled preflight")
    rows = report.get("rows", [])
    expected = {(task, mode) for task in policy["validated_task_ids"] for mode in ("oracle", "nop")}
    if (len(rows) != 10 or {(row.get("task"), row.get("agent")) for row in rows} != expected
            or any(row.get("task_sha256") != tasks[row["task"]]["normalized_sha256"] for row in rows)):
        raise V2Error("sampled preflight task scope/fingerprints do not match the RC2 bank")
    artifacts = {}
    for row in rows:
        artifacts.update(row.get("artifacts_sha256", {}))
    artifacts.update(report.get("run_safety_bindings", {}))
    _check_relative_artifacts(artifacts, root)
    _check_relative_artifacts(report.get("source_hashes"), root)
    if report.get("environment", {}).get("harbor_runtime") != runtime_evidence(root):
        raise V2Error("sampled preflight Harbor runtime changed")
    directories = {row.get("directory") for row in rows}
    if len(directories) != 1:
        raise V2Error("sampled preflight spans more than one original run")
    directory = Path(next(iter(directories))).resolve()
    if directory.parent != root / "experiments" / "smallowbench-v2":
        raise V2Error("sampled preflight original directory is outside experiment scope")
    state = read_json(directory / "run-state.json")
    if state != {"status": "completed", "execution_errors": []}:
        raise V2Error("sampled preflight no longer has its safe completed state")
    _check_relative_artifacts(read_json(directory / "old-stops.json"), root)
    cache_key = digest({
        "report": bound_file(path), "artifacts": artifacts,
        "source_hashes": report["source_hashes"],
        "harbor_runtime": report["environment"]["harbor_runtime"],
        "complete_evidence_tree": _evidence_tree_signature(directory),
    })
    if cache_key not in _SMOKE_VALIDATION_CACHE:
        checked = _strict_smoke_validation(path)
        if checked != report:
            raise V2Error("sampled preflight changed while strictly revalidating")
        _SMOKE_VALIDATION_CACHE[cache_key] = True
    return report


def _validate_runtime_receipts(value, path, tasks, preflight, root):
    """Reconstruct image/runtime identity from each original build receipt."""
    from prepare_rc2_candidate import reject_links
    from validate_rc2_containers import context_digest

    directory = Path(path).resolve().parent
    if directory.parent != root / "experiments" / "smallowbench-v2":
        raise V2Error("release image receipts must belong to one explicit initialization directory")
    raw_bindings = value["raw_artifacts_sha256"]
    environment = value["environment"]
    def required(path, *, as_json=True):
        reject_links(path)
        relative = path.relative_to(root).as_posix()
        if relative not in raw_bindings or file_hash(path) != raw_bindings[relative]:
            raise V2Error("required image initialization receipt is missing/unbound: " + relative)
        return read_json(path) if as_json else path.read_text(encoding="utf-8").strip()

    actual_files = {
        entry.relative_to(root).as_posix() for entry in directory.rglob("*") if entry.is_file()
        and entry not in {directory / "runtime.json", directory / "runtime.pending.json"}
    }
    declared_files = {name for name in raw_bindings if (root / name).is_relative_to(directory)}
    if actual_files != declared_files:
        raise V2Error("image initialization contains missing or untracked raw files")
    if {entry.name for entry in (directory / "images").iterdir() if entry.is_dir()} != set(tasks):
        raise V2Error("image initialization must contain exactly 62 task receipt directories")
    state = required(directory / "run-state.json")
    if (state.get("kind") != "smallowbench_v2_image_initialization"
            or state.get("status") != "completed" or state.get("completed_tasks") != sorted(tasks)
            or state.get("expected_tasks") != 62 or state.get("execution_errors") != []
            or state.get("historical_stops_preserved") is not True
            or any(state.get(key) != 0 or value.get(key) != 0
                   for key in ("model_calls", "task_evaluation_runs", "automatic_retries"))):
        raise V2Error("image initialization did not close safely without task/model execution")
    _check_relative_artifacts(required(directory / "old-stops.json"), root)
    if required(directory / "builder-sources.json") != value["builder_sources"]:
        raise V2Error("image initialization builder-source receipt disagrees with runtime")
    sampled_directory = Path(preflight["rows"][0]["directory"])
    sampled_profile = read_json(sampled_directory / "profile.json")
    if required(directory / "core-profile.json") != sampled_profile:
        raise V2Error("image initialization used a different RC2 component profile")
    label_key = "smallowbench.rc2.smoke"
    label = hashlib.sha256(str(directory).encode("utf-8")).hexdigest()
    if environment.get("version_probe_label") != {"key": label_key, "value": label, "kind": "dependency_version_only"}:
        raise V2Error("dependency-version probe label is not scoped to this image initialization")
    probe_names = set()
    pinned_tasks = set(preflight_policy()["validated_task_ids"])
    for task, spec in tasks.items():
        local = directory / "images" / task
        receipt = required(local / "receipt.json")
        pinned = task in pinned_tasks
        contexts = {role: context_digest(task_root(root) / task / ("environment" if role == "agent" else "tests"))
                    for role in ("agent", "grader")}
        if (receipt.get("kind") != "dependency_image_initialization_receipt" or receipt.get("task") != task
                or receipt.get("task_sha256") != spec["normalized_sha256"]
                or receipt.get("context_sha256") != contexts
                or receipt.get("runtime_versions") != environment["runtime_versions"][task]
                or receipt.get("reused_existing_rc2_pins") is not pinned
                or receipt.get("version_probe_kind") != ("existing_version_receipt_reuse" if pinned else "dependency_version_only")):
            raise V2Error("per-task image receipt has a different task/context/runtime identity: " + task)
        if pinned:
            reuse = required(local / "pinned-reuse.json")
            original_report = sampled_directory / "preflight-rc2.json"
            if (reuse.get("kind") != "exact_existing_rc2_image_runtime_reuse" or reuse.get("task") != task
                    or reuse.get("source_report") != original_report.relative_to(root).as_posix()
                    or reuse.get("source_report_sha256") != file_hash(original_report)
                    or not isinstance(reuse.get("source_artifacts_sha256"), dict)
                    or any(raw_bindings.get(name) != expected for name, expected in reuse["source_artifacts_sha256"].items())):
                raise V2Error("validated five-task image reuse lacks its original evidence")
            _check_relative_artifacts(reuse["source_artifacts_sha256"], root)
        for role, image_key in (("agent", "image_digests"), ("grader", "grader_image_digests")):
            image = environment[image_key][task]
            inspect = required(local / (role + "-image-inspect.json"))
            if (receipt.get(role + "_image") != image
                    or required(local / (role + ".iid"), as_json=False) != image
                    or required(local / (role + "-runtime.json")) != environment["runtime_versions"][task][role]
                    or inspect.get("kind") != "immutable_local_image_identity"
                    or inspect.get("requested_image") != image or inspect.get("actual_image") != image
                    or type(inspect.get("returncode")) is not int or inspect["returncode"] != 0
                    or inspect.get("exact_match") is not True):
                raise V2Error("image IID/inspection/runtime original receipts disagree with the run: " + task)
            if pinned:
                original_runtime = sampled_directory / "images" / task / (role + "-runtime.json")
                if required(original_runtime) != environment["runtime_versions"][task][role]:
                    raise V2Error("five-task original dependency-version receipt changed")
            else:
                launch = required(local / (role + "-runtime-launch.json"))
                name = "r2p-" + label[:10] + "-" + task[:25] + "-" + role
                command = ["docker", "run", "--rm", "--name", name, "--label", label_key + "=" + label,
                           "--network", "none", "--read-only", "--cap-drop", "ALL", "--security-opt", "no-new-privileges",
                           "--pids-limit", "64", "--cpus", "1", "--memory", "2g", image, "python3", "-c",
                           "import json,sys,pytest;print(json.dumps({'python':sys.version,'pytest':pytest.__version__}))"]
                if (launch.get("image") != image or launch.get("container_name") != name
                        or launch.get("label_key") != label_key or launch.get("label_value") != label
                        or launch.get("network_mode") != "none" or launch.get("command") != command):
                    raise V2Error("unfrozen or non-version-only dependency probe command")
                probe_names.add(name)
    before, after = (required(directory / ("containers-" + phase + ".json")).get("containers") for phase in ("before", "after"))
    if any(not isinstance(rows, list) or any(not isinstance(item, dict) or not isinstance(item.get("ID"), str)
            or not DIGEST_RE.fullmatch(item["ID"]) for item in rows) for rows in (before, after)):
        raise V2Error("image initialization container inventory is malformed")
    remaining = []
    for item in after:
        labels = dict(part.split("=", 1) for part in item.get("Labels", "").split(",") if "=" in part)
        if labels.get(label_key) == label or probe_names.intersection(item.get("Names", "").split(",")):
            remaining.append(item["ID"])
    cleanup = required(directory / "inventory-check.json")
    if (remaining or {item["ID"] for item in before} - {item["ID"] for item in after}
            or cleanup != environment.get("cleanup_check")
            or cleanup.get("kind") != "exact_version_probe_inventory_check"
            or cleanup.get("label_key") != label_key or cleanup.get("label_value") != label
            or cleanup.get("checked_probe_names") != sorted(probe_names)
            or cleanup.get("zero_residual") is not True or cleanup.get("remaining_containers") != []
            or cleanup.get("preexisting_containers_preserved") is not True
            or cleanup.get("missing_preexisting_container_ids") != []):
        raise V2Error("image initialization dependency probes did not close with a safe original inventory")


def validate_runtime(path, tasks, bank_binding, preflight, *, root=ROOT):
    """Freeze normal image-build evidence for all 62 tasks, not new oracle runs."""
    from rc2_pipeline import runtime_evidence

    if path is None:
        raise V2Error("formal release needs explicit 62-task immutable image/runtime evidence")
    root = Path(root).resolve()
    value = read_json(path)
    if (value.get("schema_version") != 1
            or value.get("kind") != "smallowbench_v2_release_runtime"
            or value.get("task_root") != str(task_root(root))
            or value.get("task_bank_manifest_sha256") != bank_binding["sha256"]
            or value.get("component_versions") != COMPONENT_VERSIONS
            or value.get("task_sha256") != {task: spec["normalized_sha256"] for task, spec in tasks.items()}):
        raise V2Error("release image evidence has a different task bank/component identity")
    environment = value.get("environment", {})
    if (environment.get("backend") != "docker"
            or environment.get("network_mode") != "no-network"
            or environment.get("verifier_environment_mode") != "separate"
            or environment.get("harbor_runtime") != runtime_evidence(root)):
        raise V2Error("release runtime must preserve separate no-network Docker and Harbor identity")
    for name in ("image_digests", "grader_image_digests"):
        images = environment.get(name, {})
        if (set(images) != set(tasks)
                or any(not isinstance(image, str) or not IMAGE_RE.fullmatch(image) for image in images.values())):
            raise V2Error("release needs immutable agent/grader images for all 62 tasks")
    versions = environment.get("runtime_versions", {})
    if set(versions) != set(tasks) or any(
        not isinstance(row, dict) or not all(
            isinstance(row.get(phase), dict) and all(
                isinstance(row[phase].get(key), str) and row[phase][key]
                for key in ("python", "pytest")
            ) for phase in ("agent", "grader")
        ) for row in versions.values()
    ):
        raise V2Error("release needs original per-image Python/pytest versions")
    for task in preflight_policy()["validated_task_ids"]:
        for name in ("image_digests", "grader_image_digests", "runtime_versions"):
            if environment[name][task] != preflight["environment"][name][task]:
                raise V2Error("the five validated RC2 image/runtime pins must remain unchanged")
    _check_relative_artifacts(value.get("raw_artifacts_sha256"), root)
    builders = value.get("builder_sources", {})
    if not {"scripts/build_release_v2_images.py", "scripts/release_v2_pipeline.py"}.issubset(builders):
        raise V2Error("release runtime lacks its frozen image-builder/source provenance")
    _check_relative_artifacts(builders, root)
    _validate_runtime_receipts(value, path, tasks, preflight, root)
    if value.get("container_validated", False) is not False:
        raise V2Error("normal image construction cannot claim full-bank container validation")
    return value


def source_bindings(root):
    root = Path(root).resolve()
    paths = [*HARNESS_SOURCES, *PIPELINE_SOURCES, *EXECUTION_SOURCES]
    paths += [
        path.relative_to(root).as_posix()
        for task in BANK_62
        for path in sorted((task_root(root) / task / "tests").rglob("*.py"))
    ]
    return {name: file_hash(root / name) for name in paths}


def host_runtime_evidence(root):
    harbor = Path(root).resolve().parent / "harbor"
    packages = {
        name: importlib.metadata.version(name)
        for name in ("harbor", "litellm", "pydantic", "dirhash", "PyYAML")
    }
    return {
        "python": sys.version,
        "python_utf8_mode": sys.flags.utf8_mode,
        "packages": packages,
        "harbor_source_sha256": legacy_tree_digest(harbor / "src"),
        "harbor_lock_sha256": file_hash(harbor / "uv.lock"),
    }


def new_directory(directory, root):
    directory, root = Path(directory).resolve(), Path(root).resolve()
    if directory.parent != root / "experiments" / "smallowbench-v2":
        raise V2Error("new experiments must use experiments/smallowbench-v2/<id>")
    safe_name(directory.name)
    return directory


def load_models(path):
    value = read_json(path)
    models = value.get("models", value)
    if not isinstance(models, dict) or not models:
        raise V2Error("an explicit nonempty model matrix is required")
    for name, model in models.items():
        safe_name(name)
        if (
            not isinstance(model, dict)
            or not isinstance(model.get("runtime_id"), str)
            or not model["runtime_id"]
            or not isinstance(model.get("route"), str)
            or not model["route"]
            or not isinstance(model.get("agent_kwargs"), dict)
            or "task_id" in model["agent_kwargs"]
        ):
            raise V2Error(
                "each model needs runtime_id, pinned route and task-independent agent_kwargs"
            )
        provider = (
            model["agent_kwargs"]
            .get("llm_call_kwargs", {})
            .get("extra_body", {})
            .get("provider", {})
        )
        if (
            provider.get("order") != [model["route"]]
            or provider.get("only") != [model["route"]]
            or provider.get("allow_fallbacks") is not False
            or not model["runtime_id"].startswith("openrouter/")
        ):
            raise V2Error("model providers must be pinned without fallback")
    return models


def load_diagnostic(path, models, tasks):
    """Explicit bounded engineering design, never a partial formal leaderboard."""
    value = read_json(path)
    if (
        set(value) != {"schema_version", "kind", "selection_rationale", "conditions"}
        or value["schema_version"] != 1
        or value["kind"] != "budget_diagnostic"
        or not isinstance(value["selection_rationale"], str)
        or not value["selection_rationale"].strip()
        or not isinstance(value["conditions"], list)
        or not 2 <= len(value["conditions"]) <= 4
    ):
        raise V2Error("invalid explicit budget diagnostic design")
    names = set()
    total = 0
    for condition in value["conditions"]:
        if not isinstance(condition, dict) or set(condition) != {
            "name", "tasks", "max_turns", "agent_timeout_sec"
        }:
            raise V2Error("diagnostic conditions permit only tasks and resource budgets")
        name = safe_name(condition["name"])
        selected = condition["tasks"]
        seconds = condition["agent_timeout_sec"]
        if (
            name in names
            or not isinstance(selected, list)
            or not selected
            or any(not isinstance(task, str) or task not in tasks for task in selected)
            or len(selected) != len(set(selected))
            or type(condition["max_turns"]) is not int
            or not 1 <= condition["max_turns"] <= 40
            or isinstance(seconds, bool)
            or not isinstance(seconds, (int, float))
            or not math.isfinite(seconds)
            or not 0 < seconds <= 600
        ):
            raise V2Error("duplicate/unsafe diagnostic condition or resource budget")
        names.add(name)
        total += len(models) * len(selected)
    if total > 16:
        raise V2Error("budget diagnostic is limited to at most 16 model slots")
    return value


def frozen_schedule(models, tasks, repetitions, diagnostic=None):
    result = []
    conditions = diagnostic["conditions"] if diagnostic is not None else [None]
    for model in sorted(models):
        # Alternate paired conditions across models, rather than always running
        # the more generous budget last. Order remains fully deterministic.
        ordered = conditions if sorted(models).index(model) % 2 == 0 else conditions[::-1]
        for condition in ordered:
            selected = condition["tasks"] if condition is not None else tasks
            for task in sorted(selected):
                for repetition in range(1, repetitions + 1):
                    row = {
                        "slot_id": f"{model}/{task}/r{repetition}",
                        "model": model,
                        "task": task,
                        "repetition": repetition,
                        "sequence": len(result) + 1,
                    }
                    if condition is not None:
                        row["condition"] = condition["name"]
                        row["slot_id"] += "/" + condition["name"]
                    result.append(row)
    return result


def planned_task_units(manifest):
    return len({slot["task"] for slot in manifest["schedule"]})


def build_manifest(
    directory,
    models_path,
    preflight_path,
    *,
    repetitions=1,
    bank_path=None,
    runtime_path=None,
    root=ROOT,
    created_at=None,
    budget_usd=None,
    workers=1,
    max_infra_retries=0,
    visit_reserve_usd=3.5,
    cooldown_seconds=30,
    diagnostic_path=None,
    isolate_model_infra=False,
):
    root = Path(root).resolve()
    directory = new_directory(directory, root)
    if type(isolate_model_infra) is not bool:
        raise V2Error("model infrastructure isolation must be explicitly boolean")
    if directory.exists():
        raise V2Error(
            "prepare never reuses or overwrites an existing experiment directory"
        )
    if type(repetitions) is not int or repetitions != 1 or diagnostic_path is not None:
        raise V2Error("this formal release freezes one visit per task; no new diagnostic design")
    bank_path = Path(bank_path or task_root(root).parent / "task-bank-v2.manifest.json").resolve()
    bank, tasks = load_bank(bank_path, root=root)
    bank_binding = bound_file(bank_path)
    preflight = validate_preflight(preflight_path, tasks, bank_binding, root=root)
    runtime = validate_runtime(runtime_path, tasks, bank_binding, preflight, root=root)
    models = load_models(models_path)
    roster_path = root / "analysis" / "v2" / "models.route-ready.json"
    if (len(models) != 8 or models != load_models(roster_path)
            or file_hash(roster_path) != ORIGINAL_ROSTER_SHA256):
        raise V2Error("formal release is limited to the unchanged eight existing OpenRouter configurations")
    diagnostic = load_diagnostic(diagnostic_path, models, tasks) if diagnostic_path else None
    if diagnostic is not None and repetitions != 1:
        raise V2Error("budget diagnostic freezes exactly one visit per condition")
    if (
        type(workers) is not int
        or not 1 <= workers <= 4
        or type(max_infra_retries) is not int
        or max_infra_retries != 0
        or isinstance(visit_reserve_usd, bool)
        or not isinstance(visit_reserve_usd, (int, float))
        or not math.isfinite(visit_reserve_usd)
        or visit_reserve_usd <= 0
        or isinstance(budget_usd, bool)
        or not isinstance(budget_usd, (int, float))
        or not math.isfinite(budget_usd)
        or budget_usd <= 0
        or budget_usd > 40
        or visit_reserve_usd > budget_usd
        or isinstance(cooldown_seconds, bool)
        or not isinstance(cooldown_seconds, (int, float))
        or not math.isfinite(cooldown_seconds)
        or cooldown_seconds < 0
    ):
        raise V2Error("invalid frozen budget/worker/retry limits")
    for task, spec in tasks.items():
        text = staged_task_text(
            task_root(root) / task / "task.toml",
            runtime["environment"]["image_digests"][task],
            runtime["environment"]["grader_image_digests"][task],
        )
        spec["staged_task_config_sha256"] = hashlib.sha256(
            text.encode("utf-8")
        ).hexdigest()
        spec["staged_tree_sha256"] = staged_tree_digest(task_root(root) / task, text)
    schedule = frozen_schedule(models, tasks, repetitions, diagnostic)
    from v2_paths import validate_run_paths

    validate_run_paths(directory, {row["task"] for row in schedule}, task_root=task_root(root))
    plan = (
        "# SmallOWBench 2.0 frozen experiment\n\n"
        f"Versions: benchmark/task/grader {VERSION}; unchanged harness {HARNESS_VERSION}.\n\n"
        f"Matrix: {len(models)} explicit model configurations × 62 task units × {repetitions} repetitions.\n"
        "Review candidates are nested diagnostics, not independent task units.\n"
        "Primary endpoints: artifact and clean, each reported as equal-skill macro and task micro.\n"
        "No legacy difficulty weights, imputed infrastructure zeros, IRT or old-score comparisons.\n"
        "Model task/protocol failures are final observations, never retry triggers.\n"
        "Only evidence-classified infrastructure may receive a separately authorized bounded retry.\n"
        "This release authorizes no retry: at most 8 × 62 = 496 model trials.\n"
        "Preflight scope: five RC2 tasks (10 oracle/nop slots), not full-bank container validation.\n"
        "All 62 task recipes and immutable images are frozen separately as normal execution setup.\n"
        "Preparation and execution locking do not authorize model execution. STOP remains in force.\n"
    )
    if diagnostic is not None:
        plan = (
            "# SmallOWBench 2.0 frozen budget diagnostic\n\n"
            f"Versions: benchmark/task/grader {VERSION}; unchanged harness {HARNESS_VERSION}.\n\n"
            f"Engineering sample: {len(models)} configurations; {len(schedule)} slots.\n"
            "The full 62-task container evidence remains bound; only declared slots execute.\n"
            "No ranking, five-skill macro, representative population estimate or automatic expansion.\n"
            "Only declared agent wallclock/turn budgets change; verifier budgets and task bytes do not.\n"
            "Task/protocol/budget failures are final observations, never retry triggers.\n"
            "Preparation and locking are not execution authorization; STOP remains in force.\n\n"
            + canonical(diagnostic) + "\n"
        )
    manifest = {
        "schema_version": 2,
        "kind": "smallowbench_v2_release_experiment",
        "frozen": True,
        "experiment_id": directory.name,
        "directory": str(directory),
        "repository_root": str(root),
        "task_root": str(task_root(root)),
        "component_versions": dict(COMPONENT_VERSIONS),
        "purpose": "formal_release",
        "created_at": created_at or datetime.now(timezone.utc).isoformat(),
        "benchmark_version": VERSION,
        "task_version": VERSION,
        "harness_version": HARNESS_VERSION,
        "grader_version": VERSION,
        "scorer_version": SCORER_VERSION,
        "task_bank": {
            **bank_binding,
            "revision": bank.get("revision"),
            "document_digest": bank["manifest_sha256"],
            "hash_policy": bank.get("hash_policy"),
        },
        "preflight": bound_file(preflight_path),
        "preflight_policy": preflight_policy(),
        "runtime": bound_file(runtime_path),
        "runtime_environment_evidence": runtime["environment"],
        "roster_reference": bound_file(roster_path),
        "models_source": bound_file(models_path),
        "models": models,
        "tasks": tasks,
        "submission_schemas": SUBMISSION_SCHEMAS,
        "source_hashes": source_bindings(root),
        "host_runtime_evidence": host_runtime_evidence(root),
        "agent_import_path": AGENT_IMPORT_PATH,
        "repetitions": repetitions,
        "schedule": schedule,
        "n_planned_trials": len(schedule),
        "plan_sha256": hashlib.sha256(plan.encode("utf-8")).hexdigest(),
        "execution_authorized": False,
        "execution_policy": {
            "budget_usd": budget_usd,
            "visit_reserve_usd": visit_reserve_usd,
            "workers": workers,
            "max_infra_retries": max_infra_retries,
            "cooldown_seconds": cooldown_seconds,
            "execution_authorized": False,
        },
        "caps": {
            "budget_usd": budget_usd,
            "workers": workers,
            "max_visits_per_slot": 1 + max_infra_retries,
            "max_total_visits": len(schedule) * (1 + max_infra_retries),
            "visit_reserve_usd": visit_reserve_usd,
        },
        "retry_policy": {
            "model_task_or_protocol_failure": "never",
            "infra_only": True,
            "max_attempts": 1 + max_infra_retries,
            "requires_separate_execution_approval": True,
        },
        "scoring": SCORING_POLICY,
    }
    if diagnostic is not None:
        manifest.update(
            diagnostic=diagnostic,
            diagnostic_source=bound_file(diagnostic_path),
            purpose="engineering_budget_diagnostic",
        )
    if isolate_model_infra:
        manifest["execution_policy"]["model_infra_policy"] = "pause_model_continue_others"
    manifest["manifest_sha256"] = document_digest(manifest)
    return manifest, plan


def write_prepared(directory, manifest, plan):
    directory = Path(directory).resolve()
    if directory.exists() or str(directory) != manifest["directory"]:
        raise V2Error("prepare target must be new and match its manifest")
    directory.parent.mkdir(parents=True, exist_ok=True)
    directory.mkdir(exist_ok=False)
    # Exclusive creation; a partial preparation remains visibly stopped.
    (directory / "STOP").write_text(
        "Prepared only; model execution is not authorized.\n", encoding="utf-8"
    )
    (directory / "PLAN.md").write_text(plan, encoding="utf-8", newline="\n")
    (directory / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    stage_tasks(manifest, directory, root=Path(manifest["repository_root"]))


def validate_manifest(directory, *, root=ROOT):
    directory, root = Path(directory).resolve(), Path(root).resolve()
    new_directory(directory, root)
    manifest = read_json(directory / "manifest.json")
    if (
        manifest.get("schema_version") != 2
        or manifest.get("kind") != "smallowbench_v2_release_experiment"
        or manifest.get("frozen") is not True
        or manifest.get("manifest_sha256") != document_digest(manifest)
        or manifest.get("directory") != str(directory)
        or any(
            manifest.get(name) != VERSION
            for name in (
                "benchmark_version",
                "task_version",
                "grader_version",
            )
        )
        or manifest.get("harness_version") != HARNESS_VERSION
        or manifest.get("component_versions") != COMPONENT_VERSIONS
        or manifest.get("repository_root") != str(root)
        or manifest.get("task_root") != str(task_root(root))
        or manifest.get("purpose") != "formal_release"
        or manifest.get("preflight_policy") != preflight_policy()
        or manifest.get("agent_import_path") != AGENT_IMPORT_PATH
        or manifest.get("scorer_version") != SCORER_VERSION
    ):
        raise V2Error("invalid v2 experiment identity, versions, or digest")
    bank, tasks = load_bank(manifest["task_bank"]["path"], root=root)
    for task, spec in tasks.items():
        text = staged_task_text(
            task_root(root) / task / "task.toml",
            manifest["runtime_environment_evidence"]["image_digests"][task],
            manifest["runtime_environment_evidence"]["grader_image_digests"][task],
        )
        spec["staged_task_config_sha256"] = hashlib.sha256(
            text.encode("utf-8")
        ).hexdigest()
        spec["staged_tree_sha256"] = staged_tree_digest(task_root(root) / task, text)
    if (
        file_hash(manifest["task_bank"]["path"]) != manifest["task_bank"]["sha256"]
        or tasks != manifest["tasks"]
        or bank["manifest_sha256"] != manifest["task_bank"]["document_digest"]
        or source_bindings(root) != manifest["source_hashes"]
        or host_runtime_evidence(root) != manifest.get("host_runtime_evidence")
        or file_hash(directory / "PLAN.md") != manifest["plan_sha256"]
    ):
        raise V2Error("frozen task bank, source code, or plan drifted")
    models = load_models(manifest["models_source"]["path"])
    if (
        models != manifest["models"]
        or bound_file(manifest["models_source"]["path"]) != manifest["models_source"]
    ):
        raise V2Error("model configuration drifted")
    repetitions = manifest["repetitions"]
    if type(repetitions) is not int or repetitions != 1:
        raise V2Error("formal release freezes exactly one repetition")
    diagnostic = None
    if "diagnostic" in manifest:
        diagnostic = load_diagnostic(manifest["diagnostic_source"]["path"], models, tasks)
        if (
            diagnostic != manifest["diagnostic"]
            or bound_file(manifest["diagnostic_source"]["path"]) != manifest["diagnostic_source"]
            or manifest.get("purpose") != "engineering_budget_diagnostic"
            or repetitions != 1
        ):
            raise V2Error("diagnostic design drifted")
    elif "diagnostic_source" in manifest:
        raise V2Error("diagnostic identity cannot be partially declared")
    expected = frozen_schedule(models, tasks, repetitions, diagnostic)
    schedule = manifest["schedule"]
    if (
        schedule != expected
        or len({s["slot_id"] for s in schedule}) != len(expected)
        or manifest["n_planned_trials"] != len(expected)
        or manifest.get("submission_schemas") != SUBMISSION_SCHEMAS
        or manifest.get("scoring") != SCORING_POLICY
        or manifest.get("execution_authorized") is not False
    ):
        raise V2Error("schedule is not a complete unique frozen matrix")
    policy, caps = manifest["execution_policy"], manifest["caps"]
    budget, reserve = policy.get("budget_usd"), policy.get("visit_reserve_usd")
    workers, retries = policy.get("workers"), policy.get("max_infra_retries")
    cooldown = policy.get("cooldown_seconds")
    if (
        policy.get("execution_authorized") is not False
        or policy.get("model_infra_policy") not in (None, "pause_model_continue_others")
        or isinstance(budget, bool)
        or not isinstance(budget, (int, float))
        or not math.isfinite(budget)
        or budget <= 0
        or budget > 40
        or isinstance(reserve, bool)
        or not isinstance(reserve, (int, float))
        or not math.isfinite(reserve)
        or not 0 < reserve <= budget
        or type(workers) is not int
        or not 1 <= workers <= 4
        or type(retries) is not int
        or retries != 0
        or isinstance(cooldown, bool)
        or not isinstance(cooldown, (int, float))
        or not math.isfinite(cooldown)
        or cooldown < 0
        or caps
        != {
            "budget_usd": budget,
            "visit_reserve_usd": reserve,
            "workers": workers,
            "max_visits_per_slot": 1 + retries,
            "max_total_visits": len(schedule) * (1 + retries),
        }
        or manifest["retry_policy"]
        != {
            "model_task_or_protocol_failure": "never",
            "infra_only": True,
            "max_attempts": 1 + retries,
            "requires_separate_execution_approval": True,
        }
    ):
        raise V2Error("frozen execution policy/caps are inconsistent or unsafe")
    report = read_binding(manifest["preflight"])
    validate_preflight(
        manifest["preflight"]["path"],
        tasks,
        manifest["task_bank"],
        manifest_sha256=manifest["manifest_sha256"],
        root=root,
    )
    runtime = validate_runtime(manifest["runtime"]["path"], tasks, manifest["task_bank"], report, root=root)
    if (bound_file(manifest["runtime"]["path"]) != manifest["runtime"]
            or runtime["environment"] != manifest["runtime_environment_evidence"]
            or len(models) != 8
            or manifest["roster_reference"]["path"] != str(root / "analysis" / "v2" / "models.route-ready.json")
            or bound_file(manifest["roster_reference"]["path"]) != manifest["roster_reference"]
            or models != load_models(manifest["roster_reference"]["path"])
            or file_hash(manifest["roster_reference"]["path"]) != ORIGINAL_ROSTER_SHA256):
        raise V2Error("release runtime or original model roster evidence drifted")
    return manifest


def lock_from_validated_manifest(directory, manifest):
    """Pure lock projection after the caller's fresh full manifest validation.

    Execution callers validate all frozen source/evidence immediately before
    calling this function. Recheck the on-disk manifest identity here so a
    replacement manifest cannot be accepted between those operations.
    """
    if (
        manifest.get("manifest_sha256") != document_digest(manifest)
        or read_json(Path(directory) / "manifest.json") != manifest
    ):
        raise V2Error("validated manifest changed before execution-lock comparison")
    lock = {
        "schema_version": 2,
        "kind": "smallowbench_v2_execution_lock",
        "benchmark_version": VERSION,
        "manifest_sha256": manifest["manifest_sha256"],
        "manifest_file_sha256": file_hash(Path(directory) / "manifest.json"),
        "preflight_sha256": manifest["preflight"]["sha256"],
        "runtime_sha256": manifest["runtime"]["sha256"],
        "component_versions": manifest["component_versions"],
        "task_bank_sha256": manifest["task_bank"]["sha256"],
        "source_hashes": manifest["source_hashes"],
        "execution_authorized": False,
    }
    lock["execution_lock_sha256"] = document_digest(lock, "execution_lock_sha256")
    return lock


def build_lock(directory, *, root=ROOT):
    manifest = validate_manifest(directory, root=root)
    return lock_from_validated_manifest(directory, manifest)


def validate_lock(directory, manifest=None, *, root=ROOT):
    """Validate once, or consume a manifest freshly validated by this caller."""
    if manifest is None:
        manifest = validate_manifest(directory, root=root)
    lock = read_json(Path(directory) / "execution-lock.json")
    if lock != lock_from_validated_manifest(directory, manifest):
        raise V2Error("execution lock is stale or not a v2 preparation-only lock")
    return lock


def read_visits(directory):
    directory = Path(directory).resolve()
    rows, issues = [], []
    for path in sorted((directory / "visits").glob("*.json")):
        try:
            if path.is_symlink():
                raise V2Error("symlink visit")
            row = read_json(path)
            if not isinstance(row, dict):
                raise V2Error("visit is not an object")
            rows.append(row)
        except (OSError, ValueError) as exc:
            issues.append(
                {"kind": "invalid_visit", "path": path.name, "error": str(exc)}
            )
    return rows, issues


def active_claims(directory):
    path = Path(directory) / "claims.sqlite3"
    if not path.exists():
        return []
    with sqlite3.connect(path.resolve().as_uri() + "?mode=ro", uri=True) as connection:
        return [
            row[0]
            for row in connection.execute(
                "SELECT job_name FROM visits WHERE status IN ('running','unknown')"
            )
        ]


def status(directory, *, root=ROOT):
    manifest = validate_manifest(directory, root=root)
    visits, issues = read_visits(directory)
    active = active_claims(directory)
    states = Counter(row.get("status", "invalid") for row in visits)
    stopped = (Path(directory) / "STOP").exists()
    blockers = []
    if stopped:
        blockers.append("STOP hold exists; preparation never removes it")
    if issues or active or states.get("running") or states.get("unknown"):
        blockers.append("unresolved or unreadable execution evidence")
    try:
        lock = validate_lock(directory, manifest, root=root)
        from release_v2_executor import validate_authorization

        validate_authorization(directory, manifest, lock)
    except (OSError, ValueError, KeyError, TypeError, ImportError) as exc:
        blockers.append(str(exc))
    from release_v2_executor import model_holds

    held_models = model_holds(directory, manifest)
    runnable_models = sorted(set(manifest["models"]) - set(held_models))
    if not runnable_models:
        blockers.append("all model routes are held; no automatic retry or substitution")
    return {
        "schema_version": 2,
        "benchmark_version": VERSION,
        "manifest_sha256": manifest["manifest_sha256"],
        "planned_slots": manifest["n_planned_trials"],
        "task_units": planned_task_units(manifest),
        "repetitions": manifest["repetitions"],
        "visit_statuses": dict(states),
        "active_claims": active,
        "held_models": held_models,
        "runnable_models": runnable_models,
        "issues": issues,
        "stopped": stopped,
        "execution_ready": not blockers,
        "runtime_available_not_checked": True,
        "execution_blockers": blockers,
        "history_reused": False,
    }
