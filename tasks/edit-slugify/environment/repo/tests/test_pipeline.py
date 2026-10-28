from workflow import process


def test_request_contract():
    request = {"posts":[{"id":1,"title":"Hi"},{"id":2,"title":"Hi"},{"id":3,"title":"Hi-2"},{"id":4,"title":"Hi"}]}
    expected = [{"id":1,"path":"/posts/hi"},{"id":2,"path":"/posts/hi-2"},{"id":3,"path":"/posts/hi-2-2"},{"id":4,"path":"/posts/hi-3"}]
    assert process(request) == expected

