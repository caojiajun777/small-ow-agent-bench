"""Pure, fail-closed RC1 -> RC2 candidate-bank text transformations.

These functions do not write files or select tasks. The caller must read the
frozen RC1 bank, write a separate candidate bank and freeze it independently.
No model submission or historical score is rewritten by this module.

Public API (each takes text and returns text; line endings normalize to LF):
* patch_review_state: public nonempty-description contract, structured delivery
  reason codes in private ``review_submission`` evidence. Malformed user JSON,
  shape, candidate coverage and case shape remain InvalidSubmission; trusted
  fixtures and probe failures are deliberately outside that exception boundary.
* patch_replay_verifier: retain replay/scope semantics but preserve execution
  evidence before workflow coverage, and distinguish invalid_execution,
  unstable_evidence, missed_mutant and rejects_correct_implementation. Missing
  or malformed trusted pytest reports remain TrustedGraderError, not zeroes.
* clarify_submission_readme: public source may be read by the agent; submitted
  behavioral code must not introspect it. Testgen's existing fixture suffix
  whitelist is made explicit, not widened.

The transformations are idempotent on their own outputs and reject missing,
duplicate or partially transformed anchors. They never silently replace zero
occurrences. Hidden implementations, expected labels and behavioral contracts
are neither inspected nor modified.
"""
from __future__ import annotations

import ast


class PatchError(ValueError):
    """The input is not the expected complete RC1/RC2 source."""


def _lf(text: str) -> str:
    if not isinstance(text, str):
        raise TypeError("source must be text")
    return text.replace("\r\n", "\n").replace("\r", "\n")


def _once(text: str, old: str, new: str) -> str:
    count = text.count(old)
    if count != 1:
        raise PatchError(f"expected one RC1 anchor, found {count}: {old[:85]!r}")
    return text.replace(old, new, 1)


def _completed(text: str, marker: str, required: tuple[str, ...], *, python: bool) -> bool:
    if marker not in text:
        return False
    if text.count(marker) != 1 or any(text.count(anchor) != 1 for anchor in required):
        raise PatchError("partial or duplicate RC2 transformation")
    if python:
        ast.parse(text)
    return True


def _function(text: str, name: str) -> str:
    functions = [node for node in ast.parse(text).body
                 if isinstance(node, ast.FunctionDef) and node.name == name]
    if len(functions) != 1:
        raise PatchError("expected exactly one function: " + name)
    return ast.get_source_segment(text, functions[0])


_REVIEW_HELPERS = '''# SmallOWBench RC2: explicit review delivery diagnostics.
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


'''


_REVIEW_RUN_REVISION = '''def run_revision(workspace, revision, payloads):
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
    return results'''


