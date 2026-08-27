"""Public HF catalog. Metadata only; no Harbor, no frozen-lock writes."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from build_canonical_matrix import BANK_62, FROZEN_LOCKS  # noqa: E402
from export_hf_catalog import (  # noqa: E402
    ALLOWED_KEYS,
    CATALOG_OUT,
    HF_CARD,
    HF_CATALOG,
    HF_DIR,
    TASKS,
    catalog_rows,
    parse_traps,
    render_jsonl,
)
from task_sets import HARD_RELEASE_15, MAIN_47  # noqa: E402


def test_outputs_are_not_frozen_locks():
    frozen = {p.resolve() for p in FROZEN_LOCKS}
    for path in (CATALOG_OUT, HF_CATALOG, HF_CARD):
        assert path.resolve() not in frozen


def test_catalog_covers_bank_62():
    rows = catalog_rows()
    ids = [row["id"] for row in rows]
    assert ids == list(BANK_62)
    assert len(set(ids)) == 62
    assert set(ids) == set(MAIN_47) | set(HARD_RELEASE_15)


def test_allowed_keys_only():
    for row in catalog_rows():
        assert tuple(row) == ALLOWED_KEYS


def test_every_bank_task_has_a_trap():
    traps = parse_traps((ROOT / "TRAPS.md").read_text(encoding="utf-8"))
    missing = [name for name in BANK_62 if name not in traps]
    assert missing == []


def test_instruction_is_agent_visible_file():
    for row in catalog_rows():
        expected = (TASKS / row["id"] / "instruction.md").read_text(encoding="utf-8").strip()
        assert row["instruction"] == expected
        assert row["instruction_summary"]
        assert "skill" in row
        assert row["difficulty"] in {"easy", "medium", "hard", "uncalibrated"}
        assert row["github_tag"] == "benchmark-v1.0.1"


def test_catalog_does_not_copy_hidden_verifiers():
    blob = render_jsonl(catalog_rows())
    leaked: list[str] = []
    for task in BANK_62:
        instruction = (TASKS / task / "instruction.md").read_text(encoding="utf-8")
        for folder in ("tests", "solution", "foils"):
            root = TASKS / task / folder
            if not root.is_dir():
                continue
            for path in root.rglob("*"):
                if not path.is_file():
                    continue
                text = path.read_text(encoding="utf-8", errors="ignore").strip()
                if len(text) < 40:
                    continue
                if text in instruction:
                    continue
                if text in blob:
                    leaked.append(str(path.relative_to(TASKS)))
        expected = TASKS / task / "tests" / "expected.txt"
        if expected.is_file():
            gold = expected.read_text(encoding="utf-8").strip()
            if gold and gold not in instruction and gold in blob:
                leaked.append(str(expected.relative_to(TASKS)))
    assert leaked == []


def test_readme_points_at_catalog_not_verifiers():
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    assert "results/hf_catalog.jsonl" in readme
    assert "huggingface.co/datasets/junjun77/small-ow-agent-bench" in readme
    assert "environment/repo" in readme


def test_hf_dir_only_has_catalog_and_card():
    HF_DIR.mkdir(parents=True, exist_ok=True)
    names = {p.name for p in HF_DIR.iterdir() if p.is_file()}
    assert names <= {"catalog.jsonl", "README.md"}
