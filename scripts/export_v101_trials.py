"""Sanitized canonical trials + empirical difficulty from the coverage merge.

Does not overwrite locked-core.json, locked-core-k3.json, or
locked-hard-release-k3.json.

    python scripts/export_v101_trials.py
    python scripts/export_v101_trials.py --write
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from build_canonical_matrix import BANK_62, FROZEN_LOCKS, merge_rows  # noqa: E402
from item_metadata import construct_metadata  # noqa: E402
from run_locked import attempt_of  # noqa: E402
from score_standard import atom_of  # noqa: E402
from task_sets import HARD_RELEASE_15  # noqa: E402

TRIALS_OUT = ROOT / "results" / "v1.0.1_trials.jsonl"
LABELS_OUT = ROOT / "results" / "v1.0.1_difficulty.json"

FLOOR = (
    "llama-3.2-3b-instruct",
    "ministral-3b-2512",
    "gemma-3-4b-it",
)
TARGET = "qwen3.5-9b"
RULER = "qwen3.8-27b"

KEEP = (
    "lock_id",
    "task",
    "atom",
    "attempt",
    "atomic_correct",
    "termination",
    "timeout_kind",
    "infra_retries",
    "reason",
    "agent_version",
    "temperature",
    "thinking",
    "openrouter_provider",
    "rerun_reason",
)


def job_basename(job: Any) -> str | None:
    if not isinstance(job, str) or not job:
        return None
    return Path(job).name


def sanitize(row: dict[str, Any]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for key in KEEP:
        if key in row:
            out[key] = row[key]
    out["attempt"] = attempt_of(row)
    out["atom"] = row.get("atom") or atom_of(str(row.get("task") or ""))
    out["job"] = job_basename(row.get("job"))
    if row.get("rerun_of"):
        out["rerun_of"] = job_basename(row.get("rerun_of"))
    return out


def task_counts(
    rows: list[dict[str, Any]], lock_id: str, task: str
) -> tuple[int, int, int]:
    mine = [
        r
        for r in rows
        if r.get("lock_id") == lock_id and r.get("task") == task
    ]
    atomic = sum(int(r.get("atomic_correct") or 0) for r in mine)
    e2e = sum(
        1
        for r in mine
        if r.get("atomic_correct") == 1 and r.get("termination") == "clean"
    )
    return atomic, e2e, len(mine)


def label_of(
    n9: int,
    n27: int,
    floor_hit: bool,
) -> str:
    if n9 == 0 and n27 == 3:
        return "hard"
    if n9 == 0:
        return "uncalibrated"
    if n9 == 3 and floor_hit:
        return "easy"
    return "medium"


def difficulty_table(rows: list[dict[str, Any]]) -> dict[str, Any]:
    constructs = construct_metadata()
    by_task: dict[str, dict[str, Any]] = {}
    buckets: dict[str, list[str]] = defaultdict(list)
    for task in BANK_62:
        n9, e9, k9 = task_counts(rows, TARGET, task)
        n27, e27, k27 = task_counts(rows, RULER, task)
        floor_hit = False
        floor_ok = 0
        for floor in FLOOR:
            na, _ne, _k = task_counts(rows, floor, task)
            floor_ok += na
            if na >= 1:
                floor_hit = True
        band = label_of(n9, n27, floor_hit)
        construct = constructs[task]
        empirical_band = "out_of_range" if band == "uncalibrated" else band
        rec = {
            "task": task,
            "atom": atom_of(task),
            "label": band,
            "construct_difficulty": construct["construct_difficulty"],
            "difficulty_weight": construct["difficulty_weight"],
            "trap_id": construct["trap_id"],
            "empirical_band": empirical_band,
            "calibration_status": (
                "out_of_range"
                if empirical_band == "out_of_range"
                else "calibrated"
            ),
            "n9_atomic": n9,
            "n9_e2e": e9,
            "k9": k9,
            "n27_atomic": n27,
            "n27_e2e": e27,
            "k27": k27,
            "floor_atomic": floor_ok,
            "in_hard_release_15": task in HARD_RELEASE_15,
        }
        by_task[task] = rec
        buckets[band].append(task)
    counts = {k: len(v) for k, v in buckets.items()}
    construct_counts: dict[str, int] = defaultdict(int)
    for rec in by_task.values():
        construct_counts[rec["construct_difficulty"]] += 1
    return {
        "kind": "v1.0.1_difficulty",
        "semantics": {
            "construct_difficulty": (
                "Author-designed Easy/Medium/Hard tier; determines score weight."
            ),
            "empirical_band": (
                "Observed location under the frozen v1.0.1 calibration ladder."
            ),
            "label": "Legacy alias for the empirical calibration label.",
        },
        "difficulty_weights": {"easy": 1.0, "medium": 1.5, "hard": 2.0},
        "construct_counts": {
            key: construct_counts.get(key, 0)
            for key in ("easy", "medium", "hard")
        },
        "rule": (
            "Easy = floor 3B/4B Atomic>=1 once and 9B 3/3. "
            "Hard = 9B 0/3 and 27B Atomic 3/3. "
            "Uncalibrated = 9B 0/3 and 27B not 3/3. "
            "Medium = otherwise."
        ),
        "n_labeled": 62 - counts.get("uncalibrated", 0),
        "counts": {
            "easy": counts.get("easy", 0),
            "medium": counts.get("medium", 0),
            "hard": counts.get("hard", 0),
            "uncalibrated": counts.get("uncalibrated", 0),
        },
        "tasks": by_task,
        "buckets": {k: v for k, v in buckets.items()},
    }


def hard15_slice(rows: list[dict[str, Any]], lock_id: str) -> dict[str, Any]:
    atomic = 0
    e2e = 0
    by_atom: dict[str, list[int]] = defaultdict(list)
    for task in HARD_RELEASE_15:
        na, ne, k = task_counts(rows, lock_id, task)
        assert k == 3, (lock_id, task, k)
        atomic += na
        e2e += ne
        by_atom[atom_of(task)].append(na)
    skills = {atom: sum(vals) / (3 * len(vals)) for atom, vals in by_atom.items()}
    return {
        "lock_id": lock_id,
        "atomic_ok": atomic,
        "e2e_ok": e2e,
        "n": 45,
        "skills_atomic": skills,
    }


def assert_not_frozen(path: Path) -> None:
    resolved = path.resolve()
    for frozen in FROZEN_LOCKS:
        if resolved == frozen.resolve():
            raise SystemExit(f"refusing to write frozen lock {frozen}")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--write", action="store_true")
    args = parser.parse_args()
    rows, _applied = merge_rows()
    labels = difficulty_table(rows)
    trials = [sanitize(r) for r in rows]
    print("===== V1.0.1 TRIALS / DIFFICULTY =====")
    print(f"n_trials {len(trials)}")
    print("counts", labels["counts"])
    print("n_labeled", labels["n_labeled"])
    print("hard", labels["buckets"].get("hard"))
    print("uncalibrated", labels["buckets"].get("uncalibrated"))
    print("easy", labels["buckets"].get("easy"))
    for lock_id in (TARGET, RULER):
        sl = hard15_slice(rows, lock_id)
        print(
            f"hard15 {lock_id} atomic {sl['atomic_ok']}/45 "
            f"e2e {sl['e2e_ok']}/45"
        )
    changed = [
        t
        for t in (
            "loc-failing-test-impl",
            "loc-similar-filenames",
            "loc-traceback-helper",
            "loc-vip-two-files",
            "loc-unused-fix",
            "loc-reexport",
            "repro-nested-alias",
            "repro-stale-quote",
            "review-rotate-right",
        )
        if t in labels["tasks"]
    ]
    print("\ncalibrator items:")
    for task in changed:
        rec = labels["tasks"][task]
        print(
            f"  {task} 9B {rec['n9_atomic']}/3 27B {rec['n27_atomic']}/3 "
            f"e2e27 {rec['n27_e2e']}/3 {rec['label']}"
        )
    if args.write:
        assert_not_frozen(TRIALS_OUT)
        assert_not_frozen(LABELS_OUT)
        TRIALS_OUT.parent.mkdir(parents=True, exist_ok=True)
        with TRIALS_OUT.open("w", encoding="utf-8") as fh:
            for rec in trials:
                fh.write(json.dumps(rec, ensure_ascii=True) + "\n")
        LABELS_OUT.write_text(
            json.dumps(labels, indent=2) + "\n", encoding="utf-8"
        )
        print(f"\nwrote {TRIALS_OUT}")
        print(f"wrote {LABELS_OUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
