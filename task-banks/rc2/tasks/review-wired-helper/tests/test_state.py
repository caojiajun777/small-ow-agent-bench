"""Behavioral patch review grading; gold source and contracts never come from /app."""
import json
import math
import os
import subprocess
import sys
import tempfile
from pathlib import Path

from contract import evaluate, validate
from verdict_v2 import (submission_value, submission_text, validate_review_submission,
                        record_evidence, InvalidSubmission, TrustedGraderError)

TESTS = Path(os.environ.get("BENCH_TESTS_ROOT", Path(__file__).parent))
APP = Path(os.environ.get("BENCH_APP_ROOT", "/app"))
REPO = Path(os.environ.get("BENCH_REPO_ROOT", "/app/repo"))

def canonical(value):
    return json.dumps(value, sort_keys=True, ensure_ascii=False, allow_nan=False, separators=(",", ":"))

def equivalent(left, right):
    if type(left) is bool or type(right) is bool:
        return type(left) is type(right) and left == right
    if type(left) in (int, float) and type(right) in (int, float):
        return math.isfinite(left) and math.isfinite(right) and left == right
    if isinstance(left, list) and isinstance(right, list):
        return len(left) == len(right) and all(equivalent(a, b) for a, b in zip(left, right))
    if isinstance(left, dict) and isinstance(right, dict):
        return left.keys() == right.keys() and all(equivalent(left[key], right[key]) for key in left)
    return type(left) is type(right) and left == right

def no_duplicate_keys(pairs):
    result = {}
    for key, value in pairs:
        assert key not in result, "duplicate JSON key"
        result[key] = value
    return result

def load_json(path):
    return json.loads(path.read_text(encoding="utf-8"), object_pairs_hook=no_duplicate_keys,
                      parse_constant=lambda value: (_ for _ in ()).throw(ValueError(value)))

def run_revision(workspace, revision, payloads):
    try:
        process = subprocess.run(
            [sys.executable, "-B", str(TESTS / "probe.py"), str(workspace), revision],
            input=json.dumps(payloads, ensure_ascii=False, allow_nan=False), text=True, encoding="utf-8",
            capture_output=True, timeout=15, cwd=workspace,
            env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1", "PYTHONIOENCODING": "utf-8"},
        )
    except (subprocess.TimeoutExpired, OSError) as exc:
        record_evidence({"revision": revision, "exception_type": type(exc).__name__,
                         "detail": str(exc)[-600:], "returncode": None,
                         "stdout_tail": review_probe_tail(getattr(exc, "stdout", None)),
                         "stderr_tail": review_probe_tail(getattr(exc, "stderr", None))}, "review_probe")
        raise TrustedGraderError("trusted_review_probe_execution", str(exc)) from exc
    execution = {"revision": revision, "returncode": process.returncode,
                 "stdout_tail": review_probe_tail(process.stdout),
                 "stderr_tail": review_probe_tail(process.stderr)}
    record_evidence(execution, "review_probe")
    if process.returncode != 0:
        raise TrustedGraderError("trusted_review_probe_execution", "probe did not complete")
    try:
        results = json.loads(process.stdout)
        if (not isinstance(results, list) or len(results) != len(payloads)
                or not all(isinstance(row, dict) and "result" in row and "unresolved" not in row
                           and isinstance(row.get("executed"), list) for row in results)):
            raise ValueError("unresolved or malformed probe result")
    except (ValueError, TypeError) as exc:
        raise TrustedGraderError("trusted_review_probe_result", str(exc)) from exc
    return results

# SmallOWBench RC2: explicit review delivery diagnostics.
def invalid_review(reason_code, detail):
    record_evidence({"reason_code": reason_code, "detail": str(detail)}, "review_submission")
    raise InvalidSubmission(reason_code + ": " + str(detail))


def review_delivery(condition, reason_code, detail):
    if not condition:
        invalid_review(reason_code, detail)


def read_review_report():
    path = APP / "review.json"
    review_delivery(path.is_file(), "review_report_missing", "write the structured review report")
    try:
        value = submission_value(load_json, path)
    except InvalidSubmission as exc:
        invalid_review("review_malformed_json", exc)
    try:
        return validate_review_submission(value)
    except InvalidSubmission as exc:
        invalid_review("review_invalid_shape", exc)


def validate_review_case(payload):
    try:
        return submission_value(validate, payload)
    except InvalidSubmission as exc:
        invalid_review("review_invalid_case_input", exc)


