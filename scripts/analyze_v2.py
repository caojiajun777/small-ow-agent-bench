"""Read-only SmallOWBench 2.0 raw-evidence analysis. Never launches jobs."""

from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timezone
import json
from pathlib import Path

from v2_pipeline import (
    INFRA_EXCEPTIONS,
    ROOT,
    SCORER_VERSION,
    SKILLS,
    VERSION,
    V2Error,
    active_claims,
    file_hash,
    read_json,
    read_visits,
    safe_name,
    validate_lock,
    validate_manifest,
    validate_verdict,
    legacy_tree_digest,
    job_config,
    normalized_job_config,
    harbor_task_checksum,
    planned_task_units,
)


def _timestamp(value):
    if not isinstance(value, str):
        raise V2Error("visit started_at must be a timezone-aware timestamp")
    result = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if result.tzinfo is None:
        raise V2Error("visit started_at must include timezone")
    return result.astimezone(timezone.utc)


def _regular(path, root):
    path, root = Path(path), Path(root).resolve()
    if (
        not path.is_file()
        or path.is_symlink()
        or not path.resolve().is_relative_to(root)
    ):
        raise V2Error("missing or unsafe raw evidence: " + path.name)
    return path


def termination(raw, trace):
    exception = (raw.get("exception_info") or {}).get("exception_type")
    if exception in INFRA_EXCEPTIONS:
        return "infra"
    if exception == "AgentTimeoutError":
        return "tle"
    if exception in (
        "OutputLengthExceededError",
        "OutputLengthExceeded",
        "ContextWindowExceededError",
        "ContextLengthExceededError",
    ):
        return "budget_exhaustion"
    if exception and trace["termination_reason"] == "api_error":
        return "infra"
    if exception:
        return "protocol_error"
    reason = trace["termination_reason"]
    if reason in ("api_error", "cancelled", "internal_error", "command_error"):
        return "infra"
    if reason == "command_timeout":
        return "tle"
    if reason in ("max_turns", "output_limit", "context_limit"):
        return "budget_exhaustion"
    if reason == "finish" and trace["finished"] and trace["n_shell"] > 0:
        return "clean"
    return "protocol_error"


def validate_trace(trace, task):
    if (
        not isinstance(trace, dict)
        or trace.get("schema_version") != 2
        or trace.get("harness_version") != VERSION
        or trace.get("version") != VERSION
        or trace.get("task_id") != task
        or type(trace.get("finished")) is not bool
    ):
        raise V2Error("missing/version-mismatched v2 completion trace")
    for name in ("n_turns", "n_shell", "n_shell_attempts", "n_parse_fail"):
        if type(trace.get(name)) is not int or trace[name] < 0:
            raise V2Error("invalid completion counter")
    if (
        trace["n_shell"] > trace["n_shell_attempts"]
        or trace["n_parse_fail"] > trace["n_turns"]
        or trace.get("termination_reason")
        not in (
            "finish",
            "max_turns",
            "output_limit",
            "context_limit",
            "api_error",
            "command_timeout",
            "command_error",
            "cancelled",
            "internal_error",
        )
        or (trace["finished"] != (trace["termination_reason"] == "finish"))
    ):
        raise V2Error("completion counters/reason contradict each other")
    return trace


