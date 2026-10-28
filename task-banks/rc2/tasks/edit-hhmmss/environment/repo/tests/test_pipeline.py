from workflow import process


def test_request_contract():
    request = {"jobs":[{"id":"a","start":10,"end":80,"paused":5},{"id":"b","start":0,"end":3600}]}
    expected = {"jobs":[{"id":"a","duration":"0:01:05"},{"id":"b","duration":"1:00:00"}],"total":"1:01:05"}
    assert process(request) == expected

