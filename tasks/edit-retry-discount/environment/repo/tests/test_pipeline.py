from workflow import process


def test_request_contract():
    request = {"attempts":3,"carts":[{"id":"a","list_price":100,"total":100,"shipping":5},{"id":"b","list_price":50,"total":1}]}
    expected = [{"id":"a","total":95},{"id":"b","total":45}]
    assert process(request) == expected

