from datetime import datetime


def parse_ts(text):
    return datetime.fromisoformat(text)
