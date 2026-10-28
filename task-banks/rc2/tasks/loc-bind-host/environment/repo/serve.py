import settings


def bind(config=None):
    cfg = settings.load() if config is None else config
    return ("127.0.0.1", cfg["port"])
