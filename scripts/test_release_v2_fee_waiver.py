"""Offline contracts for a monetary-only continuation of the frozen run."""
from __future__ import annotations

import ast
from contextlib import nullcontext
import functools
import hashlib
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

import analyze_release_v2_fee_waiver as analysis
import release_v2_fee_waiver_executor as executor
import release_v2_pipeline as pipeline
import validate_v2_containers as containers


def save(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value), encoding="utf-8")


def fixture(tmp_path):
    root, directory = tmp_path / "source", tmp_path / "p2"
    for name in executor.FEE_WAIVER_IMPLEMENTATION:
        source = root / name
        source.parent.mkdir(parents=True, exist_ok=True)
        source.write_text("bound source: " + name, encoding="utf-8")
    (root / "scripts/analyze_release_v2.py").write_text("frozen analysis fixture", encoding="utf-8")
    manifest = {
        "manifest_sha256":"a" * 64,
        "caps":{"budget_usd":40,"visit_reserve_usd":3.5,"workers":4,
                "max_visits_per_slot":1,"max_total_visits":496},
        "schedule":[{"slot_id":f"m{i % 8}/task-{i}/r1", "task":"edit-clip", "model":f"m{i % 8}",
                     "sequence":i + 1,"repetition":1} for i in range(496)],
        "models":{f"m{i}":{} for i in range(8)},
        "task_root":str(root / "tasks"),"execution_policy":{"model_infra_policy":None},
    }
    lock = {"execution_lock_sha256":"b" * 64}
    approval = {"schema_version":2,"kind":"smallowbench_v2_model_execution_authorization",
                "approved_by_user":True,"manifest_sha256":manifest["manifest_sha256"],
                "execution_lock_sha256":lock["execution_lock_sha256"],"budget_usd":40}
    save(directory / "authorization.json", approval)
    baseline = {}
    for i, slot in enumerate(manifest["schedule"][:120]):
        job = f"visit-{i:032x}"
        path = directory / "visits" / (job + ".json")
        save(path, {"job_name":job,"slot_id":slot["slot_id"],"status":"scored",
                    "manifest_sha256":manifest["manifest_sha256"]})
        baseline[job] = executor.file_hash(path)
    waiver = {
        "schema_version":1,"kind":"smallowbench_v2_monetary_cap_waiver","approved_by_user":True,
        "manifest_sha256":manifest["manifest_sha256"],"execution_lock_sha256":lock["execution_lock_sha256"],
        "original_authorization_sha256":executor.file_hash(directory / "authorization.json"),
        "monetary_cap_usd":None,"monetary_cap_enforced":False,
        "max_task_attempts":496,"max_visits_per_slot":1,"workers":4,
        "policy":executor.FEE_WAIVER_POLICY,
        "implementation_sha256":{name:executor.file_hash(root / name) for name in executor.FEE_WAIVER_IMPLEMENTATION},
        "initial_scored_visits_sha256":baseline,
    }
    save(directory / "fee-waiver.json", waiver)
    return root, directory, manifest, lock, waiver


def test_valid_amendment_preserves_historical_caps(tmp_path):
    root, directory, manifest, lock, _ = fixture(tmp_path)
    before = json.dumps(manifest, sort_keys=True)
    assert executor.validate_fee_waiver(directory, manifest, lock, root=root) == executor.file_hash(directory / "fee-waiver.json")
    assert json.dumps(manifest, sort_keys=True) == before
    assert manifest["caps"]["budget_usd"] == 40


@pytest.mark.parametrize("change", [
    {"approved_by_user":False}, {"monetary_cap_usd":0}, {"monetary_cap_enforced":True},
    {"manifest_sha256":"c" * 64}, {"execution_lock_sha256":"c" * 64},
    {"original_authorization_sha256":"c" * 64}, {"max_task_attempts":497},
    {"max_visits_per_slot":2}, {"workers":1}, {"policy":"remove_all_limits"},
])
def test_incomplete_or_broadened_authority_rejected(tmp_path, change):
    root, directory, manifest, lock, waiver = fixture(tmp_path)
    waiver.update(change)
    save(directory / "fee-waiver.json", waiver)
    with pytest.raises(executor.V2Error, match="fee waiver"):
        executor.validate_fee_waiver(directory, manifest, lock, root=root)


