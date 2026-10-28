def parse_ints(text):
    return [int(part.strip()) for part in text.split(",") if part.strip()]
