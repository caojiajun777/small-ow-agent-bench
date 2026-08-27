"""Public leaderboard markdown. Does not call Harbor."""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from build_canonical_matrix import FROZEN_LOCKS  # noqa: E402
from write_leaderboard import OUT, load_coverage, render  # noqa: E402


def test_output_is_not_frozen_lock():
    frozen = {p.resolve() for p in FROZEN_LOCKS}
    assert OUT.resolve() not in frozen


def test_coverage_json_says_the_tag_is_cut():
    coverage = load_coverage()
    assert coverage["published"] is True
    assert coverage["benchmark_version"] == "benchmark-v1.0.1"
    assert "is not cut" not in coverage["note"]


def test_readme_embeds_canonical_headline():
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    assert "benchmark-v1.0.1" in readme
    assert "148/186" in readme
    assert "142/186" in readme
    assert "162/186" in readme
    assert "0.786" in readme
    assert "0.863" in readme
    assert "**105**" in readme
    assert "玩具档" not in readme
    assert "目标档" not in readme
    assert "尺子" not in readme


def test_render_matches_canonical_micros():
    text = render(load_coverage())
    assert "148/186" in text
    assert "142/186" in text
    assert "162/186" in text
    assert "11/186" in text
    assert "0.786" in text
    assert "0.863" in text
    assert "`remaining_dirty` 0" in text
    assert "Halt (Artifact=1, not clean) = **105**" in text
    compact_head = text.split("## Upper-reference")[0]
    assert "Qwen3.8-27B" not in compact_head
    assert "Qwen3.5-9B" in compact_head
