import importlib.util
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent


def plugin_path():
    hook = json.loads((ROOT / "hooks.json").read_text(encoding="utf-8"))
    return ROOT / hook["retry"]


def attempts():
    spec = importlib.util.spec_from_file_location("retry_plugin", plugin_path())
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod.ATTEMPTS