def test_missing_waiver_is_not_authorized_by_old_approval(tmp_path):
    root, directory, manifest, lock, _ = fixture(tmp_path)
    (directory / "fee-waiver.json").unlink()
    with pytest.raises(executor.V2Error, match="fee-waiver"):
        executor.validate_fee_waiver(directory, manifest, lock, root=root)


@pytest.mark.parametrize("fault", ["drift", "extra", "missing"])
def test_exact_runtime_source_closure_required(tmp_path, fault):
    root, directory, manifest, lock, waiver = fixture(tmp_path)
    if fault == "drift":
        (root / executor.FEE_WAIVER_IMPLEMENTATION[0]).write_text("changed", encoding="utf-8")
    elif fault == "extra":
        waiver["implementation_sha256"]["scripts/other.py"] = "e" * 64
    else:
        waiver["implementation_sha256"].pop(executor.FEE_WAIVER_IMPLEMENTATION[-1])
    save(directory / "fee-waiver.json", waiver)
    with pytest.raises(executor.V2Error):
        executor.validate_fee_waiver(directory, manifest, lock, root=root)


@pytest.mark.parametrize("fault", ["bytes", "status", "slot", "path", "count"])
def test_initial_120_outcomes_are_bound_not_rewritten(tmp_path, fault):
    root, directory, manifest, lock, waiver = fixture(tmp_path)
    mapping = waiver["initial_scored_visits_sha256"]
    job = next(iter(mapping))
    if fault == "count":
        mapping.pop(job)
    elif fault == "path":
        mapping["../escape"] = mapping.pop(job)
    else:
        path = directory / "visits" / (job + ".json")
        row = json.loads(path.read_text(encoding="utf-8"))
        if fault == "status":
            row["status"] = "infra"
        elif fault == "slot":
            row["slot_id"] = "unplanned"
        else:
            row["unrecorded_edit"] = True
        save(path, row)
        if fault != "bytes":
            mapping[job] = executor.file_hash(path)
    save(directory / "fee-waiver.json", waiver)
    with pytest.raises(executor.V2Error):
        executor.validate_fee_waiver(directory, manifest, lock, root=root)


def mocked_executor(tmp_path, monkeypatch):
    root, directory, manifest, lock, waiver = fixture(tmp_path)
    harbor = root / "harbor"
    harbor.write_text("not executed", encoding="utf-8")
    monkeypatch.setattr(executor, "HARBOR", harbor)
    monkeypatch.setattr(executor, "validate_manifest", lambda *_a, **_k:manifest)
    monkeypatch.setattr(executor, "validate_lock", lambda *_a, **_k:lock)
    monkeypatch.setattr(executor, "validate_run_paths", lambda *_a, **_k:None)
    monkeypatch.setattr(executor, "assigned_slots", lambda *_a:manifest["schedule"][120:121])
    monkeypatch.setattr(executor, "process_lock", lambda *_a, **_k:nullcontext())
    monkeypatch.setattr(pipeline, "stage_tasks", lambda *_a, **_k:None)
    monkeypatch.setattr(containers, "docker_status", lambda:{"available":True})
    real_validator = executor.validate_fee_waiver
    monkeypatch.setattr(executor, "validate_fee_waiver", functools.partial(real_validator, root=root))
    class Store:
        def __init__(self):
            self.claim_calls = []
            self.completions = []
            self.claim_result = None
        def claim(self, *args, **kwargs):
            self.claim_calls.append((args, kwargs))
            return self.claim_result
        def active_claims(self):
            return []
        def update_running(self, *_a, **_k):
            pass
        def publish_visit(self, *_a, **_k):
            pass
        def complete(self, *args, **kwargs):
            self.completions.append((args, kwargs))
    store = Store()
    monkeypatch.setattr(executor, "ClaimStore", lambda *_a, **_k:store)
    return directory, manifest, lock, waiver, store


