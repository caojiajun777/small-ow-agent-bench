"""Hard-15 failure composition from the frozen lock JSON.

Lock fields only (reproducible without Harbor job dirs):

    task_pass_clean / task_pass_unfinished
    task_fail_clean / task_fail_unfinished
    infra_fail

Sidecar kinds (format_fail, no_attempt) are optional extras when the job
dir still has compact-shell.json. They do not replace the lock 4-way table.

    python scripts/fail_compose.py
    python scripts/fail_compose.py jobs/locked-hard-release-k3.json
"""

from __future__ import annotations

import json
import sys
from collections import Counter
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from relabel_locked import FAIL_KINDS, classify, sidecar_of  # noqa: E402
from score_standard import atom_of  # noqa: E402

HARD_LOCK = ROOT / "jobs" / "locked-hard-release-k3.json"
OUT = ROOT / "jobs" / "locked-hard-failure.json"

LOCK_KINDS = (
    "task_pass_clean",
    "task_pass_unfinished",
    "task_fail_clean",
    "task_fail_unfinished",
    "infra_fail",
)


def classify_lock(row: dict[str, Any]) -> str:
    if row.get("termination") == "infra" or row.get("reason") in {"infra", "no_job"}:
        return "infra_fail"
    atomic = 1 if row.get("atomic_correct") == 1 else 0
    clean = row.get("termination") == "clean"
    if atomic and clean:
        return "task_pass_clean"
    if atomic and not clean:
        return "task_pass_unfinished"
    if (not atomic) and clean:
        return "task_fail_clean"
    return "task_fail_unfinished"


def sidecar_found(job: str | None) -> bool:
    if not job:
        return False
    root = Path(job)
    if not root.is_dir():
        return False
    return any(root.glob("*/agent/compact-shell.json"))


def compose(rows: list[dict[str, Any]]) -> dict[str, Any]:
    scored = [
        r
        for r in rows
        if r.get("task") and r.get("lock_id") and r.get("attempt") in (1, 2, 3)
    ]
    cells: list[dict[str, Any]] = []
    for row in scored:
        lock_kind = classify_lock(row)
        job = row.get("job")
        extra = None
        if sidecar_found(job if isinstance(job, str) else None):
            extra = classify(row, sidecar_of(job))
        cells.append(
            {
                "lock_id": row["lock_id"],
                "task": row["task"],
                "atom": row.get("atom") or atom_of(row["task"]),
                "attempt": row["attempt"],
                "atomic_correct": int(row.get("atomic_correct") or 0),
                "termination": row.get("termination"),
                "lock_kind": lock_kind,
                "sidecar_kind": extra,
            }
        )

    def _counts(kind_key: str, kinds: tuple[str, ...]) -> dict[str, int]:
        c = Counter(cell[kind_key] for cell in cells if cell.get(kind_key))
        return {k: int(c.get(k, 0)) for k in kinds}

    models = sorted({c["lock_id"] for c in cells})
    by_model: dict[str, dict[str, Any]] = {}
    for model in models:
        mine = [c for c in cells if c["lock_id"] == model]
        lock_counts = Counter(c["lock_kind"] for c in mine)
        n = len(mine)
        atomic_pass = sum(c["atomic_correct"] for c in mine)
        e2e_pass = lock_counts.get("task_pass_clean", 0)
        by_model[model] = {
            "n": n,
            "atomic_pass": atomic_pass,
            "atomic_fail": n - atomic_pass,
            "e2e_pass": e2e_pass,
            "e2e_fail": n - e2e_pass,
            "lock_kind": {k: int(lock_counts.get(k, 0)) for k in LOCK_KINDS},
        }
    return {
        "kind": "locked_hard_failure",
        "published": False,
        "source": str(HARD_LOCK),
        "note": (
            "lock_kind is the published composition: atomic × termination from "
            "jobs/locked-hard-release-k3.json. Sidecar kinds need job dirs and "
            "are diagnostic. Missing Hard-15 examinees stay missing, not 0."
        ),
        "n_rows": len(cells),
        "lock_kind_counts": _counts("lock_kind", LOCK_KINDS),
        "sidecar_kind_counts": _counts("sidecar_kind", FAIL_KINDS),
        "by_model": by_model,
        "cells": cells,
    }


def main() -> int:
    path = HARD_LOCK
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    if args:
        path = Path(args[0])
    if not path.is_file():
        print(f"missing {path}", file=sys.stderr)
        return 2
    data = json.loads(path.read_text(encoding="utf-8"))
    report = compose(list(data.get("rows") or []))
    report["source"] = str(path)
    OUT.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(
        json.dumps(
            {
                "n_rows": report["n_rows"],
                "lock_kind_counts": report["lock_kind_counts"],
                "by_model": {
                    m: {
                        "atomic_pass": v["atomic_pass"],
                        "e2e_pass": v["e2e_pass"],
                        "lock_kind": v["lock_kind"],
                    }
                    for m, v in report["by_model"].items()
                },
            },
            indent=2,
        )
    )
    print(f"wrote {OUT}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
