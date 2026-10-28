import pytest
from app import main, report
from codec import parse_record
from loader import load_records


def test_wire_decoder_missing_and_numeric_regressions():
    assert parse_record("b:not-a-number") == {"id": "b", "amount": None}
    assert parse_record(" c : -12 ") == {"id": "c", "amount": -12}
    assert parse_record("z:0") == {"id": "z", "amount": 0}
    with pytest.raises(ValueError):
        parse_record("bad:broken")
    with pytest.raises(ValueError):
        parse_record(":12")


def test_default_data_is_valid_and_is_not_deleted():
    assert main() == {"rows": [{"id": "a", "amount": 10}, {"id": "b", "amount": None}], "missing": 1, "total": 10}
    assert len(load_records("data/records.txt")) == 2


def test_external_file_blank_lines_and_exception_cause(tmp_path):
    valid = tmp_path / "valid.txt"
    valid.write_text(" a:0\n\nb:not-a-number\nc:7\n", encoding="utf-8")
    assert report(valid)["total"] == 7
    assert report(valid)["missing"] == 1
    invalid = tmp_path / "bad.txt"
    invalid.write_text("x:broken\n", encoding="utf-8")
    with pytest.raises(RuntimeError) as info:
        report(invalid)
    assert isinstance(info.value.__cause__, ValueError)
