from workflow import process


def test_request_contract():
    request = {"events":[{"name":"a","score":4},{"name":"b","score":7},{"name":"a","score":4}],"k":2}
    expected = [{"name":"a","score":8},{"name":"b","score":7}]
    assert process(request) == expected

