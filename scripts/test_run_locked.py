"""Frozen 10-model runner: resume, group, full-run flags."""

from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from classify_timeouts import KIND_STALL  # noqa: E402
from run_locked import (  # noqa: E402
    _parse_argv,
    _upsert_k3,
    attempt_is_valid,
    hard_dev_subjects,
    hard_release_subjects,
    plan_hard_dev_cells,
    plan_hard_release_cells,
    plan_k3_cells,
    plan_upper_base_cells,
    tasks_for_k3_subject,
    trial_is_done,
    upper_base_subjects,
)


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


def test_k3_fill_disables_protocol():
    opts = _parse_argv(["--run", "--k3-fill", "--full", "--group", "main"])
    assert opts["k3_fill"] is True
    assert opts["protocol"] is False
    assert opts["core"] is False
    assert opts["run"] is True
    assert opts["group"] == "main"


def test_k3_main_plan_is_940():
    from models_lock import load_lock, select_subjects

    lock = load_lock()
    subjects = select_subjects("main", lock=lock)
    cells = plan_k3_cells(subjects)
    assert len(subjects) == 10
    assert len(cells) == 940
    assert {a for _, _, a in cells} == {2, 3}
    assert all(m["group"] == "compact_dense" for m, _, _ in cells)


def test_k3_ruler_plan_is_14_loc():
    from models_lock import load_lock, select_subjects
    from task_sets import LOC_RULER_K3

    lock = load_lock()
    subjects = select_subjects("ruler", lock=lock)
    cells = plan_k3_cells(subjects)
    assert len(subjects) == 1
    assert len(LOC_RULER_K3) == 7
    assert "loc-unused-fix" not in LOC_RULER_K3
    assert len(cells) == 14
    assert {name for _, name, _ in cells} == set(LOC_RULER_K3)


def test_k3_all_plan_includes_35b_base_fill():
    from models_lock import load_lock, select_subjects

    lock = load_lock()
    cells = plan_k3_cells(select_subjects("all", lock=lock))
    assert len(cells) == 1048


def test_k3_upsert_keeps_distinct_attempts():
    rows: list[dict] = []
    _upsert_k3(
        rows,
        {"lock_id": "m", "task": "loc-bind-host", "attempt": 1, "atomic_correct": 0},
    )
    _upsert_k3(
        rows,
        {"lock_id": "m", "task": "loc-bind-host", "attempt": 2, "atomic_correct": 1},
    )
    _upsert_k3(
        rows,
        {"lock_id": "m", "task": "loc-bind-host", "attempt": 2, "atomic_correct": 0},
    )
    assert len(rows) == 2
    assert {r["attempt"]: r["atomic_correct"] for r in rows} == {1: 0, 2: 0}


def test_infra_is_not_a_valid_k3_attempt():
    assert not attempt_is_valid({"termination": "infra", "atomic_correct": 0})
    assert not attempt_is_valid({"termination": "clean", "atomic_correct": None})
    assert attempt_is_valid({"termination": "clean", "atomic_correct": 1})
    assert attempt_is_valid({"termination": "protocol_error", "atomic_correct": 0})
    assert not trial_is_done(
        {"termination": "infra", "atomic_correct": 0, "attempt": 2}
    )


def test_ruler_k3_tasks_exclude_easy_loc():
    from task_sets import LOC_RULER_K3, MAIN_47

    ruler = {"id": "qwen3.8-27b", "group": "upper_dense"}
    assert tasks_for_k3_subject(ruler) == LOC_RULER_K3
    assert tasks_for_k3_subject({"id": "qwen3.8-27b", "group": "ruler"}) == LOC_RULER_K3
    main = {"id": "qwen3.5-9b", "group": "compact_dense"}
    assert tasks_for_k3_subject(main) == MAIN_47
    moe = {"id": "qwen3.6-35b-a3b", "group": "efficient_moe"}
    assert tasks_for_k3_subject(moe) == MAIN_47


def test_hard_dev_flag_disables_protocol():
    opts = _parse_argv(["--run", "--hard-dev", "--full", "--group", "main"])
    assert opts["hard_dev"] is True
    assert opts["k3_fill"] is False
    assert opts["protocol"] is False
    assert opts["core"] is False
    assert opts["run"] is True


def test_hard_dev_plan_is_60():
    from models_lock import load_lock
    from task_sets import HARD_DEV_10

    lock = load_lock()
    subjects = hard_dev_subjects("main", None, lock)
    cells = plan_hard_dev_cells(subjects)
    assert [m["id"] for m in subjects] == ["qwen3.8-27b", "qwen3.6-35b-a3b"]
    assert len(HARD_DEV_10) == 10
    assert len(cells) == 60
    assert {a for _, _, a in cells} == {1, 2, 3}
    assert {name for _, name, _ in cells} == set(HARD_DEV_10)


