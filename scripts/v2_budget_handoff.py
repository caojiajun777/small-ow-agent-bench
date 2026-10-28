"""Immutable, non-forking shares of an already approved US$4 budget envelope.

This module never calls a model or changes a charge. Each consumer must bind its
share in authorization and continue to enforce its own transactional local cap.
"""

from __future__ import annotations

import argparse
from contextlib import nullcontext
from datetime import datetime, timezone
import json
import math
from pathlib import Path
import re
import sqlite3

from ledger_io import process_lock, write_atomic
from v2_pipeline import ROOT, V2Error, bound_file, digest, read_json

KIND = "smallowbench_v2_budget_handoff"


def _money(value):
    return (not isinstance(value, bool) and isinstance(value, (int, float))
            and math.isfinite(value) and value >= 0)


def _same_money(left, right):
    return _money(left) and _money(right) and math.isclose(left, right, rel_tol=0, abs_tol=1e-12)


def _experiment(root, directory):
    root, directory = Path(root).resolve(), Path(directory).resolve()
    if directory.parent != root / "experiments/smallowbench-v2":
        raise V2Error("budget share/parent directory must be a direct child of this root's v2 experiments")
    return directory


def _lineage(parent):
    return sorted({parent["directory"], *parent.get("ancestor_directories", [])})


def _path(root, parent):
    return Path(root) / "experiments/smallowbench-v2" / (
        "budget-handoff-" + digest(parent)[:24] + ".json"
    )


def _shares(root, value, parent):
    if not isinstance(value, dict) or not value:
        raise V2Error("nonempty named directory shares are required")
    result, directories = {}, set()
    lineage = {Path(item).resolve() for item in _lineage(parent)}
    for name, share in sorted(value.items()):
        if (not isinstance(name, str) or re.fullmatch(r"[a-z][a-z0-9_-]*", name) is None
                or not isinstance(share, dict) or set(share) != {"directory", "cap_usd"}
                or not _money(share.get("cap_usd")) or share["cap_usd"] <= 0):
            raise V2Error("share must have a safe name, directory and positive finite cap_usd")
        directory = _experiment(root, share["directory"])
        if directory in directories or directory in lineage:
            raise V2Error("duplicate child directory or historical ancestor reused as a share")
        directories.add(directory)
        result[name] = {"directory": str(directory), "cap_usd": share["cap_usd"]}
    return result


def read_handoff(path, *, root=ROOT):
    """Validate immutable allocation structure without admitting any execution."""
    root = Path(root).resolve()
    path = Path(path)
    if path.is_symlink():
        raise V2Error("budget handoff must not be a symlink")
    path = path.resolve()
    value = read_json(path)
    if (value.get("schema_version") != 1 or value.get("kind") != KIND
            or value.get("handoff_sha256") != digest({k: v for k, v in value.items() if k != "handoff_sha256"})
            or value.get("root") != str(root) or value.get("aggregate_cap_usd") != 4
            or not isinstance(value.get("parent"), dict)
            or not _money(value["parent"].get("committed_usd"))):
        raise V2Error("budget handoff identity/digest/root/cap mismatch")
    parent = value["parent"]
    _experiment(root, parent["directory"])
    if path != _path(root, parent) or value.get("ancestor_directories") != _lineage(parent):
        raise V2Error("budget handoff path or ancestor binding differs")
    shares = _shares(root, value.get("shares"), parent)
    historical = parent["committed_usd"]
    allocated = math.fsum(share["cap_usd"] for share in shares.values())
    residual = 4 - historical
    unallocated = residual - allocated
    if (shares != value["shares"] or historical > 4 or unallocated < -1e-12
            or not _same_money(value.get("historical_committed_usd"), historical)
            or not _same_money(value.get("residual_cap_usd"), residual)
            or not _same_money(value.get("unallocated_usd"), max(0.0, unallocated))):
        raise V2Error("budget handoff share caps or accounting differ")
    return value


def handoff_documents(root=ROOT):
    """Strict scan used by every allocation path, including old probe entrypoints."""
    root = Path(root).resolve()
    return [(path, read_handoff(path, root=root)) for path in sorted(
        (root / "experiments/smallowbench-v2").glob("budget-handoff-*.json")
    )]


def _check_child_rights(root, shares, *, own_path=None):
    requested = {Path(row["directory"]).resolve() for row in shares.values()}
    for path, existing in handoff_documents(root):
        if own_path is not None and path.resolve() == Path(own_path).resolve():
            continue
        allocated = {Path(row["directory"]).resolve() for row in existing["shares"].values()}
        if requested.intersection(allocated):
            raise V2Error("child directory already has an immutable handoff share")


