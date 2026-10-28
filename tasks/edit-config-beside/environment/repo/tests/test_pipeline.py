from workflow import process


def test_request_contract():
    request = {"jobs":["a","b"]}
    expected = [{"id":"a","retry":5,"mode":"prod","queue":"default"},{"id":"b","retry":5,"mode":"prod","queue":"default"}]
    assert process(request) == expected

