"""Read-only evidence analysis for the separately frozen provider reassessment.

The legacy grader checks remain unchanged. Only its final, monetary-authorization
schema check is replaced by the independently validated provider authorization.
No model, container, authorization or historical result is modified here.
"""
from __future__ import annotations

import argparse
from collections import defaultdict
import copy
from datetime import datetime, timezone
import json
from pathlib import Path
import sqlite3

import analyze_release_v2 as frozen
import release_v2_executor as legacy
from release_v2_pipeline import (
    ROOT, V2Error, active_claims, digest, document_digest, file_hash,
    job_config, normalized_job_config, read_json, read_visits, safe_name,
)


MODEL_ID = "qwen3.5-9b-primeintellect-bf16"
OLD_MODEL_ID = "qwen3.5-9b"
COMPLETE_PARENT_MODELS = frozenset((
    "gemma-3-12b-it", "llama-3.2-3b-instruct", "ministral-14b-2512",
    "ministral-3b-2512", "ministral-8b-2512", "qwen3.6-35b-a3b", "qwen3.8-27b",
))
AUTH_BOUNDARY_ERROR = (
    "authorization must explicitly bind the frozen matrix, execution lock and positive budget"
)
# Store identities before any call; dynamically looking them up in an exception
# handler would allow a replacement function to masquerade as the legacy check.
_FROZEN_VALIDATOR = frozen.validate_scored_visit
_FROZEN_CODE = _FROZEN_VALIDATOR.__code__
_LEGACY_AUTHORIZER = legacy.validate_authorization
_LEGACY_AUTH_CODE = _LEGACY_AUTHORIZER.__code__
LEGACY_SOURCES = ("scripts/analyze_release_v2.py", "scripts/release_v2_executor.py")


def _core():
    # The executor imports this analyzer for admission-time evidence validation.
    import provider_reassessment_v2
    return provider_reassessment_v2


def _guard_legacy_sources(manifest, root):
    root = Path(root).resolve()
    for name, module in zip(LEGACY_SOURCES, (frozen, legacy)):
        path = root / name
        if (Path(module.__file__).resolve() != path.resolve()
                or path.is_symlink()
                or manifest.get("source_hashes", {}).get(name) != file_hash(path)):
            raise V2Error("frozen authorization/scoring source differs from bound source")
    if (frozen.validate_scored_visit is not _FROZEN_VALIDATOR
            or legacy.validate_authorization is not _LEGACY_AUTHORIZER):
        raise V2Error("frozen authorization/scoring function identity changed")


def _terminal_authorization_boundary(error):
    if type(error) is not V2Error or error.args != (AUTH_BOUNDARY_ERROR,):
        return False
    frames, cursor = [], error.__traceback__
    while cursor is not None:
        frames.append(cursor.tb_frame.f_code)
        cursor = cursor.tb_next
    return len(frames) >= 2 and frames[-2:] == [_FROZEN_CODE, _LEGACY_AUTH_CODE]


def _validated_authorization(directory, manifest, root):
    core = _core()
    checked = core.validate_manifest(directory, root=root)
    if checked != manifest:
        raise V2Error("reassessment manifest changed during evidence analysis")
    lock = core.validate_lock(directory, manifest, root=root)
    approval = core.validate_authorization(directory, manifest, lock, root=root)
    _guard_legacy_sources(manifest, root)
    return lock, approval


