"""Narrow request-audit amendment and continuation of the existing p3 run.

Original sources, claims, visits, reports and closure remain byte-identical.
One typed timeout is reclassified by a separately validated sidecar; it is
never rerun. Only the twelve unstarted slots use the child ownership ledger.
"""
from __future__ import annotations

import argparse
from collections import Counter
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import re
import socket
import sqlite3
import subprocess
import time
import uuid

import provider_reassessment_v2 as original
import release_v2_pipeline as frozen
import release_v2_executor as legacy
from classify_timeouts import load_trials
from experiment_execution import ClaimStore
from ledger_io import process_lock, write_atomic

ROOT, V2Error = frozen.ROOT, frozen.V2Error
MODEL_ID = original.MODEL_ID
MANIFEST_SHA = "e0266b57e1660adb20189fc57c880b0532ad0e43d2155e54147d29bb738261f8"
AMENDMENT_NAME = "execution-amendment-cancellation.json"
AUTHORIZATION_NAME = "execution-amendment-cancellation-authorization.json"
SIDECAR_NAME = "cancellation-reclassification.json"
CONTINUATION = "cancellation-continuation"
STOP_ARCHIVE = "STOP.cancellation-misclassification-20261029"
NEW_SOURCES = ("scripts/resume_provider_cancellation_v2.py", "scripts/provider_cancellation_scoring_v2.py")
KIND = "smallowbench_v2_typed_cancellation_execution_amendment"


def validate_request_contract(job, model):
    """Keep the frozen request settings; a typed pending cancellation is no response.

    A successful response still requires a positive PrimeIntellect receipt. The
    sole exception is the final cancelled API call in an AgentTimeoutError /
    trace.cancelled episode; its saved request settings must remain identical.
    Raw callback logs can contain credentials and are never returned or printed.
    """
    trials = load_trials(Path(job))
    if len(trials) != 1:
        raise V2Error("ambiguous request audit trial")
    trial, raw = trials[0]
    trace = frozen.read_json(original._file(trial / "agent/compact-shell-v2.json"))
    settings = model["agent_kwargs"]
    expected = {"temperature": settings["temperature"], "top_p": settings["llm_call_kwargs"]["top_p"],
                "max_tokens": settings["llm_call_kwargs"]["max_tokens"], "extra_body": settings["llm_call_kwargs"]["extra_body"]}
    calls = [call for call in trace.get("calls", []) if call.get("kind") == "api"]
    cancelled = [call for call in calls if call.get("status") == "cancelled"]
    typed_timeout = ((raw.get("exception_info") or {}).get("exception_type") == "AgentTimeoutError"
                     and trace.get("termination_reason") == "cancelled" and len(cancelled) == 1
                     and bool(calls) and cancelled[0] is calls[-1])
    typed_provider_error = legacy.provider_failure_evidence(raw, trace, trial)
    receipts = []
    for call in calls:
        name = call.get("response_log_path")
        if not isinstance(name, str) or Path(name).name != name or not re.fullmatch(r"turn-\d+(?:\.truncated)?\.txt", name):
            raise V2Error("API call lacks a safe frozen request-receipt path")
        path = trial / "agent" / name
        requires_response = (call.get("status") == "completed" or
            call.get("status") == "budget_exceeded" and call.get("termination_reason") == "output_limit")
        exempt = typed_timeout and call is calls[-1]
        provider_error = (typed_provider_error is not None and call.get("status") == "error" and call is calls[-1])
        if not path.exists() and not requires_response and not exempt:
            continue  # Preserve the preexisting failed-call absence rule.
        path = original._file(path)
        record = frozen.read_json(path)
        actual = record.get("optional_params", {})
        if {key: actual.get(key) for key in expected} != expected:
            raise V2Error("actual provider request dropped/changed a frozen request parameter")
        if exempt or provider_error:
            receipts.append({"path": name, "sha256": frozen.file_hash(path),
                "request_parameters_verified": True, "response_status": "typed_timeout_cancelled_pending_call" if exempt else "typed_provider_error_call"})
            continue
        response = record.get("original_response")
        if isinstance(response, str):
            try:
                response = json.loads(response)
            except (ValueError, TypeError):
                raise V2Error("provider response receipt is not valid JSON") from None
        if not isinstance(response, dict) or response.get("provider") != "PrimeIntellect":
            raise V2Error("API response does not positively identify frozen PrimeIntellect provider")
        receipts.append({"path": name, "sha256": frozen.file_hash(path), "provider": "PrimeIntellect"})
    return {"classification": "frozen_request_contract_verified", "receipts": receipts,
            **({"typed_timeout_cancellation_exception_applied": True} if typed_timeout else {})}


