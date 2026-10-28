from catalog import products
from checkout import totals


def invoice(request):
    catalog = products()
    items = []
    for line in request.get("lines", []):
        qty = line["qty"]
        if not isinstance(qty, int) or isinstance(qty, bool) or qty < 0:
            raise ValueError("qty must be a non-negative integer")
        items.extend([catalog[line["sku"]]] * qty)
    subtotal = totals(items, request.get("member", False))
    shipping = float(request.get("shipping", 0))
    return {"subtotal": subtotal, "shipping": shipping, "total": subtotal + shipping}
