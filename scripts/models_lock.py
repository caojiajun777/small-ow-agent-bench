"""Load the frozen 11-model roster from models.lock.yaml.

    python -c "from models_lock import load_lock, models; print(len(models(load_lock())))"
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
LOCK_PATH = ROOT / "models.lock.yaml"

MAIN_GROUP = "irt-main"
RULER_GROUP = "ruler"
IRT_GROUPS = {
    "main": (MAIN_GROUP,),
    "sensitivity": (MAIN_GROUP,),
}
RUN_GROUPS = {
    "main": MAIN_GROUP,
    "irt-main": MAIN_GROUP,
    "ruler": RULER_GROUP,
    "all": None,
}

PROVIDER_PIN = {
    "allow_fallbacks": False,
    "require_parameters": True,
}


def load_lock(path: Path = LOCK_PATH) -> dict[str, Any]:
    text = path.read_text(encoding="utf-8")
    try:
        import yaml  # type: ignore[import-untyped]
    except ImportError as exc:
        raise SystemExit(
            "PyYAML is required to read models.lock.yaml (Harbor env has it)."
        ) from exc
    data = yaml.safe_load(text)
    if not isinstance(data, dict) or not data.get("frozen"):
        raise SystemExit(f"invalid lock file: {path}")
    rows = data.get("models") or []
    if len(rows) != 11:
        raise SystemExit(f"lock must list 11 models, got {len(rows)}")
    ids = [m["id"] for m in rows]
    if len(ids) != len(set(ids)):
        raise SystemExit("duplicate model id in lock")
    n_main = sum(1 for m in rows if m.get("group") == MAIN_GROUP)
    n_ruler = sum(1 for m in rows if m.get("group") == RULER_GROUP)
    if n_main != 10 or n_ruler != 1:
        raise SystemExit(f"lock groups must be 10 main + 1 ruler, got {n_main}/{n_ruler}")
    for row in rows:
        if not row.get("openrouter_id"):
            raise SystemExit(f"{row.get('id')} missing openrouter_id")
        if not row.get("openrouter_provider"):
            raise SystemExit(f"{row.get('id')} missing openrouter_provider")
        if row.get("group") not in {MAIN_GROUP, RULER_GROUP}:
            raise SystemExit(f"unknown group {row.get('group')!r} on {row.get('id')}")
    return data


def models(lock: dict[str, Any] | None = None) -> list[dict[str, Any]]:
    data = lock or load_lock()
    return list(data["models"])


def by_group(group: str, lock: dict[str, Any] | None = None) -> list[dict[str, Any]]:
    return [m for m in models(lock) if m.get("group") == group]


def by_batch(
    batch: int | None, lock: dict[str, Any] | None = None
) -> list[dict[str, Any]]:
    rows = models(lock)
    if batch is None:
        return rows
    return [m for m in rows if int(m.get("batch") or 0) == batch]


def select_subjects(
    group: str = "main",
    batch: int | None = None,
    lock: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    data = lock or load_lock()
    if group not in RUN_GROUPS:
        allowed = ", ".join(sorted(RUN_GROUPS))
        raise SystemExit(f"unknown group {group!r}; use {allowed}")
    wanted = RUN_GROUPS[group]
    rows = models(data)
    if wanted is not None:
        rows = [m for m in rows if m.get("group") == wanted]
    if batch is not None:
        rows = [m for m in rows if int(m.get("batch") or 0) == batch]
    return rows


def irt_rows(kind: str, lock: dict[str, Any] | None = None) -> list[dict[str, Any]]:
    groups = IRT_GROUPS.get(kind)
    if not groups:
        raise SystemExit(f"unknown IRT group {kind!r}; use main")
    allowed = set(groups)
    return [m for m in models(lock) if m.get("group") in allowed]


def openrouter_id(row: dict[str, Any]) -> str | None:
    oid = row.get("openrouter_id")
    if oid in (None, "", "null"):
        return None
    return str(oid)


def llm_kwargs(
    row: dict[str, Any], lock: dict[str, Any] | None = None
) -> dict[str, Any]:
    extra_body: dict[str, Any] = {
        "provider": {
            "order": [str(row["openrouter_provider"])],
            **PROVIDER_PIN,
        }
    }
    if row.get("family") == "qwen":
        extra_body["reasoning"] = {"enabled": False}
        extra_body["enable_thinking"] = False
    inf = (lock or {}).get("inference") if lock is not None else None
    if inf is None:
        inf = (load_lock().get("inference") or {})
    max_tokens = inf.get("max_tokens")
    raw = row.get("llm_call_kwargs")
    merged: dict[str, Any]
    if isinstance(raw, dict):
        nested = raw.get("extra_body")
        if isinstance(nested, dict):
            extra_body = {**extra_body, **nested, "provider": extra_body["provider"]}
        merged = dict(raw)
        merged["extra_body"] = extra_body
    else:
        merged = {"extra_body": extra_body}
    if max_tokens is not None and "max_tokens" not in merged:
        merged["max_tokens"] = int(max_tokens)
    return merged


def row_by_runtime_id(
    runtime_id: str, lock: dict[str, Any] | None = None
) -> dict[str, Any] | None:
    for row in models(lock):
        if row.get("id") == runtime_id or openrouter_id(row) == runtime_id:
            return row
    return None
