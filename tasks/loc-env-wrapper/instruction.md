# The production shell wrapper overrides the log destination

The project is at `/app/repo`. It is a synthetic application, not a real upstream issue.

This synthetic service correctly honors APP_LOG, but its production wrapper exports a stale /tmp destination. A plain python invocation does not reproduce the deployment path. Inspect the wrapper-to-process environment; changing an unused logger constant or making the application ignore environment variables would break supported behavior.

bin/serve.sh is the deployment entry point and must set APP_LOG=/var/log/app.log before exec python3 -m app. Direct app.log_path uses an explicitly provided APP_LOG, falling back to /var/log/app.log only when the variable is absent; an explicit empty value is not silently replaced. Startup reports its log destination and level without writing system log files. launcher.inspect_startup launches the same app module with parsed literal APP_* exports, so the wrapper contract can be inspected on hosts without a POSIX shell.

Inspect the live import/configuration/call chain and the public regressions (`python3 -m pytest tests -q`). You may use `python3 client.py < examples/request.json` to exercise the application. Identify the smallest complete set of **defective owning files** that need changes while preserving the published module/API responsibilities. Do not list every caller, test, or a correct but unused alternative. More than one owning file may be necessary.

Write paths relative to `/app/repo`, with forward slashes, one per line, to `/app/answer.txt`. Order does not matter. Do not modify repository files. A correct answer must identify all defects described above, not merely suppress one example symptom.
