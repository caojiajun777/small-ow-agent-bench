"""Offline scoring boundary/aggregation contracts; no model, network or Docker."""
from __future__ import annotations

import copy
import json
from types import SimpleNamespace

import pytest

import analyze_release_v2 as frozen
import provider_reassessment_scoring_v2 as scorer
import release_v2_pipeline as pipeline


def save(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value), encoding="utf-8")
    return path


def profile(route="parasail/bf16"):
    return {"runtime_id": "openrouter/qwen/qwen3.5-9b", "route": route,
            "agent_kwargs": {"max_turns": 20, "llm_call_kwargs": {
                "temperature": 0, "top_p": 1, "max_tokens": 8192,
                "extra_body": {"reasoning": {"enabled": False}, "enable_thinking": False,
                               "provider": {"order": [route], "only": [route],
                                            "allow_fallbacks": False, "require_parameters": True,
                                            "quantizations": ["bf16"]}}}}}


@pytest.fixture
def scored_fixture(tmp_path, monkeypatch):
    directory = tmp_path / "p3"
    directory.mkdir()
    task, model, job = "edit-clip", scorer.MODEL_ID, "visit-fixture"
    slot = {"slot_id": model + "/" + task + "/r1", "model": model, "task": task,
            "repetition": 1, "sequence": 1}
    manifest = {"manifest_sha256": "a" * 64, "directory": str(directory.resolve()),
                "caps": {"budget_usd": None, "max_visits_per_slot": 3, "max_total_visits": 186},
                "models": {model: profile("primeintellect/bf16")}, "tasks": {},
                "agent_import_path": "agents.compact_shell_v2:CompactShellV2Agent",
                "schedule": [slot], "repetitions": 1,
                "runtime_environment_evidence": {"backend": "docker",
                    "image_digests": {task: "sha256:" + "1" * 64},
                    "grader_image_digests": {task: "sha256:" + "2" * 64}},
                "source_hashes": {name: pipeline.file_hash(pipeline.ROOT / name)
                                  for name in scorer.LEGACY_SOURCES}}
    lock = {"execution_lock_sha256": "b" * 64}
    save(directory / "execution-lock.json", lock)
    new_auth = {"schema_version": 2, "kind": "smallowbench_v2_provider_execution_authorization",
                "approved_by_user": True, "manifest_sha256": manifest["manifest_sha256"],
                "execution_lock_sha256": lock["execution_lock_sha256"]}
    auth_path = save(directory / "authorization.json", new_auth)
    expected = pipeline.job_config(manifest, slot, job, directory)
    generated = save(directory / "configs" / (job + ".json"), expected)
    executed = save(directory / "jobs" / job / "config.json", expected)
    trial = directory / "jobs" / job / (task + "__fixture")
    submission = trial / "agent" / "artifacts" / "repo" / "app.py"
    submission.parent.mkdir(parents=True)
    submission.write_text("result = 1\n", encoding="utf-8")
    observed = [{"path": "repo/app.py", "role": "submission", "size_bytes": submission.stat().st_size,
                 "sha256": pipeline.file_hash(submission)}]
    capture = {"schema_version": 2, "harness_version": pipeline.HARNESS_VERSION,
               "task_id": task, "status": "complete", "files": [
                   {"path": row["path"], "role": row["role"], "size": row["size_bytes"],
                    "sha256": row["sha256"]} for row in observed], "missing": [], "issues": []}
    capture_path = save(trial / "agent" / "artifacts" / "manifest.json", capture)
    trace = {"schema_version": 2, "harness_version": pipeline.HARNESS_VERSION,
             "version": pipeline.HARNESS_VERSION, "task_id": task, "finished": True,
             "n_turns": 2, "n_shell": 1, "n_shell_attempts": 1, "n_parse_fail": 0,
             "termination_reason": "finish", "artifact_capture_status": "complete",
             "artifact_manifest_path": "artifacts/manifest.json",
             "artifact_manifest_sha256": pipeline.file_hash(capture_path),
             "calls": [{"kind": "api", "elapsed_seconds": 1.5},
                       {"kind": "shell", "elapsed_seconds": .2}],
             "usage": {"input_tokens": 10, "output_tokens": 20}}
    trace_path = save(trial / "agent" / "compact-shell-v2.json", trace)
    verdict = {"schema_version": 2, "task_id": task, "task_version": pipeline.VERSION,
               "grader_version": pipeline.VERSION, "status": "pass", "artifact_correct": 1,
               "submission_manifest": observed, "submission_digest": pipeline.digest(observed),
               "elapsed_sec": .2, "failure_category": None, "evidence": [],
               "checks": {"controller": {"temporary_storage": "native_private", "temporary_parent": "/tmp"}}}
    verdict_path = save(trial / "verifier" / "verdict.json", verdict)
    staged = directory / "staged-tasks" / task
    staged.mkdir(parents=True)
    (staged / "task.toml").write_text("# synthetic checksum fixture\n", encoding="utf-8")
    manifest["tasks"][task] = {"skill": "edit",
        "staged_task_config_sha256": pipeline.file_hash(staged / "task.toml"),
        "staged_tree_sha256": pipeline.legacy_tree_digest(staged)}
    # Only Harbor's unrelated task parser is replaced. Config, capture, metadata,
    # verdict, reward, isolation, authorization and traceback checks are genuine.
    monkeypatch.setattr(frozen, "harbor_task_checksum", pipeline.legacy_tree_digest)
    raw = {"task_name": "fixture/" + task, "config": {
        "agent": expected["agents"][0], "task": expected["tasks"][0],
        "timeout_multiplier": 1, "environment": {"type": "docker"}, "trial_name": trial.name},
        "agent_result": {"metadata": copy.deepcopy(trace)}, "verifier_result": {"rewards": {"reward": 1}},
        "verifier_environment_mode": "separate", "task_checksum": pipeline.legacy_tree_digest(staged)}
    result_path = save(trial / "result.json", raw)
    for index, suffix in enumerate(("__env", "__verifier__trial")):
        image = "sha256:" + str(index + 1) * 64
        save(trial / "environment" / ("static-network-" + str(index) + ".json"), {
            "schema_version": 1, "isolation": "docker-network-none", "network_mode": "none",
            "verified": True, "container_id": str(index + 3) * 64,
            "session_id": trial.name + suffix, "image": image, "image_id": image})
    visit = {**slot, "job_name": job, "manifest_sha256": manifest["manifest_sha256"],
             "started_at": "2026-10-29T00:00:00+00:00", "status": "scored", "visit": 1,
             "counts_toward_cap": True, "config_sha256": pipeline.file_hash(executed),
             "generated_config_sha256": pipeline.file_hash(generated),
             "executed_config_sha256": pipeline.file_hash(executed),
             "execution_lock_sha256": lock["execution_lock_sha256"],
             "authorization_sha256": pipeline.file_hash(auth_path), "atomic_correct": 1, "termination": "clean",
             "request_contract": {"classification": "frozen_request_contract_verified", "receipts": []}}

    def validate_auth(directory, manifest, lock, **kwargs):
        value = pipeline.read_json(directory / "authorization.json")
        if value != new_auth or manifest["caps"]["budget_usd"] is not None:
            raise pipeline.V2Error("invalid provider authorization")
        return pipeline.file_hash(directory / "authorization.json")

    core = SimpleNamespace(validate_manifest=lambda *args, **kwargs: manifest,
                           validate_lock=lambda *args, **kwargs: lock,
                           validate_authorization=validate_auth,
                           validate_request_contract=lambda *args: visit["request_contract"])
    monkeypatch.setattr(scorer, "_core", lambda: core)
    return SimpleNamespace(**locals())


