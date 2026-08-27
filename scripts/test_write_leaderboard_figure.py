"""12-config ranking SVG. Does not call Harbor."""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from build_canonical_matrix import FROZEN_LOCKS  # noqa: E402
from write_leaderboard_figure import OUT, render_svg  # noqa: E402
from write_leaderboard import load_coverage  # noqa: E402


def test_figure_is_not_frozen_lock():
    assert OUT.resolve() not in {p.resolve() for p in FROZEN_LOCKS}


def test_svg_ranks_all_twelve():
    text = render_svg(load_coverage())
    assert text.startswith("<svg")
    assert "Qwen3.5-9B" in text
    assert "78.6%" in text
    assert "Llama-3.2-3B" in text
    assert "Qwen3.8-27B" in text
    assert "Qwen3.6-35B-A3B" in text
    assert "86.3%" in text
    assert "结果正确率" in text
    assert "完整完成率" in text
    assert "做对了却没停" in text
    assert "Artifact" not in text
    assert "Clean" not in text
    assert "halt" not in text.lower()
    assert text.find("Qwen3.8-27B") < text.find("Qwen3.5-9B")
    assert 'fill="#111111"' in text
    assert 'fill="#FA520F"' in text
    assert 'fill="#4285F4"' in text
    assert 'fill="#0F62FE"' in text
    assert 'fill="#0082FB"' in text
