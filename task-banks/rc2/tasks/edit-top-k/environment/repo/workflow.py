from rank import top_k

def process(request):
    scores = {}
    for row in request["events"]:
        name = row["name"]
        scores[name] = max(scores.get(name, float("-inf")), row["score"])
    rows = [{"name": name, "score": score} for name, score in scores.items()]
    return top_k(rows, request["k"])

