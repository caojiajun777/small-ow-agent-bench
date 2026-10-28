"""Freeze the 62 RC2 agent/grader images without evaluating any task.

The default is an offline, read-only plan. --execute creates one new short
experiment directory. Only Docker builds, immutable-image inspections and
network-none Python/pytest dependency-version probes are permitted here.
The existing five-task RC2 evidence is reused exactly, never rerun.
"""

from __future__ import annotations

import argparse
from concurrent.futures import FIRST_COMPLETED, ThreadPoolExecutor, wait
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import re
import threading

import rc2_pipeline as core
import release_v2_pipeline as release
import validate_rc2_containers as images
from prepare_rc2_candidate import BANK_62, reject_links
from validate_v2_containers import IMAGE_ID, docker_status, sha, write_new
from v2_paths import WINDOWS_PATH_LIMIT

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUTPUT = ROOT / "experiments/smallowbench-v2/im2"
DEFAULT_PROFILE = ROOT / "experiments/smallowbench-v2/r2smk/profile.json"
RUNTIME_KIND = "smallowbench_v2_release_runtime"
RECEIPT_KIND = "smallowbench_v2_image_initialization"
PINNED_TASKS = tuple(core.SMOKE_TASKS)
ROLES = ("agent", "grader")


def _json(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def _relative(path):
    path = Path(path).absolute()
    reject_links(path)
    resolved = path.resolve()
    if not resolved.is_relative_to(ROOT.resolve()) or not resolved.is_file():
        raise ValueError("image evidence must be a regular repository file")
    return resolved.relative_to(ROOT.resolve()).as_posix()


def admit_directory(directory):
    """No writes, links, existing outputs, or long predictable image paths."""
    directory = Path(directory).absolute()
    reject_links(directory)
    directory = directory.resolve()
    if (directory.parent != (ROOT / "experiments/smallowbench-v2").resolve()
            or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]{0,8}", directory.name)
            or directory.exists()):
        raise ValueError("a new 1..9-character direct experiment child is required; no overwrite")
    for task in BANK_62:
        for name in ("agent-runtime-launch.json", "grader-runtime-launch.json",
                     "agent-image-inspect.json", "grader-image-inspect.json"):
            path = directory / "images" / task / name
            if os.name == "nt" and len(str(path).encode("utf-16-le")) // 2 > WINDOWS_PATH_LIMIT:
                raise ValueError("image evidence path exceeds the Windows path budget")
    return directory


def load_inputs(profile_path=None):
    """Strictly revalidate frozen RC2 sources and original five-task evidence."""
    profile = core.load_profile(ROOT)
    core.validate_profile(profile)
    profile_path = Path(profile_path) if profile_path is not None else ROOT / "experiments/smallowbench-v2/r2smk/profile.json"
    _relative(profile_path)
    if _json(profile_path) != profile:
        raise ValueError("supplied core profile differs from the frozen RC2 profile")
    preflight_path = ROOT / "experiments/smallowbench-v2/r2smk/preflight-rc2.json"
    preflight = core.validate_smoke_report(preflight_path, profile, tasks=PINNED_TASKS)
    if set(profile["task_specs"]) != set(BANK_62) or len(profile["task_specs"]) != 62:
        raise ValueError("image initialization requires exactly the complete 62-task RC2 bank")
    source_hashes = dict(profile["source_hashes"])
    source_hashes.update(release.source_bindings(ROOT))
    for name in ("scripts/build_release_v2_images.py", "scripts/release_v2_pipeline.py"):
        source_hashes[name] = sha(ROOT / name)
    return profile, preflight, profile_path, preflight_path, source_hashes


def _validate_bindings(bindings):
    for relative, expected in bindings.items():
        path = ROOT / relative
        if _relative(path) != relative or sha(path) != expected:
            raise ValueError("frozen image initialization source/evidence drifted: " + relative)


def _write_iid(path, image):
    if not IMAGE_ID.fullmatch(image):
        raise ValueError("an immutable local image SHA is required")
    if path.exists():
        if path.read_text(encoding="utf-8").strip() != image:
            raise ValueError("image IID receipt disagrees with selected image")
    else:
        with path.open("x", encoding="utf-8", newline="\n") as stream:
            stream.write(image + "\n")


def inspect_image(image, output):
    proc = images._docker_read(["image", "inspect", "--format", "{{.Id}}", image])
    actual = proc.stdout.strip()
    write_new(output, {"kind": "immutable_local_image_identity", "requested_image": image,
                       "returncode": proc.returncode, "actual_image": actual,
                       "exact_match": proc.returncode == 0 and actual == image})
    if proc.returncode or actual != image or not IMAGE_ID.fullmatch(actual):
        raise RuntimeError("required exact image is not available locally")


