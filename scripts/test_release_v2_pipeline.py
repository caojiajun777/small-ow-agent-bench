"""Offline formal-release contracts; synthetic fixtures, no Docker/model/API."""
from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path

import pytest

import release_v2_pipeline as release


def write(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    if isinstance(value, (dict, list)):
        value = json.dumps(value, ensure_ascii=False, indent=2)
    path.write_text(value, encoding="utf-8", newline="\n")
    return path


@pytest.fixture
def workspace(tmp_path, monkeypatch):
    """Builder/strict-smoke hooks are mocked only for explicitly synthetic data."""
    import prepare_rc2_candidate
    import rc2_pipeline
    import v2_paths

    root = tmp_path / "r"
    root.mkdir()
    for name in set(release.HARNESS_SOURCES + release.PIPELINE_SOURCES + release.EXECUTION_SOURCES):
        write(root / name, "# synthetic bound source, not executed\n")
    items = []
    for task in release.BANK_62:
        source = release.task_root(root) / task
        text = (
            'schema_version = "1.4"\n[task]\nname = "unit/' + task + '"\nversion = "2.0.0-rc.2"\n'
            '[environment]\nnetwork_mode = "no-network"\n'
            '[verifier]\nenvironment_mode = "separate"\nnetwork_mode = "no-network"\n'
            '[verifier.environment]\nnetwork_mode = "no-network"\n'
        )
        write(source / "task.toml", text)
        write(source / "instruction.md", "Synthetic task fixture, not model input.\n")
        write(source / "tests/test_state.py", "# synthetic verifier source\n")
        write(source / "environment/repo/app.py", "# synthetic public repo\n")
        items.append({"id": task, "skill": task.split("-", 1)[0], "task_version": release.VERSION,
                      "task_sha256": release.task_digest(source)})
    bank = {"schema_version": 1, "task_count": 62, "task_version": release.VERSION,
            "revision": "synthetic-unit-only", "items": items}
    bank["manifest_sha256"] = hashlib.sha256(json.dumps(bank, sort_keys=True, ensure_ascii=False).encode()).hexdigest()
    bank_path = write(release.task_root(root).parent / "task-bank-v2.manifest.json", bank)
    monkeypatch.setattr(prepare_rc2_candidate, "validate_candidate", lambda candidate, root: release.read_json(candidate / bank_path.name))
    monkeypatch.setattr(rc2_pipeline, "runtime_evidence", lambda root: {"synthetic_runtime": True})
    monkeypatch.setattr(release, "host_runtime_evidence", lambda root: {"synthetic_host": True})
    monkeypatch.setattr(v2_paths, "validate_run_paths", lambda *args, **kwargs: {})
    models = {}
    for index in range(8):
        models["fixture-" + str(index)] = {
            "runtime_id": "openrouter/unit/model-" + str(index), "route": "unit/bf16",
            "agent_kwargs": {"max_turns": 20, "llm_call_kwargs": {"extra_body": {
                "provider": {"order": ["unit/bf16"], "only": ["unit/bf16"], "allow_fallbacks": False}
            }}},
        }
    models_path = write(root / "analysis/v2/models.route-ready.json", {"models": models})
    monkeypatch.setattr(release, "ORIGINAL_ROSTER_SHA256", release.file_hash(models_path))
    smoke_dir = root / "experiments/smallowbench-v2/r2smk"
    stop = write(root / "experiments/smallowbench-v2/sm8/STOP", "synthetic prior hold\n")
    stops = write(smoke_dir / "old-stops.json", {stop.relative_to(root).as_posix(): release.file_hash(stop)})
    profile = write(smoke_dir / "profile.json", {"synthetic_profile": True})
    write(smoke_dir / "run-state.json", {"status": "completed", "execution_errors": []})
    all_environment = {
        "backend": "docker", "network_mode": "no-network", "verifier_environment_mode": "separate",
        "harbor_runtime": {"synthetic_runtime": True},
        "image_digests": {task: "sha256:" + "a" * 64 for task in release.BANK_62},
        "grader_image_digests": {task: "sha256:" + "b" * 64 for task in release.BANK_62},
        "runtime_versions": {task: {role: {"python": "unit", "pytest": "unit"}
                                    for role in ("agent", "grader")} for task in release.BANK_62},
    }
    selected = release.preflight_policy()["validated_task_ids"]
    sampled_environment = copy.deepcopy(all_environment)
    for key in ("image_digests", "grader_image_digests", "runtime_versions"):
        sampled_environment[key] = {task: all_environment[key][task] for task in selected}
    rows = []
    for task in selected:
        item = next(item for item in items if item["id"] == task)
        for mode in ("oracle", "nop"):
            raw = write(smoke_dir / "original" / task / (mode + ".json"), {"synthetic_raw": True})
            rows.append({"task": task, "agent": mode, "task_sha256": item["task_sha256"],
                         "directory": str(smoke_dir), "artifacts_sha256": {raw.relative_to(root).as_posix(): release.file_hash(raw)}})
    report = {
        "schema_version": 1, "kind": "smallowbench_rc2_container_evidence",
        "component_versions": dict(release.COMPONENT_VERSIONS), "repository_root": str(root),
        "task_root": str(release.task_root(root)), "candidate_manifest_file_sha256": release.file_hash(bank_path),
        "profile_sha256": "c" * 64, "diagnostic_requested_tasks": selected,
        "diagnostic_expected_slots": 10, "diagnostic_success": True, "diagnostic_complete": True,
        "requested_scope_passed": True, "container_validated": False, "full_bank_coverage": False,
        "release_gate_passed": False, "all_passed": False, "candidate_activated": False,
        "model_execution_authorized": False, "formal_ranking_eligible": False,
        "model_calls": 0, "cloud_sandbox_creates": 0, "rows": rows, "environment": sampled_environment,
        "run_safety_bindings": {path.relative_to(root).as_posix(): release.file_hash(path) for path in (stops, profile)},
        "source_hashes": {"scripts/rc2_pipeline.py": release.file_hash(root / "scripts/rc2_pipeline.py")},
    }
    report["report_sha256"] = release.document_digest(report, "report_sha256")
    preflight = write(smoke_dir / "preflight-rc2.json", report)
    strict_calls = []
    def strict(path):
        strict_calls.append(str(path))
        return release.read_json(path)
    monkeypatch.setattr(release, "_strict_smoke_validation", strict)
    from validate_rc2_containers import context_digest
    image_directory = root / "experiments/smallowbench-v2/im2"
    image_directory.mkdir(parents=True)
    builder_sources = {name: release.file_hash(root / name) for name in
                       ("scripts/build_release_v2_images.py", "scripts/release_v2_pipeline.py")}
    write(image_directory / "builder-sources.json", builder_sources)
    write(image_directory / "core-profile.json", release.read_json(profile))
    write(image_directory / "old-stops.json", release.read_json(stops))
    label = hashlib.sha256(str(image_directory).encode("utf-8")).hexdigest()
    label_key = "smallowbench.rc2.smoke"
    probe_names, old_version_paths = set(), []
    for item in items:
        task = item["id"]
        pinned = task in selected
        local = image_directory / "images" / task
        for role, key in (("agent", "image_digests"), ("grader", "grader_image_digests")):
            image = all_environment[key][task]
            write(local / (role + ".iid"), image + "\n")
            write(local / (role + "-image-inspect.json"), {
                "kind": "immutable_local_image_identity", "requested_image": image,
                "actual_image": image, "returncode": 0, "exact_match": True,
            })
            write(local / (role + "-runtime.json"), all_environment["runtime_versions"][task][role])
            if pinned:
                old_version_paths.append(write(smoke_dir / "images" / task / (role + "-runtime.json"),
                                               all_environment["runtime_versions"][task][role]))
            else:
                name = "r2p-" + label[:10] + "-" + task[:25] + "-" + role
                probe_names.add(name)
                command = ["docker", "run", "--rm", "--name", name, "--label", label_key + "=" + label,
                           "--network", "none", "--read-only", "--cap-drop", "ALL", "--security-opt", "no-new-privileges",
                           "--pids-limit", "64", "--cpus", "1", "--memory", "2g", image, "python3", "-c",
                           "import json,sys,pytest;print(json.dumps({'python':sys.version,'pytest':pytest.__version__}))"]
                write(local / (role + "-runtime-launch.json"), {
                    "image": image, "container_name": name, "label_key": label_key,
                    "label_value": label, "network_mode": "none", "command": command,
                })
        if pinned:
            old = [smoke_dir / "images" / task / (role + "-runtime.json") for role in ("agent", "grader")]
            write(local / "pinned-reuse.json", {
                "kind": "exact_existing_rc2_image_runtime_reuse", "task": task,
                "source_report": preflight.relative_to(root).as_posix(), "source_report_sha256": release.file_hash(preflight),
                "source_artifacts_sha256": {entry.relative_to(root).as_posix(): release.file_hash(entry) for entry in old},
            })
        write(local / "receipt.json", {
            "kind": "dependency_image_initialization_receipt", "task": task,
            "task_sha256": item["task_sha256"],
            "context_sha256": {role: context_digest(release.task_root(root) / task / ("environment" if role == "agent" else "tests"))
                               for role in ("agent", "grader")},
            "agent_image": all_environment["image_digests"][task],
            "grader_image": all_environment["grader_image_digests"][task],
            "runtime_versions": all_environment["runtime_versions"][task],
            "reused_existing_rc2_pins": pinned,
            "version_probe_kind": "existing_version_receipt_reuse" if pinned else "dependency_version_only",
        })
    cleanup = {
        "kind": "exact_version_probe_inventory_check", "label_key": label_key, "label_value": label,
        "checked_probe_names": sorted(probe_names), "remaining_containers": [], "zero_residual": True,
        "missing_preexisting_container_ids": [], "preexisting_containers_preserved": True,
    }
    all_environment.update(version_probe_label={"key": label_key, "value": label, "kind": "dependency_version_only"},
                           cleanup_check=cleanup)
    write(image_directory / "inventory-check.json", cleanup)
    for phase in ("before", "after"):
        write(image_directory / ("containers-" + phase + ".json"), {"containers": []})
    write(image_directory / "run-state.json", {
        "kind": "smallowbench_v2_image_initialization", "status": "completed",
        "completed_tasks": sorted(release.BANK_62), "expected_tasks": 62,
        "execution_errors": [], "historical_stops_preserved": True,
        "automatic_retries": 0, "model_calls": 0, "task_evaluation_runs": 0,
    })
    raw_files = [entry for entry in image_directory.rglob("*") if entry.is_file()]
    raw_files += old_version_paths + [preflight, profile]
    runtime = {
        "schema_version": 1, "kind": "smallowbench_v2_release_runtime",
        "task_root": str(release.task_root(root)), "task_bank_manifest_sha256": release.file_hash(bank_path),
        "component_versions": dict(release.COMPONENT_VERSIONS),
        "task_sha256": {item["id"]: item["task_sha256"] for item in items},
        "environment": all_environment, "container_validated": False,
        "raw_artifacts_sha256": {entry.relative_to(root).as_posix(): release.file_hash(entry) for entry in raw_files},
        "builder_sources": builder_sources, "model_calls": 0, "automatic_retries": 0, "task_evaluation_runs": 0,
    }
    runtime_path = write(image_directory / "runtime.json", runtime)
    return {"root": root, "bank": bank_path, "models": models_path, "preflight": preflight,
            "runtime": runtime_path, "directory": root / "experiments/smallowbench-v2/f2",
            "stop": stop, "strict_calls": strict_calls}


def make_manifest(workspace, **kwargs):
    return release.build_manifest(workspace["directory"], workspace["models"], workspace["preflight"],
        root=workspace["root"], runtime_path=workspace["runtime"], budget_usd=40,
        workers=2, visit_reserve_usd=1, created_at="2026-10-28T00:00:00+00:00", **kwargs)


def prepare(workspace):
    manifest, plan = make_manifest(workspace)
    release.write_prepared(workspace["directory"], manifest, plan)
    lock = release.build_lock(workspace["directory"], root=workspace["root"])
    write(workspace["directory"] / "execution-lock.json", lock)
    return manifest, lock


def test_formal_matrix_reuses_split_versions_and_only_existing_smoke(workspace):
    manifest, plan = make_manifest(workspace)
    assert manifest["kind"] == "smallowbench_v2_release_experiment"
    assert manifest["purpose"] == "formal_release"
    assert manifest["component_versions"] == release.COMPONENT_VERSIONS
    assert manifest["harness_version"] == "2.0.0-rc.1"
    assert manifest["task_version"] == manifest["grader_version"] == "2.0.0-rc.2"
    assert len(manifest["schedule"]) == len({row["slot_id"] for row in manifest["schedule"]}) == 496
    assert {row["task"] for row in manifest["schedule"]} == set(release.BANK_62)
    assert manifest["caps"]["max_total_visits"] == 496
    assert manifest["preflight_policy"]["full_bank_container_validated"] is False
    assert manifest["preflight_policy"]["additional_preflight_required"] is False
    assert "not full-bank container validation" in plan
    assert not workspace["directory"].exists()


def test_prepare_lock_stage_and_job_preserve_safety_without_model_calls(workspace):
    manifest, lock = prepare(workspace)
    assert (workspace["directory"] / "STOP").exists()
    assert release.validate_manifest(workspace["directory"], root=workspace["root"]) == manifest
    assert release.validate_lock(workspace["directory"], root=workspace["root"]) == lock
    assert lock["runtime_sha256"] == manifest["runtime"]["sha256"]
    assert lock["execution_authorized"] is False
    slot = manifest["schedule"][0]
    job = release.job_config(manifest, slot, "visit-unit", workspace["directory"])
    assert job["agents"][0]["import_path"] == "agents.compact_shell_v2:CompactShellV2Agent"
    assert job["agents"][0]["model_name"].startswith("openrouter/")
    assert job["environment"]["delete"] is False
    assert job["retry"] == {"max_retries": 0}
    assert not (workspace["root"] / "tasks").exists()
    with pytest.raises(ValueError, match="new and match"):
        release.write_prepared(workspace["directory"], manifest, "do not overwrite")


@pytest.mark.parametrize("fault", ["task", "source", "models", "runtime", "plan"])
def test_frozen_release_drift_is_rejected(workspace, fault):
    prepare(workspace)
    path = {
        "task": release.task_root(workspace["root"]) / release.BANK_62[0] / "instruction.md",
        "source": workspace["root"] / "scripts/run_release_v2.py",
        "models": workspace["models"], "runtime": workspace["runtime"],
        "plan": workspace["directory"] / "PLAN.md",
    }[fault]
    if fault in {"models", "runtime"}:
        value = release.read_json(path)
        value["synthetic_changed"] = True
        write(path, value)
    else:
        write(path, path.read_text(encoding="utf-8") + "\n# changed fixture\n")
    with pytest.raises(ValueError):
        release.validate_manifest(workspace["directory"], root=workspace["root"])


@pytest.mark.parametrize("fault", ["missing_image", "five_pin_changed", "version", "full_gate", "raw_bytes", "builder"])
def test_runtime_cannot_expand_sample_claims_or_lose_frozen_identity(workspace, fault):
    value = release.read_json(workspace["runtime"])
    if fault == "missing_image":
        value["environment"]["image_digests"].pop(release.BANK_62[-1])
    elif fault == "five_pin_changed":
        value["environment"]["image_digests"]["loc-bind-host"] = "sha256:" + "d" * 64
    elif fault == "version":
        value["component_versions"]["harness"] = release.VERSION
    elif fault == "full_gate":
        value["container_validated"] = True
    elif fault == "builder":
        value["builder_sources"] = {}
    else:
        relative = next(iter(value["raw_artifacts_sha256"]))
        write(workspace["root"] / relative, "changed raw build fixture")
    write(workspace["runtime"], value)
    with pytest.raises(ValueError):
        make_manifest(workspace)


@pytest.mark.parametrize("fault", ["non_sample_image", "non_sample_version", "receipt_task", "receipt_context", "iid", "image_inspect", "unsafe_probe", "closed_state", "inventory"])
def test_runtime_reconstructs_every_non_sample_task_and_safe_closeout(workspace, fault):
    value = release.read_json(workspace["runtime"])
    task = next(task for task in release.BANK_62 if task not in release.preflight_policy()["validated_task_ids"])
    local = workspace["runtime"].parent / "images" / task
    modified = None
    if fault == "non_sample_image":
        value["environment"]["image_digests"][task] = "sha256:" + "d" * 64
    elif fault == "non_sample_version":
        value["environment"]["runtime_versions"][task]["agent"]["python"] = "unobserved version"
    elif fault in {"receipt_task", "receipt_context"}:
        modified = local / "receipt.json"
        receipt = release.read_json(modified)
        if fault == "receipt_task":
            receipt["task"] = "other-task"
        else:
            receipt["context_sha256"]["agent"] = "0" * 64
        write(modified, receipt)
    elif fault == "iid":
        modified = write(local / "agent.iid", "sha256:" + "d" * 64)
    elif fault == "image_inspect":
        modified = local / "agent-image-inspect.json"
        inspect = release.read_json(modified)
        inspect["actual_image"] = "sha256:" + "d" * 64
        write(modified, inspect)
    elif fault == "unsafe_probe":
        modified = local / "agent-runtime-launch.json"
        launch = release.read_json(modified)
        launch["command"][-1] = "import os; print(os.environ)"
        write(modified, launch)
    elif fault == "closed_state":
        modified = workspace["runtime"].parent / "run-state.json"
        state = release.read_json(modified)
        state["status"] = "failed"
        write(modified, state)
    else:
        modified = workspace["runtime"].parent / "containers-after.json"
        write(modified, {"containers": [{"ID": "d" * 64, "Labels": "smallowbench.rc2.smoke=" + value["environment"]["version_probe_label"]["value"], "Names": "owned-residual"}]})
    if modified is not None:
        value["raw_artifacts_sha256"][modified.relative_to(workspace["root"]).as_posix()] = release.file_hash(modified)
    write(workspace["runtime"], value)
    with pytest.raises(ValueError):
        make_manifest(workspace)


def test_strict_smoke_cache_never_skips_raw_or_stop_revalidation(workspace):
    make_manifest(workspace)
    make_manifest(workspace)
    assert len(workspace["strict_calls"]) == 1
    write(workspace["stop"], "changed original STOP")
    with pytest.raises(ValueError, match="drifted"):
        make_manifest(workspace)


def test_strict_cache_observes_added_files_without_changing_any_old_hash(workspace, monkeypatch):
    make_manifest(workspace)
    added = workspace["preflight"].parent / "original" / "unexpected-artifact.py"
    def reject_added(path):
        if added.exists():
            raise ValueError("synthetic strict verifier rejects added artifact")
        return release.read_json(path)
    monkeypatch.setattr(release, "_strict_smoke_validation", reject_added)
    write(added, "untracked source file")
    with pytest.raises(ValueError, match="added artifact"):
        make_manifest(workspace)


def test_strict_smoke_cache_refuses_changed_original_raw_bytes(workspace):
    make_manifest(workspace)
    report = release.read_json(workspace["preflight"])
    relative = next(iter(report["rows"][0]["artifacts_sha256"]))
    write(workspace["root"] / relative, "modified original evidence")
    with pytest.raises(ValueError, match="drifted"):
        make_manifest(workspace)


@pytest.mark.parametrize("fault", ["old_report", "fake_full_gate", "unclosed", "wrong_task"])
def test_only_version_bound_completed_sampled_evidence_is_accepted(workspace, fault):
    report = release.read_json(workspace["preflight"])
    if fault == "old_report":
        report["kind"] = "smallowbench_v2_container_preflight"
    elif fault == "fake_full_gate":
        report["full_bank_coverage"] = True
    elif fault == "wrong_task":
        report["rows"][0]["task_sha256"] = "0" * 64
    else:
        write(workspace["preflight"].parent / "run-state.json", {"status": "running", "execution_errors": []})
    report["report_sha256"] = release.document_digest(report, "report_sha256")
    write(workspace["preflight"], report)
    with pytest.raises(ValueError):
        make_manifest(workspace)


@pytest.mark.parametrize("fault", ["non_openrouter", "fallback", "unpin", "fewer_models"])
def test_release_cannot_silently_change_existing_roster_or_routes(workspace, fault):
    value = release.read_json(workspace["models"])
    model = next(iter(value["models"].values()))
    if fault == "non_openrouter":
        model["runtime_id"] = "dashscope/unit"
    elif fault == "fallback":
        model["agent_kwargs"]["llm_call_kwargs"]["extra_body"]["provider"]["allow_fallbacks"] = True
    elif fault == "unpin":
        model["agent_kwargs"]["llm_call_kwargs"]["extra_body"]["provider"]["only"] = []
    else:
        value["models"].pop(next(iter(value["models"])))
    write(workspace["models"], value)
    with pytest.raises(ValueError):
        make_manifest(workspace)


def test_no_new_diagnostic_repetitions_or_extra_attempts(workspace):
    with pytest.raises(ValueError, match="one visit"):
        make_manifest(workspace, repetitions=3)
    with pytest.raises(ValueError, match="one visit"):
        make_manifest(workspace, diagnostic_path=workspace["root"] / "unused.json")
    with pytest.raises(ValueError, match="budget/worker/retry"):
        make_manifest(workspace, max_infra_retries=1)


def test_preflight_and_lock_metadata_tampering_cannot_enable_execution(workspace):
    manifest, lock = prepare(workspace)
    value = copy.deepcopy(manifest)
    value["harness_version"] = release.VERSION
    value["manifest_sha256"] = release.document_digest(value)
    write(workspace["directory"] / "manifest.json", value)
    with pytest.raises(ValueError, match="versions"):
        release.validate_manifest(workspace["directory"], root=workspace["root"])
    write(workspace["directory"] / "manifest.json", manifest)
    value = copy.deepcopy(lock)
    value["execution_authorized"] = True
    value["execution_lock_sha256"] = release.document_digest(value, "execution_lock_sha256")
    write(workspace["directory"] / "execution-lock.json", value)
    with pytest.raises(ValueError, match="stale"):
        release.validate_lock(workspace["directory"], root=workspace["root"])


@pytest.mark.parametrize("fault", ["agent", "reference_path"])
def test_formal_validator_fixes_agent_class_and_original_roster_anchor(workspace, fault):
    manifest, _ = prepare(workspace)
    value = copy.deepcopy(manifest)
    if fault == "agent":
        value["agent_import_path"] = "arbitrary.module:UnboundAgent"
    else:
        alternate = write(workspace["root"] / "alternate-models.json", release.read_json(workspace["models"]))
        value["roster_reference"] = release.bound_file(alternate)
    value["manifest_sha256"] = release.document_digest(value)
    write(workspace["directory"] / "manifest.json", value)
    with pytest.raises(ValueError):
        release.validate_manifest(workspace["directory"], root=workspace["root"])


def test_original_modules_are_not_monkeypatched(workspace):
    import v2_pipeline
    import rc2_pipeline
    old = (v2_pipeline.VERSION, v2_pipeline.ROOT, rc2_pipeline.COMPONENT_VERSIONS.copy())
    make_manifest(workspace)
    assert old == (v2_pipeline.VERSION, v2_pipeline.ROOT, rc2_pipeline.COMPONENT_VERSIONS.copy())
