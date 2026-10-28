from discount import member_total

def checkout(list_price, member):
    if member:
        total = member_total(list_price)
    else:
        total = list_price
    return total

