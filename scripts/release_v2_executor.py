"""Explicitly authorized SmallOWBench 2.0 execution, stopped by default.

This module is never called to collect models during development tests. It
reuses transactional ownership/accounting, not the old experiment or scorer.
No age-based recovery, answer-based retries, route substitutions or implicit
authorization. STOP drains the current task and prevents another admission.
"""

from __future__ import annotations

import json
import hashlib
import math
import os
import re
from datetime import datetime, timezone
from pathlib import Path
import socket
import subprocess
import time
import uuid

from classify_timeouts import load_trials
from experiment_execution import ClaimStore
from ledger_io import process_lock, write_atomic
from v2_paths import validate_run_paths
from release_v2_pipeline import (
    ROOT,
    V2Error,
    file_hash,
    read_json,
    validate_lock,
    validate_manifest,
    validate_verdict,
)

HARBOR = (
    ROOT.parent
    / "harbor"
    / ".venv"
    / ("Scripts/harbor.exe" if os.name == "nt" else "bin/harbor")
)

PRE_AGENT_INFRA = {
    "BuildException",
    "EnvironmentStartTimeoutError",
    "EnvironmentStartError",
}
PROVIDER_INFRA = {
    "RateLimitException",
    "RateLimitError",
    "APIConnectionError",
    "ConnectError",
    "ReadError",
    "ServiceUnavailableError",
    "ServiceUnavailable",
    "InternalServerError",
    "AuthenticationError",
    "PermissionDeniedError",
}
MODEL_INFRA_POLICY = "pause_model_continue_others"


def finite_money(value):
    return (
        not isinstance(value, bool)
        and isinstance(value, (int, float))
        and math.isfinite(value)
        and value >= 0
    )


def validate_authorization(directory, manifest, lock):
    """Only an independent explicit approval can lift preparation's default hold."""
    directory = Path(directory)
    path = directory / "authorization.json"
    if not path.is_file() or path.is_symlink():
        raise V2Error("explicit model-execution authorization.json is absent")
    value = read_json(path)
    budget = manifest["caps"].get("budget_usd")
    if (
        value.get("schema_version") != 2
        or value.get("kind") != "smallowbench_v2_model_execution_authorization"
        or value.get("approved_by_user") is not True
        or value.get("manifest_sha256") != manifest["manifest_sha256"]
        or value.get("execution_lock_sha256") != lock["execution_lock_sha256"]
        or not finite_money(budget)
        or budget <= 0
        or not finite_money(value.get("budget_usd"))
        or value["budget_usd"] != budget
    ):
        raise V2Error(
            "authorization must explicitly bind the frozen matrix, execution lock and positive budget"
        )
    handoff = value.get("budget_handoff")
    if handoff is not None:
        if not isinstance(handoff, dict) or handoff.get("share") != "diagnostic" or not isinstance(handoff.get("binding"), dict):
            raise V2Error("diagnostic authorization has an invalid budget handoff")
        from v2_budget_handoff import validate_share

        validate_share(handoff["binding"], handoff["share"], directory, budget)
    return file_hash(path)


def validate_caps(manifest, worker, workers):
    caps = manifest["caps"]
    if (
        type(workers) is not int
        or not 1 <= workers <= 4
        or caps.get("workers") != workers
        or type(worker) is not int
        or not 0 <= worker < workers
        or not finite_money(caps.get("budget_usd"))
        or caps["budget_usd"] <= 0
        or not finite_money(caps.get("visit_reserve_usd"))
        or not 0 < caps["visit_reserve_usd"] <= caps["budget_usd"]
        or type(caps.get("max_visits_per_slot")) is not int
        or not 1 <= caps["max_visits_per_slot"] <= 3
        or caps.get("max_total_visits")
        != len(manifest["schedule"]) * caps["max_visits_per_slot"]
    ):
        raise V2Error(
            "execution budget, worker partition or finite retry caps are invalid"
        )
    return caps


def assigned_slots(manifest, worker, workers):
    """Assign whole models to workers; ClaimStore also enforces model serialization."""
    names = sorted(manifest["models"])
    models = {name for index, name in enumerate(names) if index % workers == worker}
    return [row for row in manifest["schedule"] if row["model"] in models]


def provider_http_failure(raw, trace):
    """Typed API exceptions plus a failed API call, never arbitrary business output."""
    info = raw.get("exception_info") or {}
    if info.get("exception_type") not in ("APIStatusError", "NotFoundError"):
        return False
    message = info.get("exception_message")
    return (
        trace.get("termination_reason") == "api_error"
        and isinstance(message, str)
        and re.search(r"\b(?:401|402|403|404|408|429|5\d\d)\b", message) is not None
    )