def patch_review_state(text: str) -> str:
    text = _lf(text)
    marker = "# SmallOWBench RC2: explicit review delivery diagnostics."
    if _completed(text, marker, ("def read_review_report():", "report = read_review_report()",
                                 '"review_behavior_empty"', '"trusted_review_probe_result"'), python=True):
        if 'len(row["behavior"].strip()) >= 10' in text:
            raise PatchError("partial RC2 behavior contract")
        return text
    text = _once(text, "                        record_evidence)",
                 "                        record_evidence, InvalidSubmission, TrustedGraderError)")
    old_probe = _function(text, "run_revision")
    if ('assert process.returncode == 0' not in old_probe or '"unresolved execution"' not in old_probe):
        raise PatchError("unrecognized RC1 review probe")
    text = _once(text, old_probe, _REVIEW_RUN_REVISION)
    text = _once(text, "def test_review_report():\n", _REVIEW_HELPERS + "def test_review_report():\n")
    text = _once(text,
                 '    assert (APP / "review.json").is_file(), "write the structured review report"\n'
                 '    report = validate_review_submission(submission_value(load_json, APP / "review.json"))',
                 '    report = read_review_report()')
    replacements = (
        ('    evidence = load_json(TESTS / "cases.json")',
         '    evidence = trusted_review_value(load_json, TESTS / "cases.json")'),
        ('    snapshot = load_json(TESTS / "workspace.json")',
         '    snapshot = trusted_review_value(load_json, TESTS / "workspace.json")'),
        ('    candidates = json.loads(snapshot["candidates.json"])["candidates"]',
         '    candidates = trusted_review_value(json.loads, snapshot["candidates.json"])["candidates"]'),
        ('    assert len(report["reviews"]) == len(candidates)',
         '    review_delivery(len(report["reviews"]) == len(candidates),\n'
         '                    "review_candidate_coverage", "exactly one entry per candidate is required")'),
        ('    assert len(supplied) == len(candidates) and set(supplied) == set(candidates), "candidate coverage"',
         '    review_delivery(len(supplied) == len(candidates) and set(supplied) == set(candidates),\n'
         '                    "review_candidate_coverage", "candidate coverage")'),
        ('    assert REPO.is_dir(), "working repository missing"',
         '    review_delivery(REPO.is_dir(), "review_workspace_missing", "working repository missing")'),
        ('    assert actual == snapshot, "review workspace is read-only; source or fixtures changed"',
         '    review_delivery(actual == snapshot, "review_workspace_modified",\n'
         '                    "review workspace is read-only; source or fixtures changed")'),
        ('            assert isinstance(cases, list) and 2 <= len(cases) <= 8',
         '            review_delivery(isinstance(cases, list) and 2 <= len(cases) <= 8,\n'
         '                            "review_case_count", "provide 2-8 cases per candidate")'),
        ('            assert len({canonical(case["input"]) for case in cases}) == len(cases), "distinct cases required"',
         '            review_delivery(len({canonical(case["input"]) for case in cases}) == len(cases),\n'
         '                            "review_duplicate_cases", "distinct cases required")'),
        ('                submission_value(validate, case["input"])',
         '                validate_review_case(case["input"])'),
        ('        validate(payload)', '        trusted_review_value(validate, payload)'),
        ('    gold = [evaluate(payload) for payload in evidence]',
         '    gold = [trusted_review_value(evaluate, payload) for payload in evidence]'),
        ('            assert destination.resolve().is_relative_to(workspace.resolve()), "unsafe snapshot path"',
         '            if not destination.resolve().is_relative_to(workspace.resolve()):\n'
         '                raise TrustedGraderError("trusted_review_fixture_invalid", "unsafe snapshot path")'),
        ('        assert valid_count == len(candidates) // 2, "bank must balance acceptance and rejection"',
         '        if valid_count != len(candidates) // 2:\n'
         '            raise TrustedGraderError("trusted_review_candidate_balance", "bank must balance acceptance and rejection")'),
        ('                assert isinstance(row["behavior"], str) and len(row["behavior"].strip()) >= 10',
         '                review_delivery(isinstance(row["behavior"], str) and bool(row["behavior"].strip()),\n'
         '                                "review_behavior_empty", "rejection requires a nonempty description")'),
    )
    for old, new in replacements:
        text = _once(text, old, new)
    ast.parse(text)
    return text


_EXECUTION_HELPERS = '''# SmallOWBench RC2: preserve execution evidence before coverage classification.
def output_tail(value):
    if isinstance(value, bytes):
        value = value.decode("utf-8", errors="replace")
    return (value or "")[-600:]


def replay_result(state, reason_code, reason, execution, workflow_exercised,
                  pytest_result=None, **extra):
    value = {"state": state, "reason_code": reason_code, "reason": reason,
             "execution": execution, "workflow_exercised": workflow_exercised,
             "returncode": execution["returncode"],
             "tail": (execution["stdout_tail"] + execution["stderr_tail"])[-600:]}
    if pytest_result is not None:
        value["pytest"] = pytest_result
    value.update(extra)
    return value


def read_pytest_result(path, returncode):
    # This file is emitted by the trusted observer, not by an agent report API.
    if not path.is_file():
        raise TrustedGraderError("trusted_replay_missing_result", "no structured pytest result")
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        if (not isinstance(data, dict) or type(data.get("collected")) is not int
                or data["collected"] < 0 or type(data.get("exitstatus")) is not int
                or data["exitstatus"] != returncode or not isinstance(data.get("reports"), list)):
            raise ValueError("invalid pytest report shape or exit-code disagreement")
        for row in data["reports"]:
            if (not isinstance(row, dict) or not {"phase", "node", "outcome", "error"}.issubset(row)
                    or row.get("phase") not in
                    ("collection", "setup", "call", "teardown")
                    or row.get("outcome") not in ("passed", "failed", "skipped")
                    or not isinstance(row.get("node"), str)
                    or (row.get("error") is not None and not isinstance(row["error"], str))):
                raise ValueError("invalid pytest report entry")
        return data
    except (ValueError, TypeError, OSError, UnicodeError) as exc:
        raise TrustedGraderError("trusted_replay_invalid_result", str(exc)) from exc


'''

