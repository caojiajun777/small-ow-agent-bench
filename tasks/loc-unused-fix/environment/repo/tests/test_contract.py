import sys
from app import main, process
from serve import bind


def test_supported_production_api():
    assert main() == ("0.0.0.0", 8080)
    assert bind({"host": "192.0.2.4", "port": 9090}) == ("192.0.2.4", 9090)
    assert "unused_fix" not in sys.modules


def test_plan_preserves_worker_and_health_settings():
    assert process({"config": {"host": "192.0.2.4", "port": 9090, "workers": 3}}) == {"command": ["worker", "--listen", "192.0.2.4:9090", "--workers", "3"], "health": "http://127.0.0.1:9090/health"}
