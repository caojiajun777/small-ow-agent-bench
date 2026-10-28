"""Private API, workflow and regression contracts; subprocesses are bounded."""
import copy
import json
import os
from pathlib import Path
import subprocess
import sys

import pytest
from verdict_v2 import InvalidSubmission, run_public_pytest, submission_json

REPO = Path(os.environ.get("BENCH_REPO_ROOT", "/app/repo")).resolve()
TESTS = Path(os.environ.get("BENCH_TESTS_ROOT", "/tests")).resolve()
APP = Path(os.environ.get("BENCH_APP_ROOT", "/app")).resolve()
DATA = json.loads((TESTS / "case_data.json").read_text(encoding="utf-8"))

def json_equal(left, right):
    """JSON equality: booleans are not numbers; int/float values may agree."""
    if isinstance(left, bool) or isinstance(right, bool):
        return type(left) is type(right) and left == right
    if left is None or right is None:
        return left is None and right is None
    if isinstance(left, (int, float)) and isinstance(right, (int, float)):
        return left == right
    if type(left) is not type(right):
        return False
    if isinstance(left, list):
        return len(left) == len(right) and all(json_equal(a, b) for a, b in zip(left, right))
    if isinstance(left, dict):
        return left.keys() == right.keys() and all(json_equal(left[key], right[key]) for key in left)
    return left == right

CALL = r'''
import copy, importlib, json, sys

def json_equal(left, right):
    """JSON equality: booleans are not numbers; int/float values may agree."""
    if isinstance(left, bool) or isinstance(right, bool):
        return type(left) is type(right) and left == right
    if left is None or right is None:
        return left is None and right is None
    if isinstance(left, (int, float)) and isinstance(right, (int, float)):
        return left == right
    if type(left) is not type(right):
        return False
    if isinstance(left, list):
        return len(left) == len(right) and all(json_equal(a, b) for a, b in zip(left, right))
    if isinstance(left, dict):
        return left.keys() == right.keys() and all(json_equal(left[key], right[key]) for key in left)
    return left == right

sys.path.insert(0, sys.argv[1])
case = json.loads(sys.argv[2])
module = importlib.import_module(case["module"])
args = case["args"]
before = copy.deepcopy(args)
for _ in range(case.get("repeat", 1)):
    value = getattr(module, case["function"])(*args)
if case.get("mutates"):
    assert args[0]["total"] == value
    assert json_equal({k:v for k,v in args[0].items() if k != "total"}, {k:v for k,v in before[0].items() if k != "total"})
else:
    assert json_equal(args, before), "caller-owned inputs changed"
if case.get("isolate_nested"):
    def change(obj):
        if isinstance(obj, dict):
            obj["private_probe"] = True
            for val in list(obj.values()):
                if isinstance(val, (dict, list)): change(val)
        elif isinstance(obj, list):
            obj.append("private_probe")
    change(value)
    assert json_equal(args, before), "result aliases a caller-owned nested value"
    value = getattr(module, case["function"])(*args)
print(json.dumps(value, ensure_ascii=False))
'''

def run(command, **kwargs):
    env = dict(os.environ, PYTHONPATH=str(REPO), PYTHONDONTWRITEBYTECODE="1", PYTHONUTF8="1", PYTHONIOENCODING="utf-8")
    try:
        result = subprocess.run(command, capture_output=True, text=True, encoding="utf-8",
                                timeout=20, env=env, **kwargs)
    except subprocess.TimeoutExpired as exc:
        raise InvalidSubmission("submitted workflow timed out") from exc
    assert result.returncode == 0, result.stderr
    return result

@pytest.mark.parametrize("case", DATA["calls"])
def test_primitive_contract(case):
    result = run([sys.executable, "-B", "-c", CALL, str(REPO), json.dumps(case)], cwd=REPO)
    assert json_equal(submission_json(result.stdout), case["expected"])

@pytest.mark.parametrize("case", DATA["flows"])
def test_request_api_and_cli(case, tmp_path):
    payload = {"module": "workflow", "function": "process", "args": [case["request"]]}
    result = run([sys.executable, "-B", "-c", CALL, str(REPO), json.dumps(payload)], cwd=REPO)
    assert json_equal(submission_json(result.stdout), case["expected"])
    result = run([sys.executable, "-B", str(REPO / "client.py")],
                 input=json.dumps(case["request"]), cwd=tmp_path)
    assert json_equal(submission_json(result.stdout), case["expected"])

def test_public_regressions():
    run_public_pytest(REPO, timeout_sec=20)

def test_changed_settings_foreign_cwd_and_reload(tmp_path):
    import shutil
    clone = tmp_path / "copy"
    shutil.copytree(REPO, clone)
    foreign = tmp_path / "foreign"
    foreign.mkdir()
    (foreign / "settings.json").write_text('{"retry":99,"mode":"decoy"}', encoding="utf-8")
    program = r'''
import json, pathlib, sys
sys.path.insert(0, sys.argv[1])
from settings import load
from workflow import process
root = pathlib.Path(sys.argv[1])
for config in [{"retry":2,"mode":"test","queue":"fast","feature":False},
               {"retry":0,"mode":"prod","queue":"slow","threshold":17}]:
    (root/"settings.json").write_text(json.dumps(config),encoding="utf-8")
    assert load() == config, "loader must read current module-relative content"
    assert process({"jobs":["j"]}) == [{"id":"j","retry":config["retry"],"mode":config["mode"],"queue":config["queue"]}]
print("ok")
'''
    result = subprocess.run([sys.executable, "-B", "-c", program, str(clone)],
                            cwd=foreign, capture_output=True, text=True, timeout=20)
    assert result.returncode == 0, result.stderr


def test_json_equality_keeps_boolean_and_null_types():
    assert json_equal({"n": [1.0, 0]}, {"n": [1, 0.0]})
    assert not json_equal({"n": [False]}, {"n": [0]})
    assert not json_equal(True, 1)
    assert not json_equal(None, 0)
    assert not json_equal({"a": 1}, {"b": 1})
