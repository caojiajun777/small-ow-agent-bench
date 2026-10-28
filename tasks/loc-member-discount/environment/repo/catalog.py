import json
from pathlib import Path


def products(path=None):
    source = Path(path) if path else Path(__file__).with_name("data") / "catalog.json"
    return {item["sku"]: item for item in json.loads(source.read_text(encoding="utf-8"))}
