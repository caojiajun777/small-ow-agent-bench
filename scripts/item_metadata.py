"""Canonical task metadata for the published 62-item bank.

The benchmark has two deliberately separate notions of difficulty:

* ``construct_difficulty`` is the author-designed Easy / Medium / Hard tier.
  It is frozen before leaderboard results and determines score weights.
* ``empirical_band`` is the observed calibration location under one frozen
  model + provider + agent protocol.  It is evidence, not a score weight.

``difficulty`` in Harbor task.toml files remains a compatibility alias for
``construct_difficulty``.
"""

from __future__ import annotations

import json
import re
from collections import Counter
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]

from task_sets import HARD_RELEASE_15, MAIN_47  # noqa: E402

PRIOR_ITEM_MAP = ROOT / "prior-item-map.json"
TRAPS_MD = ROOT / "TRAPS.md"
EMPIRICAL_LABELS = ROOT / "results" / "v1.0.1_difficulty.json"

BANK_62 = (*MAIN_47, *HARD_RELEASE_15)
CONSTRUCT_WEIGHTS = {"easy": 1.0, "medium": 1.5, "hard": 2.0}
EXPECTED_CONSTRUCT_COUNTS = {"easy": 17, "medium": 21, "hard": 24}

# Author clarification, 2026-08-29: every v1.0.1 out-of-range construct was
# designed as Hard.  The other four out-of-range tasks are already Hard in
# prior-item-map.json or HARD_RELEASE_15; only this stale prior needs repair.
CONSTRUCT_OVERRIDES = {"loc-reexport": "hard"}

TRAP_ROW = re.compile(
    r"^\|\s*(?P<id>[A-Z]{1,3}\d+)\s*\|\s*(?P<trap>.+?)\s*\|"
    r"\s*`(?P<task>[a-z0-9-]+)`\s*\|"
)


def skill_of(task: str) -> str:
    skill = task.split("-", 1)[0]
    if skill not in {"loc", "edit", "testgen", "repro", "review"}:
        raise ValueError(f"unknown skill prefix: {task}")
    return skill


def bank_of(task: str) -> str:
    if task in MAIN_47:
        return "base-47"
    if task in HARD_RELEASE_15:
        return "hard-release-15"
    raise ValueError(f"task is not in the published bank: {task}")


def parse_traps() -> dict[str, tuple[str, str]]:
    found: dict[str, tuple[str, str]] = {}
    for line in TRAPS_MD.read_text(encoding="utf-8").splitlines():
        match = TRAP_ROW.match(line)
        if match:
            found[match.group("task")] = (
                match.group("id"),
                match.group("trap").strip(),
            )
    missing = sorted(set(BANK_62) - set(found))
    if missing:
        raise ValueError(f"TRAPS.md is missing published tasks: {missing}")
    return found


def construct_metadata() -> dict[str, dict[str, Any]]:
    prior = json.loads(PRIOR_ITEM_MAP.read_text(encoding="utf-8"))
    prior_items = {row["task"]: row for row in prior["items"]}
    if set(prior_items) != set(MAIN_47):
        missing = sorted(set(MAIN_47) - set(prior_items))
        extra = sorted(set(prior_items) - set(MAIN_47))
        raise ValueError(f"prior-item-map mismatch: missing={missing}, extra={extra}")

    traps = parse_traps()
    out: dict[str, dict[str, Any]] = {}
    for task in BANK_62:
        if task in HARD_RELEASE_15:
            difficulty = "hard"
            source = "hard-release-15"
        else:
            raw = str(prior_items[task]["construct_b"])
            difficulty = "hard" if raw == "hard_candidate" else raw
            source = "prior-item-map"
        if task in CONSTRUCT_OVERRIDES:
            difficulty = CONSTRUCT_OVERRIDES[task]
            source = "author-clarification-2026-08-29"
        if difficulty not in CONSTRUCT_WEIGHTS:
            raise ValueError(f"invalid construct difficulty for {task}: {difficulty}")
        trap_id, trap = traps[task]
        out[task] = {
            "task": task,
            "skill": skill_of(task),
            "bank": bank_of(task),
            "trap_id": trap_id,
            "trap": trap,
            "construct_difficulty": difficulty,
            "difficulty_weight": CONSTRUCT_WEIGHTS[difficulty],
            "construct_source": source,
        }

    counts = Counter(row["construct_difficulty"] for row in out.values())
    if dict(counts) != EXPECTED_CONSTRUCT_COUNTS:
        raise ValueError(
            f"construct counts {dict(counts)} != {EXPECTED_CONSTRUCT_COUNTS}"
        )
    return out


def empirical_metadata(
    payload: dict[str, Any] | None = None,
) -> dict[str, dict[str, str]]:
    if payload is None:
        payload = json.loads(EMPIRICAL_LABELS.read_text(encoding="utf-8"))
    rows = payload.get("tasks") or {}
    missing = sorted(set(BANK_62) - set(rows))
    if missing:
        raise ValueError(f"empirical labels are missing tasks: {missing}")
    out: dict[str, dict[str, str]] = {}
    for task in BANK_62:
        label = str(rows[task]["label"])
        band = "out_of_range" if label == "uncalibrated" else label
        out[task] = {
            "empirical_band": band,
            "calibration_status": (
                "out_of_range" if band == "out_of_range" else "calibrated"
            ),
        }
    return out


def item_metadata(
    empirical_payload: dict[str, Any] | None = None,
) -> dict[str, dict[str, Any]]:
    construct = construct_metadata()
    empirical = empirical_metadata(empirical_payload)
    return {
        task: {**construct[task], **empirical[task]}
        for task in BANK_62
    }

