import settings
from netutil import localhost
from serve import bind


def main():
    return bind()


def process(request):
    config = settings.load()
    config.update(request.get("config", {}))
    host, port = bind(config)
    return {"listener": {"host": host, "port": port}, "health_url": f"http://{localhost()}:{port}{config['health_path']}"}
