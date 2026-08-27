"""Score a Harbor job under STANDARD.md orthogonal fields.

    python scripts/score_standard.py jobs/<job>
    python scripts/score_standard.py jobs/<job> --require-oracle
    python scripts/score_standard.py jobs/<job> --require-nop
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))
from classify_timeouts import (  # noqa: E402
    _exception_type,
    _reward,
    load_trials,
    task_name_from_trial,
)
from task_sets import DIAGNOSTIC, MAIN_47  # noqa: E402

RATE_LIMIT_EXCEPTIONS = frozenset(
    {
        "RateLimitException",
        "RateLimitError",
    }
)
# Transient API flake (not model output). OutputLengthExceeded stays protocol_error.
API_FLAKE_EXCEPTIONS = frozenset(
    {
        "ConnectError",
        "APIConnectionError",
        "ServiceUnavailableError",
        "ServiceUnavailable",
        "InternalServerError",
        "AuthenticationError",
    }
)
INFRA_EXCEPTIONS = frozenset(
    {
        "BuildException",
        "EnvironmentStartTimeoutError",
        "EnvironmentStartError",
        "CancelledError",
        "RewardFileNotFoundError",
        "RewardFileEmptyError",
        "VerifierOutputParseError",
        "ReadError",
        *RATE_LIMIT_EXCEPTIONS,
        *API_FLAKE_EXCEPTIONS,
    }
)

ATOMS = {
    "loc": "Localization",
    "edit": "Editing",
    "testgen": "Testgen",
    "repro": "Repro",
    "review": "Review",
}


def atom_of(task: str) -> str:
    for prefix in ATOMS:
        if task.startswith(f"{prefix}-"):
            return prefix
    return "other"


def _compact_shell_trace(data: dict[str, Any], trial_dir: Path | None = None) -> dict[str, Any]:
    meta = dict((data.get("agent_result") or {}).get("metadata") or {})
    if trial_dir is None:
        return meta
    for path in (
        trial_dir / "agent" / "compact-shell.json",
        trial_dir / "compact-shell.json",
    ):
        if not path.is_file():
            continue
        try:
            blob = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError, json.JSONDecodeError):
            break
        if isinstance(blob, dict):
            for key in ("finished", "n_turns", "n_shell", "n_parse_fail"):
                if key in blob:
                    meta[key] = blob[key]
        break
    return meta


def _exception_message(data: dict[str, Any]) -> str | None:
    info = data.get("exception_info") or {}
    msg = info.get("exception_message")
    return msg if isinstance(msg, str) else None


def is_rate_limit(exc: str | None, message: str | None = None) -> bool:
    """True for Harbor/LiteLLM 429. OutputLengthExceeded is not rate-limit."""
    if exc in RATE_LIMIT_EXCEPTIONS:
        return True
    if exc == "APIStatusError" and message:
        text = message.lower()
        if "429" in message or "rate limit" in text or "rate_limit" in text:
            return True
    return False


def is_auth_failure(exc: str | None, message: str | None = None) -> bool:
    """Upstream 401 / invalid key. Not a model task failure."""
    if exc == "AuthenticationError":
        return True
    if exc == "APIStatusError" and message:
        text = message.lower()
        if "401" in message or "invalid api key" in text or "unauthorized" in text:
            return True
    return False


def is_infra_exception(exc: str | None, message: str | None = None) -> bool:
    if exc in INFRA_EXCEPTIONS:
        return True
    if is_rate_limit(exc, message):
        return True
    return is_auth_failure(exc, message)


def termination_of(data: dict[str, Any], trial_dir: Path | None = None) -> str:
    exc = _exception_type(data)
    if exc == "AgentTimeoutError":
        return "tle"
    if is_infra_exception(exc, _exception_message(data)):
        return "infra"
    if exc:
        return "protocol_error"
    trace = _compact_shell_trace(data, trial_dir)
    finished = trace.get("finished")
    try:
        n_shell = int(trace.get("n_shell") or 0)
    except (TypeError, ValueError):
        n_shell = 0
    if finished is False:
        return "protocol_error"
    if finished is True and n_shell == 0:
        return "protocol_error"
    return "clean"


def _sidecar(trial_dir: Path) -> dict[str, Any]:
    path = trial_dir / "verifier" / "standard.json"
    if not path.is_file():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        return {}
    return data if isinstance(data, dict) else {}


def score_trial(trial_dir: Path, data: dict[str, Any]) -> dict[str, Any]:
    reward = _reward(data)
    atomic = 1 if (reward or 0.0) >= 1.0 else 0
    extra = _sidecar(trial_dir)
    if "atomic_correct" in extra:
        try:
            atomic = 1 if int(extra["atomic_correct"]) >= 1 else 0
        except (TypeError, ValueError):
            pass
    term = termination_of(data, trial_dir)
    scored = term != "infra"
    fmt = extra.get("format_compliance", "unknown")
    path_fmt = extra.get("path_format_compliance", "n/a")
    task = task_name_from_trial(data, trial_dir)
    return {
        "trial": trial_dir.name,
        "task": task,
        "atom": atom_of(task),
        "atomic_correct": atomic,
        "termination": term,
        "format_compliance": fmt,
        "path_format_compliance": path_fmt,
        "raw_format_compliant": extra.get("raw_format_compliant"),
        "scored": scored,
        "reward": reward,
        "exception": _exception_type(data),
        "in_main_47": task in MAIN_47,
        "in_diagnostic": task in DIAGNOSTIC,
    }


def score_job(job_dir: Path) -> dict[str, Any]:
    rows = [score_trial(trial_dir, data) for trial_dir, data in load_trials(job_dir)]
    by_task: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        by_task[row["task"]].append(row)

    task_p: dict[str, float | None] = {}
    for task, trials in by_task.items():
        scored = [t for t in trials if t["scored"]]
        if not scored:
            task_p[task] = None
            continue
        task_p[task] = sum(t["atomic_correct"] for t in scored) / len(scored)

    skill: dict[str, float | None] = {}
    for prefix, label in ATOMS.items():
        vals = [
            task_p[name]
            for name in MAIN_47
            if name.startswith(f"{prefix}-") and task_p.get(name) is not None
        ]
        skill[label] = sum(vals) / len(vals) if vals else None

    n = len(rows) or 1
    term_counts: dict[str, int] = defaultdict(int)
    for row in rows:
        term_counts[row["termination"]] += 1

    return {
        "job": str(job_dir),
        "n_trials": len(rows),
        "skill_means_main_47": skill,
        "p_i": task_p,
        "termination_rate": {k: v / n for k, v in sorted(term_counts.items())},
        "trials": rows,
    }


def format_report(report: dict[str, Any]) -> str:
    lines = [
        f"job {report['job']}",
        f"trials {report['n_trials']}",
        "skill means (MAIN_47, scored trials only):",
    ]
    for label, value in (report["skill_means_main_47"] or {}).items():
        shown = f"{value:.3f}" if value is not None else "n/a"
        lines.append(f"  {label}: {shown}")
    lines.append(f"termination {report['termination_rate']}")
    return "\n".join(lines)


def _check_expect(report: dict[str, Any], expect: int, label: str) -> list[str]:
    want = set(MAIN_47 + DIAGNOSTIC)
    seen = {row["task"] for row in report["trials"]}
    missing = sorted(want - seen)
    bad = [
        f"{row['task']} atomic_correct={row['atomic_correct']} "
        f"termination={row['termination']} exception={row['exception']}"
        for row in report["trials"]
        if row["task"] in want and row["atomic_correct"] != expect
    ]
    msgs = []
    if missing:
        msgs.append(f"{label}: missing tasks {missing}")
    if bad:
        msgs.append(f"{label}: expected atomic_correct={expect} but\n  " + "\n  ".join(bad))
    return msgs


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("jobs", nargs="+", type=Path)
    parser.add_argument("--require-oracle", action="store_true")
    parser.add_argument("--require-nop", action="store_true")
    args = parser.parse_args(argv)
    code = 0
    for job_dir in args.jobs:
        if not job_dir.is_dir():
            print(f"missing job dir: {job_dir}", file=sys.stderr)
            code = 2
            continue
        report = score_job(job_dir)
        out = job_dir / "standard-scores.json"
        out.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
        print(format_report(report), flush=True)
        print(f"wrote {out}", flush=True)
        problems: list[str] = []
        if args.require_oracle:
            problems.extend(_check_expect(report, 1, "oracle"))
        if args.require_nop:
            problems.extend(_check_expect(report, 0, "nop"))
        for msg in problems:
            print(msg, file=sys.stderr)
            code = 1
    return code


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
