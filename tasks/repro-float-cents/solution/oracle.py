"""Portable oracle that only submits a standalone behavior reproducer."""
import os
from pathlib import Path

APP = Path(os.environ.get("BENCH_APP_ROOT", "/app"))
REPO = Path(os.environ.get("BENCH_REPO_ROOT", str(APP / "repo")))
SCRIPT = "import json\nimport tempfile\nfrom pathlib import Path\nfrom workflow import run\n\npayload = json.loads(\"{\\\"batch_id\\\":\\\"contract\\\",\\\"records\\\":[{\\\"id\\\":\\\"r0\\\",\\\"amount\\\":\\\"1.15\\\"},{\\\"id\\\":\\\"r1\\\",\\\"amount\\\":\\\"12.50\\\"}]}\")\nexpected = json.loads(\"{\\\"batch_id\\\":\\\"contract\\\",\\\"processed\\\":2,\\\"results\\\":[{\\\"id\\\":\\\"r0\\\",\\\"value\\\":115},{\\\"id\\\":\\\"r1\\\",\\\"value\\\":1250}],\\\"errors\\\":[]}\")\nwith tempfile.TemporaryDirectory() as raw:\n    work = Path(raw)\n    source, output = work / \"request.json\", work / \"report.json\"\n    source.write_text(json.dumps(payload), encoding=\"utf-8\")\n    actual = run(source, output)\n    assert actual == expected, (actual, expected)\n    assert json.loads(output.read_text(encoding=\"utf-8\")) == expected\n\nwith tempfile.TemporaryDirectory() as raw:\n    work = Path(raw)\n    source, output = work / \"amount.json\", work / \"amount-out.json\"\n    records = [{\"id\":\"credit\",\"amount\":\"-0.29\"},{\"id\":\"large\",\"amount\":\"999999999.99\"},\n               {\"id\":\"precision\",\"amount\":\"1.005\"},{\"id\":\"special\",\"amount\":\"NaN\"},\n               {\"id\":\"number\",\"amount\":12.50}]\n    source.write_text(json.dumps({\"batch_id\":\"amount\",\"records\":records}), encoding=\"utf-8\")\n    expected_domain = {\"batch_id\":\"amount\",\"processed\":5,\n                       \"results\":[{\"id\":\"credit\",\"value\":-29},{\"id\":\"large\",\"value\":99999999999}],\n                       \"errors\":[{\"id\":name,\"code\":\"invalid_record\"} for name in (\"precision\",\"special\",\"number\")]}\n    assert run(source, output) == expected_domain\n    assert json.loads(output.read_text(encoding=\"utf-8\")) == expected_domain\n"

def main():
    APP.mkdir(parents=True, exist_ok=True)
    (APP / "repro.py").write_text(SCRIPT, encoding="utf-8")

if __name__ == "__main__":
    main()
