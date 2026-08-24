"""10-task harness A/B. Does not start until --run.

    python scripts/run_ablation.py
    python scripts/run_ablation.py --run openrouter/qwen/qwen3.5-9b
    python scripts/run_ablation.py --run openrouter/qwen/qwen3.5-9b --env docker
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
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

# One unique-trap Medium per atom, plus a second for loc/edit.
ABLATION = (
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


def _parse_argv(argv: list[str]) -> tuple[bool, str | None, str]:
    run = "--run" in argv
    env_name = "docker"
    model: str | None = None
    args = [a for a in argv if a not in {"--run", "--env"}]
    if "--env" in argv:
        idx = argv.index("--env")
        if idx + 1 >= len(argv):
            raise SystemExit("usage: --env docker|novita")
        env_name = argv[idx + 1]
        args = [a for a in args if a != env_name]
    if run:
        if not args:
            raise SystemExit(
                "usage: python scripts/run_ablation.py --run <model> [--env docker|novita]"
            )
        model = args[0]
    return run, model, env_name


def _env() -> dict[str, str]:
    env = os.environ.copy()
    env["PYTHONPATH"] = str(ROOT) + os.pathsep + env.get("PYTHONPATH", "")
    return env


def _cmd(agent: str, model: str, env_name: str) -> list[str]:
    cmd = [
        "harbor",
        "run",
        "--env-file",
        str(ENV),
        "-o",
        str(JOBS),
        "-p",
        str(TASKS),
        "-a",
        agent,
        "-m",
        model,
        "-k",
        "1",
        "-n",
        "1",
        "-e",
        env_name,
        "-r",
        "3",
    ]
    for exc in RETRY_INCLUDE:
        cmd.extend(["--retry-include", exc])
    if "qwen" in model.lower():
        cmd.extend(["--ak", AK_THINKING_OFF])
    for name in ABLATION:
        cmd.extend(["-i", name])
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


def main() -> int:
    run, model, env_name = _parse_argv(sys.argv[1:])
    print(
        f"ablation tasks={len(ABLATION)} terminus-2 vs compact-shell env={env_name}"
    )
    if not run:
        placeholder = "openrouter/MODEL"
        print("dry-run; pass --run <model> [--env docker|novita].")
        print(" ", " ".join(_cmd("terminus-2", placeholder, env_name)))
        print(" ", " ".join(_cmd(AGENT, placeholder, env_name)))
        return 0
    assert model is not None
    if not ENV.is_file():
        print("missing .env", file=sys.stderr)
        return 2
    missing = [n for n in ABLATION if not (TASKS / n / "task.toml").is_file()]
    if missing:
        print(f"missing tasks: {missing}", file=sys.stderr)
        return 2
    restore = _prevent_sleep()
    code = 0
    summary: list[tuple[str, Path]] = []
    try:
        for agent in ("terminus-2", AGENT):
            known = _job_names()
            print(f"===== {agent} {model} env={env_name} =====", flush=True)
            result = subprocess.run(
                _cmd(agent, model, env_name),
                cwd=str(ROOT),
                env=_env(),
                check=False,
            )
            code = result.returncode or code
            job = _newest(known)
            if job is None:
                print(f"no new job after {agent}", file=sys.stderr)
                return 2
            report = score_job(job)
            out = job / "standard-scores.json"
            out.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
            print(format_report(report), flush=True)
            summary.append((agent, job))
    finally:
        restore()
    print("===== ABLATION JOBS =====")
    for agent, job in summary:
        print(f"  {agent}: {job}")
    return code


if __name__ == "__main__":
    sys.exit(main())
