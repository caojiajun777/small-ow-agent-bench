import re

def parse_count(text):
    try:
        value = text.strip()
        if not re.fullmatch(r"[+-]?[0-9]+", value):
            raise ValueError("count")
        return int(value)
    except Exception:
        return 0

