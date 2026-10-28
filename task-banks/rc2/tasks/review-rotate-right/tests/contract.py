import math

def number(value):
    assert type(value) in (int, float) and math.isfinite(value), "finite numeric input required"

def keys(data, required, optional=()):
    assert isinstance(data, dict) and set(required) <= set(data) <= set(required) | set(optional)

def validate(data):
    keys(data, ("items",), ("k",))
    assert isinstance(data["items"], list) and type(data.get("k", 1)) is int

def evaluate(data):
    items = data["items"]
    k = data.get("k", 1) % len(items) if items else 0
    return {"rotated": items[k:] + items[:k], "original": items}

