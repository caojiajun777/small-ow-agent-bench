"""Target-band (8B/9B) unique-trap runs. Uses gitignored .env."""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

os.environ["PYTHONIOENCODING"] = "utf-8"

ROOT = Path(__file__).resolve().parents[1]
TASKS = ROOT / "tasks"
ENV = ROOT / ".env"

# Novita free tier: 5 concurrent sandboxes.
NOVITA_N = "5"

LOC_K3 = ("loc-bind-host", "loc-traceback-helper", "loc-reexport")
LOC_K1 = (
    "loc-member-discount",
    "loc-vip-two-files",
    "loc-similar-filenames",
    "loc-failing-test-impl",
    "loc-unused-fix",
)

# v1 unique-trap public set minus loc (already calibrated).
REST = (
    "edit-slugify",
    "edit-covered-length",
    "edit-deep-merge",
    "edit-int-list",
    "edit-top-k",
    "edit-jsonl-keep",
    "edit-hhmmss",
    "edit-prefix-sums",
    "edit-clip",
    "edit-timeout-zero",
    "edit-unique-keep",
    "edit-pad-left",
    "testgen-clip",
    "testgen-unique-order",
    "testgen-gregorian",
    "testgen-mean",
    "testgen-parse",
    "testgen-anagram",
    "testgen-timeout-zero",
    "testgen-greet-none",
    "testgen-cents",
    "testgen-window",
    "repro-off-by-one",
    "repro-end-exclusive",
    "repro-zero-timeout",
    "repro-keep-zero",
    "repro-none-name",
    "repro-float-cents",
    "repro-first-index",
    "repro-empty-mean",
    "repro-whitespace",
    "repro-truthy-flag",
    "review-clip-incomplete",
    "review-slug-almost",
    "review-mean-wrong",
    "review-slug-complete",
    "review-configured-timeout",
    "review-rotate-right",
    "review-prefix-complete",
)

MODELS = {
    "9b": "openrouter/qwen/qwen3.5-9b",
    "8b": "openrouter/mistralai/ministral-8b-2512",
}


def run_one(model: str, name: str, k: int, n: str = "1", environment: str | None = None) -> int:
    label = "9B" if "qwen3.5-9b" in model else "8B"
    print(f"===== {label} k={k} n={n} {name} =====", flush=True)
    cmd = [
        "harbor",
        "run",
        "--env-file",
        str(ENV),
        "-p",
        str(TASKS / name),
        "-a",
        "terminus-2",
        "-m",
        model,
        "-k",
        str(k),
        "-n",
        n,
    ]
    if environment:
        cmd.extend(["-e", environment])
    result = subprocess.run(cmd, check=False)
    print(f"exit {result.returncode} on {name}", flush=True)
    return result.returncode


def run_batch(
    model: str,
    names: tuple[str, ...],
    *,
    k: int,
    n: str,
    environment: str,
    label: str,
) -> int:
    missing = [name for name in names if not (TASKS / name / "task.toml").is_file()]
    if missing:
        print(f"missing tasks: {missing}", file=sys.stderr)
        return 2
    print(
        f"===== {label} k={k} n={n} env={environment} tasks={len(names)} =====",
        flush=True,
    )
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
        str(k),
        "-n",
        n,
        "-e",
        environment,
    ]
    for name in names:
        cmd.extend(["-i", name])
    result = subprocess.run(cmd, check=False)
    print(f"exit {result.returncode} on {label}", flush=True)
    return result.returncode


def main() -> int:
    if not ENV.is_file():
        print("missing .env with OPENROUTER_API_KEY and NOVITA_API_KEY", file=sys.stderr)
        return 2
    which = sys.argv[1] if len(sys.argv) > 1 else "9b-rest"
    code = 0
    if which == "9b-loc":
        model = MODELS["9b"]
        for name in LOC_K3:
            code = run_one(model, name, 3) or code
        for name in LOC_K1:
            code = run_one(model, name, 1) or code
    elif which == "8b-loc":
        model = MODELS["8b"]
        for name in LOC_K3:
            code = run_one(model, name, 3) or code
        for name in LOC_K1:
            code = run_one(model, name, 1) or code
    elif which == "9b-rest":
        code = run_batch(
            MODELS["9b"],
            REST,
            k=1,
            n=NOVITA_N,
            environment="novita",
            label="9b-rest",
        )
    elif which == "8b-rest":
        code = run_batch(
            MODELS["8b"],
            REST,
            k=1,
            n=NOVITA_N,
            environment="novita",
            label="8b-rest",
        )
    elif which == "rest":
        code = run_batch(
            MODELS["9b"],
            REST,
            k=1,
            n=NOVITA_N,
            environment="novita",
            label="9b-rest",
        )
        code = (
            run_batch(
                MODELS["8b"],
                REST,
                k=1,
                n=NOVITA_N,
                environment="novita",
                label="8b-rest",
            )
            or code
        )
    else:
        print(
            "usage: run_target_profile.py [9b-loc|8b-loc|9b-rest|8b-rest|rest]",
            file=sys.stderr,
        )
        return 2
    print(f"===== {which} DONE =====", flush=True)
    return code


if __name__ == "__main__":
    sys.exit(main())
