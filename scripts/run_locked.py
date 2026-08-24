"""Run the frozen roster. Default group is the 10 IRT-main models.

Batch is execution order only. Do not pick models from scores. All-0 /
all-1 stays. Provider is pinned per lock; retries never change the
OpenRouter endpoint. Restart is safe: completed (model, task) pairs skip.

    python scripts/run_locked.py
    python scripts/run_locked.py --run --full --group main
    python scripts/run_locked.py --run --protocol --group main
    python scripts/run_locked.py --run --core --group main --batch 1
    python scripts/run_locked.py --run --full --group all
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
    llm_kwargs,
    load_lock,
    openrouter_id,
    select_subjects,
)
from score_standard import ATOMS, atom_of, format_report, score_job  # noqa: E402
from task_sets import MAIN_47, PROTOCOL_SMOKE  # noqa: E402

TASKS = ROOT / "tasks"
ENV = ROOT / ".env"
JOBS = ROOT / "jobs"
AGENT = "agents.compact_shell:CompactShellAgent"
PROTOCOL_OUT = JOBS / "protocol-check.json"
CORE_OUT = JOBS / "locked-core.json"

RETRY_INCLUDE = (
    "BuildException",
    "EnvironmentStartTimeoutError",
    "RateLimitException",
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


def _env() -> dict[str, str]:
    env = os.environ.copy()
    env["PYTHONPATH"] = str(ROOT) + os.pathsep + env.get("PYTHONPATH", "")
    return env


def _ak_args(row: dict[str, Any], lock: dict[str, Any]) -> list[str]:
    args = ["--ak", "temperature=0.0"]
    extra = llm_kwargs(row, lock)
    if extra:
        args.extend(["--ak", f"llm_call_kwargs={json.dumps(extra, separators=(',', ':'))}"])
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


def _timeout_kind(job: Path | None) -> str | None:
    if job is None:
        return None
    trials = load_trials(job)
    if not trials:
        return None
    return classify_trial(trials[0][1])


def _run_task(row: dict[str, Any], name: str, lock: dict[str, Any]) -> Path | None:
    known = _job_names()
    result = subprocess.run(_cmd(row, name, lock), cwd=str(ROOT), env=_env(), check=False)
    job = _newest(known)
    if job is None:
        print(f"no new job after {name} {row['id']} exit={result.returncode}", file=sys.stderr)
        return None
    report = score_job(job)
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


def _report_ids(lock: dict[str, Any], subjects: list[dict[str, Any]], rows: list[dict]) -> list[str]:
    lock_ids = [m["id"] for m in lock["models"]]
    wanted = {m["id"] for m in subjects} | {r["lock_id"] for r in rows if r.get("lock_id")}
    return [i for i in lock_ids if i in wanted]


def _write_protocol(rows: list[dict], lock: dict[str, Any], subjects: list[dict[str, Any]]) -> Path:
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


def _write_core(rows: list[dict], lock: dict[str, Any], subjects: list[dict[str, Any]]) -> Path:
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
) -> dict:
    trial: dict[str, Any] = {}
    if job is not None:
        report = json.loads((job / "standard-scores.json").read_text(encoding="utf-8"))
        trial = (report.get("trials") or [{}])[0]
    return {
        "lock_id": row["id"],
        "group": row["group"],
        "batch": row["batch"],
        "openrouter_id": openrouter_id(row),
        "task": name,
        "atom": atom_of(name) if name in MAIN_47 else "protocol",
        "atomic_correct": trial.get("atomic_correct"),
        "termination": trial.get("termination") or ("routing" if reason else None),
        "timeout_kind": timeout_kind,
        "stall_retried": stall_retried,
        "job": str(job) if job else None,
        "reason": reason,
    }


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
                    if existing.get("lock_id") == row["id"] and existing.get("task") == name
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
            report = json.loads((job / "standard-scores.json").read_text(encoding="utf-8"))
            if _all_infra(report):
                print(f"{name}: infra, wait 60s and retry once", flush=True)
                time.sleep(60)
                job = _run_task(row, name, lock) or job
                report = json.loads((job / "standard-scores.json").read_text(encoding="utf-8"))
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
    print("batch is execution order only; no post-hoc swap; restart skips completed cells")
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
    protocol = "--protocol" in argv or full
    core = "--core" in argv or full
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
        "force": force,
        "group": group,
        "batch": batch,
    }


def main() -> int:
    opts = _parse_argv(sys.argv[1:])
    lock = load_lock()
    subjects = select_subjects(opts["group"], opts["batch"], lock)
    print(
        f"lock frozen={lock.get('frozen')} n_lock={len(lock['models'])} "
        f"selected={len(subjects)} group={opts['group']} batch={opts['batch'] or 'all'}"
    )
    if not opts["protocol"] and not opts["core"]:
        _print_plan(subjects, True, True, lock, opts["group"], opts["batch"], opts["force"])
        print(
            "dry-run. 10-model full run: --run --full --group main. "
            "Or pass --run --protocol and/or --run --core. "
            "Ruler: --group ruler. All 11: --group all.",
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
