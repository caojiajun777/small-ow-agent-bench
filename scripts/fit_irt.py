"""1PL (Rasch) on our models×items 0/1 matrix.

Published bench means are not item responses. Do not pass LCB/SWE
averages here. Fit only compact-shell atomic_correct on MAIN_47.

    python scripts/fit_irt.py
    python scripts/fit_irt.py --k3
    python scripts/fit_irt.py --score both
    python scripts/fit_irt.py --score atomic
    python scripts/fit_irt.py --score e2e
    python scripts/fit_irt.py jobs/locked-core.json
    python scripts/fit_irt.py --group main
    python scripts/fit_irt.py --group sensitivity
    python scripts/fit_irt.py --both
    python scripts/fit_irt.py --from-population

IRT-main = 10 locked OpenRouter instruct models.
The 27B ruler never enters theta. Repro items are included.
Requires ≥8 scored main models. This is exploratory 1PL, not a precision scale.
There is no coder-sensitivity fit: OpenRouter has no stable dense 3B–14B coder.
"""

from __future__ import annotations

import json
import math
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from models_lock import irt_rows, load_lock, openrouter_id, row_by_runtime_id  # noqa: E402
from task_sets import MAIN_47  # noqa: E402

LOCKED = ROOT / "jobs" / "locked-core.json"
MATRICES = ROOT / "jobs" / "locked-matrices.json"
K3_CORE = ROOT / "jobs" / "locked-core-k3.json"
K3_UPPER = ROOT / "jobs" / "locked-upper-base-k3.json"
SCREEN = ROOT / "jobs" / "core-k1-screen.json"
POP = ROOT / "prior-population.json"
OUT = ROOT / "jobs" / "irt-draft.json"
K3_OUT = ROOT / "jobs" / "irt-k3.json"
MIN_MODELS = 8
MAX_ITERS = 80
EPS = 1e-5
K3_N = 3


def _sigmoid(x: float) -> float:
    if x >= 0:
        z = math.exp(-x)
        return 1.0 / (1.0 + z)
    z = math.exp(x)
    return z / (1.0 + z)


def load_matrices(path: Path, score: str) -> dict[str, dict[str, int | None]]:
    """Load A or E from jobs/locked-matrices.json. Unfinished stays 0/1."""
    key = {"atomic": "A", "e2e": "E", "A": "A", "E": "E"}[score]
    data = json.loads(path.read_text(encoding="utf-8"))
    matrix: dict[str, dict[str, int | None]] = {t: {} for t in MAIN_47}
    for cell in data.get("cells") or []:
        task = cell.get("task")
        if task not in matrix:
            continue
        val = cell.get(key)
        matrix[task][cell["lock_id"]] = None if val is None else int(val)
    return {t: row for t, row in matrix.items() if row}


def load_screen(path: Path) -> dict[str, dict[str, int | None]]:
    data = json.loads(path.read_text(encoding="utf-8"))
    matrix: dict[str, dict[str, int | None]] = {}
    for item in data.get("items") or []:
        task = item["task"]
        if task not in MAIN_47:
            continue
        row: dict[str, int | None] = {}
        for model, cell in (item.get("by_model") or {}).items():
            if not cell:
                continue
            term = cell.get("termination")
            if term == "infra" or cell.get("atomic_correct") is None:
                row[model] = None
            else:
                row[model] = int(cell["atomic_correct"])
        matrix[task] = row
    return matrix


def models_of(matrix: dict[str, dict[str, int | None]]) -> list[str]:
    names: set[str] = set()
    for row in matrix.values():
        names.update(row)
    return sorted(names)


def filter_group(
    matrix: dict[str, dict[str, int | None]], kind: str
) -> tuple[dict[str, dict[str, int | None]], list[str], list[str]]:
    lock = load_lock()
    allowed_ids = {m["id"] for m in irt_rows(kind, lock)}
    allowed_or = {openrouter_id(m) for m in irt_rows(kind, lock)}
    allowed_or.discard(None)
    kept_models: list[str] = []
    dropped: list[str] = []
    for name in models_of(matrix):
        row = row_by_runtime_id(name, lock)
        if row and row["id"] in allowed_ids:
            kept_models.append(name)
        elif name in allowed_or:
            kept_models.append(name)
        else:
            dropped.append(name)
    filtered = {
        task: {m: rec[m] for m in kept_models if m in rec}
        for task, rec in matrix.items()
    }
    scored = [
        m for m in kept_models if any(filtered[t].get(m) is not None for t in filtered)
    ]
    return filtered, scored, dropped


