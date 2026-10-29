"""Read-only, explicitly amended scoring of a cancelled in-flight API request.

Original p3 visits/claims and the historical false report remain unchanged. The
single original timeout is represented by a hash-bound sidecar, never a rerun.
"""
from __future__ import annotations

import argparse
from collections import defaultdict
import copy
from datetime import datetime, timezone
import json
from pathlib import Path

import analyze_release_v2 as frozen
import provider_reassessment_scoring_v2 as original
import release_v2_executor as legacy
from release_v2_pipeline import (
    ROOT, V2Error, active_claims, document_digest, file_hash, job_config,
    normalized_job_config, read_json, read_visits, safe_name,
)

AMENDMENT = "execution-amendment-cancellation.json"
SIDECAR = "cancellation-reclassification.json"
CONTINUATION = "cancellation-continuation"
BASIS = "agent_timeout_with_cancelled_pending_request_not_provider_failure"
NEW_SOURCES = ("scripts/resume_provider_cancellation_v2.py", "scripts/provider_cancellation_scoring_v2.py")


def _resume():
    import resume_provider_cancellation_v2
    return resume_provider_cancellation_v2


def _guard(directory, manifest, root):
    amendment, amendment_sha = _resume().validate_amendment(directory, root=root)
    lock, auth = original._validated_authorization(directory, manifest, root)
    return amendment, amendment_sha, lock, auth


def _frozen_row(visit, manifest, directory, root):
    """Run all original checks and catch only the known terminal legacy schema."""
    lock, auth = original._validated_authorization(directory, manifest, root)
    if (visit.get("authorization_sha256") != auth
            or visit.get("execution_lock_sha256") != lock["execution_lock_sha256"]):
        raise V2Error("amended observation differs from original execution authorization")
    try:
        original._FROZEN_VALIDATOR(visit, manifest, directory, root=root)
    except V2Error as error:
        if not original._terminal_authorization_boundary(error):
            raise
    else:
        raise V2Error("legacy authorization unexpectedly accepted the provider protocol")
    return original._canonical_row(visit, manifest, directory)


def _correction_evidence(directory, amendment, *, root=ROOT):
    """Validate the exact original negative observation without new authorization recursion."""
    directory, root = Path(directory).resolve(), Path(root).resolve()
    correction = amendment["correction"]
    job = safe_name(correction["job_name"])
    path = frozen._regular(directory / "visits" / (job + ".json"), directory / "visits")
    if file_hash(path) != correction["source_visit_sha256"] or amendment["baseline_visits_sha256"].get(job) != file_hash(path):
        raise V2Error("original cancelled visit bytes differ from the amendment")
    source = read_json(path)
    if (source.get("job_name") != job or source.get("slot_id") != correction["slot_id"]
            or source.get("claim_token") != correction["claim_token"]
            or source.get("model") != original.MODEL_ID or source.get("task") != "testgen-anagram"
            or source.get("status") != "infra" or source.get("counts_toward_cap") is not True
            or source.get("reason") != "provider_configuration_contract"
            or source.get("retry_classification") != "configuration_fault_no_retry"
            or (source.get("provider_failure") or {}).get("exception_type") != "RequestContractError"):
        raise V2Error("correction is outside the sole frozen request-audit misclassification")
    job_root = directory / "jobs" / job
    paths = [path for path in job_root.glob("*/result.json") if path.is_file()]
    if len(paths) != 1 or file_hash(frozen._regular(paths[0], job_root)) != correction["raw_result_sha256"]:
        raise V2Error("correction original raw result differs")
    trace_path = frozen._regular(paths[0].parent / "agent" / "compact-shell-v2.json", paths[0].parent)
    if file_hash(trace_path) != correction["trace_sha256"]:
        raise V2Error("correction original trace differs")
    raw, trace = read_json(paths[0]), read_json(trace_path)
    if ((raw.get("exception_info") or {}).get("exception_type") != "AgentTimeoutError"
            or trace.get("termination_reason") != "cancelled"):
        raise V2Error("only original AgentTimeoutError with a cancelled pending call can be corrected")
    manifest = original._core().validate_manifest(directory, root=root)
    request = _resume().validate_request_contract(job_root, manifest["models"][original.MODEL_ID])
    if request.get("typed_timeout_cancellation_exception_applied") is not True:
        raise V2Error("correction lacks affirmative unique pending-call timeout evidence")
    payload, _cost = legacy.classify_job(job_root, source["task"])
    if (payload.get("status") != "scored" or payload.get("termination") != "tle"
            or type(payload.get("atomic_correct")) is not int or payload["atomic_correct"] != 0):
        raise V2Error("original raw evidence does not establish the exact timeout fail/zero observation")
    amendment_sha = file_hash(directory / AMENDMENT)
    virtual = {**source, **payload, "status": "scored", "request_contract": request,
               "execution_amendment_sha256": amendment_sha}
    _frozen_row(virtual, manifest, directory, root)
    return source, virtual, request


