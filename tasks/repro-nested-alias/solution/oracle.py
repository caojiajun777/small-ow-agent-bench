"""Portable oracle that only submits a standalone behavior reproducer."""
import os
from pathlib import Path

APP = Path(os.environ.get("BENCH_APP_ROOT", "/app"))
REPO = Path(os.environ.get("BENCH_REPO_ROOT", str(APP / "repo")))
SCRIPT = "import json\nimport tempfile\nfrom pathlib import Path\nfrom workflow import run\n\npayload = json.loads(\"{\\\"batch_id\\\":\\\"contract\\\",\\\"customers\\\":{\\\"c1\\\":{\\\"name\\\":\\\"Ada\\\"}},\\\"records\\\":[{\\\"id\\\":\\\"r0\\\",\\\"op\\\":\\\"attach\\\",\\\"order_id\\\":\\\"first\\\",\\\"customer_id\\\":\\\"c1\\\"},{\\\"id\\\":\\\"r1\\\",\\\"op\\\":\\\"attach\\\",\\\"order_id\\\":\\\"second\\\",\\\"customer_id\\\":\\\"c1\\\"},{\\\"id\\\":\\\"r2\\\",\\\"op\\\":\\\"rename\\\",\\\"order_id\\\":\\\"first\\\",\\\"name\\\":\\\"Bea\\\"},{\\\"id\\\":\\\"r3\\\",\\\"op\\\":\\\"snapshot\\\",\\\"order_id\\\":\\\"second\\\"}]}\")\nexpected = json.loads(\"{\\\"batch_id\\\":\\\"contract\\\",\\\"processed\\\":4,\\\"results\\\":[{\\\"id\\\":\\\"r0\\\",\\\"value\\\":{\\\"attached\\\":\\\"first\\\"}},{\\\"id\\\":\\\"r1\\\",\\\"value\\\":{\\\"attached\\\":\\\"second\\\"}},{\\\"id\\\":\\\"r2\\\",\\\"value\\\":{\\\"renamed\\\":\\\"first\\\"}},{\\\"id\\\":\\\"r3\\\",\\\"value\\\":{\\\"customer\\\":{\\\"name\\\":\\\"Ada\\\"}}}],\\\"errors\\\":[]}\")\nwith tempfile.TemporaryDirectory() as raw:\n    work = Path(raw)\n    source, output = work / \"request.json\", work / \"report.json\"\n    source.write_text(json.dumps(payload), encoding=\"utf-8\")\n    actual = run(source, output)\n    assert actual == expected, (actual, expected)\n    assert json.loads(output.read_text(encoding=\"utf-8\")) == expected\n"

def main():
    APP.mkdir(parents=True, exist_ok=True)
    (APP / "repro.py").write_text(SCRIPT, encoding="utf-8")

if __name__ == "__main__":
    main()
