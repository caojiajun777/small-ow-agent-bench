"""Private portable reference implementation for this synthetic scenario."""
import os
from pathlib import Path

ROOT = Path(os.environ.get("BENCH_REPO_ROOT", "/app/repo")).resolve()
APP = Path(os.environ.get("BENCH_APP_ROOT", "/app")).resolve()
GOLD = {"span.py":"def covered(segments):\n    intervals = sorted((s, e) for s, e in segments if e > s)\n    total = 0\n    end = None\n    for start, stop in intervals:\n        if end is None or start > end:\n            total += stop - start\n            end = stop\n        elif stop > end:\n            total += stop - end\n            end = stop\n    return total\n","workflow.py":"from span import covered\n\ndef process(request):\n    start, end = request[\"window\"]\n    groups = {}\n    for row in request[\"segments\"]:\n        groups.setdefault(row[\"device\"], []).append((max(start, row[\"start\"]), min(end, row[\"end\"])))\n    return {device: covered(parts) for device, parts in groups.items()}\n"}
for name, source in GOLD.items():
    path = ROOT / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(source, encoding="utf-8")

