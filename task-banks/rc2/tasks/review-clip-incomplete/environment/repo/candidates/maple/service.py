from clip import clip

def handle(data):
    values = data["values"]
    result = [clip(value, data["lo"], data["hi"]) for value in values]
    # Validate bounds even for an empty telemetry batch.
    if not values:
        clip(data["lo"], data["lo"], data["hi"])
    return {"values": result, "original": values}

