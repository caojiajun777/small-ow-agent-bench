"""Frozen 12-model Core lock and protocol-smoke tasks."""

from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from models_lock import by_group, hard_release_rows, llm_kwargs, load_lock, models, openrouter_id, select_subjects  # noqa: E402
from task_sets import HARD_DEV_10, HARD_RELEASE_15, MAIN_47, PROTOCOL_SMOKE  # noqa: E402

MAIN_IDS = (
    "llama-3.2-3b-instruct",
    "ministral-3b-2512",
    "gemma-3-4b-it",
    "qwen3-8b",
    "ministral-8b-2512",
    "granite-4.1-8b",
    "qwen3.5-9b",
    "gemma-3-12b-it",
    "qwen3-14b",
    "ministral-14b-2512",
)


def test_lock_has_twelve_core_models():
    lock = load_lock()
    assert lock["frozen"] is True
    rows = models(lock)
    assert len(rows) == 12
    assert [m["id"] for m in by_group("compact_dense", lock)] == list(MAIN_IDS)
    assert [m["id"] for m in by_group("irt-main", lock)] == list(MAIN_IDS)
    assert [m["id"] for m in by_group("upper", lock)] == ["qwen3.8-27b"]
    assert [m["id"] for m in by_group("moe", lock)] == ["qwen3.6-35b-a3b"]
    assert lock["core"]["n_trials_total"] == 588
    assert lock["core"]["n_core_trials"] == 564


def test_batches_are_execution_only():
    lock = load_lock()
    assert {m["batch"] for m in models(lock)} <= {1, 2}
    assert lock["substitution_policy"] == "forbidden"


def test_every_model_pins_openrouter_provider():
    lock = load_lock()
    expected = {
        "llama-3.2-3b-instruct": "parasail/bf16",
        "ministral-3b-2512": "mistral",
        "gemma-3-4b-it": "deepinfra/bf16",
        "qwen3-8b": "alibaba",
        "ministral-8b-2512": "mistral",
        "granite-4.1-8b": "coreweave/bf16",
        "qwen3.5-9b": "parasail/bf16",
        "gemma-3-12b-it": "deepinfra/bf16",
        "qwen3-14b": "deepinfra/fp8",
        "ministral-14b-2512": "mistral",
        "qwen3.8-27b": "akashml/bf16",
        "qwen3.6-35b-a3b": "Venice",
    }
    for row in models(lock):
        assert openrouter_id(row)
        assert row["openrouter_provider"] == expected[row["id"]]
        kwargs = llm_kwargs(row)
        provider = kwargs["extra_body"]["provider"]
        assert provider["order"] == [expected[row["id"]]]
        assert provider["allow_fallbacks"] is False
        assert provider["require_parameters"] is True
        if row["family"] == "qwen":
            assert kwargs["extra_body"]["reasoning"] == {"enabled": False}
            assert kwargs["extra_body"]["enable_thinking"] is False
        else:
            assert "reasoning" not in kwargs["extra_body"]
        assert kwargs["max_tokens"] == 4096


def test_excluded_models_are_absent():
    lock = load_lock()
    blob = " ".join(
        str(m.get(k) or "")
        for m in models(lock)
        for k in ("id", "display", "hf_id", "openrouter_id")
    ).lower()
    for needle in (
        "qwen3.5-4b",
        "qwen2.5-coder",
        "seed-coder",
        "nemotron",
        "granite-4.1-3b",
        "gemma-4",
        "llama-3.1-8b",
        "devstral",
        "qwen3.6-27b",
        "gpt-oss",
    ):
        assert needle not in blob, needle


def test_hard_dev_ten_disjoint_from_core():
    assert len(HARD_DEV_10) == 10
    assert len(set(HARD_DEV_10)) == 10
    assert not set(HARD_DEV_10) & set(MAIN_47)
    prefixes = [n.split("-", 1)[0] for n in HARD_DEV_10]
    assert prefixes.count("loc") == 2
    assert prefixes.count("edit") == 2
    assert prefixes.count("testgen") == 2
    assert prefixes.count("repro") == 2
    assert prefixes.count("review") == 2
    for name in HARD_DEV_10:
        assert (ROOT / "tasks" / name / "task.toml").is_file(), name


def test_hard_release_fifteen_on_disk_and_disjoint():
    assert len(HARD_RELEASE_15) == 15
    assert not set(HARD_RELEASE_15) & set(MAIN_47)
    assert not set(HARD_RELEASE_15) & set(HARD_DEV_10)
    for name in HARD_RELEASE_15:
        assert (ROOT / "tasks" / name / "task.toml").is_file(), name


def test_protocol_smoke_and_core_sizes():
    assert PROTOCOL_SMOKE == ("hello-world", "collect-todos")
    assert len(MAIN_47) == 47
    for name in (*PROTOCOL_SMOKE, *MAIN_47):
        assert (ROOT / "tasks" / name / "task.toml").is_file(), name
    hello = ROOT / "tasks" / "hello-world" / "task.toml"
    text = hello.read_text(encoding="utf-8")
    assert "timeout_sec = 180.0" in text
    assert "hello-world" not in MAIN_47
    assert "collect-todos" not in MAIN_47


def test_select_subjects_defaults_to_ten_compact():
    lock = load_lock()
    main = select_subjects("main", lock=lock)
    assert [m["id"] for m in main] == list(MAIN_IDS)
    assert select_subjects("irt-main", lock=lock) == main
    assert select_subjects("compact", lock=lock) == main
    all_rows = select_subjects("all", lock=lock)
    assert len(all_rows) == 12
    assert select_subjects("core", lock=lock) == all_rows
    assert [m["id"] for m in select_subjects("ruler", lock=lock)] == ["qwen3.8-27b"]
    assert [m["id"] for m in select_subjects("moe", lock=lock)] == ["qwen3.6-35b-a3b"]
    batch1 = select_subjects("main", batch=1, lock=lock)
    assert {m["batch"] for m in batch1} == {1}
    assert len(batch1) == 7


HARD_RELEASE_IDS = (
    "ministral-8b-2512",
    "qwen3.5-9b",
    "qwen3-14b",
    "ministral-14b-2512",
    "qwen3.8-27b",
    "qwen3.6-35b-a3b",
)


def test_hard_release_examinees_are_six():
    lock = load_lock()
    assert lock["hard_release"]["n_examinees"] == 6
    assert lock["hard_release"]["n_trials"] == 270
    assert lock["hard_release"]["skipped_not_scored_as_zero"] is True
    flagged = [m["id"] for m in models(lock) if m.get("hard_release") is True]
    assert flagged == list(HARD_RELEASE_IDS)
    assert [m["id"] for m in hard_release_rows("main", lock=lock)] == list(
        HARD_RELEASE_IDS
    )
    assert len(hard_release_rows("all", lock=lock)) == 12
    skipped = [m["id"] for m in models(lock) if m.get("hard_release") is not True]
    assert "llama-3.2-3b-instruct" in skipped
    assert "qwen3-8b" in skipped
    assert "gemma-3-12b-it" in skipped
    assert "granite-4.1-8b" in skipped