def test_hard_dev_group_moe_is_30():
    from models_lock import load_lock

    lock = load_lock()
    subjects = hard_dev_subjects("moe", None, lock)
    cells = plan_hard_dev_cells(subjects)
    assert [m["id"] for m in subjects] == ["qwen3.6-35b-a3b"]
    assert len(cells) == 30


def test_hard_dev_rejects_core_group():
    from models_lock import load_lock

    lock = load_lock()
    try:
        hard_dev_subjects("core", None, lock)
    except SystemExit as exc:
        assert "27B+35B" in str(exc)
    else:
        raise AssertionError("expected SystemExit")


def test_hard_release_flag_disables_protocol():
    opts = _parse_argv(["--run", "--hard-release", "--full", "--group", "main"])
    assert opts["hard_release"] is True
    assert opts["hard_dev"] is False
    assert opts["k3_fill"] is False
    assert opts["protocol"] is False
    assert opts["core"] is False
    assert opts["run"] is True


def test_hard_release_exclusive_with_hard_dev():
    try:
        _parse_argv(["--hard-release", "--hard-dev"])
    except SystemExit as exc:
        assert "only one" in str(exc)
    else:
        raise AssertionError("expected SystemExit")


def test_hard_release_plan_is_270():
    from models_lock import load_lock
    from task_sets import HARD_RELEASE_15

    lock = load_lock()
    subjects = hard_release_subjects("main", None, lock)
    cells = plan_hard_release_cells(subjects)
    assert [m["id"] for m in subjects] == [
        "ministral-8b-2512",
        "qwen3.5-9b",
        "qwen3-14b",
        "ministral-14b-2512",
        "qwen3.8-27b",
        "qwen3.6-35b-a3b",
    ]
    assert len(HARD_RELEASE_15) == 15
    assert len(cells) == 270
    assert {a for _, _, a in cells} == {1, 2, 3}
    assert {name for _, name, _ in cells} == set(HARD_RELEASE_15)


def test_hard_release_group_moe_is_45():
    from models_lock import load_lock

    lock = load_lock()
    subjects = hard_release_subjects("moe", None, lock)
    cells = plan_hard_release_cells(subjects)
    assert [m["id"] for m in subjects] == ["qwen3.6-35b-a3b"]
    assert len(cells) == 45


def test_hard_release_group_compact_is_180():
    from models_lock import load_lock

    lock = load_lock()
    subjects = hard_release_subjects("compact", None, lock)
    cells = plan_hard_release_cells(subjects)
    assert len(subjects) == 4
    assert len(cells) == 180
    assert all(m["group"] == "compact_dense" for m in subjects)


def test_hard_release_group_all_is_540():
    from models_lock import load_lock

    lock = load_lock()
    subjects = hard_release_subjects("all", None, lock)
    cells = plan_hard_release_cells(subjects)
    assert len(subjects) == 12
    assert len(cells) == 540


def test_base_fill_flag_disables_protocol():
    opts = _parse_argv(["--run", "--base-fill", "--full", "--group", "main"])
    assert opts["base_fill"] is True
    assert opts["k3_fill"] is False
    assert opts["hard_dev"] is False
    assert opts["hard_release"] is False
    assert opts["protocol"] is False
    assert opts["core"] is False
    assert opts["run"] is True


def test_base_fill_exclusive_with_k3_fill():
    try:
        _parse_argv(["--base-fill", "--k3-fill"])
    except SystemExit as exc:
        assert "only one" in str(exc)
    else:
        raise AssertionError("expected SystemExit")


def test_base_fill_plan_is_282():
    from models_lock import load_lock
    from task_sets import MAIN_47

    lock = load_lock()
    subjects = upper_base_subjects("main", None, lock)
    cells = plan_upper_base_cells(subjects)
    assert [m["id"] for m in subjects] == ["qwen3.8-27b", "qwen3.6-35b-a3b"]
    assert len(MAIN_47) == 47
    assert len(cells) == 282
    assert {a for _, _, a in cells} == {1, 2, 3}
    assert {name for _, name, _ in cells} == set(MAIN_47)


def test_base_fill_group_moe_is_141():
    from models_lock import load_lock

    lock = load_lock()
    subjects = upper_base_subjects("moe", None, lock)
    cells = plan_upper_base_cells(subjects)
    assert [m["id"] for m in subjects] == ["qwen3.6-35b-a3b"]
    assert len(cells) == 141


def test_base_fill_group_ruler_is_141():
    from models_lock import load_lock
    from task_sets import MAIN_47

    lock = load_lock()
    subjects = upper_base_subjects("ruler", None, lock)
    cells = plan_upper_base_cells(subjects)
    assert [m["id"] for m in subjects] == ["qwen3.8-27b"]
    assert len(cells) == 141
    assert {name for _, name, _ in cells} == set(MAIN_47)


def test_base_fill_rejects_core_group():
    from models_lock import load_lock

    lock = load_lock()
    try:
        upper_base_subjects("core", None, lock)
    except SystemExit as exc:
        assert "27B+35B" in str(exc)
    else:
        raise AssertionError("expected SystemExit")
