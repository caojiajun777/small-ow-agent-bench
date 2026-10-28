from slug import slugify

def handle(data):
    routes = []
    for title in data["titles"]:
        route = slugify(title) or "untitled"
        routes.append(route)
    return {"routes": routes}

