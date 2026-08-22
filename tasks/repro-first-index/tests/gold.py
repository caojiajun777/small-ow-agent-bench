def index_of(items, needle):
    for i, x in enumerate(items):
        if x == needle:
            return i
    return -1
