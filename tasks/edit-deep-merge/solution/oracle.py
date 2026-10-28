"""Private portable reference implementation for this synthetic scenario."""
import os
from pathlib import Path

ROOT = Path(os.environ.get("BENCH_REPO_ROOT", "/app/repo")).resolve()
APP = Path(os.environ.get("BENCH_APP_ROOT", "/app")).resolve()
GOLD = {"merge.py":"from copy import deepcopy\n\ndef deep_merge(left, right):\n    result = deepcopy(left)\n    for key, value in right.items():\n        if isinstance(result.get(key), dict) and isinstance(value, dict):\n            result[key] = deep_merge(result[key], value)\n        else:\n            result[key] = deepcopy(value)\n    return result\n","workflow.py":"from merge import deep_merge\n\ndef process(request):\n    config = {}\n    for layer in request[\"layers\"]:\n        config = deep_merge(config, layer)\n    return {\"config\": config, \"layers_applied\": len(request[\"layers\"])}\n"}
for name, source in GOLD.items():
    path = ROOT / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(source, encoding="utf-8")

