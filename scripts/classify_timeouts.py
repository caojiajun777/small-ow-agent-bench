"""Classify Harbor trials: stall vs loop vs after-pass vs task miss.

See TIMEOUT.md. Usage:

    python scripts/classify_timeouts.py jobs/2026-08-23__00-05-01
"""

from __future__ import annotations

import json
import sys
from collections import Counter
from datetime import datetime
from pathlib import Path
from typing import Any

STALL_MAX_EPISODES_SLOW_CALL = 8
STALL_SLOW_CALL_MS = 30_000
STALL_FEW_EPISODES = 3
STALL_LONG_WALL_SEC = 150.0
STALL_CMD_API_FRACTION = 0.6

KIND_PASS = "pass"
KIND_AFTER_PASS = "timeout_after_pass"
KIND_TASK_MISS = "task_miss"
KIND_LOOP = "timeout_loop"
KIND_STALL = "timeout_stall"
KIND_INFRA = "infra"
KIND_OTHER = "other_error"


def _parse_ts(value: str | None) -> datetime | None:
    if not value:
        return None
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def _duration_sec(started: str | None, finished: str | None) -> float | None:
    start = _parse_ts(started)
    end = _parse_ts(finished)
    if start is None or end is None:
        return None
    return (end - start).total_seconds()


def _reward(data: dict[str, Any]) -> float | None:
    rewards = (data.get("verifier_result") or {}).get("rewards") or {}
    if "reward" not in rewards:
        return None
    try:
        return float(rewards["reward"])
    except (TypeError, ValueError):
        return None


def _exception_type(data: dict[str, Any]) -> str | None:
    info = data.get("exception_info") or {}
    return info.get("exception_type")


def classify_trial(data: dict[str, Any]) -> str:
    exc = _exception_type(data)
    reward = _reward(data) or 0.0
    timed_out = exc == "AgentTimeoutError"

    if exc == "BuildException":
        return KIND_INFRA
    if timed_out and reward >= 1.0:
        return KIND_AFTER_PASS
    if not timed_out:
        if exc:
            return KIND_OTHER
        return KIND_PASS if reward >= 1.0 else KIND_TASK_MISS

    agent = data.get("agent_result") or {}
    meta = agent.get("metadata") or {}
    n_episodes = int(meta.get("n_episodes") or 0)
    api_times = [float(x) for x in (meta.get("api_request_times_msec") or [])]
    wall = _duration_sec(
        (data.get("agent_execution") or {}).get("started_at"),
        (data.get("agent_execution") or {}).get("finished_at"),
    )
    traceback = (data.get("exception_info") or {}).get("exception_traceback") or ""
    max_api = max(api_times) if api_times else 0.0
    sum_api_sec = (sum(api_times) / 1000.0) if api_times else 0.0

    if n_episodes <= 1 and not api_times:
        return KIND_STALL
    if n_episodes <= STALL_MAX_EPISODES_SLOW_CALL and max_api >= STALL_SLOW_CALL_MS:
        return KIND_STALL
    if n_episodes <= STALL_FEW_EPISODES and wall is not None and wall >= STALL_LONG_WALL_SEC:
        return KIND_STALL
    if (
        "_execute_commands" in traceback
        and n_episodes <= STALL_MAX_EPISODES_SLOW_CALL
        and wall is not None
        and wall > 0
        and sum_api_sec < STALL_CMD_API_FRACTION * wall
    ):
        return KIND_STALL
    return KIND_LOOP


def task_name_from_trial(data: dict[str, Any], trial_dir: Path | None = None) -> str:
    raw = data.get("task_name") or ""
    if "/" in raw:
        return raw.rsplit("/", 1)[-1]
    if trial_dir is not None and "__" in trial_dir.name:
        return trial_dir.name.split("__", 1)[0]
    return trial_dir.name if trial_dir else raw


