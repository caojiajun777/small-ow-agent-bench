"""Orthogonal STANDARD scoring fields."""

from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from score_standard import score_trial, termination_of  # noqa: E402


def _data(*, reward=1.0, exc=None, exc_msg=None, finished=None, n_shell=1, n_turns=3, n_parse=0):
    info = {}
    if exc:
        info["exception_type"] = exc
    if exc_msg is not None:
        info["exception_message"] = exc_msg
    payload = {
        "verifier_result": {"rewards": {"reward": reward}},
        "exception_info": info,
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


def test_litellm_rate_limit_is_infra():
    assert termination_of(_data(reward=0.0, exc="RateLimitError")) == "infra"
    assert termination_of(_data(reward=0.0, exc="RateLimitException")) == "infra"


def test_harbor_read_error_is_infra():
    assert termination_of(_data(reward=0.0, exc="ReadError")) == "infra"


def test_api_flake_connect_and_unavailable_are_infra():
    assert termination_of(_data(reward=0.0, exc="ConnectError")) == "infra"
    assert termination_of(_data(reward=0.0, exc="APIConnectionError")) == "infra"
    assert termination_of(_data(reward=0.0, exc="ServiceUnavailableError")) == "infra"


def test_api_status_429_and_401_are_infra():
    assert (
        termination_of(
            _data(reward=0.0, exc="APIStatusError", exc_msg="Error code: 429 rate limit")
        )
        == "infra"
    )
    assert (
        termination_of(_data(reward=0.0, exc="APIStatusError", exc_msg="Error code: 401"))
        == "infra"
    )
    assert termination_of(_data(reward=0.0, exc="AuthenticationError")) == "infra"


def test_output_length_exceeded_is_protocol_error_not_rate_limit():
    from score_standard import is_rate_limit

    data = _data(reward=0.0, exc="OutputLengthExceededError")
    assert termination_of(data) == "protocol_error"
    assert not is_rate_limit("OutputLengthExceededError", "hit max_tokens limit")
    row = score_trial(Path("."), data)
    assert row["scored"] is True
    assert row["atomic_correct"] == 0


def test_load_trials_skips_invalid_utf8(tmp_path):
    from classify_timeouts import load_trials

    trial = tmp_path / "review-mean-wrong__x"
    trial.mkdir()
    (trial / "result.json").write_bytes(b'{"trial_name": "x", "note": "\xd0\xc5"}')
    assert load_trials(tmp_path) == []


def test_load_trials_reads_utf8(tmp_path):
    from classify_timeouts import load_trials

    trial = tmp_path / "edit-clip__x"
    trial.mkdir()
    (trial / "result.json").write_text(
        '{"trial_name": "edit-clip__x"}', encoding="utf-8"
    )
    rows = load_trials(tmp_path)
    assert len(rows) == 1
    assert rows[0][1]["trial_name"] == "edit-clip__x"
