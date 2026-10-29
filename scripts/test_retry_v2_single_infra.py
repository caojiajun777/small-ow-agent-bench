"""Offline contracts for the one-slot infrastructure exception; no real clients."""
from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from experiment_execution import ClaimStore
import retry_v2_single_infra as retry


def save(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value), encoding="utf-8")


def fixture(tmp_path, monkeypatch, *, approve=True):
    root, directory = tmp_path / "source", tmp_path / "p2"
    runner = root / retry.RUNNER
    runner.parent.mkdir(parents=True)
    runner.write_text("bound retry source", encoding="utf-8")
    model = {"runtime_id": "openrouter/qwen/qwen3.5-9b", "route": "parasail/bf16",
             "agent_kwargs": {"max_turns": 20, "llm_call_kwargs": {"max_tokens": 8192}}}
    schedule = [{"slot_id": f"other/task-{i}/r1", "model": "other", "task": f"task-{i}",
                 "sequence": i + 1, "repetition": 1} for i in range(495)]
    schedule.append({"slot_id": retry.SLOT, "model": retry.MODEL, "task": retry.TASK,
                     "sequence": 496, "repetition": 1})
    manifest = {"manifest_sha256": "a" * 64, "schedule": schedule, "models": {retry.MODEL: model},
                "task_root": str(root / "tasks"),
                "caps": {"workers": 4, "max_visits_per_slot": 1, "max_total_visits": 496,
                         "budget_usd": 40, "visit_reserve_usd": 3.5}}
    staged = directory / "staged-tasks" / retry.TASK
    staged.mkdir(parents=True)
    (staged / "task.toml").write_text("frozen staged task")
    manifest["tasks"] = {retry.TASK: {
        "staged_task_config_sha256": retry.file_hash(staged / "task.toml"),
        "staged_tree_sha256": retry.legacy_tree_digest(staged),
    }}
    lock = {"execution_lock_sha256": "b" * 64}
    save(directory / "authorization.json", {"kind": "original authorization"})
    save(directory / "fee-waiver.json", {"monetary_cap_enforced": False})
    monkeypatch.setattr(retry.frozen, "validate_manifest", lambda *_a, **_k: manifest)
    monkeypatch.setattr(retry.frozen, "validate_lock", lambda *_a, **_k: lock)
    monkeypatch.setattr(retry.frozen, "validate_authorization",
                        lambda *_a: retry.file_hash(directory / "authorization.json"))
    monkeypatch.setattr(retry.frozen, "validate_fee_waiver",
                        lambda *_a, **_k: retry.file_hash(directory / "fee-waiver.json"))
    config = {"agents": [{"name": "frozen"}], "tasks": [{"path": "original-stage"}]}
    monkeypatch.setattr(retry, "job_config", lambda *_a: config)
    monkeypatch.setattr(retry, "normalized_job_config", lambda x: x)
    generated = directory / "configs" / (retry.SOURCE_JOB + ".json")
    executed = directory / "jobs" / retry.SOURCE_JOB / "config.json"
    save(generated, config)
    save(executed, config)
    trial = executed.parent / "trial"
    raw = {"task_name": "small-ow-agent-bench/" + retry.TASK,
           "config": {"agent": {"name": "frozen"}},
           "exception_info": {"exception_type": "RateLimitError", "exception_message": "HTTP 429"}}
    trace = {"schema_version": 2, "harness_version": "2.0.0-rc.1", "version": "2.0.0-rc.1",
             "task_id": retry.TASK, "finished": False, "n_turns": 3, "n_shell": 3,
             "n_shell_attempts": 3, "n_parse_fail": 0, "termination_reason": "api_error",
             "calls": [{"kind": "api", "status": "completed"} for _ in range(3)]
             + [{"kind": "api", "status": "error"}]}
    save(trial / "result.json", raw)
    save(trial / "agent/compact-shell-v2.json", trace)
    source = {**schedule[-1], "job_name": retry.SOURCE_JOB, "status": "infra", "visit": 1,
              "counts_toward_cap": True, "manifest_sha256": manifest["manifest_sha256"],
              "generated_config_sha256": retry.file_hash(generated),
              "executed_config_sha256": retry.file_hash(executed), "config_sha256": retry.file_hash(executed)}
    save(directory / "visits" / (retry.SOURCE_JOB + ".json"), source)
    store = ClaimStore(directory / "claims.sqlite3", manifest_sha256=manifest["manifest_sha256"])
    records = [{**slot, "job_name": f"visit-{i:032x}", "status": "scored", "visit": 1,
                "counts_toward_cap": True} for i, slot in enumerate(schedule[:-1])]
    store.import_visits([*records, source])
    proposal = {"schema_version": 1, "kind": "smallowbench_v2_single_infra_retry_proposal",
                "execution_authorized": False, "approved_by_user": False,
                "manifest_sha256": manifest["manifest_sha256"],
                "execution_lock_sha256": lock["execution_lock_sha256"],
                "fee_waiver_sha256": retry.file_hash(directory / "fee-waiver.json"),
                "slot_id": retry.SLOT, "source_job_name": retry.SOURCE_JOB,
                "source_visit_sha256": retry.file_hash(directory / "visits" / (retry.SOURCE_JOB + ".json")),
                "source_raw_result_sha256": retry.file_hash(trial / "result.json"),
                "source_trace_sha256": retry.file_hash(trial / "agent/compact-shell-v2.json"),
                "model_configuration": model, "reason": "evidence_confirmed_http_429",
                "max_new_attempts": 1, "slot_max_visits": 2, "global_max_counted_visits": 497,
                "require_counted_visits_before_launch": 496, "require_no_active_claims": True,
                "preserve_original_infra_record": True, "allow_retry_of_scored_slots": False,
                "change_provider_or_model": False, "monetary_cap_enforced": False}
    save(directory / retry.PROPOSAL, proposal)
    original_evidence = retry.frozen.provider_failure_evidence(raw, trace, trial)
    outcome = {"status": "scored", "atomic_correct": 0, "termination": "budget_exhaustion"}

    def classify(job, _task):
        if Path(job).name == retry.SOURCE_JOB:
            return {"status": "infra", "provider_failure": original_evidence}, None
        return dict(outcome), None

    monkeypatch.setattr(retry.frozen, "classify_job", classify)
    approval = {"schema_version": 1, "kind": retry.APPROVAL_KIND, "approved_by_user": True,
                "proposal_sha256": retry.file_hash(directory / retry.PROPOSAL),
                "runner_sha256": retry.file_hash(runner), "manifest_sha256": manifest["manifest_sha256"],
                "execution_lock_sha256": lock["execution_lock_sha256"],
                "original_authorization_sha256": retry.file_hash(directory / "authorization.json"),
                "fee_waiver_sha256": retry.file_hash(directory / "fee-waiver.json")}
    if approve:
        save(directory / retry.APPROVAL, approval)
    monkeypatch.setattr(retry, "validate_run_paths", lambda *_a, **_k: None)
    monkeypatch.setattr(retry, "_runtime_available", lambda: True)
    monkeypatch.setattr(retry, "_validate_job_config", lambda _c: None)
    popens, claims = [], []

    class RecordingStore(ClaimStore):
        def claim(self, slot_id, owner, **kwargs):
            claims.append({"slot_id": slot_id, **kwargs})
            return super().claim(slot_id, owner, **kwargs)

    monkeypatch.setattr(retry.frozen, "ClaimStore", RecordingStore)

    def popen(args, **kwargs):
        popens.append((args, kwargs))
        path = Path(args[-1])
        save(directory / "jobs" / path.stem / "config.json", json.loads(path.read_text()))
        return SimpleNamespace(pid=12345, returncode=0, poll=lambda: 0)

    monkeypatch.setattr(retry.subprocess, "Popen", popen)
    return SimpleNamespace(root=root, directory=directory, manifest=manifest, lock=lock,
                           proposal=proposal, approval=approval, store=store, popens=popens,
                           claims=claims, outcome=outcome, source=source, trial=trial)


