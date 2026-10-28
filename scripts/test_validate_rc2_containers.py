"""Offline runner contracts: no real Docker, model call or cloud backend."""

from __future__ import annotations

import json
from pathlib import Path
import subprocess
import sys
from types import SimpleNamespace
from unittest.mock import patch

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))
import validate_rc2_containers as runner
import validate_v2_containers as legacy
from test_rc2_pipeline import workspace as _real_workspace_fixture


IMAGE_A = "sha256:" + "a" * 64
IMAGE_B = "sha256:" + "b" * 64


@pytest.fixture
def real_workspace(tmp_path, monkeypatch):
    return _real_workspace_fixture.__wrapped__(tmp_path, monkeypatch)


@pytest.fixture
def root(tmp_path, monkeypatch):
    project = tmp_path / "repo"
    (project / "experiments/smallowbench-v2").mkdir(parents=True)
    monkeypatch.setattr(runner, "ROOT", project)
    # Runner tests use arbitrarily long pytest fixture paths; the actual path
    # guard has its own platform-aware test suite and is checked below by API.
    monkeypatch.setattr(
        runner, "validate_run_paths", lambda *args, **kwargs: {"checked": True}
    )
    return project


def fake_profile(root):
    return {
        "repository_root": str(root),
        "task_root": str(root / "task-banks/rc2/tasks"),
        "harbor_runtime": {"source_tree_sha256": "c" * 64},
        "profile_sha256": "d" * 64,
        "component_versions": {
            "task": "2.0.0-rc.2",
            "grader": "2.0.0-rc.2",
            "harness": "2.0.0-rc.1",
        },
        "task_specs": {task: {"normalized_sha256": "e" * 64} for task in runner.TASKS},
    }


def test_default_is_offline_fixed_ten_slots_and_does_not_mutate_rc1(
    root, monkeypatch, capsys
):
    original_root, original_version = legacy.ROOT, legacy.VERSION
    profile = fake_profile(root)
    monkeypatch.setattr(
        runner,
        "pipeline",
        lambda: SimpleNamespace(
            load_profile=lambda: profile, validate_profile=lambda value: None
        ),
    )
    monkeypatch.setattr(
        runner,
        "docker_status",
        lambda: pytest.fail("default plan must not probe Docker"),
    )
    monkeypatch.setattr(
        runner, "execute", lambda *args, **kwargs: pytest.fail("no execution")
    )
    destination = root / "experiments/smallowbench-v2/r2smk"
    assert runner.main(["--directory", str(destination)]) == 0
    plan = json.loads(capsys.readouterr().out)
    assert plan["tasks"] == list(runner.TASKS)
    assert plan["oracle_nop_slots"] == 10
    assert plan["execution_started"] is False
    assert plan["model_calls"] == 0
    assert plan["runtime_network_mode"] == "none"
    assert plan["build_network_mode"] == "none"
    assert not destination.exists()
    assert (legacy.ROOT, legacy.VERSION) == (original_root, original_version)


def test_check_runtime_is_only_a_read_probe(root, monkeypatch, capsys):
    profile = fake_profile(root)
    monkeypatch.setattr(
        runner,
        "pipeline",
        lambda: SimpleNamespace(
            load_profile=lambda: profile, validate_profile=lambda value: None
        ),
    )
    calls = []
    monkeypatch.setattr(
        runner, "docker_status", lambda: calls.append("probe") or {"available": False}
    )
    destination = root / "experiments/smallowbench-v2/r2smk"
    assert runner.main(["--directory", str(destination), "--check-runtime"]) == 0
    assert calls == ["probe"]
    assert json.loads(capsys.readouterr().out)["runtime"] == {"available": False}
    assert not destination.exists()


@pytest.mark.parametrize(
    "args",
    [
        ["--tasks", "edit-clip"],
        ["--model", "anything"],
        ["--execute", "--check-runtime"],
    ],
)
def test_cli_cannot_expand_tasks_select_models_or_mix_modes(args):
    with pytest.raises(SystemExit):
        runner.main(args)


