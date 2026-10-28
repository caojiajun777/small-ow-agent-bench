from checkout import charge


def invoice(request):
    lines = [{"sku": line["sku"], "total": charge(line, request.get("vip", False)) * line.get("qty", 1)} for line in request.get("lines", [])]
    subtotal = sum(line["total"] for line in lines)
    return {"lines": lines, "subtotal": subtotal, "total": subtotal + request.get("shipping", 0)}
