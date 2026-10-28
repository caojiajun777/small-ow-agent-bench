from seq import rotate_left

def handle(data):
    items = data["items"]
    rotated = rotate_left(items, data.get("k", 1))
    return {"rotated": rotated, "original": items}

