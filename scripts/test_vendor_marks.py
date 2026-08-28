"""Publisher marks for the ranking table. Does not call Harbor."""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from vendor_marks import VENDORS, vendor_key, vendor_path  # noqa: E402
from write_leaderboard import load_coverage, ranked_models  # noqa: E402


def test_every_ranked_model_has_a_publisher_mark():
    for model in ranked_models(load_coverage()["models"]):
        key = vendor_key(model["lock_id"], model["display"])
        assert key in VENDORS
        assert vendor_path(key).is_file()


def test_vendor_keys_match_publishers():
    assert vendor_key("qwen3.8-27b", "Qwen3.8-27B") == "qwen"
    assert vendor_key("ministral-14b-2512", "Ministral-14B") == "mistral"
    assert vendor_key("gemma-3-12b-it", "Gemma-3-12B") == "google"
    assert vendor_key("granite-4.1-8b", "Granite-4.1-8B") == "ibm"
    assert vendor_key("llama-3.2-3b-instruct", "Llama-3.2-3B") == "meta"
    assert vendor_key("gpt-oss-20b", "GPT-OSS-20B") == "openai"
    assert vendor_key("nemotron-3.5-lightning", "Nemotron-3.5-Lightning") == "nvidia"
    assert vendor_key("glm-4.7-flash", "GLM-4.7-Flash") == "zai"
