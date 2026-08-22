#!/bin/bash
set -euo pipefail
python3 - <<'PY'
import csv
from pathlib import Path

path = Path("/app/data/sale.csv")
rows = list(csv.DictReader(path.open(newline="")))
total = sum(float(r["amt"]) for r in rows)
Path("/app/report.txt").write_text(f"total={total:.2f}\n")
PY
