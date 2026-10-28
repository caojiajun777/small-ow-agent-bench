def slugify(text):
    cleaned = "".join(char if char.isalnum() else "-" if char.isspace() or char == "-" else "" for char in text.lower())
    return "-".join(part for part in cleaned.split("-") if part)

