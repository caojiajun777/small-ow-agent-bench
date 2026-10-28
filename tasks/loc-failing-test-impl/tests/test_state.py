"""Private localization grading; no reference repair is exposed to the agent."""
import json
import os
from pathlib import Path
from verdict_v2 import submission_text, record_evidence

APP = Path(os.environ.get("BENCH_APP_ROOT", "/app")).resolve()
REPO = Path(os.environ.get("BENCH_REPO_ROOT", "/app/repo")).resolve()
TESTS = Path(os.environ.get("BENCH_TESTS_ROOT", "/tests")).resolve()


def answer_paths():
    answer = APP / "answer.txt"
    assert answer.is_file(), "answer.txt is required"
    paths = set()
    for raw in submission_text(answer).splitlines():
        value = raw.strip().replace("\\", "/")
        if not value:
            continue
        for prefix in ("/app/repo/", "app/repo/"):
            if value.startswith(prefix):
                value = value[len(prefix):]
                break
        while value.startswith("./"):
            value = value[2:]
        assert value and not value.startswith("/") and ".." not in value.split("/"), "Use repository-relative paths"
        paths.add(value)
    return paths


def test_answer_exists():
    assert (APP / "answer.txt").is_file(), "Write the diagnosed file set to answer.txt"


def test_file_set_matches():
    allowed = json.loads((TESTS / "allowed_sets.json").read_text(encoding="utf-8"))
    submitted = sorted(answer_paths())
    record_evidence({"submitted_paths": submitted, "acceptable_sets": allowed}, "localization")
    assert submitted in [sorted(paths) for paths in allowed], "The diagnosed file set is incomplete or contains unrelated files"


def test_repository_was_not_modified():
    snapshot = json.loads((TESTS / "repo_snapshot.json").read_text(encoding="utf-8"))
    actual = {}
    ignored = {"__pycache__", ".pytest_cache", ".git"}
    for path in REPO.rglob("*"):
        if not path.is_file() or ignored.intersection(path.relative_to(REPO).parts) or path.suffix == ".pyc":
            continue
        actual[path.relative_to(REPO).as_posix()] = submission_text(path).replace("\r\n", "\n")
    assert actual == snapshot, "Localization requires diagnosis without changing the repository"