def build_reclassification(directory, amendment, *, root=ROOT):
    """Build only; the caller creates this sidecar before authorizing the amendment."""
    directory = Path(directory).resolve()
    source, virtual, request = _correction_evidence(directory, amendment, root=root)
    correction = amendment["correction"]
    value = {
        "schema_version": 2, "kind": "smallowbench_v2_cancellation_reclassification",
        "execution_amendment_sha256": file_hash(directory / AMENDMENT),
        "source_job_name": source["job_name"], "source_slot_id": source["slot_id"],
        "source_visit_sha256": correction["source_visit_sha256"],
        "raw_result_sha256": correction["raw_result_sha256"], "trace_sha256": correction["trace_sha256"],
        "original_status": "infra", "corrected_status": "scored", "termination": "tle",
        "atomic_correct": virtual["atomic_correct"], "request_contract": request,
        "correction_basis": BASIS, "model_execution_performed": False,
        "original_visit_modified": False, "original_claim_ledger_modified": False,
    }
    value["report_sha256"] = document_digest(value, "report_sha256")
    return value


def validate_reclassification(directory, amendment, *, root=ROOT):
    directory = Path(directory).resolve()
    path = frozen._regular(directory / SIDECAR, directory)
    actual = read_json(path)
    if actual != build_reclassification(directory, amendment, root=root):
        raise V2Error("cancellation sidecar differs from independently verified original timeout evidence")
    _source, virtual, _request = _correction_evidence(directory, amendment, root=root)
    return {**virtual, "reclassification_sha256": file_hash(path)}


def _visit_authority(visit, directory, amendment, amendment_sha):
    job = safe_name(visit.get("job_name"))
    if job == amendment["correction"]["job_name"]:
        return "sidecar"
    baseline = amendment["baseline_visits_sha256"]
    if job in baseline:
        path = frozen._regular(directory / "visits" / (job + ".json"), directory / "visits")
        if file_hash(path) != baseline[job] or read_json(path) != visit:
            raise V2Error("baseline scored observation differs from frozen original visit")
        return "baseline"
    child = directory / CONTINUATION
    path = frozen._regular(child / "visits" / (job + ".json"), child / "visits")
    if (read_json(path) != visit or visit.get("slot_id") not in amendment["remaining_slot_ids"]
            or visit.get("execution_amendment_sha256") != amendment_sha):
        raise V2Error("continuation observation lacks the exact amendment or frozen remaining slot")
    return "continuation"


def validate_scored_visit(visit, manifest, directory, *, root=ROOT):
    directory, root = Path(directory).resolve(), Path(root).resolve()
    amendment, amendment_sha, _lock, _auth = _guard(directory, manifest, root)
    authority = _visit_authority(visit, directory, amendment, amendment_sha)
    if authority == "baseline":
        # These 49 observations already satisfy the original request contract.
        # Preserve their exact receipts and every original check unchanged.
        row = original.validate_scored_visit(visit, manifest, directory, root=root)
        return {**row, "execution_amendment_sha256": amendment_sha, "observation_authority": authority}
    if authority == "sidecar" and visit != validate_reclassification(directory, amendment, root=root):
        raise V2Error("original cancelled observation must use the exact verified sidecar view")
    request = _resume().validate_request_contract(directory / "jobs" / visit["job_name"], manifest["models"][original.MODEL_ID])
    if visit.get("request_contract") != request:
        raise V2Error("amended request receipt differs from original saved request parameters")
    row = _frozen_row(visit, manifest, directory, root)
    return {**row, "execution_amendment_sha256": amendment_sha, "observation_authority": authority,
            **({"reclassification_sha256": visit["reclassification_sha256"]} if authority == "sidecar" else {})}


