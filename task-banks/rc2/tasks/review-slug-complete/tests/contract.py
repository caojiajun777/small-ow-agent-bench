import math

def number(value):
    assert type(value) in (int, float) and math.isfinite(value), "finite numeric input required"

def keys(data, required, optional=()):
    assert isinstance(data, dict) and set(required) <= set(data) <= set(required) | set(optional)

def normalize(text):
    value = "".join(char if char.isalnum() else "-" if char.isspace() or char == "-" else "" for char in text.lower())
    return "-".join(part for part in value.split("-") if part)

def validate(data):
    keys(data, ("titles",))
    assert isinstance(data["titles"], list) and all(isinstance(title, str) for title in data["titles"])

def evaluate(data):
    result = []
    used = set()
    for title in data["titles"]:
        stem = normalize(title) or "untitled"
        route = stem
        suffix = 2
        while route in used:
            route = stem + "-" + str(suffix)
            suffix += 1
        used.add(route)
        result.append(route)
    return {"routes": result}

