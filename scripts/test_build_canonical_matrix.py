"""Canonical unique-key merge. Does not call Harbor or write frozen locks."""

from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from build_canonical_matrix import (  # noqa: E402
    BANK_62,
    DIRTY_EXCEPTIONS,
    FROZEN_LOCKS,
    ROWS_OUT,
    SUMMARY_OUT,
    merge_rows,
    model_score,
    overlay,
    trial_key,
)
from run_locked import HARD_RELEASE_OUT, K3_OUT  # noqa: E402


def _row(lock_id: str, task: str, attempt: int, atomic: int, *, job: str = "a") -> dict:
    return {
        "lock_id": lock_id,
        "task": task,
        "attempt": attempt,
        "atomic_correct": atomic,
        "termination": "clean",
        "job": job,
    }


def test_overlay_later_source_wins():
    by_key = {}
    overlay(by_key, [_row("m", "edit-slugify", 1, 0, job="old")])
    overlay(by_key, [_row("m", "edit-slugify", 1, 1, job="new")])
    got = by_key[("m", "edit-slugify", 1)]
    assert got["atomic_correct"] == 1
    assert got["job"] == "new"


def test_hard_floor_does_not_clobber_other_attempts():
    layers = [
        ("core", [_row("gemma-3-12b-it", "edit-slugify", 1, 1)]),
        (
            "hard_floor",
            [_row("gemma-3-12b-it", "edit-blank-name", 1, 1, job="floor")],
        ),
    ]
    rows, applied = merge_rows(layers)
    assert applied["hard_floor"] == 1
    keys = {trial_key(r) for r in rows}
    assert ("gemma-3-12b-it", "edit-slugify", 1) in keys
    assert ("gemma-3-12b-it", "edit-blank-name", 1) in keys


def test_bank_drops_protocol_smoke():
    by_key = {}
    n = overlay(by_key, [_row("m", "hello-world", 1, 1)])
    assert n == 0
    assert by_key == {}


def test_skill_mean_is_task_macro_not_micro():
    rows = []
    for a in (1, 2, 3):
        rows.append(_row("m", "review-slug-almost", a, 1))
        rows.append(_row("m", "review-slug-complete", a, 0))
    # remaining review tasks missing -> incomplete, review mean uses only scored tasks
    got = model_score(rows, "m")
    assert got["skills_atomic"]["review"] == 0.5
    assert got["atomic_ok"] == 3
    assert got["n_scored"] == 6


def test_outputs_are_not_frozen_locks():
    frozen = {p.resolve() for p in FROZEN_LOCKS}
    assert SUMMARY_OUT.resolve() not in frozen
    assert ROWS_OUT.resolve() not in frozen
    assert ROWS_OUT.resolve() != K3_OUT.resolve()
    assert ROWS_OUT.resolve() != HARD_RELEASE_OUT.resolve()
    assert "locked-core-k3" not in ROWS_OUT.name
    assert len(BANK_62) == 62
    assert "AuthenticationError" in DIRTY_EXCEPTIONS
    assert "OutputLengthExceededError" not in DIRTY_EXCEPTIONS
