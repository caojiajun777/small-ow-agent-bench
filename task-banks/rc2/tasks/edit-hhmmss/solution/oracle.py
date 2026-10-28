"""Private portable reference implementation for this synthetic scenario."""
import os
from pathlib import Path

ROOT = Path(os.environ.get("BENCH_REPO_ROOT", "/app/repo")).resolve()
APP = Path(os.environ.get("BENCH_APP_ROOT", "/app")).resolve()
GOLD = {"timefmt.py":"def format_hms(seconds):\n    hours, rest = divmod(seconds, 3600)\n    minutes, seconds = divmod(rest, 60)\n    return f\"{hours}:{minutes:02d}:{seconds:02d}\"\n","workflow.py":"from timefmt import format_hms\n\ndef process(request):\n    jobs = []\n    total = 0\n    for job in request[\"jobs\"]:\n        seconds = max(0, job[\"end\"] - job[\"start\"] - job.get(\"paused\", 0))\n        total += seconds\n        jobs.append({\"id\": job[\"id\"], \"duration\": format_hms(seconds)})\n    return {\"jobs\": jobs, \"total\": format_hms(total)}\n"}
for name, source in GOLD.items():
    path = ROOT / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(source, encoding="utf-8")

