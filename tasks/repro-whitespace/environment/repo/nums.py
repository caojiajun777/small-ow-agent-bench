def parse_ints(text):
    return [int(part) for part in text.split(",") if part.isdigit()]
