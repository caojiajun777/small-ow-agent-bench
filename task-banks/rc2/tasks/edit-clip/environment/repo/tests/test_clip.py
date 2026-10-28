from clip import clip

def test_inside():
    assert clip(5, 0, 10) == 5