def _canonical_row(visit, manifest, directory):
    """Reconstruct exactly the legacy return value after its terminal check.

    All preauthorization checks have already executed in the original function;
    capture and isolation are reread and checked again, never inferred from flags.
    """
    slot = next(row for row in manifest["schedule"] if row["slot_id"] == visit["slot_id"])
    job_name = safe_name(visit["job_name"])
    job = directory / "jobs" / job_name
    paths = [path for path in job.glob("*/result.json") if path.is_file()]
    if len(paths) != 1:
        raise V2Error("exactly one raw Harbor trial is required")
    result_path = frozen._regular(paths[0], job)
    trial = result_path.parent
    raw = read_json(result_path)
    trace = frozen.validate_trace(read_json(frozen._regular(
        trial / "agent" / "compact-shell-v2.json", trial)), slot["task"])
    verdict_path = frozen._regular(trial / "verifier" / "verdict.json", trial)
    verdict = frozen.validate_verdict(read_json(verdict_path), slot["task"])
    term = frozen.termination(raw, trace)
    capture = frozen._validate_capture(trial, trace, verdict)
    proofs = frozen.validate_runtime_isolation(trial, raw, manifest, slot["task"], verdict)
    return {
        **slot, "job_name": job_name,
        "started_at": frozen._timestamp(visit["started_at"]).isoformat(),
        "artifact": verdict["artifact_correct"] == 1,
        "clean": verdict["artifact_correct"] == 1 and term == "clean",
        "termination": term, "termination_reason": trace["termination_reason"],
        "failure_category": verdict["failure_category"],
        "verdict_sha256": file_hash(verdict_path), "raw_result_sha256": file_hash(result_path),
        "submission_digest": verdict["submission_digest"],
        "artifact_capture_status": capture["status"],
        "artifact_state_consistency": capture["state_consistency"],
        "static_network_isolation_evidence": proofs,
        "diagnostics": {"checks": verdict["checks"], "evidence": verdict["evidence"]},
        "resources": {
            "model_loop_elapsed_seconds": trace.get("model_loop_elapsed_seconds"),
            "total_elapsed_seconds": trace.get("total_elapsed_seconds"),
            "api_seconds": sum(call.get("elapsed_seconds", 0) for call in trace.get("calls", [])
                               if call.get("kind") == "api"),
            "command_seconds": sum(call.get("elapsed_seconds", 0) for call in trace.get("calls", [])
                                   if call.get("kind") == "shell"),
            "n_turns": trace["n_turns"], "n_parse_fail": trace["n_parse_fail"],
            "n_shell": trace["n_shell"], "usage": trace.get("usage"),
        },
    }


def validate_scored_visit(visit, manifest, directory, *, root=ROOT):
    directory, root = Path(directory).resolve(), Path(root).resolve()
    lock, approval = _validated_authorization(directory, manifest, root)
    if (visit.get("execution_lock_sha256") != lock["execution_lock_sha256"]
            or visit.get("authorization_sha256") != approval):
        raise V2Error("scored visit lacks its exact new provider execution authorization")
    try:
        _FROZEN_VALIDATOR(visit, manifest, directory, root=root)
    except V2Error as error:
        if not _terminal_authorization_boundary(error):
            raise
    else:
        # A legacy positive-budget authorization is not the new authorization.
        raise V2Error("legacy authorization unexpectedly accepted the provider protocol")
    request = _core().validate_request_contract(
        directory / "jobs" / safe_name(visit["job_name"]), manifest["models"][visit["model"]])
    if visit.get("request_contract") != request:
        raise V2Error("scored request receipt differs from the frozen request contract")
    row = _canonical_row(visit, manifest, directory)
    if _core().validate_authorization(directory, manifest, lock, root=root) != approval:
        raise V2Error("provider authorization changed during evidence analysis")
    return row


def _infra_evidence(visit, slot, manifest, directory, lock, approval):
    """Require the executor's typed raw infrastructure evidence, never a score."""
    job = safe_name(visit.get("job_name"))
    if (visit.get("execution_lock_sha256") != lock["execution_lock_sha256"]
            or visit.get("authorization_sha256") != approval):
        raise V2Error("infra attempt lacks its exact provider authorization")
    expected = job_config(manifest, slot, job, directory)
    generated = frozen._regular(directory / "configs" / (job + ".json"), directory / "configs")
    if (read_json(generated) != expected
            or file_hash(generated) != visit.get("generated_config_sha256")):
        raise V2Error("infra generated configuration differs from frozen protocol")
    job_root = directory / "jobs" / job
    results = [path for path in job_root.glob("*/result.json") if path.is_file()]
    if len(results) != 1:
        raise V2Error("infra classification lacks original single-trial evidence")
    raw = read_json(frozen._regular(results[0], job_root))
    if raw.get("task_name", "").rsplit("/", 1)[-1] != slot["task"]:
        raise V2Error("infra raw task identity mismatch")
    executed = job_root / "config.json"
    if executed.is_file():
        frozen._regular(executed, job_root)
        if (file_hash(executed) != visit.get("executed_config_sha256")
                or file_hash(executed) != visit.get("config_sha256")
                or normalized_job_config(read_json(executed)) != normalized_job_config(expected)):
            raise V2Error("infra executed configuration differs from frozen protocol")
    payload, _cost = _core().classify_job(job_root, slot["task"], manifest["models"][slot["model"]])
    if payload["status"] != "infra":
        raise V2Error("infra label would conceal a model/task failure")
    for key, value in payload.items():
        if key not in ("status", "cost_status") and visit.get(key) != value:
            raise V2Error("infra visit metadata differs from original typed evidence")
    return {"job": job, "slot_id": slot["slot_id"], "visit": visit.get("visit"),
            "raw_result_sha256": file_hash(results[0]), "classification": payload,
            "contributes_to_score": False}


