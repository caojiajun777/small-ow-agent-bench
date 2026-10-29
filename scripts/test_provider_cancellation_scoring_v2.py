"""Offline amendment/sidecar contracts; original p3 data and models are untouched."""
from __future__ import annotations

import copy
from types import SimpleNamespace

import pytest

import provider_cancellation_scoring_v2 as amended
import provider_reassessment_scoring_v2 as original
import release_v2_pipeline as pipeline
from test_provider_reassessment_scoring_v2 import save, scored_fixture  # noqa: F401
from test_provider_reassessment_scoring_v2 import roster_fixture


@pytest.fixture
def future_fixture(request, monkeypatch):
    f = request.getfixturevalue("scored_fixture")
    doc = {"correction": {"job_name": "original-correction"}, "baseline_visits_sha256": {},
           "remaining_slot_ids": [f.visit["slot_id"]]}
    amendment_path = save(f.directory / amended.AMENDMENT, doc)
    f.visit["execution_amendment_sha256"] = pipeline.file_hash(amendment_path)
    visit_path = save(f.directory / amended.CONTINUATION / "visits" / (f.visit["job_name"] + ".json"), f.visit)
    resume = SimpleNamespace(validate_amendment=lambda *args, **kwargs: (doc, pipeline.file_hash(amendment_path)),
                             validate_request_contract=lambda *args: f.visit["request_contract"])
    monkeypatch.setattr(amended, "_resume", lambda: resume)
    return SimpleNamespace(f=f, doc=doc, amendment_path=amendment_path, visit_path=visit_path, resume=resume)


def test_future_scored_row_keeps_all_original_fields_and_binds_amendment(future_fixture):
    g, f = future_fixture, future_fixture.f
    expected = original.validate_scored_visit(f.visit, f.manifest, f.directory)
    actual = amended.validate_scored_visit(f.visit, f.manifest, f.directory)
    assert {key: actual[key] for key in expected} == expected
    assert actual["execution_amendment_sha256"] == pipeline.file_hash(g.amendment_path)
    assert actual["observation_authority"] == "continuation"


@pytest.mark.parametrize("fault", ["amendment", "slot", "export", "capture", "source", "audit", "authorization"])
def test_amendment_is_no_excuse_to_bypass_prior_checks(future_fixture, fault):
    g, f = future_fixture, future_fixture.f
    if fault == "amendment":
        f.visit["execution_amendment_sha256"] = "d" * 64
        save(g.visit_path, f.visit)
    elif fault == "slot":
        g.doc["remaining_slot_ids"] = []
    elif fault == "export":
        save(g.visit_path, {**f.visit, "atomic_correct": 0})
    elif fault == "capture":
        f.capture_path.unlink()
    elif fault == "source":
        f.manifest["source_hashes"][original.LEGACY_SOURCES[0]] = "d" * 64
    elif fault == "audit":
        def reject(*args):
            raise pipeline.V2Error(original.AUTH_BOUNDARY_ERROR)
        g.resume.validate_request_contract = reject
    else:
        f.visit["authorization_sha256"] = "d" * 64
        save(g.visit_path, f.visit)
    with pytest.raises((ValueError, OSError)):
        amended.validate_scored_visit(f.visit, f.manifest, f.directory)


@pytest.fixture
def correction_fixture(request, monkeypatch):
    f = request.getfixturevalue("scored_fixture")
    old_task, task = f.task, "testgen-anagram"
    f.slot["task"] = task
    f.slot["slot_id"] = f.slot["slot_id"].replace(old_task, task)
    f.manifest["tasks"][task] = f.manifest["tasks"].pop(old_task)
    f.manifest["tasks"][task]["skill"] = "testgen"
    for key in ("image_digests", "grader_image_digests"):
        f.manifest["runtime_environment_evidence"][key][task] = f.manifest["runtime_environment_evidence"][key].pop(old_task)
    staged = f.staged.with_name(task)
    f.staged.rename(staged)
    f.capture["task_id"] = task
    save(f.capture_path, f.capture)
    f.trace.update(task_id=task, finished=False, termination_reason="cancelled",
                   artifact_manifest_sha256=pipeline.file_hash(f.capture_path))
    save(f.trace_path, f.trace)
    f.verdict.update(task_id=task, status="fail", artifact_correct=0, failure_category="invalid_submission")
    save(f.verdict_path, f.verdict)
    expected = pipeline.job_config(f.manifest, f.slot, f.job, f.directory)
    save(f.generated, expected)
    save(f.executed, expected)
    f.raw.update(task_name="fixture/" + task, trial_name=f.trial.name,
                 exception_info={"exception_type": "AgentTimeoutError"})
    f.raw["config"].update(agent=expected["agents"][0], task=expected["tasks"][0])
    f.raw["agent_result"]["metadata"] = copy.deepcopy(f.trace)
    f.raw["verifier_result"]["rewards"]["reward"] = 0
    save(f.result_path, f.raw)
    f.visit.update(task=task, slot_id=f.slot["slot_id"], status="infra", termination="infra", claim_token="token",
                   reason="provider_configuration_contract", retry_classification="configuration_fault_no_retry",
                   provider_failure={"exception_type": "RequestContractError"},
                   config_sha256=pipeline.file_hash(f.executed), executed_config_sha256=pipeline.file_hash(f.executed),
                   generated_config_sha256=pipeline.file_hash(f.generated))
    source_path = save(f.directory / "visits" / (f.job + ".json"), f.visit)
    correction = {"job_name": f.job, "slot_id": f.slot["slot_id"], "claim_token": "token",
                  "source_visit_sha256": pipeline.file_hash(source_path),
                  "raw_result_sha256": pipeline.file_hash(f.result_path), "trace_sha256": pipeline.file_hash(f.trace_path)}
    doc = {"correction": correction, "baseline_visits_sha256": {f.job: pipeline.file_hash(source_path)},
           "remaining_slot_ids": []}
    amendment_path = save(f.directory / amended.AMENDMENT, doc)
    request = {**f.visit["request_contract"], "typed_timeout_cancellation_exception_applied": True}
    resume = SimpleNamespace(validate_amendment=lambda *args, **kwargs: (doc, pipeline.file_hash(amendment_path)),
                             validate_request_contract=lambda *args: request)
    monkeypatch.setattr(amended, "_resume", lambda: resume)
    return SimpleNamespace(f=f, doc=doc, source_path=source_path, request=request, resume=resume)


