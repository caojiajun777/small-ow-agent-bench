"""Distill IRT from existing agentic-coding ITEM response matrices.

Not model-card totals. Source: Agent Psychometrics (arXiv 2604.00594)
public matrices — SWE-Verified 500×134, Terminal-Bench 2.0 89×112,
SWE-Pro 730×14, GSO 102×15.

    python scripts/distill_bench_irt.py
"""

from __future__ import annotations

import csv
import io
import json
import math
import urllib.request
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CACHE = ROOT / "prior-irt" / "cache"
OUT = ROOT / "prior-irt" / "distilled.json"
BASE = "https://raw.githubusercontent.com/dariakryvosheieva/agent-psychometrics/main/data"

DATASETS = {
    "swebench_verified": {
        "atom": "composite_loc_edit_repro",
        "n_tasks": 500,
        "responses": f"{BASE}/swebench_verified/responses.jsonl",
        "items": f"{BASE}/swebench_verified/irt/1d_1pl/items.csv",
        "abilities": f"{BASE}/swebench_verified/irt/1d_1pl/abilities.csv",
    },
    "terminalbench": {
        "atom": "composite_shell_agent",
        "n_tasks": 89,
        "responses": f"{BASE}/terminalbench/responses.jsonl",
        "items": f"{BASE}/terminalbench/irt/1d_1pl/items.csv",
        "abilities": f"{BASE}/terminalbench/irt/1d_1pl/abilities.csv",
    },
    "swebench_pro": {
        "atom": "composite_loc_edit_repro",
        "n_tasks": 730,
        "responses": f"{BASE}/swebench_pro/responses.jsonl",
        "items": f"{BASE}/swebench_pro/irt/1d_1pl/items.csv",
        "abilities": f"{BASE}/swebench_pro/irt/1d_1pl/abilities.csv",
    },
}

# Terminal-Bench task names → five-atom guess (composite still wins).
TB_ATOM = {
    "fix-git": "edit",
    "fix-ocaml-gc": "edit",
    "fix-code-vulnerability": "edit",
    "large-scale-text-editing": "edit",
    "cobol-modernization": "edit",
    "modernize-scientific-stack": "edit",
    "sanitize-git-repo": "edit",
    "sqlite-with-gcov": "testgen",
    "write-compressor": "edit",
    "regex-log": "loc",
    "log-summary-date-ranges": "loc",
    "extract-elf": "loc",
    "extract-moves-from-video": "loc",
    "git-leak-recovery": "repro",
    "db-wal-recovery": "repro",
    "custom-memory-heap-crash": "repro",
    "vulnerable-secret": "review",
}


def _get(url: str, dest: Path) -> Path:
    dest.parent.mkdir(parents=True, exist_ok=True)
    if dest.is_file() and dest.stat().st_size > 0:
        return dest
    print(f"download {url}", flush=True)
    with urllib.request.urlopen(url, timeout=120) as resp:
        dest.write_bytes(resp.read())
    return dest


def _load_responses(path: Path) -> list[dict]:
    rows = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            rows.append(json.loads(line))
    return rows


def _load_csv(path: Path) -> list[dict[str, str]]:
    text = path.read_text(encoding="utf-8")
    return list(csv.DictReader(io.StringIO(text)))


def _p_and_b(responses: list[dict]) -> dict[str, dict]:
    hits: dict[str, list[int]] = defaultdict(list)
    for row in responses:
        for item, val in (row.get("responses") or {}).items():
            if val is None:
                continue
            hits[item].append(int(val))
    out = {}
    for item, xs in hits.items():
        n = len(xs)
        s = sum(xs)
        p = s / n if n else 0.0
        p_clip = min(max(p, 1e-3), 1 - 1e-3)
        out[item] = {
            "n_agents": n,
            "n_pass": s,
            "p": round(p, 4),
            "b_logit": round(-math.log(p_clip / (1.0 - p_clip)), 3),
        }
    return out


def _tag_tb(name: str) -> str:
    return TB_ATOM.get(name, "composite_shell_agent")