def _infra_evidence(visit, slot, manifest, directory, lock, auth):
    """Original config/raw checks with the amended classifier, never a patched global."""
    job = safe_name(visit.get("job_name"))
    if (visit.get("execution_lock_sha256") != lock["execution_lock_sha256"]
            or visit.get("authorization_sha256") != auth):
        raise V2Error("amended infra attempt lacks original provider authorization")
    expected = job_config(manifest, slot, job, directory)
    generated = frozen._regular(directory / "configs" / (job + ".json"), directory / "configs")
    if read_json(generated) != expected or file_hash(generated) != visit.get("generated_config_sha256"):
        raise V2Error("amended infra generated configuration differs from frozen protocol")
    job_root = directory / "jobs" / job
    results = [path for path in job_root.glob("*/result.json") if path.is_file()]
    if len(results) != 1:
        raise V2Error("amended infra lacks original single-trial evidence")
    raw = read_json(frozen._regular(results[0], job_root))
    if raw.get("task_name", "").rsplit("/", 1)[-1] != slot["task"]:
        raise V2Error("amended infra raw task identity mismatch")
    executed = job_root / "config.json"
    if executed.is_file():
        frozen._regular(executed, job_root)
        if (file_hash(executed) != visit.get("executed_config_sha256")
                or file_hash(executed) != visit.get("config_sha256")
                or normalized_job_config(read_json(executed)) != normalized_job_config(expected)):
            raise V2Error("amended infra executed configuration differs from frozen protocol")
    payload, _cost = _resume().classify_job(job_root, slot["task"], manifest["models"][slot["model"]])
    if payload.get("status") != "infra":
        raise V2Error("infra label would conceal a model/task failure")
    for key, value in payload.items():
        if key not in ("status", "cost_status") and visit.get(key) != value:
            raise V2Error("amended infra metadata differs from original typed evidence")
    return {"job": job, "slot_id": slot["slot_id"], "visit": visit.get("visit"),
            "raw_result_sha256": file_hash(results[0]), "classification": payload,
            "contributes_to_score": False}


def build_report(directory, *, root=ROOT):
    directory, root = Path(directory).resolve(), Path(root).resolve()
    _resume().validate_amendment(directory, root=root, verify_artifacts=True)
    manifest = original._core().validate_manifest(directory, root=root, cold=True)
    amendment, amendment_sha, lock, auth = _guard(directory, manifest, root)
    virtual = validate_reclassification(directory, amendment, root=root)
    # This preserves all original config, claim/export, attempt and source checks.
    base = original.build_report(directory, root=root)
    baseline, read_issues = read_visits(directory)
    child_dir = directory / CONTINUATION
    child, child_issues = read_visits(child_dir)
    visits = [virtual if row.get("job_name") == virtual["job_name"] else row for row in baseline] + child
    issues = list(read_issues) + list(child_issues)
    legal, verified_jobs, infra = [], set(), []
    scored_jobs = defaultdict(list)
    schedule = {slot["slot_id"]: slot for slot in manifest["schedule"]}
    seen = set()
    for visit in visits:
        job = visit.get("job_name")
        if job in seen:
            issues.append({"kind": "duplicate_job_name", "job": job})
        seen.add(job)
        slot = schedule.get(visit.get("slot_id"))
        if (slot is None or visit.get("manifest_sha256") != manifest["manifest_sha256"]
                or any(visit.get(key) != slot[key] for key in ("model", "task", "repetition"))):
            issues.append({"kind": "visit_identity_mismatch", "job": job})
            continue
        try:
            authority = _visit_authority(visit, directory, amendment, amendment_sha)
            if visit.get("status") == "scored":
                scored_jobs[visit["slot_id"]].append(job)
                legal.append(validate_scored_visit(visit, manifest, directory, root=root))
                verified_jobs.add(job)
            elif visit.get("status") == "infra":
                infra.append(_infra_evidence(visit, slot, manifest, directory, lock, auth))
                verified_jobs.add(job)
            elif visit.get("status") == "aborted":
                if visit.get("launch_not_requested") is not True or visit.get("counts_toward_cap") is not False:
                    raise V2Error("unproven aborted continuation")
            elif visit.get("status") not in ("running", "unknown"):
                raise V2Error("unknown continuation state")
            if authority == "sidecar" and visit.get("status") != "scored":
                raise V2Error("the corrected original timeout cannot be retried or left infra")
        except (OSError, ValueError, KeyError, TypeError) as error:
            issues.append({"kind": "invalid_amended_evidence", "job": job, "error": str(error)})
        if visit.get("status") in ("scored", "infra") and visit.get("counts_toward_cap") is not True:
            issues.append({"kind": "uncounted_executed_attempt", "job": job})
    # The original analyzer cannot see child exports, nor the explicitly added
    # timeout sidecar. Remove only its issues independently resolved above.
    resolved = []
    for issue in base["issues"]:
        if issue.get("job") in verified_jobs and issue.get("kind") in ("untracked_job_artifacts", "invalid_scored_evidence"):
            resolved.append(issue)
        else:
            issues.append(issue)
    if child:
        issues.extend(original._claim_consistency(child_dir, child))
    elif (child_dir / "claims.sqlite3").exists():
        issues.extend(original._claim_consistency(child_dir, []))
    try:
        issues.extend(original._attempt_policy(visits, manifest))
    except (OSError, ValueError, KeyError, TypeError) as error:
        issues.append({"kind": "invalid_amended_attempt_policy", "error": str(error)})
    unresolved = sorted(set(active_claims(directory) + active_claims(child_dir)
                            + [row["job_name"] for row in visits if row.get("status") in ("running", "unknown")]))
    rows, duplicates, missing = frozen.summarize_slots(legal, manifest)
    duplicates.update({slot: jobs for slot, jobs in scored_jobs.items() if len(jobs) > 1})
    accepted = len(rows) == 62 and not (issues or duplicates or missing or unresolved)
    report = copy.deepcopy(base)
    boards = frozen.leaderboard(rows, manifest)
    report.update(kind="smallowbench_v2_provider_cancellation_amended_report", accepted=accepted,
                  formal_ranking_eligible=accepted, generated_at=datetime.now(timezone.utc).isoformat(),
                  canonical_rows=rows, candidate_scores=boards, leaderboard=boards if accepted else {}, issues=issues,
                  completeness={"planned": 62, "legal_unique": len(rows), "missing": missing,
                                "duplicates": duplicates, "unresolved": unresolved},
                  infra_visits=infra, total_attempts=len(visits), execution_amendment_sha256=amendment_sha,
                  reclassification_sha256=file_hash(directory / SIDECAR),
                  reclassified_original_infra_attempts=[row for row in base["infra_visits"] if row["job"] == virtual["job_name"]],
                  resolved_original_analysis_issues=resolved,
                  original_status_and_claim_ledger_preserved=True,
                  original_partial_report_preserved=True)
    report["cost_accounting"] = {
        "reported_api_usd": sum(row.get("charged_usd") or 0 for row in visits),
        "unknown_reserved_usd": sum(row.get("reserved_usd", 0) for row in visits if row.get("charged_usd") is None),
        "monetary_cap_enforced": False,
    }
    report["analysis_provenance"]["cancellation_amendment_source_sha256"] = {
        name: file_hash(root / name) for name in NEW_SOURCES}
    return report


