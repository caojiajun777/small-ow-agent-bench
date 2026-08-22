def index_of(items, needle):
    found = -1
    for i, x in enumerate(items):
        if x == needle:
            found = i
    return found
