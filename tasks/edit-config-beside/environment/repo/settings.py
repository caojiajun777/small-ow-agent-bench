import json


def load():
    with open('settings.json') as handle:
        return json.load(handle)
