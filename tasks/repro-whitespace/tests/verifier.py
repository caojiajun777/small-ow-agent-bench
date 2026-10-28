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
        except subprocess.TimeoutExpired:
            return {"state": "invalid", "reason": "timeout"}
        if not protected_ok(base, protected):
            return {"state": "invalid", "reason": "private implementation changed",
                    "changed_paths": [name for name, value in protected.items()
                                      if not (base / name).is_file() or content(base / name) != value]}
        marker = control / "calls.log"
        if not marker.is_file() or "workflow.run" not in marker.read_text(encoding="utf-8"):
            return {"state": "invalid", "reason": "public workflow was not exercised"}
        output = (result.stdout or "") + (result.stderr or "")
        if kind == "repro":
            if result.returncode == 0:
                return {"state": "pass"}
            # Inspect the actual stderr exception prefix, never arbitrary business
            # output (an assertion can legitimately contain an ID named ImportError).
            stderr_lines = (result.stderr or "").strip().splitlines()
            exception_type = stderr_lines[-1].split(":", 1)[0].strip() if stderr_lines else "nonzero"
            invalid_types = {"ModuleNotFoundError", "ImportError", "SyntaxError",
                             "IndentationError", "TimeoutError", "TimeoutExpired",
                             "MemoryError", "KeyboardInterrupt"}
            if result.returncode < 0 or exception_type in invalid_types:
                return {"state": "invalid", "reason": "invalid reproducer execution", "tail": output[-600:]}
            return {"state": "behavior_fail", "fingerprint": [result.returncode, exception_type]}
        log = control / "result.json"
        if not log.is_file():
            return {"state": "invalid", "reason": "no structured pytest result", "tail": output[-600:]}
        data = json.loads(log.read_text(encoding="utf-8"))
        if not data.get("collected"):
            return {"state": "invalid", "reason": "no tests collected"}
        failures = [r for r in data["reports"] if r["outcome"] == "failed"]
        bad_types = {"ImportError", "ModuleNotFoundError", "SyntaxError", "IndentationError",
                     "TimeoutError", "TimeoutExpired", "MemoryError", "SystemExit",
                     "KeyboardInterrupt", "CollectionError"}
        if any(r["phase"] != "call" or r["error"] in bad_types for r in failures):
            return {"state": "invalid", "reason": "import/collection/setup/infrastructure error", "tail": output[-600:]}
        if result.returncode == 0 and any(r["phase"] == "call" and r["outcome"] == "passed" for r in data["reports"]):
            return {"state": "pass"}
        if result.returncode == 1 and failures:
            return {"state": "behavior_fail", "fingerprint": sorted((r["node"], r["error"]) for r in failures)}
        return {"state": "invalid", "reason": "no stable behavior verdict", "tail": output[-600:]}


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
        return {"ok": False, "category": "invalid_submission", "reason": str(exc)}
    evidence = []
    if kind == "repro":
        buggy = [run_case(kind, {}, submission) for _ in range(2)]
        evidence.append({"variant": "buggy", "runs": buggy})
        if not all(row["state"] == "behavior_fail" for row in buggy) or buggy[0].get("fingerprint") != buggy[1].get("fingerprint"):
            return {"ok": False, "category": "not_stable_target_reproduction", "evidence": evidence}
    for variant in manifest["correct"]:
        runs = [run_case(kind, variant["patch"], submission) for _ in range(2)]
        evidence.append({"variant": variant["name"], "runs": runs})
        if not all(row["state"] == "pass" for row in runs):
            return {"ok": False, "category": "rejects_correct_implementation", "evidence": evidence}
    if kind == "testgen":
        for variant in manifest["incorrect"]:
            runs = [run_case(kind, variant["patch"], submission) for _ in range(2)]
            evidence.append({"variant": variant["name"], "runs": runs})
            if not all(row["state"] == "behavior_fail" for row in runs) or runs[0].get("fingerprint") != runs[1].get("fingerprint"):
                return {"ok": False, "category": "missed_or_invalid_mutant_evidence", "evidence": evidence}
    return {"ok": True, "category": "verified_behavior", "evidence": evidence}