def classify_job(job, task, model):
    """Reuse the original raw grader classifier after the narrowly fixed audit."""
    trials = load_trials(Path(job))
    if len(trials) != 1:
        raise V2Error("missing/ambiguous raw trial; never retry absence")
    trial, raw = trials[0]
    trace_path = trial / "agent/compact-shell-v2.json"
    trace = frozen.read_json(trace_path) if trace_path.is_file() else {}
    info = raw.get("exception_info") or {}
    config_error = (trace.get("termination_reason") == "api_error" and
        (info.get("exception_type") == "BadRequestError" or info.get("exception_type") == "APIStatusError"
         and re.search(r"\b400\b", info.get("exception_message") or "")))
    audit_error, audit = False, None
    if trace:
        try:
            audit = validate_request_contract(job, model)
        except (ValueError, OSError, TypeError, KeyError):
            audit_error = True
    if config_error or audit_error:
        evidence = {"classification": "evidence_confirmed_provider_infra",
            "exception_type": "RequestContractError" if audit_error else info.get("exception_type"),
            "http_status": None if audit_error else 400, "termination_reason": trace.get("termination_reason"),
            "n_turns": trace.get("n_turns"), "completed_api_responses": sum(c.get("kind") == "api" and c.get("status") == "completed" for c in trace.get("calls", [])),
            "raw_result_sha256": frozen.file_hash(trial / "result.json"), "trace_sha256": frozen.file_hash(trace_path)}
        return {"status": "infra", "termination": "infra", "reason": "provider_configuration_contract",
            "retry_classification": "configuration_fault_no_retry", "provider_failure": evidence, "cost_status": "unknown_reserve_retained"}, None
    payload, cost = legacy.classify_job(job, task)
    if trace:
        payload["request_contract"] = audit
    evidence = payload.get("provider_failure")
    if isinstance(evidence, dict):
        headers = info.get("response_headers") or info.get("headers") or {}
        value = next((v for k, v in headers.items() if str(k).lower() == "retry-after"), None) if isinstance(headers, dict) else None
        try:
            if not isinstance(value, bool) and value is not None and 0 <= float(value) < float("inf"):
                evidence["retry_after_seconds"] = float(value)
        except (TypeError, ValueError):
            pass
    return payload, cost


def _base(directory, root, *, cold=False):
    directory, root = Path(directory).resolve(), Path(root).resolve()
    if directory != root / "experiments/smallowbench-v2/p3":
        raise V2Error("only the existing frozen p3 can receive this amendment")
    manifest = original.validate_manifest(directory, root=root, cold=cold)
    lock = original.validate_lock(directory, manifest, root=root)
    auth_sha = original.validate_authorization(directory, manifest, lock, root=root)
    if manifest["manifest_sha256"] != MANIFEST_SHA:
        raise V2Error("p3 manifest differs")
    return manifest, lock, auth_sha


def _read_database(directory):
    path = original._file(Path(directory) / "claims.sqlite3")
    with sqlite3.connect(path.as_uri() + "?mode=ro", uri=True) as connection:
        connection.execute("PRAGMA query_only=ON")
        connection.row_factory = sqlite3.Row
        rows = [ClaimStore._view(row) for row in connection.execute("SELECT * FROM visits ORDER BY started_at,token")]
        metadata = connection.execute("SELECT value FROM metadata WHERE key='manifest_sha256'").fetchone()
    if metadata is None or metadata[0] != MANIFEST_SHA or any(row["status"] in {"running", "unknown"} for row in rows):
        raise V2Error("baseline ledger has a different manifest or unresolved owner")
    return rows


