from text import pad_left

def test_short():
    assert pad_left("ab", 4, "0") == "00ab"