def test_new_authorization_matches_unchanged_legacy_canonical_row(scored_fixture):
    f = scored_fixture
    actual = scorer.validate_scored_visit(f.visit, f.manifest, f.directory)
    # Generate the legacy result under a genuine legacy authorization, then
    # compare every canonical/resource field rather than only the final score.
    f.manifest["caps"]["budget_usd"] = 40
    save(f.auth_path, {**f.new_auth, "kind": "smallowbench_v2_model_execution_authorization", "budget_usd": 40})
    f.visit["authorization_sha256"] = pipeline.file_hash(f.auth_path)
    expected = frozen.validate_scored_visit(f.visit, f.manifest, f.directory)
    assert actual == expected
    assert actual["resources"]["api_seconds"] == 1.5


@pytest.mark.parametrize("fault", ["missing", "unapproved", "wrong_visit"])
def test_new_authorization_is_required_before_legacy_boundary(scored_fixture, fault):
    f = scored_fixture
    if fault == "missing":
        f.auth_path.unlink()
    elif fault == "unapproved":
        save(f.auth_path, {**f.new_auth, "approved_by_user": False})
    else:
        f.visit["authorization_sha256"] = "c" * 64
    with pytest.raises((ValueError, OSError)):
        scorer.validate_scored_visit(f.visit, f.manifest, f.directory)