def _attempt_policy(visits, manifest):
    issues, grouped = [], defaultdict(list)
    counted = [row for row in visits if row.get("counts_toward_cap") is True]
    if len(counted) > manifest["caps"]["max_total_visits"]:
        issues.append({"kind": "global_attempt_cap_exceeded"})
    for row in visits:
        grouped[row.get("slot_id")].append(row)
    for slot, rows in grouped.items():
        ordered = sorted(rows, key=lambda row: (frozen._timestamp(row["started_at"]), row["job_name"]))
        numbers = [row.get("visit") for row in ordered]
        if (sum(row.get("counts_toward_cap") is True for row in ordered) > manifest["caps"]["max_visits_per_slot"]
                or numbers != list(range(1, len(ordered) + 1))):
            issues.append({"kind": "invalid_attempt_sequence", "slot_id": slot})
        if any(not (row.get("status") == "aborted" and row.get("launch_not_requested") is True
                        and row.get("counts_toward_cap") is False)
               and not _core().retryable(row) for row in ordered[:-1]):
            issues.append({"kind": "answer_based_or_unresolved_retry", "slot_id": slot})
        executed = [row for row in ordered if row.get("counts_toward_cap") is True]
        for index, (prior, following) in enumerate(zip(executed, executed[1:])):
            delay = _core().RETRY_POLICY["cooldown_seconds"][min(index, 1)]
            saved_delay = (prior.get("provider_failure") or {}).get("retry_after_seconds")
            if isinstance(saved_delay, (int, float)) and not isinstance(saved_delay, bool):
                if not 0 <= saved_delay < float("inf"):
                    raise V2Error("invalid saved provider retry delay")
                delay = max(delay, saved_delay)
            elapsed = (frozen._timestamp(following["started_at"])
                       - frozen._timestamp(prior["finished_at"])).total_seconds()
            if elapsed < delay:
                issues.append({"kind": "provider_retry_before_cooldown", "slot_id": slot,
                               "prior_job": prior["job_name"], "job": following["job_name"]})
    return issues


def _claim_consistency(directory, visits):
    """Read the database without constructing ClaimStore (which writes schema)."""
    from experiment_execution import ClaimStore
    path = directory / "claims.sqlite3"
    if not path.is_file() or path.is_symlink():
        return [{"kind": "missing_or_unsafe_claim_ledger"}]
    with sqlite3.connect(path.resolve().as_uri() + "?mode=ro", uri=True) as connection:
        connection.row_factory = sqlite3.Row
        rows = [ClaimStore._view(row) for row in connection.execute("SELECT * FROM visits")]
    by_job = {row.get("job_name"): row for row in visits}
    if len(by_job) != len(visits) or len(rows) != len(visits):
        return [{"kind": "claim_export_coverage_mismatch"}]
    return [{"kind": "claim_export_content_mismatch", "job": row["job_name"]}
            for row in rows if row != by_job.get(row["job_name"])]


