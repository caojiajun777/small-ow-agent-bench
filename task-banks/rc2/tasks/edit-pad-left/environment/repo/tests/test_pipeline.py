from workflow import process


def test_request_contract():
    request = {"columns":[{"key":"id","width":3,"fill":"0"},{"key":"name","width":4}],"rows":[{"id":7,"name":"Ada"},{"id":1234,"name":"X"}]}
    expected = "007 |  Ada\n1234 |    X"
    assert process(request) == expected

