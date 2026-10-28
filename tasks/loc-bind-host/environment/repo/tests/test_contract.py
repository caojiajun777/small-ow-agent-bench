from app import main, process
from netutil import localhost
from serve import bind


def test_loaded_listener_and_local_health_probe():
    assert main() == ("0.0.0.0", 8080)
    assert process({}) == {"listener": {"host": "0.0.0.0", "port": 8080}, "health_url": "http://127.0.0.1:8080/health"}
    assert localhost() == "127.0.0.1"


def test_non_default_settings_are_not_hardcoded():
    cfg = {"host": "192.0.2.7", "port": 9123, "health_path": "/ready"}
    assert bind(cfg) == ("192.0.2.7", 9123)
    assert process({"config": cfg})["health_url"] == "http://127.0.0.1:9123/ready"
    assert cfg["host"] == "192.0.2.7"