def test_directory_admission_requires_new_short_exact_child(root):
    allowed = root / "experiments/smallowbench-v2"
    for bad in (
        allowed,
        root / "elsewhere",
        allowed / "too-long-dir",
        allowed / "nested/x",
    ):
        with pytest.raises(ValueError):
            runner.admit_directory(bad, root / "task-banks/rc2/tasks")
    existing = allowed / "old"
    existing.mkdir()
    (existing / "STOP").write_text("immutable", encoding="utf-8")
    with pytest.raises(ValueError):
        runner.admit_directory(existing, root / "task-banks/rc2/tasks")
    assert (existing / "STOP").read_text(encoding="utf-8") == "immutable"


def test_directory_admission_supplies_actual_candidate_to_path_guard(root, monkeypatch):
    calls = []
    monkeypatch.setattr(
        runner,
        "validate_run_paths",
        lambda *args, **kwargs: calls.append((args, kwargs)) or {"checked": True},
    )
    target = root / "experiments/smallowbench-v2/r2smk"
    task_root = root / "task-banks/rc2/tasks"
    runner.admit_directory(target, task_root)
    assert calls[0][0] == (target, runner.TASKS)
    assert calls[0][1] == {"mode": "oracle_nop", "task_root": task_root}


def test_historical_stop_hashes_are_never_released(root):
    stop = root / "experiments/smallowbench-v2/old/STOP"
    stop.parent.mkdir()
    stop.write_bytes(b"old-budget-stop")
    receipts = runner.stop_receipts()
    runner.validate_stops(receipts)
    assert stop.read_bytes() == b"old-budget-stop"
    stop.write_bytes(b"changed")
    with pytest.raises(ValueError, match="historical STOP changed"):
        runner.validate_stops(receipts)


@pytest.mark.parametrize("allow,network", [(False, "none"), (True, "default")])
def test_build_networking_requires_explicit_option(
    tmp_path, monkeypatch, allow, network
):
    seen = []
    (tmp_path / "Dockerfile").write_text("FROM ubuntu:24.04\n", encoding="utf-8")
    monkeypatch.setattr(
        runner,
        "_docker_read",
        lambda args: subprocess.CompletedProcess(args, 0, IMAGE_A, ""),
    )

    def checked(command, log, *, timeout):
        seen.append(command)
        Path(command[command.index("--iidfile") + 1]).write_text(
            IMAGE_A, encoding="utf-8"
        )

    monkeypatch.setattr(runner, "checked", checked)
    assert (
        runner.build_image(tmp_path, tmp_path, "agent", allow_build_network=allow)
        == IMAGE_A
    )
    assert seen[0][:3] == ["docker", "build", "--pull=false"]
    assert seen[0][seen[0].index("--network") + 1] == network


def test_build_rejects_mutable_or_malformed_result(tmp_path, monkeypatch):
    (tmp_path / "Dockerfile").write_text("FROM ubuntu:24.04\n", encoding="utf-8")
    monkeypatch.setattr(
        runner,
        "_docker_read",
        lambda args: subprocess.CompletedProcess(args, 0, IMAGE_A, ""),
    )

    def checked(command, log, *, timeout):
        Path(command[command.index("--iidfile") + 1]).write_text(
            "ubuntu:latest", encoding="utf-8"
        )

    monkeypatch.setattr(runner, "checked", checked)
    with pytest.raises(ValueError, match="immutable image"):
        runner.build_image(tmp_path, tmp_path, "agent")


def test_missing_local_base_cannot_implicitly_pull(tmp_path, monkeypatch):
    (tmp_path / "Dockerfile").write_text("FROM ubuntu:24.04\n", encoding="utf-8")
    monkeypatch.setattr(
        runner,
        "_docker_read",
        lambda args: subprocess.CompletedProcess(args, 1, "", "not cached"),
    )
    monkeypatch.setattr(
        runner, "checked", lambda *args, **kwargs: pytest.fail("must not start build")
    )
    with pytest.raises(RuntimeError, match="refusing implicit pull"):
        runner.build_image(tmp_path, tmp_path, "agent")
    receipt = json.loads((tmp_path / "agent-base.json").read_text(encoding="utf-8"))
    assert receipt["present_locally"] is False


