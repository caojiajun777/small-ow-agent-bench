from slug import slugify

def handle(data):
    return {"slugs": [slugify(text) for text in data["texts"]]}

