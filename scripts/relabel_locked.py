"""Relabel the frozen 490-cell matrix. Does not overwrite locked-core.json.

Same jobs, three response matrices:

    A  atomic_correct          (task artifact)
    T  termination == clean    (halt policy)
    E  A and T                 (E2E leaderboard)

Unfinished cells stay 0/1. Only infra is missing.

    python scripts/relabel_locked.py
    python scripts/relabel_locked.py jobs/locked-core.json
"""

from __future__ import annotations

import json
import math
import re
import sys
from collections import Counter
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from std_normalize import file_set  # noqa: E402
from task_sets import MAIN_47  # noqa: E402

CORE = ROOT / "jobs" / "locked-core.json"
PROTO = ROOT / "jobs" / "protocol-check.json"
OUT = ROOT / "jobs" / "locked-matrices.json"

GOT_EXP = re.compile(
    r"got (?P<got>\[[^\]]*\]), expected (?P<exp>\[[^\]]*\])",
    re.IGNORECASE,
)
NO_ANSWER = "File /app/answer.txt does not exist"

FAIL_KINDS = (
    "task_pass_clean",
    "task_pass_unfinished",
    "task_fail_clean",
    "task_fail_unfinished",
    "format_fail",
    "no_attempt",
    "infra_fail",
)


def sidecar_of(job: str | None) -> dict[str, Any]:
    if not job:
        return {}
    root = Path(job)
    for path in root.glob("*/agent/compact-shell.json"):
        try:
            blob = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            return {}
        return blob if isinstance(blob, dict) else {}
    return {}


def verifier_stdout(job: str | None) -> str:
    if not job:
        return ""
    root = Path(job)
    for path in root.glob("*/verifier/test-stdout.txt"):
        return path.read_text(encoding="utf-8", errors="replace")
    return ""


def loc_gold(task: str) -> set[str]:
    path = ROOT / "tasks" / task / "tests" / "expected.txt"
    if not path.is_file():
        return set()
    return file_set(path.read_text(encoding="utf-8"))


def loc_pred_from_stdout(text: str) -> set[str] | None:
    if NO_ANSWER in text:
        return set()
    match = GOT_EXP.search(text)
    if not match:
        return None
    raw = match.group("got")
    try:
        names = json.loads(raw.replace("'", '"'))
    except json.JSONDecodeError:
        return None
    if not isinstance(names, list):
        return None
    return file_set("\n".join(str(n) for n in names))


def loc_pr(pred: set[str] | None, gold: set[str]) -> dict[str, float | None]:
    if pred is None or not gold:
        return {"precision": None, "recall": None, "n_pred": None, "n_gold": len(gold)}
    inter = pred & gold
    precision = len(inter) / len(pred) if pred else None
    recall = len(inter) / len(gold)
    return {
        "precision": precision,
        "recall": recall,
        "n_pred": len(pred),
        "n_gold": len(gold),
    }


def classify(row: dict[str, Any], sidecar: dict[str, Any]) -> str:
    if row.get("termination") == "infra":
        return "infra_fail"
    try:
        n_shell = int(sidecar.get("n_shell") or 0)
    except (TypeError, ValueError):
        n_shell = 0
    try:
        n_parse = int(sidecar.get("n_parse_fail") or 0)
    except (TypeError, ValueError):
        n_parse = 0
    if n_shell == 0 and n_parse > 0:
        return "format_fail"
    if n_shell == 0:
        return "no_attempt"
    atomic = 1 if row.get("atomic_correct") == 1 else 0
    clean = row.get("termination") == "clean"
    if atomic and clean:
        return "task_pass_clean"
    if atomic and not clean:
        return "task_pass_unfinished"
    if (not atomic) and clean:
        return "task_fail_clean"
    return "task_fail_unfinished"


def pearson(xs: list[float], ys: list[float]) -> float | None:
    if len(xs) < 3 or len(xs) != len(ys):
        return None
    mx = sum(xs) / len(xs)
    my = sum(ys) / len(ys)
    num = sum((a - mx) * (b - my) for a, b in zip(xs, ys))
    denx = math.sqrt(sum((a - mx) ** 2 for a in xs))
    deny = math.sqrt(sum((b - my) ** 2 for b in ys))
    if denx < 1e-12 or deny < 1e-12:
        return None
    return num / (denx * deny)


def item_roles(
    matrix: dict[str, dict[str, int | None]], models: list[str]
) -> dict[str, dict]:
    out: dict[str, dict] = {}
    for task, row in matrix.items():
        vals = [row[m] for m in models if row.get(m) is not None]
        if not vals:
            role = "incomplete"
        elif all(v == 1 for v in vals):
            role = "all_pass"
        elif all(v == 0 for v in vals):
            role = "uncalibrated_above_range"
        else:
            role = "irt_candidate"
        scores: list[float] = []
        items: list[float] = []
        for m in models:
            x = row.get(m)
            if x is None:
                continue
            rest = [
                matrix[other][m]
                for other in matrix
                if other != task and matrix[other].get(m) is not None
            ]
            if not rest:
                continue
            items.append(float(x))
            scores.append(float(sum(rest)))
        out[task] = {
            "role": role,
            "n_scored": len(vals),
            "p": (sum(vals) / len(vals)) if vals else None,
            "corrected_item_total_r": pearson(items, scores),
        }
    return out


