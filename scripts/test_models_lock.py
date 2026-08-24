"""Frozen 11-model lock and protocol-smoke tasks."""

from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from models_lock import by_group, llm_kwargs, load_lock, models, openrouter_id, select_subjects  # noqa: E402
from task_sets import MAIN_47, PROTOCOL_SMOKE  # noqa: E402

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


def test_lock_has_eleven_frozen_models():
    lock = load_lock()
    assert lock["frozen"] is True
    rows = models(lock)
    assert len(rows) == 11
    assert [m["id"] for m in by_group("irt-main", lock)] == list(MAIN_IDS)
    rulers = by_group("ruler", lock)
    assert len(rulers) == 1
    assert rulers[0]["id"] == "qwen3.8-27b"
    assert lock["core"]["n_trials_total"] == 539
    assert lock["core"]["n_core_trials"] == 517


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


def test_select_subjects_defaults_to_ten_main():
    lock = load_lock()
    main = select_subjects("main", lock=lock)
    assert [m["id"] for m in main] == list(MAIN_IDS)
    assert select_subjects("irt-main", lock=lock) == main
    all_rows = select_subjects("all", lock=lock)
    assert len(all_rows) == 11
    rulers = select_subjects("ruler", lock=lock)
    assert [m["id"] for m in rulers] == ["qwen3.8-27b"]
    batch1 = select_subjects("main", batch=1, lock=lock)
    assert {m["batch"] for m in batch1} == {1}
    assert len(batch1) == 7
