"""Offline RC2 text/diagnostic regression tests; never execute model artifacts."""
import ast
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
from types import ModuleType, SimpleNamespace

import pytest

from rc2_task_patches import (PatchError, clarify_submission_readme,
                              patch_replay_verifier, patch_review_state)


ROOT = Path(__file__).resolve().parents[1]
REVIEW = ROOT / "tasks/review-clip-incomplete/tests/test_state.py"
REPLAY = ROOT / "tasks/testgen-timeout-zero/tests/verifier.py"
VERDICT = ROOT / "tasks/review-clip-incomplete/tests/verdict_v2.py"


def load_trusted_verdict(monkeypatch):
    spec = importlib.util.spec_from_file_location("verdict_v2", VERDICT)
    module = importlib.util.module_from_spec(spec)
    monkeypatch.setitem(sys.modules, "verdict_v2", module)
    spec.loader.exec_module(module)
    return module


def execute_trusted_source(text, name):
    module = ModuleType(name)
    module.__file__ = str(ROOT / "scripts" / (name + ".py"))
    exec(compile(text, module.__file__, "exec"), module.__dict__)
    return module


def function_source(text, name):
    tree = ast.parse(text)
    return ast.get_source_segment(text, next(node for node in tree.body
                                             if isinstance(node, ast.FunctionDef) and node.name == name))


def test_review_patch_exact_contract_and_idempotence():
    old = REVIEW.read_text(encoding="utf-8")
    new = patch_review_state(old)
    assert 'len(row["behavior"].strip()) >= 10' not in new
    assert 'bool(row["behavior"].strip())' in new
    assert patch_review_state(new) == new
    for name in ("canonical", "equivalent", "no_duplicate_keys", "load_json"):
        assert function_source(new, name) == function_source(old, name)
    # Hidden contract evaluation and location/semantic requirements are unchanged.
    for statement in ('assert row["decision"] == ("accept" if correct else "reject")',
                      'assert equivalent(case["expected"], evaluate(case["input"]))',
                      'assert any(location in item["executed"] for item in failures)'):
        assert statement in old and statement in new


def test_replay_preserves_scope_source_guard_and_command():
    old = REPLAY.read_text(encoding="utf-8")
    new = patch_replay_verifier(old)
    assert patch_replay_verifier(new) == new
    for name in ("content", "files", "scope", "source_guard", "child_env", "protected_ok"):
        assert function_source(new, name) == function_source(old, name)
    assert '"missed_or_invalid_mutant_evidence"' not in new
    assert '"correct_variant_execution_invalid"' in new
    assert '"mutant_not_detected"' in new
    assert '"pytest_collection_error"' in new
    old_prefix = function_source(old, "run_case").split("        except subprocess.TimeoutExpired:")[0]
    new_prefix = function_source(new, "run_case").split("        except subprocess.TimeoutExpired as exc:")[0]
    assert old_prefix == new_prefix


def test_all_26_replay_tasks_and_public_readmes_are_supported():
    paths = sorted((ROOT / "tasks").glob("testgen-*/tests/verifier.py"))
    paths += sorted((ROOT / "tasks").glob("repro-*/tests/verifier.py"))
    assert len(paths) == 26
    for path in paths:
        source = path.read_text(encoding="utf-8")
        assert patch_replay_verifier(patch_replay_verifier(source)) == patch_replay_verifier(source)
        for readme in (path.parent / "baseline/README.md", path.parent.parent / "environment/repo/README.md"):
            old = readme.read_text(encoding="utf-8")
            new = clarify_submission_readme(old)
            assert clarify_submission_readme(new) == new
            assert "The agent may read public application source" in new
            assert "submitted tests or reproducer must check observable behavior" in new
            assert "grader" in new
            if path.parent.parent.name.startswith("testgen-"):
                assert "tests/helpers as .py files" in new
                assert ".json, .txt or .csv" in new
                assert "do not add conftest.py" in new
            else:
                assert "standalone repro.py" in new
                assert "permitted submission file suffixes" not in new
                assert "Do not alter repository files" in new


def test_all_ten_upgraded_review_templates_are_supported():
    paths = [path for path in (ROOT / "tasks").glob("review-*/tests/test_state.py")
             if '"""Behavioral patch review grading;' in path.read_text(encoding="utf-8")]
    assert len(paths) == 10
    for path in paths:
        new = patch_review_state(path.read_text(encoding="utf-8"))
        assert patch_review_state(new) == new


