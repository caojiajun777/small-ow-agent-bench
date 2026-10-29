"""Independent, fixed-provider reassessment of Qwen3.5-9B on the frozen RC2 bank.

No historical manifest, result, allowance, image or STOP is changed. Preparation
is offline. Execution uses the existing Harbor job/capture/verifier contract;
only affirmative transient provider failures can consume a bounded retry.
"""
from __future__ import annotations

import argparse
from collections import Counter
from copy import deepcopy
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import socket
import subprocess
import time
import uuid

import release_v2_pipeline as frozen
import release_v2_executor as legacy
from classify_timeouts import load_trials
from experiment_execution import ClaimStore
from ledger_io import process_lock, write_atomic

ROOT = frozen.ROOT
V2Error = frozen.V2Error
MODEL_ID = "qwen3.5-9b-primeintellect-bf16"
PARENT_MODEL = "qwen3.5-9b"
ROUTE = "primeintellect/bf16"
KIND = "smallowbench_v2_provider_reassessment"
PARENT_MANIFEST = "c9bebded890b7bfc49518efabadf81a8cbca35355d1fd1a1b300914849fb5fe1"
PARENT_LOCK = "8468e1368799141f67fb3b30200499be60dd9763766f18284c0ff799001c07df"
NEW_SOURCES = ("scripts/provider_reassessment_v2.py", "scripts/provider_reassessment_scoring_v2.py")
CAPS = {"budget_usd": None, "workers": 1, "max_visits_per_slot": 3,
        "max_total_visits": 186, "visit_reserve_usd": 3.5}
RETRY_POLICY = {"model_task_or_protocol_failure": "never", "infra_only": True,
                "max_attempts": 3, "transient_http_statuses": [408, 429, *range(500, 600)],
                "transport_exceptions": ["APIConnectionError", "ConnectError", "ReadError"],
                "typed_transient_exceptions": ["RateLimitError", "RateLimitException", "ServiceUnavailableError", "ServiceUnavailable", "InternalServerError"],
                "cooldown_seconds": [120, 300], "respect_saved_retry_after": True,
                "exhaustion": "hold", "automatic_provider_change": False}


def _file(path):
    path = Path(path).absolute()
    for entry in (path, *path.parents):
        if entry.is_symlink() or (entry.exists() and getattr(entry.stat(), "st_file_attributes", 0) & 0x400):
            raise V2Error("reparse/symlink evidence is forbidden")
    if not path.is_file():
        raise V2Error("required frozen file is absent: " + path.name)
    return path


def _tree_files(directory):
    directory = Path(directory)
    paths = []
    for path in directory.rglob("*"):
        if {"__pycache__", ".pytest_cache", ".git"}.intersection(path.parts) or path.suffix == ".pyc":
            continue
        if path.is_symlink() or getattr(path.stat(), "st_file_attributes", 0) & 0x400:
            raise V2Error("reparse/symlink in frozen tree")
        if path.is_file():
            paths.append(str(_file(path)))
    return sorted(paths)


