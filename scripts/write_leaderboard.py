"""Write the public leaderboard markdown from canonical-coverage.json.

Does not call Harbor or overwrite frozen locks.

    python scripts/write_leaderboard.py
    python scripts/write_leaderboard.py --write
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from build_canonical_matrix import FROZEN_LOCKS, SUMMARY_OUT, fmt3  # noqa: E402

OUT = ROOT / "results" / "leaderboard.md"
SKILLS = ("loc", "edit", "testgen", "repro", "review")
SKILL_HEAD = ("Loc", "Edit", "Testgen", "Repro", "Review")


def load_coverage() -> dict:
    return json.loads(SUMMARY_OUT.read_text(encoding="utf-8"))


def compact_and_upper(models: list[dict]) -> tuple[list[dict], list[dict]]:
    compact = [m for m in models if m.get("group") == "compact_dense"]
    upper = [m for m in models if m.get("group") != "compact_dense"]
    return compact, upper


def skill_row(model: dict, *, e2e: bool) -> str:
    skills = model["skills_e2e" if e2e else "skills_atomic"]
    macro = model["e2e_macro" if e2e else "atomic_macro"]
    ok = model["e2e_ok" if e2e else "atomic_ok"]
    cells = " | ".join(fmt3(skills[k]) for k in SKILLS)
    macro_cell = f"**{fmt3(macro)}**" if model["lock_id"] == "qwen3.5-9b" and not e2e else fmt3(macro)
    micro = f"{fmt3(ok / 186)}（{ok}/186）"
    return f"| {model['display']} | {cells} | {macro_cell} | {micro} |"


def rank_row(rank: int | str, model: dict) -> str:
    gap = model.get("gap")
    gap_s = fmt3(gap)
    if model["lock_id"] == "gemma-3-12b-it":
        gap_s = f"**{gap_s}**"
    return (
        f"| {rank} | {model['display']} | {fmt3(model['atomic_macro'])} | "
        f"{fmt3(model['e2e_macro'])} | {gap_s} | "
        f"{model['atomic_ok']}/186 | {model['e2e_ok']}/186 |"
    )


def render(coverage: dict) -> str:
    compact, upper = compact_and_upper(coverage["models"])
    skill_header = (
        "| 模型 | "
        + " | ".join(SKILL_HEAD)
        + " | **宏平均** | 微平均 |\n"
        + "|---|---:|---:|---:|---:|---:|---:|---:|"
    )
    rank_header = (
        "| # | 模型 | Artifact 宏平均 | Clean 宏平均 | Gap | Artifact 微平均 | Clean 微平均 |\n"
        "|---:|---|---:|---:|---:|---:|---:|"
    )
    lines = [
        "# v1.0.1 leaderboard",
        "",
        "Source: [`canonical-coverage.json`](canonical-coverage.json). "
        "Regenerate: `python scripts/write_leaderboard.py --write`.",
        "",
        "Headline = five-skill **macro** mean on 62 items. Micro = successes / 186. "
        "Compact-10 is ranked by Artifact macro. 27B / 35B-A3B are upper-reference "
        "and do not enter that rank. Artifact does not require `finish`; Clean does.",
        "",
        f"n = {coverage['n_models']} configs × {coverage['n_tasks']} tasks × 3 "
        f"= **{coverage['n_scored']}** scored trials. "
        f"`remaining_dirty` {len(coverage.get('remaining_dirty') or [])}. "
        f"Halt (Artifact=1, not clean) = **{coverage['halt_unfinished_atomic']}**.",
        "",
        "## Compact-10",
        "",
        rank_header,
    ]
    for i, model in enumerate(compact, start=1):
        lines.append(rank_row(i, model))
    lines += [
        "",
        "## Upper-reference (not ranked with Compact-10)",
        "",
        rank_header,
    ]
    for model in upper:
        lines.append(rank_row("—", model))
    lines += [
        "",
        "## Artifact Correctness (five skills)",
        "",
        skill_header,
    ]
    for model in compact + upper:
        lines.append(skill_row(model, e2e=False))
    lines += [
        "",
        "## Clean Completion (five skills)",
        "",
        "Row order matches the Artifact table. Granite Clean macro > Gemma-12B "
        "because of Gemma-12B's halt tax, not because Granite solves more items.",
        "",
        skill_header,
    ]
    for model in compact + upper:
        lines.append(skill_row(model, e2e=True))
    lines.append("")
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--write", action="store_true")
    args = parser.parse_args()
    text = render(load_coverage())
    print(text)
    if args.write:
        for frozen in FROZEN_LOCKS:
            if OUT.resolve() == frozen.resolve():
                print(f"refusing: would write frozen lock {frozen}", file=sys.stderr)
                return 2
        OUT.write_text(text, encoding="utf-8")
        print(f"wrote {OUT}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
