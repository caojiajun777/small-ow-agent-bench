def parse_ints(text):
    return [int(value) for value in (part.strip() for part in text.split(",")) if value]
