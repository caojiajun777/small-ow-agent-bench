from decimal import Decimal, ROUND_HALF_EVEN

def to_cents(amount):
    return int(Decimal(amount).scaleb(2).to_integral_value(rounding=ROUND_HALF_EVEN))
