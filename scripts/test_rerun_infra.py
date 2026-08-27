"""Infra rerun helper. Does not call Harbor."""

from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from rerun_infra import OUT, _already_replaced  # noqa: E402
from run_locked import CORE_OUT, HARD_RELEASE_OUT, K3_OUT, RETRY_INCLUDE  # noqa: E402
from score_standard import termination_of  # noqa: E402


def test_side_table_does_not_overwrite_frozen_locks():
    assert OUT.resolve() != K3_OUT.resolve()
    assert OUT.resolve() != CORE_OUT.resolve()
    assert OUT.resolve() != HARD_RELEASE_OUT.resolve()
    assert "locked-core" not in OUT.name
    assert "locked-hard-release" not in OUT.name


def test_auth_error_is_infra_and_retried():
    assert "AuthenticationError" in RETRY_INCLUDE
    assert (
        termination_of(
            {
                "verifier_result": {"rewards": {"reward": 0.0}},
                "exception_info": {"exception_type": "AuthenticationError"},
                "agent_result": {"metadata": {}},
            }
        )
        == "infra"
    )


def test_replaced_requires_new_valid_job():
    src = {
        "lock_id": "qwen3.5-9b",
        "task": "loc-vip-two-files",
        "attempt": 1,
        "job": "old",
        "atomic_correct": 0,
        "termination": "protocol_error",
    }
    assert not _already_replaced([], src)
    assert not _already_replaced(
        [{**src, "job": "old", "termination": "clean", "atomic_correct": 0}],
        src,
    )
    assert _already_replaced(
        [
            {
                "lock_id": "qwen3.5-9b",
                "task": "loc-vip-two-files",
                "attempt": 1,
                "job": "new",
                "atomic_correct": 0,
                "termination": "clean",
            }
        ],
        src,
    )
