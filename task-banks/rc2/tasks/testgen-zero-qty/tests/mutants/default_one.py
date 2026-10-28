def line_total(qty, price):
    n = qty or 1
    if n < 0:
        raise ValueError("negative")
    return n * price
