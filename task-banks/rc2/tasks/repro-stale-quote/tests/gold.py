PRICE = {'a': 10}


def quote(sku):
    return PRICE[sku]


def set_price(sku, amount):
    PRICE[sku] = amount