def test_build_rejects_unexpected_dockerfile_before_any_docker(tmp_path, monkeypatch):
    (tmp_path / "Dockerfile").write_text(
        "FROM some-unpinned-other-image\n", encoding="utf-8"
    )
    monkeypatch.setattr(
        runner,
        "_docker_read",
        lambda *args: pytest.fail("no Docker for invalid recipe"),
    )
    with pytest.raises(ValueError, match="frozen single-stage"):
        runner.build_image(tmp_path, tmp_path, "agent")


def test_docker_reads_hide_windows_console_and_strip_secrets(monkeypatch):
    monkeypatch.setenv("OPENROUTER_API_KEY", "not-forwarded")
    with patch.object(
        runner.subprocess,
        "run",
        return_value=subprocess.CompletedProcess([], 0, "", ""),
    ) as run:
        runner._docker_read(["image", "inspect", IMAGE_A])
    assert run.call_args.args[0] == ["docker", "image", "inspect", IMAGE_A]
    assert "OPENROUTER_API_KEY" not in run.call_args.kwargs["env"]
    assert run.call_args.kwargs["creationflags"] == (
        0x08000000 if runner.os.name == "nt" else 0
    )


def test_cleanup_only_checks_this_runs_exact_ids_or_sessions(tmp_path):
    session = "edit-clip__ABC1234__env"
    rows = [
        {
            "static_network_isolation_evidence": [
                {"session_id": session, "container_id": "a" * 64}
            ]
        }
    ]
    inventory = [
        {"ID": "a" * 64, "Names": "owned", "Labels": "other=value"},
        {
            "ID": "b" * 64,
            "Names": "owned-by-label",
            "Labels": "com.docker.compose.project=" + session.lower(),
        },
        {
            "ID": "c" * 64,
            "Names": "task-redis",
            "Labels": "com.docker.compose.project=unrelated",
        },
    ]
    result = runner.cleanup_check(tmp_path, rows, inventory)
    assert [row["container_id"] for row in result["remaining_containers"]] == [
        "a" * 64,
        "b" * 64,
    ]
    assert not result["zero_residual"]


def test_cleanup_discovers_partially_started_trial_without_network_proof(tmp_path):
    task = runner.TASKS[0]
    (tmp_path / "jobs" / f"v2-oracle-{task}" / f"{task}__ABC1234").mkdir(parents=True)
    inventory = [
        {
            "ID": "a" * 64,
            "Labels": f"com.docker.compose.project={task}__abc1234__verifier__trial",
        }
    ]
    assert not runner.cleanup_check(tmp_path, [], inventory)["zero_residual"]


def test_cleanup_also_finds_version_probe_after_docker_client_timeout(tmp_path):
    inventory = [
        {
            "ID": "a" * 64,
            "Names": "version-probe-leftover",
            "Labels": runner.PROBE_LABEL_KEY + "=" + runner.probe_label(tmp_path),
        }
    ]
    assert not runner.cleanup_check(tmp_path, [], inventory)["zero_residual"]


def test_version_probe_has_exact_run_label_and_preserved_launch_evidence(
    tmp_path, monkeypatch
):
    output = tmp_path / "images" / "edit-clip" / "agent-runtime.json"
    output.parent.mkdir(parents=True)
    seen = []

    def checked(command, log, *, timeout):
        seen.append(command)
        log.write_text(
            json.dumps({"python": "synthetic", "pytest": "synthetic"}), encoding="utf-8"
        )

    monkeypatch.setattr(runner, "checked", checked)
    assert runner.image_versions(IMAGE_A, output)["python"] == "synthetic"
    command = seen[0]
    assert command[command.index("--network") + 1] == "none"
    assert command[
        command.index("--label") + 1
    ] == runner.PROBE_LABEL_KEY + "=" + runner.probe_label(tmp_path)
    launch = json.loads(
        output.with_name("agent-runtime-launch.json").read_text(encoding="utf-8")
    )
    assert launch["command"] == command
    assert launch["image"] == IMAGE_A


