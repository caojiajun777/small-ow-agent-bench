"""Offline provider-reassessment contracts. Never access a key, Docker or a model."""

from contextlib import nullcontext
from copy import deepcopy
from datetime import datetime, timezone, timedelta
import json
from pathlib import Path

import pytest

import provider_reassessment_v2 as core


def save(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2) + "\n"
        if isinstance(value, (dict, list))
        else value,
        encoding="utf-8",
    )
    return path


def model():
    return {
        "runtime_id": "openrouter/qwen/qwen3.5-9b",
        "route": "parasail/bf16",
        "agent_kwargs": {
            "max_turns": 20,
            "command_timeout_sec": 60,
            "observation_limit": 8000,
            "temperature": 0.0,
            "llm_call_kwargs": {
                "max_tokens": 8192,
                "timeout": 180,
                "top_p": 1.0,
                "extra_body": {
                    "provider": {
                        "order": ["parasail/bf16"],
                        "only": ["parasail/bf16"],
                        "allow_fallbacks": False,
                        "require_parameters": True,
                        "quantizations": ["bf16"],
                    },
                    "reasoning": {"enabled": False},
                    "enable_thinking": False,
                },
            },
        },
    }


def catalog():
    return {
        "data": {
            "id": "qwen/qwen3.5-9b",
            "endpoints": [
                {
                    "tag": core.ROUTE,
                    "quantization": "bf16",
                    "status": 0,
                    "max_completion_tokens": 40960,
                    "supported_parameters": [
                        "temperature",
                        "top_p",
                        "max_tokens",
                        "reasoning",
                    ],
                }
            ],
        }
    }


@pytest.fixture(autouse=True)
def forbid_real_execution(monkeypatch):
    def forbidden(*_a, **_k):
        raise AssertionError("offline test attempted a process launch")

    monkeypatch.setattr(core.subprocess, "Popen", forbidden)


@pytest.fixture
def workspace(tmp_path, monkeypatch):
    root = tmp_path / "r"
    parent_dir = root / "experiments/smallowbench-v2/p2"
    parent_dir.mkdir(parents=True)
    task_root = root / "tasks"
    task_root.mkdir()
    save(root / "common.py", "# shared frozen implementation\n")
    for name in core.NEW_SOURCES:
        save(root / name, "# synthetic source binding, not executed\n")
    save(root.parent / "harbor/src/runtime.py", "# synthetic Harbor\n")
    save(root.parent / "harbor/uv.lock", "# synthetic lock\n")
    bindings = {}
    for key in (
        "task_bank",
        "preflight",
        "runtime",
        "models_source",
        "roster_reference",
    ):
        path = save(root / (key + ".json"), {})
        bindings[key] = core.frozen.bound_file(path)
    parent = {
        "schema_version": 2,
        "kind": "smallowbench_v2_release_experiment",
        "frozen": True,
        "manifest_sha256": core.PARENT_MANIFEST,
        "directory": str(parent_dir),
        "experiment_id": "p2",
        "repository_root": str(root),
        "purpose": "formal_release",
        "created_at": "synthetic",
        "task_root": str(task_root),
        "models": {core.PARENT_MODEL: model()},
        "tasks": {
            name: {"skill": name.split("-", 1)[0]} for name in core.frozen.BANK_62
        },
        "source_hashes": {"common.py": core.frozen.file_hash(root / "common.py")},
        "caps": {"budget_usd": 40},
        "repetitions": 1,
        "execution_authorized": False,
        "execution_policy": {},
        "retry_policy": {},
        "schedule": [],
        "n_planned_trials": 496,
        "plan_sha256": "old",
        "host_runtime_evidence": {"unit": True},
        **bindings,
    }
    lock = {"execution_lock_sha256": core.PARENT_LOCK}
    save(parent_dir / "manifest.json", parent)
    save(parent_dir / "execution-lock.json", lock)
    calls = []

    def fake_parent(directory, supplied_root, *, cold):
        assert Path(directory) == parent_dir
        assert Path(supplied_root) == root
        calls.append(cold)
        return deepcopy(parent), deepcopy(lock)

    monkeypatch.setattr(core, "_parent", fake_parent)
    monkeypatch.setattr(core.frozen, "stage_tasks", lambda *_a, **_k: None)
    monkeypatch.setattr(
        core.frozen, "host_runtime_evidence", lambda *_a: {"unit": True}
    )
    import v2_paths

    monkeypatch.setattr(v2_paths, "validate_run_paths", lambda *_a, **_k: None)
    catalog_path = save(root / "catalog.json", catalog())
    directory = root / "experiments/smallowbench-v2/p3"
    manifest, newlock = core.prepare(
        directory, parent_dir, catalog_path, root=root, write=True
    )
    return root, directory, manifest, newlock, parent, calls


