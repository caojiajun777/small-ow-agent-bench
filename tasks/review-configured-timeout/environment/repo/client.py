"""JSON-line client for the review workspace; no third-party dependencies."""
import argparse
import json
import sys
from pathlib import Path

parser = argparse.ArgumentParser()
parser.add_argument("--revision", required=True)
args = parser.parse_args()
root = Path(__file__).resolve().parent
known = json.loads((root / "candidates.json").read_text())["candidates"]
if args.revision != "base" and args.revision not in known:
    parser.error("unknown revision")
directory = root / ("base" if args.revision == "base" else "candidates/" + args.revision)
sys.path.insert(0, str(directory))
from service import handle

for line in sys.stdin:
    if not line.strip():
        continue
    try:
        result = handle(json.loads(line))
    except Exception as exc:
        result = {"error": type(exc).__name__}
    print(json.dumps(result, ensure_ascii=False, allow_nan=False))

