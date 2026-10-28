from invoice import build_invoice


def process(request):
    return build_invoice(request)