def build_report(directory, *, root=ROOT):
    directory, root = Path(directory).resolve(), Path(root).resolve()
    core = _core()
    manifest = core.validate_manifest(directory, root=root, cold=True)
    lock, approval = _validated_authorization(directory, manifest, root)
    visits, issues = read_visits(directory)
    schedule = {row["slot_id"]: row for row in manifest["schedule"]}
    legal, infra, unresolved, seen, scored = [], [], [], set(), defaultdict(list)
    for visit in visits:
        job = visit.get("job_name")
        if job in seen:
            issues.append({"kind": "duplicate_job_name", "job": job})
        seen.add(job)
        slot = schedule.get(visit.get("slot_id"))
        if slot is None:
            issues.append({"kind": "unplanned_visit", "job": job})
            continue
        if (visit.get("manifest_sha256") != manifest["manifest_sha256"]
                or any(visit.get(key) != slot[key] for key in ("model", "task", "repetition"))):
            issues.append({"kind": "visit_identity_mismatch", "job": job})
            continue
        state = visit.get("status")
        if state in ("running", "unknown"):
            unresolved.append(job)
        elif state == "scored":
            scored[slot["slot_id"]].append(job)
            try:
                legal.append(validate_scored_visit(visit, manifest, directory, root=root))
            except (OSError, ValueError, KeyError, TypeError) as error:
                issues.append({"kind": "invalid_scored_evidence", "job": job, "error": str(error)})
        elif state == "infra":
            try:
                infra.append(_infra_evidence(visit, slot, manifest, directory, lock, approval))
            except (OSError, ValueError, KeyError, TypeError) as error:
                issues.append({"kind": "unproven_infrastructure_retry", "job": job, "error": str(error)})
        elif state == "aborted":
            if (visit.get("launch_not_requested") is not True
                    or visit.get("counts_toward_cap") is not False
                    or visit.get("launch_state") not in (None, "not_requested")):
                issues.append({"kind": "unproven_aborted_visit", "job": job})
        else:
            issues.append({"kind": "unknown_visit_status", "job": job})
        if state in ("scored", "infra") and visit.get("counts_toward_cap") is not True:
            issues.append({"kind": "uncounted_executed_attempt", "job": job})
    for path in (directory / "jobs").iterdir() if (directory / "jobs").exists() else ():
        if path.is_dir() and path.name not in seen:
            issues.append({"kind": "untracked_job_artifacts", "job": path.name})
    try:
        issues.extend(_attempt_policy(visits, manifest))
    except (ValueError, KeyError, TypeError) as error:
        issues.append({"kind": "invalid_attempt_metadata", "error": str(error)})
    try:
        issues.extend(_claim_consistency(directory, visits))
    except (OSError, ValueError, sqlite3.Error, KeyError, TypeError) as error:
        issues.append({"kind": "invalid_claim_ledger", "error": str(error)})
    unresolved += active_claims(directory)
    rows, legal_duplicates, missing = frozen.summarize_slots(legal, manifest)
    duplicates = {key: jobs for key, jobs in scored.items() if len(jobs) > 1}
    duplicates.update(legal_duplicates)
    accepted = (len(schedule) == len(rows) == 62 and not (issues or duplicates or missing or unresolved))
    boards = frozen.leaderboard(rows, manifest)
    return {
        "schema_version": 2, "kind": "smallowbench_v2_provider_reassessment_report",
        **{key: manifest[key] for key in ("benchmark_version", "task_version", "harness_version",
                                       "grader_version", "scorer_version", "manifest_sha256")},
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "accepted": accepted, "formal_ranking_eligible": accepted,
        "repetitions": manifest["repetitions"], "task_units": 62,
        "interpretation": "single-run task scores; not repeated-run reliability or real-software E2E",
        "scoring": manifest["scoring"], "canonical_rule": "earliest_started_legal_scored_then_job_name",
        "completeness": {"planned": len(schedule), "legal_unique": len(rows), "missing": missing,
                         "duplicates": duplicates, "unresolved": sorted(set(unresolved))},
        "issues": issues, "infra_visits": infra, "canonical_rows": rows,
        "candidate_scores": boards, "leaderboard": boards if accepted else {},
        "total_attempts": len(visits), "stop_present": (directory / "STOP").exists(),
        "cost_accounting": {
            "reported_api_usd": sum(row.get("charged_usd") or 0 for row in visits),
            "unknown_reserved_usd": sum(row.get("reserved_usd", 0) for row in visits
                                        if row.get("charged_usd") is None),
            "monetary_cap_enforced": False,
        },
        "authorization_sha256": approval, "execution_lock_sha256": lock["execution_lock_sha256"],
        "analysis_provenance": {"source_sha256": {name: file_hash(root / name) for name in (
            *LEGACY_SOURCES, "scripts/provider_reassessment_v2.py",
            "scripts/provider_reassessment_scoring_v2.py")}},
        "model_execution_performed_by_analyzer": False,
        "historical_parent_records_modified": False,
    }


