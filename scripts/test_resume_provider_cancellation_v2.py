"""Offline tests of the narrowly typed cancellation audit and child ownership."""
from contextlib import nullcontext
from copy import deepcopy
import json
from pathlib import Path

import pytest

import resume_provider_cancellation_v2 as core
import provider_reassessment_v2 as old
from test_provider_reassessment_v2 import model as original_model


def save(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    text = json.dumps(value, ensure_ascii=False, indent=2) + "\n" if isinstance(value, (dict, list)) else value
    path.write_text(text, encoding="utf-8")
    return path


@pytest.fixture(autouse=True)
def no_process(monkeypatch):
    def forbidden(*_a, **_k):
        raise AssertionError("offline test attempted process launch")
    monkeypatch.setattr(core.subprocess, "Popen", forbidden)


def request_fixture(tmp_path, *, exception="AgentTimeoutError", reason="cancelled", status="cancelled", response="not a JSON response"):
    trial = tmp_path / "job/testgen-anagram__trial"
    model = old.model_from_parent({"models": {old.PARENT_MODEL: original_model()}})
    settings = model["agent_kwargs"]
    kwargs = settings["llm_call_kwargs"]
    params = {"temperature": settings["temperature"], "top_p": kwargs["top_p"], "max_tokens": kwargs["max_tokens"], "extra_body": kwargs["extra_body"]}
    calls = []
    for index in range(1, 3):
        calls.append({"kind": "api", "status": "completed", "response_log_path": f"turn-{index}.txt"})
        save(trial / "agent" / f"turn-{index}.txt", {"optional_params": params,
            "original_response": json.dumps({"provider": "PrimeIntellect"}),
            "litellm_params": {"api_key": "SYNTHETIC_NEVER_PRINT"}})
    calls.append({"kind": "api", "status": status, "response_log_path": "turn-3.txt"})
    save(trial / "agent/turn-3.txt", {"optional_params": deepcopy(params), "original_response": response})
    save(trial / "agent/compact-shell-v2.json", {"termination_reason": reason, "n_turns": 3, "calls": calls})
    save(trial / "result.json", {"trial_name": "testgen-anagram__trial", "exception_info": {"exception_type": exception}})
    return trial.parent, model, trial


def test_only_typed_pending_cancellation_does_not_require_a_success_response(tmp_path):
    job, model, _trial = request_fixture(tmp_path)
    with pytest.raises(old.V2Error):
        old.validate_request_contract(job, model)
    corrected = core.validate_request_contract(job, model)
    assert corrected["typed_timeout_cancellation_exception_applied"] is True
    assert corrected["receipts"][-1]["request_parameters_verified"] is True
    assert "provider" not in corrected["receipts"][-1]
    assert "SYNTHETIC_NEVER_PRINT" not in json.dumps(corrected)


@pytest.mark.parametrize("exception,reason,status", [
    ("APIConnectionError", "cancelled", "cancelled"),
    ("AgentTimeoutError", "api_error", "cancelled"),
    ("AgentTimeoutError", "cancelled", "completed"),
    ("AgentTimeoutError", "cancelled", "error"),
])
def test_unrelated_errors_cannot_use_pending_timeout_exception(tmp_path, exception, reason, status):
    job, model, _trial = request_fixture(tmp_path, exception=exception, reason=reason, status=status)
    with pytest.raises(core.V2Error):
        core.validate_request_contract(job, model)


def test_cancelled_request_still_requires_exact_parameters_and_saved_receipt(tmp_path):
    job, model, trial = request_fixture(tmp_path)
    path = trial / "agent/turn-3.txt"
    record = old.frozen.read_json(path)
    del record["optional_params"]["extra_body"]["enable_thinking"]
    save(path, record)
    with pytest.raises(core.V2Error):
        core.validate_request_contract(job, model)
    path.unlink()
    with pytest.raises(core.V2Error):
        core.validate_request_contract(job, model)


def test_normal_saved_request_contract_is_identical_to_the_frozen_original(tmp_path):
    job, model, _trial = request_fixture(tmp_path, exception=None, reason="finish", status="completed",
        response=json.dumps({"provider": "PrimeIntellect"}))
    assert core.validate_request_contract(job, model) == old.validate_request_contract(job, model)


def test_positive_typed_provider_error_is_infra_not_a_required_success_response(tmp_path, monkeypatch):
    job, model, _trial = request_fixture(tmp_path, exception="RateLimitError", reason="api_error", status="error")
    receipt = core.validate_request_contract(job, model)
    assert receipt["receipts"][-1]["response_status"] == "typed_provider_error_call"
    payload = {"status": "infra", "provider_failure": {"classification": "evidence_confirmed_provider_infra",
        "exception_type": "RateLimitError", "http_status": 429}}
    monkeypatch.setattr(core.legacy, "classify_job", lambda *_a: (deepcopy(payload), None))
    observed, cost = core.classify_job(job, "testgen-anagram", model)
    assert observed["status"] == "infra" and old.retryable(observed) and cost is None
    # A dropped parameter must hold even when the same provider returned a 429.
    trial = _trial
    path = trial / "agent/turn-3.txt"
    record = old.frozen.read_json(path)
    record["optional_params"]["max_tokens"] = 4096
    save(path, record)
    observed, cost = core.classify_job(job, "testgen-anagram", model)
    assert not old.retryable(observed) and observed["provider_failure"]["exception_type"] == "RequestContractError"


def test_unknown_error_cannot_bypass_json_provider_response_contract(tmp_path):
    job, model, _trial = request_fixture(tmp_path, exception="UnknownError", reason="api_error", status="error")
    with pytest.raises(core.V2Error):
        core.validate_request_contract(job, model)


def test_timeout_is_final_scored_zero_with_unknown_cost_retained(tmp_path, monkeypatch):
    job, model, _trial = request_fixture(tmp_path)
    monkeypatch.setattr(core.legacy, "classify_job", lambda *_a: ({"status": "scored", "termination": "tle", "atomic_correct": 0}, None))
    payload, cost = core.classify_job(job, "testgen-anagram", model)
    assert payload["status"] == "scored" and payload["termination"] == "tle" and payload["atomic_correct"] == 0
    assert cost is None and not old.retryable(payload)
    assert payload["request_contract"]["typed_timeout_cancellation_exception_applied"] is True


def mocked_execution(tmp_path, monkeypatch):
    root = tmp_path / "r"
    directory = root / "experiments/smallowbench-v2/p3"
    directory.mkdir(parents=True)
    manifest = {"manifest_sha256": core.MANIFEST_SHA, "models": {core.MODEL_ID: {}}, "caps": deepcopy(old.CAPS),
        "schedule": [{"slot_id": "already-scored", "task": "edit-old", "model": core.MODEL_ID, "repetition": 1, "sequence": 1},
            {"slot_id": "corrected-timeout", "task": "testgen-anagram", "model": core.MODEL_ID, "repetition": 1, "sequence": 50},
            {"slot_id": "new-slot", "task": "testgen-new", "model": core.MODEL_ID, "repetition": 1, "sequence": 51}]}
    lock, auth_sha, amendment_sha = {"execution_lock_sha256": "c" * 64}, "b" * 64, "d" * 64
    amendment = {"remaining_slot_ids": ["new-slot"], "correction": {"slot_id": "corrected-timeout"}, "baseline_counted_attempts": 50}
    monkeypatch.setattr(core, "_base", lambda *_a, **_k: (manifest, lock, auth_sha))
    monkeypatch.setattr(core, "validate_amendment", lambda *_a, **_k: (amendment, amendment_sha))
    monkeypatch.setattr(core, "_guard", lambda *_a, **_k: None)
    monkeypatch.setattr(core, "process_lock", lambda *_a, **_k: nullcontext())
    monkeypatch.setattr(core.frozen, "stage_tasks", lambda *_a, **_k: None)
    monkeypatch.setattr(core.frozen, "active_claims", lambda *_a, **_k: [])
    monkeypatch.setattr(core.frozen, "job_config", lambda *_a, **_k: {})
    from harbor.models.job.config import JobConfig
    monkeypatch.setattr(JobConfig, "model_validate", classmethod(lambda _cls, value: value))
    import provider_cancellation_scoring_v2 as scoring
    monkeypatch.setattr(scoring, "validate_reclassification", lambda *_a, **_k: {"slot_id": "corrected-timeout", "status": "scored"})
    monkeypatch.setattr(scoring, "validate_scored_visit", lambda *_a, **_k: {})
    payloads = iter([{"status": "scored", "termination": "tle", "atomic_correct": 0}])
    monkeypatch.setattr(core, "classify_job", lambda *_a: (next(payloads), None))
    class Process:
        pid, returncode = 4321, 0
        def poll(self):
            return 0
    launched = []
    def popen(command, **_kwargs):
        name = Path(command[-1]).stem
        save(directory / "jobs" / name / "config.json", {})
        launched.append(name)
        return Process()
    monkeypatch.setattr(core.subprocess, "Popen", popen)
    return root, directory, manifest, amendment_sha, launched


def test_continuation_uses_child_ledger_skips_old_and_overlay_and_keeps_finite_caps(tmp_path, monkeypatch):
    root, directory, manifest, amendment_sha, launched = mocked_execution(tmp_path, monkeypatch)
    original_db = save(directory / "claims.sqlite3", "ORIGINAL_DB_MUST_NOT_CHANGE")
    original_visit = save(directory / "visits/old.json", "ORIGINAL_EXPORT_MUST_NOT_CHANGE")
    hashes = [old.frozen.file_hash(path) for path in (original_db, original_visit)]
    observed = []
    original_claim = core.ClaimStore.claim
    def claim(store, *args, **kwargs):
        observed.append(kwargs)
        return original_claim(store, *args, **kwargs)
    monkeypatch.setattr(core.ClaimStore, "claim", claim)
    result = core.execute_experiment(directory, root=root, execute=True)
    assert result["launched"] == len(launched) == 1 and not result["stopped"]
    assert [old.frozen.file_hash(path) for path in (original_db, original_visit)] == hashes
    assert observed[0]["budget_usd"] is None and observed[0]["max_visits"] == 3 and observed[0]["max_total_visits"] == 136
    store = core.ClaimStore(directory / core.CONTINUATION / "claims.sqlite3", manifest_sha256=core.MANIFEST_SHA)
    row = store.records()[0]
    assert row["slot_id"] == "new-slot" and row["authorization_sha256"] == "b" * 64
    assert row["execution_amendment_sha256"] == amendment_sha
    assert row["status"] == "scored" and row["termination"] == "tle" and row["charged_usd"] is None


def test_real_child_artifact_validation_failure_stops_before_next_launch(tmp_path, monkeypatch):
    root, directory, manifest, _amendment_sha, launched = mocked_execution(tmp_path, monkeypatch)
    import provider_cancellation_scoring_v2 as scoring
    def reject(*_a, **_k):
        raise core.V2Error("synthetic raw capture mismatch")
    monkeypatch.setattr(scoring, "validate_scored_visit", reject)
    with pytest.raises(core.V2Error, match="capture mismatch"):
        core.execute_experiment(directory, root=root, execute=True)
    assert len(launched) == 1 and (directory / "STOP").exists()
    store = core.ClaimStore(directory / core.CONTINUATION / "claims.sqlite3", manifest_sha256=core.MANIFEST_SHA)
    assert store.records()[0]["status"] == "scored" and not store.active_claims()


def test_existing_stop_prevents_any_continuation_request(tmp_path, monkeypatch):
    root, directory, _manifest, _sha, launched = mocked_execution(tmp_path, monkeypatch)
    save(directory / "STOP", "operator hold")
    with pytest.raises(core.V2Error, match="STOP"):
        core.execute_experiment(directory, root=root, execute=True)
    assert not launched and not (directory / core.CONTINUATION).exists()


def test_child_active_claim_is_not_reaped(tmp_path, monkeypatch):
    root, directory, _manifest, _sha, launched = mocked_execution(tmp_path, monkeypatch)
    store = core.ClaimStore(directory / core.CONTINUATION / "claims.sqlite3", manifest_sha256=core.MANIFEST_SHA)
    store.claim("new-slot", "original-owner", model=core.MODEL_ID)
    with pytest.raises(core.V2Error, match="ownership"):
        core.execute_experiment(directory, root=root, execute=True)
    assert not launched and len(store.active_claims()) == 1


def test_exclusive_amendment_full_artifact_guard_returns_amendment_hash(tmp_path, monkeypatch):
    root = tmp_path / "r"
    directory = root / "experiments/smallowbench-v2/p3"
    directory.mkdir(parents=True)
    slots = [{"slot_id": f"slot-{index}"} for index in range(62)]
    manifest = {"schedule": slots, "caps": deepcopy(old.CAPS), "retry_policy": deepcopy(old.RETRY_POLICY)}
    manifest["manifest_sha256"] = old.frozen.document_digest(manifest)
    monkeypatch.setattr(core, "MANIFEST_SHA", manifest["manifest_sha256"])
    lock = {"execution_lock_sha256": "c" * 64}
    save(directory / "manifest.json", manifest)
    save(directory / "execution-lock.json", lock)
    save(directory / "authorization.json", {"synthetic_original_approval": True})
    save(directory / "claims.sqlite3", "original ledger bytes never mutated")
    save(directory / "STOP", "original false-positive hold")
    for name in core.NEW_SOURCES:
        save(root / name, "# synthetic bound implementation\n")
    visits, artifacts = [], {}
    for index in range(50):
        job = f"job-{index:02d}"
        row = {"job_name": job, "slot_id": f"slot-{index}", "status": "infra" if index == 0 else "scored", "counts_toward_cap": True}
        save(directory / "visits" / (job + ".json"), row)
        visits.append(row)
        for name, value in ((f"jobs/{job}/result.json", {}), (f"configs/{job}.json", {}), (f"runner-logs/{job}.log", "original log\n")):
            path = save(directory / name, value)
            artifacts[name] = old.frozen.file_hash(path)
    auth_sha = old.frozen.file_hash(directory / "authorization.json")
    monkeypatch.setattr(core, "_base", lambda *_a, **_k: (manifest, lock, auth_sha))
    monkeypatch.setattr(core, "_read_database", lambda *_a: deepcopy(visits))
    snapshot = {"baseline_files_sha256": {name: old.frozen.file_hash(directory / name) for name in ("manifest.json", "execution-lock.json", "authorization.json", "claims.sqlite3")},
        "baseline_artifact_files_sha256": artifacts,
        "baseline_visits_sha256": {row["job_name"]: old.frozen.file_hash(directory / "visits" / (row["job_name"] + ".json")) for row in visits},
        "baseline_claims_file_sha256": old.frozen.file_hash(directory / "claims.sqlite3"), "baseline_counted_attempts": 50,
        "remaining_slot_ids": [slot["slot_id"] for slot in slots[50:]],
        "correction": {"job_name": "job-00", "source_visit_sha256": old.frozen.file_hash(directory / "visits/job-00.json"),
            "raw_result_sha256": artifacts["jobs/job-00/result.json"], "trace_sha256": "a" * 64, "slot_id": "slot-0", "claim_token": "synthetic"}}
    monkeypatch.setattr(core, "_snapshot", lambda *_a: deepcopy(snapshot))
    import provider_cancellation_scoring_v2 as scoring
    monkeypatch.setattr(scoring, "build_reclassification", lambda *_a, **_k: {"synthetic_sidecar": True})
    amendment = core.prepare_amendment(directory, root=root, approval_reference="explicit user repair authority", write=True)
    validated, amendment_sha = core.validate_amendment(directory, root=root, verify_artifacts=True)
    assert validated == amendment and amendment_sha == old.frozen.file_hash(directory / core.AMENDMENT_NAME)
    # Releasing the hold requires the original bytes to be archived first.
    (directory / "STOP").rename(directory / core.STOP_ARCHIVE)
    assert core.validate_amendment(directory, root=root)[1] == amendment_sha
    # A new child result may be added; none of the fifty original raw files may change.
    save(directory / "jobs/new-child-job/result.json", {})
    assert core.validate_amendment(directory, root=root, verify_artifacts=True)[1] == amendment_sha
    save(directory / "jobs/job-00/result.json", {"changed": True})
    with pytest.raises(core.V2Error, match="artifact bytes"):
        core.validate_amendment(directory, root=root, verify_artifacts=True)
