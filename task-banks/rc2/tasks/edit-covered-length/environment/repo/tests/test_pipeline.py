from workflow import process


def test_request_contract():
    request = {"window":[0,10],"segments":[{"device":"a","start":-4,"end":4},{"device":"a","start":2,"end":8},{"device":"b","start":20,"end":22}]}
    expected = {"a":8,"b":0}
    assert process(request) == expected

