def new_order():
    return {}


def attach(order, customer):
    order['customer'] = customer


def rename(order, name):
    order['customer']['name'] = name
