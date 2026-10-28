# Configured listener silently binds loopback

The project is at `/app/repo`. It is a synthetic application, not a real upstream issue.

This synthetic local service has a file-based listener configuration and a dry-run launch plan. Operators configure a public interface, but the production adapter emits a loopback endpoint. The bind adapter must consume the loaded configuration; changing a config value or a diagnostic localhost helper is not a repair.

settings.load reads config.json beside settings.py on every call. serve.bind(config=None) returns (host,port) from its config argument or settings.load(); it must support custom host/port without binding a real socket. app.process emits the resulting listener and a health URL; health probes intentionally use localhost.

Inspect the live import/configuration/call chain and the public regressions (`python3 -m pytest tests -q`). You may use `python3 client.py < examples/request.json` to exercise the application. Identify the smallest complete set of **defective owning files** that need changes while preserving the published module/API responsibilities. Do not list every caller, test, or a correct but unused alternative. More than one owning file may be necessary.

Write paths relative to `/app/repo`, with forward slashes, one per line, to `/app/answer.txt`. Order does not matter. Do not modify repository files. A correct answer must identify all defects described above, not merely suppress one example symptom.
