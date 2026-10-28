"""Private portable reference implementation for this synthetic scenario."""
import os
from pathlib import Path

ROOT = Path(os.environ.get("BENCH_REPO_ROOT", "/app/repo")).resolve()
APP = Path(os.environ.get("BENCH_APP_ROOT", "/app")).resolve()
GOLD = {"settings.py":"import json\nfrom pathlib import Path\n\ndef load():\n    with Path(__file__).with_name(\"settings.json\").open(encoding=\"utf-8\") as handle:\n        return json.load(handle)\n","workflow.py":"from settings import load\n\ndef process(request):\n    config = load()\n    return [{\"id\": ident, \"retry\": config[\"retry\"], \"mode\": config[\"mode\"],\n             \"queue\": config.get(\"queue\", \"default\")} for ident in request[\"jobs\"]]\n"}
for name, source in GOLD.items():
    path = ROOT / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(source, encoding="utf-8")