@pytest.mark.parametrize("transform,path", ((patch_review_state, REVIEW), (patch_replay_verifier, REPLAY)))
def test_lf_normalization(transform, path):
    old = path.read_text(encoding="utf-8")
    assert transform(old.replace("\n", "\r\n")) == transform(old)


@pytest.mark.parametrize("transform", (patch_review_state, patch_replay_verifier, clarify_submission_readme))
def test_unknown_input_fails_closed(transform):
    with pytest.raises(PatchError):
        transform("unrecognized source\n")


def test_duplicate_and_partial_inputs_fail_closed():
    review = REVIEW.read_text(encoding="utf-8")
    with pytest.raises(PatchError):
        patch_review_state(review + review)
    with pytest.raises(PatchError):
        patch_review_state(patch_review_state(review).replace("def read_review_report():", "def incomplete():"))
    replay = REPLAY.read_text(encoding="utf-8")
    with pytest.raises(PatchError):
        patch_replay_verifier(replay.replace('"public workflow was not exercised"', '"unknown policy"'))
    with pytest.raises(PatchError):
        patch_replay_verifier(patch_replay_verifier(replay).replace('"mutant_not_detected"', '"partial"'))


@pytest.fixture
def review_fixture(tmp_path, monkeypatch):
    verdict = load_trusted_verdict(monkeypatch)
    contract = ModuleType("contract")
    def validate(payload):
        if not isinstance(payload, dict) or set(payload) != {"value"} or type(payload["value"]) is not int:
            raise ValueError("expected one integer value")
    contract.validate = validate
    contract.evaluate = lambda payload: {"value": payload["value"]}
    monkeypatch.setitem(sys.modules, "contract", contract)
    grader = execute_trusted_source(patch_review_state(REVIEW.read_text(encoding="utf-8")), "rc2_review_fixture")
    app, tests = tmp_path / "app", tmp_path / "private"
    repo = app / "repo"
    repo.mkdir(parents=True)
    tests.mkdir()
    candidates = ["cedar", "maple", "elm", "ash"]
    snapshot = {"candidates.json": json.dumps({"candidates": candidates})}
    for name, value in snapshot.items():
        (repo / name).write_text(value, encoding="utf-8")
    (tests / "workspace.json").write_text(json.dumps(snapshot), encoding="utf-8")
    (tests / "cases.json").write_text('[{"value":0}]', encoding="utf-8")
    grader.APP, grader.REPO, grader.TESTS = app, repo, tests
    grader._real_run_revision = grader.run_revision
    def run_revision(workspace, candidate, payloads):
        bad = candidate in ("elm", "ash")
        return [{"result": {"value": payload["value"] + int(bad)},
                 "executed": [{"path": "candidates/" + candidate + "/mod.py", "line": 1}]}
                for payload in payloads]
    monkeypatch.setattr(grader, "run_revision", run_revision)
    report = {"schema_version": 2, "reviews": [
        {"candidate": name, "decision": "accept" if name in ("cedar", "maple") else "reject",
         "location": None if name in ("cedar", "maple") else {"path": "candidates/" + name + "/mod.py", "line": 1},
         "behavior": None if name in ("cedar", "maple") else "x",
         "cases": [{"input": {"value": value}, "expected": {"value": value}} for value in (0, 1)]}
        for name in candidates]}
    (app / "review.json").write_text(json.dumps(report), encoding="utf-8")
    return grader, verdict, report


def save_report(grader, report):
    (grader.APP / "review.json").write_text(json.dumps(report), encoding="utf-8")


def reason_code(verdict):
    return [row["value"]["reason_code"] for row in verdict._EVIDENCE
            if row["kind"] == "review_submission"][-1]


def test_single_character_nonempty_review_description_passes(review_fixture):
    grader, _, _ = review_fixture
    grader.test_review_report()


@pytest.mark.parametrize("kind,expected", (("missing", "review_report_missing"),
                                           ("json", "review_malformed_json"),
                                           ("duplicate_key", "review_malformed_json"),
                                           ("shape", "review_invalid_shape"),
                                           ("coverage", "review_candidate_coverage"),
                                           ("duplicate_candidate", "review_candidate_coverage"),
                                           ("case_count", "review_case_count"),
                                           ("duplicate_case", "review_duplicate_cases"),
                                           ("invalid_input", "review_invalid_case_input"),
                                           ("empty_description", "review_behavior_empty")))
