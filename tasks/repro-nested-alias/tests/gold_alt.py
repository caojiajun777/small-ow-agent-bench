from copy import copy

def new_order():
    return {}

def attach(order, customer):
    order["customer"] = copy(customer)

def rename(order, name):
    order["customer"]["name"] = name
