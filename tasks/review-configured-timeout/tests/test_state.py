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
                        record_evidence)

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
    process = subprocess.run(
        [sys.executable, "-B", str(TESTS / "probe.py"), str(workspace), revision],
        input=json.dumps(payloads, ensure_ascii=False, allow_nan=False), text=True, encoding="utf-8",
        capture_output=True, timeout=15, cwd=workspace,
        env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1", "PYTHONIOENCODING": "utf-8"},
    )
    assert process.returncode == 0, "probe did not complete: " + process.stderr[-1000:]
    results = json.loads(process.stdout)
    assert len(results) == len(payloads)
    assert all("result" in result and "unresolved" not in result for result in results), "unresolved execution"
    return results

def test_review_report():
    assert (APP / "review.json").is_file(), "write the structured review report"
    report = validate_review_submission(submission_value(load_json, APP / "review.json"))
    assert set(report) == {"schema_version", "reviews"}
    assert report["schema_version"] == 2
    evidence = load_json(TESTS / "cases.json")
    snapshot = load_json(TESTS / "workspace.json")
    candidates = json.loads(snapshot["candidates.json"])["candidates"]
    assert len(report["reviews"]) == len(candidates)
    supplied = {row["candidate"]: row for row in report["reviews"]}
    assert len(supplied) == len(candidates) and set(supplied) == set(candidates), "candidate coverage"
    # Read the advertised working directory, but grade immutable clean snapshots.
    assert REPO.is_dir(), "working repository missing"
    actual = {path.relative_to(REPO).as_posix(): submission_text(path)
              for path in REPO.rglob("*") if path.is_file()
              and not {"__pycache__", ".pytest_cache", ".ruff_cache"}.intersection(path.relative_to(REPO).parts)
              and path.suffix not in {".pyc", ".pyo"}}
    assert actual == snapshot, "review workspace is read-only; source or fixtures changed"
    for payload in evidence:
        validate(payload)
    gold = [evaluate(payload) for payload in evidence]
    with tempfile.TemporaryDirectory(prefix="review-grade-", dir=APP) as temporary:
        workspace = Path(temporary) / "repo"
        workspace.mkdir()
        for relative, content in snapshot.items():
            destination = workspace / relative
            assert destination.resolve().is_relative_to(workspace.resolve()), "unsafe snapshot path"
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
            assert isinstance(cases, list) and 2 <= len(cases) <= 8
            assert len({canonical(case["input"]) for case in cases}) == len(cases), "distinct cases required"
            for case in cases:
                assert set(case) == {"input", "expected"}
                submission_value(validate, case["input"])
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
                assert isinstance(row["behavior"], str) and len(row["behavior"].strip()) >= 10
                assert failures, "reject requires an executable behavioral counterexample"
                location = row["location"]
                assert isinstance(location, dict) and set(location) == {"path", "line"}
                assert isinstance(location["path"], str) and location["path"].startswith("candidates/" + candidate + "/")
                assert type(location["line"]) is int and location["line"] > 0
                assert any(location in item["executed"] for item in failures), "location not executed by failing case"
        assert valid_count == len(candidates) // 2, "bank must balance acceptance and rejection"