def test_only_three_provider_paths_change():
    parent = {"models": {core.PARENT_MODEL: model()}}
    original = deepcopy(parent)
    result = core.model_from_parent(parent)
    result["route"] = "parasail/bf16"
    provider = result["agent_kwargs"]["llm_call_kwargs"]["extra_body"]["provider"]
    provider["order"] = provider["only"] = ["parasail/bf16"]
    assert result == model()
    assert parent == original


@pytest.mark.parametrize(
    "mutation", ["missing", "unavailable", "quantized", "maxout", "reasoning"]
)
def test_endpoint_must_preserve_contract(mutation):
    value = catalog()
    endpoint = value["data"]["endpoints"][0]
    if mutation == "missing":
        endpoint["tag"] = "other/bf16"
    elif mutation == "unavailable":
        endpoint["status"] = -5
    elif mutation == "quantized":
        endpoint["quantization"] = "int4"
    elif mutation == "maxout":
        endpoint["max_completion_tokens"] = 4096
    else:
        endpoint["supported_parameters"].remove("reasoning")
    with pytest.raises(core.V2Error):
        core.select_endpoint(value)


def test_prepare_is_independent_and_requires_bound_uncapped_auth(workspace):
    root, directory, manifest, lock, parent, calls = workspace
    assert calls == [True]
    assert manifest["caps"] == core.CAPS
    assert manifest["caps"]["budget_usd"] is None
    assert set(manifest["models"]) == {core.MODEL_ID}
    assert len(manifest["schedule"]) == 62
    assert manifest["tasks"] == parent["tasks"]
    assert (directory / "STOP").is_file()
    assert core.validate_manifest(directory, root=root, cold=True) == manifest
    assert core.validate_lock(directory, manifest, root=root) == lock
    with pytest.raises(core.V2Error):
        core.validate_authorization(directory, manifest, lock, root=root)
    auth = core.authorization_document(
        manifest,
        lock,
        approval_reference="user: solve the shared-pool rate limit; money caps removed",
    )
    save(directory / "authorization.json", auth)
    assert core.validate_authorization(directory, manifest, lock, root=root)
    auth["monetary_cap_usd"] = 40
    save(directory / "authorization.json", auth)
    with pytest.raises(core.V2Error):
        core.validate_authorization(directory, manifest, lock, root=root)


@pytest.mark.parametrize(
    "fault", ["code", "parent", "runtime", "catalog", "plan", "source_set"]
)
def test_drift_rejected_before_admission(workspace, fault):
    root, directory, manifest, lock, parent, calls = workspace
    if fault == "code":
        save(root / core.NEW_SOURCES[0], "changed")
    elif fault == "parent":
        save(
            Path(manifest["parent"]["directory"]) / "execution-lock.json", {"new": True}
        )
    elif fault == "runtime":
        save(root.parent / "harbor/src/runtime.py", "changed")
    elif fault == "catalog":
        save(manifest["catalog"]["path"], catalog() | {"changed": True})
    elif fault == "plan":
        save(directory / "PLAN.md", "changed")
    else:
        save(root.parent / "harbor/src/new_module.py", "added module")
    with pytest.raises(core.V2Error):
        core.validate_manifest(directory, root=root)


def response_job(tmp_path, *, status="completed", reason=None, drop=False, error=None):
    trial = tmp_path / "job/task__trial"
    save(trial / "result.json", {"trial_name": "task__trial", "exception_info": error})
    call = {"kind": "api", "status": status, "response_log_path": "turn-1.txt"}
    if reason:
        call["termination_reason"] = reason
    trace = {
        "termination_reason": "api_error" if error else "finish",
        "n_turns": 1,
        "calls": [call],
    }
    save(trial / "agent/compact-shell-v2.json", trace)
    m = core.model_from_parent({"models": {core.PARENT_MODEL: model()}})
    settings = m["agent_kwargs"]
    params = {
        "temperature": settings["temperature"],
        "top_p": 1.0,
        "max_tokens": 8192,
        "extra_body": deepcopy(settings["llm_call_kwargs"]["extra_body"]),
    }
    if drop:
        del params["extra_body"]["enable_thinking"]
    save(
        trial / "agent/turn-1.txt",
        {
            "optional_params": params,
            "original_response": json.dumps({"provider": "PrimeIntellect"}),
            "litellm_params": {"api_key": "synthetic-do-not-output"},
        },
    )
    return trial.parent, m, trial


