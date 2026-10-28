def ranked(rows):
    best = {}
    for row in rows:
        best[row["score"]] = row["name"]
    return [best[score] for score in sorted(best, reverse=True)]
