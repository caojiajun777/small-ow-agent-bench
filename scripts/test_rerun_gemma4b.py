"""Gemma-4B 429 sensitivity helper. Does not call Harbor."""

from pathlib import Path
import json
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from rerun_gemma4b import (  # noqa: E402
    DIRTY_EXCEPTIONS,
    K3_OUT,
    MODEL_ID,
    OUT,
    dirty_plan,
    gemma_rows,
    is_dirty,
    trial_exception_type,
)
from run_locked import RETRY_INCLUDE  # noqa: E402


def test_side_table_does_not_overwrite_core_lock():
    assert OUT.resolve() != K3_OUT.resolve()
    assert "locked-core-k3" not in OUT.name
    assert MODEL_ID == "gemma-3-4b-it"


def test_retry_include_has_litellm_rate_limit_name():
    assert "RateLimitError" in RETRY_INCLUDE


def test_dirty_detects_rate_limit(tmp_path: Path):
    trial = tmp_path / "edit-slugify__abc"
    trial.mkdir()
    (trial / "result.json").write_text(
        json.dumps(
            {
                "trial_name": "x",
                "exception_info": {"exception_type": "RateLimitError"},
            }
        ),
        encoding="utf-8",
    )
    row = {"job": str(tmp_path), "lock_id": MODEL_ID, "task": "edit-slugify"}
    assert trial_exception_type(str(tmp_path)) == "RateLimitError"
    assert is_dirty(row)
    assert "RateLimitError" in DIRTY_EXCEPTIONS
    assert "ReadError" not in DIRTY_EXCEPTIONS


def test_clean_protocol_error_is_not_dirty(tmp_path: Path):
    trial = tmp_path / "loc-bind-host__abc"
    trial.mkdir()
    (trial / "result.json").write_text(
        json.dumps({"trial_name": "x", "exception_info": {}}),
        encoding="utf-8",
    )
    assert not is_dirty({"job": str(tmp_path)})


def test_plan_from_frozen_lock_is_rate_limits_only():
    rows = gemma_rows()
    planned = dirty_plan(rows)
    assert len(rows) == 141
    assert len(planned) == 67
    assert all(trial_exception_type(r.get("job")) == "RateLimitError" for r in planned)
