"""Sensitivity rerun: Gemma-3-4B cells that were API 429.

Does not overwrite jobs/locked-core.json or jobs/locked-core-k3.json.
Official v1.0 Compact Main stays the frozen API table.

Harbor LiteLLM raises RateLimitError; the v1.0 runner only retried
RateLimitException, so DeepInfra 429s were locked as protocol_error.
This script reruns those 429 slots onto a side table.

    python scripts/rerun_gemma4b.py
    python scripts/rerun_gemma4b.py --run
"""

from __future__ import annotations

import json
import sys
import time
from collections import defaultdict
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from models_lock import load_lock, row_by_runtime_id  # noqa: E402
from run_locked import (  # noqa: E402
    CORE_OUT,
    ENV,
    K3_OUT,
    TASKS,
    _prevent_sleep,
    _run_k3_slot,
    _upsert_k3,
    attempt_is_valid,
    attempt_of,
)
from score_standard import ATOMS, atom_of  # noqa: E402
from task_sets import MAIN_47  # noqa: E402

MODEL_ID = "gemma-3-4b-it"
OUT = ROOT / "jobs" / "locked-gemma4b-rerun-k3.json"
DIRTY_EXCEPTIONS = frozenset(
    {
        "RateLimitError",
        "RateLimitException",
    }
)


def trial_exception_type(job: str | None) -> str | None:
    if not job:
        return None
    root = Path(job)
    if not root.is_dir():
        return None
    for path in root.glob("*/result.json"):
        if path.parent.name.startswith("."):
            continue
        try:
            data = json.loads(path.read_text(encoding="utf-8", errors="replace"))
        except (OSError, json.JSONDecodeError):
            continue
        info = data.get("exception_info") or {}
        exc = info.get("exception_type")
        if exc:
            return str(exc)
    return None


def is_dirty(row: dict[str, Any]) -> bool:
    return trial_exception_type(row.get("job") if isinstance(row.get("job"), str) else None) in DIRTY_EXCEPTIONS


def gemma_rows(source: Path = K3_OUT) -> list[dict[str, Any]]:
    data = json.loads(source.read_text(encoding="utf-8"))
    return [
        dict(r)
        for r in (data.get("rows") or [])
        if r.get("lock_id") == MODEL_ID and r.get("task") in MAIN_47 and attempt_of(r) in (1, 2, 3)
    ]


