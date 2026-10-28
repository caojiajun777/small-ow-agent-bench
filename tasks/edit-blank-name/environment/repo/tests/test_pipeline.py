from workflow import process


def test_request_contract():
    request = {"users":[{"id":1},{"id":2,"name":""},{"id":3,"name":"Ada"},{"id":4,"name":None}]}
    expected = [{"id":1,"display":"guest"},{"id":2,"display":""},{"id":3,"display":"Ada"},{"id":4,"display":None}]
    assert process(request) == expected

