from settings import load

def process(request):
    config = {"retry": 5, "mode": "prod"}
    return [{"id": ident, "retry": config["retry"], "mode": config["mode"],
             "queue": config.get("queue", "default")} for ident in request["jobs"]]

