def rotate_left(items, k=1):
    if not items:
        return []
    k %= len(items)
    return items[k:] + items[:k]

