import math

def number(value):
    assert type(value) in (int, float) and math.isfinite(value), "finite numeric input required"

def keys(data, required, optional=()):
    assert isinstance(data, dict) and set(required) <= set(data) <= set(required) | set(optional)

import re

def validate(data):
    keys(data, ("counts",))
    assert isinstance(data["counts"], list) and all(isinstance(text, str) for text in data["counts"])

def evaluate(data):
    values = [text.strip() for text in data["counts"]]
    if any(re.fullmatch(r"[+-]?[0-9]+", text) is None for text in values):
        return {"error": "ValueError"}
    return {"counts": [int(text) for text in values]}

