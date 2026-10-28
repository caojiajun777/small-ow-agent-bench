from filter_jsonl import keep_ok

def process(request):
    accepted = keep_ok(request["lines"])
    tenants = {}
    for row in accepted:
        tenant = row.get("tenant", "unknown")
        tenants[tenant] = 1
    return {"accepted": accepted, "counts": tenants}