@pytest.mark.parametrize(
    "status,reason", [("completed", None), ("budget_exceeded", "output_limit")]
)
def test_real_request_receipts_guard_silent_parameter_drop(tmp_path, status, reason):
    job, m, trial = response_job(tmp_path, status=status, reason=reason)
    assert core.validate_request_contract(job, m)["receipts"][0]["path"] == "turn-1.txt"
    log = core.frozen.read_json(trial / "agent/turn-1.txt")
    del log["optional_params"]["extra_body"]["enable_thinking"]
    save(trial / "agent/turn-1.txt", log)
    with pytest.raises(core.V2Error):
        core.validate_request_contract(job, m)


def test_typed400_and_request_drift_are_infra_hold_not_model_zero(tmp_path):
    error = {
        "exception_type": "BadRequestError",
        "exception_message": "400 parameter refused",
    }
    job, m, _ = response_job(tmp_path, error=error)
    payload, cost = core.classify_job(job, "loc-unit", m)
    assert payload["status"] == "infra" and cost is None
    assert payload["provider_failure"]["http_status"] == 400
    assert not core.retryable(payload)
    job, m, _ = response_job(tmp_path / "dropped", drop=True)
    payload, cost = core.classify_job(job, "loc-unit", m)
    assert payload["status"] == "infra" and not core.retryable(payload)


@pytest.mark.parametrize(
    "status,exception,expected",
    [
        (429, "RateLimitError", True),
        (503, "APIStatusError", True),
        (408, "APIStatusError", True),
        (None, "ReadError", True),
        (None, "RateLimitError", True),
        (400, "BadRequestError", False),
        (404, "NotFoundError", False),
        (401, "AuthenticationError", False),
    ],
)
def test_only_positive_transient_infra_retries(status, exception, expected):
    payload = {
        "status": "infra",
        "provider_failure": {
            "classification": "evidence_confirmed_provider_infra",
            "http_status": status,
            "exception_type": exception,
        },
    }
    assert core.retryable(payload) is expected
    payload["status"] = "scored"
    assert not core.retryable(payload)


def test_retry_after_is_longer_and_stop_interrupts(tmp_path):
    visit = {
        "visit": 1,
        "finished_at": datetime.now(timezone.utc).isoformat(),
        "provider_failure": {"retry_after_seconds": 600},
    }
    assert 590 < core.cooldown_seconds(visit) <= 600
    visit["finished_at"] = (
        datetime.now(timezone.utc) - timedelta(seconds=700)
    ).isoformat()
    assert core.cooldown_seconds(visit) == 0
    save(tmp_path / "STOP", "manual hold")
    assert not core._wait(tmp_path, 600)


def test_claim_store_retains_unknown_charge_and_blocks_scored_retry(tmp_path):
    store = core.ClaimStore(tmp_path / "claims.sqlite3", manifest_sha256="a" * 64)
    kwargs = {
        "model": core.MODEL_ID,
        "serialize_model": True,
        "max_visits": 3,
        "max_total_visits": 186,
        "reserve_usd": 3.5,
        "budget_usd": None,
    }
    first = store.claim("slot", "owner", **kwargs)
    assert store.claim("other", "owner", **kwargs) is None
    store.complete(
        first.token, "owner", "infra", {"provider_failure": {}}, charged_usd=None
    )
    assert store.records()[0]["charged_usd"] is None
    assert store.records()[0]["reserved_usd"] == 3.5
    second = store.claim("slot", "owner", **kwargs)
    store.complete(
        second.token, "owner", "scored", {"atomic_correct": 0}, charged_usd=None
    )
    assert store.claim("slot", "owner", **kwargs) is None


def test_active_claim_never_reaped_or_relaunched(workspace, monkeypatch):
    root, directory, manifest, lock, *_ = workspace
    save(
        directory / "authorization.json",
        core.authorization_document(
            manifest, lock, approval_reference="explicit user approval"
        ),
    )
    (directory / "STOP").unlink()
    monkeypatch.setattr(core, "process_lock", lambda *_a, **_k: nullcontext())
    store = core.ClaimStore(
        directory / "claims.sqlite3", manifest_sha256=manifest["manifest_sha256"]
    )
    store.claim(
        manifest["schedule"][0]["slot_id"], "original-owner", model=core.MODEL_ID
    )
    with pytest.raises(core.V2Error, match="active/unresolved"):
        core.execute_experiment(directory, root=root, execute=True)
    assert len(store.active_claims()) == 1


