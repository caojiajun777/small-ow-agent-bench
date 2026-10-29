"""Offline contracts for the two-case, negative-only capture supplement."""
from __future__ import annotations

from copy import deepcopy
import json
from pathlib import Path

import pytest

import audit_v2_capture_supplement as audit
from release_v2_pipeline import HARNESS_VERSION, VERSION, V2Error, digest, file_hash


def save(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value), encoding="utf-8")


def case(tmp_path, job=None):
    job = job or next(iter(audit.TARGETS))
    task, count = audit.TARGETS[job]
    root, directory = tmp_path / "source", tmp_path / "p2"
    trial = directory / "jobs" / job / (task + "__trial")
    seed = root / "task-banks/rc2/tasks" / task / "tests/baseline"
    seed.mkdir(parents=True)
    (seed / "workflow.py").write_bytes(b"original application")
    contents = {"repo/workflow.py": b"original application", "repo/tests/.gitkeep": b""}
    contents.update({f"repo/output-{i}.xml": f"xml {i}".encode() for i in range(count - 2)})
    records = []
    for name, data in sorted(contents.items()):
        path = trial / "artifacts/submission" / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
        records.append({"path": name, "role": "submission" if name.startswith("repo/tests/") else "observation",
                        "size_bytes": len(data), "sha256": file_hash(path)})
    detail = {"ok": False, "category": "invalid_submission", "reason_code": "submission_scope_or_source_invalid",
              "reason": "only test files/fixtures under tests are allowed", "exception_type": "ValueError"}
    checks = {"internal_errors": [], "collected": 1, "pytest_exitstatus": 1,
              "reports": [{"node": "test_state.py::test_submission", "phase": "call", "outcome": "failed",
                           "category": "invalid_submission", "exception_type": "AssertionError",
                           "detail": json.dumps(detail) + "\nassert False"}],
              "controller": {"worker_returncode": 1, "temporary_storage": "native_private", "temporary_parent": "/tmp",
                             "captured_bytes": 765, "observed_output_bytes": 765, "output_limit_bytes": 1048576}}
    verdict = {"schema_version": 2, "task_id": task, "task_version": VERSION, "grader_version": VERSION,
               "status": "fail", "artifact_correct": 0, "failure_category": "invalid_submission",
               "submission_manifest": records, "submission_digest": digest(records), "elapsed_sec": 1,
               "checks": checks, "evidence": {}, "runtime": {"python": "fixture"}}
    capture = {"schema_version": 2, "harness_version": HARNESS_VERSION, "task_id": task,
               "status": "error", "termination_reason": "max_turns", "files": [], "total_bytes": 0,
               "missing": ["repo"], "atomic": False, "final_state_verified": False,
               "issues": [{"error_type": "FileNotFoundError", "path": "", "reason": "archive_write_error"}]}
    save(trial / "agent/artifacts/manifest.json", capture)
    trace = {"schema_version": 2, "harness_version": HARNESS_VERSION, "version": HARNESS_VERSION,
             "task_id": task, "finished": False, "n_turns": 20, "n_shell": 20, "n_shell_attempts": 20,
             "n_parse_fail": 0, "termination_reason": "max_turns", "artifact_capture_status": "error",
             "artifact_manifest_path": "artifacts/manifest.json",
             "artifact_manifest_sha256": file_hash(trial / "agent/artifacts/manifest.json"), "calls": []}
    worker = {"status": "fail", "failure_category": "invalid_submission",
              "checks": {key: value for key, value in checks.items() if key != "controller"},
              "evidence": {}, "runtime": {"python": "fixture"}}
    save(trial / "verifier/worker-result.json", worker)
    save(trial / "verifier/verdict.json", verdict)
    save(trial / "agent/compact-shell-v2.json", trace)
    save(trial / "result.json", {"verifier_environment_mode": "separate", "task_checksum": "checksum"})
    save(directory / "jobs" / job / "config.json", {"fixture": True})
    staged = directory / "staged-tasks" / task
    staged.mkdir(parents=True)
    (staged / "task.toml").write_text("staged task", encoding="utf-8")
    visit = {"job_name": job, "task": task, "model": audit.MODEL, "status": "scored",
             "slot_id": f"{audit.MODEL}/{task}/r1", "started_at": "2026-10-29T00:30:00+08:00",
             "execution_lock_sha256": audit.LOCK_SHA, "authorization_sha256": "auth", "fee_waiver_sha256": "waiver"}
    save(directory / "visits" / (job + ".json"), visit)
    manifest = {"tasks": {task: {"staged_task_config_sha256": file_hash(staged / "task.toml"),
                                  "staged_tree_sha256": "tree"}},
                "schedule": [{"slot_id": visit["slot_id"], "task": task, "model": audit.MODEL, "repetition": 1}]}
    return {"root": root, "directory": directory, "trial": trial, "seed": seed, "task": task,
            "count": count, "verdict": verdict, "trace": trace, "capture": capture,
            "visit": visit, "manifest": manifest, "lock": {"execution_lock_sha256": audit.LOCK_SHA}}


