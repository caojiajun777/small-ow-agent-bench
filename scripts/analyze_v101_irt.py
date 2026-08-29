"""Exploratory Rasch analysis for the complete v1.0.1 response matrix.

This analysis validates task calibration; it does not replace the transparent
1 / 1.5 / 2 leaderboard score.  Each model-task cell is Binomial(3, p).

    python scripts/analyze_v101_irt.py
    python scripts/analyze_v101_irt.py --write
"""

from __future__ import annotations

import argparse
import json
import math
import statistics
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from fit_irt import (  # noqa: E402
    fit_1pl,
    spearman,
    split_calibrated,
    split_persons,
)
from item_metadata import BANK_62, item_metadata  # noqa: E402

TRIALS = ROOT / "results" / "v1.0.1_trials.jsonl"
COVERAGE = ROOT / "results" / "canonical-coverage.json"
OUT = ROOT / "results" / "v1.0.1_irt.json"
N_TRIALS = 3
ATOMS = ("loc", "edit", "testgen", "repro", "review")


def pearson(xs: list[float], ys: list[float]) -> float | None:
    if len(xs) < 3 or len(xs) != len(ys):
        return None
    mx = statistics.mean(xs)
    my = statistics.mean(ys)
    dx = [x - mx for x in xs]
    dy = [y - my for y in ys]
    den = math.sqrt(sum(x * x for x in dx) * sum(y * y for y in dy))
    if den < 1e-12:
        return None
    return sum(x * y for x, y in zip(dx, dy)) / den


