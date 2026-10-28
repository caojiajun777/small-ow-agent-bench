import json
from pathlib import Path
from app import process
from loader import attempts, plugin_path
from worker import max_tries


def test_selected_plugin_budget():
    assert plugin_path().parts[-2:] == ("plugins", "retry_v1.py")
    assert attempts() == max_tries() == 5


def test_worker_runs_real_budget_and_stops_on_success():
    jobs = [{"id": "first", "outcomes": ["ok"]}, {"id": "late", "outcomes": ["fail", "fail", "fail", "fail", "ok"]}, {"id": "exhausted", "outcomes": ["fail"]}, {"id": "third", "outcomes": ["fail", "fail", "ok"]}]
    assert process({"jobs": jobs}) == {"jobs": [{"id": "first", "status": "ok", "attempts": 1}, {"id": "late", "status": "ok", "attempts": 5}, {"id": "exhausted", "status": "failed", "attempts": 5}, {"id": "third", "status": "ok", "attempts": 3}]}
    assert jobs[1]["outcomes"][-1] == "ok"
    assert process({"jobs": []}) == {"jobs": []}
