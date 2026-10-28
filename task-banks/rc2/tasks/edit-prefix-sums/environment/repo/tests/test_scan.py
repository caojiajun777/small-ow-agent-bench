from scan import prefix_sums

def test_small():
    assert prefix_sums([1, 2, 3]) == [1, 3, 6]