@pytest.mark.parametrize("fault", ["capture_error", "missing_capture", "metadata", "reward", "stage", "network", "source"])
def test_every_early_evidence_failure_remains_rejected(scored_fixture, fault):
    f = scored_fixture
    if fault == "capture_error":
        f.capture["status"] = "error"
        save(f.capture_path, f.capture)
        f.trace["artifact_capture_status"] = "error"
        f.trace["artifact_manifest_sha256"] = pipeline.file_hash(f.capture_path)
        save(f.trace_path, f.trace)
        f.raw["agent_result"]["metadata"] = f.trace
        save(f.result_path, f.raw)
    elif fault == "missing_capture":
        f.capture_path.unlink()
    elif fault == "metadata":
        f.raw["agent_result"]["metadata"]["n_turns"] += 1
        save(f.result_path, f.raw)
    elif fault == "reward":
        f.raw["verifier_result"]["rewards"]["reward"] = 0
        save(f.result_path, f.raw)
    elif fault == "stage":
        (f.staged / "task.toml").write_text("changed", encoding="utf-8")
    elif fault == "network":
        (f.trial / "environment" / "static-network-0.json").unlink()
    else:
        f.manifest["source_hashes"][scorer.LEGACY_SOURCES[0]] = "d" * 64
    with pytest.raises((ValueError, OSError)):
        scorer.validate_scored_visit(f.visit, f.manifest, f.directory)


def test_same_error_at_wrong_frame_cannot_bypass_capture(scored_fixture, monkeypatch):
    def counterfeit(*args):
        raise pipeline.V2Error(scorer.AUTH_BOUNDARY_ERROR)
    monkeypatch.setattr(frozen, "_validate_capture", counterfeit)
    with pytest.raises(pipeline.V2Error, match="positive budget"):
        scorer.validate_scored_visit(scored_fixture.visit, scored_fixture.manifest, scored_fixture.directory)


def test_replaced_auth_function_cannot_forge_terminal_boundary(scored_fixture, monkeypatch):
    def counterfeit(*args):
        raise pipeline.V2Error(scorer.AUTH_BOUNDARY_ERROR)
    monkeypatch.setattr(scorer.legacy, "validate_authorization", counterfeit)
    with pytest.raises(pipeline.V2Error, match="identity changed"):
        scorer.validate_scored_visit(scored_fixture.visit, scored_fixture.manifest, scored_fixture.directory)
    try:
        counterfeit()
    except pipeline.V2Error as error:
        assert not scorer._terminal_authorization_boundary(error)


