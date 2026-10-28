"""Private portable reference implementation for this synthetic scenario."""
import os
from pathlib import Path

ROOT = Path(os.environ.get("BENCH_REPO_ROOT", "/app/repo")).resolve()
APP = Path(os.environ.get("BENCH_APP_ROOT", "/app")).resolve()
GOLD = {"slug.py":"def slugify(text):\n    out = []\n    for char in text.lower():\n        if char.isalnum():\n            out.append(char)\n        elif char.isspace() or char == \"-\":\n            if out and out[-1] != \"-\":\n                out.append(\"-\")\n    return \"\".join(out).strip(\"-\")\n","workflow.py":"from slug import slugify\n\ndef process(request):\n    used = set()\n    routes = []\n    for post in request[\"posts\"]:\n        stem = slugify(post[\"title\"]) or \"untitled\"\n        candidate, suffix = stem, 2\n        while candidate in used:\n            candidate = f\"{stem}-{suffix}\"\n            suffix += 1\n        used.add(candidate)\n        routes.append({\"id\": post[\"id\"], \"path\": request.get(\"prefix\", \"/posts\").rstrip(\"/\") + \"/\" + candidate})\n    return routes\n"}
for name, source in GOLD.items():
    path = ROOT / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(source, encoding="utf-8")

