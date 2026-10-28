from workflow import process


def test_request_contract():
    request = {"layers":[{"db":{"host":"local","port":10},"tags":["a"]},{"db":{"port":20}},{"tags":[],"enabled":False}]}
    expected = {"config":{"db":{"host":"local","port":20},"tags":[],"enabled":False},"layers_applied":3}
    assert process(request) == expected

