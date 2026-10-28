from cli import import_contacts


def process(request):
    return {"contacts": import_contacts(request.get("contacts", []))}
