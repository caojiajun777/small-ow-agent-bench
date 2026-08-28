"""Run the frozen four-model benchmark-v1.0.1 supplement.

The original 12-model lock and reports are never modified. Every formal cell
is three independent Harbor ``-k 1`` sandboxes, matching the published k=3
administration. The runner is resumable by (model, task, attempt).

    python scripts/run_supplement.py --full
    python scripts/run_supplement.py --run --protocol
    python scripts/run_supplement.py --run --formal
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import run_locked as locked  # noqa: E402
from models_lock import llm_kwargs  # noqa: E402
from score_standard import ATOMS, atom_of  # noqa: E402
from task_sets import HARD_RELEASE_15, MAIN_47, PROTOCOL_SMOKE  # noqa: E402

LOCK_PATH = ROOT / "models.supplement-2026-08.yaml"
PROTOCOL_OUT = ROOT / "jobs" / "supplement-2026-08-protocol.json"
FORMAL_OUT = ROOT / "jobs" / "supplement-2026-08-k3.json"
PROTOCOL_TASKS = PROTOCOL_SMOKE + ("loc-member-discount",)
FORMAL_TASKS = MAIN_47 + HARD_RELEASE_15
ATTEMPTS = (1, 2, 3)
REQUIRED_PARAMETERS = {"max_tokens", "reasoning", "temperature"}


def load_supplement(path: Path = LOCK_PATH) -> dict[str, Any]:
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict) or not data.get("frozen"):
        raise SystemExit(f"invalid or unfrozen supplement lock: {path}")
    models = data.get("models") or []
    if len(models) != 4:
        raise SystemExit(f"supplement lock must contain 4 models, got {len(models)}")
    ids = [row.get("id") for row in models]
    if len(ids) != len(set(ids)):
        raise SystemExit("duplicate model id in supplement lock")
    inference = data.get("inference") or {}
    expected = {"temperature": 0.0, "top_p": 1.0, "max_tokens": 4096}
    for key, value in expected.items():
        if inference.get(key) != value:
            raise SystemExit(f"supplement inference.{key} must be {value!r}")
    for row in models:
        for key in (
            "id",
            "display",
            "group",
            "batch",
            "catalog_id",
            "canonical_slug",
            "openrouter_id",
            "openrouter_provider",
            "quantization",
            "context_length",
            "max_completion_tokens",
            "reasoning",
        ):
            if row.get(key) in (None, ""):
                raise SystemExit(f"{row.get('id') or '<unknown>'} missing {key}")
        if not str(row["openrouter_id"]).startswith("openrouter/"):
            raise SystemExit(f"{row['id']} must use an explicit OpenRouter model id")
        extra = llm_kwargs(row, data).get("extra_body") or {}
        provider = extra.get("provider") or {}
        if provider.get("order") != [row["openrouter_provider"]]:
            raise SystemExit(f"{row['id']} provider pin was not preserved")
        if provider.get("allow_fallbacks") is not False:
            raise SystemExit(f"{row['id']} must disable provider fallback")
        reasoning = extra.get("reasoning") or {}
        if row["reasoning"] == "mandatory_low":
            if (
                reasoning.get("effort") != "low"
                or reasoning.get("exclude") is not False
            ):
                raise SystemExit(
                    f"{row['id']} must pin mandatory reasoning to low+retained"
                )
        elif (
            reasoning.get("enabled") is not False
            or reasoning.get("exclude") is not True
        ):
            raise SystemExit(f"{row['id']} must disable and exclude reasoning")
    scope = data.get("scope") or {}
    if tuple(scope.get("protocol_tasks") or ()) != PROTOCOL_TASKS:
        raise SystemExit("supplement protocol-task lock does not match runner")
    if int(scope.get("n_protocol_trials") or 0) != len(models) * len(PROTOCOL_TASKS):
        raise SystemExit("supplement protocol trial-count lock is inconsistent")
    if int(scope.get("n_formal_tasks") or 0) != len(FORMAL_TASKS):
        raise SystemExit("supplement task-count lock does not match task_sets.py")
    if int(scope.get("n_formal_trials") or 0) != len(models) * len(FORMAL_TASKS) * 3:
        raise SystemExit("supplement trial-count lock is inconsistent")
    return data


def select_models(
    lock: dict[str, Any], wanted: list[str] | None
) -> list[dict[str, Any]]:
    rows = list(lock["models"])
    if not wanted:
        return rows
    aliases = set(wanted)
    selected = [
        row
        for row in rows
        if row["id"] in aliases
        or row["catalog_id"] in aliases
        or row["openrouter_id"] in aliases
    ]
    missing = aliases - {
        value
        for row in selected
        for value in (row["id"], row["catalog_id"], row["openrouter_id"])
    }
    if missing:
        raise SystemExit("unknown supplement model(s): " + ", ".join(sorted(missing)))
    return selected


def plan_cells(
    subjects: list[dict[str, Any]], names: tuple[str, ...], attempts: tuple[int, ...]
) -> list[tuple[dict[str, Any], str, int]]:
    return [
        (model, name, attempt)
        for model in subjects
        for name in names
        for attempt in attempts
    ]


def _load_rows(path: Path) -> list[dict[str, Any]]:
    if not path.is_file():
        return []
    return list(json.loads(path.read_text(encoding="utf-8")).get("rows") or [])


def _model_record(row: dict[str, Any]) -> dict[str, Any]:
    return {
        key: row.get(key)
        for key in (
            "id",
            "display",
            "size",
            "hf_id",
            "hf_revision",
            "catalog_id",
            "canonical_slug",
            "openrouter_id",
            "openrouter_provider",
            "quantization",
            "context_length",
            "max_completion_tokens",
            "reasoning",
        )
    }


def _protocol_passes(
    rows: list[dict[str, Any]], subjects: list[dict[str, Any]]
) -> tuple[bool, dict[str, bool]]:
    by_key = {(r["lock_id"], r["task"]): r for r in rows}
    passed: dict[str, bool] = {}
    for model in subjects:
        passed[model["id"]] = all(
            (by_key.get((model["id"], task)) or {}).get("atomic_correct") == 1
            and (by_key.get((model["id"], task)) or {}).get("termination") == "clean"
            for task in PROTOCOL_TASKS
        )
    return all(passed.values()), passed


def _protocol_ready(
    rows: list[dict[str, Any]], subjects: list[dict[str, Any]]
) -> tuple[bool, dict[str, bool]]:
    """Transport/grammar gate; task and halt misses remain benchmark signals."""
    by_key = {(r["lock_id"], r["task"]): r for r in rows}
    ready: dict[str, bool] = {}
    for model in subjects:
        task_ready = []
        for task in PROTOCOL_TASKS:
            row = by_key.get((model["id"], task)) or {}
            trace = _trace_stats(row)
            task_ready.append(
                row.get("termination") in locked.SCORED_TERMINATIONS
                and row.get("atomic_correct") is not None
                and not row.get("reason")
                and (bool(trace.get("finished")) or int(trace.get("n_shell") or 0) > 0)
            )
        ready[model["id"]] = all(task_ready)
    return all(ready.values()), ready


def _trace_stats(row: dict[str, Any]) -> dict[str, Any]:
    keys = ("finished", "n_turns", "n_shell", "n_parse_fail")
    if all(key in row for key in keys):
        return {key: row.get(key) for key in keys}
    job_value = row.get("job")
    if not job_value:
        return {}
    job = Path(str(job_value))
    trials = [path for path in job.iterdir() if path.is_dir()]
    if not trials:
        return {}
    path = trials[0] / "agent" / "compact-shell.json"
    if not path.is_file():
        return {}
    data = json.loads(path.read_text(encoding="utf-8"))
    return {key: data.get(key) for key in keys}


def write_protocol(
    rows: list[dict[str, Any]], lock: dict[str, Any], subjects: list[dict[str, Any]]
) -> None:
    _, passed = _protocol_passes(rows, subjects)
    _, ready = _protocol_ready(rows, subjects)
    by_key = {(r["lock_id"], r["task"]): r for r in rows}
    report = {
        "kind": "supplement_2026_08_protocol",
        "published": False,
        "benchmark_version": lock["benchmark_version"],
        "lock": str(LOCK_PATH),
        "pass_rule": "all protocol tasks atomic_correct=1 and termination=clean",
        "formal_gate": (
            "all protocol tasks scored with no infra reason and at least one parsed "
            "shell/finish action; task misses and failure to halt remain scored signals"
        ),
        "models": [_model_record(row) for row in subjects],
        "subjects": [
            {
                "id": model["id"],
                "protocol_pass": passed[model["id"]],
                "protocol_ready": ready[model["id"]],
                "tasks": {
                    task: {
                        key: (by_key.get((model["id"], task)) or {}).get(key)
                        for key in ("atomic_correct", "termination", "job", "reason")
                    }
                    for task in PROTOCOL_TASKS
                },
            }
            for model in subjects
        ],
        "rows": rows,
    }
    PROTOCOL_OUT.parent.mkdir(parents=True, exist_ok=True)
    PROTOCOL_OUT.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(f"wrote {PROTOCOL_OUT}", flush=True)


def _cell(rows: list[dict[str, Any]], model_id: str, task: str) -> dict[str, Any]:
    attempts = [
        row
        for row in rows
        if row.get("lock_id") == model_id and row.get("task") == task
    ]
    valid = {
        locked.attempt_of(row): row
        for row in attempts
        if locked.attempt_is_valid(row) and locked.attempt_of(row) in ATTEMPTS
    }
    complete = len(valid) == len(ATTEMPTS)
    atomic = None
    clean = None
    if complete:
        atomic = sum(int(valid[a]["atomic_correct"]) for a in ATTEMPTS) / 3
        clean = (
            sum(
                int(
                    valid[a]["atomic_correct"] == 1
                    and valid[a]["termination"] == "clean"
                )
                for a in ATTEMPTS
            )
            / 3
        )
    return {
        "lock_id": model_id,
        "task": task,
        "atom": atom_of(task),
        "n_valid": len(valid),
        "incomplete": not complete,
        "p_atomic": atomic,
        "p_e2e": clean,
        "infra_count": sum(
            int(
                row.get("termination") == "infra"
                or row.get("reason") in {"infra", "no_job"}
            )
            for row in attempts
        ),
    }


def write_formal(
    rows: list[dict[str, Any]], lock: dict[str, Any], subjects: list[dict[str, Any]]
) -> None:
    cells = [
        _cell(rows, model["id"], task) for model in subjects for task in FORMAL_TASKS
    ]
    metrics: dict[str, Any] = {}
    for model in subjects:
        model_cells = [cell for cell in cells if cell["lock_id"] == model["id"]]
        skills: dict[str, dict[str, float | None]] = {}
        for prefix, label in ATOMS.items():
            atom_cells = [cell for cell in model_cells if cell["atom"] == prefix]
            atomic_vals = [
                cell["p_atomic"] for cell in atom_cells if cell["p_atomic"] is not None
            ]
            e2e_vals = [
                cell["p_e2e"] for cell in atom_cells if cell["p_e2e"] is not None
            ]
            skills[label] = {
                "atomic": sum(atomic_vals) / len(atomic_vals)
                if len(atomic_vals) == len(atom_cells)
                else None,
                "e2e": sum(e2e_vals) / len(e2e_vals)
                if len(e2e_vals) == len(atom_cells)
                else None,
            }
        atomic_skill = [value["atomic"] for value in skills.values()]
        e2e_skill = [value["e2e"] for value in skills.values()]
        metrics[model["id"]] = {
            "n_complete_cells": sum(not cell["incomplete"] for cell in model_cells),
            "n_cells": len(model_cells),
            "five_skill_macro_atomic": (
                sum(atomic_skill) / len(atomic_skill)
                if all(v is not None for v in atomic_skill)
                else None
            ),
            "five_skill_macro_e2e": (
                sum(e2e_skill) / len(e2e_skill)
                if all(v is not None for v in e2e_skill)
                else None
            ),
            "task_micro_atomic": (
                sum(cell["p_atomic"] for cell in model_cells) / len(model_cells)
                if all(cell["p_atomic"] is not None for cell in model_cells)
                else None
            ),
            "task_micro_e2e": (
                sum(cell["p_e2e"] for cell in model_cells) / len(model_cells)
                if all(cell["p_e2e"] is not None for cell in model_cells)
                else None
            ),
            "skills": skills,
        }
    report = {
        "kind": "supplement_2026_08_k3",
        "published": True,
        "enters_v1_0_1_canonical": True,
        "benchmark_version": lock["benchmark_version"],
        "lock": str(LOCK_PATH),
        "k": 3,
        "tasks": list(FORMAL_TASKS),
        "n_scope_cells": len(cells),
        "n_incomplete_cells": sum(cell["incomplete"] for cell in cells),
        "models": [_model_record(row) for row in subjects],
        "metrics": metrics,
        "cells": cells,
        "rows": rows,
    }
    FORMAL_OUT.parent.mkdir(parents=True, exist_ok=True)
    FORMAL_OUT.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(
        f"wrote {FORMAL_OUT}: complete_cells={len(cells) - report['n_incomplete_cells']}/{len(cells)}",
        flush=True,
    )


def _read_env_file() -> None:
    if not locked.ENV.is_file():
        raise SystemExit(f"missing {locked.ENV}")
    for raw in locked.ENV.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip())


def _get_json(url: str, key: str) -> dict[str, Any]:
    request = urllib.request.Request(
        url,
        headers={
            "Authorization": f"Bearer {key}",
            "User-Agent": "small-ow-agent-bench",
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            return json.loads(response.read().decode("utf-8"))
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
        raise SystemExit(f"OpenRouter preflight failed for {url}: {exc}") from exc


def catalog_preflight(subjects: list[dict[str, Any]]) -> None:
    _read_env_file()
    key = os.environ.get("OPENROUTER_API_KEY")
    if not key:
        raise SystemExit("OPENROUTER_API_KEY is not set")
    catalog = _get_json("https://openrouter.ai/api/v1/models", key).get("data") or []
    by_id = {row.get("id"): row for row in catalog}
    for model in subjects:
        live = by_id.get(model["catalog_id"])
        if not live:
            raise SystemExit(f"catalog missing {model['catalog_id']}")
        if live.get("canonical_slug") != model["canonical_slug"]:
            raise SystemExit(
                f"{model['id']} canonical slug drift: {live.get('canonical_slug')!r}"
            )
        if int(live.get("context_length") or 0) < int(model["context_length"]):
            raise SystemExit(f"{model['id']} context length regressed")
        endpoint_data = (
            _get_json(
                f"https://openrouter.ai/api/v1/models/{model['catalog_id']}/endpoints",
                key,
            ).get("data")
            or {}
        )
        endpoints = endpoint_data.get("endpoints") or []
        matches = [
            endpoint
            for endpoint in endpoints
            if endpoint.get("provider_name") == model["openrouter_provider"]
            and str(endpoint.get("quantization") or "").lower()
            == str(model["quantization"]).lower()
            and int(endpoint.get("max_completion_tokens") or 0) >= 4096
            and REQUIRED_PARAMETERS.issubset(
                set(endpoint.get("supported_parameters") or [])
            )
        ]
        if not matches:
            raise SystemExit(
                f"{model['id']} pinned {model['openrouter_provider']}/{model['quantization']} "
                "endpoint is unavailable or parameter-incompatible"
            )
        print(
            f"preflight ok {model['id']}: {model['openrouter_provider']}/"
            f"{model['quantization']} context={live['context_length']}",
            flush=True,
        )


def local_preflight(lock: dict[str, Any], subjects: list[dict[str, Any]]) -> None:
    _read_env_file()
    for key in ("OPENROUTER_API_KEY", "NOVITA_API_KEY"):
        value = os.environ.get(key, "")
        if not value or "your-" in value:
            raise SystemExit(f"{key} is not configured")
    missing_tasks = [
        task
        for task in PROTOCOL_TASKS + FORMAL_TASKS
        if not (locked.TASKS / task / "task.toml").is_file()
    ]
    if missing_tasks:
        raise SystemExit("missing tasks: " + ", ".join(missing_tasks))
    if not subjects:
        raise SystemExit("no supplement models selected")
    if lock.get("overwrites_v1") is not False:
        raise SystemExit("supplement must not overwrite v1 outputs")


def _run_cells(
    rows: list[dict[str, Any]],
    cells: list[tuple[dict[str, Any], str, int]],
    lock: dict[str, Any],
    writer,
    subjects: list[dict[str, Any]],
    *,
    force: bool,
) -> int:
    code = 0
    started = False
    for model, task, attempt in cells:
        previous = locked._find_k3_row(rows, model["id"], task, attempt)
        current_version = (lock.get("harness") or {}).get("agent_version")
        stale = previous and (
            previous.get("agent_version") != current_version
            or previous.get("openrouter_provider") != model["openrouter_provider"]
        )
        if stale:
            print(
                f"rerun stale {model['id']} {task} a{attempt}: "
                f"agent={previous.get('agent_version')}->{current_version} "
                f"provider={previous.get('openrouter_provider')}->"
                f"{model['openrouter_provider']}",
                flush=True,
            )
            previous = None
        if locked.trial_is_done(previous, force=force):
            print(f"skip done {model['id']} {task} a{attempt}", flush=True)
            continue
        if started:
            time.sleep(8)
        else:
            print("wait 8s before first sandbox create", flush=True)
            time.sleep(8)
            started = True
        print(
            f"===== supplement {model['id']} {task} attempt={attempt} =====", flush=True
        )
        record = locked._run_k3_slot(model, task, attempt, lock, previous)
        record["benchmark_version"] = lock["benchmark_version"]
        record.update(_trace_stats(record))
        locked._upsert_k3(rows, record)
        # Reports always retain the full four-model scope, even when --model
        # is used for a targeted resume.
        writer(rows, lock, list(lock["models"]))
        if record.get("termination") == "infra" or record.get("reason") in {
            "infra",
            "no_job",
        }:
            code = 1
    return code


def _pending(
    rows: list[dict[str, Any]],
    cells: list[tuple[dict[str, Any], str, int]],
    lock: dict[str, Any],
    *,
    force: bool,
) -> int:
    current_version = (lock.get("harness") or {}).get("agent_version")
    pending = 0
    for model, task, attempt in cells:
        previous = locked._find_k3_row(rows, model["id"], task, attempt)
        if previous and (
            previous.get("agent_version") != current_version
            or previous.get("openrouter_provider") != model["openrouter_provider"]
        ):
            previous = None
        pending += not locked.trial_is_done(previous, force=force)
    return pending


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    stage = parser.add_mutually_exclusive_group()
    stage.add_argument(
        "--protocol", action="store_true", help="two smoke tasks per model"
    )
    stage.add_argument("--formal", action="store_true", help="62 tasks x k=3")
    stage.add_argument("--full", action="store_true", help="protocol, then formal")
    parser.add_argument(
        "--run", action="store_true", help="execute; otherwise print plan"
    )
    parser.add_argument("--force", action="store_true", help="rerun scored cells")
    parser.add_argument(
        "--model", action="append", help="model id; repeat to select several"
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    if not (args.protocol or args.formal or args.full):
        args.full = True
    lock = load_supplement()
    subjects = select_models(lock, args.model)
    local_preflight(lock, subjects)
    protocol_rows = _load_rows(PROTOCOL_OUT)
    formal_rows = _load_rows(FORMAL_OUT)
    protocol_cells = plan_cells(subjects, PROTOCOL_TASKS, (1,))
    formal_cells = plan_cells(subjects, FORMAL_TASKS, ATTEMPTS)
    print(
        "===== SUPPLEMENT PLAN =====\n"
        f"models={','.join(row['id'] for row in subjects)}\n"
        f"protocol pending={_pending(protocol_rows, protocol_cells, lock, force=args.force)}/"
        f"{len(protocol_cells)} output={PROTOCOL_OUT}\n"
        f"formal pending={_pending(formal_rows, formal_cells, lock, force=args.force)}/"
        f"{len(formal_cells)} output={FORMAL_OUT}\n"
        "n_concurrent=1; each k=3 attempt is an independent Harbor -k 1 sandbox; "
        "provider fallback disabled",
        flush=True,
    )
    if not args.run:
        return 0
    catalog_preflight(subjects)
    restore_sleep = locked._prevent_sleep()
    code = 0
    try:
        if args.protocol or args.full:
            code = _run_cells(
                protocol_rows,
                protocol_cells,
                lock,
                write_protocol,
                subjects,
                force=args.force,
            )
        if args.formal or args.full:
            all_protocol_rows = _load_rows(PROTOCOL_OUT)
            ready, by_model = _protocol_ready(all_protocol_rows, subjects)
            if not ready:
                failed = [
                    model_id for model_id, passed in by_model.items() if not passed
                ]
                print(
                    "formal run blocked: protocol check has not passed for "
                    + ", ".join(failed),
                    file=sys.stderr,
                )
                return max(code, 3)
            code = max(
                code,
                _run_cells(
                    formal_rows,
                    formal_cells,
                    lock,
                    write_formal,
                    subjects,
                    force=args.force,
                ),
            )
        return code
    finally:
        restore_sleep()


if __name__ == "__main__":
    raise SystemExit(main())
