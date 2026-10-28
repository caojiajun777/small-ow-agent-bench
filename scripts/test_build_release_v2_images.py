"""Offline contracts for release image initialization; never invoke Docker."""

from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import time
from types import SimpleNamespace

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))
import build_release_v2_images as builder

REAL_VALIDATE_RUNTIME = builder.release.validate_runtime


IMAGE_A = "sha256:" + "a" * 64
IMAGE_G = "sha256:" + "b" * 64
VERSION = {"python": "synthetic python", "pytest": "synthetic pytest"}


def write(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    if isinstance(value, (dict, list)):
        value = json.dumps(value, sort_keys=True)
    path.write_text(value, encoding="utf-8")
    return path


@pytest.fixture
def world(tmp_path, monkeypatch):
    root = tmp_path / "r"
    base = root / "experiments/smallowbench-v2"
    base.mkdir(parents=True)
    monkeypatch.setattr(builder, "ROOT", root)
    monkeypatch.setattr(builder.images, "ROOT", root)
    monkeypatch.setattr(builder, "WINDOWS_PATH_LIMIT", 10000)
    sources = {}
    for name in ("scripts/build_release_v2_images.py", "scripts/release_v2_pipeline.py", "scripts/frozen.py"):
        sources[name] = builder.sha(write(root / name, "# synthetic source\n"))
    task_root = root / "task-banks/rc2/tasks"
    specs = {}
    for task in builder.BANK_62:
        write(task_root / task / "environment/Dockerfile", "FROM ubuntu:24.04\n")
        write(task_root / task / "tests/Dockerfile", "FROM ubuntu:24.04\n")
        specs[task] = {"normalized_sha256": hashlib.sha256(task.encode()).hexdigest()}
    bank_path = write(task_root.parent / "task-bank-v2.manifest.json", {"synthetic": True})
    profile = {"schema_version": 1, "repository_root": str(root), "task_root": str(task_root),
               "task_specs": specs, "source_hashes": sources, "profile_sha256": "c" * 64,
               "bank_manifest": {"path": str(bank_path), "sha256": builder.sha(bank_path)},
               "component_versions": {"benchmark": "2.0.0-rc.2", "task": "2.0.0-rc.2",
                                      "grader": "2.0.0-rc.2", "harness": "2.0.0-rc.1"},
               "harbor_runtime": {"synthetic_offline_runtime": True}}
    frozen = base / "r2smk"
    profile_path = write(frozen / "profile.json", profile)
    environment = {"image_digests": {}, "grader_image_digests": {}, "runtime_versions": {}}
    for task in builder.PINNED_TASKS:
        environment["image_digests"][task] = IMAGE_A
        environment["grader_image_digests"][task] = IMAGE_G
        environment["runtime_versions"][task] = {role: dict(VERSION) for role in builder.ROLES}
        for role in builder.ROLES:
            write(frozen / "images" / task / (role + "-runtime.json"), VERSION)
    preflight = {"environment": environment, "synthetic_unit_fixture": True,
                 "rows": [{"directory": str(frozen)}]}
    preflight_path = write(frozen / "preflight-rc2.json", preflight)
    stop = write(base / "old/STOP", "immutable historical hold")
    monkeypatch.setattr(builder.core, "load_profile", lambda root: copy.deepcopy(profile))
    monkeypatch.setattr(builder.core, "validate_profile", lambda value: value)
    monkeypatch.setattr(builder.core, "_task_source", lambda value, task: task_root / task)
    monkeypatch.setattr(builder.core, "validate_smoke_report", lambda path, profile, tasks: copy.deepcopy(preflight))
    monkeypatch.setattr(builder.release, "source_bindings", lambda root: dict(sources))
    monkeypatch.setattr(builder.release, "validate_runtime", lambda *args, **kwargs: None)
    monkeypatch.setattr(builder, "docker_status", lambda: {"available": True, "os_type": "linux"})
    commands, builds, probes, inventories = [], [], [], []
    monkeypatch.setattr(builder.images, "_docker_read", lambda command: commands.append(command) or
                        subprocess.CompletedProcess(command, 0, command[-1], ""))

    def inventory(output):
        rows = [{"ID": "e" * 64, "Names": "unrelated", "Labels": "owner=someone-else"}]
        inventories.append(output.name)
        builder.write_new(output, {"containers": rows})
        return rows

    monkeypatch.setattr(builder.images, "container_inventory", inventory)

    def cached(task, task_root, output):
        evidence = {"reused": True, "source": "synthetic_byte_identical_rc1", "actual_image": IMAGE_A}
        builder.write_new(output, evidence)
        return IMAGE_A, evidence

    monkeypatch.setattr(builder.images, "cached_agent_image", cached)

    def build(context, local, role, *, allow_build_network):
        builds.append((context.parent.name, role, allow_build_network, local))
        image = IMAGE_A if role == "agent" else IMAGE_G
        builder.write_new(local / (role + "-base.json"), {"run_network": "default" if allow_build_network else "none"})
        write(local / (role + "-build.log"), "synthetic offline build")
        write(local / (role + ".iid"), image)
        return image

    monkeypatch.setattr(builder.images, "build_image", build)

    def versions(image, output):
        role = output.stem.split("-", 1)[0]
        probes.append((output.parent.name, role))
        label = builder.images.probe_label(output.parents[2])
        name = "r2p-" + label[:10] + "-" + output.parent.name[:25] + "-" + role
        command = ["docker", "run", "--rm", "--name", name,
                   "--label", builder.images.PROBE_LABEL_KEY + "=" + label,
                   "--network", "none", "--read-only", "--cap-drop", "ALL",
                   "--security-opt", "no-new-privileges", "--pids-limit", "64",
                   "--cpus", "1", "--memory", "2g", image, "python3", "-c",
                   builder.core.VERSION_PROBE_CODE]
        builder.write_new(output.with_name(output.stem + "-launch.json"), {
            "image": image, "container_name": name, "command": command,
            "label_key": builder.images.PROBE_LABEL_KEY, "label_value": label, "network_mode": "none"})
        builder.write_new(output, VERSION)
        return dict(VERSION)

    monkeypatch.setattr(builder.images, "image_versions", versions)
    return SimpleNamespace(root=root, output=base / "im2", profile=profile, profile_path=profile_path,
                           preflight=preflight, preflight_path=preflight_path, bank_path=bank_path,
                           stop=stop, sources=sources, commands=commands, builds=builds,
                           probes=probes, inventories=inventories)


def test_default_plan_is_read_only_and_has_no_evaluation_scope(world, monkeypatch, capsys):
    monkeypatch.setattr(builder, "docker_status", lambda: pytest.fail("offline plan invoked Docker"))
    monkeypatch.setattr(builder.images, "_docker_read", lambda *args: pytest.fail("offline plan invoked Docker"))
    assert builder.main(["--output", str(world.output), "--workers", "4"]) == 0
    plan = json.loads(capsys.readouterr().out)
    assert plan["tasks"] == list(builder.BANK_62)
    assert plan["pinned_existing_rc2_tasks"] == list(builder.PINNED_TASKS)
    assert plan["execution_started"] is False
    assert plan["model_calls"] == plan["task_evaluation_runs"] == 0
    assert plan["runtime_network_mode"] == plan["build_network_mode"] == "none"
    assert not world.output.exists()
    assert not world.commands and not world.builds and not world.probes


@pytest.mark.parametrize("args", [["--workers", "0"], ["--workers", "5"], ["--model", "anything"], ["--tasks", "edit-clip"]])
def test_cli_rejects_expansion_or_unbounded_workers(args):
    with pytest.raises(SystemExit):
        builder.main(args)


def test_output_never_overwrites_existing_or_leaves_experiment_namespace(world):
    world.output.mkdir()
    with pytest.raises(ValueError, match="no overwrite"):
        builder.admit_directory(world.output)
    for path in (world.root / "elsewhere", world.output / "nested", world.output.parent / "too-long-name"):
        with pytest.raises(ValueError):
            builder.admit_directory(path)


def test_invalid_core_profile_refuses_before_docker_or_new_directory(world, monkeypatch):
    write(world.profile_path, {"changed": True})
    monkeypatch.setattr(builder, "docker_status", lambda: pytest.fail("invalid profile reached Docker"))
    with pytest.raises(ValueError, match="core profile"):
        builder.execute(world.output)
    assert not world.output.exists()


def test_unavailable_runtime_has_no_output_directory(world, monkeypatch):
    monkeypatch.setattr(builder, "docker_status", lambda: {"available": False})
    with pytest.raises(RuntimeError, match="unavailable"):
        builder.execute(world.output)
    assert not world.output.exists()


@pytest.mark.parametrize("allow", [False, True])
def test_62_image_contract_reuses_five_pins_and_binds_all_receipts(world, allow):
    old_stop = world.stop.read_bytes()
    assert builder.execute(world.output, workers=4, allow_build_network=allow) == 0
    runtime = json.loads((world.output / "runtime.json").read_text(encoding="utf-8"))
    assert runtime["kind"] == "smallowbench_v2_release_runtime"
    assert runtime["schema_version"] == 1
    assert runtime["task_root"] == world.profile["task_root"]
    assert runtime["task_bank_manifest_sha256"] == builder.sha(world.bank_path)
    assert runtime["task_sha256"] == {task: spec["normalized_sha256"] for task, spec in world.profile["task_specs"].items()}
    env = runtime["environment"]
    for key in ("image_digests", "grader_image_digests", "runtime_versions"):
        assert set(env[key]) == set(builder.BANK_62)
        for task in builder.PINNED_TASKS:
            assert env[key][task] == world.preflight["environment"][key][task]
    assert len(world.builds) == 57 and all(role == "grader" for _, role, _, _ in world.builds)
    assert all(network is allow for _, _, network, _ in world.builds)
    assert len(world.probes) == 114 and not set(builder.PINNED_TASKS).intersection(task for task, _ in world.probes)
    assert len(world.commands) == 124 and all(command[:2] == ["image", "inspect"] for command in world.commands)
    assert env["cleanup_check"]["zero_residual"] is True
    assert env["cleanup_check"]["preexisting_containers_preserved"] is True
    assert world.inventories == ["containers-before.json", "containers-after.json"]
    assert world.stop.read_bytes() == old_stop
    assert not (world.output / "runtime.pending.json").exists()
    assert "container_validated" not in runtime and "all_passed" not in runtime
    for relative, expected in runtime["raw_artifacts_sha256"].items():
        assert "\\" not in relative and builder.sha(world.root / relative) == expected
    for task in builder.BANK_62:
        local = world.output / "images" / task
        assert (local / "receipt.json").is_file()
        for role in builder.ROLES:
            for name in (role + ".iid", role + "-runtime.json", role + "-image-inspect.json"):
                assert (local / name).relative_to(world.root).as_posix() in runtime["raw_artifacts_sha256"]


def test_missing_rc1_cache_builds_only_the_missing_agents(world, monkeypatch):
    original = builder.images.cached_agent_image
    target = next(task for task in builder.BANK_62 if task not in builder.PINNED_TASKS)

    def cache(task, task_root, output):
        if task == target:
            evidence = {"reused": False, "reason": "exact_image_not_available_locally"}
            builder.write_new(output, evidence)
            return None, evidence
        return original(task, task_root, output)

    monkeypatch.setattr(builder.images, "cached_agent_image", cache)
    assert builder.execute(world.output) == 0
    assert [(task, role) for task, role, _, _ in world.builds if role == "agent"] == [(target, "agent")]


def test_atomic_completion_passes_real_release_runtime_contract(world, monkeypatch):
    monkeypatch.setattr(builder.core, "runtime_evidence", lambda root: world.profile["harbor_runtime"])
    monkeypatch.setattr(builder.release, "validate_runtime", REAL_VALIDATE_RUNTIME)
    assert builder.execute(world.output, workers=4) == 0
    runtime_path = world.output / "runtime.json"
    actual = REAL_VALIDATE_RUNTIME(runtime_path, world.profile["task_specs"],
                                   world.profile["bank_manifest"], world.preflight, root=world.root)
    assert actual["environment"]["cleanup_check"]["zero_residual"] is True
    assert not (world.output / "publication-failure.json").exists()


def test_missing_pinned_image_fails_without_rebuilding_or_reprobing_it(world, monkeypatch):
    monkeypatch.setattr(builder.images, "_docker_read", lambda command: subprocess.CompletedProcess(command, 1, "", "absent"))
    assert builder.execute(world.output) == 1
    assert not (world.output / "runtime.json").exists()
    assert not world.builds and not world.probes
    state = json.loads((world.output / "run-state.json").read_text(encoding="utf-8"))
    assert state["status"] == "failed" and state["execution_errors"]
    assert world.inventories[-1] == "containers-after.json"


@pytest.mark.parametrize("mutation", ["source", "candidate", "stop", "core_profile"])
def test_drift_during_build_stops_without_runtime_or_retry(world, monkeypatch, mutation):
    original = builder.images.build_image
    mutated = False

    def build(*args, **kwargs):
        nonlocal mutated
        image = original(*args, **kwargs)
        if not mutated:
            mutated = True
            path = {"source": world.root / "scripts/frozen.py", "candidate": world.bank_path,
                    "stop": world.stop, "core_profile": world.output / "core-profile.json"}[mutation]
            path.write_text("changed during synthetic build", encoding="utf-8")
        return image

    monkeypatch.setattr(builder.images, "build_image", build)
    assert builder.execute(world.output) == 1
    assert len(world.builds) == 1
    assert not (world.output / "runtime.json").exists()
    assert world.inventories[-1] == "containers-after.json"


def test_parallel_failure_does_not_schedule_more_tasks_or_retry(world, monkeypatch):
    attempted = []
    original = builder._task_images
    normal_tasks = [task for task in builder.BANK_62 if task not in builder.PINNED_TASKS]

    def fail(task, directory, profile, preflight, preflight_path, guard):
        if task in builder.PINNED_TASKS:
            return original(task, directory, profile, preflight, preflight_path, guard)
        attempted.append(task)
        (directory / "images" / task).mkdir(parents=True)
        if task == normal_tasks[0]:
            raise RuntimeError("synthetic first failure")
        time.sleep(0.03)
        guard(task)
        raise RuntimeError("already in flight")

    monkeypatch.setattr(builder, "_task_images", fail)
    assert builder.execute(world.output, workers=4) == 1
    assert set(attempted) <= set(normal_tasks[:4])
    assert len(attempted) == len(set(attempted))
    assert not (world.output / "runtime.json").exists()


def test_exact_probe_residual_blocks_completion_without_cleanup(world, monkeypatch):
    original = builder.images.container_inventory

    def inventory(output):
        rows = original(output)
        if output.name == "containers-after.json":
            rows.append({"ID": "f" * 64, "Names": "own-leftover", "Labels": builder.images.PROBE_LABEL_KEY + "=" + builder.images.probe_label(world.output)})
        return rows

    monkeypatch.setattr(builder.images, "container_inventory", inventory)
    assert builder.execute(world.output) == 1
    assert not (world.output / "runtime.json").exists()
    check = json.loads((world.output / "inventory-check.json").read_text(encoding="utf-8"))
    assert check["zero_residual"] is False
    assert len(world.commands) == 124  # inspections only; no rm/prune/delete


def test_unrelated_container_loss_blocks_completion(world, monkeypatch):
    original = builder.images.container_inventory
    monkeypatch.setattr(builder.images, "container_inventory", lambda output: [] if output.name == "containers-after.json" else original(output))
    assert builder.execute(world.output) == 1
    assert not (world.output / "runtime.json").exists()


def test_atomic_publication_never_replaces_existing_file(tmp_path):
    target = write(tmp_path / "runtime.json", "existing evidence")
    with pytest.raises(FileExistsError):
        builder._atomic_runtime(target, {"new": True})
    assert target.read_text(encoding="utf-8") == "existing evidence"


def test_publication_rechecks_source_after_pending_json_is_written(world, monkeypatch):
    original = builder._atomic_runtime

    def atomic(path, value, *, validate):
        (world.root / "scripts/frozen.py").write_text("late source drift", encoding="utf-8")
        original(path, value, validate=validate)

    monkeypatch.setattr(builder, "_atomic_runtime", atomic)
    assert builder.execute(world.output) == 1
    assert not (world.output / "runtime.json").exists()
    assert (world.output / "publication-failure.json").is_file()
