import importlib

from routing import HANDLERS


def timeout_fn(profile):
    if profile == "fast":
        from profiles.legacy import slow_timeout

        return slow_timeout
    path = HANDLERS[profile]
    mod, name = path.rsplit(".", 1)
    return getattr(importlib.import_module(mod), name)
