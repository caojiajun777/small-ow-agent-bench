"""Private portable reference implementation for this synthetic scenario."""
import os
from pathlib import Path

ROOT = Path(os.environ.get("BENCH_REPO_ROOT", "/app/repo")).resolve()
APP = Path(os.environ.get("BENCH_APP_ROOT", "/app")).resolve()
GOLD = {"clip.py":"def clip(value, lo, hi):\n    return max(lo, min(value, hi))\n","workflow.py":"from clip import clip\n\ndef process(request):\n    output = []\n    for row in request[\"readings\"]:\n        lo, hi = request[\"limits\"][row[\"channel\"]]\n        value = row[\"value\"] * row.get(\"scale\", 1) + row.get(\"offset\", 0)\n        output.append({\"id\": row[\"id\"], \"value\": clip(value, lo, hi)})\n    return output\n"}
for name, source in GOLD.items():
    path = ROOT / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(source, encoding="utf-8")

