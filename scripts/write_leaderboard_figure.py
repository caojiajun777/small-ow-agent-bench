"""Write a Compact-10 Artifact vs Clean SVG from canonical-coverage.json.

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
from write_leaderboard import compact_and_upper, load_coverage  # noqa: E402

OUT = ROOT / "results" / "figures" / "v1.0.1-compact10.svg"


def render_svg(coverage: dict) -> str:
    compact, _upper = compact_and_upper(coverage["models"])

    width = 860
    left = 168
    top = 64
    row_h = 36
    plot_w = 620
    height = top + row_h * len(compact) + 72
    bar_h = 11

    def x_of(value: float) -> float:
        return left + max(0.0, min(1.0, value)) * plot_w

    parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" '
        f'viewBox="0 0 {width} {height}" role="img" '
        'aria-label="Compact-10 Artifact vs Clean macro mean, v1.0.1">',
        '<rect width="100%" height="100%" fill="#ffffff"/>',
        '<text x="24" y="28" font-family="ui-sans-serif, system-ui, sans-serif" '
        'font-size="16" font-weight="600" fill="#111827">'
        "Compact-10 · Artifact vs Clean (v1.0.1)</text>",
        '<text x="24" y="48" font-family="ui-sans-serif, system-ui, sans-serif" '
        'font-size="12" fill="#6b7280">'
        "Five-skill macro mean on 62 items. Micro denominator is 186. "
        "27B / 35B-A3B are upper-reference and are not in this rank.</text>",
    ]
    for tick in (0.0, 0.25, 0.5, 0.75, 1.0):
        x = x_of(tick)
        y1 = top - 6
        y2 = top + row_h * len(compact)
        parts.append(
            f'<line x1="{x:.1f}" y1="{y1:.1f}" x2="{x:.1f}" y2="{y2:.1f}" '
            'stroke="#e5e7eb" stroke-width="1"/>'
        )
        parts.append(
            f'<text x="{x:.1f}" y="{y2 + 16:.1f}" text-anchor="middle" '
            'font-family="ui-sans-serif, system-ui, sans-serif" font-size="11" '
            f'fill="#6b7280">{tick:.2f}</text>'
        )
    for i, model in enumerate(compact):
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
            f'fill="#1f4e79">{a:.3f}</text>'
        )
    legend_y = height - 28
    parts += [
        f'<rect x="24" y="{legend_y - 10}" width="14" height="10" fill="#1f4e79"/>',
        f'<text x="44" y="{legend_y}" font-family="ui-sans-serif, system-ui, sans-serif" '
        'font-size="12" fill="#111827">Artifact</text>',
        f'<rect x="120" y="{legend_y - 10}" width="14" height="10" fill="#9db4c8"/>',
        f'<text x="140" y="{legend_y}" font-family="ui-sans-serif, system-ui, sans-serif" '
        'font-size="12" fill="#111827">Clean</text>',
        f'<text x="210" y="{legend_y}" font-family="ui-sans-serif, system-ui, sans-serif" '
        'font-size="11" fill="#6b7280">'
        "Source: results/canonical-coverage.json · halt (Artifact=1, not clean) = "
        f"{coverage['halt_unfinished_atomic']}</text>",
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