def _cell(row: dict[str, Any], sidecar: dict[str, Any]) -> dict[str, Any]:
    term = row.get("termination")
    atomic: int | None
    if term == "infra" or row.get("atomic_correct") is None:
        atomic = None
    else:
        atomic = 1 if row.get("atomic_correct") == 1 else 0
    clean = 1 if term == "clean" else 0 if atomic is not None else None
    e2e = None if atomic is None or clean is None else int(atomic == 1 and clean == 1)
    cell = {
        "lock_id": row["lock_id"],
        "task": row["task"],
        "atom": row.get("atom"),
        "A": atomic,
        "T": clean,
        "E": e2e,
        "fail_kind": classify(row, sidecar),
        "termination": term,
        "n_shell": sidecar.get("n_shell"),
        "n_parse_fail": sidecar.get("n_parse_fail"),
        "finished": sidecar.get("finished"),
        "job": row.get("job"),
    }
    if (row.get("atom") or "") == "loc":
        gold = loc_gold(row["task"])
        pred = loc_pred_from_stdout(verifier_stdout(row.get("job")))
        if pred is None and atomic == 1:
            pred = set(gold)
        diag = loc_pr(pred, gold)
        cell["loc_pred"] = sorted(pred) if pred is not None else None
        cell["loc_gold"] = sorted(gold)
        cell.update(diag)
    return cell


def _matrix(
    cells: list[dict[str, Any]], key: str, models: list[str]
) -> dict[str, dict[str, int | None]]:
    grid: dict[str, dict[str, int | None]] = {t: {} for t in MAIN_47}
    for cell in cells:
        task = cell["task"]
        if task not in grid:
            continue
        grid[task][cell["lock_id"]] = cell[key]
    for task in grid:
        for model in models:
            grid[task].setdefault(model, None)
    return grid


def _means(
    grid: dict[str, dict[str, int | None]], models: list[str]
) -> dict[str, float | None]:
    out: dict[str, float | None] = {}
    for model in models:
        vals = [row[model] for row in grid.values() if row.get(model) is not None]
        out[model] = (sum(vals) / len(vals)) if vals else None
    return out


def _preflight(path: Path) -> list[dict[str, Any]]:
    if not path.is_file():
        return []
    data = json.loads(path.read_text(encoding="utf-8"))
    rows = []
    for subject in data.get("subjects") or []:
        tasks = subject.get("tasks") or {}
        both = all(
            (tasks.get(name) or {}).get("atomic_correct") == 1
            and (tasks.get(name) or {}).get("termination") == "clean"
            for name in ("hello-world", "collect-todos")
        )
        rows.append(
            {
                "id": subject.get("id"),
                "preflight_both_pass": both,
                "legacy_protocol_pass": subject.get("protocol_pass"),
                "tasks": tasks,
            }
        )
    return rows


def relabel(core_path: Path) -> dict[str, Any]:
    data = json.loads(core_path.read_text(encoding="utf-8"))
    models = list(data.get("models") or [])
    cells = [_cell(row, sidecar_of(row.get("job"))) for row in data.get("rows") or []]
    atomic = _matrix(cells, "A", models)
    term = _matrix(cells, "T", models)
    e2e = _matrix(cells, "E", models)
    kinds = Counter(c["fail_kind"] for c in cells)
    by_model: dict[str, dict[str, int]] = {
        m: dict(Counter(c["fail_kind"] for c in cells if c["lock_id"] == m))
        for m in models
    }
    loc_cells = [c for c in cells if c.get("atom") == "loc"]
    report = {
        "kind": "locked_matrices_k1",
        "published": False,
        "source": str(core_path),
        "overwrites_source": False,
        "n_cells": len(cells),
        "models": models,
        "judgment": (
            "Engineering path succeeded. Core is a valid E2E exploratory matrix. "
            "legacy protocol_pass is preflight_both_pass, not harness compatibility. "
            "Failures mix atomic ability, format compliance, and termination policy."
        ),
        "preflight": _preflight(PROTO),
        "fail_kind_counts": {k: kinds.get(k, 0) for k in FAIL_KINDS},
        "fail_kind_by_model": by_model,
        "means": {
            "atomic": _means(atomic, models),
            "termination": _means(term, models),
            "e2e": _means(e2e, models),
        },
        "item_roles": {
            "atomic": item_roles(atomic, models),
            "e2e": item_roles(e2e, models),
        },
        "loc_diagnostics": [
            {
                "lock_id": c["lock_id"],
                "task": c["task"],
                "A": c["A"],
                "fail_kind": c["fail_kind"],
                "precision": c.get("precision"),
                "recall": c.get("recall"),
                "loc_pred": c.get("loc_pred"),
                "loc_gold": c.get("loc_gold"),
            }
            for c in loc_cells
        ],
        "cells": cells,
    }
    return report


def main() -> int:
    path = CORE
    args = [a for a in sys.argv[1:] if not a.startswith("-")]
    if args:
        path = Path(args[0])
    if not path.is_file():
        print(f"missing {path}", file=sys.stderr)
        return 2
    report = relabel(path)
    OUT.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    means = report["means"]
    print("===== LOCKED MATRICES (source frozen) =====")
    print(f"cells {report['n_cells']}  wrote {OUT}")
    print("fail_kind", report["fail_kind_counts"])
    print(
        "atomic_mean",
        {k: None if v is None else round(v, 3) for k, v in means["atomic"].items()},
    )
    print(
        "e2e_mean   ",
        {k: None if v is None else round(v, 3) for k, v in means["e2e"].items()},
    )
    atomic_roles = report["item_roles"]["atomic"]
    above = [
        t
        for t, meta in atomic_roles.items()
        if meta["role"] == "uncalibrated_above_range"
    ]
    print(f"uncalibrated_above_range {len(above)} {above}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
