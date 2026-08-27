"""Machine check for benchmark-v1.0.1 freeze. Does not call Harbor."""

from __future__ import annotations

import json
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from build_canonical_matrix import (  # noqa: E402
    BANK_62,
    remaining_dirty,
    merge_rows,
    model_score,
    e2e_hit,
)
from export_v101_trials import LABELS_OUT, TRIALS_OUT  # noqa: E402
from models_lock import load_lock, models  # noqa: E402
from run_locked import attempt_is_valid, attempt_of  # noqa: E402

SUMMARY = ROOT / "results" / "canonical-coverage.json"
N_MODELS = 12
N_TASKS = 62
N_TRIALS = N_MODELS * N_TASKS * 3


def fail(msg: str, errors: list[str]) -> None:
    errors.append(msg)


def main() -> int:
    errors: list[str] = []
    rows, _applied = merge_rows()
    dirty = remaining_dirty(rows)
    lock = load_lock()
    lock_ids = [m["id"] for m in models(lock)]
    summary = json.loads(SUMMARY.read_text(encoding="utf-8"))
    labels = json.loads(LABELS_OUT.read_text(encoding="utf-8"))
    trials = [
        json.loads(line)
        for line in TRIALS_OUT.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]

    if len(rows) != N_TRIALS:
        fail(f"trial_count rows {len(rows)} != {N_TRIALS}", errors)
    if len(trials) != N_TRIALS:
        fail(f"trial_count jsonl {len(trials)} != {N_TRIALS}", errors)
    if summary.get("n_rows") != N_TRIALS or summary.get("n_scored") != N_TRIALS:
        fail(
            f"coverage n_rows/n_scored {summary.get('n_rows')}/{summary.get('n_scored')}",
            errors,
        )

    keys_rows = [(r["lock_id"], r["task"], attempt_of(r)) for r in rows]
    keys_jsonl = [(r["lock_id"], r["task"], int(r["attempt"])) for r in trials]
    if len(set(keys_rows)) != N_TRIALS:
        fail(f"unique(model,task,attempt) rows {len(set(keys_rows))}", errors)
    if len(set(keys_jsonl)) != N_TRIALS:
        fail(f"unique(model,task,attempt) jsonl {len(set(keys_jsonl))}", errors)
    if set(keys_rows) != set(keys_jsonl):
        fail("row keys != jsonl keys", errors)

    if dirty:
        fail(f"remaining_dirty {len(dirty)}", errors)
    if summary.get("remaining_dirty"):
        fail("coverage remaining_dirty not empty", errors)
    if summary.get("n_incomplete_tasks") != 0:
        fail(f"incomplete {summary.get('n_incomplete_tasks')}", errors)

    by_mt: dict[tuple[str, str], list] = defaultdict(list)
    for r in rows:
        if attempt_is_valid(r):
            by_mt[(r["lock_id"], r["task"])].append(attempt_of(r))
    if len(lock_ids) != N_MODELS:
        fail(f"n_models {len(lock_ids)}", errors)
    if len(BANK_62) != N_TASKS:
        fail(f"n_tasks {len(BANK_62)}", errors)
    for lock_id in lock_ids:
        for task in BANK_62:
            attempts = sorted(by_mt.get((lock_id, task), []))
            if attempts != [1, 2, 3]:
                fail(f"not 3 valid {lock_id} {task} {attempts}", errors)

    for r in rows:
        atomic = int(r.get("atomic_correct") or 0)
        clean = int(r.get("atomic_correct") == 1 and r.get("termination") == "clean")
        if clean > atomic:
            fail(f"Clean>Artifact {r.get('lock_id')} {r.get('task')} a{attempt_of(r)}", errors)

    counts = labels.get("counts") or {}
    n_lab = sum(int(counts.get(k, 0)) for k in ("easy", "medium", "hard", "uncalibrated"))
    if n_lab != N_TASKS:
        fail(f"difficulty labels {n_lab}", errors)
    if len(labels.get("tasks") or {}) != N_TASKS:
        fail(f"difficulty tasks {len(labels.get('tasks') or {})}", errors)

    by_model_atomic: Counter[str] = Counter()
    by_model_e2e: Counter[str] = Counter()
    for r in rows:
        lid = str(r["lock_id"])
        by_model_atomic[lid] += int(r.get("atomic_correct") or 0)
        by_model_e2e[lid] += e2e_hit(r)
    for rec in summary.get("models") or []:
        lid = rec["lock_id"]
        if rec["atomic_ok"] != by_model_atomic[lid]:
            fail(
                f"table atomic {lid} {rec['atomic_ok']} != trials {by_model_atomic[lid]}",
                errors,
            )
        if rec["e2e_ok"] != by_model_e2e[lid]:
            fail(f"table e2e {lid} {rec['e2e_ok']} != trials {by_model_e2e[lid]}", errors)
        if rec["e2e_ok"] > rec["atomic_ok"]:
            fail(f"Clean>Artifact model {lid}", errors)
        scored = model_score(rows, lid)
        if scored["atomic_ok"] != rec["atomic_ok"] or scored["e2e_ok"] != rec["e2e_ok"]:
            fail(f"model_score mismatch {lid}", errors)

    prose = (ROOT / "项目说明.md").read_text(encoding="utf-8")
    expected_micro = {
        "qwen3.5-9b": (148, 142),
        "ministral-8b-2512": (87, 78),
        "qwen3.8-27b": (162, 159),
        "gemma-3-4b-it": (11, 11),
    }
    for lid, (a, e) in expected_micro.items():
        if by_model_atomic[lid] != a or by_model_e2e[lid] != e:
            fail(f"headline {lid} {by_model_atomic[lid]}/{by_model_e2e[lid]} != {a}/{e}", errors)
    if "148/186" not in prose or "162/186" not in prose:
        fail("项目说明 missing headline micros 148/186 or 162/186", errors)
    if re.search(r"remaining_dirty[` ]*0", prose) is None and "remaining_dirty` 0" not in prose:
        fail("项目说明 missing remaining_dirty 0", errors)

    halt = sum(
        1
        for r in rows
        if r.get("atomic_correct") == 1 and r.get("termination") != "clean"
    )
    if halt != 105 or summary.get("halt_unfinished_atomic") != 105:
        fail(f"halt {halt} coverage {summary.get('halt_unfinished_atomic')}", errors)

    print("===== V1.0.1 FREEZE CHECK =====")
    print(f"trial_count {len(rows)}")
    print(f"unique_keys {len(set(keys_rows))}")
    print(f"remaining_dirty {len(dirty)}")
    print(f"incomplete {summary.get('n_incomplete_tasks')}")
    print(f"n_models {len(lock_ids)} n_tasks {len(BANK_62)}")
    print(f"difficulty {counts}")
    print(f"halt {halt}")
    if errors:
        print("FAIL")
        for msg in errors:
            print(f"  {msg}")
        return 1
    print("PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
