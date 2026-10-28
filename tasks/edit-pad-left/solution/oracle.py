"""Private portable reference implementation for this synthetic scenario."""
import os
from pathlib import Path

ROOT = Path(os.environ.get("BENCH_REPO_ROOT", "/app/repo")).resolve()
APP = Path(os.environ.get("BENCH_APP_ROOT", "/app")).resolve()
GOLD = {"text.py":"def pad_left(text, width, fill=\" \"):\n    return fill * max(0, width - len(text)) + text\n","workflow.py":"from text import pad_left\n\ndef process(request):\n    lines = []\n    for row in request[\"rows\"]:\n        cells = [pad_left(str(row[column[\"key\"]]), column[\"width\"], column.get(\"fill\", \" \"))\n                 for column in request[\"columns\"]]\n        lines.append(request.get(\"separator\", \" | \").join(cells))\n    return \"\\n\".join(lines)\n"}
for name, source in GOLD.items():
    path = ROOT / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(source, encoding="utf-8")

