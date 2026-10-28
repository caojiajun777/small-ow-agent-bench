"""Private portable reference implementation for this synthetic scenario."""
import os
from pathlib import Path

ROOT = Path(os.environ.get("BENCH_REPO_ROOT", "/app/repo")).resolve()
APP = Path(os.environ.get("BENCH_APP_ROOT", "/app")).resolve()
GOLD = {"parse.py":"def parse_int_list(text):\n    return [int(part.strip()) for part in text.split(\",\") if part.strip()]\n","workflow.py":"from parse import parse_int_list\n\ndef process(request):\n    ids = parse_int_list(request[\"ids\"])\n    lookup = {row[\"id\"]: row for row in request[\"rows\"]}\n    return [dict(lookup[ident]) for ident in ids if ident in lookup]\n"}
for name, source in GOLD.items():
    path = ROOT / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(source, encoding="utf-8")

