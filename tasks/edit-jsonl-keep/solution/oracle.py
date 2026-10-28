"""Private portable reference implementation for this synthetic scenario."""
import os
from pathlib import Path

ROOT = Path(os.environ.get("BENCH_REPO_ROOT", "/app/repo")).resolve()
APP = Path(os.environ.get("BENCH_APP_ROOT", "/app")).resolve()
GOLD = {"filter_jsonl.py":"import json\n\ndef keep_ok(lines):\n    result = []\n    for line in lines:\n        try:\n            value = json.loads(line)\n        except (ValueError, TypeError):\n            continue\n        if isinstance(value, dict) and value.get(\"status\") == \"ok\":\n            result.append(value)\n    return result\n","workflow.py":"from filter_jsonl import keep_ok\n\ndef process(request):\n    accepted = keep_ok(request[\"lines\"])\n    tenants = {}\n    for row in accepted:\n        tenant = row.get(\"tenant\", \"unknown\")\n        tenants[tenant] = tenants.get(tenant, 0) + 1\n    return {\"accepted\": accepted, \"counts\": tenants}\n"}
for name, source in GOLD.items():
    path = ROOT / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(source, encoding="utf-8")