def load_matrix() -> tuple[dict[str, dict[str, int]], list[str], dict[str, str]]:
    rows = [
        json.loads(line)
        for line in TRIALS.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    coverage = json.loads(COVERAGE.read_text(encoding="utf-8"))
    models = [row["lock_id"] for row in coverage["models"]]
    display = {row["lock_id"]: row["display"] for row in coverage["models"]}
    counts: dict[tuple[str, str], int] = defaultdict(int)
    seen: dict[tuple[str, str], int] = defaultdict(int)
    for row in rows:
        key = (row["task"], row["lock_id"])
        counts[key] += int(row["atomic_correct"])
        seen[key] += 1
    matrix = {
        task: {model: counts[(task, model)] for model in models}
        for task in BANK_62
    }
    bad = [key for key, n in seen.items() if n != N_TRIALS]
    missing = [
        (task, model)
        for task in BANK_62
        for model in models
        if seen[(task, model)] != N_TRIALS
    ]
    if bad or missing:
        raise ValueError(f"response matrix is incomplete: bad={bad[:3]} missing={missing[:3]}")
    return matrix, models, display


def corrected_item_total(
    matrix: dict[str, dict[str, int]], models: list[str], task: str
) -> float | None:
    item = [matrix[task][model] / N_TRIALS for model in models]
    rest = [
        statistics.mean(
            matrix[other][model] / N_TRIALS for other in matrix if other != task
        )
        for model in models
    ]
    return pearson(item, rest)


def fit_atom(
    matrix: dict[str, dict[str, int]], models: list[str], atom: str
) -> dict[str, Any]:
    subset = {task: row for task, row in matrix.items() if task.startswith(f"{atom}-")}
    calibrated, all_zero, all_full = split_calibrated(
        subset, models, n_trials=N_TRIALS
    )
    persons, person_zero, person_full = split_persons(
        calibrated, models, n_trials=N_TRIALS
    )
    theta, difficulty = fit_1pl(calibrated, persons, n_trials=N_TRIALS)
    return {
        "n_items": len(subset),
        "n_items_fitted": len(calibrated),
        "n_models_fitted": len(persons),
        "all_zero_items": all_zero,
        "all_full_items": all_full,
        "all_zero_models": person_zero,
        "all_full_models": person_full,
        "theta": {model: theta[model] for model in persons},
        "item_difficulty": difficulty,
    }


def analyze() -> dict[str, Any]:
    matrix, models, display = load_matrix()
    metadata = item_metadata()
    calibrated, all_zero, all_full = split_calibrated(
        matrix, models, n_trials=N_TRIALS
    )
    persons, person_zero, person_full = split_persons(
        calibrated, models, n_trials=N_TRIALS
    )
    theta, difficulty = fit_1pl(calibrated, persons, n_trials=N_TRIALS)

    item_rows: list[dict[str, Any]] = []
    for task in BANK_62:
        counts = [matrix[task][model] for model in models]
        item_rows.append(
            {
                "task": task,
                "atom": metadata[task]["skill"],
                "trap_id": metadata[task]["trap_id"],
                "construct_difficulty": metadata[task]["construct_difficulty"],
                "empirical_band": metadata[task]["empirical_band"],
                "pass_rate": sum(counts) / (N_TRIALS * len(models)),
                "rasch_b": difficulty.get(task),
                "corrected_item_total_r": corrected_item_total(matrix, models, task),
            }
        )

    tier_summary: dict[str, dict[str, Any]] = {}
    for tier in ("easy", "medium", "hard"):
        rows = [row for row in item_rows if row["construct_difficulty"] == tier]
        bs = [float(row["rasch_b"]) for row in rows if row["rasch_b"] is not None]
        rs = [
            float(row["corrected_item_total_r"])
            for row in rows
            if row["corrected_item_total_r"] is not None
        ]
        tier_summary[tier] = {
            "n": len(rows),
            "mean_pass_rate": statistics.mean(row["pass_rate"] for row in rows),
            "mean_rasch_b": statistics.mean(bs) if bs else None,
            "median_rasch_b": statistics.median(bs) if bs else None,
            "mean_corrected_item_total_r": statistics.mean(rs) if rs else None,
        }

    ordinal = {"easy": 0.0, "medium": 1.0, "hard": 2.0}
    fitted_rows = [row for row in item_rows if row["rasch_b"] is not None]
    construct_irt_spearman = spearman(
        [ordinal[row["construct_difficulty"]] for row in fitted_rows],
        [float(row["rasch_b"]) for row in fitted_rows],
    )
    negative_discrimination = [
        row["task"]
        for row in item_rows
        if row["corrected_item_total_r"] is not None
        and float(row["corrected_item_total_r"]) < 0
    ]
    weak_discrimination = [
        row["task"]
        for row in item_rows
        if row["corrected_item_total_r"] is not None
        and float(row["corrected_item_total_r"]) < 0.2
    ]

    ranked_models = sorted(persons, key=lambda model: theta[model], reverse=True)
    return {
        "kind": "v1.0.1_irt_1pl_binomial",
        "published": False,
        "role": "diagnostic analysis; does not determine leaderboard weights",
        "note": (
            "Exploratory 1PL Rasch JML on 16 configurations x 62 tasks x 3 trials. "
            "All-zero/all-full items have no finite MLE and are excluded. "
            "Corrected item-total r is a small-sample discrimination diagnostic, "
            "not a fitted 2PL parameter."
        ),
        "n_trials_per_cell": N_TRIALS,
        "n_models": len(models),
        "n_items": len(matrix),
        "n_items_fitted": len(calibrated),
        "all_zero_items": all_zero,
        "all_full_items": all_full,
        "all_zero_models": person_zero,
        "all_full_models": person_full,
        "construct_irt_spearman": construct_irt_spearman,
        "tier_summary": tier_summary,
        "negative_discrimination_items": negative_discrimination,
        "weak_discrimination_items_lt_0_2": weak_discrimination,
        "models": [
            {"lock_id": model, "display": display[model], "theta": theta[model]}
            for model in ranked_models
        ],
        "items": item_rows,
        "by_atom": {atom: fit_atom(matrix, models, atom) for atom in ATOMS},
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--write", action="store_true")
    args = parser.parse_args()
    payload = analyze()
    print("items", payload["n_items_fitted"], "/", payload["n_items"])
    print("all_zero", payload["all_zero_items"])
    print("construct_irt_spearman", round(payload["construct_irt_spearman"], 3))
    for tier, row in payload["tier_summary"].items():
        print(
            tier,
            "n", row["n"],
            "pass", round(row["mean_pass_rate"], 3),
            "b", None if row["mean_rasch_b"] is None else round(row["mean_rasch_b"], 3),
            "r", (
                None
                if row["mean_corrected_item_total_r"] is None
                else round(row["mean_corrected_item_total_r"], 3)
            ),
        )
    print("negative_discrimination", payload["negative_discrimination_items"])
    print("weak_discrimination_n", len(payload["weak_discrimination_items_lt_0_2"]))
    if args.write:
        OUT.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
        print(f"wrote {OUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

