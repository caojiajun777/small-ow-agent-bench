"""PILOT ONLY. Not the Standard Track table.

See STANDARD.md: old OpenRouter / n=4|5 / k=1 jobs stay calibration.
Do not mix results into the published leaderboard.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

os.environ["PYTHONIOENCODING"] = "utf-8"

ROOT = Path(__file__).resolve().parents[1]
TASKS = ROOT / "tasks"
ENV = ROOT / ".env"
sys.path.insert(0, str(Path(__file__).resolve().parent))
from classify_timeouts import classify_job, format_report, summarize  # noqa: E402
from task_sets import MAIN_47  # noqa: E402

NOVITA_N = "4"  # pilot only; Standard Track is n=1 (see STANDARD.md)

THINKING_OFF = {
    "openrouter/qwen/qwen3-8b",
    "openrouter/qwen/qwen3-14b",
}
AK_THINKING_OFF = 'llm_call_kwargs={"extra_body":{"enable_thinking":false}}'

UNIQUE = MAIN_47

# Already finished unique-trap on this harness.
DONE = {
    "openrouter/qwen/qwen3.5-9b",
    "openrouter/mistralai/ministral-8b-2512",
    "openrouter/ibm-granite/granite-4.1-8b",
}

# Dense / advertised <=14B, chat+agent, OpenRouter, not RP/guard/translate/UI.
# 27B+ and 30B-A3B weights stay off this list (not laptop-small).
MODELS: list[tuple[str, str]] = [
    # 7B-9B, other families / previous Qwen
    ("granite-8b", "openrouter/ibm-granite/granite-4.1-8b"),
    ("qwen3-8b", "openrouter/qwen/qwen3-8b"),
    ("llama31-8b", "openrouter/meta-llama/llama-3.1-8b-instruct"),
    ("qwen25-7b", "openrouter/qwen/qwen-2.5-7b-instruct"),
    ("command-r7b", "openrouter/cohere/command-r7b-12-2024"),
    ("ministral-8b-v1", "openrouter/mistralai/ministral-8b"),
    # 3B-4B floor
    ("ministral-3b", "openrouter/mistralai/ministral-3b-2512"),
    ("granite-micro", "openrouter/ibm-granite/granite-4.0-h-micro"),
    ("llama32-3b", "openrouter/meta-llama/llama-3.2-3b-instruct"),
    ("gemma3-4b", "openrouter/google/gemma-3-4b-it"),
    ("gemma3n-e4b", "openrouter/google/gemma-3n-e4b-it"),
    # Upper small (12B-14B)
    ("mistral-nemo", "openrouter/mistralai/mistral-nemo"),
    ("gemma3-12b", "openrouter/google/gemma-3-12b-it"),
    ("qwen3-14b", "openrouter/qwen/qwen3-14b"),
    ("ministral-14b", "openrouter/mistralai/ministral-14b-2512"),
    # Free endpoint last: rate limits stall the paid queue if placed early
    ("nemotron-9b", "openrouter/nvidia/nemotron-nano-9b-v2:free"),
]


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


def _newest_job() -> Path | None:
    jobs = ROOT / "jobs"
    if not jobs.is_dir():
        return None
    dirs = [p for p in jobs.iterdir() if p.is_dir() and p.name[:2] == "20"]
    if not dirs:
        return None
    return max(dirs, key=lambda p: p.name)


def _harbor_cmd(model: str, names: tuple[str, ...], n: str) -> list[str]:
    cmd = [
        "harbor",
        "run",
        "--env-file",
        str(ENV),
        "-p",
        str(TASKS),
        "-a",
        "terminus-2",
        "-m",
        model,
        "-k",
        "1",
        "-n",
        n,
        "-e",
        "novita",
        "--max-retries",
        "1",
        "--retry-include",
        "BuildException",
    ]
    if model in THINKING_OFF:
        cmd.extend(["--ak", AK_THINKING_OFF])
    for name in names:
        cmd.extend(["-i", name])
    return cmd


def _classify_and_rerun_stalls(label: str, model: str) -> int:
    job = _newest_job()
    if job is None:
        print(f"no job dir after {label}", file=sys.stderr)
        return 2
    rows = classify_job(job)
    print(format_report(job, rows), flush=True)
    stalls = summarize(rows)["stall_tasks"]
    if not stalls:
        return 0
    print(f"===== {label} stall rerun n=1 tasks={stalls} =====", flush=True)
    result = subprocess.run(_harbor_cmd(model, tuple(stalls), "1"), check=False)
    print(f"exit {result.returncode} on {label} stall-rerun", flush=True)
    rerun = _newest_job()
    if rerun is not None:
        print(format_report(rerun, classify_job(rerun)), flush=True)
    return result.returncode


def run_model(label: str, model: str) -> int:
    missing = [name for name in UNIQUE if not (TASKS / name / "task.toml").is_file()]
    if missing:
        print(f"missing tasks: {missing}", file=sys.stderr)
        return 2
    print(
        f"===== {label} {model} k=1 n={NOVITA_N} tasks={len(UNIQUE)} =====",
        flush=True,
    )
    result = subprocess.run(_harbor_cmd(model, UNIQUE, NOVITA_N), check=False)
    print(f"exit {result.returncode} on {label}", flush=True)
    rerun = _classify_and_rerun_stalls(label, model)
    return result.returncode or rerun


def main() -> int:
    if not ENV.is_file():
        print("missing .env", file=sys.stderr)
        return 2
    restore_sleep = _prevent_sleep()
    try:
        print(
            "keep-awake on; n=4; retry BuildException once; "
            "Qwen3 thinking off; stall timeouts rerun once; do not close the lid",
            flush=True,
        )
        want = set(sys.argv[1:]) if len(sys.argv) > 1 else None
        code = 0
        for label, model in MODELS:
            if want and label not in want and model not in want:
                continue
            if model in DONE and not want:
                print(f"skip {label} (already on unique-trap)", flush=True)
                continue
            code = run_model(label, model) or code
        print("===== SMALL LEADERBOARD DONE =====", flush=True)
        return code
    finally:
        restore_sleep()


if __name__ == "__main__":
    sys.exit(main())