def test_version_probe_failure_keeps_launch_receipt_without_automatic_global_cleanup(
    tmp_path, monkeypatch
):
    output = tmp_path / "images" / "edit-clip" / "grader-runtime.json"
    output.parent.mkdir(parents=True)

    def checked(command, log, *, timeout):
        raise subprocess.TimeoutExpired(command, timeout)

    monkeypatch.setattr(runner, "checked", checked)
    with pytest.raises(subprocess.TimeoutExpired):
        runner.image_versions(IMAGE_A, output)
    assert output.with_name("grader-runtime-launch.json").is_file()


def test_runtime_proof_and_native_tmp_are_required():
    row = {
        "static_network_isolation_evidence": [{"verified": True}, {"verified": True}],
        "verdict": {
            "checks": {
                "controller": {
                    "temporary_storage": "native_private",
                    "temporary_parent": "/tmp",
                }
            }
        },
    }
    runner.inspect_delivery_runtime(row)
    assert row["native_temporary_storage_validated"]
    row["verdict"]["checks"]["controller"]["temporary_parent"] = "/logs/verifier/work"
    with pytest.raises(ValueError, match="native /tmp"):
        runner.inspect_delivery_runtime(row)
    row["static_network_isolation_evidence"] = []
    with pytest.raises(ValueError, match="network-none"):
        runner.inspect_delivery_runtime(row)


@pytest.fixture
def fake_execution(root, monkeypatch):
    profile = fake_profile(root)
    calls = []

    def stage(profile, task, directory, agent, grader):
        target = directory / "staged-tasks" / task
        target.mkdir(parents=True)
        return target

    def config(profile, task, mode, staged, directory):
        result = legacy.make_config(task, mode, staged, directory)
        result["environment"]["delete"] = False
        return result

    def inspect(profile, task, mode, directory, agent, grader, *, session_state):
        calls.append((task, mode))
        index = len(calls)
        return {
            "task": task,
            "agent": mode,
            "task_sha256": "e" * 64,
            "infrastructure_ok": True,
            "expected_result_matched": True,
            "verdict": {
                "checks": {
                    "controller": {
                        "temporary_storage": "native_private",
                        "temporary_parent": "/tmp",
                    }
                }
            },
            "static_network_isolation_evidence": [
                {
                    "verified": True,
                    "session_id": f"{task}__ABC1234__env",
                    "container_id": f"{index:064x}",
                },
                {
                    "verified": True,
                    "session_id": f"{task}__ABC1234__verifier__trial",
                    "container_id": f"{index + 20:064x}",
                },
            ],
        }

    def summarize(profile, tasks, rows, environment):
        return {
            "diagnostic_complete": len(rows) == 10,
            "diagnostic_success": len(rows) == 10
            and all(row["expected_result_matched"] for row in rows),
            "all_passed": False,
            "container_validated": False,
            "full_bank_coverage": False,
            "release_gate_passed": False,
            "rows": rows,
            "environment": environment,
        }

    core = SimpleNamespace(
        load_profile=lambda: profile,
        validate_profile=lambda value: None,
        stage_task=stage,
        make_config=config,
        inspect_trial=inspect,
        summarize=summarize,
    )
    monkeypatch.setattr(runner, "pipeline", lambda: core)
    monkeypatch.setattr(
        runner, "docker_status", lambda: {"available": True, "os_type": "linux"}
    )
    harbor = root / "harbor.exe"
    harbor.touch()
    monkeypatch.setattr(runner, "HARBOR", harbor)

    def inventory(path):
        runner.write_new(path, {"containers": []})
        return []

    monkeypatch.setattr(runner, "container_inventory", inventory)
    monkeypatch.setattr(
        runner,
        "cached_agent_image",
        lambda task, task_root, output: (None, {"reused": False}),
    )
    monkeypatch.setattr(
        runner,
        "build_image",
        lambda context, output, name, **kwargs: IMAGE_A if name == "agent" else IMAGE_B,
    )
    monkeypatch.setattr(
        runner,
        "image_versions",
        lambda image, output: {"python": "test", "pytest": "test"},
    )
    monkeypatch.setattr(runner, "checked", lambda command, log, **kwargs: None)
    return core, calls, root / "experiments/smallowbench-v2/r2smk"


