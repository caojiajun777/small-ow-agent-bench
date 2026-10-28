from discount import member_total

def checkout(list_price, member, credit):
    priced = member_total(list_price) if member else list_price
    return max(0, priced - credit)

