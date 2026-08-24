"""Run compact-shell on Novita. Not Terminus-2.

    python scripts/run_compact.py
    python scripts/run_compact.py --run openrouter/qwen/qwen3.5-9b
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

TASKS = ROOT / "tasks"
ENV = ROOT / ".env"
JOBS = ROOT / "jobs"
AGENT = "agents.compact_shell:CompactShellAgent"
AK_THINKING_OFF = 'llm_call_kwargs={"extra_body":{"enable_thinking":false}}'

# Same 10 unique-trap Medium slice used to validate the harness.
SLICE = (
    "loc-member-discount",
    "loc-bind-host",
    "edit-slugify",
    "edit-pad-left",
    "testgen-clip",
    "testgen-gregorian",
    "repro-off-by-one",
    "repro-whitespace",
    "review-clip-incomplete",
    "review-slug-complete",
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


def main() -> int:
    print(f"compact-shell Novita n=1 tasks={len(SLICE)}")
    if "--run" not in sys.argv:
        model = "openrouter/MODEL"
        print("dry-run; pass --run <model>. Does not start Terminus-2.")
        print(" ", " ".join(_cmd(model, SLICE[0])))
        return 0
    args = [a for a in sys.argv[1:] if a != "--run"]
    if not args:
        print("usage: python scripts/run_compact.py --run <model>", file=sys.stderr)
        return 2
    if not ENV.is_file():
        print("missing .env", file=sys.stderr)
        return 2
    missing = [n for n in SLICE if not (TASKS / n / "task.toml").is_file()]
    if missing:
        print(f"missing tasks: {missing}", file=sys.stderr)
        return 2
    model = args[0]
    restore = _prevent_sleep()
    jobs: list[tuple[str, Path]] = []
    code = 0
    try:
        print("wait 8s after sandbox cleanup", flush=True)
        time.sleep(8)
        for name in SLICE:
            print(f"===== compact-shell {name} {model} =====", flush=True)
            job = _run_task(model, name)
            if job is None:
                code = 2
                continue
            report = json.loads((job / "standard-scores.json").read_text(encoding="utf-8"))
            if _all_infra(report):
                print(f"{name}: infra, wait 60s and retry once", flush=True)
                time.sleep(60)
                job = _run_task(model, name) or job
                report = json.loads((job / "standard-scores.json").read_text(encoding="utf-8"))
                if _all_infra(report):
                    code = 1
            jobs.append((name, job))
            time.sleep(8)
    finally:
        restore()
    print("===== COMPACT-SHELL JOBS =====")
    for name, job in jobs:
        print(f"  {name}: {job}")
    return code


if __name__ == "__main__":
    sys.exit(main())
