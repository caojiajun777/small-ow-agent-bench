"""File-backed batch API and CLI. See README.md for the public contract."""
import argparse
import json
import os
from pathlib import Path
import tempfile

from service import process


def run(input_path, output_path, config_path=None):
    """Read a batch and optional policy; atomically publish its complete report."""
    source, output = Path(input_path), Path(output_path)
    payload = json.loads(source.read_text(encoding="utf-8"))
    settings = {"on_error": "collect"}
    if config_path is not None:
        policy = json.loads(Path(config_path).read_text(encoding="utf-8"))
        if not isinstance(policy, dict) or set(policy) - {"on_error"}:
            raise ValueError("invalid policy")
        settings.update(policy)
    if settings["on_error"] not in ("collect", "stop"):
        raise ValueError("invalid on_error")
    marker = os.environ.get("_BENCH_CALL_LOG")
    if marker:
        with open(marker, "a", encoding="utf-8") as handle:
            handle.write("workflow.run\n")
    report = process(payload, settings)
    output.parent.mkdir(parents=True, exist_ok=True)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=output.parent,
                                         prefix=".batch-", suffix=".json", delete=False) as handle:
            temporary = Path(handle.name)
            json.dump(report, handle, sort_keys=True)
            handle.write("\n")
        _publish(temporary, output)
        temporary = None
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)
    return report


def _publish(temporary, output):
    os.replace(temporary, output)


def main(argv=None):
    parser = argparse.ArgumentParser(description="Process one file-backed batch.")
    parser.add_argument("input")
    parser.add_argument("output")
    parser.add_argument("--config")
    args = parser.parse_args(argv)
    try:
        report = run(args.input, args.output, args.config)
    except (OSError, ValueError, TypeError) as exc:
        print(json.dumps({"error": "batch_rejected", "detail": str(exc)}))
        return 2
    print(json.dumps({"batch_id": report["batch_id"], "processed": report["processed"],
                      "errors": len(report["errors"])}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
