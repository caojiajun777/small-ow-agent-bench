"""SmallOWBench 2.0 trusted verdict controller (not a security sandbox).

Each task carries an identical copy. A separate, resource-isolated grader
container is the production execution boundary; this module provides structured
classification, output/time bounds, process cleanup and controller-only rewards.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import signal
import stat
import subprocess
import sys
import tempfile
import threading
import time

VERSION = "2.0.0-rc.1"
EXCLUDED = {".git", "__pycache__", ".pytest_cache", ".mypy_cache", ".ruff_cache"}
# Mirrored from agents.artifacts_v2.CaptureLimits; no runtime cross-repo import.
MAX_FILES, MAX_FILE_BYTES, MAX_TOTAL_BYTES = 256, 1_048_576, 8_388_608
SENSITIVE = {"credentials", "credentials.json", "id_rsa", "id_ed25519",
             ".netrc", ".npmrc", ".pypirc", ".aws", ".ssh"}
_EVIDENCE = []
_SUBMISSION_RESULT = None


class InvalidSubmission(AssertionError):
    """An explicitly identified malformed/invalid user artifact, not infrastructure."""

class InvalidResourceSubmission(InvalidSubmission):
    """An observed user artifact exceeds the frozen capture resource contract."""


class TrustedGraderError(RuntimeError):
    """A structured failure of a trusted nested runner, never a model zero."""

    def __init__(self, category, detail):
        self.category = category
        super().__init__(detail)


def record_evidence(value, kind="grading"):
    _EVIDENCE.append({"kind": kind, "value": value})


def record_submission_result(result):
    global _SUBMISSION_RESULT
    _SUBMISSION_RESULT = result
    record_evidence(result, "submission_verification")


def submission_value(function, *args, **kwargs):
    """Use ONLY at a known user-input boundary, never around trusted fixtures."""
    try:
        return function(*args, **kwargs)
    except (ValueError, TypeError, KeyError, UnicodeError, OSError, AssertionError) as exc:
        raise InvalidSubmission(str(exc)) from exc


def submission_text(path):
    return submission_value(Path(path).read_text, encoding="utf-8")


def submission_json(text):
    return submission_value(json.loads, text)


def validate_review_submission(value):
    """Validate user report shape before trusted contract evaluation."""
    if not isinstance(value, dict) or set(value) != {"schema_version", "reviews"}:
        raise InvalidSubmission("review report must be an object with schema_version and reviews")
    if type(value["schema_version"]) is not int or value["schema_version"] != 2:
        raise InvalidSubmission("unsupported review schema")
    if not isinstance(value["reviews"], list):
        raise InvalidSubmission("reviews must be a list")
    for row in value["reviews"]:
        if not isinstance(row, dict) or set(row) != {"candidate", "decision", "location", "behavior", "cases"}:
            raise InvalidSubmission("invalid review row")
        if not isinstance(row["candidate"], str) or row["decision"] not in ("accept", "reject"):
            raise InvalidSubmission("candidate and decision must be valid strings")
        if row["location"] is not None:
            location = row["location"]
            if not isinstance(location, dict) or set(location) != {"path", "line"}:
                raise InvalidSubmission("invalid review location")
            if not isinstance(location["path"], str) or type(location["line"]) is not int:
                raise InvalidSubmission("invalid location types")
        if row["behavior"] is not None and not isinstance(row["behavior"], str):
            raise InvalidSubmission("behavior must be a string or null")
        if not isinstance(row["cases"], list):
            raise InvalidSubmission("cases must be a list")
        for case in row["cases"]:
            if not isinstance(case, dict) or set(case) != {"input", "expected"}:
                raise InvalidSubmission("invalid behavioral case")
    return value


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False,
                      allow_nan=False).encode("utf-8")


def atomic_bytes(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".tmp-" + str(os.getpid()))
    try:
        temporary.write_bytes(value)
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def atomic_json(path, value):
    atomic_bytes(path, json.dumps(value, ensure_ascii=False, allow_nan=False,
                                 indent=2).encode("utf-8") + b"\n")


def native_temporary_root():
    """Do not place pytest fd-capture files on the bind-mounted verdict volume.

    In Linux graders /tmp is container-native even when /logs is a Windows
    Docker bind mount. Ignore inherited TMPDIR/TEMP/TMP on every platform.
    Windows offline checks use local app temp or an explicit trusted local
    BENCH_WINDOWS_TMP_ROOT (needed by restricted desktop test environments).
    Linux deliberately ignores that override.
    """
    if os.name == "nt":
        local = os.environ.get("LOCALAPPDATA")
        override = os.environ.get("BENCH_WINDOWS_TMP_ROOT")
        root = Path(override) if override else (
            Path(local) if local else Path.home() / "AppData" / "Local") / "Temp"
        if not root.is_absolute():
            raise ValueError("Windows native temp root must be an absolute local path")
    else:
        root = Path("/tmp")
    output = os.environ.get("BENCH_VERDICT_DIR")
    if output and root.resolve().is_relative_to(Path(output).resolve()):
        raise ValueError("native temp root must not be inside verdict output")
    root.mkdir(parents=True, exist_ok=True)
    return root.resolve()


def child_environment(control):
    env = os.environ.copy()
    for key in list(env):
        if any(marker in key.upper() for marker in
               ("API_KEY", "ACCESS_TOKEN", "SECRET_KEY", "GITHUB_TOKEN", "HF_TOKEN")):
            env.pop(key, None)
    env.pop("PYTEST_ADDOPTS", None)
    env.pop("PYTEST_PLUGINS", None)
    env.update(PYTHONDONTWRITEBYTECODE="1", PYTHONNOUSERSITE="1",
               PYTHONUTF8="1", PYTHONIOENCODING="utf-8",
               PYTEST_DISABLE_PLUGIN_AUTOLOAD="1", TMP=str(control),
               TEMP=str(control), TMPDIR=str(control))
    return env


def submission_manifest(repo, app, skill):
    """Digest received raw artifacts/observations, never hidden grader fixtures."""
    rows = []
    total = 0
    repo, app = Path(repo), Path(app)

    def append(path, name, role):
        nonlocal total
        info = path.lstat()
        if not stat.S_ISREG(info.st_mode):
            raise InvalidSubmission("non-regular file outside artifact scope: " + name)
        if path.name.startswith(".env") or path.name.lower() in SENSITIVE:
            raise InvalidSubmission("sensitive artifact filename is prohibited: " + name)
        if len(rows) >= MAX_FILES or info.st_size > MAX_FILE_BYTES or total + info.st_size > MAX_TOTAL_BYTES:
            raise InvalidResourceSubmission("artifact exceeds frozen file count/size limits: " + name)
        descriptor = os.open(path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
        with os.fdopen(descriptor, "rb") as stream:
            opened = os.fstat(stream.fileno())
            if not stat.S_ISREG(opened.st_mode) or (opened.st_ino, opened.st_dev) != (info.st_ino, info.st_dev):
                raise InvalidSubmission("artifact changed during inspection: " + name)
            value = stream.read(MAX_FILE_BYTES + 1)
            final = os.fstat(stream.fileno())
        if len(value) > MAX_FILE_BYTES or total + len(value) > MAX_TOTAL_BYTES:
            raise InvalidResourceSubmission("artifact exceeds frozen size limits: " + name)
        if (opened.st_size, opened.st_mtime_ns) != (final.st_size, final.st_mtime_ns) or len(value) != final.st_size:
            raise InvalidSubmission("artifact changed during inspection: " + name)
        rows.append({"path": name, "role": role, "size_bytes": len(value),
                     "sha256": hashlib.sha256(value).hexdigest()})
        total += len(value)

    if repo.is_symlink():
        raise InvalidSubmission("repository may not be a symlink")
    if repo.is_dir():
        pending, entries = [repo], 0
        while pending:
            directory = pending.pop()
            with os.scandir(directory) as children:
                for entry in children:
                    path = Path(entry.path)
                    entries += 1
                    if entries > MAX_FILES * 32:
                        raise InvalidResourceSubmission("artifact directory-entry limit exceeded")
                    if entry.name in EXCLUDED or path.suffix in {".pyc", ".pyo"}:
                        continue
                    relative = path.relative_to(repo)
                    name = "repo/" + relative.as_posix()
                    if entry.name.startswith(".env") or entry.name.lower() in SENSITIVE:
                        raise InvalidSubmission("sensitive artifact filename is prohibited: " + name)
                    if entry.is_symlink():
                        raise InvalidSubmission("symlink outside artifact scope: " + name)
                    if entry.is_dir(follow_symlinks=False):
                        pending.append(path)
                    else:
                        role = "submission" if skill == "edit" or (skill == "testgen" and relative.parts[0] == "tests") else "observation"
                        append(path, name, role)
    primary = {"loc": "answer.txt", "repro": "repro.py", "review": "review.json"}.get(skill)
    if primary and ((app / primary).exists() or (app / primary).is_symlink()):
        append(app / primary, primary, "submission")
    rows.sort(key=lambda row: row["path"])
    return rows, hashlib.sha256(canonical(rows)).hexdigest()


def windows_job(process):
    """Assign the local worker to a kill-on-close Windows job, including children."""
    if os.name != "nt":
        return None
    import ctypes
    from ctypes import wintypes
    class BasicLimits(ctypes.Structure):
        _fields_ = [("process_time", ctypes.c_int64), ("job_time", ctypes.c_int64),
                    ("flags", wintypes.DWORD), ("min_working_set", ctypes.c_size_t),
                    ("max_working_set", ctypes.c_size_t), ("active_processes", wintypes.DWORD),
                    ("affinity", ctypes.c_size_t), ("priority", wintypes.DWORD),
                    ("scheduling", wintypes.DWORD)]
    class IoCounters(ctypes.Structure):
        _fields_ = [(name, ctypes.c_uint64) for name in
                    ("read_ops", "write_ops", "other_ops", "read_bytes", "write_bytes", "other_bytes")]
    class ExtendedLimits(ctypes.Structure):
        _fields_ = [("basic", BasicLimits), ("io", IoCounters),
                    ("process_memory", ctypes.c_size_t), ("job_memory", ctypes.c_size_t),
                    ("peak_process_memory", ctypes.c_size_t), ("peak_job_memory", ctypes.c_size_t)]
    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel.CreateJobObjectW.argtypes = [ctypes.c_void_p, wintypes.LPCWSTR]
    kernel.CreateJobObjectW.restype = wintypes.HANDLE
    kernel.SetInformationJobObject.argtypes = [wintypes.HANDLE, ctypes.c_int, ctypes.c_void_p, wintypes.DWORD]
    kernel.AssignProcessToJobObject.argtypes = [wintypes.HANDLE, wintypes.HANDLE]
    kernel.TerminateJobObject.argtypes = [wintypes.HANDLE, wintypes.UINT]
    kernel.CloseHandle.argtypes = [wintypes.HANDLE]
    handle = kernel.CreateJobObjectW(None, None)
    if not handle:
        raise ctypes.WinError(ctypes.get_last_error())
    limits = ExtendedLimits()
    limits.basic.flags = 0x2000  # JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE
    if not kernel.SetInformationJobObject(handle, 9, ctypes.byref(limits), ctypes.sizeof(limits)):
        error = ctypes.get_last_error()
        kernel.CloseHandle(handle)
        raise ctypes.WinError(error)
    if not kernel.AssignProcessToJobObject(handle, wintypes.HANDLE(int(process._handle))):
        error = ctypes.get_last_error()
        kernel.CloseHandle(handle)
        raise ctypes.WinError(error)
    return kernel, handle


def terminate_tree(process, job=None):
    """Linux process group / Windows job cleanup of ordinary descendants."""
    if job is not None:
        kernel, handle = job
        kernel.TerminateJobObject(handle, 1)
        return
    if os.name == "posix":
        try:
            os.killpg(process.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
    elif process.poll() is None:
        flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
        try:
            subprocess.run(["taskkill", "/PID", str(process.pid), "/T", "/F"],
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                           timeout=5, creationflags=flags)
        except (OSError, subprocess.TimeoutExpired):
            process.kill()


def run_capped(command, *, cwd, env, timeout_sec, output_limit_bytes=1048576):
    """Bound total captured output and wall time, including ordinary descendants."""
    started = time.monotonic()
    options = {"start_new_session": True} if os.name == "posix" else {
        "creationflags": getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0) |
                         getattr(subprocess, "CREATE_NO_WINDOW", 0)}
    process = subprocess.Popen(command, cwd=cwd, env=env, stdin=subprocess.DEVNULL,
                               stdout=subprocess.PIPE, stderr=subprocess.PIPE, **options)
    try:
        job = windows_job(process)
    except BaseException:
        terminate_tree(process)
        process.wait(timeout=5)
        raise
    lock, exceeded = threading.Lock(), threading.Event()
    kept = [bytearray(), bytearray()]
    total = [0]

    def consume(stream, index):
        while True:
            block = stream.read(65536)
            if not block:
                break
            with lock:
                available = max(0, output_limit_bytes - total[0])
                kept[index].extend(block[:available])
                total[0] += len(block)
                if total[0] > output_limit_bytes:
                    exceeded.set()

    threads = [threading.Thread(target=consume, args=(stream, index), daemon=True)
               for index, stream in enumerate((process.stdout, process.stderr))]
    for thread in threads:
        thread.start()
    reason = None
    while process.poll() is None:
        if exceeded.is_set():
            reason = "output_limit"
            break
        if time.monotonic() - started >= timeout_sec:
            reason = "timeout"
            break
        time.sleep(0.02)
    # Kill ordinary background descendants even if the worker leader exited.
    terminate_tree(process, job)
    try:
        process.wait(timeout=5)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait(timeout=5)
    for thread in threads:
        thread.join(timeout=2)
    if not any(thread.is_alive() for thread in threads):
        process.stdout.close()
        process.stderr.close()
    if job is not None:
        job[0].CloseHandle(job[1])
    if exceeded.is_set():
        reason = reason or "output_limit"
    if any(thread.is_alive() for thread in threads):
        reason = reason or "output_stream_not_closed"
    return {"returncode": process.returncode, "termination": reason,
            "stdout": bytes(kept[0]).decode("utf-8", errors="replace"),
            "stderr": bytes(kept[1]).decode("utf-8", errors="replace"),
            "captured_bytes": sum(len(value) for value in kept),
            "observed_output_bytes": total[0],
            "elapsed_sec": round(time.monotonic() - started, 6)}


class PublicPytestPlugin:
    """Reports from submitted tests; pytest's own internal errors stay distinct."""

    def __init__(self):
        self.collected = 0
        self.reports = []
        self.internal_errors = []

    def pytest_collection_finish(self, session):
        self.collected = len(session.items)

    def pytest_collectreport(self, report):
        if report.failed:
            self.reports.append({"node": report.nodeid, "phase": "collection",
                                 "outcome": "failed", "detail": str(report.longrepr)[-4000:]})

    def pytest_runtest_logreport(self, report):
        self.reports.append({"node": report.nodeid, "phase": report.when,
                             "outcome": report.outcome,
                             "detail": str(report.longrepr)[-4000:] if report.failed else None})

    def pytest_internalerror(self, excrepr, excinfo):
        self.internal_errors.append({"exception_type": excinfo.type.__name__,
                                     "detail": str(excrepr)[-4000:]})

    def verdict(self, exitstatus):
        code = int(exitstatus)
        failed = any(row["outcome"] == "failed" for row in self.reports)
        skipped = any(row["outcome"] == "skipped" for row in self.reports)
        if self.internal_errors or code in (3, 4):
            status, category = "error", "trusted_public_pytest_internal_error"
        elif failed and code in (1, 2):
            status, category = "fail", "public_test_failure"
        elif code == 5 and self.collected == 0:
            status, category = "fail", "public_tests_missing"
        elif code == 0 and skipped:
            status, category = "fail", "public_tests_skipped"
        elif (code == 0 and self.collected > 0 and not failed and
              sum(row.get("phase") == "call" and row["outcome"] == "passed"
                  for row in self.reports) == self.collected):
            status, category = "pass", None
        else:
            status, category = "error", "trusted_public_pytest_incomplete"
        return {"schema_version": 1, "worker_kind": "public_pytest",
                "status": status, "failure_category": category,
                "checks": {"collected": self.collected, "pytest_exitstatus": code,
                           "reports": self.reports, "internal_errors": self.internal_errors}}


