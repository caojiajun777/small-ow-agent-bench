"""Private portable reference implementation for this synthetic scenario."""
import os
from pathlib import Path

ROOT = Path(os.environ.get("BENCH_REPO_ROOT", "/app/repo")).resolve()
APP = Path(os.environ.get("BENCH_APP_ROOT", "/app")).resolve()
GOLD = {"unique.py":"def unique(items):\n    output = []\n    for item in items:\n        if item not in output:\n            output.append(item)\n    return output\n","workflow.py":"from copy import deepcopy\nfrom unique import unique\n\ndef process(request):\n    events = request[\"events\"]\n    keys = unique([event[\"key\"] for event in events])\n    first = {}\n    for event in events:\n        if event[\"key\"] not in first:\n            first[event[\"key\"]] = event\n    return [deepcopy(first[key]) for key in keys]\n"}
for name, source in GOLD.items():
    path = ROOT / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(source, encoding="utf-8")

