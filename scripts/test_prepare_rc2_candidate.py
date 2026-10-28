"""Additive candidate construction/provenance tests; no model/container calls."""
from __future__ import annotations

import json
from pathlib import Path
import shutil
from types import SimpleNamespace
from unittest.mock import patch

import pytest

import prepare_rc2_candidate as candidate
from validate_upgraded_tasks import task_digest
import v2_pipeline


@pytest.fixture(scope="module")
def copied_source(tmp_path_factory):
    root = tmp_path_factory.mktemp("r2")
    for name in candidate.protected_files():
        source = candidate.ROOT / name
        target = root / name
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, target)
    for name in ("scripts/prepare_rc2_candidate.py", "scripts/rc2_task_patches.py"):
        shutil.copyfile(candidate.ROOT / name, root / name)
    return root


@pytest.fixture(scope="module")
def built(copied_source):
    root = copied_source
    before = candidate.protected_files(root)
    output = root / "task-banks" / "rc2"
    result = candidate.build_candidate(output, root=root)
    assert candidate.protected_files(root) == before
    return root, output, result


def test_builder_is_additive_and_explicitly_not_activated(built):
    root, output, manifest = built
    assert manifest["task_count"] == 62
    assert manifest["model_runs_authorized"] is False
    assert manifest["container_validated"] is False
    assert manifest["active_pipeline_compatible"] is False
    assert manifest["harness_version"] == candidate.SOURCE_VERSION
    assert manifest["harness_changed"] is False
    assert candidate.validate_candidate(output, root=root) == manifest
    assert (root / "VERSION").read_text().strip() == candidate.SOURCE_VERSION
    assert manifest["source_rc1_manifest"]["sha256"] == candidate.sha(root / "task-bank-v2.manifest.json")


def test_build_never_overwrites_existing_bank(built):
    root, output, manifest = built
    old_hash = candidate.sha(output / "task-bank-v2.manifest.json")
    with pytest.raises(ValueError, match="no overwrite"):
        candidate.build_candidate(output, root=root)
    assert candidate.sha(output / "task-bank-v2.manifest.json") == old_hash


@pytest.mark.parametrize("name", ("tasks", "experiments", "other", "task-banks/rc1"))
def test_reserved_or_wrong_outputs_rejected(copied_source, name):
    with pytest.raises(ValueError, match="new task-banks/rc2"):
        candidate.build_candidate(copied_source / name, root=copied_source)


def test_all_candidate_versions_hashes_and_readme_baselines_match(built):
    root, output, manifest = built
    for row in manifest["items"]:
        task = output / "tasks" / row["id"]
        assert row["task_version"] == candidate.VERSION
        assert row["task_sha256"] == task_digest(task)
        config = json.loads((task / "tests/grader_config.json").read_text())
        assert config["task_version"] == config["grader_version"] == candidate.VERSION
        assert f'VERSION = "{candidate.VERSION}"' in (task / "tests/verdict_v2.py").read_text()
        if row["skill"] in {"testgen", "repro"}:
            assert (task / "environment/repo/README.md").read_bytes() == (task / "tests/baseline/README.md").read_bytes()
            assert "The agent may read" in (task / "environment/repo/README.md").read_text()
        assert (task / "instruction.md").read_bytes() == (root / "tasks" / row["id"] / "instruction.md").read_bytes()


def test_old_pipeline_refuses_rc2_instead_of_silently_reusing_preflight(built):
    root, output, manifest = built
    with pytest.raises(v2_pipeline.V2Error, match="digest/version"):
        v2_pipeline.load_bank(output / "task-bank-v2.manifest.json", root=root)


def test_candidate_tamper_is_detected_without_rewriting_manifest(built):
    root, output, manifest = built
    path = output / "tasks/review-clip-incomplete/instruction.md"
    original = path.read_bytes()
    try:
        path.write_bytes(original + b"\nsynthetic tamper\n")
        with pytest.raises(ValueError, match="fingerprint"):
            candidate.validate_candidate(output, root=root)
    finally:
        path.write_bytes(original)
    assert candidate.validate_candidate(output, root=root) == manifest


def test_exact_anchor_failure_is_not_silently_ignored():
    with pytest.raises(ValueError, match="exactly one"):
        candidate.replace_once("missing", "old", "new")
    with pytest.raises(ValueError, match="exactly one"):
        candidate.replace_once("old old", "old", "new")


def test_validation_entry_rejects_empty_duplicate_or_unknown_selection():
    import validate_rc2_candidate as validation

    with patch.object(validation, "sha", return_value="unused"), patch.object(validation, "validate_candidate", return_value={}), patch.object(validation, "local_validator", side_effect=AssertionError("must not execute")):
        for tasks in ([], ["testgen-clip", "testgen-clip"], ["unknown"]):
            with pytest.raises(ValueError, match="explicit unique"):
                validation.validate_cases(Path("unused"), tasks)


@pytest.mark.parametrize("key,value", (
    ("harness_version", candidate.VERSION), ("harness_changed", True),
    ("grader_version", candidate.SOURCE_VERSION), ("benchmark_version", candidate.SOURCE_VERSION),
    ("active_pipeline_compatible", True), ("release_status", "active"),
    ("scores_comparable_to_rc1", True),
))
def test_rehashed_activation_metadata_is_not_trusted(built, key, value):
    root, output, manifest = built
    path = output / "task-bank-v2.manifest.json"
    original = path.read_bytes()
    try:
        changed = {**manifest, key: value}
        changed["manifest_sha256"] = candidate.document_digest(changed)
        candidate.write_text(path, json.dumps(changed))
        with pytest.raises(ValueError, match="metadata"):
            candidate.validate_candidate(output, root=root)
    finally:
        path.write_bytes(original)