def create_handoff(root, parent, directory_shares, aggregate_cap=4, write=False):
    """Plan by default; write grants immutable disjoint local spending ceilings."""
    from route_probe_v2 import _check_allocation_overlap, parent_budget

    root = Path(root).resolve()
    parent = _experiment(root, parent)
    if not _money(aggregate_cap) or aggregate_cap != 4:
        raise V2Error("handoff must retain the original aggregate US$4 cap")
    allocation_lock = root / "experiments/smallowbench-v2/route-budget-allocation"
    with process_lock(allocation_lock, timeout=1) if write else nullcontext():
        parent_row = parent_budget(parent)
        shares = _shares(root, directory_shares, parent_row)
        historical = parent_row["committed_usd"]
        allocated = math.fsum(share["cap_usd"] for share in shares.values())
        residual = aggregate_cap - historical
        if allocated > residual + 1e-12:
            raise V2Error("share caps exceed the original aggregate residual budget")
        # Same lock as probe allocation: completed ancestors are permitted, but
        # any sibling probe or existing overlapping handoff blocks the split.
        _check_allocation_overlap(root, {"parents": [parent_row]})
        _check_child_rights(root, shares)
        value = {
            "schema_version": 1, "kind": KIND, "root": str(root),
            "created_at": datetime.now(timezone.utc).isoformat(),
            "parent": parent_row, "ancestor_directories": _lineage(parent_row),
            "aggregate_cap_usd": aggregate_cap, "historical_committed_usd": historical,
            "residual_cap_usd": residual, "shares": shares,
            "unallocated_usd": max(0.0, residual - allocated),
            "automatic_reallocation": False,
        }
        value["handoff_sha256"] = digest(value)
        if write:
            write_atomic(_path(root, parent_row), value, overwrite=False)
        return value


def validate_share(binding, share, directory, cap, root=ROOT):
    """Revalidate the full parent and exact rights before every paid admission."""
    from route_probe_v2 import _check_allocation_overlap, parent_budget

    root = Path(root).resolve()
    if not isinstance(binding, dict) or set(binding) != {"path", "sha256"}:
        raise V2Error("exact bound_file handoff reference is required")
    path = Path(binding["path"])
    if path.is_symlink() or bound_file(path) != binding:
        raise V2Error("bound budget handoff evidence changed")
    value = read_handoff(path, root=root)
    directory = _experiment(root, directory)
    rights = value["shares"].get(share)
    if (rights is None or rights["directory"] != str(directory)
            or not _money(cap) or cap != rights["cap_usd"]):
        raise V2Error("requested directory/cap is not the exact authorized handoff share")
    current = parent_budget(value["parent"]["directory"])
    if current != value["parent"]:
        raise V2Error("budget handoff historical parent evidence changed")
    _check_child_rights(root, value["shares"], own_path=path)
    _check_allocation_overlap(root, {"parents": [current]}, handoff_path=path.resolve())
    return dict(rights)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    create = sub.add_parser("create")
    create.add_argument("--root", type=Path, default=ROOT)
    create.add_argument("--parent", type=Path, required=True)
    create.add_argument("--share", action="append", required=True, help="NAME=DIRECTORY=CAP_USD")
    create.add_argument("--aggregate-cap", type=float, default=4)
    create.add_argument("--write", action="store_true")
    validate = sub.add_parser("validate")
    validate.add_argument("--root", type=Path, default=ROOT)
    validate.add_argument("--handoff", type=Path, required=True)
    validate.add_argument("--sha256", required=True)
    validate.add_argument("--share", required=True)
    validate.add_argument("--directory", type=Path, required=True)
    validate.add_argument("--cap", type=float, required=True)
    args = parser.parse_args(argv)
    try:
        if args.command == "create":
            shares = {}
            for entry in args.share:
                name, directory, amount = entry.split("=", 2)
                if name in shares:
                    raise V2Error("duplicate named share")
                shares[name] = {"directory": directory, "cap_usd": float(amount)}
            value = create_handoff(args.root, args.parent, shares, args.aggregate_cap, args.write)
            path = _path(Path(args.root).resolve(), value["parent"])
            result = {"written": args.write, "path": str(path), "handoff_sha256": value["handoff_sha256"],
                      "binding": bound_file(path) if args.write else None, "shares": value["shares"],
                      "historical_committed_usd": value["historical_committed_usd"], "paid_calls": 0}
        else:
            rights = validate_share({"path": str(args.handoff.resolve()), "sha256": args.sha256},
                                    args.share, args.directory, args.cap, args.root)
            result = {"valid": True, "share": args.share, **rights, "paid_calls": 0}
        print(json.dumps(result, ensure_ascii=False, allow_nan=False))
        return 0
    except (OSError, ValueError, KeyError, TypeError, sqlite3.Error) as exc:
        print(json.dumps({"blocked": True, "error": str(exc)}, ensure_ascii=False))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
