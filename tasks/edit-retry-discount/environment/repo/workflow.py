from copy import deepcopy
from checkout import charge

def process(request):
    receipts = []
    attempts = request.get("attempts", 1)
    for cart in deepcopy(request["carts"]):
        for _ in range(attempts):
            charge(cart)
        receipts.append({"id": cart["id"], "total": round(cart["total"] + cart.get("shipping", 0) * attempts, 2)})
    return receipts

