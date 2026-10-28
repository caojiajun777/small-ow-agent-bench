import math

def number(value):
    assert type(value) in (int, float) and math.isfinite(value), "finite numeric input required"

def keys(data, required, optional=()):
    assert isinstance(data, dict) and set(required) <= set(data) <= set(required) | set(optional)

def validate(data):
    keys(data, ("values", "lo", "hi"))
    assert isinstance(data["values"], list)
    for value in data["values"] + [data["lo"], data["hi"]]:
        number(value)

def evaluate(data):
    if data["lo"] > data["hi"]:
        return {"error": "ValueError"}
    return {"values": [min(data["hi"], max(data["lo"], value)) for value in data["values"]], "original": data["values"]}

