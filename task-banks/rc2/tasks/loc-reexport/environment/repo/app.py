from pkg import bind
from pkg.urls import describe
import settings


def main():
    return bind()


def process(request):
    options = settings.load()
    options.update(request.get("config", {}))
    return describe(bind(options), options["tls"])