def _snapshot(directory, manifest):
    visits, issues = frozen.read_visits(directory)
    rows = _read_database(directory)
    if (issues or Counter(v["status"] for v in visits) != {"scored": 49, "infra": 1}
            or len(rows) != len(visits) or sorted(rows, key=lambda v: v["job_name"]) != sorted(visits, key=lambda v: v["job_name"])):
        raise V2Error("amendment requires the unchanged 49-scored/one-infra ledger")
    selected = [row for row in visits if row["status"] == "infra"]
    correction = selected[0]
    if (correction["task"] != "testgen-anagram" or correction["model"] != MODEL_ID
            or correction["visit"] != 1 or correction.get("counts_toward_cap") is not True):
        raise V2Error("only the original testgen-anagram misclassification may be overlaid")
    job = directory / "jobs" / correction["job_name"]
    trials = load_trials(job)
    if len(trials) != 1:
        raise V2Error("correction lacks its unique raw trial")
    trial, raw = trials[0]
    trace = frozen.read_json(original._file(trial / "agent/compact-shell-v2.json"))
    if (raw.get("exception_info") or {}).get("exception_type") != "AgentTimeoutError" or trace.get("termination_reason") != "cancelled":
        raise V2Error("correction is not the affirmative agent-timeout cancellation")
    payload, cost = classify_job(job, correction["task"], manifest["models"][MODEL_ID])
    if payload.get("status") != "scored" or payload.get("termination") != "tle" or payload.get("atomic_correct") != 0:
        raise V2Error("correction does not independently reconstruct a legal zero-score TLE")
    visited = {row["slot_id"] for row in visits}
    remaining = [slot["slot_id"] for slot in manifest["schedule"] if slot["slot_id"] not in visited]
    if len(visited) != 50 or len(remaining) != 12:
        raise V2Error("amendment may admit only the twelve never-started slots")
    files = {path.name: frozen.file_hash(original._file(path)) for path in directory.iterdir()
             if path.is_file() and (path.suffix == ".json" or path.name in {"PLAN.md", "RESULTS.md", "claims.sqlite3"})}
    artifacts = {}
    for row in visits:
        job_name = frozen.safe_name(row["job_name"])
        for name in original._tree_files(directory / "jobs" / job_name):
            path = Path(name)
            artifacts[path.relative_to(directory).as_posix()] = frozen.file_hash(path)
        for area, suffix in (("configs", ".json"), ("runner-logs", ".log")):
            path = original._file(directory / area / (job_name + suffix))
            artifacts[path.relative_to(directory).as_posix()] = frozen.file_hash(path)
    return {"baseline_files_sha256": files,
        "baseline_artifact_files_sha256": artifacts,
        "baseline_visits_sha256": {row["job_name"]: frozen.file_hash(original._file(directory / "visits" / (row["job_name"] + ".json"))) for row in visits},
        "baseline_claims_file_sha256": frozen.file_hash(directory / "claims.sqlite3"),
        "baseline_counted_attempts": sum(row["counts_toward_cap"] is True for row in rows),
        "remaining_slot_ids": remaining,
        "correction": {"job_name": correction["job_name"], "source_visit_sha256": frozen.file_hash(directory / "visits" / (correction["job_name"] + ".json")),
            "raw_result_sha256": frozen.file_hash(trial / "result.json"), "trace_sha256": frozen.file_hash(trial / "agent/compact-shell-v2.json"),
            "slot_id": correction["slot_id"], "claim_token": correction["claim_token"]}}


def authorization_document(amendment, amendment_sha256, sidecar_sha256, *, approval_reference):
    if not isinstance(approval_reference, str) or not approval_reference.strip():
        raise V2Error("explicit user repair/continuation approval reference is required")
    return {"schema_version": 2, "kind": "smallowbench_v2_typed_cancellation_amendment_authorization",
        "approved_by_user": True, "approval_reference": approval_reference,
        "manifest_sha256": MANIFEST_SHA, "execution_amendment_sha256": amendment_sha256,
        "reclassification_sha256": sidecar_sha256, "source_hashes": amendment["source_hashes"],
        "remaining_slot_ids": amendment["remaining_slot_ids"], "monetary_cap_usd": None}