def test_delivery_failures_are_structured_invalid_submission(review_fixture, kind, expected):
    grader, verdict, report = review_fixture
    path = grader.APP / "review.json"
    if kind == "missing":
        path.unlink()
    elif kind == "json":
        path.write_text("{bad", encoding="utf-8")
    elif kind == "duplicate_key":
        path.write_text('{"reviews":[],"reviews":[]}', encoding="utf-8")
    else:
        if kind == "shape":
            report = []
        elif kind == "coverage":
            report["reviews"] = []
        elif kind == "duplicate_candidate":
            report["reviews"][1] = report["reviews"][0]
        elif kind == "case_count":
            report["reviews"][0]["cases"] = []
        elif kind == "duplicate_case":
            report["reviews"][0]["cases"][1] = report["reviews"][0]["cases"][0]
        elif kind == "invalid_input":
            report["reviews"][0]["cases"][0]["input"] = {"invented": True}
        else:
            report["reviews"][2]["behavior"] = "   "
        save_report(grader, report)
    with pytest.raises(verdict.InvalidSubmission, match=expected):
        grader.test_review_report()
    assert reason_code(verdict) == expected


def test_semantic_failure_stays_behavior_mismatch_not_delivery(review_fixture):
    grader, verdict, report = review_fixture
    report["reviews"][0]["decision"] = "reject"
    save_report(grader, report)
    with pytest.raises(AssertionError, match="incorrect patch decision") as caught:
        grader.test_review_report()
    assert not isinstance(caught.value, verdict.InvalidSubmission)
    assert not any(row["kind"] == "review_submission" for row in verdict._EVIDENCE)


@pytest.mark.parametrize("kind", ("fixture", "probe"))
def test_trusted_review_faults_not_swallowed(review_fixture, monkeypatch, kind):
    grader, verdict, _ = review_fixture
    if kind == "fixture":
        (grader.TESTS / "cases.json").write_text("bad trusted JSON", encoding="utf-8")
        expected = verdict.TrustedGraderError
    else:
        def broken_probe(*args):
            raise RuntimeError("trusted probe crashed")
        monkeypatch.setattr(grader, "run_revision", broken_probe)
        expected = RuntimeError
    with pytest.raises(expected) as caught:
        grader.test_review_report()
    assert not isinstance(caught.value, verdict.InvalidSubmission)


@pytest.mark.parametrize("kind,category", (("exit", "trusted_review_probe_execution"),
                                          ("timeout", "trusted_review_probe_execution"),
                                          ("json", "trusted_review_probe_result"),
                                          ("shape", "trusted_review_probe_result")))
def test_real_review_probe_trusted_failures_are_errors(review_fixture, monkeypatch, kind, category):
    grader, verdict, _ = review_fixture
    def run(*args, **kwargs):
        if kind == "timeout":
            raise subprocess.TimeoutExpired(args[0], 15, stderr=b"partial error")
        output = "broken JSON" if kind == "json" else "[]"
        return SimpleNamespace(returncode=1 if kind == "exit" else 0, stdout=output, stderr="probe stderr")
    monkeypatch.setattr(grader.subprocess, "run", run)
    with pytest.raises(verdict.TrustedGraderError) as caught:
        grader._real_run_revision(grader.REPO, "base", [{"value": 0}])
    assert caught.value.category == category
    assert verdict._EVIDENCE[-1]["kind"] == "review_probe"


def test_real_review_probe_success_and_bounded_private_evidence(review_fixture, monkeypatch):
    grader, verdict, _ = review_fixture
    results = [{"result": {"value": 0}, "executed": []}]
    monkeypatch.setattr(grader.subprocess, "run", lambda *args, **kwargs:
                        SimpleNamespace(returncode=0, stdout=json.dumps(results), stderr="x" * 1000))
    assert grader._real_run_revision(grader.REPO, "base", [{"value": 0}]) == results
    assert len(verdict._EVIDENCE[-1]["value"]["stderr_tail"]) == 600