def test_request_contract_drift_cannot_be_scored(scored_fixture):
    f = scored_fixture
    def reject(*args):
        raise pipeline.V2Error("actual provider request dropped/changed a frozen request parameter")
    f.core.validate_request_contract = reject
    with pytest.raises(pipeline.V2Error, match="request dropped"):
        scorer.validate_scored_visit(f.visit, f.manifest, f.directory)


def test_attempt_policy_allows_typed_infra_then_score_but_never_answer_retry():
    manifest = {"caps": {"max_visits_per_slot": 3, "max_total_visits": 186}}
    rows = [{"slot_id": "s", "visit": index, "job_name": str(index), "counts_toward_cap": True,
             "started_at": "2026-10-29T00:02:01+00:00" if index == 2 else "2026-10-29T00:00:00+00:00",
             "finished_at": "2026-10-29T00:00:01+00:00", "status": status,
             "provider_failure": {"classification": "evidence_confirmed_provider_infra", "http_status": 429}}
            for index, status in enumerate(("infra", "scored"), 1)]
    assert scorer._attempt_policy(rows, manifest) == []
    rows[0]["status"] = "scored"
    assert scorer._attempt_policy(rows, manifest)[0]["kind"] == "answer_based_or_unresolved_retry"


@pytest.mark.parametrize("fault", ["permanent", "too_early", "retry_after"])
def test_provider_retry_requires_transient_evidence_and_elapsed_cooldown(fault):
    manifest = {"caps": {"max_visits_per_slot": 3, "max_total_visits": 186}}
    first = {"slot_id": "s", "visit": 1, "job_name": "first", "counts_toward_cap": True,
             "status": "infra", "started_at": "2026-10-29T00:00:00+00:00",
             "finished_at": "2026-10-29T00:00:01+00:00",
             "provider_failure": {"classification": "evidence_confirmed_provider_infra", "http_status": 429}}
    second = {**copy.deepcopy(first), "visit": 2, "job_name": "second", "status": "scored",
              "started_at": "2026-10-29T00:02:01+00:00"}
    if fault == "permanent":
        first["provider_failure"]["http_status"] = 400
    elif fault == "too_early":
        second["started_at"] = "2026-10-29T00:02:00+00:00"
    else:
        first["provider_failure"]["retry_after_seconds"] = 300
    issues = scorer._attempt_policy([first, second], manifest)
    assert any(issue["kind"] in ("answer_based_or_unresolved_retry", "provider_retry_before_cooldown")
               for issue in issues)


def roster_fixture(tmp_path):
    tasks = {task: {"skill": task.split("-", 1)[0]} for task in pipeline.BANK_62}
    old_models = {model: profile() for model in scorer.COMPLETE_PARENT_MODELS | {scorer.OLD_MODEL_ID}}
    parent = {"manifest_sha256": "a" * 64, "models": old_models, "tasks": tasks,
              "repetitions": 1, "scoring": {"macro": "five equal skills"}, "source_hashes": {},
              "schedule": pipeline.frozen_schedule(old_models, tasks, 1)}
    new = {**copy.deepcopy(parent), "manifest_sha256": "b" * 64,
           "models": {scorer.MODEL_ID: profile("primeintellect/bf16")}}
    new["publication_roster"] = {
        "policy": "seven_complete_parent_configurations_plus_independent_full_62_new_provider",
        "models": {**{model: old_models[model] for model in scorer.COMPLETE_PARENT_MODELS},
                   scorer.MODEL_ID: new["models"][scorer.MODEL_ID]},
        "excluded_parent_model": scorer.OLD_MODEL_ID,
        "parent_partial_observations_may_fill_new_provider_slots": False,
        "selection_frozen_before_new_provider_results": True,
    }
    new["schedule"] = pipeline.frozen_schedule(new["models"], tasks, 1)
    def report(manifest, accepted):
        rows = [{**slot, "job_name": "j" + str(index), "started_at": "2026-10-29T00:00:00+00:00",
                 "artifact": index % 2 == 0, "clean": index % 3 == 0}
                for index, slot in enumerate(manifest["schedule"])
                if slot["model"] != scorer.OLD_MODEL_ID or index % 2 == 0]
        return {"kind": "fresh_unit_evidence", "accepted": accepted,
                "formal_ranking_eligible": accepted, "manifest_sha256": manifest["manifest_sha256"],
                "canonical_rows": rows, "leaderboard": frozen.leaderboard(rows, manifest) if accepted else {},
                "issues": [], "completeness": {"duplicates": {}, "unresolved": []}}
    parent_report, new_report = report(parent, False), report(new, True)
    p2, p3 = tmp_path / "p2", tmp_path / "p3"
    for directory, manifest in ((p2, parent), (p3, new)):
        save(directory / "manifest.json", manifest)
        save(directory / "execution-lock.json", {})
    return parent, new, parent_report, new_report, p2, p3