def provider_failure_evidence(raw, trace, trial):
    """Positive API-failure evidence; never infer a provider fault from a score.

    Persist hashes and typed metadata, not exception messages which may contain
    request URLs or credentials. Source artifacts remain available for audit.
    """
    info = raw.get("exception_info") or {}
    exception = info.get("exception_type")
    if (
        trace.get("termination_reason") != "api_error"
        or not (exception in PROVIDER_INFRA or provider_http_failure(raw, trace))
    ):
        return None
    message = info.get("exception_message")
    match = re.search(r"\b(401|402|403|404|408|429|5\d\d)\b", message) if isinstance(message, str) else None
    status = int(match.group(1)) if match else None
    completed = sum(
        call.get("kind") == "api" and call.get("status") == "completed"
        for call in trace.get("calls", [])
    )
    return {
        "classification": "evidence_confirmed_provider_infra",
        "exception_type": exception,
        "http_status": status,
        "termination_reason": "api_error",
        "n_turns": trace["n_turns"],
        "completed_api_responses": completed,
        "raw_result_sha256": file_hash(Path(trial) / "result.json"),
        "trace_sha256": file_hash(Path(trial) / "agent" / "compact-shell-v2.json"),
    }


def isolatable_provider_failure(evidence):
    """Authentication/permission failures may affect the shared account key.

    Preserve their infra receipt and billing reserve, but stop globally rather
    than spending on other models with the same potentially invalid credential.
    """
    return (
        isinstance(evidence, dict)
        and evidence.get("classification") == "evidence_confirmed_provider_infra"
        and evidence.get("exception_type") not in {
            "AuthenticationError", "LiteLLMAuthenticationError", "PermissionDeniedError"
        }
        and evidence.get("http_status") not in {401, 402, 403}
    )


def retryable_execution_infra(raw, trace):
    """A grader/download fault must never buy another model attempt."""
    exception = (raw.get("exception_info") or {}).get("exception_type")
    if exception in PRE_AGENT_INFRA:
        return True
    if trace is None:
        return False
    return trace.get("termination_reason") == "command_error" or (
        trace.get("termination_reason") == "api_error"
        and (exception in PROVIDER_INFRA or provider_http_failure(raw, trace))
    )


def classify_job(job, task):
    """Derive retry status only from raw artifacts, never ledger cached success."""
    from analyze_release_v2 import termination, validate_trace

    trials = load_trials(Path(job))
    if len(trials) != 1:
        raise V2Error(
            "missing/ambiguous raw trial; hold for recovery, never rerun a model on absence alone"
        )
    trial, raw = trials[0]
    raw_exception = (raw.get("exception_info") or {}).get("exception_type")
    trace_path = trial / "agent" / "compact-shell-v2.json"
    verdict_path = trial / "verifier" / "verdict.json"
    trace = read_json(trace_path) if trace_path.is_file() else None
    verdict = read_json(verdict_path) if verdict_path.is_file() else None
    if trace is None:
        if retryable_execution_infra(raw, None):
            return {
                "status": "infra",
                "termination": "infra",
                "reason": raw_exception,
                "retry_classification": "evidence_confirmed_runtime_or_provider_infra",
            }, None
        raise V2Error(
            "missing v2 trace without affirmative infrastructure evidence; hold"
        )
    trace = validate_trace(trace, task)
    provider_evidence = provider_failure_evidence(raw, trace, trial)
    term = termination(raw, trace)
    if provider_http_failure(raw, trace):
        term = "infra"
    if verdict is None:
        if term == "infra" and retryable_execution_infra(raw, trace):
            return {
                "status": "infra",
                "termination": "infra",
                "reason": "upstream_infra_without_verdict",
                "retry_classification": "evidence_confirmed_runtime_or_provider_infra",
                "provider_failure": provider_evidence,
                "cost_status": "unknown_reserve_retained",
            }, None
        raise V2Error(
            "missing verdict after model execution; regrade/repair required, never a model retry"
        )
    validate_verdict(verdict, task)
    if verdict["status"] == "error":
        raise V2Error(
            "trusted grading error; hold for artifact-only regrade, not a new model attempt"
        )
    if term == "infra":
        if not retryable_execution_infra(raw, trace):
            raise V2Error(
                "unclassified harness fault; repair required before another model attempt"
            )
        status = "infra"
    else:
        reward = ((raw.get("verifier_result") or {}).get("rewards") or {}).get("reward")
        if (
            isinstance(reward, bool)
            or not isinstance(reward, (int, float))
            or reward != verdict["artifact_correct"]
        ):
            raise V2Error("raw Harbor reward disagrees with the versioned verdict")
        status = "scored"
    cost = (raw.get("agent_result") or {}).get("cost_usd")
    # Partial/default cost zero after upstream failure is not evidence of free service.
    if (
        not finite_money(cost)
        or trace["termination_reason"] in {
            "api_error", "output_limit", "context_limit", "cancelled"
        }
        or any(call.get("kind") == "api" and call.get("status") != "completed"
               for call in trace.get("calls", []))
        or cost == 0 and any(
            (trace.get("usage") or {}).get(name, 0) > 0
            for name in ("input_tokens", "output_tokens")
        )
    ):
        cost = None
    return {
        "status": status,
        "termination": term,
        "termination_reason": trace["termination_reason"],
        "retry_classification": "evidence_confirmed_runtime_or_provider_infra"
        if status == "infra"
        else None,
        "atomic_correct": verdict["artifact_correct"],
        "clean_success": verdict["artifact_correct"] == 1 and term == "clean",
        "failure_category": verdict["failure_category"],
        "raw_trial_count": 1,
        "cost_status": "reported_api_cost"
        if cost is not None
        else "unknown_reserve_retained",
        "provider_failure": provider_evidence if status == "infra" else None,
    }, cost


