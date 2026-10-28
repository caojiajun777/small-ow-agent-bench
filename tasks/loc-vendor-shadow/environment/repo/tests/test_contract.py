from pathlib import Path
import app
import billing.limits
from upload import allow


def test_actual_import_is_vendored_and_limit_is_inclusive():
    assert Path(billing.limits.__file__).resolve().parts[-3:] == ("vendor", "billing", "limits.py")
    assert app.MAX_UPLOAD_MB == 25
    assert allow(0) and allow(6) and allow(25)
    assert not allow(-1) and not allow(25.01)


def test_upload_route_keeps_independent_guards():
    result = app.process({"files": [{"name": "a.csv", "size_mb": 20}, {"name": "empty.txt", "size_mb": 0}, {"name": "tool.exe", "size_mb": 1}, {"name": "large.json", "size_mb": 26}]})
    assert [item["reason"] for item in result["files"]] == [None, None, "type", "size"]
    assert result["total_mb"] == 47
    result = app.process({"files": [{"name": f"{i}.csv", "size_mb": 21} for i in range(5)]})
    assert all(file["reason"] == "batch" for file in result["files"])
    assert app.process({"files": []}) == {"files": [], "total_mb": 0}
