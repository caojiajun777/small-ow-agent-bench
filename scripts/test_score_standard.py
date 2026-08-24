"""Orthogonal STANDARD scoring fields."""

from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from score_standard import score_trial, termination_of  # noqa: E402


def _data(*, reward=1.0, exc=None, finished=None, n_shell=1, n_turns=3, n_parse=0):
    payload = {
        "verifier_result": {"rewards": {"reward": reward}},
        "exception_info": {"exception_type": exc} if exc else {},
        "agent_result": {
            "metadata": {
                "finished": finished,
                "n_shell": n_shell,
                "n_turns": n_turns,
                "n_parse_fail": n_parse,
            }
        },
    }
    return payload


def test_unfinished_max_turns_is_protocol_error():
    data = _data(reward=1.0, finished=False, n_shell=16, n_turns=20)
    assert termination_of(data) == "protocol_error"
    row = score_trial(Path("."), data)
    assert row["atomic_correct"] == 1
    assert row["termination"] == "protocol_error"
    assert row["scored"] is True


def test_finish_without_shell_is_protocol_error():
    data = _data(reward=0.0, finished=True, n_shell=0, n_turns=4, n_parse=4)
    assert termination_of(data) == "protocol_error"


def test_clean_finish_after_shell():
    data = _data(reward=1.0, finished=True, n_shell=2, n_turns=3)
    assert termination_of(data) == "clean"


def test_missing_finished_stays_clean():
    data = _data(reward=1.0, finished=None, n_shell=0)
    data["agent_result"]["metadata"] = {}
    assert termination_of(data) == "clean"


def test_tle_wins_over_unfinished():
    data = _data(reward=0.0, exc="AgentTimeoutError", finished=False)
    assert termination_of(data) == "tle"