def public_worker(repo, control, result_path):
    """Trusted entry point; never classify pytest internals by stderr text."""
    try:
        # Import pytest before adding the submitted repository to sys.path.
        import pytest
        sys.path.insert(0, str(repo))
        ini = control / "pytest.ini"
        ini.write_text("[pytest]\n", encoding="utf-8")
        plugin = PublicPytestPlugin()
        exitstatus = pytest.main(
            [str(repo / "tests"), "-q", "--tb=short", "--capture=fd",
             "-p", "no:cacheprovider", "-c", str(ini), "--rootdir", str(repo),
             "--confcutdir", str(repo / "tests"),
             "--basetemp", str(control / "pytest-temp")], plugins=[plugin])
        result = plugin.verdict(exitstatus)
        result["runtime"] = {"python": sys.version, "pytest": pytest.__version__}
    except BaseException as exc:
        result = {"schema_version": 1, "worker_kind": "public_pytest", "status": "error",
                  "failure_category": "trusted_public_pytest_runner_exception",
                  "checks": {"exception_type": type(exc).__name__, "detail": str(exc)[-4000:]}}
    atomic_json(result_path, result)
    return {"pass": 0, "fail": 1, "error": 2}[result["status"]]


def run_public_pytest(repo, timeout_sec=20):
    """Run submitted public regressions with bounded, structured classification.

    Assertion/import/collection failures in submitted tests are model failures.
    Internal pytest failures, missing reports and inconsistent runner exits are
    trusted errors. This is evidence isolation, not a malicious-code sandbox.
    """
    repo = Path(repo).resolve()
    if not 0 < float(timeout_sec) <= 3600:
        raise ValueError("invalid public pytest timeout")
    if not (repo / "tests").is_dir():
        record_evidence({"result": {"status": "fail", "failure_category": "public_tests_missing"}},
                        "public_pytest")
        raise InvalidSubmission("public tests directory is missing")
    with tempfile.TemporaryDirectory(prefix="public-pytest-v2-", dir=native_temporary_root()) as raw:
        control = Path(raw).resolve()
        result_path = control / "public-result.json"
        env = child_environment(control)
        # No repo pytest.py/sitecustomize or inherited plugin/config injection
        # during trusted entry-point bootstrap. public_worker adds repo later.
        env["PYTHONPATH"] = ""
        try:
            execution = run_capped(
                [sys.executable, "-B", str(Path(__file__).resolve()), "--public-worker",
                 "--repo-root", str(repo), "--control", str(control),
                 "--worker-result", str(result_path)],
                cwd=control, env=env, timeout_sec=float(timeout_sec))
        except BaseException as exc:
            record_evidence({"runner_exception": type(exc).__name__, "detail": str(exc)[-4000:]},
                            "public_pytest")
            raise TrustedGraderError("trusted_public_pytest_runner_exception", str(exc)) from exc
        evidence = {"execution": execution}
        if execution["termination"]:
            record_evidence(evidence, "public_pytest")
            if execution["termination"] in ("timeout", "output_limit"):
                raise InvalidResourceSubmission("public tests exceeded " + execution["termination"])
            raise TrustedGraderError("trusted_public_pytest_stream_error", execution["termination"])
        try:
            if not result_path.is_file():
                raise TrustedGraderError("trusted_public_pytest_missing_result", "public runner did not report")
            if result_path.stat().st_size > 2 * 1048576:
                raise TrustedGraderError("trusted_public_pytest_invalid_result", "public report exceeds limit")
            result = json.loads(result_path.read_text(encoding="utf-8"))
            if (not isinstance(result, dict) or result.get("schema_version") != 1 or
                    result.get("worker_kind") != "public_pytest" or
                    not isinstance(result.get("checks"), dict)):
                raise TrustedGraderError("trusted_public_pytest_invalid_result", "invalid public report shape")
            expected = {"pass": 0, "fail": 1, "error": 2}.get(result.get("status"))
            if expected is None or execution["returncode"] != expected:
                raise TrustedGraderError("trusted_public_pytest_invalid_result", "public status/exit-code disagreement")
            checks = result["checks"]
            if result["status"] != "error" or "pytest_exitstatus" in checks:
                if (type(checks.get("collected")) is not int or checks["collected"] < 0 or
                        type(checks.get("pytest_exitstatus")) is not int or
                        not isinstance(checks.get("reports"), list) or
                        not isinstance(checks.get("internal_errors"), list) or
                        any(not isinstance(row, dict) or row.get("outcome") not in
                            ("passed", "failed", "skipped") for row in checks["reports"])):
                    raise TrustedGraderError("trusted_public_pytest_invalid_result", "invalid public check data")
                plugin = PublicPytestPlugin()
                plugin.collected, plugin.reports = checks["collected"], checks["reports"]
                plugin.internal_errors = checks["internal_errors"]
                classified = plugin.verdict(checks["pytest_exitstatus"])
                if (classified["status"], classified["failure_category"]) != (
                        result["status"], result.get("failure_category")):
                    raise TrustedGraderError("trusted_public_pytest_invalid_result", "public report classification disagrees")
            elif result.get("failure_category") != "trusted_public_pytest_runner_exception":
                raise TrustedGraderError("trusted_public_pytest_invalid_result", "invalid public error category")
            evidence["report_sha256"] = hashlib.sha256(result_path.read_bytes()).hexdigest()
            evidence["result"] = result
        except TrustedGraderError:
            record_evidence(evidence, "public_pytest")
            raise
        except BaseException as exc:
            record_evidence(evidence, "public_pytest")
            raise TrustedGraderError("trusted_public_pytest_invalid_result", str(exc)) from exc
        record_evidence(evidence, "public_pytest")
        if result["status"] == "error":
            raise TrustedGraderError(result["failure_category"], "public pytest runner failed")
        if result["status"] == "fail":
            raise InvalidSubmission(result["failure_category"])
        return result


