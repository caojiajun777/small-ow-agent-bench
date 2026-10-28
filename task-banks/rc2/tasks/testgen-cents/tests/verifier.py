"""Private clean-tree replay, scoped submissions and stable behavior evidence.

This is grading hardening, not a security sandbox for malicious Python. The
agent never receives hidden implementations, and source/implementation probes
are forbidden by the public submission contract.
"""
import ast
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile

from verdict_v2 import record_evidence, TrustedGraderError


ROOT = Path(os.environ.get("BENCH_REPO_ROOT", "/app/repo"))
TESTS = Path(os.environ.get("BENCH_TESTS_ROOT", "/tests"))
APP = Path(os.environ.get("BENCH_APP_ROOT", "/app"))
TIMEOUT = float(os.environ.get("BENCH_CASE_TIMEOUT", "8"))


def content(path):
    value = path.read_bytes()
    if path.suffix.lower() in (".py", ".md", ".json", ".txt", ".csv", ".ini", ".toml", ".sh") or path.name == ".gitkeep":
        try:
            return value.decode("utf-8").replace("\r\n", "\n").replace("\r", "\n").encode("utf-8")
        except UnicodeDecodeError:
            pass  # binary fixtures retain exact-byte identity
    return value


def files(root):
    found = {}
    for path in root.rglob("*"):
        if path.is_symlink():
            raise ValueError("symlinks are outside the submission scope")
        if not path.is_file() or any(part in ("__pycache__", ".pytest_cache") for part in path.parts):
            continue
        if path.suffix == ".pyc":
            continue
        found[path.relative_to(root).as_posix()] = content(path)
    return found


def scope(kind):
    original, current = files(TESTS / "baseline"), files(ROOT)
    for name, value in original.items():
        if kind == "testgen" and name.startswith("tests/"):
            continue  # test submission area, not immutable application source
        if current.get(name) != value:
            raise ValueError("repository source changed: " + name)
    extra = set(current) - set(original)
    if kind == "repro" and extra:
        raise ValueError("reproducer may not modify repository")
    if kind == "testgen":
        for name in extra:
            if not name.startswith("tests/") or name.endswith("/conftest.py") or name == "tests/conftest.py":
                raise ValueError("only test files/fixtures under tests are allowed")
            if Path(name).suffix not in (".py", ".json", ".txt", ".csv"):
                raise ValueError("unsupported test fixture")
    return original, current


def source_guard(text):
    tree = ast.parse(text)
    forbidden_attrs = {"getsource", "getsourcelines", "getfile", "getsourcefile",
                       "__code__", "co_code", "co_consts"}
    for node in ast.walk(tree):
        if isinstance(node, ast.Attribute) and node.attr in forbidden_attrs:
            raise ValueError("implementation/source introspection is not behavioral evidence")
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            if any(token in node.value for token in
                   ("/tests/gold", "/solution", "/app/repo", "_BENCH_CALL_LOG",
                    "_BENCH_RESULT_LOG", "case_manifest.json", "__code__")):
                raise ValueError("deployment/hidden implementation probing is forbidden")
    return tree


def child_env(base, control):
    keep = ("PATH", "SYSTEMROOT", "WINDIR", "LANG", "LC_ALL", "PATHEXT")
    env = {key: value for key, value in os.environ.items() if key.upper() in keep}
    env.update(PYTHONPATH=str(base), PYTHONDONTWRITEBYTECODE="1",
               PYTEST_DISABLE_PLUGIN_AUTOLOAD="1", PYTHONIOENCODING="utf-8", PYTHONUTF8="1",
               TMP=str(control), TEMP=str(control),
               _BENCH_CALL_LOG=str(control / "calls.log"),
               _BENCH_RESULT_LOG=str(control / "result.json"))
    return env


def protected_ok(base, before):
    return all((base / name).is_file() and content(base / name) == value
               for name, value in before.items())


# SmallOWBench RC2: preserve execution evidence before coverage classification.
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


def run_case(kind, patch, submission):
    with tempfile.TemporaryDirectory(prefix="batch-replay-", dir=APP) as raw:
        work = Path(raw)
        base, control = work / "project", work / "control"
        control.mkdir()
        shutil.copytree(TESTS / "baseline", base)
        for destination, source in patch.items():
            target = base / destination
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(TESTS / source, target)
        if kind == "testgen":
            target_tests = base / "tests"
            target_tests.mkdir(exist_ok=True)
            for name, value in submission.items():
                path = base / name
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(value)
            shutil.copyfile(TESTS / "pytest_probe.py", base / "conftest.py")
            (base / "pytest.ini").write_text("[pytest]\n", encoding="utf-8")
            command = [sys.executable, "-B", "-m", "pytest", str(target_tests), "-q",
                       "-p", "no:cacheprovider", "--assert=plain", "--rootdir", str(base),
                       "-c", str(base / "pytest.ini"), "--basetemp", str(control / "pytest")]
        else:
            script = control / "repro.py"
            script.write_bytes(submission)
            command = [sys.executable, "-B", str(script)]
        before = files(base)
        # Tests and temporary fixtures are allowed to change; implementation and
        # the trusted observer must remain intact after replay.
        protected = {name: value for name, value in before.items()
                     if not name.startswith("tests/")}
        env = child_env(base, control)
        try:
            result = subprocess.run(command, cwd=base if kind == "testgen" else control,
                                    env=env, capture_output=True,
                                    text=True, timeout=TIMEOUT)
        except subprocess.TimeoutExpired as exc:
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


def evaluate():
    manifest = json.loads((TESTS / "case_manifest.json").read_text(encoding="utf-8"))
    kind = manifest["kind"]
    try:
        original, current = scope(kind)
        if kind == "testgen":
            submission = {name: value for name, value in current.items()
                          if name.startswith("tests/") and name != "tests/.gitkeep"}
            py = [name for name in submission if name.endswith(".py")]
            if not py or not any(Path(name).name.startswith("test_") for name in py):
                raise ValueError("write behavioral tests under tests/test_*.py")
            for name in py:
                source_guard(submission[name].decode("utf-8"))
        else:
            script = APP / "repro.py"
            if not script.is_file() or script.is_symlink():
                raise ValueError("write one standalone repro.py")
            submission = script.read_bytes()
            source_guard(submission.decode("utf-8"))
    except (ValueError, OSError, SyntaxError, UnicodeDecodeError) as exc:
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
