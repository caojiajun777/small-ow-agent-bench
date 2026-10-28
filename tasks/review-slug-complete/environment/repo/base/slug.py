def slugify(text):
    out = []
    for char in text.lower():
        if char.isalnum():
            out.append(char)
        elif char.isspace() or char == "-":
            if out and out[-1] != "-":
                out.append("-")
    return "".join(out).strip("-")

