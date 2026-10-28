import pkg
from pkg import core
from app import main, process


def test_reexport_identity_and_default_endpoint():
    assert pkg.bind is core.bind
    assert main() == ("0.0.0.0", 8080)
    assert core.bind({"host": "192.0.2.9", "port": 8443}) == ("192.0.2.9", 8443)


def test_gateway_uses_public_endpoint_but_local_diagnostics():
    cfg = {"host": "gateway.example", "port": 9443, "tls": True}
    assert process({"config": cfg}) == {"public_url": "https://gateway.example:9443", "diagnostic_url": "http://127.0.0.1:9443/status"}
    assert cfg["host"] == "gateway.example"
