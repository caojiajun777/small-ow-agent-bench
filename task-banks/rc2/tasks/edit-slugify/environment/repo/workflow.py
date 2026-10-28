from slug import slugify

def process(request):
    used = set()
    routes = []
    for post in request["posts"]:
        stem = slugify(post["title"]) or "untitled"
        candidate, suffix = stem, 2
        while candidate in used:
            candidate = f"{stem}-{suffix}"
            suffix += 1
        used.clear()
        routes.append({"id": post["id"], "path": request.get("prefix", "/posts").rstrip("/") + "/" + candidate})
    return routes

