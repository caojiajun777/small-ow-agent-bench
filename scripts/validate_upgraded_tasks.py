"""Offline reference/empty-submission checks for the redesigned 62 tasks.

This executes only trusted repository fixtures and reference solutions. It is
NOT a security sandbox for arbitrary model submissions, does not invoke Harbor,
does not use model APIs, and is not a substitute for a Linux container gate.
Every case receives an independent temporary application and private verifier.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
import xml.etree.ElementTree as ET
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

from task_sets import HARD_RELEASE_15, MAIN_47

ROOT = Path(__file__).resolve().parents[1]
BANK_62 = (*MAIN_47, *HARD_RELEASE_15)
IGNORED = {"__pycache__", ".pytest_cache", ".git", ".ruff_cache"}


def task_digest(task_dir: Path) -> str:
    """Portable content hash: UTF-8 text uses LF; binary bytes are unchanged."""
    digest = hashlib.sha256()
    for path in sorted(task_dir.rglob("*")):
        if not path.is_file() or IGNORED.intersection(path.relative_to(task_dir).parts):
            continue
        if path.suffix in {".pyc", ".pyo"}:
            continue
        digest.update(path.relative_to(task_dir).as_posix().encode("utf-8") + b"\0")
        data = path.read_bytes()
        try:
            if b"\0" not in data:
                data = data.decode("utf-8").replace("\r\n", "\n").encode("utf-8")
        except UnicodeDecodeError:
            pass
        digest.update(data + b"\0")
    return digest.hexdigest()


def _copy_tree(source: Path, destination: Path) -> None:
    shutil.copytree(source, destination, ignore=shutil.ignore_patterns(*IGNORED, "*.pyc", "*.pyo"))


def _junit(path: Path) -> dict:
    if not path.is_file():
        return {"tests": 0, "failures": 0, "errors": 1, "skipped": 0}
    root = ET.parse(path).getroot()
    suites = [root] if root.tag == "testsuite" else list(root.findall("testsuite"))
    return {name: sum(int(s.get(name, 0)) for s in suites)
            for name in ("tests", "failures", "errors", "skipped")}


def validate_case(task: str, mode: str, *, timeout: float = 300) -> dict:
    if task not in BANK_62 or mode not in {"oracle", "nop"}:
        raise ValueError("Only the explicit redesigned bank and oracle/nop cases are supported")
    task_dir = ROOT / "tasks" / task
    before = task_digest(task_dir)
    started = time.monotonic()
    row = {"task": task, "mode": mode, "task_sha256": before,
           "model_calls": 0, "sandbox_creates": 0, "ok": False}
    temporary_root = ROOT.parent / ".task-upgrade-local"
    temporary_root.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="small-ow-task-check-", dir=temporary_root) as raw:
        temporary = Path(raw).resolve()
        app = temporary / "app"
        app.mkdir()
        repo = app / "repo"
        private_tests = temporary / "private-tests"
        solution = temporary / "private-solution"
        runtime_temp = temporary / "runtime-temp"
        runtime_temp.mkdir()
        _copy_tree(task_dir / "environment" / "repo", repo)
        _copy_tree(task_dir / "tests", private_tests)
        _copy_tree(task_dir / "solution", solution)
        env = os.environ.copy()
        # Do not forward unrelated API credentials to reference fixture processes.
        for name in list(env):
            if any(marker in name.upper() for marker in ("API_KEY", "ACCESS_TOKEN", "SECRET_KEY")):
                env.pop(name, None)
        env.update({"BENCH_REPO_ROOT": str(repo), "BENCH_APP_ROOT": str(app),
                    "BENCH_TESTS_ROOT": str(private_tests),
                    "BENCH_VERDICT_DIR": str(temporary / "verdict"),
                    "PYTHONPATH": os.pathsep.join((str(repo), str(private_tests))),
                    "TEMP": str(runtime_temp), "TMP": str(runtime_temp), "TMPDIR": str(runtime_temp),
                    "PYTHONDONTWRITEBYTECODE": "1", "PYTHONNOUSERSITE": "1",
                    "PYTHONIOENCODING": "utf-8", "PYTHONUTF8": "1",
                    "PYTEST_DISABLE_PLUGIN_AUTOLOAD": "1"})
        try:
            if mode == "oracle":
                oracle = subprocess.run([sys.executable, "-B", str(solution / "oracle.py")],
                                        cwd=repo, env=env, capture_output=True, text=True,
                                        encoding="utf-8", errors="replace", timeout=timeout)
                row["oracle_returncode"] = oracle.returncode
                if oracle.returncode:
                    row["error"] = "reference_solution_failed"
                    row["output"] = (oracle.stdout + oracle.stderr)[-16000:]
                    return row
            junit = temporary / "verifier.xml"
            controller = private_tests / "verdict_v2.py"
            command = ([sys.executable, "-B", str(controller), "--tests-root", str(private_tests)]
                       if controller.is_file() else [sys.executable, "-B", "-m", "pytest",
                                   str(private_tests / "test_state.py"), "-q", "--tb=short",
                                   f"--basetemp={temporary / 'pytest-temp'}",
                                   "-p", "no:cacheprovider", f"--junitxml={junit}"])
            proc = subprocess.run(command,
                                  cwd=repo, env=env, capture_output=True, text=True,
                                  encoding="utf-8", errors="replace", timeout=timeout)
            if controller.is_file():
                verdict = json.loads((temporary / "verdict" / "verdict.json").read_text(encoding="utf-8"))
                reports = verdict.get("checks", {}).get("reports", [])
                counts = {"tests": verdict.get("checks", {}).get("collected", 0),
                          "failures": sum(row.get("outcome") == "failed" for row in reports),
                          "errors": int(verdict.get("status") == "error"),
                          "skipped": sum(row.get("outcome") == "skipped" for row in reports)}
                row.update(verdict=verdict, controller_validated=True)
                reward = (temporary / "verdict" / "reward.txt")
                expected = "1" if mode == "oracle" else "0"
                row["reward_consistent"] = reward.is_file() and reward.read_text(encoding="utf-8").strip() == expected
            else:
                counts = _junit(junit)
            row.update({"returncode": proc.returncode, "junit": counts})
            completed = counts["tests"] > 0 and counts["errors"] == 0 and counts["skipped"] == 0
            row["ok"] = completed and ((mode == "oracle" and proc.returncode == 0 and
                                        counts["failures"] == 0) or
                                       (mode == "nop" and proc.returncode == 1 and
                                        counts["failures"] > 0))
            if controller.is_file():
                row["ok"] = row["ok"] and row["reward_consistent"]
            if not row["ok"]:
                row["output"] = (proc.stdout + proc.stderr)[-16000:]
        except subprocess.TimeoutExpired:
            row["error"] = "local_validation_timeout"
        except (OSError, ET.ParseError, ValueError) as exc:
            row["error"] = f"{type(exc).__name__}: {exc}"
        finally:
            row["elapsed_sec"] = round(time.monotonic() - started, 3)
            row["source_unchanged"] = before == task_digest(task_dir)
            row["ok"] = row["ok"] and row["source_unchanged"]
    return row


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--tasks", nargs="+", choices=BANK_62)
    parser.add_argument("--skill", choices=("loc", "edit", "testgen", "repro", "review"))
    parser.add_argument("--mode", choices=("both", "oracle", "nop"), default="both")
    parser.add_argument("--workers", type=int, default=2)
    parser.add_argument("--timeout", type=float, default=300)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    if not 1 <= args.workers <= 4 or args.timeout <= 0:
        parser.error("workers must be 1..4 and timeout must be positive")
    tasks = [task for task in (args.tasks or BANK_62)
             if args.skill is None or task.startswith(args.skill + "-")]
    if not tasks:
        parser.error("empty task selection")
    modes = ("nop", "oracle") if args.mode == "both" else (args.mode,)
    rows = []
    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        futures = [pool.submit(validate_case, task, mode, timeout=args.timeout)
                   for task in tasks for mode in modes]
        for future in as_completed(futures):
            row = future.result()
            rows.append(row)
            # Full structured evidence belongs in the report, not thousands of
            # lines of terminal output. Failure tails remain available there.
            print(json.dumps({key: value for key, value in row.items()
                              if key not in {"verdict", "output"}}, ensure_ascii=False), flush=True)
    rows.sort(key=lambda row: (BANK_62.index(row["task"]), row["mode"]))
    report = {"schema_version": 1, "scope": "offline trusted reference validation",
              "container_validated": False, "model_calls": 0, "sandbox_creates": 0,
              "cases": len(rows), "passed": sum(row["ok"] for row in rows),
              "all_passed": all(row["ok"] for row in rows), "rows": rows}
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({key: value for key, value in report.items() if key != "rows"},
                     ensure_ascii=False), flush=True)
    return 0 if report["all_passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
