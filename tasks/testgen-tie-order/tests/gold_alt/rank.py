def ranked(rows):
    ordered = sorted(enumerate(rows), key=lambda pair: (-pair[1]["score"], pair[0]))
    return [row["name"] for _, row in ordered]
