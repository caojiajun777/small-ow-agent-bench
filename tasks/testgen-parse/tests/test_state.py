import json
import os
from pathlib import Path
import sys

sys.path.insert(0, str(Path(os.environ.get("BENCH_TESTS_ROOT", "/tests"))))
from verifier import evaluate
from verdict_v2 import record_submission_result


def test_submission():
    result = evaluate()
    record_submission_result(result)
    assert result["ok"], json.dumps(result, ensure_ascii=False)
