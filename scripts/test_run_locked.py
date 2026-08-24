"""Frozen 10-model runner: resume, group, full-run flags."""

from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from classify_timeouts import KIND_STALL  # noqa: E402
from run_locked import _parse_argv, trial_is_done  # noqa: E402


def test_full_flag_means_protocol_then_core():
    opts = _parse_argv(["--run", "--full", "--group", "main"])
    assert opts["run"] is True
    assert opts["protocol"] is True
    assert opts["core"] is True
    assert opts["group"] == "main"
    assert opts["force"] is False


def test_default_group_is_main():
    opts = _parse_argv(["--run", "--core"])
    assert opts["group"] == "main"
    assert opts["protocol"] is False
    assert opts["core"] is True


def test_skip_completed_clean_and_protocol_error():
    assert trial_is_done(
        {"termination": "clean", "atomic_correct": 1, "task": "hello-world"}
    )
    assert trial_is_done(
        {"termination": "protocol_error", "atomic_correct": 1, "task": "edit-slugify"}
    )
    assert trial_is_done(
        {"termination": "tle", "timeout_kind": "timeout_loop", "atomic_correct": 0}
    )


def test_retry_infra_no_job_and_unretried_stall():
    assert not trial_is_done({"termination": "infra", "atomic_correct": 0})
    assert not trial_is_done({"reason": "no_job"})
    assert not trial_is_done(
        {
            "termination": "tle",
            "timeout_kind": KIND_STALL,
            "stall_retried": False,
            "atomic_correct": 0,
        }
    )
    assert trial_is_done(
        {
            "termination": "tle",
            "timeout_kind": KIND_STALL,
            "stall_retried": True,
            "atomic_correct": 0,
        }
    )


def test_force_reruns_completed():
    row = {"termination": "clean", "atomic_correct": 1}
    assert trial_is_done(row)
    assert not trial_is_done(row, force=True)
    assert trial_is_done({"reason": "missing_on_openrouter"})
