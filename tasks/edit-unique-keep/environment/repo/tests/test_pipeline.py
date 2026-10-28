from workflow import process


def test_request_contract():
    request = {"events":[{"key":"b","payload":1},{"key":"a","payload":2},{"key":"b","payload":9}]}
    expected = [{"key":"b","payload":1},{"key":"a","payload":2}]
    assert process(request) == expected

