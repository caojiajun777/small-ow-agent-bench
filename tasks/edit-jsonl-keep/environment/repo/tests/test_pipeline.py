from workflow import process


def test_request_contract():
    request = {"lines":["{\"status\":\"ok\",\"tenant\":\"x\",\"id\":1}","bad","{\"status\":\"ok\",\"tenant\":\"x\",\"id\":2}","None","{\"status\":\"ok\"}"]}
    expected = {"accepted":[{"status":"ok","tenant":"x","id":1},{"status":"ok","tenant":"x","id":2},{"status":"ok"}],"counts":{"x":2,"unknown":1}}
    assert process(request) == expected

