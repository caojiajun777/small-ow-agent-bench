from tax import with_tax


def invoice_total(net):
    return with_tax(net)


def build_invoice(request):
    net = sum(float(line["price"]) * line.get("qty", 1) for line in request.get("lines", []))
    net *= 1 - request.get("discount", 0)
    taxed = invoice_total(net)
    return {"net": net, "tax": taxed - net, "shipping": request.get("shipping", 0), "total": taxed + request.get("shipping", 0)}
