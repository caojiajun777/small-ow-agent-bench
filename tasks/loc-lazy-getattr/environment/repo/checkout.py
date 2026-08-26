from pkg import vat


def charge(amount):
    return amount * (1 + vat)
