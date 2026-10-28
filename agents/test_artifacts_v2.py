import base64
import contextlib
import copy
import hashlib
import io
import json
import os

import pytest

from agents.artifacts_v2 import (
    CaptureLimits,
    OFFICIAL_TASKS,
    artifact_policy,
    capture_script,
    save_capture,
    validate_capture,
)
from agents.protocol_v2 import HARNESS_VERSION


TASK = "review-mean-wrong"


def payload(task_id=TASK, *, missing=False):
    policy = artifact_policy(task_id)
    content = {"repo/service.py": b"def handle(data): return data\n"}
    if policy["root_file"] and not missing:
        content[policy["root_file"]] = b"{}\n"
    if policy["test_submission"]:
        content["repo/tests/test_generated.py"] = b"def test_ok(): assert 1\n"
    files = []
    for name, data in content.items():
        role = (
            "submission"
            if name == policy["root_file"]
            or policy["skill"] == "edit"
            or name.startswith("repo/tests/")
            else "context"
        )
        files.append(
            {
                "path": name,
                "size": len(data),
                "mode": 0o644,
                "role": role,
                "sha256": hashlib.sha256(data).hexdigest(),
                "data_b64": base64.b64encode(data).decode(),
            }
        )
    return {
        "schema_version": 2,
        "harness_version": HARNESS_VERSION,
        "task_id": task_id,
        "status": "incomplete" if missing else "complete",
        "files": files,
        "missing": [policy["root_file"]] if missing else [],
        "issues": [],
        "atomic": False,
        "final_state_verified": False,
        "limits": CaptureLimits().__dict__,
        "total_bytes": sum(row["size"] for row in files),
    }


@pytest.mark.parametrize("task_id", sorted(OFFICIAL_TASKS))
def test_every_official_task_has_a_bounded_policy(task_id):
    manifest, decoded = validate_capture(payload(task_id), task_id)
    assert manifest["status"] == "complete" and "repo/service.py" in decoded
    assert manifest["atomic"] is False and manifest["final_state_verified"] is False


@pytest.mark.parametrize(
    "task_id", ("review-mutates-rank", "../edit-slugify", "made-up", None)
)
def test_development_unknown_or_unsafe_tasks_rejected(task_id):
    with pytest.raises(ValueError):
        artifact_policy(task_id)


def test_complete_capture_written_with_manifest_and_hashes(tmp_path):
    manifest, decoded = validate_capture(payload(), TASK)
    sha = save_capture(tmp_path / "artifacts", manifest, decoded)
    raw = (tmp_path / "artifacts/manifest.json").read_bytes()
    assert hashlib.sha256(raw).hexdigest() == sha
    assert (tmp_path / "artifacts/review.json").read_bytes() == b"{}\n"
    assert "data_b64" not in json.loads(raw)["files"][0]


def test_missing_submission_is_incomplete_not_a_forged_success():
    manifest, decoded = validate_capture(payload(missing=True), TASK)
    assert manifest["status"] == "incomplete" and "review.json" in manifest["missing"]
    forged = payload(missing=True)
    forged.update(status="complete", missing=[])
    with pytest.raises(ValueError, match="completeness"):
        validate_capture(forged, TASK)


@pytest.mark.parametrize(
    "name",
    (
        "../escape",
        "/absolute",
        "repo/../escape",
        "repo/a\\b",
        "repo/.env",
        "repo/.ssh/key",
        "other.txt",
    ),
)
def test_unsafe_sensitive_and_non_allowlisted_paths_rejected(name):
    value = payload()
    value["files"][0]["path"] = name
    with pytest.raises(ValueError):
        validate_capture(value, TASK)


def test_bad_hash_size_duplicate_and_atomic_claim_rejected():
    for mutate in (
        lambda value: value["files"][0].update(sha256="0" * 64),
        lambda value: value["files"][0].update(size=0),
        lambda value: value["files"].append(copy.deepcopy(value["files"][0])),
        lambda value: value.update(atomic=True),
        lambda value: value.update(final_state_verified=True),
    ):
        value = payload()
        mutate(value)
        with pytest.raises(ValueError):
            validate_capture(value, TASK)


def run_capture_on_fixture(app, *, limits=None):
    script = capture_script(TASK, limits).replace(
        "root = Path('/app')", "root = Path(" + repr(str(app)) + ")"
    )
    output = io.StringIO()
    with contextlib.redirect_stdout(output):
        exec(compile(script, "<capture-fixture>", "exec"), {})
    return json.loads(output.getvalue())


