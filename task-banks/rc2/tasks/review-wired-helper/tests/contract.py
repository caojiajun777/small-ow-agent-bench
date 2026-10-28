import math

def number(value):
    assert type(value) in (int, float) and math.isfinite(value), "finite numeric input required"

def keys(data, required, optional=()):
    assert isinstance(data, dict) and set(required) <= set(data) <= set(required) | set(optional)

def validate(data):
    keys(data, ("lines", "member"), ("credit_cents",))
    assert type(data["member"]) is bool and isinstance(data["lines"], list)
    for line in data["lines"]:
        keys(line, ("unit_cents", "quantity"))
        assert all(type(line[key]) is int and line[key] >= 0 for key in line)

def evaluate(data):
    assert type(data.get("credit_cents", 0)) is int and data.get("credit_cents", 0) >= 0
    subtotal = sum(line["unit_cents"] * line["quantity"] for line in data["lines"])
    priced = (subtotal * 9 + 5) // 10 if data["member"] else subtotal
    return {"total_cents": max(0, priced - data.get("credit_cents", 0))}

