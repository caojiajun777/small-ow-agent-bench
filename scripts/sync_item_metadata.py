"""Synchronize construct and empirical metadata for the published task bank.

Dry-run by default.  ``--write`` updates the 62 Harbor task.toml files and
writes ``results/v1.0.1_item_metadata.json``.  It never touches result locks.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import tomllib
from collections import Counter
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from item_metadata import (  # noqa: E402
    BANK_62,
    CONSTRUCT_WEIGHTS,
    EXPECTED_CONSTRUCT_COUNTS,
    item_metadata,
)

OUT = ROOT / "results" / "v1.0.1_item_metadata.json"
TASKS = ROOT / "tasks"
EXPLICIT_FIELDS = (
    "construct_difficulty",
    "empirical_band",
    "calibration_status",
    "difficulty_weight",
    "trap_id",
)


def toml_value(value: Any) -> str:
    if isinstance(value, str):
        return json.dumps(value, ensure_ascii=False)
    if isinstance(value, float):
        return f"{value:.1f}"
    raise TypeError(value)


def replace_metadata(text: str, row: dict[str, Any]) -> str:
    lines = text.splitlines()
    try:
        start = lines.index("[metadata]")
    except ValueError as exc:
        raise ValueError("missing [metadata]") from exc
    end = next(
        (i for i in range(start + 1, len(lines)) if lines[i].startswith("[")),
        len(lines),
    )

    kept: list[str] = []
    for line in lines[start + 1 : end]:
        key = line.split("=", 1)[0].strip() if "=" in line else ""
        if key in EXPLICIT_FIELDS:
            continue
        if key == "difficulty":
            kept.append(f'difficulty = "{row["construct_difficulty"]}"')
            for field in EXPLICIT_FIELDS:
                kept.append(f"{field} = {toml_value(row[field])}")
            continue
        if key == "tags":
            raw = line.split("=", 1)[1].strip()
            tags = json.loads(raw)
            tags = [
                tag
                for tag in tags
                if tag not in {"easy", "medium", "hard", "uncalibrated"}
            ]
            tags.insert(1 if tags else 0, row["construct_difficulty"])
            kept.append(
                "tags = " + json.dumps(tags, ensure_ascii=False, separators=(", ", ": "))
            )
            continue
        kept.append(line)

    if not any(line.startswith("difficulty = ") for line in kept):
        raise ValueError("missing metadata difficulty field")
    out = [*lines[: start + 1], *kept, *lines[end:]]
    return "\n".join(out) + "\n"


def payload(rows: dict[str, dict[str, Any]]) -> dict[str, Any]:
    counts = Counter(row["construct_difficulty"] for row in rows.values())
    empirical = Counter(row["empirical_band"] for row in rows.values())
    return {
        "kind": "v1.0.1_item_metadata",
        "benchmark_version": "benchmark-v1.0.1",
        "semantics": {
            "construct_difficulty": (
                "Author-designed task difficulty; frozen independently of model results."
            ),
            "empirical_band": (
                "Observed calibration location for the frozen v1.0.1 system panel."
            ),
            "calibration_status": (
                "Whether the task lies inside the current calibration ladder."
            ),
            "difficulty": "Compatibility alias for construct_difficulty in task.toml.",
        },
        "difficulty_weights": CONSTRUCT_WEIGHTS,
        "weight_policy": (
            "Transparent ordinal construct weights; not estimated from leaderboard "
            "outcomes or IRT."
        ),
        "construct_counts": {
            key: int(counts.get(key, 0)) for key in ("easy", "medium", "hard")
        },
        "empirical_counts": {
            key: int(empirical.get(key, 0))
            for key in ("easy", "medium", "hard", "out_of_range")
        },
        "items": [rows[task] for task in BANK_62],
    }


def verify_task_toml(task: str, row: dict[str, Any], text: str) -> None:
    data = tomllib.loads(text)
    meta = data["metadata"]
    for key in ("difficulty", *EXPLICIT_FIELDS):
        expected = row["construct_difficulty"] if key == "difficulty" else row[key]
        if meta.get(key) != expected:
            raise ValueError(f"{task}: {key}={meta.get(key)!r} != {expected!r}")
    tags = meta.get("tags") or []
    if row["construct_difficulty"] not in tags:
        raise ValueError(f"{task}: construct difficulty missing from tags")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--write", action="store_true")
    args = parser.parse_args()
    rows = item_metadata()
    counts = Counter(row["construct_difficulty"] for row in rows.values())
    print("construct_counts", dict(counts))
    print("weights", CONSTRUCT_WEIGHTS)
    if dict(counts) != EXPECTED_CONSTRUCT_COUNTS:
        raise SystemExit("unexpected construct counts")

    changed = 0
    rendered: dict[str, str] = {}
    for task in BANK_62:
        path = TASKS / task / "task.toml"
        old = path.read_text(encoding="utf-8")
        new = replace_metadata(old, rows[task])
        verify_task_toml(task, rows[task], new)
        rendered[task] = new
        changed += int(old != new)
    print(f"task_toml_changed {changed}/{len(BANK_62)}")

    if args.write:
        for task, text in rendered.items():
            (TASKS / task / "task.toml").write_text(text, encoding="utf-8")
        OUT.write_text(
            json.dumps(payload(rows), ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        print(f"wrote {OUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
