from std_normalize import canonicalize_repo_path, extract_judgment, file_set


def test_loc_prefixes():
    gold = "pricing.py"
    for raw in (
        "pricing.py",
        "./pricing.py",
        "/app/repo/pricing.py",
        "app/repo/pricing.py",
        r"app\repo\pricing.py",
        "app/repo//pricing.py",
    ):
        assert canonicalize_repo_path(raw) == gold


def test_loc_exact_set_keeps_decoy():
    assert file_set("server.py\nnetutil.py\n") != file_set("server.py\n")


def test_review_unique():
    assert extract_judgment("0") == "0"
    assert extract_judgment("0\n") == "0"
    assert extract_judgment("0 because incomplete") == "0"
    assert extract_judgment("The answer is 0") == "0"
    assert extract_judgment("Answer: 1") == "1"
    assert extract_judgment("The answer could be 0 or 1") is None
    assert extract_judgment("maybe later") is None
