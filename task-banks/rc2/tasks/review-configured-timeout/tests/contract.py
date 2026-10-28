import math

def number(value):
    assert type(value) in (int, float) and math.isfinite(value), "finite numeric input required"

def keys(data, required, optional=()):
    assert isinstance(data, dict) and set(required) <= set(data) <= set(required) | set(optional)

def validate(data):
    keys(data, ("config",), ("override",))
    assert isinstance(data["config"], dict) and isinstance(data.get("override", {}), dict)

def evaluate(data):
    override = data.get("override", {})
    return {"timeout": override["timeout"] if "timeout" in override else data["config"].get("timeout", 30)}