def _validate_capture(trial, trace, verdict):
    agent = trial / "agent"
    if trace.get("artifact_manifest_path") != "artifacts/manifest.json":
        raise V2Error("unknown v2 artifact manifest path")
    path = _regular(agent / "artifacts" / "manifest.json", agent)
    capture = read_json(path)
    if trace.get("artifact_manifest_sha256") != file_hash(path):
        raise V2Error("artifact manifest differs from the final trace checkpoint")
    if (
        capture.get("schema_version") != 2
        or capture.get("harness_version") != VERSION
        or capture.get("task_id") != verdict["task_id"]
        or capture.get("status") not in ("complete", "incomplete")
        or capture.get("status") != trace.get("artifact_capture_status")
    ):
        raise V2Error("capture is missing, erroneous, or identity-mismatched")
    records = {}
    for row in capture.get("files", []):
        name = row.get("path")
        if (
            not isinstance(name, str)
            or name in records
            or Path(name).is_absolute()
            or ".." in name.split("/")
            or "\\" in name
            or ":" in name
        ):
            raise V2Error("unsafe/duplicate captured artifact")
        actual = _regular(agent / "artifacts" / name, agent / "artifacts")
        if (
            row.get("role") not in ("context", "submission")
            or row.get("sha256") != file_hash(actual)
            or type(row.get("size")) is not int
            or row["size"] != actual.stat().st_size
        ):
            raise V2Error("captured artifact bytes/hash/size mismatch")
        records[name] = row
    for row in verdict["submission_manifest"]:
        actual = records.get(row["path"])
        # A valid task failure may have no root deliverable; that absence is
        # represented by no row, not by a missing verifier or fabricated zero.
        if actual is None:
            raise V2Error("grader-observed file was not captured: " + row["path"])
        if (
            actual["sha256"] != row["sha256"]
            or actual["size"] != row["size_bytes"]
            or {"context": "observation", "submission": "submission"}[actual["role"]]
            != row["role"]
        ):
            raise V2Error("capture and grader observed different final bytes")
    if capture["status"] == "complete":
        if (
            set(records) != {row["path"] for row in verdict["submission_manifest"]}
            or capture.get("missing")
            or capture.get("issues")
        ):
            raise V2Error(
                "complete capture and grader do not describe the same complete file set"
            )
        capture["state_consistency"] = "complete_bidirectional_bytes_and_roles_match"
    else:
        if not capture.get("missing") and not capture.get("issues"):
            raise V2Error(
                "incomplete capture lacks explicit missing/exclusion diagnostics"
            )
        capture["state_consistency"] = (
            "incomplete_capture_not_a_verified_same_final_state"
        )
    if verdict["status"] == "pass" and capture["status"] != "complete":
        raise V2Error("successful artifact lacks complete capture evidence")
    return capture


