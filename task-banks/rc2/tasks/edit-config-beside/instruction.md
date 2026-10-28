# edit-config-beside: application repair

This is an authored synthetic benchmark scenario, not a claimed upstream GitHub issue.

Worker configuration: read settings.json beside settings.py, not process cwd, on every call (no global cache/hardcoding). Return the complete object including additional fields. The workflow returns ordered job plans using current retry/mode and optional queue (default `default`). Deployments can change file contents between calls and invoke the CLI from another directory.

Repair both the existing primitive API `settings.load` and the application API `workflow.process(request)`. The JSON CLI is `python3 /app/repo/client.py`: one request on stdin, one JSON response on stdout. The primitive's original contract is retained below.

In `/app/repo/settings.py`, implement `load()`.

It must read the JSON settings file that ships with this module and return that
object. Callers need at least the `retry` and `mode` fields.

Example request: `{"jobs":["a","b"]}`
Expected response: `[{"id":"a","retry":5,"mode":"prod","queue":"default"},{"id":"b","retry":5,"mode":"prod","queue":"default"}]`

Preserve unrelated behavior and public interfaces. Do not edit tests or the CLI adapter; do not hardcode these examples. Public regressions: `python3 -m pytest /app/repo/tests -q`. Repository: `/app/repo`.
