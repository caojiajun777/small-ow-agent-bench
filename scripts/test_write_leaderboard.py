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
    assert "leaderboard-v1.0.1" in readme
    assert "77.3" in readme
    assert "74.3" in readme
    assert "83.8" in readme
    assert "59.5" in readme
    assert "Qwen3.8-27B" in readme
    assert "Qwen3.6-35B-A3B" in readme
    assert "GLM-4.7-Flash" in readme
    assert "GPT-OSS-20B" in readme
    assert "不参加" not in readme
    assert "10 个小型模型配置中整体表现最好" not in readme
    assert "results/figures/v1.0.1-compact10.svg" in readme
    assert "Qwen3.5-9B" in readme
    assert "玩具档" not in readme
    assert "目标档" not in readme
    assert "尺子" not in readme
    assert "canonical matrix" not in readme
    for banned in ("gold", "mutant", "foil", "oracle", "no-op", "Halt"):
        assert banned not in readme
    assert "results/figures/vendors/qwen.svg" in readme
    assert "results/figures/vendors/mistralai.svg" in readme
    assert "results/figures/vendors/google.svg" in readme
    assert "results/figures/vendors/ibm.svg" in readme
    assert "results/figures/vendors/meta.svg" in readme


def test_render_matches_canonical_micros():
    text = render(load_coverage())
    assert "148/186" in text
    assert "142/186" in text
    assert "162/186" in text
    assert "11/186" in text
    assert "77.3" in text
    assert "83.8" in text
    assert "`remaining_dirty` 0" in text
    assert "Halt (Artifact=1, not clean) = **197**" in text
    assert "## Ranked (16 configs)" in text
    assert "105/186" in text
    assert "89/186" in text
    assert "## Compact-10" not in text
    assert "Upper-reference" not in text
    assert "do not enter that rank" not in text
    rank_head = text.split("## Artifact Score")[0]
    assert "| 1 | Qwen3.8-27B |" in rank_head
    assert "| 2 | Qwen3.5-9B |" in rank_head
    assert "| 3 | Qwen3.6-35B-A3B |" in rank_head
    assert "| 4 | GLM-4.7-Flash |" in rank_head
    assert "| 5 | GPT-OSS-20B |" in rank_head
