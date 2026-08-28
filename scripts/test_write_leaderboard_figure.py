"""16-config ranking SVG. Does not call Harbor."""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from build_canonical_matrix import FROZEN_LOCKS  # noqa: E402
from write_leaderboard_figure import OUT, render_svg  # noqa: E402
from write_leaderboard import load_coverage  # noqa: E402


def test_figure_is_not_frozen_lock():
    assert OUT.resolve() not in {p.resolve() for p in FROZEN_LOCKS}


def test_svg_ranks_all_sixteen():
    text = render_svg(load_coverage())
    assert text.startswith("<svg")
    assert "Qwen3.5-9B" in text
    assert "78.6%" in text
    assert "Llama-3.2-3B" in text
    assert "Qwen3.8-27B" in text
    assert "Qwen3.6-35B-A3B" in text
    assert "86.3%" in text
    assert "16 个配置" in text
    assert "GLM-4.7-Flash" in text
    assert "GPT-OSS-20B" in text
    assert "结果正确率" in text
    assert "完整完成率" in text
    assert "做对了却没停" in text
    assert "Artifact" not in text
    assert "Clean" not in text
    assert "halt" not in text.lower()
    assert text.find("Qwen3.8-27B") < text.find("Qwen3.5-9B")
    assert 'aria-label="OpenAI"' in text
    assert 'aria-label="NVIDIA"' in text
    assert 'aria-label="Z.ai"' in text
    assert text.count('aria-label="Google"') == 3
    for color in ("#4285F4", "#34A853", "#FBBC05", "#EA4335"):
        assert color in text
    assert "M12 1 21.5 6.5v11" not in text
    assert "M2 12c2.8-4.4" not in text
    assert "M12 1 23 12 12 23" not in text
