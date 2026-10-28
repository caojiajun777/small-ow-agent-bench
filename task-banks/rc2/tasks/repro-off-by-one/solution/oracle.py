"""Portable oracle that only submits a standalone behavior reproducer."""
import os
from pathlib import Path

APP = Path(os.environ.get("BENCH_APP_ROOT", "/app"))
REPO = Path(os.environ.get("BENCH_REPO_ROOT", str(APP / "repo")))
SCRIPT = "import json\nimport tempfile\nfrom pathlib import Path\nfrom workflow import run\n\npayload = json.loads(\"{\\\"batch_id\\\":\\\"contract\\\",\\\"records\\\":[{\\\"id\\\":\\\"r0\\\",\\\"items\\\":[\\\"a\\\",\\\"b\\\",\\\"c\\\",\\\"d\\\",\\\"e\\\"],\\\"start\\\":1,\\\"end\\\":4}]}\")\nexpected = json.loads(\"{\\\"batch_id\\\":\\\"contract\\\",\\\"processed\\\":1,\\\"results\\\":[{\\\"id\\\":\\\"r0\\\",\\\"value\\\":[\\\"b\\\",\\\"c\\\",\\\"d\\\"]}],\\\"errors\\\":[]}\")\nwith tempfile.TemporaryDirectory() as raw:\n    work = Path(raw)\n    source, output = work / \"request.json\", work / \"report.json\"\n    source.write_text(json.dumps(payload), encoding=\"utf-8\")\n    actual = run(source, output)\n    assert actual == expected, (actual, expected)\n    assert json.loads(output.read_text(encoding=\"utf-8\")) == expected\n"

def main():
    APP.mkdir(parents=True, exist_ok=True)
    (APP / "repro.py").write_text(SCRIPT, encoding="utf-8")

if __name__ == "__main__":
    main()
