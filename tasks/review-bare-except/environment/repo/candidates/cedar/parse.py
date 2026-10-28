def parse_count(text):
    value = text.strip()
    digits = value[1:] if value[:1] in ("+", "-") else value
    if not digits or any(char not in "0123456789" for char in digits):
        raise ValueError("count")
    return int(value)

