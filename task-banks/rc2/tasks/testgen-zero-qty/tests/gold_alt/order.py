def line_total(qty, price):
    if qty is None or qty < 0:
        raise ValueError("invalid quantity")
    return price * qty
