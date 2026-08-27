"""Rerun remaining infra-dirty coverage slots onto a side table.

Does not overwrite locked-core.json, locked-core-k3.json, or
locked-hard-release-k3.json.

    python scripts/rerun_infra.py
    python scripts/rerun_infra.py --run
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
from build_canonical_matrix import (  # noqa: E402
    DIRTY_EXCEPTIONS,
    FROZEN_LOCKS,
    INFRA_RERUN,
    remaining_dirty,
)
from models_lock import load_lock, row_by_runtime_id  # noqa: E402
from rerun_gemma4b import trial_exception_type  # noqa: E402
from run_locked import (  # noqa: E402
    CORE_OUT,
    ENV,
    HARD_RELEASE_OUT,
    K3_OUT,
    TASKS,
    _prevent_sleep,
    _run_k3_slot,
    _upsert_k3,
    attempt_is_valid,
    attempt_of,
)


OUT = INFRA_RERUN


def planned_keys() -> list[dict[str, Any]]:
    from build_canonical_matrix import merge_rows

    rows, _applied = merge_rows()
    dirty = remaining_dirty(rows)
    by = {(r["lock_id"], r["task"], attempt_of(r)): r for r in rows}
    planned: list[dict[str, Any]] = []
    for item in dirty:
        key = (item["lock_id"], item["task"], int(item["attempt"]))
        src = by.get(key)
        if src is None:
            continue
        rec = dict(src)
        rec["rerun_reason"] = item.get("exception")
        planned.append(rec)
    planned.sort(key=lambda r: (str(r["lock_id"]), str(r["task"]), attempt_of(r)))
    return planned


def _load_out() -> list[dict[str, Any]]:
    if not OUT.is_file():
        return []
    data = json.loads(OUT.read_text(encoding="utf-8"))
    return [dict(r) for r in (data.get("rows") or [])]


def _write(rows: list[dict[str, Any]], *, n_planned: int, n_replaced: int) -> None:
    payload = {
        "kind": "locked_infra_rerun_k3",
        "published": False,
        "enters_official_mean": False,
        "overwrites_locked_core": False,
        "overwrites_locked_core_k3": False,
        "overwrites_locked_hard_release_k3": False,
        "n_dirty_planned": n_planned,
        "n_replaced": n_replaced,
        "dirty_exceptions": sorted(DIRTY_EXCEPTIONS),
        "rows": rows,
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def _already_replaced(out_rows: list[dict[str, Any]], src: dict[str, Any]) -> bool:
    found = next(
        (
            r
            for r in out_rows
            if r.get("lock_id") == src.get("lock_id")
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
    for frozen in FROZEN_LOCKS:
        if OUT.resolve() == frozen.resolve():
            print(f"refusing: would write frozen lock {frozen}", file=sys.stderr)
            return 2
    planned = planned_keys()
    by_exc: dict[str, int] = defaultdict(int)
    for row in planned:
        by_exc[str(row.get("rerun_reason") or trial_exception_type(row.get("job")))] += 1
    print("===== INFRA RERUN =====")
    print(f"output {OUT}")
    print("overwrites_locked_core_k3 false")
    print("overwrites_locked_hard_release_k3 false")
    print(f"n_dirty {len(planned)}")
    print("dirty", dict(by_exc))
    for row in planned:
        print(
            f"  {row['lock_id']} {row['task']} a{attempt_of(row)} "
            f"{row.get('rerun_reason')}",
            flush=True,
        )
    if not run:
        print("dry-run; pass --run to execute on Novita n=1")
        return 0
    if not ENV.is_file():
        print("missing .env", file=sys.stderr)
        return 2
    missing = [
        n for n in {r["task"] for r in planned} if not (TASKS / n / "task.toml").is_file()
    ]
    if missing:
        print(f"missing tasks: {missing}", file=sys.stderr)
        return 2
    lock = load_lock()
    out_rows = _load_out()
    n_replaced = sum(1 for r in planned if _already_replaced(out_rows, r))
    _write(out_rows, n_planned=len(planned), n_replaced=n_replaced)
    restore = _prevent_sleep()
    code = 0
    started = False
    try:
        for i, src in enumerate(planned, start=1):
            if _already_replaced(out_rows, src):
                print(
                    f"skip done {src['lock_id']} {src['task']} a{attempt_of(src)} "
                    f"({i}/{len(planned)})",
                    flush=True,
                )
                continue
            model = row_by_runtime_id(src["lock_id"], lock)
            if not model:
                print(f"missing {src['lock_id']} in lock", file=sys.stderr)
                code = 2
                continue
            print(
                f"===== rerun {src['lock_id']} {src['task']} a{attempt_of(src)} "
                f"({i}/{len(planned)}) was {src.get('rerun_reason')} =====",
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
            rec["rerun_reason"] = src.get("rerun_reason")
            _upsert_k3(out_rows, rec)
            n_replaced = sum(1 for r in planned if _already_replaced(out_rows, r))
            if rec.get("reason") in {"infra", "no_job"} or rec.get("termination") == "infra":
                code = max(code, 1)
            _write(out_rows, n_planned=len(planned), n_replaced=n_replaced)
            print(
                f"  atomic={rec.get('atomic_correct')} "
                f"termination={rec.get('termination')} "
                f"replaced={n_replaced}/{len(planned)}",
                flush=True,
            )
    finally:
        restore()
    print(f"done replaced={n_replaced}/{len(planned)} wrote {OUT}", flush=True)
    print(f"did not touch {K3_OUT.name} / {CORE_OUT.name} / {HARD_RELEASE_OUT.name}")
    return code


if __name__ == "__main__":
    raise SystemExit(main())
