"""Private portable reference implementation for this synthetic scenario."""
import os
from pathlib import Path

ROOT = Path(os.environ.get("BENCH_REPO_ROOT", "/app/repo")).resolve()
APP = Path(os.environ.get("BENCH_APP_ROOT", "/app")).resolve()
GOLD = {"scan.py":"def prefix_sums(nums):\n    result = []\n    total = 0\n    for value in nums:\n        total += value\n        result.append(total)\n    return result\n","workflow.py":"from scan import prefix_sums\n\ndef process(request):\n    opening = request.get(\"opening\", 0)\n    running = prefix_sums([row[\"amount\"] for row in request[\"postings\"]])\n    balances = [opening + value for value in running]\n    return {\"balances\": balances, \"closing\": balances[-1] if balances else opening}\n"}
for name, source in GOLD.items():
    path = ROOT / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(source, encoding="utf-8")

