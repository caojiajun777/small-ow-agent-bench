"""One separately approved retry of the named RC2 HTTP-429 infrastructure slot.

The default command only reads readiness. Execution never clears a hold and is
possible only after all 32 previously unvisited slots have closed. It preserves
the original counted infrastructure attempt and creates at most one new visit.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import socket
import sqlite3
import subprocess
import time
import uuid

from analyze_release_v2 import normalized_job_config, validate_trace
from ledger_io import process_lock, write_atomic
import release_v2_fee_waiver_executor as frozen
from release_v2_pipeline import ROOT, V2Error, file_hash, job_config, legacy_tree_digest, read_json
from v2_paths import validate_run_paths

MODEL = "qwen3.5-9b"
TASK = "repro-float-cents"
SLOT = MODEL + "/" + TASK + "/r1"
SOURCE_JOB = "visit-df406e109c1849029c0f66e0304fc082"
RECOVERY = "provider-recovery-20261029"
PROPOSAL = RECOVERY + "/single-infra-retry-proposal.json"
APPROVAL = RECOVERY + "/single-infra-retry-approval.json"
RUNNER = "scripts/retry_v2_single_infra.py"
APPROVAL_KIND = "smallowbench_v2_single_infra_retry_approval"


def regular(path, root):
    """Reject links/reparse points in all evidence components under this root."""
    path, root = Path(path).absolute(), Path(root).absolute()
    try:
        relative = path.relative_to(root)
    except ValueError as error:
        raise V2Error("retry evidence is outside its run") from error
    current = root
    for component in (None, *relative.parts):
        if component is not None:
            current /= component
        if (current.is_symlink()
                or getattr(current.stat(), "st_file_attributes", 0) & 0x400):
            raise V2Error("retry evidence must not use links or reparse points")
    if not path.is_file():
        raise V2Error("retry evidence must be a regular file")
    return path


def source_infra(directory, manifest, proposal):
    source_path = regular(directory / "visits" / (SOURCE_JOB + ".json"), directory)
    if file_hash(source_path) != proposal.get("source_visit_sha256"):
        raise V2Error("original infrastructure visit changed")
    visit = read_json(source_path)
    if (visit.get("job_name") != SOURCE_JOB or visit.get("slot_id") != SLOT
            or visit.get("model") != MODEL or visit.get("task") != TASK
            or visit.get("status") != "infra" or visit.get("visit") != 1
            or visit.get("counts_toward_cap") is not True
            or visit.get("manifest_sha256") != manifest["manifest_sha256"]):
        raise V2Error("retry source is not the original counted infrastructure attempt")
    source_job = directory / "jobs" / SOURCE_JOB
    results = list(source_job.glob("*/result.json"))
    if len(results) != 1:
        raise V2Error("retry source needs exactly one original raw trial")
    raw_path = regular(results[0], directory)
    trace_path = regular(raw_path.parent / "agent" / "compact-shell-v2.json", directory)
    if (file_hash(raw_path) != proposal.get("source_raw_result_sha256")
            or file_hash(trace_path) != proposal.get("source_trace_sha256")):
        raise V2Error("original 429 raw evidence changed")
    raw = read_json(raw_path)
    trace = validate_trace(read_json(trace_path), TASK)
    evidence = frozen.provider_failure_evidence(raw, trace, raw_path.parent)
    if (not evidence or evidence.get("http_status") != 429
            or evidence.get("exception_type") != "RateLimitError"
            or evidence.get("completed_api_responses") != 3
            or trace.get("n_turns") != 3 or trace.get("n_shell") != 3):
        raise V2Error("retry requires the named positive HTTP-429 evidence")
    classified, _cost = frozen.classify_job(source_job, TASK)
    if classified.get("status") != "infra" or classified.get("provider_failure") != evidence:
        raise V2Error("original retry source no longer classifies as provider infrastructure")
    slot = next(row for row in manifest["schedule"] if row["slot_id"] == SLOT)
    expected = job_config(manifest, slot, SOURCE_JOB, directory)
    generated = regular(directory / "configs" / (SOURCE_JOB + ".json"), directory)
    executed = regular(source_job / "config.json", directory)
    if (file_hash(generated) != visit.get("generated_config_sha256")
            or file_hash(executed) != visit.get("executed_config_sha256")
            or file_hash(executed) != visit.get("config_sha256")
            or read_json(generated) != expected
            or normalized_job_config(read_json(executed)) != normalized_job_config(expected)):
        raise V2Error("original infrastructure configuration differs from the frozen task")
    expected_agent = expected["agents"][0]
    if (raw.get("task_name", "").rsplit("/", 1)[-1] != TASK
            or any(raw.get("config", {}).get("agent", {}).get(key) != value
                   for key, value in expected_agent.items())):
        raise V2Error("original raw model configuration differs from the frozen task")
    return visit


def validate_proposal(directory, manifest, lock, *, root=ROOT):
    directory, root = Path(directory).resolve(), Path(root).resolve()
    path = regular(directory / PROPOSAL, directory)
    proposal = read_json(path)
    fee_sha = frozen.validate_fee_waiver(directory, manifest, lock, root=root)
    expected = {
        "schema_version": 1,
        "kind": "smallowbench_v2_single_infra_retry_proposal",
        "execution_authorized": False,
        "approved_by_user": False,
        "manifest_sha256": manifest["manifest_sha256"],
        "execution_lock_sha256": lock["execution_lock_sha256"],
        "fee_waiver_sha256": fee_sha,
        "slot_id": SLOT,
        "source_job_name": SOURCE_JOB,
        "model_configuration": manifest["models"][MODEL],
        "reason": "evidence_confirmed_http_429",
        "max_new_attempts": 1,
        "slot_max_visits": 2,
        "global_max_counted_visits": 497,
        "require_counted_visits_before_launch": 496,
        "require_no_active_claims": True,
        "preserve_original_infra_record": True,
        "allow_retry_of_scored_slots": False,
        "change_provider_or_model": False,
        "monetary_cap_enforced": False,
    }
    if (any(type(proposal.get(key)) is not type(value) or proposal.get(key) != value
            for key, value in expected.items())
            or manifest["caps"].get("max_total_visits") != 496
            or manifest["caps"].get("max_visits_per_slot") != 1
            or manifest["caps"].get("workers") != 4
            or len(manifest["schedule"]) != 496):
        raise V2Error("proposal must authorize only the named single infrastructure exception")
    source_infra(directory, manifest, proposal)
    return proposal, file_hash(path)


def validate_approval(directory, manifest, lock, proposal_sha, *, root=ROOT):
    directory, root = Path(directory).resolve(), Path(root).resolve()
    path = regular(directory / APPROVAL, directory)
    value = read_json(path)
    original_sha = frozen.validate_authorization(directory, manifest, lock)
    fee_sha = frozen.validate_fee_waiver(directory, manifest, lock, root=root)
    expected = {
        "schema_version": 1, "kind": APPROVAL_KIND, "approved_by_user": True,
        "proposal_sha256": proposal_sha,
        "runner_sha256": file_hash(regular(root / RUNNER, root)),
        "manifest_sha256": manifest["manifest_sha256"],
        "execution_lock_sha256": lock["execution_lock_sha256"],
        "original_authorization_sha256": original_sha,
        "fee_waiver_sha256": fee_sha,
    }
    if any(type(value.get(key)) is not type(wanted) or value.get(key) != wanted
           for key, wanted in expected.items()):
        raise V2Error("separate single-infra approval is missing or incorrectly bound")
    return file_hash(path), original_sha, fee_sha


def database_readiness(directory, manifest, *, claim=None, owner=None):
    """Read only; all 32 initial gaps must close before this exception can run."""
    directory = Path(directory)
    database = regular(directory / "claims.sqlite3", directory)
    with sqlite3.connect(database.resolve().as_uri() + "?mode=ro", uri=True) as connection:
        connection.row_factory = sqlite3.Row
        connection.execute("BEGIN")
        rows = [dict(row) for row in connection.execute("SELECT * FROM visits")]
        blocked = connection.execute("SELECT COUNT(*) FROM blocked_slots").fetchone()[0]
        identity = connection.execute("SELECT value FROM metadata WHERE key='manifest_sha256'").fetchone()
    expected_slots = {row["slot_id"] for row in manifest["schedule"]}
    initial = [row for row in rows if claim is None or row["token"] != claim.token]
    source = [row for row in initial if row["slot_id"] == SLOT]
    others = [row for row in initial if row["slot_id"] != SLOT]
    reasons = []
    if identity is None or identity[0] != manifest["manifest_sha256"]:
        reasons.append("claim database belongs to another manifest")
    if blocked:
        reasons.append("quarantined slots remain")
    if len(initial) != 496 or sum(row["counts_toward_cap"] for row in initial) != 496:
        reasons.append("the 32 original unvisited slots have not all closed at counted total496")
    if (len(others) != 495 or any(row["status"] != "scored" for row in others)
            or {row["slot_id"] for row in others} != expected_slots - {SLOT}):
        reasons.append("all other495 frozen slots must have exactly one scored visit")
    if (len(source) != 1 or source[0]["job_name"] != SOURCE_JOB
            or source[0]["status"] != "infra" or source[0]["visit"] != 1
            or source[0]["counts_toward_cap"] != 1):
        reasons.append("target must have only its original counted infrastructure visit")
    if claim is None:
        if any(row["status"] in ("running", "unknown") for row in rows):
            reasons.append("active or unresolved claims remain")
    else:
        active = [row for row in rows if row["status"] in ("running", "unknown")]
        if (len(rows) != 497 or len(active) != 1 or active[0]["token"] != claim.token
                or active[0]["owner"] != owner or active[0]["slot_id"] != SLOT
                or active[0]["visit"] != 2 or active[0]["status"] != "running"):
            reasons.append("the only active claim must be this approved second visit")
    return {"ready": not reasons, "reasons": reasons,
            "counted_total": sum(row["counts_toward_cap"] for row in rows),
            "existing_visits": len(rows)}


def _runtime_available():
    from validate_v2_containers import docker_status

    return frozen.HARBOR.is_file() and docker_status().get("available")


def _validate_job_config(config):
    from harbor.models.job.config import JobConfig

    JobConfig.model_validate(config)


def validate_staged_task(directory, manifest):
    """Read the actual run copy before admission and before any paid launch."""
    staged = directory / "staged-tasks" / TASK
    task_config = regular(staged / "task.toml", directory)
    for path in staged.rglob("*"):
        if (path.is_symlink() or getattr(path.stat(), "st_file_attributes", 0) & 0x400):
            raise V2Error("single retry staged task contains a link or reparse point")
    expected = manifest["tasks"][TASK]
    if (file_hash(task_config) != expected["staged_task_config_sha256"]
            or legacy_tree_digest(staged) != expected["staged_tree_sha256"]):
        raise V2Error("single retry staged task has drifted; no model launch")


def _validate_execution(directory, *, root=ROOT, claim=None, owner=None):
    manifest = frozen.validate_manifest(directory, root=root)
    lock = frozen.validate_lock(directory, manifest, root=root)
    frozen.validate_caps(manifest, 1, 4)
    proposal, proposal_sha = validate_proposal(directory, manifest, lock, root=root)
    approval_sha, auth_sha, fee_sha = validate_approval(directory, manifest, lock, proposal_sha, root=root)
    if (directory / "STOP").exists():
        raise V2Error("STOP hold remains; single retry cannot resume")
    if frozen.read_model_holds(directory, manifest, lock):
        raise V2Error("provider hold remains; single retry never clears it")
    validate_staged_task(directory, manifest)
    state = database_readiness(directory, manifest, claim=claim, owner=owner)
    if not state["ready"]:
        raise V2Error("single retry not ready: " + "; ".join(state["reasons"]))
    return manifest, lock, proposal_sha, approval_sha, auth_sha, fee_sha


def execute_single_retry(directory, *, execute=False, root=ROOT):
    directory, root = Path(directory).resolve(), Path(root).resolve()
    if not execute:
        manifest = frozen.validate_manifest(directory, root=root)
        lock = frozen.validate_lock(directory, manifest, root=root)
        _proposal, proposal_sha = validate_proposal(directory, manifest, lock, root=root)
        state = database_readiness(directory, manifest)
        return {"mode": "read_only_single_infra_retry_plan", "slot_id": SLOT,
                "proposal_sha256": proposal_sha, "separate_approval_required": True,
                "STOP_present": (directory / "STOP").exists(),
                "provider_holds": sorted(frozen.read_model_holds(directory, manifest, lock)),
                "model_calls": 0, **state}
    bindings = _validate_execution(directory, root=root)
    manifest, lock, proposal_sha, approval_sha, auth_sha, fee_sha = bindings
    validate_run_paths(directory, [TASK], task_root=Path(manifest["task_root"]))
    if not _runtime_available():
        raise V2Error("frozen Docker/Harbor runtime unavailable")
    # The same lock serializes the original model worker and this exception.
    with process_lock(directory / "worker-1", timeout=1):
        if _validate_execution(directory, root=root) != bindings:
            raise V2Error("single retry approval or frozen identity changed")
        store = frozen.ClaimStore(directory / "claims.sqlite3", manifest_sha256=manifest["manifest_sha256"])
        owner = f"{socket.gethostname()}:{os.getpid()}:{uuid.uuid4().hex}"
        claim = store.claim(SLOT, owner, model=MODEL, serialize_model=True,
                            max_visits=2, max_total_visits=497,
                            reserve_usd=manifest["caps"]["visit_reserve_usd"], budget_usd=None)
        if claim is None:
            raise V2Error("single retry was already consumed or target is not eligible")
        slot = next(row for row in manifest["schedule"] if row["slot_id"] == SLOT)
        provenance = {**slot, "execution_lock_sha256": lock["execution_lock_sha256"],
                      "authorization_sha256": auth_sha, "fee_waiver_sha256": fee_sha,
                      "single_infra_retry_approval_sha256": approval_sha,
                      "single_infra_retry_proposal_sha256": proposal_sha,
                      "retry_source_job_name": SOURCE_JOB, "launch_state": "not_requested"}
        requested = False
        try:
            config = job_config(manifest, slot, claim.job_name, directory)
            _validate_job_config(config)
            config_path = directory / "configs" / (claim.job_name + ".json")
            write_atomic(config_path, config, overwrite=False)
            provenance.update(config_sha256=file_hash(config_path), generated_config_sha256=file_hash(config_path))
            store.update_running(claim.token, owner, provenance)
            store.publish_visit(claim, directory / "visits")
            if _validate_execution(directory, root=root, claim=claim, owner=owner) != bindings:
                raise V2Error("single retry approval or sources changed before launch")
            child_env = os.environ.copy()
            child_env.update(PYTHONPATH=str(root), PYTHONUTF8="1", PYTHONIOENCODING="utf-8")
            log = directory / "runner-logs" / (claim.job_name + ".log")
            log.parent.mkdir(parents=True, exist_ok=True)
            with log.open("xb") as stream:
                # Once Popen is requested, an exception is never proof of a free,
                # dead or cleaned trial. Leave the claim unresolved on ambiguity.
                requested = True
                child = subprocess.Popen([str(frozen.HARBOR), "run", "--config", str(config_path)],
                                         cwd=root, env=child_env, stdout=stream, stderr=subprocess.STDOUT,
                                         creationflags=0x08000000 if os.name == "nt" else 0)
                store.update_running(claim.token, owner, {"child_pid": child.pid, "launch_state": "started"})
                store.publish_visit(claim, directory / "visits")
                while child.poll() is None:
                    if not store.heartbeat(claim.token, owner):
                        raise RuntimeError("single retry claim ownership lost; no automatic reclamation")
                    time.sleep(1)
            payload, cost = frozen.classify_job(directory / "jobs" / claim.job_name, TASK)
            status = payload.pop("status")
            actual = directory / "jobs" / claim.job_name / "config.json"
            if actual.is_file() and not actual.is_symlink():
                provenance.update(config_sha256=file_hash(actual), executed_config_sha256=file_hash(actual))
            elif status == "scored":
                raise V2Error("scored single retry lacks resolved Harbor configuration")
            if status == "infra":
                if frozen.isolatable_provider_failure(payload.get("provider_failure")):
                    frozen.pause_model(directory, manifest, lock, slot, claim, payload)
                else:
                    frozen._hold(directory, "Single retry encountered non-isolatable infrastructure; review required.")
            store.complete(claim.token, owner, status,
                           {**provenance, **payload, "launch_state": "exited", "returncode": child.returncode},
                           charged_usd=cost)
            store.publish_visit(claim, directory / "visits")
            return {"launched": 1, "status": status, "job_name": claim.job_name,
                    "slot_id": SLOT, "automatic_further_retry": False,
                    "single_infra_retry_approval_sha256": approval_sha}
        except BaseException:
            if not requested:
                store.complete(claim.token, owner, "aborted",
                               {**provenance, "launch_not_requested": True},
                               counts_toward_cap=False, charged_usd=0.0)
                store.publish_visit(claim, directory / "visits")
            frozen._hold(directory, "Single infrastructure retry interrupted; preserve unresolved evidence.")
            raise


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--directory", required=True, type=Path)
    parser.add_argument("--execute", action="store_true")
    args = parser.parse_args(argv)
    try:
        print(json.dumps(execute_single_retry(args.directory, execute=args.execute), ensure_ascii=False))
        return 0
    except (OSError, ValueError, KeyError, TypeError, RuntimeError) as error:
        print(json.dumps({"blocked": True, "reason": str(error),
                          "model_execution_authorized_by_command": False}, ensure_ascii=False))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
