def slugify(text):
    return "".join(char if char.isalnum() else "-" if char.isspace() else "" for char in text.lower())