def validate_scored_visit(visit, manifest, directory, *, root=ROOT):
    directory, root = Path(directory).resolve(), Path(root).resolve()
    job_name = safe_name(visit.get("job_name"))
    planned = {slot["slot_id"]: slot for slot in manifest["schedule"]}
    slot = planned.get(visit.get("slot_id"))
    if slot is None:
        raise V2Error("unplanned scored visit")
    if visit.get("manifest_sha256") != manifest["manifest_sha256"]:
        raise V2Error("visit is bound to another manifest")
    for field in ("model", "task", "repetition"):
        if visit.get(field) != slot[field]:
            raise V2Error("visit slot identity mismatch")
    started = _timestamp(visit.get("started_at"))
    job = directory / "jobs" / job_name
    _regular(job / "config.json", directory / "jobs")
    executed_sha = file_hash(job / "config.json")
    if executed_sha != visit.get("config_sha256") or executed_sha != visit.get(
        "executed_config_sha256"
    ):
        raise V2Error("saved job configuration fingerprint mismatch")
    config = read_json(job / "config.json")
    task = slot["task"]
    expected = job_config(manifest, slot, job_name, directory)
    expected_agent = expected["agents"][0]
    generated_path = _regular(
        directory / "configs" / (job_name + ".json"), directory / "configs"
    )
    if (
        file_hash(generated_path) != visit.get("generated_config_sha256")
        or read_json(generated_path) != expected
        or normalized_job_config(config) != normalized_job_config(expected)
    ):
        raise V2Error("saved configuration is not the frozen single-slot protocol")
    backend = manifest["runtime_environment_evidence"]["backend"]
    # Harbor's resolved job config drops the environment section on dump; the
    # normalized JobConfig form and the raw trial config carry the backend.
    if normalized_job_config(config).get("environment", {}).get("type") != backend:
        raise V2Error("executed backend differs from container validation")
    trial_paths = [p for p in job.glob("*/result.json") if p.is_file()]
    if len(trial_paths) != 1:
        raise V2Error("exactly one raw Harbor trial is required")
    result_path = _regular(trial_paths[0], job)
    trial = result_path.parent
    raw = read_json(result_path)
    if raw.get("task_name", "").rsplit("/", 1)[-1] != task:
        raise V2Error("raw Harbor task identity mismatch")
    actual = raw.get("config", {})
    actual_agent = actual.get("agent", {})
    if (
        any(actual_agent.get(key) != value for key, value in expected_agent.items())
        or actual.get("task", {}).get("path") != expected["tasks"][0]["path"]
        or actual.get("timeout_multiplier") != 1
        or actual.get("verifier", {}).get("disable", False)
        or actual.get("environment", {}).get("type") != backend
    ):
        raise V2Error("raw executed configuration differs from frozen protocol")
    for name in (
        "override_timeout_sec",
        "max_timeout_sec",
        "override_setup_timeout_sec",
    ):
        if actual_agent.get(name) != expected_agent.get(name):
            raise V2Error("undeclared agent timeout override")
    if any(
        actual_agent.get(name) not in (None, [])
        for name in ("skills", "mcp_servers", "extra_allowed_hosts")
    ):
        raise V2Error("undeclared agent tools or skills")
    if any(
        actual.get(name) is not None
        for name in (
            "agent_timeout_multiplier",
            "verifier_timeout_multiplier",
            "agent_setup_timeout_multiplier",
        )
    ):
        raise V2Error("undeclared phase timeout override")
    if any(
        actual.get("environment", {}).get(name) is not None
        for name in (
            "override_cpus",
            "override_memory_mb",
            "override_storage_mb",
            "override_gpus",
            "override_tpu",
        )
    ):
        raise V2Error("undeclared runtime resource override")
    trace = validate_trace(
        read_json(_regular(trial / "agent" / "compact-shell-v2.json", trial)), task
    )
    metadata = (raw.get("agent_result") or {}).get("metadata", {})
    if (
        metadata.get("harness_version") != VERSION
        or metadata.get("task_id") != task
        or any(
            metadata.get(name) != trace[name]
            for name in (
                "finished",
                "n_turns",
                "n_shell",
                "n_shell_attempts",
                "n_parse_fail",
                "termination_reason",
                "artifact_capture_status",
                "artifact_manifest_path",
                "artifact_manifest_sha256",
            )
        )
    ):
        raise V2Error("raw agent metadata and trace disagree")
    verdict_path = _regular(trial / "verifier" / "verdict.json", trial)
    verdict = validate_verdict(read_json(verdict_path), task)
    rewards = (raw.get("verifier_result") or {}).get("rewards", {})
    reward = rewards.get("reward")
    if (
        verdict["status"] == "error"
        or isinstance(reward, bool)
        or not isinstance(reward, (int, float))
        or reward != verdict["artifact_correct"]
    ):
        raise V2Error("missing reward, grader error, or raw/verdict disagreement")
    term = termination(raw, trace)
    if term == "infra":
        raise V2Error("infrastructure execution cannot be a scored task observation")
    if (
        type(visit.get("atomic_correct")) is not int
        or visit["atomic_correct"] != verdict["artifact_correct"]
        or visit.get("termination") != term
    ):
        raise V2Error("ledger and raw versioned outcome disagree")
    capture = _validate_capture(trial, trace, verdict)
    staged = directory / "staged-tasks" / task
    if (
        file_hash(staged / "task.toml")
        != manifest["tasks"][task]["staged_task_config_sha256"]
        or legacy_tree_digest(staged) != manifest["tasks"][task]["staged_tree_sha256"]
        or raw.get("verifier_environment_mode") != "separate"
    ):
        raise V2Error("raw trial lacks matching separate immutable-image staged task")
    if raw.get("task_checksum") != harbor_task_checksum(staged):
        raise V2Error("raw Harbor task checksum differs from pinned staged task")
    lock = read_json(directory / "execution-lock.json")
    if visit.get("execution_lock_sha256") != lock["execution_lock_sha256"]:
        raise V2Error("raw trial/visit is not bound to this execution lock")
    from v2_executor import validate_authorization

    if visit.get("authorization_sha256") != validate_authorization(
        directory, manifest, lock
    ):
        raise V2Error(
            "scored visit is not bound to its explicit execution authorization"
        )
    return {
        **slot,
        "job_name": job_name,
        "started_at": started.isoformat(),
        "artifact": verdict["artifact_correct"] == 1,
        "clean": verdict["artifact_correct"] == 1 and term == "clean",
        "termination": term,
        "termination_reason": trace["termination_reason"],
        "failure_category": verdict["failure_category"],
        "verdict_sha256": file_hash(verdict_path),
        "raw_result_sha256": file_hash(result_path),
        "submission_digest": verdict["submission_digest"],
        "artifact_capture_status": capture["status"],
        "artifact_state_consistency": capture["state_consistency"],
        "diagnostics": {"checks": verdict["checks"], "evidence": verdict["evidence"]},
        "resources": {
            "model_loop_elapsed_seconds": trace.get("model_loop_elapsed_seconds"),
            "total_elapsed_seconds": trace.get("total_elapsed_seconds"),
            "api_seconds": sum(
                call.get("elapsed_seconds", 0) for call in trace.get("calls", [])
                if call.get("kind") == "api"
            ),
            "command_seconds": sum(
                call.get("elapsed_seconds", 0) for call in trace.get("calls", [])
                if call.get("kind") == "shell"
            ),
            "n_turns": trace["n_turns"],
            "n_parse_fail": trace["n_parse_fail"],
            "n_shell": trace["n_shell"],
            "usage": trace.get("usage"),
        },
    }


