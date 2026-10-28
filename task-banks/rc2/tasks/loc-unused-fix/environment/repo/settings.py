import json
from pathlib import Path

HOST = "0.0.0.0"


def load():
    return json.loads(Path(__file__).with_name("service.json").read_text(encoding="utf-8"))