def test_claim_disables_money_gate_preserving_finite_attempts(tmp_path, monkeypatch):
    directory, manifest, _, _, store = mocked_executor(tmp_path, monkeypatch)
    assert executor.execute_experiment(directory, workers=4, execute=True) == 0
    assert len(store.claim_calls) == 1
    _, kwargs = store.claim_calls[0]
    assert kwargs == {"model":manifest["schedule"][120]["model"],"serialize_model":True,
                      "max_visits":1,"max_total_visits":496,"reserve_usd":3.5,"budget_usd":None}


def test_waiver_change_stops_before_admission(tmp_path, monkeypatch):
    directory, _, _, waiver, store = mocked_executor(tmp_path, monkeypatch)
    original = executor.validate_fee_waiver
    calls = 0
    def changing(*args, **kwargs):
        nonlocal calls
        result = original(*args, **kwargs)
        calls += 1
        if calls == 1:
            waiver["note"] = "changed while the worker was starting"
            save(directory / "fee-waiver.json", waiver)
        return result
    monkeypatch.setattr(executor, "validate_fee_waiver", changing)
    with pytest.raises(executor.V2Error, match="changed before admission"):
        executor.execute_experiment(directory, workers=4, execute=True)
    assert store.claim_calls == []
    assert (directory / "STOP").is_file()


def test_waiver_change_stops_before_child_launch(tmp_path, monkeypatch):
    directory, _, _, waiver, store = mocked_executor(tmp_path, monkeypatch)
    store.claim_result = SimpleNamespace(token="claim", job_name="visit-test")
    monkeypatch.setattr(pipeline, "job_config", lambda *_a, **_k:{"offline":True})
    import harbor.models.job.config as config
    monkeypatch.setattr(config, "JobConfig", SimpleNamespace(model_validate=lambda _value:None))
    original = executor.validate_fee_waiver
    calls = 0
    def changing(*args, **kwargs):
        nonlocal calls
        result = original(*args, **kwargs)
        calls += 1
        if calls == 2:
            waiver["note"] = "changed after admission"
            save(directory / "fee-waiver.json", waiver)
        return result
    monkeypatch.setattr(executor, "validate_fee_waiver", changing)
    monkeypatch.setattr(executor.subprocess, "Popen", lambda *_a, **_k:pytest.fail("no child may launch"))
    with pytest.raises(executor.V2Error, match="changed before launch"):
        executor.execute_experiment(directory, workers=4, execute=True)
    assert store.completions[0][1]["counts_toward_cap"] is False
    assert store.completions[0][1]["charged_usd"] == 0


def test_dry_plan_does_not_require_or_create_waiver(tmp_path, monkeypatch):
    directory, _, _, _, store = mocked_executor(tmp_path, monkeypatch)
    (directory / "fee-waiver.json").unlink()
    assert executor.execute_experiment(directory, workers=4, execute=False) == 0
    assert not (directory / "fee-waiver.json").exists()
    assert store.claim_calls == []


def test_pre_provenance_failure_still_records_amendment(tmp_path, monkeypatch):
    directory, _, _, _, store = mocked_executor(tmp_path, monkeypatch)
    store.claim_result = SimpleNamespace(token="claim", job_name="visit-test")
    def failing_config(*_args, **_kwargs):
        raise executor.V2Error("injected config failure before provenance")
    monkeypatch.setattr(pipeline, "job_config", failing_config)
    with pytest.raises(executor.V2Error, match="injected config failure"):
        executor.execute_experiment(directory, workers=4, execute=True)
    args, kwargs = store.completions[0]
    assert args[2] == "aborted"
    assert args[3] == {"launch_not_requested":True,
                       "fee_waiver_sha256":executor.file_hash(directory / "fee-waiver.json")}
    assert kwargs["counts_toward_cap"] is False
    assert kwargs["charged_usd"] == 0


