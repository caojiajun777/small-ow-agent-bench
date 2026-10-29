"""Recompute release results with two independently audited negative observations.

Original traces, captures, visits, grades and earlier reports remain intact.
The supplementary auditor is rebuilt from original evidence on every invocation.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import analyze_release_v2 as frozen
from analyze_release_v2_fee_waiver import annotate_report
from audit_v2_capture_supplement import CAPTURE_REJECTION, TARGETS, build_supplement
from release_v2_pipeline import ROOT, V2Error, file_hash, read_json, read_visits


def apply_supplement(report, supplement, manifest):
    """Combine a freshly verified supplement with the unchanged scoring function."""
    if (supplement.get("kind") != "smallowbench_v2_capture_failure_supplement"
            or supplement.get("manifest_sha256") != report.get("manifest_sha256")
            or supplement.get("manifest_sha256") != manifest.get("manifest_sha256")
            or supplement.get("complete_final_agent_capture_established") is not False
            or supplement.get("original_records_modified") is not False
            or supplement.get("model_calls") != 0 or supplement.get("container_calls") != 0):
        raise V2Error("supplement scope or run identity differs from the audited negatives")
    observations = supplement.get("supported_negative_observations", [])
    if (len(observations) != 2 or {item.get("job_name") for item in observations} != set(TARGETS)
            or supplement.get("supported_count") != 2 or supplement.get("observed_file_count") != 35):
        raise V2Error("supplement must cover exactly the two named negative observations")
    canonical = list(report["canonical_rows"])
    existing_jobs = {row["job_name"] for row in canonical}
    issues = list(report.get("issues", []))
    resolved = []
    for item in observations:
        job = item["job_name"]
        row = item["canonical_row"]
        expected_task = TARGETS[job][0]
        expected_slots = [slot for slot in manifest["schedule"]
                          if slot.get("model") == "llama-3.2-3b-instruct"
                          and slot.get("task") == expected_task and slot.get("repetition") == 1]
        if (len(expected_slots) != 1 or any(
                row.get(field) != expected_slots[0].get(field)
                for field in ("slot_id", "model", "task", "repetition", "sequence"))):
            raise V2Error("supplement row differs from its exact frozen task slot")
        if (item.get("supported") is not True or row.get("job_name") != job
                or row.get("task") != expected_task or row.get("model") != "llama-3.2-3b-instruct"
                or row.get("artifact") is not False or row.get("clean") is not False
                or row.get("failure_category") != "invalid_submission"
                or row.get("artifact_capture_status") != "error"
                or row.get("capture_supplement_scope") != "original_invalid_submission_zero_only"
                or job in existing_jobs):
            raise V2Error("supplement cannot add a positive, duplicate or unrelated observation")
        matched = [issue for issue in issues if issue.get("job") == job]
        if (len(matched) != 1 or matched[0].get("kind") != "invalid_scored_evidence"
                or matched[0].get("error") != CAPTURE_REJECTION):
            raise V2Error("supplement may resolve only the exact original capture rejection")
        issues.remove(matched[0])
        resolved.append({**matched[0], "resolution": "audited_original_negative_grader_observation"})
        canonical.append(row)
        existing_jobs.add(job)
    rows, legal_duplicates, missing = frozen.summarize_slots(canonical, manifest)
    duplicates = {**report["completeness"].get("duplicates", {}), **legal_duplicates}
    unresolved = report["completeness"].get("unresolved", [])
    accepted = not (issues or duplicates or missing or unresolved)
    boards = frozen.leaderboard(rows, manifest)
    result = dict(report)
    result.update({
        "base_analysis_kind": report.get("kind"),
        "kind": "smallowbench_v2_supplemented_release_report",
        "accepted": accepted,
        "formal_ranking_eligible": accepted and not report.get("engineering_diagnostic", False),
        "issues": issues,
        "resolved_capture_issues": resolved,
        "canonical_rows": rows,
        "candidate_scores": boards,
        "leaderboard": boards if accepted else {},
        "completeness": {"planned": len(manifest["schedule"]), "legal_unique": len(rows),
                         "missing": missing, "duplicates": duplicates, "unresolved": unresolved},
        "capture_evidence_supplement": {
            "supported_original_negative_observations": 2,
            "verified_grader_observed_files": 35,
            "original_capture_status": "error; preserved",
            "complete_final_agent_capture_established": False,
            "scope": "two original invalid_submission fail/zero observations only",
            "fresh_original_evidence_audit": True,
            "source_sha256": supplement["source_sha256"],
        },
    })
    return result


def annotate_single_infra_retry(report, directory, manifest, lock, *, root=ROOT):
    """Disclose and validate the sole separately approved execution exception."""
    visits, errors = read_visits(directory)
    if errors:
        raise V2Error("retry provenance cannot use unreadable visit records")
    retries = [row for row in visits if row.get("visit", 1) > 1
               or row.get("single_infra_retry_approval_sha256")]
    if not retries:
        if (len(visits) > len(manifest["schedule"])
                or len({row.get("slot_id") for row in visits}) != len(visits)):
            raise V2Error("extra or repeated attempts cannot omit independent retry provenance")
        return report
    import retry_v2_single_infra as retry

    if len(retries) != 1:
        raise V2Error("only one separately approved infrastructure retry is allowed")
    row = retries[0]
    if (row.get("slot_id") != retry.SLOT or row.get("visit") != 2
            or row.get("job_name") == retry.SOURCE_JOB):
        raise V2Error("additional attempt is outside the named infrastructure exception")
    _proposal, proposal_sha = retry.validate_proposal(directory, manifest, lock, root=root)
    approval_sha, auth_sha, fee_sha = retry.validate_approval(
        directory, manifest, lock, proposal_sha, root=root,
    )
    if (row.get("single_infra_retry_approval_sha256") != approval_sha
            or row.get("single_infra_retry_proposal_sha256") != proposal_sha
            or row.get("authorization_sha256") != auth_sha
            or row.get("fee_waiver_sha256") != fee_sha
            or row.get("retry_source_job_name") != retry.SOURCE_JOB):
        raise V2Error("additional attempt lacks the exact independent retry approval")
    source = [value for value in visits if value.get("job_name") == retry.SOURCE_JOB]
    other = [value for value in visits if value.get("slot_id") != retry.SLOT]
    expected_other = {slot["slot_id"] for slot in manifest["schedule"]} - {retry.SLOT}
    if (len(visits) != 497 or len(source) != 1 or source[0].get("status") != "infra"
            or source[0].get("visit") != 1 or source[0].get("counts_toward_cap") is not True
            or len(other) != 495 or {value.get("slot_id") for value in other} != expected_other
            or any(value.get("status") != "scored" or value.get("visit") != 1
                   or value.get("counts_toward_cap") is not True for value in other)):
        raise V2Error("retry must preserve all 496 original attempts without another exception")
    if row.get("counts_toward_cap") is not True and not (
            row.get("status") == "aborted" and row.get("launch_not_requested") is True
            and row.get("counts_toward_cap") is False):
        raise V2Error("uncounted retry lacks positive no-launch evidence")
    annotated = dict(report)
    annotated["actual_execution_policy"] = {
        **report["actual_execution_policy"],
        "max_task_attempts": 497,
        "default_max_visits_per_slot": 1,
        "single_infra_retry_exception": {
            "slot_id": retry.SLOT, "slot_max_visits": 2, "max_new_attempts": 1,
            "approval_sha256": approval_sha, "proposal_sha256": proposal_sha,
            "source_job_name": retry.SOURCE_JOB,
            "reason": "evidence_confirmed_http_429", "original_counted_infra_preserved": True,
            "retry_status": row.get("status"), "retry_job_name": row.get("job_name"),
        },
        "actual_counted_attempts": sum(value.get("counts_toward_cap") is True for value in visits),
    }
    annotated["execution_phases"] = {
        **report["execution_phases"], "separately_approved_infra_retry_visits": 1,
    }
    return annotated


def build_supplemented_report(directory, *, root=ROOT):
    directory, root = Path(directory).resolve(), Path(root).resolve()
    report = frozen.build_report(directory, root=root)
    manifest = read_json(directory / "manifest.json")
    lock = read_json(directory / "execution-lock.json")
    report = annotate_report(directory, report, manifest, lock, root=root)
    supplement = build_supplement(directory, root=root)
    result = apply_supplement(report, supplement, manifest)
    result = annotate_single_infra_retry(result, directory, manifest, lock, root=root)
    result["analysis_provenance"] = {
        **result.get("analysis_provenance", {}),
        "capture_supplement_wrapper_sha256": file_hash(root / "scripts/analyze_release_v2_supplement.py"),
    }
    return result


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--directory", required=True, type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args(argv)
    try:
        report = build_supplemented_report(args.directory)
        if args.output:
            output = args.output.resolve()
            if not output.is_relative_to(args.directory.resolve()) or output.exists():
                raise V2Error("report must be a new file within the experiment")
            output.parent.mkdir(parents=True, exist_ok=True)
            with output.open("x", encoding="utf-8", newline="\n") as handle:
                json.dump(report, handle, ensure_ascii=False, indent=2, allow_nan=False)
                handle.write("\n")
        complete = report["completeness"]
        print(json.dumps({"accepted": report["accepted"],
                          "formal_ranking_eligible": report["formal_ranking_eligible"],
                          "legal_unique": complete["legal_unique"], "missing": len(complete["missing"]),
                          "issues": report["issues"],
                          "supported_negative_observations": 2}, ensure_ascii=False))
        return 0 if report["accepted"] else 2
    except (OSError, ValueError, KeyError, TypeError) as error:
        print(json.dumps({"accepted": False, "reason": str(error)}, ensure_ascii=False))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
