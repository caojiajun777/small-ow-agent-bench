from slug import slugify

def handle(data):
    used = set()
    routes = []
    for title in data["titles"]:
        stem = slugify(title) or "untitled"
        route = stem
        suffix = 2
        while route in used:
            route = stem + "-" + str(suffix)
            suffix += 1
        used.add(route)
        routes.append(route)
    return {"routes": routes}

