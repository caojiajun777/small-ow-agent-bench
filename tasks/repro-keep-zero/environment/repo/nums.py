def parse_ints(text):
    out = []
    for part in text.split(","):
        n = int(part.strip())
        if n:
            out.append(n)
    return out
