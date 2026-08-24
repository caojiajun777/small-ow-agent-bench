"""Three-matrix relabel: unfinished stays scored; Loc P/R is diagnostic."""

from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from relabel_locked import (  # noqa: E402
    classify,
    item_roles,
    loc_pr,
    loc_pred_from_stdout,
    pearson,
)


def test_unfinished_pass_is_not_missing():
    row = {"atomic_correct": 1, "termination": "protocol_error"}
    sidecar = {"n_shell": 4, "n_parse_fail": 0, "finished": False}
    assert classify(row, sidecar) == "task_pass_unfinished"


def test_clean_pass_and_e2e_and():
    row = {"atomic_correct": 1, "termination": "clean"}
    sidecar = {"n_shell": 3, "n_parse_fail": 0, "finished": True}
    assert classify(row, sidecar) == "task_pass_clean"


def test_format_fail_beats_unfinished():
    row = {"atomic_correct": 0, "termination": "protocol_error"}
    sidecar = {"n_shell": 0, "n_parse_fail": 8, "finished": False}
    assert classify(row, sidecar) == "format_fail"


def test_empty_finish_is_no_attempt():
    row = {"atomic_correct": 0, "termination": "protocol_error"}
    sidecar = {"n_shell": 0, "n_parse_fail": 0, "finished": True}
    assert classify(row, sidecar) == "no_attempt"


def test_infra_is_own_class():
    row = {"atomic_correct": None, "termination": "infra"}
    assert classify(row, {}) == "infra_fail"


def test_loc_pr_overprediction():
    stdout = "AssertionError: got ['netutil.py', 'serve.py'], expected ['serve.py']"
    pred = loc_pred_from_stdout(stdout)
    gold = {"serve.py"}
    diag = loc_pr(pred, gold)
    assert pred == {"netutil.py", "serve.py"}
    assert diag["recall"] == 1.0
    assert diag["precision"] == 0.5


def test_loc_missing_answer_is_zero_recall():
    pred = loc_pred_from_stdout("File /app/answer.txt does not exist")
    diag = loc_pr(pred, {"serve.py"})
    assert pred == set()
    assert diag["recall"] == 0.0
    assert diag["precision"] is None


def test_all_zero_item_is_above_range_and_has_no_r():
    models = ["a", "b", "c"]
    matrix = {
        "loc-bind-host": {"a": 0, "b": 0, "c": 0},
        "edit-slugify": {"a": 1, "b": 0, "c": 1},
    }
    roles = item_roles(matrix, models)
    assert roles["loc-bind-host"]["role"] == "uncalibrated_above_range"
    assert roles["loc-bind-host"]["corrected_item_total_r"] is None
    assert roles["edit-slugify"]["role"] == "irt_candidate"


def test_corrected_item_total_excludes_self():
    models = ["m1", "m2", "m3", "m4"]
    matrix = {
        "item-a": {"m1": 1, "m2": 1, "m3": 0, "m4": 0},
        "item-b": {"m1": 1, "m2": 1, "m3": 0, "m4": 0},
        "item-c": {"m1": 1, "m2": 0, "m3": 0, "m4": 0},
        "item-d": {"m1": 0, "m2": 0, "m3": 1, "m4": 1},
    }
    roles = item_roles(matrix, models)
    r_pos = roles["item-a"]["corrected_item_total_r"]
    r_neg = roles["item-d"]["corrected_item_total_r"]
    if r_pos is None or r_neg is None:
        raise AssertionError("expected finite corrected r")
    if r_pos <= 0:
        raise AssertionError(f"expected positive r, got {r_pos}")
    if r_neg >= 0:
        raise AssertionError(f"expected negative r, got {r_neg}")


def test_pearson_none_on_constant():
    assert pearson([0.0, 0.0, 0.0], [1.0, 2.0, 3.0]) is None