@pytest.mark.parametrize("relative", ("task.toml", "tests/grader_config.json"))
def test_actual_rc1_version_is_rejected_even_when_fingerprints_are_rehashed(built, relative):
    root, output, manifest = built
    task_name = "testgen-timeout-zero"
    task = output / "tasks" / task_name
    path = task / relative
    manifest_path = output / "task-bank-v2.manifest.json"
    original, original_manifest = path.read_bytes(), manifest_path.read_bytes()
    try:
        candidate.write_text(path, path.read_text().replace(candidate.VERSION, candidate.SOURCE_VERSION))
        altered = json.loads(original_manifest)
        next(row for row in altered["items"] if row["id"] == task_name)["task_sha256"] = task_digest(task)
        altered["manifest_sha256"] = candidate.document_digest(altered)
        candidate.write_text(manifest_path, json.dumps(altered))
        with pytest.raises(ValueError, match="actual task/controller version"):
            candidate.validate_candidate(output, root=root)
    finally:
        path.write_bytes(original)
        manifest_path.write_bytes(original_manifest)


def test_changes_are_limited_to_versions_contract_docs_and_grader(built):
    root, output, manifest = built
    universal = {"task.toml", "tests/grader_config.json", "tests/verdict_v2.py"}
    for row in manifest["changes"]:
        allowed = set(universal)
        if row["task"].startswith("review-"):
            allowed.add("tests/test_state.py")
        elif row["task"].startswith(("testgen-", "repro-")):
            allowed.update({"tests/verifier.py", "environment/repo/README.md", "tests/baseline/README.md"})
        assert row["path"] in allowed


def test_private_validator_instances_do_not_mutate_old_global_root():
    import validate_rc2_candidate as validation
    import validate_upgraded_tasks as shared

    original = shared.ROOT
    first = validation.local_validator(Path("one"))
    second = validation.local_validator(Path("two"))
    assert first is not second and first.ROOT != second.ROOT
    assert shared.ROOT == original


def unit_bank_and_row():
    task = "testgen-timeout-zero"
    bank = {"manifest_sha256": "synthetic", "items": [{"id": task, "task_sha256": "fixture"}]}
    row = {"task": task, "mode": "oracle", "task_sha256": "fixture", "source_unchanged": True,
           "ok": True, "controller_validated": True, "reward_consistent": True,
           "verdict": {"task_id": task, "task_version": candidate.VERSION, "grader_version": candidate.VERSION}}
    return bank, row


@pytest.mark.parametrize("change", (
    {"task_sha256": "wrong"}, {"source_unchanged": False}, {"controller_validated": False},
    {"reward_consistent": False}, {"verdict": None},
    {"verdict": {"task_id": "wrong", "task_version": candidate.VERSION, "grader_version": candidate.VERSION}},
    {"verdict": {"task_id": "testgen-timeout-zero", "task_version": candidate.SOURCE_VERSION, "grader_version": candidate.VERSION}},
))
def test_local_positive_claims_require_matching_raw_evidence(change):
    import validate_rc2_candidate as validation

    bank, row = unit_bank_and_row()
    row.update(change)
    with patch.object(validation, "validate_candidate", return_value=bank), patch.object(validation, "sha", return_value="hash"), patch.object(validation, "local_validator", return_value=SimpleNamespace(validate_case=lambda *args: row)):
        with pytest.raises(ValueError):
            validation.validate_cases(Path("unused"), [row["task"]], modes=("oracle",))


def test_manifest_cannot_be_replaced_during_local_validation():
    import validate_rc2_candidate as validation

    bank, row = unit_bank_and_row()
    hashes = iter(["before", "after"])
    with patch.object(validation, "validate_candidate", return_value=bank), patch.object(validation, "sha", side_effect=lambda path: next(hashes) if path.name == "task-bank-v2.manifest.json" else "source"), patch.object(validation, "local_validator", return_value=SimpleNamespace(validate_case=lambda *args: row)):
        with pytest.raises(ValueError, match="manifest changed"):
            validation.validate_cases(Path("unused"), [row["task"]], modes=("oracle",))


def test_invalid_workers_do_not_execute_local_fixtures():
    import validate_rc2_candidate as validation

    bank, row = unit_bank_and_row()
    with patch.object(validation, "validate_candidate", return_value=bank), patch.object(validation, "sha", return_value="hash"), patch.object(validation, "local_validator", side_effect=AssertionError("must not execute")):
        for workers in (True, 0, 5, 1.5):
            with pytest.raises(ValueError):
                validation.validate_cases(Path("unused"), [row["task"]], workers=workers)


@pytest.mark.parametrize("relative", ("tasks", "tasks/testgen-timeout-zero", "task-bank-v2.manifest.json", "VERSION"))
def test_candidate_links_at_roots_and_metadata_are_rejected(built, monkeypatch, relative):
    root, output, manifest = built
    target = output / relative
    original = Path.is_symlink
    monkeypatch.setattr(Path, "is_symlink", lambda path: path == target or original(path))
    with pytest.raises(ValueError, match="link or junction"):
        candidate.validate_candidate(output, root=root)


@pytest.mark.parametrize("key,value", (("task_count", 61), ("skill_counts", {}), ("source_rc1_manifest", {})))
def test_descriptive_counts_and_source_binding_cannot_be_forged(built, key, value):
    root, output, manifest = built
    path = output / "task-bank-v2.manifest.json"
    original = path.read_bytes()
    try:
        changed = {**manifest, key: value}
        changed["manifest_sha256"] = candidate.document_digest(changed)
        candidate.write_text(path, json.dumps(changed))
        with pytest.raises(ValueError):
            candidate.validate_candidate(output, root=root)
    finally:
        path.write_bytes(original)
