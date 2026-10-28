def index_of(items, needle):
    return next((i for i, value in enumerate(items) if value == needle), -1)
