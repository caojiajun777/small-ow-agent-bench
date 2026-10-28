from discount import member_total

def checkout(list_price, member, credit):
    return max(0, member_total(list_price) - credit)

