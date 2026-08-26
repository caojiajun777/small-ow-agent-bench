"""All-zero items stay in the raw matrix and leave Rasch MLE."""

import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from fit_irt import (  # noqa: E402
    fit_1pl,
    load_k3_counts,
    load_matrices,
    split_calibrated,
    split_persons,
)


def test_all_zero_excluded_from_mle():
    models = ["a", "b"]
    matrix = {
        "loc-bind-host": {"a": 0, "b": 0},
        "edit-slugify": {"a": 1, "b": 0},
        "edit-clip": {"a": 1, "b": 1},
    }
    keep, above, below = split_calibrated(matrix, models)
    assert above == ["loc-bind-host"]
    assert below == ["edit-clip"]
    assert list(keep) == ["edit-slugify"]


def test_all_zero_person_excluded():
    models = ["weak", "mid", "strong"]
    matrix = {
        "edit-slugify": {"weak": 0, "mid": 0, "strong": 1},
        "edit-clip": {"weak": 0, "mid": 1, "strong": 0},
    }
    keep, below, above = split_persons(matrix, models)
    assert below == ["weak"]
    assert above == []
    assert keep == ["mid", "strong"]


def test_binomial_all_three_excluded():
    models = ["a", "b"]
    matrix = {
        "loc-bind-host": {"a": 0, "b": 0},
        "edit-slugify": {"a": 2, "b": 1},
        "edit-clip": {"a": 3, "b": 3},
    }
    keep, above, below = split_calibrated(matrix, models, n_trials=3)
    assert above == ["loc-bind-host"]
    assert below == ["edit-clip"]
    assert list(keep) == ["edit-slugify"]


def test_binomial_not_majority_vote():
    models = ["weak", "strong"]
    matrix = {
        "edit-slugify": {"weak": 1, "strong": 3},
        "edit-clip": {"weak": 0, "strong": 2},
    }
    theta, b = fit_1pl(matrix, models, n_trials=3)
    assert theta["strong"] > theta["weak"]
    assert b["edit-clip"] > b["edit-slugify"]


def test_load_k3_counts_rounds_p_times_k(tmp_path: Path):
    payload = {
        "cells": [
            {
                "lock_id": "m1",
                "task": "edit-slugify",
                "n_valid": 3,
                "p_atomic": 0.6666666666666666,
                "p_e2e": 0.3333333333333333,
            }
        ]
    }
    path = tmp_path / "locked-core-k3.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    atomic = load_k3_counts(path, "atomic")
    e2e = load_k3_counts(path, "e2e")
    assert atomic["edit-slugify"]["m1"] == 2
    assert e2e["edit-slugify"]["m1"] == 1


def test_load_matrices_keeps_unfinished_zero(tmp_path: Path):
    payload = {
        "cells": [
            {
                "lock_id": "m1",
                "task": "edit-slugify",
                "A": 1,
                "E": 0,
            },
            {
                "lock_id": "m2",
                "task": "edit-slugify",
                "A": 1,
                "E": 1,
            },
        ]
    }
    path = tmp_path / "locked-matrices.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    atomic = load_matrices(path, "atomic")
    e2e = load_matrices(path, "e2e")
    assert atomic["edit-slugify"]["m1"] == 1
    assert e2e["edit-slugify"]["m1"] == 0
    assert e2e["edit-slugify"]["m2"] == 1
