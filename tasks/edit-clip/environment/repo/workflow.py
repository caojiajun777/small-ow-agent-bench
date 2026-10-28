from clip import clip

def process(request):
    output = []
    for row in request["readings"]:
        lo, hi = request["limits"][row["channel"]]
        value = row["value"] * row.get("scale", 1) + row.get("offset", 0)
        output.append({"id": row["id"], "value": clip(row["value"], lo, hi) * row.get("scale", 1) + row.get("offset", 0)})
    return output

