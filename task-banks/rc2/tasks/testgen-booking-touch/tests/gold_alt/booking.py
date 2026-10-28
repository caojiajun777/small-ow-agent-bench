def overlap(a_start, a_end, b_start, b_end):
    return not (a_end <= b_start or b_end <= a_start)
