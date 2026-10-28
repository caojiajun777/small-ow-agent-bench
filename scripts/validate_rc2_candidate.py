"""Trusted-fixture local checks for the additive RC2 bank; no model/container.

This is explicitly not a production Linux container gate or model authorization.
Only repository-authored oracle/nop fixtures are executed, never model artifacts.
"""
from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
import importlib.util
import json
from pathlib import Path

from prepare_rc2_candidate import DEFAULT_CANDIDATE, VERSION, BANK_62, sha, validate_candidate


def local_validator(candidate: Path):
    # Private module state per invocation: no mutation of the RC1 validator's
    # shared ROOT, including when two validations happen in the same process.
    path = Path(__file__).with_name("validate_upgraded_tasks.py")
    spec = importlib.util.spec_from_file_location("_rc2_private_local_validator", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    module.ROOT = candidate
    return module


def validate_cases(candidate: Path, tasks, modes=("nop", "oracle"), workers=2):
    candidate = candidate.absolute()
    bank = validate_candidate(candidate)
    manifest_hash = sha(candidate / "task-bank-v2.manifest.json")
    sources = {path.name: sha(path) for path in
               (Path(__file__), Path(__file__).with_name("validate_upgraded_tasks.py"))}
    if (not tasks or len(set(tasks)) != len(tasks) or not set(tasks).issubset(BANK_62)
            or not modes or not set(modes).issubset({"nop", "oracle"})
            or len(set(modes)) != len(modes) or type(workers) is not int or not 1 <= workers <= 4):
        raise ValueError("explicit unique candidate tasks, oracle/nop modes and 1..4 workers required")
    local = local_validator(candidate)
    rows = []
    expected_hashes = {item["id"]: item["task_sha256"] for item in bank["items"]}
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = {pool.submit(local.validate_case, task, mode): (task, mode) for task in tasks for mode in modes}
        for future in as_completed(futures):
            row = future.result()
            if ((row.get("task"), row.get("mode")) != futures[future]
                    or row.get("task_sha256") != expected_hashes[row["task"]]
                    or not row.get("source_unchanged")):
                raise ValueError("local row task identity/fingerprint/source mismatch")
            verdict = row.get("verdict")
            if verdict is not None and (verdict.get("task_id") != row["task"]
                    or verdict.get("task_version") != VERSION or verdict.get("grader_version") != VERSION):
                raise ValueError("local verdict task/controller version mismatch")
            if row.get("ok") and (not verdict or not row.get("controller_validated") or not row.get("reward_consistent")):
                raise ValueError("passing local row lacks controller and reward evidence")
            rows.append(row)
    if sha(candidate / "task-bank-v2.manifest.json") != manifest_hash or validate_candidate(candidate) != bank:
        raise ValueError("candidate manifest changed during validation")
    if any(sha(Path(__file__).with_name(name)) != expected for name, expected in sources.items()):
        raise ValueError("local validation source changed during execution")
    rows.sort(key=lambda row: (BANK_62.index(row["task"]), row["mode"]))
    return {
        "schema_version": 1, "kind": "rc2_local_reference_validation",
        "task_version": VERSION, "candidate_manifest_sha256": bank["manifest_sha256"],
        "candidate_manifest_file_sha256": manifest_hash,
        "validation_sources": sources,
        "scope": "explicit local oracle/nop subset; not a container gate or model evaluation",
        "container_validated": False, "model_calls": 0, "sandbox_creates": 0,
        "tasks": tasks, "modes": list(modes), "cases": len(rows),
        "passed": sum(row["ok"] for row in rows), "all_passed": all(row["ok"] for row in rows),
        "rows": rows,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--candidate", type=Path, default=DEFAULT_CANDIDATE)
    parser.add_argument("--tasks", nargs="+", choices=BANK_62, required=True)
    parser.add_argument("--workers", type=int, default=2)
    args = parser.parse_args()
    result = validate_cases(args.candidate, args.tasks, workers=args.workers)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["all_passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
