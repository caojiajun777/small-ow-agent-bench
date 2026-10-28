"""Model-free SmallOWBench 2.0 gate through real, separate Harbor containers.

Default: an offline plan. --check-runtime only inspects Docker. --execute builds
local images and runs oracle/nop, never a model or cloud backend. A subset is
diagnostic and can never satisfy the full-bank release gate. No old report is
overwritten; a run directory must be new.
"""

from __future__ import annotations

import argparse
import hashlib
import importlib.metadata
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import time
import tomllib
from datetime import datetime, timezone

from classify_timeouts import load_trials, _reward, _exception_type
from task_sets import MAIN_47, HARD_RELEASE_15
from validate_upgraded_tasks import task_digest
from v2_paths import validate_run_paths

ROOT = Path(__file__).resolve().parents[1]
BANK = (*MAIN_47, *HARD_RELEASE_15)
VERSION = "2.0.0-rc.1"
IMAGE_ID = re.compile(r"sha256:[0-9a-f]{64}\Z")
HARBOR = (
    ROOT.parent
    / "harbor"
    / ".venv"
    / ("Scripts/harbor.exe" if os.name == "nt" else "bin/harbor")
)


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write_new(path: Path, value: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("x", encoding="utf-8", newline="\n") as stream:
        json.dump(value, stream, ensure_ascii=False, indent=2)
        stream.write("\n")


def safe_env() -> dict[str, str]:
    result = {
        key: value
        for key, value in os.environ.items()
        if not any(
            marker in key.upper()
            for marker in (
                "API_KEY",
                "ACCESS_TOKEN",
                "AUTH_TOKEN",
                "SECRET",
                "PASSWORD",
            )
        )
    }
    result.update(PYTHONPATH=str(ROOT), PYTHONIOENCODING="utf-8", PYTHONUTF8="1")
    return result


def harbor_runtime_evidence() -> dict:
    """Fingerprint the patched local Harbor and installed runtime, not secrets."""
    source = ROOT.parent / "harbor"
    code = source / "src" / "harbor"
    if not code.is_dir():
        raise ValueError("configured Harbor source tree is unavailable")
    rows = []
    for path in sorted(code.rglob("*")):
        if (
            not path.is_file()
            or {"__pycache__", ".git"}.intersection(path.parts)
            or path.suffix in {".pyc", ".pyo"}
        ):
            continue
        if path.is_symlink() or path.name.startswith(".env"):
            raise ValueError("unsafe runtime source entry")
        rows.append([path.relative_to(source).as_posix(), sha(path)])
    payload = json.dumps(rows, sort_keys=True, separators=(",", ":")).encode("utf-8")
    dependencies = sorted(
        [
            [distribution.metadata["Name"], distribution.version]
            for distribution in importlib.metadata.distributions()
            if distribution.metadata["Name"]
        ]
    )
    return {
        "package_version": importlib.metadata.version("harbor"),
        "source_tree_sha256": hashlib.sha256(payload).hexdigest(),
        "source_files": len(rows),
        "dependency_versions": dependencies,
        "dependency_spec_sha256": {
            name: sha(source / name)
            for name in ("pyproject.toml", "uv.lock")
            if (source / name).is_file()
        },
    }


def docker_status() -> dict:
    """Read-only; never launches Docker Desktop or switches to a cloud service."""
    try:
        proc = subprocess.run(
            ["docker", "info", "--format", "{{json .}}"],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=20,
            env=safe_env(),
            creationflags=0x08000000 if os.name == "nt" else 0,
        )
        if proc.returncode:
            return {
                "available": False,
                "reason": "docker_daemon_unavailable",
                "detail": proc.stderr[-2000:],
            }
        info = json.loads(proc.stdout)
        if info.get("OSType") != "linux":
            return {"available": False, "reason": "linux_docker_required"}
        return {
            "available": True,
            "server_version": info.get("ServerVersion"),
            "os_type": info.get("OSType"),
            "architecture": info.get("Architecture"),
        }
    except (OSError, subprocess.TimeoutExpired, ValueError) as exc:
        return {"available": False, "reason": type(exc).__name__}


def read_bank() -> tuple[dict, str]:
    path = ROOT / "task-bank-v2.manifest.json"
    bank = json.loads(path.read_text(encoding="utf-8"))
    items = bank.get("items", [])
    if (
        bank.get("task_version") != VERSION
        or len(items) != len(BANK)
        or {row["id"] for row in items} != set(BANK)
    ):
        raise ValueError(
            "current RC bank manifest must cover exactly the official 62 tasks"
        )
    for item in items:
        if task_digest(ROOT / "tasks" / item["id"]) != item["task_sha256"]:
            raise ValueError("task contents changed since bank manifest: " + item["id"])
    return bank, sha(path)


def checked(command: list[str], log: Path, *, timeout: float = 900) -> int:
    """Stream potentially large build/job output to disk, not process memory."""
    with log.open("xb") as stream:
        proc = subprocess.run(
            command,
            cwd=ROOT,
            env=safe_env(),
            stdout=stream,
            stderr=subprocess.STDOUT,
            timeout=timeout,
            creationflags=0x08000000 if os.name == "nt" else 0,
        )
    if proc.returncode:
        raise RuntimeError(f"command failed ({proc.returncode}); see {log.name}")
    return proc.returncode


def build_image(context: Path, output: Path, name: str) -> str:
    iid = output / (name + ".iid")
    checked(
        ["docker", "build", "--iidfile", str(iid), str(context)],
        output / (name + "-build.log"),
    )
    digest = iid.read_text(encoding="utf-8").strip()
    if not IMAGE_ID.fullmatch(digest):
        raise ValueError("Docker did not return an immutable image ID")
    return digest


def image_versions(image: str, output: Path) -> dict:
    command = [
        "docker",
        "run",
        "--rm",
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
    checked(command, output, timeout=60)
    return json.loads(output.read_text(encoding="utf-8").strip())


def stage_task(task: str, directory: Path, agent_image: str, grader_image: str) -> Path:
    target = directory / "staged-tasks" / task
    shutil.copytree(
        ROOT / "tasks" / task,
        target,
        ignore=shutil.ignore_patterns("__pycache__", ".pytest_cache", "*.pyc", ".git"),
    )
    config = target / "task.toml"
    text = config.read_text(encoding="utf-8")
    for table, image in (
        ("environment", agent_image),
        ("verifier.environment", grader_image),
    ):
        anchor = f"[{table}]\n"
        if text.count(anchor) != 1:
            raise ValueError("expected exactly one environment table")
        text = text.replace(anchor, anchor + f'docker_image = "{image}"\n')
    # A generated run copy, not an edit to the published task or historical data.
    config.write_text(text, encoding="utf-8", newline="\n")
    return target


def make_config(task: str, mode: str, staged: Path, directory: Path) -> dict:
    if task not in BANK or mode not in {"oracle", "nop"}:
        raise ValueError("only the explicit model-free bank is allowed")
    return {
        "job_name": f"v2-{mode}-{task}",
        "jobs_dir": str(directory / "jobs"),
        "n_attempts": 1,
        "n_concurrent_trials": 1,
        "timeout_multiplier": 1.0,
        "quiet": True,
        "retry": {"max_retries": 0},
        "environment": {"type": "docker", "force_build": False, "delete": True},
        "agents": [{"name": mode}],
        "tasks": [{"path": str(staged)}],
    }


def static_network_evidence(
    trial_dir: Path, expected_sessions: dict[str, str]
) -> list[dict]:
    """Validate optional host-side proofs from the strict Docker-none backend."""
    paths = sorted((trial_dir / "environment").glob("static-network-*.json"))
    if not paths:
        return []  # nftables-capable hosts use the existing dynamic provider.
    if len(paths) != 2:
        raise ValueError("separate static isolation needs two environment proofs")
    proofs = []
    for path in paths:
        if path.is_symlink() or path.stat().st_size > 65536:
            raise ValueError("unsafe static network proof")
        proof = json.loads(path.read_text(encoding="utf-8"))
        if (
            not isinstance(proof, dict)
            or proof.get("schema_version") != 1
            or proof.get("isolation") != "docker-network-none"
            or proof.get("network_mode") != "none"
            or proof.get("verified") is not True
            or not isinstance(proof.get("container_id"), str)
            or not re.fullmatch(r"[0-9a-f]{64}", proof["container_id"])
            or not isinstance(proof.get("session_id"), str)
            or not proof["session_id"]
            or not isinstance(proof.get("image"), str)
        ):
            raise ValueError("static network isolation was not actually verified")
        proofs.append(proof)
    if (
        len({proof["container_id"] for proof in proofs}) != 2
        or len({proof["session_id"] for proof in proofs}) != 2
        or {proof["session_id"] for proof in proofs} != set(expected_sessions)
        or any(
            proof["image"] != expected_sessions[proof["session_id"]]
            or proof.get("image_id") != expected_sessions[proof["session_id"]]
            for proof in proofs
        )
    ):
        raise ValueError("static isolation does not bind separate pinned environments")
    return proofs


def inspect_trial(task: str, mode: str, job: Path, directory: Path) -> dict:
    rows = load_trials(job)
    if len(rows) != 1:
        raise ValueError("preflight must have exactly one raw Harbor trial")
    trial_dir, raw = rows[0]
    staged = directory / "staged-tasks" / task
    from dirhash import dirhash
    from v2_pipeline import legacy_tree_digest

    staged_config = tomllib.loads((staged / "task.toml").read_text(encoding="utf-8"))
    if (
        raw.get("task_checksum") != dirhash(staged, "sha256")
        or raw.get("config", {}).get("task", {}).get("path") != str(staged)
        or staged_config["verifier"].get("environment_mode") != "separate"
    ):
        raise ValueError("raw Harbor trial did not execute the pinned staged task")
    trial_name = raw.get("config", {}).get("trial_name")
    if trial_name != trial_dir.name:
        raise ValueError("raw trial identity does not match its evidence directory")
    network_proofs = static_network_evidence(
        trial_dir,
        {
            f"{trial_name}__env": staged_config["environment"]["docker_image"],
            f"{trial_name}__verifier__trial": staged_config["verifier"]["environment"][
                "docker_image"
            ],
        },
    )
    verdict_path = trial_dir / "verifier" / "verdict.json"
    verdict = json.loads(verdict_path.read_text(encoding="utf-8"))
    want = 1 if mode == "oracle" else 0
    exception = _exception_type(raw)
    ok = (
        exception is None
        and verdict.get("schema_version") == 2
        and verdict.get("task_id") == task
        and verdict.get("task_version") == VERSION
        and verdict.get("grader_version") == VERSION
        and verdict.get("status") == ("pass" if want else "fail")
        and type(verdict.get("artifact_correct")) is int
        and verdict["artifact_correct"] == want
        and _reward(raw) == want
    )
    # Bind all original files required to recompute this row, not only a boolean.
    paths = [
        trial_dir / "result.json",
        verdict_path,
        trial_dir / "verifier" / "reward.txt",
        job / "config.json",
        staged / "task.toml",
    ]
    paths.extend(
        trial_dir / "verifier" / name
        for name in ("worker-result.json", "worker.stdout.txt", "worker.stderr.txt")
        if (trial_dir / "verifier" / name).is_file()
    )
    paths.extend(p for p in (trial_dir / "artifacts").rglob("*") if p.is_file())
    paths.extend((trial_dir / "environment").glob("static-network-*.json"))
    hashes = {
        path.relative_to(ROOT).as_posix(): sha(path) for path in paths if path.is_file()
    }
    return {
        "task": task,
        "agent": mode,
        "verdict": verdict,
        "returncode": 0,
        "returncode_scope": "Harbor CLI process, not the grader's pass/fail exit code",
        "infrastructure_ok": exception is None and verdict.get("status") != "error",
        "expected_result_matched": ok,
        "exception": exception,
        "static_network_isolation_evidence": network_proofs,
        "staged_task_path": staged.relative_to(ROOT).as_posix(),
        "staged_task_config_sha256": sha(staged / "task.toml"),
        "staged_tree_sha256": legacy_tree_digest(staged),
        "harbor_task_checksum": raw["task_checksum"],
        "resolved_job_config_path": (job / "config.json").relative_to(ROOT).as_posix(),
        "resolved_job_config_sha256": sha(job / "config.json"),
        "raw_trial": trial_dir.relative_to(ROOT).as_posix(),
        "artifacts_sha256": hashes,
    }


def summarize(
    rows: list[dict],
    bank: dict,
    bank_sha: str,
    environment: dict,
    requested_tasks: list[str] | None = None,
) -> dict:
    hashes = {item["id"]: item["task_sha256"] for item in bank["items"]}
    expected = {(task, agent) for task in BANK for agent in ("oracle", "nop")}
    actual = {(row.get("task"), row.get("agent")) for row in rows}
    complete = len(rows) == len(expected) and actual == expected
    passed = complete and all(
        row.get("expected_result_matched") is True
        and row.get("infrastructure_ok") is True
        and row.get("task_sha256") == hashes.get(row.get("task"))
        for row in rows
    )
    requested_tasks = list(BANK) if requested_tasks is None else requested_tasks
    if (
        not requested_tasks
        or len(requested_tasks) != len(set(requested_tasks))
        or not set(requested_tasks).issubset(BANK)
    ):
        raise ValueError("invalid diagnostic task selection")
    diagnostic_expected = {
        (task, agent) for task in requested_tasks for agent in ("oracle", "nop")
    }
    diagnostic_complete = (
        len(rows) == len(diagnostic_expected) and actual == diagnostic_expected
    )
    diagnostic_success = diagnostic_complete and all(
        row.get("expected_result_matched") is True
        and row.get("infrastructure_ok") is True
        and row.get("task_sha256") == hashes.get(row.get("task"))
        for row in rows
    )
    return {
        "schema_version": 2,
        "kind": "smallowbench_v2_container_preflight",
        "benchmark_version": VERSION,
        "manifest_sha256": None,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "task_bank_manifest_sha256": bank_sha,
        "task_hash_policy": "normalized-v2",
        "environment": environment,
        "rows": rows,
        "full_bank_coverage": complete,
        "container_validated": passed,
        "all_passed": passed,
        "diagnostic_requested_tasks": requested_tasks,
        "diagnostic_expected_slots": len(diagnostic_expected),
        "diagnostic_complete": diagnostic_complete,
        "diagnostic_success": diagnostic_success,
        "model_calls": 0,
        "cloud_sandbox_creates": 0,
        "scope": "real Harbor oracle/nop with separate local Linux verifier containers",
    }


def execute(directory: Path, tasks: list[str]) -> int:
    path_preflight = validate_run_paths(directory, tasks, mode="oracle_nop")
    bank, bank_sha = read_bank()
    runtime = docker_status()
    if not runtime["available"]:
        raise RuntimeError(
            "Docker Linux runtime is unavailable; no containers were started"
        )
    if not HARBOR.is_file():
        raise RuntimeError("configured local Harbor executable is unavailable")
    directory.mkdir(parents=True, exist_ok=False)
    images = directory / "images"
    images.mkdir()
    environment = {
        "backend": "docker",
        "runtime": runtime,
        "image_digests": {},
        "grader_image_digests": {},
        "runtime_versions": {},
        "harbor_runtime": harbor_runtime_evidence(),
        "host_path_preflight": path_preflight,
        "network_mode": "no-network",
        "verifier_environment_mode": "separate",
    }
    rows = []
    hashes = {item["id"]: item["task_sha256"] for item in bank["items"]}
    for task in tasks:
        if (directory / "STOP").exists():
            break
        if (
            sha(ROOT / "task-bank-v2.manifest.json") != bank_sha
            or task_digest(ROOT / "tasks" / task) != hashes[task]
        ):
            raise ValueError("task/bank changed during preflight")
        local = images / task
        local.mkdir()
        agent_image = build_image(ROOT / "tasks" / task / "environment", local, "agent")
        grader_image = build_image(ROOT / "tasks" / task / "tests", local, "grader")
        environment["image_digests"][task] = agent_image
        environment["grader_image_digests"][task] = grader_image
        environment["runtime_versions"][task] = {
            "agent": image_versions(agent_image, local / "agent-runtime.json"),
            "grader": image_versions(grader_image, local / "grader-runtime.json"),
        }
        staged = stage_task(task, directory, agent_image, grader_image)
        for mode in ("oracle", "nop"):
            if (directory / "STOP").exists():
                break
            config = make_config(task, mode, staged, directory)
            from harbor.models.job.config import JobConfig

            JobConfig.model_validate(config)
            config_path = directory / "configs" / f"{config['job_name']}.json"
            write_new(config_path, config)
            started = time.monotonic()
            try:
                checked(
                    [str(HARBOR), "run", "--config", str(config_path)],
                    directory / (config["job_name"] + ".log"),
                    timeout=1200,
                )
                row = inspect_trial(
                    task, mode, directory / "jobs" / config["job_name"], directory
                )
            except (
                OSError,
                ValueError,
                RuntimeError,
                subprocess.TimeoutExpired,
            ) as exc:
                row = {
                    "task": task,
                    "agent": mode,
                    "infrastructure_ok": False,
                    "expected_result_matched": False,
                    "error_type": type(exc).__name__,
                }
            row.update(
                task_sha256=hashes[task],
                image_digest=agent_image,
                grader_image_digest=grader_image,
                elapsed_sec=time.monotonic() - started,
                config_sha256=sha(config_path),
                config_path=config_path.relative_to(ROOT).as_posix(),
            )
            rows.append(row)
            write_new(directory / "rows" / f"{mode}-{task}.json", row)
    report = summarize(rows, bank, bank_sha, environment, requested_tasks=tasks)
    # A final drift check prevents an earlier green row authorizing changed tasks.
    if sha(ROOT / "task-bank-v2.manifest.json") != bank_sha or any(
        task_digest(ROOT / "tasks" / task) != hashes[task] for task in BANK
    ):
        report.update(
            container_validated=False,
            all_passed=False,
            diagnostic_success=False,
            source_drift=True,
        )
    write_new(directory / "preflight-v2.json", report)
    print(
        json.dumps(
            {
                key: report[key]
                for key in (
                    "container_validated",
                    "all_passed",
                    "full_bank_coverage",
                    "diagnostic_complete",
                    "diagnostic_success",
                )
            }
        )
    )
    return 0 if report["all_passed"] else 1


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--directory", type=Path)
    parser.add_argument("--tasks", nargs="+", choices=BANK)
    parser.add_argument("--check-runtime", action="store_true")
    parser.add_argument("--execute", action="store_true")
    args = parser.parse_args(argv)
    tasks = args.tasks or list(BANK)
    if len(tasks) != len(set(tasks)):
        parser.error("duplicate tasks are not permitted")
    if args.execute:
        if args.directory is None:
            parser.error("--execute requires a new --directory")
        directory = args.directory.resolve()
        allowed = (ROOT / "experiments" / "smallowbench-v2").resolve()
        if not directory.is_relative_to(allowed) or directory == allowed:
            parser.error("new run directory must be under experiments/smallowbench-v2/")
        return execute(directory, tasks)
    value = {
        "mode": "offline-plan",
        "benchmark_version": VERSION,
        "tasks": len(tasks),
        "oracle_nop_slots": 2 * len(tasks),
        "full_bank_requested": len(tasks) == len(BANK),
        "model_calls": 0,
        "execution_started": False,
        "container_validated": False,
    }
    if args.check_runtime:
        value["runtime"] = docker_status()
    print(json.dumps(value, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