class VerdictPlugin:
    def __init__(self):
        self.collected = 0
        self.reports = []
        self.internal_errors = []

    def pytest_collection_finish(self, session):
        self.collected = len(session.items)

    def pytest_collectreport(self, report):
        if report.failed:
            self.reports.append({"node": report.nodeid, "phase": "collection",
                                 "outcome": "failed", "exception_type": None,
                                 "category": "trusted_collection_error"})

    def pytest_internalerror(self, excrepr, excinfo):
        self.internal_errors.append({"exception_type": excinfo.type.__name__,
                                     "detail": str(excrepr)[-4000:]})

    def pytest_runtest_makereport(self, item, call):
        outcome = yield
        report = outcome.get_result()
        exception_type = call.excinfo.type.__name__ if call.excinfo else None
        category = None
        if report.failed:
            if report.when != "call":
                category = "trusted_" + report.when + "_error"
            elif call.excinfo and isinstance(call.excinfo.value, InvalidSubmission):
                category = ("invalid_resource_submission" if isinstance(call.excinfo.value, InvalidResourceSubmission)
                            else "invalid_submission")
            elif call.excinfo and isinstance(call.excinfo.value, TrustedGraderError):
                category = call.excinfo.value.category
            elif exception_type in ("AssertionError", "Failed"):
                category = ((_SUBMISSION_RESULT or {}).get("category") or
                            "behavior_mismatch")
            else:
                category = "trusted_grader_exception"
        self.reports.append({"node": report.nodeid, "phase": report.when,
                             "outcome": report.outcome, "exception_type": exception_type,
                             "category": category,
                             "detail": str(call.excinfo.value)[-4000:] if call.excinfo else None})

    def verdict(self, exitstatus):
        failures = [row for row in self.reports if row["outcome"] == "failed"]
        errors = [row for row in failures if (row.get("category") or "").startswith("trusted_")]
        skipped = any(row["outcome"] == "skipped" for row in self.reports)
        if self.internal_errors or errors:
            status, category = "error", errors[0]["category"] if errors else "trusted_internal_error"
        elif failures:
            status, category = "fail", failures[0]["category"]
        elif int(exitstatus) != 0 or self.collected == 0 or skipped:
            status, category = "error", "trusted_grader_incomplete"
        else:
            status, category = "pass", None
        return {"status": status, "failure_category": category,
                "checks": {"collected": self.collected, "pytest_exitstatus": int(exitstatus),
                           "reports": self.reports, "internal_errors": self.internal_errors},
                "evidence": list(_EVIDENCE)}


