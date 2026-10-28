"""Synthetic offline RC2 profile/raw-evidence contracts; no Docker or model calls."""
from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path
import shutil

import pytest

import rc2_pipeline as pipe


def write(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    if isinstance(value, (dict, list)):
        value = json.dumps(value, ensure_ascii=False, indent=2)
    path.write_text(value, encoding="utf-8", newline="\n")
    return path


@pytest.fixture
def workspace(tmp_path, monkeypatch):
    """The mocked candidate/runtime guards are explicit unit-only boundaries."""
    root = tmp_path / "r"
    root.mkdir()
    for name in set(pipe.HARNESS_SOURCES + pipe.PIPELINE_SOURCES + pipe.EXECUTION_SOURCES + pipe.NEW_SOURCES):
        write(root / name, "# synthetic offline source fixture\n")
    task_root = root / "task-banks" / "rc2" / "tasks"
    items = []
    for task in pipe.BANK_62:
        source = task_root / task
        if task in pipe.SMOKE_TASKS:
            shutil.copytree(pipe.ROOT / "task-banks" / "rc2" / "tasks" / task, source,
                            ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
        else:
            write(source / "task.toml", '[task]\nname = "unit/' + task + '"\nversion = "2.0.0-rc.2"\n')
        items.append({"id": task, "skill": task.split("-", 1)[0], "task_sha256": pipe.task_digest(source)})
    bank = {"items": items, "manifest_sha256": "a" * 64}
    manifest = write(task_root.parent / "task-bank-v2.manifest.json", bank)
    monkeypatch.setattr(pipe, "validate_candidate", lambda candidate, root: pipe.read_json(candidate / manifest.name))
    monkeypatch.setattr(pipe, "runtime_evidence", lambda root: {"synthetic_unit_runtime": True})
    profile = pipe.load_profile(root)
    directory = root / "experiments" / "smallowbench-v2" / "r2"
    directory.mkdir(parents=True)
    return root, directory, profile


def raw_fixture(workspace, task="loc-bind-host", mode="oracle", unique=1):
    root, directory, profile = workspace
    images = ("sha256:" + "1" * 64, "sha256:" + "2" * 64)
    staged = directory / "staged-tasks" / task
    if not staged.exists():
        pipe.stage_task(profile, task, directory, *images)
    config = pipe.make_config(profile, task, mode, staged, directory)
    write(directory / "configs" / (config["job_name"] + ".json"), config)
    job = directory / "jobs" / config["job_name"]
    write(job / "config.json", pipe.normalized_job_config(config))
    trial = job / (task + "__unit" + str(unique))
    correct = int(mode == "oracle")
    name = {"loc": "answer.txt", "edit": "repo/app.py", "testgen": "repo/tests/test_unit.py",
            "repro": "repro.py", "review": "review.json"}[task.split("-", 1)[0]]
    payload = "synthetic submitted bytes\n"
    manifest = []
    if correct:
        artifact = write(trial / "artifacts" / "submission" / name, payload)
        manifest = [{"path": name, "role": "submission", "sha256": pipe.file_hash(artifact),
                     "size_bytes": artifact.stat().st_size}]
    else:
        (trial / "artifacts" / "submission").mkdir(parents=True)
    write(trial / "artifacts" / "manifest.json", [])
    verdict = {
        "schema_version": 2, "task_id": task, "task_version": "2.0.0-rc.2", "grader_version": "2.0.0-rc.2",
        "status": "pass" if correct else "fail", "artifact_correct": correct,
        "submission_manifest": manifest, "submission_digest": pipe.digest(manifest),
        "elapsed_sec": 0.1, "failure_category": None if correct else "missing_submission",
        "checks": {"controller": {"temporary_storage": "native_private", "temporary_parent": "/tmp"}}, "evidence": [],
        "runtime": {"python": "synthetic", "pytest": "synthetic"},
    }
    write(trial / "verifier" / "verdict.json", verdict)
    write(trial / "verifier" / "reward.txt", str(correct))
    resolved = pipe.normalized_job_config(config)
    raw = {
        "task_name": "small-ow-agent-bench/" + task, "trial_name": trial.name,
        "task_checksum": pipe.harbor_task_checksum(staged), "exception_info": None,
        "verifier_environment_mode": "separate", "verifier_result": {"rewards": {"reward": float(correct)}},
        "config": {"trial_name": trial.name, "trials_dir": str(job), "task": resolved["tasks"][0],
                   "agent": resolved["agents"][0], "environment": resolved["environment"], "timeout_multiplier": 1.0,
                   "verifier": resolved["verifier"], "install_only": False, "source_trial": None},
    }
    write(trial / "result.json", raw)
    for offset, suffix, image in ((0, "__env", images[0]), (1, "__verifier__trial", images[1])):
        proof = {
            "schema_version": 1, "isolation": "docker-network-none", "network_mode": "none", "verified": True,
            "session_id": trial.name + suffix, "container_id": hashlib.sha256(str(unique * 2 + offset).encode()).hexdigest(),
            "image": image, "image_id": image,
        }
        write(trial / "environment" / ("static-network-" + suffix + ".json"), proof)
    row = pipe.inspect_trial(profile, task, mode, directory, *images)
    return row, trial, images


def environment(profile, tasks, images, rows):
    root = Path(profile["repository_root"])
    directory = root / "experiments" / "smallowbench-v2" / "r2"
    label = hashlib.sha256(str(directory.resolve()).encode("utf-8")).hexdigest()
    write(directory / "profile.json", profile)
    stop = write(root / "experiments" / "smallowbench-v2" / "old" / "STOP", "synthetic stopped experiment")
    write(directory / "old-stops.json", {stop.relative_to(root).as_posix(): pipe.file_hash(stop)})
    for phase in ("before", "after"):
        write(directory / ("containers-" + phase + ".json"), {"containers": []})
    for task in tasks:
        for phase in ("agent", "grader"):
            write(directory / "images" / task / (phase + "-runtime.json"),
                  {"python": "synthetic", "pytest": "synthetic"})
            image = images[0 if phase == "agent" else 1]
            name = "r2p-" + label[:10] + "-" + task[:25] + "-" + phase
            command = [
                "docker", "run", "--rm", "--name", name, "--label", pipe.PROBE_LABEL_KEY + "=" + label,
                "--network", "none", "--read-only", "--cap-drop", "ALL", "--security-opt", "no-new-privileges",
                "--pids-limit", "64", "--cpus", "1", "--memory", "2g", image, "python3", "-c", pipe.VERSION_PROBE_CODE,
            ]
            write(directory / "images" / task / (phase + "-runtime-launch.json"), {
                "image": image, "container_name": name, "label_key": pipe.PROBE_LABEL_KEY,
                "label_value": label, "network_mode": "none", "command": command,
            })
    write(directory / "run-state.json", {"status": "completed", "execution_errors": []})
    return {
        "backend": "docker", "network_mode": "no-network", "verifier_environment_mode": "separate",
        "harbor_runtime": profile["harbor_runtime"],
        "image_digests": {task: images[0] for task in tasks},
        "grader_image_digests": {task: images[1] for task in tasks},
        "runtime_versions": {task: {phase: {"python": "synthetic", "pytest": "synthetic"}
                                     for phase in ("agent", "grader")} for task in tasks},
        "execution_errors": [], "container_inventory_before": [], "container_inventory_after": [],
        "version_probe_label": {"key": pipe.PROBE_LABEL_KEY, "value": label},
        "cleanup_check": {"zero_residual": True, "remaining_containers": [],
                          "checked_sessions": sorted(proof["session_id"].lower()
                              for row in rows for proof in row["static_network_isolation_evidence"])},
    }


def test_profile_explicit_component_split_and_task_root(workspace):
    root, _, profile = workspace
    assert pipe.validate_profile(profile) == profile
    assert profile["task_root"] == str(root / "task-banks" / "rc2" / "tasks")
    assert profile["component_versions"] == pipe.COMPONENT_VERSIONS
    assert len(profile["task_specs"]) == 62
    assert not profile["model_execution_enabled"]


@pytest.mark.parametrize("field", ["task_root", "component_versions", "source_hashes", "harbor_runtime"])
def test_profile_tampering_even_with_new_digest_is_rejected(workspace, field):
    _, _, original = workspace
    profile = copy.deepcopy(original)
    profile[field] = {} if field != "task_root" else str(pipe.ROOT / "tasks")
    profile["profile_sha256"] = pipe.digest({k: v for k, v in profile.items() if k != "profile_sha256"})
    with pytest.raises(ValueError, match="drifted"):
        pipe.validate_profile(profile)


@pytest.mark.parametrize("which", ["source", "task", "bank"])
def test_profile_detects_bound_source_candidate_and_manifest_drift(workspace, which):
    root, _, profile = workspace
    path = {
        "source": root / "scripts/validate_rc2_containers.py",
        "task": Path(profile["task_root"]) / "loc-bind-host" / "instruction.md",
        "bank": Path(profile["bank_manifest"]["path"]),
    }[which]
    if which == "bank":
        bank = pipe.read_json(path)
        bank["changed_unit_fixture"] = True
        write(path, bank)
    else:
        write(path, path.read_text(encoding="utf-8") + "\n# changed unit fixture\n")
    with pytest.raises(ValueError):
        pipe.validate_profile(profile)


def test_staging_is_rc2_exact_and_never_overwrites(workspace):
    root, directory, profile = workspace
    task = "loc-bind-host"
    source = Path(profile["task_root"]) / task
    before = pipe.legacy_tree_digest(source)
    staged = pipe.stage_task(profile, task, directory, "sha256:" + "a" * 64, "sha256:" + "b" * 64)
    data = tomllib_read(staged / "task.toml")
    assert data["task"]["version"] == "2.0.0-rc.2"
    assert data["environment"]["docker_image"] == "sha256:" + "a" * 64
    assert pipe.legacy_tree_digest(source) == before
    assert not (root / "tasks" / task).exists()
    with pytest.raises(ValueError, match="never overwrite"):
        pipe.stage_task(profile, task, directory, "sha256:" + "a" * 64, "sha256:" + "b" * 64)


def tomllib_read(path):
    import tomllib
    return tomllib.loads(path.read_text(encoding="utf-8"))


@pytest.mark.parametrize("mode", ["oracle", "nop"])
def test_raw_inspection_recomputes_versions_bytes_and_networks(workspace, mode):
    row, _, _ = raw_fixture(workspace, mode=mode)
    assert row["expected_result_matched"] and row["infrastructure_ok"]
    assert row["component_versions"] == pipe.COMPONENT_VERSIONS
    assert row["native_temporary_storage_validated"]
    assert row["transfer_consistency"] == "complete_bidirectional_file_set_bytes_match"
    assert len(row["static_network_isolation_evidence"]) == 2


@pytest.mark.parametrize("fault", ["task_version", "grader_version", "tmp", "reward", "bytes", "proof", "agent", "staged",
                                   "verifier_budget", "install_only", "source_trial", "trials_dir", "task_git"])
def test_raw_evidence_faults_are_fail_closed(workspace, fault):
    row, trial, images = raw_fixture(workspace)
    if fault in {"task_version", "grader_version", "tmp"}:
        path = trial / "verifier/verdict.json"
        value = pipe.read_json(path)
        if fault == "tmp":
            value["checks"]["controller"]["temporary_parent"] = "/logs/verifier"
        else:
            value[fault] = "2.0.0-rc.1"
        write(path, value)
    elif fault == "reward":
        write(trial / "verifier/reward.txt", "0")
    elif fault == "bytes":
        write(trial / "artifacts/submission/answer.txt", "different bytes")
    elif fault == "proof":
        (trial / "environment/static-network-__env.json").unlink()
    elif fault in {"agent", "verifier_budget", "install_only", "source_trial", "trials_dir", "task_git"}:
        value = pipe.read_json(trial / "result.json")
        if fault == "agent":
            value["config"]["agent"]["name"] = "compact-shell"
        elif fault == "verifier_budget":
            value["config"]["verifier"]["override_timeout_sec"] = 999
        elif fault == "task_git":
            value["config"]["task"]["git_commit_id"] = "different-commit"
        else:
            value["config"][fault] = {"install_only": True, "source_trial": "other-trial", "trials_dir": "other-job"}[fault]
        write(trial / "result.json", value)
    else:
        write(workspace[1] / "staged-tasks/loc-bind-host/instruction.md", "different staged task")
    with pytest.raises(ValueError):
        pipe.inspect_trial(workspace[2], row["task"], row["agent"], workspace[1], *images)


def test_container_ids_cannot_be_reused_between_observations(workspace):
    row, _, images = raw_fixture(workspace)
    state = {}
    pipe.inspect_trial(workspace[2], row["task"], row["agent"], workspace[1], *images, state)
    with pytest.raises(ValueError, match="reused"):
        pipe.inspect_trial(workspace[2], row["task"], row["agent"], workspace[1], *images, state)


def test_requested_scope_success_does_not_pass_full_release_gate(workspace):
    rows = []
    for index, task in enumerate(pipe.SMOKE_TASKS):
        for offset, mode in enumerate(("oracle", "nop")):
            row, _, images = raw_fixture(workspace, task, mode, index * 2 + offset + 1)
            rows.append(row)
    profile = workspace[2]
    env = environment(profile, pipe.SMOKE_TASKS, images, rows)
    report = pipe.summarize(profile, pipe.SMOKE_TASKS, rows, env)
    assert report["diagnostic_expected_slots"] == 10
    assert report["diagnostic_complete"] and report["diagnostic_success"]
    assert report["issues"] == []
    for key in ("container_validated", "all_passed", "release_gate_passed", "full_bank_coverage",
                "candidate_activated", "model_execution_authorized", "formal_ranking_eligible"):
        assert report[key] is False
    assert pipe.validate_smoke_report(report, profile, tasks=pipe.SMOKE_TASKS) == report
    for modified in (rows[:-1], rows[:-1] + [rows[0]]):
        assert not pipe.summarize(profile, pipe.SMOKE_TASKS, modified, env)["diagnostic_success"]
    bad = copy.deepcopy(report)
    bad["container_validated"] = True
    bad["report_sha256"] = pipe.digest({k: v for k, v in bad.items() if k != "report_sha256"})
    with pytest.raises(ValueError, match="recomputed"):
        pipe.validate_smoke_report(bad, profile)
    for safety_error in ("execution_errors", "cleanup_check", "runtime_versions", "version_probe_label"):
        altered = copy.deepcopy(env)
        if safety_error == "execution_errors":
            altered[safety_error] = [{"type": "unit failure"}]
        elif safety_error == "cleanup_check":
            altered[safety_error]["zero_residual"] = False
        elif safety_error == "runtime_versions":
            altered["runtime_versions"]["loc-bind-host"]["agent"]["python"] = "fabricated runtime"
        else:
            altered["version_probe_label"]["value"] = "0" * 64
        failed = pipe.summarize(profile, pipe.SMOKE_TASKS, rows, altered)
        assert not failed["diagnostic_success"]
    residual = {"ID": "e" * 64, "Labels": pipe.PROBE_LABEL_KEY + "=" + env["version_probe_label"]["value"]}
    altered = copy.deepcopy(env)
    altered["container_inventory_after"] = [residual]
    write(workspace[1] / "containers-after.json", {"containers": [residual]})
    failed = pipe.summarize(profile, pipe.SMOKE_TASKS, rows, altered)
    assert not failed["diagnostic_success"]
    assert any("did not close cleanly" in issue.get("detail", "") for issue in failed["issues"])
    write(workspace[1] / "containers-after.json", {"containers": []})
    write(workspace[1] / "run-state.json", {"status": "stopped", "execution_errors": []})
    with pytest.raises(ValueError, match="completion state"):
        pipe.validate_smoke_report(report, profile)
    write(workspace[1] / "run-state.json", {"status": "completed", "execution_errors": []})
    write(workspace[1] / "images/loc-bind-host/agent-runtime.json", {"python": "changed", "pytest": "synthetic"})
    with pytest.raises(ValueError, match="recomputed"):
        pipe.validate_smoke_report(report, profile)


def test_forged_green_cached_row_is_not_evidence(workspace):
    row, trial, images = raw_fixture(workspace)
    env = environment(workspace[2], pipe.SMOKE_TASKS, images, [row])
    write(trial / "artifacts/submission/answer.txt", "changed after inspection")
    report = pipe.summarize(workspace[2], pipe.SMOKE_TASKS, [row], env)
    assert not report["diagnostic_success"] and report["issues"]


def test_old_report_rejected_and_model_entrypoint_disabled(workspace):
    with pytest.raises(ValueError, match="not a valid"):
        pipe.validate_smoke_report({"schema_version": 2, "kind": "smallowbench_v2_container_preflight"})
    for mode in ("compact-shell", "qwen", "api"):
        with pytest.raises(ValueError, match="disabled"):
            pipe.make_config(workspace[2], "loc-bind-host", mode, workspace[1], workspace[1])
    with pytest.raises(ValueError, match="disabled"):
        pipe.execute_models()
    with pytest.raises(ValueError, match="fixed five-task"):
        pipe.summarize(workspace[2], pipe.BANK_62, [], {})


def test_no_module_global_or_original_file_changes(workspace):
    import v2_pipeline as old_pipeline
    import validate_v2_containers as old_gate
    before = old_pipeline.ROOT, old_pipeline.VERSION, old_gate.ROOT, old_gate.VERSION
    pipe.load_profile(workspace[0])
    assert before == (old_pipeline.ROOT, old_pipeline.VERSION, old_gate.ROOT, old_gate.VERSION)
