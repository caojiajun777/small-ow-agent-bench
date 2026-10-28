"""Annotate the frozen RC2 analysis with the explicit monetary-cap amendment."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from analyze_release_v2 import build_report
from release_v2_fee_waiver_executor import validate_fee_waiver
from release_v2_pipeline import ROOT, V2Error, file_hash, read_json, read_visits


def annotate_report(directory, report, manifest, lock, *, root=ROOT):
    directory, root = Path(directory).resolve(), Path(root).resolve()
    if report.get("manifest_sha256") != manifest.get("manifest_sha256"):
        raise V2Error("base analysis and amended run have different identities")
    waiver_sha = validate_fee_waiver(directory, manifest, lock, root=root)
    waiver = read_json(directory / "fee-waiver.json")
    initial = waiver["initial_scored_visits_sha256"]
    visits, read_issues = read_visits(directory)
    issues = list(report.get("issues", []))
    issues.extend(read_issues)
    jobs = {row.get("job_name"): row for row in visits}
    for job, expected_sha in initial.items():
        row = jobs.get(job)
        if (row is None or row.get("status") != "scored"
                or file_hash(directory / "visits" / (job + ".json")) != expected_sha):
            issues.append({"kind": "initial_scored_visit_changed", "job": job})
    continuation = [row for row in visits if row.get("job_name") not in initial]
    for row in continuation:
        if row.get("fee_waiver_sha256") != waiver_sha:
            issues.append({"kind": "continuation_missing_fee_waiver", "job": row.get("job_name")})
    annotated = dict(report)
    annotated["base_analysis_kind"] = report.get("kind")
    annotated["kind"] = "smallowbench_v2_release_fee_waiver_report"
    annotated["actual_execution_policy"] = {
        "monetary_cap_enforced": False,
        "monetary_cap_usd": None,
        "original_manifest_monetary_cap_usd": manifest["caps"]["budget_usd"],
        "original_cap_scope": "initial execution phase before the explicit user amendment",
        "amendment_approved_at": waiver.get("approved_at"),
        "fee_waiver_sha256": waiver_sha,
        "fee_waiver_file": "fee-waiver.json",
        "fees": "recorded; unknown fees remain unknown and do not block admissions",
        "max_task_attempts": manifest["caps"]["max_total_visits"],
        "max_visits_per_slot": manifest["caps"]["max_visits_per_slot"],
        "workers": manifest["caps"]["workers"],
        "evaluation_configuration": "original model pins, prompts, token/turn/time limits, tasks and graders unchanged",
    }
    annotated["execution_phases"] = {
        "initial_scored_visits": len(initial),
        "continuation_visits": len(continuation),
        "continuation_scored_visits": sum(row.get("status") == "scored" for row in continuation),
        "initial_scored_visit_bytes_unchanged": not any(
            issue.get("kind") == "initial_scored_visit_changed" for issue in issues
        ),
    }
    annotated["analysis_provenance"] = {
        "frozen_analyzer_sha256": file_hash(root / "scripts" / "analyze_release_v2.py"),
        "amendment_analyzer_sha256": file_hash(root / "scripts" / "analyze_release_v2_fee_waiver.py"),
        "scoring_semantics": "unchanged; this wrapper validates and reports operational fee-policy provenance",
        "model_execution_performed": False,
    }
    annotated["issues"] = issues
    annotated["accepted"] = bool(report.get("accepted")) and not issues
    annotated["formal_ranking_eligible"] = bool(report.get("formal_ranking_eligible")) and not issues
    if not annotated["formal_ranking_eligible"]:
        annotated["leaderboard"] = {}
    return annotated


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--directory", type=Path, required=True)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args(argv)
    try:
        report = build_report(args.directory)
        report = annotate_report(
            args.directory, report, read_json(args.directory / "manifest.json"),
            read_json(args.directory / "execution-lock.json"),
        )
        if args.output is not None:
            output = args.output.resolve()
            if not output.is_relative_to(args.directory.resolve()) or output.exists():
                raise V2Error("analysis output must be a new file inside the experiment")
            output.parent.mkdir(parents=True, exist_ok=True)
            with output.open("x", encoding="utf-8", newline="\n") as handle:
                json.dump(report, handle, ensure_ascii=False, indent=2, allow_nan=False)
                handle.write("\n")
        completeness = report["completeness"]
        print(json.dumps({
            "accepted": report["accepted"],
            "formal_ranking_eligible": report["formal_ranking_eligible"],
            "planned": completeness["planned"],
            "legal_unique": completeness["legal_unique"],
            "missing": len(completeness["missing"]),
            "issue_count": len(report["issues"]),
            "actual_execution_policy": report["actual_execution_policy"],
            "execution_phases": report["execution_phases"],
        }, ensure_ascii=False, allow_nan=False))
        return 0 if report["accepted"] else 2
    except (OSError, ValueError, KeyError, TypeError) as exc:
        print(json.dumps({"accepted": False, "error": str(exc)}, ensure_ascii=False))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