def test_trusted_review_balance_failure_not_model_zero(review_fixture, monkeypatch):
    grader, verdict, report = review_fixture
    for row in report["reviews"]:
        row.update(decision="accept", location=None, behavior=None)
    save_report(grader, report)
    def all_correct(workspace, candidate, payloads):
        return [{"result": {"value": payload["value"]}, "executed": []} for payload in payloads]
    monkeypatch.setattr(grader, "run_revision", all_correct)
    with pytest.raises(verdict.TrustedGraderError) as caught:
        grader.test_review_report()
    assert caught.value.category == "trusted_review_candidate_balance"


@pytest.fixture
def replay_fixture(tmp_path, monkeypatch):
    verdict = load_trusted_verdict(monkeypatch)
    grader = execute_trusted_source(patch_replay_verifier(REPLAY.read_text(encoding="utf-8")), "rc2_replay_fixture")
    app, tests = tmp_path / "app", tmp_path / "private"
    app.mkdir()
    (tests / "baseline/tests").mkdir(parents=True)
    (tests / "baseline/workflow.py").write_text("# trusted mock application\n", encoding="utf-8")
    (tests / "baseline/tests/.gitkeep").write_bytes(b"")
    (tests / "pytest_probe.py").write_text("# trusted mock observer\n", encoding="utf-8")
    grader.APP, grader.TESTS = app, tests
    return grader, verdict


def pytest_report(code=0, *, phase="call", outcome="passed", error=None, collected=1):
    return {"collected": collected, "exitstatus": code,
            "reports": [{"phase": phase, "node": "tests/test_fixture.py::test_fixture",
                         "outcome": outcome, "error": error}]}


def mock_replay_process(monkeypatch, grader, *, code=0, data=None, workflow=True,
                        stderr="", stdout="", timeout=False, protected_change=False):
    def run(command, *, cwd, env, **kwargs):
        if timeout:
            raise subprocess.TimeoutExpired(command, 8, output=b"partial stdout", stderr=b"partial stderr")
        if workflow:
            Path(env["_BENCH_CALL_LOG"]).write_text("workflow.run\n", encoding="utf-8")
        if data is not None:
            text = data if isinstance(data, str) else json.dumps(data)
            Path(env["_BENCH_RESULT_LOG"]).write_text(text, encoding="utf-8")
        if protected_change:
            (Path(cwd) / "workflow.py").write_text("# modified", encoding="utf-8")
        return SimpleNamespace(returncode=code, stdout=stdout, stderr=stderr)
    monkeypatch.setattr(grader.subprocess, "run", run)


TEST_BYTES = {"tests/test_fixture.py": b"def test_fixture():\n    assert True\n"}


def test_collection_import_error_not_masked_by_absent_workflow(replay_fixture, monkeypatch):
    grader, _ = replay_fixture
    data = pytest_report(2, phase="collection", outcome="failed", error="CollectionError", collected=0)
    mock_replay_process(monkeypatch, grader, code=2, data=data, workflow=False,
                        stderr="ModuleNotFoundError: invented_api")
    result = grader.run_case("testgen", {}, TEST_BYTES)
    assert result["state"] == "invalid"
    assert result["reason_code"] == "pytest_collection_error"
    assert result["returncode"] == 2
    assert result["pytest"] == data
    assert result["workflow_exercised"] is False
    assert "invented_api" in result["tail"]


@pytest.mark.parametrize("code,data,workflow,expected", (
    (0, pytest_report(), True, ("pass", "behavior_pass")),
    (1, pytest_report(1, outcome="failed", error="AssertionError"), True, ("behavior_fail", "behavior_failure")),
    (0, pytest_report(), False, ("invalid", "workflow_not_exercised")),
    (5, {"collected": 0, "exitstatus": 5, "reports": []}, False, ("invalid", "pytest_no_tests_collected")),
    (1, pytest_report(1, phase="setup", outcome="failed", error="ValueError"), False, ("invalid", "pytest_execution_invalid")),
))
def test_pytest_result_classification(replay_fixture, monkeypatch, code, data, workflow, expected):
    grader, _ = replay_fixture
    mock_replay_process(monkeypatch, grader, code=code, data=data, workflow=workflow, stdout="x" * 1000)
    result = grader.run_case("testgen", {}, TEST_BYTES)
    assert (result["state"], result["reason_code"]) == expected
    assert result["execution"]["returncode"] == code
    assert len(result["execution"]["stdout_tail"]) <= 600
    assert len(result["tail"]) <= 600
    assert result["pytest"] == data


