"""Offline contracts for the additive release executor/analysis entry points."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

import analyze_release_v2 as analysis
import release_v2_executor as executor
import run_release_v2 as cli
from release_v2_pipeline import HARNESS_VERSION, VERSION, V2Error


def trace(task="edit-clip"):
    return {"schema_version": 2, "harness_version": HARNESS_VERSION,
            "version": HARNESS_VERSION, "task_id": task, "finished": True,
            "n_turns": 1, "n_shell": 1, "n_shell_attempts": 1,
            "n_parse_fail": 0, "termination_reason": "finish"}


def test_trace_retains_existing_harness_identity():
    assert analysis.validate_trace(trace(), "edit-clip")["version"] == HARNESS_VERSION
    changed = trace()
    changed["version"] = VERSION
    with pytest.raises(V2Error, match="version"):
        analysis.validate_trace(changed, "edit-clip")


def fixture_isolation(tmp_path):
    trial = tmp_path / "edit-clip__Abc1234"
    proof_dir = trial / "environment"
    proof_dir.mkdir(parents=True)
    images = ["sha256:" + "1" * 64, "sha256:" + "2" * 64]
    for index, suffix in enumerate(("__env", "__verifier__trial")):
        proof = {"schema_version": 1, "isolation": "docker-network-none",
                 "network_mode": "none", "verified": True,
                 "container_id": str(index + 3) * 64,
                 "session_id": trial.name + suffix, "image": images[index],
                 "image_id": images[index]}
        (proof_dir / f"static-network-{index}.json").write_text(json.dumps(proof), encoding="utf-8")
    raw = {"config": {"trial_name": trial.name}}
    manifest = {"runtime_environment_evidence": {
        "image_digests": {"edit-clip": images[0]},
        "grader_image_digests": {"edit-clip": images[1]}}}
    verdict = {"checks": {"controller": {
        "temporary_storage": "native_private", "temporary_parent": "/tmp"}}}
    return trial, raw, manifest, verdict


def test_original_isolation_and_native_tmp_required(tmp_path):
    trial, raw, manifest, verdict = fixture_isolation(tmp_path)
    assert len(analysis.validate_runtime_isolation(trial, raw, manifest, "edit-clip", verdict)) == 2


@pytest.mark.parametrize("fault", ["missing", "bridge", "image", "duplicate", "tmp", "trial"])
def test_runtime_evidence_tampering_rejected(tmp_path, fault):
    trial, raw, manifest, verdict = fixture_isolation(tmp_path)
    first = trial / "environment" / "static-network-0.json"
    if fault == "missing":
        first.unlink()
    elif fault in {"bridge", "image", "duplicate"}:
        proof = json.loads(first.read_text(encoding="utf-8"))
        if fault == "bridge":
            proof["network_mode"] = "bridge"
        elif fault == "image":
            proof["image_id"] = "sha256:" + "9" * 64
        else:
            proof["container_id"] = "4" * 64
        first.write_text(json.dumps(proof), encoding="utf-8")
    elif fault == "tmp":
        verdict["checks"]["controller"]["temporary_parent"] = "/host-tmp"
    else:
        raw["config"]["trial_name"] = "other"
    with pytest.raises(ValueError):
        analysis.validate_runtime_isolation(trial, raw, manifest, "edit-clip", verdict)


def test_release_authorization_does_not_inherit_old_budget(tmp_path):
    with pytest.raises(V2Error, match="absent"):
        executor.validate_authorization(tmp_path, {"caps": {"budget_usd": 40}}, {})


def test_manifest_bound_authorization_is_required(tmp_path):
    manifest = {"manifest_sha256": "a" * 64, "caps": {"budget_usd": 40}}
    lock = {"execution_lock_sha256": "b" * 64}
    approval = {"schema_version": 2,
                "kind": "smallowbench_v2_model_execution_authorization",
                "approved_by_user": True, "manifest_sha256": "a" * 64,
                "execution_lock_sha256": "b" * 64, "budget_usd": 40}
    target = tmp_path / "authorization.json"
    target.write_text(json.dumps(approval), encoding="utf-8")
    assert len(executor.validate_authorization(tmp_path, manifest, lock)) == 64
    approval["budget_usd"] = 41
    target.write_text(json.dumps(approval), encoding="utf-8")
    with pytest.raises(V2Error):
        executor.validate_authorization(tmp_path, manifest, lock)


def test_cli_keeps_prepare_nonexecuting_and_binds_runtime(monkeypatch, capsys):
    captured = {}
    def build(*args, **kwargs):
        captured.update(kwargs)
        return {"manifest_sha256": "a" * 64, "models": {"x": {}},
                "n_planned_trials": 496}, "not written"
    monkeypatch.setattr(cli, "build_manifest", build)
    monkeypatch.setattr(cli, "planned_task_units", lambda value: 62)
    assert cli.main(["prepare", "--directory", "unused", "--models-file", "models.json",
                     "--preflight", "proof.json", "--runtime", "runtime.json",
                     "--budget-usd", "40", "--workers", "4"]) == 0
    result = json.loads(capsys.readouterr().out)
    assert captured["runtime_path"] == Path("runtime.json")
    assert captured["workers"] == 4
    assert result["written"] is False and result["model_calls"] == 0
    assert result["execution_authorized"] is False


def test_new_execution_modules_do_not_import_old_entry_points():
    for module in (analysis, executor, cli):
        source = Path(module.__file__).read_text(encoding="utf-8")
        assert "from v2_pipeline import" not in source
        assert "from v2_executor import" not in source
        assert "from analyze_v2 import" not in source
