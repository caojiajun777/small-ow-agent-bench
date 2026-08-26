"""Gate A solvability: oracle=1, nop=0 on MAIN_47 + diagnostic.

Novita serial n=1. No compact-shell, no model. Do not start if another
Novita job is already running.

    python scripts/run_oracle_nop.py
    python scripts/run_oracle_nop.py --run
    python scripts/run_oracle_nop.py --run oracle
    python scripts/run_oracle_nop.py --run nop
    python scripts/run_oracle_nop.py --run --hard-dev
    python scripts/run_oracle_nop.py --run --hard-release
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from pathlib import Path

os.environ["PYTHONIOENCODING"] = "utf-8"

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from score_standard import format_report, score_job  # noqa: E402
from task_sets import DIAGNOSTIC, HARD_DEV_10, HARD_RELEASE_15, MAIN_47  # noqa: E402

TASKS = ROOT / "tasks"
ENV = ROOT / ".env"
JOBS = ROOT / "jobs"
GATE_TASKS = MAIN_47 + DIAGNOSTIC
REPRO_10 = tuple(name for name in MAIN_47 if name.startswith("repro-"))
RETRY_INCLUDE = (
    "BuildException",
    "EnvironmentStartTimeoutError",
    "RateLimitException",
)


def _env() -> dict[str, str]:
    return os.environ.copy()


def _cmd(agent: str, name: str) -> list[str]:
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
        agent,
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


def _run_task(agent: str, name: str) -> Path | None:
    known = _job_names()
    result = subprocess.run(_cmd(agent, name), cwd=str(ROOT), env=_env(), check=False)
    job = _newest(known)
    if job is None:
        print(f"no new job after {agent} {name} exit={result.returncode}", file=sys.stderr)
        return None
    report = score_job(job)
    (job / "standard-scores.json").write_text(
        json.dumps(report, indent=2) + "\n", encoding="utf-8"
    )
    print(format_report(report), flush=True)
    return job


def _write_summary(
    rows: list[dict],
    tasks: tuple[str, ...] = GATE_TASKS,
    out_name: str = "gate-a-oracle-nop.json",
) -> Path:
    expect = {"oracle": 1, "nop": 0}
    summary = {
        "kind": (
            "gate_a_hard_release_oracle_nop"
            if tasks == HARD_RELEASE_15
            else (
                "gate_a_hard_dev_oracle_nop"
                if tasks == HARD_DEV_10
                else (
                    "gate_a_repro_oracle_nop"
                    if tasks == REPRO_10
                    else "gate_a_oracle_nop"
                )
            )
        ),
        "n_tasks": len(tasks),
        "tasks": list(tasks),
        "rows": rows,
    }
    for agent, want in expect.items():
        agent_rows = [r for r in rows if r["agent"] == agent]
        bad = [
            r
            for r in agent_rows
            if r.get("termination") != "infra" and r.get("atomic_correct") != want
        ]
        missing = [n for n in tasks if n not in {r["task"] for r in agent_rows}]
        infra = [r for r in agent_rows if r.get("termination") == "infra"]
        summary[agent] = {
            "n": len(agent_rows),
            "n_ok": len(agent_rows) - len(bad) - len(infra),
            "n_bad": len(bad),
            "n_infra": len(infra),
            "missing": missing,
            "bad_tasks": [r["task"] for r in bad],
            "pass": not bad
            and not missing
            and not infra
            and len(agent_rows) == len(tasks),
        }
    out = JOBS / out_name
    out.write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    print(
        f"===== GATE A { {k: summary[k].get('pass') for k in expect} } =====\n"
        f"wrote {out}",
        flush=True,
    )
    return out


def main() -> int:
    repro = "--repro" in sys.argv
    hard_dev = "--hard-dev" in sys.argv
    hard_release = "--hard-release" in sys.argv
    if sum([repro, hard_dev, hard_release]) > 1:
        print("use only one of --repro / --hard-dev / --hard-release", file=sys.stderr)
        return 2
    if hard_release:
        names = HARD_RELEASE_15
        out_name = "gate-a-hard-release-oracle-nop.json"
        label = "Hard-Release-15"
    elif hard_dev:
        names = HARD_DEV_10
        out_name = "gate-a-hard-dev-oracle-nop.json"
        label = "Hard-Dev-10"
    elif repro:
        names = REPRO_10
        out_name = "gate-a-repro-oracle-nop.json"
        label = "Repro-10"
    else:
        names = GATE_TASKS
        out_name = "gate-a-oracle-nop.json"
        label = "Gate A"
    print(f"{label} oracle/nop Novita n=1 tasks={len(names)}")
    if "--run" not in sys.argv:
        print(
            "dry-run; pass --run [oracle|nop] [--repro|--hard-dev|--hard-release]. "
            "Default: oracle then nop."
        )
        print(" ", " ".join(_cmd("oracle", names[0])))
        return 0
    args = [
        a
        for a in sys.argv[1:]
        if a not in {"--run", "--repro", "--hard-dev", "--hard-release"}
    ]
    if args and args[0] not in {"oracle", "nop"}:
        print(
            "usage: python scripts/run_oracle_nop.py --run [oracle|nop] "
            "[--repro|--hard-dev|--hard-release]",
            file=sys.stderr,
        )
        return 2
    agents = (args[0],) if args else ("oracle", "nop")
    if not ENV.is_file():
        print("missing .env", file=sys.stderr)
        return 2
    missing = [n for n in names if not (TASKS / n / "task.toml").is_file()]
    if missing:
        print(f"missing tasks: {missing}", file=sys.stderr)
        return 2
    restore = _prevent_sleep()
    rows: list[dict] = []
    code = 0
    try:
        print("wait 8s before first sandbox create", flush=True)
        time.sleep(8)
        for agent in agents:
            want = 1 if agent == "oracle" else 0
            for name in names:
                print(f"===== {agent} {name} =====", flush=True)
                job = _run_task(agent, name)
                if job is None:
                    code = 2
                    continue
                report = json.loads(
                    (job / "standard-scores.json").read_text(encoding="utf-8")
                )
                if _all_infra(report):
                    print(f"{name}: infra, wait 60s and retry once", flush=True)
                    time.sleep(60)
                    job = _run_task(agent, name) or job
                    report = json.loads(
                        (job / "standard-scores.json").read_text(encoding="utf-8")
                    )
                    if _all_infra(report):
                        code = 1
                trial = (report.get("trials") or [{}])[0]
                atomic = trial.get("atomic_correct")
                term = trial.get("termination")
                rows.append(
                    {
                        "agent": agent,
                        "task": name,
                        "atomic_correct": atomic,
                        "termination": term,
                        "job": str(job),
                    }
                )
                if term != "infra" and atomic != want:
                    print(
                        f"FAIL {agent} {name} atomic={atomic} want={want}",
                        file=sys.stderr,
                    )
                    code = 1
                _write_summary(rows, tasks=names, out_name=out_name)
                time.sleep(8)
    finally:
        restore()
        if rows:
            _write_summary(rows, tasks=names, out_name=out_name)
    return code


if __name__ == "__main__":
    sys.exit(main())
