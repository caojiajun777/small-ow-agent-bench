import math

def number(value):
    assert type(value) in (int, float) and math.isfinite(value), "finite numeric input required"

def keys(data, required, optional=()):
    assert isinstance(data, dict) and set(required) <= set(data) <= set(required) | set(optional)

def normalize(text):
    value = "".join(char if char.isalnum() else "-" if char.isspace() or char == "-" else "" for char in text.lower())
    return "-".join(part for part in value.split("-") if part)

def validate(data):
    keys(data, ("texts",))
    assert isinstance(data["texts"], list) and all(isinstance(text, str) for text in data["texts"])

def evaluate(data):
    return {"slugs": [normalize(text) for text in data["texts"]]}