@pytest.mark.parametrize("fault", [None, "invalid_capture", "active", "duplicate_scored"])
def test_report_uses_62_unique_valid_scores_not_infra_as_zero(tmp_path, monkeypatch, fault):
    _, manifest, _, source_report, _, directory = roster_fixture(tmp_path)
    manifest.update({key: value for key, value in (
        ("benchmark_version", pipeline.VERSION), ("task_version", pipeline.VERSION),
        ("grader_version", pipeline.VERSION), ("harness_version", pipeline.HARNESS_VERSION),
        ("scorer_version", pipeline.SCORER_VERSION))})
    manifest["caps"] = {"max_total_visits": 186, "max_visits_per_slot": 3}
    import provider_reassessment_v2 as core
    fake_core = SimpleNamespace(validate_manifest=lambda *args, **kwargs: manifest,
                                retryable=core.retryable, RETRY_POLICY=core.RETRY_POLICY)
    monkeypatch.setattr(scorer, "_core", lambda: fake_core)
    monkeypatch.setattr(scorer, "_validated_authorization", lambda *args: ({"execution_lock_sha256": "c" * 64}, "d" * 64))
    monkeypatch.setattr(scorer, "_claim_consistency", lambda *args: [])
    monkeypatch.setattr(scorer, "active_claims", lambda *args: ["active"] if fault == "active" else [])
    rows_by_job = {}
    for index, canonical in enumerate(source_report["canonical_rows"]):
        row = {**canonical, "manifest_sha256": manifest["manifest_sha256"], "status": "scored",
               "visit": 1, "counts_toward_cap": True, "finished_at": "2026-10-29T00:05:00+00:00"}
        if index == 0:
            row["visit"] = 2
            row["started_at"] = "2026-10-29T00:02:01+00:00"
            prior = {**row, "visit": 1, "job_name": "infra-first", "status": "infra",
                     "started_at": "2026-10-29T00:00:00+00:00", "finished_at": "2026-10-29T00:00:01+00:00",
                     "provider_failure": {"classification": "evidence_confirmed_provider_infra", "http_status": 429}}
            save(directory / "visits" / "infra-first.json", prior)
        save(directory / "visits" / (row["job_name"] + ".json"), row)
        rows_by_job[row["job_name"]] = {**canonical, "started_at": row["started_at"]}
    if fault == "duplicate_scored":
        duplicate = {**row, "visit": 2, "job_name": "duplicate-scored",
                     "started_at": "2026-10-29T00:03:00+00:00"}
        save(directory / "visits" / "duplicate-scored.json", duplicate)
        rows_by_job["duplicate-scored"] = {**rows_by_job[row["job_name"]], "job_name": "duplicate-scored"}
    def validate(visit, *args, **kwargs):
        if fault == "invalid_capture" and visit["job_name"] == "j0":
            raise pipeline.V2Error("capture is missing, erroneous, or identity-mismatched")
        return rows_by_job[visit["job_name"]]
    monkeypatch.setattr(scorer, "validate_scored_visit", validate)
    monkeypatch.setattr(scorer, "_infra_evidence", lambda *args: {"job": "infra-first", "contributes_to_score": False})
    result = scorer.build_report(directory)
    assert result["accepted"] is (fault is None)
    assert result["infra_visits"] == [{"job": "infra-first", "contributes_to_score": False}]
    if fault is None:
        assert result["completeness"]["legal_unique"] == 62
        assert result["leaderboard"] == frozen.leaderboard(source_report["canonical_rows"], manifest)
    elif fault == "invalid_capture":
        assert result["completeness"]["legal_unique"] == 61
        assert len(result["completeness"]["missing"]) == 1


