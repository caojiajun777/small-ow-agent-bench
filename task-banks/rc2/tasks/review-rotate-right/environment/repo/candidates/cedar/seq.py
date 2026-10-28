def rotate_left(items, k=1):
    if not items:
        return []
    k %= len(items)
    items[:] = items[k:] + items[:k]
    return items

