"""Audit two preserved negative observations without repairing their failed capture.

No model, container, original artifact or ledger is changed. The supplement can
support only the original fail/0 conclusions for the two explicitly named jobs;
it does not establish a complete final Agent capture or authorize any retry.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path, PurePosixPath

import analyze_release_v2 as frozen
from release_v2_executor import validate_authorization
from release_v2_fee_waiver_executor import validate_fee_waiver
from release_v2_pipeline import (
    ROOT, HARNESS_VERSION, V2Error, file_hash, harbor_task_checksum,
    legacy_tree_digest, read_json, read_visits, validate_lock, validate_manifest,
    validate_verdict,
)

RUN_SHA = "c9bebded890b7bfc49518efabadf81a8cbca35355d1fd1a1b300914849fb5fe1"
LOCK_SHA = "8468e1368799141f67fb3b30200499be60dd9763766f18284c0ff799001c07df"
MODEL = "llama-3.2-3b-instruct"
TARGETS = {
    "visit-a71e414b27f0489fbab92ad5a22fabdb": ("testgen-booking-touch", 12),
    "visit-c9e574d45d1a4215998ef257fe680a50": ("testgen-anagram", 23),
}
CAPTURE_REJECTION = "capture is missing, erroneous, or identity-mismatched"


def regular(path, boundary):
    """Reject links/reparse ancestors and files outside the original evidence root."""
    path, boundary = Path(path), Path(boundary).absolute()
    absolute = path.absolute()
    if not absolute.is_relative_to(boundary):
        raise V2Error("supplement path escapes its original evidence root")
    for part in (boundary, *[boundary.joinpath(*absolute.relative_to(boundary).parts[:i])
                             for i in range(1, len(absolute.relative_to(boundary).parts) + 1)]):
        if (part.is_symlink() or not part.exists()
                or getattr(part.stat(), "st_file_attributes", 0) & 0x400):
            raise V2Error("supplement evidence is missing or has a link/reparse ancestor")
    if not absolute.is_file() or not absolute.resolve().is_relative_to(boundary.resolve()):
        raise V2Error("supplement requires original regular evidence files")
    return absolute


def _safe_name(name):
    if (not isinstance(name, str) or not name or "\\" in name or ":" in name
            or "\0" in name or name.startswith("/")
            or any(part in ("", ".", "..") for part in name.split("/"))):
        raise V2Error("unsafe grader-observed relative path")
    return PurePosixPath(name)


def audit_negative_transport(trial, trace, verdict, task, expected_count, seed):
    """Prove only the complete grader observation and its original scope failure."""
    trial, seed = Path(trial).absolute(), Path(seed).absolute()
    frozen.validate_trace(trace, task)
    validate_verdict(verdict, task)
    if (verdict.get("status") != "fail" or verdict.get("artifact_correct") != 0
            or verdict.get("failure_category") != "invalid_submission"
            or trace.get("termination_reason") != "max_turns" or trace.get("finished")):
        raise V2Error("supplement is restricted to the original negative scope outcomes")
    manifest_path = regular(trial / "agent/artifacts/manifest.json", trial)
    capture = read_json(manifest_path)
    if (trace.get("artifact_manifest_path") != "artifacts/manifest.json"
            or trace.get("artifact_manifest_sha256") != file_hash(manifest_path)
            or trace.get("artifact_capture_status") != "error"
            or capture.get("schema_version") != 2
            or capture.get("harness_version") != HARNESS_VERSION
            or capture.get("task_id") != task or capture.get("status") != "error"
            or capture.get("termination_reason") != "max_turns"
            or capture.get("files") != [] or capture.get("total_bytes") != 0
            or capture.get("missing") != ["repo"]
            or capture.get("atomic") is not False
            or capture.get("final_state_verified") is not False
            or capture.get("issues") != [{"error_type": "FileNotFoundError", "path": "",
                                          "reason": "archive_write_error"}]):
        raise V2Error("capture error identity/hash/reason differs from the two known failures")
    checks = verdict["checks"]
    controller = checks.get("controller", {})
    if (checks.get("internal_errors") != [] or checks.get("collected") != 1
            or checks.get("pytest_exitstatus") != 1
            or controller.get("worker_returncode") != 1
            or controller.get("temporary_storage") != "native_private"
            or controller.get("temporary_parent") != "/tmp"
            or type(controller.get("captured_bytes")) is not int
            or controller["captured_bytes"] < 0
            or controller["captured_bytes"] != controller.get("observed_output_bytes")
            or type(controller.get("output_limit_bytes")) is not int
            or not 0 <= controller["captured_bytes"] <= controller["output_limit_bytes"]):
        raise V2Error("negative observation lacks a completed trusted grader outcome")
    failed = [row for row in checks.get("reports", []) if row.get("outcome") == "failed"]
    if (len(failed) != 1 or failed[0].get("node") != "test_state.py::test_submission"
            or failed[0].get("phase") != "call"
            or failed[0].get("category") != "invalid_submission"
            or failed[0].get("exception_type") != "AssertionError"):
        raise V2Error("negative observation is not the original trusted scope assertion")
    try:
        failure = json.loads(failed[0]["detail"].splitlines()[0])
    except (KeyError, ValueError, AttributeError, IndexError) as error:
        raise V2Error("original scope failure detail is not structured") from error
    if failure != {"ok": False, "category": "invalid_submission",
                   "reason_code": "submission_scope_or_source_invalid",
                   "reason": "only test files/fixtures under tests are allowed",
                   "exception_type": "ValueError"}:
        raise V2Error("negative observation is not the declared outside-tests scope failure")
    worker_path = regular(trial / "verifier/worker-result.json", trial)
    worker = read_json(worker_path)
    if (worker.get("status") != "fail" or worker.get("failure_category") != "invalid_submission"
            or worker.get("checks") != {key: value for key, value in checks.items() if key != "controller"}
            or worker.get("evidence") != verdict["evidence"]
            or worker.get("runtime") != verdict.get("runtime")):
        raise V2Error("independent grader worker and controller verdict disagree")
    transport = trial / "artifacts/submission"
    records = verdict["submission_manifest"]
    if len(records) != expected_count:
        raise V2Error("grader observation count differs from the known original case")
    checked, witnesses = [], []
    for row in records:
        name = _safe_name(row["path"]).as_posix()
        if not name.startswith("repo/"):
            raise V2Error("unexpected root in the original grader observation")
        role = "submission" if name.startswith("repo/tests/") else "observation"
        actual = regular(transport / name, transport)
        if (row["role"] != role or actual.stat().st_size != row["size_bytes"]
                or file_hash(actual) != row["sha256"]):
            raise V2Error("transport bytes/size/role disagree with the original verdict")
        checked.append(dict(row))
        if (role == "observation" and name.endswith(".xml")
                and not (seed / name.removeprefix("repo/")).exists()):
            witnesses.append(name)
    actual_names = set()
    for entry in transport.rglob("*"):
        if entry.is_symlink() or getattr(entry.stat(), "st_file_attributes", 0) & 0x400:
            raise V2Error("transport tree contains a link/reparse entry")
        if entry.is_file():
            regular(entry, transport)
            actual_names.add(entry.relative_to(transport).as_posix())
    if actual_names != {row["path"] for row in records}:
        raise V2Error("transport and grader observation file sets differ")
    if not witnesses:
        raise V2Error("no preserved outside-tests XML witness for the negative scope outcome")
    return {
        "observed_file_count": len(checked), "observed_files": checked,
        "observation_consistency": "exact_grader_observation_set_bytes_sizes_and_roles_match",
        "outside_tests_scope_witnesses": witnesses,
        "original_agent_capture_status": "error",
        "complete_final_agent_capture_established": False,
        "capture_manifest_sha256": file_hash(manifest_path),
        "worker_result_sha256": file_hash(worker_path),
        "negative_conclusion": {"artifact": False, "clean": False,
                                "failure_category": "invalid_submission"},
    }


def audit_visit(visit, manifest, lock, directory, *, root=ROOT):
    directory, root = Path(directory).resolve(), Path(root).resolve()
    job = visit.get("job_name")
    if job not in TARGETS or visit.get("model") != MODEL or visit.get("status") != "scored":
        raise V2Error("supplement cannot admit an unlisted job/model/status")
    task, count = TARGETS[job]
    if visit.get("task") != task or visit.get("slot_id") != f"{MODEL}/{task}/r1":
        raise V2Error("supplement job and fixed slot identity disagree")
    regular(directory / "visits" / (job + ".json"), directory)
    regular(directory / "jobs" / job / "config.json", directory)
    # This normally executes every original configuration/identity/trace/verdict
    # check before the capture check. Nothing is patched or made to look complete.
    try:
        frozen.validate_scored_visit(visit, manifest, directory, root=root)
    except V2Error as error:
        if str(error) != CAPTURE_REJECTION:
            raise V2Error("original validation failed for a reason outside this supplement") from error
    else:
        raise V2Error("original capture is valid; this negative-only exception is inapplicable")
    paths = list((directory / "jobs" / job).glob("*/result.json"))
    if len(paths) != 1:
        raise V2Error("supplement requires exactly one original trial")
    raw_path = regular(paths[0], directory / "jobs" / job)
    trial = raw_path.parent
    raw = read_json(raw_path)
    trace_path = regular(trial / "agent/compact-shell-v2.json", trial)
    verdict_path = regular(trial / "verifier/verdict.json", trial)
    trace, verdict = read_json(trace_path), read_json(verdict_path)
    observed = audit_negative_transport(
        trial, trace, verdict, task, count,
        root / "task-banks/rc2/tasks" / task / "tests/baseline",
    )
    # Reproduce all original checks after the rejected capture, unchanged.
    staged = directory / "staged-tasks" / task
    if (file_hash(staged / "task.toml") != manifest["tasks"][task]["staged_task_config_sha256"]
            or legacy_tree_digest(staged) != manifest["tasks"][task]["staged_tree_sha256"]
            or raw.get("verifier_environment_mode") != "separate"):
        raise V2Error("supplement lacks the original separate immutable-image task")
    if raw.get("task_checksum") != harbor_task_checksum(staged):
        raise V2Error("supplement raw task checksum differs from the staged task")
    proofs = frozen.validate_runtime_isolation(trial, raw, manifest, task, verdict)
    if visit.get("execution_lock_sha256") != lock["execution_lock_sha256"]:
        raise V2Error("supplement visit has a different original execution lock")
    if visit.get("authorization_sha256") != validate_authorization(directory, manifest, lock):
        raise V2Error("supplement visit has a different original authorization")
    waiver_sha = validate_fee_waiver(directory, manifest, lock, root=root)
    if visit.get("fee_waiver_sha256") != waiver_sha:
        raise V2Error("supplement visit lacks its original continuation provenance")
    slot = next(row for row in manifest["schedule"] if row["slot_id"] == visit["slot_id"])
    term = frozen.termination(raw, trace)
    row = {
        **slot, "job_name": job, "started_at": frozen._timestamp(visit["started_at"]).isoformat(),
        "artifact": False, "clean": False, "termination": term,
        "termination_reason": trace["termination_reason"],
        "failure_category": verdict["failure_category"],
        "verdict_sha256": file_hash(verdict_path), "raw_result_sha256": file_hash(raw_path),
        "submission_digest": verdict["submission_digest"],
        "artifact_capture_status": "error",
        "artifact_state_consistency": "supplemented_grader_observed_negative_evidence_only",
        "static_network_isolation_evidence": proofs,
        "diagnostics": {"checks": verdict["checks"], "evidence": verdict["evidence"]},
        "resources": {
            "model_loop_elapsed_seconds": trace.get("model_loop_elapsed_seconds"),
            "total_elapsed_seconds": trace.get("total_elapsed_seconds"),
            "api_seconds": sum(call.get("elapsed_seconds", 0) for call in trace.get("calls", []) if call.get("kind") == "api"),
            "command_seconds": sum(call.get("elapsed_seconds", 0) for call in trace.get("calls", []) if call.get("kind") == "shell"),
            "n_turns": trace["n_turns"], "n_parse_fail": trace["n_parse_fail"],
            "n_shell": trace["n_shell"], "usage": trace.get("usage"),
        },
        "capture_supplement_scope": "original_invalid_submission_zero_only",
    }
    bound = [directory / "visits" / (job + ".json"), raw_path, verdict_path, trace_path,
             trial / "verifier/worker-result.json", trial / "agent/artifacts/manifest.json"]
    return {"job_name": job, "task": task, "model": MODEL, "supported": True,
            "original_evidence_sha256": {path.relative_to(directory).as_posix(): file_hash(regular(path, directory)) for path in bound},
            "observation_audit": observed, "canonical_row": row}


def build_supplement(directory, *, root=ROOT):
    directory, root = Path(directory).resolve(), Path(root).resolve()
    sources = {name: file_hash(regular(root / name, root)) for name in (
        "scripts/audit_v2_capture_supplement.py", "scripts/analyze_release_v2.py")}
    manifest = validate_manifest(directory, root=root)
    lock = validate_lock(directory, manifest, root=root)
    if manifest["manifest_sha256"] != RUN_SHA or lock["execution_lock_sha256"] != LOCK_SHA:
        raise V2Error("this supplement is restricted to the named original release run")
    rows, issues = read_visits(directory)
    if issues:
        raise V2Error("visit inputs are unreadable; cannot construct a supplement")
    observations = []
    for job in TARGETS:
        selected = [row for row in rows if row.get("job_name") == job]
        if len(selected) != 1:
            raise V2Error("supplement requires each original job exactly once")
        observations.append(audit_visit(selected[0], manifest, lock, directory, root=root))
    if any(file_hash(root / name) != sha for name, sha in sources.items()):
        raise V2Error("supplement implementation changed during the original evidence audit")
    return {
        "schema_version": 1, "kind": "smallowbench_v2_capture_failure_supplement",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "manifest_sha256": manifest["manifest_sha256"],
        "execution_lock_sha256": lock["execution_lock_sha256"],
        "source_sha256": sources,
        "supported_negative_observations": observations,
        "supported_count": len(observations), "observed_file_count": sum(
            value["observation_audit"]["observed_file_count"] for value in observations),
        "admission_scope": "the_two_named_original_fail_zero_observations_only",
        "complete_final_agent_capture_established": False,
        "original_records_modified": False, "model_calls": 0, "container_calls": 0,
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--directory", required=True, type=Path)
    parser.add_argument("--output", type=Path, help="optional NEW sidecar within this experiment")
    args = parser.parse_args(argv)
    try:
        result = build_supplement(args.directory)
        if args.output:
            output = args.output.absolute()
            directory = args.directory.resolve()
            if (not output.resolve().is_relative_to(directory) or output.exists()
                    or output.is_symlink() or not output.parent.is_dir()):
                raise V2Error("sidecar must be a new file within the original experiment")
            for parent in (output.parent, *output.parent.parents):
                if not parent.is_relative_to(directory):
                    break
                if parent.is_symlink() or getattr(parent.stat(), "st_file_attributes", 0) & 0x400:
                    raise V2Error("sidecar parent cannot contain a link/reparse directory")
            with output.open("x", encoding="utf-8", newline="\n") as handle:
                json.dump(result, handle, ensure_ascii=False, indent=2, allow_nan=False)
                handle.write("\n")
        print(json.dumps({key: result[key] for key in (
            "kind", "supported_count", "observed_file_count", "admission_scope",
            "complete_final_agent_capture_established", "original_records_modified", "model_calls", "container_calls")}, ensure_ascii=False))
        return 0
    except (OSError, ValueError, KeyError, TypeError) as error:
        print(json.dumps({"supported": False, "reason": str(error)}, ensure_ascii=False))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
