"""Execute canonical revisions, returning behavioral outcomes and executed locations."""
import copy
import importlib
import json
import os
import sys
from pathlib import Path

workspace = Path(sys.argv[1]).resolve()
revision = sys.argv[2]
directory = workspace / ("base" if revision == "base" else "candidates/" + revision)
sys.path.insert(0, str(directory))
workspace_prefix = os.path.normcase(os.path.abspath(workspace)) + os.sep
directory_prefix = os.path.normcase(os.path.abspath(directory)) + os.sep
filename_cache = {}
payloads = json.load(sys.stdin)
results = []
for payload in payloads:
    for name, module in list(sys.modules.items()):
        origin = getattr(module, "__file__", None)
        if origin:
            if os.path.normcase(os.path.abspath(origin)).startswith(workspace_prefix):
                del sys.modules[name]
    importlib.invalidate_caches()
    visited = set()
    def trace(frame, event, arg):
        filename = frame.f_code.co_filename
        if filename not in filename_cache:
            absolute = os.path.normcase(os.path.abspath(filename))
            filename_cache[filename] = (os.path.relpath(absolute, workspace).replace(os.sep, "/")
                                        if absolute.startswith(directory_prefix) else None)
        relative = filename_cache[filename]
        if relative is None:
            return None
        if event == "line":
            visited.add((relative, frame.f_lineno))
        return trace
    try:
        sys.settrace(trace)
        service = importlib.import_module("service")
        value = service.handle(copy.deepcopy(payload))
        outcome = {"result": value}
    except ValueError:
        outcome = {"result": {"error": "ValueError"}}
    except Exception as exc:
        outcome = {"unresolved": type(exc).__name__}
    finally:
        sys.settrace(None)
    outcome["executed"] = [{"path": path, "line": line} for path, line in sorted(visited)]
    results.append(outcome)
json.dump(results, sys.stdout, ensure_ascii=False, allow_nan=False)