def test_original_timeout_is_a_hash_bound_zero_tle_without_original_mutation(correction_fixture):
    g, f = correction_fixture, correction_fixture.f
    before = {path: pipeline.file_hash(path) for path in (g.source_path, f.result_path, f.trace_path)}
    sidecar = amended.build_reclassification(f.directory, g.doc)
    save(f.directory / amended.SIDECAR, sidecar)
    virtual = amended.validate_reclassification(f.directory, g.doc)
    assert virtual["status"] == "scored" and virtual["termination"] == "tle" and virtual["atomic_correct"] == 0
    row = amended.validate_scored_visit(virtual, f.manifest, f.directory)
    assert row["artifact"] is False and row["clean"] is False
    assert row["observation_authority"] == "sidecar" and row["termination"] == "tle"
    assert all(pipeline.file_hash(path) == value for path, value in before.items())
    assert pipeline.read_json(g.source_path)["status"] == "infra"


@pytest.mark.parametrize("fault", ["source", "raw", "trace", "wrong_reason", "no_typed_evidence", "sidecar_positive", "sidecar_other_job"])
def test_sidecar_cannot_relabel_unrelated_or_unverified_failure(correction_fixture, fault):
    g, f = correction_fixture, correction_fixture.f
    sidecar = amended.build_reclassification(f.directory, g.doc)
    save(f.directory / amended.SIDECAR, sidecar)
    if fault == "source":
        save(g.source_path, {**f.visit, "status": "scored"})
    elif fault == "raw":
        save(f.result_path, {**f.raw, "exception_info": {"exception_type": "APIStatusError"}})
    elif fault == "trace":
        save(f.trace_path, {**f.trace, "termination_reason": "api_error"})
    elif fault == "wrong_reason":
        g.doc["correction"]["slot_id"] = "other"
    elif fault == "no_typed_evidence":
        g.request.pop("typed_timeout_cancellation_exception_applied")
    elif fault == "sidecar_positive":
        sidecar["atomic_correct"] = 1
        save(f.directory / amended.SIDECAR, sidecar)
    else:
        sidecar["source_job_name"] = "other"
        save(f.directory / amended.SIDECAR, sidecar)
    with pytest.raises((ValueError, OSError)):
        amended.validate_reclassification(f.directory, g.doc)


def test_future_infra_uses_amended_classifier_with_original_config_checks(future_fixture):
    g, f = future_fixture, future_fixture.f
    payload = {"status": "infra", "termination": "infra", "reason": "upstream",
               "retry_classification": "evidence_confirmed_runtime_or_provider_infra"}
    g.resume.classify_job = lambda *args: (payload, None)
    visit = {**f.visit, **payload}
    receipt = amended._infra_evidence(visit, f.slot, f.manifest, f.directory, f.lock, f.visit["authorization_sha256"])
    assert receipt["contributes_to_score"] is False
    visit["reason"] = "invented"
    with pytest.raises(pipeline.V2Error, match="metadata differs"):
        amended._infra_evidence(visit, f.slot, f.manifest, f.directory, f.lock, f.visit["authorization_sha256"])


