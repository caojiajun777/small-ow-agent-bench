"""Local Gate A verifier-chain tests. No Harbor / Novita.

    python -m pytest scripts/test_std_normalize.py scripts/test_verifier_chain.py
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(Path(__file__).resolve().parent))
from std_normalize import extract_judgment, file_set  # noqa: E402


def _isolate(td: Path, live_root: str = "/app/repo") -> None:
    for path in (td / "tests").rglob("*.py"):
        text = path.read_text(encoding="utf-8")
        if live_root in text:
            path.write_text(text.replace(live_root, td.resolve().as_posix()), encoding="utf-8")
    posix_live = Path(live_root).as_posix()
    (td / "conftest.py").write_text(
        "import sys\n"
        "from pathlib import Path\n"
        + ("ROOT = Path(%r)\n" % str(td))
        + ("LIVE = %r\n" % posix_live)
        + "sys.path[:] = [p for p in sys.path if LIVE not in Path(p).as_posix()]\n"
        + "sys.path.insert(0, str(ROOT))\n"
    )


def _eval_below(td: Path) -> None:
    """Run test_below after optional conftest, same order as the sandbox verifier."""
    saved_path = list(sys.path)
    sys.modules.pop("clip", None)
    try:
        ns: dict[str, object] = {}
        if (td / "conftest.py").is_file():
            exec((td / "conftest.py").read_text(encoding="utf-8"), ns)
        exec((td / "tests" / "test_clip.py").read_text(encoding="utf-8"), ns)
        ns["test_below"]()  # type: ignore[operator]
    finally:
        sys.path[:] = saved_path
        sys.modules.pop("clip", None)


def _leaky_lower_bound(live_root: str) -> str:
    return (
        "import sys\n"
        f"sys.path.insert(0, {live_root!r})\n"
        "from clip import clip\n"
        "\n"
        "def test_below():\n"
        "    assert clip(-1, 0, 10) == 0\n"
    )

GOLD_CLIP = """\
def clip(value, lo, hi):
    if value < lo:
        return lo
    if value > hi:
        return hi
    return value
"""

IDENTITY_CLIP = "def clip(value, lo, hi):\n    return value\n"


def test_testgen_isolation_catches_mutant_that_leaks_to_live_gold():
    with tempfile.TemporaryDirectory() as raw:
        root = Path(raw)
        live = root / "app" / "repo"
        live.mkdir(parents=True)
        live_root = live.resolve().as_posix()
        (live / "clip.py").write_text(GOLD_CLIP, encoding="utf-8")
        (live / "tests").mkdir()
        (live / "tests" / "test_clip.py").write_text(
            _leaky_lower_bound(live_root), encoding="utf-8"
        )
        mutant = root / "identity.py"
        mutant.write_text(IDENTITY_CLIP, encoding="utf-8")

        leaked = root / "leaked"
        leaked.mkdir()
        shutil.copytree(live / "tests", leaked / "tests")
        shutil.copy(mutant, leaked / "clip.py")
        _eval_below(leaked)

        isolated = root / "isolated"
        isolated.mkdir()
        shutil.copytree(live / "tests", isolated / "tests")
        shutil.copy(mutant, isolated / "clip.py")
        _isolate(isolated, live_root=live_root)
        try:
            _eval_below(isolated)
        except AssertionError:
            pass
        else:
            raise AssertionError("isolated tests must fail on the identity mutant")


def test_testgen_isolation_gold_still_passes():
    with tempfile.TemporaryDirectory() as raw:
        root = Path(raw)
        live = root / "app" / "repo"
        live.mkdir(parents=True)
        td = root / "goldrun"
        td.mkdir()
        (td / "tests").mkdir()
        (td / "tests" / "test_clip.py").write_text(
            _leaky_lower_bound(live.resolve().as_posix()), encoding="utf-8"
        )
        (td / "clip.py").write_text(GOLD_CLIP, encoding="utf-8")
        _isolate(td, live_root=live.resolve().as_posix())
        _eval_below(td)


def _extract_oracle_repro(solve: str) -> str:
    start = solve.find("<<'PY'")
    body = solve[start + 6 :]
    body = body[body.find("\n") + 1 :]
    return body[: body.rfind("PY")].strip() + "\n"


def test_repro_dual_state_harbor_layout():
    """Match sandbox layout: /app/repro.py imports from /app/repo via PYTHONPATH."""
    names = [
        "repro-off-by-one",
        "repro-end-exclusive",
        "repro-zero-timeout",
        "repro-keep-zero",
        "repro-none-name",
        "repro-float-cents",
        "repro-first-index",
        "repro-empty-mean",
        "repro-whitespace",
        "repro-truthy-flag",
    ]
    for name in names:
        task = ROOT / "tasks" / name
        target = (task / "tests" / "target.txt").read_text(encoding="utf-8").strip()
        gold = (task / "tests" / "gold.py").read_text(encoding="utf-8")
        buggy = (task / "environment" / "repo" / target).read_text(encoding="utf-8")
        body = _extract_oracle_repro(
            (task / "solution" / "solve.sh").read_text(encoding="utf-8")
        )
        with tempfile.TemporaryDirectory() as raw:
            app = Path(raw) / "app"
            repo = app / "repo"
            repo.mkdir(parents=True)
            (repo / target).write_text(buggy, encoding="utf-8")
            script = app / "repro.py"
            script.write_text(body, encoding="utf-8")
            env = os.environ.copy()
            env["PYTHONPATH"] = str(repo)
            fail = subprocess.run(
                [sys.executable, str(script)],
                cwd=repo,
                env=env,
                capture_output=True,
                text=True,
            )
            assert fail.returncode != 0, f"{name} must fail on buggy: {fail.stderr}"
            (repo / target).write_text(gold, encoding="utf-8")
            ok = subprocess.run(
                [sys.executable, str(script)],
                cwd=repo,
                env=env,
                capture_output=True,
                text=True,
            )
            assert ok.returncode == 0, f"{name} must pass after gold: {ok.stderr}"


def test_loc_exact_set_not_subset():
    assert file_set("pricing.py\nconfig.py\n") != file_set("pricing.py\n")


def test_review_ambiguous_is_format_fail():
    assert extract_judgment("0 or 1") is None
    assert extract_judgment("The answer is 0") == "0"


def test_score_standard_tle_after_pass():
    from score_standard import score_trial

    trial = ROOT / "jobs" / "2026-08-23__01-29-00" / "edit-pad-left__gkpGS6F"
    data = __import__("json").loads((trial / "result.json").read_text(encoding="utf-8"))
    row = score_trial(trial, data)
    assert row["atomic_correct"] == 1
    assert row["termination"] == "tle"
    assert row["scored"] is True
