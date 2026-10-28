def resolve_timeout(config, override):
    if override.get("timeout"):
        return override["timeout"]
    return config.get("timeout", 30)

