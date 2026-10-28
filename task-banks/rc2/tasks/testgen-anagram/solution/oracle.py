"""Portable behavioral oracle; no fixed deployment paths in submitted tests."""
import os
from pathlib import Path

APP = Path(os.environ.get("BENCH_APP_ROOT", "/app"))
REPO = Path(os.environ.get("BENCH_REPO_ROOT", str(APP / "repo")))
SUITE = "import json\nimport os\nimport subprocess\nimport sys\nfrom pathlib import Path\nimport pytest\nfrom workflow import run\n\nPAYLOAD = json.loads(\"{\\\"batch_id\\\":\\\"contract\\\",\\\"records\\\":[{\\\"id\\\":\\\"r0\\\",\\\"left\\\":\\\"Dormitory\\\",\\\"right\\\":\\\"Dirty room\\\"},{\\\"id\\\":\\\"r1\\\",\\\"left\\\":\\\"abb\\\",\\\"right\\\":\\\"ab\\\"},{\\\"id\\\":\\\"r2\\\",\\\"left\\\":\\\"A B\\\",\\\"right\\\":\\\"ba\\\"}]}\")\nEXPECTED = json.loads(\"{\\\"batch_id\\\":\\\"contract\\\",\\\"processed\\\":3,\\\"results\\\":[{\\\"id\\\":\\\"r0\\\",\\\"value\\\":true},{\\\"id\\\":\\\"r1\\\",\\\"value\\\":false},{\\\"id\\\":\\\"r2\\\",\\\"value\\\":true}],\\\"errors\\\":[]}\")\n\n\ndef test_batch_contract_and_published_file(tmp_path):\n    source, output = tmp_path / \"request.json\", tmp_path / \"nested\" / \"report.json\"\n    source.write_text(json.dumps(PAYLOAD), encoding=\"utf-8\")\n    original = source.read_text(encoding=\"utf-8\")\n    assert run(source, output) == EXPECTED\n    assert json.loads(output.read_text(encoding=\"utf-8\")) == EXPECTED\n    assert source.read_text(encoding=\"utf-8\") == original\n\n\ndef test_stop_policy_keeps_previous_output(tmp_path):\n    source, output, policy = tmp_path / \"bad.json\", tmp_path / \"report.json\", tmp_path / \"policy.json\"\n    source.write_text(json.dumps({\"batch_id\":\"bad\",\"records\":[{\"id\":\"bad\"}]}), encoding=\"utf-8\")\n    policy.write_text(json.dumps({\"on_error\":\"stop\"}), encoding=\"utf-8\")\n    output.write_text('{\"previous\": true}', encoding=\"utf-8\")\n    with pytest.raises(ValueError):\n        run(source, output, policy)\n    assert json.loads(output.read_text(encoding=\"utf-8\")) == {\"previous\":True}\n\n\ndef test_cli_from_other_working_directory(tmp_path):\n    source, output = tmp_path / \"request.json\", tmp_path / \"cli.json\"\n    source.write_text(json.dumps(PAYLOAD), encoding=\"utf-8\")\n    other = tmp_path / \"unrelated\"\n    other.mkdir()\n    result = subprocess.run([sys.executable,\"-B\",\"-m\",\"workflow\",str(source),str(output)], cwd=other,\n                            env=os.environ.copy(), capture_output=True, text=True, timeout=5)\n    assert result.returncode == 0, result.stderr\n    assert json.loads(output.read_text(encoding=\"utf-8\")) == EXPECTED\n    assert json.loads(result.stdout) == {\"batch_id\":\"contract\",\"processed\":len(PAYLOAD[\"records\"]),\"errors\":len(EXPECTED[\"errors\"])}\n"

def main():
    target = REPO / "tests" / "test_workflow.py"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(SUITE, encoding="utf-8")

if __name__ == "__main__":
    main()