def distill_one(key: str, spec: dict) -> dict:
    resp = _load_responses(_get(spec["responses"], CACHE / key / "responses.jsonl"))
    items_irt = {}
    try:
        for row in _load_csv(_get(spec["items"], CACHE / key / "items.csv")):
            name = row.get("item") or row.get("item_id") or row.get("task") or ""
            if not name:
                name = next(iter(row.values()), "")
            diff = None
            for k in ("diff", "difficulty", "b", "beta"):
                if k in row and row[k] not in ("", None):
                    try:
                        diff = float(row[k])
                    except ValueError:
                        continue
            items_irt[name] = {"irt_b": diff, "raw": row}
    except Exception as exc:  # noqa: BLE001
        print(f"{key} items.csv skip: {exc}", flush=True)
    abilities = []
    try:
        abilities = _load_csv(_get(spec["abilities"], CACHE / key / "abilities.csv"))
    except Exception as exc:  # noqa: BLE001
        print(f"{key} abilities.csv skip: {exc}", flush=True)

    stats = _p_and_b(resp)
    items = []
    for name, st in stats.items():
        irt = items_irt.get(name) or {}
        b = irt.get("irt_b")
        if b is None:
            b = st["b_logit"]
        p = st["p"]
        # Fisher info of 1PL at theta=0 is p(1-p); peak at p=0.5.
        info0 = round(p * (1.0 - p), 4)
        if p <= 0.02:
            band = "ceiling_all_fail"
        elif p >= 0.98:
            band = "floor_all_pass"
        elif p < 0.20:
            band = "hard_for_this_population"
        elif p > 0.80:
            band = "easy_for_this_population"
        else:
            band = "informative_for_this_population"
        items.append(
            {
                "item": name,
                "p": p,
                "b": round(float(b), 3) if b is not None else None,
                "b_source": "psychometrics_1pl" if irt.get("irt_b") is not None else "logit_p",
                "info_at_theta0": info0,
                "band": band,
                "atom_guess": _tag_tb(name) if key == "terminalbench" else spec["atom"],
                "n_agents": st["n_agents"],
            }
        )
    items.sort(key=lambda r: (r["p"], r["item"]))
    keep = [i for i in items if i["band"] == "informative_for_this_population"]
    easy = [i for i in items if i["band"] == "easy_for_this_population"]
    hard = [i for i in items if i["band"] == "hard_for_this_population"]
    dead = [i for i in items if i["band"] in {"ceiling_all_fail", "floor_all_pass"}]
    return {
        "dataset": key,
        "n_subjects": len(resp),
        "n_items": len(items),
        "n_abilities": len(abilities),
        "counts": {
            "informative": len(keep),
            "easy_tail": len(easy),
            "hard_tail": len(hard),
            "zero_info": len(dead),
        },
        "note": (
            "Population is mostly frontier agents. Items with p≈0 have no "
            "information for 3B–9B either (still fail). The easy tail is the "
            "only place a small-model θ could land; still too hard if even "
            "weak frontier agents fail."
        ),
        "easiest_20": list(reversed(items[-20:])),
        "hardest_10": items[:10],
        "informative": keep,
    }


def main() -> int:
    CACHE.mkdir(parents=True, exist_ok=True)
    reports = {k: distill_one(k, spec) for k, spec in DATASETS.items()}
    summary = {
        "kind": "existing_bench_item_irt",
        "source": "https://arxiv.org/abs/2604.00594",
        "method": (
            "1PL on published item×agent 0/1 matrices. Distill = drop "
            "all-pass/all-fail, keep items with 0.2<p<0.8 in THAT population, "
            "and separately list the easiest tail as the only candidates "
            "whose b might approach small-model θ."
        ),
        "what_this_is_not": (
            "Not z-scores of model-card LCB/SWE means. Not IRT on our 47."
        ),
        "implication_for_our_47": (
            "SWE-Verified / TB2 IRT is calibrated on frontier agents. "
            "Most items are composite issue-fix or shell jobs. For 3B–9B, "
            "copying those items yields a floor of zeros (no IRT information). "
            "Refine = take the *construct* of the easy/informative tail "
            "(named-file edit, local git fix, log extract) and rewrite as "
            "atomic Harbor tasks; drop Doom-for-MIPS / Windows-3.11 class."
        ),
        "datasets": {k: {kk: vv for kk, vv in r.items() if kk != "informative"} | {
            "informative_ids": [i["item"] for i in r["informative"][:40]]
        } for k, r in reports.items()},
    }
    # keep full informative lists in a sidecar
    full = {k: r["informative"] for k, r in reports.items()}
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    (OUT.parent / "informative-items.json").write_text(
        json.dumps(full, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps({k: v["counts"] for k, v in reports.items()}, indent=2))
    print(f"wrote {OUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
