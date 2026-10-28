from checkout import charge
from orders import invoice


def run(item, vip):
    return charge(item, vip)


def process(request):
    return invoice(request)