@pytest.mark.parametrize("data,code,category", (
    (None, 0, "trusted_replay_missing_result"),
    ("{broken", 0, "trusted_replay_invalid_result"),
    ({"collected": True, "exitstatus": 0, "reports": []}, 0, "trusted_replay_invalid_result"),
    (pytest_report(), 1, "trusted_replay_invalid_result"),
    ({"collected": 1, "exitstatus": 0, "reports": [{"phase": "call", "node": "x", "outcome": "passed"}]},
     0, "trusted_replay_invalid_result"),
    (pytest_report(3), 3, "trusted_replay_pytest_error"),
    (pytest_report(4), 4, "trusted_replay_pytest_error"),
))
def test_trusted_replay_report_faults_remain_errors(replay_fixture, monkeypatch, data, code, category):
    grader, verdict = replay_fixture
    mock_replay_process(monkeypatch, grader, data=data, code=code)
    with pytest.raises(verdict.TrustedGraderError) as caught:
        grader.run_case("testgen", {}, TEST_BYTES)
    assert caught.value.category == category
    assert verdict._EVIDENCE[-1]["kind"] == "replay_runner"


def test_timeout_keeps_exception_and_output(replay_fixture, monkeypatch):
    grader, _ = replay_fixture
    mock_replay_process(monkeypatch, grader, timeout=True)
    result = grader.run_case("testgen", {}, TEST_BYTES)
    assert result["reason_code"] == "execution_timeout"
    assert result["execution"]["exception_type"] == "TimeoutExpired"
    assert "partial stderr" in result["tail"]
    assert result["returncode"] is None


def test_protected_source_rules_not_weakened(replay_fixture, monkeypatch):
    grader, _ = replay_fixture
    mock_replay_process(monkeypatch, grader, data=pytest_report(), protected_change=True)
    result = grader.run_case("testgen", {}, TEST_BYTES)
    assert result["reason_code"] == "private_implementation_modified"
    assert "workflow.py" in result["changed_paths"]
    assert result["pytest"] == pytest_report()
    with pytest.raises(ValueError, match="introspection"):
        grader.source_guard("import inspect\ninspect.getsource(workflow.run)")
    grader.source_guard("import inspect\ninspect.signature(workflow.run)")


@pytest.mark.parametrize("code,stderr,workflow,expected", (
    (1, "ModuleNotFoundError: invented_api", False, ("invalid", "reproducer_execution_invalid")),
    (1, "AssertionError: business_id ImportError", True, ("behavior_fail", "behavior_failure")),
    (1, "AssertionError: failure", False, ("invalid", "workflow_not_exercised")),
    (0, "", True, ("pass", "behavior_pass")),
))
def test_repro_execution_precedes_workflow_coverage(replay_fixture, monkeypatch, code, stderr, workflow, expected):
    grader, _ = replay_fixture
    mock_replay_process(monkeypatch, grader, code=code, stderr=stderr, workflow=workflow)
    result = grader.run_case("repro", {}, b"# trusted fixture never executed\n")
    assert (result["state"], result["reason_code"]) == expected
    assert result["execution"]["returncode"] == code


PASS = {"state": "pass", "reason_code": "behavior_pass", "returncode": 0}
FAIL = {"state": "behavior_fail", "fingerprint": [1, "AssertionError"], "returncode": 1}
FAIL_OTHER = {"state": "behavior_fail", "fingerprint": [1, "ValueError"], "returncode": 1}
INVALID = {"state": "invalid", "reason": "import failed", "reason_code": "pytest_collection_error", "returncode": 2}


