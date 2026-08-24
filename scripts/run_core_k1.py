"""Draft k=1 screen: Qwen3.5-9B and Ministral-8B only.

Official frozen roster is models.lock.yaml via scripts/run_locked.py.
Do not use this script to pick wave2 models.

    python scripts/run_core_k1.py
    python scripts/run_core_k1.py --run
    python scripts/run_core_k1.py --run openrouter/qwen/qwen3.5-9b
    python scripts/run_core_k1.py --run --repro
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from collections import defaultdict
from pathlib import Path

os.environ["PYTHONIOENCODING"] = "utf-8"

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from score_standard import ATOMS, atom_of, format_report, score_job  # noqa: E402
from task_sets import MAIN_47  # noqa: E402

TASKS = ROOT / "tasks"
ENV = ROOT / ".env"
JOBS = ROOT / "jobs"
AGENT = "agents.compact_shell:CompactShellAgent"
AK_THINKING_OFF = 'llm_call_kwargs={"extra_body":{"enable_thinking":false}}'
REPRO_10 = tuple(name for name in MAIN_47 if name.startswith("repro-"))
SCREEN = JOBS / "core-k1-screen.json"

DEFAULT_MODELS = (
    "openrouter/qwen/qwen3.5-9b",
    "openrouter/mistralai/ministral-8b-2512",
)

RETRY_INCLUDE = (
    "BuildException",
    "EnvironmentStartTimeoutError",
    "RateLimitException",
)


def _env() -> dict[str, str]:
    env = os.environ.copy()
    env["PYTHONPATH"] = str(ROOT) + os.pathsep + env.get("PYTHONPATH", "")
    return env


def _cmd(model: str, name: str) -> list[str]:
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
    if "qwen" in model.lower():
        cmd.extend(["--ak", AK_THINKING_OFF])
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


def _run_task(model: str, name: str) -> Path | None:
    known = _job_names()
    result = subprocess.run(_cmd(model, name), cwd=str(ROOT), env=_env(), check=False)
    job = _newest(known)
    if job is None:
        print(f"no new job after {name} exit={result.returncode}", file=sys.stderr)
        return None
    report = score_job(job)
    (job / "standard-scores.json").write_text(
        json.dumps(report, indent=2) + "\n", encoding="utf-8"
    )
    print(format_report(report), flush=True)
    return job


def _rows_from_screen(path: Path) -> list[dict]:
    if not path.is_file():
        return []
    data = json.loads(path.read_text(encoding="utf-8"))
    rows: list[dict] = []
    for item in data.get("items") or []:
        task = item.get("task")
        if not task:
            continue
        for model, rec in (item.get("by_model") or {}).items():
            if not rec:
                continue
            rows.append(
                {
                    "model": model,
                    "task": task,
                    "atom": item.get("atom") or atom_of(task),
                    "atomic_correct": rec.get("atomic_correct"),
                    "termination": rec.get("termination"),
                    "job": rec.get("job"),
                }
            )
    return rows


def _upsert_row(rows: list[dict], row: dict) -> None:
    for i, existing in enumerate(rows):
        if existing["model"] == row["model"] and existing["task"] == row["task"]:
            rows[i] = row
            return
    rows.append(row)


def _short_model(model: str) -> str:
    return model.rsplit("/", 1)[-1]


def _write_discrimination(rows: list[dict]) -> Path:
    by_task: dict[str, dict[str, dict]] = defaultdict(dict)
    for row in rows:
        by_task[row["task"]][row["model"]] = row

    models = list(dict.fromkeys(r["model"] for r in rows))
    items = []
    for task in MAIN_47:
        scores = by_task.get(task) or {}
        entry = {
            "task": task,
            "atom": atom_of(task),
            "by_model": {
                model: {
                    "atomic_correct": (scores[model] or {}).get("atomic_correct"),
                    "termination": (scores[model] or {}).get("termination"),
                    "job": (scores[model] or {}).get("job"),
                }
                if model in scores
                else None
                for model in models
            },
        }
        vals = [
            scores[m]["atomic_correct"]
            for m in models
            if m in scores and scores[m].get("atomic_correct") is not None
        ]
        if len(vals) >= 2 and len(set(vals)) > 1:
            entry["role"] = "discriminator"
        elif vals and all(v == 1 for v in vals):
            entry["role"] = "smoke"
        elif vals and all(v == 0 for v in vals):
            entry["role"] = "both_miss"
        else:
            entry["role"] = "incomplete"
        items.append(entry)

    skill: dict[str, dict[str, float | None]] = {}
    for prefix, label in ATOMS.items():
        skill[label] = {}
        for model in models:
            vals = [
                r["atomic_correct"]
                for r in rows
                if r["model"] == model
                and r["atom"] == prefix
                and r.get("atomic_correct") is not None
                and r.get("termination") != "infra"
            ]
            skill[label][_short_model(model)] = (
                sum(vals) / len(vals) if vals else None
            )

    report = {
        "kind": "core_k1_screen",
        "published": False,
        "models": models,
        "n_tasks": len(MAIN_47),
        "skill_means": skill,
        "n_discriminator": sum(1 for i in items if i["role"] == "discriminator"),
        "n_smoke": sum(1 for i in items if i["role"] == "smoke"),
        "n_both_miss": sum(1 for i in items if i["role"] == "both_miss"),
        "n_incomplete": sum(1 for i in items if i["role"] == "incomplete"),
        "items": items,
    }
    out = JOBS / "core-k1-screen.json"
    out.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(
        "===== CORE k=1 SCREEN =====\n"
        f"discriminator {report['n_discriminator']}  "
        f"smoke {report['n_smoke']}  "
        f"both_miss {report['n_both_miss']}  "
        f"incomplete {report['n_incomplete']}\n"
        f"skill means {json.dumps(skill, indent=2)}\n"
        f"wrote {out}",
        flush=True,
    )
    return out


def main() -> int:
    repro = "--repro" in sys.argv
    names = REPRO_10 if repro else MAIN_47
    print(
        f"Core k=1 screen compact-shell Novita n=1 "
        f"tasks={len(names)}{' (repro patch)' if repro else ''}"
    )
    print("Draft only. Not Frontier/Hard. Not the published k=3 table.")
    if "--run" not in sys.argv:
        print("dry-run; pass --run [model ...] [--repro]. Default models:")
        for model in DEFAULT_MODELS:
            print(" ", model)
        print(" ", " ".join(_cmd(DEFAULT_MODELS[0], names[0])))
        return 0
    args = [a for a in sys.argv[1:] if a not in {"--run", "--repro"}]
    models = tuple(args) if args else DEFAULT_MODELS
    if not ENV.is_file():
        print("missing .env", file=sys.stderr)
        return 2
    missing = [n for n in names if not (TASKS / n / "task.toml").is_file()]
    if missing:
        print(f"missing tasks: {missing}", file=sys.stderr)
        return 2
    restore = _prevent_sleep()
    rows = _rows_from_screen(SCREEN) if repro else []
    code = 0
    try:
        print("wait 8s before first sandbox create", flush=True)
        time.sleep(8)
        for model in models:
            for name in names:
                print(f"===== core-k1 {name} {model} =====", flush=True)
                job = _run_task(model, name)
                if job is None:
                    code = 2
                    continue
                report = json.loads(
                    (job / "standard-scores.json").read_text(encoding="utf-8")
                )
                if _all_infra(report):
                    print(f"{name}: infra, wait 60s and retry once", flush=True)
                    time.sleep(60)
                    job = _run_task(model, name) or job
                    report = json.loads(
                        (job / "standard-scores.json").read_text(encoding="utf-8")
                    )
                    if _all_infra(report):
                        code = 1
                trial = (report.get("trials") or [{}])[0]
                _upsert_row(
                    rows,
                    {
                        "model": model,
                        "task": name,
                        "atom": atom_of(name),
                        "atomic_correct": trial.get("atomic_correct"),
                        "termination": trial.get("termination"),
                        "job": str(job),
                    },
                )
                _write_discrimination(rows)
                time.sleep(8)
    finally:
        restore()
        if rows:
            _write_discrimination(rows)
    return code


if __name__ == "__main__":
    sys.exit(main())
