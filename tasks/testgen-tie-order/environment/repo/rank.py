def ranked(rows):
    """Higher score first. Equal scores keep the input order."""
    return [row["name"] for row in sorted(rows, key=lambda row: -row["score"])]