def worker(tests, control, result_path):
    """Run only the immutable trusted test_state, not agent pytest configuration."""
    global _EVIDENCE, _SUBMISSION_RESULT
    _EVIDENCE, _SUBMISSION_RESULT = [], None
    sys.modules["verdict_v2"] = sys.modules[__name__]
    sys.path.insert(0, str(tests))
    try:
        import pytest
        VerdictPlugin.pytest_runtest_makereport = pytest.hookimpl(hookwrapper=True)(
            VerdictPlugin.pytest_runtest_makereport)
        plugin = VerdictPlugin()
        ini = control / "pytest.ini"
        ini.write_text("[pytest]\n", encoding="utf-8")
        exitstatus = pytest.main(
            [str(tests / "test_state.py"), "-q", "-s", "-x", "--tb=short", "-p", "no:cacheprovider",
             "-c", str(ini), "--rootdir", str(tests),
             "--basetemp", str(control / "pytest-temp")], plugins=[plugin])
        result = plugin.verdict(exitstatus)
        result["runtime"] = {"python": sys.version, "pytest": pytest.__version__}
    except BaseException as exc:
        result = {"status": "error", "failure_category": "trusted_worker_exception",
                  "checks": {"exception_type": type(exc).__name__, "detail": str(exc)[-4000:]},
                  "evidence": list(_EVIDENCE)}
    atomic_json(result_path, result)
    return {"pass": 0, "fail": 1, "error": 2}[result["status"]]


