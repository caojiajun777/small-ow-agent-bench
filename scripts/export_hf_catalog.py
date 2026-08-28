"""Export a public Hugging Face catalog for the 62-item bank.

Metadata only: id, skill, difficulty, trap, agent-visible instruction.
Does not copy tests/, solution/, foils/, expected files, or environment/repo.
Does not overwrite frozen Harbor locks.

    python scripts/export_hf_catalog.py
    python scripts/export_hf_catalog.py --write
    python scripts/export_hf_catalog.py --write --push
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from build_canonical_matrix import BANK_62, FROZEN_LOCKS  # noqa: E402
from task_sets import HARD_RELEASE_15, MAIN_47  # noqa: E402

TASKS = ROOT / "tasks"
TRAPS_MD = ROOT / "TRAPS.md"
LABELS = ROOT / "results" / "v1.0.1_difficulty.json"
CATALOG_OUT = ROOT / "results" / "hf_catalog.jsonl"
HF_DIR = ROOT / "results" / "hf_dataset"
HF_CATALOG = HF_DIR / "catalog.jsonl"
HF_CARD = HF_DIR / "README.md"

GITHUB_REPO = "caojiajun777/small-ow-agent-bench"
GITHUB_TAG = "benchmark-v1.0.1"
LICENSE = "Apache-2.0"
COMPACT_SHELL = "0.1.1"
DEFAULT_HF_REPO = "junjun77/small-ow-agent-bench"

ALLOWED_KEYS = (
    "id",
    "skill",
    "difficulty",
    "bank",
    "trap_id",
    "trap",
    "instruction",
    "instruction_summary",
    "license",
    "github_repo",
    "github_tag",
    "github_task_url",
    "compact_shell_version",
    "benchmark_version",
)

TRAP_ROW = re.compile(
    r"^\|\s*(?P<id>[A-Z]{1,3}\d+)\s*\|\s*(?P<trap>.+?)\s*\|\s*`(?P<task>[a-z0-9-]+)`\s*\|"
)

SKILL_OF = {
    "loc": "loc",
    "edit": "edit",
    "testgen": "testgen",
    "repro": "repro",
    "review": "review",
}


def skill_of(task: str) -> str:
    prefix = task.split("-", 1)[0]
    if prefix not in SKILL_OF:
        raise SystemExit(f"unknown skill prefix on {task}")
    return SKILL_OF[prefix]


def bank_of(task: str) -> str:
    if task in HARD_RELEASE_15:
        return "hard-release-15"
    if task in MAIN_47:
        return "base-47"
    raise SystemExit(f"{task} is not in BANK_62")


def first_paragraph(text: str) -> str:
    parts = [p.strip() for p in re.split(r"\n\s*\n", text.strip()) if p.strip()]
    summary = parts[0] if parts else text.strip()
    summary = re.sub(r"\s+", " ", summary)
    if len(summary) > 280:
        summary = summary[:277].rstrip() + "..."
    return summary


def parse_traps(text: str) -> dict[str, tuple[str, str]]:
    found: dict[str, tuple[str, str]] = {}
    for line in text.splitlines():
        match = TRAP_ROW.match(line)
        if not match:
            continue
        task = match.group("task")
        found[task] = (match.group("id"), match.group("trap").strip())
    return found


def load_difficulty() -> dict[str, str]:
    payload = json.loads(LABELS.read_text(encoding="utf-8"))
    return {name: row["label"] for name, row in payload["tasks"].items()}


def catalog_rows() -> list[dict[str, Any]]:
    traps = parse_traps(TRAPS_MD.read_text(encoding="utf-8"))
    difficulty = load_difficulty()
    rows: list[dict[str, Any]] = []
    for task in BANK_62:
        instruction_path = TASKS / task / "instruction.md"
        instruction = instruction_path.read_text(encoding="utf-8").strip()
        trap_id, trap = traps[task]
        row = {
            "id": task,
            "skill": skill_of(task),
            "difficulty": difficulty[task],
            "bank": bank_of(task),
            "trap_id": trap_id,
            "trap": trap,
            "instruction": instruction,
            "instruction_summary": first_paragraph(instruction),
            "license": LICENSE,
            "github_repo": GITHUB_REPO,
            "github_tag": GITHUB_TAG,
            "github_task_url": (
                f"https://github.com/{GITHUB_REPO}/tree/{GITHUB_TAG}/tasks/{task}"
            ),
            "compact_shell_version": COMPACT_SHELL,
            "benchmark_version": GITHUB_TAG,
        }
        extra = set(row) - set(ALLOWED_KEYS)
        if extra:
            raise SystemExit(f"unexpected catalog keys: {sorted(extra)}")
        rows.append(row)
    if len(rows) != 62:
        raise SystemExit(f"expected 62 catalog rows, got {len(rows)}")
    return rows


def render_jsonl(rows: list[dict[str, Any]]) -> str:
    return "".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows)


def dataset_card() -> str:
    from write_leaderboard import load_coverage, rank_row, ranked_models

    coverage = load_coverage()
    ranked = ranked_models(coverage["models"])
    rank_header = (
        "| # | Model | Artifact macro | Clean macro | Gap | Artifact micro | Clean micro |\n"
        "|---:|---|---:|---:|---:|---:|---:|"
    )
    rank_table = "\n".join(
        [rank_header, *[rank_row(i, model) for i, model in enumerate(ranked, start=1)]]
    )
    return f"""---
