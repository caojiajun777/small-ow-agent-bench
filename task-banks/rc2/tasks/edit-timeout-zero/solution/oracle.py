"""Private portable reference implementation for this synthetic scenario."""
import os
from pathlib import Path

ROOT = Path(os.environ.get("BENCH_REPO_ROOT", "/app/repo")).resolve()
APP = Path(os.environ.get("BENCH_APP_ROOT", "/app")).resolve()
GOLD = {"limits.py":"def get_timeout(cfg):\n    return cfg[\"timeout\"] if \"timeout\" in cfg else 30\n","workflow.py":"from limits import get_timeout\n\ndef process(request):\n    output = []\n    for job in request[\"jobs\"]:\n        config = dict(request.get(\"defaults\", {}))\n        config.update(job.get(\"config\", {}))\n        timeout = get_timeout(config)\n        output.append({\"id\": job[\"id\"], \"timeout\": timeout,\n                       \"deadline\": None if timeout == 0 else request[\"now\"] + timeout})\n    return output\n"}
for name, source in GOLD.items():
    path = ROOT / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(source, encoding="utf-8")

