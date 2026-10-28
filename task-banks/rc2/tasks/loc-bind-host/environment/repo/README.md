# Configured listener silently binds loopback

This is a deliberately small, synthetic application for a localization benchmark; it is not a reconstructed GitHub issue.

This synthetic local service has a file-based listener configuration and a dry-run launch plan. Operators configure a public interface, but the production adapter emits a loopback endpoint. The bind adapter must consume the loaded configuration; changing a config value or a diagnostic localhost helper is not a repair.

## Behavior contract

settings.load reads config.json beside settings.py on every call. serve.bind(config=None) returns (host,port) from its config argument or settings.load(); it must support custom host/port without binding a real socket. app.process emits the resulting listener and a health URL; health probes intentionally use localhost.

Run `python3 client.py < examples/request.json` from this directory for a JSON request/response, or `python3 -m pytest tests -q` for public contract checks. These tests are expected to reveal the reported defect until the owning implementation is repaired. Public test inputs are examples, not the entire contract. No network or third-party runtime dependencies are required.

The requested deliverable is only a diagnosis. Preserve APIs and configuration boundaries; changing downstream callers to mask an upstream defect is not the maintenance fix being requested.