def summarize_slots(rows, manifest):
    by_slot = defaultdict(list)
    for row in rows:
        by_slot[row["slot_id"]].append(row)
    canonical_rows, duplicates = [], {}
    for slot_id, candidates in sorted(by_slot.items()):
        ordered = sorted(
            candidates, key=lambda row: (_timestamp(row["started_at"]), row["job_name"])
        )
        canonical_rows.append(ordered[0])
        if len(ordered) > 1:
            duplicates[slot_id] = [row["job_name"] for row in ordered]
    expected = {slot["slot_id"] for slot in manifest["schedule"]}
    return canonical_rows, duplicates, sorted(expected - set(by_slot))


def leaderboard(rows, manifest):
    if manifest.get("diagnostic") is not None:
        return {}  # A complete engineering sample is not a 62-task leaderboard.
    reps = manifest["repetitions"]
    cells = defaultdict(dict)
    for row in rows:
        key = (row["model"], row["task"])
        if row["repetition"] in cells[key]:
            raise V2Error("leaderboard requires unique canonical slots")
        cells[key][row["repetition"]] = row
    boards = {}
    for model in sorted(manifest["models"]):
        tasks = {}
        for task, spec in sorted(manifest["tasks"].items()):
            values = cells.get((model, task), {})
            complete = set(values) == set(range(1, reps + 1))
            tasks[task] = {
                "skill": spec["skill"],
                "n_scored": len(values),
                "complete": complete,
                **{
                    name: sum(int(row[name]) for row in values.values()) / reps
                    if complete
                    else None
                    for name in ("artifact", "clean")
                },
            }
        complete = all(value["complete"] for value in tasks.values())
        board = {
            "complete": complete,
            "task_units": 62,
            "task_rates": tasks,
            "planned_slots": 62 * reps,
            "scored_slots": sum(v["n_scored"] for v in tasks.values()),
            "skills": {"artifact": {}, "clean": {}},
        }
        for endpoint in ("artifact", "clean"):
            for skill in SKILLS:
                values = [value for value in tasks.values() if value["skill"] == skill]
                board["skills"][endpoint][skill] = (
                    sum(value[endpoint] for value in values) / len(values)
                    if values and all(value["complete"] for value in values)
                    else None
                )
            board[endpoint + "_macro_100"] = (
                100 * sum(board["skills"][endpoint].values()) / 5 if complete else None
            )
            board[endpoint + "_task_micro"] = (
                sum(value[endpoint] for value in tasks.values()) / 62
                if complete
                else None
            )
        boards[model] = board
    return boards


