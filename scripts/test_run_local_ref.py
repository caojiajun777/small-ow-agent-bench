"""Local Reference pins cover the frozen 12-model lock."""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from run_local_ref import load_pins, validate_against_lock  # noqa: E402


def test_local_pins_match_lock_and_are_full_shas():
    pins = load_pins()
    assert pins["kind"] == "local_reference_pins"
    assert pins["overwrites_api_standard"] is False
    assert pins["published"] is False
    assert not validate_against_lock()
    for row in pins["models"]:
        assert len(row["hf_revision"]) == 40
        assert all(c in "0123456789abcdef" for c in row["hf_revision"])
