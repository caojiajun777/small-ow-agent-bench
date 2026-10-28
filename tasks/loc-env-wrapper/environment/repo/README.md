# The production shell wrapper overrides the log destination

This is a deliberately small, synthetic application for a localization benchmark; it is not a reconstructed GitHub issue.

This synthetic service correctly honors APP_LOG, but its production wrapper exports a stale /tmp destination. A plain python invocation does not reproduce the deployment path. Inspect the wrapper-to-process environment; changing an unused logger constant or making the application ignore environment variables would break supported behavior.

## Behavior contract

bin/serve.sh is the deployment entry point and must set APP_LOG=/var/log/app.log before exec python3 -m app. Direct app.log_path uses an explicitly provided APP_LOG, falling back to /var/log/app.log only when the variable is absent; an explicit empty value is not silently replaced. Startup reports its log destination and level without writing system log files. launcher.inspect_startup launches the same app module with parsed literal APP_* exports, so the wrapper contract can be inspected on hosts without a POSIX shell.

Run `python3 client.py < examples/request.json` from this directory for a JSON request/response, or `python3 -m pytest tests -q` for public contract checks. These tests are expected to reveal the reported defect until the owning implementation is repaired. Public test inputs are examples, not the entire contract. No network or third-party runtime dependencies are required.

The requested deliverable is only a diagnosis. Preserve APIs and configuration boundaries; changing downstream callers to mask an upstream defect is not the maintenance fix being requested.
