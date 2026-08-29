from __future__ import annotations

import json
import sys
import tomllib
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from item_metadata import (  # noqa: E402
    BANK_62,
    CONSTRUCT_WEIGHTS,
    EXPECTED_CONSTRUCT_COUNTS,
    item_metadata,
)
from analyze_v101_irt import analyze  # noqa: E402


def test_item_metadata_is_complete_and_separates_semantics() -> None:
    rows = item_metadata()
    assert list(rows) == list(BANK_62)
    assert len(rows) == 62
    assert len({row["trap_id"] for row in rows.values()}) == 62
    assert Counter(row["construct_difficulty"] for row in rows.values()) == Counter(
        EXPECTED_CONSTRUCT_COUNTS
    )
    assert rows["loc-reexport"]["construct_difficulty"] == "hard"
    assert rows["loc-reexport"]["empirical_band"] == "out_of_range"
    assert rows["loc-reexport"]["difficulty_weight"] == 2.0
    assert all(
        row["construct_difficulty"] == "hard"
        for row in rows.values()
        if row["empirical_band"] == "out_of_range"
    )
    for row in rows.values():
        assert row["difficulty_weight"] == CONSTRUCT_WEIGHTS[
            row["construct_difficulty"]
        ]


def test_task_toml_matches_canonical_metadata() -> None:
    rows = item_metadata()
    for task, row in rows.items():
        data = tomllib.loads(
            (ROOT / "tasks" / task / "task.toml").read_text(encoding="utf-8")
        )
        meta = data["metadata"]
        assert meta["difficulty"] == row["construct_difficulty"]
        assert meta["construct_difficulty"] == row["construct_difficulty"]
        assert meta["empirical_band"] == row["empirical_band"]
        assert meta["calibration_status"] == row["calibration_status"]
        assert meta["difficulty_weight"] == row["difficulty_weight"]
        assert meta["trap_id"] == row["trap_id"]


def test_published_metadata_artifact_matches_source() -> None:
    artifact = json.loads(
        (ROOT / "results" / "v1.0.1_item_metadata.json").read_text(
            encoding="utf-8"
        )
    )
    rows = item_metadata()
    assert artifact["construct_counts"] == EXPECTED_CONSTRUCT_COUNTS
    assert artifact["empirical_counts"] == {
        "easy": 12,
        "medium": 38,
        "hard": 7,
        "out_of_range": 5,
    }
    assert artifact["difficulty_weights"] == CONSTRUCT_WEIGHTS
    assert artifact["items"] == [rows[task] for task in BANK_62]


def test_irt_artifact_is_reproducible_and_diagnostic_only() -> None:
    expected = analyze()
    artifact = json.loads(
        (ROOT / "results" / "v1.0.1_irt.json").read_text(encoding="utf-8")
    )
    assert artifact == expected
    assert artifact["published"] is False
    assert artifact["n_items_fitted"] == 61
    assert artifact["all_zero_items"] == ["loc-reexport"]
    assert artifact["negative_discrimination_items"] == []
    rates = [
        artifact["tier_summary"][tier]["mean_pass_rate"]
        for tier in ("easy", "medium", "hard")
    ]
    assert rates[0] > rates[1] > rates[2]
