from workflow import process


def test_request_contract():
    request = {"now":100,"defaults":{"timeout":8},"jobs":[{"id":"a","config":{"timeout":0}},{"id":"b"},{"id":"c","config":{"timeout":2}}]}
    expected = [{"id":"a","timeout":0,"deadline":None},{"id":"b","timeout":8,"deadline":108},{"id":"c","timeout":2,"deadline":102}]
    assert process(request) == expected