def test_real_capture_omits_credentials_and_caches_and_marks_incomplete(tmp_path):
    app = tmp_path / "app"
    repo = app / "repo"
    repo.mkdir(parents=True)
    (repo / "service.py").write_text("value = 1\n", encoding="utf-8")
    (repo / ".env").write_text("SECRET=do-not-archive", encoding="utf-8")
    cache = repo / ".pytest_cache"
    cache.mkdir()
    (cache / "data").write_bytes(b"\xff")
    (app / "review.json").write_text("{}", encoding="utf-8")
    value = run_capture_on_fixture(app)
    manifest, decoded = validate_capture(value, TASK)
    assert manifest["status"] == "incomplete"
    assert set(decoded) == {"repo/service.py", "review.json"}
    assert "do-not-archive" not in json.dumps(value)


def test_real_capture_caps_file_bytes_and_reports_omission(tmp_path):
    app = tmp_path / "app"
    repo = app / "repo"
    repo.mkdir(parents=True)
    (repo / "large.py").write_bytes(b"x" * 50)
    (app / "review.json").write_text("{}", encoding="utf-8")
    limits = CaptureLimits(max_files=4, max_file_bytes=16, max_total_bytes=32)
    value = run_capture_on_fixture(app, limits=limits)
    manifest, decoded = validate_capture(value, TASK, limits)
    assert manifest["status"] == "incomplete" and "repo/large.py" not in decoded
    assert any(item["reason"] == "size_limit" for item in manifest["issues"])


def test_real_capture_does_not_follow_symlink(tmp_path):
    app = tmp_path / "app"
    repo = app / "repo"
    repo.mkdir(parents=True)
    (repo / "service.py").write_text("value = 1\n", encoding="utf-8")
    outside = tmp_path / "secret.txt"
    outside.write_text("not-allowed", encoding="utf-8")
    try:
        (repo / "leak.py").symlink_to(outside)
    except (OSError, NotImplementedError):
        pytest.skip("host does not grant symlink creation")
    (app / "review.json").write_text("{}", encoding="utf-8")
    manifest, decoded = validate_capture(run_capture_on_fixture(app), TASK)
    assert manifest["status"] == "incomplete" and "repo/leak.py" not in decoded


@pytest.mark.parametrize("limits", ((0, 1, 1), (True, 1, 1), (1, -1, 1)))
def test_invalid_limits(limits):
    with pytest.raises(ValueError):
        CaptureLimits(*limits)


@pytest.mark.parametrize(
    "limits", (CaptureLimits(1, 100, 100), CaptureLimits(20, 100, 10))
)
def test_file_count_and_total_byte_caps_are_not_silent(tmp_path, limits):
    app = tmp_path / "app"
    repo = app / "repo"
    repo.mkdir(parents=True)
    for name in ("first.py", "second.py"):
        (repo / name).write_bytes(b"12345678")
    (app / "review.json").write_text("{}", encoding="utf-8")
    manifest, decoded = validate_capture(
        run_capture_on_fixture(app, limits=limits), TASK, limits
    )
    assert manifest["status"] == "incomplete" and any(
        row["reason"] == "size_limit" for row in manifest["issues"]
    )
    assert (
        len(decoded) <= limits.max_files
        and sum(map(len, decoded.values())) <= limits.max_total_bytes
    )


def test_oversized_encoding_is_rejected_before_decoding():
    value = payload()
    value["files"][0]["data_b64"] = "A" * (
        4 * ((CaptureLimits().max_file_bytes + 2) // 3) + 1
    )
    with pytest.raises(ValueError, match="encoded"):
        validate_capture(value, TASK)


def test_write_atomic_retries_windows_target_lock(tmp_path, monkeypatch):
    """A briefly-held destination (winerror 5/32/33) must not kill the trial."""
    if os.name != "nt":
        pytest.skip("Windows target-lock retry contract")
    import agents.artifacts_v2 as artifacts_v2

    real_replace = os.replace
    failures = {"count": 0}

    def flaky_replace(source, destination):
        if failures["count"] < 2:
            failures["count"] += 1
            error = PermissionError("destination locked")
            error.winerror = 5
            raise error
        return real_replace(source, destination)

    monkeypatch.setattr(artifacts_v2.os, "replace", flaky_replace)
    target = tmp_path / "compact-shell-v2.json"
    digest = artifacts_v2.write_json_atomic(target, {"a": 1})
    assert failures["count"] == 2
    assert json.loads(target.read_text(encoding="utf-8")) == {"a": 1}
    assert len(digest) == 64
    assert not list(tmp_path.glob("*.tmp"))


def test_write_atomic_raises_unrelated_permission_error(tmp_path, monkeypatch):
    """Permission errors without a Windows sharing winerror are not retried."""
    import agents.artifacts_v2 as artifacts_v2

    def refused(source, destination):
        raise PermissionError("filesystem refusal")

    monkeypatch.setattr(artifacts_v2.os, "replace", refused)
    target = tmp_path / "compact-shell-v2.json"
    with pytest.raises(PermissionError):
        artifacts_v2.write_json_atomic(target, {"a": 1})
    assert not target.exists()