def _write(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("x", encoding="utf-8", newline="\n") as stream:
        stream.write(_serialized(value))


def _serialized(value):
    return json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + "\n"


def _parent(directory, root, *, cold):
    directory = Path(directory).resolve()
    if directory != Path(root).resolve() / "experiments/smallowbench-v2/p2":
        raise V2Error("parent must be the unchanged original p2 experiment")
    manifest = frozen.validate_manifest(directory, root=root) if cold else frozen.read_json(_file(directory / "manifest.json"))
    lock = frozen.validate_lock(directory, manifest, root=root) if cold else frozen.read_json(_file(directory / "execution-lock.json"))
    if (manifest.get("manifest_sha256") != PARENT_MANIFEST
            or frozen.document_digest(manifest) != PARENT_MANIFEST
            or lock.get("execution_lock_sha256") != PARENT_LOCK
            or frozen.document_digest(lock, "execution_lock_sha256") != PARENT_LOCK):
        raise V2Error("original p2 identity differs")
    return manifest, lock


def model_from_parent(parent):
    model = deepcopy(parent["models"][PARENT_MODEL])
    model["route"] = ROUTE
    provider = model["agent_kwargs"]["llm_call_kwargs"]["extra_body"]["provider"]
    provider["order"], provider["only"] = [ROUTE], [ROUTE]
    if (provider.get("quantizations") != ["bf16"] or provider.get("allow_fallbacks") is not False
            or provider.get("require_parameters") is not True):
        raise V2Error("parent precision/no-fallback/parameter contract differs")
    return model


def publication_roster(parent):
    models = {name: deepcopy(value) for name, value in parent["models"].items() if name != PARENT_MODEL}
    models[MODEL_ID] = model_from_parent(parent)
    return {"policy": "seven_complete_parent_configurations_plus_independent_full_62_new_provider",
            "models": models, "excluded_parent_model": PARENT_MODEL,
            "parent_partial_observations_may_fill_new_provider_slots": False,
            "selection_frozen_before_new_provider_results": True}


def select_endpoint(catalog):
    data = catalog.get("data", catalog)
    if not isinstance(data, dict) or data.get("id") != "qwen/qwen3.5-9b":
        raise V2Error("catalog does not identify Qwen3.5-9B")
    endpoints = [row for row in data.get("endpoints", [])
                 if row.get("tag") == ROUTE]
    if len(endpoints) != 1:
        raise V2Error("catalog must contain exactly one fixed PrimeIntellect BF16 endpoint")
    endpoint = endpoints[0]
    if (endpoint.get("quantization") != "bf16" or type(endpoint.get("status")) is not int
            or endpoint["status"] != 0
            or not {"temperature", "top_p", "max_tokens", "reasoning"}.issubset(endpoint.get("supported_parameters", []))
            or not isinstance(endpoint.get("max_completion_tokens"), int)
            or endpoint["max_completion_tokens"] < 8192):
        raise V2Error("fixed endpoint is unavailable or cannot preserve frozen request settings")
    return endpoint


def _guard(parent, root, parent_directory, catalog_path):
    root = Path(root).resolve()
    paths = {str(_file(root / name)) for name in parent["source_hashes"]}
    paths.update(str(_file(root / name)) for name in NEW_SOURCES)
    paths.update(str(_file(Path(parent_directory) / name)) for name in ("manifest.json", "execution-lock.json"))
    paths.add(str(_file(catalog_path)))
    for key in ("task_bank", "preflight", "runtime", "models_source", "roster_reference"):
        binding = parent[key]
        paths.add(str(_file(binding["path"])))
        obj = frozen.read_binding(binding)
        for name in ("protected_source_hashes", "builder_sources", "source_hashes", "raw_artifacts_sha256", "run_safety_bindings"):
            for relative, sha in obj.get(name, {}).items():
                path = _file(root / relative)
                if frozen.file_hash(path) != sha:
                    raise V2Error("parent evidence/source bytes differ")
                paths.add(str(path))
    directories = [str(Path(parent["task_root"]).resolve()), str(root.parent / "harbor/src")]
    trees = {directory: _tree_files(directory) for directory in directories}
    paths.update(str(_file(root.parent / "harbor/uv.lock")) for _ in range(1))
    for entries in trees.values():
        paths.update(entries)
    task_root = Path(parent["task_root"]).resolve()
    fast_files = [name for name in sorted(paths) if not Path(name).is_relative_to(task_root)]
    return {"files": {name: frozen.file_hash(name) for name in sorted(paths)}, "trees": trees,
            "fast_files": fast_files, "runtime_tree": str(root.parent / "harbor/src")}


def _verify_guard(guard, *, full=False):
    for directory, entries in guard["trees"].items():
        if (full or directory == guard["runtime_tree"]) and _tree_files(directory) != entries:
            raise V2Error("frozen task/runtime file set changed")
    names = guard["files"] if full else guard["fast_files"]
    for name in names:
        sha = guard["files"][name]
        if frozen.file_hash(_file(name)) != sha:
            raise V2Error("bound source/evidence bytes changed: " + Path(name).name)


def _parent_binding(directory, parent, lock):
    return {"directory": str(Path(directory).resolve()), "manifest_sha256": parent["manifest_sha256"],
            "manifest_file_sha256": frozen.file_hash(Path(directory) / "manifest.json"),
            "execution_lock_sha256": lock["execution_lock_sha256"],
            "execution_lock_file_sha256": frozen.file_hash(Path(directory) / "execution-lock.json")}


def _lock(manifest, manifest_file_sha256):
    value = {"schema_version": 2, "kind": "smallowbench_v2_provider_execution_lock",
             "manifest_sha256": manifest["manifest_sha256"], "manifest_file_sha256": manifest_file_sha256,
             "parent": manifest["parent"], "source_hashes": manifest["source_hashes"],
             "guard_sha256": frozen.digest(manifest["integrity_guard"]),
             "model_configuration_sha256": frozen.digest(manifest["models"]),
             "monetary_cap_usd": None, "execution_authorized": False}
    value["execution_lock_sha256"] = frozen.document_digest(value, "execution_lock_sha256")
    return value


def prepare(directory, parent_directory, catalog_path, *, root=ROOT, write=False):
    root, directory = Path(root).resolve(), frozen.new_directory(directory, root)
    if directory.exists():
        raise V2Error("prepare never overwrites an existing experiment")
    parent, parent_lock = _parent(parent_directory, root, cold=True)
    catalog_path = _file(catalog_path)
    endpoint = select_endpoint(frozen.read_json(catalog_path))
    manifest = deepcopy(parent)
    manifest.update(kind=KIND, purpose="independent_provider_reassessment", experiment_id=directory.name,
                    directory=str(directory), repository_root=str(root), created_at=datetime.now(timezone.utc).isoformat(),
                    parent=_parent_binding(parent_directory, parent, parent_lock),
                    models={MODEL_ID: model_from_parent(parent)}, caps=deepcopy(CAPS), repetitions=1,
                    execution_policy={"budget_usd": None, "workers": 1, "max_infra_retries": 2,
                                      "execution_authorized": False, "model_infra_policy": legacy.MODEL_INFRA_POLICY},
                    retry_policy=deepcopy(RETRY_POLICY), execution_authorized=False,
                    publication_roster=publication_roster(parent),
                    catalog={**frozen.bound_file(catalog_path), "selected_endpoint_sha256": frozen.digest(endpoint)},
                    integrity_guard=_guard(parent, root, parent_directory, catalog_path))
    manifest["models_source"] = {"parent_model": PARENT_MODEL, "parent_manifest_sha256": PARENT_MANIFEST,
                                 "route_only_change": ROUTE}
    manifest["source_hashes"].update({name: frozen.file_hash(root / name) for name in NEW_SOURCES})
    manifest["schedule"] = frozen.frozen_schedule(manifest["models"], manifest["tasks"], 1)
    manifest["n_planned_trials"] = 62
    plan = ("# Independent PrimeIntellect BF16 reassessment\n\n"
            "Qwen3.5-9B; unchanged RC2 tasks/images/Harbor/CompactShell; 62 tasks × 1.\n"
            "The provider pin changes; all other model and evaluation settings are inherited exactly.\n"
            "Old Parasail observations remain separate. No monetary admission cap; unknown charges retain reserves.\n"
            "Only positive transient provider infra may retry, at most three visits per slot (186 total);\n"
            "cooldowns 120/300 seconds or longer saved Retry-After. Scored failures are final.\n"
            "Permanent/configuration faults and validity failures hold execution. No automatic route changes.\n")
    manifest["plan_sha256"] = hashlib.sha256(plan.encode()).hexdigest()
    manifest["manifest_sha256"] = frozen.document_digest(manifest)
    lock = _lock(manifest, hashlib.sha256(_serialized(manifest).encode()).hexdigest())
    from v2_paths import validate_run_paths
    validate_run_paths(directory, manifest["tasks"], task_root=Path(manifest["task_root"]))
    if write:
        directory.mkdir(parents=True, exist_ok=False)
        (directory / "STOP").write_text("Prepared only; explicit bound execution authorization required.\n", encoding="utf-8")
        (directory / "PLAN.md").write_text(plan, encoding="utf-8", newline="\n")
        _write(directory / "manifest.json", manifest)
        _write(directory / "execution-lock.json", lock)
        frozen.stage_tasks(manifest, directory, root=root)
    return manifest, lock


def validate_manifest(directory, *, root=ROOT, cold=False):
    directory, root = frozen.new_directory(directory, root), Path(root).resolve()
    manifest = frozen.read_json(_file(directory / "manifest.json"))
    if (manifest.get("kind") != KIND or manifest.get("schema_version") != 2
            or manifest.get("manifest_sha256") != frozen.document_digest(manifest)
            or manifest.get("directory") != str(directory) or manifest.get("repository_root") != str(root)
            or manifest.get("experiment_id") != directory.name or manifest.get("frozen") is not True
            or manifest.get("execution_authorized") is not False
            or manifest.get("purpose") != "independent_provider_reassessment"
            or manifest.get("caps") != CAPS or manifest.get("retry_policy") != RETRY_POLICY
            or manifest.get("repetitions") != 1 or manifest.get("n_planned_trials") != 62):
        raise V2Error("invalid independent provider reassessment manifest")
    parent, parent_lock = _parent(manifest["parent"]["directory"], root, cold=cold)
    if manifest["parent"] != _parent_binding(manifest["parent"]["directory"], parent, parent_lock):
        raise V2Error("parent byte bindings differ")
    changed = {"manifest_sha256", "kind", "purpose", "experiment_id", "directory", "repository_root", "created_at",
               "models", "models_source", "caps", "execution_policy", "retry_policy", "schedule", "n_planned_trials",
               "plan_sha256", "parent", "catalog", "integrity_guard", "source_hashes", "publication_roster"}
    if ({key: value for key, value in manifest.items() if key not in changed}
            != {key: value for key, value in parent.items() if key not in changed}
            or manifest["models"] != {MODEL_ID: model_from_parent(parent)}
            or manifest.get("publication_roster") != publication_roster(parent)
            or manifest["schedule"] != frozen.frozen_schedule(manifest["models"], parent["tasks"], 1)
            or manifest["execution_policy"] != {"budget_usd": None, "workers": 1, "max_infra_retries": 2,
                                                 "execution_authorized": False, "model_infra_policy": legacy.MODEL_INFRA_POLICY}
            or manifest["models_source"] != {"parent_model": PARENT_MODEL, "parent_manifest_sha256": PARENT_MANIFEST,
                                               "route_only_change": ROUTE}):
        raise V2Error("reassessment changed settings beyond the declared provider pin")
    expected_sources = {**parent["source_hashes"], **{name: frozen.file_hash(_file(root / name)) for name in NEW_SOURCES}}
    if manifest["source_hashes"] != expected_sources:
        raise V2Error("source binding does not exactly cover parent and new pipeline")
    for name, sha in expected_sources.items():
        if (cold or not (root / name).is_relative_to(Path(parent["task_root"]))) and frozen.file_hash(_file(root / name)) != sha:
            raise V2Error("frozen implementation changed")
    catalog = frozen.read_binding(manifest["catalog"])
    if frozen.digest(select_endpoint(catalog)) != manifest["catalog"]["selected_endpoint_sha256"]:
        raise V2Error("selected endpoint metadata differs")
    if hashlib.sha256(_file(directory / "PLAN.md").read_bytes()).hexdigest() != manifest["plan_sha256"]:
        raise V2Error("frozen plan changed")
    if cold and manifest["integrity_guard"] != _guard(parent, root, manifest["parent"]["directory"], manifest["catalog"]["path"]):
        raise V2Error("integrity guard omits or changes frozen dependencies")
    _verify_guard(manifest["integrity_guard"], full=cold)
    if cold and frozen.host_runtime_evidence(root) != parent["host_runtime_evidence"]:
        raise V2Error("host Python/packages/Harbor runtime differs")
    return manifest


def validate_lock(directory, manifest=None, *, root=ROOT):
    manifest = manifest or validate_manifest(directory, root=root)
    path = _file(Path(directory) / "execution-lock.json")
    value = frozen.read_json(path)
    if value != _lock(manifest, frozen.file_hash(_file(Path(directory) / "manifest.json"))):
        raise V2Error("provider execution lock differs from frozen manifest/configuration")
    return value


def authorization_document(manifest, lock, *, approval_reference):
    if not isinstance(approval_reference, str) or not approval_reference.strip():
        raise V2Error("an explicit user approval reference is required")
    return {"schema_version": 2, "kind": "smallowbench_v2_provider_execution_authorization",
            "approved_by_user": True, "approval_reference": approval_reference,
            "manifest_sha256": manifest["manifest_sha256"], "execution_lock_sha256": lock["execution_lock_sha256"],
            "model_configuration_sha256": frozen.digest(manifest["models"]), "source_hashes": manifest["source_hashes"],
            "monetary_cap_usd": None, "caps": deepcopy(CAPS), "retry_policy": deepcopy(RETRY_POLICY)}


def validate_authorization(directory, manifest, lock, *, root=ROOT):
    path = _file(Path(directory) / "authorization.json")
    value = frozen.read_json(path)
    if value != authorization_document(manifest, lock, approval_reference=value.get("approval_reference")):
        raise V2Error("execution authorization does not bind the exact provider reassessment and uncapped accounting")
    return frozen.file_hash(path)


def validate_current_task(manifest, slot, directory):
    task, spec = slot["task"], manifest["tasks"][slot["task"]]
    source, stage = Path(manifest["task_root"]) / task, Path(directory) / "staged-tasks" / task
    expected_text = frozen.staged_task_text(source / "task.toml",
        manifest["runtime_environment_evidence"]["image_digests"][task],
        manifest["runtime_environment_evidence"]["grader_image_digests"][task])
    if (frozen.staged_tree_digest(source, expected_text) != spec["staged_tree_sha256"]
            or frozen.file_hash(_file(stage / "task.toml")) != spec["staged_task_config_sha256"]
            or frozen.legacy_tree_digest(stage) != spec["staged_tree_sha256"]):
        raise V2Error("current task/source/staged bytes differ")


def validate_request_contract(job, model):
    """Inspect whitelisted request settings only; raw logs contain credentials."""
    trials = load_trials(Path(job))
    if len(trials) != 1:
        raise V2Error("ambiguous request audit trial")
    trial, raw = trials[0]
    trace = frozen.read_json(_file(trial / "agent/compact-shell-v2.json"))
    kwargs = model["agent_kwargs"]
    expected = {"temperature": kwargs["temperature"], "top_p": kwargs["llm_call_kwargs"]["top_p"],
                "max_tokens": kwargs["llm_call_kwargs"]["max_tokens"],
                "extra_body": kwargs["llm_call_kwargs"]["extra_body"]}
    receipts = []
    for call in trace.get("calls", []):
        if call.get("kind") != "api":
            continue
        name = call.get("response_log_path")
        if not isinstance(name, str) or Path(name).name != name or not re.fullmatch(r"turn-\d+(?:\.truncated)?\.txt", name):
            raise V2Error("completed API response lacks safe request receipt")
        path = trial / "agent" / name
        requires_response = (call.get("status") == "completed" or
                             call.get("status") == "budget_exceeded" and call.get("termination_reason") == "output_limit")
        if not path.exists() and not requires_response:
            continue
        path = _file(path)
        record = frozen.read_json(path)
        actual = record.get("optional_params", {})
        selected = {key: actual.get(key) for key in expected}
        if selected != expected:
            raise V2Error("actual provider request dropped/changed a frozen request parameter")
        response = record.get("original_response")
        if isinstance(response, str):
            try:
                response = json.loads(response)
            except (ValueError, TypeError):
                raise V2Error("provider response receipt is not valid JSON") from None
        if not isinstance(response, dict) or response.get("provider") != "PrimeIntellect":
            raise V2Error("completed API response does not positively identify frozen PrimeIntellect provider")
        receipts.append({"path": name, "sha256": frozen.file_hash(path), "provider": "PrimeIntellect"})
    return {"classification": "frozen_request_contract_verified", "receipts": receipts}


def classify_job(job, task, model):
    """Add explicit configuration-fault handling to the frozen classifier."""
    trials = load_trials(Path(job))
    if len(trials) != 1:
        raise V2Error("missing/ambiguous raw trial; never retry absence")
    trial, raw = trials[0]
    trace_path = trial / "agent/compact-shell-v2.json"
    trace = frozen.read_json(trace_path) if trace_path.is_file() else {}
    info = raw.get("exception_info") or {}
    message = info.get("exception_message") or ""
    config_error = (trace.get("termination_reason") == "api_error"
                    and (info.get("exception_type") == "BadRequestError"
                         or info.get("exception_type") == "APIStatusError" and re.search(r"\b400\b", message)))
    audit_error = False
    if trace:
        try:
            audit = validate_request_contract(job, model)
        except (ValueError, OSError, TypeError, KeyError):
            audit_error = True
    if config_error or audit_error:
        evidence = {"classification": "evidence_confirmed_provider_infra", "exception_type": "RequestContractError" if audit_error else info.get("exception_type"),
                    "http_status": None if audit_error else 400, "termination_reason": trace.get("termination_reason"),
                    "n_turns": trace.get("n_turns"), "completed_api_responses": sum(c.get("kind") == "api" and c.get("status") == "completed" for c in trace.get("calls", [])),
                    "raw_result_sha256": frozen.file_hash(trial / "result.json"), "trace_sha256": frozen.file_hash(trace_path)}
        return {"status": "infra", "termination": "infra", "reason": "provider_configuration_contract",
                "retry_classification": "configuration_fault_no_retry", "provider_failure": evidence,
                "cost_status": "unknown_reserve_retained"}, None
    payload, cost = legacy.classify_job(job, task)
    evidence = payload.get("provider_failure")
    if isinstance(evidence, dict):
        # Only an already persisted response-header value can extend backoff.
        # Exception text is neither printed nor interpreted as an invoice.
        headers = info.get("response_headers") or info.get("headers") or {}
        value = next((value for key, value in headers.items() if str(key).lower() == "retry-after"), None) if isinstance(headers, dict) else None
        if isinstance(value, (int, float, str)) and not isinstance(value, bool):
            try:
                seconds = float(value)
                if 0 <= seconds < float("inf"):
                    evidence["retry_after_seconds"] = seconds
            except ValueError:
                pass
    if trace:
        payload["request_contract"] = audit
    return payload, cost


def retryable(payload):
    evidence = payload.get("provider_failure") or {}
    status = evidence.get("http_status")
    return (payload.get("status") == "infra"
            and evidence.get("classification") == "evidence_confirmed_provider_infra"
            and (status in RETRY_POLICY["transient_http_statuses"]
                 or status is None and evidence.get("exception_type") in [*RETRY_POLICY["transport_exceptions"], *RETRY_POLICY["typed_transient_exceptions"]]))


def cooldown_seconds(visit, *, attempt=None):
    attempts = visit["visit"] if attempt is None else attempt
    if attempts not in (1, 2):
        return 0
    delay = RETRY_POLICY["cooldown_seconds"][attempts - 1]
    evidence = visit.get("provider_failure") or {}
    retry_after = evidence.get("retry_after_seconds")
    if isinstance(retry_after, (int, float)) and not isinstance(retry_after, bool) and 0 <= retry_after < float("inf"):
        delay = max(delay, retry_after)
    finished = datetime.fromisoformat(visit["finished_at"])
    return max(0, delay - (datetime.now(timezone.utc) - finished).total_seconds())


def _wait(directory, seconds):
    end = time.monotonic() + seconds
    while time.monotonic() < end:
        if (Path(directory) / "STOP").exists():
            return False
        time.sleep(min(1, end - time.monotonic()))
    return not (Path(directory) / "STOP").exists()


def _guard_admission(directory, manifest, lock, auth_sha, slot, *, root):
    if validate_manifest(directory, root=root) != manifest or validate_lock(directory, manifest, root=root) != lock:
        raise V2Error("run binding changed")
    if validate_authorization(directory, manifest, lock, root=root) != auth_sha:
        raise V2Error("execution authorization changed")
    validate_current_task(manifest, slot, directory)


def execute_experiment(directory, *, root=ROOT, execute=False, limit=None):
    directory, root = Path(directory).resolve(), Path(root).resolve()
    manifest = validate_manifest(directory, root=root, cold=True)
    lock = validate_lock(directory, manifest, root=root)
    auth_sha = validate_authorization(directory, manifest, lock, root=root)
    if not execute:
        return status(directory, root=root)
    if (directory / "STOP").exists():
        raise V2Error("STOP exists; this executor never removes holds")
    if limit is not None and (type(limit) is not int or limit <= 0):
        raise V2Error("execution limit must be positive")
    from v2_paths import validate_run_paths
    validate_run_paths(directory, manifest["tasks"], task_root=Path(manifest["task_root"]))
    with process_lock(directory / "worker-0", timeout=1):
        with process_lock(directory / "staging", timeout=30):
            frozen.stage_tasks(manifest, directory, root=root)
        store = ClaimStore(directory / "claims.sqlite3", manifest_sha256=manifest["manifest_sha256"])
        if store.active_claims():
            raise V2Error("active/unresolved claim exists; no reaping or duplicate launch")
        owner, launched = f"{socket.gethostname()}:{os.getpid()}:{uuid.uuid4().hex}", 0
        for slot in manifest["schedule"]:
            while not (directory / "STOP").exists() and (limit is None or launched < limit):
                prior = sorted((row for row in store.records() if row["slot_id"] == slot["slot_id"]), key=lambda row: row["visit"])
                if any(row["status"] == "scored" for row in prior):
                    break
                counted = [row for row in prior if row["counts_toward_cap"]]
                if counted:
                    last = counted[-1]
                    if len(counted) >= 3 or not retryable(last):
                        legacy._hold(directory, "Provider infra exhausted or permanent/configuration fault; explicit review required.")
                        break
                    if not _wait(directory, cooldown_seconds(last, attempt=len(counted))):
                        break
                try:
                    _guard_admission(directory, manifest, lock, auth_sha, slot, root=root)
                    claim = store.claim(slot["slot_id"], owner, model=MODEL_ID, serialize_model=True,
                                        max_visits=3, max_total_visits=186, reserve_usd=3.5, budget_usd=None)
                except BaseException:
                    legacy._hold(directory, "Admission binding/attempt-cap validation failed; explicit review required.")
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
                                  "launch_state": "not_requested"}
                    store.update_running(claim.token, owner, provenance)
                    store.publish_visit(claim, directory / "visits")
                    if (directory / "STOP").exists():
                        store.complete(claim.token, owner, "aborted", {"launch_not_requested": True}, counts_toward_cap=False, charged_usd=0)
                        store.publish_visit(claim, directory / "visits")
                        break
                    _guard_admission(directory, manifest, lock, auth_sha, slot, root=root)
                    env = {**os.environ, "PYTHONPATH": str(root), "PYTHONUTF8": "1", "PYTHONIOENCODING": "utf-8"}
                    log = directory / "runner-logs" / (claim.job_name + ".log")
                    log.parent.mkdir(parents=True, exist_ok=True)
                    with log.open("xb") as stream:
                        requested = True
                        child = subprocess.Popen([str(legacy.HARBOR), "run", "--config", str(config_path)], cwd=root, env=env,
                            stdout=stream, stderr=subprocess.STDOUT, creationflags=0x08000000 if os.name == "nt" else 0)
                        store.update_running(claim.token, owner, {"child_pid": child.pid, "launch_state": "started"})
                        store.publish_visit(claim, directory / "visits")
                        while child.poll() is None:
                            if not store.heartbeat(claim.token, owner):
                                raise V2Error("claim ownership lost; no automatic recovery")
                            time.sleep(1)
                    payload, cost = classify_job(directory / "jobs" / claim.job_name, slot["task"], manifest["models"][MODEL_ID])
                    visit_status = payload.pop("status")
                    actual_config = directory / "jobs" / claim.job_name / "config.json"
                    if actual_config.is_file():
                        provenance.update(config_sha256=frozen.file_hash(_file(actual_config)), executed_config_sha256=frozen.file_hash(actual_config))
                    elif visit_status == "scored":
                        raise V2Error("scored job lacks resolved Harbor configuration")
                    store.complete(claim.token, owner, visit_status,
                        {**provenance, **payload, "launch_state": "exited", "returncode": child.returncode}, charged_usd=cost)
                    receipt = store.publish_visit(claim, directory / "visits")
                    launched += 1
                    if visit_status == "scored":
                        from provider_reassessment_scoring_v2 import validate_scored_visit
                        try:
                            validate_scored_visit(frozen.read_json(receipt), manifest, directory, root=root)
                        except BaseException:
                            legacy._hold(directory, "Scored raw-artifact validity check failed; preserve artifacts and repair before continuing.")
                            raise
                        break
                    if not retryable({**payload, "status": visit_status}) or len(counted) + 1 >= 3:
                        legacy._hold(directory, "Provider failure is permanent/configuration-related or retry allowance exhausted.")
                        break
                except BaseException:
                    if not requested:
                        store.complete(claim.token, owner, "aborted", {"launch_not_requested": True}, counts_toward_cap=False, charged_usd=0)
                        store.publish_visit(claim, directory / "visits")
                    legacy._hold(directory, "Execution interrupted; preserve ownership and unknown charges; never auto-reap.")
                    raise
            if (directory / "STOP").exists() or limit is not None and launched >= limit:
                break
        return {"launched": launched, "stopped": (directory / "STOP").exists(), "unresolved_claims": len(store.active_claims()),
                "monetary_cap_enforced": False}


