"""Private portable reference implementation for this synthetic scenario."""
import os
from pathlib import Path

ROOT = Path(os.environ.get("BENCH_REPO_ROOT", "/app/repo")).resolve()
APP = Path(os.environ.get("BENCH_APP_ROOT", "/app")).resolve()
GOLD = {"rank.py":"def top_k(rows, k):\n    return sorted(rows, key=lambda row: -row[\"score\"])[:max(0, k)]\n","workflow.py":"from rank import top_k\n\ndef process(request):\n    scores = {}\n    for row in request[\"events\"]:\n        name = row[\"name\"]\n        scores[name] = scores.get(name, 0) + row[\"score\"]\n    rows = [{\"name\": name, \"score\": score} for name, score in scores.items()]\n    return top_k(rows, request[\"k\"])\n"}
for name, source in GOLD.items():
    path = ROOT / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(source, encoding="utf-8")

