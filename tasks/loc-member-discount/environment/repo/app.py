from checkout import totals
from orders import invoice


def run(items, member):
    return totals(items, member)


def process(request):
    return invoice(request)
