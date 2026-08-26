def charge(cart):
    cart["total"] = round(cart["total"] * 0.9, 2)
    return cart["total"]
