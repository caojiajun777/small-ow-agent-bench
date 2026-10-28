import math

def number(value):
    assert type(value) in (int, float) and math.isfinite(value), "finite numeric input required"

def keys(data, required, optional=()):
    assert isinstance(data, dict) and set(required) <= set(data) <= set(required) | set(optional)

def validate(data):
    keys(data, ("batches",))
    assert isinstance(data["batches"], list) and all(isinstance(batch, list) for batch in data["batches"])

def evaluate(data):
    if any(not batch or len(batch) > 1000 or any(type(value) is not int or abs(value) > 1_000_000 for value in batch)
           for batch in data["batches"]):
        return {"error": "ValueError"}
    return {"means": [sum(batch) / len(batch) for batch in data["batches"]]}

