"""Hard-Release-15: disjoint traps, no instruction leaks, files on disk."""

from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from task_sets import HARD_DEV_10, HARD_RELEASE_15, MAIN_47  # noqa: E402

LEAKS = (
    "casefold",
    "round-half-even",
    "round_half_even",
    "banker",
    "__getattr__",
    "fromisoformat",
    "object_pairs",
    "lru_cache",
    "mutable default",
    "sys.path",
    "sitecustomize",
)

LOC_GOLD = {
    "loc-vendor-shadow": "vendor/billing/limits.py",
    "loc-env-wrapper": "bin/serve.sh",
    "loc-hook-plugin": "plugins/retry_v1.py",
}


def test_hard_release_fifteen_disjoint():
    assert len(HARD_RELEASE_15) == 15
    assert len(set(HARD_RELEASE_15)) == 15
    assert not set(HARD_RELEASE_15) & set(MAIN_47)
    assert not set(HARD_RELEASE_15) & set(HARD_DEV_10)
    prefixes = [n.split("-", 1)[0] for n in HARD_RELEASE_15]
    assert prefixes.count("loc") == 3
    assert prefixes.count("edit") == 3
    assert prefixes.count("testgen") == 3
    assert prefixes.count("repro") == 3
    assert prefixes.count("review") == 3
    for name in HARD_RELEASE_15:
        assert (ROOT / "tasks" / name / "task.toml").is_file(), name
        assert (ROOT / "tasks" / name / "instruction.md").is_file(), name
        assert (ROOT / "tasks" / name / "solution" / "solve.sh").is_file(), name


def test_hard_release_instructions_do_not_leak_trap():
    for name in HARD_RELEASE_15:
        text = (ROOT / "tasks" / name / "instruction.md").read_text(encoding="utf-8").lower()
        for leak in LEAKS:
            assert leak not in text, f"{name} leaks {leak!r}"
        gold = LOC_GOLD.get(name)
        if gold:
            assert gold.lower() not in text, f"{name} names gold path"


def test_loc_instructions_drop_unique_grep_anchors():
    env = (ROOT / "tasks" / "loc-env-wrapper" / "instruction.md").read_text(encoding="utf-8").lower()
    assert "debug" not in env
    hook = (ROOT / "tasks" / "loc-hook-plugin" / "instruction.md").read_text(encoding="utf-8")
    assert "3" not in hook
    assert "5 times" not in hook.lower()


def test_v0_candidate_archived_and_official_swapped_twins():
    from task_sets import HARD_RELEASE_V0_CANDIDATE

    assert "repro-double-discount" in HARD_RELEASE_V0_CANDIDATE
    assert "repro-double-discount" not in HARD_RELEASE_15
    assert "repro-second-export" in HARD_RELEASE_15
    assert "review-shared-cart" not in HARD_RELEASE_15
    assert "review-wired-helper" in HARD_RELEASE_15
    text = (ROOT / "tasks" / HARD_RELEASE_15[0] / "task.toml").read_text(encoding="utf-8")
    assert "hard-release" in text
    assert "hard-dev" not in text