_REPLAY_FINISH = '''        except subprocess.TimeoutExpired as exc:
            execution = {"returncode": None, "stdout_tail": output_tail(exc.stdout),
                         "stderr_tail": output_tail(exc.stderr), "exception_type": type(exc).__name__}
            marker = control / "calls.log"
            exercised = marker.is_file() and "workflow.run" in marker.read_text(encoding="utf-8")
            return replay_result("invalid", "execution_timeout", "timeout", execution, exercised)
        execution = {"returncode": result.returncode, "stdout_tail": output_tail(result.stdout),
                     "stderr_tail": output_tail(result.stderr)}
        marker = control / "calls.log"
        workflow_exercised = marker.is_file() and "workflow.run" in marker.read_text(encoding="utf-8")
        data = None
        if kind == "testgen":
            try:
                data = read_pytest_result(control / "result.json", result.returncode)
            except TrustedGraderError as exc:
                record_evidence({"reason_code": exc.category, "execution": execution,
                                 "workflow_exercised": workflow_exercised}, "replay_runner")
                raise
        def outcome(state, code, reason, **extra):
            return replay_result(state, code, reason, execution, workflow_exercised, data, **extra)
        if not protected_ok(base, protected):
            return outcome("invalid", "private_implementation_modified", "private implementation changed",
                           changed_paths=[name for name, value in protected.items()
                                          if not (base / name).is_file() or content(base / name) != value])
        if kind == "repro":
            stderr_lines = (result.stderr or "").strip().splitlines()
            exception_type = stderr_lines[-1].split(":", 1)[0].strip() if stderr_lines else "nonzero"
            execution["exception_type"] = None if result.returncode == 0 else exception_type
            invalid_types = {"ModuleNotFoundError", "ImportError", "SyntaxError",
                             "IndentationError", "TimeoutError", "TimeoutExpired",
                             "MemoryError", "KeyboardInterrupt"}
            if result.returncode < 0 or exception_type in invalid_types:
                return outcome("invalid", "reproducer_execution_invalid", "invalid reproducer execution")
            if not workflow_exercised:
                return outcome("invalid", "workflow_not_exercised", "public workflow was not exercised")
            if result.returncode == 0:
                return outcome("pass", "behavior_pass", "observable behavior passed")
            return outcome("behavior_fail", "behavior_failure", "observable behavior failed",
                           fingerprint=[result.returncode, exception_type])
        failures = [row for row in data["reports"] if row["outcome"] == "failed"]
        bad_types = {"ImportError", "ModuleNotFoundError", "SyntaxError", "IndentationError",
                     "TimeoutError", "TimeoutExpired", "MemoryError", "SystemExit",
                     "KeyboardInterrupt", "CollectionError"}
        if result.returncode in (3, 4):
            record_evidence({"execution": execution, "pytest": data}, "replay_runner")
            raise TrustedGraderError("trusted_replay_pytest_error", "pytest internal/configuration error")
        if any(row["phase"] != "call" or row["error"] in bad_types for row in failures):
            code = "pytest_collection_error" if any(row["phase"] == "collection" for row in failures) else "pytest_execution_invalid"
            return outcome("invalid", code, "import/collection/setup/infrastructure error")
        if not data["collected"]:
            return outcome("invalid", "pytest_no_tests_collected", "no tests collected")
        if result.returncode == 0 and any(row["phase"] == "call" and row["outcome"] == "passed" for row in data["reports"]):
            state, code, reason = "pass", "behavior_pass", "observable behavior passed"
        elif result.returncode == 1 and failures:
            state, code, reason = "behavior_fail", "behavior_failure", "observable behavior failed"
        else:
            return outcome("invalid", "pytest_no_stable_verdict", "no stable behavior verdict")
        if not workflow_exercised:
            return outcome("invalid", "workflow_not_exercised", "public workflow was not exercised")
        if state == "behavior_fail":
            return outcome(state, code, reason, fingerprint=sorted((row["node"], row["error"]) for row in failures))
        return outcome(state, code, reason)


'''

_EVALUATE_FINISH = '''    except (ValueError, OSError, SyntaxError, UnicodeDecodeError) as exc:
        return {"ok": False, "category": "invalid_submission",
                "reason_code": "submission_scope_or_source_invalid", "reason": str(exc),
                "exception_type": type(exc).__name__}
    evidence = []
    def failed(category, code, reason):
        return {"ok": False, "category": category, "reason_code": code,
                "reason": reason, "evidence": evidence}
    def stable_failure(runs):
        return (all(row["state"] == "behavior_fail" for row in runs)
                and runs[0].get("fingerprint") == runs[1].get("fingerprint"))
    if kind == "repro":
        buggy = [run_case(kind, {}, submission) for _ in range(2)]
        evidence.append({"variant": "buggy", "runs": buggy})
        if any(row["state"] == "invalid" for row in buggy):
            return failed("invalid_execution", "target_execution_invalid", "invalid target replay is not reproduction evidence")
        if all(row["state"] == "pass" for row in buggy):
            return failed("not_stable_target_reproduction", "target_not_reproduced", "target defect was not reproduced")
        if not stable_failure(buggy):
            return failed("unstable_evidence", "target_evidence_unstable", "target replay did not fail consistently")
    for variant in manifest["correct"]:
        runs = [run_case(kind, variant["patch"], submission) for _ in range(2)]
        evidence.append({"variant": variant["name"], "runs": runs})
        if any(row["state"] == "invalid" for row in runs):
            return failed("invalid_execution", "correct_variant_execution_invalid", "invalid execution on correct variant")
        if stable_failure(runs):
            return failed("rejects_correct_implementation", "correct_variant_behavior_rejected", "behavioral evidence rejected a correct implementation")
        if not all(row["state"] == "pass" for row in runs):
            return failed("unstable_evidence", "correct_variant_evidence_unstable", "correct variant replay disagreed across runs")
    if kind == "testgen":
        for variant in manifest["incorrect"]:
            runs = [run_case(kind, variant["patch"], submission) for _ in range(2)]
            evidence.append({"variant": variant["name"], "runs": runs})
            if any(row["state"] == "invalid" for row in runs):
                return failed("invalid_execution", "mutant_execution_invalid", "invalid execution is not mutant detection")
            if all(row["state"] == "pass" for row in runs):
                return failed("missed_mutant", "mutant_not_detected", "a required mutant passed both replays")
            if not stable_failure(runs):
                return failed("unstable_evidence", "mutant_evidence_unstable", "mutant failure did not reproduce consistently")
    return {"ok": True, "category": "verified_behavior", "reason_code": "verified_behavior", "evidence": evidence}
'''


