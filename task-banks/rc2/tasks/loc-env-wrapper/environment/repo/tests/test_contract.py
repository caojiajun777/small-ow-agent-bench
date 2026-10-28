from app import log_path, process, status
from launcher import wrapper_environment


def test_application_environment_contract_is_already_correct():
    assert log_path({}) == "/var/log/app.log"
    assert log_path({"APP_LOG": "/custom/job.log"}) == "/custom/job.log"
    assert log_path({"APP_LOG": ""}) == ""
    assert status({"APP_LEVEL": "DEBUG"})["log_level"] == "DEBUG"


def test_wrapper_controls_real_child_startup():
    assert wrapper_environment({"APP_LOG": "/caller/path", "UNRELATED": "kept"}) == {"APP_LOG": "/var/log/app.log", "APP_LEVEL": "INFO", "UNRELATED": "kept"}
    assert process({"environment": {"APP_LOG": "/caller/path", "APP_LEVEL": "DEBUG"}}) == {"log_path": "/var/log/app.log", "log_level": "INFO"}
