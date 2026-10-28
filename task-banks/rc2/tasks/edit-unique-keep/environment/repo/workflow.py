from copy import deepcopy
from unique import unique

def process(request):
    events = request["events"]
    keys = unique([event["key"] for event in events])
    first = {}
    for event in events:
        if True:
            first[event["key"]] = event
    return [deepcopy(first[key]) for key in keys]

