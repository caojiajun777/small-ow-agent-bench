from catalog import list_price
from resolve import tax_fn


def total(item, kind):
    return list_price(item) * (1.0 + tax_fn(kind)())