def prepare_amendment(directory, *, root=ROOT, approval_reference, write=False):
    directory, root = Path(directory).resolve(), Path(root).resolve()
    if any((directory / name).exists() for name in (AMENDMENT_NAME, AUTHORIZATION_NAME, SIDECAR_NAME, CONTINUATION)):
        raise V2Error("amendment preparation never overwrites existing evidence")
    manifest, lock, auth_sha = _base(directory, root, cold=True)
    snapshot = _snapshot(directory, manifest)
    stopped = original._file(directory / "STOP")
    amendment = {"schema_version": 2, "kind": KIND, "created_at": datetime.now(timezone.utc).isoformat(),
        "directory": str(directory), "manifest_sha256": MANIFEST_SHA,
        "execution_lock_sha256": lock["execution_lock_sha256"], "authorization_sha256": auth_sha,
        "source_hashes": {name: frozen.file_hash(original._file(root / name)) for name in NEW_SOURCES},
        "continuation_subdirectory": CONTINUATION, "original_stop_sha256": frozen.file_hash(stopped), "stop_archive_name": STOP_ARCHIVE,
        "repair_scope": "typed_agent_timeout_cancelled_pending_call_is_not_a_successful_response",
        "typed_provider_error_policy": "affirmative_typed_provider_failure_and_exact_saved_parameters_then_frozen_infra_classifier",
        "original_records_modified": False, "rerun_corrected_slot": False, "new_model_configuration": False,
        "caps": manifest["caps"], "retry_policy": manifest["retry_policy"], **snapshot}
    amendment["amendment_document_sha256"] = frozen.document_digest(amendment, "amendment_document_sha256")
    if write:
        original._write(directory / AMENDMENT_NAME, amendment)
        from provider_cancellation_scoring_v2 import build_reclassification
        sidecar = build_reclassification(directory, amendment, root=root)
        original._write(directory / SIDECAR_NAME, sidecar)
        auth = authorization_document(amendment, frozen.file_hash(directory / AMENDMENT_NAME), frozen.file_hash(directory / SIDECAR_NAME), approval_reference=approval_reference)
        original._write(directory / AUTHORIZATION_NAME, auth)
    return amendment


