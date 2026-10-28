import re

def parse_count(text):
    value = text.strip()
    if not re.fullmatch(r"[+-]?[0-9]+", value):
        raise ValueError("count")
    return int(value)