def assert_profile_identity(parent_manifest, manifest):
    """Permit precisely the separately named provider substitution, no other knob."""
    if set(manifest["models"]) != {MODEL_ID} or set(parent_manifest["models"]) != (
            COMPLETE_PARENT_MODELS | {OLD_MODEL_ID}):
        raise V2Error("combined roster must contain exactly seven parent profiles and one new provider profile")
    expected = copy.deepcopy(parent_manifest["models"][OLD_MODEL_ID])
    expected["route"] = "primeintellect/bf16"
    provider = expected["agent_kwargs"]["llm_call_kwargs"]["extra_body"]["provider"]
    provider["order"] = provider["only"] = ["primeintellect/bf16"]
    if manifest["models"][MODEL_ID] != expected:
        raise V2Error("new provider profile changed model, precision, or non-route configuration")
    expected_roster = {
        "policy": "seven_complete_parent_configurations_plus_independent_full_62_new_provider",
        "models": {**{model: parent_manifest["models"][model] for model in sorted(COMPLETE_PARENT_MODELS)},
                   MODEL_ID: expected},
        "excluded_parent_model": OLD_MODEL_ID,
        "parent_partial_observations_may_fill_new_provider_slots": False,
        "selection_frozen_before_new_provider_results": True,
    }
    if manifest.get("publication_roster") != expected_roster:
        raise V2Error("joined roster selection differs from the independently prefrozen publication roster")
    for key in ("tasks", "task_bank", "runtime", "runtime_environment_evidence", "component_versions",
                "benchmark_version", "task_version", "harness_version", "grader_version",
                "scorer_version", "repetitions", "scoring", "submission_schemas", "agent_import_path"):
        if manifest.get(key) != parent_manifest.get(key):
            raise V2Error("combined roster differs in frozen task/runtime/scoring profile: " + key)


def join_roster(report, parent_report, manifest, parent_manifest, *, directory, parent_directory, root=ROOT):
    """Build an independent complete roster; never repair the parent's false flag."""
    assert_profile_identity(parent_manifest, manifest)
    if (report.get("accepted") is not True or report.get("formal_ranking_eligible") is not True
            or set(report.get("leaderboard", {})) != {MODEL_ID}
            or parent_report.get("accepted") is not False
            or parent_report.get("formal_ranking_eligible") is not False
            or parent_report.get("manifest_sha256") != parent_manifest["manifest_sha256"]
            or report.get("manifest_sha256") != manifest["manifest_sha256"]):
        raise V2Error("superseding roster requires a complete new profile and preserves incomplete parent status")
    if (parent_report.get("issues") or parent_report["completeness"].get("duplicates")
            or parent_report["completeness"].get("unresolved")):
        raise V2Error("parent evidence has unresolved validation issues")
    if (any(row.get("model") != MODEL_ID for row in report["canonical_rows"])
            or any(row.get("model") not in COMPLETE_PARENT_MODELS | {OLD_MODEL_ID}
                   for row in parent_report["canonical_rows"])):
        raise V2Error("source reports include an unapproved model profile")
    rows = []
    coverage = {}
    for model in sorted(COMPLETE_PARENT_MODELS | {MODEL_ID}):
        source = report if model == MODEL_ID else parent_report
        source_manifest = manifest if model == MODEL_ID else parent_manifest
        source_dir = Path(directory if model == MODEL_ID else parent_directory).resolve()
        selected = [row for row in source["canonical_rows"] if row["model"] == model]
        profile_schedule = [slot for slot in source_manifest["schedule"] if slot["model"] == model]
        expected_slots = {slot["slot_id"]: slot for slot in profile_schedule}
        if (len(selected) != 62 or len(profile_schedule) != 62
                or len({row["slot_id"] for row in selected}) != 62
                or {row["task"] for row in selected} != set(manifest["tasks"])
                or {row["repetition"] for row in selected} != {1}
                or {row["slot_id"] for row in selected} != set(expected_slots)
                or any(any(row.get(key) != expected_slots.get(row["slot_id"], {}).get(key)
                           for key in ("model", "task", "repetition", "sequence")) for row in selected)):
            raise V2Error("cannot combine a partial, duplicate or extra-task model profile: " + model)
        board = frozen.leaderboard(selected, {**manifest, "models": {model: source_manifest["models"][model]}})
        if not board[model]["complete"]:
            raise V2Error("combined profile is not complete")
        rows.extend(selected)
        coverage[model] = {
            "source_directory": str(source_dir), "manifest_sha256": source_manifest["manifest_sha256"],
            "manifest_file_sha256": file_hash(source_dir / "manifest.json"),
            "execution_lock_file_sha256": file_hash(source_dir / "execution-lock.json"),
            "profile_sha256": digest(source_manifest["models"][model]),
            "canonical_rows_sha256": digest(selected), "scored_task_units": 62,
            "source_report_kind": source["kind"], "fresh_raw_evidence_validation": True,
        }
    roster = {
        "schema_version": 2, "kind": "smallowbench_v2_superseding_roster_manifest",
        "repetitions": 1, "tasks": manifest["tasks"], "scoring": manifest["scoring"],
        "models": {**{model: parent_manifest["models"][model] for model in sorted(COMPLETE_PARENT_MODELS)},
                   MODEL_ID: manifest["models"][MODEL_ID]},
        "schedule": [slot for slot in parent_manifest["schedule"] if slot["model"] in COMPLETE_PARENT_MODELS]
                    + manifest["schedule"],
        "source_coverage": coverage,
        "publication_roster_frozen_in_provider_manifest": manifest["publication_roster"],
        "source_hashes": {"parent_frozen": parent_manifest["source_hashes"],
                          "provider_reassessment": manifest["source_hashes"]},
        "excluded_parent_provider": OLD_MODEL_ID,
        "excluded_parent_observations": sum(row["model"] == OLD_MODEL_ID
                                            for row in parent_report["canonical_rows"]),
        "parent_global_accepted_preserved": parent_report["accepted"],
    }
    roster["manifest_sha256"] = document_digest(roster)
    canonical, duplicates, missing = frozen.summarize_slots(rows, roster)
    if len(canonical) != 496 or duplicates or missing:
        raise V2Error("superseding roster does not contain exactly 496 unique complete slots")
    return {
        "schema_version": 2, "kind": "smallowbench_v2_superseding_roster_report",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "accepted": True, "formal_ranking_eligible": True,
        "superseding_roster_manifest": roster, "manifest_sha256": roster["manifest_sha256"],
        "parent_original_roster_accepted": False, "historical_parent_records_modified": False,
        "completeness": {"planned": 496, "legal_unique": 496, "missing": [],
                         "duplicates": {}, "unresolved": []},
        "canonical_rows": canonical, "leaderboard": frozen.leaderboard(canonical, roster),
        "issues": [], "source_coverage": coverage,
        "analysis_provenance": {"source_sha256": {name: file_hash(Path(root) / name) for name in (
            "scripts/analyze_release_v2_supplement.py", "scripts/audit_v2_capture_supplement.py",
            "scripts/provider_reassessment_scoring_v2.py")}},
        "model_execution_performed_by_analyzer": False,
    }