def person_item_means(
    matrix: dict[str, dict[str, int | None]],
    models: list[str],
    n_trials: int = 1,
) -> tuple[dict[str, float], dict[str, float]]:
    theta0: dict[str, float] = {}
    for m in models:
        vals = [row[m] for row in matrix.values() if m in row and row[m] is not None]
        denom = n_trials * len(vals) + 1.0
        p = (sum(vals) + 0.5) / denom if vals else 0.5
        p = min(max(p, 0.02), 0.98)
        theta0[m] = math.log(p / (1.0 - p))
    b0: dict[str, float] = {}
    for task, row in matrix.items():
        vals = [v for v in row.values() if v is not None]
        denom = n_trials * len(vals) + 1.0
        p = (sum(vals) + 0.5) / denom if vals else 0.5
        p = min(max(p, 0.02), 0.98)
        b0[task] = -math.log(p / (1.0 - p))
    return theta0, b0


def split_calibrated(
    matrix: dict[str, dict[str, int | None]],
    models: list[str],
    n_trials: int = 1,
) -> tuple[dict[str, dict[str, int | None]], list[str], list[str]]:
    """Keep items with mixed counts. All-0 / all-n have no finite MLE b."""
    keep: dict[str, dict[str, int | None]] = {}
    above: list[str] = []
    below: list[str] = []
    for task, row in matrix.items():
        vals = [row[m] for m in models if row.get(m) is not None]
        if vals and all(v == 0 for v in vals):
            above.append(task)
        elif vals and all(v == n_trials for v in vals):
            below.append(task)
        else:
            keep[task] = row
    return keep, above, below


def split_persons(
    matrix: dict[str, dict[str, int | None]],
    models: list[str],
    n_trials: int = 1,
) -> tuple[list[str], list[str], list[str]]:
    """All-0 / all-n persons have no finite JML theta."""
    keep: list[str] = []
    below: list[str] = []
    above: list[str] = []
    for model in models:
        vals = [row[model] for row in matrix.values() if row.get(model) is not None]
        if vals and all(v == 0 for v in vals):
            below.append(model)
        elif vals and all(v == n_trials for v in vals):
            above.append(model)
        else:
            keep.append(model)
    return keep, below, above


def fit_1pl(
    matrix: dict[str, dict[str, int | None]],
    models: list[str],
    n_trials: int = 1,
) -> tuple[dict[str, float], dict[str, float]]:
    theta, b = person_item_means(matrix, models, n_trials=n_trials)
    items = list(matrix)
    for _ in range(MAX_ITERS):
        delta = 0.0
        for m in models:
            num = 0.0
            den = 0.0
            for task in items:
                x = matrix[task].get(m)
                if x is None:
                    continue
                p = _sigmoid(theta[m] - b[task])
                num += x - n_trials * p
                den += n_trials * p * (1.0 - p)
            if den > 1e-8:
                step = num / den
                theta[m] += step
                delta = max(delta, abs(step))
        mean_t = sum(theta.values()) / len(theta)
        for m in models:
            theta[m] -= mean_t
        for task in items:
            num = 0.0
            den = 0.0
            for m in models:
                x = matrix[task].get(m)
                if x is None:
                    continue
                p = _sigmoid(theta[m] - b[task])
                num += n_trials * p - x
                den += n_trials * p * (1.0 - p)
            if den > 1e-8:
                step = num / den
                b[task] += step
                delta = max(delta, abs(step))
        if delta < EPS:
            break
    return theta, b


def _ranks(values: list[float]) -> list[float]:
    indexed = sorted(enumerate(values), key=lambda kv: kv[1])
    ranks = [0.0] * len(values)
    i = 0
    while i < len(indexed):
        j = i
        while j + 1 < len(indexed) and indexed[j + 1][1] == indexed[i][1]:
            j += 1
        rank = (i + j) / 2.0 + 1.0
        for k in range(i, j + 1):
            ranks[indexed[k][0]] = rank
        i = j + 1
    return ranks


def spearman(xs: list[float], ys: list[float]) -> float:
    rx = _ranks(xs)
    ry = _ranks(ys)
    n = len(rx)
    mx = sum(rx) / n
    my = sum(ry) / n
    num = sum((a - mx) * (b - my) for a, b in zip(rx, ry))
    denx = math.sqrt(sum((a - mx) ** 2 for a in rx))
    deny = math.sqrt(sum((b - my) ** 2 for b in ry))
    if denx < 1e-12 or deny < 1e-12:
        return 0.0
    return num / (denx * deny)


