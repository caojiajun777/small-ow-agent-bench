def clip(value, lo, hi):
    if lo <= value <= hi:
        return value
    return lo if value < lo else hi