def validate_amendment(directory, *, root=ROOT, verify_artifacts=False):
    directory, root = Path(directory).resolve(), Path(root).resolve()
    amendment_path = original._file(directory / AMENDMENT_NAME)
    amendment = frozen.read_json(amendment_path)
    manifest = frozen.read_json(original._file(directory / "manifest.json"))
    if (directory != root / "experiments/smallowbench-v2/p3" or amendment.get("schema_version") != 2
            or amendment.get("kind") != KIND or amendment.get("directory") != str(directory)
            or amendment.get("manifest_sha256") != MANIFEST_SHA or manifest.get("manifest_sha256") != MANIFEST_SHA
            or frozen.document_digest(manifest) != MANIFEST_SHA
            or amendment.get("amendment_document_sha256") != frozen.document_digest(amendment, "amendment_document_sha256")
            or amendment.get("continuation_subdirectory") != CONTINUATION
            or amendment.get("original_records_modified") is not False or amendment.get("rerun_corrected_slot") is not False
            or amendment.get("new_model_configuration") is not False
            or amendment.get("caps") != manifest["caps"] or amendment.get("retry_policy") != manifest["retry_policy"]
            or amendment.get("baseline_counted_attempts") != 50 or len(amendment.get("remaining_slot_ids", [])) != 12
            or amendment.get("stop_archive_name") != STOP_ARCHIVE
            or amendment.get("typed_provider_error_policy") != "affirmative_typed_provider_failure_and_exact_saved_parameters_then_frozen_infra_classifier"
            or amendment.get("repair_scope") != "typed_agent_timeout_cancelled_pending_call_is_not_a_successful_response"):
        raise V2Error("execution amendment differs from its narrow fixed p3 scope")
    expected_sources = {name: frozen.file_hash(original._file(root / name)) for name in NEW_SOURCES}
    if amendment.get("source_hashes") != expected_sources:
        raise V2Error("amendment source bytes changed")
    for name, expected in amendment["baseline_files_sha256"].items():
        if Path(name).name != name or frozen.file_hash(original._file(directory / name)) != expected:
            raise V2Error("original p3 baseline file changed")
    if frozen.file_hash(original._file(directory / "claims.sqlite3")) != amendment["baseline_claims_file_sha256"]:
        raise V2Error("original claims ledger changed")
    if verify_artifacts:
        artifacts = amendment.get("baseline_artifact_files_sha256")
        if not isinstance(artifacts, dict) or not artifacts:
            raise V2Error("original job artifact byte bindings are absent")
        jobs = set(amendment["baseline_visits_sha256"])
        expected_paths = set()
        for job_name in jobs:
            frozen.safe_name(job_name)
            expected_paths.update(Path(name).relative_to(directory).as_posix() for name in original._tree_files(directory / "jobs" / job_name))
            expected_paths.update(f"{area}/{job_name}{suffix}" for area, suffix in (("configs", ".json"), ("runner-logs", ".log")))
        if set(artifacts) != expected_paths:
            raise V2Error("original artifact file set changed")
        for name, expected in artifacts.items():
            artifact_path = directory / name
            if not artifact_path.resolve().is_relative_to(directory):
                raise V2Error("unsafe original artifact path")
            if frozen.file_hash(original._file(artifact_path)) != expected:
                raise V2Error("original raw artifact bytes changed")
    visits, issues = frozen.read_visits(directory)
    expected_visits = amendment["baseline_visits_sha256"]
    if issues or {row["job_name"] for row in visits} != set(expected_visits) or len(visits) != 50:
        raise V2Error("original fifty visit exports changed")
    for job_name, expected in expected_visits.items():
        frozen.safe_name(job_name)
        if frozen.file_hash(original._file(directory / "visits" / (job_name + ".json"))) != expected:
            raise V2Error("original visit bytes changed")
    baseline = _read_database(directory)
    if sorted(baseline, key=lambda row: row["job_name"]) != sorted(visits, key=lambda row: row["job_name"]):
        raise V2Error("original ledger/export disagreement")
    planned = {slot["slot_id"] for slot in manifest["schedule"]}
    visited = {row["slot_id"] for row in visits}
    if (set(amendment["remaining_slot_ids"]) != planned - visited or len(set(amendment["remaining_slot_ids"])) != 12
            or amendment["correction"]["slot_id"] in amendment["remaining_slot_ids"]):
        raise V2Error("remaining slots include a started/corrected task")
    stop_receipt = directory / STOP_ARCHIVE
    if not stop_receipt.exists():
        stop_receipt = directory / "STOP"
    if frozen.file_hash(original._file(stop_receipt)) != amendment["original_stop_sha256"]:
        raise V2Error("original erroneous STOP lacks its unchanged archived receipt")
    sha = frozen.file_hash(amendment_path)
    auth = frozen.read_json(original._file(directory / AUTHORIZATION_NAME))
    sidecar_sha = frozen.file_hash(original._file(directory / SIDECAR_NAME))
    if auth != authorization_document(amendment, sha, sidecar_sha, approval_reference=auth.get("approval_reference")):
        raise V2Error("amendment authorization is absent or differs")
    if amendment["authorization_sha256"] != frozen.file_hash(original._file(directory / "authorization.json")):
        raise V2Error("original authorization changed")
    if amendment["execution_lock_sha256"] != frozen.read_json(original._file(directory / "execution-lock.json"))["execution_lock_sha256"]:
        raise V2Error("amendment references a different original execution lock")
    return amendment, sha