def controller(tests):
    started = time.monotonic()
    output = Path(os.environ.get("BENCH_VERDICT_DIR", "/logs/verifier")).resolve()
    output.mkdir(parents=True, exist_ok=True)
    # A caller must use a fresh trial directory. Invalidate only this controller's
    # owned reward before any new classification so errors cannot retain stale 1/0.
    for owned in ("reward.txt", "worker-result.json", "worker.stdout.txt", "worker.stderr.txt"):
        (output / owned).unlink(missing_ok=True)
    config = {}
    rows, digest = [], hashlib.sha256(canonical([])).hexdigest()
    result = {"status": "error", "failure_category": "trusted_controller_exception",
              "checks": {}, "evidence": []}
    execution = None
    try:
        config = json.loads((tests / "grader_config.json").read_text(encoding="utf-8"))
        if config["task_version"] != VERSION or config["grader_version"] != VERSION:
            raise ValueError("grader configuration version mismatch")
        if not isinstance(config["task_id"], str) or config["skill"] not in ("loc", "edit", "testgen", "repro", "review"):
            raise ValueError("invalid trusted task identity")
        repo = Path(os.environ.get("BENCH_REPO_ROOT", "/app/repo"))
        app = Path(os.environ.get("BENCH_APP_ROOT", "/app"))
        rows, digest = submission_manifest(repo, app, config["skill"])
        budget = float(os.environ.get("BENCH_GRADER_TIMEOUT_SEC", config["worker_timeout_sec"]))
        limit = int(os.environ.get("BENCH_GRADER_OUTPUT_BYTES", "1048576"))
        if not 0 < budget <= 3600 or not 1024 <= limit <= 16777216:
            raise ValueError("invalid trusted worker resource bounds")
        with tempfile.TemporaryDirectory(prefix="verdict-v2-", dir=native_temporary_root()) as raw:
            control = Path(raw).resolve()
            result_path = control / "worker-result.json"
            env = child_environment(control)
            env["BENCH_TESTS_ROOT"] = str(tests)
            execution = run_capped(
                [sys.executable, "-B", str(Path(__file__).resolve()), "--worker",
                 "--tests-root", str(tests), "--control", str(control),
                 "--worker-result", str(result_path)],
                cwd=control, env=env, timeout_sec=budget, output_limit_bytes=limit)
            atomic_bytes(output / "worker.stdout.txt", execution["stdout"].encode("utf-8"))
            atomic_bytes(output / "worker.stderr.txt", execution["stderr"].encode("utf-8"))
            if result_path.is_file():
                if result_path.stat().st_size > 4 * 1048576:
                    raise ValueError("trusted worker report exceeds limit")
                # Temporary native workspace may now be removed; preserve the
                # raw trusted report (including nested public-runner evidence).
                atomic_bytes(output / "worker-result.json", result_path.read_bytes())
            if execution["termination"]:
                result = {"status": "error", "failure_category": "grader_" + execution["termination"],
                          "checks": {"execution": execution}, "evidence": []}
            elif not result_path.is_file():
                result = {"status": "error", "failure_category": "missing_worker_result",
                          "checks": {"worker_returncode": execution["returncode"]}, "evidence": []}
            else:
                result = json.loads(result_path.read_text(encoding="utf-8"))
                expected = {"pass": 0, "fail": 1, "error": 2}.get(result.get("status"))
                if expected is None or execution["returncode"] != expected:
                    raise ValueError("worker status/exit-code disagreement")
            result.setdefault("checks", {})["controller"] = {
                "worker_timeout_sec": budget, "output_limit_bytes": limit,
                "worker_returncode": execution["returncode"],
                "captured_bytes": execution["captured_bytes"],
                "observed_output_bytes": execution["observed_output_bytes"],
                "temporary_storage": "native_private",
                "temporary_parent": str(native_temporary_root())}
    except InvalidSubmission as exc:
        result = {"status": "fail", "failure_category":
                  "invalid_resource_submission" if isinstance(exc, InvalidResourceSubmission) else "invalid_submission",
                  "checks": {"detail": str(exc)}, "evidence": []}
    except BaseException as exc:
        result = {"status": "error", "failure_category": "trusted_controller_exception",
                  "checks": {"exception_type": type(exc).__name__, "detail": str(exc)[-4000:]},
                  "evidence": []}
    verdict = {
        "schema_version": 2, "task_id": config.get("task_id"),
        "task_version": config.get("task_version", VERSION), "grader_version": VERSION,
        "status": result["status"],
        "artifact_correct": {"pass": 1, "fail": 0, "error": None}[result["status"]],
        "failure_category": result["failure_category"],
        "submission_digest": digest, "submission_manifest": rows,
        "elapsed_sec": round(time.monotonic() - started, 6),
        "checks": result.get("checks", {}), "evidence": result.get("evidence", [])}
    if "runtime" in result:
        verdict["runtime"] = result["runtime"]
    atomic_json(output / "verdict.json", verdict)
    if verdict["status"] in ("pass", "fail"):
        atomic_bytes(output / "reward.txt", (str(verdict["artifact_correct"]) + "\n").encode())
    print(json.dumps({"schema_version": 2, "task_id": verdict["task_id"],
                      "status": verdict["status"], "failure_category": verdict["failure_category"]}))
    return {"pass": 0, "fail": 1, "error": 2}[verdict["status"]]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--worker", action="store_true")
    parser.add_argument("--public-worker", action="store_true")
    parser.add_argument("--tests-root", type=Path)
    parser.add_argument("--repo-root", type=Path)
    parser.add_argument("--control", type=Path)
    parser.add_argument("--worker-result", type=Path)
    args = parser.parse_args()
    tests = (args.tests_root or Path(os.environ.get("BENCH_TESTS_ROOT", Path(__file__).parent))).resolve()
    if args.worker and args.public_worker:
        parser.error("worker modes are mutually exclusive")
    if args.public_worker:
        if args.repo_root is None or args.control is None or args.worker_result is None:
            parser.error("public worker requires trusted repo, control and result paths")
        return public_worker(args.repo_root.resolve(), args.control.resolve(), args.worker_result.resolve())
    if args.worker:
        if args.control is None or args.worker_result is None:
            parser.error("worker requires trusted control and result paths")
        return worker(tests, args.control.resolve(), args.worker_result.resolve())
    return controller(tests)


if __name__ == "__main__":
    raise SystemExit(main())
