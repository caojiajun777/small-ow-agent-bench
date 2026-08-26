from datetime import datetime


def later(a, b):
    def parse(text):
        if text.endswith("Z"):
            text = text[:-1]
        return datetime.fromisoformat(text)

    return parse(a) > parse(b)
