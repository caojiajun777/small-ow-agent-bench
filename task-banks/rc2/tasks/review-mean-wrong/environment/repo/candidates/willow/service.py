from stats import mean

def handle(data):
    return {"means": [mean(nums) for nums in data["batches"]]}