def build_report(directory, *, root=ROOT):
    directory = Path(directory).resolve()
    manifest = validate_manifest(directory, root=root)
    lock = validate_lock(directory, manifest, root=root)
    from v2_executor import read_model_holds

    held_models = read_model_holds(directory, manifest, lock)
    visits, issues = read_visits(directory)
    legal, seen_jobs, scored_by_slot = [], set(), defaultdict(list)
    schedule = {slot["slot_id"]: slot for slot in manifest["schedule"]}
    unresolved, infra = [], []
    for visit in visits:
        job = visit.get("job_name")
        if job in seen_jobs:
            issues.append({"kind": "duplicate_job_name", "job": job})
        seen_jobs.add(job)
        if visit.get("slot_id") not in schedule:
            issues.append({"kind": "unplanned_visit", "job": job})
            continue
        slot = schedule[visit["slot_id"]]
        if visit.get("manifest_sha256") != manifest["manifest_sha256"] or any(
            name in visit and visit[name] != slot[name]
            for name in ("model", "task", "repetition")
        ):
            issues.append({"kind": "visit_identity_mismatch", "job": job})
            continue
        state = visit.get("status")
        if state in ("running", "unknown"):
            unresolved.append(job)
        elif state == "infra":
            try:
                safe_name(job)
                job_root = directory / "jobs" / job
                results = [
                    path for path in job_root.glob("*/result.json") if path.is_file()
                ]
                if len(results) != 1:
                    # A no-trial/missing-verdict event can be infrastructure,
                    # but absence alone cannot prove that a model failure was
                    # not hidden. Keep strict acceptance blocked for review.
                    raise V2Error("infra classification lacks original trial evidence")
                raw = read_json(_regular(results[0], job_root))
                if raw.get("task_name", "").rsplit("/", 1)[-1] != slot["task"]:
                    raise V2Error("infra raw task identity mismatch")
                trace_path = results[0].parent / "agent" / "compact-shell-v2.json"
                trace = (
                    validate_trace(read_json(trace_path), slot["task"])
                    if trace_path.is_file()
                    else None
                )
                exception = (raw.get("exception_info") or {}).get("exception_type")
                verdict_path = results[0].parent / "verifier" / "verdict.json"
                observed = (
                    validate_verdict(read_json(verdict_path), slot["task"])
                    if verdict_path.is_file()
                    else None
                )
                proven = (
                    exception in INFRA_EXCEPTIONS
                    or trace is not None
                    and termination(raw, trace) == "infra"
                    or observed is not None
                    and observed["status"] == "error"
                )
                if not proven:
                    raise V2Error(
                        "infra visit may conceal a task/protocol failure; no answer-based retry"
                    )
                infra.append({"job": job, "slot_id": visit["slot_id"]})
            except (OSError, ValueError, KeyError, TypeError) as exc:
                issues.append(
                    {
                        "kind": "unproven_infrastructure_retry",
                        "job": job,
                        "error": str(exc),
                    }
                )
        elif state == "scored":
            scored_by_slot[visit["slot_id"]].append(job)
            try:
                legal.append(
                    validate_scored_visit(visit, manifest, directory, root=root)
                )
            except (OSError, ValueError, KeyError, TypeError) as exc:
                issues.append(
                    {"kind": "invalid_scored_evidence", "job": job, "error": str(exc)}
                )
        elif state == "aborted":
            if visit.get("launch_not_requested") is not True:
                issues.append({"kind": "unproven_aborted_visit", "job": job})
        else:
            issues.append({"kind": "unknown_visit_status", "job": job})
    for path in (directory / "jobs").iterdir() if (directory / "jobs").exists() else ():
        if path.is_dir() and path.name not in seen_jobs:
            issues.append({"kind": "untracked_job_artifacts", "job": path.name})
    unresolved += active_claims(directory)
    canonical_rows, legal_duplicates, missing = summarize_slots(legal, manifest)
    duplicates = {slot: jobs for slot, jobs in scored_by_slot.items() if len(jobs) > 1}
    accepted = not (issues or duplicates or missing or unresolved)
    candidates = leaderboard(canonical_rows, manifest)
    return {
        "schema_version": 2,
        "kind": "smallowbench_v2_report",
        "benchmark_version": VERSION,
        "task_version": VERSION,
        "harness_version": VERSION,
        "grader_version": VERSION,
        "scorer_version": SCORER_VERSION,
        "manifest_sha256": manifest["manifest_sha256"],
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "accepted": accepted,
        "formal_ranking_eligible": accepted and manifest.get("diagnostic") is None,
        "engineering_diagnostic": manifest.get("diagnostic") is not None,
        "task_units": planned_task_units(manifest),
        "review_candidates_are_nested_diagnostics": True,
        "repetitions": manifest["repetitions"],
        "scoring": manifest["scoring"],
        "canonical_rule": "earliest_started_legal_scored_then_job_name",
        "completeness": {
            "planned": len(schedule),
            "legal_unique": len(canonical_rows),
            "missing": missing,
            "duplicates": duplicates,
            "unresolved": sorted(set(unresolved)),
        },
        "issues": issues,
        "infra_visits": infra,
        "held_models": held_models,
        "canonical_rows": canonical_rows,
        "candidate_scores": candidates,
        "leaderboard": candidates if accepted else {},
        "candidate_diagnostics": [
            {
                "model": row["model"],
                "task": row["task"],
                "repetition": row["repetition"],
                "slot_id": row["slot_id"],
                **row["diagnostics"],
            }
            for row in canonical_rows
            if manifest["tasks"][row["task"]]["skill"] == "review"
        ],
        "model_execution_performed_by_analyzer": False,
    }


def main(argv=None):
    import argparse

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--directory", required=True, type=Path)
    parser.add_argument(
        "--output",
        type=Path,
        help="explicit NEW JSON output; default prints a read-only summary",
    )
    args = parser.parse_args(argv)
    try:
        report = build_report(args.directory)
        if args.output:
            output = args.output.resolve()
            if not output.is_relative_to(args.directory.resolve()) or output.exists():
                raise V2Error("report output must be a new file inside this experiment")
            output.parent.mkdir(parents=True, exist_ok=True)
            with output.open("x", encoding="utf-8", newline="\n") as handle:
                json.dump(report, handle, ensure_ascii=False, indent=2, allow_nan=False)
                handle.write("\n")
        print(
            json.dumps(
                {
                    key: report[key]
                    for key in (
                        "schema_version",
                        "benchmark_version",
                        "accepted",
                        "formal_ranking_eligible",
                        "completeness",
                        "issues",
                    )
                },
                ensure_ascii=False,
            )
        )
        return 0 if report["accepted"] else 2
    except (OSError, ValueError, KeyError, TypeError) as exc:
        print(json.dumps({"accepted": False, "error": str(exc)}, ensure_ascii=False))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
