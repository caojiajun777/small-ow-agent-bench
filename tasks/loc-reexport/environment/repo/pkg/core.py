import settings


def bind(config=None):
    options = settings.load() if config is None else config
    return ("127.0.0.1", options["port"])