def dirty_plan(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [r for r in rows if is_dirty(r)]


def skill_means(rows: list[dict[str, Any]]) -> dict[str, float | None]:
    by_task: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        if attempt_is_valid(row):
            by_task[row["task"]].append(row)
    p: dict[str, float] = {}
    for task, trials in by_task.items():
        if len(trials) != 3:
            continue
        p[task] = sum(int(t["atomic_correct"]) for t in trials) / 3
    out: dict[str, float | None] = {}
    for prefix, label in ATOMS.items():
        vals = [p[name] for name in MAIN_47 if name.startswith(f"{prefix}-") and name in p]
        out[label] = sum(vals) / len(vals) if vals else None
    return out


def micro(rows: list[dict[str, Any]]) -> tuple[int, int]:
    scored = [r for r in rows if attempt_is_valid(r)]
    return sum(int(r["atomic_correct"]) for r in scored), len(scored)


def _write(rows: list[dict[str, Any]], *, n_dirty: int, n_replaced: int) -> None:
    ok, n = micro(rows)
    payload = {
        "kind": "locked_gemma4b_rerun_k3",
        "published": False,
        "enters_official_mean": False,
        "overwrites_locked_core": False,
        "overwrites_locked_core_k3": False,
        "source": str(K3_OUT),
        "model": MODEL_ID,
        "dirty_exceptions": sorted(DIRTY_EXCEPTIONS),
        "n_dirty_planned": n_dirty,
        "n_replaced": n_replaced,
        "atomic_successes": ok,
        "n_scored": n,
        "skill_means_atomic": skill_means(rows),
        "rows": rows,
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def _already_replaced(out_rows: list[dict[str, Any]], src: dict[str, Any]) -> bool:
    found = next(
        (
            r
            for r in out_rows
            if r.get("lock_id") == MODEL_ID
            and r.get("task") == src.get("task")
            and attempt_of(r) == attempt_of(src)
            and r.get("job")
            and r.get("job") != src.get("job")
        ),
        None,
    )
    return bool(found and attempt_is_valid(found))


def main() -> int:
    run = "--run" in sys.argv
    if K3_OUT.resolve() == CORE_OUT.resolve():
        print("refusing: k3 and k1 paths collided", file=sys.stderr)
        return 2
    lock = load_lock()
    model = row_by_runtime_id(MODEL_ID, lock)
    if not model:
        print(f"missing {MODEL_ID} in models.lock.yaml", file=sys.stderr)
        return 2
    baseline = gemma_rows()
    planned = dirty_plan(baseline)
    before_ok, before_n = micro(baseline)
    print("===== GEMMA-3-4B 429 SENSITIVITY =====")
    print(f"source {K3_OUT}")
    print(f"output {OUT}")
    print("overwrites_locked_core_k3 false")
    print(f"n_baseline {len(baseline)}  n_dirty {len(planned)}")
    print(f"frozen_atomic {before_ok}/{before_n}")
    by_exc: dict[str, int] = defaultdict(int)
    for row in planned:
        by_exc[str(trial_exception_type(row.get("job")))] += 1
    print("dirty", dict(by_exc))
    if not run:
        print("dry-run; pass --run to execute on Novita n=1")
        print("does not overwrite jobs/locked-core-k3.json")
        return 0
    if not ENV.is_file():
        print("missing .env", file=sys.stderr)
        return 2
    missing = [n for n in {r["task"] for r in planned} if not (TASKS / n / "task.toml").is_file()]
    if missing:
        print(f"missing tasks: {missing}", file=sys.stderr)
        return 2

    out_rows = list(baseline)
    if OUT.is_file():
        prev = json.loads(OUT.read_text(encoding="utf-8"))
        for row in prev.get("rows") or []:
            if (
                row.get("lock_id") == MODEL_ID
                and row.get("job")
                and attempt_is_valid(row)
            ):
                src = next(
                    (
                        s
                        for s in baseline
                        if s.get("task") == row.get("task")
                        and attempt_of(s) == attempt_of(row)
                    ),
                    None,
                )
                if src and row.get("job") != src.get("job"):
                    _upsert_k3(out_rows, row)

    n_replaced = sum(1 for r in planned if _already_replaced(out_rows, r))
    _write(out_rows, n_dirty=len(planned), n_replaced=n_replaced)
    restore = _prevent_sleep()
    code = 0
    started = False
    try:
        for i, src in enumerate(planned, start=1):
            if _already_replaced(out_rows, src):
                print(
                    f"skip done {src['task']} a{attempt_of(src)} ({i}/{len(planned)})",
                    flush=True,
                )
                continue
            print(
                f"===== rerun {MODEL_ID} {src['task']} a{attempt_of(src)} "
                f"({i}/{len(planned)}) was {trial_exception_type(src.get('job'))} =====",
                flush=True,
            )
            if not started:
                print("wait 8s before first sandbox create", flush=True)
                time.sleep(8)
                started = True
            else:
                time.sleep(8)
            rec = _run_k3_slot(model, src["task"], attempt_of(src), lock, None)
            rec["rerun_of"] = src.get("job")
            rec["rerun_reason"] = trial_exception_type(src.get("job"))
            _upsert_k3(out_rows, rec)
            n_replaced = sum(1 for r in planned if _already_replaced(out_rows, r))
            if rec.get("reason") in {"infra", "no_job"} or rec.get("termination") == "infra":
                code = 1
            _write(out_rows, n_dirty=len(planned), n_replaced=n_replaced)
            print(
                f"  atomic={rec.get('atomic_correct')} "
                f"termination={rec.get('termination')} "
                f"replaced={n_replaced}/{len(planned)}",
                flush=True,
            )
    finally:
        restore()
    after_ok, after_n = micro(out_rows)
    print(
        f"done frozen_atomic={before_ok}/{before_n} "
        f"rerun_atomic={after_ok}/{after_n} wrote {OUT}",
        flush=True,
    )
    print("official Compact Main is still jobs/locked-core-k3.json")
    return code


if __name__ == "__main__":
    sys.exit(main())
