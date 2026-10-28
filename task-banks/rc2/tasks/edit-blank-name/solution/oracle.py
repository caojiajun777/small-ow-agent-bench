"""Private portable reference implementation for this synthetic scenario."""
import os
from pathlib import Path

ROOT = Path(os.environ.get("BENCH_REPO_ROOT", "/app/repo")).resolve()
APP = Path(os.environ.get("BENCH_APP_ROOT", "/app")).resolve()
GOLD = {"profile.py":"def display_name(user):\n    return user[\"name\"] if \"name\" in user else \"guest\"\n","workflow.py":"from profile import display_name\n\ndef process(request):\n    return [{\"id\": user[\"id\"], \"display\": display_name(user)} for user in request[\"users\"]]\n"}
for name, source in GOLD.items():
    path = ROOT / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(source, encoding="utf-8")

