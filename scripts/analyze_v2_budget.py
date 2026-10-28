"""Descriptive paired budget diagnostics. No ranking or model execution."""

from __future__ import annotations

import argparse
from collections import defaultdict
import json
from pathlib import Path

from analyze_v2 import build_report
from v2_pipeline import ROOT, V2Error, read_json


def paired_summary(report, manifest):
    diagnostic = manifest.get("diagnostic")
    if diagnostic is None or report.get("formal_ranking_eligible") is not False:
        raise V2Error("paired budget analysis requires a non-ranking diagnostic")
    by_task = defaultdict(list)
    for condition in diagnostic["conditions"]:
        for task in condition["tasks"]:
            by_task[task].append(condition)
    cells = {(row["model"], row["task"], row["condition"]): row
             for row in report["canonical_rows"]}
    pairs = []
    for model in sorted(manifest["models"]):
        for task, conditions in sorted(by_task.items()):
            if len(conditions) != 2:
                raise V2Error("each diagnostic task needs exactly two frozen conditions")
            changed = [key for key in ("agent_timeout_sec", "max_turns")
                       if conditions[0][key] != conditions[1][key]]
            if len(changed) != 1:
                raise V2Error("paired analysis requires exactly one varying budget")
            budget = changed[0]
            lower, higher = sorted(conditions, key=lambda row: row[budget])
            low = cells.get((model, task, lower["name"]))
            high = cells.get((model, task, higher["name"]))
            pair = {"model": model, "task": task, "varied_budget": budget,
                    "lower_condition": lower["name"], "higher_condition": higher["name"],
                    "lower_budget": lower[budget], "higher_budget": higher[budget],
                    "complete_pair": low is not None and high is not None,
                    "lower": low, "higher": high,
                    "artifact_delta": None, "clean_delta": None}
            if pair["complete_pair"]:
                pair.update(artifact_delta=int(high["artifact"]) - int(low["artifact"]),
                            clean_delta=int(high["clean"]) - int(low["clean"]))
            pairs.append(pair)
    return {
        "schema_version": 1,
        "kind": "smallowbench_v2_budget_diagnostic_pairs",
        "manifest_sha256": manifest["manifest_sha256"],
        "accepted": report["accepted"],
        "formal_ranking_eligible": False,
        "selection_rationale": diagnostic["selection_rationale"],
        "limitations": [
            "Symptom-selected sample, not a population estimate or a leaderboard.",
            "One observation per condition; paired differences are descriptive, not significance tests.",
            "API call time includes generation, service queueing and transport; these are not separated.",
            "Condition order is reversed across models but there is no within-model replication.",
        ],
        "complete_pairs": sum(pair["complete_pair"] for pair in pairs),
        "planned_pairs": len(pairs),
        "pairs": pairs,
        "execution_performed": False,
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--directory", type=Path, required=True)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args(argv)
    try:
        manifest = read_json(args.directory / "manifest.json")
        report = build_report(args.directory, root=ROOT)
        result = paired_summary(report, manifest)
        text = json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False)
        if args.output:
            with args.output.open("x", encoding="utf-8", newline="\n") as stream:
                stream.write(text + "\n")
        print(json.dumps({key: value for key, value in result.items() if key != "pairs"},
                         ensure_ascii=False, allow_nan=False))
        return 0 if result["accepted"] else 2
    except (OSError, ValueError, KeyError, TypeError) as exc:
        print(json.dumps({"accepted": False, "error": str(exc)}, ensure_ascii=False))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
