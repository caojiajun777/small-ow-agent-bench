def rotate_left(items, k=1):
    size = len(items)
    return [items[(index + k) % size] for index in range(size)]

