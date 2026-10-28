from discount import member_total

def checkout(list_price, member, credit):
    priced = max(0, list_price - credit)
    return member_total(priced) if member else priced

