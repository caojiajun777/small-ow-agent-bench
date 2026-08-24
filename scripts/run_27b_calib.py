"""Ceiling calibration shots (DashScope Qwen3.5-27B, thinking off)."""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

os.environ["PYTHONIOENCODING"] = "utf-8"

BENCH = Path(__file__).resolve().parents[1]
ROOT = BENCH / "tasks"
ENV = BENCH / ".env"
MODEL = "dashscope/qwen3.5-27b"
AK = 'llm_call_kwargs={"extra_body":{"enable_thinking":false}}'
DEFAULT_TASKS = ("testgen-gregorian",)


def run_batch(names: tuple[str, ...], k: int, n: int) -> int:
    print(f"===== 27B k={k} n={n} tasks={list(names)} =====", flush=True)
    cmd = [
        "harbor",
        "run",
        "--env-file",
        str(ENV),
        "-p",
        str(ROOT),
        "-a",
        "terminus-2",
        "-m",
        MODEL,
        "--ak",
        AK,
        "-k",
        str(k),
        "-n",
        str(n),
        "-e",
        "novita",
    ]
    for name in names:
        cmd.extend(["-i", name])
    result = subprocess.run(cmd, check=False)
    print(f"exit {result.returncode}", flush=True)
    return result.returncode


def run_one(name: str, k: int = 1, force_build: bool = False) -> int:
    print(f"===== 27B k={k} {name} =====", flush=True)
    cmd = [
        "harbor",
        "run",
        "--env-file",
        str(ENV),
        "-p",
        str(ROOT / name),
        "-a",
        "terminus-2",
        "-m",
        MODEL,
        "--ak",
        AK,
        "-k",
        str(k),
        "-n",
        "1",
        "-e",
        "novita",
    ]
    if force_build:
        cmd.append("--force-build")
    result = subprocess.run(cmd, check=False)
    print(f"exit {result.returncode} on {name}", flush=True)
    return result.returncode


def main() -> int:
    args = list(sys.argv[1:])
    if args and args[0] == "k3":
        names = tuple(args[1:]) or (
            "loc-traceback-helper",
            "loc-reexport",
        )
        # Serial n=1: concurrent Novita template builds raced (5/6 BuildException).
        code = 0
        for i, name in enumerate(names):
            code = run_one(name, k=3, force_build=True) or code
    else:
        tasks = tuple(args) if args else DEFAULT_TASKS
        code = 0
        for name in tasks:
            code = run_one(name) or code
    print("===== 27B CALIB DONE =====", flush=True)
    return code


if __name__ == "__main__":
    sys.exit(main())
