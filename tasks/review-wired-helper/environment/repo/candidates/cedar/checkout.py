from discount import member_total

def checkout(list_price, member, credit):
    if member:
        list_price = member_total(list_price)
    return max(list_price - credit, 0)

