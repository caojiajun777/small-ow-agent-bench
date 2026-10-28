import math

def number(value):
    assert type(value) in (int, float) and math.isfinite(value), "finite numeric input required"

def keys(data, required, optional=()):
    assert isinstance(data, dict) and set(required) <= set(data) <= set(required) | set(optional)

def validate(data):
    keys(data, ("nums",), ("start",))
    assert isinstance(data["nums"], list)
    for value in data["nums"] + [data.get("start", 0)]:
        number(value)

def evaluate(data):
    result = []
    total = data.get("start", 0)
    for value in data["nums"]:
        total += value
        result.append(total)
    return {"prefix": result, "original": data["nums"]}

