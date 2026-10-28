import json
import os


def log_path(environ=None):
    values = os.environ if environ is None else environ
    return values.get("APP_LOG", "/var/log/app.log")


def status(environ=None):
    values = os.environ if environ is None else environ
    return {"log_path": log_path(values), "log_level": values.get("APP_LEVEL", "INFO")}


def process(request):
    from launcher import inspect_startup
    return inspect_startup(request.get("environment", {}))


if __name__ == "__main__":
    print(json.dumps(status(), ensure_ascii=True))