def build_combined_report(directory, *, root=ROOT):
    from analyze_release_v2_supplement import build_supplemented_report
    directory, root = Path(directory).resolve(), Path(root).resolve()
    report = build_report(directory, root=root)
    manifest = original._core().validate_manifest(directory, root=root, cold=True)
    parent_dir = Path(manifest["parent"]["directory"])
    parent = build_supplemented_report(parent_dir, root=root)
    combined = original.join_roster(report, parent, manifest, read_json(parent_dir / "manifest.json"),
                                    directory=directory, parent_directory=parent_dir, root=root)
    combined["execution_amendment_sha256"] = report["execution_amendment_sha256"]
    combined["reclassification_sha256"] = report["reclassification_sha256"]
    combined["analysis_provenance"]["cancellation_amendment_source_sha256"] = report["analysis_provenance"]["cancellation_amendment_source_sha256"]
    roster = combined["superseding_roster_manifest"]
    roster["execution_amendment_sha256"] = report["execution_amendment_sha256"]
    roster["reclassification_sha256"] = report["reclassification_sha256"]
    roster["source_hashes"]["cancellation_amendment"] = report["analysis_provenance"]["cancellation_amendment_source_sha256"]
    roster["manifest_sha256"] = document_digest(roster)
    combined["manifest_sha256"] = roster["manifest_sha256"]
    return combined


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--directory", type=Path, required=True)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--combine-parent", action="store_true")
    args = parser.parse_args(argv)
    try:
        report = (build_combined_report if args.combine_parent else build_report)(args.directory)
        if args.output:
            path = args.output.resolve()
            if path.exists() or not path.is_relative_to(args.directory.resolve()):
                raise V2Error("amended report must use a new filename inside the original run")
            with path.open("x", encoding="utf-8", newline="\n") as stream:
                json.dump(report, stream, ensure_ascii=False, indent=2, allow_nan=False)
                stream.write("\n")
        print(json.dumps({key: report[key] for key in ("kind", "accepted", "completeness")}, ensure_ascii=False))
        return 0 if report["accepted"] else 2
    except (OSError, ValueError, KeyError, TypeError) as error:
        print(json.dumps({"exception_type": type(error).__name__}))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
