from unique import unique

def test_plain():
    assert unique([1, 2, 2]) == [1, 2]
