"""Run the frozen 12-model Core roster.

--group main = original 10 compact_dense (Base-47 k=3 reuse).
--group moe  = Qwen3.6-35B-A3B only.
--group core / all = all 12.
Do not overwrite jobs/locked-core.json or jobs/locked-core-k3.json.

    python scripts/run_locked.py --run --protocol --group moe
    python scripts/run_locked.py --run --full --group main
    python scripts/run_locked.py --k3-fill --group main
    python scripts/run_locked.py --run --hard-dev
    python scripts/run_locked.py --hard-release
    python scripts/run_locked.py --run --hard-release
    python scripts/run_locked.py --hard-floor
    python scripts/run_locked.py --run --hard-floor
    python scripts/run_locked.py --base-fill
    python scripts/run_locked.py --run --base-fill
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from collections import defaultdict
from pathlib import Path
from typing import Any

os.environ["PYTHONIOENCODING"] = "utf-8"

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from classify_timeouts import KIND_STALL, classify_trial, load_trials  # noqa: E402
from models_lock import (  # noqa: E402
    COMPACT_GROUP,
    MOE_GROUP,
    UPPER_GROUP,
    hard_floor_rows,
    hard_release_rows,
    llm_kwargs,
    load_lock,
    models,
    openrouter_id,
    select_subjects,
)
from score_standard import (  # noqa: E402
    ATOMS,
    atom_of,
    format_report,
    is_rate_limit,
    score_job,
)
from task_sets import (  # noqa: E402
    HARD_DEV_10,
    HARD_RELEASE_15,
    LOC_RULER_K3,
    MAIN_47,
    PROTOCOL_SMOKE,
)

TASKS = ROOT / "tasks"
ENV = ROOT / ".env"
JOBS = ROOT / "jobs"
AGENT = "agents.compact_shell:CompactShellAgent"
PROTOCOL_OUT = JOBS / "protocol-check.json"
CORE_OUT = JOBS / "locked-core.json"
K3_OUT = JOBS / "locked-core-k3.json"
HARD_DEV_OUT = JOBS / "locked-hard-dev-k3.json"
HARD_RELEASE_OUT = JOBS / "locked-hard-release-k3.json"
HARD_FLOOR_OUT = JOBS / "locked-hard-floor-k3.json"
UPPER_BASE_OUT = JOBS / "locked-upper-base-k3.json"
BENCHMARK_VERSION = "benchmark-v1.0-rc1"
K3_ATTEMPTS = (2, 3)
HARD_DEV_ATTEMPTS = (1, 2, 3)
HARD_RELEASE_ATTEMPTS = (1, 2, 3)
UPPER_BASE_ATTEMPTS = (1, 2, 3)
K3_K = 3
# BuildException / no_job / non-429 API flake: give up the visit after this many
# Harbor calls and record termination=infra (resume can retry later).
INFRA_RETRY_CAP = 3
# 429 must not fill the k=3 slot or be recorded as a model 0. None = unbounded.
RATE_LIMIT_RETRY_CAP: int | None = None
INFRA_BACKOFF_SEC = 60

RETRY_INCLUDE = (
    "BuildException",
    "EnvironmentStartTimeoutError",
    "RateLimitException",
    "RateLimitError",
    "ConnectError",
    "APIConnectionError",
    "ServiceUnavailableError",
    "AuthenticationError",
)
SCORED_TERMINATIONS = frozenset({"clean", "tle", "protocol_error"})


def trial_is_done(row: dict[str, Any] | None, *, force: bool = False) -> bool:
    if force or not row:
        return False
    if row.get("reason") == "missing_on_openrouter":
        return True
    if row.get("reason") == "no_job":
        return False
    term = row.get("termination")
    if term == "infra":
        return False
    if (
        term == "tle"
        and row.get("timeout_kind") == KIND_STALL
        and not row.get("stall_retried")
    ):
        return False
    if row.get("atomic_correct") is None:
        return False
    return term in SCORED_TERMINATIONS


def attempt_is_valid(row: dict[str, Any] | None) -> bool:
    """Scored non-infra attempt. Stall after retry counts; infra never does."""
    if not row:
        return False
    if row.get("termination") == "infra":
        return False
    if row.get("atomic_correct") is None:
        return False
    return row.get("termination") in SCORED_TERMINATIONS


def attempt_of(row: dict[str, Any] | None) -> int:
    if not row:
        return 1
    return int(row.get("attempt") or 1)


def tasks_for_k3_subject(model: dict[str, Any]) -> tuple[str, ...]:
    if model.get("group") in {UPPER_GROUP, "ruler"}:
        return LOC_RULER_K3
    return MAIN_47


def plan_hard_cells(
    subjects: list[dict[str, Any]],
    tasks: tuple[str, ...],
    attempts: tuple[int, ...],
) -> list[tuple[dict[str, Any], str, int]]:
    cells: list[tuple[dict[str, Any], str, int]] = []
    for model in subjects:
        for name in tasks:
            for attempt in attempts:
                cells.append((model, name, attempt))
    return cells


def plan_hard_dev_cells(
    subjects: list[dict[str, Any]],
) -> list[tuple[dict[str, Any], str, int]]:
    return plan_hard_cells(subjects, HARD_DEV_10, HARD_DEV_ATTEMPTS)


def plan_hard_release_cells(
    subjects: list[dict[str, Any]],
) -> list[tuple[dict[str, Any], str, int]]:
    return plan_hard_cells(subjects, HARD_RELEASE_15, HARD_RELEASE_ATTEMPTS)


def _write_hard_k3(
    rows: list[dict],
    lock: dict[str, Any],
    subjects: list[dict[str, Any]],
    *,
    tasks: tuple[str, ...],
    out_path: Path,
    kind: str,
    enters_official_mean: bool,
    banner: str,
) -> Path:
    by_id = {m["id"]: m for m in lock.get("models") or []}
    wanted = {m["id"] for m in subjects} | {
        r["lock_id"] for r in rows if r.get("lock_id")
    }
    cells = []
    n_incomplete = 0
    for lock_id in [m["id"] for m in lock["models"] if m["id"] in wanted]:
        for task in tasks:
            attempts = [
                r for r in rows if r.get("lock_id") == lock_id and r.get("task") == task
            ]
            by_attempt = {
                attempt_of(r): r
                for r in attempts
                if attempt_is_valid(r) and attempt_of(r) in (1, 2, 3)
            }
            n_valid = len(by_attempt)
            incomplete = n_valid < K3_K
            if incomplete:
                n_incomplete += 1
            p_atomic = None
            p_e2e = None
            if n_valid == K3_K:
                p_atomic = (
                    sum(int(by_attempt[a]["atomic_correct"]) for a in (1, 2, 3)) / K3_K
                )
                p_e2e = (
                    sum(
                        1
                        if by_attempt[a].get("atomic_correct") == 1
                        and by_attempt[a].get("termination") == "clean"
                        else 0
                        for a in (1, 2, 3)
                    )
                    / K3_K
                )
            cells.append(
                {
                    "lock_id": lock_id,
                    "task": task,
                    "group": (by_id.get(lock_id) or {}).get("group"),
                    "n_valid": n_valid,
                    "incomplete": incomplete,
                    "p_atomic": p_atomic,
                    "p_e2e": p_e2e,
                }
            )
    report = {
        "kind": kind,
        "published": False,
        "enters_official_mean": enters_official_mean,
        "benchmark_version": BENCHMARK_VERSION,
        "k": K3_K,
        "overwrites_locked_core": False,
        "overwrites_locked_core_k3": False,
        "n_scope_cells": len(cells),
        "n_incomplete_cells": n_incomplete,
        "models": [i for i in _report_ids(lock, subjects, rows)],
        "tasks": list(tasks),
        "cells": cells,
        "rows": rows,
    }
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(
        f"===== {banner} k=3 =====\n"
        f"scope {report['n_scope_cells']}  incomplete {n_incomplete}\n"
        f"wrote {out_path} (did not touch {CORE_OUT} or {K3_OUT})",
        flush=True,
    )
    return out_path


def _write_hard_dev_k3(
    rows: list[dict], lock: dict[str, Any], subjects: list[dict[str, Any]]
) -> Path:
    return _write_hard_k3(
        rows,
        lock,
        subjects,
        tasks=HARD_DEV_10,
        out_path=HARD_DEV_OUT,
        kind="locked_hard_dev_k3",
        enters_official_mean=False,
        banner="HARD-DEV",
    )


def _write_hard_release_k3(
    rows: list[dict], lock: dict[str, Any], subjects: list[dict[str, Any]]
) -> Path:
    return _write_hard_k3(
        rows,
        lock,
        subjects,
        tasks=HARD_RELEASE_15,
        out_path=HARD_RELEASE_OUT,
        kind="locked_hard_release_k3",
        enters_official_mean=True,
        banner="HARD-RELEASE",
    )


def _write_hard_floor_k3(
    rows: list[dict], lock: dict[str, Any], subjects: list[dict[str, Any]]
) -> Path:
    if HARD_FLOOR_OUT.resolve() == HARD_RELEASE_OUT.resolve():
        raise SystemExit("hard-floor must not write locked-hard-release-k3.json")
    return _write_hard_k3(
        rows,
        lock,
        subjects,
        tasks=HARD_RELEASE_15,
        out_path=HARD_FLOOR_OUT,
        kind="locked_hard_floor_k3",
        enters_official_mean=False,
        banner="HARD-FLOOR",
    )


def _execute_hard_set(
    rows_out: list[dict],
    subjects: list[dict[str, Any]],
    lock: dict[str, Any],
    *,
    force: bool,
    cells: list[tuple[dict[str, Any], str, int]],
    write,
    label: str,
) -> int:
    code = 0
    started = False
    for model, name, attempt in cells:
        prev = _find_k3_row(rows_out, model["id"], name, attempt)
        if trial_is_done(prev, force=force):
            print(f"skip done {model['id']} {name} a{attempt}", flush=True)
            continue
        print(
            f"===== {label} {model['id']} {name} attempt={attempt} =====",
            flush=True,
        )
        if not openrouter_id(model):
            _upsert_k3(
                rows_out,
                _trial_row(
                    model,
                    name,
                    None,
                    "missing_on_openrouter",
                    attempt=attempt,
                    lock=lock,
                ),
            )
            write(rows_out, lock, subjects)
            continue
        if not started:
            print("wait 8s before first sandbox create", flush=True)
            time.sleep(8)
            started = True
        else:
            time.sleep(8)
        rec = _run_k3_slot(model, name, attempt, lock, prev)
        if rec.get("termination") == "infra" or rec.get("reason") in {
            "infra",
            "no_job",
        }:
            code = max(code, 1)
        _upsert_k3(rows_out, rec)
        write(rows_out, lock, subjects)
    return code


def _execute_hard_dev(
    rows_out: list[dict],
    subjects: list[dict[str, Any]],
    lock: dict[str, Any],
    *,
    force: bool,
) -> int:
    return _execute_hard_set(
        rows_out,
        subjects,
        lock,
        force=force,
        cells=plan_hard_dev_cells(subjects),
        write=_write_hard_dev_k3,
        label="hard-dev",
    )


def _execute_hard_release(
    rows_out: list[dict],
    subjects: list[dict[str, Any]],
    lock: dict[str, Any],
    *,
    force: bool,
) -> int:
    return _execute_hard_set(
        rows_out,
        subjects,
        lock,
        force=force,
        cells=plan_hard_release_cells(subjects),
        write=_write_hard_release_k3,
        label="hard-release",
    )


def _execute_hard_floor(
    rows_out: list[dict],
    subjects: list[dict[str, Any]],
    lock: dict[str, Any],
    *,
    force: bool,
) -> int:
    return _execute_hard_set(
        rows_out,
        subjects,
        lock,
        force=force,
        cells=plan_hard_release_cells(subjects),
        write=_write_hard_floor_k3,
        label="hard-floor",
    )


def plan_upper_base_cells(
    subjects: list[dict[str, Any]],
) -> list[tuple[dict[str, Any], str, int]]:
    return plan_hard_cells(subjects, MAIN_47, UPPER_BASE_ATTEMPTS)


def _write_upper_base_k3(
    rows: list[dict], lock: dict[str, Any], subjects: list[dict[str, Any]]
) -> Path:
    return _write_hard_k3(
        rows,
        lock,
        subjects,
        tasks=MAIN_47,
        out_path=UPPER_BASE_OUT,
        kind="locked_upper_base_k3",
        enters_official_mean=False,
        banner="UPPER-BASE",
    )


def _seed_upper_base(
    rows: list[dict],
    lock: dict[str, Any],
    subjects: list[dict[str, Any]],
) -> int:
    """Copy scored 27B Base-47 cells from frozen core locks. Do not rewrite them."""
    wanted = {m["id"] for m in subjects}
    by_id = {m["id"]: m for m in lock.get("models") or []}
    added = 0
    for src_path in (K3_OUT, CORE_OUT):
        for src in _load_rows(src_path):
            lock_id = src.get("lock_id")
            task = src.get("task")
            if lock_id not in wanted or task not in MAIN_47:
                continue
            attempt = attempt_of(src)
            if attempt not in (1, 2, 3):
                continue
            seeded = dict(src)
            seeded["attempt"] = attempt
            if not attempt_is_valid(seeded):
                continue
            if _find_k3_row(rows, lock_id, task, attempt) is not None:
                continue
            model = by_id.get(lock_id) or {}
            for key, value in _k3_meta(model, lock).items():
                seeded.setdefault(key, value)
            rows.append(seeded)
            added += 1
    return added


def _execute_upper_base(
    rows_out: list[dict],
    subjects: list[dict[str, Any]],
    lock: dict[str, Any],
    *,
    force: bool,
) -> int:
    return _execute_hard_set(
        rows_out,
        subjects,
        lock,
        force=force,
        cells=plan_upper_base_cells(subjects),
        write=_write_upper_base_k3,
        label="upper-base",
    )


def plan_k3_cells(
    subjects: list[dict[str, Any]],
    attempts: tuple[int, ...] = K3_ATTEMPTS,
) -> list[tuple[dict[str, Any], str, int]]:
    """(model, task, attempt) for the k=3 fill. Default attempts 2–3 only."""
    cells: list[tuple[dict[str, Any], str, int]] = []
    for model in subjects:
        for name in tasks_for_k3_subject(model):
            for attempt in attempts:
                cells.append((model, name, attempt))
    return cells


def _upper_moe_subjects(
    group: str,
    batch: int | None,
    lock: dict[str, Any],
    *,
    label: str,
) -> list[dict[str, Any]]:
    allowed = {
        "main",
        "hard-dev",
        "base-fill",
        "upper-moe",
        "upper",
        "ruler",
        "moe",
        "35b",
    }
    if group not in allowed:
        raise SystemExit(f"{label} is 27B+35B only; omit --group or use upper/moe")
    if group in {"upper", "ruler", "moe", "35b"}:
        return select_subjects(group, batch, lock)
    rows = [m for m in models(lock) if m.get("group") in {UPPER_GROUP, MOE_GROUP}]
    if batch is not None:
        rows = [m for m in rows if int(m.get("batch") or 0) == batch]
    return rows


def hard_dev_subjects(
    group: str,
    batch: int | None,
    lock: dict[str, Any],
) -> list[dict[str, Any]]:
    """Hard-Dev k=3 examinees are 27B then 35B. Compact-10 stay off this set."""
    return _upper_moe_subjects(group, batch, lock, label="Hard-Dev k=3")


def upper_base_subjects(
    group: str,
    batch: int | None,
    lock: dict[str, Any],
) -> list[dict[str, Any]]:
    """27B/35B Base-47 k=3. Compact-10 stay on locked-core-k3.json."""
    return _upper_moe_subjects(group, batch, lock, label="Base-47 k=3 fill")


def hard_release_subjects(
    group: str,
    batch: int | None,
    lock: dict[str, Any],
) -> list[dict[str, Any]]:
    """Hard-Release defaults to the 6 Base-competent examinees, not all 12."""
    return hard_release_rows(group, batch, lock)


def hard_floor_subjects(
    group: str,
    batch: int | None,
    lock: dict[str, Any],
) -> list[dict[str, Any]]:
    """Hard-15 completeness for the 6 skipped compact models."""
    return hard_floor_rows(group, batch, lock)


def _env() -> dict[str, str]:
    env = os.environ.copy()
    env["PYTHONPATH"] = str(ROOT) + os.pathsep + env.get("PYTHONPATH", "")
    return env


def _ak_args(row: dict[str, Any], lock: dict[str, Any]) -> list[str]:
    args = ["--ak", "temperature=0.0"]
    extra = llm_kwargs(row, lock)
    if extra:
        args.extend(
            ["--ak", f"llm_call_kwargs={json.dumps(extra, separators=(',', ':'))}"]
        )
    return args


def _cmd(row: dict[str, Any], name: str, lock: dict[str, Any]) -> list[str]:
    model = openrouter_id(row)
    if not model:
        raise ValueError(f"{row['id']} has no openrouter_id")
    cmd = [
        "harbor",
        "run",
        "--env-file",
        str(ENV),
        "-o",
        str(JOBS),
        "-p",
        str(TASKS / name),
        "-a",
        AGENT,
        "-m",
        model,
        "-k",
        "1",
        "-n",
        "1",
        "-e",
        "novita",
        "-r",
        "5",
    ]
    for exc in RETRY_INCLUDE:
        cmd.extend(["--retry-include", exc])
    cmd.extend(_ak_args(row, lock))
    return cmd


def _prevent_sleep():
    if sys.platform != "win32":
        return lambda: None
    import ctypes
    import threading

    es_continuous = 0x80000000
    es_system_required = 0x00000001
    k32 = ctypes.windll.kernel32
    stop = threading.Event()

    def pulse() -> None:
        while not stop.wait(30):
            k32.SetThreadExecutionState(es_continuous | es_system_required)

    k32.SetThreadExecutionState(es_continuous | es_system_required)
    threading.Thread(target=pulse, daemon=True).start()

    def restore() -> None:
        stop.set()
        k32.SetThreadExecutionState(es_continuous)

    return restore


def _job_names() -> set[str]:
    if not JOBS.is_dir():
        return set()
    return {p.name for p in JOBS.iterdir() if p.is_dir() and p.name[:2] == "20"}


def _newest(before: set[str]) -> Path | None:
    created = [
        p
        for p in JOBS.iterdir()
        if p.is_dir() and p.name[:2] == "20" and p.name not in before
    ]
    if not created:
        return None
    return max(created, key=lambda p: p.name)


def _all_infra(report: dict) -> bool:
    trials = report.get("trials") or []
    if not trials:
        return True
    return all(row.get("termination") == "infra" for row in trials)


def report_is_scored(report: dict | None) -> bool:
    """True when a trial has a non-infra termination and atomic_correct is set."""
    if not report:
        return False
    trials = report.get("trials") or []
    if not trials:
        return False
    row = trials[0]
    if row.get("atomic_correct") is None:
        return False
    return row.get("termination") in SCORED_TERMINATIONS


def _job_exception(job: Path | None) -> tuple[str | None, str | None]:
    if job is None:
        return None, None
    trials = load_trials(job)
    if not trials:
        return None, None
    info = trials[0][1].get("exception_info") or {}
    exc = info.get("exception_type")
    msg = info.get("exception_message")
    return (
        str(exc) if exc else None,
        msg if isinstance(msg, str) else None,
    )


def slot_fill_kind(
    report: dict | None,
    *,
    exc: str | None = None,
    message: str | None = None,
    no_job: bool = False,
) -> str:
    """Classify one Harbor visit: scored | rate_limit | infra."""
    if no_job or report is None:
        return "infra"
    if report_is_scored(report):
        return "scored"
    trial_exc = exc
    if trial_exc is None:
        trials = report.get("trials") or []
        if trials:
            trial_exc = trials[0].get("exception")
    if is_rate_limit(trial_exc, message):
        return "rate_limit"
    return "infra"


def infra_retry_exhausted(
    kind: str, *, visit_infra: int, visit_rate_limit: int
) -> bool:
    """Rate-limit is unbounded (RATE_LIMIT_RETRY_CAP=None); other infra uses INFRA_RETRY_CAP."""
    if kind == "rate_limit":
        cap = RATE_LIMIT_RETRY_CAP
        return cap is not None and visit_rate_limit >= cap
    return visit_infra >= INFRA_RETRY_CAP


def _timeout_kind(job: Path | None) -> str | None:
    if job is None:
        return None
    trials = load_trials(job)
    if not trials:
        return None
    return classify_trial(trials[0][1])


def _run_task(row: dict[str, Any], name: str, lock: dict[str, Any]) -> Path | None:
    known = _job_names()
    result = subprocess.run(
        _cmd(row, name, lock), cwd=str(ROOT), env=_env(), check=False
    )
    job = _newest(known)
    if job is None:
        print(
            f"no new job after {name} {row['id']} exit={result.returncode}",
            file=sys.stderr,
        )
        return None
    try:
        report = score_job(job)
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        print(
            f"unreadable job {job} after {name} {row['id']}: "
            f"{type(exc).__name__}: {exc}",
            flush=True,
        )
        return None
    (job / "standard-scores.json").write_text(
        json.dumps(report, indent=2) + "\n", encoding="utf-8"
    )
    print(format_report(report), flush=True)
    return job


def _load_rows(path: Path) -> list[dict]:
    if not path.is_file():
        return []
    data = json.loads(path.read_text(encoding="utf-8"))
    return list(data.get("rows") or [])


def _upsert_row(rows: list[dict], row: dict) -> None:
    keys = ("lock_id", "task")
    for i, existing in enumerate(rows):
        if all(existing.get(k) == row.get(k) for k in keys):
            rows[i] = row
            return
    rows.append(row)


def _find_k3_row(
    rows: list[dict], lock_id: str, task: str, attempt: int
) -> dict[str, Any] | None:
    for existing in rows:
        if (
            existing.get("lock_id") == lock_id
            and existing.get("task") == task
            and attempt_of(existing) == attempt
        ):
            return existing
    return None


def _upsert_k3(rows: list[dict], row: dict) -> None:
    lock_id = row["lock_id"]
    task = row["task"]
    attempt = attempt_of(row)
    for i, existing in enumerate(rows):
        if (
            existing.get("lock_id") == lock_id
            and existing.get("task") == task
            and attempt_of(existing) == attempt
        ):
            rows[i] = row
            return
    rows.append(row)


def _k3_meta(model: dict[str, Any], lock: dict[str, Any]) -> dict[str, Any]:
    harness = lock.get("harness") or {}
    inf = lock.get("inference") or {}
    return {
        "benchmark_version": BENCHMARK_VERSION,
        "agent": harness.get("agent") or AGENT,
        "agent_version": harness.get("agent_version"),
        "temperature": inf.get("temperature", 0.0),
        "thinking": inf.get("thinking"),
        "openrouter_provider": model.get("openrouter_provider"),
    }


def _seed_attempt1(rows: list[dict], lock: dict[str, Any]) -> int:
    added = 0
    by_id = {m["id"]: m for m in lock.get("models") or []}
    for src in _load_rows(CORE_OUT):
        lock_id = src.get("lock_id")
        task = src.get("task")
        if not lock_id or not task:
            continue
        if _find_k3_row(rows, lock_id, task, 1) is not None:
            continue
        seeded = dict(src)
        seeded["attempt"] = 1
        seeded.setdefault("benchmark_version", BENCHMARK_VERSION)
        model = by_id.get(lock_id) or {}
        for key, value in _k3_meta(model, lock).items():
            seeded.setdefault(key, value)
        rows.append(seeded)
        added += 1
    return added


def _k3_scope_cells(lock: dict[str, Any]) -> list[tuple[str, str]]:
    cells: list[tuple[str, str]] = []
    for model in lock.get("models") or []:
        for name in tasks_for_k3_subject(model):
            cells.append((model["id"], name))
    return cells


def _report_ids(
    lock: dict[str, Any], subjects: list[dict[str, Any]], rows: list[dict]
) -> list[str]:
    lock_ids = [m["id"] for m in lock["models"]]
    wanted = {m["id"] for m in subjects} | {
        r["lock_id"] for r in rows if r.get("lock_id")
    }
    return [i for i in lock_ids if i in wanted]


def _write_protocol(
    rows: list[dict], lock: dict[str, Any], subjects: list[dict[str, Any]]
) -> Path:
    by_model: dict[str, list[dict]] = defaultdict(list)
    for row in rows:
        by_model[row["lock_id"]].append(row)
    id_order = _report_ids(lock, subjects, rows)
    by_id = {m["id"]: m for m in lock["models"]}
    report_subjects = []
    for model_id in id_order:
        model = by_id[model_id]
        recs = by_model.get(model["id"]) or []
        tasks = {r["task"]: r for r in recs}
        passed = all(
            (tasks.get(name) or {}).get("atomic_correct") == 1
            and (tasks.get(name) or {}).get("termination") == "clean"
            for name in PROTOCOL_SMOKE
        )
        routing = None if openrouter_id(model) else "missing_on_openrouter"
        if routing and not recs:
            passed = False
        report_subjects.append(
            {
                "id": model["id"],
                "group": model["group"],
                "batch": model["batch"],
                "openrouter_id": openrouter_id(model),
                "routing": model.get("routing") or routing,
                "protocol_pass": passed if recs or routing else None,
                "tasks": {
                    name: {
                        "atomic_correct": (tasks.get(name) or {}).get("atomic_correct"),
                        "termination": (tasks.get(name) or {}).get("termination"),
                        "job": (tasks.get(name) or {}).get("job"),
                        "reason": (tasks.get(name) or {}).get("reason"),
                    }
                    for name in PROTOCOL_SMOKE
                },
            }
        )
    report = {
        "kind": "protocol_check",
        "published": False,
        "substitution_policy": "forbidden",
        "pass_rule": "atomic_correct=1 and termination=clean; ignore MAIN_47 scores",
        "fail_rule": "keep the model in the lock; record protocol_fail; do not replace",
        "n_models": len(id_order),
        "tasks": list(PROTOCOL_SMOKE),
        "rows": rows,
        "subjects": report_subjects,
    }
    PROTOCOL_OUT.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(f"wrote {PROTOCOL_OUT}", flush=True)
    return PROTOCOL_OUT


def _write_core(
    rows: list[dict], lock: dict[str, Any], subjects: list[dict[str, Any]]
) -> Path:
    by_task: dict[str, dict[str, dict]] = defaultdict(dict)
    for row in rows:
        by_task[row["task"]][row["lock_id"]] = row
    ids = _report_ids(lock, subjects, rows)
    items = []
    for task in MAIN_47:
        scores = by_task.get(task) or {}
        vals = [
            scores[i]["atomic_correct"]
            for i in ids
            if i in scores and scores[i].get("atomic_correct") is not None
        ]
        if len(vals) >= 2 and len(set(vals)) > 1:
            role = "discriminator"
        elif vals and all(v == 1 for v in vals):
            role = "smoke"
        elif vals and all(v == 0 for v in vals):
            role = "both_miss"
        else:
            role = "incomplete"
        items.append(
            {
                "task": task,
                "atom": atom_of(task),
                "role": role,
                "by_model": {
                    i: {
                        "atomic_correct": (scores[i] or {}).get("atomic_correct"),
                        "termination": (scores[i] or {}).get("termination"),
                        "timeout_kind": (scores[i] or {}).get("timeout_kind"),
                        "job": (scores[i] or {}).get("job"),
                        "openrouter_id": (scores[i] or {}).get("openrouter_id"),
                        "group": (scores[i] or {}).get("group"),
                    }
                    if i in scores
                    else None
                    for i in ids
                },
            }
        )
    skill: dict[str, dict[str, float | None]] = {}
    for prefix, label in ATOMS.items():
        skill[label] = {}
        for model_id in ids:
            vals = [
                r["atomic_correct"]
                for r in rows
                if r["lock_id"] == model_id
                and r["atom"] == prefix
                and r.get("atomic_correct") is not None
                and r.get("termination") != "infra"
            ]
            skill[label][model_id] = sum(vals) / len(vals) if vals else None
    report = {
        "kind": "locked_core_k1",
        "published": False,
        "substitution_policy": "forbidden",
        "lock": str(ROOT / "models.lock.yaml"),
        "models": ids,
        "n_tasks": len(MAIN_47),
        "n_trials_expected": len(ids) * len(MAIN_47),
        "skill_means": skill,
        "n_discriminator": sum(1 for i in items if i["role"] == "discriminator"),
        "n_smoke": sum(1 for i in items if i["role"] == "smoke"),
        "n_both_miss": sum(1 for i in items if i["role"] == "both_miss"),
        "n_incomplete": sum(1 for i in items if i["role"] == "incomplete"),
        "rows": rows,
        "items": items,
    }
    CORE_OUT.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(
        "===== LOCKED CORE k=1 =====\n"
        f"discriminator {report['n_discriminator']}  "
        f"smoke {report['n_smoke']}  "
        f"both_miss {report['n_both_miss']}  "
        f"incomplete {report['n_incomplete']}\n"
        f"wrote {CORE_OUT}",
        flush=True,
    )
    return CORE_OUT


def _trial_row(
    row: dict[str, Any],
    name: str,
    job: Path | None,
    reason: str | None,
    *,
    timeout_kind: str | None = None,
    stall_retried: bool = False,
    attempt: int = 1,
    infra_retries: int = 0,
    lock: dict[str, Any] | None = None,
) -> dict:
    trial: dict[str, Any] = {}
    if job is not None:
        report = json.loads((job / "standard-scores.json").read_text(encoding="utf-8"))
        trial = (report.get("trials") or [{}])[0]
    rec = {
        "lock_id": row["id"],
        "group": row["group"],
        "batch": row["batch"],
        "openrouter_id": openrouter_id(row),
        "task": name,
        "atom": "protocol" if name in PROTOCOL_SMOKE else atom_of(name),
        "attempt": attempt,
        "atomic_correct": trial.get("atomic_correct"),
        "termination": trial.get("termination") or ("routing" if reason else None),
        "timeout_kind": timeout_kind,
        "stall_retried": stall_retried,
        "infra_retries": infra_retries,
        "job": str(job) if job else None,
        "reason": reason,
    }
    if lock is not None:
        rec.update(_k3_meta(row, lock))
    return rec


def _execute(
    rows_out: list[dict],
    subjects: list[dict[str, Any]],
    names: tuple[str, ...],
    writer,
    lock: dict[str, Any],
    *,
    force: bool,
) -> int:
    code = 0
    started = False
    for row in subjects:
        oid = openrouter_id(row)
        for name in names:
            prev = next(
                (
                    existing
                    for existing in rows_out
                    if existing.get("lock_id") == row["id"]
                    and existing.get("task") == name
                ),
                None,
            )
            if trial_is_done(prev, force=force):
                print(f"skip done {row['id']} {name}", flush=True)
                continue
            print(f"===== locked {row['id']} {name} =====", flush=True)
            if not oid:
                _upsert_row(
                    rows_out,
                    _trial_row(row, name, None, "missing_on_openrouter"),
                )
                writer(rows_out, lock, subjects)
                print("skip: no OpenRouter id; slot kept, not substituted", flush=True)
                continue
            if not started:
                print("wait 8s before first sandbox create", flush=True)
                time.sleep(8)
                started = True
            else:
                time.sleep(8)
            job = _run_task(row, name, lock)
            if job is None:
                code = 2
                _upsert_row(rows_out, _trial_row(row, name, None, "no_job"))
                writer(rows_out, lock, subjects)
                continue
            report = json.loads(
                (job / "standard-scores.json").read_text(encoding="utf-8")
            )
            if _all_infra(report):
                print(f"{name}: infra, wait 60s and retry once", flush=True)
                time.sleep(60)
                job = _run_task(row, name, lock) or job
                report = json.loads(
                    (job / "standard-scores.json").read_text(encoding="utf-8")
                )
                if _all_infra(report):
                    code = 1
            kind = _timeout_kind(job)
            stall_retried = False
            if kind == KIND_STALL:
                print(f"{name}: timeout_stall, wait 60s and retry once", flush=True)
                time.sleep(60)
                replacement = _run_task(row, name, lock)
                stall_retried = True
                if replacement is not None:
                    job = replacement
                    kind = _timeout_kind(job)
                    report = json.loads(
                        (job / "standard-scores.json").read_text(encoding="utf-8")
                    )
                    if _all_infra(report):
                        code = 1
            _upsert_row(
                rows_out,
                _trial_row(
                    row,
                    name,
                    job,
                    None,
                    timeout_kind=kind,
                    stall_retried=stall_retried,
                ),
            )
            writer(rows_out, lock, subjects)
    return code


def _run_k3_slot(
    model: dict[str, Any],
    name: str,
    attempt: int,
    lock: dict[str, Any],
    prev: dict[str, Any] | None,
) -> dict[str, Any]:
    """New Harbor trial for one (model, task, attempt).

    429 / RateLimit does not fill the slot and is retried until a scored
    trial exists (clean / tle / protocol_error with atomic_correct set).
    Other infra keeps INFRA_RETRY_CAP visits then records termination=infra.
    """
    infra_retries = int((prev or {}).get("infra_retries") or 0)
    visit_infra = 0
    visit_rate_limit = 0
    stall_retried = False
    job: Path | None = None
    kind: str | None = None
    reason: str | None = None
    while True:
        job = _run_task(model, name, lock)
        if job is None:
            visit_infra += 1
            infra_retries += 1
            reason = "no_job"
            fill = "infra"
            if infra_retry_exhausted(
                fill, visit_infra=visit_infra, visit_rate_limit=visit_rate_limit
            ):
                return _trial_row(
                    model,
                    name,
                    None,
                    reason,
                    attempt=attempt,
                    infra_retries=infra_retries,
                    lock=lock,
                )
            print(
                f"{model['id']} {name} a{attempt}: no_job, "
                f"wait {INFRA_BACKOFF_SEC}s infra retry {visit_infra}/{INFRA_RETRY_CAP}",
                flush=True,
            )
            time.sleep(INFRA_BACKOFF_SEC)
            continue
        report = json.loads((job / "standard-scores.json").read_text(encoding="utf-8"))
        exc, message = _job_exception(job)
        fill = slot_fill_kind(report, exc=exc, message=message)
        if fill == "scored":
            kind = _timeout_kind(job)
            if kind == KIND_STALL and not stall_retried:
                stall_retried = True
                print(
                    f"{model['id']} {name} a{attempt}: timeout_stall, "
                    f"wait {INFRA_BACKOFF_SEC}s retry once",
                    flush=True,
                )
                time.sleep(INFRA_BACKOFF_SEC)
                continue
            return _trial_row(
                model,
                name,
                job,
                None,
                timeout_kind=kind,
                stall_retried=stall_retried,
                attempt=attempt,
                infra_retries=infra_retries,
                lock=lock,
            )
        if fill == "rate_limit":
            visit_rate_limit += 1
            infra_retries += 1
            reason = "infra"
            if infra_retry_exhausted(
                fill,
                visit_infra=visit_infra,
                visit_rate_limit=visit_rate_limit,
            ):
                return _trial_row(
                    model,
                    name,
                    job,
                    reason,
                    timeout_kind=_timeout_kind(job),
                    attempt=attempt,
                    infra_retries=infra_retries,
                    lock=lock,
                )
            cap_shown = RATE_LIMIT_RETRY_CAP if RATE_LIMIT_RETRY_CAP is not None else "unbounded"
            print(
                f"{model['id']} {name} a{attempt}: rate-limit {exc or 'RateLimit'}, "
                f"wait {INFRA_BACKOFF_SEC}s retry {visit_rate_limit}/{cap_shown} "
                f"(slot not filled)",
                flush=True,
            )
            time.sleep(INFRA_BACKOFF_SEC)
            continue
        visit_infra += 1
        infra_retries += 1
        reason = "infra"
        if infra_retry_exhausted(
            fill, visit_infra=visit_infra, visit_rate_limit=visit_rate_limit
        ):
            return _trial_row(
                model,
                name,
                job,
                reason,
                timeout_kind=_timeout_kind(job),
                attempt=attempt,
                infra_retries=infra_retries,
                lock=lock,
            )
        print(
            f"{model['id']} {name} a{attempt}: infra, "
            f"wait {INFRA_BACKOFF_SEC}s retry {visit_infra}/{INFRA_RETRY_CAP} "
            f"(slot not filled)",
            flush=True,
        )
        time.sleep(INFRA_BACKOFF_SEC)


def _write_core_k3(
    rows: list[dict], lock: dict[str, Any], subjects: list[dict[str, Any]]
) -> Path:
    by_id = {m["id"]: m for m in lock.get("models") or []}
    scope = _k3_scope_cells(lock)
    cells = []
    n_incomplete = 0
    for lock_id, task in scope:
        attempts = [
            r for r in rows if r.get("lock_id") == lock_id and r.get("task") == task
        ]
        by_attempt = {
            attempt_of(r): r
            for r in attempts
            if attempt_is_valid(r) and attempt_of(r) in (1, 2, 3)
        }
        n_valid = len(by_attempt)
        infra_count = sum(
            1
            for r in attempts
            if r.get("termination") == "infra" or r.get("reason") in {"infra", "no_job"}
        )
        incomplete = n_valid < K3_K
        if incomplete:
            n_incomplete += 1
        p_atomic = None
        p_e2e = None
        if n_valid == K3_K:
            p_atomic = (
                sum(int(by_attempt[a]["atomic_correct"]) for a in (1, 2, 3)) / K3_K
            )
            p_e2e = (
                sum(
                    1
                    if by_attempt[a].get("atomic_correct") == 1
                    and by_attempt[a].get("termination") == "clean"
                    else 0
                    for a in (1, 2, 3)
                )
                / K3_K
            )
        cells.append(
            {
                "lock_id": lock_id,
                "task": task,
                "group": (by_id.get(lock_id) or {}).get("group"),
                "n_valid": n_valid,
                "incomplete": incomplete,
                "p_atomic": p_atomic,
                "p_e2e": p_e2e,
                "infra_count": infra_count,
            }
        )
    main_ids = [
        m["id"] for m in lock.get("models") or [] if m.get("group") == COMPACT_GROUP
    ]
    skill: dict[str, dict[str, float | None]] = {}
    for prefix, label in ATOMS.items():
        skill[label] = {}
        for model_id in main_ids:
            vals = [
                c["p_atomic"]
                for c in cells
                if c["lock_id"] == model_id
                and atom_of(c["task"]) == prefix
                and c["p_atomic"] is not None
            ]
            skill[label][model_id] = sum(vals) / len(vals) if vals else None
    report = {
        "kind": "locked_core_k3",
        "published": False,
        "benchmark_version": BENCHMARK_VERSION,
        "k": K3_K,
        "source_attempt1": str(CORE_OUT),
        "overwrites_source": False,
        "attempts_filled": list(K3_ATTEMPTS),
        "n_valid_required": K3_K,
        "models": _report_ids(lock, subjects, rows),
        "n_scope_cells": len(scope),
        "n_incomplete_cells": n_incomplete,
        "skill_means_atomic": skill,
        "cells": cells,
        "rows": rows,
    }
    K3_OUT.parent.mkdir(parents=True, exist_ok=True)
    K3_OUT.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(
        "===== LOCKED CORE k=3 fill =====\n"
        f"scope {report['n_scope_cells']}  incomplete {n_incomplete}\n"
        f"wrote {K3_OUT} (did not overwrite {CORE_OUT})",
        flush=True,
    )
    return K3_OUT


def _execute_k3(
    rows_out: list[dict],
    subjects: list[dict[str, Any]],
    lock: dict[str, Any],
    *,
    force: bool,
) -> int:
    code = 0
    started = False
    cells = plan_k3_cells(subjects)
    for model, name, attempt in cells:
        prev = _find_k3_row(rows_out, model["id"], name, attempt)
        if trial_is_done(prev, force=force):
            print(f"skip done {model['id']} {name} a{attempt}", flush=True)
            continue
        print(f"===== k3 fill {model['id']} {name} attempt={attempt} =====", flush=True)
        if not openrouter_id(model):
            _upsert_k3(
                rows_out,
                _trial_row(
                    model,
                    name,
                    None,
                    "missing_on_openrouter",
                    attempt=attempt,
                    lock=lock,
                ),
            )
            _write_core_k3(rows_out, lock, subjects)
            continue
        if not started:
            print("wait 8s before first sandbox create", flush=True)
            time.sleep(8)
            started = True
        else:
            time.sleep(8)
        rec = _run_k3_slot(model, name, attempt, lock, prev)
        if rec.get("termination") == "infra" or rec.get("reason") in {
            "infra",
            "no_job",
        }:
            code = max(code, 1)
        _upsert_k3(rows_out, rec)
        _write_core_k3(rows_out, lock, subjects)
    return code


def _print_hard_dev_plan(
    subjects: list[dict[str, Any]],
    lock: dict[str, Any],
    group: str,
    force: bool,
) -> list[tuple[dict[str, Any], str, int]]:
    cells = plan_hard_dev_cells(subjects)
    rows = _load_rows(HARD_DEV_OUT)
    n_skip = 0
    n_pending = 0
    for model, name, attempt in cells:
        prev = _find_k3_row(rows, model["id"], name, attempt)
        if trial_is_done(prev, force=force):
            n_skip += 1
        else:
            n_pending += 1
    print(
        f"===== HARD-DEV k=3 PLAN =====\n"
        f"benchmark_version={BENCHMARK_VERSION}\n"
        f"group={group} n_subjects={len(subjects)} force={force}\n"
        f"attempts={list(HARD_DEV_ATTEMPTS)}  n_trials={len(cells)}\n"
        f"pending={n_pending} already_done={n_skip}\n"
        f"writes={HARD_DEV_OUT}\n"
        f"does not overwrite {CORE_OUT} or {K3_OUT}\n"
        f"each attempt is a new Harbor -k 1 sandbox; infra retries do not fill the slot"
    )
    for row in subjects:
        oid = openrouter_id(row) or "UNROUTABLE"
        print(
            f"  {row['id']:36} {row['group']:14} "
            f"{len(HARD_DEV_10)} tasks × {len(HARD_DEV_ATTEMPTS)} = "
            f"{len(HARD_DEV_10) * len(HARD_DEV_ATTEMPTS)}  {oid}"
        )
    if subjects:
        sample = next((s for s in subjects if openrouter_id(s)), subjects[0])
        print(" ", " ".join(_cmd(sample, HARD_DEV_10[0], lock)))
    return cells


def _print_hard_release_plan(
    subjects: list[dict[str, Any]],
    lock: dict[str, Any],
    group: str,
    force: bool,
) -> list[tuple[dict[str, Any], str, int]]:
    cells = plan_hard_release_cells(subjects)
    rows = _load_rows(HARD_RELEASE_OUT)
    n_skip = 0
    n_pending = 0
    for model, name, attempt in cells:
        prev = _find_k3_row(rows, model["id"], name, attempt)
        if trial_is_done(prev, force=force):
            n_skip += 1
        else:
            n_pending += 1
    print(
        f"===== HARD-RELEASE k=3 PLAN =====\n"
        f"benchmark_version={BENCHMARK_VERSION}\n"
        f"group={group} n_subjects={len(subjects)} force={force}\n"
        f"attempts={list(HARD_RELEASE_ATTEMPTS)}  n_trials={len(cells)}\n"
        f"pending={n_pending} already_done={n_skip}\n"
        f"writes={HARD_RELEASE_OUT}\n"
        f"does not overwrite {CORE_OUT} or {K3_OUT} or {HARD_DEV_OUT}\n"
        f"each attempt is a new Harbor -k 1 sandbox; infra retries do not fill the slot"
    )
    skipped = [m["id"] for m in models(lock) if m.get("hard_release") is not True]
    if group != "all" and skipped:
        print(
            "skipped (Base floor / Medium-struggle; completeness is --hard-floor): "
            + ", ".join(skipped)
        )
    for row in subjects:
        oid = openrouter_id(row) or "UNROUTABLE"
        print(
            f"  {row['id']:36} {row['group']:14} "
            f"{len(HARD_RELEASE_15)} tasks × {len(HARD_RELEASE_ATTEMPTS)} = "
            f"{len(HARD_RELEASE_15) * len(HARD_RELEASE_ATTEMPTS)}  {oid}"
        )
    if subjects:
        sample = next((s for s in subjects if openrouter_id(s)), subjects[0])
        print(" ", " ".join(_cmd(sample, HARD_RELEASE_15[0], lock)))
    return cells


def _print_hard_floor_plan(
    subjects: list[dict[str, Any]],
    lock: dict[str, Any],
    group: str,
    force: bool,
) -> list[tuple[dict[str, Any], str, int]]:
    cells = plan_hard_release_cells(subjects)
    rows = _load_rows(HARD_FLOOR_OUT)
    n_skip = 0
    n_pending = 0
    for model, name, attempt in cells:
        prev = _find_k3_row(rows, model["id"], name, attempt)
        if trial_is_done(prev, force=force):
            n_skip += 1
        else:
            n_pending += 1
    print(
        f"===== HARD-FLOOR k=3 PLAN =====\n"
        f"benchmark_version={BENCHMARK_VERSION}\n"
        f"group={group} n_subjects={len(subjects)} force={force}\n"
        f"attempts={list(HARD_RELEASE_ATTEMPTS)}  n_trials={len(cells)}\n"
        f"pending={n_pending} already_done={n_skip}\n"
        f"writes={HARD_FLOOR_OUT}\n"
        f"does not overwrite {CORE_OUT} or {K3_OUT} or {HARD_RELEASE_OUT}\n"
        f"each attempt is a new Harbor -k 1 sandbox; infra retries do not fill the slot"
    )
    for row in subjects:
        oid = openrouter_id(row) or "UNROUTABLE"
        print(
            f"  {row['id']:36} {row['group']:14} "
            f"{len(HARD_RELEASE_15)} tasks × {len(HARD_RELEASE_ATTEMPTS)} = "
            f"{len(HARD_RELEASE_15) * len(HARD_RELEASE_ATTEMPTS)}  {oid}"
        )
    if subjects:
        sample = next((s for s in subjects if openrouter_id(s)), subjects[0])
        print(" ", " ".join(_cmd(sample, HARD_RELEASE_15[0], lock)))
    return cells


def _print_upper_base_plan(
    subjects: list[dict[str, Any]],
    lock: dict[str, Any],
    group: str,
    force: bool,
) -> list[tuple[dict[str, Any], str, int]]:
    cells = plan_upper_base_cells(subjects)
    rows = _load_rows(UPPER_BASE_OUT)
    seeded = _seed_upper_base(rows, lock, subjects)
    n_skip = 0
    n_pending = 0
    for model, name, attempt in cells:
        prev = _find_k3_row(rows, model["id"], name, attempt)
        if trial_is_done(prev, force=force):
            n_skip += 1
        else:
            n_pending += 1
    print(
        f"===== UPPER-BASE k=3 PLAN =====\n"
        f"benchmark_version={BENCHMARK_VERSION}\n"
        f"group={group} n_subjects={len(subjects)} force={force}\n"
        f"attempts={list(UPPER_BASE_ATTEMPTS)}  n_trials={len(cells)}\n"
        f"pending={n_pending} already_done={n_skip} seeded={seeded}\n"
        f"writes={UPPER_BASE_OUT}\n"
        f"does not overwrite {CORE_OUT} or {K3_OUT} or {HARD_DEV_OUT} "
        f"or {HARD_RELEASE_OUT}\n"
        f"seeds 27B from {K3_OUT} then {CORE_OUT}; 35B starts empty\n"
        f"each attempt is a new Harbor -k 1 sandbox; infra retries do not fill the slot"
    )
    for row in subjects:
        oid = openrouter_id(row) or "UNROUTABLE"
        print(
            f"  {row['id']:36} {row['group']:14} "
            f"{len(MAIN_47)} tasks × {len(UPPER_BASE_ATTEMPTS)} = "
            f"{len(MAIN_47) * len(UPPER_BASE_ATTEMPTS)}  {oid}"
        )
    if subjects:
        sample = next((s for s in subjects if openrouter_id(s)), subjects[0])
        print(" ", " ".join(_cmd(sample, MAIN_47[0], lock)))
    return cells


def _print_k3_plan(
    subjects: list[dict[str, Any]],
    lock: dict[str, Any],
    group: str,
    force: bool,
) -> list[tuple[dict[str, Any], str, int]]:
    cells = plan_k3_cells(subjects)
    n_main = sum(1 for m, _, _ in cells if m.get("group") == COMPACT_GROUP)
    n_ruler = sum(1 for m, _, _ in cells if m.get("group") in {UPPER_GROUP, "ruler"})
    rows = _load_rows(K3_OUT)
    seeded = _seed_attempt1(list(rows), lock)
    n_skip = 0
    n_pending = 0
    for model, name, attempt in cells:
        prev = _find_k3_row(rows, model["id"], name, attempt)
        if trial_is_done(prev, force=force):
            n_skip += 1
        else:
            n_pending += 1
    print(
        f"===== K3 FILL PLAN =====\n"
        f"benchmark_version={BENCHMARK_VERSION}\n"
        f"group={group} n_subjects={len(subjects)} force={force}\n"
        f"attempts={list(K3_ATTEMPTS)}  n_new_trials={len(cells)}  "
        f"main={n_main} ruler_loc={n_ruler}\n"
        f"pending={n_pending} already_done={n_skip} "
        f"attempt1_would_seed={seeded}\n"
        f"source_attempt1={CORE_OUT}\n"
        f"writes={K3_OUT} (does not overwrite locked-core.json)\n"
        f"each attempt is a new Harbor -k 1 sandbox; infra retries do not fill the slot"
    )
    for row in subjects:
        oid = openrouter_id(row) or "UNROUTABLE"
        names = tasks_for_k3_subject(row)
        print(
            f"  {row['id']:36} {row['group']:14} "
            f"{len(names)} tasks × {len(K3_ATTEMPTS)} = {len(names) * len(K3_ATTEMPTS)}  {oid}"
        )
    if subjects:
        sample = next((s for s in subjects if openrouter_id(s)), subjects[0])
        print(" ", " ".join(_cmd(sample, tasks_for_k3_subject(sample)[0], lock)))
    return cells


def _print_plan(
    subjects: list[dict[str, Any]],
    protocol: bool,
    core: bool,
    lock: dict[str, Any],
    group: str,
    batch: int | None,
    force: bool,
) -> None:
    n_proto = len(subjects) * len(PROTOCOL_SMOKE) if protocol else 0
    n_core = len(subjects) * len(MAIN_47) if core else 0
    print(
        f"frozen lock; group={group} batch={batch or 'all'} "
        f"n_subjects={len(subjects)} force={force}"
    )
    print(
        "batch is execution order only; no post-hoc swap; restart skips completed cells"
    )
    for row in subjects:
        oid = openrouter_id(row) or "UNROUTABLE"
        print(f"  batch{row['batch']} {row['group']:14} {row['id']:36} {oid}")
    if protocol:
        print("protocol tasks:", ", ".join(PROTOCOL_SMOKE), f"({n_proto} trials)")
        sample = next((s for s in subjects if openrouter_id(s)), None)
        if sample:
            print(" ", " ".join(_cmd(sample, PROTOCOL_SMOKE[0], lock)))
    if core:
        print(f"core tasks: MAIN_47 ({len(MAIN_47)}), expected {n_core} trials")


def _parse_argv(argv: list[str]) -> dict[str, Any]:
    run = "--run" in argv
    full = "--full" in argv
    k3_fill = "--k3-fill" in argv
    hard_dev = "--hard-dev" in argv
    hard_release = "--hard-release" in argv
    hard_floor = "--hard-floor" in argv
    base_fill = "--base-fill" in argv
    if sum([k3_fill, hard_dev, hard_release, hard_floor, base_fill]) > 1:
        raise SystemExit(
            "use only one of --k3-fill / --hard-dev / --hard-release / "
            "--hard-floor / --base-fill"
        )
    exclusive = k3_fill or hard_dev or hard_release or hard_floor or base_fill
    protocol = False if exclusive else ("--protocol" in argv or full)
    core = False if exclusive else ("--core" in argv or full)
    force = "--force" in argv
    group = "main"
    batch = None
    if "--group" in argv:
        i = argv.index("--group")
        group = argv[i + 1]
    if "--batch" in argv:
        i = argv.index("--batch")
        batch = int(argv[i + 1])
    return {
        "run": run,
        "protocol": protocol,
        "core": core,
        "k3_fill": k3_fill,
        "hard_dev": hard_dev,
        "hard_release": hard_release,
        "hard_floor": hard_floor,
        "base_fill": base_fill,
        "force": force,
        "group": group,
        "batch": batch,
    }


def main() -> int:
    opts = _parse_argv(sys.argv[1:])
    lock = load_lock()
    if opts["hard_release"] and opts["run"] and opts["group"] == "all":
        raise SystemExit(
            "--hard-release --group all --run would write floor cells into "
            f"{HARD_RELEASE_OUT.name}. Use --run --hard-floor "
            f"(writes {HARD_FLOOR_OUT.name})."
        )
    if opts["hard_floor"]:
        subjects = hard_floor_subjects(opts["group"], opts["batch"], lock)
    elif opts["hard_release"]:
        subjects = hard_release_subjects(opts["group"], opts["batch"], lock)
    elif opts["hard_dev"]:
        subjects = hard_dev_subjects(opts["group"], opts["batch"], lock)
    elif opts["base_fill"]:
        subjects = upper_base_subjects(opts["group"], opts["batch"], lock)
    else:
        subjects = select_subjects(opts["group"], opts["batch"], lock)
    print(
        f"lock frozen={lock.get('frozen')} n_lock={len(lock['models'])} "
        f"selected={len(subjects)} group={opts['group']} batch={opts['batch'] or 'all'}"
    )
    if opts["hard_floor"]:
        cells = _print_hard_floor_plan(subjects, lock, opts["group"], opts["force"])
        if not opts["run"]:
            print(
                "dry-run; pass --run --hard-floor to execute on Novita n=1",
                flush=True,
            )
            return 0
        if not ENV.is_file():
            print("missing .env", file=sys.stderr)
            return 2
        needed = sorted({name for _, name, _ in cells})
        missing = [n for n in needed if not (TASKS / n / "task.toml").is_file()]
        if missing:
            print(f"missing tasks: {missing}", file=sys.stderr)
            return 2
        restore = _prevent_sleep()
        try:
            rows = _load_rows(HARD_FLOOR_OUT)
            code = _execute_hard_floor(rows, subjects, lock, force=opts["force"])
            _write_hard_floor_k3(rows, lock, subjects)
        finally:
            restore()
        return code
    if opts["hard_release"]:
        cells = _print_hard_release_plan(subjects, lock, opts["group"], opts["force"])
        if not opts["run"]:
            print(
                "dry-run; pass --run --hard-release to execute on Novita n=1",
                flush=True,
            )
            return 0
        if not ENV.is_file():
            print("missing .env", file=sys.stderr)
            return 2
        needed = sorted({name for _, name, _ in cells})
        missing = [n for n in needed if not (TASKS / n / "task.toml").is_file()]
        if missing:
            print(f"missing tasks: {missing}", file=sys.stderr)
            return 2
        restore = _prevent_sleep()
        try:
            rows = _load_rows(HARD_RELEASE_OUT)
            code = _execute_hard_release(rows, subjects, lock, force=opts["force"])
            _write_hard_release_k3(rows, lock, subjects)
        finally:
            restore()
        return code
    if opts["hard_dev"]:
        cells = _print_hard_dev_plan(subjects, lock, opts["group"], opts["force"])
        if not opts["run"]:
            print("dry-run; pass --run --hard-dev to execute on Novita n=1", flush=True)
            return 0
        if not ENV.is_file():
            print("missing .env", file=sys.stderr)
            return 2
        needed = sorted({name for _, name, _ in cells})
        missing = [n for n in needed if not (TASKS / n / "task.toml").is_file()]
        if missing:
            print(f"missing tasks: {missing}", file=sys.stderr)
            return 2
        restore = _prevent_sleep()
        try:
            rows = _load_rows(HARD_DEV_OUT)
            code = _execute_hard_dev(rows, subjects, lock, force=opts["force"])
            _write_hard_dev_k3(rows, lock, subjects)
        finally:
            restore()
        return code
    if opts["base_fill"]:
        cells = _print_upper_base_plan(subjects, lock, opts["group"], opts["force"])
        if not opts["run"]:
            print(
                "dry-run; pass --run --base-fill to execute on Novita n=1",
                flush=True,
            )
            return 0
        if not ENV.is_file():
            print("missing .env", file=sys.stderr)
            return 2
        needed = sorted({name for _, name, _ in cells})
        missing = [n for n in needed if not (TASKS / n / "task.toml").is_file()]
        if missing:
            print(f"missing tasks: {missing}", file=sys.stderr)
            return 2
        restore = _prevent_sleep()
        try:
            rows = _load_rows(UPPER_BASE_OUT)
            _seed_upper_base(rows, lock, subjects)
            _write_upper_base_k3(rows, lock, subjects)
            code = _execute_upper_base(rows, subjects, lock, force=opts["force"])
            _write_upper_base_k3(rows, lock, subjects)
        finally:
            restore()
        return code
    if opts["k3_fill"]:
        cells = _print_k3_plan(subjects, lock, opts["group"], opts["force"])
        if not opts["run"]:
            print("dry-run; pass --run --k3-fill to execute on Novita n=1", flush=True)
            return 0
        if not ENV.is_file():
            print("missing .env", file=sys.stderr)
            return 2
        needed = sorted({name for _, name, _ in cells})
        missing = [n for n in needed if not (TASKS / n / "task.toml").is_file()]
        if missing:
            print(f"missing tasks: {missing}", file=sys.stderr)
            return 2
        restore = _prevent_sleep()
        try:
            rows = _load_rows(K3_OUT)
            _seed_attempt1(rows, lock)
            code = _execute_k3(rows, subjects, lock, force=opts["force"])
            _write_core_k3(rows, lock, subjects)
        finally:
            restore()
        return code
    if not opts["protocol"] and not opts["core"]:
        _print_plan(
            subjects, True, True, lock, opts["group"], opts["batch"], opts["force"]
        )
        print(
            "dry-run. Compact 10: --run --full --group main. "
            "35B protocol: --run --protocol --group moe. "
            "All 12: --group core. "
            "k=3 fill: --k3-fill --group main (940). "
            "Hard-Dev 27B+35B: --run --hard-dev (60). "
            "Hard-Release 6×15×k=3: --run --hard-release (270). "
            "Hard-Floor skipped 6×15×k=3: --run --hard-floor (270, new file). "
            "27B/35B Base-47 k=3: --run --base-fill (seeds 27B; 35B from scratch). "
            "Do not overwrite locked-core.json, locked-core-k3.json, "
            "or locked-hard-release-k3.json.",
            flush=True,
        )
        return 0
    _print_plan(
        subjects,
        opts["protocol"],
        opts["core"],
        lock,
        opts["group"],
        opts["batch"],
        opts["force"],
    )
    if not opts["run"]:
        print("dry-run; pass --run to execute on Novita n=1")
        return 0
    if not ENV.is_file():
        print("missing .env", file=sys.stderr)
        return 2
    needed = list(PROTOCOL_SMOKE if opts["protocol"] else ()) + list(
        MAIN_47 if opts["core"] else ()
    )
    missing = [n for n in needed if not (TASKS / n / "task.toml").is_file()]
    if missing:
        print(f"missing tasks: {missing}", file=sys.stderr)
        return 2
    restore = _prevent_sleep()
    code = 0
    try:
        if opts["protocol"]:
            rows = _load_rows(PROTOCOL_OUT)
            code = max(
                code,
                _execute(
                    rows,
                    subjects,
                    PROTOCOL_SMOKE,
                    _write_protocol,
                    lock,
                    force=opts["force"],
                ),
            )
            _write_protocol(rows, lock, subjects)
        if opts["core"]:
            rows = _load_rows(CORE_OUT)
            code = max(
                code,
                _execute(
                    rows,
                    subjects,
                    MAIN_47,
                    _write_core,
                    lock,
                    force=opts["force"],
                ),
            )
            _write_core(rows, lock, subjects)
    finally:
        restore()
    return code


if __name__ == "__main__":
    sys.exit(main())