def test_claim_database_and_export_must_agree(tmp_path):
    from experiment_execution import ClaimStore
    directory = tmp_path / "p3"
    directory.mkdir()
    store = ClaimStore(directory / "claims.sqlite3", manifest_sha256="a" * 64)
    claim = store.claim("slot", "synthetic-owner", model=scorer.MODEL_ID, reserve_usd=3.5, budget_usd=None)
    store.complete(claim.token, "synthetic-owner", "scored", {"atomic_correct": 0}, charged_usd=.01)
    export = store.publish_visit(claim, directory / "visits")
    visits, issues = pipeline.read_visits(directory)
    assert issues == [] and scorer._claim_consistency(directory, visits) == []
    altered = pipeline.read_json(export)
    altered["atomic_correct"] = 1
    assert scorer._claim_consistency(directory, [altered])[0]["kind"] == "claim_export_content_mismatch"
    assert scorer._claim_consistency(directory, [])[0]["kind"] == "claim_export_coverage_mismatch"


def test_join_is_independent_complete_roster_with_no_parasail_rows(tmp_path):
    parent, new, old_report, report, p2, p3 = roster_fixture(tmp_path)
    original = copy.deepcopy(old_report)
    joined = scorer.join_roster(report, old_report, new, parent, directory=p3, parent_directory=p2)
    assert joined["accepted"] and len(joined["canonical_rows"]) == 496
    assert scorer.OLD_MODEL_ID not in joined["leaderboard"]
    assert len(joined["source_coverage"]) == 8
    assert old_report == original and old_report["accepted"] is False
    assert joined["leaderboard"] == frozen.leaderboard(
        joined["canonical_rows"], joined["superseding_roster_manifest"])
    assert joined["source_coverage"][scorer.MODEL_ID]["source_directory"] == str(p3.resolve())


@pytest.mark.parametrize("fault", ["partial_new", "partial_parent", "extra_model", "extra_row", "identity", "duplicate", "drift", "precision", "task_drift"])
def test_incomplete_or_different_configuration_cannot_join(tmp_path, fault):
    parent, new, old_report, report, p2, p3 = roster_fixture(tmp_path)
    if fault == "partial_new":
        report["canonical_rows"].pop()
    elif fault == "partial_parent":
        index = next(i for i, row in enumerate(old_report["canonical_rows"])
                     if row["model"] in scorer.COMPLETE_PARENT_MODELS)
        old_report["canonical_rows"].pop(index)
    elif fault == "extra_model":
        new["models"]["unapproved"] = profile()
    elif fault == "extra_row":
        report["canonical_rows"].append({**report["canonical_rows"][0], "model": "unapproved"})
    elif fault == "identity":
        report["canonical_rows"][0]["sequence"] = 999
    elif fault == "duplicate":
        report["canonical_rows"][-1] = report["canonical_rows"][0]
    elif fault == "drift":
        new["models"][scorer.MODEL_ID]["agent_kwargs"]["max_turns"] = 30
    elif fault == "precision":
        new["models"][scorer.MODEL_ID]["agent_kwargs"]["llm_call_kwargs"]["extra_body"]["provider"]["quantizations"] = ["fp8"]
    else:
        new["tasks"][next(iter(new["tasks"]))]["skill"] = "review"
    with pytest.raises(pipeline.V2Error):
        scorer.join_roster(report, old_report, new, parent, directory=p3, parent_directory=p2)
