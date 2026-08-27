"""Sanitized v1.0.1 trial export. Does not call Harbor."""

from pathlib import Path
import json
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from export_v101_trials import (  # noqa: E402
    LABELS_OUT,
    TRIALS_OUT,
    difficulty_table,
    job_basename,
    sanitize,
)
from build_canonical_matrix import FROZEN_LOCKS  # noqa: E402


def test_sanitize_drops_windows_path():
    row = {
        "lock_id": "qwen3.5-9b",
        "task": "loc-failing-test-impl",
        "attempt": 1,
        "atomic_correct": 1,
        "termination": "clean",
        "job": r"C:\Users\90556\Desktop\learning\benchmark\small-ow-agent-bench\jobs\2026-08-27__16-06-11",
        "rerun_of": r"C:\Users\90556\Desktop\learning\benchmark\small-ow-agent-bench\jobs\old",
        "openrouter_id": "openrouter/qwen/qwen3.5-9b",
    }
    got = sanitize(row)
    assert got["job"] == "2026-08-27__16-06-11"
    assert got["rerun_of"] == "old"
    blob = json.dumps(got)
    assert "C:\\Users" not in blob
    assert "openrouter_id" not in got


def test_outputs_are_not_frozen_locks():
    frozen = {p.resolve() for p in FROZEN_LOCKS}
    assert TRIALS_OUT.resolve() not in frozen
    assert LABELS_OUT.resolve() not in frozen


def test_job_basename():
    assert job_basename(None) is None
    assert job_basename("jobs/2026-08-27__16-00-19") == "2026-08-27__16-00-19"


def test_label_rules_easy_hard_uncalibrated():
    rows = []
    for a in (1, 2, 3):
        rows.append(
            {
                "lock_id": "qwen3.5-9b",
                "task": "edit-timeout-zero",
                "attempt": a,
                "atomic_correct": 1,
                "termination": "clean",
            }
        )
        rows.append(
            {
                "lock_id": "gemma-3-4b-it",
                "task": "edit-timeout-zero",
                "attempt": a,
                "atomic_correct": 1 if a == 1 else 0,
                "termination": "clean",
            }
        )
        for floor in ("llama-3.2-3b-instruct", "ministral-3b-2512"):
            rows.append(
                {
                    "lock_id": floor,
                    "task": "edit-timeout-zero",
                    "attempt": a,
                    "atomic_correct": 0,
                    "termination": "protocol_error",
                }
            )
        rows.append(
            {
                "lock_id": "qwen3.8-27b",
                "task": "edit-timeout-zero",
                "attempt": a,
                "atomic_correct": 1,
                "termination": "clean",
            }
        )
    labels = difficulty_table(rows)
    assert labels["tasks"]["edit-timeout-zero"]["label"] == "easy"