def test_default_is_read_only_and_does_not_need_approval(tmp_path, monkeypatch):
    f = fixture(tmp_path, monkeypatch, approve=False)
    before = retry.file_hash(f.directory / "claims.sqlite3")
    report = retry.execute_single_retry(f.directory, root=f.root)
    assert report["ready"] and report["model_calls"] == 0
    assert report["separate_approval_required"]
    assert not f.popens and not f.claims
    assert retry.file_hash(f.directory / "claims.sqlite3") == before


def test_missing_approval_cannot_launch(tmp_path, monkeypatch):
    f = fixture(tmp_path, monkeypatch, approve=False)
    with pytest.raises((OSError, retry.V2Error)):
        retry.execute_single_retry(f.directory, execute=True, root=f.root)
    assert not f.popens and not f.claims


@pytest.mark.parametrize("field,value", [("runner_sha256", "x"), ("proposal_sha256", "x"),
                                        ("approved_by_user", False), ("fee_waiver_sha256", "x")])
def test_separate_approval_is_exact(tmp_path, monkeypatch, field, value):
    f = fixture(tmp_path, monkeypatch)
    f.approval[field] = value
    save(f.directory / retry.APPROVAL, f.approval)
    with pytest.raises(retry.V2Error, match="approval"):
        retry.execute_single_retry(f.directory, execute=True, root=f.root)
    assert not f.claims and not f.popens


