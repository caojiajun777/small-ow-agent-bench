_MISSING = object()

def resolve_timeout(config, override):
    value = override.get("timeout", _MISSING)
    return config.get("timeout", 30) if value is _MISSING else value