def test_execute_is_exactly_ten_serial_model_free_slots(fake_execution):
    core, calls, destination = fake_execution
    assert runner.execute(destination) == 0
    assert calls == [(task, mode) for task in runner.TASKS for mode in runner.MODES]
    report = json.loads(
        (destination / "preflight-rc2.json").read_text(encoding="utf-8")
    )
    assert report["diagnostic_success"]
    assert not report["container_validated"]
    assert report["model_calls"] == report["cloud_sandbox_creates"] == 0
    assert report["environment"]["build_network_mode"] == "none"
    assert report["environment"]["cleanup_check"]["zero_residual"]
    for config in (destination / "configs").glob("*.json"):
        data = json.loads(config.read_text(encoding="utf-8"))
        assert data["environment"]["delete"] is False
        assert data["retry"]["max_retries"] == 0
        assert data["agents"][0]["name"] in {"oracle", "nop"}
        assert data["n_concurrent_trials"] == 1


def test_first_failed_slot_stops_without_retry_or_overwriting(fake_execution):
    core, calls, destination = fake_execution
    inspect = core.inspect_trial

    def failure(*args, **kwargs):
        row = inspect(*args, **kwargs)
        row["expected_result_matched"] = False
        return row

    core.inspect_trial = failure
    assert runner.execute(destination) == 1
    assert len(calls) == 1
    report = json.loads(
        (destination / "preflight-rc2.json").read_text(encoding="utf-8")
    )
    assert not report["diagnostic_success"]
    assert report["execution_errors"]
    assert len(list((destination / "rows").glob("*.json"))) == 1
    with pytest.raises(ValueError, match="new 1..9-character"):
        runner.execute(destination)


def test_runtime_unavailable_creates_no_run_and_never_builds(
    fake_execution, monkeypatch
):
    core, calls, destination = fake_execution
    monkeypatch.setattr(runner, "docker_status", lambda: {"available": False})
    monkeypatch.setattr(
        runner, "build_image", lambda *args, **kwargs: pytest.fail("no build")
    )
    with pytest.raises(RuntimeError, match="no container or run directory"):
        runner.execute(destination)
    assert not destination.exists()
    assert not calls


def test_source_drift_is_recorded_and_cannot_authorize_more_slots(fake_execution):
    core, calls, destination = fake_execution

    def validate(profile):
        if calls:
            raise ValueError("profile changed")

    core.validate_profile = validate
    assert runner.execute(destination) == 1
    assert len(calls) == 1
    report = json.loads(
        (destination / "preflight-rc2.json").read_text(encoding="utf-8")
    )
    assert any(
        error["type"] == "SourceOrStopDrift" for error in report["execution_errors"]
    )
    assert not report["diagnostic_success"]


def test_cached_agent_never_reuses_changed_public_readme(root, monkeypatch, tmp_path):
    task = runner.TASKS[2]
    old = root / "tasks" / task / "environment/repo"
    new = root / "task-banks/rc2/tasks" / task / "environment/repo"
    old.mkdir(parents=True)
    new.mkdir(parents=True)
    (old / "README.md").write_text("old public rules", encoding="utf-8")
    (new / "README.md").write_text("new public rules", encoding="utf-8")
    monkeypatch.setattr(
        runner,
        "_docker_read",
        lambda args: pytest.fail("changed context must not query/reuse old image"),
    )
    image, evidence = runner.cached_agent_image(
        task, root / "task-banks/rc2/tasks", tmp_path / "reuse.json"
    )
    assert image is None
    assert evidence["reason"] == "agent_context_changed"


