def ranked(rows):
    return [row["name"] for row in sorted(rows, key=lambda row: (-row["score"], row["name"]))]