def rank_population() -> dict:
    pop = json.loads(POP.read_text(encoding="utf-8"))
    rows = [r for r in pop["comparable_slice"]["rows"] if r["class"] != "agent_sft"]
    metrics = ("lcb_2410_2502", "aider_whole_t2", "swe_verified_agentless")
    z_rows: list[dict] = []
    for metric in metrics:
        vals = [r[metric] for r in rows if r.get(metric) is not None]
        if len(vals) < 3:
            continue
        mu = sum(vals) / len(vals)
        var = sum((v - mu) ** 2 for v in vals) / len(vals)
        sd = math.sqrt(var) if var > 1e-12 else 1.0
        for r in rows:
            if r.get(metric) is None:
                continue
            z_rows.append({"id": r["id"], "metric": metric, "z": (r[metric] - mu) / sd})
    by_id: dict[str, list[float]] = {}
    for row in z_rows:
        by_id.setdefault(row["id"], []).append(row["z"])
    ranked = [
        {
            "id": i,
            "theta_z_mean": round(sum(zs) / len(zs), 3),
            "n_metrics": len(zs),
        }
        for i, zs in by_id.items()
    ]
    ranked.sort(key=lambda r: r["theta_z_mean"], reverse=True)
    return {
        "kind": "population_theta_z",
        "note": "z-mean of comparable published means. Not item IRT.",
        "source": pop["comparable_slice"]["source"],
        "ranked": ranked,
    }


def _fit_kind(
    matrix: dict[str, dict[str, int | None]],
    kind: str,
    n_trials: int = 1,
) -> dict:
    filtered, models, dropped = filter_group(matrix, kind)
    payload = {
        "kind": f"irt_1pl_{kind}",
        "group": kind,
        "n_trials": n_trials,
        "n_models": len(models),
        "n_items": len(filtered),
        "models": models,
        "dropped_rulers_or_unlocked": dropped,
        "excluded": "rulers never enter main theta; Repro included",
        "min_models": MIN_MODELS,
        "lock": "models.lock.yaml",
    }
    calibrated, above, below = split_calibrated(filtered, models, n_trials=n_trials)
    persons, person_below, person_above = split_persons(
        calibrated, models, n_trials=n_trials
    )
    payload["uncalibrated_above_range"] = above
    payload["uncalibrated_below_range"] = below
    payload["uncalibrated_person_below_range"] = person_below
    payload["uncalibrated_person_above_range"] = person_above
    payload["n_items_calibrated"] = len(calibrated)
    payload["n_models_calibrated"] = len(persons)
    if len(models) < MIN_MODELS:
        payload["fit"] = None
        payload["warning"] = (
            f"{len(models)} scored models in IRT-{kind} < {MIN_MODELS}. "
            "Wrote the response matrix only. Run scripts/run_locked.py on the "
            "frozen 11, then re-fit. Do not swap models after seeing scores."
        )
        return payload
    if len(calibrated) < 2:
        payload["fit"] = None
        payload["warning"] = "fewer than 2 calibrated items after dropping all-0/all-n"
        return payload
    if len(persons) < MIN_MODELS:
        payload["fit"] = None
        payload["warning"] = (
            f"{len(persons)} calibrated models < {MIN_MODELS} after dropping "
            "all-0/all-n persons"
        )
        return payload
    theta, b = fit_1pl(calibrated, persons, n_trials=n_trials)
    payload["fit"] = "1pl_jml_binomial" if n_trials > 1 else "1pl_jml"
    payload["theta"] = {m: round(theta[m], 3) for m in persons}
    payload["theta_excluded"] = {m: None for m in person_below + person_above}
    payload["b"] = {t: round(b[t], 3) for t in MAIN_47 if t in b}
    return payload


def _default_matrix_path() -> Path:
    if MATRICES.is_file():
        return MATRICES
    if LOCKED.is_file():
        return LOCKED
    return SCREEN


def _score_flag() -> str:
    if "--score" in sys.argv:
        return sys.argv[sys.argv.index("--score") + 1]
    if MATRICES.is_file():
        return "both"
    return "atomic"


def load_k3_counts(path: Path, score: str) -> dict[str, dict[str, int | None]]:
    """Success counts 0..k, not majority-vote 0/1."""
    key = "p_atomic" if score in {"atomic", "A"} else "p_e2e"
    data = json.loads(path.read_text(encoding="utf-8"))
    matrix: dict[str, dict[str, int | None]] = {t: {} for t in MAIN_47}
    for cell in data.get("cells") or []:
        task = cell.get("task")
        lock_id = cell.get("lock_id")
        if task not in matrix or not lock_id:
            continue
        if cell.get("n_valid") != K3_N or cell.get(key) is None:
            matrix[task][lock_id] = None
        else:
            matrix[task][lock_id] = int(round(float(cell[key]) * K3_N))
    return {t: row for t, row in matrix.items() if row}


