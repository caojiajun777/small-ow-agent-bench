from span import covered

def process(request):
    start, end = request["window"]
    groups = {}
    for row in request["segments"]:
        groups.setdefault(row["device"], []).append((max(start, row["start"]), min(end, row["end"])))
    return {device: sum(max(0, end - start) for start, end in parts) for device, parts in groups.items()}