def test_cached_agent_requires_real_image_id_and_bound_receipt(
    root, monkeypatch, tmp_path
):
    task = runner.TASKS[0]
    for base in (root / "tasks", root / "task-banks/rc2/tasks"):
        context = base / task / "environment"
        context.mkdir(parents=True)
        (context / "Dockerfile").write_text("same", encoding="utf-8")
    (root / "task-bank-v2.manifest.json").write_text("old-bank", encoding="utf-8")
    receipt = root / "experiments/smallowbench-v2/full124/preflight-v2.json"
    receipt.parent.mkdir()
    receipt.write_text(
        json.dumps(
            {
                "container_validated": True,
                "task_bank_manifest_sha256": runner.sha(
                    root / "task-bank-v2.manifest.json"
                ),
                "environment": {"image_digests": {task: IMAGE_A}},
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(
        runner,
        "_docker_read",
        lambda args: subprocess.CompletedProcess(args, 0, IMAGE_A + "\n", ""),
    )
    image, evidence = runner.cached_agent_image(
        task, root / "task-banks/rc2/tasks", tmp_path / "reuse.json"
    )
    assert image == IMAGE_A and evidence["reused"]
    monkeypatch.setattr(
        runner,
        "_docker_read",
        lambda args: subprocess.CompletedProcess(args, 0, IMAGE_B, ""),
    )
    image, evidence = runner.cached_agent_image(
        task, root / "task-banks/rc2/tasks", tmp_path / "reuse2.json"
    )
    assert image is None and not evidence["reused"]


def test_runner_report_roundtrips_real_core_validation(real_workspace, monkeypatch):
    """Synthetic raw files traverse real inspect/summarize/serialized reanalysis."""
    import rc2_pipeline as core
    from test_rc2_pipeline import raw_fixture

    root, _, profile = real_workspace
    destination = root / "experiments/smallowbench-v2/r2smk"
    proxy = SimpleNamespace(
        **{
            name: getattr(core, name)
            for name in (
                "validate_profile",
                "stage_task",
                "make_config",
                "inspect_trial",
                "summarize",
            )
        }
    )
    proxy.load_profile = lambda: profile
    monkeypatch.setattr(runner, "ROOT", root)
    monkeypatch.setattr(runner, "pipeline", lambda: proxy)
    monkeypatch.setattr(
        runner, "validate_run_paths", lambda *args, **kwargs: {"checked": True}
    )
    monkeypatch.setattr(
        runner, "docker_status", lambda: {"available": True, "os_type": "linux"}
    )
    harbor = root / "harbor.exe"
    harbor.touch()
    monkeypatch.setattr(runner, "HARBOR", harbor)
    monkeypatch.setattr(
        runner, "cached_agent_image", lambda *args: (None, {"reused": False})
    )

    def synthetic_build(context, output, name, **kwargs):
        image = "sha256:" + ("1" if name == "agent" else "2") * 64
        (output / (name + ".iid")).write_text(image, encoding="utf-8")
        return image

    monkeypatch.setattr(runner, "build_image", synthetic_build)

    def inventory(path):
        runner.write_new(path, {"containers": []})
        return []

    monkeypatch.setattr(runner, "container_inventory", inventory)
    visited = []

    def checked(command, log, **kwargs):
        if command[:2] == ["docker", "run"]:
            log.write_text(
                json.dumps({"python": "synthetic", "pytest": "synthetic"}),
                encoding="utf-8",
            )
            return
        config = json.loads(Path(command[-1]).read_text(encoding="utf-8"))
        task = Path(config["tasks"][0]["path"]).name
        mode = config["agents"][0]["name"]
        visited.append((task, mode))
        raw_fixture((root, destination, profile), task, mode, len(visited))

    monkeypatch.setattr(runner, "checked", checked)
    assert runner.execute(destination) == 0
    report_path = destination / "preflight-rc2.json"
    report = json.loads(report_path.read_text(encoding="utf-8"))
    assert report["report_sha256"] == runner.digest(
        {key: value for key, value in report.items() if key != "report_sha256"}
    )
    validated = core.validate_smoke_report(
        report_path, profile, tasks=list(runner.TASKS)
    )
    assert validated["diagnostic_success"]
    assert len(visited) == 10
    assert not validated["release_gate_passed"]
