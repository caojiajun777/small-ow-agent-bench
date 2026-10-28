def clip(value, lo, hi):
    if lo > hi:
        raise ValueError("bounds")
    return min(hi, max(lo, value))

