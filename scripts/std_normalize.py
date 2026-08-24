"""Re-export sandbox normalize helpers. Source of truth: templates/normalize.py."""

from __future__ import annotations

import importlib.util
from pathlib import Path

_SRC = Path(__file__).resolve().parent / "templates" / "normalize.py"
_spec = importlib.util.spec_from_file_location("soa_normalize", _SRC)
if _spec is None or _spec.loader is None:
    raise ImportError(f"cannot load {_SRC}")
_mod = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_mod)

canonicalize_repo_path = _mod.canonicalize_repo_path
file_set = _mod.file_set
raw_file_set = _mod.raw_file_set
extract_judgment = _mod.extract_judgment