def run_transport(value):
    return audit.audit_negative_transport(value["trial"], value["trace"], value["verdict"],
                                          value["task"], value["count"], value["seed"])


def tree_bytes(path):
    return {file.relative_to(path).as_posix(): file.read_bytes() for file in path.rglob("*") if file.is_file()}


@pytest.mark.parametrize("job", list(audit.TARGETS))
def test_negative_observation_is_proven_without_repairing_capture(tmp_path, job):
    value = case(tmp_path, job)
    before = tree_bytes(value["directory"])
    result = run_transport(value)
    assert result["observed_file_count"] == value["count"]
    assert result["negative_conclusion"] == {"artifact": False, "clean": False, "failure_category": "invalid_submission"}
    assert result["original_agent_capture_status"] == "error"
    assert result["complete_final_agent_capture_established"] is False
    assert result["outside_tests_scope_witnesses"]
    assert tree_bytes(value["directory"]) == before


@pytest.mark.parametrize("mutation", ["positive", "different_category", "different_capture_error", "capture_hash",
                                     "different_capture_identity", "capture_complete", "internal_error", "worker_conflict"])
def test_rejects_other_outcomes_and_capture_errors(tmp_path, mutation):
    value = case(tmp_path)
    if mutation == "positive":
        value["verdict"].update(status="pass", artifact_correct=1)
    elif mutation == "different_category":
        value["verdict"]["failure_category"] = "behavior_mismatch"
    elif mutation == "capture_hash":
        value["trace"]["artifact_manifest_sha256"] = "0" * 64
    elif mutation == "internal_error":
        value["verdict"]["checks"]["internal_errors"] = ["grader crashed"]
    elif mutation == "worker_conflict":
        worker = json.loads((value["trial"] / "verifier/worker-result.json").read_text())
        worker["evidence"] = {"unexpected": True}
        save(value["trial"] / "verifier/worker-result.json", worker)
    else:
        capture = deepcopy(value["capture"])
        if mutation == "different_capture_error":
            capture["issues"][0]["error_type"] = "PermissionError"
        elif mutation == "different_capture_identity":
            capture["task_id"] = "testgen-other"
        elif mutation == "capture_complete":
            capture["status"] = "complete"
        save(value["trial"] / "agent/artifacts/manifest.json", capture)
        value["trace"]["artifact_manifest_sha256"] = file_hash(value["trial"] / "agent/artifacts/manifest.json")
    with pytest.raises(V2Error):
        run_transport(value)


@pytest.mark.parametrize("mutation", ["bytes", "size", "role", "extra_file", "missing_file", "unsafe_path", "count", "no_scope_witness"])
def test_transport_proof_rejects_missing_changed_or_unobserved_material(tmp_path, mutation):
    value = case(tmp_path)
    row = next(row for row in value["verdict"]["submission_manifest"] if row["path"].endswith(".xml"))
    path = value["trial"] / "artifacts/submission" / row["path"]
    if mutation == "bytes":
        path.write_bytes(b"changed")
    elif mutation == "size":
        row["size_bytes"] += 1
    elif mutation == "role":
        row["role"] = "submission"
    elif mutation == "extra_file":
        (path.parent / "unobserved.txt").write_text("not graded")
    elif mutation == "missing_file":
        path.unlink()
    elif mutation == "unsafe_path":
        row["path"] = "repo/../../outside.xml"
    elif mutation == "count":
        value["count"] = 23
    elif mutation == "no_scope_witness":
        for record in value["verdict"]["submission_manifest"]:
            if record["path"].endswith(".xml"):
                (value["seed"] / Path(record["path"]).name).write_text("original fixture")
    value["verdict"]["submission_digest"] = digest(value["verdict"]["submission_manifest"])
    with pytest.raises(V2Error):
        run_transport(value)