def status(directory, *, root=ROOT):
    manifest = validate_manifest(directory, root=root)
    lock = validate_lock(directory, manifest, root=root)
    rows, issues = frozen.read_visits(directory)
    active = frozen.active_claims(directory)
    auth = True
    try:
        validate_authorization(directory, manifest, lock, root=root)
    except (ValueError, OSError):
        auth = False
    states = dict(Counter(row.get("status", "invalid") for row in rows))
    reported = sum(row.get("charged_usd") or 0 for row in rows)
    unknown = sum(row.get("reserved_usd", 0) for row in rows if row.get("charged_usd") is None)
    return {"manifest_sha256": manifest["manifest_sha256"], "models": [MODEL_ID], "planned_slots": 62,
            "states": states, "active_claims": len(active), "issues": issues, "authorized": auth,
            "stopped": (Path(directory) / "STOP").exists(), "reported_usd": reported,
            "unknown_reserved_usd": unknown, "conservative_usd": reported + unknown, "monetary_cap_enforced": False}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    prep = sub.add_parser("prepare")
    prep.add_argument("--directory", required=True, type=Path)
    prep.add_argument("--parent-directory", default=ROOT / "experiments/smallowbench-v2/p2", type=Path)
    prep.add_argument("--catalog", required=True, type=Path)
    prep.add_argument("--write", action="store_true")
    for name in ("status", "execute"):
        command = sub.add_parser(name)
        command.add_argument("--directory", required=True, type=Path)
        if name == "execute":
            command.add_argument("--execute", action="store_true")
            command.add_argument("--limit", type=int)
    args = parser.parse_args(argv)
    if args.command == "prepare":
        manifest, lock = prepare(args.directory, args.parent_directory, args.catalog, write=args.write)
        result = {"manifest_sha256": manifest["manifest_sha256"], "execution_lock_sha256": lock["execution_lock_sha256"],
                  "written": args.write, "model_calls": 0, "docker_calls": 0}
    elif args.command == "execute":
        result = execute_experiment(args.directory, execute=args.execute, limit=args.limit)
    else:
        result = status(args.directory)
    print(json.dumps(result, ensure_ascii=False))


if __name__ == "__main__":
    main()
