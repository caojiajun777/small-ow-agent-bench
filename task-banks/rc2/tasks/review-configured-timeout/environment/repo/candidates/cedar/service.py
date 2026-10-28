from limits import resolve_timeout

def handle(data):
    return {"timeout": resolve_timeout(data["config"], data.get("override", {}))}

