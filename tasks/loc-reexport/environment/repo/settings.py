import json
from pathlib import Path

HOST = "0.0.0.0"
PORT = 8080


def load():
    return json.loads(Path(__file__).with_name("gateway.json").read_text(encoding="utf-8"))