def inventory_check(directory, before, after):
    """Inspect only this directory's exact probe label and launch-receipt names."""
    label = images.probe_label(directory)
    names = set()
    for path in (directory / "images").glob("*/*-runtime-launch.json"):
        reject_links(path)
        launch = _json(path)
        if (launch.get("label_key") != images.PROBE_LABEL_KEY
                or launch.get("label_value") != label):
            raise ValueError("version probe launch has a different run identity")
        names.add(launch["container_name"])

    def own(row):
        labels = dict(part.split("=", 1) for part in row.get("Labels", "").split(",") if "=" in part)
        return (labels.get(images.PROBE_LABEL_KEY) == label
                or bool(names.intersection(row.get("Names", "").split(","))))

    residual = [{"container_id": row["ID"], "names": row.get("Names", "")}
                for row in after if own(row)]
    missing = sorted({row["ID"] for row in before} - {row["ID"] for row in after})
    return {"kind": "exact_version_probe_inventory_check", "label_key": images.PROBE_LABEL_KEY,
            "label_value": label, "checked_probe_names": sorted(names),
            "remaining_containers": residual, "zero_residual": not residual,
            "missing_preexisting_container_ids": missing,
            "preexisting_containers_preserved": not missing,
            "cleanup_policy": "version probes use --rm only; no automatic image/volume/unknown-container cleanup"}


def _atomic_runtime(path, value, *, validate=None):
    """Publish fully flushed JSON atomically, without replacing any existing file."""
    pending = path.with_name("runtime.pending.json")
    with pending.open("x", encoding="utf-8", newline="\n") as stream:
        json.dump(value, stream, ensure_ascii=False, indent=2)
        stream.write("\n")
        stream.flush()
        os.fsync(stream.fileno())
    if validate is not None:
        validate(pending)
    # A hard link is an atomic create-if-absent on the same filesystem. The
    # destination cannot be overwritten even if another writer creates it.
    os.link(pending, path)
    pending.unlink()


def _task_images(task, directory, profile, preflight, preflight_path, guard):
    local = directory / "images" / task
    local.mkdir(parents=True, exist_ok=False)
    guard(task)
    pinned = task in PINNED_TASKS
    runtime_versions = {}
    selected = {}
    if pinned:
        old = preflight_path.parent / "images" / task
        provenance = {"kind": "exact_existing_rc2_image_runtime_reuse", "task": task,
                      "source_report": _relative(preflight_path), "source_report_sha256": sha(preflight_path),
                      "source_artifacts_sha256": {}}
        for path in sorted(old.iterdir()):
            if path.is_file():
                provenance["source_artifacts_sha256"][_relative(path)] = sha(path)
        write_new(local / "pinned-reuse.json", provenance)
        for role, key in (("agent", "image_digests"), ("grader", "grader_image_digests")):
            guard(task)
            selected[role] = preflight["environment"][key][task]
            inspect_image(selected[role], local / (role + "-image-inspect.json"))
            _write_iid(local / (role + ".iid"), selected[role])
            runtime_versions[role] = preflight["environment"]["runtime_versions"][task][role]
            if _json(old / (role + "-runtime.json")) != runtime_versions[role]:
                raise ValueError("original five-task runtime receipt drifted")
            write_new(local / (role + "-runtime.json"), runtime_versions[role])
    else:
        agent, reuse = images.cached_agent_image(task, Path(profile["task_root"]), local / "agent-reuse.json")
        guard(task)
        if agent is None:
            agent = images.build_image(Path(profile["task_root"]) / task / "environment", local,
                                       "agent", allow_build_network=guard.allow_build_network)
        selected["agent"] = agent
        guard(task)
        selected["grader"] = images.build_image(Path(profile["task_root"]) / task / "tests", local,
                                                "grader", allow_build_network=guard.allow_build_network)
        for role in ROLES:
            guard(task)
            inspect_image(selected[role], local / (role + "-image-inspect.json"))
            _write_iid(local / (role + ".iid"), selected[role])
            runtime_versions[role] = images.image_versions(selected[role], local / (role + "-runtime.json"))
            guard(task)
    guard(task)
    row = {"kind": "dependency_image_initialization_receipt", "task": task,
           "task_sha256": profile["task_specs"][task]["normalized_sha256"],
           "context_sha256": {"agent": images.context_digest(Path(profile["task_root"]) / task / "environment"),
                              "grader": images.context_digest(Path(profile["task_root"]) / task / "tests")},
           "agent_image": selected["agent"], "grader_image": selected["grader"],
           "runtime_versions": runtime_versions, "reused_existing_rc2_pins": pinned,
           "version_probe_kind": "existing_version_receipt_reuse" if pinned else "dependency_version_only"}
    write_new(local / "receipt.json", row)
    return row


