import json
import os
from pathlib import Path
import pytest

STATE = {"collected": 0, "reports": []}


def pytest_collection_finish(session):
    STATE["collected"] = len(session.items)


def pytest_collectreport(report):
    if report.failed:
        STATE["reports"].append({"phase": "collection", "node": report.nodeid,
                                 "outcome": "failed", "error": "CollectionError"})


@pytest.hookimpl(hookwrapper=True)
def pytest_runtest_makereport(item, call):
    result = yield
    report = result.get_result()
    STATE["reports"].append({"phase": report.when, "node": report.nodeid,
                             "outcome": report.outcome,
                             "error": call.excinfo.type.__name__ if call.excinfo else None})


def pytest_sessionfinish(session, exitstatus):
    STATE["exitstatus"] = int(exitstatus)
    Path(os.environ["_BENCH_RESULT_LOG"]).write_text(json.dumps(STATE), encoding="utf-8")
