from slug import slugify


def test_basic():
    assert slugify("Hello World") == "hello-world"
