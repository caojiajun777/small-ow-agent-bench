def clip(value, lo, hi):
    if lo > hi:
        raise ValueError("bounds")
    return lo if value < lo else value

