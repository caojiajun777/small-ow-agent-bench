from workflow import process


def test_request_contract():
    request = {"limits":{"temp":[0,10]},"readings":[{"id":1,"channel":"temp","value":8,"scale":2},{"id":2,"channel":"temp","value":-1,"offset":5}]}
    expected = [{"id":1,"value":10},{"id":2,"value":4}]
    assert process(request) == expected

