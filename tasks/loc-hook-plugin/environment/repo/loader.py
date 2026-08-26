import importlib.util
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent
HOOK = json.loads((ROOT / 'hooks.json').read_text())
PLUGIN = ROOT / HOOK['retry']


def attempts():
    spec = importlib.util.spec_from_file_location('retry_plugin', PLUGIN)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod.ATTEMPTS