license: apache-2.0
pretty_name: small-ow-agent-bench
task_categories:
  - text-generation
language:
  - en
tags:
  - agents
  - code
  - evaluation
  - harbor
  - benchmark
size_categories:
  - n<1K
configs:
  - config_name: catalog
    data_files: catalog.jsonl
    default: true
---

# small-ow-agent-bench (catalog)

Frozen compact-shell **system** reliability for compact open-weight coding agents — not coding IQ.

- GitHub: [caojiajun777/small-ow-agent-bench](https://github.com/caojiajun777/small-ow-agent-bench)
- Tag: [`benchmark-v1.0.1`](https://github.com/caojiajun777/small-ow-agent-bench/releases/tag/benchmark-v1.0.1)
- This dataset: [`junjun77/small-ow-agent-bench`](https://huggingface.co/datasets/junjun77/small-ow-agent-bench)

This dataset is **not** the Harbor task dump. Each of the 62 rows is catalog metadata plus the agent-visible instruction:

- `id`, `skill`, `difficulty`, `bank`
- `trap_id` / `trap` (failure-mode label from `TRAPS.md`)
- `instruction` / `instruction_summary`
- license, GitHub tag, compact-shell version

It does **not** include hidden verifiers: `tests/`, `solution/`, `foils/`, gold file lists, mutants, or `environment/repo`. Those stay in Harbor `tasks/` on GitHub.

Do not train on this 62-item bank and then report the same items as evaluation.

The `benchmark-v1.0.1` tag preserves the original 12-model freeze. The current canonical table adds four fully evaluated models as an append-only supplement without rewriting those frozen source rows.

## Leaderboard (v1.0.1)

Headline = five-skill **macro** mean. Micro = successes / 186. Artifact does not require `finish`; Clean does. Halt (Artifact=1, not clean) = **{coverage["halt_unfinished_atomic"]}**. {coverage["n_models"]}×62×3 = **{coverage["n_scored"]}** scored trials. All {coverage["n_models"]} configs enter one rank. Qwen3.6-35B-A3B is a MoE with ~3B active parameters.

![结果正确率与完整完成率](v1.0.1-compact10.svg)

{rank_table}

Full five-skill tables: [results/leaderboard.md](https://github.com/caojiajun777/small-ow-agent-bench/blob/main/results/leaderboard.md).

Regenerate:

```text
python scripts/export_hf_catalog.py --write
```
"""


def load_env_file() -> None:
    path = ROOT / ".env"
    if not path.is_file():
        return
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key and key not in os.environ:
            os.environ[key] = value


def refuse_frozen(path: Path) -> None:
    for frozen in FROZEN_LOCKS:
        if path.resolve() == frozen.resolve():
            raise SystemExit(f"refusing: would write frozen lock {frozen}")


def write_outputs(text: str) -> None:
    from write_leaderboard_figure import OUT as FIGURE_OUT, render_svg
    from write_leaderboard import load_coverage

    for path in (CATALOG_OUT, HF_CATALOG, HF_CARD):
        refuse_frozen(path)
    HF_DIR.mkdir(parents=True, exist_ok=True)
    CATALOG_OUT.write_text(text, encoding="utf-8")
    HF_CATALOG.write_text(text, encoding="utf-8")
    HF_CARD.write_text(dataset_card(), encoding="utf-8")
    figure = render_svg(load_coverage())
    if FIGURE_OUT.resolve() not in {p.resolve() for p in FROZEN_LOCKS}:
        FIGURE_OUT.parent.mkdir(parents=True, exist_ok=True)
        FIGURE_OUT.write_text(figure, encoding="utf-8")
        (HF_DIR / FIGURE_OUT.name).write_text(figure, encoding="utf-8")
    print(f"wrote {CATALOG_OUT}")
    print(f"wrote {HF_CATALOG}")
    print(f"wrote {HF_CARD}")
    print(f"wrote {FIGURE_OUT}")


def push_dataset(repo_id: str) -> None:
    from huggingface_hub import HfApi

    load_env_file()
    if not (os.environ.get("HF_TOKEN") or os.environ.get("HUGGING_FACE_HUB_TOKEN")):
        raise SystemExit("missing HF_TOKEN in .env (do not paste the token into chat)")
    api = HfApi()
    api.create_repo(repo_id=repo_id, repo_type="dataset", exist_ok=True)
    api.upload_folder(
        folder_path=str(HF_DIR),
        repo_id=repo_id,
        repo_type="dataset",
        commit_message="Refresh v1.0.1 catalog card to rank all 16 configs.",
    )
    print(f"https://huggingface.co/datasets/{repo_id}")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--write", action="store_true")
    parser.add_argument("--push", action="store_true")
    parser.add_argument("--hf-repo", default=DEFAULT_HF_REPO)
    args = parser.parse_args()
    rows = catalog_rows()
    text = render_jsonl(rows)
    print(f"rows={len(rows)}")
    print(text.splitlines()[0][:200])
    if args.write:
        write_outputs(text)
    if args.push:
        if not args.write:
            print("refusing --push without --write", file=sys.stderr)
            return 2
        push_dataset(args.hf_repo)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