def _hold(directory, reason):
    path = Path(directory) / "STOP"
    try:
        with path.open("x", encoding="utf-8") as stream:
            stream.write(reason + "\n")
    except FileExistsError:
        pass  # Another worker's global hold is equally authoritative.


def _model_hold_path(directory, model):
    name = hashlib.sha256(model.encode("utf-8")).hexdigest()[:24]
    return Path(directory) / "model-holds" / (name + ".json")


def read_model_holds(directory, manifest, lock):
    """Durable holds never expire or clear on restart; changed bindings fail shut."""
    root = Path(directory) / "model-holds"
    if root.is_symlink():
        raise V2Error("model-holds must not be a symlink")
    holds = {}
    slots = {row["slot_id"]: row for row in manifest["schedule"]}
    for path in root.glob("*.json"):
        if path.is_symlink() or not path.is_file():
            raise V2Error("unsafe model hold evidence")
        value = read_json(path)
        model = value.get("model")
        slot = slots.get(value.get("source_slot_id"), {})
        if (
            value.get("schema_version") != 2
            or value.get("kind") != "smallowbench_v2_model_provider_hold"
            or value.get("status") != "held"
            or model not in manifest["models"]
            or path != _model_hold_path(directory, model)
            or value.get("manifest_sha256") != manifest["manifest_sha256"]
            or value.get("execution_lock_sha256") != lock.get("execution_lock_sha256")
            or value.get("model_infra_policy") != MODEL_INFRA_POLICY
            or slot.get("model") != model
            or not value.get("source_job_name")
            or not isinstance(value.get("provider_failure"), dict)
            or value["provider_failure"].get("classification")
            != "evidence_confirmed_provider_infra"
            or not isolatable_provider_failure(value["provider_failure"])
        ):
            raise V2Error("model hold differs from the frozen experiment or evidence")
        holds[model] = value
    return holds


def model_holds(directory, manifest):
    """Read-only status view, including frozen runs whose source now differs.

    This never authorizes execution: the executor independently validates the
    current source lock and uses read_model_holds with that verified lock.
    """
    root = Path(directory) / "model-holds"
    if not root.exists() and not root.is_symlink():
        return {}
    return read_model_holds(
        directory, manifest, read_json(Path(directory) / "execution-lock.json")
    )


def pause_model(directory, manifest, lock, slot, claim, payload):
    """Append-only first fault evidence; source/config changes require a new run."""
    path = _model_hold_path(directory, slot["model"])
    value = {
        "schema_version": 2,
        "kind": "smallowbench_v2_model_provider_hold",
        "status": "held",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "manifest_sha256": manifest["manifest_sha256"],
        "execution_lock_sha256": lock["execution_lock_sha256"],
        "model_infra_policy": MODEL_INFRA_POLICY,
        "model": slot["model"],
        "source_slot_id": slot["slot_id"],
        "source_job_name": claim.job_name,
        "source_claim_token": claim.token,
        "provider_failure": payload["provider_failure"],
        "automatic_retry": False,
        "automatic_provider_change": False,
        "cost_status": payload.get("cost_status", "unknown_reserve_retained"),
    }
    # write_atomic supplies a cross-process lock and an atomic replace. An
    # existing record is checked rather than overwritten or silently cleared.
    if not path.exists():
        try:
            write_atomic(path, value, overwrite=False)
        except FileExistsError:
            pass
    return read_model_holds(directory, manifest, lock)[slot["model"]]


