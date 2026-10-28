"""Trusted localization answer; does not alter the application."""
import os
from pathlib import Path

REPO = Path(os.environ.get("BENCH_REPO_ROOT", "/app/repo"))
APP = Path(os.environ.get("BENCH_APP_ROOT", "/app"))
if not REPO.is_dir():
    raise RuntimeError("Repository root does not exist")
APP.mkdir(parents=True, exist_ok=True)
(APP / "answer.txt").write_text("vendor/billing/limits.py\n", encoding="utf-8")
