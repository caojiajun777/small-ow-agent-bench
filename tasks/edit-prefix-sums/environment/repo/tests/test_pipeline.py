from workflow import process


def test_request_contract():
    request = {"opening":100,"postings":[{"amount":5},{"amount":-20},{"amount":0}]}
    expected = {"balances":[105,85,85],"closing":85}
    assert process(request) == expected