def _guard(directory, manifest, lock, auth_sha, amendment_sha, slot, *, root):
    original._guard_admission(directory, manifest, lock, auth_sha, slot, root=root)
    amendment, current_sha = validate_amendment(directory, root=root)
    if current_sha != amendment_sha or slot["slot_id"] not in amendment["remaining_slot_ids"]:
        raise V2Error("admission no longer matches the exact twelve-slot amendment")


def execute_experiment(directory, *, root=ROOT, execute=False, limit=None):
    directory, root = Path(directory).resolve(), Path(root).resolve()
    manifest, lock, auth_sha = _base(directory, root, cold=True)
    amendment, amendment_sha = validate_amendment(directory, root=root, verify_artifacts=True)
    from provider_cancellation_scoring_v2 import validate_reclassification, validate_scored_visit
    virtual = validate_reclassification(directory, amendment, root=root)
    if virtual["slot_id"] != amendment["correction"]["slot_id"] or virtual["status"] != "scored":
        raise V2Error("corrected slot has no independently accepted overlay")
    if not execute:
        return {"remaining_slots": 12, "model_calls": 0, "stopped": (directory / "STOP").exists()}
    if (directory / "STOP").exists():
        raise V2Error("STOP remains authoritative; only the operator archives/releases the new erroneous hold")
    if limit is not None and (type(limit) is not int or limit <= 0):
        raise V2Error("limit must be positive")
    child_root = directory / CONTINUATION
    with process_lock(directory / "worker-0", timeout=1):
        with process_lock(directory / "staging", timeout=30):
            frozen.stage_tasks(manifest, directory, root=root)
        if (child_root / "claims.sqlite3").exists():
            original._file(child_root / "claims.sqlite3")
        store = ClaimStore(child_root / "claims.sqlite3", manifest_sha256=MANIFEST_SHA)
        if store.active_claims() or frozen.active_claims(directory):
            raise V2Error("active original/child ownership exists; never reap or duplicate launch")
        owner, launched = f"{socket.gethostname()}:{os.getpid()}:{uuid.uuid4().hex}", 0
        for slot in manifest["schedule"]:
            if slot["slot_id"] not in amendment["remaining_slot_ids"]:
                continue  # Preserve 49 scored slots and the validated TLE sidecar without another request.
            while not (directory / "STOP").exists() and (limit is None or launched < limit):
                prior = sorted((row for row in store.records() if row["slot_id"] == slot["slot_id"]), key=lambda row: row["visit"])
                if any(row["status"] == "scored" for row in prior):
                    break
                counted = [row for row in prior if row["counts_toward_cap"]]
                if counted:
                    last = counted[-1]
                    if len(counted) >= manifest["caps"]["max_visits_per_slot"] or not original.retryable(last):
                        legacy._hold(directory, "Permanent/configuration provider fault or transient retry allowance exhausted.")
                        break
                    if not original._wait(directory, original.cooldown_seconds(last, attempt=len(counted))):
                        break
                try:
                    _guard(directory, manifest, lock, auth_sha, amendment_sha, slot, root=root)
                    claim = store.claim(slot["slot_id"], owner, model=MODEL_ID, serialize_model=True, max_visits=manifest["caps"]["max_visits_per_slot"],
                        max_total_visits=manifest["caps"]["max_total_visits"] - amendment["baseline_counted_attempts"],
                        reserve_usd=manifest["caps"]["visit_reserve_usd"], budget_usd=None)
                except BaseException:
                    legacy._hold(directory, "Cancellation amendment admission/source/attempt-cap guard failed.")
                    raise
                if claim is None:
                    break
                requested = False
                try:
                    config = frozen.job_config(manifest, slot, claim.job_name, directory)
                    from harbor.models.job.config import JobConfig
                    JobConfig.model_validate(config)
                    config_path = directory / "configs" / (claim.job_name + ".json")
                    write_atomic(config_path, config, overwrite=False)
                    provenance = {**slot, "config_sha256": frozen.file_hash(config_path), "generated_config_sha256": frozen.file_hash(config_path),
                        "execution_lock_sha256": lock["execution_lock_sha256"], "authorization_sha256": auth_sha,
                        "execution_amendment_sha256": amendment_sha, "launch_state": "not_requested"}
                    store.update_running(claim.token, owner, provenance)
                    store.publish_visit(claim, child_root / "visits")
                    if (directory / "STOP").exists():
                        store.complete(claim.token, owner, "aborted", {"launch_not_requested": True}, counts_toward_cap=False, charged_usd=0)
                        store.publish_visit(claim, child_root / "visits")
                        break
                    _guard(directory, manifest, lock, auth_sha, amendment_sha, slot, root=root)
                    env = {**os.environ, "PYTHONPATH": str(root), "PYTHONUTF8": "1", "PYTHONIOENCODING": "utf-8"}
                    log = directory / "runner-logs" / (claim.job_name + ".log")
                    log.parent.mkdir(parents=True, exist_ok=True)
                    with log.open("xb") as stream:
                        requested = True
                        child = subprocess.Popen([str(legacy.HARBOR), "run", "--config", str(config_path)], cwd=root, env=env,
                            stdout=stream, stderr=subprocess.STDOUT, creationflags=0x08000000 if os.name == "nt" else 0)
                        store.update_running(claim.token, owner, {"child_pid": child.pid, "launch_state": "started"})
                        store.publish_visit(claim, child_root / "visits")
                        while child.poll() is None:
                            if not store.heartbeat(claim.token, owner):
                                raise V2Error("child claim ownership lost; no automatic recovery")
                            time.sleep(1)
                    payload, cost = classify_job(directory / "jobs" / claim.job_name, slot["task"], manifest["models"][MODEL_ID])
                    visit_status = payload.pop("status")
                    actual_config = directory / "jobs" / claim.job_name / "config.json"
                    if actual_config.is_file():
                        provenance.update(config_sha256=frozen.file_hash(original._file(actual_config)), executed_config_sha256=frozen.file_hash(actual_config))
                    elif visit_status == "scored":
                        raise V2Error("scored task lacks its resolved Harbor config")
                    store.complete(claim.token, owner, visit_status,
                        {**provenance, **payload, "launch_state": "exited", "returncode": child.returncode}, charged_usd=cost)
                    receipt = store.publish_visit(claim, child_root / "visits")
                    launched += 1
                    if visit_status == "scored":
                        validate_scored_visit(frozen.read_json(receipt), manifest, directory, root=root)
                        break  # Wrong answers, TLE and protocol/budget failures are final.
                    if not original.retryable({**payload, "status": visit_status}) or len(counted) + 1 >= 3:
                        legacy._hold(directory, "Provider fault is permanent/configuration-related or retries are exhausted.")
                        break
                except BaseException:
                    if not requested:
                        store.complete(claim.token, owner, "aborted", {"launch_not_requested": True}, counts_toward_cap=False, charged_usd=0)
                        store.publish_visit(claim, child_root / "visits")
                    legacy._hold(directory, "Amended execution/real-artifact validation interrupted; preserve all ownership and unknown fees.")
                    raise
            if (directory / "STOP").exists() or limit is not None and launched >= limit:
                break
        return {"launched": launched, "stopped": (directory / "STOP").exists(), "unresolved_claims": len(store.active_claims()),
            "baseline_records_modified": False, "corrected_task_rerun": False, "monetary_cap_enforced": False}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    prep = sub.add_parser("prepare")
    prep.add_argument("--directory", required=True, type=Path)
    prep.add_argument("--approval-reference", required=True)
    prep.add_argument("--write", action="store_true")
    run = sub.add_parser("execute")
    run.add_argument("--directory", required=True, type=Path)
    run.add_argument("--execute", action="store_true")
    run.add_argument("--limit", type=int)
    args = parser.parse_args(argv)
    if args.command == "prepare":
        amendment = prepare_amendment(args.directory, approval_reference=args.approval_reference, write=args.write)
        result = {"written": args.write, "remaining_slots": len(amendment["remaining_slot_ids"]), "model_calls": 0}
    else:
        result = execute_experiment(args.directory, execute=args.execute, limit=args.limit)
    print(json.dumps(result, ensure_ascii=False))


if __name__ == "__main__":
    main()