def execute_experiment(directory, *, worker=0, workers=1, execute=False, limit=None):
    from release_v2_pipeline import job_config, stage_tasks
    from validate_v2_containers import docker_status

    directory = Path(directory).resolve()
    manifest = validate_manifest(directory)
    lock = validate_lock(directory, manifest)
    caps = validate_caps(manifest, worker, workers)
    model_policy = manifest["execution_policy"].get("model_infra_policy")
    if model_policy not in (None, MODEL_INFRA_POLICY):
        raise V2Error("unknown model infrastructure policy")
    held_models = read_model_holds(directory, manifest, lock)
    if limit is not None and (type(limit) is not int or limit < 1):
        raise V2Error("limit must be a positive number of admissions")
    slots = assigned_slots(manifest, worker, workers)
    if not execute:
        result = {
            "schema_version": 2,
            "mode": "execution-plan",
            "worker": worker,
            "workers": workers,
            "planned_worker_slots": len(slots),
            "stopped": (directory / "STOP").exists(),
            "execution_started": False,
            "model_calls": 0,
            "authorization_required": True,
            "held_models": sorted(held_models),
        }
        print(json.dumps(result))
        return 0
    if (directory / "STOP").exists():
        raise V2Error("STOP hold exists; no model execution admitted")
    validate_run_paths(directory, [slot["task"] for slot in manifest["schedule"]], task_root=Path(manifest["task_root"]))
    approval_sha = validate_authorization(directory, manifest, lock)
    if not docker_status().get("available") or not HARBOR.is_file():
        raise V2Error("the frozen local Linux Docker/Harbor runtime is unavailable")
    with process_lock(directory / f"worker-{worker}", timeout=1):
        # Validate staged bytes independently. This never edits the published task.
        with process_lock(directory / "staging", timeout=30):
            stage_tasks(manifest, directory)
        store = ClaimStore(
            directory / "claims.sqlite3", manifest_sha256=manifest["manifest_sha256"]
        )
        owner = f"{socket.gethostname()}:{os.getpid()}:{uuid.uuid4().hex}"
        visits = directory / "visits"
        launched = 0
        for slot in slots:
            held_models = read_model_holds(directory, manifest, lock)
            if slot["model"] in held_models:
                continue
            for _attempt in range(caps["max_visits_per_slot"]):
                if (directory / "STOP").exists() or (
                    limit is not None and launched >= limit
                ):
                    break
                # All code, task, model, runtime and approval bindings are rechecked
                # immediately before every admission and again before process launch.
                try:
                    validate_manifest(directory)
                    validate_lock(directory, manifest)
                    if validate_authorization(directory, manifest, lock) != approval_sha:
                        raise V2Error("execution authorization changed")
                    held_models = read_model_holds(directory, manifest, lock)
                    if slot["model"] in held_models:
                        break
                    claim = store.claim(
                        slot["slot_id"],
                        owner,
                        model=slot["model"],
                        serialize_model=True,
                        max_visits=caps["max_visits_per_slot"],
                        max_total_visits=caps["max_total_visits"],
                        reserve_usd=caps["visit_reserve_usd"],
                        budget_usd=caps["budget_usd"],
                    )
                except BaseException:
                    _hold(directory, "Admission safety/budget check failed; explicit review required.")
                    raise
                if claim is None:
                    break
                requested = False
                try:
                    config = job_config(manifest, slot, claim.job_name, directory)
                    from harbor.models.job.config import JobConfig

                    JobConfig.model_validate(config)
                    config_path = directory / "configs" / (claim.job_name + ".json")
                    config_path.parent.mkdir(parents=True, exist_ok=True)
                    write_atomic(config_path, config, overwrite=False)
                    provenance = {
                        **slot,
                        "config_sha256": file_hash(config_path),
                        "generated_config_sha256": file_hash(config_path),
                        "execution_lock_sha256": lock["execution_lock_sha256"],
                        "authorization_sha256": approval_sha,
                        "launch_state": "not_requested",
                    }
                    store.update_running(claim.token, owner, provenance)
                    store.publish_visit(claim, visits)
                    if (directory / "STOP").exists():
                        store.complete(
                            claim.token,
                            owner,
                            "aborted",
                            {"launch_not_requested": True},
                            counts_toward_cap=False,
                            charged_usd=0.0,
                        )
                        store.publish_visit(claim, visits)
                        break
                    validate_manifest(directory)
                    validate_lock(directory, manifest)
                    if (
                        validate_authorization(directory, manifest, lock)
                        != approval_sha
                    ):
                        raise V2Error("execution authorization changed before launch")
                    child_env = os.environ.copy()
                    # No implicit .env load. Keys must be deliberately supplied by
                    # the operator; only the host LLM client needs them.
                    child_env.update(
                        PYTHONPATH=str(ROOT), PYTHONUTF8="1", PYTHONIOENCODING="utf-8"
                    )
                    log = directory / "runner-logs" / (claim.job_name + ".log")
                    log.parent.mkdir(parents=True, exist_ok=True)
                    with log.open("xb") as stream:
                        requested = True
                        child = subprocess.Popen(
                            [str(HARBOR), "run", "--config", str(config_path)],
                            cwd=ROOT,
                            env=child_env,
                            stdout=stream,
                            stderr=subprocess.STDOUT,
                            creationflags=0x08000000 if os.name == "nt" else 0,
                        )
                        store.update_running(
                            claim.token,
                            owner,
                            {"child_pid": child.pid, "launch_state": "started"},
                        )
                        store.publish_visit(claim, visits)
                        while child.poll() is None:
                            if not store.heartbeat(claim.token, owner):
                                raise RuntimeError(
                                    "claim ownership lost; positive recovery evidence is required"
                                )
                            time.sleep(1)
                    payload, cost = classify_job(
                        directory / "jobs" / claim.job_name, slot["task"]
                    )
                    status = payload.pop("status")
                    actual_config = directory / "jobs" / claim.job_name / "config.json"
                    if actual_config.is_file() and not actual_config.is_symlink():
                        provenance["config_sha256"] = file_hash(actual_config)
                        provenance["executed_config_sha256"] = file_hash(actual_config)
                    elif status == "scored":
                        raise V2Error(
                            "scored job lacks its resolved Harbor configuration"
                        )
                    if (
                        model_policy == MODEL_INFRA_POLICY
                        and status == "infra"
                    ):
                        if isolatable_provider_failure(payload.get("provider_failure")):
                            pause_model(directory, manifest, lock, slot, claim, payload)
                        else:
                            _hold(directory, "Global account/permission or non-provider infrastructure fault; repair required.")
                    store.complete(
                        claim.token,
                        owner,
                        status,
                        {
                            **provenance,
                            **payload,
                            "launch_state": "exited",
                            "returncode": child.returncode,
                        },
                        charged_usd=cost,
                    )
                    store.publish_visit(claim, visits)
                    launched += 1
                    if status == "scored":
                        break  # Wrong answers and protocol failures are never retried.
                    if model_policy == MODEL_INFRA_POLICY:
                        break  # Provider faults hold only this model, never buy a retry.
                    cooldown = manifest["execution_policy"].get("cooldown_seconds", 0)
                    deadline = time.monotonic() + cooldown
                    while (
                        time.monotonic() < deadline
                        and not (directory / "STOP").exists()
                    ):
                        time.sleep(min(1, max(0, deadline - time.monotonic())))
                except BaseException:
                    if not requested:
                        store.complete(
                            claim.token,
                            owner,
                            "aborted",
                            {"launch_not_requested": True},
                            counts_toward_cap=False,
                            charged_usd=0.0,
                        )
                        store.publish_visit(claim, visits)
                    # A missing file or Python exception after Popen is not proof
                    # of process death, sandbox cleanup or a zero invoice.
                    _hold(
                        directory,
                        "Execution interrupted; do not auto-reap unresolved claims.",
                    )
                    raise
            if (directory / "STOP").exists() or (
                limit is not None and launched >= limit
            ):
                break
        print(
            json.dumps(
                {
                    "launched": launched,
                    "stopped": (directory / "STOP").exists(),
                    "unresolved_claims": len(store.active_claims()),
                    "held_models": sorted(read_model_holds(directory, manifest, lock)),
                }
            )
        )
    return 0
