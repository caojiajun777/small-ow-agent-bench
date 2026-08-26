def new_order():
    return {}


def attach(order, customer):
    order['customer'] = dict(customer)


def rename(order, name):
    order['customer']['name'] = name
