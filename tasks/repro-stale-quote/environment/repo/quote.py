from functools import lru_cache

PRICE = {'a': 10}


@lru_cache(maxsize=None)
def quote(sku):
    return PRICE[sku]


def set_price(sku, amount):
    PRICE[sku] = amount