def test_missing_auth_cannot_launch(workspace):
    root, directory, *_ = workspace
    with pytest.raises(core.V2Error):
        core.execute_experiment(directory, root=root, execute=True)


def mocked_run(workspace, monkeypatch, payloads, *, reject_scored=False):
    root, directory, manifest, lock, *_ = workspace
    save(
        directory / "authorization.json",
        core.authorization_document(
            manifest, lock, approval_reference="explicit user approval"
        ),
    )
    (directory / "STOP").unlink()
    monkeypatch.setattr(core, "process_lock", lambda *_a, **_k: nullcontext())
    monkeypatch.setattr(core, "validate_current_task", lambda *_a, **_k: None)
    monkeypatch.setattr(core.frozen, "job_config", lambda *_a, **_k: {})
    from harbor.models.job.config import JobConfig

    monkeypatch.setattr(
        JobConfig, "model_validate", classmethod(lambda _cls, value: value)
    )
    launched = []

    class FakeChild:
        pid, returncode = 12345, 0

        def poll(self):
            return 0

    def launch(command, **kwargs):
        assert kwargs["creationflags"] == (0x08000000 if core.os.name == "nt" else 0)
        job_name = Path(command[-1]).stem
        save(directory / "jobs" / job_name / "config.json", {})
        launched.append(job_name)
        return FakeChild()

    monkeypatch.setattr(core.subprocess, "Popen", launch)
    iterator = iter(payloads)
    monkeypatch.setattr(
        core, "classify_job", lambda *_a: (deepcopy(next(iterator)), None)
    )
    monkeypatch.setattr(core, "_wait", lambda *_a: True)
    import provider_reassessment_scoring_v2 as scoring

    def validate(*_a, **_k):
        if reject_scored:
            raise core.V2Error("synthetic captured artifact mismatch")
        return {"artifact": 0}

    monkeypatch.setattr(scoring, "validate_scored_visit", validate)
    return root, directory, manifest, launched


def transient(code=429):
    return {
        "status": "infra",
        "termination": "infra",
        "provider_failure": {
            "classification": "evidence_confirmed_provider_infra",
            "http_status": code,
            "exception_type": "APIStatusError",
        },
        "cost_status": "unknown_reserve_retained",
    }


def test_runner_retries_only_infra_and_accepts_final_wrong_answer(
    workspace, monkeypatch
):
    root, directory, manifest, launched = mocked_run(
        workspace,
        monkeypatch,
        [transient(), transient(503), {"status": "scored", "atomic_correct": 0}],
    )
    result = core.execute_experiment(directory, root=root, execute=True, limit=3)
    assert len(launched) == 3 and not result["stopped"]
    store = core.ClaimStore(
        directory / "claims.sqlite3", manifest_sha256=manifest["manifest_sha256"]
    )
    rows = store.records()
    assert [row["status"] for row in rows] == ["infra", "infra", "scored"]
    assert not store.active_claims()
    assert all(
        row["charged_usd"] is None and row["reserved_usd"] == 3.5 for row in rows
    )


@pytest.mark.parametrize(
    "failures",
    [[transient()] * 3, [transient(400)], [transient(401)], [transient(404)]],
)
def test_runner_holds_exhausted_or_permanent_provider_fault(
    workspace, monkeypatch, failures
):
    root, directory, manifest, launched = mocked_run(workspace, monkeypatch, failures)
    result = core.execute_experiment(directory, root=root, execute=True)
    assert result["stopped"] and len(launched) == len(failures)
    assert result["unresolved_claims"] == 0


def test_scored_capture_failure_preserves_result_and_stops_next_launch(
    workspace, monkeypatch
):
    root, directory, manifest, launched = mocked_run(
        workspace,
        monkeypatch,
        [{"status": "scored", "atomic_correct": 0}],
        reject_scored=True,
    )
    with pytest.raises(core.V2Error, match="captured artifact"):
        core.execute_experiment(directory, root=root, execute=True)
    assert len(launched) == 1 and (directory / "STOP").is_file()
    store = core.ClaimStore(
        directory / "claims.sqlite3", manifest_sha256=manifest["manifest_sha256"]
    )
    assert store.records()[0]["status"] == "scored" and not store.active_claims()
