"""Write the public 12-config ranking SVG from canonical-coverage.json.

Does not call Harbor or overwrite frozen locks. No matplotlib.

    python scripts/write_leaderboard_figure.py --write
"""

from __future__ import annotations

import argparse
import html
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from build_canonical_matrix import FROZEN_LOCKS  # noqa: E402
from write_leaderboard import load_coverage, ranked_models  # noqa: E402

OUT = ROOT / "results" / "figures" / "v1.0.1-compact10.svg"


def render_svg(coverage: dict) -> str:
    ranked = ranked_models(coverage["models"])

    width = 860
    left = 176
    top = 64
    row_h = 36
    plot_w = 612
    height = top + row_h * len(ranked) + 72
    bar_h = 11

    def x_of(value: float) -> float:
        return left + max(0.0, min(1.0, value)) * plot_w

    parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" '
        f'viewBox="0 0 {width} {height}" role="img" '
        'aria-label="12 个配置的结果正确率与完整完成率">',
        '<rect width="100%" height="100%" fill="#ffffff"/>',
        '<text x="24" y="28" font-family="ui-sans-serif, system-ui, sans-serif" '
        'font-size="16" font-weight="600" fill="#111827">'
        "12 个配置：结果正确率与完整完成率</text>",
        '<text x="24" y="48" font-family="ui-sans-serif, system-ui, sans-serif" '
        'font-size="12" fill="#6b7280">'
        "深色是最终结果对不对；浅色是做对了，并且正常停下来。五类任务等权平均。</text>",
    ]
    for tick in (0.0, 0.25, 0.5, 0.75, 1.0):
        x = x_of(tick)
        y1 = top - 6
        y2 = top + row_h * len(ranked)
        parts.append(
            f'<line x1="{x:.1f}" y1="{y1:.1f}" x2="{x:.1f}" y2="{y2:.1f}" '
            'stroke="#e5e7eb" stroke-width="1"/>'
        )
        parts.append(
            f'<text x="{x:.1f}" y="{y2 + 16:.1f}" text-anchor="middle" '
            'font-family="ui-sans-serif, system-ui, sans-serif" font-size="11" '
            f'fill="#6b7280">{int(tick * 100)}%</text>'
        )
    for i, model in enumerate(ranked):
        y = top + i * row_h
        label = html.escape(model["display"])
        parts.append(
            f'<text x="{left - 12:.1f}" y="{y + 18:.1f}" text-anchor="end" '
            'font-family="ui-sans-serif, system-ui, sans-serif" font-size="12" '
            f'fill="#111827">{label}</text>'
        )
        a = float(model["atomic_macro"])
        e = float(model["e2e_macro"])
        parts.append(
            f'<rect x="{left:.1f}" y="{y + 6:.1f}" width="{a * plot_w:.1f}" '
            f'height="{bar_h}" fill="#1f4e79" rx="1"/>'
        )
        parts.append(
            f'<rect x="{left:.1f}" y="{y + 6 + bar_h + 3:.1f}" '
            f'width="{e * plot_w:.1f}" height="{bar_h}" fill="#9db4c8" rx="1"/>'
        )
        parts.append(
            f'<text x="{x_of(a) + 6:.1f}" y="{y + 6 + bar_h - 1:.1f}" '
            'font-family="ui-sans-serif, system-ui, sans-serif" font-size="10" '
            f'fill="#1f4e79">{a * 100:.1f}%</text>'
        )
    legend_y = height - 28
    parts += [
        f'<rect x="24" y="{legend_y - 10}" width="14" height="10" fill="#1f4e79"/>',
        f'<text x="44" y="{legend_y}" font-family="ui-sans-serif, system-ui, sans-serif" '
        'font-size="12" fill="#111827">结果正确率</text>',
        f'<rect x="148" y="{legend_y - 10}" width="14" height="10" fill="#9db4c8"/>',
        f'<text x="168" y="{legend_y}" font-family="ui-sans-serif, system-ui, sans-serif" '
        'font-size="12" fill="#111827">完整完成率</text>',
        f'<text x="276" y="{legend_y}" font-family="ui-sans-serif, system-ui, sans-serif" '
        'font-size="12" fill="#6b7280">'
        f"两条差一截，就是做对了却没停：共 {coverage['halt_unfinished_atomic']} 次</text>",
        "</svg>",
        "",
    ]
    return "\n".join(parts)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--write", action="store_true")
    args = parser.parse_args()
    text = render_svg(load_coverage())
    if args.write:
        for frozen in FROZEN_LOCKS:
            if OUT.resolve() == frozen.resolve():
                print(f"refusing: would write frozen lock {frozen}", file=sys.stderr)
                return 2
        OUT.parent.mkdir(parents=True, exist_ok=True)
        OUT.write_text(text, encoding="utf-8")
        print(f"wrote {OUT}")
    else:
        print(text[:200])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
