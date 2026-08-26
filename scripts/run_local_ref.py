"""Local Reference dry-run / gate. Does not overwrite API Standard scores.

    python scripts/run_local_ref.py
    python scripts/run_local_ref.py --run

--run requires VLLM_BASE_URL (OpenAI-compatible vLLM on Linux). Native
Windows is not a vLLM host. A completed local table writes
jobs/locked-local-ref-k3.json and must not overwrite locked-core*.json.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from models_lock import models  # noqa: E402
from task_sets import MAIN_47  # noqa: E402

LOCAL = ROOT / "models.local.yaml"
OUT = ROOT / "jobs" / "locked-local-ref-k3.json"


def load_pins(path: Path = LOCAL) -> dict[str, Any]:
    try:
        import yaml  # type: ignore[import-untyped]
    except ImportError as exc:
        raise SystemExit("PyYAML is required to read models.local.yaml") from exc
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict) or data.get("kind") != "local_reference_pins":
        raise SystemExit(f"invalid local pin file: {path}")
    return data


def pins_by_id(data: dict[str, Any] | None = None) -> dict[str, dict[str, str]]:
    blob = data or load_pins()
    return {row["id"]: row for row in blob.get("models") or []}


def validate_against_lock() -> list[str]:
    pins = pins_by_id()
    missing = [m["id"] for m in models() if m["id"] not in pins]
    short = [
        row["id"]
        for row in pins.values()
        if len(row.get("hf_revision") or "") < 40
    ]
    problems = []
    if missing:
        problems.append(f"missing pins: {missing}")
    if short:
        problems.append(f"hf_revision not a full SHA: {short}")
    return problems


def main() -> int:
    run = "--run" in sys.argv
    problems = validate_against_lock()
    if problems:
        print("\n".join(problems), file=sys.stderr)
        return 2
    pins = load_pins()
    print("===== LOCAL REFERENCE =====")
    print(f"pins {LOCAL}")
    print(f"pinned_at {pins.get('pinned_at')}")
    print(f"n_models {len(pins.get('models') or [])}  n_tasks {len(MAIN_47)}")
    print("overwrites_api_standard", pins.get("overwrites_api_standard"))
    print("output would be", OUT)
    print("VLLM_BASE_URL", os.environ.get("VLLM_BASE_URL") or "(unset)")
    if not run:
        print("dry-run; pass --run after a Linux vLLM server is up")
        return 0
    base = os.environ.get("VLLM_BASE_URL", "").strip()
    if not base:
        print(
            "missing VLLM_BASE_URL. Local Reference is a Linux vLLM table; "
            "it is not required for benchmark-v1.0 API Standard.",
            file=sys.stderr,
        )
        return 2
    if OUT.is_file():
        print(f"{OUT} already exists; not overwriting", file=sys.stderr)
        return 2
    print(
        "VLLM_BASE_URL is set, but the Harbor local-ref loop is not wired "
        "in this snapshot. Pins are frozen; do not overwrite API locks.",
        file=sys.stderr,
    )
    return 2


if __name__ == "__main__":
    sys.exit(main())
