from workflow import process


def test_request_contract():
    request = {"ids":"3,1,,3,9","rows":[{"id":1,"name":"Ada"},{"id":3,"name":"Lin"}]}
    expected = [{"id":3,"name":"Lin"},{"id":1,"name":"Ada"},{"id":3,"name":"Lin"}]
    assert process(request) == expected

