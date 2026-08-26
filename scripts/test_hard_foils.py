"""Gate-B foils: documented wrong answers must not match gold / hidden tests."""

from __future__ import annotations

import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from task_sets import HARD_RELEASE_15  # noqa: E402
from templates.normalize import file_set  # noqa: E402


def _foils(name: str) -> dict:
    path = ROOT / "tasks" / name / "foils" / "foils.json"
    assert path.is_file(), name
    return json.loads(path.read_text(encoding="utf-8"))


def test_every_hard_release_item_has_two_foils():
    for name in HARD_RELEASE_15:
        data = _foils(name)
        assert data["kind"]
        assert len(data["foils"]) >= 2, name


def test_loc_foils_are_not_gold_set():
    for name in HARD_RELEASE_15:
        if not name.startswith("loc-"):
            continue
        gold = file_set((ROOT / "tasks" / name / "tests" / "expected.txt").read_text())
        for foil in _foils(name)["foils"]:
            got = file_set("\n".join(foil["paths"]))
            assert got != gold, f"{name} {foil['id']}"


def test_review_flip_foil_is_wrong_bit():
    for name in HARD_RELEASE_15:
        if not name.startswith("review-"):
            continue
        label = (ROOT / "tasks" / name / "tests" / "label.txt").read_text().strip()
        foils = {item["id"]: item for item in _foils(name)["foils"]}
        assert foils["flip"]["label"] != label


def test_edit_hardcoded_and_stack_foils_fail_hidden_predicates():
    ns: dict = {}
    exec(
        next(
            item["body"]
            for item in _foils("edit-config-beside")["foils"]
            if item["id"] == "hardcoded"
        ),
        ns,
    )
    try:
        cfg = ns["load"]()
        assert cfg.get("mode") == "prod"
        raise AssertionError("hardcoded load must not satisfy mode")
    except (AssertionError, KeyError):
        pass

    ns = {}
    exec(
        next(
            item["body"]
            for item in _foils("edit-retry-discount")["foils"]
            if item["id"] == "stack-total"
        ),
        ns,
    )
    cart = {"list_price": 100, "total": 100}
    ns["charge"](cart)
    assert ns["charge"](cart) != 90

    ns = {}
    exec(
        next(
            item["body"]
            for item in _foils("edit-blank-name")["foils"]
            if item["id"] == "or-guest"
        ),
        ns,
    )
    assert ns["display_name"]({"name": ""}) != ""
