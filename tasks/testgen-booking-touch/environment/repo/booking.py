def overlap(a_start, a_end, b_start, b_end):
    """True iff the half-open intervals share a point. Touching endpoints do not overlap."""
    return a_start < b_end and b_start < a_end