def execute(directory, *, profile_path=None, workers=1, allow_build_network=False):
    if not 1 <= workers <= 4:
        raise ValueError("workers must be between 1 and 4")
    directory = admit_directory(directory)
    profile, preflight, profile_path, preflight_path, sources = load_inputs(profile_path)
    old_stops = images.stop_receipts()
    bank = Path(profile["bank_manifest"]["path"])
    bindings = {**sources, _relative(profile_path): sha(profile_path),
                _relative(preflight_path): sha(preflight_path), _relative(bank): sha(bank)}
    _validate_bindings(bindings)
    images.validate_stops(old_stops)
    runtime_status = docker_status()
    if not runtime_status.get("available"):
        raise RuntimeError("Linux Docker unavailable; no image initialization directory created")
    core.validate_profile(profile)
    _validate_bindings(bindings)
    directory.mkdir(exist_ok=False)
    write_new(directory / "core-profile.json", profile)
    write_new(directory / "builder-sources.json", sources)
    write_new(directory / "old-stops.json", old_stops)
    bindings[_relative(directory / "core-profile.json")] = sha(directory / "core-profile.json")
    stopped = threading.Event()
    guard_lock = threading.Lock()

    def guard(task=None):
        if stopped.is_set():
            raise RuntimeError("image initialization stopped after first failure; no retries")
        with guard_lock:
            _validate_bindings(bindings)
            images.validate_stops(old_stops)
            if (directory / "STOP").exists():
                raise RuntimeError("this initialization STOP is present; no resume")
            if task is not None:
                core._task_source(profile, task)

    guard.allow_build_network = allow_build_network
    rows, errors, before = {}, [], None
    cleanup = None
    try:
        before = images.container_inventory(directory / "containers-before.json")
        if not inventory_check(directory, [], before)["zero_residual"]:
            raise RuntimeError("this exact version-probe label already has a container")
        # Admit every historical pin first. A missing required RC2 image must
        # not cause us to spend time building any of the remaining 57 tasks.
        for task in PINNED_TASKS:
            rows[task] = _task_images(task, directory, profile, preflight, preflight_path, guard)
        pending_tasks = iter(task for task in BANK_62 if task not in PINNED_TASKS)
        with ThreadPoolExecutor(max_workers=workers) as pool:
            futures = {}

            def submit_next():
                task = next(pending_tasks, None)
                if task is not None:
                    guard(task)
                    futures[pool.submit(_task_images, task, directory, profile, preflight, preflight_path, guard)] = task

            for _ in range(workers):
                submit_next()
            while futures:
                finished, _ = wait(futures, return_when=FIRST_COMPLETED)
                for future in finished:
                    task = futures.pop(future)
                    try:
                        rows[task] = future.result()
                    except Exception as exc:
                        stopped.set()
                        error = {"task": task, "type": type(exc).__name__, "detail": str(exc)[-2000:]}
                        errors.append(error)
                        write_new(directory / "images" / task / "failure.json", error)
                if not errors:
                    for _ in finished:
                        submit_next()
    except Exception as exc:
        stopped.set()
        errors.append({"type": type(exc).__name__, "detail": str(exc)[-2000:]})
    finally:
        try:
            after = images.container_inventory(directory / "containers-after.json")
            cleanup = inventory_check(directory, before or [], after)
            write_new(directory / "inventory-check.json", cleanup)
            if not cleanup["zero_residual"] or not cleanup["preexisting_containers_preserved"]:
                raise RuntimeError("container inventory changed outside the allowed zero-residual probe scope")
        except Exception as exc:
            errors.append({"type": type(exc).__name__, "detail": str(exc)[-2000:]})
        try:
            images.validate_stops(old_stops)
            _validate_bindings(bindings)
            core.validate_profile(profile)
            checked_preflight = core.validate_smoke_report(preflight_path, profile, tasks=PINNED_TASKS)
            if checked_preflight != preflight:
                raise ValueError("original RC2 evidence changed during image initialization")
        except Exception as exc:
            errors.append({"type": type(exc).__name__, "detail": str(exc)[-2000:]})
    state = {"kind": RECEIPT_KIND, "status": "failed" if errors else "completed",
             "completed_tasks": sorted(rows), "expected_tasks": 62, "execution_errors": errors,
             "automatic_retries": 0, "model_calls": 0, "task_evaluation_runs": 0,
             "historical_stops_preserved": all((ROOT / name).is_file() and sha(ROOT / name) == value
                                               for name, value in old_stops.items())}
    if not errors and set(rows) != set(BANK_62):
        errors.append({"type": "ValueError", "detail": "incomplete 62-task image coverage"})
        state["status"] = "failed"
    write_new(directory / "run-state.json", state)
    if errors:
        print(json.dumps({"status": "failed", "directory": str(directory), "errors": errors}, ensure_ascii=False, indent=2))
        return 1
    environment = {"backend": "docker", "network_mode": "no-network",
                   "verifier_environment_mode": "separate", "harbor_runtime": profile["harbor_runtime"],
                   "runtime": runtime_status, "build_network_mode": "default" if allow_build_network else "none",
                   "allow_build_network_explicit": bool(allow_build_network),
                   "build_network_scope": "Dockerfile RUN only; Docker metadata egress is not attested",
                   "image_digests": {task: rows[task]["agent_image"] for task in BANK_62},
                   "grader_image_digests": {task: rows[task]["grader_image"] for task in BANK_62},
                   "runtime_versions": {task: rows[task]["runtime_versions"] for task in BANK_62},
                   "version_probe_label": {"key": images.PROBE_LABEL_KEY, "value": images.probe_label(directory),
                                           "kind": "dependency_version_only"},
                   "cleanup_check": cleanup}
    artifacts = {_relative(path): sha(path) for path in sorted(directory.rglob("*")) if path.is_file()}
    # Bind the original exact pinned receipts as well as each new task's files.
    for task in PINNED_TASKS:
        artifacts.update(_json(directory / "images" / task / "pinned-reuse.json")["source_artifacts_sha256"])
    artifacts.update({_relative(profile_path): sha(profile_path), _relative(preflight_path): sha(preflight_path)})
    result = {"schema_version": 1, "kind": RUNTIME_KIND,
              "generated_at": datetime.now(timezone.utc).isoformat(), "task_root": profile["task_root"],
              "task_bank_manifest_sha256": profile["bank_manifest"]["sha256"],
              "component_versions": profile["component_versions"],
              "task_sha256": {task: profile["task_specs"][task]["normalized_sha256"] for task in BANK_62},
              "builder_sources": sources, "environment": environment, "raw_artifacts_sha256": artifacts,
              "model_calls": 0, "task_evaluation_runs": 0, "automatic_retries": 0}
    def validate_publication(pending):
        _validate_bindings(bindings)
        _validate_bindings(artifacts)
        images.validate_stops(old_stops)
        core.validate_profile(profile)
        release.validate_runtime(pending, profile["task_specs"], profile["bank_manifest"], preflight, root=ROOT)
        _validate_bindings(bindings)

    try:
        _atomic_runtime(directory / "runtime.json", result, validate=validate_publication)
    except Exception as exc:
        error = {"type": type(exc).__name__, "detail": str(exc)[-2000:]}
        write_new(directory / "publication-failure.json", error)
        print(json.dumps({"status": "failed", "directory": str(directory), "errors": [error]}, ensure_ascii=False, indent=2))
        return 1
    print(json.dumps({"status": "completed", "kind": RUNTIME_KIND, "tasks": 62,
                      "runtime": str(directory / "runtime.json"), "task_evaluation_runs": 0}, indent=2))
    return 0


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", "--directory", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--profile", type=Path)
    parser.add_argument("--workers", type=int, choices=range(1, 5), default=1)
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--allow-build-network", action="store_true")
    args = parser.parse_args(argv)
    if args.execute:
        return execute(args.output, profile_path=args.profile, workers=args.workers,
                       allow_build_network=args.allow_build_network)
    directory = admit_directory(args.output)
    profile, _, _, _, sources = load_inputs(args.profile)
    print(json.dumps({"kind": "smallowbench_v2_image_initialization_plan", "mode": "offline-plan",
                      "execution_started": False, "output": str(directory), "tasks": list(BANK_62),
                      "pinned_existing_rc2_tasks": list(PINNED_TASKS), "workers": args.workers,
                      "component_versions": profile["component_versions"],
                      "profile_sha256": profile["profile_sha256"], "builder_sources": sources,
                      "build_network_mode": "default" if args.allow_build_network else "none",
                      "runtime_network_mode": "none", "version_probe_kind": "dependency_version_only",
                      "model_calls": 0, "task_evaluation_runs": 0, "automatic_retries": 0},
                     ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
