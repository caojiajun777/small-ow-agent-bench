def label(user):
    return "Hello, {}".format(user.get("name") or "guest")
