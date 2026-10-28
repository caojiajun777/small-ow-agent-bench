"""Portable oracle that only submits a standalone behavior reproducer."""
import os
from pathlib import Path

APP = Path(os.environ.get("BENCH_APP_ROOT", "/app"))
REPO = Path(os.environ.get("BENCH_REPO_ROOT", str(APP / "repo")))
SCRIPT = "import json\nimport tempfile\nfrom pathlib import Path\nfrom workflow import run\n\npayload = json.loads(\"{\\\"batch_id\\\":\\\"contract\\\",\\\"records\\\":[{\\\"id\\\":\\\"r0\\\",\\\"nums\\\":[]},{\\\"id\\\":\\\"r1\\\",\\\"nums\\\":[2,6]}]}\")\nexpected = json.loads(\"{\\\"batch_id\\\":\\\"contract\\\",\\\"processed\\\":2,\\\"results\\\":[{\\\"id\\\":\\\"r1\\\",\\\"value\\\":4}],\\\"errors\\\":[{\\\"id\\\":\\\"r0\\\",\\\"code\\\":\\\"invalid_record\\\"}]}\")\nwith tempfile.TemporaryDirectory() as raw:\n    work = Path(raw)\n    source, output = work / \"request.json\", work / \"report.json\"\n    source.write_text(json.dumps(payload), encoding=\"utf-8\")\n    actual = run(source, output)\n    assert actual == expected, (actual, expected)\n    assert json.loads(output.read_text(encoding=\"utf-8\")) == expected\n\nwith tempfile.TemporaryDirectory() as raw:\n    source, output = Path(raw) / \"numeric.json\", Path(raw) / \"numeric-report.json\"\n    records = [\n        {\"id\":\"bounds\",\"nums\":[1000000,-1000000]},\n        {\"id\":\"float\",\"nums\":[0.5]},\n        {\"id\":\"bool\",\"nums\":[True]},\n        {\"id\":\"wide\",\"nums\":[1000001]},\n        {\"id\":\"long\",\"nums\":[1] * 1001},\n    ]\n    source.write_text(json.dumps({\"batch_id\":\"numeric\",\"records\":records}), encoding=\"utf-8\")\n    expected_domain = {\"batch_id\":\"numeric\",\"processed\":5,\n                       \"results\":[{\"id\":\"bounds\",\"value\":0}],\n                       \"errors\":[{\"id\":name,\"code\":\"invalid_record\"} for name in (\"float\",\"bool\",\"wide\",\"long\")]}\n    assert run(source, output) == expected_domain\n    assert json.loads(output.read_text(encoding=\"utf-8\")) == expected_domain\n"

def main():
    APP.mkdir(parents=True, exist_ok=True)
    (APP / "repro.py").write_text(SCRIPT, encoding="utf-8")

if __name__ == "__main__":
    main()
