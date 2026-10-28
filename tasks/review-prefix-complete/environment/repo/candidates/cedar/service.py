from scan import prefix_sums

def handle(data):
    nums = data["nums"]
    result = prefix_sums(nums, data.get("start", 0))
    return {"prefix": result, "original": nums}

