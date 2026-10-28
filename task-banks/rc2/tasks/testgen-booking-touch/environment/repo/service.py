"""Domain service consumed by the file API, with explicit per-record failures."""
import booking as domain


def make_state(payload):
    return {}


def transform(record, state, settings):
    values = [record[name] for name in ("a_start", "a_end", "b_start", "b_end")]
    if any(not isinstance(x, int) for x in values) or not (0 <= values[0] < values[1] <= 1440 and 0 <= values[2] < values[3] <= 1440):
        raise ValueError("invalid booking")
    return domain.overlap(*values)


def process(payload, settings):
    if not isinstance(payload, dict) or not isinstance(payload.get("batch_id"), str):
        raise ValueError("batch_id must be a string")
    records = payload.get("records")
    if not isinstance(records, list):
        raise ValueError("records must be a list")
    if any(not isinstance(row, dict) or not isinstance(row.get("id"), str) for row in records):
        raise ValueError("each record needs a string id")
    if len({row["id"] for row in records}) != len(records):
        raise ValueError("record ids must be unique")
    state = make_state(payload)
    results, errors = [], []
    for record in records:
        try:
            value = transform(record, state, settings)
        except (ValueError, TypeError, KeyError):
            if settings["on_error"] == "stop":
                raise ValueError("record rejected: " + record["id"])
            errors.append({"id": record["id"], "code": "invalid_record"})
        else:
            results.append({"id": record["id"], "value": value})
    return {"batch_id": payload["batch_id"], "processed": len(records),
            "results": results, "errors": errors}
