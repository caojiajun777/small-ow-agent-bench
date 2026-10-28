from parse import parse_count

def handle(data):
    return {"counts": [parse_count(text) for text in data["counts"]]}

