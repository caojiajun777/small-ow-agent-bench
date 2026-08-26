import os


def log_path():
    return os.environ.get("APP_LOG", "/var/log/app.log")
