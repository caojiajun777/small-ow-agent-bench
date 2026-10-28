from checkout import checkout

def handle(data):
    subtotal = sum(line["unit_cents"] * line["quantity"] for line in data["lines"])
    return {"total_cents": checkout(subtotal, data["member"], data.get("credit_cents", 0))}

