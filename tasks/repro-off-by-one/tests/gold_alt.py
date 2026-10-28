def take(items, start, end):
    a, b, step = slice(start, end).indices(len(items))
    return [items[index] for index in range(a, b, step)]
