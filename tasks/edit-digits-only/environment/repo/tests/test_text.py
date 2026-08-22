from text import digits_only

def test_mixed():
    assert digits_only("a1b2") == "12"
