def resolve_timeout(config, override):
    return override.get("timeout") or config.get("timeout") or 30