def evaluate_with_runs(grader, monkeypatch, kind, runs):
    manifest = {"kind": kind, "correct": [{"name": "gold", "patch": {}}],
                "incorrect": [{"name": "mutant", "patch": {}}]}
    (grader.TESTS / "case_manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    monkeypatch.setattr(grader, "scope", lambda kind: ({}, TEST_BYTES))
    if kind == "repro":
        (grader.APP / "repro.py").write_text("assert True\n", encoding="utf-8")
    rows = iter(runs)
    monkeypatch.setattr(grader, "run_case", lambda *args: next(rows))
    return grader.evaluate()


@pytest.mark.parametrize("runs,category,code", (
    ([INVALID, INVALID], "invalid_execution", "correct_variant_execution_invalid"),
    ([PASS, INVALID], "invalid_execution", "correct_variant_execution_invalid"),
    ([FAIL, FAIL], "rejects_correct_implementation", "correct_variant_behavior_rejected"),
    ([PASS, FAIL], "unstable_evidence", "correct_variant_evidence_unstable"),
    ([FAIL, FAIL_OTHER], "unstable_evidence", "correct_variant_evidence_unstable"),
    ([PASS, PASS, PASS, PASS], "missed_mutant", "mutant_not_detected"),
    ([PASS, PASS, INVALID, FAIL], "invalid_execution", "mutant_execution_invalid"),
    ([PASS, PASS, PASS, FAIL], "unstable_evidence", "mutant_evidence_unstable"),
    ([PASS, PASS, FAIL, FAIL_OTHER], "unstable_evidence", "mutant_evidence_unstable"),
    ([PASS, PASS, FAIL, FAIL], "verified_behavior", "verified_behavior"),
))
def test_testgen_evaluate_preserves_underlying_evidence(replay_fixture, monkeypatch, runs, category, code):
    grader, _ = replay_fixture
    result = evaluate_with_runs(grader, monkeypatch, "testgen", runs)
    assert (result["category"], result["reason_code"]) == (category, code)
    assert result["ok"] == (category == "verified_behavior")
    flattened = [row for entry in result["evidence"] for row in entry["runs"]]
    assert flattened == runs


@pytest.mark.parametrize("runs,category,code", (
    ([INVALID, FAIL], "invalid_execution", "target_execution_invalid"),
    ([PASS, PASS], "not_stable_target_reproduction", "target_not_reproduced"),
    ([PASS, FAIL], "unstable_evidence", "target_evidence_unstable"),
    ([FAIL, FAIL_OTHER], "unstable_evidence", "target_evidence_unstable"),
    ([FAIL, FAIL, PASS, PASS], "verified_behavior", "verified_behavior"),
))
def test_repro_evaluate_classification(replay_fixture, monkeypatch, runs, category, code):
    grader, _ = replay_fixture
    result = evaluate_with_runs(grader, monkeypatch, "repro", runs)
    assert (result["category"], result["reason_code"]) == (category, code)
    assert [row for entry in result["evidence"] for row in entry["runs"]] == runs


def test_evaluate_does_not_turn_trusted_fault_into_model_zero(replay_fixture, monkeypatch):
    grader, verdict = replay_fixture
    (grader.TESTS / "case_manifest.json").write_text("broken trusted fixture", encoding="utf-8")
    with pytest.raises(json.JSONDecodeError):
        grader.evaluate()
    manifest = {"kind": "testgen", "correct": [{"name": "gold", "patch": {}}], "incorrect": []}
    (grader.TESTS / "case_manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    monkeypatch.setattr(grader, "scope", lambda kind: ({}, TEST_BYTES))
    def broken_replay(*args):
        raise verdict.TrustedGraderError("trusted_replay_invalid_result", "broken trusted result")
    monkeypatch.setattr(grader, "run_case", broken_replay)
    with pytest.raises(verdict.TrustedGraderError):
        grader.evaluate()


@pytest.mark.parametrize("kind,expected_status,expected_category", (
    ("delivery", "fail", "invalid_submission"),
    ("replay_invalid", "fail", "invalid_execution"),
    ("trusted", "error", "trusted_replay_invalid_result"),
))
def test_existing_top_level_controller_classification(monkeypatch, kind, expected_status, expected_category):
    verdict = load_trusted_verdict(monkeypatch)
    if kind == "delivery":
        error = verdict.InvalidSubmission("review_candidate_coverage: candidate coverage")
    elif kind == "replay_invalid":
        verdict.record_submission_result({"ok": False, "category": "invalid_execution",
                                          "reason_code": "correct_variant_execution_invalid"})
        error = AssertionError("submission verification failed")
    else:
        error = verdict.TrustedGraderError("trusted_replay_invalid_result", "bad trusted report")
    plugin = verdict.VerdictPlugin()
    plugin.collected = 1
    report = SimpleNamespace(when="call", nodeid="test_state.py::test_submission", failed=True, outcome="failed")
    call = SimpleNamespace(excinfo=SimpleNamespace(type=type(error), value=error))
    hook = plugin.pytest_runtest_makereport(None, call)
    next(hook)
    with pytest.raises(StopIteration):
        hook.send(SimpleNamespace(get_result=lambda: report))
    result = plugin.verdict(1)
    assert (result["status"], result["failure_category"]) == (expected_status, expected_category)
