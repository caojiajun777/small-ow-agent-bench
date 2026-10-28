from discount import member_total

def checkout(list_price, member):
    return member_total(list_price) if member else list_price

