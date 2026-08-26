"""Hard-15 lock-field failure composition."""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from fail_compose import classify_lock, compose  # noqa: E402


def test_lock_four_way():
    assert (
        classify_lock({"atomic_correct": 1, "termination": "clean"})
        == "task_pass_clean"
    )
    assert (
        classify_lock({"atomic_correct": 1, "termination": "protocol_error"})
        == "task_pass_unfinished"
    )
    assert (
        classify_lock({"atomic_correct": 0, "termination": "clean"})
        == "task_fail_clean"
    )
    assert (
        classify_lock({"atomic_correct": 0, "termination": "protocol_error"})
        == "task_fail_unfinished"
    )
    assert classify_lock({"termination": "infra"}) == "infra_fail"


def test_compose_e2e_fail_is_not_atomic_fail():
    rows = [
        {
            "lock_id": "m",
            "task": "repro-nested-alias",
            "atom": "repro",
            "attempt": 1,
            "atomic_correct": 1,
            "termination": "protocol_error",
        },
        {
            "lock_id": "m",
            "task": "repro-nested-alias",
            "atom": "repro",
            "attempt": 2,
            "atomic_correct": 1,
            "termination": "protocol_error",
        },
        {
            "lock_id": "m",
            "task": "repro-nested-alias",
            "atom": "repro",
            "attempt": 3,
            "atomic_correct": 0,
            "termination": "clean",
        },
    ]
    report = compose(rows)
    stats = report["by_model"]["m"]
    assert stats["atomic_pass"] == 2
    assert stats["e2e_pass"] == 0
    assert stats["e2e_fail"] == 3
    assert stats["lock_kind"]["task_pass_unfinished"] == 2
    assert stats["lock_kind"]["task_fail_clean"] == 1
