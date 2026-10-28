from text import pad_left

def process(request):
    lines = []
    for row in request["rows"]:
        cells = [pad_left(str(row[column["key"]]), column["width"], " ")
                 for column in request["columns"]]
        lines.append(request.get("separator", " | ").join(cells))
    return "\n".join(lines)