@pytest.mark.parametrize("fault", [None, "partial", "uncounted", "invalid_capture", "active", "unknown_job"])
def test_report_preserves_baseline_and_requires_exact_complete_child_projection(tmp_path, monkeypatch, fault):
    _, manifest, _, source, _, directory = roster_fixture(tmp_path)
    manifest["caps"] = {"max_visits_per_slot": 3, "max_total_visits": 186}
    slots = manifest["schedule"]
    target = next(slot for slot in slots if slot["task"] == "testgen-anagram")
    baseline_slots = [slot for slot in slots if slot != target][:49]
    child_slots = [slot for slot in slots if slot not in baseline_slots and slot != target]
    canonical = {row["slot_id"]: row for row in source["canonical_rows"]}
    baseline = []
    child = []
    for group, chosen in ((baseline, baseline_slots + [target]), (child, child_slots)):
        for slot in chosen:
            row = {**canonical[slot["slot_id"]], "manifest_sha256": manifest["manifest_sha256"],
                   "status": "infra" if slot == target else "scored", "visit": 1,
                   "counts_toward_cap": True, "charged_usd": .001}
            group.append(row)
    correction = baseline[-1]
    virtual = {**correction, "status": "scored", "termination": "tle", "atomic_correct": 0}
    doc = {"correction": {"job_name": correction["job_name"]},
           "baseline_visits_sha256": {}, "remaining_slot_ids": [slot["slot_id"] for slot in child_slots]}
    doc_path = save(directory / amended.AMENDMENT, doc)
    amendment_sha = pipeline.file_hash(doc_path)
    save(directory / amended.SIDECAR, {"synthetic_sidecar": True})
    for row in baseline:
        path = save(directory / "visits" / (row["job_name"] + ".json"), row)
        doc["baseline_visits_sha256"][row["job_name"]] = pipeline.file_hash(path)
    cold_flags = []
    def validate_amendment(*args, **kwargs):
        cold_flags.append(kwargs.get("verify_artifacts", False))
        return doc, amendment_sha
    import provider_reassessment_v2 as original_core
    core = SimpleNamespace(validate_manifest=lambda *args, **kwargs: manifest,
                           retryable=original_core.retryable, RETRY_POLICY=original_core.RETRY_POLICY)
    monkeypatch.setattr(original, "_core", lambda: core)
    monkeypatch.setattr(amended, "_resume", lambda: SimpleNamespace(validate_amendment=validate_amendment))
    monkeypatch.setattr(amended, "_guard", lambda *args: (doc, amendment_sha, {}, "auth"))
    monkeypatch.setattr(amended, "validate_reclassification", lambda *args, **kwargs: virtual)
    for row in child:
        row["execution_amendment_sha256"] = amendment_sha
    if fault == "partial":
        child.pop()
    elif fault == "uncounted":
        child[0]["counts_toward_cap"] = False
    for row in child:
        save(directory / amended.CONTINUATION / "visits" / (row["job_name"] + ".json"), row)
    base = {"kind": "smallowbench_v2_provider_reassessment_report", "manifest_sha256": manifest["manifest_sha256"],
            "accepted": False, "formal_ranking_eligible": False, "canonical_rows": [canonical[row["slot_id"]] for row in baseline[:-1]],
            "issues": [{"kind": "untracked_job_artifacts", "job": row["job_name"]} for row in child],
            "infra_visits": [{"job": correction["job_name"]}], "analysis_provenance": {}}
    if fault == "unknown_job":
        base["issues"].append({"kind": "untracked_job_artifacts", "job": "unverified-stranger"})
    snapshot = copy.deepcopy(base)
    monkeypatch.setattr(original, "build_report", lambda *args, **kwargs: base)
    monkeypatch.setattr(original, "_claim_consistency", lambda *args: [])
    monkeypatch.setattr(amended, "active_claims", lambda path: ["still-running"]
                        if fault == "active" and path.name == amended.CONTINUATION else [])
    def validate(visit, *args, **kwargs):
        if fault == "invalid_capture" and visit["job_name"] == child[0]["job_name"]:
            raise pipeline.V2Error("capture is missing, erroneous, or identity-mismatched")
        row = canonical[visit["slot_id"]]
        if visit["job_name"] == correction["job_name"]:
            row = {**row, "artifact": False, "clean": False, "termination": "tle"}
        return {**row, "execution_amendment_sha256": amendment_sha}
    monkeypatch.setattr(amended, "validate_scored_visit", validate)
    report = amended.build_report(directory)
    assert report["accepted"] is (fault is None)
    assert base == snapshot and base["accepted"] is False
    assert report["infra_visits"] == []
    assert report["reclassified_original_infra_attempts"] == [{"job": correction["job_name"]}]
    assert cold_flags[0] is True
    if fault is None:
        assert report["completeness"]["legal_unique"] == 62
        assert report["cost_accounting"]["reported_api_usd"] == pytest.approx(.062)
    elif fault == "uncounted":
        assert any(issue["kind"] == "uncounted_executed_attempt" for issue in report["issues"])