def merge_counts(
    base: dict[str, dict[str, int | None]],
    extra: dict[str, dict[str, int | None]],
) -> dict[str, dict[str, int | None]]:
    out = {t: dict(row) for t, row in base.items()}
    for task, row in extra.items():
        out.setdefault(task, {}).update(row)
    return out


def load_k3_merged(score: str) -> dict[str, dict[str, int | None]]:
    matrix = load_k3_counts(K3_CORE, score)
    if K3_UPPER.is_file():
        matrix = merge_counts(matrix, load_k3_counts(K3_UPPER, score))
    return matrix


def _dual_from_matrix(
    matrix: dict[str, dict[str, int | None]],
    e2e_matrix: dict[str, dict[str, int | None]],
    kind: str,
    n_trials: int,
) -> dict:
    atomic = _fit_kind(matrix, kind, n_trials=n_trials)
    e2e = _fit_kind(e2e_matrix, kind, n_trials=n_trials)
    models = [m for m in (atomic.get("theta") or {}) if m in (e2e.get("theta") or {})]
    items = [
        t for t in MAIN_47 if t in (atomic.get("b") or {}) and t in (e2e.get("b") or {})
    ]
    theta_rho = None
    b_rho = None
    if len(models) >= 3 and atomic.get("fit") and e2e.get("fit"):
        theta_rho = round(
            spearman(
                [atomic["theta"][m] for m in models],
                [e2e["theta"][m] for m in models],
            ),
            3,
        )
    if len(items) >= 3 and atomic.get("fit") and e2e.get("fit"):
        b_rho = round(
            spearman([atomic["b"][t] for t in items], [e2e["b"][t] for t in items]),
            3,
        )
    return {
        "atomic": atomic,
        "e2e": e2e,
        "theta_spearman": theta_rho,
        "b_spearman": b_rho,
    }


def fit_k3_payload() -> dict:
    atomic_m = load_k3_merged("atomic")
    e2e_m = load_k3_merged("e2e")
    main = _dual_from_matrix(atomic_m, e2e_m, "main", K3_N)
    with_upper = _dual_from_matrix(atomic_m, e2e_m, "core", K3_N)
    no_35 = {
        t: {m: v for m, v in row.items() if m != "qwen3.6-35b-a3b"}
        for t, row in atomic_m.items()
    }
    no_35_e = {
        t: {m: v for m, v in row.items() if m != "qwen3.6-35b-a3b"}
        for t, row in e2e_m.items()
    }
    exclude_35 = _dual_from_matrix(no_35, no_35_e, "core", K3_N)
    return {
        "kind": "irt_1pl_k3_binomial",
        "published": False,
        "n_trials": K3_N,
        "note": (
            "Exploratory 1PL on compact-shell k=3. Each cell is Binomial(3, p), "
            "not majority vote. Main theta is 10 compact models only. "
            "27B/35B are sensitivity. Hard-15 is not fitted. "
            "All-0 / all-3 items have no finite b. Order only; not a scale."
        ),
        "source_core": str(K3_CORE),
        "source_upper": str(K3_UPPER) if K3_UPPER.is_file() else None,
        "main": main,
        "sensitivity_with_upper": with_upper,
        "sensitivity_exclude_35b": exclude_35,
    }


def _load_matrix(path: Path, score: str) -> dict[str, dict[str, int | None]]:
    if path.name == "locked-matrices.json" or score in {"atomic", "e2e"}:
        src = path if path.name == "locked-matrices.json" else MATRICES
        if src.is_file() and score in {"atomic", "e2e", "A", "E"}:
            return load_matrices(src, score)
    return load_screen(path)


def _dual_score_payload(group: str) -> dict:
    atomic = _fit_kind(_load_matrix(MATRICES, "atomic"), group)
    e2e = _fit_kind(_load_matrix(MATRICES, "e2e"), group)
    models = [m for m in (atomic.get("theta") or {}) if m in (e2e.get("theta") or {})]
    items = [
        t for t in MAIN_47 if t in (atomic.get("b") or {}) and t in (e2e.get("b") or {})
    ]
    theta_rho = None
    b_rho = None
    if len(models) >= 3 and atomic.get("fit") and e2e.get("fit"):
        theta_rho = round(
            spearman(
                [atomic["theta"][m] for m in models],
                [e2e["theta"][m] for m in models],
            ),
            3,
        )
    if len(items) >= 3 and atomic.get("fit") and e2e.get("fit"):
        b_rho = round(
            spearman([atomic["b"][t] for t in items], [e2e["b"][t] for t in items]),
            3,
        )
    return {
        "kind": "irt_1pl_atomic_and_e2e",
        "published": False,
        "note": (
            "Exploratory 1PL. All-0 Loc items are uncalibrated_above_range "
            "and excluded from MLE. Unfinished stays 0/1, not missing. "
            "E2E = atomic and clean finish."
        ),
        "theta_spearman": theta_rho,
        "b_spearman": b_rho,
        "atomic": atomic,
        "e2e": e2e,
    }


