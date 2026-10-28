def get_timeout(cfg):
    try:
        return cfg["timeout"]
    except KeyError:
        return 30
