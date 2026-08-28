from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from models_lock import llm_kwargs  # noqa: E402
from run_supplement import (  # noqa: E402
    ATTEMPTS,
    FORMAL_TASKS,
    PROTOCOL_TASKS,
    _cell,
    _protocol_passes,
    _protocol_ready,
    load_supplement,
    plan_cells,
    select_models,
)


def test_lock_has_four_pinned_models_and_frozen_protocol():
    lock = load_supplement()
    assert lock["frozen"] is True
    assert lock["overwrites_v1"] is False
    assert len(lock["models"]) == 4
    assert lock["inference"]["temperature"] == 0.0
    assert lock["inference"]["max_tokens"] == 4096
    for model in lock["models"]:
        extra = llm_kwargs(model, lock)["extra_body"]
        assert extra["provider"] == {
            "order": [model["openrouter_provider"]],
            "allow_fallbacks": False,
            "require_parameters": True,
        }


def test_gpt_oss_has_declared_mandatory_reasoning_exception():
    lock = load_supplement()
    model = select_models(lock, ["gpt-oss-20b"])[0]
    reasoning = llm_kwargs(model, lock)["extra_body"]["reasoning"]
    assert model["reasoning"] == "mandatory_low"
    assert reasoning == {"effort": "low", "exclude": False}


def test_other_models_disable_reasoning():
    lock = load_supplement()
    for model in lock["models"]:
        if model["id"] == "gpt-oss-20b":
            continue
        reasoning = llm_kwargs(model, lock)["extra_body"]["reasoning"]
        assert reasoning == {"enabled": False, "exclude": True}


def test_gemma_has_single_action_stop_adapter_only():
    lock = load_supplement()
    for model in lock["models"]:
        stop = model["llm_call_kwargs"].get("stop")
        if model["id"] == "gemma-4-26b-a4b-it":
            assert "\n\nWait" in stop
        else:
            assert stop is None


def test_formal_plan_is_744_independent_slots():
    lock = load_supplement()
    cells = plan_cells(lock["models"], FORMAL_TASKS, ATTEMPTS)
    assert len(FORMAL_TASKS) == 62
    assert len(cells) == 744
    assert {attempt for _, _, attempt in cells} == {1, 2, 3}


def test_protocol_plan_includes_complex_action_probe():
    lock = load_supplement()
    cells = plan_cells(lock["models"], PROTOCOL_TASKS, (1,))
    assert PROTOCOL_TASKS == (
        "hello-world",
        "collect-todos",
        "loc-member-discount",
    )
    assert len(cells) == 12


def test_protocol_gate_requires_all_clean_passes():
    lock = load_supplement()
    subjects = select_models(lock, ["glm-4.7-flash"])
    rows = [
        {
            "lock_id": "glm-4.7-flash",
            "task": "hello-world",
            "atomic_correct": 1,
            "termination": "clean",
        },
        {
            "lock_id": "glm-4.7-flash",
            "task": "collect-todos",
            "atomic_correct": 1,
            "termination": "tle",
        },
        {
            "lock_id": "glm-4.7-flash",
            "task": "loc-member-discount",
            "atomic_correct": 1,
            "termination": "clean",
        },
    ]
    ready, by_model = _protocol_passes(rows, subjects)
    assert not ready
    assert by_model == {"glm-4.7-flash": False}
    rows[1]["termination"] = "clean"
    assert _protocol_passes(rows, subjects) == (True, {"glm-4.7-flash": True})


def test_protocol_ready_distinguishes_task_miss_from_transport_failure():
    lock = load_supplement()
    subjects = select_models(lock, ["gpt-oss-20b"])
    rows = [
        {
            "lock_id": "gpt-oss-20b",
            "task": task,
            "atomic_correct": 0,
            "termination": "clean",
            "reason": None,
            "finished": True,
            "n_turns": 1,
            "n_shell": 0,
            "n_parse_fail": 0,
        }
        for task in PROTOCOL_TASKS
    ]
    assert _protocol_passes(rows, subjects) == (False, {"gpt-oss-20b": False})
    assert _protocol_ready(rows, subjects) == (True, {"gpt-oss-20b": True})
    rows[1]["termination"] = "protocol_error"
    rows[1]["finished"] = False
    rows[1]["n_shell"] = 2
    assert _protocol_ready(rows, subjects) == (True, {"gpt-oss-20b": True})
    rows[1]["n_shell"] = 0
    assert _protocol_ready(rows, subjects) == (False, {"gpt-oss-20b": False})


def test_cell_requires_three_valid_attempts_and_scores_clean_separately():
    rows = [
        {
            "lock_id": "m",
            "task": "edit-slugify",
            "attempt": 1,
            "atomic_correct": 1,
            "termination": "clean",
        },
        {
            "lock_id": "m",
            "task": "edit-slugify",
            "attempt": 2,
            "atomic_correct": 1,
            "termination": "tle",
        },
        {
            "lock_id": "m",
            "task": "edit-slugify",
            "attempt": 3,
            "atomic_correct": 0,
            "termination": "clean",
        },
    ]
    cell = _cell(rows, "m", "edit-slugify")
    assert cell["n_valid"] == 3
    assert cell["p_atomic"] == 2 / 3
    assert cell["p_e2e"] == 1 / 3

    rows[2]["termination"] = "infra"
    incomplete = _cell(rows, "m", "edit-slugify")
    assert incomplete["incomplete"] is True
    assert incomplete["p_atomic"] is None
    assert incomplete["infra_count"] == 1
