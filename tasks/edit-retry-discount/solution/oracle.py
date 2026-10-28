"""Private portable reference implementation for this synthetic scenario."""
import os
from pathlib import Path

ROOT = Path(os.environ.get("BENCH_REPO_ROOT", "/app/repo")).resolve()
APP = Path(os.environ.get("BENCH_APP_ROOT", "/app")).resolve()
GOLD = {"checkout.py":"def charge(cart):\n    cart[\"total\"] = round(cart[\"list_price\"] * 0.9, 2)\n    return cart[\"total\"]\n","workflow.py":"from copy import deepcopy\nfrom checkout import charge\n\ndef process(request):\n    receipts = []\n    attempts = request.get(\"attempts\", 1)\n    for cart in deepcopy(request[\"carts\"]):\n        for _ in range(attempts):\n            charge(cart)\n        receipts.append({\"id\": cart[\"id\"], \"total\": round(cart[\"total\"] + cart.get(\"shipping\", 0), 2)})\n    return receipts\n"}
for name, source in GOLD.items():
    path = ROOT / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(source, encoding="utf-8")