def base_report(manifest):
    return {"kind":"smallowbench_v2_release_report","manifest_sha256":manifest["manifest_sha256"],
            "accepted":True,"formal_ranking_eligible":True,"issues":[],
            "leaderboard":{"model":{"artifact_macro_100":1}}}


def test_complete_base_report_adds_actual_fee_policy_and_phase_provenance(tmp_path):
    root, directory, manifest, lock, _ = fixture(tmp_path)
    job = "visit-" + "f" * 32
    save(directory / "visits" / (job + ".json"), {
        "job_name":job,"slot_id":manifest["schedule"][120]["slot_id"],"status":"scored",
        "manifest_sha256":manifest["manifest_sha256"],
        "fee_waiver_sha256":executor.file_hash(directory / "fee-waiver.json"),
    })
    original = base_report(manifest)
    report = analysis.annotate_report(directory, original, manifest, lock, root=root)
    assert report["accepted"] and report["formal_ranking_eligible"]
    assert report["actual_execution_policy"]["monetary_cap_enforced"] is False
    assert report["actual_execution_policy"]["monetary_cap_usd"] is None
    assert report["actual_execution_policy"]["original_manifest_monetary_cap_usd"] == 40
    assert report["execution_phases"] == {"initial_scored_visits":120,"continuation_visits":1,
                                           "continuation_scored_visits":1,"initial_scored_visit_bytes_unchanged":True}
    assert report["leaderboard"] == original["leaderboard"]
    assert "actual_execution_policy" not in original


@pytest.mark.parametrize("waiver_field", [None, "0" * 64])
def test_unbound_continuation_cannot_publish_complete_ranking(tmp_path, waiver_field):
    root, directory, manifest, lock, _ = fixture(tmp_path)
    job = "visit-" + "f" * 32
    row = {"job_name":job,"status":"scored","slot_id":manifest["schedule"][120]["slot_id"],
           "manifest_sha256":manifest["manifest_sha256"]}
    if waiver_field is not None:
        row["fee_waiver_sha256"] = waiver_field
    save(directory / "visits" / (job + ".json"), row)
    report = analysis.annotate_report(directory, base_report(manifest), manifest, lock, root=root)
    assert report["accepted"] is False
    assert report["formal_ranking_eligible"] is False
    assert report["leaderboard"] == {}
    assert report["issues"] == [{"kind":"continuation_missing_fee_waiver","job":job}]


def test_report_annotation_rejects_changed_initial_result_bytes(tmp_path):
    root, directory, manifest, lock, waiver = fixture(tmp_path)
    job = next(iter(waiver["initial_scored_visits_sha256"]))
    path = directory / "visits" / (job + ".json")
    path.write_text(path.read_text(encoding="utf-8") + "\n", encoding="utf-8")
    with pytest.raises(executor.V2Error, match="bytes changed"):
        analysis.annotate_report(directory, base_report(manifest), manifest, lock, root=root)


def test_original_executor_and_non_admission_helpers_unchanged():
    original = Path(__file__).with_name("release_v2_executor.py").read_bytes()
    assert hashlib.sha256(original).hexdigest() == "bd4cbbf77f97a2b9591dda3e9939dca26bddbb4c71470835e0d02346bf7968f8"
    before = {item.name:ast.dump(item, include_attributes=False) for item in ast.parse(original).body if isinstance(item, ast.FunctionDef)}
    after = {item.name:ast.dump(item, include_attributes=False) for item in ast.parse(Path(executor.__file__).read_bytes()).body if isinstance(item, ast.FunctionDef)}
    assert all(after[name] == value for name, value in before.items() if name != "execute_experiment")
