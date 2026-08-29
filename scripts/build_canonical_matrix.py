"""Unique-key coverage matrix from frozen locks + completeness overlays.

Does not overwrite jobs/locked-core.json, locked-core-k3.json, or
locked-hard-release-k3.json.

    python scripts/build_canonical_matrix.py
    python scripts/build_canonical_matrix.py --write
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from models_lock import load_lock, models  # noqa: E402
from rerun_gemma4b import trial_exception_type  # noqa: E402
from run_locked import (  # noqa: E402
    CORE_OUT,
    HARD_FLOOR_OUT,
    HARD_RELEASE_OUT,
    K3_OUT,
    UPPER_BASE_OUT,
    attempt_is_valid,
    attempt_of,
)
from score_standard import ATOMS, API_FLAKE_EXCEPTIONS, RATE_LIMIT_EXCEPTIONS  # noqa: E402
from item_metadata import CONSTRUCT_WEIGHTS, construct_metadata  # noqa: E402
from task_sets import HARD_RELEASE_15, MAIN_47  # noqa: E402

BANK_62 = MAIN_47 + HARD_RELEASE_15
GEMMA_RERUN = ROOT / "jobs" / "locked-gemma4b-rerun-k3.json"
INFRA_RERUN = ROOT / "jobs" / "locked-infra-rerun-k3.json"
SUMMARY_OUT = ROOT / "results" / "canonical-coverage.json"
ROWS_OUT = ROOT / "jobs" / "locked-coverage-k3.json"
SUPPLEMENT_LOCK = ROOT / "models.supplement-2026-08.yaml"
SUPPLEMENT_OUT = ROOT / "jobs" / "supplement-2026-08-k3.json"
FROZEN_LOCKS = (
    CORE_OUT,
    K3_OUT,
    HARD_RELEASE_OUT,
    SUPPLEMENT_LOCK,
    SUPPLEMENT_OUT,
)

DIRTY_EXCEPTIONS = frozenset(
    RATE_LIMIT_EXCEPTIONS | API_FLAKE_EXCEPTIONS | {"AuthenticationError"}
)

SHORT_LABEL = {
    "llama-3.2-3b-instruct": "Llama-3.2-3B",
    "ministral-3b-2512": "Ministral-3B",
    "gemma-3-4b-it": "Gemma-3-4B",
    "qwen3-8b": "Qwen3-8B",
    "ministral-8b-2512": "Ministral-8B",
    "granite-4.1-8b": "Granite-4.1-8B",
    "qwen3.5-9b": "Qwen3.5-9B",
    "gemma-3-12b-it": "Gemma-3-12B",
    "qwen3-14b": "Qwen3-14B",
    "ministral-14b-2512": "Ministral-14B",
    "qwen3.8-27b": "Qwen3.8-27B",
    "qwen3.6-35b-a3b": "Qwen3.6-35B-A3B",
    "gpt-oss-20b": "GPT-OSS-20B",
    "nemotron-3.5-lightning": "Nemotron-3.5-Lightning",
    "glm-4.7-flash": "GLM-4.7-Flash",
    "gemma-4-26b-a4b-it": "Gemma-4-26B-A4B",
}
SHORT_ATOM = {
    "loc": "Loc",
    "edit": "Edit",
    "testgen": "Testgen",
    "repro": "Repro",
    "review": "Review",
}

LAYERS = (
    ("core", K3_OUT),
    ("upper_base", UPPER_BASE_OUT),
    ("hard_release", HARD_RELEASE_OUT),
    ("hard_floor", HARD_FLOOR_OUT),
    ("gemma4b_rerun", GEMMA_RERUN),
    ("infra_rerun", INFRA_RERUN),
    ("supplement_2026_08", SUPPLEMENT_OUT),
)


def load_supplement_lock() -> dict[str, Any]:
    try:
        import yaml  # type: ignore[import-untyped]
    except ImportError as exc:
        raise SystemExit("PyYAML is required to read the supplement lock") from exc
    data = yaml.safe_load(SUPPLEMENT_LOCK.read_text(encoding="utf-8"))
    if not isinstance(data, dict) or not data.get("frozen"):
        raise SystemExit(f"invalid supplement lock: {SUPPLEMENT_LOCK}")
    rows = list(data.get("models") or [])
    if len(rows) != 4 or not data.get("enters_v1_0_1_canonical"):
        raise SystemExit("supplement lock must publish exactly four canonical models")
    return data


def canonical_models(lock: dict[str, Any] | None = None) -> list[dict[str, Any]]:
    rows = [*models(lock or load_lock()), *load_supplement_lock()["models"]]
    ids = [str(row["id"]) for row in rows]
    if len(ids) != len(set(ids)):
        raise SystemExit("duplicate model id across canonical locks")
    return rows


def trial_key(row: dict[str, Any]) -> tuple[str, str, int]:
    return (str(row["lock_id"]), str(row["task"]), attempt_of(row))


def load_rows(path: Path) -> list[dict[str, Any]]:
    if not path.is_file():
        return []
    data = json.loads(path.read_text(encoding="utf-8"))
    return [dict(r) for r in (data.get("rows") or [])]


def in_bank(row: dict[str, Any]) -> bool:
    return (
        bool(row.get("lock_id"))
        and row.get("task") in BANK_62
        and attempt_of(row) in (1, 2, 3)
    )


def overlay(
    by_key: dict[tuple[str, str, int], dict[str, Any]],
    incoming: list[dict[str, Any]],
) -> int:
    n = 0
    for row in incoming:
        if not in_bank(row):
            continue
        by_key[trial_key(row)] = dict(row)
        n += 1
    return n


def merge_rows(
    layers: list[tuple[str, list[dict[str, Any]]]] | None = None,
) -> tuple[list[dict[str, Any]], dict[str, int]]:
    by_key: dict[tuple[str, str, int], dict[str, Any]] = {}
    applied: dict[str, int] = {}
    if layers is None:
        pairs = [(name, load_rows(path)) for name, path in LAYERS]
    else:
        pairs = layers
    for name, rows in pairs:
        applied[name] = overlay(by_key, rows)
    out = [by_key[k] for k in sorted(by_key)]
    return out, applied


def e2e_hit(row: dict[str, Any]) -> int:
    return int(row.get("atomic_correct") == 1 and row.get("termination") == "clean")


def model_score(rows: list[dict[str, Any]], lock_id: str) -> dict[str, Any]:
    metadata = construct_metadata()
    mine = [r for r in rows if r.get("lock_id") == lock_id and in_bank(r)]
    by_task: dict[str, dict[int, dict[str, Any]]] = defaultdict(dict)
    for row in mine:
        if attempt_is_valid(row):
            by_task[row["task"]][attempt_of(row)] = row
    p_atomic: dict[str, float] = {}
    p_e2e: dict[str, float] = {}
    incomplete = 0
    for task in BANK_62:
        attempts = by_task.get(task) or {}
        if len(attempts) != 3:
            incomplete += 1
            continue
        p_atomic[task] = sum(int(attempts[a]["atomic_correct"]) for a in (1, 2, 3)) / 3
        p_e2e[task] = sum(e2e_hit(attempts[a]) for a in (1, 2, 3)) / 3
    skills_atomic: dict[str, float | None] = {}
    skills_e2e: dict[str, float | None] = {}
    skills_atomic_weighted: dict[str, float | None] = {}
    skills_e2e_weighted: dict[str, float | None] = {}
    for prefix, _label in ATOMS.items():
        names = [t for t in BANK_62 if t.startswith(f"{prefix}-") and t in p_atomic]
        skills_atomic[prefix] = (
            sum(p_atomic[t] for t in names) / len(names) if names else None
        )
        skills_e2e[prefix] = (
            sum(p_e2e[t] for t in names) / len(names) if names else None
        )
        weight_sum = sum(float(metadata[t]["difficulty_weight"]) for t in names)
        skills_atomic_weighted[prefix] = (
            sum(float(metadata[t]["difficulty_weight"]) * p_atomic[t] for t in names)
            / weight_sum
            if weight_sum
            else None
        )
        skills_e2e_weighted[prefix] = (
            sum(float(metadata[t]["difficulty_weight"]) * p_e2e[t] for t in names)
            / weight_sum
            if weight_sum
            else None
        )
    atomic_vals = [v for v in skills_atomic.values() if v is not None]
    e2e_vals = [v for v in skills_e2e.values() if v is not None]
    weighted_atomic_vals = [
        v for v in skills_atomic_weighted.values() if v is not None
    ]
    weighted_e2e_vals = [v for v in skills_e2e_weighted.values() if v is not None]
    scored = [r for r in mine if attempt_is_valid(r)]
    atomic_ok = sum(int(r["atomic_correct"]) for r in scored)
    e2e_ok = sum(e2e_hit(r) for r in scored)
    halt = sum(
        1
        for r in scored
        if r.get("atomic_correct") == 1 and r.get("termination") != "clean"
    )
    return {
        "lock_id": lock_id,
        "n_rows": len(mine),
        "n_scored": len(scored),
        "n_incomplete_tasks": incomplete,
        "atomic_ok": atomic_ok,
        "e2e_ok": e2e_ok,
        "halt_unfinished_atomic": halt,
        "atomic_macro": sum(atomic_vals) / len(atomic_vals) if atomic_vals else None,
        "e2e_macro": sum(e2e_vals) / len(e2e_vals) if e2e_vals else None,
        "skills_atomic": skills_atomic,
        "skills_e2e": skills_e2e,
        "artifact_score": (
            100 * sum(weighted_atomic_vals) / len(weighted_atomic_vals)
            if weighted_atomic_vals
            else None
        ),
        "clean_score": (
            100 * sum(weighted_e2e_vals) / len(weighted_e2e_vals)
            if weighted_e2e_vals
            else None
        ),
        "skills_atomic_weighted": skills_atomic_weighted,
        "skills_e2e_weighted": skills_e2e_weighted,
    }


def remaining_dirty(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    found: list[dict[str, Any]] = []
    for row in rows:
        job = row.get("job")
        if not isinstance(job, str):
            continue
        exc = trial_exception_type(job)
        if exc not in DIRTY_EXCEPTIONS:
            continue
        found.append(
            {
                "lock_id": row.get("lock_id"),
                "task": row.get("task"),
                "attempt": attempt_of(row),
                "exception": exc,
                "termination": row.get("termination"),
            }
        )
    return found


def compact_then_upper(
    lock: dict[str, Any], scores: dict[str, dict[str, Any]]
) -> list[str]:
    ranked = [m["id"] for m in canonical_models(lock)]
    ranked.sort(
        key=lambda i: (
            -(scores[i]["artifact_score"] or 0.0),
            -(scores[i]["atomic_macro"] or 0.0),
            -(scores[i]["atomic_ok"] or 0),
            i,
        )
    )
    return ranked


def fmt3(value: float | None) -> str:
    if value is None:
        return "—"
    return f"{value:.3f}"


def markdown_table(
    lock: dict[str, Any], scores: dict[str, dict[str, Any]], *, e2e: bool
) -> str:
    order = compact_then_upper(lock, scores)
    skill_key = "skills_e2e" if e2e else "skills_atomic"
    macro_key = "e2e_macro" if e2e else "atomic_macro"
    ok_key = "e2e_ok" if e2e else "atomic_ok"
    lines = [
        "| 模型 | Loc | Edit | Testgen | Repro | Review | **宏平均** | 微平均 |",
        "|---|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for lock_id in order:
        row = scores[lock_id]
        skills = row[skill_key]
        macro = row[macro_key]
        label = SHORT_LABEL.get(lock_id, lock_id)
        if lock_id == "qwen3.5-9b" and not e2e:
            macro_cell = f"**{fmt3(macro)}**"
        else:
            macro_cell = fmt3(macro)
        micro = f"{fmt3((row[ok_key] or 0) / 186)}（{row[ok_key]}/186）"
        cells = " | ".join(fmt3(skills[p]) for p in SHORT_ATOM)
        lines.append(f"| {label} | {cells} | {macro_cell} | {micro} |")
    return "\n".join(lines)


def build_summary(
    rows: list[dict[str, Any]],
    applied: dict[str, int],
    dirty: list[dict[str, Any]] | None,
) -> dict[str, Any]:
    lock = load_lock()
    subjects = canonical_models(lock)
    scores = {m["id"]: model_score(rows, m["id"]) for m in subjects}
    order = compact_then_upper(lock, scores)
    halt = sum(scores[i]["halt_unfinished_atomic"] for i in order)
    incomplete = sum(scores[i]["n_incomplete_tasks"] for i in order)
    n_scored = sum(scores[i]["n_scored"] for i in order)
    payload = {
        "kind": "canonical_coverage_k3",
        "published": True,
        "enters_official_mean": True,
        "benchmark_version": "benchmark-v1.0.1",
        "overwrites_locked_core": False,
        "overwrites_locked_core_k3": False,
        "overwrites_locked_hard_release_k3": False,
        "note": (
            "Unique-key merge of frozen Base + official Hard + Hard-floor "
            "+ Gemma-4B 429 replacements + 13 infra-dirty replacements "
            "+ the four-model full-coverage source. "
            "remaining_dirty=0. This is the v1.0.1 canonical matrix. "
            "Tag benchmark-v1.0.1 is on the freeze commit. Frozen v1.0 locks unchanged."
        ),
        "n_models": len(subjects),
        "n_tasks": 62,
        "n_trials_expected": len(subjects) * 62 * 3,
        "n_rows": len(rows),
        "n_scored": n_scored,
        "n_incomplete_tasks": incomplete,
        "halt_unfinished_atomic": halt,
        "score_method": {
            "range": [0, 100],
            "construct_weights": CONSTRUCT_WEIGHTS,
            "weight_policy": "author-designed ordinal tiers; not fitted to results",
            "aggregation": "difficulty-weighted within skill, then five-skill macro",
            "primary": "artifact_score",
            "secondary": "clean_score",
        },
        "layers_applied": applied,
        "models": [],
        "remaining_dirty": dirty,
    }
    for lock_id in order:
        row = scores[lock_id]
        model = next(m for m in subjects if m["id"] == lock_id)
        payload["models"].append(
            {
                "lock_id": lock_id,
                "display": SHORT_LABEL.get(lock_id, lock_id),
                "group": model.get("group"),
                "n_scored": row["n_scored"],
                "n_incomplete_tasks": row["n_incomplete_tasks"],
                "atomic_ok": row["atomic_ok"],
                "e2e_ok": row["e2e_ok"],
                "atomic_macro": row["atomic_macro"],
                "e2e_macro": row["e2e_macro"],
                "artifact_score": row["artifact_score"],
                "clean_score": row["clean_score"],
                "score_gap": (
                    None
                    if row["artifact_score"] is None or row["clean_score"] is None
                    else row["artifact_score"] - row["clean_score"]
                ),
                "gap": (
                    None
                    if row["atomic_macro"] is None or row["e2e_macro"] is None
                    else row["atomic_macro"] - row["e2e_macro"]
                ),
                "skills_atomic": row["skills_atomic"],
                "skills_e2e": row["skills_e2e"],
                "skills_atomic_weighted": row["skills_atomic_weighted"],
                "skills_e2e_weighted": row["skills_e2e_weighted"],
                "halt_unfinished_atomic": row["halt_unfinished_atomic"],
            }
        )
    return payload


def assert_not_frozen(path: Path) -> None:
    resolved = path.resolve()
    for frozen in FROZEN_LOCKS:
        if resolved == frozen.resolve():
            raise SystemExit(f"refusing to write frozen lock {frozen}")


def write_outputs(rows: list[dict[str, Any]], summary: dict[str, Any]) -> None:
    assert_not_frozen(SUMMARY_OUT)
    assert_not_frozen(ROWS_OUT)
    SUMMARY_OUT.parent.mkdir(parents=True, exist_ok=True)
    SUMMARY_OUT.write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    payload = {
        "kind": "locked_coverage_k3",
        "published": False,
        "overwrites_locked_core": False,
        "overwrites_locked_core_k3": False,
        "overwrites_locked_hard_release_k3": False,
        "n_rows": len(rows),
        "rows": rows,
    }
    ROWS_OUT.parent.mkdir(parents=True, exist_ok=True)
    ROWS_OUT.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--write", action="store_true")
    parser.add_argument("--skip-dirty", action="store_true")
    args = parser.parse_args()
    rows, applied = merge_rows()
    dirty = None if args.skip_dirty else remaining_dirty(rows)
    lock = load_lock()
    scores = {m["id"]: model_score(rows, m["id"]) for m in canonical_models(lock)}
    summary = build_summary(rows, applied, dirty)
    print("===== CANONICAL COVERAGE =====")
    print(
        f"rows {len(rows)}  scored {summary['n_scored']}  incomplete {summary['n_incomplete_tasks']}"
    )
    print(f"halt {summary['halt_unfinished_atomic']}  layers {applied}")
    if dirty is not None:
        print(f"remaining_dirty {len(dirty)}")
    print("\n## Atomic\n")
    print(markdown_table(lock, scores, e2e=False))
    print("\n## E2E\n")
    print(markdown_table(lock, scores, e2e=True))
    if args.write:
        write_outputs(rows, summary)
        print(f"\nwrote {SUMMARY_OUT}")
        print(f"wrote {ROWS_OUT} (did not touch frozen locks)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
