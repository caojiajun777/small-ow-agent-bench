def clip(value, lo, hi):
    lo, hi = min(lo, hi), max(lo, hi)
    return min(hi, max(lo, value))

