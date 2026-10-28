def enabled(cfg):
    if "on" not in cfg:
        return True
    return bool(cfg["on"])
