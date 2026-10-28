from timefmt import format_hms


def test_minute():
    assert format_hms(65) == "0:01:05"
