from resolve import timeout_fn


def wait(profile):
    return timeout_fn(profile)()