@pytest.mark.parametrize("field,value", [("slot_id", "other/task-0/r1"), ("max_new_attempts", 2),
                                        ("slot_max_visits", 3), ("global_max_counted_visits", 1000),
                                        ("change_provider_or_model", True), ("approved_by_user", True)])
def test_proposal_cannot_broaden_scope(tmp_path, monkeypatch, field, value):
    f = fixture(tmp_path, monkeypatch)
    f.proposal[field] = value
    save(f.directory / retry.PROPOSAL, f.proposal)
    with pytest.raises(retry.V2Error, match="proposal"):
        retry.execute_single_retry(f.directory, root=f.root)
    assert not f.popens


@pytest.mark.parametrize("fault", ["missing32", "active", "already_scored", "second_visit", "hold", "stop"])
def test_only_last_single_infra_gap_can_run(tmp_path, monkeypatch, fault):
    f = fixture(tmp_path, monkeypatch)
    with f.store._transaction() as connection:
        if fault == "missing32":
            connection.execute("DELETE FROM visits WHERE slot_id='other/task-0/r1'")
        elif fault == "active":
            connection.execute("UPDATE visits SET status='running' WHERE slot_id='other/task-0/r1'")
        elif fault == "already_scored":
            connection.execute("UPDATE visits SET status='scored' WHERE slot_id=?", (retry.SLOT,))
        elif fault == "second_visit":
            connection.execute("UPDATE visits SET visit=2 WHERE slot_id=?", (retry.SLOT,))
    if fault == "hold":
        monkeypatch.setattr(retry.frozen, "read_model_holds", lambda *_a: {retry.MODEL: {}})
    if fault == "stop":
        (f.directory / "STOP").write_text("preserve this hold")
    with pytest.raises(retry.V2Error):
        retry.execute_single_retry(f.directory, execute=True, root=f.root)
    assert not f.claims and not f.popens


def test_source_drift_is_not_reclassified_or_retried(tmp_path, monkeypatch):
    f = fixture(tmp_path, monkeypatch)
    save(f.trial / "result.json", {"exception_info": {"exception_type": "OtherError"}})
    with pytest.raises(retry.V2Error, match="raw evidence"):
        retry.execute_single_retry(f.directory, root=f.root)
    assert not f.popens


def test_actual_staged_task_drift_rejected_before_claim(tmp_path, monkeypatch):
    f = fixture(tmp_path, monkeypatch)
    (f.directory / "staged-tasks" / retry.TASK / "task.toml").write_text("changed")
    with pytest.raises(retry.V2Error, match="staged task has drifted"):
        retry.execute_single_retry(f.directory, execute=True, root=f.root)
    assert not f.claims and not f.popens


