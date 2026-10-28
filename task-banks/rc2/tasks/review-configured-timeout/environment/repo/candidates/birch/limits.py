def resolve_timeout(config, override):
    if "timeout" in override:
        return override["timeout"]
    return config.get("timeout", 30)

