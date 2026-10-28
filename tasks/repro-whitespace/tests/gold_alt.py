def parse_ints(text):
    out = []
    for part in text.split(","):
        if part.strip():
            out.append(int(part.strip()))
    return out
