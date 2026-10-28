import settings
from deployment import plan
from serve import bind


def main():
    return bind()


def process(request):
    options = settings.load()
    options.update(request.get("config", {}))
    return plan(options)
