def line_total(qty, price):
    if not qty:
        raise ValueError("missing")
    return qty * price
