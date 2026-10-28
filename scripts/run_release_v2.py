"""SmallOWBench 2.0 prepare, plan, lock, status and explicitly gated execution.

Every command is read-only by default. --write creates only new experiment
artifacts; it never grants model execution or removes STOP. The execute command
delegates only to the dedicated v2 executor, never a legacy controller.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from release_v2_pipeline import (
    ROOT,
    VERSION,
    V2Error,
    build_lock,
    build_manifest,
    digest,
    job_config,
    planned_task_units,
    stage_tasks,
    status,
    validate_manifest,
    write_prepared,
)


def write_new(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("x", encoding="utf-8", newline="\n") as handle:
        json.dump(value, handle, ensure_ascii=False, indent=2, allow_nan=False)
        handle.write("\n")


def make_job_plan(directory, *, write=False, root=ROOT):
    directory = Path(directory).resolve()
    manifest = validate_manifest(directory, root=root)
    rows = []
    for slot in manifest["schedule"]:
        name = f"v2-plan-{slot['sequence']:06d}"
        config = job_config(manifest, slot, name, directory)
        rows.append(
            {
                "slot_id": slot["slot_id"],
                "job_name": name,
                "planned_config_digest": digest(config),
                "config": config,
            }
        )
    plan = {
        "schema_version": 2,
        "benchmark_version": VERSION,
        "manifest_sha256": manifest["manifest_sha256"],
        "slots": rows,
        "config_digest_policy": "canonical compact JSON content; not an executed-config file hash",
        "execution_authorized": False,
        "model_calls": 0,
        "sandbox_creates": 0,
    }
    plan["job_plan_sha256"] = digest(plan)
    if write:
        if (directory / "job-plan.json").exists():
            raise V2Error("job plan already exists; never overwrite frozen plans")
        stage_tasks(manifest, directory, root=root)
        write_new(directory / "job-plan.json", plan)
    return plan


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    prepare = commands.add_parser(
        "prepare", help="new frozen experiment; dry-run unless --write"
    )
    prepare.add_argument("--directory", required=True, type=Path)
    prepare.add_argument("--models-file", required=True, type=Path)
    prepare.add_argument("--preflight", required=True, type=Path)
    prepare.add_argument("--runtime", required=True, type=Path,
                         help="frozen image-preparation evidence for the 62 RC2 tasks")
    prepare.add_argument("--budget-usd", required=True, type=float)
    prepare.add_argument("--workers", type=int, default=1)
    prepare.add_argument("--max-infra-retries", type=int, default=0)
    prepare.add_argument("--cooldown-seconds", type=float, default=30)
    prepare.add_argument("--visit-reserve-usd", type=float, default=3.5)
    prepare.add_argument("--repetitions", type=int, choices=(1,), default=1)
    prepare.add_argument("--isolate-model-infra", action="store_true",
                         help="freeze provider-fault holds per model; keep other models eligible")
    prepare.add_argument("--write", action="store_true")
    for name in ("lock", "plan", "status", "analyze", "execute"):
        command = commands.add_parser(name)
        command.add_argument("--directory", required=True, type=Path)
        if name in ("lock", "plan"):
            command.add_argument("--write", action="store_true")
        if name == "analyze":
            command.add_argument("--output", type=Path)
        if name == "execute":
            command.add_argument("--execute", action="store_true")
            command.add_argument("--worker", type=int, default=0)
            command.add_argument("--workers", type=int)
            command.add_argument("--limit", type=int)
    args = parser.parse_args(argv)
    try:
        if args.command == "prepare":
            manifest, plan = build_manifest(
                args.directory,
                args.models_file,
                args.preflight,
                runtime_path=args.runtime,
                repetitions=args.repetitions,
                budget_usd=args.budget_usd,
                workers=args.workers,
                max_infra_retries=args.max_infra_retries,
                cooldown_seconds=args.cooldown_seconds,
                visit_reserve_usd=args.visit_reserve_usd,
                isolate_model_infra=args.isolate_model_infra,
            )
            if args.write:
                write_prepared(args.directory, manifest, plan)
            result = {
                "command": "prepare",
                "written": args.write,
                "benchmark_version": VERSION,
                "manifest_sha256": manifest["manifest_sha256"],
                "directory": str(args.directory.resolve()),
                "models": len(manifest["models"]),
                "task_units": planned_task_units(manifest),
                "engineering_diagnostic": manifest.get("diagnostic") is not None,
                "planned_slots": manifest["n_planned_trials"],
                "STOP_created_on_write": True,
                "execution_authorized": False,
                "model_calls": 0,
                "sandbox_creates": 0,
            }
        elif args.command == "lock":
            lock = build_lock(args.directory)
            if args.write:
                write_new(args.directory / "execution-lock.json", lock)
            result = {
                "command": "lock",
                "written": args.write,
                "execution_lock_sha256": lock["execution_lock_sha256"],
                "execution_authorized": False,
                "STOP_removed": False,
            }
        elif args.command == "plan":
            plan = make_job_plan(args.directory, write=args.write)
            result = {
                "command": "plan",
                "written": args.write,
                "slots": len(plan["slots"]),
                "job_plan_sha256": plan["job_plan_sha256"],
                "execution_authorized": False,
                "model_calls": 0,
                "sandbox_creates": 0,
            }
        elif args.command == "status":
            result = status(args.directory)
        elif args.command == "analyze":
            from analyze_release_v2 import main as analyze_main

            values = ["--directory", str(args.directory)]
            if args.output:
                values += ["--output", str(args.output)]
            return analyze_main(values)
        else:
            from release_v2_executor import execute_experiment

            manifest = validate_manifest(args.directory)
            workers = (
                args.workers
                if args.workers is not None
                else manifest["execution_policy"]["workers"]
            )
            return execute_experiment(
                args.directory,
                worker=args.worker,
                workers=workers,
                execute=args.execute,
                limit=args.limit,
            )
        print(json.dumps(result, ensure_ascii=False, allow_nan=False))
        return 0
    except (OSError, ValueError, KeyError, TypeError, ImportError) as exc:
        print(
            json.dumps(
                {
                    "blocked": True,
                    "command": args.command,
                    "reason": str(exc),
                    "model_execution_authorized_by_command": False,
                },
                ensure_ascii=False,
            )
        )
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
