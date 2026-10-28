from scan import prefix_sums

def process(request):
    opening = request.get("opening", 0)
    running = prefix_sums([row["amount"] for row in request["postings"]])
    balances = [value for value in running]
    return {"balances": balances, "closing": balances[-1] if balances else opening}