def patch_replay_verifier(text: str) -> str:
    text = _lf(text)
    marker = "# SmallOWBench RC2: preserve execution evidence before coverage classification."
    if _completed(text, marker, ("def read_pytest_result(path, returncode):",
                                 '"correct_variant_execution_invalid"', '"mutant_not_detected"'), python=True):
        if '"missed_or_invalid_mutant_evidence"' in text:
            raise PatchError("partial RC2 replay classification")
        return text
    text = _once(text, "import tempfile\n", "import tempfile\n\nfrom verdict_v2 import record_evidence, TrustedGraderError\n")
    text = _once(text, "def run_case(kind, patch, submission):\n", _EXECUTION_HELPERS + "def run_case(kind, patch, submission):\n")
    start = text.index("        except subprocess.TimeoutExpired:\n") if text.count("        except subprocess.TimeoutExpired:\n") == 1 else -1
    end = text.index("def evaluate():\n") if text.count("def evaluate():\n") == 1 else -1
    if start < 0 or end <= start:
        raise PatchError("missing or duplicate replay function boundary")
    old_finish = text[start:end]
    for anchor in ('"public workflow was not exercised"', '"no structured pytest result"',
                   '"no stable behavior verdict"', '"fingerprint"'):
        if anchor not in old_finish:
            raise PatchError("unrecognized RC1 replay body")
    text = text[:start] + _REPLAY_FINISH + text[end:]
    anchor = "    except (ValueError, OSError, SyntaxError, UnicodeDecodeError) as exc:\n"
    if text.count(anchor) != 1 or not text.rstrip().endswith('return {"ok": True, "category": "verified_behavior", "evidence": evidence}'):
        raise PatchError("unrecognized RC1 evaluate body")
    text = text[:text.index(anchor)] + _EVALUATE_FINISH
    ast.parse(text)
    return text


_SOURCE_OLD = '''Do not inspect implementation source, bytecode, verifier files, candidate names,
hidden paths or deployment-absolute paths. Ordinary subprocess CLI testing and
inspect.signature are allowed; inspect.getsource/getfile is not behavioral
evidence. Import workflow normally; grading supplies its module search path.
'''
_SOURCE_NEW = '''The agent may read public application source while understanding the task.
The submitted tests or reproducer must check observable behavior: they must not
inspect implementation source or bytecode, verifier files, candidate names,
hidden paths or deployment-absolute paths. This restriction applies to the
submitted behavioral code, not the agent's reading of public application source.
Ordinary subprocess CLI testing and inspect.signature are allowed;
inspect.getsource/getfile in submitted code is not behavioral evidence.
Import workflow normally; grading supplies its module search path.
'''
_FIXTURES_OLD = "Add tests and small JSON/CSV/text fixtures only under tests/."
_FIXTURES_NEW = ("Add tests/helpers as .py files and small .json, .txt or .csv fixtures only under tests/. "
                 "These are the permitted submission file suffixes.")


def clarify_submission_readme(text: str) -> str:
    text = _lf(text)
    if _SOURCE_NEW in text:
        if text.count(_SOURCE_NEW) != 1 or _SOURCE_OLD in text:
            raise PatchError("partial README clarification")
        if _FIXTURES_OLD in text:
            raise PatchError("partial Testgen fixture clarification")
        return text
    text = _once(text, _SOURCE_OLD, _SOURCE_NEW)
    if _FIXTURES_OLD in text:
        text = _once(text, _FIXTURES_OLD, _FIXTURES_NEW)
    elif text.count("Write one standalone repro.py outside the repository.") != 1:
        raise PatchError("unrecognized Testgen/Repro submission contract")
    return text