def test_staged_task_drift_between_claim_and_popen_aborts(tmp_path, monkeypatch):
    f = fixture(tmp_path, monkeypatch)
    monkeypatch.setattr(retry, "_validate_job_config", lambda _c: (
        f.directory / "staged-tasks" / retry.TASK / "task.toml").write_text("changed"))
    with pytest.raises(retry.V2Error, match="staged task has drifted"):
        retry.execute_single_retry(f.directory, execute=True, root=f.root)
    assert not f.popens
    assert f.store.records()[-1]["status"] == "aborted"


def test_exactly_one_counted_second_visit_and_original_preserved(tmp_path, monkeypatch):
    f = fixture(tmp_path, monkeypatch)
    source_path = f.directory / "visits" / (retry.SOURCE_JOB + ".json")
    source_sha = retry.file_hash(source_path)
    report = retry.execute_single_retry(f.directory, execute=True, root=f.root)
    assert report["launched"] == 1 and not report["automatic_further_retry"]
    assert f.claims == [{"slot_id": retry.SLOT, "model": retry.MODEL, "serialize_model": True,
                         "max_visits": 2, "max_total_visits": 497, "reserve_usd": 3.5,
                         "budget_usd": None}]
    assert len(f.popens) == 1 and len(f.store.records()) == 497
    target = [r for r in f.store.records() if r["slot_id"] == retry.SLOT]
    assert [r["status"] for r in target] == ["infra", "scored"]
    assert all(r["counts_toward_cap"] for r in target)
    assert target[-1]["single_infra_retry_approval_sha256"] == retry.file_hash(f.directory / retry.APPROVAL)
    assert target[-1]["fee_waiver_sha256"] == retry.file_hash(f.directory / "fee-waiver.json")
    assert retry.file_hash(source_path) == source_sha
    with pytest.raises(retry.V2Error):
        retry.execute_single_retry(f.directory, execute=True, root=f.root)
    assert len(f.popens) == 1


def test_new_429_reholds_and_never_buys_a_third_visit(tmp_path, monkeypatch):
    f = fixture(tmp_path, monkeypatch)
    f.outcome.clear()
    f.outcome.update(status="infra", termination="infra", provider_failure={
        "classification": "evidence_confirmed_provider_infra", "exception_type": "RateLimitError",
        "http_status": 429})
    report = retry.execute_single_retry(f.directory, execute=True, root=f.root)
    assert report["status"] == "infra" and len(f.popens) == 1
    hold = retry.frozen.read_model_holds(f.directory, f.manifest, f.lock)[retry.MODEL]
    assert hold["source_job_name"] != retry.SOURCE_JOB
    with pytest.raises(retry.V2Error, match="hold"):
        retry.execute_single_retry(f.directory, execute=True, root=f.root)
    assert len(f.popens) == 1


def test_approval_drift_before_launch_aborts_without_paid_request(tmp_path, monkeypatch):
    f = fixture(tmp_path, monkeypatch)
    monkeypatch.setattr(retry, "_validate_job_config",
                        lambda _c: save(f.directory / retry.APPROVAL, {"approved_by_user": False}))
    with pytest.raises(retry.V2Error, match="approval"):
        retry.execute_single_retry(f.directory, execute=True, root=f.root)
    new = f.store.records()[-1]
    assert new["status"] == "aborted" and new["launch_not_requested"]
    assert not new["counts_toward_cap"] and new["charged_usd"] == 0
    assert new["single_infra_retry_approval_sha256"]
    assert not f.popens and (f.directory / "STOP").exists()


def test_popen_ambiguity_retains_unresolved_claim_and_stops(tmp_path, monkeypatch):
    f = fixture(tmp_path, monkeypatch)
    monkeypatch.setattr(retry.subprocess, "Popen", lambda *_a, **_k: (_ for _ in ()).throw(OSError("uncertain")))
    with pytest.raises(OSError):
        retry.execute_single_retry(f.directory, execute=True, root=f.root)
    new = f.store.records()[-1]
    assert new["status"] == "running" and new["charged_usd"] is None
    assert new["counts_toward_cap"] and (f.directory / "STOP").exists()
