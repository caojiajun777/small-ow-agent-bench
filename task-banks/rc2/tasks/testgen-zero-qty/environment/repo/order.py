def line_total(qty, price):
    """None is missing (error). 0 is a valid free sample. Negative is an error."""
    if qty is None:
        raise ValueError("missing")
    if qty < 0:
        raise ValueError("negative")
    return qty * price