def build_combined_report(directory, *, root=ROOT):
    from analyze_release_v2_supplement import build_supplemented_report
    directory, root = Path(directory).resolve(), Path(root).resolve()
    report = build_report(directory, root=root)
    manifest = _core().validate_manifest(directory, root=root, cold=True)
    parent_directory = Path(manifest["parent"]["directory"]).resolve()
    parent_report = build_supplemented_report(parent_directory, root=root)
    parent_manifest = read_json(parent_directory / "manifest.json")
    return join_roster(report, parent_report, manifest, parent_manifest,
                       directory=directory, parent_directory=parent_directory, root=root)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--directory", required=True, type=Path)
    parser.add_argument("--output", type=Path, help="a NEW JSON file inside the new run")
    parser.add_argument("--combine-parent", action="store_true")
    args = parser.parse_args(argv)
    try:
        report = (build_combined_report if args.combine_parent else build_report)(args.directory)
        if args.output:
            output = args.output.resolve()
            if output.exists() or not output.is_relative_to(args.directory.resolve()):
                raise V2Error("report output must be a new file inside the new experiment")
            output.parent.mkdir(parents=True, exist_ok=True)
            with output.open("x", encoding="utf-8", newline="\n") as handle:
                json.dump(report, handle, ensure_ascii=False, indent=2, allow_nan=False)
                handle.write("\n")
        print(json.dumps({key: report[key] for key in (
            "kind", "accepted", "formal_ranking_eligible", "completeness", "issues")},
                         ensure_ascii=False, allow_nan=False))
        return 0 if report["accepted"] else 2
    except (OSError, ValueError, KeyError, TypeError) as error:
        print(json.dumps({"error": str(error)}, ensure_ascii=False))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
