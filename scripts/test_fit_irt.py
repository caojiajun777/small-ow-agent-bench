"""All-zero items stay in the raw matrix and leave Rasch MLE."""

import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from fit_irt import load_matrices, split_calibrated, split_persons  # noqa: E402


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
