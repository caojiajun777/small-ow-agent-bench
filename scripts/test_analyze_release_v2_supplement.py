import copy

import pytest

import analyze_release_v2_supplement as analyzer


@pytest.fixture
def evidence(monkeypatch):
    monkeypatch.setattr(analyzer.frozen, "leaderboard", lambda rows, manifest: {"audited_rows": len(rows)})
    observations, schedule, issues = [], [], []
    for index, (job, (task, count)) in enumerate(analyzer.TARGETS.items()):
        row = {"slot_id": task, "job_name": job, "task": task,
               "model": "llama-3.2-3b-instruct", "artifact": False, "clean": False,
               "repetition": 1, "sequence": index + 1,
               "started_at": f"2026-10-29T01:0{index}:00+00:00",
               "failure_category": "invalid_submission", "artifact_capture_status": "error",
               "capture_supplement_scope": "original_invalid_submission_zero_only"}
        observations.append({"job_name": job, "supported": True, "canonical_row": row})
        schedule.append({field: row[field] for field in
                         ("slot_id", "model", "task", "repetition", "sequence")})
        issues.append({"kind": "invalid_scored_evidence", "job": job,
                       "error": analyzer.CAPTURE_REJECTION})
    report = {"manifest_sha256": "original", "canonical_rows": [], "issues": issues,
              "completeness": {"duplicates": {}, "unresolved": []}}
    supplement = {"kind": "smallowbench_v2_capture_failure_supplement",
                  "manifest_sha256": "original", "complete_final_agent_capture_established": False,
                  "original_records_modified": False, "model_calls": 0, "container_calls": 0,
                  "supported_negative_observations": observations, "supported_count": 2,
                  "observed_file_count": 35, "source_sha256": {"auditor": "source"}}
    return report, supplement, {"manifest_sha256": "original", "schedule": schedule}


def test_exact_negative_observations_close_only_capture_issues(evidence):
    report, supplement, manifest = evidence
    original = copy.deepcopy(report)
    result = analyzer.apply_supplement(report, supplement, manifest)
    assert result["accepted"] is True
    assert result["leaderboard"] == {"audited_rows": 2}
    assert len(result["resolved_capture_issues"]) == 2
    assert all(row["artifact_capture_status"] == "error" for row in result["canonical_rows"])
    assert result["capture_evidence_supplement"]["complete_final_agent_capture_established"] is False
    assert report == original


def test_other_error_and_missing_slot_still_prevent_ranking(evidence):
    report, supplement, manifest = evidence
    report["issues"].append({"kind": "unrelated_error"})
    manifest["schedule"].append({"slot_id": "not-run"})
    result = analyzer.apply_supplement(report, supplement, manifest)
    assert result["accepted"] is False
    assert result["formal_ranking_eligible"] is False
    assert result["leaderboard"] == {}
    assert result["issues"] == [{"kind": "unrelated_error"}]
    assert result["completeness"]["missing"] == ["not-run"]


@pytest.mark.parametrize("field,value", [("artifact", True), ("clean", True),
                                         ("artifact_capture_status", "complete"),
                                         ("model", "unrelated-model"),
                                         ("slot_id", "unrelated-slot"),
                                         ("repetition", 2), ("sequence", 999)])
def test_positive_or_unrelated_observation_cannot_be_admitted(evidence, field, value):
    report, supplement, manifest = evidence
    supplement["supported_negative_observations"][0]["canonical_row"][field] = value
    with pytest.raises(analyzer.V2Error):
        analyzer.apply_supplement(report, supplement, manifest)


def test_other_failure_cannot_be_erased_by_same_job_name(evidence):
    report, supplement, manifest = evidence
    report["issues"][0]["error"] = "different trusted error"
    with pytest.raises(analyzer.V2Error):
        analyzer.apply_supplement(report, supplement, manifest)


@pytest.fixture
def retry_evidence(monkeypatch):
    import retry_v2_single_infra as retry

    other = [{"slot_id": f"other-{i}", "job_name": f"original-{i}", "visit": 1,
              "status": "scored", "counts_toward_cap": True} for i in range(495)]
    source = {"slot_id": retry.SLOT, "job_name": retry.SOURCE_JOB, "visit": 1,
              "status": "infra", "counts_toward_cap": True}
    added = {"slot_id": retry.SLOT, "job_name": "approved-second-visit", "visit": 2,
             "status": "scored", "counts_toward_cap": True,
             "single_infra_retry_approval_sha256": "approval",
             "single_infra_retry_proposal_sha256": "proposal",
             "authorization_sha256": "auth", "fee_waiver_sha256": "fee",
             "retry_source_job_name": retry.SOURCE_JOB}
    rows = [source, *other, added]
    monkeypatch.setattr(analyzer, "read_visits", lambda directory: (rows, []))
    monkeypatch.setattr(retry, "validate_proposal", lambda *args, **kwargs: ({}, "proposal"))
    monkeypatch.setattr(retry, "validate_approval", lambda *args, **kwargs: ("approval", "auth", "fee"))
    manifest = {"schedule": [{"slot_id": value["slot_id"]} for value in [source, *other]]}
    report = {"actual_execution_policy": {"max_task_attempts": 496},
              "execution_phases": {"initial_scored_visits": 120}}
    return rows, report, manifest


def test_only_executed_approved_exception_changes_reported_attempt_cap(retry_evidence):
    rows, report, manifest = retry_evidence
    result = analyzer.annotate_single_infra_retry(report, ".", manifest, {})
    assert result["actual_execution_policy"]["max_task_attempts"] == 497
    assert result["actual_execution_policy"]["actual_counted_attempts"] == 497
    assert result["actual_execution_policy"]["single_infra_retry_exception"]["original_counted_infra_preserved"]
    assert report["actual_execution_policy"]["max_task_attempts"] == 496


def test_prepared_approval_without_additional_visit_does_not_change_policy(retry_evidence):
    rows, report, manifest = retry_evidence
    rows.pop()
    assert analyzer.annotate_single_infra_retry(report, ".", manifest, {}) is report


@pytest.mark.parametrize("mutation", ["wrong_approval", "wrong_slot", "erase_original_count",
                                      "second_exception", "strip_retry_markers"])
def test_retry_report_rejects_unapproved_or_broader_attempt_changes(retry_evidence, mutation):
    rows, report, manifest = retry_evidence
    if mutation == "wrong_approval":
        rows[-1]["single_infra_retry_approval_sha256"] = "stale"
    elif mutation == "wrong_slot":
        rows[-1]["slot_id"] = "other-0"
    elif mutation == "erase_original_count":
        rows[0]["counts_toward_cap"] = False
    elif mutation == "strip_retry_markers":
        rows[-1]["visit"] = 1
        rows[-1].pop("single_infra_retry_approval_sha256")
    else:
        rows[1]["visit"] = 2
    with pytest.raises(analyzer.V2Error):
        analyzer.annotate_single_infra_retry(report, ".", manifest, {})
