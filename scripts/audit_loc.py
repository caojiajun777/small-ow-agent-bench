"""Audit MAIN_47 Loc cells from frozen jobs. Does not rerun models.

python scripts/audit_loc.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from relabel_locked import loc_gold, sidecar_of  # noqa: E402
from task_sets import MAIN_47  # noqa: E402

MAT = ROOT / "jobs" / "locked-matrices.json"
OUT = ROOT / "jobs" / "loc-audit.json"
LOC_TASKS = [t for t in MAIN_47 if t.startswith("loc-")]


def _touched(sidecar: dict, gold: set[str]) -> list[str]:
    hits: list[str] = []
    blob = json.dumps(sidecar.get("turns") or [], ensure_ascii=False)
    for name in sorted(gold):
        stem = name.rsplit("/", 1)[-1]
        if name in blob or stem in blob:
            hits.append(name)
    return hits


def _wrote_answer(sidecar: dict) -> bool:
    for turn in sidecar.get("turns") or []:
        cmd = turn.get("command") or ""
        if "answer.txt" in cmd:
            return True
    return False


def main() -> int:
    data = json.loads(MAT.read_text(encoding="utf-8"))
    jobs = {
        (c.get("lock_id"), c.get("task")): c.get("job") for c in data.get("cells") or []
    }
    by_task: dict[str, list[dict]] = {t: [] for t in LOC_TASKS}
    for cell in data.get("loc_diagnostics") or []:
        task = cell["task"]
        if task not in by_task:
            continue
        sidecar = sidecar_of(jobs.get((cell["lock_id"], task)))
        gold = loc_gold(task)
        row = {
            **cell,
            "wrote_answer": _wrote_answer(sidecar),
            "n_shell": sidecar.get("n_shell"),
            "finished": sidecar.get("finished"),
            "n_parse_fail": sidecar.get("n_parse_fail"),
            "touched_gold": _touched(sidecar, gold),
        }
        by_task[task].append(row)

    summary = []
    for task in LOC_TASKS:
        rows = by_task[task]
        gold = sorted(loc_gold(task))
        n_submit = sum(1 for r in rows if r["wrote_answer"])
        n_recall1 = sum(1 for r in rows if r.get("recall") == 1.0)
        n_exact = sum(1 for r in rows if r.get("A") == 1)
        n_touch = sum(1 for r in rows if r.get("touched_gold"))
        verdict = "keep_exact_set"
        if n_exact == 0 and n_recall1:
            verdict = "exact_set_overpredict_only"
        elif n_exact == 0 and n_submit == 0:
            verdict = "no_submit_or_search_fail"
        elif n_exact == 0 and n_touch and not n_recall1:
            verdict = "saw_gold_wrong_set"
        summary.append(
            {
                "task": task,
                "gold": gold,
                "n_models": len(rows),
                "n_atomic_pass": n_exact,
                "n_wrote_answer": n_submit,
                "n_recall_1": n_recall1,
                "n_touched_gold": n_touch,
                "verdict": verdict,
                "by_model": rows,
            }
        )

    report = {
        "kind": "loc_audit_k1",
        "published": False,
        "instruction_construct": "minimal file set that must change; extra decoy is 0",
        "items": summary,
    }
    OUT.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print("===== LOC AUDIT =====")
    for item in summary:
        print(
            f"{item['task']:28} gold={item['gold']}  "
            f"pass={item['n_atomic_pass']} submit={item['n_wrote_answer']} "
            f"R1={item['n_recall_1']} touch={item['n_touched_gold']}  "
            f"{item['verdict']}"
        )
    print(f"wrote {OUT}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
