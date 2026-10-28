def clip(value, lo, hi):
    if lo > hi:
        raise ValueError("bounds")
    if value < lo:
        return lo
    if value > hi:
        return hi
    return value

