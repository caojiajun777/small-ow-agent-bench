"""Bounded, model-free RC2 Linux container smoke, never a model evaluation.

Default is a read-only offline plan. --check-runtime inspects Docker but never
starts it. --execute runs exactly five fixed tasks x oracle/nop in a new short
directory. Build RUN networking is denied unless explicitly permitted, and a
local base image is required by default; Docker metadata lookups are not a
network-isolation guarantee. Both runtime roles always remain network-none.
Historical tasks, STOPs and scores are untouched.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import time
from datetime import datetime, timezone

from prepare_rc2_candidate import reject_links
from validate_v2_containers import (
    HARBOR,
    IMAGE_ID,
    checked,
    docker_status,
    safe_env,
    sha,
    write_new,
)
from v2_paths import validate_run_paths
from v2_pipeline import digest

ROOT = Path(__file__).resolve().parents[1]
TASKS = (
    "loc-bind-host",
    "edit-clip",
    "testgen-timeout-zero",
    "repro-keep-zero",
    "review-clip-incomplete",
)
MODES = ("oracle", "nop")
DEFAULT_DIRECTORY = ROOT / "experiments" / "smallowbench-v2" / "r2smk"
_CID = re.compile(r"[0-9a-f]{64}\Z")
_IGNORED = {".git", "__pycache__", ".pytest_cache"}
PROBE_LABEL_KEY = "smallowbench.rc2.smoke"


def pipeline():
    # No global mutation or aliasing of the RC1 validator's ROOT/VERSION.
    import rc2_pipeline

    return rc2_pipeline


def admit_directory(directory: Path, task_root: Path) -> tuple[Path, dict]:
    """Check exact resolved scope, old evidence and Windows paths before Docker."""
    directory = directory.absolute()
    reject_links(directory)
    allowed = (ROOT / "experiments" / "smallowbench-v2").resolve()
    resolved = directory.resolve()
    if (
        resolved.parent != allowed
        or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]{0,8}", resolved.name)
        or resolved.exists()
    ):
        raise ValueError(
            "a new 1..9-character direct child of experiments/smallowbench-v2 is required"
        )
    return resolved, validate_run_paths(
        resolved, TASKS, mode="oracle_nop", task_root=task_root
    )


def stop_receipts() -> dict[str, str]:
    """Fingerprint existing experiment STOPs without reading or changing their text."""
    base = ROOT / "experiments" / "smallowbench-v2"
    return {
        path.relative_to(ROOT).as_posix(): sha(path)
        for path in sorted(base.rglob("STOP"))
        if path.is_file() and not path.is_symlink()
    }


def validate_stops(receipts: dict[str, str]) -> None:
    for name, expected_digest in receipts.items():
        path = ROOT / name
        if not path.is_file() or path.is_symlink() or sha(path) != expected_digest:
            raise ValueError("historical STOP changed during RC2 smoke: " + name)


def _docker_read(command: list[str]) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["docker", *command],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=30,
        env=safe_env(),
        creationflags=0x08000000 if os.name == "nt" else 0,
    )


def container_inventory(output: Path) -> list[dict]:
    proc = _docker_read(["ps", "--all", "--no-trunc", "--format", "{{json .}}"])
    if proc.returncode:
        raise RuntimeError("cannot verify local container inventory")
    rows = [json.loads(line) for line in proc.stdout.splitlines() if line.strip()]
    if any(
        not isinstance(row, dict) or not _CID.fullmatch(row.get("ID", ""))
        for row in rows
    ):
        raise ValueError("Docker returned malformed container identities")
    write_new(output, {"command": "docker ps --all --no-trunc", "containers": rows})
    return rows


def own_sessions(directory: Path, rows: list[dict]) -> set[str]:
    sessions = {
        proof["session_id"]
        for row in rows
        for proof in row.get("static_network_isolation_evidence", [])
    }
    # Also cover a partially started trial whose proof was not written yet.
    for task in TASKS:
        for mode in MODES:
            job = directory / "jobs" / f"v2-{mode}-{task}"
            if not job.is_dir():
                continue
            for trial in job.iterdir():
                if trial.is_dir() and re.fullmatch(
                    re.escape(task) + r"__[A-Za-z0-9]{7}", trial.name
                ):
                    sessions.update(
                        (trial.name + "__env", trial.name + "__verifier__trial")
                    )
    return {re.sub(r"[^a-z0-9_-]", "-", value.lower()) for value in sessions}


def cleanup_check(directory: Path, rows: list[dict], inventory: list[dict]) -> dict:
    sessions = own_sessions(directory, rows)
    proof_ids = {
        proof["container_id"]
        for row in rows
        for proof in row.get("static_network_isolation_evidence", [])
    }
    residual = []
    for item in inventory:
        labels = dict(
            part.split("=", 1)
            for part in item.get("Labels", "").split(",")
            if "=" in part
        )
        if (
            item["ID"] in proof_ids
            or labels.get("com.docker.compose.project") in sessions
            or labels.get(PROBE_LABEL_KEY) == probe_label(directory)
        ):
            residual.append({"container_id": item["ID"], "names": item.get("Names")})
    return {
        "scope": "this run's exact proof IDs, trial compose sessions and unique version-probe label only; no global prune",
        "checked_sessions": sorted(sessions),
        "remaining_containers": residual,
        "zero_residual": not residual,
        "automatic_cleanup": "Harbor compose down with environment.delete=false; no image/volume removal",
    }


def probe_label(directory: Path) -> str:
    return hashlib.sha256(str(directory.resolve()).encode("utf-8")).hexdigest()


def image_versions(image: str, output: Path) -> dict:
    """Version-only ephemeral container, identified even if Docker client times out."""
    directory = output.parents[2]
    role = output.stem.split("-", 1)[0]
    label = probe_label(directory)
    name = "r2p-" + label[:10] + "-" + output.parent.name[:25] + "-" + role
    command = [
        "docker",
        "run",
        "--rm",
        "--name",
        name,
        "--label",
        PROBE_LABEL_KEY + "=" + label,
        "--network",
        "none",
        "--read-only",
        "--cap-drop",
        "ALL",
        "--security-opt",
        "no-new-privileges",
        "--pids-limit",
        "64",
        "--cpus",
        "1",
        "--memory",
        "2g",
        image,
        "python3",
        "-c",
        "import json,sys,pytest;print(json.dumps({'python':sys.version,'pytest':pytest.__version__}))",
    ]
    write_new(
        output.with_name(output.stem + "-launch.json"),
        {
            "image": image,
            "container_name": name,
            "label_key": PROBE_LABEL_KEY,
            "label_value": label,
            "network_mode": "none",
            "command": command,
            "scope": "Python/pytest version inspection only; no task or model code",
        },
    )
    checked(command, output, timeout=60)
    versions = json.loads(output.read_text(encoding="utf-8"))
    if not isinstance(versions, dict) or any(
        not isinstance(versions.get(key), str) or not versions[key]
        for key in ("python", "pytest")
    ):
        raise ValueError("runtime version probe returned malformed evidence")
    return versions


def context_digest(directory: Path) -> str:
    rows = []
    for path in sorted(directory.rglob("*")):
        relative = path.relative_to(directory)
        if _IGNORED.intersection(relative.parts) or path.suffix in {".pyc", ".pyo"}:
            continue
        reject_links(path)
        if path.is_file():
            rows.append([relative.as_posix(), sha(path)])
    return hashlib.sha256(json.dumps(rows, separators=(",", ":")).encode()).hexdigest()


def cached_agent_image(
    task: str, task_root: Path, output: Path
) -> tuple[str | None, dict]:
    """Reuse only byte-identical RC1 agent contexts with a verified local SHA ID."""
    old = ROOT / "tasks" / task / "environment"
    current = task_root / task / "environment"
    evidence = {
        "source": "full124",
        "context_sha256": context_digest(current),
        "reused": False,
    }
    if context_digest(old) != evidence["context_sha256"]:
        evidence["reason"] = "agent_context_changed"
        write_new(output, evidence)
        return None, evidence
    report_path = (
        ROOT / "experiments" / "smallowbench-v2" / "full124" / "preflight-v2.json"
    )
    if not report_path.is_file():
        evidence["reason"] = "historical_receipt_unavailable"
        write_new(output, evidence)
        return None, evidence
    report = json.loads(report_path.read_text(encoding="utf-8"))
    image = report.get("environment", {}).get("image_digests", {}).get(task)
    if (
        report.get("container_validated") is not True
        or report.get("task_bank_manifest_sha256")
        != sha(ROOT / "task-bank-v2.manifest.json")
        or not isinstance(image, str)
        or not IMAGE_ID.fullmatch(image)
    ):
        raise ValueError(
            "historical image receipt is not a valid pinned full-bank receipt"
        )
    proc = _docker_read(["image", "inspect", "--format", "{{.Id}}", image])
    evidence.update(
        receipt_sha256=sha(report_path),
        requested_image=image,
        returncode=proc.returncode,
    )
    if proc.returncode == 0 and proc.stdout.strip() == image:
        evidence.update(reused=True, actual_image=image)
    else:
        evidence["reason"] = "exact_image_not_available_locally"
    write_new(output, evidence)
    return (image if evidence["reused"] else None), evidence


def build_image(
    context: Path, output: Path, name: str, *, allow_build_network=False
) -> str:
    dockerfile = (context / "Dockerfile").read_text(encoding="utf-8")
    bases = re.findall(r"(?im)^\s*FROM\s+([^\s]+)\s*$", dockerfile)
    if bases != ["ubuntu:24.04"]:
        raise ValueError("only the frozen single-stage ubuntu:24.04 recipe is allowed")
    proc = _docker_read(["image", "inspect", "--format", "{{.Id}}", bases[0]])
    base_id = proc.stdout.strip()
    present = proc.returncode == 0 and IMAGE_ID.fullmatch(base_id) is not None
    write_new(
        output / (name + "-base.json"),
        {
            "base_reference": bases[0],
            "present_locally": present,
            "local_image_id": base_id if present else None,
            "run_network": "default" if allow_build_network else "none",
            "scope": "RUN-network control and local-base admission, not Docker metadata egress isolation",
        },
    )
    if not present and not allow_build_network:
        raise RuntimeError(
            "base image is not locally cached; refusing implicit pull; no build started"
        )
    iid = output / (name + ".iid")
    checked(
        [
            "docker",
            "build",
            "--pull=false",
            "--network",
            "default" if allow_build_network else "none",
            "--iidfile",
            str(iid),
            str(context),
        ],
        output / (name + "-build.log"),
        timeout=900,
    )
    digest = iid.read_text(encoding="utf-8").strip()
    if not IMAGE_ID.fullmatch(digest):
        raise ValueError("Docker build did not return an immutable image SHA")
    return digest


def inspect_delivery_runtime(row: dict) -> None:
    proofs = row.get("static_network_isolation_evidence", [])
    controller = row.get("verdict", {}).get("checks", {}).get("controller", {})
    if len(proofs) != 2 or any(proof.get("verified") is not True for proof in proofs):
        raise ValueError(
            "two independently verified runtime network-none proofs required"
        )
    if (
        controller.get("temporary_storage") != "native_private"
        or controller.get("temporary_parent") != "/tmp"
    ):
        raise ValueError("grader did not attest container-native /tmp workspace")
    row["native_temporary_storage_validated"] = True


def execute(directory: Path, *, allow_build_network=False) -> int:
    core = pipeline()
    profile = core.load_profile()
    directory, paths = admit_directory(directory, Path(profile["task_root"]))
    receipts = stop_receipts()
    runtime = docker_status()
    if not runtime.get("available"):
        raise RuntimeError(
            "Linux Docker unavailable; no container or run directory was created"
        )
    if not HARBOR.is_file():
        raise RuntimeError("configured local Harbor executable unavailable")
    core.validate_profile(profile)
    directory.mkdir(exist_ok=False)
    write_new(directory / "profile.json", profile)
    write_new(directory / "old-stops.json", receipts)
    environment = {
        "backend": "docker",
        "runtime": runtime,
        "network_mode": "no-network",
        "verifier_environment_mode": "separate",
        "build_network_mode": "default" if allow_build_network else "none",
        "build_network_scope": "Dockerfile RUN only; default requires local base; metadata lookup egress is not attested",
        "allow_build_network_explicit": bool(allow_build_network),
        "harbor_runtime": profile["harbor_runtime"],
        "host_path_preflight": paths,
        "image_digests": {},
        "grader_image_digests": {},
        "runtime_versions": {},
        "agent_image_reuse": {},
        "version_probe_label": {
            "key": PROBE_LABEL_KEY,
            "value": probe_label(directory),
        },
    }
    rows, errors, session_state = [], [], {}
    historical_stops_preserved = True
    try:
        before = container_inventory(directory / "containers-before.json")
        environment["container_inventory_before"] = before
        for task in TASKS:
            core.validate_profile(profile)
            validate_stops(receipts)
            if (directory / "STOP").exists():
                raise RuntimeError("this run's STOP is present; no resume is permitted")
            local = directory / "images" / task
            local.mkdir(parents=True)
            agent, reuse = cached_agent_image(
                task, Path(profile["task_root"]), local / "agent-reuse.json"
            )
            if agent is None:
                agent = build_image(
                    Path(profile["task_root"]) / task / "environment",
                    local,
                    "agent",
                    allow_build_network=allow_build_network,
                )
            grader = build_image(
                Path(profile["task_root"]) / task / "tests",
                local,
                "grader",
                allow_build_network=allow_build_network,
            )
            environment["image_digests"][task] = agent
            environment["grader_image_digests"][task] = grader
            environment["agent_image_reuse"][task] = reuse
            environment["runtime_versions"][task] = {
                "agent": image_versions(agent, local / "agent-runtime.json"),
                "grader": image_versions(grader, local / "grader-runtime.json"),
            }
            core.validate_profile(profile)
            staged = core.stage_task(profile, task, directory, agent, grader)
            for mode in MODES:
                core.validate_profile(profile)
                validate_stops(receipts)
                if (directory / "STOP").exists():
                    raise RuntimeError(
                        "this run's STOP is present; no resume is permitted"
                    )
                config = core.make_config(profile, task, mode, staged, directory)
                if (
                    config["agents"] != [{"name": mode}]
                    or config["environment"].get("delete") is not False
                ):
                    raise ValueError("model-free cleanup contract mismatch")
                from harbor.models.job.config import JobConfig

                JobConfig.model_validate(config)
                config_path = directory / "configs" / f"v2-{mode}-{task}.json"
                write_new(config_path, config)
                started = time.monotonic()
                try:
                    checked(
                        [str(HARBOR), "run", "--config", str(config_path)],
                        directory / f"v2-{mode}-{task}.log",
                        timeout=1200,
                    )
                    row = core.inspect_trial(
                        profile,
                        task,
                        mode,
                        directory,
                        agent,
                        grader,
                        session_state=session_state,
                    )
                    inspect_delivery_runtime(row)
                except (
                    OSError,
                    ValueError,
                    RuntimeError,
                    subprocess.TimeoutExpired,
                ) as exc:
                    row = {
                        "task": task,
                        "agent": mode,
                        "task_sha256": profile["task_specs"][task]["normalized_sha256"],
                        "image_digest": agent,
                        "grader_image_digest": grader,
                        "infrastructure_ok": False,
                        "expected_result_matched": False,
                        "error_type": type(exc).__name__,
                        "error": str(exc)[-2000:],
                    }
                row["elapsed_sec"] = time.monotonic() - started
                rows.append(row)
                write_new(directory / "rows" / f"{mode}-{task}.json", row)
                core.validate_profile(profile)
                if not row.get("expected_result_matched") or not row.get(
                    "infrastructure_ok"
                ):
                    raise RuntimeError(
                        "slot failed; bounded smoke stopped without retries"
                    )
    except (OSError, ValueError, RuntimeError, subprocess.TimeoutExpired) as exc:
        errors.append({"type": type(exc).__name__, "detail": str(exc)[-2000:]})
    finally:
        try:
            inventory = container_inventory(directory / "containers-after.json")
            environment["container_inventory_after"] = inventory
            environment["cleanup_check"] = cleanup_check(directory, rows, inventory)
            if not environment["cleanup_check"]["zero_residual"]:
                errors.append(
                    {
                        "type": "ResidualContainers",
                        "detail": "this run has residual containers; no global removal attempted",
                    }
                )
        except (OSError, ValueError, RuntimeError, subprocess.TimeoutExpired) as exc:
            errors.append(
                {"type": "CleanupCheckUnavailable", "detail": str(exc)[-2000:]}
            )
        try:
            core.validate_profile(profile)
        except (OSError, ValueError, RuntimeError) as exc:
            errors.append({"type": "SourceOrStopDrift", "detail": str(exc)[-2000:]})
        try:
            validate_stops(receipts)
        except (OSError, ValueError, RuntimeError) as exc:
            historical_stops_preserved = False
            errors.append({"type": "HistoricalStopDrift", "detail": str(exc)[-2000:]})
    environment["execution_errors"] = list(errors)
    try:
        report = core.summarize(profile, list(TASKS), rows, environment)
    except (OSError, ValueError, RuntimeError) as exc:
        # A profile drift must stop execution, but must not erase the failure
        # archive merely because the evidence validator correctly rejects it.
        errors.append({"type": "SummaryUnavailable", "detail": str(exc)[-2000:]})
        report = {
            "schema_version": 1,
            "kind": "smallowbench_rc2_container_execution_failure",
            "repository_root": profile["repository_root"],
            "task_root": profile["task_root"],
            "profile_sha256": profile["profile_sha256"],
            "component_versions": profile["component_versions"],
            "diagnostic_requested_tasks": list(TASKS),
            "diagnostic_expected_slots": len(TASKS) * len(MODES),
            "diagnostic_complete": len(rows) == len(TASKS) * len(MODES),
            "diagnostic_success": False,
            "container_validated": False,
            "release_gate_passed": False,
            "all_passed": False,
            "full_bank_coverage": False,
            "model_execution_authorized": False,
            "formal_ranking_eligible": False,
            "environment": environment,
            "rows": rows,
        }
    report.update(
        execution_errors=errors,
        completed_at=datetime.now(timezone.utc).isoformat(),
        historical_stops_preserved=historical_stops_preserved,
        automatic_retries=0,
        model_calls=0,
        cloud_sandbox_creates=0,
    )
    if errors:
        report.update(
            diagnostic_success=False,
            requested_scope_passed=False,
            all_passed=False,
            container_validated=False,
            release_gate_passed=False,
        )
    report["report_sha256"] = digest(
        {key: value for key, value in report.items() if key != "report_sha256"}
    )
    write_new(directory / "preflight-rc2.json", report)
    write_new(
        directory / "run-state.json",
        {
            "status": "completed" if report.get("diagnostic_success") else "stopped",
            "execution_errors": errors,
        },
    )
    print(
        json.dumps(
            {
                key: report.get(key)
                for key in (
                    "diagnostic_complete",
                    "diagnostic_success",
                    "container_validated",
                    "model_calls",
                    "execution_errors",
                )
            },
            ensure_ascii=False,
        )
    )
    return 0 if report.get("diagnostic_success") else 1


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--directory", type=Path, default=DEFAULT_DIRECTORY)
    parser.add_argument("--check-runtime", action="store_true")
    parser.add_argument("--execute", action="store_true")
    parser.add_argument(
        "--allow-build-network",
        action="store_true",
        help="explicitly allow apt/base-image build networking; runtime remains network-none",
    )
    args = parser.parse_args(argv)
    if args.execute and args.check_runtime:
        parser.error("choose --check-runtime or --execute, not both")
    if args.execute:
        return execute(args.directory, allow_build_network=args.allow_build_network)
    core = pipeline()
    profile = core.load_profile()
    core.validate_profile(profile)
    directory, paths = admit_directory(args.directory, Path(profile["task_root"]))
    value = {
        "mode": "offline-plan",
        "execution_started": False,
        "component_versions": profile["component_versions"],
        "profile_sha256": profile["profile_sha256"],
        "task_root": profile["task_root"],
        "tasks": list(TASKS),
        "oracle_nop_slots": 10,
        "directory": str(directory),
        "host_path_preflight": paths,
        "build_network_mode": "default" if args.allow_build_network else "none",
        "runtime_network_mode": "none",
        "model_calls": 0,
        "cloud_sandbox_creates": 0,
        "container_validated": False,
        "formal_ranking_allowed": False,
    }
    if args.check_runtime:
        value["runtime"] = docker_status()
    print(json.dumps(value, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
