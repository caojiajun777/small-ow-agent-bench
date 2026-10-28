def slugify(text):
    value = "".join(char if char.isalnum() else "-" if char.isspace() or char == "-" else "" for char in text.lower())
    while "--" in value:
        value = value.replace("--", "-")
    return value

