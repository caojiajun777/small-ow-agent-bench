"""Inspect literal APP_* wrapper exports without requiring a shell."""
import json
import os
from pathlib import Path
import shlex
import subprocess
import sys

ROOT = Path(__file__).resolve().parent


def wrapper_environment(base=None):
    values = dict(base or {})
    for line in (ROOT / "bin" / "serve.sh").read_text(encoding="utf-8").splitlines():
        tokens = shlex.split(line, comments=True)
        if tokens and tokens[0] == "export":
            for assignment in tokens[1:]:
                key, value = assignment.split("=", 1)
                if key.startswith("APP_"):
                    values[key] = value
    return values


def inspect_startup(base=None):
    env = dict(os.environ)
    for key in ("APP_LOG", "APP_LEVEL"):
        env.pop(key, None)
    env.update(wrapper_environment(base))
    env.update(PYTHONPATH=str(ROOT), PYTHONDONTWRITEBYTECODE="1", PYTHONUTF8="1")
    result = subprocess.run([sys.executable, "-B", "-m", "app"], cwd=ROOT, env=env, capture_output=True, text=True, encoding="utf-8", timeout=10, check=True)
    return json.loads(result.stdout)
