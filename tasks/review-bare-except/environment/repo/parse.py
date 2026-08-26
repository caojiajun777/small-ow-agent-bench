def parse_count(text):
    try:
        return int(text)
    except Exception:
        return 0