def trusted_review_value(function, *args):
    try:
        return function(*args)
    except (ValueError, TypeError, KeyError, UnicodeError, OSError, AssertionError) as exc:
        raise TrustedGraderError("trusted_review_fixture_invalid", str(exc)) from exc


def review_probe_tail(value):
    if isinstance(value, bytes):
        value = value.decode("utf-8", errors="replace")
    return (value or "")[-600:]


def test_review_report():
    report = read_review_report()
    assert set(report) == {"schema_version", "reviews"}
    assert report["schema_version"] == 2
    evidence = trusted_review_value(load_json, TESTS / "cases.json")
    snapshot = trusted_review_value(load_json, TESTS / "workspace.json")
    candidates = trusted_review_value(json.loads, snapshot["candidates.json"])["candidates"]
    review_delivery(len(report["reviews"]) == len(candidates),
                    "review_candidate_coverage", "exactly one entry per candidate is required")
    supplied = {row["candidate"]: row for row in report["reviews"]}
    review_delivery(len(supplied) == len(candidates) and set(supplied) == set(candidates),
                    "review_candidate_coverage", "candidate coverage")
    # Read the advertised working directory, but grade immutable clean snapshots.
    review_delivery(REPO.is_dir(), "review_workspace_missing", "working repository missing")
    actual = {path.relative_to(REPO).as_posix(): submission_text(path)
              for path in REPO.rglob("*") if path.is_file()
              and not {"__pycache__", ".pytest_cache", ".ruff_cache"}.intersection(path.relative_to(REPO).parts)
              and path.suffix not in {".pyc", ".pyo"}}
    review_delivery(actual == snapshot, "review_workspace_modified",
                    "review workspace is read-only; source or fixtures changed")
    for payload in evidence:
        trusted_review_value(validate, payload)
    gold = [trusted_review_value(evaluate, payload) for payload in evidence]
    with tempfile.TemporaryDirectory(prefix="review-grade-", dir=APP) as temporary:
        workspace = Path(temporary) / "repo"
        workspace.mkdir()
        for relative, content in snapshot.items():
            destination = workspace / relative
            if not destination.resolve().is_relative_to(workspace.resolve()):
                raise TrustedGraderError("trusted_review_fixture_invalid", "unsafe snapshot path")
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_text(content, encoding="utf-8")
        run_revision(workspace, "base", evidence)
        valid_count = 0
        for candidate in candidates:
            hidden = run_revision(workspace, candidate, evidence)
            correct = all(equivalent(item["result"], expected)
                          for item, expected in zip(hidden, gold))
            valid_count += correct
            row = supplied[candidate]
            assert set(row) == {"candidate", "decision", "location", "behavior", "cases"}
            record_evidence({"candidate": candidate, "contract_correct": correct,
                             "submitted_decision": row["decision"]}, "review_candidate")
            assert row["decision"] == ("accept" if correct else "reject"), "incorrect patch decision"
            cases = row["cases"]
            review_delivery(isinstance(cases, list) and 2 <= len(cases) <= 8,
                            "review_case_count", "provide 2-8 cases per candidate")
            review_delivery(len({canonical(case["input"]) for case in cases}) == len(cases),
                            "review_duplicate_cases", "distinct cases required")
            for case in cases:
                assert set(case) == {"input", "expected"}
                validate_review_case(case["input"])
                assert equivalent(case["expected"], evaluate(case["input"])), "invented expected behavior"
            payloads = [case["input"] for case in cases]
            # Both pre-change and candidate versions are executed on clean source.
            run_revision(workspace, "base", payloads)
            observed = run_revision(workspace, candidate, payloads)
            record_evidence({"candidate": candidate, "submitted_cases": cases,
                             "observed": observed}, "review_behavior")
            failures = [item for item, case in zip(observed, cases)
                        if not equivalent(item["result"], case["expected"])]
            if correct:
                assert row["location"] is None and row["behavior"] is None, "do not invent a defect"
                assert not failures, "compatibility evidence contradicts the contract"
            else:
                review_delivery(isinstance(row["behavior"], str) and bool(row["behavior"].strip()),
                                "review_behavior_empty", "rejection requires a nonempty description")
                assert failures, "reject requires an executable behavioral counterexample"
                location = row["location"]
                assert isinstance(location, dict) and set(location) == {"path", "line"}
                assert isinstance(location["path"], str) and location["path"].startswith("candidates/" + candidate + "/")
                assert type(location["line"]) is int and location["line"] > 0
                assert any(location in item["executed"] for item in failures), "location not executed by failing case"
        if valid_count != len(candidates) // 2:
            raise TrustedGraderError("trusted_review_candidate_balance", "bank must balance acceptance and rejection")
