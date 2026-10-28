from limits import get_timeout

def test_present():
    assert get_timeout({"timeout": 15}) == 15
