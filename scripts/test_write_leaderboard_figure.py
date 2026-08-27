"""Compact-10 SVG. Does not call Harbor."""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from build_canonical_matrix import FROZEN_LOCKS  # noqa: E402
from write_leaderboard_figure import OUT, render_svg  # noqa: E402
from write_leaderboard import load_coverage  # noqa: E402


def test_figure_is_not_frozen_lock():
    assert OUT.resolve() not in {p.resolve() for p in FROZEN_LOCKS}


def test_svg_has_compact_headline():
    text = render_svg(load_coverage())
    assert text.startswith("<svg")
    assert "Qwen3.5-9B" in text
    assert "0.786" in text
    assert "Llama-3.2-3B" in text
    assert "Qwen3.8-27B" not in text
    assert "Artifact" in text
    assert "Clean" in text
    assert "halt" in text.lower()