def mock_prefix_and_suffix(monkeypatch):
    def rejected(*args, **kwargs):
        raise V2Error(audit.CAPTURE_REJECTION)
    monkeypatch.setattr(audit.frozen, "validate_scored_visit", rejected)
    monkeypatch.setattr(audit, "legacy_tree_digest", lambda path: "tree")
    monkeypatch.setattr(audit, "harbor_task_checksum", lambda path: "checksum")
    monkeypatch.setattr(audit.frozen, "validate_runtime_isolation", lambda *args: ["agent-none-proof", "grader-none-proof"])
    monkeypatch.setattr(audit, "validate_authorization", lambda *args: "auth")
    monkeypatch.setattr(audit, "validate_fee_waiver", lambda *args, **kwargs: "waiver")


def run_visit(value):
    return audit.audit_visit(value["visit"], value["manifest"], value["lock"], value["directory"], root=value["root"])


def test_canonical_negative_row_preserves_error_and_waiver_provenance(tmp_path, monkeypatch):
    value = case(tmp_path)
    mock_prefix_and_suffix(monkeypatch)
    before = tree_bytes(value["directory"])
    result = run_visit(value)
    row = result["canonical_row"]
    assert row["artifact"] is False and row["clean"] is False
    assert row["artifact_capture_status"] == "error"
    assert row["capture_supplement_scope"] == "original_invalid_submission_zero_only"
    assert len(row["static_network_isolation_evidence"]) == 2
    assert tree_bytes(value["directory"]) == before


@pytest.mark.parametrize("mutation", ["original_other_error", "original_success", "stage", "network", "authorization", "waiver", "unlisted_job", "other_model"])
def test_full_supplement_keeps_all_original_non_capture_checks(tmp_path, monkeypatch, mutation):
    value = case(tmp_path)
    mock_prefix_and_suffix(monkeypatch)
    if mutation == "original_other_error":
        def reject(*args, **kwargs):
            raise V2Error("config mismatch")
        monkeypatch.setattr(audit.frozen, "validate_scored_visit", reject)
    elif mutation == "original_success":
        monkeypatch.setattr(audit.frozen, "validate_scored_visit", lambda *args, **kwargs: {})
    elif mutation == "stage":
        value["manifest"]["tasks"][value["task"]]["staged_tree_sha256"] = "different"
    elif mutation == "network":
        def reject_network(*args):
            raise V2Error("original no-network proof absent")
        monkeypatch.setattr(audit.frozen, "validate_runtime_isolation", reject_network)
    elif mutation == "authorization":
        value["visit"]["authorization_sha256"] = "different"
    elif mutation == "waiver":
        value["visit"]["fee_waiver_sha256"] = "different"
    elif mutation == "unlisted_job":
        value["visit"]["job_name"] = "visit-" + "0" * 32
    elif mutation == "other_model":
        value["visit"]["model"] = "another-model"
    with pytest.raises(V2Error):
        run_visit(value)


def test_default_cli_is_read_only_and_output_is_exclusive(tmp_path, monkeypatch, capsys):
    directory = tmp_path / "p2"
    directory.mkdir()
    result = {"kind": "supplement", "supported_count": 2, "observed_file_count": 35,
              "admission_scope": "negative_only", "complete_final_agent_capture_established": False,
              "original_records_modified": False, "model_calls": 0, "container_calls": 0}
    monkeypatch.setattr(audit, "build_supplement", lambda directory: result)
    assert audit.main(["--directory", str(directory)]) == 0
    assert list(directory.iterdir()) == []
    output = directory / "audit.json"
    assert audit.main(["--directory", str(directory), "--output", str(output)]) == 0
    before = output.read_bytes()
    assert audit.main(["--directory", str(directory), "--output", str(output)]) == 2
    assert output.read_bytes() == before
    assert audit.main(["--directory", str(directory), "--output", str(tmp_path / "outside.json")]) == 2
    capsys.readouterr()