def load_trials(job_dir: Path) -> list[tuple[Path, dict[str, Any]]]:
    out: list[tuple[Path, dict[str, Any]]] = []
    for path in sorted(job_dir.glob("*/result.json")):
        if path.parent.name.startswith("."):
            continue
        data = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(data, dict) or "trial_name" not in data:
            continue
        out.append((path.parent, data))
    return out


def classify_job(job_dir: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for trial_dir, data in load_trials(job_dir):
        kind = classify_trial(data)
        reward = _reward(data)
        atom = 1.0 if (reward or 0.0) >= 1.0 else 0.0
        if kind in {KIND_STALL, KIND_INFRA}:
            atom_included = False
        else:
            atom_included = True
        rows.append(
            {
                "trial": trial_dir.name,
                "task": task_name_from_trial(data, trial_dir),
                "kind": kind,
                "reward": reward,
                "atom": atom,
                "atom_included": atom_included,
                "exception": _exception_type(data),
            }
        )
    return rows


def summarize(rows: list[dict[str, Any]]) -> dict[str, Any]:
    counts = Counter(r["kind"] for r in rows)
    scored = [r for r in rows if r["atom_included"]]
    atom_mean = (
        sum(r["atom"] for r in scored) / len(scored) if scored else None
    )
    harbor_mean = (
        sum(1.0 if (r["reward"] or 0.0) >= 1.0 else 0.0 for r in rows) / len(rows)
        if rows
        else None
    )
    n = len(rows) or 1
    return {
        "n_trials": len(rows),
        "kinds": dict(counts),
        "harbor_mean": harbor_mean,
        "atom_mean": atom_mean,
        "n_atom_scored": len(scored),
        "timeout_after_pass": counts[KIND_AFTER_PASS],
        "timeout_loop": counts[KIND_LOOP],
        "timeout_stall": counts[KIND_STALL],
        "task_miss": counts[KIND_TASK_MISS],
        "halt_or_timeout_rate": (counts[KIND_AFTER_PASS] + counts[KIND_LOOP] + counts[KIND_STALL])
        / n,
        "stall_tasks": sorted({r["task"] for r in rows if r["kind"] == KIND_STALL}),
        "loop_tasks": sorted({r["task"] for r in rows if r["kind"] == KIND_LOOP}),
        "after_pass_tasks": sorted({r["task"] for r in rows if r["kind"] == KIND_AFTER_PASS}),
        "task_miss_tasks": sorted({r["task"] for r in rows if r["kind"] == KIND_TASK_MISS}),
    }


def format_report(job_dir: Path, rows: list[dict[str, Any]]) -> str:
    stats = summarize(rows)
    harbor = stats["harbor_mean"]
    atom = stats["atom_mean"]
    harbor_s = f"{harbor:.3f}" if harbor is not None else "n/a"
    atom_s = (
        f"{atom:.3f} (n={stats['n_atom_scored']}, stalls excluded)"
        if atom is not None
        else "n/a"
    )
    lines = [
        f"job {job_dir}",
        f"trials {stats['n_trials']}  harbor_mean {harbor_s}",
        f"atom_mean {atom_s}",
        f"kinds {stats['kinds']}",
        f"timeout_after_pass {stats['timeout_after_pass']} {stats['after_pass_tasks']}",
        f"timeout_loop {stats['timeout_loop']} {stats['loop_tasks']}",
        f"timeout_stall {stats['timeout_stall']} {stats['stall_tasks']}",
        f"task_miss {stats['task_miss']} {stats['task_miss_tasks']}",
    ]
    return "\n".join(lines)


def main(argv: list[str]) -> int:
    if len(argv) < 2:
        print("usage: python scripts/classify_timeouts.py jobs/<job> [...]", file=sys.stderr)
        return 2
    code = 0
    for raw in argv[1:]:
        job_dir = Path(raw)
        if not job_dir.is_dir():
            print(f"missing job dir: {job_dir}", file=sys.stderr)
            code = 2
            continue
        rows = classify_job(job_dir)
        print(format_report(job_dir, rows), flush=True)
        print(flush=True)
    return code


if __name__ == "__main__":
    sys.exit(main(sys.argv))