def main() -> int:
    if "--k3" in sys.argv:
        payload = fit_k3_payload()
        K3_OUT.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
        main_fit = payload["main"]
        print(
            json.dumps(
                {
                    "main_theta_spearman": main_fit.get("theta_spearman"),
                    "main_b_spearman": main_fit.get("b_spearman"),
                    "n_atomic_items": main_fit["atomic"].get("n_items_calibrated"),
                    "theta_atomic": main_fit["atomic"].get("theta"),
                    "theta_e2e": main_fit["e2e"].get("theta"),
                    "sensitivity_with_upper_theta": (
                        payload["sensitivity_with_upper"]["atomic"].get("theta")
                    ),
                    "sensitivity_exclude_35b_theta": (
                        payload["sensitivity_exclude_35b"]["atomic"].get("theta")
                    ),
                },
                indent=2,
            )
        )
        print(f"wrote {K3_OUT}")
        ok = bool(main_fit["atomic"].get("fit") and main_fit["e2e"].get("fit"))
        return 0 if ok else 1
    if "--from-population" in sys.argv:
        out = rank_population()
        dest = ROOT / "jobs" / "prior-theta-z.json"
        dest.write_text(json.dumps(out, indent=2) + "\n", encoding="utf-8")
        print(json.dumps(out, indent=2))
        print(f"wrote {dest}")
        return 0
    path = _default_matrix_path()
    args = [
        a
        for a in sys.argv[1:]
        if not a.startswith("--")
        and a
        not in {
            "main",
            "sensitivity",
            "atomic",
            "e2e",
            "both",
        }
    ]
    if args:
        path = Path(args[0])
    if not path.is_file():
        print(f"missing {path}", file=sys.stderr)
        return 2
    kind = "main"
    if "--group" in sys.argv:
        kind = sys.argv[sys.argv.index("--group") + 1]
    score = _score_flag()
    if score == "both" and MATRICES.is_file() and "--both" not in sys.argv:
        payload = _dual_score_payload(kind)
        OUT.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
        print(
            json.dumps(
                {
                    "theta_spearman": payload["theta_spearman"],
                    "b_spearman": payload["b_spearman"],
                    "n_atomic_items": payload["atomic"].get("n_items_calibrated"),
                    "n_e2e_items": payload["e2e"].get("n_items_calibrated"),
                    "theta_atomic": payload["atomic"].get("theta"),
                    "theta_e2e": payload["e2e"].get("theta"),
                },
                indent=2,
            )
        )
        print(f"wrote {OUT}")
        return 0 if payload["atomic"].get("fit") and payload["e2e"].get("fit") else 1
    matrix = _load_matrix(path, "atomic" if score == "both" else score)
    if "--both" in sys.argv:
        main_fit = _fit_kind(matrix, "main")
        sens_fit = _fit_kind(matrix, "sensitivity")
        overlap = [
            t
            for t in MAIN_47
            if t in (main_fit.get("b") or {}) and t in (sens_fit.get("b") or {})
        ]
        rho = None
        if overlap and main_fit.get("fit") and sens_fit.get("fit"):
            rho = round(
                spearman(
                    [main_fit["b"][t] for t in overlap],
                    [sens_fit["b"][t] for t in overlap],
                ),
                3,
            )
        payload = {
            "kind": "irt_1pl_main_and_sensitivity",
            "main": main_fit,
            "sensitivity": sens_fit,
            "b_spearman": rho,
            "note": "If Edit b ranks jump after adding coders, those items have a coder specialty.",
        }
        OUT.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
        print(json.dumps({"b_spearman": rho, "n_main": main_fit["n_models"]}, indent=2))
        print(f"wrote {OUT}")
        return 0 if main_fit.get("fit") else 1
    payload = _fit_kind(matrix, kind)
    OUT.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    if payload.get("warning"):
        print(payload["warning"])
        print(f"wrote {OUT}")
        return 1
    print(
        json.dumps({"theta": payload["theta"], "n_items": len(payload["b"])}, indent=2)
    )
    print(f"wrote {OUT}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
